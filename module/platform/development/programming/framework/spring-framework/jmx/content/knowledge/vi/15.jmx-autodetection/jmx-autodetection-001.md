# Autodetect MBean đã triển khai giao diện JMX trong Spring Framework

## 1. Autodetection giải quyết bài toán gì?

Trong một ứng dụng Java, JMX (Java Management Extensions) cho phép đưa các đối tượng quản trị vào `MBeanServer` để các công cụ như JConsole, Java Mission Control hoặc một JMX client có thể đọc thuộc tính và gọi các operation. Cách thuần Java thường đăng ký từng MBean:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName("demo.orders:type=OrderMonitor");
server.registerMBean(new OrderMonitor(), name);
```

Khi ứng dụng dùng Spring, các đối tượng đã được quản lý bởi `ApplicationContext`. Nếu có nhiều MBean, viết code đăng ký riêng cho từng object vừa lặp lại cấu hình vừa làm lifecycle phức tạp. **Autodetection** của `MBeanExporter` cho phép Spring tìm những bean phù hợp, tự export chúng thành JMX MBean, thay vì yêu cầu liệt kê tất cả bằng `setBeans(...)`.

Tuy nhiên, từ “tự động phát hiện” phải được hiểu chính xác: Spring không có nghĩa vụ phơi bày **mọi** bean trong container. Các MBean đã tuân thủ giao diện JMX chuẩn, các bean có metadata quản trị và bean thông thường là các trường hợp khác nhau.

Mục tiêu bài này:

- Hiểu MBean nào có thể được exporter tự phát hiện.
- Phân biệt Standard MBean, MXBean, Dynamic MBean và bean có annotation quản trị.
- Cấu hình autodetection bằng `MBeanExporter` và biết vai trò của `AnnotationMBeanExporter`.
- Hiểu cách xác định `ObjectName`, registration lifecycle và chính sách xử lý xung đột.
- Xác minh kết quả bằng `MBeanServer.queryNames(...)` và `MBeanInfo`.
- Nhận biết ảnh hưởng của proxy, lazy initialization và phạm vi bảo mật.

## 2. Mental model: Spring bean → JMX registry

```text
       Spring ApplicationContext
                  |
       các bean được quản lý
                  |
                  v
             MBeanExporter
                  |
        +---------+---------+
        |                   |
   Explicit beans       Autodetection
   setBeans(...)        xem bean đủ điều kiện
        |                   |
        +---------+---------+
                  |
          chọn ObjectName
                  |
        MBeanServer.registerMBean(...)
                  |
                  v
        JMX management surface
                  |
            JConsole / client
```

Autodetection có hai chiều cần giữ tách biệt:

1. **Lựa chọn ứng viên:** bean nào thuộc tập MBean mà exporter sẽ quản lý?
2. **Xây dựng/đăng ký MBean:** bean được đăng ký trực tiếp như MBean chuẩn hay phải được thích ứng thành ModelMBean, và ObjectName nào được sử dụng?

Việc một bean tồn tại trong Spring không chứng minh nó đã được đăng ký JMX. Việc một class có interface tên `SomethingMBean` cũng chưa bảo đảm ứng dụng đã bật đúng exporter và liên kết tới MBeanServer mà công cụ đang quan sát.

## 3. JMX-compliant MBean nghĩa là gì?

Một đối tượng JMX-compliant có hình thức mà JMX có thể hiểu và quản trị trực tiếp, thường là:

| Dạng | Nhận diện cơ bản | Ý nghĩa |
|---|---|---|
| Standard MBean | Class thực hiện interface có tên dạng `ClassNameMBean` hoặc được bọc thích hợp | JMX suy ra thuộc tính và operation từ interface |
| MXBean | Class thực hiện interface `*MXBean`, `@MXBean` hoặc wrapper MXBean hợp lệ | Giao diện JMX với type mapping sang Open Types |
| Dynamic MBean | Class triển khai `DynamicMBean` | Tự cung cấp metadata và xử lý access/invoke |
| ModelMBean | Implementation `ModelMBean` hoặc được Spring tạo khi export bean thông thường | Dùng metadata mô tả quản trị linh hoạt |

Trong Spring JMX, autodetect đối tượng đã là MBean hợp lệ là một mục đích khác với tự phát hiện bean có `@ManagedResource`. Một Java object bình thường không tự trở thành Standard MBean chỉ vì tên class có chữ `Monitor`.

Ví dụ:

```java
public interface QueueMonitorMBean {
    int getQueueDepth();
    void resetStatistics();
}

