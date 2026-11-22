# Ảnh hưởng của Spring AOP proxy tới việc nhận diện annotation JMX

## Mục tiêu

Trong Spring Framework, một bean được gắn annotation JMX có thể không còn xuất hiện ở runtime dưới dạng class gốc. Các cơ chế AOP như `@Transactional`, `@Async`, `@Cacheable`, method security và custom advice có thể tạo **JDK dynamic proxy** hoặc **class-based proxy**. Điều này tác động đến cách exporter tìm `@ManagedResource`, đọc `@ManagedAttribute` và `@ManagedOperation`, xác định method có thể gọi được và chuyển lời gọi JMX tới bean thực tế.

Sau bài này, bạn có thể:

- Phân biệt target class, runtime proxy class và các interface được proxy expose.
- Giải thích cơ chế exporter/metadata assembler nhận diện annotation JMX trên Spring bean.
- Hiểu vì sao annotation có thể tồn tại trên target nhưng method vẫn không truy cập được qua proxy.
- Tổ chức cấu hình `@EnableMBeanExport`, `MBeanExporter`, naming strategy và AOP phù hợp.
- Chẩn đoán tình huống JMX MBean bị thiếu, tên thay đổi, operation không xuất hiện hoặc lời gọi bỏ qua advice.
- Thiết kế adapter quản trị và integration test có cả Spring AOP lẫn MBeanServer.

## 1. Một Spring bean có thể là proxy chứ không phải target

Giả sử service:

```java
@Service
@ManagedResource(
    objectName = "com.example.orders:type=Processor,name=Main"
)
public class OrderProcessor {

    @ManagedAttribute
    public int getPendingCount() {
        return 10;
    }

    @ManagedOperation
    public void retryFailed() {
        // ...
    }
}
```

Nếu một advisor hoặc annotation như `@Transactional` áp dụng cho bean, ApplicationContext có thể cung cấp một proxy thay cho instance class này.

```text
ApplicationContext.getBean("orderProcessor")
         |
         v
    Spring AOP proxy
         |
         v
      target object
       OrderProcessor
```

Từ phía caller, proxy là bean thực tế. Nhưng annotation JMX thường được khai báo trên **class và method của target**. Một công cụ đọc metadata theo `bean.getClass()` mà không hiểu proxy có thể thấy:

- Class runtime là `jdk.proxy...` hoặc `com.sun.proxy...` đối với JDK dynamic proxy.
- Class runtime là subclass dạng `OrderProcessor$$SpringCGLIB$$...` đối với class-based proxy.
- Annotation class-level hoặc method-level có thể cần được tìm ở target class hoặc method khai báo gốc.

Spring JMX và Spring AOP có các helper nhằm xử lý tình huống này, nhưng kết quả cuối cùng còn phụ thuộc kiểu proxy, giao diện được expose, assembler và exporter được cấu hình.

## 2. Annotation JMX có những vai trò nào?

Spring JMX cung cấp các annotation:

- `@ManagedResource`: đánh dấu managed resource, thường khai báo ObjectName và description.
- `@ManagedAttribute`: mô tả getter/setter được xuất thành JMX attribute.
- `@ManagedOperation`: đánh dấu method được công bố như operation.
- `@ManagedOperationParameter` và `@ManagedOperationParameters`: cung cấp thông tin tham số quản trị.
- `@ManagedNotification` và `@ManagedNotifications`: khai báo metadata notification cho resource phù hợp.

Các annotation không tự đăng ký một MBean. Chúng cần hạ tầng như `AnnotationMBeanExporter` hoặc `MBeanExporter` có `MetadataMBeanInfoAssembler`/`AnnotationJmxAttributeSource`.

Một cấu hình Java đơn giản:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Nếu Spring bean đã được quét và metadata được nhận diện, exporter có thể đăng ký MBean vào `MBeanServer`. Nhưng nếu bean bị proxy, cần phân biệt hai câu hỏi:

