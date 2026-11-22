# Attribute hoặc operation không xuất hiện trong MBeanInfo: chẩn đoán Spring Framework JMX

## 1. Hiện tượng và mục tiêu

Spring Framework có thể xuất bean thành MBean thông qua `MBeanExporter`, sử dụng Standard MBean, MXBean, `DynamicMBean` hoặc `ModelMBean` được xây dựng từ metadata. Người vận hành truy cập bằng JConsole, VisualVM hoặc JMX client và đọc `MBeanInfo` để biết MBean đang công bố những gì.

Một lỗi quen thuộc: **MBean được đăng ký và hiển thị đúng ObjectName nhưng thuộc tính hoặc thao tác mong muốn lại không nằm trong `MBeanInfo`**. Ví dụ class Java có `getQueueDepth()`, `pause()`, thậm chí đặt `@ManagedAttribute` và `@ManagedOperation`, nhưng tool chỉ thấy một vài thuộc tính hoặc operation khác.

Mục tiêu của quy trình này là tìm đúng tầng gây thiếu metadata:

- Đang xem **đúng MBeanServer và ObjectName** chưa?
- MBean đang sử dụng **Standard MBean/MXBean** hay **ModelMBean do Spring dựng**?
- Phương thức có nằm trong **management interface** hoặc được **assembler** chọn không?
- `@ManagedAttribute`/`@ManagedOperation` có thực sự được metadata source xử lý không?
- Bean có phải **JDK/CGLIB AOP proxy** che target class hoặc giới hạn method không?
- Getter/setter có được ánh xạ thành **attribute** thay vì operation không?
- Có khác biệt về **method signature, kiểu dữ liệu, overload, tên và chữ hoa/chữ thường** không?

**Không chữa bằng cách export tất cả public methods ngay lập tức.** Điều đó có thể mở lộ API nghiệp vụ, setter nhạy cảm hoặc thao tác có side effect.

## 2. Phân biệt “không thấy MBean” và “MBeanInfo thiếu thành phần”

Cần xác định triệu chứng trước:

| Triệu chứng | Lớp cần điều tra |
| --- | --- |
| `MBeanServer.isRegistered(name) == false` | Export, autodetection, ObjectName, server, startup |
| MBean có, nhưng `getMBeanInfo(name)` không chứa attribute | Management interface, assembler, metadata, getter/setter |
| MBean có, nhưng thiếu operation | Assembler, annotation, signature, interface proxy |
| Metadata có attribute nhưng `getAttribute` thất bại | Runtime invocation, permission, reflection, getter exception |
| Metadata có operation nhưng `invoke` thất bại | Signature mismatch, authorization, target method exception |
| JConsole không thấy nhưng probe local có | Tool đang kết nối JVM/server khác, cache/UI hoặc connector |

Lỗi thiếu entry trong `MBeanInfo` là vấn đề **bề mặt metadata**, không tự động đồng nghĩa method Java không tồn tại.

Nếu MBean chưa đăng ký, đi theo quy trình startup/registration trước, rồi mới quay lại metadata.

## 3. MBeanInfo là nguồn xác nhận hợp đồng JMX

`javax.management.MBeanInfo` mô tả các thành phần mà JMX client có thể thấy:

- `MBeanAttributeInfo[]`: tên, type, khả năng đọc/ghi, mô tả.
- `MBeanOperationInfo[]`: tên operation, return type, impact và tham số.
- `MBeanNotificationInfo[]`: notification types được công bố.
- `MBeanConstructorInfo[]`: metadata constructor khi có.
- `Descriptor`: thông tin bổ sung tùy loại MBean.

Một Java class có 15 public methods không có nghĩa `MBeanInfo` phải chứa 15 operations. Standard MBean giới hạn theo management interface; Spring metadata assembler có thể chỉ chọn một vài method được đánh dấu.

