# Spring Framework JMX — Thực hành phơi bày resource bằng @ManagedResource

## 1. Mục tiêu bài thực hành

`@ManagedResource` là annotation của Spring Framework trong package `org.springframework.jmx.export.annotation`. Annotation này khai báo một Spring bean là một resource có thể quản trị qua Java Management Extensions (JMX). Khi infrastructure của Spring JMX được cấu hình đúng, bean có thể được export thành MBean và đăng ký với một `ObjectName` trong `MBeanServer`.

Bài thực hành này đi từ một Java POJO thông thường đến resource được JConsole hoặc một JMX client nhìn thấy. Nội dung bao gồm cấu hình Spring, `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, kiểm tra `MBeanInfo`, đặt tên và xử lý lỗi thường gặp.

**Kết quả mong đợi:** Sau khi chạy ứng dụng, một MBean có ObjectName `com.example.training:type=WorkerPool,name=primary` xuất hiện, cho phép đọc trạng thái pool, cập nhật giới hạn hợp lệ và gọi một operation an toàn.

```text
Spring ApplicationContext
   |
   +-- WorkerPoolControl (@ManagedResource)
   |      +-- getActiveWorkers() (@ManagedAttribute)
   |      +-- getMaxWorkers()    (@ManagedAttribute)
   |      +-- setMaxWorkers()    (@ManagedAttribute)
   |      +-- resetStatistics()  (@ManagedOperation)
   |
   +-- JMX export infrastructure
            |
            v
       MBeanServer
            |
            v
com.example.training:type=WorkerPool,name=primary
            |
            v
       JConsole / JMX client
```

## 2. Phân biệt annotation và quá trình đăng ký

| Thành phần | Vai trò |
|---|---|
| `@ManagedResource` | Đánh dấu class/resource để exporter lấy metadata quản trị |
| `@ManagedAttribute` | Công bố getter/setter thành JMX attribute |
| `@ManagedOperation` | Công bố một method thành JMX operation |
| `@EnableMBeanExport` | Kích hoạt cơ chế export JMX theo annotation trong Spring context |
| `MBeanExporter` | Đăng ký bean vào MBeanServer, có thể cấu hình tường minh |
| `MBeanServer` | Registry của MBeans đang chạy trong một JVM |
| `ObjectName` | Định danh duy nhất của MBean trong một MBeanServer |
| `MBeanInfo` | Mô tả các attributes, operations và notifications đã công bố |

Chỉ thêm `@ManagedResource` lên một class không đồng nghĩa có MBean đăng ký thành công. Class đó phải được Spring quản lý như một bean, infrastructure JMX phải hoạt động, object name hợp lệ và không trùng registration hiện hữu.

Ví dụ:

```java
@ManagedResource(objectName = "com.example.training:type=WorkerPool,name=primary")
public class WorkerPoolControl {
    // ...
}
```

Nếu ứng dụng không tạo instance `WorkerPoolControl` trong Spring context, exporter không có bean thích hợp để quét hoặc đăng ký.

## 3. Chuẩn bị môi trường

Ví dụ sử dụng Java 17 hoặc mới hơn, Spring Framework 6.x và Maven. Bạn có thể dùng ứng dụng Spring Boot tương thích, nhưng để tránh nhầm lẫn giữa Boot auto-configuration và Spring Framework JMX, phần chính sẽ dùng một Spring context thuần.

Maven dependencies tối thiểu:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
    <version>${spring.version}</version>
  </dependency>
</dependencies>
```

Trong `pom.xml`, xác định `spring.version` thành một phiên bản Spring Framework thích hợp cho JDK đang sử dụng, hoặc dùng dependency management đã được dự án quản lý. Không nên hardcode các phiên bản Spring module khác nhau trong cùng một ứng dụng.

JMX API nằm trong Java platform (`java.management` module). Khi dùng một modular application, cần khai báo `requires java.management;` và các module Spring cần thiết theo thiết kế module của dự án.

Bạn có thể tạo package:

```text
src/main/java/com/example/training/
  WorkerPoolControl.java
  TrainingJmxConfig.java
  TrainingApplication.java
  JmxInspector.java
```

