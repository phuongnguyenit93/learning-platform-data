# Cấu hình JMX bằng Java Config trong Spring Framework

## Mục tiêu học tập

Bài này thuộc nhóm **Spring configuration** của Spring Framework JMX. Sau khi hoàn thành, bạn có thể:

- Hiểu các thành phần chính khi cấu hình Java Management Extensions (JMX) bằng Spring Java configuration: `@Configuration`, `@Bean`, `MBeanServer`, `MBeanExporter`, `ObjectName`.
- Tạo một Standard MBean rồi export đối tượng Spring bằng Java Config, không cần XML.
- Biết sự khác nhau giữa export tường minh bằng `MBeanExporter` và export bằng annotation thông qua `@EnableMBeanExport`.
- Gắn một `MBeanServer` xác định vào exporter, kiểm soát tên đăng ký và registration policy.
- Chạy, kiểm tra và gọi MBean bằng `MBeanServer` hoặc JConsole.
- Nhận diện các vấn đề về vòng đời, nhiều instance, nhiều exporter, Spring AOP proxy và Spring Boot auto-configuration.

## 1. Tổng quan: Spring JMX và Java Config

JMX là cơ chế chuẩn của Java cho phép một JVM công bố các đối tượng quản trị gọi là MBean. MBean có thể cung cấp **attributes** để theo dõi hoặc điều chỉnh trạng thái, **operations** để thực hiện hành động, và **metadata** để công cụ quản trị hiểu hợp đồng.

Spring Framework hỗ trợ tích hợp JMX để ứng dụng có thể đăng ký các Spring-managed objects vào một `MBeanServer` mà không cần tự viết toàn bộ code `registerMBean`/unregister trong business logic.

Với Java Config, ta khai báo các thành phần bằng class `@Configuration` và các factory method `@Bean`:

```text
@Configuration
   |
   +-- @Bean -> Managed Spring object
   |
   +-- @Bean -> MBeanServer
   |
   +-- @Bean -> MBeanExporter
                    |
                    +-- setServer(MBeanServer)
                    +-- setBeans(ObjectName -> bean)
                    |
                    v
               JMX Registry
                    |
                    v
            JConsole / JMX client
```

Trong mô hình này, **Spring bean name** (ví dụ `jobMonitor`) và **JMX `ObjectName`** (ví dụ `com.example.jobs:type=JobMonitor,name=primary`) là hai không gian tên riêng. Exporter quyết định object nào xuất hiện ở JMX và với tên nào.

## 2. Các thư viện cần có

Spring JMX là một phần của Spring Framework. Với dự án Maven độc lập, `spring-context` cung cấp các thành phần IoC và hỗ trợ JMX liên quan. Ví dụ cấu trúc dependency:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
        <version>${spring.version}</version>
    </dependency>
</dependencies>
```

`spring.version` phải được định nghĩa theo bộ dependency quản lý trong dự án. Với Spring Boot, nên dùng dependency management/BOM của Boot thay vì tự chọn rời rạc phiên bản Spring Framework.

Các API JMX cốt lõi như `MBeanServer`, `ObjectName` thuộc JDK (`javax.management`). Trong Java 9+ chúng nằm trong module `java.management`. Các annotation Spring JMX nằm trong package `org.springframework.jmx.export.annotation`, không phải `javax.management`.

Không cần bật JMX remote để làm bài trong cùng JVM. JMX remote chỉ cần khi một client khác tiến trình/máy phải kết nối đến server qua connector; khi ấy còn phải cấu hình bảo mật và mạng.

## 3. Bước 1 — Khai báo Standard MBean

Tạo interface chuẩn của JMX. Quy ước Standard MBean yêu cầu interface quản lý có tên `<ImplementationClassName>MBean`.

**JobMonitorMBean.java**

```java
package com.example.jmx;

public interface JobMonitorMBean {
    int getProcessedCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void resetStatistics();
}
```

**JobMonitor.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger processed = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordProcessedJob() {
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
    public void resetStatistics() {
        processed.set(0);
    }
}
```

`JobMonitor` là một POJO có thể được Spring quản lý, đồng thời implement hợp đồng JMX thông qua `JobMonitorMBean`.

