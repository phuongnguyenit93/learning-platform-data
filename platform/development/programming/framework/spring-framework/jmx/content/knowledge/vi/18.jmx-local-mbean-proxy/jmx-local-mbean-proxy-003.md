# ObjectName của MBean mục tiêu khi dùng proxy MBean local trong Spring Framework

## 1. Vai trò của ObjectName trong local JMX proxy

Spring Framework JMX cho phép ứng dụng truy cập MBean thông qua một proxy Java, giúp client gọi getter hoặc operation trên management interface mà không cần tự viết các lời gọi MBeanServerConnection. Một proxy như vậy không trực tiếp nắm implementation object: nó xác định đối tượng đích bằng **ObjectName**, gửi yêu cầu qua **MBeanServerConnection** và ánh xạ lời gọi theo **proxyInterface**.

Có thể tóm tắt định tuyến bằng bộ ba:

```text
Target = (MBeanServerConnection, ObjectName, management interface)
```

Trong đó:

- MBeanServerConnection cho biết registry/server nào được truy cập.
- ObjectName là khóa xác định một MBean trong registry đó.
- Management interface mô tả phương thức Java mà proxy dùng để đọc attribute hoặc gọi operation.

Ví dụ ObjectName chính xác:

```text
com.example.cache:type=CacheControl,name=Primary
```

Không được đồng nhất ObjectName với Spring bean name, tên class, tên interface hay địa chỉ JMX connector. Một tên hợp lệ vẫn có thể dẫn tới sai đối tượng nếu nó được dùng trên MBeanServer khác, hoặc nếu ứng dụng đã đăng ký MBean dưới tên khác.

## 2. Luồng hoạt động của MBean proxy local

```text
Spring business component
        |
        | Java interface method
        v
MBeanProxyFactoryBean-created proxy
        |
        | ObjectName + MBeanServerConnection
        v
Local MBeanServer
        |
        | lookup by exact ObjectName
        v
Registered target MBean
        |
        | attribute read/write or operation
        v
Managed application resource
```

Proxy local thường dùng MBeanServer trong cùng JVM, ví dụ platform MBeanServer. Tuy nhiên việc gọi qua JMX proxy **không đồng nghĩa gọi trực tiếp một Spring bean reference**: nếu MBean chưa đăng ký, bị unregister, hoặc proxy dùng server sai thì lời gọi có thể thất bại.

## 3. Cú pháp ObjectName

ObjectName của JMX có cấu trúc:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.cache:type=CacheControl,name=Primary
com.example.jobs:type=QueueMonitor,name=Main
java.lang:type=Memory
```

Domain là namespace logic; danh sách key properties như type, name và instance phân biệt MBean trong domain. Một ObjectName không chứa địa chỉ IP, port, URI hay tên ApplicationContext theo mặc định.

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.cache:type=CacheControl,name=Primary"
);
System.out.println(name.getDomain());                  // com.example.cache
System.out.println(name.getKeyProperty("type"));       // CacheControl
System.out.println(name.getKeyProperty("name"));       // Primary
System.out.println(name.getCanonicalName());
// com.example.cache:name=Primary,type=CacheControl
```

Thứ tự key properties không làm đổi danh tính. Hai tên sau tương đương:

```text
com.example.cache:type=CacheControl,name=Primary
com.example.cache:name=Primary,type=CacheControl
```

JMX phân biệt chữ hoa/thường: name=Primary khác name=primary; type khác Type. Khi cần so sánh, dùng ObjectName.equals() hoặc getCanonicalName(), không so sánh chuỗi thủ công theo thứ tự các key.

## 4. Proxy cần ObjectName chính xác, không dùng pattern

ObjectName có thể là **exact name** hoặc **pattern**:

```text
Exact:   com.example.cache:type=CacheControl,name=Primary
Pattern: com.example.cache:type=CacheControl,*
```

Pattern thích hợp cho MBeanServer.queryNames hoặc queryMBeans để khám phá nhiều MBean. Nhưng một proxy thông thường đại diện cho **một target**, nên objectName của proxy phải chỉ rõ tên cụ thể.

```java
ObjectName exact = new ObjectName(
    "com.example.cache:type=CacheControl,name=Primary"
);
ObjectName pattern = new ObjectName(
    "com.example.cache:type=CacheControl,*"
);
System.out.println(exact.isPattern());   // false
System.out.println(pattern.isPattern()); // true
```

Nếu chỉ biết domain/type và không biết instance, hãy query các tên hiện có rồi chọn đúng target theo quy tắc nghiệp vụ. Không lấy phần tử đầu tiên của Set queryNames làm target vì thứ tự không được đảm bảo. Không dùng wildcard làm khóa định tuyến của một proxy đơn lẻ.

