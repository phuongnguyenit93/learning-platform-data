# Ảnh hưởng của proxy hoặc decorator tới việc nhận diện MBean

## Mục tiêu

Sau bài học, bạn có thể giải thích vì sao một đối tượng Java triển khai đúng interface MBean nhưng vẫn bị JMX từ chối đăng ký sau khi được bọc bằng proxy hoặc decorator; phân biệt các quy tắc nhận diện của Standard MBean, MXBean và Spring JMX exporter; lựa chọn cách xuất MBean rõ ràng; và chẩn đoán các lỗi như `NotCompliantMBeanException`, `InstanceAlreadyExistsException` hoặc thiếu attribute/operation trong `MBeanInfo`.

## 1. JMX nhìn thấy đối tượng nào?

JMX đăng ký **đối tượng thực tế được truyền vào `MBeanServer.registerMBean`**, tức kiểu runtime và hợp đồng quản trị mà hệ thống nhận diện từ đối tượng đó. Kiểu nguồn trong code không phải lúc nào cũng là kiểu của object đi qua ranh giới đăng ký.

Ví dụ đơn giản:

```java
public interface PaymentMonitorMBean {
    int getPendingPayments();
    void retryFailedPayments();
}

public class PaymentMonitor implements PaymentMonitorMBean {
    @Override
    public int getPendingPayments() {
        return 12;
    }

    @Override
    public void retryFailedPayments() {
        System.out.println("Retry requested");
    }
}
```

Đối tượng trực tiếp:

```java
PaymentMonitor target = new PaymentMonitor();
server.registerMBean(target, objectName);
```

Với Standard MBean, cặp `PaymentMonitor` / `PaymentMonitorMBean` tuân theo quy ước tên. JMX có thể nhận diện giao diện quản trị của class đích.

Nhưng sau khi được Spring AOP, thư viện instrumentation, decorator hoặc một proxy tự viết bọc lại:

```text
Client / MBeanServer
         |
         v
      Proxy object
         |
         v
    Target object
       PaymentMonitor
```

Class được đưa vào đăng ký có thể là class proxy phát sinh động thay vì `PaymentMonitor`. Dù các lời gọi nghiệp vụ vẫn chạy đúng, bước nhận diện MBean dựa trên **kiểu runtime và các interface có thể nhìn thấy**. Vì thế, khả năng gọi method qua proxy không tự động bảo đảm JMX sẽ công bố đúng metadata.

## 2. Standard MBean và quy ước interface

Một Standard MBean thông thường dùng interface public có tên `<ConcreteClassName>MBean` và một class triển khai interface đó.

```java
public interface WorkerManagerMBean {
    int getActiveWorkers();
    void pause();
}

public class WorkerManager implements WorkerManagerMBean {
    @Override
    public int getActiveWorkers() {
        return 4;
    }

    @Override
    public void pause() {
        // Quản lý worker
    }
}
```

Nếu đăng ký trực tiếp một `WorkerManager`, quy ước tên có thể được nhận diện. Tuy nhiên, proxy runtime có class như `jdk.proxy2.$Proxy...` hoặc `WorkerManager$$SpringCGLIB$$...`; class proxy này không nhất thiết có interface tên tương ứng với class proxy.

Những hệ quả thường gặp:

- `registerMBean(proxy, name)` có thể ném `NotCompliantMBeanException` vì không nhận diện được Standard MBean hoặc MXBean hợp lệ.
- Đối tượng có thể được đăng ký, nhưng giao diện quản trị mà JMX lựa chọn không đúng với kỳ vọng.
- Proxy chỉ công bố một tập interface; interface `WorkerManagerMBean` có thể không nằm trong các interface được proxy đưa ra.
- Decorator triển khai interface nghiệp vụ nhưng không triển khai interface MBean nên hợp đồng JMX có thể biến mất ở đối tượng ngoài cùng.

Một cách làm rõ ranh giới là dùng `javax.management.StandardMBean` để chỉ định interface quản trị, giảm phụ thuộc vào quy ước class runtime:

```java
import javax.management.StandardMBean;

WorkerManager target = new WorkerManager();
StandardMBean managed = new StandardMBean(
    target, WorkerManagerMBean.class
);
server.registerMBean(managed, objectName);
```