| Method | Phần tử JMX | Quyền truy cập |
| --- | --- | --- |
| `getProcessedCount()` | Attribute `ProcessedCount` | Read-only |
| `isEnabled()` và `setEnabled(boolean)` | Attribute `Enabled` | Read/write |
| `resetStatistics()` | Operation `resetStatistics` | Invoke |
| `recordProcessedJob()` | Không nằm trong Standard MBean interface | Chỉ là method nội bộ |

Không nên mở mọi method nghiệp vụ ra JMX. Hợp đồng quản trị nên nhỏ, có chủ đích và hạn chế operations có tác dụng phụ.

## 4. Bước 2 — Khai báo @Configuration, @Bean và MBeanExporter

Cấu hình tường minh dưới đây dùng platform `MBeanServer` của JVM và xuất đúng một Spring bean qua JMX.

**JmxConfiguration.java**

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
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
}
```

Các thành phần có vai trò riêng:

1. `jobMonitor()`: tạo instance mà nghiệp vụ và JMX sẽ cùng quản lý.
2. `platformMBeanServer()`: trả server có sẵn của JVM; Spring chỉ **dùng** server này chứ không sở hữu vòng đời của nó.
3. `jobMonitorExporter(...)`: tạo exporter, inject đúng object và server, rồi ánh xạ tên JMX tới instance.
4. `setServer(...)`: tránh mơ hồ khi có nhiều MBean servers.
5. `setBeans(...)`: chỉ định chính xác object nào được export và `ObjectName` mong muốn.

Khi `ApplicationContext` khởi tạo, `MBeanExporter` được Spring lifecycle quản lý và đăng ký MBean. Không cần gọi `ManagementFactory.getPlatformMBeanServer().registerMBean(...)` thủ công thêm lần nữa với cùng `ObjectName`; nếu làm như vậy sẽ có xung đột.

## 5. Bước 3 — Khởi chạy ApplicationContext

Có thể chạy bài thực hành trong ứng dụng Spring Framework thuần:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxDemoApplication {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            JobMonitor monitor = context.getBean(JobMonitor.class);
            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            System.out.println("Registered: " + server.isRegistered(name));

            monitor.recordProcessedJob();
            monitor.recordProcessedJob();

            System.out.println(
                    "ProcessedCount: "
                    + server.getAttribute(name, "ProcessedCount"));

            System.out.println("PID: " + ProcessHandle.current().pid());
            System.out.println("Press Enter to close context.");
            System.in.read();
        }
    }
}
```

Với cấu hình đúng, `Registered: true` và `ProcessedCount: 2`. Lời gọi `getAttribute` đi qua JMX registry, vì vậy kết quả chứng minh exporter đã đưa MBean vào server với tên mong đợi.

`System.in.read()` chỉ giúp giữ chương trình thử nghiệm chạy để mở JConsole. Trong web application/server thật, vòng đời được quản lý bởi runtime. Khi context đóng, exporter có thể unregister những MBeans mà nó đã đăng ký; điều này khác với giải phóng platform server của JVM.

## 6. Bước 4 — Kiểm tra trong JConsole

JConsole thường đi kèm JDK và hỗ trợ quan sát MBean của JVM local. Các bước:

1. Chạy `JmxDemoApplication`.
2. Mở `jconsole` từ JDK phù hợp.
3. Chọn đúng Java process theo PID vừa in.
4. Mở tab **MBeans**.
5. Tìm domain `com.example.jobs`.
6. Chọn MBean `type=JobMonitor,name=primary`.
7. Đọc `ProcessedCount`, `Enabled` và kiểm tra operation `resetStatistics`.
8. Trong môi trường thử nghiệm, thay `Enabled=false` hoặc invoke `resetStatistics`, rồi đối chiếu giá trị mới.

Mỗi JMX client có thể trình bày thứ tự key properties khác nhau, nhưng `ObjectName` vẫn xác định registration. Nếu không thấy MBean, kiểm tra đúng PID/JVM, server mà exporter dùng, context có còn chạy, và `isRegistered(name)` trước khi suy luận Java Config bị lỗi.

## 7. Cấu hình nhiều MBean trong Java Config

Một exporter có thể đăng ký nhiều bean dưới các tên riêng:

