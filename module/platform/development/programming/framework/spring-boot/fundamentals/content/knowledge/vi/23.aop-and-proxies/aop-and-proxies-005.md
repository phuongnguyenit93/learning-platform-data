# Nhận diện bean proxy và kiểu tham chiếu có thể tiêm

Trong Spring Boot, một bean có thể được quản lý bằng **proxy** để Spring áp dụng AOP, transaction, caching, async hoặc một cơ chế lifecycle đặc biệt. Lúc đó, object mà một service nhận qua dependency injection **không nhất thiết là instance trực tiếp của class đã viết trong source code**.

Điều này dẫn đến câu hỏi thực tế: nếu Spring tạo bean từ class `PaymentService`, bạn có thể khai báo constructor nhận `PaymentService` hay chỉ nên nhận interface `PaymentOperations`? Vì sao một dependency theo interface inject thành công nhưng dependency theo class lại báo lỗi, dù tên bean hoàn toàn đúng?

Muốn trả lời, cần phân biệt rõ:

- **Target object:** đối tượng nghiệp vụ gốc, ví dụ `PaymentService`.
- **Proxy object:** đối tượng trung gian nhận lời gọi, áp dụng advice rồi chuyển tiếp đến target theo cơ chế phù hợp.
- **Bean reference:** đối tượng thực tế mà application context cung cấp cho client. Tham chiếu này có thể trỏ tới proxy.
- **Dependency type:** kiểu mà constructor hoặc field yêu cầu. Kiểu này phải tương thích với object được inject, không chỉ với target class trên giấy.

Hai chiến lược proxy quan trọng:

1. **JDK dynamic proxy** dựa vào interface; proxy thường không phải instance của concrete target class.
2. **Class-based proxy (CGLIB)** được sinh như subclass của target class; proxy thường assignable với cả concrete class và những interface mà class đó implement.

Hiểu cơ chế trên giúp bạn nhận diện bean proxy chính xác, chọn kiểu tham chiếu phù hợp và tránh những lỗi dependency injection khó hiểu.

## 1. Proxy nằm ở đâu trong luồng gọi method?

Giả sử có một nghiệp vụ thanh toán:

```java
package com.example.shop.payment;

public interface PaymentOperations {
    void charge(String orderId);
}
```

Implementation:

```java
package com.example.shop.payment;

import org.springframework.stereotype.Service;

@Service
public class PaymentService implements PaymentOperations {

    @Override
    public void charge(String orderId) {
        System.out.println("Charging order: " + orderId);
    }
}
```

Một client được inject:

```java
@Service
public class CheckoutService {

    private final PaymentOperations payments;

    public CheckoutService(PaymentOperations payments) {
        this.payments = payments;
    }

    public void checkout(String orderId) {
        payments.charge(orderId);
    }
}
```

Nếu không có proxy, luồng gọi có thể là:

```text
CheckoutService
      |
      v
PaymentService.charge(...)
```

Khi có Spring AOP proxy:

```text
CheckoutService
      |
      | payments.charge(...)
      v
Payment proxy                     <-- reference được inject
      |
      +--> Transaction / logging / cache / security advice
      |
      v
PaymentService target             <-- object nghiệp vụ
      |
      v
charge(orderId)
```

Tùy advice, một số lời gọi có thể trả về kết quả từ cache mà không gọi target; hoặc được gửi sang executor. Sơ đồ là mô hình tổng quát, không phải mô tả cố định của mọi interceptor.

### 1.1. Proxy giúp tách cross-cutting concern

Những việc như transaction, logging, metrics và security thường xuất hiện trong nhiều service. Nếu mọi method tự viết logic bao quanh, code nghiệp vụ sẽ bị lặp.

Proxy cho phép framework hoặc aspect cung cấp hành vi bổ sung ở ranh giới lời gọi.

Ví dụ về các annotation thường liên quan proxy:

```java
@Transactional
public void transferMoney() {
    // Nghiệp vụ chuyển tiền
}
```

```java
@Cacheable("products")
public Product findProduct(String sku) {
    // Nghiệp vụ truy vấn sản phẩm
}
```

```java
@Async
public CompletableFuture<Void> sendEmail(String email) {
    // Nghiệp vụ gửi email
    return CompletableFuture.completedFuture(null);
}
```

Những annotation này cần cơ chế tương ứng được bật và cấu hình thích hợp. Chỉ gắn annotation **không bảo đảm** một proxy được tạo hoặc advice luôn chạy.

### 1.2. Bean definition, target và proxy không đồng nhất

| Thành phần | Vai trò |
| --- | --- |
| `BeanDefinition` | Metadata về cách Spring đăng ký và tạo bean |
| Target class | Kiểu nghiệp vụ, chẳng hạn `PaymentService` |
| Target instance | Instance chứa trạng thái và logic nghiệp vụ |
| Proxy instance | Object được tạo để áp dụng hành vi trung gian |
| Bean name | Định danh trong container, ví dụ `paymentService` |
| Dependency type | Kiểu client yêu cầu: `PaymentOperations` hoặc `PaymentService` |

Với AOP proxy thông thường, bean name có thể vẫn là `paymentService` dù runtime object trả về là proxy.

Không nên cho rằng Spring sẽ tạo hai bean nghiệp vụ độc lập tên `paymentService` và `paymentServiceProxy`; thông thường Spring expose proxy dưới bean name của đối tượng được bao bọc. Một số cơ chế scoped proxy có bean definition nội bộ dành cho target, nhưng đó là chi tiết của hạ tầng.

## 2. Khi nào Spring tạo proxy?

Proxy thường xuất hiện khi bean được một cơ chế hạ tầng xử lý, ví dụ:

- AOP advisor/pointcut khớp bean và method.
- Transaction management xử lý `@Transactional`.
- Cache infrastructure xử lý `@Cacheable`, `@CachePut` hoặc `@CacheEvict`.
- Async method execution xử lý `@Async`.
- Scoped proxy phục vụ bean có request/session scope.
- Lazy-resolution proxy cho một dependency có `@Lazy`.

Một bean chỉ có `@Service` **không mặc nhiên là AOP proxy**.

Một class được tạo bằng:

```java
PaymentService service = new PaymentService();
```

không được Spring tự động áp dụng proxy của container.

Trong vòng đời bean thông thường, Spring tạo target, thực hiện dependency injection và initialization, sau đó các bean post-processor có thể cung cấp proxy reference cho client.