Constructor `StandardMBean(implementation, interface)` yêu cầu implementation phù hợp interface khai báo. Nếu bạn truyền proxy làm implementation thì proxy cũng phải triển khai interface đó. Việc chỉ định interface giải quyết phần hợp đồng nhận diện, nhưng **không tự làm proxy có thêm method hoặc sửa lỗi wiring**.

## 3. JDK Dynamic Proxy: chỉ công bố các interface đã chọn

JDK dynamic proxy triển khai danh sách interface được chỉ định; nó không kế thừa class đích. Ví dụ:

```java
import java.lang.reflect.Proxy;

WorkerManager target = new WorkerManager();

WorkerManagerMBean proxy = (WorkerManagerMBean) Proxy.newProxyInstance(
    WorkerManagerMBean.class.getClassLoader(),
    new Class<?>[] { WorkerManagerMBean.class },
    (p, method, args) -> method.invoke(target, args)
);
```

Proxy trên là một object khác với `WorkerManager`, nhưng vẫn `instanceof WorkerManagerMBean`. Tuy nhiên, class của proxy không mang tên `WorkerManager`, nên đừng dựa vào quy ước Standard MBean theo tên class của target để đăng ký proxy trực tiếp.

Đăng ký với interface tường minh:

```java
StandardMBean exposed = new StandardMBean(
    proxy, WorkerManagerMBean.class
);
server.registerMBean(exposed, objectName);
```

Khi `MBeanServer` gọi operation qua wrapper, lời gọi được chuyển tới proxy rồi tới target. Điều này có thể quan trọng nếu proxy áp dụng bảo mật, transaction, tracing hoặc các aspect khác.

Cần chú ý:

1. Proxy chỉ triển khai interface `BusinessService` mà không triển khai `WorkerManagerMBean` thì `new StandardMBean(proxy, WorkerManagerMBean.class)` không phù hợp và không thể ép kiểu an toàn.
2. Nếu expose target thay proxy, lời gọi JMX đi thẳng vào target và có thể **bỏ qua logic của advice**.
3. Nếu expose proxy, các operation phải được proxy thực sự hỗ trợ, bao gồm chữ ký getter/setter attribute.
4. Java reflection handler trong ví dụ có thể bọc exception trong `InvocationTargetException`; code sản xuất nên tháo lớp bọc và truyền lỗi theo hợp đồng.

## 4. CGLIB/Class-based Proxy: kế thừa class nhưng không bảo đảm nhận diện giống nhau

Spring AOP có thể tạo class proxy dựa trên subclass. Proxy này thường là subtype của class đích và có thể kế thừa các interface mà class đích triển khai.

```text
WorkerManager
      ^
      |
WorkerManager$$SpringCGLIB$$...
```

Điều này có thể giúp proxy còn tương thích với `WorkerManagerMBean`, nhưng tên class runtime đã thay đổi. Khả năng JMX tự nhận diện tên interface theo quy ước không nên được suy luận chỉ từ `instanceof`.

Ví dụ kiểm tra tại runtime:

```java
Object bean = applicationContext.getBean("workerManager");

System.out.println(bean.getClass().getName());
System.out.println(bean instanceof WorkerManagerMBean);
```

Nếu dùng Spring AOP:

```java
import org.springframework.aop.support.AopUtils;

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

Các API này giúp phân biệt proxy class và target class, nhưng không thay thế kiểm tra `MBeanInfo` sau khi đăng ký. Spring và JMX có thể dùng chiến lược chọn giao diện khác nhau theo cấu hình.

Với CGLIB, còn có giới hạn kỹ thuật như class/method `final`, khả năng subclass và visibility; một method `final` không được CGLIB advice theo cơ chế override. Nếu một operation quản trị phải được bảo vệ bởi aspect, cần xác nhận lời gọi qua JMX thật sự đi qua advice.

## 5. Decorator: interface MBean có được chuyển tiếp không?

Decorator là object bọc và chuyển tiếp lời gọi tới một object khác, có thể được viết thủ công mà không sử dụng proxy framework.

```java
public interface WorkerService {
    void pause();
}

