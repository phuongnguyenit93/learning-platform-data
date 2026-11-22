# Thực hành: Export một bean Spring bằng MBeanExporter

## 1. Mục tiêu bài thực hành

Trong bài này, bạn sẽ xây dựng một ứng dụng Spring Framework nhỏ, tạo một bean Java đại diện cho bộ xử lý công việc, dùng **`MBeanExporter`** công bố bean đó thành **JMX MBean** và quan sát bằng `MBeanServer`, JConsole hoặc một Java JMX client.

Sau khi hoàn tất, bạn có thể:

- Giải thích vai trò của `MBeanExporter`, `MBeanServer`, `ObjectName`, `MBeanInfo` và các JMX annotations của Spring.
- Tạo một Spring bean có attribute đọc được, attribute ghi được và operation quản trị an toàn.
- Cấu hình `MBeanExporter` tường minh trong Java `@Configuration` để export đúng một bean, không cần mở remote JMX.
- Sử dụng `AnnotationJmxAttributeSource`, `MetadataMBeanInfoAssembler` và `MetadataNamingStrategy` cho annotation-based export.
- Khởi động `ApplicationContext`, tìm MBean bằng `isRegistered`, đọc attribute và gọi operation.
- Đối chiếu runtime `MBeanInfo` để biết bean đã công bố những gì và kiểm tra API nội bộ không bị phơi bày.
- Nhận diện các lỗi như trùng `ObjectName`, sai server, thiếu metadata hoặc method signature không khớp.
- Viết bài test lifecycle để xác minh MBean được unregister sau khi đóng context.

**Phạm vi:** Lab local trong một JVM, dùng platform `MBeanServer`; không yêu cầu remote RMI connector, tài khoản JMX hay thay đổi firewall. Các operation sẽ không xóa dữ liệu hay truy cập dịch vụ production.

## 2. Kiến trúc bạn sẽ xây dựng

```text
Java application (một JVM)
   |
   +-- Spring ApplicationContext
   |       |
   |       +-- JobController bean
   |       |      +-- getQueueDepth()
   |       |      +-- getMaxWorkers()
   |       |      +-- setMaxWorkers(int)
   |       |      +-- requestPause()
   |       |
   |       +-- MBeanExporter bean
   |              |
   |              +-- AnnotationJmxAttributeSource
   |              +-- MetadataMBeanInfoAssembler
   |              +-- MetadataNamingStrategy
   |              |
   |              v
   +-- Platform MBeanServer
             |
             +-- com.example.lab:type=Worker,name=Importer
             |
             +-- JConsole hoặc Java client
```

`MBeanExporter` là cầu nối giữa bean được Spring quản lý và cơ chế đăng ký JMX. `ObjectName` định danh MBean trong một `MBeanServer`; `MBeanInfo` mô tả attributes/operations mà client thực sự thấy. Không có yêu cầu bean phải tự mở socket hoặc tự chạy HTTP server.

## 3. Điều kiện chuẩn bị

Bạn cần:

- JDK có module `java.management` và công cụ quan sát như `jconsole` (thường đi kèm JDK).
- Maven hoặc công cụ build Java tương đương.
- Spring Framework, đặc biệt `spring-context` và các module phụ thuộc liên quan JMX.
- IDE hoặc terminal để chạy Java application.
- Môi trường lab không chứa dữ liệu nhạy cảm.

Ví dụ sử dụng **Java 17+** và một phiên bản Spring Framework 6.x tương thích với JDK dự án. Nếu đang sử dụng Spring Framework 7 hoặc Spring Boot 4, cần kiểm tra phiên bản Java/dependency tương ứng; code minh họa dựa trên các API JMX Spring có tên như trong bài.

### 3.1. Maven tối thiểu

File `pom.xml` tham khảo:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>spring-jmx-export-lab</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>6.2.0</spring.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context-support</artifactId>
      <version>${spring.version}</version>
    </dependency>
  </dependencies>