public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getQueueDepth() {
        return 42;
    }

    @Override
    public void resetStatistics() {
        // Reset các số đo do ứng dụng quản lý.
    }
}
```

`QueueMonitor` là một Standard MBean theo convention của JMX vì implement `QueueMonitorMBean`. Trong Spring, nếu instance của nó được quản lý như một bean và được exporter chọn, JMX có thể đọc attribute `QueueDepth` và gọi operation `resetStatistics`.

Ngược lại:

```java
public class InternalQueueService {
    public int getQueueDepth() { return 42; }
    public void deleteAllJobs() { /* ... */ }
}
```

Class này không có management interface hay metadata đặc biệt. Không nên mặc định autodetection sẽ đăng ký nó thành một MBean có thể gọi mọi public method. Việc export một bean thông thường là quyết định cấu hình rõ ràng, thường thông qua assembler/metadata tương ứng.

## 4. Dùng MBeanExporter với autodetect

`org.springframework.jmx.export.MBeanExporter` là thành phần chính của Spring JMX export. Nó có thể export một danh sách bean được chỉ định và/hoặc tự phát hiện những bean hợp lệ trong application context.

Ví dụ cấu hình Java:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanServerFactoryBean mBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }

    @Bean
    public MBeanExporter mBeanExporter(javax.management.MBeanServer server) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setAutodetect(true);
        return exporter;
    }
}
```

Cấu hình thể hiện ba ý:

- `setAutodetect(true)` bật tìm kiếm MBean tự động.
- `setServer(server)` xác định `MBeanServer` đích.
- Spring quản lý vòng đời của exporter trong `ApplicationContext`.

Trong một ứng dụng thực tế, có thể đã có platform MBeanServer được cấu hình sẵn. Bạn cũng có thể tạo bean `MBeanServer` từ `ManagementFactory.getPlatformMBeanServer()` thay vì dùng `MBeanServerFactoryBean` nếu ứng dụng muốn đăng ký trên server JVM mặc định. Không tạo nhiều `MBeanServer` một cách không chủ đích vì JConsole có thể đang quan sát server khác với server mà exporter ghi dữ liệu.

Ví dụ thay thế:

```java
@Bean
public javax.management.MBeanServer platformMBeanServer() {
    return java.lang.management.ManagementFactory
        .getPlatformMBeanServer();
}
```

**Chọn đúng một bean server theo mô hình ứng dụng.** Nếu nhiều `MBeanServer` bean cùng type tồn tại, injection theo type có thể trở nên mơ hồ; khi đó cần dùng `@Qualifier` hoặc thiết kế cấu hình rõ ràng.

## 5. Ví dụ chạy được: Standard MBean được Spring phát hiện

### 5.1. Management interface

Tạo file `TaskMonitorMBean.java`:

```java
public interface TaskMonitorMBean {
    long getCompletedCount();
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
    void resetCounters();
}
```

`CompletedCount` là read-only attribute; `WarningThreshold` là read-write attribute; `resetCounters()` là operation.

### 5.2. Implementation

Tạo `TaskMonitor.java`:

```java
import java.util.concurrent.atomic.AtomicLong;

public class TaskMonitor implements TaskMonitorMBean {
    private final AtomicLong completed = new AtomicLong();
    private volatile int warningThreshold = 100;

    @Override
    public long getCompletedCount() {
        return completed.get();
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int value) {
        if (value < 1 || value > 10_000) {
            throw new IllegalArgumentException(
                "WarningThreshold must be 1..10000"
            );
        }
        warningThreshold = value;
    }

    @Override
    public void resetCounters() {
        completed.set(0);
    }

    // Nội bộ: không có trong management interface.
    public void recordCompletedTask() {
        completed.incrementAndGet();
    }
}
```

