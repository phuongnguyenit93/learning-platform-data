# Spring AOP dựa trên proxy trong container

Spring AOP (*Aspect-Oriented Programming*) giúp tách những xử lý dùng chung khỏi logic nghiệp vụ: ghi log, đo thời gian thực thi, kiểm tra quyền, quản lý transaction, caching hoặc các quy tắc cần áp dụng trước/sau lời gọi method. Thay vì lặp lại cùng một đoạn code trong hàng chục service, Spring có thể đặt một lớp **proxy** trước bean để bổ sung hành vi mỗi khi một method phù hợp được gọi.

Điểm nền tảng của Spring AOP là: **advice thường chạy khi lời gọi method đi qua proxy do Spring container quản lý**. Spring AOP không tự viết lại bytecode của mọi class trong chương trình, không chặn được mọi lời gọi Java, và không làm một object được tạo bằng `new` tự nhiên trở thành đối tượng được áp dụng aspect.

Vì vậy, hiểu AOP không chỉ là nhớ cú pháp `@Aspect` hay `@Around`. Bạn cần hình dung rõ **ai tạo proxy, caller đang giữ reference tới proxy hay target, phương thức nào có thể bị intercept, và điều gì xảy ra khi target gọi method của chính nó**.

Bài này xây dựng mô hình từ đầu, kèm ví dụ Spring Boot, sơ đồ đường đi của lời gọi, so sánh JDK dynamic proxy với CGLIB, những giới hạn liên quan đến `final`/`private`/constructor, cách kiểm tra proxy trong test và quy tắc thiết kế để tránh hành vi “annotation có nhưng không chạy”.

## 1. Bài toán: logic xuyên suốt nhiều thành phần

Giả sử hệ thống có các service:

~~~java
@Service
public class OrderService {
    public String placeOrder(String orderId) {
        // Logic tạo đơn hàng.
        return "order-" + orderId;
    }
}

@Service
public class InvoiceService {
    public String issueInvoice(String orderId) {
        // Logic phát hành hóa đơn.
        return "invoice-" + orderId;
    }
}
~~~

Bạn muốn đo thời gian mỗi method xử lý để ghi nhận hiệu năng. Cách trực tiếp là chèn thời gian trước và sau từng method:

~~~java
public String placeOrder(String orderId) {
    long start = System.nanoTime();
    try {
        return doPlaceOrder(orderId);
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println("Elapsed: " + elapsed);
    }
}
~~~

Khi nhiều method đều có yêu cầu giống nhau, cách này tạo ra một số vấn đề:

- Logic nghiệp vụ và logic quan sát bị trộn lẫn.
- Dễ quên instrument một method mới.
- Khó cập nhật một quy tắc áp dụng trên toàn hệ thống.
- Các test nghiệp vụ phải đối mặt với code hạ tầng không liên quan.
- Một thay đổi về log/metric có thể ảnh hưởng tới nhiều class.

AOP giải quyết bằng cách chuyển trách nhiệm đo thời gian vào một **aspect**. Aspect mô tả *khi nào* cần can thiệp và *cần làm gì* trước/sau lời gọi.

Tuy nhiên, việc can thiệp của **Spring AOP** có một ranh giới cụ thể: nó diễn ra khi lời gọi vào **Spring AOP proxy**.

## 2. Proxy là gì?

Proxy là một object đứng trước một object khác (target). Caller gọi method trên proxy; proxy có thể thực hiện xử lý bổ sung rồi chuyển lời gọi tới target.

~~~mermaid
flowchart LR
    C["Controller / Caller"] --> P["AOP Proxy"]
    P --> A["Interceptor / Advice"]
    A --> T["Target Service"]
    T --> R["Kết quả / Exception"]
    R --> A
    A --> P
    P --> C
~~~

Với một method `placeOrder`, luồng khái quát:

1. Controller nhận reference được inject.
2. Reference đó có thể là **proxy**, không phải raw target.
3. Caller gọi `proxy.placeOrder(...)`.
4. Proxy xác định các interceptor/advice áp dụng cho method.
5. Advice thực hiện logic trước lời gọi (ví dụ bắt đầu timer).
6. Advice cho phép lời gọi tiến tới target.
7. Target chạy logic nghiệp vụ.
8. Advice xử lý kết quả hoặc exception (ví dụ ghi thời gian).
9. Kết quả hoặc exception quay về caller.

Nếu một bean không được tạo proxy hoặc method không khớp advisor nào, lời gọi có thể đi thẳng vào target mà không được xử lý AOP.

### 2.1. Proxy khác target

Giả sử:

~~~java
@Service
public class OrderService {
    public void submit() {
        System.out.println("Saving an order");
    }
}
~~~

Khi có aspect áp dụng cho `submit()`, Spring có thể expose một proxy thay cho target để các bean khác sử dụng. Điều đó không có nghĩa Spring sửa nội dung mã nguồn class `OrderService`.

Trong class-based proxy, proxy có thể là một subclass do CGLIB tạo ra. Trong interface-based proxy, proxy là một object được tạo bằng JDK dynamic proxies và triển khai các interface tương ứng. Cả hai có thể cung cấp cùng một hành vi AOP nhưng khác nhau về kiểu runtime và các method có thể intercept.

### 2.2. Proxy chỉ hữu ích khi caller thực sự đi qua nó

So sánh hai luồng:

~~~text
Caller -> Proxy -> Advice -> Target.method()      (được intercept)
Caller -> Target.method()                         (không đi qua proxy)
~~~

Đây là nguồn gốc của các giới hạn rất quan trọng như *self-invocation* và object được tạo bằng `new`.

## 3. Spring AOP được triển khai trong container ra sao?

Spring container quản lý bean qua các giai đoạn: đăng ký bean definition, khởi tạo object, inject dependency, áp dụng `BeanPostProcessor`, initialization và expose bean cho consumer.

AOP tận dụng chính cơ chế này. Khi infrastructure AOP được bật, Spring đăng ký các thành phần như **auto-proxy creator** để nhận biết các bean phù hợp với advisor và tạo proxy khi cần.

~~~mermaid
flowchart TD
    A["BeanDefinition được đăng ký"] --> B["Spring tạo target object"]
    B --> C["Dependency injection / initialization"]
    C --> D["AOP BeanPostProcessor xem xét bean"]
    D --> E{"Có advisor khớp?"}
    E -->|Có| F["Tạo / expose AOP proxy"]
    E -->|Không| G["Expose bean thông thường"]
    F --> H["Consumer nhận proxy từ container"]
    G --> I["Consumer nhận bean"]
    H --> J["Method call đi qua advisor chain"]
    I --> K["Method call trực tiếp"]
~~~

Sơ đồ giản lược thứ tự nội bộ để làm rõ ý tưởng: Spring quản lý target và có thể expose một proxy cho phần còn lại của ứng dụng. Trong các tình huống đặc biệt như circular dependency hoặc bean tạo bởi infrastructure post-processor, chi tiết tạo/expose proxy có thể khác.

### 3.1. BeanPostProcessor và auto-proxy creator

`BeanPostProcessor` là extension point cho phép hạ tầng xử lý bean trong quá trình khởi tạo. AOP infrastructure sử dụng post-processor thích hợp để tìm advisor và quyết định có cần proxy không.

Với cấu hình dùng `@Aspect`, một thành phần tiêu biểu là `AnnotationAwareAspectJAutoProxyCreator`. Nó tìm advice được khai báo theo cú pháp AspectJ annotation và tạo Spring AOP proxy cho các target phù hợp.

**Không phải mọi bean đều trở thành proxy.** Việc có `spring-boot-starter-aop` trên classpath không có nghĩa mọi service đều bị wrap. Spring cần advisor/pointcut phù hợp với bean và method, hoặc infrastructure feature khác yêu cầu proxy.

### 3.2. Object đưa vào constructor là proxy hay target?

Giả sử:

~~~java
@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/orders")
    public void create() {
        orderService.submit();
    }
}
~~~

Nếu `OrderService` được Spring AOP proxy, reference mà controller nhận qua injection thường là **proxy**. Controller không cần tự tạo proxy hoặc gọi một API AOP đặc biệt.

Spring giải quyết dependency và cung cấp bean được expose cuối cùng. Đây là lý do constructor injection từ container và việc gọi qua một bean khác thường khiến advice hoạt động đúng.

### 3.3. Spring AOP không tự áp dụng cho mọi object trong JVM

