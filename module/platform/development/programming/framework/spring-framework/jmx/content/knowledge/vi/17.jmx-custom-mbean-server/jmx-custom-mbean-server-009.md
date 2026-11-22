# Ảnh hưởng của classloader và nhiều ứng dụng trong một JVM khi dùng MBeanServer tùy biến

## 1. Bối cảnh và mục tiêu

Trong Java, một JVM có thể chạy nhiều ứng dụng, nhiều module, nhiều Spring `ApplicationContext` hoặc nhiều bản triển khai của cùng một ứng dụng. Mỗi ứng dụng có thể sở hữu một `ClassLoader` riêng. Khi các ứng dụng này cùng sử dụng Java Management Extensions (JMX), việc chọn **MBeanServer dùng chung hay MBeanServer tùy biến** quyết định không chỉ nơi đăng ký MBean mà còn ảnh hưởng tới tính duy nhất của `ObjectName`, vòng đời đối tượng, khả năng truy cập metadata, dọn dẹp khi redeploy và ranh giới quan sát.

Một ứng dụng Spring Framework có thể dùng `MBeanExporter` để đưa bean quản trị lên MBeanServer. Trong trường hợp đơn giản, exporter dùng platform MBeanServer. Với nhiều ứng dụng trong cùng JVM — ví dụ một application server chứa nhiều WAR, nhiều Spring context hoặc một plugin host nạp module động — cấu hình đó cần được cân nhắc kỹ hơn.

Sau bài học, bạn có thể:

- Phân biệt **namespace của MBeanServer** và **namespace của ClassLoader**.
- Hiểu vì sao cùng tên class nhưng do hai classloader nạp có thể là hai kiểu Java khác nhau.
- Nhận diện va chạm `ObjectName` khi nhiều ứng dụng đăng ký MBean vào một server.
- Hiểu các nguy cơ giữ tham chiếu làm **classloader leak** khi undeploy/redeploy.
- Chọn giữa platform/shared MBeanServer và MBeanServer riêng theo nhu cầu vận hành.
- Cấu hình Spring `MBeanExporter` và `MBeanServerFactoryBean` với quyền sở hữu rõ ràng.
- Xây dựng quy trình kiểm tra đăng ký, hủy đăng ký và kết nối JMX ở môi trường nhiều ứng dụng.

## 2. Classloader là gì và vì sao ảnh hưởng đến JMX?

Java `ClassLoader` chịu trách nhiệm tải định nghĩa class. Trong JVM, danh tính một class không chỉ phụ thuộc tên đầy đủ của class mà còn phụ thuộc **classloader định nghĩa nó**.

Ví dụ:

```text
JVM
├── Shared / parent classloader
│   └── javax.management.MBeanServer
├── Application A classloader
│   └── com.example.monitoring.CacheMonitor
└── Application B classloader
    └── com.example.monitoring.CacheMonitor
```

Hai class `com.example.monitoring.CacheMonitor` có cùng tên nhưng được định nghĩa bởi hai application classloader độc lập **không nhất thiết là cùng một kiểu runtime**.

Điều này quan trọng khi JMX introspection khám phá interface của MBean, khi client truy cập các kiểu dữ liệu tùy biến và khi server giữ tham chiếu tới MBean sau khi một ứng dụng bị gỡ triển khai.

### 2.1. Ví dụ cùng tên nhưng khác loader

```java
Class<?> a = applicationALoader.loadClass(
    "com.example.monitoring.CacheMonitor");

Class<?> b = applicationBLoader.loadClass(
    "com.example.monitoring.CacheMonitor");

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b); // Có thể false
```

Nếu mỗi loader thực sự định nghĩa riêng class này, `a == b` là `false`. Một object do loader A tạo không thể mặc nhiên ép sang cùng tên class do loader B định nghĩa.

Bản thân API `javax.management` thuộc nền tảng Java nên nhiều ứng dụng có thể cùng tương tác với nó. Tuy nhiên, MBean implementation, interface quản trị tùy biến, `NotificationListener` và nhiều dữ liệu truyền qua JMX thường mang class hoặc object do application loader nạp.

## 3. MBeanServer không đồng nghĩa với ClassLoader

`MBeanServer` là registry quản trị trong JMX. Nó lưu các MBean theo `ObjectName` và phục vụ operation, attribute, notification.