```java
@Bean("primaryJobMonitor")
public JobMonitor primaryJobMonitor() {
    return new JobMonitor();
}

@Bean("secondaryJobMonitor")
public JobMonitor secondaryJobMonitor() {
    return new JobMonitor();
}
```

Khi inject hai bean cùng type, dùng qualifier:

```java
@Bean
public MBeanExporter multiMonitorExporter(
        @org.springframework.beans.factory.annotation.Qualifier(
                "primaryJobMonitor") JobMonitor primary,
        @org.springframework.beans.factory.annotation.Qualifier(
                "secondaryJobMonitor") JobMonitor secondary,
        MBeanServer platformMBeanServer) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(platformMBeanServer);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary", primary,
            "com.example.jobs:type=JobMonitor,name=secondary", secondary));
    return exporter;
}
```

Đây là **một phương án thay thế** cấu hình `jobMonitorExporter` ở mục 4, không nên bật cả hai exporter cho cùng `ObjectName`. Hai Spring instances cùng Java class là hợp lệ; mỗi instance chỉ cần một `ObjectName` duy nhất trong cùng server.

Cả hai có thể dùng chung `JobMonitorMBean`, và JMX sẽ điều khiển đúng instance theo tên `primary` hoặc `secondary`. Tên bean Spring và tên JMX vẫn là hai không gian tên khác nhau.

## 8. RegistrationPolicy khi trùng ObjectName

Nếu một `ObjectName` đã tồn tại trong server, exporter cần chính sách xử lý. Spring Framework cung cấp `RegistrationPolicy` với các lựa chọn:

- `FAIL_ON_EXISTING`: báo lỗi khi tên đã được đăng ký.
- `IGNORE_EXISTING`: giữ MBean đã có, bỏ qua registration mới ở tên đó.
- `REPLACE_EXISTING`: thay registration cũ bằng MBean mới.

Trong Java Config:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING);
```

Lỗi tên trùng thường là dấu hiệu naming strategy hoặc lifecycle có vấn đề. Không nên chọn `IGNORE_EXISTING` để “làm startup chạy được” nếu thực tế cần công bố MBean mới: JMX client có thể vẫn đọc dữ liệu của instance cũ. Với `REPLACE_EXISTING`, cần hiểu owner của registration và tác động tới các công cụ đang quản trị.

Các phiên bản Spring cũ có thể dùng integer constants `REGISTRATION_FAIL_ON_EXISTING` và method cấu hình khác. Khi triển khai, chọn API phù hợp phiên bản dependency đang dùng.

## 9. Dùng @ManagedResource và @EnableMBeanExport thay cho interface *MBean

Spring cũng có **annotation-driven JMX exporting**. Thay vì implement interface `JobMonitorMBean`, một POJO có thể khai báo Spring JMX metadata:

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.jobs:type=AnnotatedJobMonitor,name=primary",
        description = "Managed job metrics")
public class AnnotatedJobMonitor {

    private final AtomicInteger processed = new AtomicInteger();

    @ManagedAttribute(description = "Processed job count")
    public int getProcessedCount() {
        return processed.get();
    }

    @ManagedOperation(description = "Reset processed counter")
    public void resetStatistics() {
        processed.set(0);
    }
}
```