Một object được tạo bằng:

~~~java
OrderService service = new OrderService();
service.submit();
~~~

không đi qua Spring container. Nó không tự nhận proxy/advice chỉ vì class `OrderService` mang `@Service` hoặc method có annotation liên quan đến AOP.

Annotation là metadata. Container và infrastructure phải tham gia để metadata tạo thành hành vi runtime.

## 4. Bật AOP trong Spring Boot

Một ứng dụng Spring Boot có thể dùng AspectJ-style annotations trên nền **Spring AOP proxy**, không cần AspectJ compile-time weaving.

Với Spring Boot 3.x, dependency thường dùng là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Starter cung cấp các thành phần cần thiết cho Spring AOP và AspectJ-style pointcut parsing. Khi auto-configuration AOP của Boot có điều kiện phù hợp, Spring Boot có thể tự kích hoạt AOP support. Với trường hợp ứng dụng Boot thông thường đã có starter, bạn không cần thêm `@EnableAspectJAutoProxy` chỉ vì muốn dùng `@Aspect`.

### 4.1. @EnableAspectJAutoProxy

Trong Spring Framework hoặc một context được dựng thủ công, có thể bật cơ chế nhận diện `@Aspect` bằng:

~~~java
@Configuration
@EnableAspectJAutoProxy
public class AopConfiguration {
}
~~~

`@EnableAspectJAutoProxy` cho phép hạ tầng dùng các `@Aspect` bean để tạo advisor và proxy. Tên annotation có “AspectJ” vì dùng mô hình/annotation và ngôn ngữ pointcut kiểu AspectJ; bản thân Spring AOP vẫn dựa trên proxy, không đồng nghĩa ứng dụng đã bật AspectJ weaving.

Trong Spring Boot, hãy kiểm tra auto-configuration hiện có trước khi thêm cấu hình trùng lặp.

### 4.2. Một số property liên quan

~~~properties
spring.aop.auto=true
spring.aop.proxy-target-class=true
~~~

Trong Spring Boot, AOP auto-configuration được bật mặc định khi điều kiện classpath phù hợp. Boot cũng thường chọn **class-based proxy** (CGLIB) theo mặc định thông qua `spring.aop.proxy-target-class=true`.

Đặt:

~~~properties
spring.aop.proxy-target-class=false
~~~

để ưu tiên JDK dynamic proxy khi target có interface thích hợp. Nếu target không có interface, Spring vẫn có thể cần class-based proxy.

`spring.aop.auto=false` ảnh hưởng tới **AOP auto-configuration của Spring Boot**; nó không phải công tắc toàn cục tắt mọi loại proxy có thể được tạo bởi các infrastructure feature khác, chẳng hạn transaction management được cấu hình riêng.

Không thay proxy strategy ở production chỉ để làm một class cụ thể cast được; việc thay đổi có thể ảnh hưởng đến nhiều bean và các điểm injection.

## 5. Hai cơ chế chính: JDK dynamic proxy và CGLIB

Spring AOP thường có hai lựa chọn tạo proxy:

| Tiêu chí | JDK dynamic proxy | CGLIB class-based proxy |
| --- | --- | --- |
| Cách hoạt động | Proxy implement interface của target | Proxy tạo subclass của target class |
| Yêu cầu target có interface | Thường có | Không bắt buộc |
| Kiểu runtime | JDK-generated proxy class | Subclass được sinh động |
| Injection bằng interface | Phù hợp | Phù hợp nếu target triển khai interface |
| Injection bằng concrete class | Có thể lỗi vì JDK proxy không phải subtype của class | Có thể nếu class proxy được |
| Target class là `final` | Interface proxy vẫn có thể dùng | Không thể subclass final class |
| Method là `final` | Method qua interface có thể được intercept bởi JDK proxy | Không thể override method final |
| Private method | Không được intercept theo mô hình Spring proxy | Không thể override/intercept |
| Self-invocation | Bị bypass | Bị bypass |
| Thường là mặc định Spring Framework khi có interface | Có | Phụ thuộc cấu hình |
| Mặc định phổ biến của Spring Boot | Có thể chọn bằng property | Thường được Boot ưu tiên |

### 5.1. Ví dụ target có interface

~~~java
public interface PaymentService {
    void pay(String orderId);
}

@Service
public class DefaultPaymentService implements PaymentService {

    @Override
    public void pay(String orderId) {
        System.out.println("Paying order " + orderId);
    }
}
~~~

Với JDK proxy, caller nên làm việc với interface:

~~~java
@Service
public class CheckoutService {

    private final PaymentService paymentService;

    public CheckoutService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout(String orderId) {
        paymentService.pay(orderId);
    }
}
~~~

Nếu cố inject bằng concrete class `DefaultPaymentService` trong khi Spring expose JDK proxy chỉ implement `PaymentService`, container có thể không cung cấp bean có kiểu concrete như mong đợi.

Thiết kế dựa trên interface thường thuận tiện cho test doubles, thay implementation và giảm coupling giữa các module.

### 5.2. CGLIB khi class không có interface

~~~java
@Service
public class ShippingService {

    public void ship(String orderId) {
        System.out.println("Shipping order " + orderId);
    }
}
~~~

Nếu phương thức public `ship` khớp advisor và class có thể được subclass, Spring có thể tạo proxy dạng CGLIB. Caller vẫn có thể inject `ShippingService` vì proxy là subtype của class.

CGLIB không cần bạn tự viết một subclass. Spring tạo proxy động theo cơ chế của nó.

### 5.3. Vì sao Spring Boot thường dùng CGLIB?

Lựa chọn class-based proxy giúp nhiều bean không cần interface riêng vẫn được AOP proxy và inject theo concrete type. Đây là một default tiện dụng, nhưng nó không biến mọi method thành interceptable: `final`, `private`, những phương thức không thể override và self-invocation vẫn là giới hạn.

Trong Spring Framework nói chung, nếu target implement ít nhất một interface và không ép class-based proxy, JDK dynamic proxy là lựa chọn thường gặp. Spring Boot cấu hình mặc định riêng, nên phải phân biệt **framework default** với **Boot auto-configuration default**.

### 5.4. Proxy strategy có thể được quyết định ở mức container

Khi nhiều cơ chế sử dụng auto-proxying, chẳng hạn transaction, caching và AspectJ-style AOP, Spring có thể hợp nhất các thiết lập proxy creator thành một hạ tầng thống nhất với cấu hình proxy có hiệu lực mạnh hơn.

Không nên giả định rằng đặt một annotation cho một feature nhất định sẽ chỉ ảnh hưởng đúng bean đó mà hoàn toàn không liên quan đến các proxy khác. Khi thay `proxyTargetClass`, hãy kiểm tra các bean transaction/cache/AOP đang dùng.

## 6. Ví dụ hoàn chỉnh: tự viết annotation và aspect đo thời gian

Ta tạo một annotation `@TimedOperation` để đánh dấu method cần đo thời gian, sau đó tạo aspect xử lý những lời gọi đi qua proxy.

### 6.1. Tạo annotation

~~~java
package com.example.demo.aop;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TimedOperation {
}
~~~

`@Target(METHOD)` cho phép gắn annotation vào method. `@Retention(RUNTIME)` giữ metadata tại runtime để Spring AOP có thể nhận diện.

### 6.2. Tạo @Aspect

~~~java
package com.example.demo.aop;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TimedOperationAspect {

    @Around("@annotation(com.example.demo.aop.TimedOperation)")
    public Object measure(ProceedingJoinPoint joinPoint) throws Throwable {
        long startedAt = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long elapsedNanos = System.nanoTime() - startedAt;

            System.out.printf(
                    "Method %s took %.3f ms%n",
                    joinPoint.getSignature().toShortString(),
                    elapsedNanos / 1_000_000.0
            );
        }
    }
}
~~~

Các thành phần:

- `@Aspect`: đánh dấu class khai báo logic AOP.
- `@Component`: đăng ký aspect thành Spring bean qua component scanning.
- `@Around(...)`: advice bọc quanh lời gọi method khớp pointcut.
- `ProceedingJoinPoint`: cung cấp thông tin lời gọi và phương thức `proceed()` để tiếp tục chuỗi interceptor/target.
- `finally`: ghi thời gian dù method trả kết quả hay ném exception.

Ví dụ in `System.out` để dễ quan sát. Trong production, hãy sử dụng logging/metrics framework, hạn chế dữ liệu nhạy cảm và cân nhắc overhead trên hot path.

