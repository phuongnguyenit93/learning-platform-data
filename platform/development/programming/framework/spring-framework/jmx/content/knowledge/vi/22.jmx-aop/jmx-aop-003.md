# Target-class proxy và cờ proxy-target-class trong Spring AOP kết hợp JMX

## 1. Mục tiêu

Spring AOP sử dụng proxy để áp dụng các hành vi xuyên suốt như transaction, security, logging, caching hoặc metrics quanh lời gọi method. Trong ứng dụng Spring Framework JMX, một bean được export thành MBean cũng có thể đang là **AOP proxy**. Khi đó cần hiểu proxy thực sự thuộc kiểu nào, nó có expose interface hay class implementation và cách Spring JMX xác định những method cần đưa ra quản trị.

Chủ đề này giải thích sự khác nhau giữa **JDK dynamic proxy (interface-based)** và **class-based proxy (thường dùng CGLIB)**, ý nghĩa của `proxy-target-class`, và tác động đến `MBeanExporter`, `@ManagedResource`, assembler, naming strategy và khả năng nhìn thấy method trong JMX.

**Điểm cốt lõi:** `proxy-target-class=true` chỉ đạo các cơ chế tạo AOP proxy liên quan ưu tiên proxy dựa trên **class mục tiêu** thay vì chỉ proxy theo interface khi thích hợp. Đây **không phải** một công tắc bảo đảm mọi method của target được export qua JMX, cũng không tự tạo MBean hoặc thay đổi authorization của JMX connector.

## 2. Hai kiểu proxy phổ biến của Spring AOP

### 2.1. JDK dynamic proxy: proxy qua interface

Giả sử một service có interface:

```java
public interface PaymentService {
    void processPayment(String paymentId);
    long getProcessedCount();
}
```

Implementation:

```java
@Service
public class DefaultPaymentService implements PaymentService {
    @Override
    public void processPayment(String paymentId) {
        // Thực hiện nghiệp vụ.
    }

    @Override
    public long getProcessedCount() {
        return 42L;
    }

    public void clearInternalCache() {
        // Method không nằm trong PaymentService.
    }
}
```

Khi Spring tạo **JDK dynamic proxy**, object proxy chủ yếu triển khai các interface được cấu hình. Với `PaymentService`, caller có thể gọi `processPayment` và `getProcessedCount` thông qua interface, nhưng không thể xem proxy như một instance của `DefaultPaymentService` bằng cách cast thông thường.

```text
Caller -> JDK Proxy implements PaymentService
                    |
                    v
          DefaultPaymentService target
```

Method `clearInternalCache()` thuộc concrete class và không được định nghĩa trong `PaymentService`; một JDK proxy chỉ biểu diễn các interface của nó không cho client gọi trực tiếp method này qua kiểu proxy.

### 2.2. Target-class proxy: proxy qua concrete class

Với class-based proxy, Spring thường tạo subclass proxy bằng CGLIB. Một proxy như vậy có thể giữ kiểu tương thích với concrete target class, cho phép code injection theo concrete type trong nhiều trường hợp.

```text
Caller -> CGLIB subclass of DefaultPaymentService
                    |
                    v
           DefaultPaymentService target
```

Class-based proxy có các giới hạn đáng chú ý:

- Class `final` không thể được subclass để tạo proxy theo class.
- Method `final` hoặc `private` không thể được override để advice theo kiểu subclass.
- Các method không thể override vì phạm vi truy cập cũng có thể không được advice.
- Self-invocation (`this.someMethod()`) thông thường không đi qua AOP proxy, nên có thể bỏ qua advice.
- Việc tạo proxy có thể tương tác với constructor, visibility, module system và các framework khác.

**Proxy theo class không đồng nghĩa toàn bộ target class được AOP advice**: khả năng chặn lời gọi còn tùy advisor, pointcut, tính override của method và đường gọi.

## 3. proxy-target-class nghĩa là gì?

Trong cấu hình Spring, thuộc tính `proxy-target-class` cho biết nên ưu tiên sử dụng class-based proxy khi tạo AOP proxies cho cơ chế được cấu hình.

Ví dụ XML:

```xml
<aop:config proxy-target-class="true">
    <!-- advisor / aspect configuration -->
</aop:config>
```

