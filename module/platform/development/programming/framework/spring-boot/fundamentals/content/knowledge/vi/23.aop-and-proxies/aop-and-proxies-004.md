# JDK dynamic proxy và proxy dựa trên lớp

Khi dùng Spring Boot, bạn có thể gắn `@Transactional` lên một service rồi thấy transaction tự động được mở và đóng khi method được gọi. Bạn có thể dùng `@Async` để lời gọi được chuyển sang executor, hoặc `@Cacheable` để kết quả được lưu vào cache. Với Spring AOP, nhiều hành vi như vậy được triển khai bằng **proxy**: một object trung gian đứng giữa nơi gọi và object nghiệp vụ thực sự.

Spring AOP thường tạo proxy theo hai chiến lược:

- **JDK dynamic proxy:** tạo object proxy triển khai các interface của target.
- **Class-based proxy:** tạo một lớp con của target bằng công nghệ CGLIB được Spring tích hợp.

Hai chiến lược có thể tạo ra kết quả khác nhau khi inject bean theo interface hoặc concrete class, khi method là `final`, khi class không có interface, và khi một method tự gọi method khác bên trong cùng object.

Bài học thuộc chương **AOP và proxy** của **Spring Boot Fundamentals**. Sau bài này, bạn cần hiểu vì sao một bean có thể không cùng runtime class với class bạn viết, cách lựa chọn JDK hoặc class-based proxy trong Spring Boot, các giới hạn của từng loại và cách chẩn đoán khi advice không chạy.

## 1. Proxy là gì?

Trong Java, thay vì đưa trực tiếp object nghiệp vụ cho bên gọi, chúng ta có thể đưa một object trung gian có cùng giao diện sử dụng. Object trung gian nhận lời gọi, thực hiện công việc bổ sung rồi chuyển tiếp đến object thật.

Ví dụ:

```text
Controller
    │
    │ paymentService.pay("ORDER-001")
    ▼
Spring AOP proxy
    │
    ├── Trước lời gọi: bắt đầu đo thời gian
    │
    ▼
Target: PaymentService
    │
    └── Thực thi logic thanh toán
    │
    ▼
Spring AOP proxy
    │
    ├── Sau lời gọi: ghi thời gian thực thi
    │
    ▼
Controller nhận kết quả
```

Các thành phần:

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Target** | Object thực hiện nghiệp vụ gốc |
| **Proxy** | Object trung gian mà client thường nhận từ Spring container |
| **Advice** | Hành vi bổ sung trước, sau hoặc bao quanh lời gọi |
| **Join point** | Điểm mà advice có thể áp dụng; trong Spring AOP chủ yếu là method execution |
| **Pointcut** | Quy tắc xác định những method/join point được advice áp dụng |
| **Advisor** | Kết hợp pointcut và advice trong hạ tầng Spring AOP |

Spring AOP hoạt động theo mô hình proxy, khác với một cơ chế tự sửa bytecode của mọi object trong JVM. Chỉ những lời gọi đi qua proxy thích hợp mới có cơ hội được interceptor của proxy xử lý.

### 1.1. Ví dụ không dùng Spring: decorator thủ công

Giả sử:

```java
public interface PaymentOperations {
    void pay(String orderId);
}
```

Implementation:

```java
public final class DefaultPaymentOperations
        implements PaymentOperations {

    @Override
    public void pay(String orderId) {
        System.out.println("Paying order " + orderId);
    }
}
```

Ta có thể tự viết một wrapper:

```java
public final class LoggingPaymentOperations
        implements PaymentOperations {

    private final PaymentOperations delegate;

    public LoggingPaymentOperations(PaymentOperations delegate) {
        this.delegate = delegate;
    }

    @Override
    public void pay(String orderId) {
        System.out.println("Before payment");
        delegate.pay(orderId);
        System.out.println("After payment");
    }
}
```

Client dùng:

```java
PaymentOperations payment =
        new LoggingPaymentOperations(
                new DefaultPaymentOperations()
        );

payment.pay("ORDER-001");
```

Đây là cách minh họa proxy/decorator bằng tay. Spring AOP tự động tạo lớp trung gian và nối advice theo cấu hình, để bạn không phải viết wrapper cho từng service.

## 2. JDK dynamic proxy hoạt động như thế nào?

JDK dynamic proxy là cơ chế có sẵn trong Java, thuộc package:

```java
java.lang.reflect.Proxy
java.lang.reflect.InvocationHandler
```

Nó tạo ra một object có runtime class do JDK sinh, **triển khai một hoặc nhiều interface**. Mỗi lời gọi method được hỗ trợ đi qua `InvocationHandler`.

Sơ đồ:

```text
PaymentOperations interface
          ▲             ▲
          │             │
          │             └── DefaultPaymentService (target)
          │
JDK-generated proxy
          │
          ├── InvocationHandler / interceptor
          │
          └── Gọi target.pay(...)
```

Đặc điểm quan trọng:

- Proxy triển khai các interface đã chọn.
- Proxy **không phải subclass** của concrete target class.
- Client nên làm việc qua interface mà proxy cung cấp.
- `final` trên target class không cản trở JDK proxy khi target vẫn triển khai interface phù hợp.
- Method không nằm trong các interface được proxy bộc lộ thường không thể gọi qua một biến tham chiếu kiểu interface đó.

### 2.1. Ví dụ JDK proxy thuần Java

Tạo interface:

```java
package com.example.proxy;

public interface Calculator {
    int add(int a, int b);
}
```

Implementation:

```java
package com.example.proxy;

public class SimpleCalculator implements Calculator {

    @Override
    public int add(int a, int b) {
        return a + b;
    }
}
```

Tạo proxy:

```java
package com.example.proxy;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class JdkProxyExample {

    public static void main(String[] args) {
        Calculator target = new SimpleCalculator();

        Calculator proxy = (Calculator) Proxy.newProxyInstance(
                Calculator.class.getClassLoader(),
                new Class<?>[] { Calculator.class },
                (proxyObject, method, arguments) -> {
                    System.out.println("Before: " + method.getName());
                    try {
                        Object result = method.invoke(target, arguments);
                        System.out.println("After: " + method.getName());
                        return result;
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                }
        );

        System.out.println(proxy.add(2, 3));
        System.out.println(proxy instanceof Calculator);
        System.out.println(proxy instanceof SimpleCalculator);
    }
}
```

Kết quả minh họa:

```text
Before: add
After: add
5
true
false
```

Trong ví dụ, JDK tạo runtime class triển khai `Calculator`. Vì nó không kế thừa `SimpleCalculator`, kiểm tra `proxy instanceof SimpleCalculator` trả về `false`.

Đây là ví dụ tối giản để hiểu nền tảng Java. Spring AOP không yêu cầu bạn tự gọi `Proxy.newProxyInstance`; framework quản lý interceptor, chain, pointcut và target theo các abstraction của Spring.

### 2.2. Vì sao JDK proxy cần interface?

JDK dynamic proxy sinh class triển khai một danh sách interface. Nó không thể tự tạo một subclass của một concrete class không có interface chỉ bằng API `java.lang.reflect.Proxy`.

Ví dụ, class này không có interface:

```java
public class InventoryService {

    public int available() {
        return 42;
    }
}
```

Nếu Spring AOP cần proxy cho `InventoryService` và không có interface phù hợp để sử dụng, Spring thường phải chọn cơ chế class-based proxy.

### 2.3. Interface là hợp đồng client nhìn thấy

Giả sử:

```java
public interface OrderService {
    void placeOrder(String orderId);
}
```

```java
@Service
public class DefaultOrderService implements OrderService {

    @Override
    public void placeOrder(String orderId) {
        System.out.println("Placed " + orderId);
    }

    public void internalRebuildIndex() {
        System.out.println("Rebuilding index");
    }
}
```

Với JDK interface proxy, client có tham chiếu kiểu `OrderService` và gọi được `placeOrder`. Method `internalRebuildIndex` không nằm trong contract của interface, nên không thể gọi qua `OrderService`.