### 6.3. Gắn annotation lên service

~~~java
package com.example.demo.service;

import com.example.demo.aop.TimedOperation;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    @TimedOperation
    public int availableItems(String sku) {
        // Mô phỏng logic đọc dữ liệu.
        return sku == null ? 0 : 42;
    }
}
~~~

Controller inject service:

~~~java
package com.example.demo.web;

import com.example.demo.service.InventoryService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InventoryController {

    private final InventoryService inventoryService;

    public InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @GetMapping("/inventory")
    public int inventory(@RequestParam String sku) {
        return inventoryService.availableItems(sku);
    }
}
~~~

Khi HTTP request gọi controller, controller gọi service qua reference do Spring inject. Nếu proxy/advisor được tạo đúng, aspect sẽ đo thời gian cho `availableItems`.

~~~mermaid
sequenceDiagram
    participant Client as HTTP client
    participant Controller as InventoryController
    participant Proxy as InventoryService proxy
    participant Aspect as TimedOperationAspect
    participant Target as InventoryService target
    Client->>Controller: GET /inventory?sku=A-1
    Controller->>Proxy: availableItems("A-1")
    Proxy->>Aspect: @Around measure()
    Aspect->>Target: joinPoint.proceed()
    Target-->>Aspect: 42
    Aspect->>Aspect: Ghi elapsed time
    Aspect-->>Proxy: 42
    Proxy-->>Controller: 42
    Controller-->>Client: HTTP 200 / 42
~~~

Các bước cần có để hoạt động:

1. Project có AOP infrastructure phù hợp, ví dụ `spring-boot-starter-aop`.
2. Aspect nằm trong vùng component scan hoặc được đăng ký dưới dạng bean.
3. Service là bean do Spring quản lý.
4. Public method có annotation và khớp pointcut.
5. Caller dùng bean được container inject, không dùng target tạo thủ công.
6. Lời gọi đi **từ bên ngoài qua proxy**.

### 6.4. @Around có nhất thiết phải gọi proceed()?

Không, và đây là lý do `@Around` mạnh nhất nhưng cũng dễ làm sai. Một around advice có thể quyết định không gọi target, gọi một lần hoặc trong thiết kế đặc biệt gọi nhiều lần.

Với lời gọi nghiệp vụ thông thường, hãy gọi `joinPoint.proceed()` **đúng một lần**, rồi giữ nguyên kết quả hoặc exception trừ khi có yêu cầu rất rõ ràng.

Nếu quên `proceed()`:

~~~java
@Around("@annotation(com.example.demo.aop.TimedOperation)")
public Object invalid(ProceedingJoinPoint joinPoint) {
    // Target method không chạy.
    return null;
}
~~~

Lời gọi sẽ bị chặn và method nghiệp vụ không chạy. Nếu method trả primitive hoặc caller không chấp nhận null, lỗi có thể xuất hiện ở nơi khác.

## 7. Join point, pointcut, advice, aspect và advisor

Các thuật ngữ AOP thường đi cùng nhau:

| Thuật ngữ | Ý nghĩa trong Spring AOP |
| --- | --- |
| **Join point** | Điểm có thể áp dụng advice; Spring AOP tập trung vào method execution của Spring bean |
| **Pointcut** | Biểu thức xác định những method executions nào được chọn |
| **Advice** | Hành vi chạy trước/sau/quanh lời gọi |
| **Aspect** | Nhóm pointcut và advice giải quyết một mối quan tâm chung |
| **Target** | Object cung cấp logic nghiệp vụ gốc |
| **Proxy** | Object trung gian đưa lời gọi qua advice |
| **Advisor** | Kết hợp advice với điều kiện pointcut ở mức hạ tầng Spring |

Một số tài liệu AspectJ còn có thuật ngữ **weaving**: gắn advice vào join point của chương trình. Trong Spring AOP thông thường, hành vi được cung cấp bằng proxy, không bằng việc weave trực tiếp bytecode target.

### 7.1. Spring AOP hỗ trợ method execution join point

Spring AOP dựa trên proxy, nên các join point được áp dụng chủ yếu là **thực thi method trên Spring bean**.

Nó không cung cấp khả năng intercept tùy ý:

- Lời gọi constructor hoặc quá trình khởi tạo object bằng `new`.
- Đọc/ghi trực tiếp một field.
- Thực thi code của một object không được Spring quản lý.
- Các điểm join point đặc biệt mà AspectJ full weaving hỗ trợ, chẳng hạn field get/set hoặc constructor execution.

Nếu yêu cầu thực sự cần can thiệp vào field access, constructor hoặc object ngoài container, Spring AOP proxy có thể không đủ; khi đó cần xem xét AspectJ compile-time/load-time weaving hoặc một kiến trúc khác.

### 7.2. Pointcut bằng execution(...)

Ví dụ chọn mọi public method trong một package service:

~~~java
@Around("execution(public * com.example.demo.service.*.*(..))")
public Object observeService(ProceedingJoinPoint joinPoint)
        throws Throwable {
    return joinPoint.proceed();
}
~~~

Biểu thức `execution(public * com.example.demo.service.*.*(..))` có thể được đọc như sau:

- `public`: chỉ chọn method có visibility public.
- `*` đầu tiên: mọi kiểu trả về.
- `com.example.demo.service.*`: các class phù hợp trong package được nêu.
- `.*`: mọi tên method.
- `(..)`: nhận số lượng/kiểu tham số bất kỳ.

Để áp dụng cho các subpackage, có thể dùng pattern với `..`, ví dụ:

~~~java
@Pointcut("execution(* com.example.demo.service..*(..))")
public void applicationServiceOperations() {}
~~~

Một số biểu thức rộng có thể intercept nhiều method ngoài mong đợi. Hãy chọn phạm vi đủ hẹp để tránh log dữ liệu nhạy cảm hoặc làm tăng chi phí xử lý trên toàn bộ ứng dụng.

### 7.3. Pointcut bằng @annotation

~~~java
@Around("@annotation(com.example.demo.aop.TimedOperation)")
public Object measure(ProceedingJoinPoint joinPoint)
        throws Throwable {
    return joinPoint.proceed();
}
~~~

`@annotation` giới hạn advice tới method có annotation tương ứng trong bối cảnh pointcut được giải quyết. Cách này rất hữu ích khi chỉ muốn chọn một số method rõ ràng.

Đặt annotation trên **concrete implementation method** thường là lựa chọn dễ dự đoán, đặc biệt khi chuyển đổi giữa JDK interface proxy và CGLIB proxy. Đừng mặc định annotation ở interface method, implementation method và inherited method luôn được giải quyết giống nhau trong mọi cơ chế annotation-driven.

### 7.4. Tái sử dụng named pointcut

~~~java
@Aspect
@Component
public class ServiceAuditAspect {

    @Pointcut("within(com.example.demo.service..*)")
    public void inServiceLayer() {}

    @Pointcut("execution(public * *(..))")
    public void publicMethod() {}

    @Before("inServiceLayer() && publicMethod()")
    public void beforeServiceMethod() {
        // Logic audit chung.
    }
}
~~~

`@Pointcut` giúp tách điều kiện chọn method khỏi advice. Các pointcut có thể kết hợp với `&&`, `||` và `!` theo cú pháp hỗ trợ.

Không nên đưa logic nghiệp vụ thay đổi thường xuyên vào một biểu thức pointcut quá phức tạp. Khi phạm vi cần chọn thực sự mang nghĩa nghiệp vụ, một custom annotation thường dễ đọc và ổn định hơn.

## 8. Những loại advice thường gặp

AspectJ-style advice trong Spring bao gồm:

| Annotation | Thời điểm | Điểm cần nhớ |
| --- | --- | --- |
| `@Before` | Trước khi method được thực thi | Không trực tiếp thay đổi kết quả trả về |
| `@AfterReturning` | Khi method trả về bình thường | Có thể đọc kết quả, không thay thế object được trả về bằng cách gán lại parameter |
| `@AfterThrowing` | Khi method ném exception phù hợp | Phù hợp với audit lỗi, không mặc nhiên xử lý được mọi lỗi |
| `@After` | Sau method dù thành công hay ném exception | Tương tự ý nghĩa finally |
| `@Around` | Bao quanh invocation | Chủ động gọi `proceed()` và có thể thay đổi kết quả/exception |