</project>
```

Phiên bản trên chỉ làm ví dụ cấu hình để học; khi triển khai hãy dùng một release Spring được tổ chức hỗ trợ và quản lý nhất quán bằng BOM/dependency management. Trong một ứng dụng Spring Boot, thường không cần tự khai báo các thư viện này riêng nếu starter phù hợp đã mang theo chúng.

## 4. Xác định hợp đồng quản trị trước khi code

Trong lab, một worker quản lý hàng đợi import có các thông tin sau:

| Thành phần | Kiểu | Truy cập | Ý nghĩa |
| --- | --- | --- | --- |
| `QueueDepth` | `long` | Đọc | Số việc đang chờ. |
| `MaxWorkers` | `int` | Đọc/ghi | Giới hạn concurrency từ 1 đến 16. |
| `Running` | `boolean` | Đọc | Worker đang ở trạng thái chạy hay không. |
| `requestPause()` | `void` operation | Điều khiển | Yêu cầu tạm dừng một cách an toàn. |

`MaxWorkers` được giới hạn tại setter vì việc cho phép client gán một số tùy ý là nguy hiểm. `requestPause()` chỉ cập nhật trạng thái trong lab; với ứng dụng thực tế, nó phải giao việc cho một service có lifecycle, authorization và audit phù hợp.

ObjectName cố định:

```text
com.example.lab:type=Worker,name=Importer
```

Không đưa password, token, email khách hàng hoặc payload động vào ObjectName.

## 5. Bước 1 — Tạo bean được Spring quản lý

Tạo file `src/main/java/com/example/lab/JobController.java`:

```java
package com.example.lab;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.lab:type=Worker,name=Importer",
    description = "Importer worker management"
)
public final class JobController {

    private final AtomicLong queueDepth = new AtomicLong(12);
    private final AtomicInteger maxWorkers = new AtomicInteger(4);
    private final AtomicBoolean running = new AtomicBoolean(true);

    @ManagedAttribute(description = "Queued jobs (count)")
    public long getQueueDepth() {
        return queueDepth.get();
    }

    @ManagedAttribute(description = "Maximum parallel workers")
    public int getMaxWorkers() {
        return maxWorkers.get();
    }

    @ManagedAttribute(description = "Set maximum parallel workers")
    public void setMaxWorkers(int value) {
        if (value < 1 || value > 16) {
            throw new IllegalArgumentException(
                "maxWorkers must be between 1 and 16"
            );
        }
        maxWorkers.set(value);
    }

    @ManagedAttribute(description = "Whether worker is running")
    public boolean isRunning() {
        return running.get();
    }

    @ManagedOperation(
        description = "Request a graceful pause of importer"
    )
    public void requestPause() {
        running.set(false);
    }

