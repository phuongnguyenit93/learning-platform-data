# Lời gọi từ bean khác đi qua proxy và lời gọi trực tiếp vào đối tượng đích

## 1. Vấn đề thực tế: cùng một method nhưng advice có lúc chạy, có lúc không

Trong Spring AOP, việc một method được viết bên trong **Spring bean** hoặc khớp biểu thức **pointcut** chưa đủ để bảo đảm advice sẽ chạy. Điều quyết định còn là **tham chiếu được dùng để thực hiện lời gọi**:

- Caller đang gọi một **Spring AOP proxy** do container cung cấp hay đang gọi **đối tượng target gốc**?
- Nếu caller là **một Spring bean khác**, dependency nó nhận được có phải proxy hay không?
- Nếu target gọi method của chính mình qua `this`, lời gọi có đi ngược ra proxy hay không?
- Nếu code tự tạo object bằng `new`, object đó có từng được Spring AOP auto-proxy creator xử lý hay không?

Một ví dụ điển hình:

```text
ClientBean  --------> OrderService proxy  --------> OrderService target
                       |                              |
                       +-- @Before/@Around advice     +-- business code

ClientBean  --------> raw OrderService target
                       (đi trực tiếp, không qua proxy)
```

Hai lời gọi có thể chạy **cùng code nghiệp vụ trên cùng target instance**, nhưng chỉ đường đi qua proxy mới cho Spring AOP cơ hội thực hiện advice.

**Mấu chốt:** *Spring AOP là proxy-based AOP*. Lời gọi không đi qua proxy thường không kích hoạt advice dù method được chọn bởi pointcut. Bài này tập trung vào **Spring Aspect và Spring-managed bean**, không mở rộng sang lý thuyết AOP chung hoặc AspectJ weaving độc lập.

## 2. Phân biệt caller, proxy và raw target

| Thành phần | Ý nghĩa trong Spring AOP | Điều cần kiểm chứng |
| --- | --- | --- |
| **Calling bean** | Một Spring bean gọi method trên dependency đã inject. | Dependency có thực sự là proxy Spring AOP không? |
| **Spring AOP proxy** | Object trung gian Spring trao cho caller khi bean cần advisor. | `AopUtils.isAopProxy(bean)` có `true` không? |
| **Target (raw object)** | Object chứa method nghiệp vụ thực tế. | Có bị gọi trực tiếp, bỏ qua proxy không? |
| **Aspect bean** | Spring bean khai báo `@Aspect`, có advice/pointcut. | Có đăng ký và được auto-proxy infrastructure nhận diện không? |
| **Advisor/interceptor chain** | Logic mà proxy áp dụng cho method khớp. | Có advice thực thi đúng số lần và thứ tự không? |
| **`this` trong target** | Reference bên trong chính target instance. | Có phải self-invocation bypass proxy không? |

Nếu gọi `clientBean.send()`, method `send()` của client **không cần tự được advice**. Nó có thể gọi dependency `orderService.submit()`, và chính lời gọi thứ hai mới đi qua Spring proxy.

Ngược lại, việc một class được đánh dấu `@Service` **không biến mọi tham chiếu đến instance của class đó thành proxy**. Spring chỉ có thể kiểm soát các instance/reference mà container đã tạo hoặc trả về theo cơ chế của nó.

### 2.1. Ba luồng gọi cơ bản

**Luồng A — từ bean khác qua dependency Spring đã inject:**

```text
CallerBean
   |
   | this.orderService.submit("A")  // field chứa Spring AOP proxy
   v
OrderService proxy
   |
   +-- Advice @Before / @Around nếu pointcut khớp
   |
   v
Raw target.submit("A")
```

**Luồng B — caller có sẵn tham chiếu raw target:**

```text
Caller / test / code giữ raw object
   |
   | rawTarget.submit("B")
   v
Raw target.submit("B")
   |
   +-- Không có Spring AOP proxy trên đường gọi
```

**Luồng C — self-invocation trong target:**

```text
Caller -> proxy -> rawTarget.outer()
                         |
                         | this.submit("C")
                         v
                    rawTarget.submit("C")
                    (lời gọi nội bộ, bypass proxy)
```

Nếu pointcut chỉ chọn `submit()`, advice chạy với luồng A; không chạy ở B; và **không chạy cho lời gọi `submit()` nội bộ** trong C. Nếu pointcut còn chọn `outer()`, lời gọi vào `outer()` có thể được advice, nhưng điều đó **không có nghĩa** lời gọi `submit()` qua `this` được advice lần thứ hai.