## 5. Spring bean name khác JMX ObjectName

Ví dụ một bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component("cacheManagement")
@ManagedResource(
    objectName = "com.example.cache:type=CacheControl,name=Primary"
)
public class CacheManagement {
    @ManagedAttribute
    public int getEntryCount() {
        return 10;
    }
}
```

Ở đây cacheManagement là tên Spring IoC; CacheManagement là class; còn com.example.cache:type=CacheControl,name=Primary là ObjectName của MBean. MBeanProxyFactoryBean không tự hiểu Spring bean name thành ObjectName. Nếu exporter dùng ObjectNamingStrategy khác, tên cuối cùng có thể khác annotation hoặc tên bean, vì vậy client phải dựa vào tên **đã đăng ký thực tế**.

## 6. Tạo management contract cho proxy

Giả sử cần đọc số phần tử cache và yêu cầu refresh. Một interface nhỏ:

```java
package com.example.management;

public interface CacheControlMBean {
    int getEntryCount();
    boolean isEnabled();
    void requestRefresh();
}
```

Implementation theo Standard MBean convention:

```java
package com.example.management;

import java.util.concurrent.atomic.AtomicInteger;

public class CacheControl implements CacheControlMBean {
    private final AtomicInteger entries = new AtomicInteger(10);
    private volatile boolean enabled = true;

    @Override
    public int getEntryCount() {
        return entries.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void requestRefresh() {
        entries.incrementAndGet(); // Chỉ minh họa tác động.
    }
}
```

Interface xác định những khả năng client kỳ vọng. Ở một Standard MBean, tên và signature được JMX suy ra từ interface này. Spring cũng có thể export bean bằng metadata annotation và ModelMBean; khi đó vẫn cần bảo đảm proxyInterface phù hợp với MBeanInfo thực tế.

## 7. Export target bằng Spring

Ví dụ cấu hình explicit MBeanExporter:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MBeanTargetConfiguration {
    @Bean
    public CacheControl cacheControl() {
        return new CacheControl();
    }

    @Bean
    public MBeanExporter targetExporter(CacheControl target) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.cache:type=CacheControl,name=Primary",
            target
        ));
        return exporter;
    }
}
```

Key trong map xác định tên đăng ký, khi sử dụng naming strategy mặc định phù hợp. Không đồng thời đăng ký cùng một target bằng một exporter khác. Ví dụ này cũng có thể được thay bằng @ManagedResource và @EnableMBeanExport theo đường annotation-driven, miễn là ObjectName cuối cùng nhất quán với proxy.

## 8. Cấu hình MBeanProxyFactoryBean tới MBean local

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class LocalJmxClientConfiguration {
    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanProxyFactoryBean cacheProxy(
            MBeanServer platformMBeanServer) throws Exception {
        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
        factory.setServer(platformMBeanServer);
        factory.setObjectName(new ObjectName(
            "com.example.cache:type=CacheControl,name=Primary"
        ));
        factory.setProxyInterface(CacheControlMBean.class);
        return factory;
    }
}
```

FactoryBean tạo proxy triển khai interface được cấu hình. Một thành phần Spring có thể inject CacheControlMBean để gọi:

```java
public class CacheManagementClient {
    private final CacheControlMBean proxy;

    public CacheManagementClient(CacheControlMBean proxy) {
        this.proxy = proxy;
    }