Bật annotation exporting trong Java Config:

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "platformMBeanServer")
public class AnnotationJmxConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotatedJobMonitor annotatedJobMonitor() {
        return new AnnotatedJobMonitor();
    }
}
```

`@EnableMBeanExport` kích hoạt hỗ trợ export theo Spring JMX annotation. `@ManagedResource` đánh dấu bean là đối tượng quản lý; `@ManagedAttribute` và `@ManagedOperation` xác định các phần tử được công bố. Bản thân `@ManagedResource` không tạo Spring bean nếu class không được đăng ký qua `@Bean` hoặc component scanning phù hợp.

**Chỉ chọn một mô hình cho cùng tên JMX**: export tường minh bằng `MBeanExporter` hoặc annotation-based exporter. Nếu vô tình bật hai cơ chế cùng đăng ký một `ObjectName`, có thể gặp `InstanceAlreadyExistsException`.

## 10. Cấu hình JMX bằng Java Config với custom MBeanServer

Không bắt buộc dùng platform server. Spring có `MBeanServerFactoryBean` để tạo hoặc tìm server tùy biến:

```java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class CustomMBeanServerConfiguration {

    @Bean(name = "applicationMBeanServer")
    public MBeanServerFactoryBean applicationMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.management");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }
}
```

Nếu một exporter cần custom server, inject bean sản phẩm `MBeanServer` đó vào `setServer`. `MBeanServerFactoryBean` được container quản lý, vì vậy vòng đời của server do factory tạo có thể được xử lý qua callbacks khởi tạo và destroy.

Ví dụ exporter:

```java
@Bean
public MBeanExporter customExporter(
        JobMonitor monitor,
        @org.springframework.beans.factory.annotation.Qualifier(
                "applicationMBeanServer") MBeanServer server) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(
            "com.example.management:type=JobMonitor,name=custom", monitor));
    return exporter;
}
```

Cấu hình này là **biến thể của exporter trước đó**; không đăng ký cùng object/name lần hai nếu không có chủ đích. Một custom `MBeanServer` có registry riêng; JConsole local có thể đang quan sát platform server thay vì custom server. Khi cần client truy cập custom server, phải thiết kế kết nối/connector tương ứng.

## 11. Naming strategy và ObjectName

`ObjectName` có dạng:

```text
domain:key1=value1,key2=value2
```

Ví dụ:

```text
com.example.jobs:type=JobMonitor,name=primary
com.example.jobs:type=JobMonitor,name=secondary
com.example.db:type=PoolMonitor,pool=read
```

Spring có các cơ chế naming strategy như `KeyNamingStrategy`, `MetadataNamingStrategy` và `IdentityNamingStrategy`, tùy cách exporter được cấu hình. Khi dùng `setBeans(Map.of("fullObjectName", bean))`, ta kiểm soát tên rõ ràng, phù hợp để học và debug.

Trong hệ thống lớn, naming convention nên chứa domain, type và key phân biệt từng instance để tránh trùng. Các giá trị `ObjectName` có ký tự đặc biệt phải được quote/escape theo chuẩn JMX. Không đưa bí mật hoặc thông tin nhạy cảm vào tên hiển thị.

Nếu muốn dashboard giám sát ổn định, tránh phụ thuộc vào object identity ngẫu nhiên thay đổi sau mỗi lần khởi động, trừ khi đó là yêu cầu thực sự.

## 12. Đảm bảo cùng Spring bean được xuất qua JMX

Một lỗi thường gặp là Spring service dùng một instance nhưng exporter đăng ký instance khác:

```java
@Bean
public MBeanExporter wrongExporter(MBeanServer server) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary",
            new JobMonitor())); // Instance mới, không phải bean nghiệp vụ.
    return exporter;
}
```

Cấu hình có thể đăng ký MBean hợp lệ nhưng số đếm trong JConsole không phản ánh luồng xử lý thực. Cách đúng là inject chính bean mà business service dùng:

```java
@Bean
public MBeanExporter correctExporter(
        JobMonitor monitor,
        MBeanServer server) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary", monitor));
    return exporter;
}
```

Khi nhiều bean cùng Java type, dùng `@Qualifier` để chỉ đúng instance. Một `ObjectName` đúng nhưng trỏ nhầm object cũng là lỗi chức năng, vì client nhận một nguồn dữ liệu không như dự kiến.

## 13. Vòng đời ApplicationContext và cleanup

`MBeanExporter` là một Spring bean có các lifecycle callbacks. Khi context khởi tạo, exporter đăng ký MBeans. Khi context đóng bình thường, nó unregister những registration mà mình quản lý.

```text
ApplicationContext refresh
    |
    +-- JobMonitor Spring bean
    +-- MBeanServer
    +-- MBeanExporter.register
    |
Ứng dụng đang chạy
    |
ApplicationContext close
    |
    +-- MBeanExporter.unregister
    +-- Destroy các bean còn lại
