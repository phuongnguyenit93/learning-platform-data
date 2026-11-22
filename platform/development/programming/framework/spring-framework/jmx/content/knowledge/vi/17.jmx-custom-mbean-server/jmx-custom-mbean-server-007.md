# Quản lý vòng đời MBeanServer tùy biến trong container Spring

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích vòng đời của một `MBeanServer` do Spring Framework quản lý, phân biệt server do Spring tạo với server có sẵn trong JVM, sử dụng `MBeanServerFactoryBean` hoặc `@Bean` để cung cấp server cho `MBeanExporter`, xử lý việc khởi tạo/đăng ký/hủy đăng ký MBean khi `ApplicationContext` đóng, đồng thời tránh mất MBean hoặc tài nguyên bị giữ lại khi ứng dụng được khởi động lại trong cùng JVM.

Nội dung tập trung vào **MBeanServer tùy biến** trong Spring IoC container, không phải vòng đời của container Docker. “Container” ở đây chủ yếu là `ApplicationContext` và quá trình Spring quản lý các bean.

## 1. Phân biệt vòng đời MBean, MBeanServer và ApplicationContext

JMX (Java Management Extensions) cung cấp `MBeanServer` để quản lý các đối tượng (MBean) được đăng ký dưới `ObjectName` duy nhất. Trong ứng dụng Spring:

- `ApplicationContext` quản lý lifecycle của Spring beans.
- `MBeanExporter` đăng ký các managed beans vào `MBeanServer` và có khả năng hủy đăng ký những MBean thuộc trách nhiệm của nó khi exporter bị destroy.
- `MBeanServer` giữ registry quản trị cho đến khi server được giải phóng hoặc JVM kết thúc; vòng đời thực tế phụ thuộc server do ai tạo.
- JMX client như JConsole đọc registry qua kết nối đến server thích hợp.

Đây là ba trách nhiệm khác nhau. Việc đóng `ApplicationContext` không luôn đồng nghĩa giải phóng platform `MBeanServer`, và việc giải phóng một server không nên được xem là cách thay thế cho việc để exporter dọn các registration do nó sở hữu.

Sơ đồ lifecycle:

```text
Spring ApplicationContext.start/refresh
       |
       +--> tạo hoặc lấy MBeanServer
       |
       +--> tạo managed Spring beans
       |
       +--> khởi tạo MBeanExporter
                 |
                 +--> registerMBean(bean, ObjectName)
       |
       v
Ứng dụng hoạt động: JConsole/JMX client đọc MBeans
       |
Spring ApplicationContext.close
       |
       +--> destroy exporter -> unregister MBeans do exporter quản lý
       |
       +--> destroy bean quản lý server (nếu là server do bean tạo)
                 |
                 +--> release server phù hợp với ownership
```

Thứ tự destroy bean còn phụ thuộc dependency graph; vì vậy phải biểu diễn quan hệ exporter → server rõ ràng thay vì giả định thứ tự ngẫu nhiên.

## 2. MBeanServer do ứng dụng tạo hay do JVM cung cấp?

Hai trường hợp dễ bị nhầm:

### Platform MBeanServer

```java
MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
```

Đây là server nền tảng của JVM. Các platform MXBeans thông thường được công bố qua server này. Nếu Spring chỉ **mượn** platform server, Spring không phải owner của nó và không nên giải phóng server nền tảng khi context đóng.

Nếu khai báo:

```java
@Bean
public MBeanServer platformMBeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
```

thì bean `MBeanServer` chỉ trả về một server có sẵn. Về mặt ownership, Spring context đang sử dụng server chứ không tạo một server JMX độc lập cần release.

### Server tùy biến

```java
MBeanServer custom =
        MBeanServerFactory.createMBeanServer("custom.monitoring");
```

Đây là một `MBeanServer` mới, tách khỏi platform server. Nếu tạo bằng `MBeanServerFactory.createMBeanServer`, server được thêm vào danh sách do JMX factory theo dõi để có thể tìm và giải phóng sau đó. Thành phần tạo server nên xác định rõ thời điểm gọi `MBeanServerFactory.releaseMBeanServer(custom)`.