    public void eraseInternalState() {
        // Không phải một JMX operation được định nghĩa trong lab.
    }
}
```

**Điểm cần lưu ý:** `@ManagedResource` xác định metadata cấp resource; `@ManagedAttribute` mô tả getter/setter; `@ManagedOperation` công bố operation. Các annotations chỉ có hiệu quả khi exporter dùng nguồn metadata tương ứng.

### 5.1. Vì sao dùng AtomicLong/AtomicInteger/AtomicBoolean?

JMX client có thể đọc hoặc ghi trạng thái đồng thời với thread khác. Các kiểu atomic giúp minh họa khả năng đọc/ghi thread-safe đối với các trường đơn giản. Chúng **không** thay thế thiết kế đồng bộ của một job processing system thực tế, nhưng thích hợp cho một lab JMX nhỏ.

### 5.2. Vì sao không đặt annotation lên mọi public method?

Management API cần được thiết kế như một hợp đồng có chủ đích. Method `eraseInternalState()` tồn tại để bạn kiểm tra rằng metadata assembler phù hợp **không** tự công bố mọi public method khi chỉ định annotation-based exposure.

## 6. Bước 2 — Cấu hình MBeanExporter

Tạo file `src/main/java/com/example/lab/JmxLabConfig.java`:

```java
package com.example.lab;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxLabConfig {

    @Bean
    public JobController jobController() {
        return new JobController();
    }

    @Bean
    public MBeanServer jmxMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy strategy =
            new MetadataNamingStrategy();
        strategy.setAttributeSource(source);
        return strategy;
    }

    @Bean
    public MBeanExporter jmxExporter(
            MBeanServer jmxMBeanServer,
            JobController jobController,
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(jmxMBeanServer);
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setBeans(Map.of(
            "jobController", jobController
        ));
        return exporter;
    }
}
```

Đây là cấu hình **explicit**: một bean `JobController` được export theo metadata và đặt tên bằng naming strategy, sử dụng platform MBeanServer. Không cần bật `@EnableMBeanExport` đồng thời, vì lab đã tạo exporter theo cách thủ công.

### 6.1. Từng thành phần làm gì?

| Thành phần | Nhiệm vụ |
| --- | --- |
| `MBeanServer` | Registry và dispatcher thực tế cho JMX. |
| `AnnotationJmxAttributeSource` | Đọc metadata từ annotations JMX của Spring. |
| `MetadataMBeanInfoAssembler` | Xây dựng `MBeanInfo` dựa trên metadata đã đọc. |
| `MetadataNamingStrategy` | Tạo ObjectName từ metadata của resource. |
| `MBeanExporter` | Đăng ký resource vào MBeanServer khi Spring context khởi tạo. |
| `setBeans(Map.of(...))` | Chỉ định bean cần export, không phụ thuộc autodetection. |

Với một ứng dụng khác, bạn có thể cấu hình `MBeanExporter` bằng bean name hoặc thông qua annotation-based configuration. Nhưng trong lab nên giữ một đường rõ để dễ chẩn đoán.

## 7. Bước 3 — Khởi động ApplicationContext

Tạo file `src/main/java/com/example/lab/App.java`:

```java
package com.example.lab;

import java.lang.management.ManagementFactory;
import java.util.concurrent.TimeUnit;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class App {
    public static void main(String[] args) throws Exception {
        ObjectName objectName = new ObjectName(
            "com.example.lab:type=Worker,name=Importer"
        );

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxLabConfig.class)) {

            System.out.println(
                "MBean registered: "
                    + server.isRegistered(objectName)
            );

            MBeanInfo info = server.getMBeanInfo(objectName);
            System.out.println(
                "MBean description: " + info.getDescription()
            );

            System.out.println(
                "Initial queue depth: "
                    + server.getAttribute(objectName, "QueueDepth")
            );

            System.out.println(
                "Initial running: "
                    + server.getAttribute(objectName, "Running")
            );

            System.out.println("Open JConsole to inspect this JVM.");
            TimeUnit.SECONDS.sleep(60);
        }

        System.out.println(
            "MBean registered after close: "
                + server.isRegistered(objectName)
        );
    }
}
```

Trong 60 giây giữ context mở, bạn có thể dùng JConsole để xem và thao tác với bean. Khoảng đợi chỉ phục vụ lab, không phải cách vận hành production. Khi đóng context, exporter sẽ thực hiện cleanup cho MBean do nó đăng ký theo lifecycle.

### 7.1. Kết quả minh họa

```text
MBean registered: true
MBean description: Importer worker management
Initial queue depth: 12
Initial running: true
Open JConsole to inspect this JVM.
...
MBean registered after close: false
```

Giá trị cụ thể có thể thay đổi nếu bạn tương tác với MBean trong lúc chạy. Nếu `MBean registered: false`, đừng chỉ đổi ObjectName tùy ý; hãy kiểm tra exporter, metadata source và server đích.

## 8. Bước 4 — Tìm MBean trong JConsole

1. Chạy ứng dụng từ IDE hoặc terminal.
2. Mở `jconsole` từ JDK trên cùng máy.
3. Chọn đúng JVM/PID đang chạy `com.example.lab.App` trong danh sách Local Process.
4. Mở tab **MBeans**.
5. Tìm domain `com.example.lab`.
6. Mở các key properties `type=Worker` và `name=Importer` theo cách hiển thị của JConsole.
7. Kiểm tra phần **Attributes** và **Operations**.

Kỳ vọng:

```text
com.example.lab
  type=Worker
    name=Importer
      Attributes
        QueueDepth = 12
        MaxWorkers = 4
        Running = true
      Operations
        requestPause()