`getClassName()` của `MBeanInfo` cũng không nên coi là bằng chứng trực tiếp về target class trong Spring context, nhất là khi MBean là ModelMBean hoặc wrapper.

## 4. Kiểm tra đúng MBeanServer và ObjectName

Thực hiện probe trên chính `MBeanServer` mà exporter sử dụng:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

System.out.println("Registered: " + server.isRegistered(expected));

for (ObjectName name : server.queryNames(
        new ObjectName("com.example.jobs:*"), null)) {
    System.out.println(name.getCanonicalName());
}
```

Nếu exporter được cấu hình `setServer(customServer)`, phải inject hoặc lấy đúng `customServer`. Platform server không mặc nhiên chứa các MBean của server tùy chỉnh.

Khi dùng JMX remote, `MBeanServerConnection` trên client chỉ đại diện server mà connector trỏ tới; nếu connector khác exporter, client có thể thấy các MBean nền tảng nhưng thiếu MBean của ứng dụng.

`ObjectName` có thể có key properties được sắp lại trong canonical representation. Kiểm tra `getCanonicalName()`, domain, type và name thay vì so sánh chuỗi thô không đúng ngữ nghĩa.

## 5. Dump attributes và operations để tránh đoán từ UI

Sau khi xác nhận đăng ký:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(expected);

System.out.println("MBeanInfo class=" + info.getClassName());

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "ATTR name=%s type=%s readable=%s writable=%s is=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable(),
        attr.isIs()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "OP name=%s return=%s impact=%d%n",
        op.getName(),
        op.getReturnType(),
        op.getImpact()
    );

    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.printf("  PARAM %s : %s%n",
            p.getName(), p.getType());
    }
}
```

Kết quả giúp giải quyết ba nhầm lẫn:

1. Getter `getQueueDepth()` có thể xuất thành **attribute `QueueDepth`**, không phải operation `getQueueDepth`.
2. Setter `setEnabled(boolean)` có thể xuất thành **writable attribute `Enabled`**, không phải operation riêng.
3. Operation overloaded có cùng tên nhưng nhiều **parameter signatures**, vì thế client cần so sánh cả signature.

`MBeanInfo` của server là bằng chứng tốt hơn việc đoán từ danh sách public method trong IDE.

## 6. Standard MBean: chỉ những method trong interface chuẩn được expose

Xét:

```java
package com.example.jobs.jmx;

public interface WorkerAdminMBean {
    int getQueueDepth();
    void pause();
}
```

```java
package com.example.jobs.jmx;

public final class WorkerAdmin implements WorkerAdminMBean {
    public int getQueueDepth() { return 7; }
    public void pause() { }

    public void resetDatabase() {
        // Public Java method, không nằm trong management interface.
    }
}
```

Khi `WorkerAdmin` được đăng ký như **Standard MBean**, `getQueueDepth` và `pause` thuộc hợp đồng JMX; `resetDatabase` không tự trở thành operation JMX.

Đây là **chủ đích thiết kế** chứ không phải lỗi annotation. Nếu một method thật sự cần xuất, bổ sung nó vào management interface với đánh giá tác động và quyền truy cập rõ ràng, hoặc xây một adapter quản trị riêng.

Lưu ý quy ước Standard MBean yêu cầu tên interface theo pattern class name cộng hậu tố `MBean`, hoặc sử dụng cách liên kết interface MBean phù hợp. MXBean có quy ước và mapping riêng với `MXBean`/annotation JMX.

## 7. MXBean và kiểu dữ liệu

MXBean áp dụng ánh xạ kiểu dữ liệu để có khả năng quản trị độc lập classloader hơn so với MBean tùy ý.

Ví dụ:

```java
public interface CacheStatisticsMXBean {
    long getHitCount();
    long getMissCount();
}
```

`CacheStatisticsMXBean` mô tả thuộc tính read-only `HitCount` và `MissCount`. Nếu client tìm operation `getHitCount`, kết luận thiếu operation sẽ sai vì method được thể hiện như attribute.