`ClassLoader` là thành phần nạp class. Hai khái niệm thuộc hai trục khác nhau:

| Khía cạnh | MBeanServer | ClassLoader |
| --- | --- | --- |
| Vai trò | Registry và API quản trị MBean | Nạp, liên kết và định danh class |
| Định danh chính | `ObjectName` trong một server | Tên class kết hợp loader định nghĩa |
| Có thể dùng chung giữa ứng dụng? | Có | Có thể có loader chung hoặc loader riêng |
| Liên quan tới vòng đời | Đăng ký/hủy đăng ký MBean | Tải class; có thể được GC khi không còn tham chiếu |
| Lỗi thường gặp | Trùng `ObjectName`, sai server, MBean không tồn tại | `ClassCastException`, `ClassNotFoundException`, leak khi redeploy |

Một MBeanServer có thể đăng ký MBean đến từ nhiều classloader. Ngược lại, một ứng dụng dùng một classloader có thể đăng ký MBean vào nhiều MBeanServer. **Không có quan hệ một-một bắt buộc.**

### 3.1. Hai ứng dụng cùng dùng platform MBeanServer

```text
Application A (ClassLoader A) --+
                                +--> Platform MBeanServer
Application B (ClassLoader B) --+         |
                                          +-- A MBeans
                                          +-- B MBeans
```

Cách này thuận tiện cho công cụ quản trị: một connector có thể nhìn thấy những MBean mà cả hai ứng dụng đăng ký vào cùng server. Nhưng namespace ObjectName được chia sẻ, nên hai ứng dụng phải tránh va chạm tên.

### 3.2. Mỗi ứng dụng dùng server riêng

```text
Application A --> MBeanServer A --> A MBeans
Application B --> MBeanServer B --> B MBeans
```

Hai server có registry độc lập. Cùng một ObjectName có thể xuất hiện ở cả hai mà không xung đột. Tuy nhiên JConsole hoặc client kết nối platform server **không tự động nhìn thấy** các server riêng: cần đường truy cập thích hợp. Tạo server riêng không tự bật JMX Remote connector.

## 4. Va chạm ObjectName giữa nhiều ứng dụng

Trong JMX, một ObjectName chỉ được đăng ký cho một MBean tại mỗi thời điểm **trong một MBeanServer**.

Giả sử application A và B cùng export:

```text
com.example.app:type=CacheMonitor,name=Main
```

Nếu cả hai dùng platform server, ứng dụng đăng ký sau có thể nhận `InstanceAlreadyExistsException`. Việc hai MBean implementation được nạp từ classloader khác nhau **không làm ObjectName khác nhau**.

Ví dụ:

```java
ObjectName name = new ObjectName(
    "com.example.app:type=CacheMonitor,name=Main");

server.registerMBean(mbeanFromAppA, name);
server.registerMBean(mbeanFromAppB, name);
// Lần thứ hai thất bại vì ObjectName đã tồn tại.
```

Để tránh trùng, nên tạo quy ước namespace có tên ứng dụng, module hoặc instance:

```text
com.example.applicationA:type=CacheMonitor,name=Main
com.example.applicationB:type=CacheMonitor,name=Main
```

hoặc:

```text
com.example.platform:type=CacheMonitor,app=orders,name=Main
com.example.platform:type=CacheMonitor,app=inventory,name=Main
```

Domain và key property là các quy ước ứng dụng; Java không tự thêm classloader ID vào ObjectName. Nếu có nhiều deployment cùng JVM, hãy đặt định danh instance ổn định và không chứa bí mật.

### 4.1. Cùng ObjectName ở hai server riêng

```java
MBeanServer a =
    MBeanServerFactory.newMBeanServer("com.example.app");

MBeanServer b =
    MBeanServerFactory.newMBeanServer("com.example.app");

ObjectName sameName = new ObjectName(
    "com.example.app:type=CacheMonitor,name=Main");
```

Bạn có thể đăng ký các MBean tương thích với tên đó trong cả hai server, vì registry độc lập. Để xác định đích quản trị trên một dashboard đa server, identity thực tế cần gồm cả **connection/server identity** và ObjectName, không chỉ ObjectName.

## 5. Classloader leak khi undeploy hoặc redeploy

Nguy cơ nổi bật của JMX trong application server là **MBean còn đăng ký sau khi ứng dụng đã dừng**.

