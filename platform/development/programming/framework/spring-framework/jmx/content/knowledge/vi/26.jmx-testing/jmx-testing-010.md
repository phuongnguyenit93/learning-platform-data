# Kiểm thử proxy hoặc AOP không làm mất metadata trong Spring Framework JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích tại sao một Spring bean có `@ManagedResource`, `@ManagedAttribute` hoặc `@ManagedOperation` vẫn có thể thiếu metadata JMX khi được bao bởi AOP proxy.
- Phân biệt **target class**, **runtime proxy class**, **management interface** và metadata thực tế do `MBeanServer.getMBeanInfo` trả về.
- Hiểu sự khác biệt giữa **JDK dynamic proxy** và **class-based (CGLIB) proxy** khi Spring tìm annotation và xác định các method có thể gọi.
- Viết kiểm thử tự động xác minh `ObjectName`, attributes, operations, signature, description và descriptor sau khi `MBeanExporter` đăng ký MBean.
- Tạo phép thử phản diện nhằm phát hiện operation nhạy cảm bị export nhầm hoặc một operation quản trị bị biến mất sau khi thêm `@Transactional`, `@Async`, `@Cacheable` hoặc một aspect khác.
- Kiểm tra không chỉ metadata mà còn **đường gọi thực tế qua proxy**, tránh false positive khi annotation xuất hiện nhưng advice không chạy.
- Thiết kế management adapter riêng, hạn chế phụ thuộc vào chi tiết proxy của business service.
- Chẩn đoán lỗi JMX export, không nhầm vấn đề proxy với sai `ObjectName`, naming strategy, registration policy hay sai `MBeanServer`.

## 2. Vấn đề: metadata có thể thay đổi khi bean được proxy

Trong Spring, một method thường được gọi thông qua bean lấy từ `ApplicationContext`. Khi AOP được bật, object thực tế được container đưa cho consumer có thể không phải instance của class gốc mà là proxy bao quanh class đó.

```text
Source code
  @ManagedResource
  class WorkerManagement {
      @ManagedAttribute getQueueDepth()
      @ManagedOperation requestPause()
  }
             |
             v
Spring AOP infrastructure
             |
       +-----+------+
       |            |
 JDK proxy      CGLIB proxy
       |            |
       +-----+------+
             |
             v
        MBeanExporter
             |
             v
     MBeanInfoAssembler
             |
             v
         MBeanServer
             |
             v
  MBeanInfo client nhìn thấy
```

Có hai câu hỏi độc lập:

1. **Bean có được export không?** Phụ thuộc exporter, cách autodetect, metadata source, naming strategy, registration policy và server đích.
2. **Những thành phần nào được export?** Phụ thuộc management interface, assembler, annotations, proxy/target class và loại MBean.

Thêm AOP có thể tác động tới cả hai câu hỏi. Ví dụ annotation quản trị nằm trên implementation class nhưng runtime object là JDK proxy chỉ trực tiếp expose interface. Nếu đường introspection không truy được annotation ở target class, assembler có thể không nhận diện đúng resource hoặc mất mô tả một số method.

Không mặc định mọi phiên bản Spring hoặc mọi assembler đều gặp lỗi này. Spring có các cơ chế hỗ trợ introspection proxy, nhưng **kết quả phải được kiểm tra tại runtime trong cấu hình cụ thể**.

## 3. Định nghĩa metadata JMX cần giữ nguyên

`MBeanInfo` là mô tả hợp đồng của MBean mà client thực sự nhìn thấy. Các thành phần cần kiểm tra:

| Nhóm | API đọc | Ví dụ kỳ vọng |
| --- | --- | --- |
| Identity | `ObjectName` | `com.example:type=Worker,name=Importer` |
| Mô tả MBean | `MBeanInfo.getDescription()` | Import worker monitoring |
| Attributes | `getAttributes()` | `QueueDepth` read-only |
| Attribute type | `MBeanAttributeInfo.getType()` | `long` |
| Writable flag | `MBeanAttributeInfo.isWritable()` | `false` |
| Operations | `getOperations()` | `requestPause()` |
| Operation return type | `MBeanOperationInfo.getReturnType()` | `void` |
| Operation signature | `MBeanOperationInfo.getSignature()` | `[]` hoặc `int` |
| Operation description | `MBeanOperationInfo.getDescription()` | Request graceful pause |
| Parameter metadata | `MBeanParameterInfo` | name, type, description |
| Descriptor | `getDescriptor()` | những field thực sự được assembler tạo |