```

Đừng lo nếu cấu trúc cây trên JConsole hơi khác do cách JConsole sắp xếp key properties. Giá trị `ObjectName` chính xác mới là định danh JMX.

### 8.1. Thử đọc attribute

Chọn `QueueDepth`; JConsole có thể hiển thị giá trị `12`. Đây là attribute read-only.

### 8.2. Thử ghi attribute

Chọn `MaxWorkers`, thay giá trị từ `4` sang `8` bằng giao diện của JConsole nếu được hỗ trợ. Sau đó đọc lại, dự kiến `8`.

Nếu thử `MaxWorkers=100`, setter sẽ từ chối bằng `IllegalArgumentException` do vượt phạm vi. Tùy loại MBean và connector, exception có thể được bọc trong JMX wrapper và hiển thị thành thông báo lỗi.

### 8.3. Thử gọi operation

Gọi `requestPause()` ở tab Operations. Sau đó đọc lại `Running`, dự kiến là `false`. Lab này không có worker thật; operation chỉ đổi flag để minh họa.

**Không thực hiện thao tác tương tự trên production MBean có operation như `shutdown()`, `clearAll()` hoặc `dropCache()` nếu chưa được cho phép.**

## 9. Bước 5 — Kiểm tra trực tiếp bằng MBeanServer

Nếu không dùng được JConsole, bạn vẫn có thể tạo Java JMX client trong cùng JVM:

```java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.lab:type=Worker,name=Importer"
);

boolean exists = server.isRegistered(name);
System.out.println("Registered: " + exists);

Object depth = server.getAttribute(name, "QueueDepth");
System.out.println("Depth: " + depth);

server.setAttribute(
    name,
    new Attribute("MaxWorkers", 8)
);

server.invoke(
    name,
    "requestPause",
    new Object[0],
    new String[0]
);

System.out.println(
    "Running after pause: "
        + server.getAttribute(name, "Running")
);
```

`ObjectName` phải đúng theo exporter đã đăng ký. Nếu exporter dùng custom `MBeanServer` thay vì platform server, đoạn ví dụ phải được sửa để truy vấn đúng server ấy.

## 10. Bước 6 — Đọc MBeanInfo và xác minh metadata

Chỉ nhìn thấy MBean trong JConsole chưa đủ. Bạn cần kiểm tra hợp đồng thực tế:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(info.getDescription());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s, type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation=%s, return=%s, parameters=%d%n",
        operation.getName(),
        operation.getReturnType(),
        operation.getSignature().length
    );
}
```

Kỳ vọng về metadata:

| Thành phần | Loại | Đọc | Ghi |
| --- | --- | --- | --- |
| `QueueDepth` | `long` | Có | Không |
| `MaxWorkers` | `int` | Có | Có |
| `Running` | `boolean` | Có | Không |
| `requestPause` | `void` operation | N/A | N/A |

Quan trọng: `eraseInternalState()` **không** được công bố khi cấu hình annotation metadata đúng. Nếu nó xuất hiện, hãy kiểm tra assembler và exposure policy đang dùng.

### 10.1. Metadata không phải phân quyền

`MBeanAttributeInfo.isWritable()` cho biết thuộc tính có setter được công bố, **không** nói rằng một tài khoản JMX cụ thể được phép ghi. Một connector readonly vẫn có thể không cho setAttribute dù metadata writable.

Với remote JMX, security là lớp riêng và cần được kiểm tra bằng client authenticated thực tế.