**Quan trọng:** `releaseMBeanServer` chỉ áp dụng hợp lệ đối với server do factory tạo và còn được factory quản lý theo cơ chế tương ứng. Nó không phải lệnh “xóa mọi MBean” hay “đóng toàn bộ kết nối JMX” theo một hợp đồng tổng quát.

Trong Spring, `MBeanServerFactoryBean` là tiện ích phù hợp để đưa quá trình tạo/tìm server và lifecycle thành phần của IoC container.

## 3. Dùng MBeanServerFactoryBean để Spring sở hữu custom server

`org.springframework.jmx.support.MBeanServerFactoryBean` là `FactoryBean<MBeanServer>` cung cấp một server JMX cho các bean khác. Nó hỗ trợ cấu hình `defaultDomain`, chế độ tìm server hiện có và vòng đời giải phóng server mà nó tự tạo.

Ví dụ:

```java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class CustomServerConfiguration {

    @Bean(name = "applicationMBeanServer")
    public MBeanServerFactoryBean applicationMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.management");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }
}
```

Ở đây, Spring quản lý **factory bean**, còn các bean muốn inject một `MBeanServer` nhận object do factory cung cấp. Vì `locateExistingServerIfPossible=false`, cấu hình yêu cầu tạo server mới thay vì cố tìm server đã tồn tại.

`defaultDomain` là domain mặc định cho `ObjectName` được tạo mà không có domain theo quy tắc JMX tương ứng; nó không tự đặt tất cả MBean của ứng dụng vào một domain hay đảm bảo tính duy nhất toàn hệ thống.

Cách trả trực tiếp `MBeanServerFactoryBean` qua `@Bean` cho phép Spring quản lý lifecycle của factory. Ngược lại, nếu tự `new MBeanServerFactoryBean()`, gọi `afterPropertiesSet()` rồi chỉ trả `factory.getObject()`, container có thể không biết đến factory để gọi destroy và giải phóng server. Nếu chọn cách đó, bạn phải tự có cơ chế cleanup.

## 4. Cung cấp custom server cho MBeanExporter

Tạo Standard MBean để quan sát việc đăng ký:

**JobMonitorMBean.java**

```java
package com.example.jmx;

public interface JobMonitorMBean {
    int getCompletedJobs();
    void recordCompletedJob();
}
```

**JobMonitor.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger completed = new AtomicInteger();

    @Override
    public int getCompletedJobs() {
        return completed.get();
    }

    @Override
    public void recordCompletedJob() {
        completed.incrementAndGet();
    }
}
```

Đưa exporter và server vào cùng Spring configuration:

```java
package com.example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class CustomJmxConfiguration {

    @Bean(name = "applicationMBeanServer")
    public MBeanServerFactoryBean applicationMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.management");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanExporter jobMonitorExporter(
            JobMonitor jobMonitor,
            MBeanServer applicationMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(applicationMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.management:type=JobMonitor,name=primary",
                jobMonitor
        ));
        return exporter;
    }
}
```

Lúc này `MBeanExporter` đăng ký vào **custom server** chứ không phải mặc định là platform server. Hai server có registry độc lập, ngay cả khi nằm trong cùng JVM.

Để tránh mơ hồ nếu context chứa nhiều bean kiểu `MBeanServer`, có thể dùng `@Qualifier("applicationMBeanServer")` trong tham số factory method của exporter. Sự phụ thuộc này cũng giúp Spring nhận biết exporter cần server trong lifecycle.

## 5. Chạy ApplicationContext và đọc registry

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class CustomServerDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer capturedServer;

        try (var context = new AnnotationConfigApplicationContext(
                CustomJmxConfiguration.class)) {

            capturedServer = context.getBean(
                    "applicationMBeanServer", MBeanServer.class);

            ObjectName name = new ObjectName(
                    "com.example.management:type=JobMonitor,name=primary");

            System.out.println(
                    "Custom registered: " + capturedServer.isRegistered(name));

            JobMonitor monitor = context.getBean(JobMonitor.class);
            monitor.recordCompletedJob();

            System.out.println(
                    "CompletedJobs: "
                    + capturedServer.getAttribute(name, "CompletedJobs"));

            System.out.println(
                    "Default domain: " + capturedServer.getDefaultDomain());
        }

        // Context đã đóng: exporter và factory đều được destroy.
        // Không sử dụng capturedServer như một dịch vụ quản trị còn sống.
    }
}
```