Khi dùng DTO/record hoặc generic types, MXBean/OpenType mapping có thể ảnh hưởng kiểu thực tế mà `MBeanInfo` công bố. Một method dùng kiểu không được hỗ trợ có thể gây lỗi compliance hoặc mapping. Không khắc phục bằng việc đổi đại khái chữ ký phía client mà không đối chiếu server metadata.

Với custom DTO phức tạp, cân nhắc scalar, `CompositeData`, `TabularData` hoặc các kiểu có mapping JMX rõ ràng.

## 8. Spring POJO export và MBeanInfoAssembler

Spring có thể export một POJO không phải Standard MBean bằng ModelMBean. Bề mặt được quyết định bởi `MBeanInfoAssembler`.

Những chiến lược thường gặp:

| Assembler | Tiêu chí quyết định method xuất |
| --- | --- |
| `SimpleReflectiveMBeanInfoAssembler` | Reflection với các public methods/properties đủ điều kiện |
| `MetadataMBeanInfoAssembler` | Metadata từ `JmxAttributeSource`, thường là annotation |
| `InterfaceBasedMBeanInfoAssembler` | Các method thuộc interface được chỉ định |
| `MethodNameBasedMBeanInfoAssembler` | Danh sách tên method được cho phép |
| `MethodExclusionMBeanInfoAssembler` | Loại khỏi tập các method được cấu hình |

Nếu bean dùng `MetadataMBeanInfoAssembler`, một public method không có annotation quản trị phù hợp **có thể bị loại có chủ đích**. Nếu dùng `InterfaceBasedMBeanInfoAssembler`, annotation trên method nằm ngoài interface không làm assembler tự bổ sung method đó.

Bước điều tra: tìm cấu hình exporter thực sự trong Spring context, không chỉ xem class đang được annotate. Một bean có `@ManagedResource` chưa bảo đảm exporter đã được cấu hình đọc metadata annotation.

## 9. Cấu hình annotation-based Spring JMX

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
class JmxMetadataConfiguration {

    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter mbeanExporter(
            AnnotationJmxAttributeSource source) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);
        return exporter;
    }
}
```

Ở đây:

- `AnnotationJmxAttributeSource` đọc thông tin như `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.
- `MetadataMBeanInfoAssembler` quyết định attribute/operation theo metadata.
- `MetadataNamingStrategy` tìm tên MBean theo metadata.
- `MBeanExporter` đăng ký bean với server.

Nếu Spring Boot đã auto-configure exporter, cần kiểm tra cấu hình cuối cùng trước khi tạo thêm exporter tùy chỉnh để tránh duplicate ObjectName. Ví dụ Java ở trên không thay thế việc xác minh dependencies, context và phiên bản Spring thực tế.

## 10. Dùng đúng annotation theo loại method

Một adapter quản trị:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary"
)
public class WorkerJmxAdapter {

    @ManagedAttribute(description = "Current queued jobs")
    public int getQueueDepth() {
        return 12;
    }

    @ManagedAttribute(description = "Paused state")
    public boolean isPaused() {
        return false;
    }

    @ManagedOperation(description = "Pause the worker")
    public void pause() {
        // Lệnh quản trị.
    }

