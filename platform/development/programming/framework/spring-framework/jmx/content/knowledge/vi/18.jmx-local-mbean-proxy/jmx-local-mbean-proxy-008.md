# Phân biệt proxy MBean local với gọi trực tiếp bean Spring

## Mục tiêu học tập

Bài học này thuộc nhóm **Proxy MBean local** của Spring Framework JMX. Sau khi hoàn thành, bạn có thể:

- Giải thích đường đi của một lời gọi Java thông thường tới Spring bean và lời gọi thông qua một JMX MBean proxy trong cùng JVM.
- Phân biệt **Spring bean**, **MBean đã đăng ký**, **JMX `ObjectName`** và **MBean proxy**.
- Cấu hình `MBeanExporter` ở phía công bố và `MBeanProxyFactoryBean` ở phía sử dụng.
- Dùng cùng một management interface để gọi trực tiếp bean hoặc gọi qua registry, rồi xác minh hai đường đi.
- Hiểu khác biệt về kiểm tra kiểu, metadata, lỗi, chi phí, vòng đời và ảnh hưởng của AOP.
- Biết khi nào nên inject trực tiếp Spring bean và khi nào một local JMX proxy là lựa chọn phù hợp.

## 1. Hai cách gọi có vẻ giống nhau nhưng khác đường đi

Giả sử ứng dụng Spring có một đối tượng `JobMonitor` với các phương thức `getProcessedCount()`, `isEnabled()`, `setEnabled(boolean)` và `reset()`. Có hai cách truy cập:

**Gọi trực tiếp Spring bean:** thành phần sử dụng nhận dependency qua `@Autowired`, constructor injection hoặc `ApplicationContext.getBean(...)`, sau đó gọi phương thức trên reference Java.

**Gọi qua local JMX proxy:** thành phần sử dụng giữ reference tới một Java proxy biểu diễn MBean. Proxy kết nối đến `MBeanServerConnection` trong cùng JVM, dùng `ObjectName` tìm registration và chuyển method call thành các thao tác JMX như `getAttribute`, `setAttribute` hoặc `invoke`.

Sơ đồ:

```text
A. Đường trực tiếp
   Spring Service
        |
        | jobMonitor.reset()
        v
   Spring bean reference
        |
        v
   JobMonitor instance

B. Đường local JMX proxy
   Spring Service
        |
        | jobMonitorProxy.reset()
        v
   MBean proxy
        |
        | MBeanServerConnection.invoke(ObjectName, ...)
        v
   MBeanServer registry
        |
        | tìm MBean theo ObjectName
        v
   JobMonitor được export
```

Điểm khác biệt không nằm ở cú pháp gọi trong Java: cả hai có thể là `monitor.reset()`. Điểm khác nằm ở **reference trỏ tới loại object nào** và những cơ chế trung gian mà lời gọi đi qua.

“Local” ở đây nghĩa là proxy truy cập `MBeanServerConnection` cùng tiến trình, không cần tạo một kết nối JMX qua TCP. Tuy nhiên local proxy vẫn đi qua hợp đồng JMX, chứ không biến thành lời gọi trực tiếp trên bean.

## 2. Những thành phần cần phân biệt

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Spring bean | Đối tượng do IoC container quản lý | `JobMonitor` |
| Management interface | Các method được phép công bố và gọi qua JMX | `JobMonitorMBean` |
| MBeanExporter | Đăng ký bean vào JMX server | `MBeanExporter` |
| MBeanServer | Registry và cổng truy cập MBean | Platform `MBeanServer` |
| ObjectName | Định danh registration trong một server | `com.example.jobs:type=JobMonitor,name=primary` |
| MBean proxy | Java object chuyển method call thành JMX request | `MBeanProxyFactoryBean` |
| Spring AOP proxy | Đối tượng thay mặt bean để áp dụng interceptor như transaction, security, logging | Proxy do Spring AOP tạo |

**JMX MBean proxy không đồng nghĩa Spring AOP proxy.** Chúng có thể đều xuất hiện dưới dạng Java proxy, nhưng có mục đích và đường xử lý khác nhau. MBean proxy đóng vai trò **client của JMX management interface**; Spring AOP proxy là một cơ chế áp dụng cross-cutting advice trong ứng dụng.