Ví dụ `@Before`:

~~~java
@Aspect
@Component
public class LoggingAspect {

    @Before("execution(* com.example.demo.service..*(..))")
    public void beforeCall(JoinPoint joinPoint) {
        System.out.println(
                "Calling " + joinPoint.getSignature().toShortString()
        );
    }
}
~~~

Ví dụ `@AfterReturning`:

~~~java
@AfterReturning(
        pointcut = "execution(* com.example.demo.service..*(..))",
        returning = "result"
)
public void afterSuccess(Object result) {
    // Quan sát kết quả; không log nội dung nhạy cảm.
}
~~~

Ví dụ `@AfterThrowing`:

~~~java
@AfterThrowing(
        pointcut = "execution(* com.example.demo.service..*(..))",
        throwing = "error"
)
public void afterFailure(Throwable error) {
    // Ghi số liệu lỗi hoặc audit phù hợp.
}
~~~

Nếu chỉ cần ghi một mốc trước hoặc sau lời gọi, advice chuyên biệt có thể rõ hơn `@Around`. Nếu cần đo tổng thời gian, thay đổi kết quả, retry hoặc quyết định có đi tiếp hay không, `@Around` phù hợp hơn nhưng cần thận trọng với tác động phụ.

### 8.1. @AfterReturning và @AfterThrowing không thay thế finally

`@AfterReturning` chỉ chạy khi invocation trả về bình thường. `@AfterThrowing` dùng cho đường exception. Nếu luôn cần dọn dữ liệu theo scope invocation, `@After` hoặc `try/finally` trong `@Around` thích hợp hơn.

Ví dụ một phép đo thời gian dùng `finally` để ghi thời lượng kể cả khi target ném lỗi.

### 8.2. Không log toàn bộ args và return theo mặc định

`JoinPoint.getArgs()` có thể chứa password, access token, số tài khoản, dữ liệu cá nhân hoặc object rất lớn. Log `toString()` toàn bộ arguments cho mọi method có thể vừa rò rỉ dữ liệu vừa gây lỗi/overhead.

Chỉ ghi metadata được cho phép như operation name, duration, correlation ID an toàn và phân loại kết quả. Với thông tin nhạy cảm, hãy áp dụng quy tắc masking/redaction phù hợp.

## 9. Nhiều advice và chuỗi interceptor

Một method có thể khớp nhiều advisor: logging, timing, caching, transaction, validation hoặc authorization.

Sơ đồ:

~~~mermaid
flowchart LR
    A["Caller"] --> P["Proxy"]
    P --> X["Advice A"]
    X --> Y["Advice B"]
    Y --> Z["Advice C"]
    Z --> T["Target method"]
    T --> Z
    Z --> Y
    Y --> X
    X --> P
~~~

Lời gọi có thể được bao quanh theo kiểu lồng nhau. Nếu một around advice không gọi `proceed()`, các interceptor bên trong và target có thể không chạy.

### 9.1. @Order điều khiển thứ tự aspect

~~~java
@Aspect
@Component
@Order(10)
public class OuterAspect {
    // ...
}

@Aspect
@Component
@Order(20)
public class InnerAspect {
    // ...
}
~~~

Với các aspect được Spring sắp xếp theo order, số order **nhỏ hơn có độ ưu tiên cao hơn**. Aspect có ưu tiên cao thường chạy trước ở đường vào và kết thúc sau ở đường ra khi dùng around chain.

Trong một aspect có nhiều advice cùng join point, thứ tự chi tiết của advice còn phụ thuộc loại advice và quy tắc framework. Đừng dựa vào việc sắp xếp tên method source để tạo hợp đồng thứ tự.

### 9.2. @Order không phải thứ tự khởi tạo bean

`@Order` trên aspect liên quan đến precedence trong advice chain. Nó không buộc một service được khởi tạo trước service khác trong toàn bộ container. Nếu cần dependency khởi tạo/hủy, dùng constructor injection hoặc `@DependsOn` khi chỉ có quan hệ thứ tự.

### 9.3. Transaction và caching cùng xuất hiện

Nếu một method được đánh dấu `@Transactional` và `@Cacheable`, cả hai cơ chế có thể dùng proxy-based interceptors. Thứ tự advisor có thể ảnh hưởng:

- Transaction bắt đầu trước hay sau khi cache lookup xảy ra.
- Một cache hit có đi vào phần transaction interceptor hay không.
- Việc cache result diễn ra theo điều kiện nào.

Không nên suy đoán thứ tự chỉ từ thứ tự annotation trong source. Khi semantics phụ thuộc ordering, hãy thiết kế và kiểm thử transaction/cache behavior một cách tường minh.

## 10. Giới hạn quan trọng nhất: self-invocation

**Self-invocation** là tình huống một method trong target gọi method khác của chính target bằng `this` hoặc gọi trực tiếp không đi qua proxy.

Ví dụ:

~~~java
@Service
public class CheckoutService {

    public void checkout(String orderId) {
        validate(orderId);
        charge(orderId); // Lời gọi nội bộ trong cùng object.
    }

    @TimedOperation
    public void charge(String orderId) {
        // Logic trừ tiền.
    }

    private void validate(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
    }
}
~~~

Khi controller gọi `checkoutService.checkout(...)` qua proxy, proxy có thể intercept `checkout` nếu pointcut tương ứng khớp. Nhưng lời gọi `charge(...)` **từ bên trong target** không đi lại qua proxy.

Vì vậy, `@TimedOperation` trên `charge` có thể không được kích hoạt trong đường gọi từ `checkout`, dù nếu một bean khác gọi trực tiếp `checkoutService.charge(...)` thì advice chạy.

~~~mermaid
flowchart TD
    A["Controller"] --> B["CheckoutService proxy"]
    B --> C["Target.checkout()"]
    C --> D["this.charge()"]
    D --> E["Target.charge() trực tiếp"]
    F["Bean khác"] --> B2["CheckoutService proxy"]
    B2 --> G["@TimedOperation advice"]
    G --> H["Target.charge()"]
~~~

Điểm khác biệt không nằm ở annotation, mà ở **đường đi của lời gọi**.

### 10.1. Self-invocation ảnh hưởng cả @Transactional

Ví dụ:

~~~java
@Service
public class OrderApplicationService {

    public void processOrder(String orderId) {
        saveOrder(orderId); // Internal call.
    }

    @Transactional
    public void saveOrder(String orderId) {
        // Ghi dữ liệu cần transaction.
    }
}
~~~

Với transaction management dùng proxy mode, lời gọi `saveOrder` từ `processOrder` trong cùng target **không kích hoạt transaction interceptor** của `saveOrder`.

Nếu `processOrder` đã được gọi trong một transaction khác, logic bên trong có thể vẫn chạy dưới transaction đang tồn tại; nhưng annotation `@Transactional` của `saveOrder` không được áp dụng *riêng* qua lời gọi nội bộ đó. Đây là khác biệt quan trọng khi debug propagation và rollback.

Với `@Cacheable`, `@Async` và các proxy-based features khác, self-invocation cũng cần được xem xét theo cơ chế tương ứng.

### 10.2. Cách xử lý khuyến nghị: tách trách nhiệm sang bean khác

~~~java
@Service
public class PaymentExecutor {

    @Transactional
    public void charge(String orderId) {
        // Thực hiện thao tác trong transaction.
    }
}

@Service
public class CheckoutService {

    private final PaymentExecutor executor;

    public CheckoutService(PaymentExecutor executor) {
        this.executor = executor;
    }

    public void checkout(String orderId) {
        executor.charge(orderId); // Lời gọi qua Spring-injected bean.
    }
}
~~~

`CheckoutService` nhận `PaymentExecutor` qua constructor injection. Khi Spring tạo proxy cho `PaymentExecutor`, lời gọi từ checkout đi qua proxy, nên advisor có thể chạy đúng.

Ưu điểm:

- Ranh giới transaction hoặc cross-cutting concern rõ ràng.
- Dependency thể hiện qua constructor.
- Dễ viết unit test bằng test double.
- Không phụ thuộc vào API nội bộ của Spring AOP.
- Phù hợp với nguyên tắc phân tách application orchestration và operation cụ thể.

### 10.3. Self-injection và AopContext.currentProxy()

Có những workaround như inject proxy của chính bean hoặc gọi:

~~~java
((CheckoutService) AopContext.currentProxy()).charge(orderId);
~~~