Với annotation-driven AOP:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
}
```

Lưu ý tên trong Java annotation là **`proxyTargetClass`** theo camelCase, trong XML thường thấy **`proxy-target-class`**. Hai cách chỉ cấu hình một ý tưởng, nhưng áp dụng qua các entry point khác nhau.

Khi để `false` (hoặc không ép class proxy), Spring có thể dùng JDK proxy nếu target có interface phù hợp; nếu không có interface thích hợp thì có thể dùng class-based proxy. Khi `true`, target class được ưu tiên làm kiểu proxy, nhưng nếu target không thể subclass thì vẫn có giới hạn.

**Phạm vi cấu hình:** các thành phần như `<aop:config>`, `<aop:aspectj-autoproxy>` và `<tx:annotation-driven>` có thể dùng cơ chế tạo auto-proxy chung trong ApplicationContext; thiết lập ép class proxy ở một nơi có thể ảnh hưởng các AOP proxies khác được tạo bởi cùng hạ tầng. Không nên mặc định cờ chỉ tác động duy nhất một bean.

## 4. Spring Boot và các mặc định proxy

Trong Spring Boot, các mặc định AOP có thể được Boot auto-configuration điều chỉnh. Một số phiên bản Spring Boot ưu tiên class-based proxies theo cấu hình AOP, và có property kiểu `spring.aop.proxy-target-class` để điều khiển lựa chọn.

```properties
spring.aop.proxy-target-class=true
```

Hoặc:

```properties
spring.aop.proxy-target-class=false
```

Không được suy ra Spring Framework thuần tự đọc property của Spring Boot. Trong Framework, phải cấu hình qua AOP infrastructure, annotation hoặc XML tương ứng. Cũng cần kiểm tra phiên bản Boot/Framework và các thành phần transaction, security, caching đang dùng vì không phải mọi proxy đều được tạo bởi cùng một cơ chế hoặc chịu cùng tùy chọn.

## 5. JMX có liên quan đến AOP proxy ở điểm nào?

JMX không tự tạo AOP proxy. Nhưng Spring-managed bean được export có thể đã bị AOP proxy hóa trước đó:

```text
ApplicationContext
     |
     +-- PaymentService bean
          |
          +-- AOP auto-proxying
          |      +-- JDK dynamic proxy
          |      +-- class-based proxy
          |
          v
     MBeanExporter sees bean
          |
          +-- chooses MBean interface / assembler
          +-- assigns ObjectName
          v
     MBeanServer
          |
          v
     JConsole / VisualVM / JMX client
```

Khi `MBeanExporter` nhận một proxy thay vì target thô, **class và interface nhìn thấy trên proxy** có thể khác implementation target. Điều này ảnh hưởng tới việc:

- Nhận diện bean là Standard MBean/MXBean hay POJO cần thích ứng.
- Tìm `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` trên target class hoặc method.
- Ánh xạ method đã chọn tới operation/attribute thật sự gọi được trên proxy.
- Kiểm tra chữ ký và kiểu trả về, nhất là khi concrete method không nằm trong interface JDK proxy.
- Đảm bảo AOP advice (ví dụ transaction/authorization) còn được áp dụng trên đường gọi từ JMX.

Không có một kết luận chung rằng bật `proxy-target-class=true` là đủ để sửa mọi lỗi JMX. Cần xem **đường export cụ thể**, assembler, AOP proxy kind và MBeanInfo thực tế.

## 6. Ví dụ bean có cả business interface và JMX metadata

Giả sử implementation có các annotation quản trị:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;

@Service
@ManagedResource(
    objectName = "com.example.payment:type=PaymentMonitor,name=Main",
    description = "Trạng thái và thao tác quản trị payment"
)
public class DefaultPaymentService implements PaymentService {
    private volatile boolean paused;

    @Override
    public long getProcessedCount() {
        return 42;
    }

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation
    public void requestResume() {
        paused = false;
    }

    @Override
    public void processPayment(String id) {
        // Logic xử lý payment.
    }
}
```

Interface `PaymentService` chỉ công bố business methods. Nếu một JDK proxy chỉ triển khai `PaymentService`, phương thức `isPaused()` và `requestResume()` không nằm trên public API của proxy đó. Với class proxy, concrete method có thể tiếp tục nằm trên kiểu proxy; nhưng Spring JMX còn phải chọn đúng metadata và cách gọi target.

**Thiết kế thường dễ kiểm soát hơn:** tạo management adapter riêng, tránh buộc business service phải vừa làm endpoint JMX vừa là target AOP với một tập interface không tương thích.

## 7. Management adapter riêng: lựa chọn rõ ràng

Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.payment:type=PaymentMonitor,name=Main"
)
public class PaymentManagement {
    private final PaymentService service;
    private final PaymentStateView state;

    public PaymentManagement(
            PaymentService service, PaymentStateView state) {
        this.service = service;
        this.state = state;
    }