public class WorkerServiceImpl implements WorkerService, WorkerManagerMBean {
    @Override public int getActiveWorkers() { return 4; }
    @Override public void pause() { /* ... */ }
}

public class AuditedWorkerDecorator implements WorkerService {
    private final WorkerService delegate;

    public AuditedWorkerDecorator(WorkerService delegate) {
        this.delegate = delegate;
    }

    @Override public void pause() {
        System.out.println("Audit");
        delegate.pause();
    }
}
```

`AuditedWorkerDecorator` chỉ triển khai `WorkerService`, do đó **không công bố `getActiveWorkers()` qua interface MBean**. Đăng ký decorator trực tiếp có thể không được JMX nhận diện theo hợp đồng mong đợi.

Một decorator chuyên cho JMX có thể triển khai đầy đủ interface quản trị:

```java
public class AuditedWorkerMBean implements WorkerManagerMBean {
    private final WorkerManagerMBean delegate;

    public AuditedWorkerMBean(WorkerManagerMBean delegate) {
        this.delegate = delegate;
    }

    @Override
    public int getActiveWorkers() {
        return delegate.getActiveWorkers();
    }

    @Override
    public void pause() {
        System.out.println("Audit JMX pause");
        delegate.pause();
    }
}
```

Đăng ký với wrapper tường minh:

```java
WorkerManagerMBean audited = new AuditedWorkerMBean(
    new WorkerManager()
);
server.registerMBean(
    new StandardMBean(audited, WorkerManagerMBean.class),
    objectName
);
```

Cách này bảo toàn hợp đồng quản trị và giữ được logic audit trong đường đi của lời gọi. Nên đảm bảo audit/security nằm ở lớp phù hợp với mục tiêu vận hành; một decorator nghiệp vụ không nhất thiết phù hợp để bảo vệ remote JMX nếu có đường gọi khác.

## 6. MXBean cũng chịu tác động của proxy

MXBean sử dụng các quy tắc đặt tên interface kết thúc bằng `MXBean`, annotation `@MXBean` hoặc khai báo MXBean rõ ràng qua `StandardMBean`. MXBean còn áp dụng cơ chế mapping kiểu Java sang Open Types.

Ví dụ:

```java
public interface WorkerStatsMXBean {
    long getCompletedTasks();
    void resetCounters();
}

public class WorkerStats implements WorkerStatsMXBean {
    @Override
    public long getCompletedTasks() {
        return 18;
    }

    @Override
    public void resetCounters() {
        // Reset thống kê
    }
}
```

Khi bọc bằng proxy, cần bảo đảm object expose thực sự triển khai `WorkerStatsMXBean`. Nếu việc nhận diện tự động không phù hợp, dùng constructor chỉ định chế độ MXBean:

```java
WorkerStatsMXBean exposed = new WorkerStats();
StandardMBean wrapper = new StandardMBean(
    exposed, WorkerStatsMXBean.class, true
);
server.registerMBean(wrapper, objectName);
```

Tham số `true` yêu cầu xử lý như MXBean. Trong ví dụ, `WorkerStatsMXBean` chỉ có primitive, nên phù hợp với Open Type mapping.

Không nhầm hai vấn đề:

- **Nhận diện interface:** JMX có biết phải dùng `WorkerStatsMXBean` không?
- **Ánh xạ kiểu:** Getter/operation trong interface MXBean có dùng kiểu được quy tắc MXBean hỗ trợ không?

Một proxy đã được nhận diện đúng vẫn có thể gặp lỗi mapping do interface chứa kiểu không hợp lệ. Ngược lại, interface dùng kiểu đơn giản vẫn có thể không được phát hiện nếu proxy không công bố interface.

## 7. Spring Framework JMX: exporter, metadata và proxy

Spring có thể export MBean bằng `org.springframework.jmx.export.MBeanExporter`. Đối với bean Spring được AOP bọc, quá trình export cần xét cả kiểu của proxy và thông tin annotation/target class.

Một bean được đánh dấu:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.worker:type=WorkerManager",
    description = "Worker management"
)
public class WorkerManagerResource {

    @ManagedAttribute
    public int getActiveWorkers() {
        return 4;
    }

    @ManagedOperation
    public void pause() {
        // Pause service
    }
}
```