Nhưng cách trên chỉ hoạt động khi proxy exposure được bật thích hợp và lời gọi hiện tại đang đi qua proxy. Nó cũng có thể lỗi cast khi dùng JDK dynamic proxy, và gắn chặt domain code với Spring AOP.

`AopContext.currentProxy()` yêu cầu cấu hình `exposeProxy = true` ở hạ tầng proxy, có thêm coupling và chi phí. Không coi đây là thiết kế mặc định. **Refactor sang một bean khác hoặc chỉnh lại ranh giới method public** thường là lựa chọn tốt hơn.

### 10.4. AspectJ weaving khác self-invocation ra sao?

AspectJ compile-time hoặc load-time weaving có thể can thiệp ở các join point trực tiếp trong bytecode và không bị giới hạn bởi đúng cơ chế self-invocation của Spring proxy AOP.

Điều đó **không có nghĩa** chỉ cần đặt `@Aspect` thì weaving đã được bật. Cấu hình weaving, build pipeline và class loading cần được thiết lập riêng. Trong một ứng dụng Spring Boot thông thường dùng `spring-boot-starter-aop`, bạn đang dùng **proxy-based Spring AOP**.

## 11. Method nào không thể intercept qua Spring proxy?

Proxy không phải một công cụ “chặn mọi dòng code”. Khả năng intercept phụ thuộc proxy strategy và loại method.

### 11.1. Private method

~~~java
@Service
public class ReportService {

    public void generate() {
        calculateInternal();
    }

    @TimedOperation
    private void calculateInternal() {
        // Không phải method có thể intercept qua Spring AOP proxy.
    }
}
~~~

Private method không được expose như một method có thể gọi từ ngoài qua proxy. CGLIB subclass cũng không thể override private method. Annotation AOP trên private method không khiến lời gọi nội bộ được intercept.

Nếu cần cross-cutting behavior cho một tác vụ, hãy đặt nó ở một **public operation boundary** có thể được caller khác gọi qua proxy hoặc tách thành bean riêng.

### 11.2. Final method với CGLIB

~~~java
@Service
public class FinalMethodService {

    @TimedOperation
    public final void execute() {
        // CGLIB không thể override method final này.
    }
}
~~~

Class-based proxy dựa trên subclass overriding method để intercept. Vì method `final` không thể override, nó không thể được CGLIB advice theo cách đó.

Nếu sử dụng JDK interface proxy, một method được gọi qua interface có thể đi qua invocation handler ngay cả khi implementation method là final. Vì vậy cần phân biệt giới hạn của **class-based proxy** với **interface-based proxy**.

### 11.3. Final class

~~~java
@Service
public final class FinalReportService {

    @TimedOperation
    public void execute() {
        // CGLIB không thể tạo subclass của final class.
    }
}
~~~

CGLIB không thể subclass một class được khai báo `final`. Nếu class đó implement interface phù hợp, JDK dynamic proxy có thể là một lựa chọn. Với ứng dụng Kotlin, class/method mặc định final theo ngôn ngữ; các plugin hỗ trợ mở class của Spring thường cần được cấu hình nếu muốn class-based proxy.

Không vội bỏ `final` khỏi mọi class. Hãy cân nhắc liệu class có thật sự cần Spring proxy hay có thể chuyển mối quan tâm sang API khác hoặc dùng interface.

### 11.4. Constructor và static method

Spring AOP proxy can thiệp vào method execution trên bean được gọi qua proxy, **không phải constructor invocation**. Một annotation pointcut trên method không biến các thao tác `new Target()` thành lời gọi được intercept.

Static method cũng không đi qua dispatch trên instance proxy theo cách Spring AOP cần. Không dựa vào `@Aspect` của Spring để advice static method.

### 11.5. Public, protected và package-private method

Với **JDK dynamic proxy**, interface-based invocation chủ yếu dựa trên các method public được interface expose. Method không nằm trên interface không tự nhiên là một API gọi qua JDK proxy.

Với **class-based proxy**, khả năng intercept các method không public phụ thuộc quy tắc override của Java và hạ tầng Spring. Đặc biệt, một số feature ở Spring Framework 6 có thể áp dụng cho `protected` và package-private method khi dùng class-based proxy. Tuy nhiên, **private và final method vẫn không thể được advice bằng CGLIB**.

Để viết code dễ dự đoán qua nhiều proxy strategy, nên thiết kế cross-cutting boundaries như **public service methods** và gọi chúng qua bean reference do Spring inject.

## 12. @PostConstruct, constructor và thời điểm proxy sẵn sàng

Một cạm bẫy khác là gọi method có aspect trong constructor hoặc `@PostConstruct` của cùng bean.

~~~java
@Service
public class StartupService {

    public StartupService() {
        // Không gọi method AOP-dependent từ constructor.
    }

    @PostConstruct
    public void init() {
        doWork(); // Lời gọi nội bộ, không qua AOP proxy.
    }

    @TimedOperation
    public void doWork() {
        // Logic cần advice.
    }
}
~~~

Ở thời điểm constructor, object đang được tạo. `@PostConstruct` là một initialization callback thuộc quá trình hình thành bean; nó không phải một lời gọi từ bên ngoài qua reference proxy được inject.

Vì vậy đừng dựa vào `@Transactional`, `@Async` hoặc một aspect tự định nghĩa khi gọi method cùng object trong `@PostConstruct`.

### 12.1. Muốn chạy nghiệp vụ sau startup thì làm gì?

Một lựa chọn là dùng `ApplicationRunner` hoặc `CommandLineRunner` trong một bean khác, inject service cần gọi:

~~~java
@Component
public class StartupRunner implements ApplicationRunner {

    private final StartupService service;

    public StartupRunner(StartupService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        service.doWork(); // Đường gọi ngoài qua bean đã được inject.
    }
}
~~~

Lúc runner chạy, context đã được refresh trong luồng startup thông thường. Nếu `StartupService` được AOP proxy, lời gọi từ runner có cơ hội đi qua proxy.

Nếu công việc chỉ nên chạy sau khi mọi runner hoàn tất, hãy cân nhắc `ApplicationReadyEvent` hoặc lifecycle event phù hợp. Không dùng early startup event trước context refresh để lấy service chưa sẵn sàng.

## 13. @Transactional, @Cacheable và @Async liên quan gì tới proxy?

Spring AOP thường được giới thiệu qua `@Aspect`, nhưng proxy infrastructure còn xuất hiện trong nhiều chức năng Spring.

### 13.1. @Transactional

~~~java
@Service
public class TransferService {

    @Transactional
    public void transfer(String from, String to, long amount) {
        // Thực hiện nhiều thao tác dữ liệu trong transaction.
    }
}
~~~

Khi transaction management được bật ở proxy mode, transaction interceptor tạo transaction boundary quanh lời gọi tới method phù hợp **qua proxy**.

Điều kiện vẫn là method được gọi qua Spring-managed bean, advisor được áp dụng đúng và có transaction manager thích hợp. Việc đặt annotation không tự tạo database transaction nếu không có hạ tầng giao dịch được cấu hình.

### 13.2. @Cacheable

~~~java
@Service
public class CatalogService {