Điều này thường là điểm tốt trong thiết kế: phần công khai của service được định nghĩa bằng interface, còn chi tiết riêng của implementation không bị sử dụng trực tiếp từ consumer.

## 3. Class-based proxy hoạt động như thế nào?

Class-based proxy của Spring thường sử dụng **CGLIB** (Code Generation Library), được Spring tích hợp và đóng gói lại trong `spring-core`.

Thay vì sinh object chỉ triển khai interface, Spring sinh một class **kế thừa concrete target class** và có thể override những method phù hợp để chèn logic interceptor.

Sơ đồ:

```text
       InventoryService
              ▲
              │ extends
              │
InventoryService$$SpringCGLIB$$...
              │
              ├── Interceptor / advice chain
              │
              └── Delegate sang target method
```

Tên class động có thể chứa ký hiệu như `$$SpringCGLIB$$` ở một số phiên bản Spring, nhưng không nên phụ thuộc tên đó vì là chi tiết implementation.

### 3.1. Ví dụ class không có interface

```java
package com.example.demo.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    public int countAvailable() {
        return 42;
    }
}
```

Nếu có một advisor áp dụng cho `countAvailable()` và Spring cần tạo proxy, class-based proxy cho phép client tiếp tục dùng kiểu `InventoryService`:

```java
@Service
public class InventoryControllerHelper {

    private final InventoryService inventoryService;

    public InventoryControllerHelper(
            InventoryService inventoryService
    ) {
        this.inventoryService = inventoryService;
    }

    public int available() {
        return inventoryService.countAvailable();
    }
}
```

Ở đây, proxy được tạo là một subtype của `InventoryService`. Vì vậy injection theo concrete class có thể hoạt động.

### 3.2. Điểm khác với JDK proxy

| Đặc tính | JDK dynamic proxy | Class-based proxy (CGLIB) |
|---|---|---|
| Cơ chế Java | Sinh class triển khai interface | Sinh subclass của target class |
| Target bắt buộc có interface? | Có interface để proxy | Không |
| Proxy là instance của interface? | Có, nếu interface được proxy | Có nếu target implement interface |
| Proxy là instance của concrete class? | Không | Thường có |
| Có thể proxy target class `final`? | Có thể nếu dùng interface | Không thể subclass `final` class |
| Có thể override `final` method? | Không cần subclass target để intercept lời gọi qua interface | Không thể override method `final` |
| Có thể intercept `private` method? | Không như một method contract thông thường | Không, vì private method không thể override |
| Injection theo concrete target type | Thường không phù hợp | Thường phù hợp |

**Class-based proxy không có nghĩa mọi method đều được advise.** Chỉ method được cơ chế proxy và pointcut hỗ trợ mới đi qua interceptor; final/private/static/constructor là các giới hạn quan trọng.

## 4. Spring AOP chọn proxy bằng những quy tắc nào?

Ở cấp Spring Framework, khi dùng cơ chế auto-proxying với mặc định interface-based, quy tắc khái quát là:

1. Nếu target có interface phù hợp và không bị ép dùng class proxy, Spring có thể dùng JDK dynamic proxy.
2. Nếu target không có interface phù hợp, Spring thường dùng class-based proxy.
3. Nếu cấu hình `proxyTargetClass = true`, Spring cố dùng class-based proxy dù target có interface.
4. Nếu bean không được advisor nào áp dụng, có thể hoàn toàn **không có AOP proxy**.

Sơ đồ:

```text
              Bean có cần AOP advice?
                        │
             ┌──────────┴──────────┐
             │                     │
            Không                  Có
             │                     │
             ▼                     ▼
      Bean không cần proxy    Có ép class proxy?
                                   │
                          ┌────────┴────────┐
                          │                 │
                         Có                Không
                          │                 │
                          ▼                 ▼
                    Class-based       Có interface phù hợp?
                    proxy (CGLIB)         │
                                    ┌──────┴──────┐
                                    │             │
                                   Có            Không
                                    │             │
                                    ▼             ▼
                                JDK proxy      Class proxy
```

Đây là mô hình suy luận cho việc chọn công nghệ proxy. Các framework integration cụ thể có thể cấu hình auto-proxy creator riêng hoặc hợp nhất các tùy chọn proxying trong container.

### 4.1. Spring Framework mặc định khác Spring Boot mặc định

Đây là điểm đặc biệt cần ghi nhớ.

Với Spring Framework khi dùng:

```java
@EnableAspectJAutoProxy
```

thuộc tính `proxyTargetClass` mặc định là `false`. Khi target có interface, JDK proxy là lựa chọn thường gặp.

Trong **Spring Boot** với AOP auto-configuration thông thường, Boot **mặc định cấu hình class-based proxy**. Property:

```properties
spring.aop.proxy-target-class=true
```

là giá trị mặc định thông dụng của Boot. Vì vậy, có interface không có nghĩa Boot chắc chắn sẽ tạo JDK proxy.

Muốn sử dụng JDK proxy khi có interface, có thể cấu hình:

```properties
spring.aop.proxy-target-class=false
```

Điều này cực kỳ quan trọng khi bạn chạy một ví dụ Spring Framework thuần rồi mang sang Spring Boot: cùng một service và aspect, loại proxy có thể khác do cấu hình mặc định.

### 4.2. Property chỉ có tác dụng trong hệ AOP đang được cấu hình

Property `spring.aop.proxy-target-class` thuộc cấu hình AOP của Spring Boot. Khi AOP auto-configuration/auto-proxying tương ứng hoạt động, nó điều khiển việc ưu tiên class proxy hay interface proxy.

Nếu ứng dụng tự thiết lập proxy factory, sử dụng custom auto-proxy creator hoặc các cơ chế proxy khác, cần xem cấu hình cụ thể của cơ chế đó. Không nên giả định một property luôn điều khiển mọi object proxy trong toàn JVM.

## 5. Cấu hình chuyển giữa JDK proxy và class-based proxy

### 5.1. Cấu hình trong application.properties

Để ưu tiên JDK dynamic proxy khi bean có interface:

```properties
spring.aop.proxy-target-class=false
```

Để dùng class-based proxy:

```properties
spring.aop.proxy-target-class=true
```

### 5.2. Cấu hình trong application.yml

Ưu tiên JDK proxy:

```yaml
spring:
  aop:
    proxy-target-class: false
```

Ưu tiên class proxy:

```yaml
spring:
  aop:
    proxy-target-class: true
```

### 5.3. Cấu hình bằng @EnableAspectJAutoProxy

Trong một ứng dụng Spring Framework tự cấu hình AOP, có thể viết:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
```

Muốn để Spring dùng chiến lược interface-based khi phù hợp:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AopConfiguration {
}
```

Tuy nhiên, trong Spring Boot, không nên vừa đặt property Boot vừa thêm nhiều annotation auto-proxy creator khác nhau mà không hiểu chúng tương tác thế nào. Các thiết lập yêu cầu class proxy có thể được Spring hợp nhất với mức mạnh hơn trong cùng bean factory.

Trong phần lớn ứng dụng Boot dùng `spring-boot-starter-aop`, hãy bắt đầu bằng property `spring.aop.proxy-target-class` và kiểm tra proxy thực tế.

### 5.4. Nếu không có interface thì sao?

Đặt:

```properties
spring.aop.proxy-target-class=false
```

**không buộc Spring tạo JDK proxy cho mọi bean**. Nếu một bean cần advice nhưng không có interface phù hợp, Spring vẫn có thể dùng class-based proxy.

Giá trị `false` nghĩa là không ép tất cả proxy phải dựa trên class; không có nghĩa mọi target có thể sử dụng JDK proxy.

### 5.5. Cấu hình khác có thể ép class proxy

Một ứng dụng có thể bật transaction management, async support, caching hoặc các auto-proxy creator khác. Một số cấu hình ép `proxyTargetClass=true` có thể tác động đến chính sách proxying của container, không chỉ một aspect.

Vì thế, nếu bạn đặt property `false` nhưng vẫn thấy class proxy, hãy kiểm tra các cơ chế proxy liên quan và liệu target có interface phù hợp hay không. Không kết luận ngay rằng property đã bị bỏ qua.