```text
BeanDefinition
      |
      v
Tạo và khởi tạo target
      |
      v
BeanPostProcessor / auto-proxy creator
      |
      +--> Không cần proxy -> Expose target
      |
      +--> Cần proxy ------> Expose proxy
                                      |
                                      v
                                 Inject vào client
```

Thực tế có thêm trường hợp early references, scoped targets, factory beans và các bước nội bộ khác. Mô hình trên dùng để nhận biết vì sao **kiểu runtime của bean có thể khác target class**.

## 3. JDK dynamic proxy

JDK dynamic proxy sử dụng Java Reflection Proxy để tạo object implement một hay nhiều interface. Với Spring AOP, đây là lựa chọn phù hợp khi bean có interface nghiệp vụ và cấu hình ưu tiên interface-based proxy.

Giả sử:

```java
public interface NotificationSender {
    void send(String message);
}
```

```java
@Service
public class EmailSender implements NotificationSender {

    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}
```

Quan hệ kiểu:

```text
                  NotificationSender
                    ^          ^
                    |          |
              implements   implements
                    |          |
                    |          |
               EmailSender   JDK Proxy
                   ^            |
                   |            |
                target  <-------+ lời gọi được chuyển tiếp
```

**JDK proxy implement `NotificationSender`, nhưng không kế thừa `EmailSender`.**

### 3.1. Vì sao inject interface thành công?

```java
@Service
public class AlertService {

    private final NotificationSender sender;

    public AlertService(NotificationSender sender) {
        this.sender = sender;
    }
}
```

Dependency yêu cầu interface. Nếu bean được expose qua JDK proxy implement interface đó, JVM cho phép gán:

```java
NotificationSender reference = proxy;
```

Điều kiện còn lại là Spring phải tìm được một ứng viên phù hợp theo quy tắc autowiring.

### 3.2. Vì sao inject concrete class có thể thất bại?

```java
@Service
public class AlertService {

    private final EmailSender sender;

    public AlertService(EmailSender sender) {
        this.sender = sender;
    }
}
```

Constructor yêu cầu `EmailSender`, nhưng object được expose là JDK dynamic proxy, không phải instance của `EmailSender`.

Phép gán tương đương:

```text
EmailSender reference = object_of_JdkProxyType
```

không hợp lệ về kiểu.

Spring có thể báo lỗi thiếu dependency phù hợp hoặc lỗi `BeanNotOfRequiredTypeException`, tùy cách truy vấn bean và vị trí xảy ra lỗi. Thông báo thường cho biết kiểu yêu cầu là implementation class trong khi object được expose có kiểu proxy được sinh ra.

### 3.3. Ép kiểu không giải quyết được

Sai:

```java
NotificationSender sender =
        context.getBean(NotificationSender.class);

EmailSender implementation = (EmailSender) sender;
```

Nếu `sender` là JDK proxy, cast có thể gây `ClassCastException`. Java runtime không tự động bỏ qua proxy để lấy target class.

Hãy thiết kế client sử dụng các method được công bố bởi interface. Nếu client cần một method khác, mở rộng hợp đồng bằng interface phù hợp thay vì cast.

### 3.4. Method chỉ tồn tại trên implementation

Ví dụ:

```java
public class EmailSender implements NotificationSender {

    @Override
    public void send(String message) {
        System.out.println(message);
    }

    public void rebuildTemplates() {
        System.out.println("Rebuild templates");
    }
}
```

`rebuildTemplates()` không thuộc `NotificationSender`, nên client nhận interface không thể gọi nó trực tiếp.

Nếu tính năng này phải được dùng từ bên ngoài, có thể khai báo interface khác:

```java
public interface TemplateMaintenance {
    void rebuildTemplates();
}
```

Và để implementation implement cả `NotificationSender` lẫn `TemplateMaintenance`. Khi proxy công bố các interface tương ứng, client có thể inject đúng hợp đồng cần sử dụng.

## 4. Class-based proxy (CGLIB)

Spring còn có thể tạo class-based proxy bằng cách sinh một **subclass** của target class, thường được gọi là CGLIB proxy.

Ví dụ quan hệ kiểu:

```text
NotificationSender
       ^
       | implements
   EmailSender
       ^
       | extends
   EmailSender$$SpringCGLIB$$...
       ^
       |
Injected reference
```

Trong trường hợp class-based proxy tạo được, object proxy có thể vừa implement `NotificationSender`, vừa là một instance của `EmailSender` theo quan hệ kế thừa Java.

### 4.1. Hai kiểu injection đều có thể dùng

Inject theo interface:

```java
public AlertService(NotificationSender sender) {
    this.sender = sender;
}
```

Inject theo implementation class:

```java
public AlertService(EmailSender sender) {
    this.sender = sender;
}
```

Với class-based proxy là subclass của `EmailSender`, cả hai kiểu đều có thể assignable.

Nhưng inject theo implementation class tạo coupling với class cụ thể. Khi cấu hình AOP chuyển sang JDK proxy hoặc implementation được thay bằng class khác, client có thể phải sửa.

### 4.2. Những giới hạn quan trọng

Class-based proxy cần khả năng tạo subclass và override method phù hợp:

- **Final class** không thể được subclass.
- **Final method** không thể bị override để gắn advice theo cơ chế subclass thông thường.
- **Private method** không thể override từ subclass.
- Một số method có visibility không cho phép override cũng không thể được intercept như dự kiến.
- Lời gọi nội bộ bằng `this` không tự động đi qua proxy boundary.

Ví dụ class không phù hợp để tạo CGLIB subclass:

```java
public final class FinalPaymentService {
    public void pay() {
        System.out.println("Paid");
    }
}
```

Ví dụ method final:

```java
public class InventoryService {
    public final void reserve(String sku) {
        System.out.println("Reserve " + sku);
    }
}
```

Spring AOP class-based proxy không thể override method final để áp dụng lời khuyên theo cách thông thường.

### 4.3. Proxy không có nghĩa mọi method đều được advice

Giả sử `InventoryService` có `reserve()` và `viewCatalog()`, nhưng pointcut chỉ khớp `reserve()`. Object vẫn là proxy; tuy vậy, logic advice tương ứng không nhất thiết chạy khi gọi `viewCatalog()`.

Vì thế cần phân biệt:

1. Bean có phải proxy không?
2. Proxy là JDK hay class-based?
3. Method đang gọi có được advisor chọn không?
4. Lời gọi có thực sự đi qua proxy không?

Nhận diện proxy chỉ giải quyết hai câu hỏi đầu.

## 5. Spring Boot cấu hình proxy strategy

Trong nhiều dự án Spring Boot hiện đại, auto-configuration của Spring AOP ưu tiên **class-based proxy** theo mặc định. Bạn có thể yêu cầu interface-based proxy khi thích hợp.

Trong `application.properties`:

```properties
spring.aop.proxy-target-class=false
```

Hoặc `application.yml`:

```yaml
spring:
  aop:
    proxy-target-class: false
```

Giá trị `false` cho biết Spring Boot nên sử dụng JDK interface-based proxy khi có thể trong cơ chế AOP tương ứng.

Để ưu tiên class-based proxy:

```properties
spring.aop.proxy-target-class=true
```

### 5.1. Property này có thay đổi mọi proxy trong context?

Không nhất thiết. Nó điều khiển phần AOP auto-configuration được Spring Boot hỗ trợ, **không phải mọi proxy** do scoped proxy, thư viện bên ngoài hoặc một `ProxyFactory` cấu hình riêng tạo ra.

Nếu có nhiều cấu hình đăng ký auto-proxy creator hoặc nhiều annotation bật AOP, kết quả cần được xác nhận trên object thực tế.

### 5.2. Khi target không implement interface

Nếu target không có interface phù hợp để tạo JDK proxy, Spring AOP có thể sử dụng class-based proxy ngay cả khi ứng dụng ưu tiên interface-based proxy. Vì vậy, không nên kết luận rằng `proxy-target-class=false` buộc **mọi bean** dùng JDK proxy.

### 5.3. `@EnableAspectJAutoProxy`

Trong Spring Framework, có thể bật proxy-based AspectJ-style AOP:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AopConfiguration {
}
```

Hoặc:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
```

Trong Spring Boot, thường không cần thêm annotation này nếu AOP auto-configuration đã cung cấp cơ chế phù hợp. Tránh khai báo nhiều cấu hình AOP có chiến lược mâu thuẫn mà không hiểu kết quả cuối cùng.

### 5.4. Bảng lựa chọn kiểu tham chiếu

| Target | Object được expose | Inject interface | Inject concrete class |
| --- | --- | --- | --- |
| `EmailSender implements NotificationSender` | Target không proxy | Có | Có |
| `EmailSender implements NotificationSender` | JDK proxy | Có | Không, proxy không kế thừa `EmailSender` |
| `EmailSender implements NotificationSender` | Class-based proxy | Có | Có, nếu subclass proxy hợp lệ |
| Class không implement interface nghiệp vụ | Class-based proxy | Không có interface nghiệp vụ tương ứng | Có, nếu subclass hợp lệ |
| Final target class | CGLIB proxy được yêu cầu | Không bảo đảm | Có thể lỗi tạo proxy |

Các ô “Có” giả định bean có thể tạo thành công và được chọn đúng giữa các ứng viên.

## 6. Quy tắc inject: assignability trước, lựa chọn ứng viên sau

Kiểu dependency do constructor hoặc field khai báo:

```java
public CheckoutService(PaymentOperations payments) {
    this.payments = payments;
}
```

Spring cần cung cấp một object assignable với `PaymentOperations`.

Nếu object là JDK proxy implement `PaymentOperations`, phép gán hợp lệ. Nếu dependency yêu cầu concrete `PaymentService`, object proxy chỉ implement interface có thể không đáp ứng.

### 6.1. Tra cứu theo tên không bỏ qua type checking

Ví dụ:

```java
PaymentOperations payments =
        context.getBean(
                "paymentService",
                PaymentOperations.class
        );
```

Lời gọi có thể thành công với JDK proxy.

Nhưng:

```java
PaymentService payments =
        context.getBean(
                "paymentService",
                PaymentService.class
        );
```

có thể thất bại nếu bean được expose qua JDK proxy.

**Bean name xác định một mục trong container; nó không thay đổi class hierarchy của object.**

### 6.2. `@Qualifier` không sửa type mismatch

```java
public CheckoutService(
        @Qualifier("paymentService") PaymentService payments) {
    this.payments = payments;
}
```

Qualifier giúp chọn bean mang tên hoặc qualifier tương ứng. Nhưng nếu object của bean đó là JDK proxy không phải `PaymentService`, dependency vẫn sai kiểu.

Thay bằng:

```java
public CheckoutService(
        @Qualifier("paymentService") PaymentOperations payments) {
    this.payments = payments;
}
```

### 6.3. `@Primary` cũng không sửa type mismatch

Ví dụ một class được gắn `@Primary`:

```java
@Service
@Primary
public class CardPaymentService implements PaymentOperations {
    @Override
    public void charge(String orderId) {
        System.out.println("Card payment " + orderId);
    }
}
```

`@Primary` ưu tiên ứng viên giữa nhiều bean phù hợp; nó không khiến một JDK proxy trở thành instance của `CardPaymentService`.

### 6.4. Collection injection

Ví dụ:

```java
@Service
public class PaymentRouter {

    private final List<PaymentOperations> handlers;

    public PaymentRouter(List<PaymentOperations> handlers) {
        this.handlers = handlers;
    }
}
```

Spring có thể inject một list gồm nhiều object implement `PaymentOperations`, bao gồm những JDK proxies phù hợp.

Ngược lại, `List<CardPaymentService>` không phải cách tổng quát để lấy các JDK proxy của concrete target class. Nếu mục tiêu là xử lý nhiều implementation, hãy inject theo interface chung.

## 7. Ví dụ chạy xuyên suốt: tạo AOP proxy và quan sát kiểu

Ta xây dựng một ứng dụng có interface, target service, aspect và runner chẩn đoán.

### 7.1. Dependency

Với một dự án Spring Boot có dependency management thích hợp, Gradle Groovy DSL thường dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Hoặc Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

### 7.2. Interface nghiệp vụ

`InventoryOperations.java`:

```java
package com.example.demo.inventory;

public interface InventoryOperations {
    void reserve(String sku);
}
```

### 7.3. Target class

`InventoryService.java`:

```java
package com.example.demo.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryService implements InventoryOperations {

    @Override
    public void reserve(String sku) {
        System.out.println("Reserved SKU: " + sku);
    }
}
```

### 7.4. Aspect