Một MBean đăng ký trong server sống lâu hơn ứng dụng có thể giữ tham chiếu tới:

- Instance MBean do application classloader định nghĩa.
- Các service, cache, executor, callback và dependency được MBean giữ.
- Class và metadata của lớp ứng dụng.
- `NotificationListener`, filter hoặc handback do ứng dụng tạo.
- Thread, timer hoặc resource phụ trợ thuộc ứng dụng.

Nếu các tham chiếu vẫn còn reachable từ platform/shared MBeanServer, classloader cũ có thể không được garbage collection sau undeploy. Khi ứng dụng redeploy nhiều lần, nhiều classloader cũ có thể tồn tại, làm tăng mức sử dụng bộ nhớ và gây lỗi khó chẩn đoán.

```text
Platform MBeanServer (sống suốt JVM)
        |
        +--> MBean cũ (đã quên unregister)
                  |
                  +--> Service ứng dụng cũ
                  |        |
                  |        +--> ClassLoader cũ
                  |
                  +--> Listener / callback cũ
```

Đây là một ví dụ của **classloader leak**: sự tồn tại của MBean trong registry dùng chung có thể giữ lại cả đồ thị đối tượng của phiên triển khai trước.

Không phải mọi `ClassLoader` còn sống đều là leak; cần có bằng chứng về đối tượng/loader cũ vẫn được giữ ngoài vòng đời dự kiến. Tuy nhiên, unregister MBean đúng lúc là biện pháp phòng ngừa trọng yếu.

### 5.1. Dấu hiệu thường gặp

- Redeploy vài lần làm heap hoặc metaspace tăng, nhưng không giảm tương xứng sau GC.
- MBean của bản triển khai cũ vẫn hiện trong JConsole.
- Lỗi `InstanceAlreadyExistsException` ngay khi deploy bản mới.
- Notification listener cũ tiếp tục xử lý sự kiện.
- Log từ classloader cũ vẫn xuất hiện sau undeploy.
- Các thread hoặc timer thuộc module cũ vẫn hoạt động.

Những hiện tượng này có thể do nhiều nguyên nhân khác ngoài JMX. Khi điều tra, cần kiểm tra registry MBean, listener, thread, classloader và heap reference graph, không chỉ kết luận từ việc bộ nhớ tăng.

## 6. Vai trò của Spring MBeanExporter trong vòng đời

Spring `MBeanExporter` thường tham gia vòng đời `ApplicationContext`: đăng ký MBean khi khởi tạo và hủy các đăng ký mà exporter quản lý khi context đóng.