## 6. Demo Spring Boot: service, interface và @Aspect

Ta xây một ví dụ đủ nhỏ để quan sát trực tiếp sự khác biệt.

### 6.1. Dependency AOP

Với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Ví dụ giả định project đã có Spring Boot plugin, Java version và dependency management phù hợp. Starter AOP cung cấp những dependency cần thiết để dùng Spring AOP và AspectJ annotation style.

### 6.2. Interface của service

```java
package com.example.demo.payment;

public interface PaymentOperations {
    PaymentReceipt pay(String orderId);
}
```

Khai báo DTO:

```java
package com.example.demo.payment;

public record PaymentReceipt(
        String orderId,
        boolean successful
) {
}
```

`record` phù hợp với dự án dùng Java 17 trở lên, chẳng hạn các ứng dụng Spring Boot 3.

### 6.3. Implementation

```java
package com.example.demo.payment;

import org.springframework.stereotype.Service;

@Service
public class DefaultPaymentService implements PaymentOperations {

    @Override
    public PaymentReceipt pay(String orderId) {
        System.out.println("Đang thanh toán " + orderId);
        return new PaymentReceipt(orderId, true);
    }
}
```

### 6.4. Aspect đo thời gian

```java
package com.example.demo.payment;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class PaymentTimingAspect {

    @Around(
        "execution(* com.example.demo.payment..*.pay(..))"
    )
    public Object measure(ProceedingJoinPoint joinPoint)
            throws Throwable {

        long started = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - started;

            System.out.println(
                    "Payment method: " + joinPoint.getSignature()
                            + ", elapsed nanos = " + elapsed
            );
        }
    }
}
```

Pointcut chọn các method có tên `pay` trong package `com.example.demo.payment` và các subpackage. `@Around` gọi `proceed()` để chuyển tiếp lời gọi, sau đó ghi thời gian trong `finally`.

Nếu quên `joinPoint.proceed()` mà vẫn trả về một giá trị, business method có thể không được thực thi. Đây là lỗi quan trọng khi viết around advice.

### 6.5. Main class và runner

```java
package com.example.demo;

import com.example.demo.payment.PaymentOperations;
import org.springframework.aop.support.AopUtils;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner proxyInspector(PaymentOperations payments) {
        return args -> {
            System.out.println(
                    "Is AOP proxy: " + AopUtils.isAopProxy(payments)
            );
            System.out.println(
                    "Is JDK proxy: " + AopUtils.isJdkDynamicProxy(payments)
            );
            System.out.println(
                    "Is class proxy: " + AopUtils.isCglibProxy(payments)
            );
            System.out.println(
                    "Runtime class: " + payments.getClass().getName()
            );

            payments.pay("ORDER-001");
        };
    }
}
```

Nếu aspect được Spring phát hiện và advisor khớp, bean nhận bởi runner thường là AOP proxy.

### 6.6. Chạy với JDK dynamic proxy

Trong `application.yml`:

```yaml
spring:
  aop:
    proxy-target-class: false
```

Log minh họa:

```text
Is AOP proxy: true
Is JDK proxy: true
Is class proxy: false
Runtime class: jdk.proxy...$Proxy...
Đang thanh toán ORDER-001
Payment method: ..., elapsed nanos = ...
```

Tên runtime class có thể khác tùy JDK. Điều cần quan sát là kết quả `AopUtils`, không phải chuỗi tên class cụ thể.

### 6.7. Chạy với class-based proxy

Đổi:

```yaml
spring:
  aop:
    proxy-target-class: true
```

Log minh họa:

```text
Is AOP proxy: true
Is JDK proxy: false
Is class proxy: true
Runtime class: com.example.demo.payment.DefaultPaymentService$$SpringCGLIB$$...
Đang thanh toán ORDER-001
Payment method: ..., elapsed nanos = ...
```

Hai chế độ vẫn chạy nghiệp vụ và timing advice như nhau đối với lời gọi phù hợp. Khác biệt chính là cơ chế tạo proxy và các kiểu/giới hạn mà proxy hỗ trợ.

## 7. Proxy và dependency injection: vì sao inject theo interface an toàn hơn?

Giả sử `DefaultPaymentService` implement `PaymentOperations`.

Injection theo interface:

```java
@Service
public class CheckoutService {

    private final PaymentOperations payments;

    public CheckoutService(PaymentOperations payments) {
        this.payments = payments;
    }

    public void checkout(String orderId) {
        payments.pay(orderId);
    }
}
```

Phù hợp với cả:

- JDK dynamic proxy triển khai `PaymentOperations`.
- Class-based proxy kế thừa `DefaultPaymentService` và vẫn implement `PaymentOperations`.

Ngược lại, injection theo concrete class:

```java
@Service
public class CheckoutService {

    private final DefaultPaymentService payments;

    public CheckoutService(DefaultPaymentService payments) {
        this.payments = payments;
    }
}
```

có thể thất bại nếu Spring tạo JDK proxy cho service.

Lý do:

```text
JDK proxy
  implements PaymentOperations
  KHÔNG extends DefaultPaymentService
                │
                ▼
Không tương thích kiểu DefaultPaymentService
```

### 7.1. Biểu hiện khi inject concrete class

Khi dùng JDK proxy, bạn có thể gặp lỗi startup có nội dung đại ý:

```text
BeanNotOfRequiredTypeException:
Bean named 'defaultPaymentService' is expected to be of type
'DefaultPaymentService' but was actually of type
'jdk.proxy...$Proxy...'
```

Hoặc lỗi dependency injection liên quan tới việc không có candidate phù hợp theo concrete type.

Giải pháp ưu tiên:

1. Định nghĩa interface biểu diễn contract nghiệp vụ.
2. Inject interface vào consumer.
3. Đảm bảo method cần sử dụng được khai báo trong contract.
4. Chỉ bắt buộc dùng class-based proxy nếu kiến trúc thật sự cần proxy là subtype của concrete class.

### 7.2. Không dùng ép kiểu để giải quyết lỗi

Sai:

```java
DefaultPaymentService target =
        (DefaultPaymentService) payments;
```

Nếu `payments` là JDK proxy, cast này không hợp lệ và có thể ném `ClassCastException`.

Đúng hơn là dùng interface:

```java
PaymentOperations payments = context.getBean(
        PaymentOperations.class
);
```

Nếu mục tiêu là debug, dùng API của Spring AOP để xác định proxy/target type. Không ép kiểu tùy tiện hoặc bóc target khỏi proxy cho logic nghiệp vụ.

### 7.3. Class-based proxy có phải lúc nào cũng tốt hơn?

Không hẳn. Class-based proxy cho phép injection theo concrete class, nhưng phụ thuộc khả năng subclass/override method và chịu các giới hạn của Java inheritance.

JDK proxy khuyến khích consumer phụ thuộc vào interface; class-based proxy phù hợp khi không có interface hoặc cần tương thích với một thiết kế class cụ thể.

Việc Spring Boot mặc định dùng class-based proxy không có nghĩa nên ngừng thiết kế service qua interface ở mọi nơi.

## 8. Final class và final method: khác biệt rất quan trọng

Java cho phép khai báo class `final`:

```java
public final class FinalPaymentService
        implements PaymentOperations {

    @Override
    public PaymentReceipt pay(String orderId) {
        return new PaymentReceipt(orderId, true);
    }
}
```

### 8.1. JDK proxy có thể làm việc với final target class

JDK proxy triển khai interface `PaymentOperations`, không cần subclass `FinalPaymentService`. Vì vậy một target class final vẫn có thể được proxy qua interface.

Cấu hình `spring.aop.proxy-target-class=false` có thể cho phép dùng JDK proxy trong tình huống này, nếu các điều kiện AOP khác đều phù hợp.

### 8.2. Class-based proxy không subclass được final class

CGLIB tạo subclass. Java không cho phép kế thừa một class được khai báo `final`.