    public void privateBusinessAction() {
        // Public Java method nhưng không được annotate cho JMX.
    }
}
```

Một số lỗi thường gặp:

- Dùng `@ManagedOperation` cho một getter mà JMX client đang tìm như attribute.
- Đặt `@ManagedAttribute` lên method không có getter/setter signature phù hợp.
- Đặt annotation trên implementation trong khi exporter đọc contract khác.
- Bỏ `@ManagedOperation` vì cho rằng `@ManagedResource` sẽ xuất mọi public method.
- Đặt annotation trên overloaded method nhưng mapping/invocation không như dự kiến.
- Dùng type hoặc access flags không tương thích kỳ vọng.

**Annotation không tự động bật exporter hoặc mở remote JMX.** Nó chỉ cung cấp metadata cho một đường cấu hình biết đọc annotation đó.

## 11. Getter, setter và JavaBeans convention

JMX attributes thường bắt nguồn từ property-style methods.

```java
public int getQueueDepth();
public boolean isPaused();
public void setPaused(boolean paused);
```

Các ánh xạ thông dụng:

| Java method | JMX attribute | Kiểu / quyền |
| --- | --- | --- |
| `getQueueDepth()` | `QueueDepth` | Readable int |
| `isPaused()` | `Paused` | Readable boolean |
| `setPaused(boolean)` | `Paused` | Writable boolean |
| `getState()` | `State` | Readable kiểu trả về |

Với setter, có thể cần matching getter cùng property hoặc quy tắc assembler cụ thể để xác định writable attribute. Một method `getQueueDepth(String queue)` không phải JavaBeans getter không tham số; nó phù hợp hơn với một operation nhận tham số nếu cần expose.

Cẩn thận với tên chữ hoa/thường: `queueDepth`, `QueueDepth` và `getQueueDepth` là những biểu diễn khác nhau. Client JMX nên đọc danh sách attribute names thực tế thay vì tự suy đoán.

## 12. JDK proxy và CGLIB proxy che metadata/method

Spring AOP có thể bọc bean bằng JDK dynamic proxy hoặc CGLIB subclass proxy.

- **JDK proxy** chỉ expose method của các interface được proxy triển khai.
- **CGLIB proxy** có quan hệ subclass với target nhưng không intercept được các phương thức `final` theo cơ chế override.
- Annotation trên target class không tự được sao chép vào JDK proxy class.
- Metadata source/assembler có thể nhận biết target class theo cơ chế Spring, nên không phải mọi proxy đều làm mất annotation.

Quan sát:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("workerService");

System.out.println("runtime=" + bean.getClass());
System.out.println("isProxy=" + AopUtils.isAopProxy(bean));
System.out.println("jdk=" + AopUtils.isJdkDynamicProxy(bean));
System.out.println("cglib=" + AopUtils.isCglibProxy(bean));
System.out.println("target=" + AopUtils.getTargetClass(bean));
```

`context` là Spring `ApplicationContext` được cung cấp ở nơi gọi. Nếu target có method `pause()` nhưng interface mà JDK proxy thực hiện chỉ có `submitJob()`, exporter có thể không expose hoặc không invoke `pause()` qua object proxy theo cách kỳ vọng.

Sửa lỗi bền vững thường là đưa các method quản trị vào một interface mà proxy hỗ trợ, hoặc tạo **adapter JMX riêng** inject management port. Không bật CGLIB cho toàn ứng dụng một cách mù quáng.

## 13. Hai lỗi có vẻ giống nhau nhưng khác bản chất

### 13.1. Metadata thiếu

`MBeanInfo.getOperations()` không chứa `pause`. Cần xem:

1. Interface MBean có `pause()` không?
2. Assembler đang dùng là loại nào?
3. `@ManagedOperation` nằm đúng method và được metadata source đọc không?
4. Runtime proxy có khả năng expose method không?
5. Có đang query đúng ObjectName/server không?

### 13.2. Metadata có nhưng invocation thất bại

`MBeanInfo` có `pause`, nhưng:

```java
server.invoke(
    expected,
    "pause",
    new Object[0],
    new String[0]
);
```

ném lỗi. Đây có thể là vấn đề khác: Spring AOP advice, security context, transaction, method target, data validation hoặc JMX signature.

Không thay assembler chỉ vì method runtime ném exception. Trước tiên đọc nested cause và đối chiếu signature trong MBeanInfo.

## 14. Kiểm tra method overload và chữ ký operation

Ví dụ:

```java
public void retry();
public void retry(String jobId);
public void retry(String jobId, int attempts);
```

