# Quy ước tên Interface và MBean cho Standard MBean

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích **Standard MBean** là gì và vì sao JMX nhận diện giao diện quản trị thông qua quy ước tên.
- Đặt tên đúng cho interface và lớp triển khai, kể cả khi lớp có hậu tố như \`Service\`, \`Manager\` hoặc \`Impl\`.
- Hiểu chính xác phương thức nào trở thành attribute hoặc operation được JMX công bố.
- Đăng ký và truy vấn Standard MBean trong \`MBeanServer\`.
- Phân biệt cách dùng trực tiếp quy ước Standard MBean với \`StandardMBean\` wrapper và cơ chế xuất bản MBean trong Spring Framework.
- Xử lý các lỗi thường gặp như \`NotCompliantMBeanException\`, đặt sai tên interface và nhầm giữa tên Java class với \`ObjectName\`.

## 1. Standard MBean là gì?

Java Management Extensions (JMX) cho phép ứng dụng Java công bố thông tin quản trị ở thời gian chạy. Các thông tin này được đăng ký vào một \`MBeanServer\` dưới dạng **Managed Bean (MBean)**, từ đó công cụ như JConsole hoặc JMX client có thể đọc thuộc tính hay gọi thao tác quản trị.

JMX có nhiều kiểu MBean; **Standard MBean** là kiểu dựa trên **Java interface có quy ước đặt tên cụ thể**. Lớp triển khai chứa logic; interface quản trị xác định phần nào của lớp được công bố cho JMX.

Ví dụ về quan hệ:

\`\`\`text
CacheManager                  // Lớp triển khai
    implements
CacheManagerMBean             // Giao diện quản trị của Standard MBean
        |
        v
MBeanServer.registerMBean(...)
        |
        v
JMX client thấy attributes / operations được công bố
\`\`\`

Điểm cốt lõi:

> Với cách triển khai Standard MBean theo quy ước tên mặc định, interface quản trị có tên **TênLớpTriểnKhai + MBean**.

Ví dụ lớp \`CacheManager\` phải có interface quản trị \`CacheManagerMBean\`. Interface này là **hợp đồng quản trị JMX**, không nhất thiết là mọi interface nghiệp vụ mà lớp đang triển khai.

## 2. Quy tắc tên: lớp triển khai và interface MBean

Giả sử tên đơn giản (simple class name) của lớp triển khai là \`DeviceMonitor\`. Interface quản trị theo convention phải có tên:

\`\`\`java
public interface DeviceMonitorMBean {
    // Những member cần JMX công bố
}
\`\`\`

Lớp triển khai:

\`\`\`java
public class DeviceMonitor implements DeviceMonitorMBean {
    // Logic hiện thực interface
}
\`\`\`

Hậu tố \`MBean\` được gắn vào **tên lớp triển khai** \`DeviceMonitor\`, không gắn vào tên biến hay ObjectName.

### Các ví dụ đặt tên

| Lớp triển khai | Interface Standard MBean tương ứng | Đúng convention? |
|---|---|---|
| \`CacheManager\` | \`CacheManagerMBean\` | Có |
| \`TaskQueue\` | \`TaskQueueMBean\` | Có |
| \`TaskQueueImpl\` | \`TaskQueueImplMBean\` | Có |
| \`OrderService\` | \`OrderServiceMBean\` | Có |
| \`DatabasePoolMonitor\` | \`DatabasePoolMonitorMBean\` | Có |
| \`TaskQueueImpl\` | \`TaskQueueMBean\` | Không, nếu dùng **mặc định quy ước tên** trực tiếp |
| \`TaskQueue\` | \`TaskQueueMXBean\` | Không phải tên Standard MBean mặc định; gắn với quy ước MXBean |

Một lớp có thể triển khai nhiều interface Java, nhưng để JMX tìm đúng **Standard MBean interface** bằng convention, interface quản trị phải phù hợp tên lớp triển khai và được khai báo theo quan hệ interface thích hợp.

### Phân biệt simple name và tên package

Ví dụ:

\`\`\`text
com.example.monitoring.DeviceMonitor
com.example.monitoring.DeviceMonitorMBean
\`\`\`

Trong trường hợp thông thường, interface quản trị nằm trong package phù hợp để được JMX nhận diện qua kiểu Java. Tên cuối cùng \`DeviceMonitorMBean\` là phần tuân theo convention. Điều cần nhớ là không thể tùy ý dùng \`IManagedDevice\` rồi mong Standard MBean được nhận diện chỉ vì interface chứa các phương thức \`getStatus()\` và \`restart()\`.

**Lưu ý:** Không cần đặt tên Java class của MBean bằng domain/key property của \`ObjectName\`. Đây là hai cơ chế định danh khác nhau.

## 3. Ví dụ Java hoàn chỉnh: Standard MBean

Ta muốn quản lý một hàng đợi xử lý công việc trong ứng dụng: đọc trạng thái \`Paused\`, số lượng công việc đã hoàn tất \`CompletedJobs\`, và gọi thao tác \`pause()\`/\`resume()\`.

### 3.1. Tạo interface quản trị đúng convention

Tệp \`TaskQueueMBean.java\`:

\`\`\`java
package com.example.jmx;

public interface TaskQueueMBean {
    boolean isPaused();

    long getCompletedJobs();

    void pause();

    void resume();
}
\`\`\`

Tên là \`TaskQueueMBean\` vì lớp triển khai ở phần sau là \`TaskQueue\`.

Điều quan trọng: interface này là **phần bề mặt công khai qua JMX**. Nó không cần bao gồm mọi hàm sử dụng nội bộ trong ứng dụng.

### 3.2. Viết lớp triển khai

Tệp \`TaskQueue.java\`:

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class TaskQueue implements TaskQueueMBean {
    private volatile boolean paused;
    private final AtomicLong completedJobs = new AtomicLong();

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public long getCompletedJobs() {
        return completedJobs.get();
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }

    // Chỉ phục vụ logic ứng dụng, không nằm trong TaskQueueMBean.
    public void onJobCompleted() {
        completedJobs.incrementAndGet();
    }
}
\`\`\`

Những thành phần JMX nhận được:

- Attribute \`Paused\` qua getter \`isPaused()\`.
- Attribute \`CompletedJobs\` qua getter \`getCompletedJobs()\`.
- Operation \`pause()\`.
- Operation \`resume()\`.

Phương thức \`onJobCompleted()\` dù \`public\` nhưng **không thuộc \`TaskQueueMBean\`**, nên không được công bố như operation của Standard MBean này.

### 3.3. Đăng ký MBean với MBeanServer

Tệp \`App.java\`:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class App {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        TaskQueue queue = new TaskQueue();

        ObjectName name = new ObjectName(
                "com.example.jmx:type=TaskQueue,name=Primary"
        );

        server.registerMBean(queue, name);

        System.out.println("Registered: " + server.isRegistered(name));
        System.out.println("PID: " + ProcessHandle.current().pid());

        // Giữ JVM chạy để có thể thử với JConsole.
        System.out.println("Press Enter to exit.");
        System.in.read();

        server.unregisterMBean(name);
    }
}
\`\`\`

Kết quả mong đợi khi đăng ký:

\`\`\`text
Registered: true
PID: <một-số-PID>
Press Enter to exit.
\`\`\`

Từ JConsole, kết nối vào đúng JVM, tìm tab MBeans rồi xem domain \`com.example.jmx\` và entry có \`type=TaskQueue,name=Primary\`. Các attribute và operation được công bố từ interface \`TaskQueueMBean\`.

Để chạy ví dụ, tổ chức ba tệp cùng package \`com.example.jmx\`; dự án Java hiện đại có thể chạy bằng IDE hoặc build tooling của ứng dụng. Vì JConsole cần kết nối trong khi JVM còn hoạt động, ví dụ giữ process chạy đến khi nhận input.

## 4. Hậu tố MBean khác gì tên ObjectName?

Một trong những nhầm lẫn phổ biến nhất là xem \`TaskQueueMBean\` và \`ObjectName\` như cùng một loại tên.

Chúng có chức năng khác nhau:

| Thành phần | Ví dụ | Mục đích |
|---|---|---|
| Lớp Java | \`TaskQueue\` | Thực thi logic/trạng thái |
| Interface quản trị | \`TaskQueueMBean\` | Quy định attributes và operations theo convention |
| ObjectName | \`com.example.jmx:type=TaskQueue,name=Primary\` | Định danh **instance MBean** bên trong MBeanServer |
| Domain | \`com.example.jmx\` | Nhóm ObjectName |
| Key property | \`name=Primary\` | Phân biệt instance cùng domain |

Bạn có thể đăng ký một object \`TaskQueue\` thành:

\`\`\`java
new ObjectName("operations:type=Queue,name=BackOffice")
\`\`\`

hoặc:

\`\`\`java
new ObjectName("monitoring:type=WorkerPool,id=7")
\`\`\`

Cả hai đều có thể hợp lệ nếu không trùng ObjectName đang đăng ký. **Thay đổi ObjectName không làm thay đổi quy ước tên interface Standard MBean**.

Ngược lại, có interface đúng convention chưa bảo đảm \`registerMBean\` thành công nếu ObjectName không hợp lệ, đã trùng hoặc object không tuân thủ các yêu cầu khác của MBean.

## 5. Cách JMX ánh xạ phương thức của interface

Standard MBean interface công bố **attributes** và **operations** theo quy tắc JavaBeans/JMX.

### 5.1. Attribute chỉ đọc

\`\`\`java
public interface CacheStatsMBean {
    int getEntryCount();
}
\`\`\`

JMX công bố attribute \`EntryCount\` có thể đọc.

### 5.2. Attribute có thể đọc và ghi

\`\`\`java
public interface WorkerSettingsMBean {
    int getMaxWorkers();
    void setMaxWorkers(int value);
}
\`\`\`

JMX công bố attribute \`MaxWorkers\` có thể đọc/ghi. Một setter công khai trong interface MBean làm thay đổi cấu hình từ công cụ JMX; cần kiểm tra giới hạn hợp lệ trong implementation.

### 5.3. Boolean attribute

\`\`\`java
public interface SchedulerStatusMBean {
    boolean isPaused();
}
\`\`\`

Getter \`isPaused()\` công bố attribute boolean \`Paused\`.

### 5.4. Operation

\`\`\`java
public interface CacheControlMBean {
    void clearCache();
}
\`\`\`

\`clearCache()\` được công bố như operation. Khác với việc đọc attribute, operation có thể làm thay đổi trạng thái ứng dụng.

### 5.5. Không mọi phương thức đều thành attribute

Phương thức:

\`\`\`java
int calculateTotal();
\`\`\`

không tuân theo mẫu getter \`getX()\` hoặc \`isX()\`, nên thường được công bố là **operation**, nếu có trong MBean interface.

Phương thức không khai báo trong interface sẽ không được xuất qua Standard MBean, dù lớp triển khai có chứa nó. Đây là lý do nên giữ interface quản trị nhỏ, ổn định và được kiểm soát.

## 6. Sai tên interface dẫn đến lỗi gì?

Giả sử bạn viết:

\`\`\`java
public interface QueueAdmin {
    int getDepth();
}

public class TaskQueue implements QueueAdmin {
    @Override
    public int getDepth() {
        return 0;
    }
}
\`\`\`

Sau đó:

\`\`\`java
server.registerMBean(
    new TaskQueue(),
    new ObjectName("example:type=Queue")
);
\`\`\`

Với đăng ký Standard MBean trực tiếp theo convention, \`QueueAdmin\` không phải \`TaskQueueMBean\`; JMX không tự biết \`QueueAdmin\` là management interface mong muốn. Đăng ký có thể thất bại với:

\`\`\`text
javax.management.NotCompliantMBeanException
\`\`\`

Lỗi này cho biết object không thỏa những quy tắc MBean mà MBeanServer đang kiểm tra. Không phải mọi \`NotCompliantMBeanException\` đều do sai tên: còn có thể do visibility, hợp đồng interface, kiểu dữ liệu không hợp lệ hoặc cách công bố không phù hợp.

### Cách sửa theo convention

\`\`\`java
public interface TaskQueueMBean {
    int getDepth();
}

public class TaskQueue implements TaskQueueMBean {
    @Override
    public int getDepth() {
        return 0;
    }
}
\`\`\`

Khi đó interface đúng \`TaskQueueMBean\` so với lớp \`TaskQueue\`.

### Cách sửa nếu muốn giữ tên interface khác

JMX cung cấp \`StandardMBean\` wrapper để chỉ định interface quản trị rõ ràng thay vì dựa hoàn toàn vào hậu tố của lớp triển khai.

\`\`\`java
import javax.management.StandardMBean;

public interface QueueAdmin {
    int getDepth();
}

public class QueueService implements QueueAdmin {
    @Override
    public int getDepth() {
        return 5;
    }
}

// Trong code đăng ký:
QueueService service = new QueueService();

StandardMBean wrapper =
        new StandardMBean(service, QueueAdmin.class);

server.registerMBean(
        wrapper,
        new ObjectName("example:type=Queue,name=Main")
);
\`\`\`

Ở đây \`StandardMBean\` biết management interface là \`QueueAdmin.class\` vì được chỉ định tường minh. Interface không cần phải tên \`QueueServiceMBean\` nữa.

**Vì sao cách này hữu ích?**

- Giữ được tên interface nghiệp vụ/quản trị đã tồn tại.
- Dễ dùng trong môi trường nhiều lớp wrapper/proxy.
- Có thể xác định rõ contract khi class name không phù hợp convention.
- Giảm nhu cầu đổi tên các lớp đã là một phần của hệ thống lớn.

Đừng hiểu nhầm rằng Standard MBean *luôn luôn* buộc interface kết thúc bằng \`MBean\`; quy tắc hậu tố là **convention mặc định khi JMX tự nhận diện management interface**. Wrapper là cách khai báo tường minh.

## 7. Trường hợp có hậu tố Impl, Service, Manager

Trong dự án Spring, tên lớp thường gặp là \`OrderServiceImpl\`, \`CacheManager\`, \`JobSchedulerService\`.

Với đăng ký trực tiếp kiểu Standard MBean dựa trên convention:

\`\`\`text
OrderServiceImpl         -> OrderServiceImplMBean
CacheManager             -> CacheManagerMBean
JobSchedulerService      -> JobSchedulerServiceMBean
\`\`\`

Ví dụ hay mắc lỗi:

\`\`\`java
public interface OrderServiceMBean {
    int getPendingCount();
}

public class OrderServiceImpl implements OrderServiceMBean {
    @Override
    public int getPendingCount() {
        return 10;
    }
}
\`\`\`

Nếu \`registerMBean(new OrderServiceImpl(), name)\` dựa vào tên lớp triển khai, interface \`OrderServiceMBean\` không khớp với simple name \`OrderServiceImpl\`; bạn không nên mặc định đăng ký sẽ thành công chỉ vì lớp implements interface kết thúc bằng \`MBean\`.

Các phương án thiết kế:

1. Đổi tên interface thành \`OrderServiceImplMBean\` nếu muốn giữ \`OrderServiceImpl\` và dùng convention.
2. Đổi tên lớp triển khai thành \`OrderService\` nếu thiết kế cho phép.
3. Sử dụng \`StandardMBean\` và cung cấp \`OrderServiceMBean.class\` tường minh.
4. Dùng cơ chế JMX exporter/metadata assembler của Spring để kiểm soát contract, thay vì buộc cấu trúc service nghiệp vụ phải đi theo convention.

Trong nhiều ứng dụng, phương án 3 hoặc 4 giúp tách biệt giao diện quản trị khỏi cách đặt tên lớp nghiệp vụ.

## 8. Khi nào cần interface public?

Đối với ví dụ đơn giản và các lớp được công cụ/framework bên ngoài sử dụng, khai báo MBean interface là \`public\` là lựa chọn an toàn và rõ ràng:

\`\`\`java
public interface CacheMonitorMBean { ... }
public class CacheMonitor implements CacheMonitorMBean { ... }
\`\`\`

Đặt interface thành một type top-level truy cập được sẽ giúp MBeanServer có thể phân tích interface và dễ tích hợp với công cụ JMX.

Hãy tránh các vấn đề như:

- Interface private/nested không có visibility phù hợp.
- Class triển khai hoặc public method có visibility bất thường.
- Interface MBean có member dùng kiểu không dễ biểu diễn qua JMX client.
- Interface khai báo rất nhiều setter/operation nhạy cảm mà người vận hành không cần.

Với MBean cần tương tác từ xa, các kiểu dữ liệu quản trị cũng phải được chọn cẩn thận. JMX hỗ trợ các kiểu Java theo quy tắc của MBean, nhưng không nên cho rằng mọi object đồ thị Java bất kỳ đều được client phía xa hiểu dễ dàng. MXBean có cơ chế ánh xạ sang các kiểu dữ liệu chuẩn hóa, phù hợp hơn cho một số nhu cầu tương thích cross-JVM.

## 9. Phân biệt Standard MBean và MXBean

Tên interface thường gây nhầm:

\`\`\`java
public interface CacheManagerMBean { ... }
\`\`\`

và:

\`\`\`java
public interface CacheManagerMXBean { ... }
\`\`\`

- **Standard MBean:** thường nhận diện interface theo hậu tố \`MBean\`, công bố thuộc tính và thao tác theo interface Java, có thể dùng \`StandardMBean\` để cấu hình tường minh.
- **MXBean:** thường nhận diện theo hậu tố \`MXBean\` hoặc annotation \`@MXBean\`; dùng cơ chế mapping dữ liệu quản trị sang Open Types để hỗ trợ client dễ trao đổi dữ liệu qua ranh giới JVM.

Đừng đặt \`MXBean\` vào tên rồi giải thích mọi hành vi như Standard MBean thông thường. Cả hai đều sống trong JMX nhưng khác cơ chế công bố thông tin và cách ánh xạ kiểu dữ liệu.

Ví dụ:

\`\`\`java
public interface WorkerPoolMXBean {
    int getActiveWorkers();
}
\`\`\`

Tên này gợi ý MXBean; khi triển khai thực tế, cần chọn rõ Standard MBean hay MXBean theo yêu cầu contract.

## 10. Standard MBean và Spring Framework

Trong Java thuần, bạn có thể dùng:

\`\`\`java
server.registerMBean(bean, objectName);
\`\`\`

Trong **Spring Framework**, \`MBeanExporter\` và các chiến lược assembler giúp xuất bản bean được quản lý bởi Spring. Spring hỗ trợ nhiều cách xác định thuộc tính/thao tác JMX:

- Theo convention Standard MBean.
- Theo giao diện quản trị hoặc chiến lược assembler được cấu hình.
- Theo annotation \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` khi cấu hình annotation-based metadata exporter phù hợp.