## 3. Vì sao bean khác thường nhận được proxy?

Khi dùng cấu hình Spring AOP chuẩn, chẳng hạn `@EnableAspectJAutoProxy` hoặc Spring Boot AOP auto-configuration phù hợp:

1. `ApplicationContext` đăng ký auto-proxy infrastructure, trong đó có `BeanPostProcessor` chuyên phát hiện advisor/aspect.
2. Spring khởi tạo target bean và xử lý vòng đời.
3. Nếu bean đủ điều kiện áp dụng advisor, Spring có thể tạo **JDK dynamic proxy** hoặc **class-based proxy (CGLIB)**.
4. Khi một bean khác inject dependency ấy bằng kiểu phù hợp, container giải quyết bean reference qua cơ chế quản lý của nó. Caller thường nhận **proxy đã được tạo**, không phải raw target mà proxy bao.
5. Lời gọi method từ caller đi vào proxy; advisor phù hợp được thực hiện trước/sau/quanh method target.

Điều này áp dụng cả khi service được khai báo bằng `@Component`/`@Service` và khi service đến từ `@Bean`, nếu instance được Spring quản lý và đủ điều kiện post-processing.

Ví dụ:

```java
@Service
public class CheckoutService {
    private final OrderOperations orders;

    public CheckoutService(OrderOperations orders) {
        this.orders = orders; // Spring inject bean reference (có thể là AOP proxy).
    }

    public void checkout(String id) {
        orders.submit(id); // Qua proxy nếu dependency là Spring AOP proxy.
    }
}
```

Đây là **đoạn code minh họa**, giả định đã khai báo interface `OrderOperations` và một bean implement nó. Kết luận “có advice” còn phụ thuộc aspect được đăng ký, pointcut khớp `submit()`, loại proxy, scope, và dependency thực sự trỏ đến proxy.

**Không phải cứ gọi từ một Spring bean khác là mặc nhiên chạy advice.** Nếu code trong bean khác tự `new OrderService()`, cố tình lấy raw target, hoặc inject bean thuộc context không có auto-proxy tương ứng, lời gọi đó vẫn có thể bypass AOP.

## 4. Thế nào là “gọi trực tiếp vào đối tượng đích”?

Một lời gọi trực tiếp là lời gọi trên **reference đến chính target**, không phải reference đến Spring AOP proxy. Ví dụ:

```java
OrderService raw = new OrderService();
raw.submit("X");
```

Đây là fragment, không phải project độc lập. `raw` ở ví dụ được tạo bằng `new` nên Spring container chưa quản lý và không thể tự áp dụng các advisor Spring AOP lên nó.

Một biến thể quan trọng hơn để debug là **cùng một raw target mà Spring đã proxy**, nhưng code vẫn giữ một reference trực tiếp đến raw instance. Khi đó:

```text
proxy.submit("X")  -> advice -> target.submit("X")
raw.submit("Y")    ------------> target.submit("Y")
```

Cùng target, cùng method, khác đường đi. Vì thế, nếu thấy nghiệp vụ vẫn chạy nhưng audit/logging/transaction advice không xuất hiện, cần kiểm tra **reference của caller** trước khi nghi ngờ pointcut.

Trong production, **không nên cố tình để lộ raw target của singleton bean** nhằm tránh AOP: điều đó phá vỡ khả năng áp dụng chính sách chung nhất quán. Ví dụ chạy ở phần sau cố ý giữ reference raw chỉ để chứng minh cơ chế Spring AOP.

## 5. Ví dụ runnable Java 17+: cùng một target, năm đường gọi

Ví dụ được thiết kế để phân biệt chính xác:

1. Bean `CheckoutFacade` gọi `OrderService` **thông qua proxy được Spring inject**.
2. Code gọi trực tiếp `proxy.submit()`.
3. Code gọi `proxy.submitViaThis()` rồi method target tự gọi `this.submit()`.
4. Code gọi `rawTarget.submit()` trên **cùng target instance đang được proxy**.
5. Code gọi method trên một instance **ngoài Spring container** bằng `new`.

Aspect chỉ advice method `OrderService.submit(..)`; chỉ hai đường đầu chạy advice.

### 5.1. Cấu trúc thư mục

```text
spring-aop-call-boundary/
├── pom.xml
└── src/main/java/com/example/boundary/
    ├── AppConfig.java
    ├── OrderService.java
    ├── CheckoutFacade.java
    ├── RawTargetHolder.java
    ├── AuditAspect.java
    └── DemoApp.java
```