Spring metadata assembler, annotation source và exporter có thể công bố các method được khai báo trong metadata. Nếu bean bị proxy, khả năng exporter truy xuất annotation trên target, khả năng method được proxy expose, và cấu hình exporter đều ảnh hưởng đến kết quả.

Không nên suy luận rằng một `@ManagedResource` trên class đích luôn đủ để mọi JDK proxy có thể được xuất như mong đợi. Cần kiểm tra behavior theo cấu hình Spring đang dùng.

Ví dụ cấu hình exporter dùng annotation:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {
    @Bean
    public MBeanExporter mBeanExporter() {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);

        return exporter;
    }
}
```

Đây là cấu hình Spring Framework minh họa. Trong ứng dụng dùng `@EnableMBeanExport`, Spring Boot auto-configuration hoặc XML namespace, cần tránh tạo thêm exporter gây đăng ký trùng. Kiểm tra chính xác exporter nào đang hoạt động và `ObjectName` nào được đăng ký.

### Vì sao annotation có thể không xuất hiện?

Giả sử annotation đặt trên một method cụ thể của class đích, nhưng JDK proxy chỉ công bố một interface không chứa method đó. Metadata assembler có thể đọc được thông tin target, song lời gọi qua proxy không có method tương ứng. Các vấn đề có thể xảy ra trong quá trình introspection hoặc invocation.

Các hướng xử lý thường gặp:

1. Công bố một interface quản trị tường minh mà proxy triển khai.
2. Chọn JDK proxy hay class-based proxy dựa trên hợp đồng cần expose, hiểu giới hạn advice.
3. Xuất một adapter MBean chuyên dụng thay vì cả service proxy.
4. Dùng `StandardMBean`/MXBean wrapper nếu muốn kiểm soát interface quản trị của JMX.
5. Kiểm tra `MBeanInfo` thực tế và thực hiện `getAttribute`/`invoke` thay vì chỉ xác nhận bean có annotation.

## 8. Adapter MBean: tách hẳn API quản trị khỏi đối tượng proxied

Trong ứng dụng Spring, một mẫu thiết kế rõ ràng là giữ service nghiệp vụ sau proxy và tạo adapter riêng cho JMX.

```java
public interface BillingService {
    int pendingCount();
    void retryFailures(int limit);
}
```

```java
public interface BillingAdminMBean {
    int getPendingCount();
    void retryFailures(int limit);
}
```

```java
public final class BillingAdmin implements BillingAdminMBean {
    private final BillingService service;

    public BillingAdmin(BillingService service) {
        this.service = service;
    }

    @Override
    public int getPendingCount() {
        return service.pendingCount();
    }

    @Override
    public void retryFailures(int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit out of range");
        }
        service.retryFailures(limit);
    }
}
```

Đăng ký adapter như một Standard MBean riêng:

```java
BillingAdmin admin = new BillingAdmin(billingServiceProxy);
server.registerMBean(
    new StandardMBean(admin, BillingAdminMBean.class),
    new ObjectName("com.example.billing:type=Admin")
);
```

Luồng gọi:

```text
JMX client
    |
    v
BillingAdmin (MBean contract)
    |
    v
BillingService proxy (security / transaction / tracing)
    |
    v
BillingService implementation
```

Ưu điểm là JMX có hợp đồng tường minh, ổn định; các method của service không bị công bố vô ý; Spring proxy vẫn nằm trong chuỗi lời gọi; và adapter có thể giới hạn tham số/kiểu dữ liệu phù hợp remote JMX.

Nếu tổ chức dùng Spring `@ManagedResource`, có thể đánh dấu adapter và export nó qua `MBeanExporter`. Tránh đồng thời đăng ký cùng adapter thủ công và qua exporter tự động dưới cùng `ObjectName`.

## 9. Dùng MBeanInfo để xác nhận hợp đồng thực tế

Sau đăng ký, đừng chỉ kiểm tra `isRegistered(name)`. Hãy đọc metadata:

```java
import javax.management.*;

MBeanInfo info = server.getMBeanInfo(objectName);