    @ManagedAttribute(description = "Payment đang tạm dừng?")
    public boolean isPaused() {
        return state.isPaused();
    }

    @ManagedAttribute(description = "Số payment đã xử lý")
    public long getProcessedCount() {
        return service.getProcessedCount();
    }

    @ManagedOperation(description = "Yêu cầu tiếp tục xử lý payment")
    public void requestResume() {
        state.requestResume();
    }
}
```

`PaymentStateView` là abstraction ứng dụng cung cấp để đọc/điều khiển trạng thái; ở một project thật cần định nghĩa interface/bean tương ứng. `PaymentManagement` là bean nhỏ, thiết kế riêng cho JMX; nó delegate sang service. Khi business service dùng JDK proxy, adapter chỉ tương tác với những method có trong interface `PaymentService`, nên không phụ thuộc vào concrete class cho business calls.

Ưu điểm:

1. Bề mặt MBean được chọn chính xác bằng annotation.
2. Không buộc tất cả business methods thành public JMX operations.
3. AOP advice trên business service vẫn có thể hoạt động khi adapter gọi qua Spring proxy đã inject.
4. Management contract giữ ổn định kể cả khi refactor class implementation.
5. Dễ kiểm tra quyền của operation có side effect.

## 8. Bật annotation-driven JMX export

Trong Spring Framework:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {
}
```

Với `@ManagedResource` và metadata assembler được Spring cấu hình, bean quản trị đủ điều kiện sẽ được export theo naming/metadata tương ứng.

**Điểm quan trọng:** `@EnableMBeanExport` không có nghĩa mọi Spring bean được convert thành MBean và không tự ép AOP class proxy. Nó là cấu hình JMX exporter; AOP proxy mode cần được xem riêng.

## 9. Vì sao JDK proxy đôi khi gây lỗi export JMX?

JDK dynamic proxy chỉ expose interfaces. Nếu `MBeanExporter` hoặc một assembler cấu hình tay cần phản chiếu method chỉ có trên class target, quá trình xác định metadata hoặc invoke có thể không trùng với proxy class.

Ví dụ:

```java
public interface TaskService {
    int getPendingTasks();
}

public class DefaultTaskService implements TaskService {
    @Override
    public int getPendingTasks() { return 5; }

    public void forceCleanup() { /* ... */ }
}
```

Nếu `DefaultTaskService` được proxied bằng JDK proxy của `TaskService`, object proxy không có public method `forceCleanup()` theo interface đó. Một MBean assembler dự kiến export `forceCleanup()` từ target class có thể không có đường gọi tương ứng qua proxy trong mọi cấu hình.

Những phương án hợp lý:

- Dùng management interface riêng và export interface/method được hỗ trợ.
- Dùng management adapter delegate qua interface của service.
- Cấu hình class-based proxy khi thực sự cần và target có thể subclass.
- Kiểm tra và sửa MBeanInfoAssembler, naming strategy hoặc target object export thay vì chỉ đổi proxy flag.
- Bảo đảm metadata JMX được đọc từ đúng target class, không chỉ từ proxy class.

Không nên xem việc làm method `public` trên implementation là đủ nếu proxy phía Spring vẫn chỉ triển khai interface.

## 10. Cờ proxy-target-class không quyết định JMX management interface

Cần tách ba khái niệm:

| Khái niệm | Vai trò |
| --- | --- |
| `proxy-target-class` / `proxyTargetClass` | Quyết định kiểu AOP proxy tạo bởi cơ chế Spring tương ứng |
| `MBeanInfoAssembler` / `@ManagedAttribute` / `@ManagedOperation` | Quyết định attributes/operations được công bố |
| `ObjectName` / `ObjectNamingStrategy` | Quyết định MBean nào được đăng ký và JMX client tìm được tên nào |

Ví dụ bật class proxy không làm `deleteAll()` tự trở thành JMX operation nếu annotation-based assembler chỉ chọn một số method. Ngược lại, dùng `SimpleReflectiveMBeanInfoAssembler` có thể expose nhiều public methods ngay cả khi AOP proxy dựa trên interface/class có hình dạng khác.

Để biết contract thực tế, phải đọc MBeanInfo sau khi export, không đoán từ AOP configuration.

## 11. Ví dụ cùng code với cấu hình proxy khác nhau

### 11.1. Cấu hình JDK interface proxy

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class InterfaceProxyConfig {}
```

Nếu bean có interface phù hợp, Spring AOP thường có thể dùng JDK dynamic proxy; bean nhận từ IoC có thể là một instance `java.lang.reflect.Proxy` triển khai interface, không phải subclass của target concrete class.

### 11.2. Cấu hình class proxy

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassProxyConfig {}
```