1. Spring có **tìm thấy annotation trên target** không?
2. JMX có **thực sự invoke được method** qua object được export không?

Đó là hai lớp vấn đề khác nhau. Một cấu hình có thể vượt qua bước phát hiện metadata nhưng vẫn lỗi lúc gọi operation.

## 3. JDK dynamic proxy: chỉ expose interface

JDK dynamic proxy tạo object triển khai một hoặc nhiều Java interface. Nó không kế thừa trực tiếp implementation class.

Ví dụ:

```java
public interface OrderService {
    int getPendingCount();
}

@Service
@ManagedResource(
    objectName = "com.example.orders:type=Processor,name=Main"
)
public class OrderServiceImpl implements OrderService {

    @Override
    @ManagedAttribute
    public int getPendingCount() {
        return 10;
    }

    @ManagedOperation
    public void retryFailed() {
        // Method này KHÔNG có trên OrderService.
    }
}
```

Khi Spring tạo JDK proxy chỉ cho `OrderService`, caller có thể gọi `getPendingCount()` qua proxy nhưng không thể gọi `retryFailed()` bằng interface đó. Vì thế, mặc dù `retryFailed()` có `@ManagedOperation` trên target, exporter dùng proxy làm object quản trị có thể gặp tình huống không expose hoặc không invoke được method đó.

```text
JDK proxy implements OrderService
  getPendingCount()    -> có
  retryFailed()        -> không thuộc interface proxy

OrderServiceImpl target
  getPendingCount()    -> có
  retryFailed()        -> có, @ManagedOperation
```

**Không thể sửa vấn đề chỉ bằng cách thêm annotation trên target method.** Cần thiết kế interface/proxy/adapter phù hợp hoặc dùng phương pháp export bảo đảm lời gọi tới target đúng cách.

Một phương án là đưa những operation thực sự cần quản trị vào một interface mà proxy expose. Nhưng không nhất thiết phải trộn method quản trị vào interface nghiệp vụ; adapter quản trị riêng thường rõ hơn.

## 4. Class-based proxy: kế thừa class nhưng vẫn có giới hạn

Class-based proxy (thường dùng CGLIB trong Spring AOP) tạo subclass của target class.

```text
OrderServiceImpl
   ^
   |
OrderServiceImpl$$SpringCGLIB$$...
```

Với kiểu này, các method public kế thừa thường có thể được gọi qua proxy và các helper Spring có thể tìm về target class để đọc annotation.

Tuy nhiên, class-based proxy không có nghĩa mọi method đều được advice:

- `final` method không thể bị override để intercept theo cơ chế subclass.
- `private` method không thể được proxy intercept như public method.
- Một số method không visible đối với subclass có thể không được advice.
- `final` class không thể được class-based proxy theo cách kế thừa.
- Self-invocation trong target thường bỏ qua proxy-based advice.

Vì vậy, ngay cả khi JMX export nhìn thấy operation, cần kiểm tra **đường gọi có đi qua advice mong đợi** hay không, đặc biệt với transaction, security hoặc logging.

## 5. Annotation ở class gốc, proxy ở runtime

Trong Java, việc gọi:

```java
bean.getClass().isAnnotationPresent(ManagedResource.class)
```

có thể cho kết quả không đúng với kỳ vọng nếu `bean` là proxy. JDK proxy class không phải class gốc có annotation.

Spring cung cấp API AOP utility để xác định target class, ví dụ:

```java
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;

Class<?> targetType = AopProxyUtils.ultimateTargetClass(bean);

System.out.println("runtime class = " + bean.getClass());
System.out.println("target class  = " + targetType);
System.out.println("is AOP proxy  = " + AopUtils.isAopProxy(bean));
System.out.println("is JDK proxy  = " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("is class proxy= " + AopUtils.isCglibProxy(bean));
```

Những helper này hữu ích cho diagnostic và test. Đừng viết logic export bằng cách tự lấy target object bên trong proxy một cách tùy tiện, vì như vậy có thể làm mất advice mà ứng dụng phụ thuộc.

