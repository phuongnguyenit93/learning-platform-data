# Spring Framework JMX: Xuất bean đã là MBean và bean thường qua assembler

## 1. Bài toán

Spring Framework có thể đưa Spring bean vào hệ thống quản trị JMX thông qua \`MBeanExporter\`. Tuy nhiên không phải bean nào cũng có cùng hình dạng:

1. **Bean đã là JMX MBean**: đối tượng đã đáp ứng một hợp đồng JMX, ví dụ Standard MBean (\`WorkerControlMBean\`) hoặc \`DynamicMBean\`.
2. **Bean Java/Spring thông thường**: một POJO không triển khai interface MBean. Muốn quản trị qua JMX, Spring cần xác định phương thức/thuộc tính nào được công bố và có thể sử dụng **\`MBeanInfoAssembler\`** cùng ModelMBean adapter để tạo bề mặt JMX.

Cùng một exporter có thể xử lý cả hai, nhưng ý nghĩa của thao tác export khác nhau. Với bean đã là MBean, hợp đồng JMX chủ yếu được định nghĩa bởi chính bean. Với bean thường, assembler quyết định những thuộc tính/operation nào được đưa ra cho client.

\`\`\`text
Spring ApplicationContext
        |
        +-- Standard MBean / DynamicMBean
        |       |
        |       +-- MBeanExporter -> MBeanServer
        |                              |
        +-- POJO Spring bean            |
                |                       |
                +-- MBeanInfoAssembler  |
                        |               |
                        +-- ModelMBean -+
                                        |
                              JConsole / JMX client
\`\`\`

Điểm chung là kết quả cuối cùng được **đăng ký dưới một \`ObjectName\` trong \`MBeanServer\`**. Khác biệt là **bề mặt quản trị được lấy từ đâu**.

## 2. Thuật ngữ cần nắm

| Thành phần | Vai trò |
|---|---|
| \`MBeanServer\` | Registry và điểm truy cập đọc/ghi attribute, gọi operation, nhận notification |
| \`ObjectName\` | Định danh MBean trong server, ví dụ \`com.example:type=Worker,name=primary\` |
| \`MBeanExporter\` | Spring component nhận bean và đăng ký dưới ObjectName |
| \`Standard MBean\` | Đối tượng theo quy ước Java JMX, ví dụ class \`Worker\` triển khai \`WorkerMBean\` |
| \`DynamicMBean\` | MBean tự cung cấp metadata và cơ chế đọc/ghi/gọi qua API động |
| \`ModelMBean\` | MBean có metadata mô tả các attribute/operation được expose; Spring có thể sử dụng để bọc POJO |
| \`MBeanInfoAssembler\` | Thành phần Spring tạo \`ModelMBeanInfo\` từ bean và cấu hình |
| \`MetadataMBeanInfoAssembler\` | Assembler dùng metadata annotation JMX của Spring |
| \`MethodNameBasedMBeanInfoAssembler\` | Assembler chọn phương thức dựa trên danh sách tên |
| \`InterfaceBasedMBeanInfoAssembler\` | Assembler chỉ công bố những thành viên trong interface chỉ định |

**Export không có nghĩa toàn bộ public API đều được mở ra JMX.** Với bean đã là MBean, giao diện MBean/metadata quyết định. Với POJO, assembler và cấu hình exporter quyết định.

## 3. Cách 1: Export một bean đã là Standard MBean

Java JMX có convention Standard MBean: class \`WorkerControl\` triển khai interface \`WorkerControlMBean\`, trong đó các getter/setter và method định nghĩa hợp đồng quản trị.

### 3.1. Định nghĩa interface quản trị

\`\`\`java
package com.example.jmx;

public interface WorkerControlMBean {
    int getMaxThreads();
    void setMaxThreads(int maxThreads);
    boolean isRunning();
    long getProcessedCount();
    void resetCounters();
}
\`\`\`

### 3.2. Triển khai Standard MBean

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class WorkerControl implements WorkerControlMBean {
    private volatile int maxThreads = 8;
    private volatile boolean running = true;
    private final AtomicLong processedCount = new AtomicLong();

    @Override
    public int getMaxThreads() {
        return maxThreads;
    }

    @Override
    public void setMaxThreads(int maxThreads) {
        if (maxThreads < 1 || maxThreads > 64) {
            throw new IllegalArgumentException("maxThreads must be 1..64");
        }
        this.maxThreads = maxThreads;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public long getProcessedCount() {
        return processedCount.get();
    }

    @Override
    public void resetCounters() {
        processedCount.set(0L);
    }

    // Không thuộc interface MBean, nên không tự động là operation JMX.
    public void internalMaintenance() {
        // ...
    }
}
\`\`\`

Theo convention này, JMX nhìn thấy:

- Attribute \`MaxThreads\`: readable và writable, kiểu \`int\`.
- Attribute \`Running\`: read-only, kiểu \`boolean\`.
- Attribute \`ProcessedCount\`: read-only, kiểu \`long\`.
- Operation \`resetCounters()\`.
- \`internalMaintenance()\` không nằm trong \`WorkerControlMBean\` nên không trở thành operation chỉ vì đó là public method.

Với dữ liệu nhạy cảm, không nên đặt phương thức quản trị trong interface MBean nếu client không được phép sử dụng.

### 3.3. Export qua Spring MBeanExporter

\`\`\`java
package com.example.jmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ExistingMBeanConfig {

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public MBeanExporter existingMBeanExporter(
            WorkerControl workerControl) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl
        ));
        return exporter;
    }
}
\`\`\`

\`setBeans\` tạo mapping từ tên JMX sang bean được đăng ký. Với bean tuân thủ quy tắc Standard MBean, exporter có thể đăng ký nó dưới ObjectName đã cung cấp. Không cần assembler để **phát minh thêm** giao diện JMX cho bean đã có MBean contract.

Mã này giả định ứng dụng không còn cấu hình một exporter khác tự động export cùng bean; trong Spring Boot hoặc context dùng \`@EnableMBeanExport\`, cần xác định rõ ai sở hữu registration để tránh trùng ObjectName.

### 3.4. Xác minh qua API chuẩn

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName target = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);

if (!server.isRegistered(target)) {
    throw new IllegalStateException("MBean chưa được đăng ký");
}

MBeanInfo info = server.getMBeanInfo(target);
for (var attribute : info.getAttributes()) {
    System.out.printf(
        "%s (%s), read=%s, write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

Trong ứng dụng thực, exporter có thể dùng MBeanServer được cấu hình thay vì platform server mặc định. Để readback chính xác, lấy cùng \`MBeanServer\` mà exporter đang sử dụng; ví dụ trên minh họa trường hợp hai bên dùng platform MBeanServer.

## 4. Cách 2: Export bean đã là DynamicMBean

Một \`DynamicMBean\` không dựa vào convention interface tên \`XxxMBean\`. Nó tự cung cấp:

- \`getMBeanInfo()\`: metadata động.
- \`getAttribute\` và \`setAttribute\`: đường đọc/ghi.
- \`getAttributes\` và \`setAttributes\`: thao tác theo danh sách.
- \`invoke\`: gọi operation.

Ví dụ tối thiểu cho một MBean có attribute \`Enabled\`:

\`\`\`java
package com.example.jmx;

import javax.management.*;

public class FeatureFlagDynamicMBean implements DynamicMBean {
    private boolean enabled = true;

    @Override
    public Object getAttribute(String name)
            throws AttributeNotFoundException {
        if ("Enabled".equals(name)) {
            return enabled;
        }
        throw new AttributeNotFoundException(name);
    }

    @Override
    public void setAttribute(Attribute attribute)
            throws AttributeNotFoundException,
                   InvalidAttributeValueException {
        if (attribute == null ||
            !"Enabled".equals(attribute.getName())) {
            throw new AttributeNotFoundException(
                attribute == null ? "null" : attribute.getName()
            );
        }
        if (!(attribute.getValue() instanceof Boolean value)) {
            throw new InvalidAttributeValueException(
                "Enabled must be Boolean"
            );
        }
        enabled = value;
    }

    @Override
    public AttributeList getAttributes(String[] names) {
        AttributeList result = new AttributeList();
        for (String name : names) {
            try {
                result.add(new Attribute(name, getAttribute(name)));
            } catch (Exception ignored) {
                // Ví dụ tối giản; thực tế cần logging phù hợp.
            }
        }
        return result;
    }

    @Override
    public AttributeList setAttributes(AttributeList updates) {
        AttributeList result = new AttributeList();
        for (Object raw : updates) {
            Attribute attribute = (Attribute) raw;
            try {
                setAttribute(attribute);
                result.add(new Attribute(
                    attribute.getName(),
                    getAttribute(attribute.getName())
                ));
            } catch (Exception ignored) {
                // Ví dụ tối giản; thực tế cần logging phù hợp.
            }
        }
        return result;
    }

    @Override
    public Object invoke(
            String action,
            Object[] params,
            String[] signature)
            throws ReflectionException {
        throw new ReflectionException(
            new NoSuchMethodException(action)
        );
    }

    @Override
    public MBeanInfo getMBeanInfo() {
        MBeanAttributeInfo enabledInfo =
            new MBeanAttributeInfo(
                "Enabled",
                "boolean",
                "Feature flag runtime state",
                true,
                true,
                true
            );
        return new MBeanInfo(
            getClass().getName(),
            "Example DynamicMBean",
            new MBeanAttributeInfo[] { enabledInfo },
            null,
            new MBeanOperationInfo[0],
            new MBeanNotificationInfo[0]
        );
    }
}
\`\`\`

Bean này có hợp đồng quản trị riêng, nên \`MBeanExporter\` có thể nhận mapping \`ObjectName -> FeatureFlagDynamicMBean\` mà không cần xác định metadata của bean qua một assembler POJO.

**Lưu ý:** các exception từ \`DynamicMBean\` cần theo đúng hợp đồng \`javax.management.DynamicMBean\`; ví dụ chỉ minh họa một attribute. Với hệ thống lớn, triển khai \`DynamicMBean\` thủ công có thể tốn công hơn sử dụng Standard MBean hoặc Spring assembler.

## 5. Cách 3: Export Spring POJO thông qua assembler

Giờ xét một bean Java bình thường, không triển khai \`SomethingMBean\` và không triển khai \`DynamicMBean\`.

\`\`\`java
package com.example.jmx;

public class JobCoordinator {
    private volatile int maxParallelJobs = 4;
    private volatile boolean paused = false;

    public int getMaxParallelJobs() {
        return maxParallelJobs;
    }

    public void setMaxParallelJobs(int value) {
        if (value < 1 || value > 32) {
            throw new IllegalArgumentException("value must be 1..32");
        }
        maxParallelJobs = value;
    }

    public boolean isPaused() {
        return paused;
    }

    public void pause() {
        paused = true;
    }

    public void resume() {
        paused = false;
    }

    public String internalDebugSnapshot() {
        return "not for JMX";
    }
}
\`\`\`

Không có interface \`JobCoordinatorMBean\`. Nếu exporter cần expose bean này, Spring sử dụng ModelMBean adapter và \`MBeanInfoAssembler\` để chọn thành viên quản trị.

**Assembler là bộ chọn metadata, không phải phép biến mọi method thành MBean operation tự động.** Thông tin do assembler tạo có thể quy định getter, setter, operation, mô tả và các đặc tính khác tùy implementation.

### 5.1. Export POJO qua MethodNameBasedMBeanInfoAssembler

Ví dụ muốn chỉ expose:

- \`getMaxParallelJobs\` và \`setMaxParallelJobs\` thành attribute đọc/ghi.
- \`isPaused\` thành attribute chỉ đọc.
- \`pause\`, \`resume\` thành operations.
- **Không expose** \`internalDebugSnapshot\`.

\`\`\`java
package com.example.jmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class OrdinaryBeanExportConfig {

    @Bean
    public JobCoordinator jobCoordinator() {
        return new JobCoordinator();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler jobAssembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();

        assembler.setManagedMethods(
            "getMaxParallelJobs",
            "setMaxParallelJobs",
            "isPaused",
            "pause",
            "resume"
        );
        return assembler;
    }

    @Bean
    public MBeanExporter jobMBeanExporter(
            JobCoordinator jobCoordinator,
            MethodNameBasedMBeanInfoAssembler jobAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.app:type=JobCoordinator,name=default",
            jobCoordinator
        ));
        exporter.setAssembler(jobAssembler);
        return exporter;
    }
}
\`\`\`

Khi exporter tạo ModelMBean từ POJO, assembler mô tả các member JMX có thể truy cập. \`internalDebugSnapshot\` không nằm trong danh sách nên không phải public operation do assembler này chọn.

Cần phân biệt **method được đưa vào metadata** và **method chỉ có trong class Java**. Phương thức public bình thường không tự động trở thành operation trong ví dụ này.

### 5.2. Các loại assembler thường gặp

| Assembler | Cách quyết định thành viên | Phù hợp khi |
|---|---|---|
| \`SimpleReflectiveMBeanInfoAssembler\` | Dựa trên phản chiếu nhiều phương thức public | Demo hoặc môi trường kiểm soát nghiêm ngặt, tránh mở rộng API ngoài ý muốn |
| \`MethodNameBasedMBeanInfoAssembler\` | Chọn bằng danh sách tên method | Có ít bean, muốn whitelist cụ thể |
| \`MethodExclusionMBeanInfoAssembler\` | Loại những phương thức trong danh sách | Khi bề mặt phần lớn được phép expose nhưng cần chặn một số method |
| \`InterfaceBasedMBeanInfoAssembler\` | Chọn method dựa vào interface được chỉ định | Muốn quản trị theo hợp đồng Java tách riêng |
| \`MetadataMBeanInfoAssembler\` | Lấy metadata từ annotation hoặc metadata source | Muốn mô tả theo annotation JMX của Spring |

Với hệ thống production, whitelist rõ ràng thường dễ kiểm soát hơn việc mở tất cả public methods. Dùng reflection hoặc exclusion cần cân nhắc tương lai khi class được thêm một public method mới.

## 6. InterfaceBasedMBeanInfoAssembler: hợp đồng quản trị của POJO

Một bean thường có thể triển khai interface nghiệp vụ dành cho JMX **mà không cần tuân thủ convention Standard MBean về tên interface**. Interface đó chỉ được dùng như danh sách phương thức cho assembler.

Ví dụ:

\`\`\`java
package com.example.jmx;

public interface JobOperations {
    int getMaxParallelJobs();
    void setMaxParallelJobs(int value);
    boolean isPaused();
    void pause();
    void resume();
}
\`\`\`

\`\`\`java
package com.example.jmx;

public class JobCoordinator implements JobOperations {
    private int maxParallelJobs = 4;
    private boolean paused = false;

    @Override public int getMaxParallelJobs() {
        return maxParallelJobs;
    }

    @Override public void setMaxParallelJobs(int value) {
        maxParallelJobs = value;
    }

    @Override public boolean isPaused() {
        return paused;
    }

    @Override public void pause() {
        paused = true;
    }

    @Override public void resume() {
        paused = false;
    }

    public void clearAllProductionData() {
        // Không thuộc JobOperations; không export.
    }
}
\`\`\`

Cấu hình assembler:

\`\`\`java
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;

@Bean
InterfaceBasedMBeanInfoAssembler interfaceAssembler() {
    InterfaceBasedMBeanInfoAssembler assembler =
        new InterfaceBasedMBeanInfoAssembler();
    assembler.setManagedInterfaces(JobOperations.class);
    return assembler;
}
\`\`\`

Sau đó truyền vào \`exporter.setAssembler(interfaceAssembler)\` và đăng ký bean vào mapping như ví dụ trước.

Khác biệt quan trọng:

- Với **Standard MBean**, interface tên \`JobCoordinatorMBean\` theo convention JMX được Java/JMX dùng trực tiếp để xác định contract.
- Với **InterfaceBasedMBeanInfoAssembler**, Spring chủ động đọc interface bạn chỉ định để tạo ModelMBean metadata cho bean thường. Tên interface không nhất thiết phải theo mẫu \`ClassNameMBean\`.

Phương thức không nằm trong interface quản trị sẽ không được assembler này công bố chỉ vì là public Java method. Với các proxy/AOP và method resolution, cần kiểm tra proxy thực tế có phương thức mà ModelMBean sẽ gọi.

## 7. MetadataMBeanInfoAssembler và annotation của Spring

Spring có nhóm annotation JMX trong package:

\`\`\`text
org.springframework.jmx.export.annotation
\`\`\`

Ví dụ:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=JobCoordinator,name=annotation",
    description = "Controls jobs at runtime"
)
public class AnnotatedJobCoordinator {
    private volatile int maxParallelJobs = 4;

    @ManagedAttribute(description = "Maximum concurrent jobs")
    public int getMaxParallelJobs() {
        return maxParallelJobs;
    }

    @ManagedAttribute(description = "Changes maximum concurrent jobs")
    public void setMaxParallelJobs(int value) {
        if (value < 1 || value > 32) {
            throw new IllegalArgumentException("Expected 1..32");
        }
        maxParallelJobs = value;
    }

    @ManagedOperation(description = "Pauses job intake")
    public void pause() {
        // ...
    }

    public void dangerousInternalMethod() {
        // Không được công bố khi chỉ chọn annotated members.
    }
}
\`\`\`

Bên cạnh đó, \`MetadataMBeanInfoAssembler\` cần một \`JmxAttributeSource\` để đọc annotation metadata. \`AnnotationJmxAttributeSource\` là implementation phổ biến:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
MetadataMBeanInfoAssembler annotationAssembler(
        AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler =
        new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}
\`\`\`

Trong cấu hình thường gặp, \`@EnableMBeanExport\` có thể tự đăng ký các thành phần annotation-export cần thiết. Không nên cấu hình đồng thời nhiều exporter quét cùng bean mà không có ý đồ rõ ràng, vì dẫn tới registration trùng hoặc naming không nhất quán.

### Annotation không đồng nghĩa interface MBean

\`@ManagedResource\` không làm class trở thành Standard MBean theo convention Java. Spring cần assembler/exporter thích hợp để tạo đối tượng quản trị. Khi JConsole nhìn thấy MBean đã export, nó giao tiếp qua JMX chuẩn mà không biết hoặc không cần biết bean gốc là POJO của Spring.

## 8. Một MBeanExporter với cả Standard MBean và POJO

Có thể cấu hình cùng exporter để export hai kiểu bean nếu application cần quản trị chúng dưới một namespace. Ví dụ:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class CombinedJmxConfig {

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public JobCoordinator jobCoordinator() {
        return new JobCoordinator();
    }

    @Bean
    public MBeanExporter combinedExporter(
            WorkerControl workerControl,
            JobCoordinator jobCoordinator) {

        MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();
        assembler.setManagedMethods(
            "getMaxParallelJobs",
            "setMaxParallelJobs",
            "isPaused",
            "pause",
            "resume"
        );

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl,
            "com.example.app:type=JobCoordinator,name=default",
            jobCoordinator
        ));
        return exporter;
    }
}
\`\`\`

Ở đây \`WorkerControl\` là Standard MBean và \`JobCoordinator\` là POJO. Exporter có thể phân biệt bean đã đáp ứng hợp đồng MBean và bean cần adapter. Assembler được cấu hình để mô tả POJO; **không được hiểu rằng assembler có thể tùy tiện biến contract Standard MBean thành danh sách methods mới**.

Khi sử dụng một assembler cho nhiều bean POJO khác nhau, hãy tránh dùng một danh sách method chung mà chỉ phù hợp với một class. Có thể dùng assembler hỗ trợ cấu hình theo bean key, annotation hoặc tách cấu hình nếu các contract quản trị khác nhau.

## 9. Xác nhận bằng MBeanInfo: nguồn sự thật của client JMX

Những gì client có thể làm được được mô tả bởi \`MBeanInfo\` mà MBeanServer trả về. Dù code gốc là Standard MBean hay POJO, client nên khám phá MBean theo cùng một cách.

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

static void inspect(MBeanServer server, ObjectName name)
        throws Exception {

    MBeanInfo info = server.getMBeanInfo(name);

    System.out.println("MBean: " + name);
    System.out.println("Class: " + info.getClassName());

    for (MBeanAttributeInfo attribute : info.getAttributes()) {
        System.out.printf(
            "attribute=%s, type=%s, readable=%s, writable=%s%n",
            attribute.getName(),
            attribute.getType(),
            attribute.isReadable(),
            attribute.isWritable()
        );
    }

    for (MBeanOperationInfo operation : info.getOperations()) {
        System.out.print("operation=" + operation.getName() + "(");
        var params = operation.getSignature();
        for (int i = 0; i < params.length; i++) {
            if (i > 0) System.out.print(", ");
            System.out.print(params[i].getType());
        }
        System.out.println(")");
    }
}
\`\`\`

Ví dụ gọi:

\`\`\`java
ObjectName worker = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);
ObjectName coordinator = new ObjectName(
    "com.example.app:type=JobCoordinator,name=default"
);

inspect(server, worker);
inspect(server, coordinator);
\`\`\`

Sau đó client có thể đọc thuộc tính và gọi operation theo metadata:

\`\`\`java
int threads = (Integer) server.getAttribute(
    worker, "MaxThreads"
);

server.setAttribute(
    coordinator,
    new javax.management.Attribute("MaxParallelJobs", 6)
);

server.invoke(
    coordinator,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

Dù hai loại bean được export theo cách khác nhau, client vẫn dùng chung JMX API. Đây là mục tiêu của cơ chế MBean exporter và ModelMBean adapter.

## 10. Mapping ObjectName và NamingStrategy

\`MBeanExporter\` cần xác định ObjectName cho mỗi bean. Có thể cung cấp tên cụ thể trong \`setBeans\`, hoặc cấu hình naming strategy để tạo tên nhất quán.

Ví dụ mapping tường minh:

\`\`\`java
exporter.setBeans(Map.of(
    "com.example.app:type=WorkerControl,name=primary", workerControl,
    "com.example.app:type=JobCoordinator,name=default", jobCoordinator
));
\`\`\`

Với hệ thống nhiều instance, khóa \`name\` hoặc \`instance\` cần đảm bảo hai bean cùng loại trong một MBeanServer có ObjectName khác nhau. Hai JVM khác nhau có registry riêng, nên có thể sử dụng cùng tên logic mà không trực tiếp xung đột.

Nếu cần \`ObjectNamingStrategy\`, có thể tạo theo bean key trong context:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class ApplicationNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey) throws MalformedObjectNameException {

        String safeKey = beanKey.replaceAll(
            "[^a-zA-Z0-9._-]", "_"
        );

        return new ObjectName(
            "com.example.app:type=ManagedBean,name=" + safeKey
        );
    }
}
\`\`\`

Đây là minh họa chiến lược; trong production cần xử lý collision khi hai bean key khác nhau được normalize thành cùng giá trị. Nên dùng một naming contract ổn định và xác thực giá trị key thay vì tự động thay ký tự không kiểm soát.

## 11. Lỗi thường gặp khi export hai kiểu bean

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| \`NotCompliantMBeanException\` | MBean không tuân thủ Standard/Dynamic MBean convention và không được bọc phù hợp | Kiểm tra interface \`XxxMBean\` hoặc cấu hình assembler |
| \`InstanceAlreadyExistsException\` | Hai bean được đăng ký với cùng ObjectName | Kiểm tra mapping, auto-export và exporter trùng |
| POJO export nhưng thiếu attribute | Assembler không chọn getter/setter hoặc metadata không đúng | Xem \`MBeanInfo\`, whitelist methods, annotation |
| Operation nội bộ bị expose | Assembler quá rộng, ví dụ reflection mở public methods | Chuyển sang whitelist/interface/annotation |
| Client gọi operation bị lỗi tên | Client dùng Java method name nhưng MBean metadata khác | Lấy \`MBeanOperationInfo\` từ server |
| Ghi attribute thất bại | Attribute chỉ đọc hoặc kiểu giá trị không khớp | Xem \`isWritable()\` và \`getType()\` |
| Proxy/AOP gây khác biệt | Method của proxy không khớp metadata hoặc target | Kiểm tra bean thực tế, proxy interface và exporter |
| MBean biến mất khi context shutdown | Exporter unregister khi bean/context bị hủy | Theo dõi Spring lifecycle và MBeanServer |
| Gọi sai MBeanServer | Exporter và client dùng hai server khác nhau | So sánh server được inject/cấu hình |
| Annotation không có tác dụng | Chưa có annotation assembler hoặc \`@EnableMBeanExport\` tương ứng | Kiểm tra \`MetadataMBeanInfoAssembler\` và source |

Các exception và cách Spring bọc chúng có thể khác theo Spring version, loại MBean và thời điểm lỗi. Bảng chỉ là đường định hướng; cần kiểm tra cause chain và log runtime.

### Vấn đề double-registration

Nếu một class vừa được annotate \`@ManagedResource\`, vừa được đưa vào \`setBeans\`, và còn được auto-detect bởi exporter khác, có thể xảy ra nhiều nỗ lực export cùng MBean. Điều này cần giải quyết bằng cấu hình rõ ràng về **ai là chủ thể duy nhất sở hữu registration**, không đơn giản đổi ObjectName để che triệu chứng trùng.

## 12. Lựa chọn assembler theo mục tiêu

Một số quy tắc lựa chọn:

**Sẵn có Standard MBean interface**

Dùng contract Standard MBean đó nếu phù hợp. Không cần biến nó thành POJO export chỉ vì ứng dụng sử dụng Spring.

**Bean thường chỉ có vài method quản trị**

Dùng \`MethodNameBasedMBeanInfoAssembler\` để chọn chính xác những method cần thiết.

**Bean thường có interface quản trị riêng**

Dùng \`InterfaceBasedMBeanInfoAssembler\` để giữ contract độc lập với implementation, đặc biệt khi nhiều implementation cần cùng giao diện.

**Bean có annotation JMX**

Dùng annotation exporter/metadata assembler của Spring và chỉ annotate thành viên có chủ đích.

**Bean chứa nhiều method nội bộ/nhạy cảm**

Ưu tiên whitelist, interface hoặc annotation. Không dùng assembler phản chiếu toàn bộ public methods mặc định nếu có nguy cơ expose method nội bộ.

**Muốn dynamic metadata cao**

Cân nhắc \`DynamicMBean\` khi metadata thực sự thay đổi động và cần điều khiển toàn bộ JMX contract; đổi lại implementation phức tạp hơn và phải xử lý API JMX trực tiếp.

## 13. Kiểm soát bảo mật và vòng đời

Export một bean đồng nghĩa tạo bề mặt quản trị runtime. Những thông tin được expose qua JMX có thể rất nhạy cảm, đặc biệt nếu có quyền ghi attribute hoặc invoke operation.

- Chỉ expose phương thức cần thiết; assembler là một lớp kiểm soát bề mặt API.
- Xác thực input ở setter/operation, kể cả khi client JConsole hiển thị type hợp lệ.
- Không expose getter trả token, password, thông tin cá nhân hay internal secrets.
- Hạn chế JMX remote bằng authentication, authorization và bảo vệ transport.
- Khi context dừng, exporter nên unregister các MBean do nó quản lý theo vòng đời của Spring.
- Với nhiều application context dùng chung server, đặt tên có namespace rõ và xác định ownership.
- Ghi audit cho thao tác quản trị thay đổi trạng thái, nhưng không log dữ liệu nhạy cảm.

Một writable attribute qua JMX thường thay đổi state đang chạy; nó không tự persist cấu hình qua restart. Nếu muốn duy trì, service cần cơ chế lưu giá trị riêng.

## 14. Bài thực hành

### Bài 1: Nhận diện đường export

Cho hai bean:

\`\`\`java
class A implements AMBean { /* ... */ }
class B { public int getCount() { return 0; } }
\`\`\`

\`A\` có thể được export theo Standard MBean contract nếu interface và method hợp lệ. \`B\` không phải Standard MBean; muốn chọn \`Count\` làm JMX attribute qua Spring nên dùng assembler hoặc annotation export phù hợp.

### Bài 2: Vì sao assembler không thấy method?

Bean \`JobCoordinator\` có \`resetCounters()\` nhưng assembler chỉ quản lý \`getMaxParallelJobs\`, \`setMaxParallelJobs\`, \`pause\`, \`resume\`.

Phương thức \`resetCounters\` sẽ không được assembler đó chọn để công bố. Nếu muốn expose, thêm tên vào whitelist hoặc annotation/interface theo hợp đồng quản trị.

### Bài 3: Chẩn đoán trùng ObjectName

Hai Spring contexts cùng platform MBeanServer export:

\`\`\`text
com.example.app:type=WorkerControl,name=default
\`\`\`

Hai registration không thể cùng tồn tại với ObjectName này trong một server. Cần phân biệt \`context\`, \`name\` hoặc một key có ý nghĩa khác; đồng thời kiểm tra có đang export trùng cùng bean không.

### Bài 4: So sánh interface MBean và interface assembler

Giải thích sự khác biệt giữa:

\`\`\`java
class Worker implements WorkerMBean
\`\`\`

và

\`\`\`java
class Worker implements WorkerOperations
\`\`\`

trong đó \`WorkerOperations\` được đưa vào \`InterfaceBasedMBeanInfoAssembler\`.

Trường hợp đầu theo convention của Java JMX; trường hợp sau dùng Spring assembler để tạo ModelMBean metadata từ interface đã chọn.

### Bài 5: Lỗi \`ClassCastException\` phía client

MBean attribute \`ProcessedCount\` có kiểu \`long\`; client viết:

\`\`\`java
Integer count = (Integer) server.getAttribute(name, "ProcessedCount");
\`\`\`

Client sai kiểu ép dữ liệu; kết quả được trả thường là \`Long\`. Kiểm tra \`MBeanAttributeInfo.getType()\` và cast phù hợp.

### Bài 6: Export nhầm method nguy hiểm

Một service có \`deleteAllRecords()\` public. Nếu dùng assembler phản chiếu quá rộng, operation đó có thể trở thành bề mặt JMX. Hướng giải quyết là chuyển sang whitelist/interface/annotation giới hạn phương thức quản trị và kiểm tra \`MBeanInfo\` thực tế.

## 15. Ghi nhớ

Với **bean đã là MBean**, Spring \`MBeanExporter\` chủ yếu làm nhiệm vụ **đăng ký** đối tượng theo JMX contract có sẵn. Với **bean Java/Spring thông thường**, Spring dùng **assembler và ModelMBean adapter** để xác định bề mặt quản trị muốn công bố.

Hai đường export khác nhau nhưng hội tụ về một giao diện client thống nhất: \`MBeanServer\`, \`ObjectName\`, \`getAttribute\`, \`setAttribute\` và \`invoke\`. Thiết kế tốt bắt đầu từ hợp đồng quản trị nhỏ, ổn định, có tên rõ ràng, chỉ mở những thành viên thực sự phục vụ vận hành và xác nhận kết quả bằng \`MBeanInfo\` của MBean đã đăng ký.