## 11. Bước 7 — Viết integration test

Một test có thể khởi tạo context, kiểm tra MBeanInfo, thao tác bằng MBeanServer và đảm bảo cleanup:

```java
package com.example.lab;

import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class MBeanExportIntegrationTest {

    @Test
    void exportsBeanAndUnregistersOnClose() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.lab:type=Worker,name=Importer"
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxLabConfig.class)) {

            assertTrue(server.isRegistered(name));
            assertEquals(
                12L,
                server.getAttribute(name, "QueueDepth")
            );

            server.setAttribute(
                name, new Attribute("MaxWorkers", 8)
            );
            assertEquals(
                8,
                server.getAttribute(name, "MaxWorkers")
            );

            server.invoke(
                name, "requestPause",
                new Object[0], new String[0]
            );
            assertEquals(
                false,
                server.getAttribute(name, "Running")
            );

            boolean hidden = java.util.Arrays.stream(
                server.getMBeanInfo(name).getOperations()
            ).anyMatch(op ->
                "eraseInternalState".equals(op.getName()));
            assertFalse(hidden);
        }

        assertFalse(server.isRegistered(name));
    }
}
```

Test này cần dependency JUnit Jupiter phù hợp. Nếu các test khác chạy cùng JVM, cần cẩn thận khi dùng một `ObjectName` cố định: chạy song song nhiều contexts có thể gây `InstanceAlreadyExistsException`. Dùng ObjectName riêng theo test hoặc cấu hình test isolation.

### 11.1. Không chỉ test bằng lời gọi trực tiếp bean

```java
JobController controller = context.getBean(JobController.class);
controller.requestPause();
```

Đoạn trên chứng minh logic Java hoạt động nhưng **không** chứng minh exporter đã đăng ký hay JMX dispatch đúng. Một integration test JMX phải gọi qua `MBeanServer` và đọc metadata thực tế.

## 12. Hiểu vòng đời đăng ký và hủy đăng ký

Spring `MBeanExporter` đăng ký MBean trong quá trình khởi tạo container/exporter theo lifecycle framework. Khi context đóng đúng cách, exporter dọn những MBean do nó quản lý.

```text
ApplicationContext.refresh()
        |
        v
MBeanExporter initialized
        |
        v
MBeanServer.registerMBean(...)
        |
        v
JConsole / client can inspect
        |
        v
ApplicationContext.close()
        |
        v
MBeanExporter cleanup
        |
        v
MBean no longer registered
```

Với JVM bị kill cứng, cleanup callback Java không có bảo đảm chạy. Tuy nhiên registry nằm trong JVM đó cũng kết thúc cùng tiến trình. Với các test cùng JVM, context không được đóng có thể làm MBean cũ tồn tại, gây xung đột cho test sau.

## 13. Vì sao chọn exporter tường minh thay autodetect?

`MBeanExporter` có nhiều cách xác định bean cần xuất:

- Map bean tường minh qua `setBeans(...)`.
- Tự phát hiện theo interface quản trị hoặc assembler/autodetection.
- Cấu hình annotation-driven qua Spring context.

Trong bài thực hành đầu tiên, map tường minh có các lợi ích:

1. Dễ xác định đúng bean được export.
2. Dễ thấy exporter đang quản lý bean nào.
3. Hạn chế rủi ro công bố các bean không dự định.
4. Dễ chẩn đoán `ObjectName` trùng.
5. Không phụ thuộc cách autodetection quét toàn context.

Khi nâng cấp ứng dụng, có thể cân nhắc annotation-based autodetect để giảm cấu hình, nhưng phải viết kiểm thử hợp đồng MBeanInfo và bảo mật exposure.

## 14. So sánh với @EnableMBeanExport