Thông tin `isWritable=false` là metadata về khả năng ghi của MBean, không phải quyền của tài khoản JMX hiện tại. Tương tự, `impact` là metadata vận hành, không phải cơ chế cấp quyền.

**Không kiểm thử metadata bằng cách gọi mọi operation.** Chỉ đọc `getMBeanInfo` để khám phá bề mặt API; gọi operation có thể làm thay đổi trạng thái ứng dụng.

## 4. JDK dynamic proxy và class-based proxy

### 4.1. JDK dynamic proxy

Nếu target implements interface và Spring chọn JDK proxy, proxy thường expose các method được khai báo trên interface mà proxy triển khai:

```java
public interface WorkerService {
    long getQueueDepth();
    void requestPause();
}

@Service
public class WorkerServiceImpl implements WorkerService {
    @Override
    public long getQueueDepth() { return 12; }

    @Override
    @Transactional
    public void requestPause() {
        // Update worker state.
    }
}
```

Với JDK proxy, reflection trên proxy class khác với reflection trên implementation class. Một assembler hoặc custom naming strategy chỉ xem `proxy.getClass()` có thể không thấy annotation của target theo cách dự kiến.

### 4.2. Class-based proxy (thường CGLIB)

Class-based proxy kế thừa target class. Một số annotation có thể được đọc qua class hierarchy/method resolution, nhưng không nên khẳng định tất cả metadata luôn được giữ nguyên, nhất là với method `final`, class `final`, private methods hoặc cơ chế proxy không thể intercept một method.

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
@Configuration
class ClassProxyConfiguration {
}
```

Đây là cấu hình minh họa một cách yêu cầu class-based proxy trong một ngữ cảnh Spring; các cấu hình AOP khác như transaction/async có thể ảnh hưởng quyết định proxy thực tế. Luôn kiểm tra `AopUtils.isJdkDynamicProxy`, `AopUtils.isCglibProxy` và target class của bean trong test.

### 4.3. Những giả định cần tránh

- JDK proxy không đồng nghĩa metadata sẽ chắc chắn mất.
- CGLIB proxy không đồng nghĩa tất cả method đều được advice.
- `@ManagedResource` trên class không có nghĩa exporter chắc chắn đã dùng metadata annotation.
- Method có `@ManagedOperation` không chắc nằm trong MBeanInfo nếu bean không được chọn hoặc assembler không đọc annotation.
- Method có metadata xuất hiện trong MBeanInfo không bảo đảm Spring advice tương ứng thực sự chạy.

## 5. Thiết kế mẫu: adapter JMX riêng

Một hướng dễ bảo trì là tách bề mặt JMX khỏi bean nghiệp vụ chịu nhiều advice:

```text
MBeanServer
    |
    v
@ManagedResource WorkerAdminAdapter
    |
    +-- @ManagedAttribute getQueueDepth()
    +-- @ManagedOperation requestPause()
    |
    v
WorkerService Spring proxy
    |
    +-- @Transactional
    +-- @Async
    +-- custom aspects
    |
    v
Target service
```

Cách này giúp metadata JMX nằm trên một class quản trị ổn định, trong khi behavior vẫn đi qua service proxy đã được Spring quản lý. Adapter không cần tự chứa transaction hoặc async logic.

### 5.1. Service contract

```java
package example.jmx;

public interface WorkerService {
    long queueDepth();
    void requestPause();
}
```

### 5.2. Service implementation có AOP

```java
package example.jmx;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WorkerServiceImpl implements WorkerService {
    @Override
    public long queueDepth() {
        return 12L;
    }

    @Override
    @Transactional
    public void requestPause() {
        // Thay đổi trạng thái thực tế ở service layer.
    }
}
```

Để `@Transactional` thật sự có hiệu lực, cần transaction management và một transaction manager phù hợp. Chỉ gắn annotation không đủ.

### 5.3. Management adapter

```java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Importer",
    description = "Import worker management"
)
public class WorkerAdminAdapter {
    private final WorkerService workerService;