### 5.3. Cấu hình Spring

Tạo `LabConfig.java`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.naming.IdentityNamingStrategy;

@Configuration
public class LabConfig {

    @Bean
    public TaskMonitor taskMonitor() {
        return new TaskMonitor();
    }

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(MBeanServer jmxServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(jmxServer);
        exporter.setAutodetect(true);
        exporter.setNamingStrategy(new IdentityNamingStrategy());
        return exporter;
    }
}
```

Ở đây `IdentityNamingStrategy` là một ví dụ chiến lược đặt tên Spring; không nên hard-code một ObjectName mà bạn chưa biết có được sinh ra bởi naming strategy đã chọn. Trong thực hành, cách xác nhận đáng tin cậy nhất là truy vấn MBeanServer để tìm ObjectName thực sự sau khi context refresh.

Một chiến lược naming khác, bao gồm custom naming strategy hoặc key mapping, có thể cho kết quả khác. **Autodetection chọn đối tượng**, còn naming strategy chọn tên đăng ký; đừng gộp hai việc đó thành một.

### 5.4. Khởi chạy và liệt kê MBean

Tạo `Main.java`:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(LabConfig.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            System.out.println("Spring JMX context started");

            for (ObjectName name : server.queryNames(null, null)) {
                if (name.toString().contains("TaskMonitor")) {
                    MBeanInfo info = server.getMBeanInfo(name);
                    System.out.println("Found: " + name);
                    System.out.println("Class: " + info.getClassName());
                }
            }

            Thread.sleep(90_000L);
        }
    }
}
```

Cần dependency Spring Context và Spring JMX module tương ứng trong dự án. Đoạn code nhằm minh họa cách đăng ký và khám phá. Có thể thay điều kiện lọc theo `TaskMonitor` bằng một ObjectName pattern phù hợp với naming strategy thực tế.

Một kết quả đúng về mặt nguyên lý là có MBean được đăng ký đại diện cho `TaskMonitor`; tên cụ thể phụ thuộc naming strategy và cấu hình exporter.

**Không suy luận từ việc compile thành công rằng exporter đã đăng ký đúng:** đọc `MBeanServer.queryNames` và `MBeanInfo` mới xác nhận registration thực tế.

## 6. Nếu cần tên ObjectName ổn định

ObjectName là cách client định vị MBean, có dạng:

```text
domain:key1=value1,key2=value2
```

Ví dụ:

```text
demo.tasks:type=TaskMonitor,name=primary
```

Đối với production, một tên ổn định giúp monitoring query, alerting và dashboard không bị gãy khi đổi tên Spring bean hoặc class.

Với các bean được export bằng mapping explicit, bạn có thể chỉ định tên:

```java
@Bean
public MBeanExporter explicitMBeanExporter(
        MBeanServer server,
        TaskMonitor taskMonitor) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(java.util.Map.of(
        "demo.tasks:type=TaskMonitor,name=primary",
        taskMonitor
    ));
    return exporter;
}
```

Ví dụ này là cấu hình **explicit export** để so sánh với autodetection. Không dùng đồng thời hai exporter cùng đăng ký `TaskMonitor` với ObjectName trùng nhau nếu không có chính sách chủ đích. Trong dự án thật, cần chọn cách đặt tên thống nhất và kiểm tra collision.

**Trade-off:** autodetection giảm cấu hình từng bean; explicit mapping dễ kiểm soát chính xác những bean được export và tên của chúng. Khi compliance hoặc bảo mật yêu cầu allowlist chặt chẽ, explicit mapping thường đáng xem xét.

## 7. Autodetect các đối tượng đã triển khai giao diện JMX

Đối tượng có interface quản trị theo chuẩn là ứng viên rõ ràng cho autodetection:

```java
public interface CacheMonitorMBean {
    int getCacheSize();
}

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public int getCacheSize() {
        return 64;
    }
}
```

Nếu class này là Spring bean được exporter xem xét, nó có thể được nhận diện như Standard MBean và export theo giao diện `CacheMonitorMBean`.

Với MXBean:

```java
public interface WorkerPoolMXBean {
    int getActiveWorkers();
}

public class WorkerPool implements WorkerPoolMXBean {
    @Override
    public int getActiveWorkers() {
        return 4;
    }
}
```

MXBean là một kiểu MBean quản trị của JMX có type mapping sang OpenData; các class compliant có thể được đăng ký theo cơ chế thích hợp. Tuy nhiên, chính sách autodetection và cách Spring xác định MBean có thể phụ thuộc phiên bản, đối tượng proxy và loại bean. Khi MXBean không xuất hiện như dự kiến, hãy kiểm tra `MBeanInfo`, log của exporter và tính JMX-compliant của đối tượng thực tế, thay vì tự động chuyển sang export mọi method.

Với `DynamicMBean`:

```java
public class DynamicMonitor implements javax.management.DynamicMBean {
    // Implement getMBeanInfo, getAttribute, setAttribute,
    // getAttributes, setAttributes và invoke theo hợp đồng JMX.
}
```

Dynamic MBean tự cung cấp metadata; nó cũng là một dạng có thể dùng trong JMX. Nhưng ví dụ skeleton này chưa đủ triển khai đầy đủ. Nếu cần thực hành, bắt đầu với Standard MBean vì hợp đồng ngắn, dễ đối chiếu.

### Một điểm cần tránh

Không suy ra rằng **mọi interface bất kỳ** đều làm một bean JMX-compliant. Ví dụ `Runnable`, `Closeable`, `OrderRepository` hoặc `TaskService` không phải management interface của JMX. Chuẩn JMX nhận diện theo các quy tắc Standard MBean/MXBean/DynamicMBean và các wrapper phù hợp.

## 8. AnnotationMBeanExporter và @ManagedResource: cơ chế khác cần phân biệt

Spring hỗ trợ annotation-based export:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "demo.cache:type=CacheStatus")
public class CacheStatus {
    @ManagedAttribute
    public int getSize() {
        return 42;
    }
}
```

Với `@EnableMBeanExport` hoặc một `AnnotationMBeanExporter` được cấu hình phù hợp, Spring có thể tìm các bean có `@ManagedResource`, đọc metadata `@ManagedAttribute`/`@ManagedOperation` và đăng ký chúng qua JMX.

Đây là một đường **autodetection dựa trên annotation metadata**, không đồng nghĩa với việc class triển khai interface `CacheStatusMBean` theo JMX chuẩn. Một bean có `@ManagedResource` có thể không triển khai Standard MBean interface nhưng vẫn được exporter thích hợp biến thành Spring ModelMBean.

Hai trường hợp điển hình:

```text
Standard MBean autodetection:
  Spring bean implements SomethingMBean
       -> MBeanExporter detects compliant MBean
       -> MBeanServer registration

Annotation-based autodetection:
  Spring bean annotated @ManagedResource
       -> AnnotationMBeanExporter / metadata assembler
       -> ModelMBean registration