```

Không nên dùng một static MBean registration độc lập không có cleanup nếu ứng dụng có thể reload context nhiều lần trong cùng JVM. Những registration còn sót có thể khiến lần khởi tạo mới gặp tên trùng hoặc client tiếp tục đọc instance cũ.

Platform `MBeanServer` thuộc JVM nên không bị giải phóng chỉ vì một context đóng. Nếu Spring dùng custom server do factory bean tạo, owner server cần quản lý release theo vòng đời; exporter phải có cơ hội unregister trước khi server bị giải phóng.

## 14. Spring AOP proxy và JMX exporter

Spring beans có thể được bao quanh bởi AOP proxy vì `@Transactional`, security hoặc logging aspects. Khi export bean đó, cần xác định object nào thực sự được MBean exporter đăng ký và metadata nào được dùng để dựng management interface.

Không nên mặc định lời gọi JMX luôn đi qua toàn bộ advice hoặc luôn bypass advice. Behavior phụ thuộc việc exporter đăng ký proxy Spring hay target object và cách introspection được cấu hình. Với hệ thống có proxy động, hãy kiểm tra MBean metadata và hành vi runtime.

Nếu cần một management interface ổn định, có thể tạo một management facade riêng:

```java
public class JobAdminFacade {
    private final JobService jobService;

    public JobAdminFacade(JobService jobService) {
        this.jobService = jobService;
    }

    public long getProcessedCount() {
        return jobService.getProcessedCount();
    }
}
```

Sau đó dùng phù hợp giữa Standard MBean, assembler hoặc Spring JMX annotations để công bố chỉ những method quản trị mong muốn. Một facade quản trị giúp giảm rủi ro phơi bày các method nghiệp vụ nhạy cảm.

## 15. Kiểm tra qua MBeanInfo và các operation

Đọc metadata từ server để xác nhận exporter đã công bố đúng interface:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = context.getBean(MBeanServer.class);
ObjectName name = new ObjectName(
        "com.example.jobs:type=JobMonitor,name=primary");

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean is not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

for (var attribute : info.getAttributes()) {
    System.out.println(
            "Attribute: " + attribute.getName()
            + " / " + attribute.getType());
}

for (var operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
```

Đoạn mã giả định có sẵn biến `context` thuộc kiểu `ApplicationContext` phù hợp. `isRegistered` chứng minh tên có trong registry; `getMBeanInfo` chứng minh metadata mà JMX server đang công bố. Khi cần xác minh đúng instance, hãy đọc một attribute nhận diện hoặc so sánh hành vi sau khi thay đổi trạng thái của bean được inject.

Nếu có một MBean khác đã đăng ký dưới cùng `ObjectName` từ trước và exporter dùng policy ignore/replace, chỉ kiểm tra `isRegistered` chưa đủ để kết luận bean mới chính là target.

## 16. JUnit integration test cho Java Config