Vì vậy, nếu Spring thật sự cần tạo class-based AOP proxy cho `FinalPaymentService`, quá trình tạo proxy có thể thất bại.

Đừng giải thích rằng “Spring không thể AOP cho final class trong mọi trường hợp”. Nhận định chính xác hơn là **class-based proxy không thể kế thừa final class; interface-based proxy vẫn có thể là một giải pháp**.

### 8.3. Final method trong class-based proxy

Ví dụ:

```java
@Service
public class BillingService {

    public final void charge(String invoiceId) {
        System.out.println("Charge " + invoiceId);
    }
}
```

Class-based proxy không thể override `charge` vì method là `final`. Lời gọi tới method final đó không thể được Spring AOP class-proxy interceptor advise theo cách override thông thường.

Đây là lý do không nên đánh dấu method cần `@Transactional`, `@Async` hay `@Cacheable` là final nếu dựa vào class-based proxy.

### 8.4. Final method qua JDK interface proxy

Nếu một method public final của target **được khai báo trong interface được proxy**, lời gọi qua JDK proxy vẫn có thể đi qua `InvocationHandler`, vì proxy intercept ở interface boundary chứ không cần override target method.

Ví dụ:

```java
public interface Operation {
    void execute();
}
```

```java
public class FinalMethodOperation implements Operation {

    @Override
    public final void execute() {
        System.out.println("Executing");
    }
}
```

Với JDK interface proxy cho `Operation`, lời gọi `proxy.execute()` vẫn đi qua proxy. `final` trên implementation method không tự ngăn JDK proxy intercept lời gọi giao diện này.

**Kết luận theo cơ chế:** hạn chế final method là hạn chế override của **class proxy**, không phải hạn chế chung của mọi lời gọi thông qua interface proxy.

## 9. Private, static, constructor và non-public methods

Một AOP proxy không thể tùy ý intercept mọi thao tác Java.

### 9.1. Private method

```java
@Service
public class ReportService {

    public void publish() {
        validateInternal();
    }

    private void validateInternal() {
        // ...
    }
}
```

Method `private` không thể override bởi subclass và không thuộc contract public của JDK interface proxy. Vì vậy Spring AOP proxy không trực tiếp advise lời gọi tới private method này.

Nếu hành vi quan trọng cần advice, hãy đưa điểm cắt vào một method thích hợp có thể được gọi qua proxy, hoặc tách hành vi sang bean khác.

### 9.2. Static method

`static` method thuộc class và không được dispatch như instance method theo cách mà AOP proxy intercept. Không trông đợi `@Transactional` trên static utility method hoạt động như trên instance method được gọi qua Spring bean proxy.

### 9.3. Constructor

Spring AOP proxy chủ yếu intercept method execution đi qua proxy. Constructor không phải điểm cắt mà proxy này tự động chặn để thêm `@Around`.

Nếu cần chạy logic sau khi dependency injection, dùng lifecycle callback tương ứng; nếu cần can thiệp sâu vào object construction, đó là phạm vi khác với proxy-based Spring AOP thông thường.

### 9.4. Protected/package-private methods

JDK interface proxy chỉ bộc lộ các phương thức thông qua interface, thông thường là public instance methods.

Class-based proxy có thể override một số method `protected` hoặc package-private nếu Java visibility và cơ chế Spring cho phép. Tuy nhiên, **khả năng được proxy ở cấp kỹ thuật không bảo đảm mọi annotation framework đều áp dụng cho mọi non-public method**. Cần xét phiên bản Spring và rule của `@Transactional`, `@Async`, `@Cacheable` hoặc advisor cụ thể.

Lựa chọn ít gây bất ngờ khi học Spring AOP là đặt điểm cắt chính trên **public service method được gọi từ bean khác**.

## 10. Self-invocation: lời gọi bên trong cùng object không đi qua proxy

Đây là một trong những lỗi Spring AOP phổ biến nhất.

Ví dụ:

```java
@Service
public class OrderService {

    @Transactional
    public void saveOrder() {
        System.out.println("Saving order");
    }

    public void createOrder() {
        // Gọi trực tiếp method khác trên cùng object.
        saveOrder();
    }
}
```

Giả sử một controller inject `OrderService` và gọi:

```java
orderService.createOrder();
```

Luồng thực tế khái quát:

```text
Controller
    │
    ▼
Spring proxy
    │
    ▼
Target.createOrder()
    │
    └── this.saveOrder()
          │
          └── Gọi nội bộ trên target,
              KHÔNG qua proxy lần nữa
```

Vì vậy, advice chỉ áp dụng cho `saveOrder()` khi lời gọi đó đi qua proxy, không tự áp dụng cho một lời gọi trực tiếp `this.saveOrder()` ở bên trong cùng target.

### 10.1. Có khác giữa JDK proxy và CGLIB không?

Đối với **Spring AOP proxy-based** thông thường, vấn đề self-invocation vẫn tồn tại ở **cả hai** chiến lược.

Dù CGLIB tạo subclass, Spring AOP vẫn quản lý lời gọi từ proxy đến target theo cơ chế của framework. Một lời gọi nội bộ qua `this` của target không tự chuyển lại qua outer proxy.

Không nên kết luận “đổi từ JDK sang CGLIB sẽ sửa được mọi lỗi `@Transactional` do self-invocation”.

### 10.2. Cách sửa khuyến nghị: tách sang một bean khác

```java
@Service
public class OrderPersistenceService {

    @Transactional
    public void saveOrder() {
        System.out.println("Saving order");
    }
}
```

```java
@Service
public class OrderWorkflowService {

    private final OrderPersistenceService persistence;

    public OrderWorkflowService(
            OrderPersistenceService persistence
    ) {
        this.persistence = persistence;
    }

    public void createOrder() {
        // Lời gọi đi qua bean dependency do Spring inject.
        persistence.saveOrder();
    }
}
```

Khi `persistence` là proxy được container cung cấp, lời gọi `saveOrder()` đi qua advice phù hợp.

Thiết kế này thường tốt hơn vì trách nhiệm transaction được đặt ở một service boundary rõ ràng.

### 10.3. Có thể tự lấy proxy của mình không?

Spring AOP có `AopContext.currentProxy()` trong một số cấu hình khi `exposeProxy` được bật.

Tuy nhiên, cách này làm business code phụ thuộc mạnh vào Spring AOP infrastructure và có thể tạo coupling, khó test hoặc lỗi khi code không chạy trong proxy invocation context phù hợp.

Không nên coi việc tự gọi `AopContext.currentProxy()` là giải pháp mặc định cho self-invocation. Hãy ưu tiên tách trách nhiệm hoặc thay đổi điểm gọi.

### 10.4. AspectJ weaving khác proxy AOP

Full AspectJ compile-time hoặc load-time weaving có thể can thiệp trực tiếp vào bytecode thay vì chỉ chặn lời gọi qua proxy. Vì vậy, một số hạn chế của proxy-based AOP như self-invocation có thể được giải quyết khác đi khi dùng weaving.

Nhưng chỉ thêm `spring-boot-starter-aop` **không có nghĩa** ứng dụng đã bật AspectJ weaving. Bài này tập trung vào Spring AOP proxy; weaving là một cơ chế cần cấu hình, triển khai và kiểm thử riêng.

## 11. @Transactional, @Async và @Cacheable liên quan thế nào?

Trong các chế độ proxy thông dụng, nhiều annotation Spring có thể được thực hiện bằng proxy/advice.

### 11.1. @Transactional

```java
@Service
public class TransferService {

    @Transactional
    public void transfer() {
        // Các lời gọi database trong transaction context phù hợp.
    }
}
```

Transaction interceptor có thể bắt đầu/commit/rollback transaction quanh lời gọi qua proxy. Nếu lời gọi bỏ qua proxy vì self-invocation, transaction advice của method bên trong có thể không chạy như mong đợi.

Lưu ý transaction hoạt động còn tùy transaction manager, cấu hình, phạm vi propagation và exception semantics; proxy chỉ là cơ chế intercept.

### 11.2. @Async