System.out.println("MBean class: " + info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute %s [%s] read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation %s -> %s%n",
        operation.getName(),
        operation.getReturnType()
    );
}
```

Nếu `getPendingCount()` được công bố như attribute, client đọc bằng:

```java
Object count = server.getAttribute(objectName, "PendingCount");
```

Nếu `retryFailures(int)` là operation:

```java
server.invoke(
    objectName,
    "retryFailures",
    new Object[] { 10 },
    new String[] { "int" }
);
```

Các cờ attribute (readable/writable), tên operation, loại tham số và notification được xác định bởi MBean đã đăng ký. Các proxy/adapter có thể làm metadata khác với toàn bộ method public trên class đích.

Kiểm tra cả hiệu ứng mong muốn của operation: nếu cần transaction/security, hãy xác nhận gọi từ JMX thực sự đi qua proxy tương ứng. `MBeanInfo` chứng minh khả năng khám phá interface, không tự chứng minh một aspect đã chạy.

## 10. Chuỗi chẩn đoán khi đăng ký thất bại

### Trường hợp A: NotCompliantMBeanException

Ví dụ lỗi:

```text
javax.management.NotCompliantMBeanException
```

Nguyên nhân thường là object không thỏa quy ước Standard MBean, MXBean hay Dynamic MBean. Đặc biệt lưu ý class proxy runtime và các interface nó triển khai.

Hướng xử lý:

```java
Object candidate = context.getBean("workerManager");