Một bài test tích hợp nên tạo `ApplicationContext` thật và đọc JMX registry:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class JmxConfigurationTest {

    @Test
    void exportsJobMonitorWithExpectedAttributes() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            JobMonitor monitor = context.getBean(JobMonitor.class);
            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            assertTrue(server.isRegistered(name));

            monitor.recordProcessedJob();
            assertEquals(
                    1, server.getAttribute(name, "ProcessedCount"));

            server.invoke(
                    name,
                    "resetStatistics",
                    new Object[0],
                    new String[0]);

            assertEquals(
                    0, server.getAttribute(name, "ProcessedCount"));
        }
    }
}
```

Trong một test suite chạy song song, dùng chung platform `MBeanServer` và cùng `ObjectName` có thể tạo xung đột. Cần cô lập server test hoặc dùng domain/tên riêng cho mỗi fixture. Test cũng phải đóng context để exporter cleanup.

Bài kiểm thử chứng minh cả việc đăng ký, đọc attribute và invoke operation; đó là kiểm thử tích hợp đường Java Config → exporter → JMX registry, thay vì chỉ kiểm tra class có `@Configuration`.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Spring context có bean nhưng JConsole không thấy | Chưa có exporter, sai `ObjectName`, sai JVM/server | Kiểm tra `isRegistered` trên đúng server |
| `InstanceAlreadyExistsException` | Trùng tên JMX giữa các exporter/context | Sử dụng tên duy nhất và một owner rõ ràng |
| `NotCompliantMBeanException` | Standard MBean interface hoặc kiểu không tuân thủ JMX | Kiểm tra `JobMonitor implements JobMonitorMBean` |
| Số đếm khác giữa service và JMX | Exporter đăng ký instance khác với bean nghiệp vụ | Inject cùng bean vào exporter |
| Attribute thiếu | Interface/annotation/assembler không công bố method | Đọc `MBeanInfo` và kiểm tra metadata |
| Cấu hình `@EnableMBeanExport` nhưng không thấy bean | Bean chưa nằm trong context hoặc không có metadata quản lý phù hợp | Kiểm tra `@ManagedResource` và exporter |
| MBean biến mất khi đóng context | Exporter unregister theo lifecycle | Xác minh context vẫn sống |
| Hai bean cùng type gây inject ambiguity | Không có qualifier | Dùng `@Qualifier` hoặc tên bean cụ thể |
| Custom server không xuất hiện trong JConsole local | JConsole nhìn platform server | Kết nối đúng custom server hoặc dùng API trực tiếp |
| Chỉ chạy test suite mới lỗi | Tests chia sẻ server/tên | Cô lập fixture, cleanup context |

## 18. Bảo mật JMX và quản lý operation

JMX có thể công bố operations thay đổi trạng thái: `resetStatistics`, `clearCache`, `reloadRules`, `pauseQueue` hoặc `shutdown`. Java Config chỉ quyết định registration và metadata; nó **không tự cấp** một lớp phân quyền chi tiết cho mọi operation.

Khi dùng trong production:

1. Công bố tối thiểu những attributes/operations cần thiết.
2. Không đưa secret hoặc dữ liệu khách hàng vào thuộc tính JMX.
3. Kiểm tra điều kiện trước khi thực hiện operation có side effect.
4. Bảo vệ remote JMX bằng xác thực, mã hóa và giới hạn network.
5. Ghi log/metrics phù hợp để xác định operation đã chạy và trạng thái sau đó.
6. Không retry mù operation không idempotent khi kết nối bị gián đoạn.
7. Thiết kế `ObjectName` ổn định nhưng không chứa thông tin nhạy cảm.

Với ứng dụng chỉ cần metric/health, có thể cân nhắc cách quan sát phù hợp khác. JMX vẫn hữu ích khi cần quản trị trực tiếp các JVM MBeans trong cùng process hoặc thông qua JMX client tương thích.

## 19. Bài tập thực hành

**Bài 1 — Standard MBean bằng Java Config.** Tạo `CacheMonitorMBean` và `CacheMonitor`, export theo `com.example.cache:type=CacheMonitor,name=primary`. Xác minh `CacheSize` bằng JConsole và `MBeanServer.getAttribute`.

**Bài 2 — Nhiều instance.** Tạo hai beans `primaryCacheMonitor` và `secondaryCacheMonitor` cùng class. Dùng một `MBeanExporter` đăng ký hai `ObjectName` phân biệt; xác nhận thay đổi instance này không ảnh hưởng instance kia.

**Bài 3 — Annotation exporting.** Tạo class có `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, rồi bật `@EnableMBeanExport`. So sánh metadata của annotation-based MBean với Standard MBean ở bài 1.

**Bài 4 — Xử lý xung đột.** Cố tình dùng hai exporters cùng `ObjectName` trong môi trường test. Quan sát lỗi rồi sửa bằng naming strategy rõ ràng, thay vì chọn ignore nếu cần hai MBeans.

**Bài 5 — Vòng đời.** Đọc `isRegistered(name)` trước và sau `ApplicationContext.close()`. Giải thích khác biệt giữa cleanup registration và vòng đời platform MBean server.

**Bài 6 — Proxy local.** Thêm `MBeanProxyFactoryBean` truy cập một MBean đã export. So sánh lời gọi qua local proxy với gọi trực tiếp Spring bean theo đường xử lý và metadata.

## Kết luận

Cấu hình JMX bằng Java Config trong Spring Framework giúp đưa đối tượng Spring ra JMX registry thông qua `@Configuration`, `@Bean`, `MBeanServer` và `MBeanExporter`, hoặc qua annotation support như `@EnableMBeanExport`. Mô hình tường minh dùng **bean → ObjectName → exporter → MBeanServer** để kiểm soát instance nào được công bố. Mô hình annotation dùng metadata `@ManagedResource` và các annotation quản trị để chọn interface hiển thị. Dù chọn cách nào, hãy xác minh registration qua `MBeanServer`, quản lý lifecycle rõ ràng, tránh tên trùng và bảo vệ operations có tác dụng phụ.