```java
@Service
public class MailService {

    @Async
    public void sendMail() {
        // Công việc có thể được chuyển sang executor.
    }
}
```

Với chế độ proxy mặc định của async support, lời gọi từ một bean khác đi qua proxy để chuyển công việc sang executor.

Nếu tự gọi `this.sendMail()`, lời gọi có thể thực hiện đồng bộ vì bỏ qua proxy.

### 11.3. @Cacheable

```java
@Service
public class ProductCatalog {

    @Cacheable("products")
    public Product findById(String id) {
        // Truy vấn dữ liệu.
        return loadProduct(id);
    }
}
```

Cache interceptor chỉ áp dụng ở những điểm gọi phù hợp qua proxy. Nếu method này được gọi nội bộ mà không đi qua proxy, cache advice có thể không có tác dụng.

### 11.4. Annotation không tự tạo AOP proxy trong mọi trường hợp

Cần bật/configure các subsystem tương ứng:

- Transaction support và `PlatformTransactionManager` thích hợp.
- Async support (chẳng hạn `@EnableAsync`) và executor.
- Caching support (chẳng hạn `@EnableCaching`) và cache manager.
- AspectJ-style AOP với `@Aspect` và hạ tầng phù hợp.

Đừng quy mọi lỗi annotation không chạy thành lỗi chọn JDK hay CGLIB. Có thể subsystem chưa bật, advisor không match, method không đi qua proxy hoặc bean không do Spring quản lý.

## 12. Chú ý annotation đặt trên interface hay implementation

Với JDK proxy, client gọi method qua interface; với class-based proxy, client gọi proxy subclass. Nhưng Spring có cơ chế tra cứu metadata trên target method, class và interface theo từng advisor.

Ví dụ:

```java
public interface BillingOperations {

    void charge(String invoiceId);
}
```

```java
@Service
public class BillingService implements BillingOperations {

    @Override
    @Transactional
    public void charge(String invoiceId) {
        // ...
    }
}
```

Đặt `@Transactional` trên implementation method thường rõ ràng khi bạn muốn behavior áp dụng cho concrete business code và giảm sự phụ thuộc vào cách annotation trên interface được diễn giải.

Nếu chỉ đặt annotation trên interface, hành vi có thể phụ thuộc cơ chế annotation matching, framework version và proxy mode; không nên giả định mọi loại annotation tự được kế thừa từ interface khi chuyển sang class-based proxy.

Một nguyên tắc thực hành là: **kiểm thử behavior thực sự dưới chế độ proxy mà ứng dụng sử dụng**, nhất là khi nâng cấp từ JDK proxy sang class-based proxy hoặc ngược lại.

## 13. Proxy được tạo ở giai đoạn nào của bean lifecycle?

Một Spring bean thông thường đi qua các bước:

```text
Bean definition
      │
      ▼
Instantiate target
      │
      ▼
Dependency injection
      │
      ▼
Lifecycle initialization
      │
      ▼
BeanPostProcessor / AOP infrastructure
      │
      ▼
Proxy được đưa vào container/consumer
      │
      ▼
Lời gọi nghiệp vụ từ bean khác
```

Đây là mô hình đơn giản. Spring có thể tạo early reference hoặc proxy ở những thời điểm khác nhau tùy circular dependency và hạ tầng AOP.

Điều cần hiểu:

- Constructor của target không phải một lời gọi method qua AOP proxy.
- `@PostConstruct` thông thường chạy trong giai đoạn khởi tạo target, trước khi bean được đưa ra cho consumer theo proxy cuối cùng.
- Gọi một method được annotate từ constructor hoặc `@PostConstruct` của cùng bean thường không đi qua proxy đó.
- Một object bạn tự tạo bằng `new` ngoài container không tự được Spring AOP áp dụng.

### 13.1. Object tạo bằng new không phải AOP bean

Ví dụ:

```java
PaymentOperations payment = new DefaultPaymentService();
payment.pay("ORDER-001");
```

Lời gọi này đi thẳng vào target. Dù `DefaultPaymentService` mang `@Service` hoặc method được annotate, object tự tạo bằng `new` không tự trở thành proxy do Spring quản lý.

Đúng hơn trong ứng dụng Spring:

```java
@Service
public class CheckoutService {

    private final PaymentOperations payment;

    public CheckoutService(PaymentOperations payment) {
        this.payment = payment;
    }

    public void checkout() {
        payment.pay("ORDER-001");
    }
}
```

Container inject một bean phù hợp, có thể là proxy nếu advisor áp dụng.

## 14. Không phải bean nào cũng trở thành proxy

Giả sử project có `spring-boot-starter-aop`, một `@Aspect` và mười service. Spring không nhất thiết tạo proxy cho cả mười.

Nếu pointcut chỉ chọn method `pay` trong package payment, những service không có join point khớp có thể vẫn là object thường.

Điều đó tạo ra một quy tắc chẩn đoán:

```text
AopUtils.isAopProxy(bean) == false
```

không tự chứng minh rằng “Spring Boot không bật AOP”. Có thể bean đó không cần advice.

### 14.1. Pointcut quyết định có được advise hay không

Ví dụ:

```java
@Around("execution(* com.example.demo.payment..*.pay(..))")
```

chỉ nhắm tới method phù hợp biểu thức này.

Nếu service thực tế nằm trong package khác hoặc tên method là `checkout`, pointcut không match và bạn không thấy log advice.

Đừng đổi `spring.aop.proxy-target-class` chỉ để sửa một biểu thức pointcut sai.

### 14.2. Aspect cần được Spring phát hiện

```java
@Aspect
@Component
public class PaymentTimingAspect {
    // ...
}
```

`@Aspect` mô tả aspect. `@Component` hoặc một đường đăng ký bean phù hợp giúp Spring quản lý aspect đó.

Nếu class aspect nằm ngoài vùng component scan và không được import/đăng ký, advice không được cấu hình tự động như mong muốn.

## 15. Kiểm tra loại proxy bằng AopUtils

Spring cung cấp tiện ích:

```java
import org.springframework.aop.support.AopUtils;
```

Các phương thức hữu ích:

```java
AopUtils.isAopProxy(bean);
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
```

Ví dụ:

```java
@Component
public class ProxyInspector implements ApplicationRunner {

    private final PaymentOperations payments;

    public ProxyInspector(PaymentOperations payments) {
        this.payments = payments;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "AOP proxy = " + AopUtils.isAopProxy(payments)
        );
        System.out.println(
                "JDK proxy = " + AopUtils.isJdkDynamicProxy(payments)
        );
        System.out.println(
                "CGLIB proxy = " + AopUtils.isCglibProxy(payments)
        );
    }
}
```

Cách này rõ ràng hơn so với suy luận từ chuỗi của `getClass().getName()`.

### 15.1. Proxy runtime class khác target class

Với JDK proxy:

```text
proxy.getClass() -> class được JDK sinh
target class      -> DefaultPaymentService
```

Với class-based proxy:

```text
proxy.getClass() -> subclass được Spring/CGLIB sinh
target class      -> DefaultPaymentService
```

Do đó, nếu mục tiêu là biết business type thực, không nên mặc định `bean.getClass() == DefaultPaymentService.class`.

Trong code chẩn đoán có thể dùng:

```java
import org.springframework.aop.framework.AopProxyUtils;

Class<?> targetType =
        AopProxyUtils.ultimateTargetClass(bean);

System.out.println(targetType.getName());
```

`ultimateTargetClass` là một tiện ích hữu ích để nhận diện target class qua hạ tầng AOP phổ biến. Khi làm việc với proxy nhiều tầng hoặc custom TargetSource, cần xét ngữ cảnh cụ thể và không dùng introspection để thay thế một API business rõ ràng.

### 15.2. Không dùng instanceof như phép đo duy nhất

Kiểm tra:

```java
bean instanceof PaymentOperations
```

có thể trả `true` cho cả JDK proxy và class-based proxy nếu bean hỗ trợ interface.

Kiểm tra:

```java
bean instanceof DefaultPaymentService
```