Spring cũng hỗ trợ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class AnnotationDrivenJmxConfig {
}
```

Đường annotation-driven có thể tạo/cấu hình exporter qua infrastructure của Spring. **Không cần thêm nó vào lab đang dùng `MBeanExporter` tường minh** nếu cả hai có thể đăng ký cùng `ObjectName`.

Trong Spring Boot, auto-configuration với `spring.jmx.enabled` cũng có thể tạo exporter tùy phiên bản/cấu hình. Nếu tạo exporter thủ công, cần xác định ownership và tránh duplicate registration.

## 15. RegistrationPolicy và ObjectName trùng

Nếu ObjectName đã có trong cùng `MBeanServer`, cố đăng ký lần nữa có thể gây:

```text
javax.management.InstanceAlreadyExistsException:
com.example.lab:type=Worker,name=Importer
```

Spring cung cấp `RegistrationPolicy` như `FAIL_ON_EXISTING`, `IGNORE_EXISTING` và `REPLACE_EXISTING` để quy định hành vi khi tên đã tồn tại.

Ví dụ:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

Trong lab, chính sách fail khi trùng giúp phát hiện cấu hình sai. Đừng đổi sang `REPLACE_EXISTING` để che xung đột mà chưa xác định MBean hiện tại thuộc thành phần nào. `IGNORE_EXISTING` cũng có thể khiến test tưởng đăng ký thành công khi thực ra chỉ đang quan sát MBean cũ.

### 15.1. Những nguồn gây trùng

- Hai Spring contexts dùng chung platform MBeanServer.
- Hai exporters cùng export một bean.
- Code đăng ký trực tiếp qua JMX API trước Spring.
- Test trước chưa đóng context.
- Nhiều module dùng chung domain/type/name.
- Spring Boot auto-exporter tồn tại cùng exporter thủ công.

Giải pháp đúng là xác định owner và naming convention, không chỉ đổi registration policy.

## 16. Lỗi thường gặp khi export

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `isRegistered=false` | Exporter chưa khởi tạo hoặc ObjectName sai. | Kiểm tra context, naming strategy, đúng server. |
| `InstanceAlreadyExistsException` | MBean trùng tên. | Đóng context cũ, một owner cho tên. |
| `MalformedObjectNameException` | Tên chứa ký tự đặc biệt không quote đúng. | Sử dụng `ObjectName` hợp lệ. |
| `NotCompliantMBeanException` | Bean không tuân JMX convention hoặc adapter không phù hợp. | Kiểm tra assembler/metadata và loại MBean. |
| `ReflectionException` khi invoke | Operation name/signature không đúng. | Đọc `MBeanInfo.getOperations()`. |
| `AttributeNotFoundException` | Attribute không được công bố hoặc sai tên. | Kiểm tra `MBeanInfo.getAttributes()`. |
| Attribute không writable | Setter không export hoặc bị security policy chặn. | Kiểm tra metadata và quyền connector. |
| JConsole không thấy app | Kết nối nhầm JVM hoặc app đã kết thúc. | Kiểm tra PID, giữ context sống trong lab. |
| Operation xuất method nội bộ | Assembler/exposure không phải allowlist như dự định. | Kiểm tra `MetadataMBeanInfoAssembler`. |
| MBean vẫn tồn tại sau test | Context chưa đóng hoặc owner không rõ. | Cleanup theo lifecycle, kiểm tra registry. |

## 17. Đọc log khi export thất bại

Để chẩn đoán có thể tăng log level package Spring JMX trong môi trường lab:

```properties
logging.level.org.springframework.jmx=DEBUG
logging.level.org.springframework.jmx.export=DEBUG
```

Các property trên là cú pháp Spring Boot logging; với Spring Framework thuần, bạn cần cấu hình backend logging tương ứng. Không có bảo đảm mọi phiên bản Spring phát cùng thông điệp log. Đọc exception cause chain và quan sát registry là nguồn dữ liệu quan trọng hơn một dòng log cụ thể.

Ví dụ nếu `BeanCreationException` bọc `MBeanExportException` và bên trong có `InstanceAlreadyExistsException`, nguyên nhân gần gốc có thể là xung đột ObjectName, không phải thiếu bean.

## 18. JMX local không cần remote port

Trong lab, mọi thứ nằm trong một JVM và bạn dùng:

```java
ManagementFactory.getPlatformMBeanServer()
```

Vì vậy không cần:

```text
-Dcom.sun.management.jmxremote.port=9010
```

`MBeanExporter` không tự mở cổng remote JMX. Nếu muốn kết nối từ máy khác, bạn phải cấu hình connector/JVM management agent riêng, cùng authentication, TLS, firewall và RMI hostname/port phù hợp. Không mở remote JMX không xác thực ra môi trường công khai.

## 19. Nâng cấp bài lab: MBeanServer riêng

Trong một test integration phức tạp, có thể tạo `MBeanServer` cô lập để giảm va chạm với platform registry:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer isolated =
    MBeanServerFactory.createMBeanServer("com.example.lab");
```

