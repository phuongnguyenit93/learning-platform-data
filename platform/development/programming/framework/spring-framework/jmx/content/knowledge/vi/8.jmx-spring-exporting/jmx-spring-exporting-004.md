# Đăng ký exporter như một bean trong ApplicationContext

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của \`MBeanExporter\` khi Spring Framework đưa các Spring bean ra JMX.
- Đăng ký \`MBeanExporter\` như một bean trong \`ApplicationContext\` bằng Java configuration hoặc XML.
- Hiểu quan hệ giữa \`ApplicationContext\`, \`MBeanExporter\`, \`MBeanServer\`, \`ObjectName\` và các managed bean.
- Kiểm soát tên đăng ký, xử lý trùng tên, vòng đời đăng ký/hủy đăng ký và thứ tự khởi tạo phù hợp.
- Phân biệt exporter được khai báo tường minh với annotation-driven exporting và các cơ chế JMX tự cấu hình trong Spring Boot.
- Kiểm tra kết quả bằng \`MBeanServer\`, JConsole hoặc client JMX khác.

## 1. Exporting trong Spring Framework là gì?

JMX (Java Management Extensions) cho phép theo dõi và quản trị các đối tượng Java đang chạy bằng MBean. Một MBean được đăng ký trong \`MBeanServer\` và có tên nhận diện \`ObjectName\`.

Spring Framework cung cấp \`org.springframework.jmx.export.MBeanExporter\` để chuyển việc đăng ký MBean thành một phần của quá trình quản lý bean trong IoC container. Ta khai báo exporter là **một Spring bean** trong \`ApplicationContext\`, cấu hình các bean cần xuất và tên JMX tương ứng. Khi context khởi tạo exporter, nó đăng ký các đối tượng được quản lý vào \`MBeanServer\`. Khi context đóng một cách bình thường, exporter có khả năng hủy đăng ký các MBean mà nó quản lý theo vòng đời của mình.

Điều quan trọng: **Spring bean** và **JMX MBean** không đồng nghĩa. Có một object trong \`ApplicationContext\` chưa chắc object đó được công bố qua JMX. \`MBeanExporter\` là cầu nối giúp xác định rõ đối tượng nào được đưa ra registry quản trị.

Luồng tổng quát:

\`\`\`text
Spring ApplicationContext
   |
   +-- jobMonitor  -----------------------------+
   |                                           |
   +-- mbeanServer                              |
   |                                           |
   +-- mBeanExporter                            |
           |                                    |
           | khai báo ObjectName -> bean -------+
           v
       MBeanServer
           |
           +-- com.example.monitoring:type=JobMonitor,name=primary
                    |
                    +-- Attributes: ProcessedCount, Enabled
                    +-- Operations: reset()
           |
           v
       JConsole / JMX client
\`\`\`

\`MBeanExporter\` hoạt động ở phía ứng dụng, còn JConsole là client kết nối tới registry. Không cần triển khai REST controller để JMX client gọi các operation này.

## 2. Chuẩn bị Standard MBean làm đối tượng được xuất

Để minh họa rõ sự khác nhau giữa hợp đồng quản lý và bean Spring, sử dụng Standard MBean với giao diện \`JobMonitorMBean\`.

**JobMonitorMBean.java**

\`\`\`java
package com.example.monitoring;

public interface JobMonitorMBean {
    int getProcessedCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void reset();
}
\`\`\`

**JobMonitor.java**

\`\`\`java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger processed = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordJob() {
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
\`\`\`

Quy ước Standard MBean sử dụng interface tên \`ClassNameMBean\`; vì vậy \`JobMonitor\` implement \`JobMonitorMBean\`. Các method trong interface là hợp đồng JMX:

| Method Java | Phần tử JMX | Ý nghĩa |
| --- | --- | --- |
| \`getProcessedCount()\` | Attribute \`ProcessedCount\`, read-only | Đọc số tác vụ |
| \`isEnabled()\` và \`setEnabled(boolean)\` | Attribute \`Enabled\`, readable/writable | Điều khiển cờ ghi nhận |
| \`reset()\` | Operation \`reset\` | Đặt bộ đếm về 0 |
| \`recordJob()\` chỉ có ở implementation | Không công bố qua Standard MBean | Ghi nhận tác vụ nội bộ |

Không cần có \`@ManagedResource\` trên lớp này. Đây là Standard MBean theo quy ước JMX Java thuần; Spring chỉ thực hiện phần đăng ký.

## 3. Cách đăng ký MBeanExporter bằng Java configuration

Một cách minh bạch là khai báo \`@Configuration\` gồm ba bean:

1. Managed object \`JobMonitor\`.
2. \`MBeanServer\` mà exporter sẽ sử dụng.
3. \`MBeanExporter\` chứa mapping từ \`ObjectName\` đến object.

\`\`\`java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MonitoringJmxConfiguration {

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            JobMonitor jobMonitor,
            MBeanServer mBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
                "com.example.monitoring:type=JobMonitor,name=primary",
                jobMonitor
        ));
        return exporter;
    }
}
\`\`\`

Cấu hình này dùng Java configuration Spring Framework và không phụ thuộc lớp auto-configuration của Spring Boot.

### Ý nghĩa của từng phần

**\`@Configuration\`** cho Spring biết class chứa các khai báo bean.

**\`@Bean jobMonitor()\`** tạo \`JobMonitor\` trong \`ApplicationContext\`, vì vậy các thành phần nghiệp vụ khác có thể inject chính instance này. Khi ứng dụng gọi \`recordJob()\`, trạng thái của instance sẽ thay đổi và dữ liệu mới có thể được JMX client đọc.

**\`@Bean mBeanServer()\`** cung cấp platform \`MBeanServer\` của JVM bằng API \`ManagementFactory.getPlatformMBeanServer()\`. Đây là server thuận tiện để kết nối bằng JConsole đến cùng tiến trình. Nếu ứng dụng đã có một \`MBeanServer\` bean phù hợp, có thể inject nó và không cần tạo thêm bean khác cùng kiểu.

**\`@Bean mBeanExporter(...)\`** tạo \`MBeanExporter\`, chỉ định server bằng \`setServer\` và chọn danh sách bean xuất bằng \`setBeans\`. Tên trong map là \`ObjectName\` JMX, còn value là object được quản lý.

**\`Map.of(...)\`** minh họa mapping một managed bean. \`MBeanExporter.setBeans\` nhận một \`Map<String, Object>\`; mỗi khóa là JMX name, mỗi giá trị là Spring-managed object hoặc tham chiếu bean thích hợp theo cơ chế được exporter hỗ trợ.

Khi context khởi tạo xong, \`MBeanExporter\` sẽ đăng ký MBean theo chu kỳ \`afterPropertiesSet()\`/các lifecycle callback của chính nó. Bạn không cần gọi \`registerMBean\` thủ công trong một \`@PostConstruct\` nếu đã dùng exporter.

## 4. Chạy ApplicationContext và kiểm tra đăng ký

Ví dụ Spring Framework thuần sử dụng \`AnnotationConfigApplicationContext\`:

\`\`\`java
package com.example.monitoring;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class SpringJmxDemo {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                MonitoringJmxConfiguration.class)) {

            JobMonitor monitor = context.getBean(JobMonitor.class);
            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                    "com.example.monitoring:type=JobMonitor,name=primary");

            System.out.println("Registered: " + server.isRegistered(name));

            monitor.recordJob();
            monitor.recordJob();

            System.out.println(
                    "ProcessedCount: "
                    + server.getAttribute(name, "ProcessedCount"));

            System.out.println(
                    "PID: " + ProcessHandle.current().pid());

            // Giữ ví dụ chạy để có thể mở JConsole; nhấn Enter để đóng.
            System.in.read();
        }
    }
}
\`\`\`

Với cấu hình và môi trường bình thường, \`isRegistered(name)\` trả \`true\`, còn \`ProcessedCount\` bằng 2 sau hai lần \`recordJob()\`.

Nếu ứng dụng đóng context trước khi JConsole kết nối, MBean có thể đã được gỡ đăng ký. Vì vậy, \`System.in.read()\` ở ví dụ nhằm giữ context tồn tại trong lúc quan sát; trong ứng dụng Spring server thật, vòng đời được quản lý bởi runtime.

Trong quá trình thử nghiệm, mở JConsole, chọn đúng PID, chuyển tới tab **MBeans** rồi tìm domain \`com.example.monitoring\` và \`type=JobMonitor,name=primary\`. Bạn sẽ thấy các attributes và operation được interface quản lý công bố.

## 5. Đăng ký exporter bằng XML configuration

Với dự án Spring Framework sử dụng XML, bạn cũng có thể khai báo \`MBeanExporter\` bằng bean definition:

\`\`\`xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="jobMonitor"
          class="com.example.monitoring.JobMonitor"/>

    <bean id="mbeanServer"
          class="org.springframework.jmx.support.MBeanServerFactoryBean">
        <property name="locateExistingServerIfPossible" value="true"/>
    </bean>

    <bean id="mBeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">
        <property name="server" ref="mbeanServer"/>
        <property name="beans">
            <map>
                <entry key="com.example.monitoring:type=JobMonitor,name=primary"
                       value-ref="jobMonitor"/>
            </map>
        </property>
    </bean>
</beans>
\`\`\`

\`MBeanServerFactoryBean\` là một cơ chế hỗ trợ chọn hoặc tạo \`MBeanServer\` trong Spring. Cấu hình \`locateExistingServerIfPossible=true\` có thể sử dụng server đã tồn tại; với môi trường có nhiều JMX server, vẫn cần xác minh chính xác server nào đang được chọn. Nếu mục tiêu là chắc chắn dùng platform MBeanServer, Java configuration ở mục trước với \`ManagementFactory.getPlatformMBeanServer()\` diễn đạt mục đích trực tiếp hơn.

Dù dùng XML hay \`@Bean\`, nguyên tắc vẫn giống nhau: Spring container quản lý exporter, exporter quản lý quá trình đăng ký các đối tượng được chọn vào MBean server.

## 6. Tại sao phải khai báo MBeanExporter là một bean?

Khi tự viết code như:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setBeans(...);
\`\`\`

nhưng **không** đăng ký object exporter với Spring, các callback vòng đời IoC không tự diễn ra. Bạn phải tự đảm bảo việc khởi tạo, đưa server vào, đăng ký và dọn dẹp. Đó không phải cách sử dụng thông thường trong Spring.

Khi được khai báo là một Spring bean, exporter nhận được các callback vòng đời container: được cấu hình dependency, khởi tạo đúng thời điểm và có cơ hội quản lý việc unregister khi bean bị destroy. Đây là lý do nên đặt exporter trong \`ApplicationContext\`, thay vì tạo object độc lập rồi giả định rằng Spring sẽ tự nhìn thấy nó.

Tương tự, khai báo managed bean trong context giúp JMX thao tác trên **chính instance ứng dụng đang sử dụng**. Nếu vô tình tạo \`new JobMonitor()\` bên trong exporter thay vì inject \`jobMonitor\` hiện hữu, JMX sẽ quản lý một instance khác với instance đang xử lý nghiệp vụ.

### Ví dụ lỗi phổ biến

\`\`\`java
@Bean
public MBeanExporter wrongExporter(MBeanServer server) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(
            "com.example.monitoring:type=JobMonitor,name=primary",
            new JobMonitor() // Có thể là instance khác với bean nghiệp vụ.
    ));
    return exporter;
}
\`\`\`

Mã vẫn có thể đăng ký một MBean hợp lệ, nhưng người vận hành có thể thấy \`ProcessedCount=0\` mãi vì object JMX không phải object được business service inject. Truyền managed bean làm tham số \`@Bean\` giúp tránh lỗi này.

## 7. ObjectName, bean name và chiến lược naming

Tên Spring bean và tên JMX phục vụ hai phạm vi khác nhau.

| Khái niệm | Ví dụ | Phạm vi |
| --- | --- | --- |
| Spring bean name | \`jobMonitor\` | Tra cứu trong \`ApplicationContext\` |
| Java interface | \`JobMonitorMBean\` | Hợp đồng Standard MBean |
| JMX ObjectName | \`com.example.monitoring:type=JobMonitor,name=primary\` | Định danh MBean trong \`MBeanServer\` |

Khi dùng \`setBeans\` với key \`ObjectName\` cụ thể, bạn kiểm soát tên JMX rõ ràng. \`ObjectName\` có cấu trúc \`domain:key=value,key=value\`; trong cùng một server, hai MBean không thể cùng có một \`ObjectName\`.

Spring cung cấp các cách tự động quyết định tên JMX qua naming strategy, nhưng khi mới học exporter, map tường minh giúp dễ kiểm tra và tránh hiểu nhầm tên Spring bean có thể tự động là tên JMX.

Nếu ứng dụng có nhiều instance được xuất, đặt key rõ ràng như:

\`\`\`text
com.example.monitoring:type=JobMonitor,name=primary
com.example.monitoring:type=JobMonitor,name=secondary
\`\`\`

Các tên này có thể cùng loại nhưng phải phân biệt đầy đủ trong registry. Nếu tên chứa ký tự đặc biệt, hãy dùng cú pháp \`ObjectName\` hợp lệ thay vì nối chuỗi không được escape.

## 8. Xử lý đăng ký trùng và vòng đời

\`MBeanExporter\` cho phép cấu hình **registration behavior** khi gặp MBean đã đăng ký trước đó. Các chế độ phổ biến được khai báo bằng các hằng như:

- \`REGISTRATION_FAIL_ON_EXISTING\`: thất bại khi tên đã tồn tại (thường là mặc định).
- \`REGISTRATION_IGNORE_EXISTING\`: giữ MBean đang tồn tại, không thay thế bằng instance mới.
- \`REGISTRATION_REPLACE_EXISTING\`: cho phép thay thế đối tượng đã đăng ký dưới cùng tên.

Có thể cấu hình theo hằng của \`MBeanRegistrationSupport\`, ví dụ:

\`\`\`java
import org.springframework.jmx.support.MBeanRegistrationSupport;

exporter.setRegistrationBehavior(
        MBeanRegistrationSupport.REGISTRATION_FAIL_ON_EXISTING);
\`\`\`

Đây là quyết định về hành vi đăng ký, không phải một cách sửa mọi xung đột. Nếu dùng \`REPLACE_EXISTING\` mà không hiểu owner hiện tại, bạn có thể thay thế MBean của module khác. Trong ứng dụng lớn, nên có chiến lược \`ObjectName\` nhất quán và một thành phần chịu trách nhiệm mỗi đăng ký.

Một exporter được quản lý bởi Spring có thể unregister MBean do chính nó đăng ký khi context đóng. Với nhiều context hoặc exporter chia sẻ một \`MBeanServer\`, cần tránh việc từng exporter tự coi MBean của exporter khác là của mình. Khi dùng nhiều Spring contexts, hãy xác định rõ tên và phạm vi ownership.

## 9. Thứ tự khởi tạo và các dependency

\`MBeanExporter\` cần object được xuất và một MBean server phù hợp. Khi \`@Bean\` nhận \`JobMonitor\` và \`MBeanServer\` qua tham số, Spring đảm bảo các dependency đó được tạo trước khi factory method tạo exporter.

Tuy nhiên, **đăng ký sớm không đồng nghĩa mọi thành phần nghiệp vụ đã hoàn tất khởi tạo**. Nếu MBean được client gọi khi hệ thống chưa ready, các operation có thể gây lỗi hoặc tác dụng phụ ngoài dự kiến. Với ứng dụng cần giai đoạn warm-up dài, cân nhắc:

- Chỉ xuất các attribute an toàn trong giai đoạn chưa ready.
- Đặt điều kiện trạng thái \`Ready\` hoặc \`MaintenanceAllowed\` trước các operation ghi.
- Thiết kế operation để từ chối rõ ràng khi lifecycle chưa phù hợp.
- Không dùng MBean như một lối tắt vượt qua kiểm tra sẵn sàng nghiệp vụ.

Spring hỗ trợ \`@DependsOn\`, \`SmartLifecycle\`, các event lifecycle và nhiều cơ chế điều phối khác; dùng khi thật sự cần đảm bảo thứ tự, tránh thêm phụ thuộc không cần thiết chỉ để “cho chắc”.

## 10. Đăng ký exporter theo annotation có gì khác?

Ngoài mô hình Standard MBean, Spring còn có annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(objectName =
        "com.example.monitoring:type=Counter,name=annotation")
public class CounterAdmin {
    private int count;

    @ManagedAttribute
    public int getCount() {
        return count;
    }

    @ManagedOperation
    public void reset() {
        count = 0;
    }
}
\`\`\`

Để Spring đọc các annotation đó, cần exporter có cấu hình annotation-aware, ví dụ \`AnnotationMBeanExporter\`, \`@EnableMBeanExport\` hoặc cấu hình tương đương theo phiên bản Spring.

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class AnnotationJmxConfiguration {
}
\`\`\`

\`@EnableMBeanExport\` kích hoạt support xuất MBean theo annotation trong Spring Framework. Nếu cần cấu hình nâng cao (server, naming, autodection policy), phải xem cơ chế exporter cụ thể mà ứng dụng đang dùng.

**Khác biệt cốt lõi:**

- \`MBeanExporter\` với \`setBeans\`: bạn chọn rõ những object và JMX name cần xuất.
- Annotation-based export: bạn đánh dấu object/method bằng metadata Spring, sau đó exporter tương ứng khám phá và đăng ký.

Không nên đồng thời đăng ký cùng một đối tượng dưới \`ObjectName\` giống nhau bằng cả hai cơ chế.

## 11. Liên hệ với Spring Boot và auto-configuration

Bài này nói về **Spring Framework**; trong ứng dụng Spring Boot, JMX có thể được hỗ trợ bởi auto-configuration và các thuộc tính cấu hình như \`spring.jmx.enabled\`. Trạng thái bật/tắt mặc định và các bean exporter được tạo cần kiểm tra theo phiên bản Boot và cấu hình ứng dụng thực tế.

Khi dự án Boot đã cấu hình JMX exporter, việc tự thêm \`@Bean MBeanExporter\` có thể dẫn đến:

- Hai exporter cùng cố đăng ký một \`ObjectName\`.
- Khác nhau về \`MBeanServer\` được chọn.
- MBean được đăng ký dưới naming strategy khác kỳ vọng.
- Khác biệt về vòng đời và xử lý trùng.

Đối với Boot, hãy quyết định sử dụng cơ chế auto-export hoặc cấu hình thủ công dựa trên yêu cầu ứng dụng, tránh chồng hai cơ chế mà không có phạm vi rõ ràng.

## 12. Kiểm tra kết quả bằng JMX API

Khi \`ApplicationContext\` đã sẵn sàng, có thể xác minh trực tiếp:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = context.getBean(MBeanServer.class);
ObjectName name = new ObjectName(
        "com.example.monitoring:type=JobMonitor,name=primary");

boolean registered = server.isRegistered(name);
System.out.println("Registered = " + registered);

if (registered) {
    MBeanInfo info = server.getMBeanInfo(name);

    for (var attribute : info.getAttributes()) {
        System.out.println(
                "Attribute: " + attribute.getName()
                + " / type: " + attribute.getType());
    }

    for (var operation : info.getOperations()) {
        System.out.println("Operation: " + operation.getName());
    }

    System.out.println(
            "ProcessedCount = "
            + server.getAttribute(name, "ProcessedCount"));
}
\`\`\`

Mã ví dụ giả định có sẵn biến \`context\` thuộc kiểu \`ApplicationContext\` phù hợp và quyền truy cập MBean server. Với \`MBeanInfo\`, bạn xác minh chính xác hợp đồng mà server đang công bố; \`isRegistered(name)\` chỉ kiểm tra sự tồn tại của tên.

Sau khi context đóng, có thể đọc lại \`server.isRegistered(name)\` nếu vẫn giữ tham chiếu đến server; kết quả phụ thuộc vòng đời exporter và ownership. Nếu một exporter khác sử dụng cùng tên hoặc replacement policy khác, không nên suy luận về cleanup chỉ từ một lần quan sát.

## 13. Kiểm tra bằng JConsole

Khi chương trình Spring đang chạy:

1. Mở \`jconsole\` từ JDK có hỗ trợ công cụ này.
2. Chọn đúng JVM bằng PID được ứng dụng in ra.
3. Vào tab **MBeans**.
4. Mở domain \`com.example.monitoring\`.
5. Tìm \`type=JobMonitor,name=primary\`, xem các attributes \`ProcessedCount\` và \`Enabled\`.
6. Thử đặt \`Enabled=false\`, gọi logic \`recordJob()\` của ứng dụng và xác minh số đếm không tăng.
7. Gọi operation \`reset()\` trong môi trường thử nghiệm, rồi đọc \`ProcessedCount\` về 0.
8. Đóng context, kiểm tra MBean còn xuất hiện hay không. Có thể cần refresh JConsole.

Nếu ứng dụng chạy trong container hoặc runtime tối giản, JConsole có thể không có hoặc không kết nối trực tiếp. Trong trường hợp đó, dùng client JMX phù hợp hoặc kiểm tra từ trong cùng JVM bằng \`MBeanServer\`.

## 14. Các lỗi phổ biến

### Exporter không được Spring quản lý

**Biểu hiện:** đã \`new MBeanExporter()\` nhưng MBean không xuất hiện.

**Nguyên nhân:** exporter không được khai báo thành bean và callback lifecycle không chạy.

**Cách xử lý:** dùng \`@Bean\`, XML \`<bean>\` hoặc cấu hình exporter phù hợp. Đảm bảo context thực sự scan/import configuration.

### Bean được xuất không phải bean nghiệp vụ

**Biểu hiện:** JConsole đọc được MBean nhưng số liệu không phản ánh ứng dụng.

**Nguyên nhân:** exporter dùng instance mới tạo thay vì instance mà nghiệp vụ đang dùng.

**Cách xử lý:** inject Spring bean đang tồn tại vào factory method \`mBeanExporter\`.

### Sai MBeanServer

**Biểu hiện:** \`isRegistered\` trả false trong một server, nhưng exporter thông báo đã đăng ký.

**Nguyên nhân:** ứng dụng có nhiều \`MBeanServer\` hoặc client đang quan sát server khác.

**Cách xử lý:** đảm bảo exporter và code kiểm tra dùng cùng server, đối chiếu JVM/PID và kết nối JMX.

### Trùng ObjectName

**Biểu hiện:** \`InstanceAlreadyExistsException\`, lỗi startup exporter hoặc MBean không được thay mới.

**Nguyên nhân:** hai thành phần dùng cùng JMX name.

**Cách xử lý:** định nghĩa naming convention và owner của đăng ký. Chỉ dùng \`IGNORE_EXISTING\` hoặc \`REPLACE_EXISTING\` khi đã hiểu hệ quả.

### NotCompliantMBeanException

**Biểu hiện:** lỗi khi exporter đăng ký bean Standard MBean.

**Nguyên nhân:** lớp hoặc interface chưa tuân thủ hợp đồng MBean, tên interface sai, kiểu/phương thức không hợp lệ.

**Cách xử lý:** kiểm tra \`JobMonitor implements JobMonitorMBean\`, interface public, tên phương thức và kiểu công bố.

### Không có MBean trong JConsole

**Biểu hiện:** context chạy nhưng tab MBeans thiếu tên mong đợi.

**Nguyên nhân:** configuration không được nạp, exporter không hoạt động, sai \`ObjectName\`, kết nối sai JVM, hoặc context đã đóng.

**Cách xử lý:** xác minh \`context.containsBean("mBeanExporter")\`, \`server.isRegistered(name)\`, log registration và PID kết nối.

## 15. Bài tập thực hành

**Bài 1 — Xuất hai MBean.** Tạo \`JobMonitor\` và \`CacheMonitor\` là hai Spring beans, mỗi lớp có interface \`*MBean\` tương ứng. Đăng ký cả hai bằng một \`MBeanExporter\` qua \`Map.of\` và hai \`ObjectName\` khác nhau. Kiểm tra với JConsole.

**Bài 2 — Chứng minh cùng instance.** Inject \`JobMonitor\` vào một Spring service, gọi \`recordJob()\` từ service, rồi đọc \`ProcessedCount\` qua \`MBeanServer\`. Giải thích vì sao exporter cần nhận cùng bean từ container.

**Bài 3 — Xung đột tên.** Đăng ký một MBean thủ công dưới \`ObjectName\` dự kiến, sau đó khởi tạo exporter có cùng tên trong môi trường thử nghiệm. Quan sát hành vi theo policy mặc định, rồi đọc tài liệu các chế độ \`REGISTRATION_IGNORE_EXISTING\` và \`REGISTRATION_REPLACE_EXISTING\` trước khi thử.

**Bài 4 — Vòng đời context.** Gọi \`isRegistered(name)\` sau khi context khởi tạo, đóng context, rồi gọi lại trên server vẫn đang tồn tại. Giải thích vai trò của exporter trong việc unregister.

**Bài 5 — Annotation.** So sánh một bean Standard MBean khai báo tường minh bằng \`setBeans\` với một bean \`@ManagedResource\` được đăng ký bằng \`@EnableMBeanExport\`. Xác định cách mỗi mô hình chọn tên, metadata và những method được xuất.

## Kết luận

Đăng ký \`MBeanExporter\` như một bean của \`ApplicationContext\` giúp Spring kiểm soát quá trình đưa các bean được chọn ra JMX registry cùng với vòng đời của container. Cấu hình cốt lõi gồm **managed bean**, **MBeanServer**, **MBeanExporter** và mapping **ObjectName → bean**. Nhờ đó, JConsole và các JMX client có thể đọc thuộc tính hoặc gọi operation trên chính instance đang chạy trong ứng dụng Spring. Cần kiểm tra trùng tên, đúng server và sự khác biệt giữa cấu hình tường minh với annotation hoặc Spring Boot auto-configuration.