có thể phân biệt hai chiến lược trong ví dụ đơn giản, nhưng không khẳng định chắc chắn có hay không AOP. Một target thật chưa proxy cũng là instance của concrete class.

Hãy dùng `AopUtils` khi mục tiêu là xác định proxy type.

## 16. Thử trực tiếp bằng ProxyFactory

Spring cung cấp `ProxyFactory` để tạo proxy thủ công. Ví dụ này giúp tách việc chọn proxy khỏi toàn bộ cơ chế component scanning và auto-configuration.

Interface:

```java
public interface GreetingOperations {
    String greet(String name);
}
```

Implementation:

```java
public class GreetingService implements GreetingOperations {

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Tạo JDK proxy:

```java
import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;

public class ProxyFactoryDemo {

    public static void main(String[] args) {
        ProxyFactory factory = new ProxyFactory();

        factory.setTarget(new GreetingService());
        factory.setInterfaces(GreetingOperations.class);
        factory.setProxyTargetClass(false);

        factory.addAdvice((MethodInterceptor) invocation -> {
            System.out.println("Before greet");
            return invocation.proceed();
        });

        GreetingOperations proxy =
                (GreetingOperations) factory.getProxy();

        System.out.println(AopUtils.isJdkDynamicProxy(proxy));
        System.out.println(proxy.greet("Lan"));
    }
}
```

Để dùng class-based proxy, trong cùng ví dụ đổi:

```java
factory.setProxyTargetClass(true);
```

Sau đó proxy có thể là subtype của `GreetingService`:

```java
Object proxy = factory.getProxy();

System.out.println(AopUtils.isCglibProxy(proxy));
System.out.println(proxy instanceof GreetingService);
```

Ví dụ này minh họa `ProxyFactory`, không phải cách nên dùng trong mọi service. Trong ứng dụng Spring Boot, auto-proxying thường đảm nhiệm việc tạo proxy cho các advisor đã đăng ký.

### 16.1. Vì sao ProxyFactory hữu ích để học?

Nó cho phép tự kiểm soát:

- Target object.
- Interface được proxy.
- Chế độ ép proxy theo class.
- Advice/interceptor cần chạy.
- Thời điểm lấy proxy.

Nhờ đó, bạn có thể xác định vấn đề thuộc cơ chế Java proxy hay thuộc Spring container, pointcut, component scan hoặc configuration.

## 17. Proxy và method overload, generic, bridge method

Trong dự án Java thực tế, service có thể có method overload hoặc generic interface:

```java
public interface Repository<T> {
    T save(T value);
}
```

```java
public class UserRepository implements Repository<User> {

    @Override
    public User save(User value) {
        return value;
    }
}
```

Java compiler có thể tạo **bridge methods** để giữ tương thích kiểu sau type erasure. Spring AOP và các công cụ reflection của Spring có cơ chế xử lý method resolution/bridge method khi cần.

Tuy nhiên, khi viết pointcut quá phụ thuộc vào signature ở runtime, overload hoặc generic method có thể làm việc match phức tạp hơn mong đợi.

Một vài nguyên tắc:

- Ưu tiên pointcut rõ ràng theo package, class, annotation và method.
- Kiểm tra method nào thực sự được advisor match.
- Không suy luận toàn bộ behavior chỉ từ method name.
- Test cả overload quan trọng nếu chúng có yêu cầu transaction/caching khác nhau.

Đừng cố sửa lỗi generic bridge method bằng cách đổi loại proxy trước khi xác minh pointcut và annotation metadata.

## 18. CGLIB và những giới hạn của Java inheritance

Class-based proxy dựa vào subclass, nên phải tuân theo những ràng buộc của Java.

### 18.1. Final class

Không thể subclass `final class`, do đó không thể tạo class-based proxy theo cách CGLIB.

### 18.2. Final method

Không thể override `final method`, nên method này không được class proxy intercept theo cơ chế override.

### 18.3. Private method

Không thể override method private; class proxy không thể advise nó trực tiếp.

### 18.4. Visibility/package boundary

Một method package-private nằm ở package khác hoặc không nhìn thấy từ subclass có thể không được override theo cách cần thiết.

### 18.5. Java module system

Nếu ứng dụng chạy với Java Platform Module System (JPMS), quyền truy cập module/package có thể giới hạn việc tạo class proxy hoặc reflect vào những class cụ thể.

Ví dụ, việc cố proxy một class thuộc một package của JDK có thể vướng hạn chế mở package; một số tình huống cần `--add-opens`, nhưng không nên thêm cờ này tùy tiện. Ưu tiên proxy các service class do ứng dụng sở hữu hoặc dùng interface proxy khi phù hợp.

### 18.6. Constructor và side effect

CGLIB tạo subclass, nhưng cách Spring instantiate proxy có thể dùng Objenesis để tránh gọi constructor của proxy thêm một lần không cần thiết. Không nên dựa vào việc constructor được gọi một hay nhiều lần để xác định loại proxy hoặc để thực hiện side effect quan trọng.

Bất kể dùng proxy nào, constructor của target không phải một AOP-advised method call.

## 19. Kotlin, record và class mặc định final

Một số mô hình ngôn ngữ dễ gặp giới hạn class proxy.

### 19.1. Kotlin classes mặc định final

Trong Kotlin, class và method mặc định không mở để kế thừa. Vì vậy, một `@Service` Kotlin nếu không được mở phù hợp có thể không thể tạo class-based proxy.

Hệ sinh thái Kotlin có plugin `kotlin-spring`/`all-open` giúp tự động mở các class được annotate bằng một số stereotype của Spring.

Điểm cần kiểm tra:

- Class có thể subclass được không?
- Method cần advice có thể override được không?
- Kotlin plugin đã được cấu hình chưa?
- Bean có interface để dùng JDK proxy không?

Không nên chữa bằng cách đổi ngẫu nhiên giữa proxy modes mà không hiểu Kotlin-generated bytecode.

### 19.2. Java record là final

Java `record` là class final. Nó rất phù hợp cho DTO, value object và configuration data immutable, nhưng không phải lựa chọn tự nhiên cho một class service cần class-based AOP proxy.

Có thể dùng record làm giá trị trả về của service; không cần biến mọi record thành bean có AOP advice.

### 19.3. Immutable domain object khác service bean

Một entity, value object hoặc DTO không cần được Spring AOP proxy hóa chỉ vì ứng dụng sử dụng Spring Boot. Hãy để AOP nằm ở service boundary thích hợp, nơi cross-cutting behavior có ý nghĩa.

## 20. Không nhầm AOP class proxy với các loại proxy khác trong Spring

Spring có nhiều cơ chế tạo proxy hoặc tăng cường class. Chúng có thể dùng công nghệ giống nhau nhưng **không có cùng mục đích**.

### 20.1. @Configuration(proxyBeanMethods = true)

Một `@Configuration` class có thể được Spring tăng cường để bảo đảm các lời gọi giữa những `@Bean` methods phù hợp được định tuyến qua container.

Ví dụ:

```java
@Configuration(proxyBeanMethods = true)
public class AppConfiguration {

    @Bean
    public Client client() {
        return new Client();
    }