    @Cacheable("products")
    public Product findProduct(String id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

Khi caching được bật và cache infrastructure phù hợp, interceptor có thể trả về dữ liệu từ cache mà không gọi target method.

Đây là ví dụ rõ ràng cho việc một advice **không nhất thiết gọi target**: khi cache hit, logic nghiệp vụ có thể được bỏ qua theo contract caching.

Self-invocation vẫn là điều cần kiểm tra với proxy-based caching.

### 13.3. @Async

~~~java
@Service
public class NotificationService {

    @Async
    public CompletableFuture<Void> sendNotification(String recipient) {
        // Thực hiện công việc trong executor theo cấu hình @Async.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Trong proxy mode mặc định của asynchronous method execution, lời gọi qua proxy mới được chuyển tới asynchronous interceptor/executor. Một lời gọi nội bộ vào `@Async` method trên cùng target có thể chạy đồng bộ ngoài dự kiến.

Cần bật/configure async execution phù hợp, chẳng hạn `@EnableAsync`, và xử lý exception/return type đúng contract. Spring AOP là một phần của cơ chế; annotation đơn lẻ không đủ để tạo hành vi nền.

### 13.4. Không phải mọi thứ “annotation-driven” đều dùng cùng một proxy

Spring MVC request mapping, Jakarta Bean Validation, event listeners hoặc serialization cũng dựa vào annotation metadata, nhưng không phải tất cả đều đi qua **cùng một kiểu AOP proxy**.

Đừng suy ra rằng mọi annotation Java bị ảnh hưởng bởi self-invocation giống `@Transactional`. Hãy tìm hiểu cơ chế thực thi của tính năng cụ thể.

## 14. Điểm khác giữa Spring AOP và AspectJ weaving

Hai thuật ngữ thường được đặt cạnh nhau nhưng phạm vi khác nhau.

| Tiêu chí | Spring AOP | AspectJ weaving |
| --- | --- | --- |
| Cơ chế chính | Proxy trong Spring container | Chèn advice bằng compile-time hoặc load-time weaving |
| Phạm vi object | Bean/lời gọi đi qua Spring proxy | Có thể áp dụng cả object không do Spring quản lý |
| Join points | Method execution của bean | Rộng hơn, gồm field access và constructor-related join points |
| Self-invocation | Bypass proxy | Có thể được advise bằng weaving |
| Yêu cầu cấu hình | AOP infrastructure / advisors | Weaver và công cụ cấu hình riêng |
| Dùng @AspectJ syntax | Có | Có |
| Tích hợp IoC container | Rất trực tiếp | Có thể kết hợp Spring nhưng không giới hạn ở proxy |

### 14.1. @Aspect không đồng nghĩa weaving

Code:

~~~java
@Aspect
@Component
public class SecurityAuditAspect {
    // Advice...
}
~~~

chỉ cho biết class khai báo aspect theo annotation syntax. Nếu dùng Spring AOP, aspect được đưa vào proxy advice chain; class nghiệp vụ không nhất thiết bị weave bytecode.

Muốn dùng AspectJ compile-time weaving hoặc load-time weaving, dự án cần cấu hình riêng. Không nên chuyển sang weaving chỉ để sửa một self-invocation có thể giải quyết bằng thiết kế service rõ hơn.

### 14.2. Khi nào Spring AOP đủ?

Spring AOP phù hợp với nhiều use case doanh nghiệp:

- Transaction boundaries ở service layer.
- Caching các lời gọi method.
- Ghi metric/log method-level.
- Chính sách áp dụng cho service public methods.
- Một số cơ chế bảo mật ở method boundary.
- Asynchronous interception theo contract của Spring.

Nếu không cần field/constructor join points hoặc object ngoài container, proxy-based AOP thường là cách đơn giản hơn để tích hợp trong Spring Boot.

## 15. this và target trong pointcut

Spring AOP có hai khái niệm dễ nhầm:

- **Proxy object**: reference mà caller đang gọi.
- **Target object**: object cung cấp implementation nghiệp vụ bên dưới.

Trong Spring AOP, biểu thức pointcut `this(Type)` xét kiểu của **proxy**, còn `target(Type)` xét kiểu của **target**.

Với JDK dynamic proxy implement interface:

~~~java
public interface ReportPort {
    String createReport();
}
~~~

proxy có thể là một đối tượng thuộc class do JDK tạo, không phải subtype của `DefaultReportService`. Vì vậy biểu thức `this(DefaultReportService)` có thể không match trong khi `target(DefaultReportService)` match, tùy cấu hình target và type.

Với CGLIB class-based proxy, proxy là subtype của target class nên cả hai có thể match theo những cách gần nhau hơn.

Đây là lý do khi dùng advanced pointcut, bạn cần biết proxy strategy đang có hiệu lực. Phần lớn ứng dụng có thể tránh phụ thuộc vào sự khác nhau này bằng cách dùng pointcut theo method/annotation/service layer rõ ràng.

## 16. Proxy và method return type

Around advice phải giữ contract của method được gọi. Ví dụ một method trả về `int` hoặc `String` không nên bị around advice trả `null` hoặc một kiểu không tương thích.

~~~java
@Around("@annotation(com.example.demo.aop.TimedOperation)")
public Object measure(ProceedingJoinPoint joinPoint) throws Throwable {
    return joinPoint.proceed();
}
~~~

Đoạn trên giữ nguyên kết quả target. Nếu có yêu cầu biến đổi kết quả, phải hiểu kiểu trả về thực tế, generics và các ngoại lệ.

### 16.1. Reactive publisher và async return

Một method:

~~~java
public Mono<Order> findOrder(String id) {
    return repository.findById(id);
}
~~~

có thể trả về `Mono` rất nhanh, trong khi database call bên trong pipeline chỉ thực sự thực hiện khi có subscription. Một aspect đo thời gian quanh `joinPoint.proceed()` có thể chỉ đo **thời gian tạo publisher**, không đo toàn bộ thời gian hoàn tất reactive pipeline.

Tương tự, method trả `CompletableFuture` có thể trả future trước khi công việc thực sự hoàn thành. Nếu metric cần tổng thời gian công việc, phải instrument completion của publisher/future theo abstraction phù hợp, không chỉ quanh method invocation.

### 16.2. Thread-local và context propagation

Nhiều aspect sử dụng thread-local để lưu correlation ID hoặc transaction context. Với `@Async`, task executor hoặc reactive pipelines, thread thực thi có thể thay đổi.

Đừng mặc định thread-local được truyền qua các boundary đó. Nếu aspect cần context xuyên luồng, dùng cơ chế context propagation của framework/runtime phù hợp với loại công việc.

## 17. Kiểm tra runtime: bean có phải AOP proxy không?

Spring cung cấp một số utility trong `org.springframework.aop.support.AopUtils`:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("inventoryService");

boolean isProxy = AopUtils.isAopProxy(bean);
boolean isJdkProxy = AopUtils.isJdkDynamicProxy(bean);
boolean isCglibProxy = AopUtils.isCglibProxy(bean);
~~~

Những method này hữu ích khi debug:

- `isAopProxy(bean)`: bean có được Spring AOP expose dưới dạng proxy không.
- `isJdkDynamicProxy(bean)`: có phải proxy dựa trên JDK dynamic proxies không.
- `isCglibProxy(bean)`: có phải class-based CGLIB proxy không.

Không nên đặt logic nghiệp vụ phụ thuộc vào kết quả các utility này. Đây chủ yếu là công cụ quan sát cấu hình hạ tầng và kiểm thử.

### 17.1. Bean class có thể là generated class

~~~java
Object bean = applicationContext.getBean(InventoryService.class);

System.out.println(bean.getClass().getName());
~~~

Tên class có thể chứa các dấu hiệu generated proxy như `$$SpringCGLIB$$`, nhưng tên nội bộ không phải một API contract ổn định. Nếu muốn kiểm tra proxy theo cách có ý nghĩa, dùng `AopUtils`.

### 17.2. @Transactional bean chưa chắc hiện trong mỗi test như production

Một test thuần Java:

~~~java
InventoryService service = new InventoryService();
~~~

không tạo Spring AOP proxy. Một unit test như vậy kiểm tra logic class, không kiểm tra advice.

Muốn xác nhận AOP thực sự hoạt động, cần context có advisor/AOP infrastructure phù hợp. Tùy mục tiêu, dùng context test tối giản hoặc `@SpringBootTest`.

### 17.3. Không cast JDK proxy sang implementation

Sai trong cấu hình JDK proxy:

~~~java
DefaultPaymentService service =
        (DefaultPaymentService) context.getBean(PaymentService.class);
~~~

Nếu bean là JDK proxy implement `PaymentService`, nó có thể không là instance của `DefaultPaymentService`. Hãy sử dụng interface:

~~~java
PaymentService service = context.getBean(PaymentService.class);
~~~

Nếu thật sự cần injection bằng concrete class, kiểm tra class-based proxy configuration; nhưng đừng thay thiết kế dependency chỉ để hỗ trợ một cast trong code nghiệp vụ.

## 18. Kiểm thử một aspect bằng Spring context nhỏ

Có thể dùng `AnnotationConfigApplicationContext` để bật AOP tường minh và kiểm tra lời gọi thực sự đi qua proxy. Ví dụ dưới đây sử dụng các class trong cùng package test để làm rõ cơ chế.

### 18.1. Bean cần được intercept

~~~java
package com.example.aoptest;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    @Tracked
    public String greet(String name) {
        return "Hello " + name;
    }
}
~~~

Annotation:

~~~java
package com.example.aoptest;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Tracked {}
~~~

### 18.2. Aspect ghi số lần gọi

~~~java
package com.example.aoptest;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class CountingAspect {

    private final AtomicInteger count = new AtomicInteger();

    @Before("@annotation(com.example.aoptest.Tracked)")
    public void increment() {
        count.incrementAndGet();
    }

    public int invocations() {
        return count.get();
    }
}
~~~

### 18.3. Cấu hình context test

~~~java
package com.example.aoptest;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
@Import({
        GreetingService.class,
        CountingAspect.class
})
public class TestAopConfiguration {}
~~~

Ở đây `@EnableAspectJAutoProxy` được khai báo tường minh vì test dùng context Spring Framework tối giản, không phụ thuộc Spring Boot AOP auto-configuration.

### 18.4. JUnit 5 kiểm tra proxy và advice

~~~java
package com.example.aoptest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class GreetingAopTest {

    @Test
    void adviceRunsThroughContainerProxy() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        TestAopConfiguration.class
                )) {

            GreetingService service =
                    context.getBean(GreetingService.class);
            CountingAspect aspect =
                    context.getBean(CountingAspect.class);

            assertTrue(AopUtils.isAopProxy(service));

            assertEquals("Hello Linh", service.greet("Linh"));
            assertEquals(1, aspect.invocations());
        }
    }
}
~~~

