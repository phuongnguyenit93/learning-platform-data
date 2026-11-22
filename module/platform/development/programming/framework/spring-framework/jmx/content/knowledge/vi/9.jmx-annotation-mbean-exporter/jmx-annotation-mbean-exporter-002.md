# @EnableMBeanExport để bật cấu hình Java

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** AnnotationMBeanExporter  
> **Bài học:** @EnableMBeanExport để bật cấu hình Java

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Giải thích vì sao một Spring bean có \`@ManagedResource\` chưa mặc nhiên xuất hiện trong JMX MBeanServer.
- Dùng \`@EnableMBeanExport\` trên lớp \`@Configuration\` để kích hoạt export MBean bằng Java configuration.
- Hiểu thành phần \`AnnotationMBeanExporter\` và vai trò của \`MBeanServer\`, \`ObjectName\`, assembler, naming strategy và registration policy.
- Phân biệt bật JMX export trong Spring Framework với cấu hình remote JMX connector và các thiết lập tự động của Spring Boot.
- Viết ví dụ có attribute, operation, kiểm tra được qua JConsole hoặc \`MBeanServerConnection\`.
- Xử lý tình huống bean không được export, trùng ObjectName, sai MBeanServer, hoặc annotation không được nhận diện.

## 2. Bức tranh tổng thể

Java Management Extensions (JMX) mô tả tài nguyên JVM qua **MBean**. Spring có thể xuất bản bean được quản lý trong \`ApplicationContext\` thành MBean nhờ \`MBeanExporter\`. Với cách sử dụng annotation, Spring cung cấp \`AnnotationMBeanExporter\` để nhận diện metadata như \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\`.

\`@EnableMBeanExport\` là cách khai báo ngắn gọn trong Java configuration để kích hoạt cơ chế này.

\`\`\`text
@Configuration
@EnableMBeanExport
      |
      v
Spring đăng ký infrastructure cho JMX export
      |
      v
AnnotationMBeanExporter
      |
      +--> Tìm Spring bean có @ManagedResource
      +--> Đọc @ManagedAttribute / @ManagedOperation
      +--> Xác định ObjectName, metadata và MBeanServer
      |
      v
MBeanServer (JMX registry của JVM)
      |
      +--> learning.jmx:type=CacheMonitor,name=main
      |
      +--> JConsole / JMX client
           đọc attributes, gọi operations, nhận notifications
\`\`\`

Điểm cần nhớ: \`@ManagedResource\` mô tả **bean nào có thể xuất bản**, còn \`@EnableMBeanExport\` cung cấp **hạ tầng để thực hiện xuất bản**. Nếu chưa có exporter thích hợp, Spring không tự đăng ký MBean chỉ vì một class có annotation.

Cơ chế trên thuộc **quản trị ứng dụng**, độc lập với luồng HTTP request/response. Sau khi export, Spring bean vẫn tồn tại trong container như trước; JMX chỉ tạo một bề mặt quan sát hoặc điều khiển bổ sung.

## 3. @EnableMBeanExport làm gì?

Annotation \`org.springframework.context.annotation.EnableMBeanExport\` được đặt trên lớp cấu hình:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Khi Spring xử lý cấu hình này, nó kích hoạt bộ đăng ký và xuất bản MBean theo annotation, tương ứng cơ chế \`AnnotationMBeanExporter\`.

Những trách nhiệm quan trọng:

1. **Tạo hạ tầng export:** bổ sung infrastructure bean cần thiết để phát hiện và đăng ký MBean.
2. **Phát hiện bean thích hợp:** xét những bean trong context có \`@ManagedResource\` hoặc cách nhận diện MBean được cấu hình.
3. **Đọc metadata:** xác định attribute, operation và notification tương ứng.
4. **Đặt ObjectName:** dùng tên khai báo hoặc naming strategy.
5. **Đăng ký:** đưa MBean vào MBeanServer phù hợp.
6. **Gắn với lifecycle:** quản lý registration của các MBean do exporter tạo khi application context khởi tạo và đóng.

Annotation này **không tự bật remote JMX** và **không xuất bản mọi public method của mọi bean** theo mặc định. Nó cũng không tự động định nghĩa authentication, TLS, firewall, hoặc quyền điều khiển operation từ client.

## 4. Các thành phần trong cơ chế export

| Thành phần | Vai trò |
|---|---|
| \`@EnableMBeanExport\` | Kích hoạt cơ chế export bằng Java configuration. |
| \`AnnotationMBeanExporter\` | Exporter dùng metadata annotation để phát hiện bean và tạo mô hình quản trị JMX. |
| \`@ManagedResource\` | Đánh dấu bean là tài nguyên quản trị và có thể chỉ định ObjectName/description. |
| \`@ManagedAttribute\` | Mô tả getter/setter được expose thành JMX attribute. |
| \`@ManagedOperation\` | Mô tả method được expose thành JMX operation. |
| \`@ManagedOperationParameters\` | Cung cấp metadata tên và mô tả tham số operation. |
| \`@ManagedNotification\` / \`@ManagedNotifications\` | Công bố metadata về những notification MBean có thể phát. |
| \`ObjectName\` | Định danh duy nhất trong MBeanServer, dạng \`domain:key=value\`. |
| \`MBeanServer\` | Đăng ký MBean và xử lý query, attribute access, invocation và notification. |
| \`JConsole\` / client JMX | Đọc và tương tác với MBean đã đăng ký. |

Một \`ObjectName\` minh họa:

\`\`\`text
learning.jmx:type=CacheMonitor,name=main
\`\`\`

Trong tên này, \`learning.jmx\` là domain; \`type\` và \`name\` là key properties. Hai MBean không thể đồng thời sử dụng cùng ObjectName trong một MBeanServer nếu không có chính sách xử lý registration conflict tương ứng.

## 5. Ví dụ tối thiểu: bật export trong Java configuration

Ví dụ sử dụng Spring Framework với một bean quản trị cache. Bean có attribute đọc số lần cache được làm mới và một operation reset counter.

### 5.1. Bean có metadata JMX

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=main",
    description = "Cache refresh monitoring"
)
public class CacheMonitor {

    private final AtomicLong refreshCount = new AtomicLong();

    public void cacheRefreshed() {
        refreshCount.incrementAndGet();
    }

    @ManagedAttribute(
        description = "Number of cache refresh operations"
    )
    public long getRefreshCount() {
        return refreshCount.get();
    }

    @ManagedOperation(
        description = "Reset refresh count"
    )
    public void resetCounter() {
        refreshCount.set(0);
    }
}
\`\`\`

Ý nghĩa:

- \`@Component\` yêu cầu Spring tạo \`CacheMonitor\` như một bean.
- \`@ManagedResource\` đánh dấu bean để cơ chế JMX annotation export nhận diện và gắn ObjectName cố định.
- \`@ManagedAttribute\` công bố \`RefreshCount\` là thuộc tính chỉ đọc.
- \`@ManagedOperation\` công bố \`resetCounter()\` là operation.
- \`cacheRefreshed()\` không có annotation quản trị nên không được đưa vào bề mặt quản trị annotation trong ví dụ này.

Spring giữ một bean thực trong ApplicationContext. Khi JMX client đọc \`RefreshCount\`, exporter/adapter chuyển đến getter trên bean đó, không tạo một bản sao trạng thái riêng cho JConsole.

### 5.2. Java configuration

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = CacheMonitor.class)
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

\`@ComponentScan\` bảo đảm \`CacheMonitor\` được Spring phát hiện. \`@EnableMBeanExport\` kích hoạt hạ tầng export JMX.

### 5.3. Khởi chạy Spring context

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxExample {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     JmxConfiguration.class
                 )) {

            CacheMonitor monitor =
                context.getBean(CacheMonitor.class);

            monitor.cacheRefreshed();
            monitor.cacheRefreshed();

            System.out.println(
                "Spring context started; JMX MBean exported"
            );
            System.out.println(
                "PID: " + ProcessHandle.current().pid()
            );

            // Giữ JVM để quan sát bằng JConsole.
            System.in.read();
        }
    }
}
\`\`\`

Sau khi chạy, context tạo bean, exporter đăng ký MBean rồi chương trình giữ JVM đang hoạt động để bạn kết nối JConsole. Khi thoát khỏi \`try-with-resources\`, context đóng và exporter dọn các MBean thuộc lifecycle quản lý của nó.

Ví dụ dùng các thư viện Spring phù hợp với phiên bản ứng dụng. Trong dự án Maven/Gradle thực tế, cần có các dependency Spring Context và phần JMX tương ứng; JMX API chuẩn \`javax.management\` được cung cấp bởi JDK.

## 6. Đọc và gọi MBean bằng JMX API

Nếu exporter sử dụng platform MBeanServer, có thể xác thực bằng code chạy trong cùng JVM:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "learning.jmx:type=CacheMonitor,name=main"
);

System.out.println(
    "Registered: " + server.isRegistered(name)
);

Object count = server.getAttribute(
    name,
    "RefreshCount"
);
System.out.println("RefreshCount: " + count);

server.invoke(
    name,
    "resetCounter",
    new Object[0],
    new String[0]
);

System.out.println(
    "After reset: "
        + server.getAttribute(name, "RefreshCount")
);
\`\`\`

Kết quả khi đã gọi \`cacheRefreshed()\` hai lần:

\`\`\`text
Registered: true
RefreshCount: 2
After reset: 0
\`\`\`

**Giả định then chốt:** \`ManagementFactory.getPlatformMBeanServer()\` phải chính là server nơi Spring exporter đăng ký MBean. Nếu exporter được cấu hình với một server khác, việc tìm bằng platform server có thể trả về \`false\` dù MBean đã export thành công.

### Luồng gọi từ JMX client

\`\`\`text
JConsole / Java JMX Client
   |
   | getAttribute("RefreshCount")
   v
MBeanServer (ObjectName exact)
   |
   v
Spring ModelMBean / JMX adapter
   |
   v
CacheMonitor.getRefreshCount()
   |
   v
AtomicLong.get() -> 2
\`\`\`

Với \`resetCounter()\`, client gọi \`MBeanServer.invoke\`; adapter định tuyến tới method của Spring bean và cập nhật trạng thái.

## 7. Cấu hình MBeanServer bằng @EnableMBeanExport

Trong ứng dụng phức tạp, có thể có nhiều MBeanServer hoặc Spring exporter cần một server cụ thể. \`@EnableMBeanExport\` có thuộc tính \`server\` để chỉ định **tên bean** đại diện cho MBeanServer.

Ví dụ:

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;
import java.lang.management.ManagementFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "jmxServer")
public class JmxServerConfiguration {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Trong ví dụ, \`server = "jmxServer"\` là **bean name**, không phải URL, hostname hay ObjectName. Spring lấy bean MBeanServer có tên này làm nơi đăng ký.

Khi không chỉ định rõ, cơ chế export sẽ xác định MBeanServer theo quy tắc của Spring Framework và môi trường. Đừng giả định mọi cấu hình JVM đều có cùng một MBeanServer; hãy kiểm tra server thực tế khi cần truy cập từ công cụ.

Một số cấu hình có thể sử dụng \`MBeanServerFactoryBean\` để tạo hoặc định vị MBeanServer. Nếu tạo một MBeanServer riêng, JConsole attach đến platform server có thể không nhìn thấy MBean đó. Để quản trị qua JConsole, hãy chọn registry phù hợp với cách công cụ sẽ kết nối.

## 8. NamingStrategy và ObjectName

\`@ManagedResource(objectName = "...")\` cho phép khai báo tên trực tiếp:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=main"
)
\`\`\`

Nếu không cố định ObjectName, Spring cần cơ chế đặt tên thích hợp, thường thông qua \`ObjectNamingStrategy\` hoặc strategy tích hợp với exporter. Với các hệ thống nhiều instance, nên có quy ước:

\`\`\`text
learning.jmx:type=WorkerPool,name=primary,node=one
learning.jmx:type=WorkerPool,name=primary,node=two
\`\`\`

Nhưng không đưa dữ liệu tùy ý chưa escape vào \`ObjectName\`, nhất là dấu phẩy, dấu bằng, dấu hai chấm và ký tự wildcard. Dùng \`ObjectName.quote(value)\` hoặc phương pháp xây \`ObjectName\` phù hợp khi key property chứa dữ liệu đặc biệt.

Hai MBean có cùng tên trong cùng server có thể gặp lỗi \`InstanceAlreadyExistsException\` (hoặc lỗi export được bao bọc bởi Spring), trừ khi cấu hình chính sách xử lý registration rõ ràng. Không dựa vào tên class hay Spring bean name làm bằng chứng chắc chắn của ObjectName thực tế: hãy đọc metadata hoặc dùng \`queryNames\` từ đúng MBeanServer.

## 9. Annotation cho attributes và operations

### 9.1. Attribute chỉ đọc

\`\`\`java
@ManagedAttribute(description = "Current queue size")
public int getQueueSize() {
    return queue.size();
}
\`\`\`

Theo cách đặt tên JavaBeans, getter \`getQueueSize()\` expose attribute \`QueueSize\`.

### 9.2. Attribute có setter

\`\`\`java
private volatile int maxRetries = 3;

@ManagedAttribute
public int getMaxRetries() {
    return maxRetries;
}

@ManagedAttribute
public void setMaxRetries(int maxRetries) {
    if (maxRetries < 0) {
        throw new IllegalArgumentException(
            "maxRetries must be non-negative"
        );
    }
    this.maxRetries = maxRetries;
}
\`\`\`

Getter và setter được đánh dấu thích hợp giúp client đọc/ghi thuộc tính, nếu exporter/assembler công bố chúng. Giá trị đầu vào cần kiểm tra, vì công cụ quản trị có thể thay đổi trạng thái ứng dụng.

### 9.3. Operation có tham số

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Resize worker pool")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "workers",
        description = "New worker count"
    )
})
public void resizeWorkers(int workers) {
    if (workers <= 0) {
        throw new IllegalArgumentException(
            "workers must be positive"
        );
    }
    // Cập nhật worker pool thật.
}
\`\`\`

Client gọi qua:

\`\`\`java
server.invoke(
    name,
    "resizeWorkers",
    new Object[] { 8 },
    new String[] { "int" }
);
\`\`\`

\`@ManagedOperationParameters\` bổ sung tên và mô tả tham số, nhưng không thay đổi kiểu Java hay chữ ký dùng trong JMX invocation. \`params\` chứa giá trị, \`signature\` chứa tên kiểu khai báo như \`int\`, \`long\`, \`java.lang.String\`.

## 10. Notification với @EnableMBeanExport

Spring bean cũng có thể phát JMX notification khi cơ chế exporter hỗ trợ. Một cách là implement \`NotificationPublisherAware\` để nhận \`NotificationPublisher\` từ Spring.

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

public class JobService
        implements NotificationPublisherAware {

    private NotificationPublisher publisher;
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher
    ) {
        this.publisher = publisher;
    }

    public void jobCompleted(String jobId) {
        Notification notification = new Notification(
            "app.job.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job completed: " + jobId
        );

        publisher.sendNotification(notification);
    }
}
\`\`\`

Đoạn trên là phần logic minh họa. Để dùng thực tế, cần khai báo \`JobService\` làm Spring bean, gắn \`@ManagedResource\`, bật exporter và cấu hình metadata notification thích hợp. Publisher thường chỉ sẵn sàng sau khi bean được exporter xử lý; tránh gọi phương thức phát notification quá sớm trong lifecycle.

Để công cụ hiển thị loại notification được công bố, Spring cung cấp metadata annotation \`@ManagedNotification\` và \`@ManagedNotifications\`, hoặc assembler tương ứng. Khai báo metadata không tự phát sự kiện: code vẫn phải gọi \`publisher.sendNotification\` hoặc broadcaster.

## 11. Phân biệt Spring Framework thuần và Spring Boot

Với **Spring Framework thuần**, \`@EnableMBeanExport\` là cách Java configuration để bật annotation-driven JMX export.

Với **Spring Boot**, có thêm auto-configuration và các property liên quan tới JMX. Tùy phiên bản và cấu hình, Spring Boot có thể tự tạo exporter khi JMX được bật, đồng thời đưa Actuator MBeans vào domain riêng. Ví dụ một số phiên bản Boot dùng property:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Hãy kiểm tra tài liệu đúng phiên bản Spring Boot đang chạy và những exporter đã được khởi tạo. Không nên vừa bật auto-configuration export vừa thêm \`@EnableMBeanExport\` mà không kiểm tra khả năng tạo nhiều exporter hoặc đăng ký trùng ObjectName.

**JMX export khác remote JMX:** \`spring.jmx.enabled\` hoặc \`@EnableMBeanExport\` chỉ liên quan việc xuất bản MBean trong server. Remote connector/agent, xác thực, TLS và endpoint là lớp cấu hình riêng.

### Khi nào chọn @EnableMBeanExport?

Chọn khi:

- Ứng dụng dùng Java-based Spring configuration.
- Muốn các \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` trở thành tài nguyên quản trị.
- Cần giảm cấu hình exporter thủ công cho nhiều bean.
- Cần kiểm soát MBeanServer được sử dụng qua cấu hình Java.

