# Đọc MBeanInfo sau khi bean đã qua nhiều interceptor trong Spring JMX và AOP

## 1. Vì sao cần xem MBeanInfo ở cuối chuỗi proxy?

Trong Spring Framework, một bean nghiệp vụ có thể đi qua nhiều lớp AOP trước khi được đưa ra ngoài `ApplicationContext`: transaction, caching, security, metrics, tracing, custom advice. Cùng một bean ban đầu có thể có nhiều interceptor, thậm chí nhiều tầng proxy lồng nhau.

Khi bean được Spring JMX `MBeanExporter` xuất thành MBean, người phát triển thường chỉ xem class gốc hoặc annotation trên source code để đoán attribute/operation nào xuất hiện. Điều này dễ gây nhầm lẫn bởi JMX client **không nhìn trực tiếp source class**. Client nhìn thấy metadata đăng ký trong `MBeanServer`, thông qua `MBeanInfo`.

Ví dụ thực tế:

- Target class có `@ManagedAttribute` nhưng JConsole không hiện attribute.
- Interface nghiệp vụ thiếu method quản trị; JDK proxy chỉ expose interface.
- Spring có thể đọc annotation ở target class nhưng method không được gọi qua proxy như mong đợi.
- MBean được đăng ký bằng Standard MBean/MXBean thay vì ModelMBean do Spring assembler tạo.
- Operation xuất hiện trong `MBeanInfo` nhưng invocation có thể thất bại ở tầng AOP hoặc code nghiệp vụ.
- Hai instance được đăng ký với cùng kiểu interface nhưng metadata không khớp vì exporter/config khác nhau.

Bài này hướng dẫn kiểm tra **hợp đồng JMX thực tế sau khi bean đã qua interceptor**, đồng thời tránh suy luận quá mức từ `bean.getClass()`.

## 2. Hai lớp metadata cần phân biệt

### 2.1. Metadata của class và proxy trong Spring

Spring quản lý bean Java. Có thể quan sát:

- `bean.getClass()`: runtime class của object được lấy từ container.
- `AopUtils.isAopProxy(bean)`: bean có phải Spring AOP proxy không.
- `AopUtils.isJdkDynamicProxy(bean)` hoặc `isCglibProxy(bean)`.
- `AopUtils.getTargetClass(bean)`: target class mà proxy đại diện, khi Spring có đủ thông tin.
- Annotation trên implementation hoặc interface, ví dụ `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.
- Các advisor/interceptor được gắn vào proxy (nếu object hỗ trợ `Advised`).

Đây là dữ liệu để chẩn đoán **đường đi từ bean tới exporter**.

### 2.2. Metadata MBeanInfo trong JMX

`javax.management.MBeanInfo` mô tả contract của MBean đã đăng ký:

- `getClassName()`: class name mà MBean metadata báo về, không mặc định là target class của Spring.
- `getAttributes()`: tên, kiểu dữ liệu, khả năng đọc/ghi và description.
- `getOperations()`: tên operation, chữ ký tham số, kiểu trả về, impact.
- `getConstructors()`: metadata constructor theo JMX.
- `getNotifications()`: notification mà MBean công bố.
- `getDescriptor()`: metadata bổ sung, nếu có.

Đây là **bề mặt quản trị mà JMX client nhìn thấy**. Không phải cứ có method Java public là xuất hiện trong `MBeanInfo`.

Cần kiểm tra cả hai lớp khi AOP tham gia: target metadata giải thích ý định thiết kế; MBeanInfo xác nhận hợp đồng được đăng ký.

## 3. Sơ đồ đường đi nhiều interceptor

```text
Business implementation
  @ManagedResource / @ManagedAttribute / @ManagedOperation
          |
          v
  Transaction advice
          |
          v
  Method security advice
          |
          v
  Cache / logging / metrics advice
          |
          v
  JDK proxy hoặc CGLIB proxy
          |
          v
  MBeanExporter
     +-- ObjectNamingStrategy
     +-- MBeanInfoAssembler (nếu export POJO)
          |
          v
  MBeanServer.registerMBean(ObjectName)
          |
          v
  MBeanServer.getMBeanInfo(ObjectName)
          |
          v
  JConsole / VisualVM / JMX client