## 3. Ví dụ Standard MBean được cả hai cách sử dụng

Để bài tập có cùng hợp đồng Java ở hai phía, tạo một Standard MBean.

**JobMonitorMBean.java**

```java
package com.example.jmx;

public interface JobMonitorMBean {
    int getProcessedCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void reset();
}
```

**JobMonitor.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger processed = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordCompletedJob() {
        if (enabled) {
            processed.incrementAndGet();
        }
    }

    @Override
    public int getProcessedCount() {
        return processed.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void reset() {
        processed.set(0);
    }
}
```

Interface `JobMonitorMBean` có đúng hậu tố mà JMX Standard MBean convention yêu cầu với class `JobMonitor`. Bốn method thuộc management interface; `recordCompletedJob()` không nằm trong interface quản lý nên không tự xuất như operation.

Trong registry, các phần tử quản trị thường gồm:

| Java method | Phần tử JMX | Ý nghĩa |
| --- | --- | --- |
| `getProcessedCount()` | Attribute `ProcessedCount`, chỉ đọc | Đếm tác vụ |
| `isEnabled()` và `setEnabled(boolean)` | Attribute `Enabled`, đọc/ghi | Thay trạng thái |
| `reset()` | Operation `reset` | Reset bộ đếm |
| `recordCompletedJob()` | Không thuộc API Standard MBean | Chỉ gọi trực tiếp qua class phù hợp |

Việc tạo một interface dùng chung cho hai đường truy cập giúp so sánh mà không nhầm lỗi thiếu method với lỗi cấu hình JMX.

## 4. Cấu hình MBeanExporter và local MBeanProxyFactoryBean

Ví dụ dưới đây dùng Spring Framework Java configuration, một `MBeanServer` và một registration duy nhất.

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JobJmxConfiguration {

    @Bean("jobMonitor")
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter jobMonitorExporter(
            JobMonitor jobMonitor,
            MBeanServer platformMBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.jobs:type=JobMonitor,name=primary",
                jobMonitor));
        return exporter;
    }

    @Bean("jobMonitorJmxProxy")
    public MBeanProxyFactoryBean jobMonitorJmxProxy(
            MBeanServer platformMBeanServer) throws Exception {
        MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
        proxy.setServer(platformMBeanServer);
        proxy.setObjectName(new ObjectName(
                "com.example.jobs:type=JobMonitor,name=primary"));
        proxy.setProxyInterface(JobMonitorMBean.class);
        return proxy;
    }
}
```

**Giải thích cấu hình:**

1. `jobMonitor()` tạo một Spring bean thật, có lifecycle của container.
2. `platformMBeanServer()` cung cấp JMX server của JVM hiện tại.
3. `jobMonitorExporter()` đăng ký **instance JobMonitor đó** vào server với `ObjectName` cụ thể.
4. `jobMonitorJmxProxy()` tạo một `FactoryBean` xuất ra object proxy thực hiện `JobMonitorMBean`. Nó không tạo thêm `JobMonitor` nghiệp vụ.
5. Khi method được gọi trên proxy, Spring JMX access layer tương tác với MBean đã đăng ký dưới cùng `ObjectName`.

Trong cấu hình thực tế, cần bảo đảm MBean đã được exporter đăng ký trước khi proxy thực hiện kiểm tra kết nối hoặc sử dụng. Nếu thứ tự khởi tạo gây lỗi, khai báo dependency tường minh bằng `@DependsOn("jobMonitorExporter")` trên bean proxy hoặc thiết kế thứ tự lifecycle phù hợp.

Nếu đã có Spring Boot JMX auto-configuration hoặc exporter khác, không đăng ký cùng `ObjectName` hai lần. Chỉ dùng một cơ chế đăng ký cho mỗi tên.

## 5. Gọi trực tiếp và gọi qua proxy trong cùng ApplicationContext