### 5.2. `pom.xml`

Ví dụ dùng **Spring Framework 6.1.14**, `aspectjweaver 1.9.22.1`, JDK 17+ và Maven. Đây là bộ phiên bản **cố định để học**, không phải khẳng định các phiên bản mới nhất.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-call-boundary</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp container và kéo Spring AOP trong dependency graph của bộ bản mẫu; `aspectjweaver` cần cho kiểu khai báo `@AspectJ`. Không cần AspectJ compile-time/load-time weaving để chạy ví dụ này.

### 5.3. `src/main/java/com/example/boundary/OrderService.java`

```java
package com.example.boundary;

public class OrderService {

    public void submit(String id) {
        System.out.println("[TARGET] submit " + id);
    }

    public void submitViaThis(String id) {
        this.submit(id);
    }
}
```

`submitViaThis()` gọi `submit()` trên `this` của **raw target**. Nếu được gọi qua proxy, lời gọi vào `submitViaThis()` đến target, nhưng bước gọi tiếp `this.submit()` không quay ngược lại proxy.

### 5.4. `src/main/java/com/example/boundary/CheckoutFacade.java`

```java
package com.example.boundary;

public class CheckoutFacade {
    private final OrderService orders;

    public CheckoutFacade(OrderService orders) {
        this.orders = orders;
    }

    public void checkout(String id) {
        orders.submit(id);
    }

    public OrderService injectedReference() {
        return orders;
    }
}
```

`CheckoutFacade` đóng vai caller bean được container khởi tạo. `OrderService` được constructor-injected; ở cấu hình có aspect và proxy, tham chiếu `orders` là Spring AOP proxy.

### 5.5. `src/main/java/com/example/boundary/RawTargetHolder.java`

```java
package com.example.boundary;

public class RawTargetHolder {
    private OrderService raw;

    public void remember(OrderService target) {
        this.raw = target;
    }

    public OrderService raw() {
        return raw;
    }
}
```

Class này cố ý giữ **raw target reference** trước khi Spring hoàn tất việc cung cấp AOP proxy. Đây là **kỹ thuật thí nghiệm**, không nên dùng trong kiến trúc nghiệp vụ vì dễ bỏ qua audit, transaction hoặc policies khác.

### 5.6. `src/main/java/com/example/boundary/AuditAspect.java`

```java
package com.example.boundary;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(public void com.example.boundary.OrderService.submit(..))")
    public void beforeSubmit(JoinPoint joinPoint) {
        calls.incrementAndGet();
        Object id = joinPoint.getArgs()[0];
        System.out.println("[AOP] before submit " + id);
    }

    public int calls() {
        return calls.get();
    }
}
```

Pointcut cố tình chọn **một method duy nhất**: `OrderService.submit(..)`. Nó không chọn `submitViaThis()` hoặc `CheckoutFacade.checkout()`. Điều này giúp phân biệt advice có hoặc không **do đường gọi**, thay vì do có nhiều method vô tình khớp.

`AtomicInteger` dùng để đếm số lần advice thực sự được gọi; kết quả không dựa vào parsing log.

### 5.7. `src/main/java/com/example/boundary/AppConfig.java`

```java
package com.example.boundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public RawTargetHolder rawTargetHolder() {
        return new RawTargetHolder();
    }

    @Bean
    public OrderService orderService(RawTargetHolder holder) {
        OrderService target = new OrderService();
        holder.remember(target); // Chỉ để đối chiếu raw target với proxy.
        return target;
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public CheckoutFacade checkoutFacade(OrderService orderService) {
        return new CheckoutFacade(orderService);
    }
}
```

`@EnableAspectJAutoProxy(proxyTargetClass = true)` dùng **class-based proxy** để `CheckoutFacade` inject `OrderService` theo concrete type thuận tiện cho demo. Trong ứng dụng interface-based, Spring có thể dùng JDK proxy; nguyên tắc **caller đi qua proxy** vẫn không đổi.

Khi `orderService()` tạo target và lưu vào `RawTargetHolder`, Spring còn phải thực hiện các bước post-processing để bọc proxy trước khi một consumer khác inject bean `orderService`. Vì thế, cùng object `target` ban đầu có thể được truy cập qua hai con đường: raw reference và Spring proxy reference.

### 5.8. `src/main/java/com/example/boundary/DemoApp.java`