    public WorkerAdminAdapter(WorkerService workerService) {
        this.workerService = workerService;
    }

    @ManagedAttribute(description = "Current queue depth")
    public long getQueueDepth() {
        return workerService.queueDepth();
    }

    @ManagedOperation(
        description = "Request a graceful pause of the worker"
    )
    public void requestPause() {
        workerService.requestPause();
    }

    public void deleteInternalState() {
        // Không có annotation quản trị.
    }
}
```

Adapter này công bố đúng API quản trị cần thiết. `deleteInternalState` không nên được export trong metadata-based assembler thích hợp, và test cần xác minh điều đó.

## 6. Cấu hình Spring JMX metadata exporter

Một cấu hình tường minh giúp loại bỏ sự mơ hồ về assembler:

```java
package example.jmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxExportConfiguration {
    @Bean
    public MBeanExporter jmxExporter(WorkerAdminAdapter admin) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setBeans(Map.of("workerAdminAdapter", admin));
        return exporter;
    }
}
```

Nếu Spring Boot đã auto-configure exporter, tránh tạo thêm exporter trùng cùng `ObjectName`. Trong test cần xác định **một chủ sở hữu đăng ký MBean** hoặc bảo đảm các exporter có phạm vi không chồng chéo.

Trong một ứng dụng có cấu hình hiện hữu, có thể dùng `@EnableMBeanExport` thay vì bean exporter tường minh. Điều cần kiểm tra không phải có bao nhiêu annotation trong source mà là MBeanInfo runtime của MBean thực sự được export.

## 7. Kiểm tra bean có bị AOP proxy hay không

Spring cung cấp các tiện ích ở `org.springframework.aop.support.AopUtils`:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean(WorkerService.class);

System.out.println("Proxy? " + AopUtils.isAopProxy(bean));
System.out.println("JDK? " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB? " + AopUtils.isCglibProxy(bean));
System.out.println(
    "Target class: " + AopUtils.getTargetClass(bean)
);
```

Đoạn này hữu ích khi test đang kiểm tra JDK proxy hay CGLIB proxy. Nếu không có advice áp dụng, Spring có thể không tạo AOP proxy. Test muốn so sánh hai proxy types phải chủ động tạo advice phù hợp và assert loại proxy thực tế.

### 7.1. Không dựa vào tên class proxy

JDK proxy có thể mang tên class do JDK tạo; CGLIB proxy cũng có tên sinh tự động. Không dùng tên runtime proxy class làm hợp đồng quản trị ổn định, không hardcode tên proxy vào ObjectName hoặc test.

Ưu tiên xác định target class qua cơ chế Spring hỗ trợ và dùng naming strategy/metadata rõ ràng.

## 8. Kiểm tra ObjectName được đăng ký

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=Importer"
);

if (!server.isRegistered(name)) {
    throw new AssertionError("Expected MBean is missing");
}
```

Đoạn này giả định exporter đang dùng platform MBeanServer. Nếu exporter dùng custom server, phải inject/lấy đúng server. `isRegistered=true` vẫn chưa chứng minh bean nào chiếm ObjectName: với registration policy `IGNORE_EXISTING` có thể là object khác đã tồn tại.

Để xác minh đầy đủ, đọc `MBeanInfo` ngay sau đó.

## 9. In metadata runtime và so sánh hợp đồng

```java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanAttributeInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("Class: " + info.getClassName());
System.out.println("Description: " + info.getDescription());

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf(
        "attribute=%s type=%s readable=%s writable=%s desc=%s%n",
        a.getName(), a.getType(),
        a.isReadable(), a.isWritable(), a.getDescription()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "operation=%s return=%s signature=%d desc=%s%n",
        op.getName(),
        op.getReturnType(),
        op.getSignature().length,
        op.getDescription()
    );
}
```

Kỳ vọng của adapter mẫu:

```text
Attribute: QueueDepth
  type = long
  readable = true
  writable = false
  description = Current queue depth

Operation: requestPause
  signature = []
  returnType = void
  description = Request a graceful pause of the worker