Để thấy rõ hai references, lấy chúng theo tên bean.

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class LocalProxyDemo {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JobJmxConfiguration.class)) {

            JobMonitor direct = context.getBean(
                    "jobMonitor", JobMonitor.class);

            JobMonitorMBean viaJmx = context.getBean(
                    "jobMonitorJmxProxy", JobMonitorMBean.class);

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            System.out.println("Registered: " + server.isRegistered(name));

            direct.recordCompletedJob();
            direct.recordCompletedJob();

            System.out.println("Direct count: "
                    + direct.getProcessedCount());
            System.out.println("JMX proxy count: "
                    + viaJmx.getProcessedCount());

            viaJmx.reset();

            System.out.println("Direct count after proxy reset: "
                    + direct.getProcessedCount());
        }
    }
}
```

Kết quả mong đợi khi exporter đăng ký đúng instance:

```text
Registered: true
Direct count: 2
JMX proxy count: 2
Direct count after proxy reset: 0
```

Cả hai references cùng **quan sát một đối tượng đích** khi exporter đăng ký đúng `jobMonitor`. Tuy nhiên:

- `direct` là reference trực tiếp đến Spring bean.
- `viaJmx` là reference đến một client proxy truy cập đối tượng qua `MBeanServer`.
- Hai reference không nhất thiết là cùng Java object; so sánh `direct == viaJmx` không phải phép kiểm tra chính xác về cùng target.
- Trên proxy chỉ có các method thuộc `JobMonitorMBean`; `recordCompletedJob()` không có trong interface đó.

Sự trùng khớp về giá trị được bảo đảm bởi việc cả hai đường đi trỏ về cùng managed instance, **không phải** vì proxy có bộ nhớ trạng thái riêng rồi đồng bộ với bean.

## 6. So sánh chi tiết hành vi

| Tiêu chí | Gọi trực tiếp Spring bean | Gọi qua local MBean proxy |
| --- | --- | --- |
| Cách định vị đối tượng | Bean reference từ IoC container | `MBeanServerConnection` + `ObjectName` |
| Giao diện gọi | Các method thấy được trên Java type được inject | Chỉ method thuộc JMX proxy interface |
| Đường đi | Java method call (có thể qua Spring AOP) | Proxy → JMX attribute/operation → registered MBean |
| Yêu cầu đăng ký MBean | Không | Có |
| Có cần mạng? | Không | Không nếu kết nối server local |
| Metadata JMX | Không cần | Theo hợp đồng MBean đã công bố |
| Hiệu năng | Ít tầng trung gian hơn trong trường hợp thông thường | Có thêm dispatch, kiểm tra metadata và chuyển đổi |
| Lỗi khi tên không tồn tại | Không có khái niệm `ObjectName` | Có thể gặp lỗi kết nối/truy cập MBean |
| Method không được export | Vẫn gọi được nếu Java type cho phép | Không được gọi qua interface JMX |
| Thích hợp | Luồng nghiệp vụ nội bộ | Giao diện quản trị, kiểm thử đường JMX, tích hợp với MBean |

Điểm mấu chốt: **local JMX proxy không phải một cách inject Spring bean khác**. Nó là một client đi qua API quản trị JMX dù cùng nằm trong một tiến trình.

## 7. ObjectName quyết định mục tiêu, không phải tên Spring bean

Spring bean có thể được gọi là `jobMonitor` hoặc `primaryMonitor`, nhưng tên JMX do exporter đăng ký là một `ObjectName` độc lập:

```text
com.example.jobs:type=JobMonitor,name=primary
```

Nếu có hai instance cùng loại:

```text
com.example.jobs:type=JobMonitor,name=primary
com.example.jobs:type=JobMonitor,name=secondary
```

một local proxy được cấu hình với tên `primary` sẽ điều khiển MBean primary, bất kể component inject proxy đó được đặt tên gì trong Spring context.

Ngược lại, inject `JobMonitor` bằng `@Qualifier` sẽ lấy đúng Spring bean theo tên/qualifier được container biết. Hai cơ chế phân giải danh tính khác nhau và không có ánh xạ tự động bắt buộc giữa chúng.

Nếu proxy được cấu hình sai `ObjectName`, có thể đọc hoặc điều khiển MBean khác với ý định, đặc biệt trong JVM chứa nhiều exporters và nhiều contexts. Luôn đối chiếu full `ObjectName`.

## 8. Getter và setter được proxy chuyển thành lời gọi JMX thế nào?

Các method JavaBean trong management interface có thể được ánh xạ sang JMX attributes:

```java
int count = viaJmx.getProcessedCount();
boolean enabled = viaJmx.isEnabled();
viaJmx.setEnabled(false);
```

Ở JMX layer, ý nghĩa tương ứng thường là:

```java
server.getAttribute(name, "ProcessedCount");
server.getAttribute(name, "Enabled");
server.setAttribute(
        name, new javax.management.Attribute("Enabled", false));