Ví dụ cấu hình:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfig {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            CacheMonitor cacheMonitor,
            MBeanServer mbeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(
            "com.example.applicationA:type=CacheMonitor,name=Main",
            cacheMonitor
        ));
        return exporter;
    }
}
```

Ví dụ giả định `CacheMonitor` là Standard MBean hợp lệ hoặc được cấu hình assembler thích hợp. Nếu đóng context đúng cách, exporter có cơ hội cleanup những đăng ký của mình.

**Không nên chỉ dựa vào việc JVM sẽ tắt.** Trong application server, một WAR hoặc một Spring context có thể bị undeploy trong khi JVM và platform MBeanServer vẫn sống. Thao tác dọn đăng ký phải gắn với vòng đời ứng dụng.

### 6.1. Khi nào exporter không đủ?

Những MBean được đăng ký **ngoài** `MBeanExporter` có thể không được Spring exporter tự quản lý. Ví dụ:

```java
server.registerMBean(customMBean, customName);
```

Nếu code này chạy thủ công, chính code sở hữu đăng ký phải bảo đảm `unregisterMBean` khi module dừng.

Tương tự, một listener do code khác thêm vào broadcaster hoặc một remote connector được tạo thủ công cũng cần được gỡ/dừng theo lifecycle của chúng. Đóng `ApplicationContext` không mặc nhiên dọn mọi tài nguyên được tạo bên ngoài Spring.

## 7. MBeanServer dùng chung hay server tùy biến?

### 7.1. Dùng shared/platform MBeanServer

Ưu điểm:

- Công cụ quản trị JVM có thể truy cập MBean ứng dụng cùng platform MXBeans.
- Ít cần cấu hình connector hoặc discovery riêng.
- Thống nhất quan sát nhiều module trong cùng JVM.
- Hợp lý khi muốn một bề mặt quản trị chung.

Nhược điểm:

- Namespace ObjectName chia sẻ; trùng tên dễ hơn.
- MBean bị bỏ quên có thể giữ classloader của một ứng dụng đã dừng.
- Cần quy định rõ ai sở hữu đăng ký của từng ObjectName.
- Một tài khoản JMX có phạm vi quá rộng có thể nhìn thấy nhiều ứng dụng nếu không có authorization phù hợp.

### 7.2. Dùng MBeanServer riêng

Ưu điểm:

- Registry độc lập, giảm va chạm ObjectName với ứng dụng khác.
- Có thể quản lý server/connector theo phạm vi ứng dụng.
- Hữu ích cho test, plugin hoặc môi trường cần tách hệ thống quản trị.

Nhược điểm:

- Client phải biết kết nối đến server riêng; JConsole kết nối platform server không tự thấy MBean này.
- Cần quản lý lifecycle server và mọi connector liên quan.
- Nhiều server làm discovery, monitoring và alert configuration phức tạp hơn.
- Không tự bảo đảm isolation bảo mật hoặc loại bỏ classloader leak nếu còn tham chiếu từ thành phần dùng chung.

**Kết luận thiết kế:** server riêng là một công cụ để tổ chức registry, không phải cách thay thế hoàn toàn việc quản lý ObjectName, lifecycle và classloader.

## 8. Tạo server riêng bằng MBeanServerFactoryBean

Spring có `org.springframework.jmx.support.MBeanServerFactoryBean` để cung cấp MBeanServer thông qua container.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class PrivateServerConfig {

    @Bean
    public MBeanServerFactoryBean privateJmxServer() {
        MBeanServerFactoryBean factory =
            new MBeanServerFactoryBean();

        factory.setDefaultDomain("com.example.private");
        factory.setLocateExistingServerIfPossible(false);
        factory.setRegisterWithFactory(false);
        return factory;
    }
}
```

Cấu hình trên yêu cầu tạo MBeanServer mới và không đăng ký vào danh sách tra cứu của `MBeanServerFactory`. Điều đó giảm nguy cơ một thành phần khác vô tình dùng chung server qua factory lookup. Tuy nhiên, nếu một singleton dùng chung hoặc JMX connector vẫn giữ server sau khi application context đóng, server và các MBean có thể tiếp tục sống.

Để export vào server riêng, `MBeanExporter` phải nhận đúng `MBeanServer`:

```java
@Bean
MBeanExporter privateExporter(
        CacheMonitor monitor,
        MBeanServer privateJmxServer) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(privateJmxServer);
    exporter.setBeans(Map.of(
        "com.example.private:type=CacheMonitor,name=Main",
        monitor
    ));
    return exporter;
}
```

Khi context có nhiều bean kiểu `MBeanServer`, hãy dùng `@Qualifier` hoặc tên để chọn đúng instance. Không nên dựa vào tự động chọn server theo thứ tự ngẫu nhiên.

### 8.1. createMBeanServer và newMBeanServer

JMX API có:

```java
MBeanServer registered =
    MBeanServerFactory.createMBeanServer("com.example.registered");

MBeanServer unregistered =
    MBeanServerFactory.newMBeanServer("com.example.private");
```

`createMBeanServer` đưa server mới vào danh sách do `MBeanServerFactory` theo dõi; `newMBeanServer` tạo server nhưng không đưa vào danh sách đó. Cả hai đều không tự tạo remote connector.

Không nên hiểu `newMBeanServer` là giải pháp tự động cho classloader isolation. Khả năng thu gom bộ nhớ phụ thuộc toàn bộ đồ thị tham chiếu, không chỉ việc server có nằm trong danh sách factory hay không.

## 9. Classloader repository và introspection của JMX

JMX có cơ chế class loading và introspection liên quan đến MBean. `MBeanServer` hỗ trợ `ClassLoaderRepository` và các operation phục vụ nạp class trong các tình huống JMX được định nghĩa.

Điều này đặc biệt quan trọng khi:

- Một MBean được nạp qua application classloader nhưng server nằm ở tầng chung.
- JMX cần introspect interface hoặc method signatures.
- MBean operation dùng parameter/return type là class của ứng dụng.
- Client JMX từ JVM khác không có class tương ứng.
- Có hai phiên bản cùng tên class trong các ứng dụng khác nhau.