Spring AOP có thể tạo subclass proxy. Đối với một method public, non-final được advice, lời gọi qua proxy có thể chạy advice và sau đó target method.

**Tránh bật cả hai cấu hình mâu thuẫn trong cùng context để so sánh trực tiếp**. Để thử nghiệm thực tế, chạy hai context/ứng dụng thử nghiệm tách biệt với cấu hình rõ ràng.

## 12. Xác định proxy kind bằng Spring AopUtils

Để quan sát object được inject là proxy loại nào:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("paymentService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

`AopUtils` là API hỗ trợ của Spring AOP. Đoạn code cần module `spring-aop` trên classpath và một ApplicationContext đã khởi tạo. Nếu bean không có advice áp dụng, nó có thể không được proxy dù cấu hình `proxyTargetClass` được bật: cờ là lựa chọn **kiểu proxy khi cần tạo proxy**, không phải lệnh ép mọi bean trở thành proxy.

Với nhiều lớp proxy lồng nhau hoặc custom `TargetSource`, cần hiểu đường gọi thực tế; không chỉ đọc `getClass()` của bean rồi kết luận tất cả metadata JMX đến từ class đó.

## 13. Export trực tiếp AOP proxy: các điểm cần quan tâm

Khi muốn export một bean AOP-proxied, kiểm tra:

1. **Nguồn metadata:** assembler có đọc `@ManagedResource` và các annotation từ target class phù hợp không?
2. **Proxy interface:** những getter/operation cần expose có hiện diện trên type proxy không?
3. **AOP advice:** lời gọi từ JMX vào MBean có thực sự đi qua proxy/advice như mong muốn không?
4. **Target object:** exporter quản lý proxy hay target thô? Tránh cố ý unwrap proxy làm mất security/transaction advice mà không nhận ra.
5. **Method visibility:** final/private methods có được proxy advice không?
6. **ObjectName:** có ổn định, duy nhất và trỏ đúng MBean trong MBeanServer không?
7. **Lifecycle:** exporter đăng ký/hủy đăng ký bean trong cùng context một cách nhất quán không?

Nếu JMX gọi trực tiếp vào implementation object thay vì vào AOP proxy chứa security advice, không nên coi method-level authorization của AOP đã tự áp dụng. Với management operations nhạy cảm, cần có kiểm soát quyền ở connector/layer riêng và validation ngay trong operation.

## 14. Phân biệt JMX proxy với AOP proxy

Spring có cả hai khái niệm khác nhau:

**AOP proxy:** client gọi một Spring bean, proxy chặn lời gọi theo advisors/pointcuts rồi chuyển đến target.

**JMX client proxy:** Spring `MBeanProxyFactoryBean` tạo proxy Java cho MBean; nó dùng `MBeanServerConnection`, `ObjectName` và management interface để chuyển lời gọi thành JMX operations/attributes.

```text
Business call
  -> AOP proxy -> target bean

JMX client call
  -> MBeanProxyFactoryBean proxy
  -> MBeanServerConnection -> ObjectName -> MBean
```

`proxy-target-class` chủ yếu nói về **cách AOP proxy được tạo**. Nó không phải tham số quyết định ObjectName hoặc kiểu JMX client proxy của `MBeanProxyFactoryBean`.

## 15. Interface-based management contract và class proxy

Một ứng dụng có thể dùng Standard MBean interface:

```java
public interface QueueManagementMBean {
    int getQueueDepth();
    void requestPause();
}
```

```java
public class QueueManagement implements QueueManagementMBean {
    @Override
    public int getQueueDepth() { return 5; }

    @Override
    public void requestPause() { /* ... */ }
}
```

Interface-based MBean contract này tồn tại độc lập với việc có AOP hay không. Nếu exporter cần tạo AOP proxy cho QueueManagement, lựa chọn JDK/class proxy có thể ảnh hưởng kiểu object trung gian, nhưng interface vẫn mô tả rõ API quản trị. Đây là lý do management interface hoặc adapter chuyên biệt thường an toàn hơn khi application có nhiều advice.

## 16. Khi nào cân nhắc bật proxyTargetClass=true?

Nên cân nhắc khi:

- Ứng dụng cần proxy tương thích với concrete class để inject/tra cứu theo class và không muốn phụ thuộc interface.
- AOP advice áp dụng cho method không nằm trên interface nhưng method có thể override.
- Một tích hợp framework khác yêu cầu xem target-class methods và đã kiểm chứng tương thích với class proxy.
- Đã hiểu giới hạn của final methods/classes và các class có constructor/phạm vi truy cập đặc biệt.

Không nên bật chỉ vì:

- Muốn mọi Java method tự biến thành JMX operation.
- Muốn bỏ qua security của JMX connector.
- Muốn sửa một ObjectName không tồn tại.
- Muốn proxy intercept private/final methods.
- Muốn giải quyết xung đột MBeanServer/registration policy.

Việc đổi proxy mode có thể ảnh hưởng dependency injection, AOP advice behavior và các bean khác trong context; cần thử với cấu hình ứng dụng thực tế.

## 17. Xem MBeanInfo để biết API JMX đã export

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.payment:type=PaymentMonitor,name=Main"
);