Nếu exporter chỉ công bố một overload, `MBeanInfo` có thể chứa một operation `retry` với danh sách parameter types cụ thể. Để gọi đúng:

```java
server.invoke(
    expected,
    "retry",
    new Object[] { "job-7", 3 },
    new String[] { "java.lang.String", "int" }
);
```

Dùng `int` trong signature thay vì `java.lang.Integer` nếu operation server thực sự khai báo primitive. Một chút khác biệt kiểu tham số cũng có thể làm JMX không tìm đúng operation.

Khi operation không xuất hiện trong UI, dump toàn bộ `MBeanOperationInfo` cùng `MBeanParameterInfo.getType()`; đừng chỉ so sánh operation name.

## 15. Kiểm tra annotation trên target class và method

Nếu nghi ngờ proxy che annotation, so sánh runtime class và target class:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.jmx.export.annotation.ManagedResource;

Object bean = context.getBean("workerService");
Class<?> runtime = bean.getClass();
Class<?> target = AopUtils.getTargetClass(bean);

System.out.println("runtime=" + runtime.getName());
System.out.println("target=" + target.getName());

System.out.println("runtime managed=" +
    AnnotatedElementUtils.hasAnnotation(
        runtime, ManagedResource.class));

System.out.println("target managed=" +
    AnnotatedElementUtils.hasAnnotation(
        target, ManagedResource.class));
```

Nếu runtime thiếu annotation nhưng target có, dữ liệu này chỉ là bằng chứng về **đường reflection**, chưa chứng minh exporter không đọc được metadata. Cần tiếp tục xem `MBeanInfo` và exporter configuration.

Nếu nhiều interceptor tham gia, có thể xem advisor list qua `Advised` khi proxy hỗ trợ, nhưng không cần tháo toàn bộ proxy chain hoặc gọi target methods chỉ để tìm annotation.

## 16. Một integration test bảo vệ bề mặt JMX

Một test nên dùng Spring context thật với exporter và các AOP advice mà production bật.

Ví dụ logic assertion:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import javax.management.MBeanServer;
import javax.management.ObjectName;

void assertJmxContract(MBeanServer server) throws Exception {
    ObjectName name = new ObjectName(
        "com.example.jobs:type=Worker,name=Primary"
    );

    assertTrue(server.isRegistered(name));

    var info = server.getMBeanInfo(name);

    Set<String> attributeNames =
        Arrays.stream(info.getAttributes())
            .map(a -> a.getName())
            .collect(Collectors.toSet());

    Set<String> operationNames =
        Arrays.stream(info.getOperations())
            .map(op -> op.getName())
            .collect(Collectors.toSet());

    assertTrue(attributeNames.contains("QueueDepth"));
    assertTrue(attributeNames.contains("Paused"));
    assertTrue(operationNames.contains("pause"));
    assertFalse(operationNames.contains("privateBusinessAction"));
}
```

Khi dùng JUnit thực tế, xác minh cả type, readable/writable flags và signatures để bảo vệ contract đầy đủ. Test cần cleanup Spring context/MBeanServer để tránh ObjectName collision khi chạy suite hoặc redeploy.

Không test bằng cách gọi `new WorkerJmxAdapter()` rồi đoán JMX metadata: cần **đăng ký MBean** để lấy `MBeanInfo` cuối cùng.

## 17. Adapter quản trị riêng giúp giảm rủi ro

Một cách thiết kế bền vững:

```java
public interface WorkerManagementPort {
    int queueDepth();
    boolean paused();
    void pause();
}
```

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary"
)
public final class WorkerManagementAdapter {

    private final WorkerManagementPort management;

    public WorkerManagementAdapter(WorkerManagementPort management) {
        this.management = management;
    }

    @ManagedAttribute
    public int getQueueDepth() {
        return management.queueDepth();
    }

    @ManagedAttribute
    public boolean isPaused() {
        return management.paused();
    }