Không có operation: deleteInternalState
```

Không dựa vào thứ tự array `getAttributes()` hoặc `getOperations()` để assert; so sánh bằng tên, signature và property.

## 10. Unit test metadata helper

Một phép assertion có thể dùng Java streams:

```java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanAttributeInfo depth =
    Arrays.stream(info.getAttributes())
        .filter(a -> "QueueDepth".equals(a.getName()))
        .findFirst()
        .orElseThrow(() ->
            new AssertionError("QueueDepth missing"));

if (!"long".equals(depth.getType())
        || !depth.isReadable()
        || depth.isWritable()) {
    throw new AssertionError("QueueDepth contract changed");
}

MBeanOperationInfo pause =
    Arrays.stream(info.getOperations())
        .filter(op -> "requestPause".equals(op.getName())
            && op.getSignature().length == 0)
        .findFirst()
        .orElseThrow(() ->
            new AssertionError("requestPause() missing"));

if (!"void".equals(pause.getReturnType())) {
    throw new AssertionError("Wrong return type");
}
```

Đây là **runtime contract check**, không kiểm tra business operation đã chạy. Thêm các phép kiểm tra description/parameter metadata nếu đó là phần cần giữ ổn định.

## 11. Negative test: ngăn xuất API nội bộ

Một yêu cầu bảo mật quan trọng là những method không dự định quản trị phải không nằm trong MBeanInfo:

```java
boolean leaked = Arrays.stream(info.getOperations())
    .anyMatch(op ->
        "deleteInternalState".equals(op.getName()));

if (leaked) {
    throw new AssertionError(
        "Internal method exposed through JMX"
    );
}
```

Nếu dùng custom DynamicMBean, còn cần test code `invoke(...)` thực sự từ chối tên method không được phép, vì metadata ẩn một operation không bảo đảm dynamic implementation không xử lý nó.

Không xuất toàn bộ service bean có các method nhạy cảm chỉ để giảm vài dòng cấu hình. Một management adapter có allowlist annotations rõ thường dễ kiểm soát hơn.

## 12. Kiểm thử với JDK proxy và CGLIB proxy

Nên tổ chức một ma trận test:

| Tình huống | Kiểu proxy | Metadata cần xác nhận |
| --- | --- | --- |
| Baseline | Không proxy | Attributes/operations đúng |
| Transaction advice | JDK proxy | Metadata không mất |
| Transaction advice | Class-based proxy | Metadata không mất |
| Custom logging aspect | JDK proxy | ObjectName và descriptions ổn định |
| Custom logging aspect | Class-based proxy | Signature và flags ổn định |
| Async service | Proxy theo config | Metadata adapter ổn định, async chạy qua proxy |

Trong mỗi test:

1. Khởi động một ApplicationContext cô lập.
2. Xác nhận loại proxy thực tế (không chỉ tin vào flag cấu hình).
3. Xác minh MBean xuất hiện ở đúng ObjectName.
4. Đọc MBeanInfo và so sánh hợp đồng kỳ vọng.
5. Kiểm tra không lộ method nội bộ.
6. Nếu test advice behavior, gọi operation thử nghiệm an toàn.
7. Đóng ApplicationContext và xác minh cleanup.

**Lưu ý:** nếu adapter không chịu AOP nhưng service phía sau có proxy, bài test chứng minh metadata của adapter ổn định khi service được proxy. Để kiểm tra chính **annotated management bean** bị proxy, cần thêm một biến thể annotate trên bean chịu AOP, rồi kiểm tra exporter có xử lý đúng target/proxy theo phiên bản Spring dự án.

## 13. Test trực tiếp bean được annotate và bị AOP proxy

Giả sử annotation JMX được đặt trực tiếp trên service:

```java
@Service
@ManagedResource(
    objectName = "com.example:type=Worker,name=Direct"
)
public class DirectWorkerManagement {

    @ManagedAttribute(description = "Current queue depth")
    public long getQueueDepth() {
        return 12;
    }