Đọc metadata cần hiểu target class, nhưng **invocation** phải đi theo đường được thiết kế để giữ transaction/security nếu các advice đó là yêu cầu.

## 6. MetadataMBeanInfoAssembler và AnnotationJmxAttributeSource

Khi dùng annotation-driven JMX export, việc lấy thông tin `@Managed*` thuộc trách nhiệm metadata source và assembler.

Các thành phần tiêu biểu:

```text
Spring bean
  |
  +--> AnnotationJmxAttributeSource
  |      đọc @ManagedResource/@ManagedAttribute/@ManagedOperation
  |
  +--> MetadataMBeanInfoAssembler
  |      tạo metadata JMX (attributes, operations, descriptions)
  |
  +--> MetadataNamingStrategy
  |      xác định ObjectName khi áp dụng metadata naming
  |
  v
MBeanExporter / AnnotationMBeanExporter
  |
  v
MBeanServer
```

Nếu dùng:

```java
@EnableMBeanExport
```

Spring cấu hình hạ tầng phù hợp cho annotation-driven export. Nếu tự cấu hình `MBeanExporter`, không nên giả định exporter đó tự dùng annotation metadata assembler mà chưa đặt cấu hình cần thiết.

Với bean bị proxy, sự khác nhau giữa target method và proxy method có thể tác động đến:

- Tìm annotation gắn trên implementation method.
- Kiểu class được dùng để introspect.
- Khả năng ánh xạ method vào object thực sự expose qua JMX.
- Tên ObjectName nếu strategy dựa vào runtime class.
- Danh sách attributes và operations trong `MBeanInfo`.

Do đó, chẩn đoán cần xem **metadata đã đăng ký thực tế** chứ không chỉ nhìn source code annotation.

## 7. Đừng nhầm nhận diện annotation với gọi method

Giả sử Spring đọc được:

```java
@ManagedOperation
public void retryFailed() { ... }
```

Nhưng object được MBeanServer gọi là JDK proxy chỉ expose `OrderService` không có `retryFailed`. Một số tình huống có thể xảy ra tùy phiên bản Spring và cấu hình:

1. Exporter không đưa operation đó vào MBeanInfo.
2. Exporter tạo metadata chứa operation nhưng lời gọi thất bại do không resolve được method trên object expose.
3. Exporter yêu cầu cách xử lý proxy/adapter khác trước khi đăng ký.
4. Exporter đăng ký target thay proxy, operation chạy nhưng advice Spring có thể bị bỏ qua.

Không thể kết luận chính xác chỉ bằng câu “class có annotation”. Hãy kiểm tra lần lượt `isRegistered`, `MBeanInfo.getOperations()` và thực thi `MBeanServer.invoke`.

## 8. Dùng management adapter để tách AOP và JMX

Một thiết kế bền vững hơn là **adapter JMX** nhận service interface do Spring inject.

Interface nghiệp vụ:

```java
package com.example.orders;

public interface OrderService {
    int pendingCount();
    void retryFailed(int maxCount);
}
```

Implementation:

```java
package com.example.orders;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DefaultOrderService implements OrderService {

    @Override
    public int pendingCount() {
        return 10;
    }

    @Override
    @Transactional
    public void retryFailed(int maxCount) {
        // Xử lý nghiệp vụ bên trong transaction.
    }
}
```

Management adapter:

```java
package com.example.orders.management;

import com.example.orders.OrderService;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Processor,name=Main",
    description = "Order processing statistics and bounded retry operations"
)
public class OrderManagementAdapter {

    private final OrderService orderService;

    public OrderManagementAdapter(OrderService orderService) {
        this.orderService = orderService;
    }

    @ManagedAttribute(
        description = "Number of orders pending in this application instance"
    )
    public int getPendingCount() {
        return orderService.pendingCount();
    }

    @ManagedOperation(
        description = "Retries at most maxCount failed orders"
    )
    public void retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException("maxCount must be 1..100");
        }
        orderService.retryFailed(maxCount);
    }
}
```