MBeanInfo info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute %s: readable=%s writable=%s%n",
        attr.getName(), attr.isReadable(), attr.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println("Operation " + operation.getName());
}
```

Đoạn code giả định MBean được đăng ký vào platform MBeanServer. Nếu exporter dùng server riêng, cần lấy đúng server đó. MBeanInfo cho thấy contract JMX client nhìn thấy; đây là cách xác định attribute/operation thực tế sau khi cả annotation, assembler và AOP proxy mode cùng tham gia.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| JMX không thấy `@ManagedAttribute` trên target | Exporter/metadata source không giải được annotation từ target class hoặc proxy chỉ expose interface | Kiểm tra AOP proxy kind, annotation assembler, target metadata |
| Cast Spring bean sang concrete class thất bại | Bean là JDK proxy chỉ implement interface | Inject interface hoặc cân nhắc class proxy |
| Bật class proxy nhưng vẫn không intercept final method | CGLIB không override final method | Chuyển logic sang method proxyable hoặc cơ chế khác |
| Transaction/security advice không chạy khi JMX gọi operation | Đường gọi không qua proxy advice hoặc self-invocation | Kiểm tra target object được export và call path |
| JMX exporter báo MBean không compliant | Object proxy/interface không đáp ứng đường export | Dùng management adapter/interface hoặc metadata assembler phù hợp |
| Bean xuất hiện nhưng operation ngoài dự kiến | Reflection assembler expose public methods | Chọn annotation/interface/allowlist assembler |
| Bean không xuất hiện sau khi bật AOP | ObjectName, exporter hoặc metadata không khớp | Kiểm tra registration, MBeanInfo, errors startup |
| Bật proxyTargetClass làm startup lỗi | Class final hoặc visibility/construction không phù hợp | Đổi proxy strategy hoặc refactor target |

## 19. An toàn bảo mật và hiệu năng

JMX thường là bề mặt quản trị có quyền cao. AOP proxy mode không thay thế chính sách bảo mật:

- Không export API thay đổi dữ liệu ngoài nhu cầu vận hành.
- Không tin rằng method-level Spring Security luôn được áp dụng nếu JMX gọi theo đường bypass AOP proxy.
- Luôn validate tham số cho operation có tác động.
- Hạn chế thông tin từ management attributes và notification.
- Bảo vệ remote JMX connector bằng network policy, authentication, TLS và authorization tương ứng.
- Tránh getter JMX làm việc nặng, vì monitoring có thể polling thường xuyên.
- Giữ ObjectName và MBean contract ổn định khi thay đổi proxy/assembler.

Với class proxy, việc advice được áp dụng có thể thay đổi timing, exceptions và transaction boundaries. Đừng gọi JMX operation dài bên trong critical path mà không có giới hạn tài nguyên.

## 20. Mô hình tư duy

```text
                   Spring target bean
                          |
                AOP infrastructure
                          |
         proxyTargetClass = false / true
                          |
                  +-------+-------+
                  |               |
              JDK proxy      Class proxy
             (interfaces)    (subclass)
                  |               |
                  +-------+-------+
                          |
                     MBeanExporter
                          |
                MBeanInfoAssembler
                          |
                       MBeanServer
                          |
                      JMX clients
```

**Kết luận:** `proxy-target-class` điều khiển **kiểu AOP proxy** của Spring theo cơ chế cấu hình tương ứng, không trực tiếp quyết định quyền hay danh sách attributes/operations JMX. JDK proxy phù hợp với contract interface, còn class-based proxy có thể giữ API của concrete target nhưng bị giới hạn bởi final/private methods. Khi kết hợp Spring AOP và JMX, nên ưu tiên management interface hoặc adapter nhỏ, cấu hình assembler rõ ràng và kiểm tra MBeanInfo cùng đường gọi advice thực tế.