Trước khi đóng context, server có thể trả `Custom registered: true` và `CompletedJobs: 1`.

Khi context đóng đúng cách, exporter cần unregister MBean mà nó quản lý và factory chịu trách nhiệm release server do nó tạo. Không nên tiếp tục dùng reference `capturedServer` như một server được bảo đảm còn nằm trong vòng đời quản lý của ứng dụng sau khi context đã đóng.

Một `MBeanServer` được release khỏi factory registry có thể vẫn là một Java object nếu còn reference, nhưng điều đó không đồng nghĩa lifecycle hợp lệ hoặc đang được JMX discovery quản lý. Test cần kiểm tra chính sách và ownership thay vì suy ra object bị garbage-collected ngay.

## 6. Spring lifecycle: init và destroy bean

`ApplicationContext.refresh()` khởi tạo các bean theo dependency graph. `MBeanServerFactoryBean` thực hiện phần khởi tạo server khi được tạo. `MBeanExporter` cũng sử dụng các lifecycle callback của Spring để đăng ký MBean.

Khi `ApplicationContext.close()`:

1. Container phát tín hiệu đóng.
2. Lifecycle processor dừng các `Lifecycle` hoặc `SmartLifecycle` beans nếu có.
3. Các singleton beans được destroy theo quan hệ dependency và quy tắc của container.
4. Exporter unregister MBeans do nó quản lý.
5. Factory quản lý server được destroy/release nếu nó sở hữu server đã tạo.

Trong cấu hình exporter có tham số `MBeanServer`, Spring biết exporter phụ thuộc vào server. Điều này giúp quá trình destroy giữ server sẵn có khi exporter còn cần hủy registration. Nếu cấu hình bằng tham chiếu không được container nắm rõ, nên xác minh lifecycle thực tế; có thể dùng `@DependsOn` hoặc dependency injection tường minh thay vì chỉ dựa vào thứ tự khai báo method trong file Java.

**Không nên gọi `MBeanServerFactory.releaseMBeanServer` từ một `@PreDestroy` ngẫu nhiên của business bean** khi exporter còn có thể phải unregister các MBean. Hãy để thành phần owner của server thực hiện cleanup tại thời điểm phù hợp.

## 7. locateExistingServerIfPossible: vay mượn server hay tạo mới?

`MBeanServerFactoryBean` có cấu hình quyết định có tìm server sẵn có trước hay không.

```java
factory.setLocateExistingServerIfPossible(true);
```

Khi bật tìm server hiện có, factory có thể sử dụng một `MBeanServer` đang tồn tại nếu phù hợp, hoặc tạo mới khi không tìm thấy. Điều này thay đổi ownership:

| Tình huống | Nguồn server | Nguyên tắc lifecycle |
| --- | --- | --- |
| Factory tạo server mới | Custom JMX server thuộc về factory | Factory có thể release server nó tạo |
| Factory tìm được server hiện có | Server được component khác tạo/quản lý | Không tự ý release server mà factory không sở hữu |
| App lấy platform MBeanServer trực tiếp | Server nền tảng JVM | Không release khi Spring context đóng |

Hành vi tìm server có thể phụ thuộc danh sách server đang tồn tại và tiêu chí tìm kiếm. Nếu yêu cầu thử nghiệm hoặc production bắt buộc một server riêng để cô lập registry, hãy cấu hình rõ thay vì dựa vào kết quả tìm kiếm tự động.

Một ứng dụng có nhiều `ApplicationContext` cùng JVM cần thống nhất ownership server. Nếu cả hai context mượn một server chung thì chúng không nên tự release server đó khi chỉ một context đóng.

## 8. Vấn đề nhiều ApplicationContext dùng chung MBeanServer

Giả sử một JVM có root context và child context:

```text
JVM
  |
  +-- Root ApplicationContext
  |      |
  |      +-- sharedMBeanServer
  |      +-- exporterA -> ObjectName A
  |
  +-- Child ApplicationContext
         |
         +-- exporterB -> ObjectName B
         +-- inject sharedMBeanServer
```