```

Trong một ứng dụng đã dùng Spring Boot, auto-configuration cũng có thể tham gia tạo exporter. Tránh bật hai cơ chế chồng lấn cùng lúc cho một tập bean nếu không có chiến lược ownership và ObjectName rõ ràng.

## 9. Autodetect không có nghĩa export tất cả bean

Một hiểu nhầm phổ biến:

```java
@Component
public class PaymentService {
    public String getApiKey() { /* ... */ }
    public void chargeCustomer() { /* ... */ }
}
```

Nếu chỉ `@Component`, không có hợp đồng JMX hoặc metadata quản trị thích hợp, bean không nên bị xem là MBean chỉ vì có public getter. Điều này có ý nghĩa lớn về bảo mật.

Nhưng cũng không nên coi autodetection là bộ lọc bảo mật hoàn hảo. Khi codebase có nhiều bean triển khai interface MBean hoặc có `@ManagedResource`, bật autodetection có thể làm số MBean được công bố tăng khi team thêm bean mới.

Các quy tắc nên áp dụng:

1. Định nghĩa rõ policy: loại MBean nào được phép tự động export.
2. Giữ management interface nhỏ và chỉ chứa các attribute/operation có ý nghĩa vận hành.
3. Tránh getter trả secret, raw configuration, user data hoặc object graph lớn.
4. Chọn ObjectName ổn định; kiểm soát collision.
5. Kiểm kê MBeanInfo thực tế sau thay đổi.
6. Giới hạn remote JMX bằng network access, authentication, TLS và quyền tối thiểu.

Nếu cần ranh giới nghiêm ngặt, dùng explicit `setBeans(...)` hoặc chiến lược đặt tên/filter phù hợp thay vì bật autodetect không có kiểm kê.

## 10. Những biến thể cấu hình autodetect

`MBeanExporter` hỗ trợ cấu hình autodetection. Ngoài `setAutodetect(true)`, một số phiên bản Spring cung cấp chế độ autodetect theo hằng số như `AUTODETECT_MBEAN` và `AUTODETECT_ASSEMBLER`. Hằng số và API sử dụng cần đối chiếu với phiên bản Spring đang dùng.

Về mặt tư duy:

| Chế độ | Ý nghĩa khái quát |
|---|---|
| Không autodetect | Chỉ export bean đã liệt kê/cấu hình rõ |
| Detect MBeans | Tìm bean đã là MBean compliant theo JMX |
| Detect assembler candidates | Tìm bean đáp ứng metadata assembler, thường phục vụ annotation-based export |
| Kết hợp | Dùng cả các nguồn khám phá phù hợp |

Một số version Spring phân biệt rõ autodetect compliant MBeans với bean có metadata; vì vậy không nên suy ra rằng bật một flag duy nhất sẽ chọn cùng một tập ứng viên trong mọi phiên bản.

Dù chọn chế độ nào, kết quả cuối cùng cần kiểm chứng qua những ObjectName thực sự có trong MBeanServer. Thay đổi mode có thể làm tăng bề mặt quản trị, gây đăng ký trùng hoặc thay đổi hành vi startup.

## 11. Khi nào MBean được đăng ký và hủy?

Spring thường khởi tạo và export MBean trong vòng đời ApplicationContext. Với những bean singleton không lazy, exporter có thể tìm và đăng ký chúng khi context refresh. Khi context đóng, exporter chịu trách nhiệm unregister các MBean thuộc phạm vi quản lý của mình theo cơ chế lifecycle thích hợp.

Nhưng có các ngoại lệ cần suy nghĩ:

- Bean lazy có thể chưa được tạo ở giai đoạn exporter autodetect.
- Bean được proxy có thể mang kiểu/interface khác với implementation.
- Bean prototype có lifecycle không giống singleton.
- Hai ApplicationContext cùng dùng một MBeanServer có thể đăng ký tên trùng.
- MBean được đăng ký trực tiếp ngoài Spring không tự trở thành MBean do exporter sở hữu.
- Remote client có thể gọi operation khi service đang STARTING hoặc STOPPING.

Đừng nhầm **MBean registered** với **service ready**. Một MBean có thể trả trạng thái `STARTING` để giúp vận hành biết vì sao hệ thống chưa sẵn sàng; getter phải xử lý trạng thái này an toàn.

Nếu một operation quản trị yêu cầu dependency đã READY, kiểm tra điều kiện runtime trước khi thực hiện.

## 12. Vấn đề Spring proxy và kiểm tra kiểu

Spring AOP có thể tạo JDK dynamic proxy hoặc class-based proxy. Với JDK dynamic proxy, đối tượng proxy thường lộ những interface được proxy; những method chỉ có trên class target có thể không xuất hiện qua proxy. Với class-based proxy, quan hệ kiểu có thể khác.

Ví dụ:

```java
public interface WorkerManagementMBean {
    int getActiveWorkers();
}
```

Nếu implementation `WorkerService` thực hiện interface theo convention MBean nhưng Spring trả về proxy không giữ hoặc không thể được JMX introspect đúng như mong muốn, autodetection có thể không nhận bean là compliant hoặc registration có thể thất bại.

Cách chẩn đoán:

- Xác định bean đang được exporter nhìn thấy là target hay proxy.
- Kiểm tra danh sách interface thực tế của proxy.
- Kiểm tra management interface và naming convention.
- Đọc exception gốc từ registration.
- Nếu Spring annotation exporter đang dùng, kiểm tra metadata assembler và ObjectName.

Không nên bỏ qua vấn đề bằng cách thay management interface thành export toàn bộ public methods, vì điều đó có thể vô tình làm lộ chức năng nghiệp vụ.

## 13. ObjectName và chính sách xung đột

Một JMX `ObjectName` phải duy nhất trong `MBeanServer`. Nếu một MBean đã đăng ký với:

```text
demo.tasks:type=TaskMonitor,name=primary
```

một exporter khác cố đăng ký cùng tên có thể nhận `InstanceAlreadyExistsException` hoặc chịu chính sách registration của exporter, tùy cấu hình.

Spring hỗ trợ cấu hình behavior khi MBean đã tồn tại. Các lựa chọn mang tính khái niệm gồm: báo lỗi, bỏ qua đăng ký của exporter mới, hoặc thay MBean cũ trong các tình huống được phép.

Không dùng hành vi replace chỉ để “hết lỗi” nếu không rõ ai sở hữu MBean ban đầu. Thay một MBean của platform hoặc thành phần khác có thể phá công cụ giám sát.

Để hạn chế xung đột:

- Quy hoạch domain riêng, ví dụ `company.orders`, `company.cache`.
- Có key `type` và `name` ổn định.
- Đảm bảo naming strategy sinh tên duy nhất cho những bean khác nhau.
- Kiểm soát số lượng exporter và phạm vi autodetection.
- Xác minh trên MBeanServer thực tế.

## 14. Kiểm tra danh sách đăng ký bằng JMX API

Một khi exporter hoạt động, có thể dùng code xác minh:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(
        new ObjectName("demo.*:*"), null)) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println(
        name + " -> " + info.getClassName()
    );
}
```