```java
package com.example.boundary;

import org.springframework.aop.framework.Advised;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService proxy = context.getBean(OrderService.class);
            RawTargetHolder holder = context.getBean(RawTargetHolder.class);
            OrderService raw = holder.raw();
            CheckoutFacade facade = context.getBean(CheckoutFacade.class);
            AuditAspect aspect = context.getBean(AuditAspect.class);

            System.out.println("proxyIsAop=" + AopUtils.isAopProxy(proxy));
            System.out.println("rawIsAop=" + AopUtils.isAopProxy(raw));
            System.out.println("facadeHasProxy="
                    + (facade.injectedReference() == proxy));
            System.out.println("sameReference=" + (proxy == raw));
            System.out.println("sameTarget="
                    + (((Advised) proxy).getTargetSource().getTarget() == raw));

            System.out.println("-- from another bean --");
            facade.checkout("A");

            System.out.println("-- external through proxy --");
            proxy.submit("B");

            System.out.println("-- self-invocation via target.this --");
            proxy.submitViaThis("C");

            System.out.println("-- direct raw target --");
            raw.submit("D");

            System.out.println("-- outside Spring container --");
            new OrderService().submit("E");

            System.out.println("adviceCalls=" + aspect.calls());
        }
    }
}
```

`Advised.getTargetSource().getTarget()` là **kiểm tra thí nghiệm** để xác minh proxy của bean singleton đang trỏ tới đúng raw target trong `RawTargetHolder`. Đừng làm vậy trong business code để lách chính sách AOP. Với `TargetSource` tùy chỉnh hoặc target theo scope, việc unwrap/nhận một target ổn định có thể không hợp lệ.

### 5.9. Chạy và kết quả dự kiến