JMX API không xóa đi ranh giới Java class identity. Cùng tên class ở hai loader vẫn là hai định nghĩa khác nhau khi không được chia sẻ qua delegation.

### 9.1. Standard MBean và interface classloader

Một Standard MBean được nhận diện theo quy ước interface, ví dụ:

```java
package com.example.monitoring;

public interface CacheMonitorMBean {
    long getHitCount();
}
```

```java
package com.example.monitoring;

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public long getHitCount() {
        return 0L;
    }
}
```

Để một lớp implements interface theo đúng Java type identity, interface mà nó implements phải phù hợp với classloader resolution. Nếu hai ứng dụng đều mang bản copy của `CacheMonitorMBean`, đó có thể là hai class khác nhau dù trùng tên.

Khi introspection MBean thất bại, hãy kiểm tra không chỉ tên interface mà còn classloader thực sự định nghĩa class và dependency version. Đừng xem `ClassCastException` giữa hai lớp cùng tên là điều bất khả thi.

### 9.2. Tránh kiểu DTO tùy biến trong remote JMX

Một MBean operation dùng kiểu application-specific:

```java
public CustomerOrderSummary getSummary();
```

có thể đòi hỏi JMX client biết class, cùng package, phiên bản và serialization contract tương ứng. Với nhiều app classloader, điều này dễ phức tạp và khó bảo trì.

Đối với giao diện quản trị ổn định, nên ưu tiên primitive, wrapper, `String`, `CompositeData`, `TabularData` hoặc các kiểu Open MBean phù hợp. Đừng export nguyên domain entity có cấu trúc phụ thuộc nhiều class của ứng dụng nếu mục tiêu chỉ là giám sát.

## 10. Listener và tham chiếu chéo giữa ứng dụng

Notification listener có thể tạo ra chuỗi tham chiếu dài sống vượt vòng đời mong muốn.

Ví dụ:

```java
NotificationListener listener =
    (notification, handback) -> monitoringService.onEvent(notification);

server.addNotificationListener(
    objectName, listener, null, null);
```

Nếu `monitoringService` thuộc ứng dụng A, lambda listener có thể giữ reference đến service A. Nếu broadcaster MBean còn tồn tại trên server chung sau khi A undeploy, reference này có thể giữ lại classloader A.

Khi dọn:

```java
server.removeNotificationListener(objectName, listener);
```

Tuy nhiên, lệnh này chỉ đúng khi listener và MBean còn được đăng ký theo cách tương ứng. Nếu MBean đã bị unregister, remove có thể gặp `InstanceNotFoundException`. Cần tổ chức cleanup theo thứ tự hợp lý, bắt lỗi dọn dẹp có chọn lọc và giữ đúng danh tính listener ban đầu.

Cẩn trọng với các nguồn tham chiếu khác:

- Handback object được truyền khi đăng ký listener.
- Executor chứa task hoặc callback thuộc ứng dụng.
- Timer, scheduler và thread-local.
- Static collection trong thư viện dùng chung lưu class/instance của ứng dụng.
- MBeanServer hoặc connector đặt trong singleton có vòng đời JVM.

Đăng ký listener và MBean từ nhiều ứng dụng đòi hỏi hợp đồng rõ ràng về ai là người gỡ nó khi kết thúc.

## 11. Classloader context và thread context classloader

Trong Java, `Thread.currentThread().getContextClassLoader()` (TCCL) có thể ảnh hưởng đến việc nạp class qua một số framework hoặc thư viện. Application server và một số integration có thể đặt TCCL theo application trước khi gọi code.

Khi thao tác quản trị được gọi từ thread JMX connector hoặc code nền, TCCL có thể khác với thread request bình thường. Một bean dựa vào TCCL để load resource, driver hoặc service provider có thể hoạt động khác khi được invoke qua JMX.

Ví dụ quan sát:

```java
@ManagedOperation(description = "Print diagnostic classloader info")
public String classLoaderInfo() {
    ClassLoader ownLoader = getClass().getClassLoader();
    ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();

    return "own=" + ownLoader + ", context=" + contextLoader;
}
```