## 4. Tạo resource có @ManagedResource

Đầu tiên xây dựng POJO quản trị một worker pool giả lập. Trong ứng dụng thật, nên dùng management facade bọc executor hoặc worker service thực tế; ví dụ này được đơn giản hóa để dễ thử thao tác.

```java
package com.example.training;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.training:type=WorkerPool,name=primary",
    description = "Training worker pool controls"
)
public class WorkerPoolControl {
    private final AtomicInteger activeWorkers = new AtomicInteger(3);
    private volatile int maxWorkers = 8;
    private final AtomicInteger processedJobs = new AtomicInteger(42);

    @ManagedAttribute(description = "Currently active workers")
    public int getActiveWorkers() {
        return activeWorkers.get();
    }

    @ManagedAttribute(description = "Maximum allowed workers")
    public int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute(description = "Set the maximum worker count")
    public void setMaxWorkers(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException("maxWorkers must be 1..64");
        }
        maxWorkers = value;
    }

    @ManagedAttribute(description = "Processed job counter")
    public int getProcessedJobs() {
        return processedJobs.get();
    }

    @ManagedOperation(description = "Reset the processed job counter")
    public void resetStatistics() {
        processedJobs.set(0);
    }

    // Phương thức nội bộ không được đánh dấu JMX.
    public void internalMaintenance() {
        activeWorkers.set(0);
    }
}
```

### Giải thích

- `@ManagedResource` khai báo metadata cho resource và chỉ định ObjectName rõ ràng.
- Các getter có `@ManagedAttribute` tạo attributes readable; `getMaxWorkers` kết hợp `setMaxWorkers` tạo attribute read/write.
- `resetStatistics()` là một JMX operation vì có `@ManagedOperation`.
- `internalMaintenance()` không được annotate; với metadata assembler theo annotation, không chủ định công bố method này.
- Setter kiểm tra giá trị hợp lệ. Một thao tác JMX có thể đến từ công cụ vận hành, vì vậy validation phải ở server.

**Không công bố toàn bộ public methods** chỉ vì chúng nằm trong class. Hãy xem surface của MBean như một API quản trị, giới hạn những gì thật sự cần.

## 5. Kích hoạt JMX annotation export

Spring Framework cung cấp `@EnableMBeanExport` để đăng ký các bean có annotation quản trị thích hợp:

```java
package com.example.training;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class TrainingJmxConfig {

    @Bean
    public WorkerPoolControl workerPoolControl() {
        return new WorkerPoolControl();
    }
}
```

Với cấu hình này, Spring tạo instance `WorkerPoolControl` trong application context rồi infrastructure JMX có thể export thành MBean có ObjectName được khai báo.

Chỉ chọn một cơ chế export chính. Nếu dự án đã bật `spring.jmx.enabled=true` trong Spring Boot và đang có JMX auto-configuration, kiểm tra tránh tạo thêm exporter trùng tên bởi `@EnableMBeanExport` hoặc `MBeanExporter` tự khai báo.

## 6. Chạy Spring context và giữ ứng dụng sống

Để JConsole kịp kết nối vào JVM, ứng dụng demo cần duy trì process sau khi Spring context đã khởi tạo.

```java
package com.example.training;

import java.util.concurrent.CountDownLatch;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class TrainingApplication {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext ctx =
                 new AnnotationConfigApplicationContext(TrainingJmxConfig.class)) {

            System.out.println("JMX demo started; PID = " + ProcessHandle.current().pid());
            System.out.println("Use JConsole to inspect WorkerPool MBean.");

            new CountDownLatch(1).await();
        }
    }
}
```

Đây là ví dụ local demo. `CountDownLatch.await()` giữ chương trình chờ cho đến khi bị ngắt; khi phát tín hiệu dừng phù hợp, context đóng và exporter có cơ hội unregister các MBeans do nó sở hữu. Không dùng mô hình chờ vô hạn này để thiết kế lifecycle cho ứng dụng production.

## 7. Xác minh ObjectName bằng MBeanServer

Không chỉ dựa vào log startup. Dùng JMX API kiểm tra MBean đã đăng ký:

```java
package com.example.training;

import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxInspector {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.training:type=WorkerPool,name=primary"
        );

        System.out.println("registered = " + server.isRegistered(name));

        if (server.isRegistered(name)) {
            MBeanInfo info = server.getMBeanInfo(name);

            for (var attr : info.getAttributes()) {
                System.out.printf(
                    "%s type=%s read=%s write=%s%n",
                    attr.getName(), attr.getType(),
                    attr.isReadable(), attr.isWritable()
                );
            }

            for (var operation : info.getOperations()) {
                System.out.println("operation=" + operation.getName());
            }
        }
    }
}
```

**Quan trọng:** một Java process khác gọi `ManagementFactory.getPlatformMBeanServer()` chỉ lấy server của chính nó, không phải MBeanServer của demo JVM. Muốn kiểm tra bằng Java, nên chạy inspector trong cùng process hoặc kết nối remote qua `JMXConnector` tới JVM đích. Nếu chạy `JmxInspector` như một chương trình độc lập, kết quả `registered=false` không chứng minh demo export thất bại.

Để test trong cùng JVM, có thể gọi nội dung kiểm tra ngay sau khi context được khởi tạo, hoặc inject MBeanServer do exporter đang dùng.

## 8. Xem resource bằng JConsole

Quy trình thực hành:

1. Chạy chương trình `TrainingApplication` và ghi lại PID.
2. Mở `jconsole` từ một JDK phù hợp.
3. Chọn JVM demo trong danh sách local processes rồi kết nối.
4. Mở tab **MBeans**.
5. Tìm domain `com.example.training`, chọn `type=WorkerPool,name=primary`.
6. Mở **Attributes** để xem `ActiveWorkers`, `MaxWorkers`, `ProcessedJobs`.
7. Đọc giá trị hiện tại của `MaxWorkers` rồi thử ghi giá trị hợp lệ, ví dụ 12.
8. Mở **Operations** để gọi `resetStatistics()`.
9. Đọc lại `ProcessedJobs` để xác minh bộ đếm về 0.

JConsole có thể hiển thị key properties theo một dạng cây khác nhau tùy phiên bản JDK. Nếu không thấy MBean, kiểm tra đúng JVM/PID, đúng MBeanServer mà exporter dùng và ObjectName thực tế.

Không cần mở remote JMX port chỉ để dùng JConsole với một local JVM trong môi trường phát triển; việc mở remote connector có tác động bảo mật riêng.

## 9. Gọi MBean bằng Java JMX API

Trong cùng JVM và đúng MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.training:type=WorkerPool,name=primary"
);

int previous = (Integer) server.getAttribute(name, "MaxWorkers");
System.out.println("maxWorkers before=" + previous);

server.setAttribute(name, new Attribute("MaxWorkers", 12));

int updated = (Integer) server.getAttribute(name, "MaxWorkers");
System.out.println("maxWorkers after=" + updated);

server.invoke(
    name,
    "resetStatistics",
    new Object[0],
    new String[0]
);
```

Với operations có tham số, phải truyền đúng chữ ký kiểu Java. Ví dụ `resize(int)` yêu cầu signature `new String[]{"int"}`, không phải `java.lang.Integer` chỉ vì giá trị trong `Object[]` được boxing.

## 10. Cấu hình explicit MBeanExporter thay thế

Ngoài annotation-driven exporter, Spring còn cho phép khai báo `MBeanExporter` tường minh. Nếu dùng hướng này cho một POJO có Spring JMX annotations, nên cấu hình assembler đọc metadata:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
AnnotationJmxAttributeSource jmxSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
MetadataMBeanInfoAssembler jmxAssembler(AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler = new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}

@Bean
MBeanExporter customExporter(
        WorkerPoolControl control,
        MetadataMBeanInfoAssembler assembler) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setAssembler(assembler);
    exporter.setBeans(Map.of(
        "com.example.training:type=WorkerPool,name=primary",
        control
    ));
    return exporter;
}
```