```

Sơ đồ chỉ diễn đạt luồng khái niệm; một Spring AOP proxy thông thường có thể chứa **một chuỗi interceptor** thay vì một proxy Java mới cho mỗi advice. Khi proxy lồng nhau xảy ra do cấu hình hoặc library bổ sung, việc khám phá target class phức tạp hơn.

Điều quan trọng là **advisor/interceptor không đồng nghĩa MBean attribute/operation**. Advice thay đổi hành vi khi gọi; việc xuất method quản trị được quyết định bởi contract JMX hoặc `MBeanInfoAssembler`.

## 4. Ví dụ target bean chịu nhiều advice

Một service có cả cache và transaction:

```java
package com.example.jobs;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary",
    description = "Worker management"
)
public class WorkerService implements WorkerOperations {

    private volatile boolean paused;

    @Override
    @Transactional
    public void submit(String jobId) {
        // Xử lý nghiệp vụ.
    }

    @ManagedAttribute(description = "Worker paused")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Pause worker")
    public void pause() {
        paused = true;
    }

    @Cacheable("worker-summary")
    public String getSummary() {
        return "worker-state";
    }
}
```

Interface nghiệp vụ:

```java
public interface WorkerOperations {
    void submit(String jobId);
}
```

Nếu Spring chọn JDK dynamic proxy vì AOP, proxy thường triển khai `WorkerOperations`, nhưng không nhất thiết có các method `pause()`, `isPaused()`, `getSummary()` ở giao diện Java của proxy. Spring metadata có thể tìm annotation trên target class theo cấu hình, song việc thực hiện một method chỉ có trên implementation qua JDK proxy có thể gặp vấn đề.

Nếu Spring dùng CGLIB class proxy, các method có thể được nhìn thấy theo subclass nhưng vẫn chịu giới hạn với method `final`, `private`, self-invocation và sự tương tác của advice.

Không dùng ví dụ này để kết luận mọi Spring JMX export với JDK proxy đều thất bại. Phải đo **thực tế** qua MBeanInfo và thử invocation.

## 5. Inspect runtime bean và target class

Trong một Spring component nhận `ApplicationContext`:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.context.ApplicationContext;

public final class AopBeanProbe {

    public static void describe(
            ApplicationContext context,
            String beanName) {

        Object bean = context.getBean(beanName);

        System.out.println("beanName=" + beanName);
        System.out.println("runtime=" + bean.getClass().getName());
        System.out.println("isAopProxy=" + AopUtils.isAopProxy(bean));
        System.out.println("isJdkProxy=" + AopUtils.isJdkDynamicProxy(bean));
        System.out.println("isCglibProxy=" + AopUtils.isCglibProxy(bean));
        System.out.println("targetClass=" +
            AopUtils.getTargetClass(bean).getName());
    }
}
```

Ví dụ kết quả:

```text
beanName=workerService
runtime=jdk.proxy2.$Proxy...
isAopProxy=true
isJdkProxy=true
isCglibProxy=false
targetClass=com.example.jobs.WorkerService
```

Điều đó chứng minh Spring context đã trả về proxy; nó **không** chứng minh rằng MBeanExporter đã đăng ký đúng bean hoặc JMX client thấy đầy đủ operation.

Mỗi phép kiểm tra phải trả lời một câu hỏi cụ thể: loại object Spring giao cho exporter khác với contract JMX cuối cùng.

## 6. Kiểm tra chuỗi advisor/interceptor trên Spring AOP proxy

Nhiều interceptor có thể nằm trong cùng một Spring AOP proxy. Với một proxy triển khai `org.springframework.aop.framework.Advised`, có thể in danh sách advisor:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;