Đây chỉ là ví dụ chẩn đoán, không phải lời khuyên log mọi cấu trúc classloader trong production. Không nên đổi TCCL tùy tiện trong operation rồi quên khôi phục; nếu một thao tác cần chạy với loader cụ thể, phải thiết kế và restore an toàn trong `finally`.

Không phải mọi JMX operation đều đổi TCCL; hành vi cụ thể phụ thuộc connector, framework và môi trường thực thi. Điều cần kiểm tra là **đường gọi quản trị có thể không giống luồng HTTP/request bình thường**.

## 12. Nhiều ứng dụng chung JVM: ranh giới bảo mật

Một JVM chứa nhiều ứng dụng không đồng nghĩa các ứng dụng đã được cách ly bảo mật ở mức process. Nếu các ứng dụng chia sẻ MBeanServer và một JMX client có quyền quản trị rộng, client đó có thể quan sát hoặc gọi operation trên MBean của nhiều ứng dụng.

Domain và key property của ObjectName **không tự tạo access control**:

```text
com.example.appA:type=CacheMonitor,name=Main
com.example.appB:type=CacheMonitor,name=Main
```

Hai domain khác nhau giúp nhận diện và tránh tên trùng, nhưng không đảm bảo một user được phép truy cập appA sẽ bị từ chối appB.

Cần lưu ý:

1. JMX Remote phải được bảo vệ bằng authentication và transport security phù hợp.
2. Quyền truy cập tới MBean/operation phải dựa trên policy thực sự, không suy từ prefix tên.
3. Không export operation nguy hiểm chỉ vì người dùng “chỉ kết nối nội bộ”.
4. Không trả dữ liệu nhạy cảm của ứng dụng khác qua attribute hoặc notification.
5. Server riêng có thể thu hẹp phạm vi connector nếu được triển khai đúng, nhưng vẫn cần kiểm soát quyền và lifecycle.

Với các ứng dụng không tin cậy lẫn nhau, process/JVM isolation thường tạo ranh giới mạnh hơn việc chỉ tách MBeanServer trong cùng JVM.

## 13. Quy trình deploy, redeploy và undeploy an toàn

Một quy trình vận hành nên có các bước:

### Khi khởi tạo

1. Chọn MBeanServer rõ ràng: platform, container-managed hay riêng.
2. Gán domain và ObjectName phân biệt ứng dụng, module và instance.
3. Khởi tạo bean và exporter.
4. Đăng ký MBean hoặc để `MBeanExporter` quản lý việc đăng ký.
5. Kiểm tra `isRegistered(ObjectName)` trên đúng server.
6. Đăng ký notification listener cần thiết; ghi lại ownership để gỡ sau này.

### Khi dừng hoặc redeploy

1. Ngừng nguồn tác vụ hoặc callback có thể sinh đăng ký mới.
2. Gỡ listener do ứng dụng sở hữu.
3. Đóng Spring `ApplicationContext` theo lifecycle.
4. Đảm bảo các MBean đăng ký thủ công được unregister.
5. Dừng connector/executor/thread do ứng dụng tạo.
6. Xác minh không còn ObjectName của deployment cũ trên server được dùng chung.
7. Điều tra nếu classloader cũ còn bị giữ tham chiếu hoặc nếu MBean cũ vẫn tồn tại.

Nếu ứng dụng dùng server riêng, cần xác định ai giữ reference tới server đó sau khi dừng. Một server mới do application context tạo có thể được thu gom nếu không còn tham chiếu tới nó; nhưng nếu singleton hoặc connector còn giữ server, rủi ro vẫn tồn tại.

### 13.1. Cleanup bằng code khi tự đăng ký

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class ManualJmxRegistration
        implements AutoCloseable {

    private final MBeanServer server;
    private final ObjectName name;
    private boolean registered;

    public ManualJmxRegistration(
            MBeanServer server, ObjectName name, Object mbean)
            throws Exception {
        this.server = server;
        this.name = name;
        server.registerMBean(mbean, name);
        registered = true;
    }

    @Override
    public synchronized void close() throws Exception {
        if (!registered) {
            return;
        }
        if (server.isRegistered(name)) {
            server.unregisterMBean(name);
        }
        registered = false;
    }
}
```

Đây là ví dụ minh họa ownership đơn giản. Trong môi trường đồng thời, `isRegistered` rồi `unregisterMBean` không là một giao dịch atomic; một MBean khác có thể thay thế đăng ký nếu có thay đổi giữa hai lời gọi. Vì vậy cleanup trong production cần giữ ownership đúng, tránh unregister MBean của thành phần khác.

## 14. Kiểm tra trên đúng server và đúng classloader

### 14.1. Kiểm tra registry JMX

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.applicationA:type=CacheMonitor,name=Main");

System.out.println(server.isRegistered(name));
```