    @ManagedOperation
    public void pause() {
        management.pause();
    }
}
```

Adapter đặt contract JMX ở một chỗ, không buộc POJO nghiệp vụ phải export nhiều public methods và không phụ thuộc quá mạnh vào cấu trúc proxy của service.

Nếu adapter cũng bị AOP proxy, vẫn phải kiểm tra runtime class/target và MBeanInfo; tách adapter không tự bảo đảm mọi cấu hình proxy đều tương thích.

## 18. Quy trình chẩn đoán từng bước

```text
MBean không có attribute/operation mong đợi
                  |
                  v
       Đúng server và ObjectName?
             /           \\
           Không         Có
            |             |
     Sửa wiring/name       v
                        isRegistered?
                         /    \\
                       No      Yes
                       |        |
                  Export issue  v
                            Dump MBeanInfo
                              |
               +--------------+--------------+
               |                             |
         Standard/MXBean               Spring ModelMBean
               |                             |
       Kiểm tra interface            Kiểm tra assembler
               |                    và metadata source
               +--------------+--------------+
                              |
                        Kiểm tra proxy
                              |
                  Đối chiếu signature/type
                              |
                  Test attribute/invoke riêng
```

Checklist thực tế:

1. Xác định đúng `MBeanServer` của exporter.
2. In canonical `ObjectName` đang đăng ký.
3. Đọc `MBeanInfo`, ghi attribute/operation types và signatures.
4. Xác định MBean là Standard, MXBean, Dynamic hay Spring ModelMBean.
5. Nếu Standard/MXBean, xem management interface.
6. Nếu ModelMBean, xem `MBeanInfoAssembler` và `JmxAttributeSource`.
7. Kiểm tra annotation có đúng method và type không.
8. Kiểm tra AOP runtime proxy và target class.
9. Chạy integration test có Spring context thật.
10. Chỉ khi metadata đúng, mới kiểm tra getAttribute/invoke và nested exception.

## 19. Bảng nguyên nhân và hướng xử lý nhanh

| Nguyên nhân | Dấu hiệu | Giải pháp đúng hướng |
| --- | --- | --- |
| Sai ObjectName | `isRegistered=false` hoặc có tên tương tự | Query canonical names, sửa tên |
| Sai MBeanServer | Chỉ thấy MBean JVM | Cho exporter/connector dùng cùng server |
| Standard MBean interface không chứa method | Public method thiếu trong MBeanInfo | Cập nhật management interface |
| Metadata assembler không đọc annotation | Annotation có nhưng không có entry | Cấu hình metadata assembler/source |
| Reflective assembler expose khác kỳ vọng | Có nhiều/ít method | Chọn allowlist hoặc interface-based |
| JDK proxy che method quản trị | Target có method, interface proxy không có | Adapter hoặc interface phù hợp |
| Getter signature sai | `getX` có tham số hoặc return không phù hợp | Dùng operation hoặc sửa getter |
| Overload/type mismatch | Operation name có nhưng signature khác | Đọc MBeanOperationInfo |
| Remote client kết nối sai JVM | UI khác probe local | Kiểm tra connector URL/server |
| Metadata đúng nhưng invocation lỗi | `getAttribute`/`invoke` ném exception | Kiểm tra AOP/security/code runtime |

## 20. Ghi nhớ

**Nếu attribute hoặc operation không xuất hiện trong `MBeanInfo`, hãy bắt đầu từ metadata của MBean đã đăng ký, không bắt đầu từ public methods của Java class.** Trước hết kiểm tra server/ObjectName và dump đầy đủ attributes/operations. Sau đó phân nhánh theo Standard MBean/MXBean interface hoặc Spring ModelMBean assembler; đối chiếu annotation, method signature và AOP proxy. Đừng lẫn lộn metadata thiếu với invocation lỗi, và đừng dùng export-all để che vấn đề, vì điều đó có thể mở lộ API quản trị không mong muốn.