Test này chứng minh:

1. `GreetingService` là Spring-managed bean.
2. Context đã bật AOP và nhận diện aspect.
3. Bean được expose dưới dạng proxy.
4. Lời gọi `greet` qua proxy làm advice chạy.

Nó cũng minh họa điểm khác với unit test tạo `new GreetingService()`: object tạo trực tiếp không có proxy của Spring.

### 18.5. Kiểm tra self-invocation

Bạn có thể thêm vào `GreetingService`:

~~~java
public String greetTwice(String name) {
    return greet(name) + " and " + greet(name);
}
~~~

Nếu chỉ `greet` được đánh dấu `@Tracked` và caller gọi `service.greetTwice("Linh")`, hai lời gọi `greet` phát sinh **bên trong target**, không đi qua proxy, nên counter không tăng vì annotation của `greet` theo đường self-invocation.

Nếu caller gọi trực tiếp `service.greet("Linh")` hai lần qua proxy, counter tăng hai lần. Đây là bài test ngắn nhưng hiệu quả để hiểu giới hạn của proxy.

## 19. Vì sao aspect “không chạy” trong ứng dụng thực tế?

Khi một method có annotation nhưng không thấy advice, hãy điều tra theo thứ tự từ bên ngoài vào trong.

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Không thấy proxy | AOP infrastructure/aspect chưa được đăng ký hoặc không có advisor match | Kiểm tra dependency, auto-config, component scan, pointcut |
| Aspect có `@Aspect` nhưng không chạy | Aspect không phải Spring bean | Đăng ký `@Component` hoặc `@Bean` |
| Method gọi từ controller chạy advice, gọi nội bộ không chạy | Self-invocation | Tách sang bean khác và inject qua constructor |
| Annotation trên private method không có hiệu lực | Private method không thể intercepted bằng proxy | Đặt concern ở public boundary |
| CGLIB proxy không advice final method | Không thể override final method | Thiết kế lại method/class hoặc dùng interface proxy nếu phù hợp |
| Final class gặp lỗi proxy | CGLIB không thể subclass class final | Kiểm tra proxy strategy và thiết kế class |
| Chạy bằng `new` không có advice | Không qua container | Dùng Spring-managed bean |
| Advice không chạy trong `@PostConstruct` | Internal call khi bean chưa sẵn sàng qua proxy | Dùng caller bean/runner sau refresh |
| Bean interface inject được, concrete class không | JDK proxy chỉ implement interface | Inject bằng interface hoặc xem class-based proxy |
| Advice chạy nhưng không đo được reactive duration | Đo thời gian tạo `Mono` thay vì completion | Instrument publisher completion |
| Thứ tự advice khác mong đợi | Advisor precedence/order | Kiểm tra `@Order` và advisor ordering |
| `@Async` không thực sự async | Chưa bật async support hoặc lời gọi bypass proxy | Kiểm tra `@EnableAsync` và đường gọi |
| `@Transactional` không rollback như kỳ vọng | Bypass proxy, exception semantics hoặc transaction manager | Xác định transaction boundary thật |
| Test không thấy aspect | Test chỉ tạo target hoặc dùng context không có AOP config | Dùng context có advisor/auto-configuration |

### 19.1. Cách chẩn đoán theo sáu câu hỏi

1. **Đây có phải Spring bean?** Kiểm tra nó được tạo bằng container, không phải `new`.
2. **Aspect/advisor có được đăng ký?** Kiểm tra starter AOP, `@Aspect`, `@Component` và vùng scan.
3. **Bean có thực sự là proxy?** Dùng `AopUtils.isAopProxy(...)`.
4. **Pointcut có khớp method?** Kiểm tra package, signature, annotation và visibility.
5. **Caller có đi qua proxy?** Kiểm tra self-invocation, constructor và `@PostConstruct`.
6. **Proxy strategy có tương thích?** Kiểm tra interface, final class/method và kiểu injection.

Sau đó mới xem exception behavior, ordering, transaction manager hoặc async executor cụ thể. Tránh sửa ngẫu nhiên `@Order` hoặc `proxyTargetClass` khi chưa biết lời gọi có đi qua proxy hay không.

### 19.2. Xem log hạ tầng khi cần

Trong môi trường phát triển, có thể bật mức log phù hợp cho các package Spring AOP và auto-configuration để quan sát việc tạo proxy/đăng ký advisor.

~~~yaml
logging:
  level:
    org.springframework.aop: DEBUG
~~~

Mức log và thông tin cụ thể phụ thuộc phiên bản Spring. Không nên dựa vào một chuỗi log nội bộ cố định làm contract test, và không để mức DEBUG quá rộng trong production nếu tạo nhiều log.

## 20. Proxy AOP và boundary trong thiết kế ứng dụng

Spring AOP có tính hiệu quả cao khi áp vào một ranh giới có ý nghĩa nghiệp vụ:

~~~text
HTTP Controller
       |
       v
Application Service proxy   <-- transaction / metric / authorization advice
       |
       v
Application Service target
       |
       v
Repository / Gateway
~~~

Một kiến trúc thường có:

- Controller xử lý request, validation đầu vào và giao thức HTTP.
- Application service định nghĩa operation boundary.
- Repository hoặc gateway làm việc với database/hệ thống ngoài.
- Aspect/advisor xử lý logic cắt ngang tại operation boundary thích hợp.

### 20.1. Không biến mọi method thành advice point

Nếu aspect intercept tất cả getter, setter, utility method và mapper, hệ thống có thể khó debug và tăng overhead không cần thiết.

Hãy chọn điểm cắt có ý nghĩa như:

- Public method của application service.
- Method mang annotation được thiết kế riêng.
- Các operation có contract transaction/cache/authorization rõ ràng.

Đừng dựa vào AOP để che giấu dependency hoặc thay thế thiết kế component.

### 20.2. Đừng dùng AOP thay mọi control flow

AOP phù hợp với logic xuyên suốt nhiều nơi và có thể được diễn đạt bằng một rule nhất quán. Với quy tắc nghiệp vụ cần branch, quyết định domain state hoặc phối hợp nhiều tác vụ, code service tường minh thường dễ hiểu hơn aspect.

Ví dụ kiểm tra “đơn hàng có thể giao hay không” là business rule nên nằm trong domain/application logic; đo elapsed time của các lời gọi service là cross-cutting concern thích hợp để trừu tượng hóa qua AOP.

### 20.3. Tránh điểm cắt quá rộng ảnh hưởng performance

Mỗi lời gọi qua proxy và advice chain có chi phí. Thường đây không phải bottleneck lớn so với database/network call, nhưng pointcut áp cho hàng triệu lời gọi nhỏ có thể tạo overhead đáng kể.

Nếu muốn đo hiệu năng, hãy đo và lựa chọn metric đúng mức. Không nhất thiết gắn aspect vào từng method nội bộ của object.

### 20.4. AOP không thay thế bảo mật ở mọi tầng

Một method security advisor bảo vệ method được gọi qua proxy và đúng security infrastructure. Nhưng nó không tự thay thế filter chain, input validation hoặc bảo vệ các đường truy cập khác.