Object bean = context.getBean("workerService");

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
```

Danh sách này có thể chứa transaction interceptor, cache interceptor, method security interceptor hoặc advice tùy chỉnh. Thứ tự advisor có thể ảnh hưởng hành vi, nhưng không luôn đồng nghĩa thứ tự chính xác của mọi đường thực thi nếu advisor có pointcut, dynamic matching hoặc logic khác.

Không gọi `getTargetSource().getTarget()` một cách tùy tiện chỉ để inspect khi target source có lifecycle đặc biệt, pooling hoặc lazy creation; thao tác đó có thể khởi tạo hoặc mượn object. Dùng `AopUtils.getTargetClass` và metadata an toàn trước.

Nếu proxy không triển khai `Advised`, không thể suy luận rằng không có interceptor: proxy khác hoặc frozen/proxy custom có thể không expose API này.

## 7. Đọc MBeanInfo bằng MBeanServer

Đây là phép kiểm tra trực tiếp hợp đồng JMX:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("ObjectName=" + name.getCanonicalName());
System.out.println("MBeanInfo class=" + info.getClassName());
System.out.println("Description=" + info.getDescription());
```

**Phải dùng đúng server mà exporter đăng ký MBean.** Nếu exporter sử dụng custom `MBeanServer`, platform server có thể không chứa bean. Một kết quả `isRegistered=false` trên server sai không cho phép kết luận AOP làm mất annotation.

Với client remote, `MBeanServerConnection.getMBeanInfo(ObjectName)` cung cấp thông tin tương đương qua JMX connector.

## 8. In toàn bộ attribute của MBeanInfo

```java
import javax.management.MBeanAttributeInfo;

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s; type=%s; readable=%s; writable=%s; is=%s%n",
        a.getName(),
        a.getType(),
        a.isReadable(),
        a.isWritable(),
        a.isIs()
    );
}
```

Nếu `@ManagedAttribute` trên target có tên getter `isPaused()`, kỳ vọng thông thường là attribute `Paused` (kiểu boolean). Nhưng naming và exposure có thể bị ảnh hưởng bởi assembler và metadata khác.

Đừng chỉ nhìn có `Paused` hay không; phải kiểm tra:
- Tên attribute chính xác và phân biệt chữ hoa/thường.
- Type string mà JMX báo.
- `isReadable()` và `isWritable()`.
- `isIs()` cho boolean getter dạng `is...`.
- Description khi cần tài liệu vận hành.

Một method Java đã nằm trên proxy cũng không đủ để thành JMX attribute nếu exporter không chọn method ấy.

## 9. In operation và parameter signature

```java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "Operation=%s; return=%s; impact=%d%n",
        op.getName(),
        op.getReturnType(),
        op.getImpact()
    );

    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.printf(
            "  parameter=%s type=%s%n",
            p.getName(),
            p.getType()
        );
    }
}
```

Một operation JMX được xác định bởi tên và danh sách kiểu tham số. Khi có overload, hai operation cùng tên vẫn có thể là hai chữ ký khác nhau.

Ví dụ client invoke:

```java
server.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);
```

Nếu MBeanInfo công bố `pause(java.lang.String)` nhưng client gọi không tham số, invocation không khớp. Nếu `pause()` có trong metadata nhưng call ném exception, xem nested cause ở tầng AOP/security/transaction thay vì kết luận metadata sai.

## 10. Inspect notification và descriptor

Bề mặt JMX không chỉ có attribute và operation. Một MBean có thể công bố notification:

```java
for (var notification : info.getNotifications()) {
    System.out.println(notification.getName());

    for (String type : notification.getNotifTypes()) {
        System.out.println("  " + type);
    }
}
```

Với ModelMBean do Spring dựng, `Descriptor` có thể chứa thông tin hữu ích liên quan metadata, field và cách expose:

```java
System.out.println(info.getDescriptor());
```

Không giả định mọi descriptor có cùng field hoặc luôn chứa class target. Nội dung descriptor tùy loại MBean (Standard, Dynamic, ModelMBean, MXBean) và framework/assembler.

Nếu MBeanInfo chỉ có một phần attribute/operation, cần phân biệt **thiếu metadata** với **các method không được expose có chủ ý**. Một management interface nhỏ thường tốt hơn tự động xuất tất cả public method.

## 11. Vì sao nhiều interceptor làm MBeanInfo khác dự kiến?