Mô hình này hợp lệ nếu cả hai exporter quản lý các tên riêng. Nhưng nếu root context đóng trước child context và giải phóng server do root tạo, child exporter có thể mất nền tảng registry mà nó vẫn đang sử dụng.

Có hai hướng thiết kế:

- Đặt server ở tầng có vòng đời dài hơn mọi context sử dụng nó; các context con chỉ tham chiếu/mượn server.
- Tạo server riêng cho từng context để việc đóng context này không làm ảnh hưởng registry của context kia.

Trong cả hai hướng, phải xác định `ObjectName` và owner của mỗi registration. Dùng `RegistrationPolicy.IGNORE_EXISTING` để che xung đột tên không giải quyết vấn đề vòng đời nếu các context còn lại phụ thuộc server đã bị release.

## 9. Custom server và JConsole: vì sao có thể không nhìn thấy?

Platform `MBeanServer` là nơi JConsole thường hiển thị các platform MXBeans và nhiều managed objects của JVM. Một custom server do ứng dụng tạo có thể **không được trình xem MBeans của một JConsole local connection tự động chọn hoặc liệt kê theo cách bạn kỳ vọng**.

Việc `server.isRegistered(name)=true` trên custom server không chứng minh JConsole đang kết nối tới chính server đó.

Khi chẩn đoán:

1. Đọc `MBeanServer` được inject vào exporter.
2. Kiểm tra `isRegistered(name)` trên **chính server đó**.
3. Xác định connector/client đang kết nối đến server nào.
4. Nếu cần quản trị custom server từ xa, tạo và quản lý `JMXConnectorServer` thích hợp gắn với server đó.
5. Kiểm soát transport, xác thực và mạng trước khi mở endpoint JMX.

Nếu mục đích chỉ là xem MBeans bằng JConsole local theo tiến trình, dùng platform server thường ít phức tạp hơn. Custom server hữu ích khi cần cô lập registry, lifecycle hoặc yêu cầu quản trị đặc biệt, nhưng phải chủ động thiết kế kết nối client.

## 10. JMXConnectorServer có vòng đời riêng

`MBeanServer` quản lý registry; `JMXConnectorServer` cung cấp một endpoint để client kết nối qua một giao thức như JMX RMI. Hai thành phần không đồng nhất.

```text
ApplicationContext
   |
   +-- MBeanServer (registry)
   |
   +-- MBeanExporter (register MBeans)
   |
   +-- JMXConnectorServer (network endpoint)
              |
              v
        Remote JMX clients
```

Nếu ứng dụng tạo connector cho custom server, nó cần được start/stop theo lifecycle của ứng dụng. Không nên giả định `MBeanServerFactoryBean` tự tạo và quản lý remote connector.

Một bean wrapper lifecycle có thể thực hiện `connector.start()` ở giai đoạn start và `connector.stop()` khi destroy. Với Spring, có thể dùng `@Bean(initMethod="start", destroyMethod="stop")` nếu đối tượng và cấu hình endpoint đáp ứng yêu cầu, hoặc xây dựng `SmartLifecycle` cho thứ tự và trạng thái start/stop phức tạp.

Việc mở remote JMX có rủi ro quản trị cao vì có thể cho phép đọc thuộc tính hoặc gọi operation gây side effect. Cần xác thực, mã hóa và kiểm soát truy cập mạng theo môi trường. Không mở endpoint quản trị ra mạng công cộng chỉ để kiểm thử.

## 11. Dọn MBean khi context đóng và vấn đề ownership

`MBeanExporter` thường quản lý việc unregister các MBeans mà chính nó đăng ký. Khi có nhiều exporter dùng chung server, mỗi exporter cần có trách nhiệm rõ với `ObjectName` của mình.

Ví dụ:

```text
Exporter A -> com.example:type=Cache,name=primary
Exporter B -> com.example:type=Cache,name=secondary
```

Nếu cả hai được đăng ký thành công, đóng context chứa exporter A chỉ nên hủy MBean A, không tự ý hủy B.