Sau đó inject server này vào `MBeanExporter` và test client. Nếu dùng custom server, JConsole local platform connection có thể không tự hiển thị MBean ở custom server theo cách giống platform server. Cần kết nối qua server/connector phù hợp.

Đảm bảo release/cleanup những tài nguyên test tạo và không vô tình giữ reference khiến test leak.

## 20. Nâng cấp bài lab: MBeanExporterListener

Spring có `MBeanExporterListener` để theo dõi những MBean được exporter đăng ký/hủy đăng ký:

```java
import javax.management.ObjectName;
import org.springframework.jmx.export.MBeanExporterListener;

public final class LoggingRegistrationListener
        implements MBeanExporterListener {

    @Override
    public void mbeanRegistered(ObjectName name) {
        System.out.println("Registered: " + name);
    }

    @Override
    public void mbeanUnregistered(ObjectName name) {
        System.out.println("Unregistered: " + name);
    }
}
```

Gắn listener:

```java
exporter.setListeners(
    new LoggingRegistrationListener()
);
```

Listener giúp quan sát lifecycle thành công, nhưng không có callback chuẩn nhận mọi exception đăng ký thất bại. Với failure, vẫn phải đọc exception/log của exporter.

## 21. Mở rộng: tác động của AOP proxy

Trong ứng dụng thực tế, bean có thể được Spring AOP proxy do `@Transactional`, `@Async` hoặc aspect khác. Khi MBeanExporter/assembler introspect proxy, metadata có thể phụ thuộc cách nó truy xuất target class và management interface.

Để tránh phụ thuộc phức tạp cho API quản trị:

- Tạo management adapter riêng, có `@ManagedResource` và operations được chọn.
- Adapter inject service interface/proxy được Spring quản lý.
- Giữ method quản trị ngắn và kiểm soát side effect.
- Test `MBeanInfo` runtime sau khi AOP được bật.
- Không dùng runtime proxy class name làm ObjectName.

Trong bài lab cơ bản, `JobController` không có AOP nên đường export dễ theo dõi. Bài nâng cao có thể thử service proxy và so sánh metadata.

## 22. Bảo mật khi viết management API

Một MBean có thể cung cấp các operation ảnh hưởng lớn tới JVM. Vì vậy:

1. **Chỉ công bố API cần thiết**, không export tùy ý mọi public method.
2. **Ưu tiên attribute read-only** cho monitoring.
3. **Validate setter/operation arguments**; không tin dữ liệu client.
4. **Không trả thông tin bí mật** qua attributes hoặc ObjectName.
5. **Không để operation dài block thread JMX**; dùng request ID + async job khi cần.
6. **Bảo vệ remote connector** bằng authentication, authorization, TLS và mạng quản trị.
7. **Audit thao tác có side effect** với danh tính đáng tin cậy.
8. **Kiểm tra MBeanInfo** để bảo đảm method nội bộ không bị lộ.

Không coi annotation `@ManagedOperation` là một authorization rule. Nó chỉ xác định metadata công bố operation.

## 23. Tự đánh giá bài lab