    @Bean
    public ClientConsumer consumer() {
        return new ClientConsumer(client());
    }
}
```

Lớp configuration được enhance bằng cơ chế class generation trong một số chế độ. Nhưng đây là xử lý lifecycle/configuration semantics của `@Bean` methods, **không đồng nghĩa rằng mọi method của configuration class đều được Spring AOP aspect advise**.

Với `proxyBeanMethods = false`, Spring không cần proxy class để intercept các lời gọi giữa `@Bean` methods theo cách đó. Đây là quyết định về cấu hình bean, không phải cách chọn JDK hay CGLIB cho `@Transactional`.

### 20.2. Scoped proxy

Một request-scoped bean được inject vào singleton có thể cần scoped proxy:

```java
@RequestScope(proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestContextData {
    // ...
}
```

Proxy chuyển lời gọi đến đúng target instance của request hiện tại. Nó có thể là class-based proxy nhưng mục đích là quản lý scope, không phải timing advice.

Đừng suy ra rằng mọi bean có runtime class dạng proxy đều do một `@Aspect` tạo ra.

### 20.3. Lazy proxy và các decorator khác

Một số hạ tầng sử dụng proxy để trì hoãn việc tạo dependency hoặc chuyển lời gọi đến target về sau. Mục đích khác với AOP advice, dù cùng liên quan đến một object trung gian.

Khi debug, hãy xác định proxy xuất hiện vì AOP, scope, lazy resolution hay cơ chế khác trước khi sửa config.

## 21. Vấn đề proxy lồng nhau và nhiều advisor

Một method có thể chịu nhiều cross-cutting behavior:

- Transaction.
- Security.
- Caching.
- Timing/metrics.
- Retry.
- Async.

Spring có thể tạo một proxy chứa chuỗi advisor/interceptor, hoặc trong một số cấu hình tạo proxy nhiều tầng.

Sơ đồ khái quát:

```text
Caller
   │
   ▼
Proxy
   ├── Security advice
   ├── Transaction advice
   ├── Metrics advice
   │
   ▼
Target method
```

Thứ tự advice **không được quyết định bởi JDK hay CGLIB**. Framework sử dụng ordering/precedence và quy tắc riêng của advisor.

Nếu cần điều khiển thứ tự aspect:

```java
@Aspect
@Component
@Order(10)
public class LoggingAspect {
    // ...
}
```

Có thể dùng `@Order` để biểu đạt precedence cho aspect tương ứng. Đây là cơ chế khác với `spring.aop.proxy-target-class`: một cái chọn **advice nào chạy trước**, cái kia chọn **proxy được tạo theo kiểu nào**.

### 21.1. Một proxy có thể mang nhiều interface

JDK proxy có thể triển khai nhiều interface:

```java
Proxy.newProxyInstance(
        loader,
        new Class<?>[] {
                PaymentOperations.class,
                Auditable.class
        },
        handler
);
```

Spring AOP cũng có thể quảng bá các interface phù hợp theo cấu hình. Vì vậy, JDK proxy không bị giới hạn đúng một interface.

### 21.2. Nhiều advisor không có nghĩa cần nhiều proxy object

Một Spring AOP proxy có thể chứa interceptor chain với nhiều advisor. Không cần sinh một wrapper mới cho từng `@Aspect` trong mọi trường hợp.

Khi điều tra proxy type và advisor order, hãy tách hai câu hỏi:

1. **Proxy type:** interface-based hay class-based?
2. **Advisor chain:** các advice nào được áp dụng và theo thứ tự nào?

## 22. Chẩn đoán khi @Transactional hoặc @Aspect không hoạt động

Khi thấy advice không chạy, thực hiện kiểm tra theo trình tự.

### 22.1. Bean có do Spring quản lý không?

Nếu object được tạo bằng `new`, Spring AOP không tự intercept nó.

### 22.2. Hạ tầng AOP hoặc subsystem đã được bật chưa?

Kiểm tra starter/dependency và các annotation/cấu hình `@Enable...` liên quan. Có `@Aspect` trong source nhưng class không được scan cũng không tạo advice.

### 22.3. Proxy có thực sự tồn tại không?

Sử dụng:

```java
AopUtils.isAopProxy(bean)
```

Nếu false, cần xác định đó là bean không được advisor match hay AOP infrastructure chưa hoạt động.

### 22.4. Proxy là loại gì?

```java
AopUtils.isJdkDynamicProxy(bean)
AopUtils.isCglibProxy(bean)
```

Đối chiếu với `spring.aop.proxy-target-class`, interface và các cấu hình proxying khác.

### 22.5. Có đi qua proxy không?

Ví dụ:

```java
this.save();
```

là self-invocation, không đi qua Spring AOP proxy thông thường. Hãy thử gọi từ một bean khác qua dependency được inject.

### 22.6. Method có thể được intercept không?

Kiểm tra:

- Method `private`?
- Method `final` với class proxy?
- Target class `final` nhưng bị ép class proxy?
- Method không có trong interface khi dùng JDK proxy?
- Method `static` hoặc constructor?
- Advisor của subsystem có chỉ hỗ trợ một số visibility nhất định không?

### 22.7. Pointcut hoặc annotation metadata có match không?

Kiểm tra package, tên method, signature, annotation location và phiên bản framework.

### 22.8. Lỗi xảy ra khi inject bean theo concrete class?

Nếu JDK proxy được tạo, đổi constructor injection sang interface là cách xử lý phổ biến. Không giải quyết bằng cast target class từ proxy.

### 22.9. Có proxy khác không phải AOP không?

Nếu type trông giống proxy nhưng `AopUtils` không cho thấy AOP proxy mong muốn, kiểm tra scoped proxy, configuration enhancement, lazy resolution hoặc cơ chế khác.

## 23. Bảng lỗi thường gặp

| Hiện tượng | Giải thích có thể | Hướng xử lý |
|---|---|---|
| Inject `DefaultPaymentService` thất bại khi dùng JDK proxy | JDK proxy chỉ triển khai interface, không là subtype của implementation | Inject `PaymentOperations` |
| `ClassCastException` khi cast proxy về implementation | Proxy không extends target class | Không cast; dùng interface |
| Class `final` không tạo được CGLIB proxy | Không thể subclass final class | Bỏ final khi thích hợp hoặc dùng interface proxy |
| `@Transactional` không chạy trên final method | Class proxy không override được final method | Bỏ final hoặc thiết kế lại boundary |
| `@Transactional` không chạy khi method tự gọi | Self-invocation bỏ qua proxy | Tách sang bean khác |
| Thêm `@Aspect` nhưng không thấy advice | Aspect không thành bean hoặc pointcut không match | Kiểm tra component scan và pointcut |
| `AopUtils.isAopProxy` là false | Bean không có advisor phù hợp hoặc AOP chưa bật | Kiểm tra infrastructure và advisor |
| Đặt `proxy-target-class=false` nhưng vẫn thấy CGLIB | Bean không có interface hoặc có cấu hình khác ép class proxy | Kiểm tra interface và proxy settings |
| Đặt `proxy-target-class=true` nhưng method private không được intercept | Class proxy không override private method | Dùng service boundary public phù hợp |
| Thấy `$$SpringCGLIB$$` rồi kết luận do @Aspect | Configuration/scoped proxies cũng có thể dùng class generation | Xác định cơ chế proxy thực tế |
| Advice hoạt động với gọi từ bean khác nhưng không hoạt động từ `@PostConstruct` | Callback chạy trong initialization, không phải lời gọi ngoài qua proxy | Dời logic hoặc thay thiết kế lifecycle |
| JDK proxy vẫn chặn lời gọi vào final target method | Proxy intercept tại interface, không cần override target method | Đây là hành vi có thể xảy ra đúng theo cơ chế |

## 24. Kiểm thử proxy mode có chủ đích

Một ứng dụng có thể trông như hoạt động bình thường dưới class-based proxy nhưng gặp lỗi injection khi đổi sang JDK proxy. Nếu thư viện hoặc module cần hỗ trợ cả hai chế độ, nên kiểm tra chúng riêng.

### 24.1. Test chế độ JDK

Ví dụ với Spring Boot test:

```java
@SpringBootTest(
        properties = "spring.aop.proxy-target-class=false"
)
class JdkProxyTest {

    @Autowired
    PaymentOperations payments;

    @Test
    void usesJdkProxy() {
        assertThat(AopUtils.isAopProxy(payments)).isTrue();
        assertThat(AopUtils.isJdkDynamicProxy(payments)).isTrue();
    }
}
```

Test giả định `PaymentOperations` có implementation và aspect/advisor phù hợp để bean được AOP-proxy hóa.

### 24.2. Test chế độ class-based

```java
@SpringBootTest(
        properties = "spring.aop.proxy-target-class=true"
)
class ClassProxyTest {

    @Autowired
    PaymentOperations payments;

    @Test
    void usesClassProxy() {
        assertThat(AopUtils.isAopProxy(payments)).isTrue();
        assertThat(AopUtils.isCglibProxy(payments)).isTrue();
    }
}
```

Nếu bean không được advisor nào match, `isAopProxy` có thể false và test này không có ý nghĩa về proxy strategy. Hãy bảo đảm test tạo được advised bean.

### 24.3. Test behavior thay vì chỉ test class

Một integration test tốt còn phải kiểm tra advice thực sự chạy:

- Timing advice ghi nhận lời gọi mong muốn.
- Transaction được bật cho method boundary phù hợp.
- Cache hit không gọi lại repository ngoài dự kiến.
- Async method chuyển sang executor được cấu hình.
- Self-invocation không bị hiểu nhầm là external proxy call.

Chỉ test rằng proxy class chứa chuỗi `CGLIB` không chứng minh behavior nghiệp vụ đúng.

## 25. Khi nào nên chọn JDK proxy, khi nào chọn class-based proxy?

### Chọn JDK dynamic proxy khi

- Bạn có interface rõ ràng cho service boundary.
- Client chỉ cần các method trong interface.
- Muốn tách contract khỏi implementation cụ thể.
- Target class là final nhưng vẫn implement interface phù hợp.
- Muốn tránh phụ thuộc vào việc subclass concrete class.
- Có yêu cầu tương thích với thư viện/thiết kế interface-driven.

Ví dụ:

```java
public interface InvoiceOperations {
    void issueInvoice(String id);
}
```

Consumer inject `InvoiceOperations`, không phụ thuộc kiểu concrete.

### Chọn class-based proxy khi

- Target không có interface phù hợp.
- Ứng dụng Spring Boot dùng cấu hình mặc định và service class có thể subclass.
- Consumer có lý do hợp lệ cần injection theo concrete type.
- Method cần advise có thể được override và đáp ứng giới hạn visibility.
- Bạn chấp nhận các ràng buộc của inheritance và runtime class generation.

Ví dụ:

```java
@Service
public class SearchIndexer {

    public void rebuild() {
        // ...
    }
}
```

Nếu `rebuild()` được advisor áp dụng và không có interface, class proxy là lựa chọn tự nhiên.

### 25.1. Bảng quyết định

| Câu hỏi | Gợi ý |
|---|---|
| Service có interface và consumer inject interface? | JDK hoặc class proxy đều có thể phù hợp |
| Service không có interface? | Class-based proxy nếu cần AOP |
| Target class là final? | Xem JDK interface proxy nếu có interface |
| Method cần advice là final? | Tránh class proxy cho method đó; cân nhắc API/interface và thiết kế |
| Có self-invocation? | Tách bean hoặc thay service boundary; đổi proxy type không đủ |
| Spring Boot đang dùng mặc định? | Thường là class-based proxy với AOP auto-config |
| Muốn thử interface-based? | `spring.aop.proxy-target-class=false` và xác nhận bằng `AopUtils` |
| Inject implementation thất bại với JDK proxy? | Ưu tiên inject interface |
| Không có advice nào match? | Có thể không cần AOP proxy |

Đừng chọn chỉ theo quan niệm “JDK luôn nhanh hơn” hoặc “CGLIB luôn nhanh hơn”. Hiệu năng phụ thuộc nhiều yếu tố và thường nhỏ hơn chi phí của database/network I/O. Hãy chọn theo contract, giới hạn kỹ thuật, nhu cầu framework và sự rõ ràng của thiết kế.

## 26. Bài thực hành

### Bài 1 — Tạo JDK dynamic proxy thuần Java

Tạo interface `Calculator`, implementation `SimpleCalculator` và `InvocationHandler`. Ghi log trước/sau `add(...)`. Kiểm tra `instanceof Calculator` và `instanceof SimpleCalculator` để giải thích bản chất interface proxy.

### Bài 2 — Quan sát proxy mặc định của Spring Boot

Tạo project với `spring-boot-starter-aop`, một `@Service` và một `@Aspect` có pointcut khớp. Dùng `AopUtils` in proxy type khi chưa cấu hình `spring.aop.proxy-target-class`.

### Bài 3 — Chuyển sang JDK proxy

Thêm:

```properties
spring.aop.proxy-target-class=false
```

Chạy lại, kiểm tra `AopUtils.isJdkDynamicProxy(...)`. Giải thích vì sao bean phải có interface phù hợp.

### Bài 4 — Chuyển sang class-based proxy

Đặt:

```properties
spring.aop.proxy-target-class=true
```

Kiểm tra `AopUtils.isCglibProxy(...)` và `instanceof` concrete implementation.

### Bài 5 — Inject theo interface và concrete class

Tạo `CheckoutService` nhận `PaymentOperations`, rồi đổi sang `DefaultPaymentService`. Chạy dưới hai proxy mode và giải thích các kết quả, đặc biệt lỗi kiểu dữ liệu với JDK proxy.

### Bài 6 — Không có interface

Tạo `InventoryService` không implement interface, có method được aspect match. Đặt `proxy-target-class=false` và kiểm tra Spring có thể dùng class proxy thay vì JDK proxy hay không.

### Bài 7 — Final class

Đánh dấu target service thành `final` trong khi nó implement interface. Thử JDK proxy và class-based proxy. Ghi lại trường hợp nào tạo proxy thành công và nguyên nhân inheritance.

### Bài 8 — Final method

Tạo service implement interface với method `public final`. So sánh khả năng advice khi sử dụng JDK proxy và class-based proxy. Chú ý lời gọi phải đi qua proxy.

### Bài 9 — Self-invocation

Tạo service có method `outer()` gọi `inner()`, trên `inner()` đặt advice. Gọi `outer()` từ bean khác và quan sát advice. Sau đó chuyển `inner()` sang service khác và gọi qua dependency injection.

### Bài 10 — Method private và constructor

Đặt logic trong private method và constructor. Thử dùng Spring AOP advice theo method execution và giải thích vì sao không nên kỳ vọng proxy chặn trực tiếp các điểm đó.

### Bài 11 — Kiểm tra advisor/pointcut

Thay đổi tên package và tên method sao cho không còn khớp `execution(...)`. Quan sát `AopUtils.isAopProxy(...)` và log advice. Phân biệt “không match pointcut” với “dùng sai proxy mode”.

### Bài 12 — Test hai proxy modes

Viết hai Spring Boot integration tests, một với `spring.aop.proxy-target-class=false` và một với `true`. Kiểm tra loại proxy và behavior của advice. Không chỉ dựa vào runtime class name.

## 27. Tài liệu tham khảo chính thức

- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): giải thích JDK dynamic proxy, CGLIB, giới hạn final/private và self-invocation.
- [Spring Framework Reference — Spring AOP APIs](https://docs.spring.io/spring-framework/reference/core/aop-api.html): các abstraction proxy/advisor và cách dùng ProxyFactory.
- [Spring Framework Reference — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): khai báo aspect bằng `@Aspect`, pointcut và advice.
- [Spring Framework API — AopUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): xác định AOP, JDK và CGLIB proxy.
- [Spring Boot Reference — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): AOP auto-configuration và mặc định class-based proxy trong Spring Boot.
- [Spring Framework Reference — Transaction Declarative Annotations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): giới hạn của transaction proxy và vị trí annotation.
- [Java API — java.lang.reflect.Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): cơ chế JDK dynamic proxy.

Điều quan trọng khi làm việc với Spring AOP là hiểu **proxy được đưa vào giữa client và target để intercept lời gọi**. JDK dynamic proxy triển khai interface và không phải subtype của concrete implementation; class-based proxy dùng subclass nên hỗ trợ concrete type nhưng bị giới hạn bởi `final`, `private` và các quy tắc inheritance. Spring Boot thường ưu tiên class-based proxy mặc định, song có thể cấu hình interface-based bằng `spring.aop.proxy-target-class=false`. Dù chọn chiến lược nào, advice chỉ hoạt động khi bean do Spring quản lý, advisor match và lời gọi đi qua đúng proxy; đổi proxy mode không tự sửa self-invocation hay lỗi thiết kế service boundary.