Nếu hai exporter cùng cố đăng ký dưới một tên, registration policy (`FAIL_ON_EXISTING`, `IGNORE_EXISTING`, `REPLACE_EXISTING`) sẽ ảnh hưởng ownership và cleanup. Đặc biệt, policy `REPLACE_EXISTING` có thể làm thay đổi MBean đang nằm dưới cùng tên, còn `IGNORE_EXISTING` có thể khiến exporter mới không thực sự sở hữu registration đó.

Vì vậy, trước khi xử lý lifecycle phức tạp, nên dùng naming strategy tạo `ObjectName` duy nhất. Registration policy không phải cơ chế thay thế cho quản lý owner.

## 12. Kiểm thử với server riêng, không làm nhiễm platform registry

Một integration test có thể tạo `MBeanServer` riêng cho fixture và release sau khi hoàn thành.

Ví dụ JUnit:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class CustomMBeanServerLifecycleTest {

    @Test
    void contextRegistersAndUnregistersMBeans() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("isolated-test");

        ObjectName name = new ObjectName(
                "com.example.management:type=JobMonitor,name=primary");

        try {
            try (var context = new AnnotationConfigApplicationContext()) {
                context.registerBean(
                        "externalTestServer",
                        MBeanServer.class,
                        () -> server);

                context.registerBean(JobMonitor.class);

                context.registerBean(
                        MBeanExporter.class,
                        () -> {
                            MBeanExporter exporter = new MBeanExporter();
                            exporter.setServer(server);
                            exporter.setBeans(
                                    java.util.Map.of(
                                            name.toString(),
                                            context.getBean(JobMonitor.class)));
                            return exporter;
                        });

                context.refresh();

                assertTrue(server.isRegistered(name));
            }

            assertFalse(server.isRegistered(name));
        } finally {
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Đây là ví dụ minh họa quản lý **server ở ngoài** Spring context, còn exporter được container quản lý. Khi context đóng, exporter unregister MBean; test cuối cùng release server do chính nó tạo. Mục tiêu chính là tách rõ hai nghĩa vụ cleanup.

Khi áp dụng, cần dùng cách đăng ký bean phù hợp Spring version, đảm bảo exporter có dependency rõ với managed bean và server. Nếu Spring context có thêm MBean exporter tự động, loại bỏ hoặc cô lập cơ chế đó trong test để tránh đăng ký trùng.

## 13. Cách test lifecycle của MBeanServerFactoryBean

Một test khác có thể dùng server được Spring factory tạo và quản lý. Vì sau `context.close()` server có thể đã được release, không nên chỉ dùng `server.isRegistered(...)` để kết luận server đã biến mất khỏi factory registry.

Có thể đối chiếu danh sách server do `MBeanServerFactory` theo dõi, nhưng phải tránh cùng default domain hoặc server khác có sẵn gây nhầm. Test cô lập nên có domain riêng:

```java
MBeanServer server;
try (var context = new AnnotationConfigApplicationContext(
        CustomJmxConfiguration.class)) {
    server = context.getBean(
            "applicationMBeanServer", MBeanServer.class);
    // assert registered ...
}
// Sau khi context đóng, không còn do Spring factory quản lý.
// Nếu cần, kiểm tra registry của MBeanServerFactory theo identity server.
```

Việc `releaseMBeanServer` loại server khỏi danh sách quản lý của JMX factory không yêu cầu object Java bị GC ngay. Vì vậy, test lifecycle phải kiểm tra **cleanup hợp đồng**, không kiểm tra sự biến mất vật lý của object.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Custom server không thấy trong JConsole | JConsole kết nối platform server, không phải custom server | Đọc đúng server hoặc cấu hình connector tới custom server |
| MBean vẫn xuất hiện sau khi Spring context đóng | Có exporter khác sở hữu tên hoặc context không đóng | Kiểm tra lifecycle, owner và server đang đọc |
| Server bị release dù context khác vẫn dùng | Ownership đặt sai tầng | Chuyển server lên scope dài hơn hoặc tách server |
| Registry tồn tại nhưng MBean biến mất | Exporter đã unregister khi context đóng | Kiểm tra thứ tự đóng context |
| Test pass riêng, fail khi chạy song song | Dùng chung platform server/`ObjectName` | Tạo server riêng, domain/instance name riêng |
| Lỗi release server | Không thuộc registry factory, đã release hoặc ownership sai | Chỉ release server do component tạo và quản lý |
| `InstanceAlreadyExistsException` | Hai exporter dùng cùng `ObjectName` | Sửa naming strategy, owner và registration policy |
| Không thấy MBean dù exporter tồn tại | Exporter dùng server khác hoặc bean không nằm trong mapping | Kiểm tra server được inject và `setBeans` |
| Context không thể shutdown sạch | Connector chưa stop, task còn chạy hoặc cleanup không đúng thứ tự | Thiết kế lifecycle cho connector và dependencies |
| Nhiều server được tạo ngoài ý muốn | Factory mặc định tạo mới trong nhiều contexts | Dùng shared server có owner rõ hoặc bật tìm server phù hợp |

## 15. Nguyên tắc thiết kế vòng đời bền vững

1. **Xác định ownership ngay từ đầu.** Ai tạo server thì component đó cần chịu trách nhiệm release, trừ khi lifecycle được bàn giao tường minh.
2. **Phân biệt server mượn và server tạo mới.** Không giải phóng platform server của JVM khi chỉ đóng một Spring context.
3. **Inject server vào exporter.** Tránh exporter tự chọn server không giống server mà code kiểm tra hoặc connector đang dùng.
4. **Dùng một owner cho mỗi `ObjectName`.** Nhiều exporters cùng server được nhưng không nên đăng ký trùng tên.
5. **Tận dụng destroy callbacks của Spring.** Để exporter unregister trước khi owner giải phóng server.
6. **Quản lý connector riêng.** Remote connector có start/stop độc lập với registry.
7. **Không dùng static server reference tùy tiện.** Static reference có thể kéo dài vòng đời vượt quá Spring context và gây resource leak.
8. **Cô lập test.** Server và tên JMX riêng giúp tránh ảnh hưởng giữa test cases.
9. **Đối chiếu đúng JVM/server khi debug.** `isRegistered` trên platform server không thể chứng minh trạng thái custom server.
10. **Kiểm tra shutdown.** Sau khi đóng context, xác minh MBeans của exporter đã được unregister và owner server đã thực hiện cleanup đúng hợp đồng.

## 16. Bài tập thực hành

**Bài 1 — Server riêng.** Tạo một `MBeanServerFactoryBean` với domain `training.jmx`, đăng ký `JobMonitor` qua `MBeanExporter`. Dùng API server để xác minh `ObjectName` tồn tại, sau đó đóng context.

**Bài 2 — So sánh platform với custom.** Đăng ký một MBean chỉ ở custom server. Chạy `ManagementFactory.getPlatformMBeanServer().isRegistered(name)` và custom `server.isRegistered(name)`. Giải thích sự khác biệt.

**Bài 3 — Hai contexts.** Tạo một custom server ở root context, cho child context dùng cùng server nhưng với `ObjectName` khác. Đóng child trước root; xác minh chỉ MBeans do child exporter quản lý bị unregister.

**Bài 4 — Ownership sai.** Thiết kế một fixture cố ý release server trước khi exporter đóng. Quan sát hậu quả và sửa dependency graph để exporter destroy trước server owner.

**Bài 5 — Lifecycle remote connector.** Phác thảo một `JMXConnectorServer` quản lý bằng `SmartLifecycle`. Liệt kê các bước start, stop, xác thực và kiểm tra kết nối cần thực hiện trước khi dùng trong môi trường thật.

## Kết luận

Quản lý vòng đời `MBeanServer` tùy biến trong Spring Framework nghĩa là phân biệt rõ **ai tạo server, ai sử dụng nó, ai đăng ký MBean và ai chịu trách nhiệm dọn dẹp**. `MBeanServerFactoryBean` giúp đưa lifecycle của custom server vào `ApplicationContext`, trong khi `MBeanExporter` quản lý registration của những managed beans được xuất. Khi sử dụng server chung, nhiều contexts hoặc remote JMX connector, phải thiết kế ownership và thứ tự shutdown rõ ràng để tránh mất MBean, đăng ký trùng, resource leak hoặc công cụ quản trị đọc nhầm registry.