```

Operation:

```java
viaJmx.reset();
```

tương ứng với một thao tác invoke như:

```java
server.invoke(
        name, "reset", new Object[0], new String[0]);
```

Spring `MBeanProxyFactoryBean` chịu trách nhiệm che các chi tiết dispatch đó đằng sau interface Java. Đừng nhầm rằng nó gọi Java method trên `JobMonitor` bằng reflection trực tiếp vào Spring bean: lời gọi phải được JMX server giải quyết theo registration và management metadata.

Đối với method có tham số, JMX dùng danh sách giá trị và chữ ký kiểu tham số. Spring proxy có thể thực hiện việc chuyển đổi cần thiết cho client. Với kiểu tùy biến, Standard MBean hoặc MXBean có các yêu cầu dữ liệu khác nhau; client proxy không tự làm mọi Java DTO trở nên truyền được qua JMX.

## 9. Direct call vẫn có thể đi qua Spring AOP

“Gọi trực tiếp bean Spring” không luôn nghĩa là gọi thẳng object gốc không có bất kỳ interceptor nào. Nếu bean được Spring AOP tạo proxy để thực hiện transaction, security hoặc aspect khác, dependency mà service nhận được có thể đã là **AOP proxy**.

Ví dụ:

```text
Service
  |
  | directBean.execute()
  v
Spring AOP proxy
  |
  | transaction/security/logging advice
  v
Target bean
```

Trong khi đó, local MBean proxy có đường riêng:

```text
Service
  |
  | jmxProxy.execute()
  v
JMX client proxy
  |
  v
MBeanServer
  |
  v
MBean registration / adapter
  |
  v
Target object
```

Nếu `MBeanExporter` đã đăng ký một Spring AOP proxy làm managed object, đường JMX có thể đi qua AOP advice tùy cách exporter xây dựng adapter và object được đăng ký. Nếu exporter đăng ký raw target instance, advice có thể không được áp dụng theo cùng cách.

Vì vậy không nên phát biểu tuyệt đối rằng JMX proxy “luôn bypass AOP” hoặc “luôn áp dụng tất cả Spring advice”. Cần xác định exporter đăng ký **object nào** và kiểm tra behavior theo cấu hình đang chạy.

Đối với luồng nghiệp vụ cần transaction/security của Spring, inject service theo đúng kiến trúc ứng dụng; không dùng JMX proxy như đường gọi thay thế chỉ vì cùng interface.

## 10. Vấn đề lifecycle của proxy và exporter

Proxy có thể được tạo trong context, nhưng MBean tương ứng có thể chưa được đăng ký hoặc có thể bị gỡ trong quá trình runtime.

Những tình huống cần xét:

1. **Proxy khởi tạo trước exporter:** nếu proxy kiểm tra kết nối hoặc metadata sớm, nó có thể không tìm thấy MBean. Dùng dependency rõ ràng.
2. **Exporter khởi động thành công nhưng chọn server khác:** proxy dùng `MBeanServer` A, exporter dùng B thì `ObjectName` có thể không tồn tại trên A.
3. **Context chứa exporter đóng:** MBean được unregister, nhưng một reference tới proxy còn tồn tại ở thành phần khác. Lời gọi tiếp theo có thể thất bại.
4. **MBean bị thay thế dưới cùng tên:** proxy có thể tiếp tục giải quyết cùng `ObjectName` nhưng trỏ tới implementation khác, miễn contract tương thích.
5. **Server tùy biến được release:** proxy không thể giả định server còn hoạt động hay registration còn hợp lệ sau khi owner đóng.

Một cách thiết kế an toàn là để exporter, server và proxy có lifecycle rõ ràng trong cùng scope Spring context, đồng thời tránh giữ proxy vượt vòng đời của server mà nó truy cập.

## 11. Cách proxy xác nhận thuộc tính và operation của MBean

Trước khi gọi, công cụ JMX hoặc code kiểm tra có thể truy vấn metadata:

```java
MBeanServer server = context.getBean(MBeanServer.class);