Có một số cơ chế độc lập:

### 11.1. JDK proxy giới hạn method có thể gọi

Nếu target có `pause()` nhưng JDK proxy chỉ triển khai interface `submit(String)`, method `pause()` không xuất hiện như một Java method trên proxy. Exporter có thể lấy target metadata nhưng gặp vấn đề khi liên kết lời gọi tới runtime proxy.

### 11.2. Spring metadata source chọn class/annotation khác

`AnnotationJmxAttributeSource` hoặc assembler có thể tra annotation trên target, interface hoặc các method qua resolver. Nếu cấu hình khác, kết quả chọn method cũng khác. Không phải mọi phép `bean.getClass().isAnnotationPresent(...)` đều phản ánh khả năng đọc metadata thực tế của Spring.

### 11.3. Exporter dùng interface/assembler khác

Nếu dùng `InterfaceBasedMBeanInfoAssembler`, `MethodNameBasedMBeanInfoAssembler` hoặc contract Standard MBean, bề mặt cuối cùng có thể không dựa vào annotation trên target. AOP có thể chỉ là sự trùng hợp khi một thay đổi cấu hình export thực sự gây khác biệt.

### 11.4. Proxy thêm interface hoặc method hỗ trợ

Một proxy có thể triển khai `Advised` và các interface framework nội bộ. Điều đó không có nghĩa chúng được phép lộ qua JMX. Một assembler phản chiếu quá rộng có thể tăng bề mặt công bố ngoài dự kiến; cần dùng allowlist/metadata assembler phù hợp.

### 11.5. Khởi tạo và vòng đời context khác nhau

MBean có thể chưa đăng ký khi probe chạy, hoặc đã được unregister lúc context đóng. Một lỗi startup cũng có thể xảy ra ở bước export trước khi JMX client có cơ hội đọc MBeanInfo.

Chính vì vậy, **đọc MBeanInfo của tên đã đăng ký trên server thực** có giá trị hơn đoán từ loại proxy.

## 12. Kiểm tra annotation target bên cạnh metadata JMX

Một probe cho phép so sánh hai góc nhìn:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.jmx.export.annotation.ManagedResource;

Object bean = context.getBean("workerService");

Class<?> runtime = bean.getClass();
Class<?> target = AopUtils.getTargetClass(bean);

System.out.println("runtime=" + runtime.getName());
System.out.println("target=" + target.getName());

System.out.println(
    "runtime @ManagedResource=" +
    AnnotatedElementUtils.hasAnnotation(
        runtime, ManagedResource.class
    )
);
System.out.println(
    "target @ManagedResource=" +
    AnnotatedElementUtils.hasAnnotation(
        target, ManagedResource.class
    )
);
```

Nếu runtime class không có annotation nhưng target có, điều đó gợi ý ảnh hưởng proxy tới reflection. **Không tự động kết luận exporter bỏ qua bean**: Spring JMX có thể đọc annotation theo target metadata.

Cần tiếp tục kiểm tra `MBeanServer.isRegistered` và `MBeanInfo`; nếu không đăng ký được MBean, đọc startup log để phân biệt autodetection không chọn bean với registerMBean lỗi.

## 13. Thử invocation để phân biệt metadata và hành vi

MBeanInfo là contract hiển thị, nhưng chỉ inspection chưa chứng minh operation chạy được. Test đọc attribute và gọi method:

```java
Object paused = server.getAttribute(name, "Paused");
System.out.println("Paused=" + paused);

server.invoke(
    name, "pause", new Object[0], new String[0]
);