    @Transactional
    @ManagedOperation(description = "Request graceful pause")
    public void requestPause() {
        // Deliberately safe action in test.
    }
}
```

Khi AOP proxy được tạo, exporter có thể nhận một object khác với target class. Một test cần chứng minh:

- MBean đăng ký với `com.example:type=Worker,name=Direct`.
- Thuộc tính `QueueDepth` vẫn xuất hiện đúng metadata.
- Operation `requestPause` vẫn có đúng description và signature.
- Không có method nội bộ bị export.
- Khi gọi `requestPause` qua JMX, Spring advice có thực sự chạy nếu đó là yêu cầu của ứng dụng.

Đừng sửa test bằng cách thay vì gọi MBeanServer thì lại gọi method trên target class: như vậy không còn kiểm thử đường JMX export thực tế.

## 14. Kiểm tra advice thực sự chạy sau JMX invocation

MBeanInfo đúng chỉ chứng minh **metadata**, không chứng minh AOP advice chạy. Nếu muốn kiểm tra transaction hoặc async, phải quan sát execution path.

### 14.1. Transaction test

Trong service method:

```java
@Transactional
public boolean isTransactionActiveOnInvocation() {
    return org.springframework.transaction.support
        .TransactionSynchronizationManager
        .isActualTransactionActive();
}
```

Test gọi qua MBeanServer:

```java
Object answer = server.invoke(
    name,
    "isTransactionActiveOnInvocation",
    new Object[0],
    new String[0]
);

if (!Boolean.TRUE.equals(answer)) {
    throw new AssertionError("Transaction advice not applied");
}
```

Điều kiện: method phải được công bố như operation quản trị thử nghiệm và có transaction manager phù hợp. Test method **không nên mang `@Transactional`** nếu điều đó có thể khiến transaction test framework có sẵn che mất lỗi advice của service.

### 14.2. Async test

Một `@Async` service có thể trả `CompletableFuture<String>` với tên thread đã chạy code:

```java
@Async("managementExecutor")
public CompletableFuture<String> workerThreadName() {
    return CompletableFuture.completedFuture(
        Thread.currentThread().getName()
    );
}
```

Adapter JMX dùng operation riêng để lấy/đọc trạng thái, hoặc trong lab có thể đợi Future với timeout nhỏ rồi trả chuỗi thread name. Assert tên thread thuộc executor được cấu hình; không chỉ assert method có annotation.

Không nên trả `CompletableFuture` như một object JMX tùy ý cho mọi client, hoặc làm operation production block nhiều phút bằng `future.get()`.

## 15. Self-invocation và lý do test có thể cho kết luận sai

Spring AOP proxy mode thường không intercept lời gọi từ method cùng object tới một method khác qua `this`:

```java
@Service
public class ExampleService {
    public void outer() {
        inner(); // Self-invocation: không đi qua Spring proxy.
    }

    @Transactional
    public void inner() {
        // Expected transactional work.
    }
}
```

Trong trường hợp này, MBean có thể công bố `outer` đúng metadata nhưng transaction ở `inner` vẫn không hoạt động. Đó là lỗi **đường gọi advice**, không phải mất metadata.

Giải pháp thường dễ bảo trì: chuyển method transaction/async sang một bean khác và inject proxy của bean đó vào adapter hoặc orchestrator.

## 16. Kiểm tra parameter metadata khi method có signature

Một operation có tham số nên kiểm tra cả tên, type và description:

```java
@ManagedOperation(
    description = "Retry up to maxTasks failed items"
)
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "maxTasks",
        description = "Maximum retry items (1..100)"
    )
})
public int retryFailedTasks(int maxTasks) {
    return maxTasks;
}
```

Test:

```java
var operation = Arrays.stream(info.getOperations())
    .filter(op -> "retryFailedTasks".equals(op.getName()))
    .findFirst()
    .orElseThrow();