Ở đây:

- Adapter có metadata JMX.
- Adapter thường không cần bị proxy AOP riêng.
- Service có thể là JDK proxy chỉ expose `OrderService`, đúng với method adapter cần gọi.
- Transaction advice trên service được thực thi khi adapter gọi qua service proxy, nếu transaction infrastructure được cấu hình và lời gọi không bị bypass.
- Interface quản trị chỉ công bố trạng thái và operation cần thiết, không lộ toàn bộ API nghiệp vụ.

## 9. Cấu hình Spring để export adapter

Một ví dụ Java configuration:

```java
package com.example.orders.management;

import com.example.orders.OrderService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxManagementConfiguration {

    @Bean
    public OrderManagementAdapter orderManagementAdapter(
            OrderService service) {
        return new OrderManagementAdapter(service);
    }
}
```

Nếu ứng dụng dùng component scan hoặc `@SpringBootApplication`, cần bảo đảm service implementation được đăng ký trong ApplicationContext và transaction/security infrastructure (nếu cần) đã được cấu hình riêng.

Đừng dùng đồng thời `@EnableMBeanExport` và một `MBeanExporter` thủ công đăng ký **cùng ObjectName**, nếu không có một thiết kế tránh trùng rõ ràng. Hai exporter có thể gây `InstanceAlreadyExistsException` hoặc áp dụng registration policy làm kết quả không đúng kỳ vọng.

Đối với XML-based Spring, `<context:mbean-export/>` bật cơ chế annotation export tương ứng, nhưng không tự giải quyết sự không khớp giữa method của target và interface được proxy expose.

## 10. Khi nào cần giữ trực tiếp annotation trên service?

Không phải lúc nào cũng phải tạo adapter.

Nếu:

- Component nhỏ và chỉ phục vụ quản trị.
- Không có AOP proxy phức tạp.
- Management interface là một phần rõ ràng của public contract.
- Các methods quản trị có thể gọi qua proxy theo cơ chế đang dùng.

thì gắn `@ManagedResource` và method annotation trên bean có thể là lựa chọn đơn giản.

Nhưng nếu service có nhiều transaction/security advice, thay đổi interface thường xuyên hoặc operation quản trị có side effect, adapter thường giảm kết dính và rủi ro hơn.

Không có quy tắc “JDK proxy luôn làm mất annotation” hoặc “CGLIB luôn an toàn”: cần xét chính xác cách Spring tìm metadata và class/interface mà exporter thực sự thấy.

## 11. ObjectNamingStrategy và class proxy

Một nguồn lỗi khác là cách tạo ObjectName.

Nếu naming strategy dùng `bean.getClass().getName()`, một class-based proxy có thể tạo tên chứa suffix động:

```text
com.example.orders:type=OrderServiceImpl$$SpringCGLIB$$...
```

Tên như vậy không ổn định hoặc không hữu ích cho dashboard. Với JDK proxy, runtime class có thể giống `jdk.proxy2.$Proxy...`, càng không phù hợp làm định danh quản trị.

Nên đặt tên logic rõ ràng:

```text
com.example.orders:type=Processor,name=Main
```

hoặc dùng metadata naming strategy lấy tên từ `@ManagedResource(objectName=...)`, nếu cấu hình exporter hỗ trợ.

Tách **danh tính nghiệp vụ** khỏi **runtime proxy class** giúp tránh thay đổi ObjectName khi AOP advice hoặc proxy mode thay đổi.

## 12. Kiểm tra proxy thực sự được tạo

Trong integration test hoặc log diagnostic:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("orderService");

System.out.println(bean.getClass());
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Cần ghi nhận cả kiểu proxy và interface mà bean thực tế expose:

```java
for (Class<?> iface : bean.getClass().getInterfaces()) {
    System.out.println(iface.getName());
}
```