Bạn có thể tự trả lời các câu hỏi:

**1. `MBeanExporter` làm gì?** Chọn bean và đăng ký dưới dạng MBean trong một MBeanServer.

**2. Tại sao `@ManagedResource` chưa đủ nếu không có exporter?** Vì metadata annotation tự nó không thực hiện đăng ký vào registry.

**3. `ObjectName` dùng để làm gì?** Định danh duy nhất một MBean trong cùng MBeanServer.

**4. Vì sao dùng `MetadataMBeanInfoAssembler`?** Để xây MBeanInfo dựa trên metadata của annotations được nguồn attribute đọc.

**5. Tại sao phải đọc `MBeanInfo`?** Để biết attributes, operations, signatures và khả năng đọc/ghi thực tế.

**6. Tại sao `MaxWorkers` cần validation?** Vì client JMX có thể truyền giá trị bất hợp lý và gây ảnh hưởng tài nguyên.

**7. Vì sao không nên thấy `eraseInternalState` trong Operations?** Vì đó là method nội bộ không được phép xuất.

**8. Nếu exporter đăng ký MBean vào custom server, lấy platform server có tìm thấy không?** Không nhất thiết; phải kiểm tra đúng server.

**9. Khi context đóng, điều gì xảy ra với MBean do exporter quản lý?** Exporter thực hiện unregistration theo lifecycle.

**10. Tại sao không nên dùng `REPLACE_EXISTING` để làm mất lỗi trùng tên?** Vì có thể vô tình thay thế MBean của thành phần khác.

## 24. Bài tập mở rộng

### Bài tập A — Thêm operation có tham số

Thêm:

```java
@ManagedOperation(description = "Adjust queue depth for lab")
public void setQueueDepthForLab(long value) {
    if (value < 0 || value > 1000) {
        throw new IllegalArgumentException(
            "Queue depth out of lab range"
        );
    }
    queueDepth.set(value);
}
```

Kiểm tra `MBeanInfo` signature là `long`; khi gọi `MBeanServer.invoke`, truyền mảng signature `new String[] {"long"}` thay vì `java.lang.Long`.

### Bài tập B — Thêm metadata cho tham số

Đặt `@ManagedOperationParameters` và `@ManagedOperationParameter` để mô tả `value`. Kiểm tra thông tin trong `MBeanOperationInfo.getSignature()` sau export.

### Bài tập C — Thêm listener

Gắn `MBeanExporterListener`, ghi log khi đăng ký/hủy đăng ký và xác nhận callback xảy ra trong lifecycle.

### Bài tập D — Test xung đột

Đăng ký trước một MBean cùng ObjectName trong một MBeanServer cô lập. Thử exporter với `FAIL_ON_EXISTING` và quan sát exception, sau đó cleanup chắc chắn.

### Bài tập E — Đổi kiểu MBean

Tạo một Standard MBean qua `JobControllerMBean` interface. So sánh sự khác nhau giữa Standard MBean convention và Spring metadata-based Model MBean bằng `MBeanInfo`.

## 25. Tổng kết

Bạn đã học cách **export một Spring bean thành JMX MBean bằng `MBeanExporter`**: định nghĩa resource, attributes và operation bằng annotations; cấu hình metadata source, assembler và naming strategy; chọn platform MBeanServer; đăng ký một bean cụ thể; quan sát qua JConsole và kiểm tra bằng JMX API.

Điểm cốt lõi là **không dừng ở việc ApplicationContext khởi động thành công**. Hãy kiểm tra `ObjectName` đã đăng ký, đọc `MBeanInfo`, thử những thao tác an toàn trong lab, xác nhận API nội bộ không bị lộ và kiểm tra unregistration khi context đóng. Trong ứng dụng thực tế, quản lý exporter ownership, bảo vệ remote JMX, giới hạn operation side effects và duy trì integration tests.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `ManagedResource`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — `MetadataMBeanInfoAssembler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — `MetadataNamingStrategy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html