`InventoryLoggingAspect.java`:

```java
package com.example.demo.inventory;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class InventoryLoggingAspect {

    @Before(
        "execution(* com.example.demo.inventory.InventoryOperations.reserve(..))"
    )
    public void beforeReserve() {
        System.out.println("AOP: before reserve");
    }
}
```

Aspect có một before advice được áp dụng khi pointcut khớp lời gọi method tương ứng qua Spring AOP proxy.

### 7.5. Khởi động ứng dụng

`DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Package `com.example.demo.inventory` nằm dưới package gốc `com.example.demo` để component scan mặc định tìm thấy service và aspect.

### 7.6. Chọn JDK proxy

Trong `application.properties`:

```properties
spring.aop.proxy-target-class=false
```

Khi aspect match và Spring AOP tạo interface-based proxy, bean `inventoryService` được expose dưới một JDK proxy implement `InventoryOperations`.

### 7.7. Inject theo interface

```java
package com.example.demo.inventory;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class InventoryRunner implements ApplicationRunner {

    private final InventoryOperations inventory;

    public InventoryRunner(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    @Override
    public void run(ApplicationArguments args) {
        inventory.reserve("SKU-100");
    }
}
```

Đầu ra minh họa:

```text
AOP: before reserve
Reserved SKU: SKU-100
```

Nếu không xuất hiện lời log của aspect, hãy kiểm tra dependency AOP, pointcut, class được scan và proxy strategy. Không nên kết luận code đã được intercept chỉ vì ứng dụng khởi động thành công.

## 8. Nhận diện proxy bằng `AopUtils`

Spring cung cấp utility:

```java
import org.springframework.aop.support.AopUtils;
```

Những phương thức thường dùng:

| API | Mục đích |
| --- | --- |
| `AopUtils.isAopProxy(obj)` | Kiểm tra Spring AOP proxy |
| `AopUtils.isJdkDynamicProxy(obj)` | Kiểm tra Spring AOP JDK dynamic proxy |
| `AopUtils.isCglibProxy(obj)` | Kiểm tra Spring AOP class-based proxy |
| `AopUtils.getTargetClass(obj)` | Trả về target class mà framework có thể xác định |

### 8.1. Runner chẩn đoán kiểu

```java
package com.example.demo.inventory;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ProxyInspector implements ApplicationRunner {

    private final InventoryOperations inventory;

    public ProxyInspector(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    @Override
    public void run(ApplicationArguments args) {
        Object bean = inventory;

        System.out.println(
                "Runtime class: " + bean.getClass().getName()
        );

        System.out.println(
                "Spring AOP proxy: " + AopUtils.isAopProxy(bean)
        );

        System.out.println(
                "JDK proxy: " + AopUtils.isJdkDynamicProxy(bean)
        );

        System.out.println(
                "CGLIB proxy: " + AopUtils.isCglibProxy(bean)
        );

        System.out.println(
                "Target class: " +
                AopUtils.getTargetClass(bean).getName()
        );

        System.out.println(
                "Assignable to interface: " +
                (bean instanceof InventoryOperations)
        );

        System.out.println(
                "Assignable to concrete: " +
                (bean instanceof InventoryService)
        );
    }
}
```

### 8.2. Kết quả minh họa với JDK proxy

```text
Runtime class: jdk.proxy2.$Proxy...
Spring AOP proxy: true
JDK proxy: true
CGLIB proxy: false
Target class: com.example.demo.inventory.InventoryService
Assignable to interface: true
Assignable to concrete: false
```

Tên class được sinh bởi JDK có thể khác theo Java version. Không hard-code hoặc assert nguyên tên class proxy trong test.

### 8.3. Kết quả minh họa với class-based proxy

Đổi cấu hình:

```properties
spring.aop.proxy-target-class=true
```

Nếu class có thể được proxy theo cơ chế subclass:

```text
Runtime class: com.example.demo.inventory.InventoryService$$SpringCGLIB$$...
Spring AOP proxy: true
JDK proxy: false
CGLIB proxy: true
Target class: com.example.demo.inventory.InventoryService
Assignable to interface: true
Assignable to concrete: true
```

Trong các ví dụ trên, `getClass()` báo **runtime class của reference**, còn `getTargetClass()` báo **target class**. Không cần object proxy và target có cùng runtime class.

## 9. `getClass()`, `instanceof` và target class khác nhau thế nào?

Ba phép kiểm tra trả lời ba câu hỏi khác nhau:

```java
bean.getClass()
```

Cho biết class runtime thật của object reference.

```java
bean instanceof InventoryService
```

Kiểm tra object reference có assignable với `InventoryService` không.

```java
AopUtils.getTargetClass(bean)
```

Giúp nhận diện class mục tiêu theo thông tin Spring AOP có thể truy cập.

### 9.1. Không nhầm target class với kiểu được inject

Một JDK proxy có thể cho:

```java
AopUtils.getTargetClass(bean) == InventoryService.class
```

nhưng:

```java
bean instanceof InventoryService
```

lại là `false`.

Không có mâu thuẫn: target class là kiểu của implementation phía sau proxy; kiểu assignable của object proxy do class hierarchy/interface implementation của chính proxy quyết định.

### 9.2. `AopUtils.getTargetClass()` không lấy target instance

API này trả về `Class<?>`, không phải object đích:

```java
Class<?> type = AopUtils.getTargetClass(bean);
```

Không nên dùng nó để cố lấy target rồi gọi trực tiếp. Gọi target ngoài proxy có thể bỏ qua transaction, caching, security hoặc các advice khác.

### 9.3. Java `Proxy.isProxyClass()`

Java có:

```java
import java.lang.reflect.Proxy;
```

Kiểm tra:

```java
boolean jdkProxyClass =
        Proxy.isProxyClass(bean.getClass());
```

Nó cho biết runtime class có phải **Java dynamic proxy class** hay không.

Tuy nhiên:

- Java dynamic proxy có thể do thư viện khác tạo, không nhất thiết là Spring AOP proxy.
- CGLIB proxy không phải Java dynamic proxy.
- Nếu đang chẩn đoán Spring AOP, `AopUtils.isAopProxy(...)` thường diễn đạt đúng mục tiêu hơn.

### 9.4. Không tìm proxy bằng substring

Không nên:

```java
boolean proxy = bean.getClass()
        .getName()
        .contains("SpringCGLIB");
```

Tên generated class có thể thay đổi theo Java/Spring version. Hơn nữa Spring còn dùng bytecode enhancement vì mục đích khác, không chỉ Spring AOP.

## 10. Interface-first injection trong thiết kế service

Trong nhiều service có hợp đồng nghiệp vụ rõ ràng, nên inject theo interface:

```java
@Service
public class CheckoutService {

    private final PaymentOperations payments;

    public CheckoutService(PaymentOperations payments) {
        this.payments = payments;
    }
}
```

Cách này:

- Hoạt động với JDK proxy implement interface.
- Vẫn hoạt động với CGLIB proxy của implementation.
- Giảm phụ thuộc vào concrete class.
- Dễ tạo fake, mock hoặc decorator trong test.
- Cho phép đổi implementation mà không sửa client.

Không phải class nào cũng bắt buộc có interface. Với một bean đơn giản không cần abstraction, concrete injection vẫn có thể phù hợp. Nhưng khi bean có thể bị JDK proxy, interface-first injection thường ít rủi ro nhất.

### 10.1. Nhiều implementation và `@Qualifier`

```java
public interface PaymentOperations {
    void charge(String orderId);
}
```

```java
@Service("cardPayments")
public class CardPayments implements PaymentOperations {
    @Override
    public void charge(String orderId) {
        System.out.println("Card " + orderId);
    }
}
```

```java
@Service("walletPayments")
public class WalletPayments implements PaymentOperations {
    @Override
    public void charge(String orderId) {
        System.out.println("Wallet " + orderId);
    }
}
```

Chọn implementation:

```java
public CheckoutService(
        @Qualifier("cardPayments") PaymentOperations payments) {
    this.payments = payments;
}
```

Kết hợp qualifier với **interface type** cho phép Spring chọn bean mong muốn mà vẫn giữ type contract tương thích JDK proxy.

## 11. `@Transactional`: proxy có thể cần thiết cho lời gọi bên ngoài

Một tình huống quen thuộc:

```java
public interface OrderOperations {
    void submit(String orderId);
}
```

```java
@Service
public class OrderService implements OrderOperations {

    @Override
    @Transactional
    public void submit(String orderId) {
        System.out.println("Submit " + orderId);
    }
}
```

Khi transaction infrastructure được bật, có transaction manager phù hợp và advice áp dụng, `OrderService` có thể được expose thông qua proxy.

Client:

```java
@Service
public class OrderWorkflow {

    private final OrderOperations orders;

    public OrderWorkflow(OrderOperations orders) {
        this.orders = orders;
    }

    public void run(String id) {
        orders.submit(id);
    }
}
```

Nếu `orders` là JDK proxy, reference theo `OrderOperations` vẫn hợp lệ.

### 11.1. Lỗi self-invocation

Proxy tồn tại không có nghĩa mọi lời gọi nội bộ đều được intercept:

```java
@Service
public class OrderService {

    public void runWorkflow(String id) {
        saveOrder(id);
    }

    @Transactional
    public void saveOrder(String id) {
        System.out.println("Save " + id);
    }
}
```

Trong proxy-based Spring AOP, lời gọi `saveOrder(id)` từ chính target qua `this` thường không đi ra ngoài rồi quay lại qua proxy.

```text
Client
  |
  v
Proxy
  |
  v
target.runWorkflow()
  |
  +--> this.saveOrder()
           |
           v
      Target trực tiếp
      (không qua proxy boundary)
```

Nếu transaction advice chỉ nằm ở `saveOrder`, transaction có thể không được áp dụng như người viết mong muốn khi gọi nội bộ.

### 11.2. Thiết kế lại để đi qua proxy

Tách method cần advice sang một bean khác:

```java
public interface OrderWriteOperations {
    void saveOrder(String id);
}
```

```java
@Service
public class OrderWriter implements OrderWriteOperations {

    @Override
    @Transactional
    public void saveOrder(String id) {
        System.out.println("Save " + id);
    }
}
```

```java
@Service
public class OrderWorkflow {

    private final OrderWriteOperations writer;

    public OrderWorkflow(OrderWriteOperations writer) {
        this.writer = writer;
    }

    public void runWorkflow(String id) {
        writer.saveOrder(id);
    }
}
```

Khi `writer` là Spring proxy, lời gọi từ `OrderWorkflow` đi qua proxy boundary.

Không nên tìm cách “gỡ proxy để lấy target” nhằm chữa self-invocation; làm vậy còn dễ bypass advice hơn.

## 12. `@Async`, caching và các proxy có nhiều advisor

Spring hỗ trợ những hành vi AOP khác khi được bật và cấu hình đúng.

Ví dụ async:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

```java
public interface NotificationOperations {
    CompletableFuture<Void> sendAsync(String message);
}
```

```java
@Service
public class NotificationService implements NotificationOperations {

    @Override
    @Async
    public CompletableFuture<Void> sendAsync(String message) {
        System.out.println(message);
        return CompletableFuture.completedFuture(null);
    }
}
```

Client inject `NotificationOperations`, nên không phụ thuộc vào việc Spring tạo JDK proxy hay CGLIB proxy trong trường hợp phù hợp.

Caching:

```java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

```java
@Cacheable("products")
public Product findProduct(String sku) {
    return repository.findBySku(sku);
}
```

Ví dụ cache giả định có cache manager, repository và model `Product` phù hợp. Đây là các cơ chế minh họa, không phải toàn bộ ứng dụng chạy được nếu bỏ qua dependency.

Một bean có thể có nhiều advisor:

```text
Client
  |
  v
Spring AOP proxy
  |
  +--> Transaction advice
  +--> Metrics advice
  +--> Custom logging advice
  |
  v
Target
```

Không nhất thiết mỗi annotation tạo một proxy riêng. Một proxy có thể chứa nhiều advisor theo cấu hình thực tế.

## 13. Scoped proxy: proxy không chỉ dành cho AOP method

Một request-scoped bean có vòng đời ngắn hơn singleton. Nếu một singleton cần một dependency gắn với request hiện tại, Spring có thể cung cấp **scoped proxy**.

```java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMetadata {

    public String requestId() {
        return "example-request";
    }
}
```

Một singleton:

```java
@Service
public class AuditService {

    private final RequestMetadata metadata;

    public AuditService(RequestMetadata metadata) {
        this.metadata = metadata;
    }

    public String currentRequestId() {
        return metadata.requestId();
    }
}
```

Trong cấu hình Spring Web phù hợp, `@RequestScope` mặc định sử dụng class-based scoped proxy. Singleton có thể giữ reference proxy ổn định, trong khi target thay đổi theo từng HTTP request.

```text
AuditService (singleton)
           |
           v
RequestMetadata proxy
           |
           +--> HTTP Request A -> Target A
           |
           +--> HTTP Request B -> Target B
```

### 13.1. Proxy reference sống lâu hơn target

Reference proxy có thể tồn tại trước khi có request active. Nhưng nếu gọi method cần request scope bên ngoài một request hợp lệ, Spring có thể báo lỗi vì chưa có request context.

Đừng coi việc inject được scoped proxy là bảo đảm mọi lời gọi đều hợp lệ ở mọi thread.

### 13.2. `ScopedProxyMode`

Bạn có thể chỉ định chế độ proxy:

```java
@Component
@Scope(
    value = WebApplicationContext.SCOPE_REQUEST,
    proxyMode = ScopedProxyMode.INTERFACES
)
public class CurrentUserContext implements UserContext {
}
```

Ví dụ giả định `UserContext` là interface do ứng dụng định nghĩa. Cần import `Scope`, `WebApplicationContext` và `ScopedProxyMode` từ Spring.

Với `ScopedProxyMode.INTERFACES`, client nên inject `UserContext`. Với `ScopedProxyMode.TARGET_CLASS`, class-based proxy có thể assignable với concrete class nếu tạo subclass thành công.

**Kết luận:** khi debug kiểu bean, trước tiên xác định *vì sao* proxy được tạo: transaction, custom aspect, scope, lazy resolution hay một library khác.

## 14. `@Lazy` trên injection point có thể tạo proxy

Ví dụ:

```java
@Service
public class ReportService {

    private final HeavyReportEngine engine;

    public ReportService(@Lazy HeavyReportEngine engine) {
        this.engine = engine;
    }
}
```

`@Lazy` trên injection point có thể khiến Spring cung cấp proxy để trì hoãn việc resolve target dependency.

Phân biệt với:

```java
@Component
@Lazy
public class HeavyReportEngine {
}
```

Ở mức bean definition, `@Lazy` cho phép trì hoãn việc tạo bean cho tới khi cần. Nhưng nếu một non-lazy singleton inject trực tiếp bean đó, Spring vẫn có thể cần tạo dependency sớm để hoàn tất singleton.

Không nên suy luận “có proxy” đồng nghĩa bean có transaction advice.

## 15. `getClass()` của target khác `getClass()` của client

Xét:

```java
@Service
public class InventoryService implements InventoryOperations {

    public InventoryService() {
        System.out.println(
                "Inside target constructor: " +
                getClass().getName()
        );
    }

    @Override
    public void reserve(String sku) {
        System.out.println(sku);
    }
}
```

Trong một AOP JDK-proxy scenario thông thường, target constructor có thể in tên `InventoryService`, còn bean reference được inject vào client báo một JDK proxy class.

Điều này không mâu thuẫn. `this` của target và object reference client đang giữ không nhất thiết là cùng một object.

Với class-based proxies, chi tiết tạo instance và callback có thể khác; không dựa vào log constructor để suy ra cấu trúc mọi loại proxy.

### 15.1. `instanceof` là công cụ kiểm tra assignability

```java
Object bean = context.getBean("inventoryService");

System.out.println(bean instanceof InventoryOperations);
System.out.println(bean instanceof InventoryService);
```

Với JDK proxy của interface:

```text
true
false
```

Với CGLIB proxy hợp lệ kế thừa implementation:

```text
true
true
```

Những giá trị trên là kết quả kỳ vọng cho các proxy scenario tương ứng; không nên dùng chúng để chứng minh lời gọi cụ thể có chạy qua một advisor nhất định.

## 16. `ApplicationContext.getType()` và runtime object

Spring có thể suy luận kiểu bean từ bean definition và những thông tin của container:

```java
Class<?> predicted = context.getType("inventoryService");
```

Trong khi:

```java
Class<?> actual =
        context.getBean("inventoryService").getClass();
```

trả về runtime class của object thực sự được lấy ra.

Tùy thời điểm, `FactoryBean`, proxy creator, scope hoặc lazy initialization, khả năng dự đoán kiểu có thể khác với class runtime của một instance sau này.

### 16.1. Không ép khởi tạo bean chỉ để quan sát quá sớm

`getBean()` có thể kích hoạt việc tạo bean. Nếu gọi trong giai đoạn xử lý bean definition hoặc condition rất sớm, nó có thể thay đổi timing lifecycle và tạo lỗi ngoài ý muốn.

Thường nên chẩn đoán proxy sau khi context đã sẵn sàng, ví dụ trong một integration test hoặc `ApplicationRunner`.

### 16.2. Có thể có nhiều lớp proxy

Một bean có thể được bao bọc bởi nhiều proxy hoặc decorator:

```text
Client
   |
   v
Outer proxy
   |
   v
Inner proxy
   |
   v
Target
```

`AopUtils.getTargetClass(...)` giúp tìm target class trong các tình huống phổ biến. Spring còn có `AopProxyUtils.ultimateTargetClass(...)` để hỗ trợ chẩn đoán chuỗi proxy khi target source cho phép.

Không nên tự gỡ từng lớp proxy rồi gọi target trực tiếp trong code nghiệp vụ vì có thể làm mất transaction, cache, security hoặc scope semantics.

## 17. `Advised` và thông tin advisor

Một số Spring AOP proxies công bố interface `Advised`, cho phép xem thông tin advisor và target source.

```java
import org.springframework.aop.framework.Advised;

if (bean instanceof Advised advised) {
    System.out.println(
            "Advisor count: " + advised.getAdvisors().length
    );
}
```

Đây là công cụ chẩn đoán hạ tầng, không phải hợp đồng nghiệp vụ.

Không phải mọi proxy đều expose `Advised`; proxy có thể được cấu hình opaque hoặc được tạo bởi thư viện khác.

Không nên dùng `Advised` để quyết định luồng xử lý đơn hàng, quyền truy cập hoặc lựa chọn implementation. Client nên phụ thuộc interface nghiệp vụ.

## 18. Class `@Configuration` được enhance không luôn là AOP proxy

Một configuration class có thể được Spring sinh subclass để hỗ trợ lời gọi giữa `@Bean` methods khi `proxyBeanMethods=true`.

Ví dụ:

```java
@Configuration
public class TimeConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    public TimeService timeService() {
        return new TimeService(clock());
    }
}
```

Trong tình huống phù hợp, Spring tăng cường configuration class để `clock()` từ một `@Bean` method khác vẫn tuân thủ cách tra cứu bean theo container.

Đây **không nhất thiết** là cùng loại Spring AOP proxy dùng cho `@Transactional` hoặc một aspect.

### 18.1. `proxyBeanMethods=false`

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {
}
```

Điều này điều chỉnh việc enhance configuration class, không phải tắt mọi AOP proxy của các bean được tạo bởi class đó.

Đừng kết luận một class là transaction proxy chỉ vì runtime class name có dấu hiệu generated subclass.

## 19. Quy trình xử lý lỗi inject concrete target class

Giả sử application startup báo rằng bean có tên `inventoryService` không thể được dùng như kiểu `InventoryService`, và actual runtime bean type là JDK proxy.

### Bước 1: xác định dependency type

```java
public InventoryController(InventoryService inventory) {
    this.inventory = inventory;
}
```

Client đang yêu cầu **concrete class**.

### Bước 2: tìm interface nghiệp vụ

```java
public class InventoryService implements InventoryOperations {
}
```

Nếu interface đủ phương thức cần dùng, đây là ứng viên tốt để làm dependency contract.

### Bước 3: xác định proxy strategy

Kiểm tra cấu hình Spring AOP, ví dụ:

```properties
spring.aop.proxy-target-class=false
```

Nếu bean có advisor match và proxy thực tế là JDK, concrete-class injection không phù hợp.

### Bước 4: chẩn đoán object thực tế

Trong một test context không có consumer sai kiểu:

```java
Object bean = context.getBean("inventoryService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

### Bước 5: sửa kiểu injection

Nên đổi thành:

```java
public InventoryController(InventoryOperations inventory) {
    this.inventory = inventory;
}
```

Nếu nhiều bean implement `InventoryOperations`, thêm `@Qualifier` hoặc thiết kế bean selection phù hợp.

### Bước 6: cân nhắc class-based proxy khi thực sự cần

Đổi:

```properties
spring.aop.proxy-target-class=true
```

có thể khiến concrete injection hợp lệ với target class có thể được subclass. Tuy nhiên đây là thay đổi proxy strategy có ảnh hưởng hạ tầng, không nên dùng như cách vá mọi lỗi injection.

Kiểm tra final class, final method, proxy của thư viện khác và tác động lên các bean còn lại.

## 20. Các lỗi khác dễ bị nhầm với proxy type

| Triệu chứng | Cần phân biệt |
| --- | --- |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng kiểu, cần chọn ứng viên, không nhất thiết sai proxy type |
| `NoSuchBeanDefinitionException` | Không có bean phù hợp, có thể do scan/configuration hoặc kiểu proxy |
| `BeanNotOfRequiredTypeException` | Bean được chọn nhưng object không đúng kiểu được yêu cầu |
| `ClassCastException` | Cast reference sang class không tương thích, thường gặp với JDK proxy |
| `AopUtils.isAopProxy(bean)` là false | Bean có thể chưa bị proxy do pointcut, configuration hoặc loại bean |
| Aspect không chạy dù bean là proxy | Lời gọi có thể bypass proxy hoặc pointcut không match |
| `@Transactional` không hoạt động khi self-call | Lời gọi nội bộ không đi qua proxy boundary |
| Request-scoped method báo không có scope | Proxy tồn tại nhưng request context không active |
| Class final không tạo được subclass proxy | Giới hạn của class-based proxy |

Không nên cho rằng mọi lỗi autowiring của Spring đều do AOP. Hãy phân biệt candidate selection, bean registration, proxy type và method interception.

## 21. Kiểm thử proxy type trong Spring Boot

Giả sử dùng các class `InventoryOperations`, `InventoryService` và `InventoryLoggingAspect` của mục 7.

### 21.1. Test JDK proxy

```java
package com.example.demo.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    properties = "spring.aop.proxy-target-class=false"
)
class InventoryJdkProxyTest {

    @Autowired
    InventoryOperations inventory;

    @Test
    void exposesInterfaceBasedProxy() {
        assertThat(AopUtils.isAopProxy(inventory)).isTrue();
        assertThat(AopUtils.isJdkDynamicProxy(inventory)).isTrue();
        assertThat(inventory)
                .isNotInstanceOf(InventoryService.class);
        assertThat(AopUtils.getTargetClass(inventory))
                .isEqualTo(InventoryService.class);
    }
}
```

Test yêu cầu aspect được component scan và thực sự có advisor áp dụng; nếu không có advisor match, bean có thể không được proxy. Lúc đó cần kiểm tra cấu hình AOP trước khi kết luận về khả năng inject.

### 21.2. Test CGLIB proxy

```java
@SpringBootTest(
    properties = "spring.aop.proxy-target-class=true"
)
class InventoryClassProxyTest {

    @Autowired
    InventoryService inventory;

    @Test
    void exposesClassBasedProxy() {
        assertThat(AopUtils.isAopProxy(inventory)).isTrue();
        assertThat(AopUtils.isCglibProxy(inventory)).isTrue();
        assertThat(inventory)
                .isInstanceOf(InventoryService.class);
    }
}
```

Ví dụ giả định target class không final và có thể được subclass.

### 21.3. Kiểm tra behavior của advice

Kiểm tra proxy type chưa đủ để xác nhận aspect chạy. Có thể dùng test collaborator ghi nhận số lần advice:

```java
@Component
public class AdviceRecorder {

    private final AtomicInteger calls = new AtomicInteger();

    public void mark() {
        calls.incrementAndGet();
    }

    public int count() {
        return calls.get();
    }
}
```

Aspect trong bài kiểm thử:

```java
@Aspect
@Component
public class RecordingAspect {

    private final AdviceRecorder recorder;

    public RecordingAspect(AdviceRecorder recorder) {
        this.recorder = recorder;
    }

    @Before(
        "execution(* com.example.demo.inventory.InventoryOperations.reserve(..))"
    )
    public void before() {
        recorder.mark();
    }
}
```

Gọi `inventory.reserve("SKU-200")`, rồi kiểm tra counter tăng như kỳ vọng. Khi test song song, cần cách ly hoặc reset collaborator để số lần gọi của test khác không gây nhiễu.

### 21.4. Không assert generated class name

Không nên test:

```java
assertThat(inventory.getClass().getName())
        .contains("com.sun.proxy");
```

Tên Java proxy có thể khác giữa các phiên bản JDK. Dùng API:

```java
assertThat(AopUtils.isJdkDynamicProxy(inventory)).isTrue();
```

hoặc:

```java
assertThat(AopUtils.isCglibProxy(inventory)).isTrue();
```

## 22. Khi nào không nên tạo hoặc gỡ proxy?

### 22.1. Không bypass proxy để “tránh lỗi kiểu”

Nếu constructor yêu cầu concrete class trong khi bean là JDK proxy, việc truy cập target object từ hạ tầng rồi truyền thủ công vào service có thể khiến transaction, cache và security advice bị bỏ qua.

Sửa đúng dependency contract thường là giải pháp tốt hơn.

### 22.2. Không thay proxy strategy chỉ vì một câu lệnh cast

Chuyển từ JDK sang class-based có thể tác động tới nhiều bean. Trước khi đổi, hãy cân nhắc:

- Có final class/method không?
- Module hoặc thư viện bên ngoài có dùng proxy strategy riêng không?
- Interface đã diễn đạt đủ hợp đồng nghiệp vụ chưa?
- Những integration test có phụ thuộc proxy type không?

Nếu chỉ một client cần method của implementation, có thể nên trích interface phù hợp thay vì đổi cấu hình toàn hệ thống.

### 22.3. Không phụ thuộc Spring AOP API trong business logic

Những lời gọi như:

```java
AopUtils.isAopProxy(service)
```

nên phục vụ quan sát, debug hoặc test hạ tầng. Business logic không nên thay đổi kết quả thanh toán chỉ vì service đang là JDK proxy hay CGLIB proxy.

## 23. Bài tập thực hành

### Bài 1 — Dự đoán assignability

Cho:

```java
interface TaskPort {
    void run();
}

class DefaultTask implements TaskPort {
    @Override
    public void run() {
    }
}
```

Giả sử Spring expose bean qua JDK proxy implement `TaskPort`. Hãy giải thích:

- Inject `TaskPort` có thể thành công không?
- Inject `DefaultTask` có thể thành công không?
- `proxy instanceof TaskPort` và `proxy instanceof DefaultTask` có kết quả gì?

### Bài 2 — Quan sát hai proxy strategy

Dùng ví dụ `InventoryService` và `InventoryLoggingAspect`. Cấu hình:

```properties
spring.aop.proxy-target-class=false
```

Ghi lại `getClass()`, `AopUtils.isJdkDynamicProxy`, `AopUtils.getTargetClass` và `instanceof`.

Sau đó đổi thành `true`, khởi động lại và so sánh.

### Bài 3 — Tái hiện lỗi inject concrete class

Trong JDK mode, đổi constructor của `InventoryRunner` từ `InventoryOperations` sang `InventoryService`.

Quan sát thông báo lỗi khi startup, rồi sửa lại bằng interface. Giải thích tại sao bean name đúng không đủ để gán object cho concrete class.

### Bài 4 — Thử `@Qualifier`

Tạo hai implementation `EmailSender` và `SmsSender` cùng implement `NotificationSender`. Inject một bean bằng:

```java
public AlertService(
        @Qualifier("emailSender") NotificationSender sender) {
    this.sender = sender;
}
```

Giải thích vì sao qualifier giải quyết **chọn bean** chứ không thay đổi kiểu proxy.

### Bài 5 — Thử final class

Tạo một class `final` có method được aspect chọn. Bật class-based proxy và quan sát việc Spring có thể tạo proxy phù hợp không.

Sau đó bỏ `final` hoặc dùng interface-based mode khi class có interface.

### Bài 6 — Self-invocation

Tạo service có method A gọi trực tiếp method B, trong khi B được advice bằng `@Transactional` hoặc custom aspect.

Quan sát lời gọi ngoài proxy và lời gọi nội bộ. Tách B sang service riêng rồi gọi qua dependency được inject; so sánh kết quả.

### Bài 7 — Scoped proxy

Tạo một `@RequestScope` bean và inject vào singleton service. Gọi endpoint từ hai request khác nhau và quan sát scoped target.

Giải thích tại sao reference proxy có thể giữ ổn định nhưng target request thay đổi.

### Bài 8 — `@Lazy` dependency

Inject `HeavyReportEngine` qua tham số constructor mang `@Lazy`. Quan sát thời điểm bean được resolve và so sánh với `@Lazy` trên class.

### Bài 9 — Kiểm thử bằng `AopUtils`

Viết integration test xác nhận JDK proxy và CGLIB proxy bằng API của Spring. Không so sánh generated class name.

Thêm một test gọi method và xác nhận advice thực sự chạy.

### Bài 10 — Thiết kế hợp đồng interface

Thư viện cung cấp `DocumentProcessor` và class `PdfProcessor`. Hệ thống phải chạy được với cả JDK proxy mode và class-based mode.

Thiết kế `DocumentController` inject `DocumentProcessor`; nếu có thêm `WordProcessor`, dùng qualifier phù hợp. Giải thích vì sao điều này bền hơn inject `PdfProcessor` trực tiếp.

## 24. Tổng kết

Khi Spring tạo proxy, bean mà client nhận qua dependency injection có thể là **proxy object**, không phải target instance. Với **JDK dynamic proxy**, object thường chỉ implement những interface được công bố nên có thể inject theo interface nhưng không assignable với concrete target class. Với **CGLIB/class-based proxy**, object thường kế thừa target class và có thể inject bằng cả interface lẫn class khi subclass proxy tạo được.

Hãy dùng `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy` và `getTargetClass` để chẩn đoán; dùng `instanceof` để hiểu khả năng gán kiểu. Đừng suy luận từ tên generated class, đừng dùng `@Qualifier` hoặc `@Primary` như cách ép proxy sang concrete class, và đừng lấy target trực tiếp để né advice.

Thiết kế ít phụ thuộc proxy strategy nhất thường là **constructor injection qua interface nghiệp vụ rõ ràng**. Cuối cùng, bean là proxy không có nghĩa mọi method đều được advice: kết quả còn phụ thuộc pointcut, visibility, final method và việc lời gọi có đi qua proxy boundary hay không.