Nếu false:

- Có thể exporter chưa chạy.
- Có thể ObjectName thực tế khác.
- Có thể bean đã bị unregister.
- Có thể kiểm tra nhầm MBeanServer.
- Có thể cấu hình classloader hoặc metadata khiến export thất bại.

Nếu true nhưng không truy cập được attribute, tiếp tục kiểm tra `MBeanInfo` và quyền/kiểu dữ liệu.

### 14.2. In thông tin classloader khi chẩn đoán

```java
Class<?> type = monitor.getClass();
ClassLoader loader = type.getClassLoader();

System.out.println("MBean class=" + type.getName());
System.out.println("ClassLoader=" + loader);
```

Trong Spring AOP, `getClass()` có thể là proxy class, nên có thể cần đối chiếu class đích nếu muốn xác định loader của ứng dụng. Thông tin loader cần được dùng trong chẩn đoán có kiểm soát, không nên công bố tùy tiện thành endpoint công khai.

### 14.3. Kiểm tra JMX metadata

```java
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);
System.out.println(info.getClassName());
System.out.println(info.getDescription());
```

`MBeanInfo.getClassName()` là tên class được metadata công bố, không phải bằng chứng duy nhất về classloader đã nạp instance. Hai ứng dụng có thể cùng tên class trong metadata nhưng dùng loader khác.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách tiếp cận |
| --- | --- | --- |
| `InstanceAlreadyExistsException` lúc redeploy | MBean cũ chưa unregister hoặc ObjectName trùng | Xác định owner, kiểm tra lifecycle, thiết kế key instance |
| MBean đã đăng ký nhưng JConsole không thấy | Exporter dùng server riêng; JConsole nối platform server | Xác minh connector và MBeanServer đích |
| `ClassNotFoundException` khi gọi operation | Kiểu dữ liệu tùy biến không có ở client/loader | Dùng kiểu JMX/Open MBean phù hợp |
| `ClassCastException` giữa lớp cùng tên | Hai classloader định nghĩa class khác nhau | Kiểm tra loader, version và dependency |
| Heap/metaspace tăng sau redeploy | MBean/listener/thread giữ loader cũ | Kiểm tra heap reference graph và cleanup |
| Listener cũ tiếp tục nhận notification | Không gỡ listener hoặc broadcaster còn sống | Quản lý ownership/lifecycle listener |
| MBean operation hoạt động khác HTTP request | TCCL, thread context hoặc security context khác | Kiểm tra giả định về môi trường gọi |
| Dùng server riêng nhưng vẫn rò rỉ memory | Connector/static reference giữ server/bean | Dừng connector và giải phóng reference |

Những lỗi này có thể xảy ra độc lập hoặc đồng thời. Không nên dùng “tạo MBeanServer riêng” như một biện pháp sửa mọi lỗi classloader.

## 16. Bài tập thực hành

Giả sử một JVM chứa hai Spring contexts, mỗi context tạo `CacheMonitor`.

### Phần A — cùng platform MBeanServer

1. Cấu hình cả context A và B dùng `ManagementFactory.getPlatformMBeanServer()`.
2. Cho cả hai cố export ObjectName `com.example.shared:type=CacheMonitor,name=Main`.
3. Quan sát đăng ký thứ hai bị từ chối hoặc exporter gặp lỗi trùng tên.
4. Sửa thành `app=A` và `app=B` trong key property.
5. Dùng `queryNames("com.example.shared:type=CacheMonitor,*")` để liệt kê hai instance.

### Phần B — server riêng

1. Tạo server A và B bằng `MBeanServerFactory.newMBeanServer(...)` hoặc Spring `MBeanServerFactoryBean`.
2. Export mỗi `CacheMonitor` vào server tương ứng.
3. Thử dùng cùng ObjectName trong cả hai server.
4. Xác nhận mỗi server có registry riêng, không va chạm.
5. Giải thích vì sao một JMX client chỉ kết nối platform server không tự tìm thấy hai MBean trên server riêng.