Yêu cầu JDK 17+, Maven và kết nối để tải dependency. Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.boundary.DemoApp
```

Các dòng do code `DemoApp` và aspect in ra, theo thứ tự (không tính log Maven/Spring nếu có):

```text
proxyIsAop=true
rawIsAop=false
facadeHasProxy=true
sameReference=false
sameTarget=true
-- from another bean --
[AOP] before submit A
[TARGET] submit A
-- external through proxy --
[AOP] before submit B
[TARGET] submit B
-- self-invocation via target.this --
[TARGET] submit C
-- direct raw target --
[TARGET] submit D
-- outside Spring container --
[TARGET] submit E
adviceCalls=2
```

**Giải thích từng nhóm đầu ra:**

1. `proxyIsAop=true` nhưng `rawIsAop=false`: cùng nghiệp vụ có **một reference Spring AOP proxy** và **một reference raw target** khác nhau.
2. `facadeHasProxy=true`: Spring đã inject đúng tham chiếu proxy vào caller `CheckoutFacade`.
3. `sameTarget=true`: trong demo singleton này, proxy thực sự bao target object đang giữ trong `RawTargetHolder`. Đây là bằng chứng rằng sự khác biệt advice **không đến từ việc thay service instance**.
4. Lời gọi từ `CheckoutFacade` và lời gọi trực tiếp trên biến `proxy` đều đi qua proxy và khớp pointcut `submit(..)`, nên có hai dòng `[AOP]`.
5. `proxy.submitViaThis("C")` đi vào `submitViaThis`, sau đó `this.submit("C")` gọi ngay trên target; pointcut chọn `submit`, nhưng lời gọi nội bộ không quay về proxy, vì vậy không có dòng `[AOP]`.
6. Lời gọi trên `raw` và instance từ `new` đều không đi qua proxy; chúng chỉ in `[TARGET]`. Counter cuối là `2`, không phải `5`.

Thí nghiệm thể hiện **điểm chặn nằm ở reference/đường gọi**, không phải thuộc tính cố định của method `submit` trong source code.

## 6. Ma trận hành vi: phương thức khớp pointcut chưa đủ

Giả sử chỉ có `@Before` cho `OrderService.submit(..)`:

| Cách gọi | Reference tại thời điểm gọi | Có `@Before` cho `submit`? | Lý do |
| --- | --- | --- | --- |
| `facade.checkout("A")` gọi `orders.submit("A")` | `orders` là proxy do Spring inject | **Có** | Lời gọi cross-bean đi vào Spring proxy. |
| `context.getBean(OrderService.class).submit("B")` | Bean reference là proxy | **Có** | Caller dùng Spring proxy trực tiếp. |
| `proxy.submitViaThis("C")` → `this.submit("C")` | Internal reference là raw target `this` | **Không** cho lời gọi `submit` nội bộ | Self-invocation bypass proxy. |
| `raw.submit("D")` | Raw target reference | **Không** | Không có proxy trên đường gọi. |
| `new OrderService().submit("E")` | Object tự tạo ngoài container | **Không** | Spring chưa quản lý hay auto-proxy object. |
| `@PostConstruct` trong target gọi `this.submit(...)` | Raw target trong init callback | **Không** theo proxy AOP thông thường | Callback khởi tạo xảy ra trước khi proxy bình thường sẵn sàng; lại là lời gọi nội bộ. |
| Bean khác inject interface của service rồi gọi method qua JDK proxy | Interface proxy | **Có** nếu pointcut khớp và method có thể gọi qua interface | Proxy style khác, ranh giới interception vẫn vậy. |

Trong hệ thống thực tế, một lời gọi có thể có **nhiều advisors** và một method khác cũng được advice. Bảng chỉ đếm riêng advice `@Before` trên `submit` như giả thiết, tránh nhầm “không có advice `submit`” với “không có advisor nào hoạt động”.

## 7. Phân biệt “gọi từ bean khác” với “cross-bean thật sự qua proxy”

### 7.1. Caller bean thuộc Spring nhưng tự `new` target

```java
public class CheckoutFacade {
    public void checkout() {
        OrderService service = new OrderService();
        service.submit("X");
    }
}
```

Dù `CheckoutFacade` được đăng ký thành Spring bean, biến `service` trong method này là object **tự tạo**. Không có bean lookup, injection hay proxy Spring AOP. Aspect dành cho `OrderService.submit` không chạy trong lời gọi đó.

**Cách làm đúng:** inject service đã được Spring quản lý qua constructor hoặc truy cập container theo thiết kế được kiểm soát; tránh tự `new` một service cần transaction, audit, caching hoặc authorization advice.

### 7.2. Caller giữ tham chiếu cũ tới raw target

Có thể xảy ra khi code tự tạo object rồi đem object ấy đăng ký vào `BeanFactory`, hoặc một factory/registry chia sẻ raw reference ra ngoài trước khi Spring tạo proxy. Khi đó dù target cũng được Spring quản lý, caller cũ vẫn gọi trên **reference đã giữ**, không tự biến thành proxy sau khi auto-proxy creator chạy.

```text
rawRef = target;              // Giữ object gốc.
springBean = getBean(...);    // Spring có thể trả proxy quanh target.
rawRef.submit();              // Bypass.
springBean.submit();          // Qua proxy nếu advisor khớp.
```

Đây là mô hình chẩn đoán, **không phải khuyến nghị trữ raw target**. Luôn cố gắng thống nhất một đường nhận dependency từ Spring container để tránh chính sách dùng chung chạy lúc có lúc không.

### 7.3. Caller lấy bean thuộc context khác

Một ứng dụng có thể có **parent và child `ApplicationContext`**, hoặc nhiều context độc lập. Auto-proxy configuration là cục bộ cho context tương ứng, nên một bean ngoài context đang bật `@EnableAspectJAutoProxy` có thể không được auto-proxy giống bean trong context đó.

Lời gọi từ bean khác không chứng minh “cùng context” hay “cùng hạ tầng AOP”. Khi debug, xác định rõ context nào sở hữu target và aspect, nơi `@Bean`/`@ComponentScan` đăng ký và cách dependency được resolve.

## 8. Self-invocation: lời gọi không quay lại proxy

Trong demo mục 5, `proxy.submitViaThis("C")` đi vào target, nhưng lệnh `this.submit("C")` bên trong target không quay ra Spring proxy. Do đó advice chỉ nhắm `submit(..)` không chạy ở lượt gọi nội bộ, dù `submit` là public và pointcut khớp. Nếu advisor còn nhắm `submitViaThis`, method ngoài có thể được advice nhưng điều đó không làm `submit` được intercept thêm lần nữa.

Đổi JDK proxy sang CGLIB không khắc phục self-invocation. Khi policy thật sự cần áp dụng cho method được gọi bên trong, nên cân nhắc **đặt boundary ở method ngoài** nếu policy thuộc toàn operation, hoặc **chuyển trách nhiệm sang một Spring collaborator bean** rồi gọi qua dependency được inject. Self-injection có thể liên quan circular dependencies, lifecycle và kiểu proxy; `AopContext.currentProxy()` cần `exposeProxy=true` cùng một AOP invocation đang hoạt động nên chỉ phù hợp ngoại lệ. Các bài tiếp theo phân tích và kiểm chứng riêng từng lựa chọn.

## 9. Ranh giới khởi tạo: bean chưa trao proxy hoàn chỉnh cho caller

Constructor, `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và custom init method của chính target thường chạy **trước khi bean được công bố qua AOP proxy hoàn chỉnh**. Nếu callback gọi `this.submit("INIT")`, đó còn là self-invocation; lời gọi tới `submit` không được advice nhờ Spring AOP proxy. Vì thế chỉ nhìn annotation trên method không đủ để suy ra transaction, audit hay cache interceptor đã chạy.