Object after = server.getAttribute(name, "Paused");
System.out.println("Paused after=" + after);
```

Việc gọi `pause` có side effect; chỉ thực hiện trong test hoặc môi trường đã được cho phép. Với production, ưu tiên read-only probe như `getMBeanInfo`, `queryNames` và những attribute an toàn.

Nếu operation có trong MBeanInfo nhưng bị `SecurityException`, `MBeanException`, `ReflectionException` hoặc wrapper tương tự, hãy xem cause sâu nhất. Method security có thể không có authentication context như HTTP request, vì cuộc gọi JMX có thể chạy trên thread khác.

Tương tự, transaction hoặc caching advice có thể tham gia khi gọi method từ JMX nếu object đăng ký thực sự là Spring proxy. Không coi annotation `@Transactional` trên target là bằng chứng chắc chắn rằng lời gọi từ MBeanServer đi qua transaction advice.

## 14. Adapter quản trị giúp giữ hợp đồng ổn định

Khi service có nhiều interceptor và bề mặt JMX cần ổn định, thiết kế adapter riêng:

```java
public interface WorkerManagementPort {
    boolean isPaused();
    int getQueueDepth();
    void pause();
}
```

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Management,name=Primary"
)
public final class WorkerJmxAdapter {

    private final WorkerManagementPort management;

    public WorkerJmxAdapter(WorkerManagementPort management) {
        this.management = management;
    }

    @ManagedAttribute
    public boolean isPaused() {
        return management.isPaused();
    }

    @ManagedAttribute
    public int getQueueDepth() {
        return management.getQueueDepth();
    }

    @ManagedOperation
    public void pause() {
        management.pause();
    }
}
```

Service thực hiện `WorkerManagementPort` có thể là Spring AOP proxy. Adapter gọi qua interface mà proxy expose, nên các advice của nghiệp vụ vẫn có thể hoạt động đúng khi được cấu hình. JMX metadata tập trung trên adapter, tách khỏi các chi tiết proxy của service.

Nếu pointcut AOP bao cả adapter, adapter cũng có thể bị proxy; integration test phải lấy bean thực tế và kiểm tra kết quả export.

## 15. Cấu hình metadata assembler phù hợp

Khi dùng Spring JMX annotation, cần một cấu hình nhận metadata tương ứng. Ví dụ Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
class JmxConfig {