### Phần C — lifecycle

1. Ghi lại ObjectName do mỗi context sở hữu.
2. Đóng context A, xác nhận MBean thuộc A được gỡ khỏi server dùng chung.
3. Đảm bảo listener và connector do A tạo được dọn.
4. Khởi tạo lại context A với cùng ObjectName và quan sát không còn conflict nếu cleanup đúng.
5. Dùng profiler nếu cần để kiểm tra loader và object graph của deployment cũ.

Một minh họa registry biệt lập:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer a = MBeanServerFactory.newMBeanServer("com.example.a");
MBeanServer b = MBeanServerFactory.newMBeanServer("com.example.b");

ObjectName name = new ObjectName(
    "com.example.shared:type=CacheMonitor,name=Main");

a.registerMBean(new CacheMonitor(), name);
b.registerMBean(new CacheMonitor(), name);

System.out.println(a.isRegistered(name)); // true
System.out.println(b.isRegistered(name)); // true
```

Để chạy đoạn minh họa, `CacheMonitor` phải là MBean hợp lệ và bạn cần xử lý vòng đời, lỗi và cleanup phù hợp trong chương trình thực tế.

## 17. Câu hỏi tự kiểm tra

**1. Hai class cùng package và tên có luôn là cùng kiểu runtime không?** Không. Classloader định nghĩa có thể khác nhau.

**2. ObjectName có duy nhất giữa mọi MBeanServer trong JVM không?** Không; nó duy nhất trong từng server.

**3. Vì sao hai ứng dụng dùng chung platform MBeanServer dễ gặp lỗi trùng tên?** Vì cả hai chia sẻ cùng registry ObjectName.

**4. MBeanServer riêng có tự giải quyết classloader leak không?** Không, vẫn cần quản lý tham chiếu, listener, connector và lifecycle.

**5. Vì sao một MBean còn đăng ký sau undeploy có thể giữ classloader cũ?** Vì shared server còn giữ tham chiếu tới MBean và đồ thị đối tượng của ứng dụng.

**6. `MBeanExporter` giúp gì khi Spring context đóng?** Nó quản lý hủy đăng ký những MBean do exporter sở hữu theo lifecycle của context.

**7. Vì sao `MBeanInfo.getClassName()` không đủ chứng minh classloader nào đã nạp MBean?** Vì nó chỉ thể hiện tên class trong metadata, không định danh loader.

**8. Dùng domain khác nhau có tự tách quyền truy cập không?** Không, domain chỉ là phần định danh và nhóm namespace.

**9. Nếu client JMX dùng remote connector với DTO riêng, cần cân nhắc gì?** Class availability, serialization, version và kiểu dữ liệu quản trị phù hợp.

**10. Sau redeploy, nên kiểm tra gì?** ObjectName cũ, listener, connector, thread, reference graph và khả năng thu gom classloader.

## 18. Ghi nhớ

- **Class identity** phụ thuộc tên class **và classloader định nghĩa**.
- **MBeanServer** là registry JMX, không phải classloader; một server có thể chứa MBean của nhiều ứng dụng.
- **ObjectName chỉ duy nhất trong một MBeanServer**, nên nhiều ứng dụng dùng chung server cần namespace/instance key rõ ràng.
- **Shared platform server** thuận tiện cho giám sát nhưng cần ownership và cleanup nghiêm túc.
- **Private MBeanServer** tách registry, nhưng không tự bật remote connector hoặc bảo đảm isolation bảo mật.
- **MBean, listener và connector còn sống sau undeploy** có thể giữ classloader cũ, gây memory leak.
- **Spring MBeanExporter** hỗ trợ vòng đời đăng ký/hủy đăng ký nhưng không tự dọn mọi tài nguyên tạo ngoài Spring.
- **Classloader/TCCL** có thể ảnh hưởng introspection, kiểu dữ liệu, callback và lời gọi operation từ JMX.
- Kiểm tra trên **đúng MBeanServer**, với đúng ObjectName, và quản lý rõ owner khi đăng ký cũng như khi dừng ứng dụng.

Tách bạch MBeanServer, ObjectName, classloader và lifecycle giúp vận hành nhiều Spring application trong cùng JVM một cách nhất quán, đồng thời hạn chế rủi ro va chạm tên, lỗi tải class và giữ lại tài nguyên sau redeploy.