Một callback trên **bean khác** có thể gọi qua proxy của dependency đã khởi tạo hoàn chỉnh; không nên gộp mọi callback vào cùng kết luận “luôn bypass”. Đối với startup work cần interception, hãy dùng một coordinator khác gọi service qua dependency đã được Spring quản lý ở thời điểm phù hợp, chẳng hạn `ApplicationRunner` trong Spring Boot. Bài riêng về lifecycle giải thích kỹ các mốc và ngoại lệ.

## 10. Ảnh hưởng của JDK proxy và CGLIB tới cross-bean invocation

Nguyên tắc **phải đi qua proxy** áp dụng cho cả hai cơ chế, nhưng kiểu tham chiếu mà bean khác có thể inject/call khác nhau.

| Khía cạnh | JDK dynamic proxy | Class-based (CGLIB) proxy |
| --- | --- | --- |
| Kiểu proxy | Triển khai interface phù hợp | Subclass của target class |
| Inject thường phù hợp | Theo **business interface** | Theo interface hoặc concrete class khi proxy hợp lệ |
| Method có thể gọi qua proxy | Những method thuộc proxied interfaces | Những method mà subclass proxy có thể expose/override theo giới hạn Spring |
| Lời gọi `this.method()` từ target | Bypass proxy | Bypass proxy |
| Caller dùng `new Target()` | Không có Spring AOP proxy | Không có Spring AOP proxy |
| Raw target reference được giữ ngoài proxy | Bypass | Bypass |
| `final`/private methods | Interface proxy intercept ở ranh giới method interface khi khả dụng; private method nội bộ không là contract interface | Không override được final/private method |
| Kiểm tra tại runtime | `AopUtils.isJdkDynamicProxy(bean)` | `AopUtils.isCglibProxy(bean)` |

Ví dụ một service triển khai `OrderOperations` nhưng caller inject concrete `OrderService` trong khi Spring dùng JDK proxy. Điều này có thể gây lỗi resolve dependency theo concrete class vì JDK proxy **không phải instance của implementation class**. Khi đó nên inject qua business interface, hoặc chủ động chọn class-based proxy nếu có nhu cầu và target có thể subclass.

**Đừng đổi proxy type để che lỗi gọi trực tiếp raw target.** Dù JDK hay CGLIB, nếu tham chiếu không đi qua proxy, advice vẫn không có cơ hội chặn method execution.

## 11. Ranh giới interception khi dùng Spring Boot hoặc Spring Framework thuần

### Spring Framework thuần

Thường cần các thư viện Spring Context, Spring AOP và AspectJ hỗ trợ `@AspectJ`, đồng thời khai báo:

```java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
```

Kèm theo một bean `@Aspect` được đăng ký bằng `@Bean` hoặc `@Aspect` + `@Component` nằm trong component scan. `@Aspect` **không tự biến class thành component** nếu thiếu cơ chế đăng ký bean phù hợp.

### Spring Boot

Boot có auto-configuration của AOP tùy dòng phiên bản/starter và cấu hình. Ví dụ Boot 3.x sử dụng `spring-boot-starter-aop`; Boot 4.x có `spring-boot-starter-aspectj`. Auto-configuration làm cho việc bật auto-proxy thuận tiện hơn, nhưng **không tự thay đổi ranh giới lời gọi của Spring proxy AOP**.

Ngay cả khi `@Transactional`, `@Cacheable` hoặc `@Async` được cấu hình qua Spring proxy, lời gọi nội bộ/đi thẳng raw target vẫn phải được xem xét theo cơ chế riêng của từng subsystem và proxy của nó. Chỉ từ việc một annotation có mặt trên method chưa đủ khẳng định interceptor sẽ chạy.

## 12. Cách kiểm chứng đường gọi trong ứng dụng đang chạy

### 12.1. Bước 1: xác định bean reference của caller

Khi có quyền truy cập `ApplicationContext` ở test hoặc thời điểm chẩn đoán:

```java
Object service = context.getBean("orderService");
System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(service));
```

Đây là fragment cần biến `context`. Nếu `true`, bean trả về là Spring AOP proxy. Nếu `false`, chưa thể kết luận framework lỗi: có thể pointcut không khớp, bean không phải target cần advice, aspect chưa đăng ký hoặc bạn lấy bean ở context khác.

Trong một test, có thể so sánh bằng `==` giữa dependency mà caller đang giữ và reference Spring trả cho cùng singleton bean. Điều đó giúp phát hiện caller đang giữ raw/old reference. **Không so sánh bằng `equals` để kết luận cùng Java reference**, vì Spring proxy có xử lý equality riêng.

### 12.2. Bước 2: kiểm tra advisor trên proxy, không chỉ có proxy

```java
Object bean = context.getBean("orderService");

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

Đây là fragment chẩn đoán; output không cố định theo Spring version và advisor set. Proxy có thể tồn tại do transaction, scoped proxy hoặc một advisor khác; **có proxy không đồng nghĩa `@Before` của bạn khớp method đang gọi**.

### 12.3. Bước 3: so sánh với lời gọi trực tiếp raw target trong một test cô lập

Nếu bạn thật sự cần chứng minh cơ chế, dùng test/demonstration như `RawTargetHolder` ở phần 5. Không lan truyền raw references trong code sản xuất chỉ để debug. Xác nhận:

- Lời gọi qua dependency Spring inject chạy advice.
- Lời gọi trên raw target vẫn thực hiện nghiệp vụ nhưng không có advice.
- Lời gọi self-invocation chỉ gây advice cho **method bên ngoài** nếu method đó cũng khớp pointcut; method bên trong không tự đi qua proxy.
- Kết quả nghiệp vụ, ngoại lệ và state biến đổi của target đúng như mong đợi.

Nếu lời gọi qua proxy không chạy advice, kiểm tra cả pointcut và bean lifecycle thay vì kết luận ngay do self-invocation.

### 12.4. Bước 4: đo bằng counter hoặc test event

Không chỉ tìm một dòng log giống nhau: một API request có thể gọi method hai lần; log từ transaction/filter cũng có thể trông tương tự.

Một kiểm thử tốt nên có counter/event collector ở advice và ở target:

```text
Một lần clientBean -> proxy.submit():
    advice count +1, target count +1

Một lần raw.submit():
    advice count +0, target count +1

Một lần this.submit() trong raw target:
    advice count +0, target count +1