ObjectName name = new ObjectName(
        "com.example.jobs:type=JobMonitor,name=primary");

if (!server.isRegistered(name)) {
    throw new IllegalStateException("JobMonitor MBean is missing");
}

var info = server.getMBeanInfo(name);

for (var attribute : info.getAttributes()) {
    System.out.println("Attribute: " + attribute.getName());
}

for (var operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
```

Đây là cách xác minh interface quản trị thực tế. Một proxy interface có method mà MBean không công bố có thể được tạo thành công ở một số cấu hình, nhưng lỗi phát sinh khi gọi hoặc khi kiểm tra metadata.

Chỉ kiểm tra `isRegistered(name)` không đủ chứng minh contract tương thích. Có thể một MBean khác đã đăng ký trước dưới cùng `ObjectName`; cần đối chiếu attributes, operations và dữ liệu nhận diện instance.

## 12. Các loại lỗi và cách xử lý

| Triệu chứng | Khi gọi trực tiếp | Khi dùng local JMX proxy |
| --- | --- | --- |
| Không có bean | Lỗi dependency injection hoặc `NoSuchBeanDefinitionException` | Proxy bean có thể tồn tại nhưng MBean target bị thiếu |
| Sai đích | Inject nhầm bean cùng type | Proxy trỏ sai `ObjectName` hoặc server |
| Không thấy method | Java type/interface không khai báo method | Proxy interface/MBean management metadata không công bố |
| Lỗi trong business method | Java exception theo đường gọi AOP hoặc target | Exception có thể được JMX/Spring access layer bọc hoặc chuyển thành exception truy cập |
| MBean bị unregister | Không ảnh hưởng direct bean nếu bean vẫn sống | Lời gọi proxy có thể thất bại vì target registration biến mất |
| Không có JMX server | Direct call vẫn hoạt động | Proxy cần `MBeanServerConnection` phù hợp |
| Lỗi chữ ký JMX | Không có riêng tầng này | Operation signature/attribute mapping có thể không khớp |
| Sai server khi nhiều contexts | Tùy bean injection scope | Proxy và exporter có thể dùng hai server khác nhau |

Có thể gặp `InstanceNotFoundException`, `AttributeNotFoundException`, `ReflectionException` hoặc exception được Spring JMX access layer ánh xạ/bọc. Để chẩn đoán, đọc root cause, xác minh `ObjectName`, `MBeanInfo` và trạng thái registry. Không tự coi lỗi từ client là bằng chứng rằng operation chắc chắn không chạy: với các operation có side effect, trạng thái thực tế có thể cần được đọc lại trước khi retry.

## 13. Ưu điểm và giới hạn về hiệu năng

Lời gọi trực tiếp qua Java reference thường có ít bước hơn lời gọi qua local JMX proxy. JMX client proxy phải tạo request ở tầng management, phân giải method thành attribute/operation và đi qua `MBeanServer`.

Dù cùng JVM và không có mạng, các bước đó vẫn tiêu tốn xử lý. Vì vậy:

- Dùng direct bean reference cho đường nóng như xử lý từng request, từng item trong batch hoặc gọi rất thường xuyên.
- Dùng local JMX proxy khi cần diễn tập đường quản trị, tái sử dụng hợp đồng quản lý hoặc tích hợp với thành phần vốn làm việc qua JMX.
- Không mặc định JMX proxy là lựa chọn tốt cho business-to-business dependency bên trong Spring application.
- Không đánh giá hiệu năng chỉ bằng trực giác nếu hệ thống có yêu cầu latency cụ thể; đo đạc trong runtime thực tế khi cần.

Local proxy không tạo mạng không có nghĩa là không có overhead; ngược lại, overhead đó không đồng nghĩa mọi lời gọi JMX đều chậm đến mức không dùng được. Phù hợp hay không phụ thuộc tần suất và mục đích.

## 14. Kiểm thử so sánh hai đường gọi

Một integration test nên xác nhận cùng trạng thái target nhưng references khác nhau.

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class LocalJmxProxyTest {

    @Test
    void localProxyAndSpringBeanReachSameMBeanState() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JobJmxConfiguration.class)) {

            JobMonitor direct = context.getBean(
                    "jobMonitor", JobMonitor.class);

            JobMonitorMBean proxy = context.getBean(
                    "jobMonitorJmxProxy", JobMonitorMBean.class);

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            assertTrue(server.isRegistered(name));

            direct.recordCompletedJob();
            direct.recordCompletedJob();

            assertEquals(2, direct.getProcessedCount());
            assertEquals(2, proxy.getProcessedCount());

            proxy.setEnabled(false);
            direct.recordCompletedJob();

            assertEquals(2, direct.getProcessedCount());
            assertFalse(direct.isEnabled());

            proxy.reset();
            assertEquals(0, direct.getProcessedCount());
        }
    }
}
```

Bài test so sánh hành vi giữa direct reference và JMX proxy bằng cùng giá trị attribute, thay vì kiểm tra identity `==`. Nếu nhiều tests dùng platform `MBeanServer` và cùng `ObjectName` khi chạy song song, có thể gặp `InstanceAlreadyExistsException`. Dùng một server riêng cho test hoặc tên phân biệt để cô lập fixture.

### Kiểm thử sai ObjectName

Tạo một proxy trỏ tới:

```text
com.example.jobs:type=JobMonitor,name=missing
```

rồi gọi `getProcessedCount()`. Xác minh lỗi truy cập MBean hoặc lỗi kiểm tra metadata, đồng thời ghi nhận direct bean vẫn có thể truy cập bình thường. Đó là bằng chứng rằng JMX proxy cần registry còn direct call không cần.

## 15. Sử dụng MBeanServerConnection trực tiếp để hiểu proxy

Nếu muốn bỏ lớp tiện ích Spring để quan sát cơ chế bên dưới:

```java
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = context.getBean(MBeanServer.class);
ObjectName name = new ObjectName(
        "com.example.jobs:type=JobMonitor,name=primary");

JobMonitorMBean jmxProxy = JMX.newMBeanProxy(
        server, name, JobMonitorMBean.class);

int count = jmxProxy.getProcessedCount();
jmxProxy.reset();
```

`JMX.newMBeanProxy(...)` thuộc JDK và tạo proxy cho Standard MBean interface. `MBeanProxyFactoryBean` là tiện ích Spring giúp quản lý proxy như một bean, cấu hình server/name/interface và tích hợp với dependency injection.

Trong môi trường local, `MBeanServer` cũng thực hiện `MBeanServerConnection`, nên có thể truyền trực tiếp cho cơ chế proxy. Nếu ở môi trường remote, `MBeanServerConnection` nhận được từ `JMXConnector` sau khi kết nối đến server. Dù cùng management interface, remote call có thêm vấn đề mạng, xác thực, serialization và timeout.

## 16. Khi nào nên chọn từng cách?

**Chọn direct Spring bean injection khi:**

- Thành phần gọi là một phần luồng xử lý nghiệp vụ nội bộ.
- Cần API đầy đủ của bean, không chỉ management interface.
- Muốn tận dụng dependency injection, Spring AOP và transaction boundaries theo kiến trúc ứng dụng.
- Gọi method thường xuyên và muốn tránh dispatch JMX không cần thiết.
- Không có nhu cầu coi một `ObjectName` là hợp đồng truy cập.

**Chọn local MBean proxy khi:**

- Đang xây dựng một tool hoặc module quản trị dựa trên hợp đồng JMX.
- Muốn kiểm tra đường đi qua `MBeanServer` giống JConsole/client JMX.
- Component client không nên phụ thuộc vào implementation class của target.
- Cần truy cập một MBean đã được đăng ký theo `ObjectName`, kể cả khi không có reference Spring bean trực tiếp.
- Muốn mô phỏng một JMX client trong cùng JVM mà không cần remote connector.

Nếu ứng dụng đã giữ trực tiếp bean và không cần đường JMX, tạo thêm local proxy chỉ để gọi một method nghiệp vụ thường làm kiến trúc phức tạp hơn.

## 17. Các sai lầm thường gặp

### “Cùng JVM thì proxy chính là bean”

Sai. Một local JMX proxy là object client khác, chuyển cuộc gọi qua registry. Nó có thể truy cập **cùng target**, nhưng không phải cùng reference hay cùng call path.

### “JMX proxy gọi được mọi method public”

Sai. Proxy bị giới hạn bởi interface được cấu hình và contract MBean được server công bố. Method chỉ nằm trong implementation mà không thuộc management interface không tự xuất ra JMX.

### “Có Spring bean là có MBean”

Sai. Bean phải được exporter đăng ký hoặc được một cơ chế JMX registration khác đưa vào server. Bản thân `ApplicationContext` không tự đồng nghĩa registry JMX.

### “Gọi trực tiếp luôn bỏ qua proxy”

Sai. Spring dependency có thể là AOP proxy khi bean được áp dụng aspect. Phải phân biệt AOP proxy và JMX proxy bằng mục tiêu và đường xử lý.

### “Đúng ObjectName là chắc chắn đúng instance”

Chưa đủ. Có thể exporter khác đã đăng ký hoặc thay thế MBean tại tên đó. Nếu quan trọng, kiểm tra attribute nhận diện, metadata và owner của registration.

### “Proxy local không cần quan tâm lifecycle”

Sai. MBean có thể bị unregister, server có thể được release và context có thể đóng. Reference proxy còn tồn tại không đảm bảo target JMX tiếp tục truy cập được.

## 18. Bài tập thực hành

**Bài 1 — Hai đường gọi.** Tạo `JobMonitor`, exporter và local proxy như ví dụ. Gọi `recordCompletedJob()` trực tiếp hai lần rồi đọc `ProcessedCount` qua proxy. Reset bằng proxy và xác minh direct bean trả 0.

**Bài 2 — Method không export.** Thử gọi `recordCompletedJob()` trên biến kiểu `JobMonitorMBean`. Giải thích vì sao Java compiler không cho phép dù method có trên lớp implementation, rồi đối chiếu với JMX `MBeanInfo`.

**Bài 3 — Sai target.** Cấu hình proxy sai `ObjectName`, xác định lỗi phát sinh lúc khởi tạo hay khi invoke trong cấu hình bạn dùng, rồi sửa tên. Kiểm tra server thực tế thay vì chỉ đổi bean name.

**Bài 4 — Hai instance.** Đăng ký `primary` và `secondary` dưới hai tên khác nhau. Tạo hai local JMX proxies dùng chung interface, mỗi proxy trỏ tới một `ObjectName`. Chứng minh reset primary không đổi số đếm secondary.

**Bài 5 — AOP.** Thêm một aspect logging quanh `reset()` rồi so sánh hành vi direct call và JMX proxy. Xác định object thực sự được exporter đăng ký trước khi giải thích vì sao advice có hoặc không được áp dụng.

## Kết luận

**Gọi trực tiếp Spring bean** đi theo reference do IoC container cung cấp và là cách thông thường cho logic ứng dụng. **Local MBean proxy** là một JMX client trong cùng JVM: nó dùng `MBeanServerConnection` và `ObjectName` để truy cập management interface đã được đăng ký. Hai con đường có thể chạm cùng target và cùng trạng thái, nhưng khác nhau về cơ chế phân giải object, API được phép gọi, metadata, xử lý lỗi, lifecycle và overhead. Chọn direct injection cho nghiệp vụ nội bộ; dùng local JMX proxy khi thật sự cần thao tác qua hợp đồng JMX.