Nếu cần chỉ định từng bean, naming strategy đặc biệt, assembler cụ thể hoặc listener phức tạp, cấu hình \`MBeanExporter\` tường minh cũng có thể phù hợp. Tránh kích hoạt hai exporter cùng đăng ký một MBean nếu không có chủ đích.

## 12. Đọc metadata để xác nhận export

\`MBeanInfo\` là nguồn kiểm tra thực tế về bề mặt JMX được đăng ký. Ví dụ:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        "Operation: " + operation.getName()
    );
}
\`\`\`

Nếu bean được export với metadata như ví dụ \`CacheMonitor\`, kỳ vọng thấy attribute \`RefreshCount\` và operation \`resetCounter\`. Đây là bằng chứng mạnh hơn việc chỉ quan sát annotation tồn tại trong source code.

Có thể dùng JConsole:

1. Chạy ứng dụng và ghi PID.
2. Mở \`jconsole\` từ JDK.
3. Chọn đúng local Java process.
4. Mở tab **MBeans**.
5. Tìm domain \`learning.jmx\`.
6. Chọn \`type=CacheMonitor,name=main\`.
7. Quan sát **Attributes** và **Operations**.
8. Đọc \`RefreshCount\`, gọi \`resetCounter\`, rồi đọc lại attribute.

JConsole có thể không attach được do quyền người dùng, container hoặc cấu hình JVM. Lúc đó kiểm tra qua \`MBeanServerConnection\` hoặc thiết lập connector thích hợp.

## 13. Sự cố thường gặp

### 13.1. Có @ManagedResource nhưng JConsole không thấy bean

Kiểm tra:

1. \`@EnableMBeanExport\` đã nằm trên lớp \`@Configuration\` được ApplicationContext xử lý chưa?
2. Lớp có \`@Component\` và nằm trong vùng component scan, hoặc có \`@Bean\` tương ứng chưa?
3. Bean có \`@ManagedResource\` và ObjectName hợp lệ chưa?
4. Context đã khởi tạo hoàn tất, exporter đã chạy chưa?
5. JConsole kết nối đúng JVM và MBeanServer chưa?
6. Có lỗi registration trong log startup không?

Nếu chưa có Spring bean trong context, JMX exporter không thể tự tạo bean chỉ nhờ annotation quản trị.

### 13.2. MBean có nhưng không thấy một method

\`@ManagedResource\` không mặc nhiên expose tất cả method nghiệp vụ. Kiểm tra \`@ManagedOperation\`, \`@ManagedAttribute\`, quy tắc JavaBeans và metadata assembler đang áp dụng. Dùng \`MBeanInfo\` để xem method nào thật sự đã được công bố.

### 13.3. Lỗi trùng ObjectName

Nếu có nhiều bean được export dưới cùng:

\`\`\`text
learning.jmx:type=CacheMonitor,name=main
\`\`\`

MBeanServer không thể chứa hai MBean cùng tên theo cùng cách thông thường. Hãy sửa chiến lược đặt tên, bảo đảm duy nhất hoặc cấu hình registration policy thích hợp nếu có chủ đích xử lý MBean đang tồn tại. Không unregister MBean khác một cách tùy tiện.

### 13.4. Không tìm thấy MBeanServer

Nếu dùng \`@EnableMBeanExport(server = "jmxServer")\`, xác nhận bean có đúng tên, đúng kiểu \`javax.management.MBeanServer\` và khởi tạo được. Cấu hình sai có thể khiến exporter không đăng ký được.

### 13.5. Spring Boot gặp lỗi đăng ký trùng

Kiểm tra các exporter do auto-configuration cung cấp và exporter bạn cấu hình thủ công. MBean với ObjectName giống nhau có thể bị đăng ký hai lần. Chọn một cơ chế export thống nhất cho bean đó hoặc cấu hình domain/naming policy rõ ràng.

### 13.6. Attribute xuất hiện nhưng không cập nhật

Xác nhận trạng thái bean có thay đổi thực tế và getter đọc đúng nguồn. JConsole có thể cần refresh/polling để thấy giá trị mới. Việc một field thay đổi không tự động tạo JMX notification nếu không có publisher/broadcaster phát event.

### 13.7. Remote JMX không kết nối được

Đây thường là vấn đề connector, địa chỉ RMI, port, authentication, TLS hoặc firewall. \`@EnableMBeanExport\` không phải công tắc bật remote JMX. Đừng giải quyết bằng cách mở cổng quản trị công khai lên Internet.

## 14. Thiết kế bề mặt quản trị an toàn

Một MBean operation có thể làm thay đổi tài nguyên đang chạy. Nên áp dụng các nguyên tắc:

- Chỉ export những bean và method có mục đích vận hành rõ ràng.
- Giữ attribute quan sát quan trọng ở chế độ read-only nếu không cần chỉnh sửa.
- Kiểm tra tham số ở mỗi operation như với một API quản trị.
- Tránh expose dữ liệu nhạy cảm qua attribute, notification \`userData\` hay mô tả lỗi.
- Khi có remote connector, cấu hình authentication, authorization, encryption và network restriction.
- Ghi log cho thao tác có tác dụng phụ, đồng thời không ghi credentials hoặc secret.
- Giữ ObjectName có cấu trúc, ổn định, tránh đặt tên trùng giữa instance.
- Cân nhắc idempotency và timeout cho operation có thể được gọi lặp.

MBean hữu ích cho quản trị JVM, nhưng không tự thay thế hệ thống metrics, audit trail hay business API. Với số liệu dài hạn, có thể tích hợp hệ metrics riêng; JMX phù hợp để kiểm tra và điều khiển trực tiếp.

## 15. Bài tập thực hành

### Bài 1: Thêm attribute

Thêm vào \`CacheMonitor\`:

\`\`\`java
private volatile boolean enabled = true;

@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
\`\`\`

Khởi động lại application context, mở JConsole và kiểm tra attribute \`Enabled\` có thể đọc/ghi theo metadata. Đọc lại giá trị sau khi thay đổi, xác nhận state trên cùng Spring bean.

### Bài 2: Thay ObjectName

Đổi:

\`\`\`text
learning.jmx:type=CacheMonitor,name=main
\`\`\`

thành:

\`\`\`text
learning.jmx:type=CacheMonitor,name=secondary
\`\`\`

Sau khi context khởi động lại, truy vấn ObjectName mới và kiểm tra tên cũ không còn đại diện cho MBean do context này quản lý. Không sửa ObjectName khi ứng dụng production có client đang phụ thuộc tên cũ mà chưa phối hợp thay đổi.

### Bài 3: Tắt export

Tạm bỏ \`@EnableMBeanExport\` trong ứng dụng Spring Framework thuần không có exporter khác. Bean \`CacheMonitor\` vẫn là Spring bean do \`@ComponentScan\` tạo, nhưng MBean không còn được annotation exporter đăng ký.

Điều này làm rõ hai vòng đời khác nhau:

\`\`\`text
@Component -> Spring bean tồn tại trong context

@EnableMBeanExport + @ManagedResource
    -> bean có thêm giao diện quản trị trong MBeanServer
\`\`\`

### Bài 4: Kiểm tra bằng JMX client

Viết code:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=CacheMonitor,name=main"
);

if (server.isRegistered(name)) {
    System.out.println(
        server.getAttribute(name, "RefreshCount")
    );
}
\`\`\`

Sau đó giải thích vì sao \`isRegistered\` không bảo đảm một \`getAttribute\` tiếp theo luôn thành công nếu MBean có thể bị unregister ở giữa hai lời gọi.

## 16. Câu hỏi tự kiểm tra

1. Vì sao \`@ManagedResource\` chưa đủ để MBean xuất hiện nếu thiếu exporter?
2. \`@EnableMBeanExport\` kích hoạt thành phần nào?
3. \`AnnotationMBeanExporter\` khác gì với một \`MBeanServer\`?
4. Vì sao \`ObjectName\` phải duy nhất trong một MBeanServer?
5. Có phải mọi public method của bean đều được expose khi bật export không?
6. Vì sao client local có thể không thấy MBean nếu exporter dùng một MBeanServer riêng?
7. \`@EnableMBeanExport(server = "jmxServer")\` nhận tên bean hay endpoint URL?
8. \`@ManagedAttribute\` và \`@ManagedOperation\` dùng cho hai mục đích nào?
9. Vì sao bật export không đồng nghĩa bật remote JMX?
10. Khi Spring Boot có exporter auto-configured, cần lưu ý gì nếu thêm \`@EnableMBeanExport\`?

Để trả lời, hãy lần lượt phân biệt Spring bean, annotation metadata, exporter, ObjectName, MBeanServer và client kết nối. Đây là những trách nhiệm độc lập tạo thành một luồng quản trị hoàn chỉnh.

## 17. Ghi nhớ

\`\`\`text
@Configuration + @EnableMBeanExport
     |
     v
AnnotationMBeanExporter
     |
     v
Spring beans có @ManagedResource
     |
     +-- @ManagedAttribute -> JMX attribute
     |
     +-- @ManagedOperation -> JMX operation
     |
     +-- @ManagedNotification -> notification metadata
     |
     v
ObjectName + MBeanServer
     |
     v
JConsole / JMX client
\`\`\`

**Quy tắc quan trọng:** \`@EnableMBeanExport\` kích hoạt **quá trình export MBean từ Spring**, còn \`@ManagedResource\` và các annotation quản trị mô tả **những gì client được phép nhìn thấy và thao tác**. Kết nối remote, quyền truy cập, tính duy nhất của ObjectName và cách quản lý lifecycle vẫn cần được cấu hình và kiểm tra riêng.