```

Đây là số lần kỳ vọng **với một advice chỉ áp dụng cho `submit`**. Nếu có nhiều advisors hoặc một `@Around` không gọi `proceed()`, cần chỉnh expected counts theo chính sách thực tế.

## 13. Hành vi `@Around` còn làm khác biệt giữa proxy và target rõ hơn

Với `@Before`, raw target bypass chủ yếu làm thiếu thao tác trước method. Với `@Around`, hậu quả có thể nghiêm trọng hơn: khi đi qua proxy, advice **có thể quyết định có gọi target hay không**, thay đổi kết quả trả về hoặc chuyển tiếp ngoại lệ. Khi bypass proxy, toàn bộ khả năng điều phối đó bị bỏ qua.

Ví dụ một method fragment trong aspect:

```java
@Around("execution(public * com.example.boundary.OrderService.submit(..))")
public Object around(org.aspectj.lang.ProceedingJoinPoint pjp)
        throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed(); // Qua proxy: tiếp tục thực thi target.
    } finally {
        System.out.println("durationNanos=" + (System.nanoTime() - start));
    }
}
```

Đây là **method fragment minh họa**, cần đặt vào một class `@Aspect` đã đăng ký bean và import annotation `Around`. Không thêm đồng thời fragment này vào project phần 5 nếu vẫn muốn giữ nguyên stdout đã công bố.

Với một đường gọi raw target, không có `ProceedingJoinPoint` của Spring AOP cho lần gọi ấy và không có logic đo thời gian trong aspect. Điều tương tự áp dụng cho audit, retry, security check hoặc caching advice được thiết kế dựa trên interception.

**Không tự coi bypass proxy là lỗi performance nhỏ.** Nó có thể khiến một yêu cầu bảo mật hoặc transaction policy không được áp dụng. Nếu một hành vi bắt buộc về tính đúng đắn, nên kết hợp thiết kế API/bean boundary, unit/integration tests và chính sách bảo vệ ngoài AOP khi cần.

## 14. Các lỗi phổ biến và hướng khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@Before` chạy khi gọi từ controller, không chạy khi gọi trong cùng service | Controller có reference tới proxy, nhưng service gọi `this.method()` trên raw target | Tách method cần advice sang Spring bean khác; gọi qua proxy được inject. |
| Có `@Aspect` nhưng lời gọi từ bean khác vẫn không được advice | Aspect chưa là Spring bean, proxy chưa được bật, pointcut không khớp, hoặc caller giữ raw reference | Kiểm tra registration → context → AOP creator → proxy → pointcut → đường gọi. |
| Tự tạo service bằng `new` khiến transaction/audit không chạy | Instance ngoài Spring container | Đưa service vào IoC và inject bean Spring quản lý. |
| `@PostConstruct` gọi method có aspect nhưng advice không chạy | Initialization xảy ra trên raw bean trước proxy + self-invocation | Di chuyển invocation sang giai đoạn sau khi context sẵn sàng qua bean khác. |
| Ép `proxyTargetClass=true` nhưng `this.method()` vẫn bypass | CGLIB không đổi bản chất self-invocation của Spring proxy AOP | Không dùng proxy type để sửa call boundary; tách bean hoặc cấu hình đường gọi hợp lệ. |
| Advice có lúc chạy, có lúc không với cùng class | Có nhiều instances/references, một số qua proxy, một số raw/new, hoặc bean khác context | Theo dõi bean origin, `AopUtils`, identity và nơi dependency được resolve. |
| `getBean(ConcreteClass.class)` lỗi khi dùng JDK proxy | Proxy chỉ triển khai interface nên không thuộc concrete class | Inject theo business interface, hoặc chọn class proxy có chủ đích nếu hợp lệ. |
| Bean được proxy nhưng method không chạy advice | Proxy có advisor khác hoặc pointcut không khớp method đó | Liệt kê advisors, đo invocation và kiểm tra pointcut cụ thể. |
| Cố dùng `AopContext.currentProxy()` rồi gặp lỗi | Chưa bật `exposeProxy`, không trong proxy invocation hoặc cast sai type | Ưu tiên tái cấu trúc bean; chỉ dùng cơ chế này khi thật sự cần và được cấu hình đúng. |
| Unit test dùng `new Service()` nhưng kỳ vọng aspect chạy | Test không khởi tạo Spring AOP context | Test Spring AOP bằng integration test có context, hoặc test nghiệp vụ raw riêng không kỳ vọng advice. |

## 15. Quy trình thiết kế ranh giới Spring AOP bền vững

1. **Xác định method nào là điểm chặn có chủ đích**, ví dụ `OrderService.submit()`.
2. **Đặt target thành Spring bean** và đăng ký aspect thành bean trong đúng `ApplicationContext`.
3. **Bật Spring auto-proxy đúng cách**, qua Java config, XML hoặc Spring Boot auto-configuration tương ứng.
4. **Thiết kế public entry point được gọi từ bean khác**, tránh để policy quan trọng phụ thuộc vào self-invocation.
5. **Inject theo kiểu phù hợp với proxy strategy**; với JDK proxy, ưu tiên business interface. Không tự `new` service cần advice.
6. **Không giữ raw references ngoài container**; nếu cần debug, dùng một test cô lập và loại khỏi code sản xuất.
7. **Kiểm tra `AopUtils.isAopProxy` và lời gọi thực tế** trên dependency của caller, không chỉ bean type hoặc annotation.
8. **Đo advice count và target count**, đặc biệt với `@Around`, lỗi/exception, transaction và nhiều advisors.
9. **Kiểm tra các context/scope**, khi service được chuyển module, web child context hoặc dùng prototype/scoped proxy.
10. **Đưa test về call boundary vào regression suite**, để refactor không vô tình chuyển từ proxy reference sang raw target reference.

### Tài liệu chính thức của Spring

- Spring Framework — Proxying Mechanisms, Understanding AOP Proxies: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Declaring an Aspect: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- Spring Framework — AOP Concepts: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- Spring Framework — Programmatic AOP Proxy Creation: https://docs.spring.io/spring-framework/reference/core/aop-api/prog.html

**Tóm lại, trong Spring AOP, cùng một target method có thể được gọi theo hai đường: qua Spring proxy hoặc trực tiếp trên raw target. Chỉ đường qua proxy mới thực hiện advisor/advice phù hợp.** Thiết kế bean boundaries và kiểm thử đúng reference của caller chính là cách bảo đảm Spring Aspect được áp dụng nhất quán.