Khi bảo mật phụ thuộc proxy, cần xác định ranh giới được gọi từ đâu và liệu có đường đi nội bộ vượt qua interception hay không. Tốt hơn là tổ chức security boundaries rõ ràng, kiểm thử với context thật và tránh phụ thuộc vào side effect ngầm.

## 21. Phân biệt AOP proxy với các loại proxy khác trong Spring

Không phải object có chữ “proxy” đều là Spring AOP proxy với cùng semantics.

### 21.1. Scoped proxy

Ví dụ inject request-scoped bean vào singleton. Spring có thể dùng một proxy để trì hoãn việc xác định target theo request hiện tại. Đây là một proxy có mục tiêu **quản lý scope**, không nhất thiết là aspect logging/transaction.

Scoped proxy và AOP advisor có thể phối hợp, nhưng cần xem chúng như các tầng abstraction khác nhau.

### 21.2. @Configuration class enhancement

`@Configuration(proxyBeanMethods = true)` có thể dùng class enhancement để giữ semantics khi một `@Bean` method gọi một `@Bean` method khác bên trong configuration class.

Cơ chế này có thể dùng subclassing, nhưng không nên nhầm nó với Spring AOP aspect proxy. `proxyBeanMethods` điều khiển semantics của Java configuration, không phải công tắc bật/tắt `@Aspect` cho service.

### 21.3. HTTP client proxy hoặc repository proxy

Spring Data repository có thể được tạo bằng proxy thực thi API repository; HTTP declarative client có thể expose proxy interface gọi remote API. Chúng không nhất thiết là cùng loại proxy được tạo bởi `AnnotationAwareAspectJAutoProxyCreator`.

Khi debug, hãy xác định **proxy được dùng để làm gì**, đừng chỉ nhìn tên class generated rồi kết luận đó là AspectJ-style AOP.

## 22. Các câu hỏi kiểm tra hiểu bản chất

### Câu hỏi 1: Có @Aspect nhưng chưa có spring-boot-starter-aop

Một class có `@Aspect` và `@Component` đã bảo đảm advice chạy chưa?

**Chưa chắc.** Cần AOP infrastructure và các dependency phù hợp để Spring nhận diện aspect và tạo advisors/proxies. Một số tính năng khác có thể kéo AOP support vào classpath, nhưng không nên dựa vào tác dụng bắc cầu không rõ ràng.

### Câu hỏi 2: Method có @Transactional nhưng gọi từ cùng class

Transaction interceptor có chạy không?

Trong proxy mode, lời gọi nội bộ không đi qua proxy nên annotation của method được gọi **không được áp dụng qua lời gọi đó**. Nếu đã có transaction từ operation ngoài, code có thể đang nằm trong transaction ấy; cần phân biệt transaction có sẵn với advice mới được kích hoạt.

### Câu hỏi 3: Service không có interface

Có thể được AOP proxy không?

Có. Spring có thể dùng class-based proxy với CGLIB, nếu class/method có thể được subclass/override và hạ tầng được cấu hình phù hợp.

### Câu hỏi 4: Method là final

Có thể bị advice không?

Với CGLIB class-based proxy, method final không thể bị override nên không thể intercept theo cơ chế đó. Với JDK interface proxy, invocation của method được expose qua interface có thể đi qua proxy; cần xét proxy strategy thực tế.

### Câu hỏi 5: Method trả Mono

@Around đo elapsed time có đo được toàn bộ request reactive không?

Không nhất thiết. Advice đo thời gian gọi method có thể kết thúc khi `Mono` được trả về, trước khi pipeline thực thi và hoàn tất. Muốn đo completion cần instrument publisher lifecycle thích hợp.

### Câu hỏi 6: @Order có thay thế @DependsOn không?

Không. `@Order` trên aspect điều chỉnh precedence advice; `@DependsOn` liên quan tới quan hệ khởi tạo/hủy giữa các bean.

### Câu hỏi 7: new Service() có chạy advice không?

Không tự động. Object tạo bằng `new` không phải Spring AOP proxy. Nếu cần logic AOP, hãy dùng bean được container expose hoặc cân nhắc một kiến trúc khác.

## 23. Bài tập thực hành

### Bài tập 1 — Tạo aspect đo thời gian

Tạo `@TimedOperation` và một `@Aspect` dùng `@Around` để ghi elapsed time. Gắn annotation lên hai public method của một service. Gọi chúng từ controller/runner qua Spring-injected bean và quan sát advice.

### Bài tập 2 — Quan sát proxy strategy

Tạo một service có interface và một service không có interface. Dùng `AopUtils.isAopProxy`, `isJdkDynamicProxy` và `isCglibProxy` để quan sát. Thử `spring.aop.proxy-target-class=false` rồi so sánh kiểu runtime, khả năng injection theo interface/concrete class.

### Bài tập 3 — Tái hiện self-invocation

Trong cùng một service, viết `outer()` gọi `inner()`. Chỉ đánh dấu `inner()` bằng annotation pointcut. Gọi `outer()` qua proxy và so sánh với gọi `inner()` trực tiếp qua proxy.

### Bài tập 4 — Refactor sang hai bean

Chuyển `inner()` sang `InnerService` độc lập, inject vào `OuterService` qua constructor. Chứng minh lời gọi từ outer qua injected inner service kích hoạt advice.

### Bài tập 5 — Final và private method

Tạo một class có final method và một private method mang annotation AOP. Thử class-based proxy và giải thích vì sao chúng không được intercept như public, non-final method.

### Bài tập 6 — Advice ordering

Tạo hai aspect với `@Order(5)` và `@Order(10)`; mỗi aspect có `@Around` ghi log “enter” và “exit”. Gọi một service method và ghi lại thứ tự log theo cách lồng nhau.

### Bài tập 7 — Chặn lời gọi bằng @Around

Tạo một around advice có điều kiện không gọi `proceed()` cho một method thử nghiệm. Quan sát method target không chạy và giá trị caller nhận được. Giải thích rủi ro nếu lạm dụng pattern này cho transaction hoặc nghiệp vụ.

### Bài tập 8 — Kiểm thử bằng context thật

Dùng `AnnotationConfigApplicationContext` và `@EnableAspectJAutoProxy` để đăng ký bean/aspect. Kiểm tra bean là proxy và một counter tăng khi gọi qua container. So sánh với `new` object.

### Bài tập 9 — Spring transaction boundary

Tạo một application service với method `@Transactional` được gọi nội bộ. Dùng test có transaction manager thực hoặc mock phù hợp để quan sát. Tách method sang bean độc lập và giải thích thay đổi ở boundary.

### Bài tập 10 — Reactive timing

Tạo method trả `Mono.delay(...)` rồi map thành kết quả. Đo bằng around advice đơn giản và so sánh với metric đo tới lúc publisher hoàn tất. Giải thích vì sao không thể coi thời gian tạo `Mono` là thời gian xử lý toàn bộ pipeline.

## 24. Ghi nhớ

**Spring AOP trong ứng dụng Spring Boot thông thường dựa trên proxy do container tạo và expose cho consumer.** Proxy nhận lời gọi từ bên ngoài, áp dụng interceptor/advice phù hợp rồi gọi target. Nó không tự weave mọi class của JVM và không intercept những object được tạo ngoài container.

Hai proxy strategy chính là **JDK dynamic proxy** cho interface-based invocation và **CGLIB** cho class-based proxy. Spring Boot thường ưu tiên class-based proxy theo cấu hình mặc định, nhưng proxy strategy có thể thay đổi. CGLIB không thể override final/private method hoặc subclass final class; JDK proxy không mặc nhiên tương thích với injection bằng implementation class.

Giới hạn quan trọng nhất là **self-invocation**: một method target gọi method khác của chính nó thì không đi lại qua proxy. Vì vậy `@Transactional`, `@Cacheable`, `@Async` hoặc custom `@Aspect` có thể không có tác dụng ở đường gọi nội bộ. Thiết kế dễ hiểu nhất là đặt operation boundary ở public method của một bean riêng và gọi qua dependency được Spring inject.

Khi advice không chạy, hãy kiểm tra theo thứ tự: bean có được Spring quản lý không, AOP infrastructure có được bật không, pointcut có khớp không, bean có là proxy không, lời gọi có đi qua proxy không, và proxy strategy có tương thích với method không. Hiểu những điều này giúp dùng AOP để tách mối quan tâm xuyên suốt một cách có kiểm soát, thay vì dựa vào annotation như một “phép màu” không thấy được ranh giới.