Câu lệnh trên chỉ nhìn vào **platform MBeanServer**. Nếu exporter dùng một MBeanServer riêng, cần truy vấn đúng instance do Spring quản lý. `queryNames` trả tập kết quả, không nên dựa vào thứ tự để suy luận “bean nào export trước”.

### 14.1. Xem attribute và operation

```java
MBeanInfo info = server.getMBeanInfo(objectName);

for (var attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName() +
        " readable=" + attribute.isReadable() +
        " writable=" + attribute.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println("operation: " + operation.getName());
}
```

`objectName` cần là tên đã tìm thấy thực sự. Dữ liệu metadata giúp phân biệt:

- MBean đã được đăng ký hay chưa.
- Những attribute nào đọc/ghi được.
- Những operation nào có thể được gọi.
- Có method quản trị thừa hoặc thiếu so với management interface không.

Đừng chỉ dựa vào việc tên MBean xuất hiện trong JConsole: registration thành công không có nghĩa hợp đồng đã đúng hoặc dữ liệu xuất ra an toàn.

## 15. Thực hành so sánh ba cấu hình

**Tình huống A — không bật autodetection.** Cấu hình `MBeanExporter` với danh sách `setBeans(...)` chỉ chứa `TaskMonitor`. Kiểm tra chỉ MBean đã explicit mapping được đăng ký. Thêm một bean implement `CacheMonitorMBean` nhưng không đưa vào mapping; kiểm tra kết quả.

**Tình huống B — bật autodetection.** Bật `setAutodetect(true)`. Với các bean compliant trong context, truy vấn MBeanServer để xem MBean nào xuất hiện thêm. Ghi lại ObjectName thực tế và xem metadata. Nếu không thấy một bean, kiểm tra rule compliant, lifecycle và proxy.