Đối với JDK proxy, interface list là bằng chứng trực tiếp về những methods có thể gọi qua proxy type. Với class-based proxy, method set thường rộng hơn nhưng vẫn có giới hạn advice.

Đừng viết test chỉ assert `isAopProxy(bean)` rồi kết luận JMX chắc chắn nhận diện annotation. Test JMX riêng vẫn cần thiết.

## 13. Kiểm tra MBeanInfo của resource đã export

Dùng `MBeanServer` để xem hạ tầng Spring thực sự công bố gì:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Processor,name=Main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("Expected MBean not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("MBean: " + info.getClassName());

for (var attr : info.getAttributes()) {
    System.out.println(
        "Attribute " + attr.getName() + " : " + attr.getType()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(
        "Operation " + operation.getName()
        + " : " + operation.getReturnType()
    );
}
```

Đoạn code giả định Spring exporter sử dụng platform MBeanServer; nếu ứng dụng dùng server tùy chỉnh, cần lấy đúng server instance.

Nếu MBean tồn tại nhưng thiếu `PendingCount` hoặc `retryFailed`, nguyên nhân có thể là:

- Annotation không được metadata source nhận diện.
- Bean không được exporter autodetect.
- Proxy interface không chứa method hoặc method không thể được introspect như kỳ vọng.
- Exporter dùng một assembler khác với annotation-based assembler.
- Exporter đăng ký một bean khác dưới cùng ObjectName.

`MBeanInfo` là bằng chứng về metadata thực tế, không phải chỉ là reflection trên source class.

## 14. Kiểm thử AOP + JMX bằng Spring context

Một integration test có thể:

1. Bật AOP trên một service.
2. Đăng ký service bean và JMX management adapter.
3. Bật `@EnableMBeanExport`.
4. Khởi tạo ApplicationContext.
5. Kiểm tra service đang là JDK/CGLIB proxy đúng kỳ vọng.
6. Kiểm tra MBean được đăng ký và metadata đầy đủ.
7. Gọi operation qua `MBeanServer.invoke`.
8. Xác minh service advice/side effect được thực thi.
9. Đóng context và xác minh cleanup.

Ví dụ JUnit 5 với cấu hình adapter:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxAopIntegrationTest {
    @Test
    void exposesAdapterAndInvokesService() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.orders:type=Processor,name=Main"
        );

        try (var context = new AnnotationConfigApplicationContext(
                JmxManagementConfiguration.class,
                ServiceConfiguration.class)) {

            assertTrue(server.isRegistered(name));

            Object pending =
                server.getAttribute(name, "PendingCount");
            assertEquals(10, pending);

            server.invoke(
                name,
                "retryFailed",
                new Object[] { 5 },
                new String[] { "int" }
            );

            // Với test thực tế, assert side effect/counter
            // chứng minh service đã được gọi qua proxy.
        }
    }
}
```

`ServiceConfiguration` trong ví dụ là cấu hình test của ứng dụng có service bean và AOP infrastructure. Nếu `@Transactional` được kiểm thử thật, cần transaction manager được cấu hình phù hợp; một annotation đơn lẻ chưa bảo đảm transaction advice được áp dụng.

Để test cách ly, có thể cấu hình exporter sử dụng `MBeanServerFactory.newMBeanServer` và inject server đó thay vì platform server; cần chắc chắn annotation exporter sử dụng server test đang được chọn.

## 15. Tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bean có `@ManagedResource` nhưng không thấy MBean | Exporter/scan không hoạt động hoặc proxy metadata không được phát hiện | Kiểm tra context, annotation exporter, `MBeanInfo` |
| MBean có nhưng thiếu operation | Method không có trong JDK proxy interface hoặc metadata assembler không đọc đúng | Kiểm tra interface, target method, assembler |
| `ReflectionException` khi gọi operation | JMX signature không khớp hoặc proxy không expose method | Lấy signature từ `MBeanOperationInfo` |
| Lỗi `NotCompliantMBeanException` | Cách export Standard MBean/ModelMBean không phù hợp với object hoặc proxy | Dùng annotation assembler/adapter/StandardMBean phù hợp |
| Operation chạy nhưng transaction không có hiệu lực | Export target bỏ qua proxy hoặc self-invocation | Export adapter gọi service proxy |
| ObjectName thay đổi sau khi bật AOP | Naming dựa vào runtime proxy class | Dùng tên logic/metadata naming ổn định |
| Client đọc nhầm MBean | Hai exporter hoặc context dùng tên không đúng | Kiểm tra `ObjectName` và owner đăng ký |
| JConsole không hiển thị metadata mong đợi | Client nối sai server hoặc exporter dùng metadata khác | Kiểm tra MBeanServer, class, `MBeanInfo` |

## 16. Checklist thiết kế khi kết hợp Spring AOP và JMX

Trước khi expose bean qua JMX:

- Xác định bean thực tế là target hay Spring AOP proxy.
- Với JDK proxy, xác minh các method quản trị thuộc interface mà proxy expose hoặc sử dụng adapter.
- Với class-based proxy, xem xét method `final`/`private` và đường advice.
- Xác minh annotation-based metadata assembler thực sự được cấu hình.
- Giữ ObjectName ổn định, không phụ thuộc tên class proxy.
- Không expose toàn bộ public methods chỉ vì thuận tiện.
- Đối với các operation nhạy cảm, kiểm tra authorization ngoài metadata JMX.
- Kiểm tra `MBeanInfo` và gọi operation trên server test thật.
- Bảo đảm service advice được áp dụng theo đường gọi JMX.
- Tránh trùng exporter registration và cleanup MBean đúng lifecycle.

## 17. Bài tập thực hành

1. Tạo `OrderService` interface với `getPendingCount`, class implementation có thêm `retryFailed` được gắn `@ManagedOperation`. Bật JDK proxy rồi quan sát khác biệt method set.
2. Chuyển sang class-based proxy và kiểm tra lại `MBeanInfo`; giải thích vì sao kết quả có thể thay đổi.
3. Dùng `AopUtils.isJdkDynamicProxy`, `AopUtils.isCglibProxy` và `AopProxyUtils.ultimateTargetClass` trong test diagnostic.
4. Tạo JMX adapter nhận `OrderService` proxy, expose một attribute và một operation. Xác minh lời gọi qua `MBeanServer`.
5. Bật một advisor đếm số lần gọi `retryFailed`. So sánh khi gọi qua adapter proxy và gọi trực tiếp target.
6. Cố tình đặt naming strategy dựa vào `bean.getClass().getName()`, quan sát tên thay đổi khi bật AOP rồi sửa bằng ObjectName logic.
7. Viết integration test kiểm tra MBean registration, metadata, invocation và unregister khi context đóng.

## 18. Câu hỏi tự kiểm tra

- Tại sao `bean.getClass()` có thể không phải class chứa `@ManagedResource`?
- JDK proxy và class-based proxy khác nhau gì về tập method được expose?
- Vì sao metadata annotation được tìm thấy chưa chắc method gọi được qua JMX?
- Trong trường hợp nào export target thay proxy có thể làm mất transaction/security advice?
- Vì sao nên dùng JMX management adapter đối với service có nhiều AOP advice?
- `@EnableMBeanExport` có tự tạo transaction manager hay bảo vệ JMX operation không?
- Cách kiểm tra chính xác operations đã xuất là gì?
- Naming strategy dựa vào tên runtime proxy có rủi ro gì qua các lần deploy?

**Ghi nhớ:** Khi Spring AOP tạo proxy, class runtime và method surface có thể khác target class chứa annotation JMX. Hãy phân biệt **metadata discovery** với **method invocation**, kiểm tra JDK/class-based proxy, giữ ObjectName độc lập với proxy class và ưu tiên adapter quản trị gọi qua Spring service proxy khi cần giữ transaction/security advice.