var signature = operation.getSignature();
if (signature.length != 1
        || !"int".equals(signature[0].getType())
        || !"maxTasks".equals(signature[0].getName())) {
    throw new AssertionError("Parameter metadata changed");
}
```

Với JDK proxy, tên parameter Java trong bytecode không nhất thiết là tên mà JMX công bố. Annotation metadata và assembler phù hợp giúp hợp đồng rõ hơn.

## 17. Descriptor metadata và khác biệt Model MBean

Spring `MetadataMBeanInfoAssembler` thường làm việc với metadata theo mô hình Model MBean. Descriptor có thể có các field bổ sung như `currencyTimeLimit`, `role`, `descriptorType` hoặc metadata đặc thù.

Đọc runtime descriptors:

```java
System.out.println(info.getDescriptor());
for (var operation : info.getOperations()) {
    System.out.println(
        operation.getName() + " -> " + operation.getDescriptor()
    );
}
```

Test chỉ nên assert những field thực sự thuộc hợp đồng ứng dụng. Không mặc định mọi MBean có descriptor giống nhau: Standard MBean, MXBean và Model MBean có metadata khác nhau.

Đặc biệt, `currencyTimeLimit` là metadata có thể liên quan Model MBean caching, không phải timeout JMX operation và không phải giới hạn thread quản trị.

## 18. Các lỗi thường gặp khi thêm AOP

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| MBean biến mất sau khi bật AOP | Autodetection/metadata source không thấy target class hoặc exporter không chọn bean proxy | Xác định bean type, assembler và target class |
| Operation biến mất | JDK proxy không expose method, assembler xử lý proxy khác kỳ vọng | Kiểm tra interface và `MBeanInfo` |
| Description trống | Annotation source không được áp dụng hoặc metadata trên implementation không được tìm | Kiểm tra `AnnotationJmxAttributeSource` và assembler |
| ObjectName đổi | Naming strategy dựa vào tên runtime proxy | Dùng explicit ObjectName hoặc naming ổn định |
| `NotCompliantMBeanException` | Proxy object không tuân Standard MBean convention, adapter/assembler không đúng | Xuất management adapter hoặc wrapper phù hợp |
| `InstanceAlreadyExistsException` | Hai exporter hoặc hai test context trùng ObjectName | Quy định ownership, cleanup |
| JMX operation chạy nhưng transaction inactive | Self-invocation, target bypass proxy hoặc thiếu transaction manager | Test advice runtime; tách service |
| `@Async` không đổi thread | Self-invocation hoặc cấu hình executor/proxy không đúng | Assert worker thread, kiểm tra `@EnableAsync` |
| Attribute bất ngờ writable | Setter được expose bởi assembler/interface | Kiểm tra `MBeanAttributeInfo.isWritable()` |
| Không tìm thấy MBean ở platform server | Exporter dùng custom MBeanServer | Đọc đúng server của exporter |
| Test pass khi chạy riêng, fail khi chạy song song | ObjectName trùng, platform registry dùng chung | Isolate context/ObjectName |

## 19. Integration test lifecycle

Trong Spring Test, một test cần kiểm tra lifecycle:

1. Khởi tạo context với exporter và AOP configuration.
2. Assert bean nằm trong context và loại proxy đúng kỳ vọng.
3. Assert `MBeanServer.isRegistered(name)`.
4. Assert metadata đầy đủ như phần trên.
5. Nếu an toàn, invoke một operation probe và kiểm tra advice hoạt động.
6. Đóng context.
7. Assert MBean do exporter sở hữu đã unregister.

Không unregister MBean của ứng dụng khác chỉ để dọn test. Khi dùng platform MBeanServer toàn JVM, ObjectName nên độc lập giữa các test suites để không gây race.

Ví dụ kiểm tra đăng ký và cleanup:

```java
ObjectName name = new ObjectName(
    "com.example.tests:type=Worker,name=ProxyMetadata"
);

try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext()) {
    context.register(TestJmxConfiguration.class);
    context.refresh();

    if (!server.isRegistered(name)) {
        throw new AssertionError("MBean not registered");
    }
    MBeanInfo info = server.getMBeanInfo(name);
    assertExpectedContract(info);
}

if (server.isRegistered(name)) {
    throw new AssertionError("MBean not cleaned after close");
}
```

`TestJmxConfiguration` và `assertExpectedContract` là các thành phần do bài test định nghĩa, không phải class API có sẵn. Test phải sử dụng đúng ObjectName do configuration khai báo.

## 20. Không so sánh metadata bằng thứ tự thô

`MBeanInfo.getAttributes()` và `getOperations()` trả arrays, nhưng thứ tự có thể thay đổi theo implementation/assembler/reflection. Một test snapshot so sánh string dump nguyên thứ tự có thể báo false failure khi chức năng không đổi.

Khuyến nghị tạo tập key chuẩn hóa:

```text
Attribute key:
  name + type + readable + writable