**Tình huống C — annotation-based export.** Thêm một `@ManagedResource` bean nhưng không implement Standard MBean interface. Dùng `@EnableMBeanExport` hoặc `AnnotationMBeanExporter` tương ứng và so sánh cách MBean được nhận diện. Tránh chạy đồng thời cấu hình xung đột cùng ObjectName.

Các tình huống nên được chạy riêng để nhìn rõ khác biệt. Việc bật thêm exporter trong cùng một context có thể dẫn đến xung đột thay vì một phép so sánh có ích.

## 16. Các lỗi thường gặp và cách xử lý

### 16.1. Bean có interface MBean nhưng không thấy trong JConsole

Kiểm tra bean có thật trong context, exporter có bật autodetect và kết nối tới đúng MBeanServer không. Kiểm tra proxy và ObjectName thực tế thay vì chỉ tìm theo tên class.

### 16.2. Spring báo NotCompliantMBeanException

Kiểm tra quy tắc naming của Standard MBean, các method trong interface, kiểu Java và sự tương thích giữa target/proxy. Một interface đặt tên gần đúng không nhất thiết được JMX xem là compliant.

### 16.3. Bean có @ManagedResource nhưng không được detect

Kiểm tra có AnnotationMBeanExporter hoặc hạ tầng metadata export thích hợp, bean có được Spring quản lý, và cấu hình auto-detection có bao gồm annotated candidates không. `MBeanExporter` thông thường với chế độ detect compliant MBeans không đồng nghĩa một annotation exporter được bật đầy đủ.

### 16.4. Không tìm thấy ObjectName dự đoán

Autodetection và naming strategy là hai việc khác nhau. Truy vấn tên thực tế, kiểm tra naming strategy và property/domain đã cấu hình, rồi xây dựng query phù hợp.

### 16.5. Trùng MBean khi bật nhiều exporter

Xác định exporter nào sở hữu từng ObjectName, bỏ cấu hình dư hoặc phân vùng resource rõ ràng. Tránh thay thế MBean của thành phần khác nếu không có chủ đích.

### 16.6. Bean được tìm thấy nhưng chưa ready

MBean có thể đăng ký trong quá trình startup trước khi background initialization hoàn tất. Getter nên báo state như `STARTING`; operation có tác dụng phụ phải kiểm tra readiness.

### 16.7. MBean xuất hiện rồi mất

Kiểm tra application context có bị đóng, bean/exporter có lifecycle bất thường, JVM có restart, hoặc ObjectName bị đăng ký lại. JConsole đang kết nối đến một process cũ cũng gây hiểu nhầm.

### 16.8. Số lượng MBean tăng bất thường sau khi thêm code

Với autodetection, một class mới implement interface JMX hoặc một bean annotation mới có thể được export tự động. Kiểm kê MBean mới và bảo đảm policy quản trị được tuân thủ.

## 17. Bảo mật khi dùng autodetection

Autodetection tiện lợi, nhưng có thể làm **bề mặt quản trị tăng mà không có một dòng mapping explicit mới**. Vì thế mọi management interface và `@ManagedResource` cần được review như API có đặc quyền.

Một số nguyên tắc vận hành:

1. Không công bố credential, API key, session token, private key hoặc dữ liệu người dùng qua getter.
2. Không export operation nguy hiểm chỉ vì thuận tiện debug.
3. Đặt validation cho writable attribute và operation thay đổi trạng thái.
4. Không mở remote JMX ra mạng công cộng; kiểm soát authentication, TLS, network access và quyền.
5. Phân biệt read-only JMX attribute với cơ chế phân quyền người dùng: read-only vẫn có thể làm lộ dữ liệu.
6. Kiểm kê ObjectName/MBeanInfo sau khi deploy.
7. Giữ management interface nhỏ, mô tả rõ semantics và đơn vị số đo.
8. Nếu môi trường compliance yêu cầu allowlist tường minh, cân nhắc tắt autodetection và dùng explicit mappings.