    @Bean
    AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter exporter(AnnotationJmxAttributeSource source) {
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

Trong Spring Boot, nếu auto-configuration đã cung cấp exporter, tránh tạo hai exporter cùng trách nhiệm. Với Spring Framework thuần, `@EnableMBeanExport` cũng có thể được sử dụng. Chọn một chiến lược, xác định server và ObjectName thực tế, rồi kiểm chứng bằng probe.

## 16. Integration test MBeanInfo khi AOP hoạt động

Một test nên bật những advice mà production sử dụng, bảo đảm bean đã được proxy và kiểm tra MBeanInfo cuối cùng:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.aop.support.AopUtils;

void assertManagementContract(
        Object businessBean,
        MBeanServer server
) throws Exception {

    assertTrue(AopUtils.isAopProxy(businessBean));

    ObjectName name = new ObjectName(
        "com.example.jobs:type=Management,name=Primary"
    );

    assertTrue(server.isRegistered(name));

    var info = server.getMBeanInfo(name);

    Set<String> attributes = Arrays.stream(info.getAttributes())
        .map(a -> a.getName())
        .collect(Collectors.toSet());

    assertTrue(attributes.contains("Paused"));
    assertTrue(attributes.contains("QueueDepth"));

    Set<String> operations = Arrays.stream(info.getOperations())
        .map(op -> op.getName())
        .collect(Collectors.toSet());

    assertTrue(operations.contains("pause"));
}
```

Test trên cần context, transaction/caching/security AOP và MBeanServer thật. Không đủ nếu chỉ `new WorkerService()` bên ngoài Spring, vì khi đó advisor/interceptor không tham gia.

Đối với contract nghiêm ngặt, kiểm tra thêm:
- Kiểu attribute, quyền read/write.
- Tên operation và parameter signature.
- Không có operation nội bộ ngoài allowlist.
- Read-only getters chạy mà không có side effect.
- Notification metadata nếu dùng notification.
- Lifecycle unregister khi đóng context.

## 17. So sánh MBeanInfo trước và sau thay đổi AOP

Khi thêm một interceptor mới, viết test regression:

1. Khởi động Spring context với AOP cấu hình thực tế.
2. Lấy đúng `MBeanServer` và ObjectName.
3. Đọc `MBeanInfo`, lưu cấu trúc contract được chuẩn hóa trong test expectation.
4. Thêm/thay đổi advice hoặc proxy strategy.
5. Khởi động context thử nghiệm, đọc lại `MBeanInfo`.
6. So sánh attribute names/types, read-write flags và operation signatures.
7. Chạy invocation test cho các method được phép.
8. Dọn context để không giữ registration cũ.

Không so sánh mọi trường text của `MBeanInfo.toString()` vì descriptor, description hoặc thứ tự hiển thị có thể thay đổi do version/framework mà không làm thay đổi hợp đồng cần bảo vệ. So sánh các field mà client thật sự phụ thuộc.

Nếu chạy hai context song song cùng JVM, chọn ObjectName namespace riêng cho mỗi test. Đừng để `InstanceAlreadyExistsException` che lấp mục tiêu kiểm tra AOP.

## 18. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Bước xác minh |
| --- | --- | --- |
| Bean có annotation nhưng không thấy MBean | Autodetect, naming hoặc proxy metadata | Spring bean class, exporter config, `isRegistered` |
| MBean có nhưng thiếu getter | Assembler không chọn hoặc interface proxy thiếu method | `getAttributes`, target/interface |
| Operation có tên nhưng thiếu overload | Signature không được export | `getOperations`, parameter list |
| Metadata đúng nhưng invoke lỗi | Method security, transaction, reflection hoặc code nghiệp vụ | Nested exception và AOP call path |
| Thêm advice khiến class runtime khác | JDK/CGLIB proxy strategy thay đổi | `AopUtils` và advisors |
| `getClassName` không giống target | ModelMBean/wrapper/adapter được đăng ký | `MBeanInfo`, exporter wiring |
| MBeanInfo sai trong test nhưng đúng prod | Khác exporter, profile, AOP hoặc MBeanServer | So sánh effective config |
| MBean biến mất sau restart | Context unregister hoặc ObjectName thay đổi | Lifecycle và `queryNames` |
| Client thấy MBean JVM nhưng không thấy app | Connector trỏ server khác exporter | Inject và so sánh MBeanServer instance |

Khi gặp lỗi, không vội bật class-based proxy toàn hệ thống. Đầu tiên xác nhận exact ObjectName, contract JMX, assembler và sự khác biệt giữa runtime proxy với target class.

## 19. Quy trình kiểm tra trong 10 phút

```text
Lấy bean từ Spring context
  |
  +-- In bean.getClass()
  +-- AopUtils.isAopProxy / getTargetClass
  +-- Nếu Advised: in advisors
  |
  v
Xác nhận MBeanExporter và MBeanServer
  |
  v
server.isRegistered(ObjectName)?
  |
  +-- NO -> kiểm tra autodetection, naming, registration logs
  |
  +-- YES -> server.getMBeanInfo(ObjectName)
                |
                +-- In attributes (name/type/read/write)
                +-- In operations (name/signature/return)
                +-- In notifications và descriptor khi cần
                |
                v
          Metadata đúng?
           /       \\
         NO         YES
         |           |
  assembler/       test getAttribute/invoke
  interface/        và nested exceptions
  proxy metadata
```

Dữ liệu đáng lưu khi chẩn đoán là ObjectName canonical, runtime proxy class, target class, advisors, exporter config, MBeanInfo và lỗi invocation. Hạn chế log giá trị attribute hoặc tham số nhạy cảm trong production.

## 20. Ghi nhớ

**Khi bean đã đi qua nhiều Spring AOP interceptor, nguồn đáng tin cậy nhất về bề mặt JMX cuối cùng là `MBeanServer.getMBeanInfo(ObjectName)`.** Runtime class và target annotation giúp giải thích vì sao metadata được chọn hoặc bị bỏ qua, còn MBeanInfo cho biết client thực sự nhìn thấy attributes, operations, signatures và notifications nào. Metadata hiển thị và khả năng invocation vẫn là hai phép kiểm tra riêng. Với kiến trúc có AOP phức tạp, adapter JMX nhỏ, giữ contract ổn định và integration test trên context thật thường giúp tránh phụ thuộc vào chi tiết của proxy.