Đây là **cấu hình thay thế** cho `@EnableMBeanExport`, không phải một exporter bổ sung để chạy đồng thời với cùng bean. Các component exporter/naming/assembler ở ứng dụng cụ thể có thể cần cấu hình thêm tùy cách export POJO; nên xác minh metadata trong MBeanServer thay vì chỉ thấy bean được tạo.

## 11. Phân biệt @ManagedResource với @ManagedAttribute và @ManagedOperation

```java
@ManagedResource(objectName = "com.example.training:type=Cache,name=products")
public class CacheControl {

    @ManagedAttribute
    public int getSize() {
        return 100;
    }

    @ManagedOperation
    public void clearCache() {
        // ...
    }
}
```

`@ManagedResource` định danh và mô tả class/resource. Nó không quyết định rằng mọi field hoặc public method đều được expose. `@ManagedAttribute` mô tả property có getter/setter và `@ManagedOperation` mô tả hành động.

Một số Bean getters có thể được assembler xử lý theo metadata đã cấu hình. Không nên coi public method không annotate là JMX operation nếu đang dùng annotation metadata assembler.

## 12. Những lưu ý đặt ObjectName

Mẫu ObjectName:

```text
com.example.training:type=WorkerPool,name=primary
```

Bao gồm:

- Domain `com.example.training`: namespace JMX của ứng dụng.
- Key `type=WorkerPool`: loại tài nguyên.
- Key `name=primary`: định danh instance.

Trong cùng MBeanServer, ObjectName là duy nhất. Nếu hai Spring beans có cùng ObjectName, `InstanceAlreadyExistsException` có thể xảy ra. Khi có nhiều worker pools, dùng tên riêng:

```text
com.example.training:type=WorkerPool,name=primary
com.example.training:type=WorkerPool,name=background
```

Không đưa password, token, email cá nhân hay dữ liệu nhạy cảm vào ObjectName. Tên thường được hiển thị trong JMX client, monitoring và logs.

Với nhiều JVM replicas khác nhau, ObjectName giống nhau ở hai JVM không gây collision trực tiếp vì mỗi JVM có MBeanServer riêng. Monitoring cần phân biệt endpoint/target của mỗi replica.

## 13. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không thấy MBean dù class có `@ManagedResource` | Bean không nằm trong Spring context hoặc exporter không bật | Kiểm tra `@Bean`, `@ComponentScan`, `@EnableMBeanExport` |
| `InstanceAlreadyExistsException` | Trùng ObjectName hoặc có hai exporters | Kiểm tra danh sách exporter và `queryNames` |
| `MalformedObjectNameException` | Tên domain/key property sai cú pháp | Tạo `new ObjectName(...)` và validate |
| MBean có nhưng không thấy attribute | Getter/setter thiếu `@ManagedAttribute` hoặc assembler sai | Xem `MBeanInfo.getAttributes()` |
| Không thấy operation | Method thiếu `@ManagedOperation` | Xem `MBeanInfo.getOperations()` |
| `AttributeNotFoundException` | Tên attribute JMX sai, ví dụ dùng `maxWorkers` thay `MaxWorkers` | Đọc metadata attribute |
| `InvalidAttributeValueException` hoặc business exception | Giá trị ghi không hợp lệ | So miền validation và kiểu dữ liệu |
| JConsole kết nối mà không thấy resource | Kết nối sai JVM/server | So PID, JMX endpoint và MBeanServer reference |
| JMX operation chạy nhưng sai hành vi AOP | Bean bị proxy, đường invocation bypass interceptor | Kiểm tra facade/proxy và test thực tế |
| Bean bị unregister khi context đóng | Exporter quản lý lifecycle của registration | Kiểm tra owner/context shutdown |

## 14. Mở rộng cho nhiều môi trường

Trong ứng dụng Spring Boot, có thể bật JMX export tùy dòng phiên bản:

```properties
spring.jmx.enabled=true
```

Nhưng cần kiểm tra auto-configuration của phiên bản Boot đang dùng. Không bật thêm `@EnableMBeanExport` nếu nó tạo một exporter thứ hai cho cùng bean và ObjectName. Actuator JMX endpoints cũng khác với custom application MBeans có `@ManagedResource`; cấu hình Actuator exposure không thay thế annotation/resource của ứng dụng.