**Autodetection không phải một security boundary.** Nó là cơ chế tìm và đăng ký ứng viên. Quyền được kết nối/call, tính an toàn dữ liệu và hành vi nghiệp vụ vẫn phải được thiết kế độc lập.

## 18. Bài tập thực hành

### Bài 1 — Standard MBean được tự phát hiện

Tạo `CounterMBean` với `getCount()` và `reset()`. Viết `Counter` implement interface đó và khai báo Spring bean. Bật `MBeanExporter.setAutodetect(true)`, tìm ObjectName trên MBeanServer, đọc attribute và gọi operation.

### Bài 2 — Một bean thông thường có được export không?

Thêm `BillingService` không có MBean interface và không có annotation JMX, dù có nhiều public method. Xác minh nó không tự xuất hiện như Standard MBean khi chỉ dùng autodetection compliant MBeans.

### Bài 3 — MXBean và type mapping

Tạo `WorkerPoolMXBean` với `int getActiveWorkers()` và `Map<String,Integer> getByQueue()`. Kiểm tra class compliant và cách giá trị Map được trình bày qua JMX khi exporter đăng ký.

### Bài 4 — Annotation-based export

Tạo bean `CacheStatus` dùng `@ManagedResource`/`@ManagedAttribute` nhưng không có interface `CacheStatusMBean`. Bật annotation export và quan sát khác biệt với Standard MBean autodetection.

### Bài 5 — Naming collision

Export hai bean dưới cùng một ObjectName bằng hai cấu hình khác nhau trong môi trường test. Quan sát lỗi registration, rồi sửa naming strategy hoặc key mapping sao cho tên duy nhất. Không thử replace một MBean không thuộc quyền sở hữu của ứng dụng.

### Bài 6 — MBeanInfo inventory

Viết đoạn code lấy `MBeanInfo` và in các attribute/operation cho mọi ObjectName trong domain `demo.*`. So sánh với management interface ở source, đánh dấu những method không nên công bố.

### Bài 7 — Proxy effect

Bật Spring AOP cho một service implement management interface. Quan sát loại proxy và các interface nó lộ ra; kiểm tra MBean có được phát hiện/đăng ký như trước không.

## 19. Câu hỏi tự kiểm tra

1. `MBeanExporter.setAutodetect(true)` giúp giảm thao tác nào?
2. Standard MBean được nhận diện bằng những quy tắc gì?
3. MXBean và DynamicMBean khác Standard MBean ở cấp hợp đồng như thế nào?
4. Tại sao `@Component` đơn lẻ không đồng nghĩa một bean sẽ trở thành MBean?
5. `AnnotationMBeanExporter` khác gì cơ chế phát hiện MBean compliant?
6. Autodetection và `ObjectNamingStrategy` giải quyết hai việc nào?
7. Vì sao bật hai exporter có thể gây trùng ObjectName?
8. Một bean proxy có thể làm thay đổi khả năng phát hiện MBean ra sao?
9. Tại sao `MBeanInfo` là bước kiểm chứng quan trọng?
10. Những rủi ro bảo mật nào cần xem xét nếu nhiều MBean mới được tự động export?

## 20. Ghi nhớ

**Autodetection trong Spring JMX giúp exporter tìm các bean quản trị đủ điều kiện mà không cần explicit mapping từng bean.** Đối tượng đã triển khai hợp đồng JMX compliant là trọng tâm của cơ chế phát hiện MBean; bean có annotation `@ManagedResource` đi qua cơ chế metadata export tương ứng. Autodetection không có nghĩa export toàn bộ Spring bean.

Thiết kế tốt cần phân biệt rõ selection, naming, registration và lifecycle; kiểm tra `ObjectName` cùng `MBeanInfo` thực tế; giữ bề mặt quản trị nhỏ; và bảo vệ kết nối JMX. Khi sự minh bạch hoặc yêu cầu kiểm soát chặt quan trọng hơn giảm cấu hình, hãy dùng explicit mapping thay vì autodetection không giới hạn.