Operation key:
  name + ordered parameter types + return type
```

Description và descriptors nên được assert riêng nếu thuộc hợp đồng ổn định cần duy trì.

### 20.1. Vì sao không assert mọi field?

Một số field mô tả, class name nội bộ hoặc descriptor defaults có thể khác giữa Spring/JDK versions. Chỉ cố định những gì client phụ thuộc và những gì liên quan bảo mật. Không nên bỏ qua kiểm tra bề mặt thừa: một operation ngoài allowlist là thay đổi quan trọng, kể cả khi các operation cũ vẫn còn.

## 21. So sánh baseline và phiên bản AOP

Một chiến lược test có thể tạo hai context **tách biệt**:

```text
Context A:
  bean không AOP
  -> MBeanInfo baseline

Context B:
  bean có AOP
  -> MBeanInfo proxied

Normalize contract:
  attribute keys
  operation keys
  descriptions quan trọng
  forbidden operation check

Compare:
  baseline == proxied
```

Nếu dùng platform MBeanServer chung, phải đóng A trước khi mở B hoặc dùng các ObjectName riêng để tránh registration conflict. Nếu cả hai context cùng chạy, đừng dựa vào registration policy `REPLACE_EXISTING` để test dễ pass.

**Không mặc định baseline là đúng về bảo mật.** Cần có expected allowlist độc lập: nếu baseline đã lộ method nhạy cảm thì so sánh bằng nhau chỉ bảo tồn lỗi đó.

## 22. Bảo mật khi proxy làm thay đổi export surface

Metadata bị mất có thể làm monitoring lỗi. Nhưng metadata bị **mở rộng ngoài ý định** còn nguy hiểm hơn:

- Thêm một public method vào service có thể bị reflective assembler công bố.
- Một getter nội bộ có thể lộ configuration secret.
- Một operation debug có thể cho phép xóa cache hoặc thay đổi trạng thái.
- Một JMX proxy có thể giữ kết nối tới ObjectName cũ nếu registry đã thay đổi.
- Quyền connector readwrite có thể cho phép thao tác trên nhiều MBeans, không chỉ bean mới.

Vì vậy test cần cả **positive assertions** (đúng method phải có) và **negative assertions** (method bị cấm phải không có).

Spring Security trên HTTP không tự bảo vệ JMX/RMI connector. Remote JMX cần authentication, TLS, giới hạn mạng và authorization theo connector/server. Annotation `@ManagedOperation` không là rule phân quyền.

## 23. Tổ chức kiểm thử trong CI

Một bộ test tối thiểu:

| Test | Mục tiêu |
| --- | --- |
| Bean proxy classification | Chứng minh JDK/CGLIB proxy thực tế được tạo |
| Export registration | MBean có đúng ObjectName |
| Attribute contract | Tên, kiểu, readable/writable |
| Operation contract | Tên, parameter types, return types |
| Description contract | Mô tả không mất khi proxy |
| Negative export test | Không lộ API nội bộ |
| Advice behavior | Transaction/async thật sự chạy qua proxy |
| Lifecycle cleanup | Không giữ MBean sau context close |
| Cross-version smoke test | Phát hiện thay đổi khi nâng Spring/JDK |

Nếu test chạy song song, có thể dùng custom `MBeanServer` riêng cho mỗi test context hoặc `ObjectName` duy nhất; tránh để nhiều test tranh tên trong platform server.

Đừng chỉ test với mocks không tạo AOP proxy: các mocks có thể bỏ qua chính cơ chế cần xác minh. Unit test giúp kiểm tra logic nhỏ, nhưng muốn chứng minh JMX + AOP phải có integration test với exporter thực và MBeanInfo runtime.

## 24. Bài tập thực hành

### Bài tập 1 — Baseline metadata

Tạo `@ManagedResource` có một attribute read-only và một operation. Export, đọc MBeanInfo và viết expected contract.

**Mục tiêu:** biết lấy hợp đồng JMX từ runtime.

### Bài tập 2 — JDK proxy

Thêm interface và transaction advice để tạo JDK proxy. Assert loại proxy bằng `AopUtils`, đọc MBeanInfo và so sánh baseline.

**Mục tiêu:** nhận diện tác động của proxy interface.

### Bài tập 3 — CGLIB proxy

Bật class-based proxy trong test context riêng. So sánh metadata và behavior với JDK proxy.

**Mục tiêu:** hiểu target class, subclass proxy và method interception.

### Bài tập 4 — Annotation trên implementation

Đặt `@ManagedOperation` chỉ ở implementation, rồi chạy JDK proxy. Quan sát có operation xuất hiện hay không theo assembler/source đang dùng; thử đổi sang management adapter.

**Mục tiêu:** phát hiện cấu hình nhạy với vị trí annotation.

### Bài tập 5 — Negative export

Thêm public method `deleteInternalState()` không annotate. Assert method không xuất hiện trong operations sau khi thêm AOP.

**Mục tiêu:** ngăn rò rỉ API nội bộ.

### Bài tập 6 — Transaction behavior

Thêm operation probe trả trạng thái `TransactionSynchronizationManager.isActualTransactionActive()` trong service có transaction manager. Gọi qua JMX và assert true.

**Mục tiêu:** phân biệt metadata được giữ với advice thực sự chạy.

### Bài tập 7 — Async behavior

Đưa công việc vào `@Async` service có named executor. Từ JMX adapter gọi service và kiểm tra thread worker trong test.

**Mục tiêu:** ngăn false positive do self-invocation hoặc executor đồng bộ.

### Bài tập 8 — Cleanup

Khởi tạo và đóng context nhiều lần với ObjectName riêng, xác nhận không rò registry.

**Mục tiêu:** bảo đảm ổn định khi CI chạy lặp hoặc song song.

## 25. Câu hỏi ôn tập

**1. Vì sao cần kiểm thử MBeanInfo khi bật AOP?** Vì proxy có thể thay đổi object/type mà exporter/assembler introspect, ảnh hưởng metadata được công bố.

**2. JDK proxy khác CGLIB proxy ở điểm nào?** JDK proxy thường expose interface methods; CGLIB tạo subclass của target class theo những giới hạn của class-based proxy.

**3. Có `@ManagedOperation` trên source đã đủ chưa?** Chưa. Cần exporter/assembler phù hợp và kiểm tra runtime MBeanInfo.

**4. Metadata đúng có chứng minh advice chạy không?** Không. Cần test behavior qua đường JMX.

**5. Vì sao self-invocation thường bỏ qua transaction advice?** Vì lời gọi `this.method()` không đi qua Spring proxy.

**6. Làm sao chứng minh một operation không bị lộ?** Kiểm tra negative assertion trên danh sách operations và, với DynamicMBean, behavior invoke.

**7. Có nên kiểm tra đúng thứ tự operations không?** Thường không; dùng key theo tên và signature.

**8. Khi MBean không xuất hiện, chỉ nên đổ lỗi cho AOP?** Không. Cần kiểm tra exporter, ObjectName, naming strategy, MBeanServer và registration policy.

**9. Tại sao không dùng `REPLACE_EXISTING` để giải quyết mọi test conflict?** Vì có thể thay MBean của context khác và che lỗi ownership.

**10. Thiết kế dễ giữ metadata ổn định là gì?** Một JMX management adapter nhỏ, gọi business services qua Spring proxies.

## 26. Tổng kết

**Kiểm thử proxy hoặc AOP không làm mất metadata** là kiểm thử hợp đồng JMX sau khi Spring đã tạo các proxies và exporter đã đăng ký MBean. Không chỉ nhìn annotation hoặc class gốc: phải đọc `MBeanServer.getMBeanInfo(...)` trên đúng MBeanServer để khẳng định attributes, operations, signature, descriptions và khả năng read/write còn nguyên như mong đợi.

Khi thêm `@Transactional`, `@Async` hoặc aspects, hãy kiểm tra cả **metadata runtime** và **đường thực thi advice**. Kết hợp positive/negative contract tests, tách adapter quản trị khỏi service nghiệp vụ khi cần và quản lý lifecycle/ObjectName để tránh lỗi registration trong CI.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework Javadoc — `AopUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `MetadataMBeanInfoAssembler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html