Trong Docker/Kubernetes, remote JMX cần đặc biệt quan tâm authentication, TLS và RMI networking. Đối với local demo, không cần expose cổng remote JMX rộng rãi.

## 15. Kiểm thử tự động resource đã export

Một integration test tốt nên kiểm tra:

1. Spring context khởi tạo và bean đã được export.
2. MBeanServer có ObjectName mong đợi.
3. `MaxWorkers` readable/writable đúng ý đồ.
4. `ActiveWorkers` và `ProcessedJobs` readable, không writable nếu chỉ có getter.
5. `resetStatistics` có trong danh sách operations.
6. Ghi MaxWorkers hợp lệ thành công.
7. Ghi giá trị ngoài miền bị từ chối, state không đổi.
8. Sau khi context đóng, registration do exporter sở hữu được dọn.

Ví dụ assertion khung:

```java
ObjectName name = new ObjectName(
    "com.example.training:type=WorkerPool,name=primary"
);

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);
assertTrue(
    java.util.Arrays.stream(info.getOperations())
        .anyMatch(op -> op.getName().equals("resetStatistics"))
);
```

Với test, dùng MBeanServer do context test kiểm soát hoặc một tên riêng để tránh collision với ứng dụng khác. Không để test gọi operation nhạy cảm trên production.

## 16. Bài tập thực hành

### Bài 1 — Resource tối thiểu

Tạo `@ManagedResource(objectName="com.example.training:type=Cache,name=users")` cho class `UserCacheControl`, thêm getter `getEntryCount()` gắn `@ManagedAttribute` và xác minh attribute `EntryCount` xuất hiện.

### Bài 2 — Read/write attribute

Thêm `getCapacity()` và `setCapacity(int)` có `@ManagedAttribute`, validation 1..10000. Dùng JConsole để thử ghi một giá trị hợp lệ và một giá trị không hợp lệ.

### Bài 3 — Operation

Thêm `@ManagedOperation` cho `refreshCache()`. Dùng JMX API hoặc JConsole để gọi operation và đọc một counter chứng minh nó đã chạy.

### Bài 4 — Hai instances

Tạo hai resources `primary` và `secondary`. Giải thích tại sao không nên dùng một ObjectName chung cho cả hai và xác minh chúng nằm trong cùng domain với key `name` khác nhau.

### Bài 5 — Duplicate exporter

Bật cả `@EnableMBeanExport` và một explicit `MBeanExporter` export chính bean đó. Quan sát lỗi collision trong môi trường test, sau đó chọn một cấu hình sở hữu registration.

### Bài 6 — Giới hạn surface

Thêm một helper public method không có annotation và xác minh method không xuất hiện trong danh sách operations khi dùng metadata assembler theo annotation.

## 17. Checklist hoàn thành

- Bean được Spring tạo và quản lý.
- Class gắn `@ManagedResource` với ObjectName hợp lệ.
- Những getters/setters cần thiết có `@ManagedAttribute`.
- Những actions được phép có `@ManagedOperation`.
- Spring JMX exporter được bật đúng một lần.
- Bean đăng ký trong MBeanServer mà JConsole/client đang kết nối.
- Tên ObjectName không trùng và không chứa dữ liệu nhạy cảm.
- Giá trị ghi qua JMX được validate.
- Metadata MBeanInfo khớp attributes/operations dự kiến.
- Có kiểm thử lifecycle/unregister và quyền truy cập khi triển khai thật.

## 18. Tổng kết

`@ManagedResource` là điểm khởi đầu để biến một Spring-managed POJO thành resource được quản trị qua JMX. Nhưng annotation trên class phải đi cùng JMX export infrastructure, ObjectName hợp lệ và metadata của `@ManagedAttribute`/`@ManagedOperation` để client thấy đúng interface quản trị. Bài thực hành nên kết thúc bằng việc kiểm tra ObjectName, `MBeanInfo`, đọc/ghi một attribute hợp lệ và gọi một operation an toàn trong JConsole. Việc xác minh runtime giúp tránh ngộ nhận rằng annotation tự động công bố mọi method hay tự mở kết nối JMX remote.