    public void inspect() {
        int count = proxy.getEntryCount();
        System.out.println("Entry count = " + count);
        proxy.requestRefresh();
    }
}
```

Đoạn ví dụ giả định MBean đã được đăng ký vào chính platform MBeanServer và bean proxy được inject đúng. Không phải mọi ứng dụng Spring tự động export vào platform server: nếu có server riêng, hãy dùng cùng MBeanServer bean/config cho cả exporter và proxy.

## 9. ObjectName + server là một cặp định tuyến

Hai MBeanServer khác nhau có thể cùng chứa:

```text
com.example.cache:type=CacheControl,name=Primary
```

nhưng trỏ tới hai MBean khác nhau. Do đó proxy chọn tên đúng trên server sai vẫn không đảm bảo truy cập đúng đối tượng. Về mặt logic:

```text
Connection A + ObjectName X -> MBean A
Connection B + ObjectName X -> MBean B
```

Trong một JVM có thể tồn tại platform MBeanServer và server do ứng dụng/container tạo riêng. Khi debugging, đừng chỉ so sánh tên. Cần xác định server instance, cách exporter tìm server, cấu hình bean MBeanServer và connector thực tế.

Đối với remote connector, MBeanServerConnection là interface client tới server từ xa; kiến trúc ObjectName vẫn như vậy nhưng còn cần cấu hình URL, credentials, TLS và khả năng kết nối. Local proxy không tự động chuyển thành remote proxy chỉ vì cùng ObjectName.

## 10. Tên chính xác nhưng sai instance

Giả sử MBeanServer chứa:

```text
com.example.cache:type=CacheControl,name=Primary
com.example.cache:type=CacheControl,name=Secondary
com.example.cache:type=CacheControl,name=Archive
```

Proxy đặt name=Archive thay vì Primary có thể gọi thành công nhưng ảnh hưởng sai cache. Đặc biệt nguy hiểm khi proxy gọi operation có side effect như clear hoặc pause. Vì vậy cần kiểm tra các property định danh (application, name, instance, role) và có thể cung cấp thêm một attribute quan sát an toàn để xác nhận role của target.

Nếu nhiều application context chia sẻ MBeanServer, có thể thêm key application:

```text
com.example.cache:application=billing,type=CacheControl,name=Primary
com.example.cache:application=shipping,type=CacheControl,name=Primary
```

Không dùng RegistrationPolicy.REPLACE_EXISTING như biện pháp mặc định khi hai ứng dụng cùng chiếm tên. Proxy có thể bất ngờ gọi MBean khác sau khi một exporter thay thế registration.

## 11. Giá trị key có ký tự đặc biệt

Nếu tên target được ghép từ identifier động có dấu phẩy, dấu hai chấm, dấu bằng hoặc wildcard, cần quote đúng phần value:

```java
String cacheId = "prices,west";
ObjectName name = new ObjectName(
    "com.example.cache:type=CacheControl,name=" +
    ObjectName.quote(cacheId)
);
```

ObjectName.quote(value) diễn tả literal value và escape ký tự đặc biệt theo quy tắc JMX; không phải URL encoding hoặc JSON escaping. Hãy giữ quy tắc tạo tên của exporter và proxy giống nhau. Khi log, getCanonicalName giúp chuẩn hóa thứ tự key.

Không đặt access token, password hoặc dữ liệu cá nhân vào ObjectName; các tên thường có thể được liệt kê qua JMX và xuất hiện trong log.

## 12. Kiểm tra target trước khi sử dụng proxy

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName target = new ObjectName(
    "com.example.cache:type=CacheControl,name=Primary"
);

if (!server.isRegistered(target)) {
    throw new IllegalStateException(
        "Target MBean missing: " + target.getCanonicalName()
    );
}

MBeanInfo info = server.getMBeanInfo(target);
for (var attribute : info.getAttributes()) {
    System.out.println(attribute.getName());
}
for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

Thông tin MBeanInfo cho biết các thuộc tính và operation được công bố. Nếu getter của proxy là getEntryCount, hãy tìm attribute EntryCount. Nếu method requestRefresh được gọi, cần operation cùng tên và signature phù hợp.

isRegistered chỉ là snapshot tại một thời điểm; MBean có thể bị unregister giữa bước kiểm tra và lời gọi. Proxy/client vẫn phải xử lý lỗi sau đó.

## 13. Cách JMX ánh xạ getter và operation

Về ý nghĩa, proxy.getEntryCount() tương ứng với:

```java
Object count = server.getAttribute(target, "EntryCount");
```

proxy.requestRefresh() tương ứng với:

```java
server.invoke(
    target,
    "requestRefresh",
    new Object[0],
    new String[0]
);
```

Spring proxy giúp mã gọi đơn giản hơn, nhưng không bỏ qua hợp đồng JMX. Nếu target không có attribute EntryCount, gọi getter có thể lỗi. Nếu operation overload hoặc signature khác interface proxy, invoke có thể thất bại.

Cũng cần chú ý kiểu trả về. Một interface phía client khai báo String getEntryCount() trong khi MBean trả int không tự trở thành đúng chỉ nhờ proxy. Nên giữ interface đồng bộ với contract phía server hoặc dùng kiểu JMX tương thích, đặc biệt khi remote JMX cần Open Types.

## 14. Lifecycle và thứ tự khởi tạo

Proxy và target MBean là hai thành phần có lifecycle khác nhau:

- Exporter đăng ký MBean trong quá trình khởi tạo context theo cơ chế của Spring.
- Proxy có thể được tạo trong cùng quá trình khởi tạo hoặc được sử dụng sớm bởi bean khác.
- Nếu target chưa đăng ký, việc lấy metadata hoặc gọi proxy có thể gặp lỗi.
- Nếu context đóng hoặc MBean bị unregister, proxy không giữ cho target tồn tại.
- Trong hệ thống có MBean động, cùng tên có thể được unregister và đăng ký lại cho một instance mới.

Khi hai cấu hình cùng một ApplicationContext, nên thiết kế dependency rõ ràng, chỉ kích hoạt sử dụng proxy sau khi registration thành công. Có thể dùng @DependsOn với tên bean exporter phù hợp nếu cần kiểm soát thứ tự, nhưng phải đảm bảo nó thực sự tương ứng với quá trình đăng ký.

Đối với operation có side effect, không retry vô điều kiện khi nhận lỗi timeout/kết nối: request có thể đã được server xử lý nhưng client mất phản hồi.

## 15. Các lỗi hay gặp

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| MalformedObjectNameException | Chuỗi domain:key=value sai cú pháp | Kiểm tra key/value, dấu phân cách, quote |
| InstanceNotFoundException | Target chưa đăng ký, đã biến mất hoặc tên khác | Dùng isRegistered/queryNames trên đúng server |
| JConsole thấy MBean nhưng proxy không thấy | Hai client trỏ khác MBeanServer/JVM | Đối chiếu server và connector |
| Proxy gọi đúng tên nhưng sai resource | Key name/application/instance trỏ sai | Kiểm tra danh tính target và naming contract |
| AttributeNotFoundException | Getter proxy không khớp attribute trong MBeanInfo | Kiểm tra tên và chữ hoa/thường |
| ReflectionException hoặc invoke error | Operation name/signature không khớp | Đọc MBeanOperationInfo và interface |
| Lỗi conversion/cast | Kiểu dữ liệu phía client khác phía target | Đồng bộ contract và dùng Open Types nếu cần |
| Startup lỗi vì MBean chưa tồn tại | Thứ tự khởi tạo proxy/exporter chưa phù hợp | Thiết kế dependency/lifecycle |
| Hoạt động trước redeploy nhưng lỗi sau đó | MBean bị unregister hoặc đổi ObjectName | Giữ naming ổn định và có recovery policy |

## 16. Khi nào dùng local proxy?

Local proxy hữu ích khi muốn:

- Sử dụng management interface theo mô hình Java thay vì tự thao tác chuỗi attribute/operation.
- Truy cập JMX contract giống như client quản trị độc lập trong cùng JVM.
- Tái sử dụng thiết kế interface giữa local và remote JMX client.
- Kiểm thử sự tương thích của management API qua MBeanServer.

Ngược lại, nếu một Spring bean chỉ cần gọi business service khác trong cùng context, inject service trực tiếp thường đơn giản hơn. Gọi qua JMX proxy thêm chi phí lookup/metadata và phụ thuộc ObjectName, registration, server, lifecycle. Không nên dùng JMX proxy thay cho dependency injection thông thường nếu không có yêu cầu JMX cụ thể.

## 17. Checklist thiết kế

1. Chọn đúng MBeanServerConnection; nếu local, ưu tiên dùng chung MBeanServer với exporter.
2. Tạo ObjectName chính xác, không phải wildcard pattern.
3. Đảm bảo tên proxy khớp tên export, kể cả domain, hoa/thường và mọi key properties.
4. Nếu có nhiều instance, chọn name/application/instance đúng resource.
5. Cung cấp proxyInterface tương thích các attributes/operations thực tế.
6. Kiểm tra MBeanInfo khi nghi ngờ metadata không khớp.
7. Giữ ObjectName ổn định qua các bản triển khai để client không phải đổi cấu hình.
8. Không gọi proxy trước khi target được đăng ký; xử lý lỗi khi target biến mất.
9. Không retry operation tác động trạng thái một cách mù quáng.
10. Giữ connector, attributes và operations an toàn theo nguyên tắc quyền tối thiểu.

## 18. Mô hình tư duy

```text
proxyInterface                  ObjectName
     |                              |
  Java API                    Exact target key
     |                              |
     +--------------+---------------+
                    |
         MBeanServerConnection
                    |
                    v
           MBeanServer registry
                    |
                    v
                Target MBean
```

**Kết luận:** ObjectName là khóa định tuyến tới MBean mục tiêu của local proxy. Một proxy chỉ hoạt động đúng khi **server, exact ObjectName và management interface** nhất quán với đối tượng đã đăng ký. Cần phân biệt tên JMX với tên Spring bean, xác minh đúng instance, kiểm soát lifecycle và tránh thay đổi naming làm hỏng client quản trị.