Ví dụ sử dụng trực tiếp một bean tuân theo Standard MBean convention:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfig {

    @Bean
    public TaskQueue taskQueue() {
        return new TaskQueue();
    }

    @Bean
    public MBeanExporter mBeanExporter(TaskQueue queue) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(
                ManagementFactory.getPlatformMBeanServer()
        );

        exporter.setBeans(Map.of(
            "com.example.jmx:type=TaskQueue,name=Primary",
            queue
        ));

        return exporter;
    }
}
\`\`\`

Ở đây:

1. Spring tạo \`TaskQueue\`.
2. \`MBeanExporter\` đăng ký bean trong platform MBeanServer được chỉ định.
3. Contract quản trị do \`TaskQueueMBean\` quy định nếu bean được xuất theo Standard MBean convention.
4. ObjectName chỉ là định danh registration, không thay thế interface.

Spring cũng có thể xuất bean bằng metadata assembler không dựa vào hậu tố \`MBean\`. Vì vậy khi gặp mã Spring không có \`SomeClassMBean\` nhưng vẫn được công bố trên JConsole, hãy kiểm tra **cấu hình exporter/assembler** trước khi kết luận nó không hợp lệ.

### Lưu ý với Spring Boot

Spring Boot có tính năng Actuator và hỗ trợ expose các endpoint qua JMX, nhưng không nên đánh đồng:

- **Một Standard MBean do bạn tự viết**, với contract nằm trong \`*MBean\` interface.
- **MBean do Spring JMX exporter tạo** từ một Spring bean.
- **Actuator endpoint xuất qua JMX** khi các điều kiện dependency và cấu hình được đáp ứng.

Đây là các đường triển khai có thể khác nhau. Các thuộc tính cấu hình của Spring Boot cũng phụ thuộc phiên bản, vì thế cần kiểm tra reference documentation tương ứng dự án.

## 11. Kiểm tra metadata của MBean đã đăng ký

Khi cần xác minh contract thật sự, không chỉ kiểm tra Java class name. Dùng \`MBeanServer.getMBeanInfo(...)\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectMBean {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jmx:type=TaskQueue,name=Primary"
        );

        if (!server.isRegistered(name)) {
            System.out.println("MBean is not registered");
            return;
        }

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.println("Attribute: "
                    + attribute.getName());
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.println("Operation: "
                    + operation.getName());
        }
    }
}
\`\`\`

Lưu ý ví dụ này phải chạy **trong JVM đang giữ đăng ký đó**, hoặc được điều chỉnh để dùng \`MBeanServerConnection\` từ JMX connector vào JVM đích. Nếu chạy như một Java process độc lập thông thường, \`ManagementFactory.getPlatformMBeanServer()\` trả về server **của process mới**, nên nó sẽ không tìm thấy MBean của process trước đó.

\`getMBeanInfo()\` là một cách tốt để xác nhận attribute/operation nào thực sự được công bố, nhất là khi có Spring exporter hoặc wrapper làm thay đổi cách khai báo.

## 12. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/hướng xử lý |
|---|---|---|
| \`NotCompliantMBeanException\` | Không có interface \`<ClassName>MBean\` theo convention hoặc không khai báo wrapper | Đối chiếu simple class name, interface, visibility; dùng \`StandardMBean\` nếu muốn tên interface khác |
| Lớp có \`*MBean\` interface nhưng không được nhận diện | Tên interface khớp với lớp khác, chẳng hạn \`OrderServiceMBean\` so với \`OrderServiceImpl\` | Đổi tên hoặc xác định contract tường minh |
| MBean đã đăng ký nhưng JConsole không thấy | Sai JVM, server, ObjectName hoặc lỗi kết nối | Kiểm tra \`isRegistered\`, \`queryNames\`, PID/connector |
| \`InstanceAlreadyExistsException\` | Hai đăng ký trùng ObjectName trong một MBeanServer | Chọn ObjectName riêng hoặc xử lý chính sách re-registration |
| Attribute không hiện | Getter không nằm trong interface hoặc không theo quy tắc getter | Kiểm tra interface MBean và \`getMBeanInfo\` |
| Operation nội bộ bị lộ | Đã đưa nhầm method vào MBean interface hoặc assembler export quá rộng | Thu hẹp contract quản trị |
| Gọi operation bị lỗi kiểu dữ liệu | Signature/parameters không khớp contract được công bố | Đọc \`MBeanInfo\`, kiểm tra signature và kiểu |
| Bean Spring không có \`*MBean\` nhưng vẫn hiện | Spring exporter/assembler dùng metadata hoặc strategy khác | Kiểm tra \`MBeanExporter\`, annotations và strategy |
| Một process khác không thấy MBean | MBean thuộc server của JVM khác | Dùng JMX connector vào đúng JVM, không đọc server local của process mới |

### Lộ trình debug nhanh

Khi đăng ký Standard MBean thất bại:

1. In tên class thực tế: \`bean.getClass().getName()\`.
2. Xác định interface quản trị thực tế: \`bean.getClass().getInterfaces()\` hoặc xem hệ kế thừa.
3. Kiểm tra convention \`<TênLớp>MBean\` hoặc có dùng \`StandardMBean\` wrapper hay không.
4. Kiểm tra interface \`public\`, các method và kiểu dữ liệu.
5. Kiểm tra \`ObjectName\` hợp lệ, chưa bị trùng.
6. Nếu dùng Spring, kiểm tra exporter và assembler đã chọn.
7. Sau khi register, dùng \`getMBeanInfo()\` xác nhận contract được công bố.

Đừng sửa tên \`ObjectName\` chỉ vì \`NotCompliantMBeanException\`: trừ khi log cho thấy ObjectName sai cú pháp hoặc trùng, nguyên nhân có thể nằm ở quản trị type/interface.

## 13. Bài tập thực hành

### Bài tập A — Dự đoán tên

Cho ba lớp:

\`\`\`text
PaymentScheduler
PaymentSchedulerImpl
DiskCacheManager
\`\`\`

Hãy viết tên interface Standard MBean mặc định tương ứng.

**Đáp án:** \`PaymentSchedulerMBean\`, \`PaymentSchedulerImplMBean\`, \`DiskCacheManagerMBean\`.

### Bài tập B — Sửa một đăng ký sai

Cho code:

\`\`\`java
public interface WorkerPoolAdmin {
    int getActiveCount();
}

public class WorkerPoolService implements WorkerPoolAdmin {
    @Override
    public int getActiveCount() {
        return 3;
    }
}
\`\`\`

Một developer gọi:

\`\`\`java
server.registerMBean(
    new WorkerPoolService(),
    new ObjectName("training:type=WorkerPool")
);
\`\`\`

Hãy sửa theo hai hướng:

- **Convention:** Đổi interface thành \`WorkerPoolServiceMBean\`, cập nhật \`implements\` và giữ \`registerMBean\` trực tiếp.
- **Explicit wrapper:** Giữ \`WorkerPoolAdmin\` và dùng \`new StandardMBean(service, WorkerPoolAdmin.class)\` khi đăng ký.

Thảo luận: Trong dự án có nhiều class \`*Impl\` và đang muốn giữ API ổn định, phương án wrapper hoặc Spring exporter có lợi gì?

### Bài tập C — Thử đọc attribute

Sau khi đăng ký \`TaskQueue\`, đọc attribute:

\`\`\`java
Object paused = server.getAttribute(
    new ObjectName("com.example.jmx:type=TaskQueue,name=Primary"),
    "Paused"
);
System.out.println(paused);
\`\`\`

Hãy giải thích vì sao thuộc tính tên \`Paused\` mà Java method là \`isPaused()\`. Sau đó bỏ \`isPaused()\` khỏi \`TaskQueueMBean\` và kiểm tra metadata JMX thay đổi thế nào.

### Bài tập D — Chọn bề mặt quản trị

Một lớp dịch vụ có:

\`\`\`java
public void processPayment(Payment payment);
public void reloadNonSensitiveConfig();
public int getQueuedCount();
\`\`\`

Bạn sẽ đưa method nào vào MBean interface? Vì sao?

**Gợi ý:** \`getQueuedCount()\` có thể phù hợp attribute \`QueuedCount\`, \`reloadNonSensitiveConfig()\` có thể là operation nếu được phân quyền. Không đưa luồng nghiệp vụ \`processPayment(...)\` vào bề mặt JMX chỉ vì nó là public method. Quyền truy cập và rủi ro tác dụng phụ phải được phân tích riêng.

## 14. Các điểm cần ghi nhớ

1. **Standard MBean theo convention:** Lớp \`Foo\` ↔ interface quản trị \`FooMBean\`.
2. Hậu tố \`MBean\` áp dụng cho **tên interface Java**; \`ObjectName\` là định danh instance riêng biệt.
3. **Chỉ các method trong management interface** mới được JMX công bố theo Standard MBean contract.
4. Getter/setter theo convention ánh xạ thành attribute; các method còn lại thường thành operation.
5. \`FooImpl\` mặc định ghép với \`FooImplMBean\`, không tự suy luận \`FooMBean\`.
6. **StandardMBean wrapper** cho phép chọn management interface tường minh ngay cả khi tên không tuân theo hậu tố.
7. **Spring Framework** có thể dùng \`MBeanExporter\`, assembler và annotations để quản lý MBean theo cách linh hoạt hơn convention trực tiếp.
8. Khi có lỗi, kiểm tra **class + interface + registration + metadata** trước khi suy đoán từ JConsole.
9. Hãy giữ MBean interface nhỏ, ổn định, có quyền và chỉ công bố dữ liệu/thao tác quản trị thực sự cần.

## Tài liệu tham khảo

- Oracle Java SE 21 — \`StandardMBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html
- Oracle Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Oracle Java SE 21 — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Oracle Java Management Extensions overview: https://docs.oracle.com/javase/8/docs/technotes/guides/jmx/