System.out.println(candidate.getClass());
System.out.println(
    java.util.Arrays.toString(candidate.getClass().getInterfaces())
);
System.out.println(candidate instanceof WorkerManagerMBean);
```

Nếu interface MBean tồn tại trên proxy, thử đăng ký qua wrapper tường minh. Nếu không, thiết kế adapter hoặc cấu hình proxy phù hợp.

### Trường hợp B: InstanceAlreadyExistsException

```text
javax.management.InstanceAlreadyExistsException
```

Điều này có nghĩa đã tồn tại MBean với cùng `ObjectName` trong `MBeanServer`. Có thể do cùng bean được export hai lần, nhiều exporter hoặc lifecycle cũ chưa unregister.

Xử lý bằng cách xác định đúng owner và một cơ chế đăng ký duy nhất; không đặt thêm UUID ngẫu nhiên chỉ để tránh lỗi xung đột.

### Trường hợp C: MBean đăng ký được nhưng thiếu operation

Kiểm tra xem interface mà proxy expose có method đó không. Đối với Spring annotation, xác minh annotation source/assembler và cách exporter chọn metadata. Với Standard MBean, chỉ các method theo giao diện quản trị được công bố.

### Trường hợp D: Operation chạy nhưng aspect không áp dụng

Nếu MBean giữ reference tới target gốc, lời gọi có thể bỏ qua proxy. Truy lại đối tượng mà adapter dùng làm delegate; nếu cần aspect thì delegate nên là Spring proxy đúng interface, hoặc dùng cơ chế bảo vệ độc lập ở ranh giới JMX.

### Trường hợp E: Lỗi kiểu dữ liệu MXBean

Nếu metadata nhận diện được interface nhưng báo lỗi ánh xạ kiểu, vấn đề có thể nằm ở quy tắc Open Types, DTO, generic hoặc constructor mapping, không phải bản thân AOP proxy. Xử lý từng lớp vấn đề theo dấu hiệu thực tế.

## 11. Những lưu ý về bảo mật và vòng đời

Đăng ký proxy hay target là quyết định có hậu quả vận hành:

- **Security advice:** nếu bảo mật áp dụng ở Spring AOP proxy, đăng ký target trực tiếp có thể cho phép đường gọi JMX vượt qua advice đó. Remote JMX cần cấu hình authentication/authorization độc lập.
- **Transaction advice:** operation gọi qua target trực tiếp có thể không tạo transaction như khi gọi qua Spring proxy.
- **Exception handling:** method thực thi qua reflection hoặc proxy có thể tạo exception wrapper. Cần phân biệt lỗi nghiệp vụ, lỗi JMX và lỗi proxy.
- **Lifecycle:** exporter hoặc component đăng ký phải unregister MBean khi context đóng; nhiều lần đăng ký cùng `ObjectName` trong một JVM cần owner rõ ràng.
- **Thông tin nhạy cảm:** chỉ công bố các attribute và operation thật sự cần quản trị, dùng kiểu dữ liệu đơn giản hoặc MXBean/Open Data khi phù hợp.
- **Performance:** getter JMX có thể bị client poll liên tục; advice tracing/transaction trên getter có thể tăng overhead.

Một adapter JMX rõ ràng là lựa chọn tốt khi hệ thống có nhiều Spring aspects và cần hợp đồng quản trị dễ bảo trì.

## 12. Ví dụ thực hành: so sánh ba con đường đăng ký

Giả sử `WorkerManager` triển khai `WorkerManagerMBean`.

**A. Đăng ký trực tiếp target:**

```java
server.registerMBean(new WorkerManager(), name);
```

Cách này phù hợp khi không cần Spring proxy trên đường gọi JMX và class tuân theo quy ước Standard MBean.

**B. Đăng ký JDK proxy bằng wrapper:**

```java
WorkerManagerMBean proxied = /* proxy triển khai WorkerManagerMBean */;
server.registerMBean(
    new StandardMBean(proxied, WorkerManagerMBean.class), name
);
```

Cách này giữ proxy trong luồng gọi và công bố hợp đồng interface tường minh.

**C. Đăng ký adapter riêng:**

```java
BillingAdmin admin = new BillingAdmin(billingServiceProxy);
server.registerMBean(
    new StandardMBean(admin, BillingAdminMBean.class),
    new ObjectName("com.example.billing:type=Admin")
);
```

Cách này dùng khi service nghiệp vụ không muốn triển khai MBean interface và cần giới hạn rõ khả năng JMX.

Khi triển khai thật, chọn một đường đăng ký cho mỗi `ObjectName` và dùng `MBeanInfo` để kiểm tra interface mà client nhìn thấy.

## 13. Bài tập

1. Viết `WorkerManagerMBean` và `WorkerManager`. Đăng ký trực tiếp rồi in `MBeanInfo.getAttributes()` và `getOperations()`.
2. Tạo JDK proxy chỉ triển khai `WorkerManagerMBean`; đăng ký thông qua `StandardMBean`. Gọi `pause` qua `MBeanServer.invoke`.
3. Tạo decorator chỉ triển khai `WorkerService`. Giải thích vì sao nó không tự thỏa hợp đồng `WorkerManagerMBean`; chuyển sang adapter hoặc decorator triển khai interface MBean.
4. Tạo Spring AOP proxy cho một service có thao tác cập nhật. Dùng adapter JMX delegate vào Spring proxy, xác nhận aspect chạy khi gọi qua JMX.
5. Tạo một `@ManagedResource` trong Spring, kiểm tra các attribute và operation thực tế sau khi exporter đăng ký. Thử thay đổi proxy mode và ghi nhận metadata thay đổi nếu có.

## 14. Câu hỏi tự kiểm tra

- Vì sao một object triển khai interface nghiệp vụ vẫn có thể không được nhận diện là Standard MBean?
- JDK proxy và CGLIB proxy khác nhau thế nào về kiểu runtime và interface?
- `StandardMBean` giúp xử lý trường hợp nhận diện interface của proxy ra sao?
- Điều gì xảy ra nếu expose target thay vì Spring proxy khi transaction/security nằm trong advice?
- Vì sao annotation `@ManagedResource` chưa đủ để kết luận client chắc chắn thấy mọi operation?
- Cách nào cho phép giữ proxy nghiệp vụ nhưng có hợp đồng JMX riêng, ổn định?

**Ghi nhớ:** JMX đăng ký đối tượng được cung cấp ở runtime. Proxy hoặc decorator có thể thay đổi kiểu, interface và đường gọi mà JMX nhìn thấy. Hãy công bố giao diện MBean tường minh bằng `StandardMBean`, MXBean hoặc adapter khi cần; đăng ký đúng object để giữ các advice quan trọng; và xác nhận hợp đồng thực tế bằng `MBeanInfo`.