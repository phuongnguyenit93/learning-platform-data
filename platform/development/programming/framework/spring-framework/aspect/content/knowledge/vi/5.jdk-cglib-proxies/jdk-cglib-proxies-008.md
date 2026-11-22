# Kiểu tham chiếu khi tiêm phụ thuộc qua interface hoặc lớp cụ thể trong Spring AOP

## 1. Tại sao Spring AOP ảnh hưởng đến kiểu được inject?

Một ứng dụng có thể khai báo `PaymentServiceImpl implements PaymentService` và tiêm dependency ở hai cách:

```java
private final PaymentService paymentService;         // theo interface
private final PaymentServiceImpl paymentServiceImpl; // theo lớp triển khai
```

Khi **Spring AOP auto-proxy** áp dụng advice cho bean ấy, object container cung cấp cho các bean khác có thể **không còn là instance trực tiếp của `PaymentServiceImpl`**. Tùy chiến lược proxy:

- **JDK dynamic proxy:** object proxy implements các interface được expose, ví dụ `PaymentService`, nhưng **không extends `PaymentServiceImpl`**. Inject theo interface phù hợp; yêu cầu ép kiểu hoặc inject theo implementation class có thể thất bại.
- **CGLIB class-based proxy:** object proxy là **subclass** của `PaymentServiceImpl`. Vì vậy proxy có thể được gán cho cả interface `PaymentService` và concrete type `PaymentServiceImpl`, miễn là việc tạo proxy subclass hợp lệ.

Bài này tập trung vào **Spring AOP và dependency injection**: chọn kiểu constructor parameter/field, ảnh hưởng của cấu hình `proxyTargetClass`, biểu hiện khi runtime, và cách debug. Lý thuyết Aspect chung không phải trọng tâm.

## 2. Minh họa đối tượng thật và object được Spring cung cấp

Giả sử:

```java
public interface PaymentService {
    void pay();
}

public class PaymentServiceImpl implements PaymentService {
    @Override
    public void pay() {
        // xử lý thanh toán
    }
}
```

Hai hình thức Spring có thể tạo khi có advisor khớp:

```text
                      Spring IoC container
                              |
                  target: PaymentServiceImpl
                              |
           +------------------+------------------+
           |                                     |
      JDK proxy                              CGLIB proxy
   implements PaymentService          extends PaymentServiceImpl
           |                                     |
     instanceof PaymentService: true       instanceof PaymentService: true
     instanceof PaymentServiceImpl: false  instanceof PaymentServiceImpl: true
           |                                     |
        advice -> target.pay()                  advice -> target.pay()
```

Hai cột đều là **Spring AOP proxy** nếu được tạo bởi Spring AOP. Điều khác biệt quan trọng với dependency injection là **các kiểu mà object proxy có thể được gán cho**.

| Phép thử đối với object được trả từ context | JDK proxy của `PaymentService` | CGLIB proxy của `PaymentServiceImpl` |
| --- | --- | --- |
| `proxy instanceof PaymentService` | `true` | `true` |
| `proxy instanceof PaymentServiceImpl` | `false` | `true` |
| `AopUtils.isAopProxy(proxy)` | `true` | `true` |
| `AopUtils.isJdkDynamicProxy(proxy)` | `true` | `false` |
| `AopUtils.isCglibProxy(proxy)` | `false` | `true` |
| Có thể tham chiếu theo interface `PaymentService` | Có | Có |
| Có thể tham chiếu theo concrete `PaymentServiceImpl` | **Không** bằng chính JDK proxy ấy | Có, nếu class proxy được tạo thành công |

Bảng giả định AOP proxy đã được tạo cho đúng bean, không có các proxy lồng nhau hay bean replacement bất thường. **Không phải mọi Spring bean đều có AOP proxy:** nếu không có advisor áp dụng, Spring có thể trả target gốc; khi đó dependency injection theo concrete class vẫn có thể hoạt động dù dự án cấu hình `proxyTargetClass=false`.

## 3. JDK dynamic proxy: tiêm qua interface

### 3.1. Cách Spring chọn JDK proxy

Trong cấu hình Spring AOP điển hình, nếu target implements interface và **không bị ép tạo class-based proxy**, Spring có thể dùng JDK dynamic proxy. Proxy này triển khai **business interface** cùng một số interface nội bộ Spring, nhưng không kế thừa implementation class.

Ví dụ constructor injection được khuyến nghị:

```java
@Service
public class CheckoutController {
    private final PaymentService paymentService;

    public CheckoutController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
```

Đây là **đoạn minh họa**, giả định `PaymentService` và bean triển khai đã được đăng ký, `@Service` được component scan và đúng một bean `PaymentService` có thể tiêm.

Khi Spring cung cấp JDK proxy cho bean triển khai, nó vẫn là một `PaymentService`. Code gọi `paymentService.pay()` thông qua tham chiếu interface, giúp lời gọi đi qua proxy và advisor tương ứng.

**Không nên làm:**

```java
PaymentServiceImpl impl =
    (PaymentServiceImpl) context.getBean("paymentService");
```

Nếu bean được bọc bằng JDK proxy, phép cast này có thể ném `ClassCastException`. `getBean("paymentService", PaymentServiceImpl.class)` có thể ném `BeanNotOfRequiredTypeException` vì kiểu **object proxy được trả ra** không tương thích với `PaymentServiceImpl`.

### 3.2. Điều gì xảy ra khi inject trực tiếp implementation?

```java
@Service
public class CheckoutController {
    private final PaymentServiceImpl implementation;

    public CheckoutController(PaymentServiceImpl implementation) {
        this.implementation = implementation;
    }
}
```

Nếu Spring cố cung cấp **JDK proxy** cho bean `PaymentServiceImpl`, dependency trên yêu cầu **concrete type** không được chính JDK proxy đáp ứng. Việc tạo application context có thể thất bại với lỗi dependency resolution, chẳng hạn `UnsatisfiedDependencyException`, `BeanNotOfRequiredTypeException`, hoặc một exception chứa nguyên nhân kiểu không tương thích.

Lỗi chi tiết phụ thuộc cách khai báo bean, thời điểm resolve dependency và phiên bản Spring. Không nên dự đoán duy nhất một exception cho mọi dự án; bản chất lỗi là **proxy không assignable cho kiểu được yêu cầu**.

**Sửa đúng tại hợp đồng API**: chuyển constructor/field sang interface nếu caller chỉ cần những method thuộc interface. Nếu caller thực sự cần API của implementation class, cân nhắc **class-based proxy**, thiết kế lại interface để expose chức năng hợp lý, hoặc tách trách nhiệm sang bean khác.

### 3.3. Method chỉ có trong implementation

```java
public interface PaymentService {
    void pay();
}

public class PaymentServiceImpl implements PaymentService {
    @Override
    public void pay() {}

    public void retryFailedPayments() {}
}
```

`retryFailedPayments()` không nằm trong `PaymentService`. Với JDK proxy được khai báo theo `PaymentService`, caller **không thể** gọi `retryFailedPayments()` qua interface đó. Khi cần AOP advice cho method này, bạn cần quyết định liệu method nên thuộc một **interface phù hợp** hay cần chiến lược class proxy. Không dùng cast về implementation vì JDK proxy không phải implementation class.

## 4. CGLIB class-based proxy: tiêm được qua lớp cụ thể

Khi Spring AOP sử dụng CGLIB, một lớp con của target được sinh lúc chạy. Vì subclass là một instance hợp lệ của lớp cha, Spring có thể cung cấp nó cho constructor đang yêu cầu `PaymentServiceImpl`:

```java
@Service
public class ReconciliationJob {
    private final PaymentServiceImpl paymentService;

    public ReconciliationJob(PaymentServiceImpl paymentService) {
        this.paymentService = paymentService;
    }

    public void run() {
        paymentService.pay();
    }
}
```

Đoạn này **có thể hoạt động** nếu proxy thực tế là class-based, type hợp lệ và chỉ có một bean phù hợp.

Tuy nhiên, CGLIB có giới hạn quan trọng:

- **`final class`:** không thể subclass, nên không thể tạo CGLIB AOP proxy của chính class đó.
- **`final method`:** không thể override; lời gọi method ấy không được Spring CGLIB advice thông qua cơ chế override.
- **`private method`:** không thể override, không thể advice bằng Spring proxy.
- **Method không nhìn thấy đối với subclass** (chẳng hạn package-private ở parent thuộc package khác) cũng không được can thiệp.
- **Self-invocation:** `this.method()` bên trong target vẫn bỏ qua proxy, dù proxy dùng CGLIB.
- Việc CGLIB được Spring đóng gói trong `spring-core` nghĩa là ứng dụng Spring Framework hiện đại thường không cần khai báo dependency `cglib` riêng để dùng class-based Spring AOP.

**Kết luận thiết kế:** Inject concrete type có thể hữu ích trong codebase legacy hoặc khi không có interface ổn định, nhưng làm contract phụ thuộc vào cấu trúc implementation và lựa chọn proxy. Inject interface thường dễ giữ ổn định hơn khi refactor hay thay loại proxy.

## 5. Ví dụ hoàn chỉnh: hai context, cùng target, hai kiểu injection

Dự án này dùng **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Maven. Nó cố ý tạo **hai `AnnotationConfigApplicationContext` riêng biệt** để cấu hình ép proxy không ảnh hưởng lẫn nhau:

- **Context A:** `@EnableAspectJAutoProxy(proxyTargetClass = false)` → JDK proxy cho target có interface; client tiêm interface.
- **Context B:** `@EnableAspectJAutoProxy(proxyTargetClass = true)` → CGLIB proxy; client tiêm implementation class.

### 5.1. Cấu trúc

```text
proxy-type-injection/
├── pom.xml
└── src/main/java/example/
    ├── GreetingPort.java
    ├── GreetingService.java
    ├── TraceAspect.java
    ├── InterfaceClient.java
    ├── ConcreteClient.java
    ├── JdkConfig.java
    ├── ClassConfig.java
    └── Main.java
```

### 5.2. Maven

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>proxy-type-injection</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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

### 5.3. Business interface và implementation

**`GreetingPort.java`**:

```java
package example;

public interface GreetingPort {
    String greet(String name);
}
```

**`GreetingService.java`**:

```java
package example;

public class GreetingService implements GreetingPort {
    @Override
    public String greet(String name) {
        return "Xin chào " + name;
    }
}
```

### 5.4. Một `@Aspect` dùng chung cho hai context

**`TraceAspect.java`**:

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(* example.GreetingService.greet(..))")
    public void beforeGreet() {
        System.out.println("advice: before greet");
    }
}
```

Pointcut áp dụng lên **method `GreetingService.greet`**. Lớp aspect được đăng ký làm bean riêng trong cả hai context bằng `@Bean`; chỉ `@Aspect` trên class **không tự đăng ký bean**.

### 5.5. Client phụ thuộc interface hoặc concrete class

**`InterfaceClient.java`**:

```java
package example;

public class InterfaceClient {
    private final GreetingPort service;

    public InterfaceClient(GreetingPort service) {
        this.service = service;
    }

    public void run() {
        System.out.println("interface client: " + service.greet("Lan"));
    }
}
```

**`ConcreteClient.java`**:

```java
package example;

public class ConcreteClient {
    private final GreetingService service;

    public ConcreteClient(GreetingService service) {
        this.service = service;
    }

    public void run() {
        System.out.println("concrete client: " + service.greet("Minh"));
    }
}
```

Hai client không tự tra context hoặc cast proxy. Mỗi client nhận dependency bằng constructor, để Spring resolve phù hợp với kiểu đã khai báo.

### 5.6. Context A: JDK proxy, inject interface

**`JdkConfig.java`**:

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class JdkConfig {
    @Bean
    public GreetingPort greetingService() {
        return new GreetingService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    public InterfaceClient interfaceClient(GreetingPort service) {
        return new InterfaceClient(service);
    }
}
```

Bean `greetingService` được khai báo bằng **return type `GreetingPort`**. Với Spring AOP proxy JDK, object cuối cùng vẫn implements interface này. Interface client được inject qua chính tham chiếu do Spring cung cấp nên lời gọi nhận advice.

### 5.7. Context B: CGLIB proxy, inject concrete class

**`ClassConfig.java`**:

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassConfig {
    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    public ConcreteClient concreteClient(GreetingService service) {
        return new ConcreteClient(service);
    }
}
```

Spring được chỉ thị dùng **class-based proxy**, nên object được inject vào `ConcreteClient` là một subtype hợp lệ của `GreetingService`, miễn lớp này proxy được.

### 5.8. Chạy và xác minh kiểu object

**`Main.java`**:

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.BeanNotOfRequiredTypeException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(JdkConfig.class)) {
            Object bean = context.getBean("greetingService");

            System.out.println("jdk proxy: " + AopUtils.isJdkDynamicProxy(bean));
            System.out.println("jdk is concrete: " + (bean instanceof GreetingService));

            try {
                context.getBean("greetingService", GreetingService.class);
                System.out.println("concrete lookup: succeeded");
            } catch (BeanNotOfRequiredTypeException ex) {
                System.out.println("concrete lookup: failed");
            }

            context.getBean(InterfaceClient.class).run();
        }

        try (var context = new AnnotationConfigApplicationContext(ClassConfig.class)) {
            Object bean = context.getBean("greetingService");

            System.out.println("cglib proxy: " + AopUtils.isCglibProxy(bean));
            System.out.println("cglib is concrete: " + (bean instanceof GreetingService));
            context.getBean(ConcreteClient.class).run();
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Các dòng do `Main` và `TraceAspect`/clients in ra trong cấu hình ví dụ:

```text
jdk proxy: true
jdk is concrete: false
concrete lookup: failed
advice: before greet
interface client: Xin chào Lan
cglib proxy: true
cglib is concrete: true
advice: before greet
concrete client: Xin chào Minh
```

**Giải thích kết quả:**

1. Spring AOP tìm `TraceAspect`, thấy pointcut khớp `GreetingService.greet` và tạo AOP proxy cho bean đích.
2. Trong `JdkConfig`, proxy triển khai `GreetingPort` nhưng không extends `GreetingService`. Vì vậy lookup theo `GreetingService.class` bị từ chối, còn constructor cần `GreetingPort` nhận được dependency phù hợp.
3. Khi `InterfaceClient.run()` gọi `service.greet("Lan")`, lời gọi qua **JDK proxy** chạy advice trước khi method đích trả chuỗi.
4. Trong `ClassConfig`, proxy là subclass CGLIB của `GreetingService`; `ConcreteClient` được inject theo concrete type và vẫn gọi qua proxy.
5. Mỗi `ApplicationContext` có bean và cấu hình riêng, nên ví dụ không bị cấu hình `proxyTargetClass=true` của một context ép context kia sang CGLIB.

Ví dụ có **một advisor phù hợp với một method**. Nếu thêm advisor hoặc auto-proxy infrastructure khác, kiểu proxy và thứ tự advice có thể thay đổi; khi đó phải kiểm tra trạng thái thực tế.

## 6. Vấn đề của `@Autowired`: kiểu inject là một hợp đồng

### 6.1. Chọn interface khi caller chỉ cần API nghiệp vụ

```java
@Service
public class InvoiceController {
    private final InvoiceService service;

    public InvoiceController(InvoiceService service) {
        this.service = service;
    }
}
```

Ví dụ này giả định `InvoiceService` là **interface** và Spring cung cấp đúng một candidate bean (hoặc có `@Qualifier`/`@Primary` khi cần). Đây là cách giảm ràng buộc giữa controller và chi tiết implementation/proxy.

Dù Spring cấu hình JDK hay CGLIB proxy, cả hai đều có thể thực thi interface ấy. Việc dùng interface **không tự bảo đảm có AOP**: method phải match advisor và được gọi qua bean proxy.

### 6.2. Khi nào inject concrete class vẫn hợp lệ?

Inject concrete class hợp lệ nếu thực tế container trả về object tương thích. Ví dụ:

- Bean **không bị proxy** và object gốc thuộc implementation class.
- Bean dùng **CGLIB proxy**, không gặp giới hạn class/method.
- Project có quy ước class-based proxy rõ ràng và test kiểm chứng cho các bean liên quan.

Điều đáng tránh là viết code phụ thuộc vào concrete type trong khi **không kiểm soát chiến lược proxy**. Một cấu hình AOP hoặc Spring Boot property thay đổi có thể khiến cùng code inject thất bại.

### 6.3. Kiểu trả về của `@Bean` có liên quan nhưng không thay thế kiểu proxy

Với Java configuration:

```java
@Bean
public PaymentService paymentService() {
    return new PaymentServiceImpl();
}
```

Spring có metadata kiểu từ khai báo `@Bean`; runtime instance có thể là `PaymentServiceImpl` trước khi post-processing. Nhưng nếu sau đó Spring tạo **JDK proxy**, object cuối cùng chỉ assignable cho interface được proxy expose.

Ngược lại:

```java
@Bean
public PaymentServiceImpl paymentService() {
    return new PaymentServiceImpl();
}
```

Khai báo return type cụ thể **không ép Spring AOP phải dùng CGLIB**. Cấu hình `proxyTargetClass` và khả năng proxy mới quyết định chiến lược. Không dựa vào kiểu trả về factory method để cast một JDK proxy thành implementation.

## 7. Cấu hình chiến lược proxy trong Spring

### 7.1. Spring Framework thuần

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class InterfaceProxyConfig {
}
```

Đối với target có business interface, ví dụ này **ưu tiên JDK proxy** theo quy tắc Spring AOP. `false` không bảo đảm mọi bean đều dùng JDK: nếu target không có interface phù hợp, Spring có thể cần class-based proxy.

Khi cần CGLIB:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassProxyConfig {
}
```

Điều này chọn class-based proxy cho các bean AOP phù hợp trong phạm vi cấu hình. Không phải cách để biến một class `final` thành proxy được.

### 7.2. Spring Boot

Theo tài liệu Spring Boot, auto-configuration AOP **mặc định chọn class-based (CGLIB) proxy**. Để ưu tiên JDK proxy khi target có interface:

```properties
spring.aop.proxy-target-class=false
```

Muốn giữ mặc định class-based hoặc khai báo rõ:

```properties
spring.aop.proxy-target-class=true
```

Khi dùng AspectJ trên classpath và auto-configuration được bật, Spring Boot thường không cần thêm `@EnableAspectJAutoProxy` để hoạt động. Tuy nhiên, aspect vẫn phải đăng ký thành Spring bean.

Một khác biệt quan trọng: **Spring Framework thuần** thường mặc định dùng JDK proxy nếu có interface; **Spring Boot auto-configuration** mặc định dùng CGLIB. Đừng áp dụng kết quả của một ứng dụng Boot cho mọi ứng dụng Spring Framework thuần.

### 7.3. Cấu hình proxy có thể ảnh hưởng tới hạ tầng AOP khác

Spring có thể hợp nhất một số cấu hình auto-proxy creator, và thuộc tính **`proxyTargetClass=true` mạnh hơn** có thể ảnh hưởng tới các proxy do transaction hoặc AOP infrastructure khác tạo ra trong cùng context. Vì vậy:

- Tránh thêm `@EnableAspectJAutoProxy(proxyTargetClass=true)` chỉ để “chữa” một injection error nếu điều đó đổi proxy strategy toàn ứng dụng.
- Xem `@EnableTransactionManagement`, `@EnableCaching`, các auto-configurations và global proxy settings đang hoạt động.
- Kiểm tra **object thực tế** bằng `AopUtils.isJdkDynamicProxy(...)`/`isCglibProxy(...)` sau mọi thay đổi.

Spring Framework 7 còn có một số lựa chọn proxy-target cụ thể theo bean (ví dụ `@Proxyable` trong phiên bản hỗ trợ); không giả định các API mới đó sẵn có trong Spring 6.2 của ví dụ.

## 8. Các trường hợp dễ gây nhầm lẫn

### 8.1. Có nhiều implementation cùng interface

```java
public interface PaymentService { void pay(); }
public class CardPaymentService implements PaymentService { /* ... */ }
public class BankPaymentService implements PaymentService { /* ... */ }
```

Nếu cả hai được đăng ký làm Spring beans, constructor chỉ nhận `PaymentService` có thể **không xác định được bean nào**. Đây là vấn đề **candidate resolution**, không phải lỗi JDK/CGLIB proxy. Có thể dùng `@Qualifier`, `@Primary` hoặc tập hợp `List<PaymentService>` nếu yêu cầu nghiệp vụ phù hợp.

**Ví dụ minh họa:**

```java
public CheckoutController(@Qualifier("cardPaymentService") PaymentService service) {
    this.service = service;
}
```

Đây là snippet constructor, cần import `@Qualifier` và các type liên quan; không phải chương trình độc lập.

### 8.2. JDK proxy nhưng vẫn “thấy” target class

`AopUtils.getTargetClass(proxy)` có thể trả về `PaymentServiceImpl.class` ngay khi:

```java
proxy instanceof PaymentServiceImpl // false với JDK proxy
```

Không có mâu thuẫn: **target class** là lớp đứng sau proxy, còn **runtime type của proxy** quyết định việc assign/cast/inject. Đừng dùng `getTargetClass` làm lý do ép kiểu proxy thành target implementation.

### 8.3. Bean name không chữa lỗi assignability

`@Qualifier("paymentService")` giúp **chọn bean theo qualifier/name**, nhưng không làm JDK proxy tự trở thành subtype `PaymentServiceImpl`:

```java
// Vẫn không tương thích nếu Spring đang trả JDK proxy:
public CheckoutController(
        @Qualifier("paymentService") PaymentServiceImpl service) {
    // ...
}
```

Nếu cần inject implementation class, hãy đảm bảo **proxy class-based thật sự được tạo** hoặc thiết kế lại API thay vì chỉ thêm qualifier.

### 8.4. Class không implements interface

Một target không implements business interface không thể được JDK dynamic proxy đại diện qua API business của nó; trong Spring AOP thông thường cần class-based proxy. `proxyTargetClass=false` chỉ có nghĩa không **ép** dùng CGLIB cho các target có interface, chứ không thể tạo JDK proxy cho một class bất kỳ.

### 8.5. Interface default methods và generic method

JDK proxy expose các method interface, kể cả một số default method, nhưng việc advice match vẫn phụ thuộc expression, implementation và đường gọi qua proxy. Khi dùng generics/bridge methods hoặc overload, hãy kiểm tra **method signature thực tế** thay vì suy diễn từ tên. Chọn kiểu injection theo interface không thay thế kiểm tra pointcut.

### 8.6. Không “lấy target ra” để tránh cast lỗi

Có thể bạn thấy cách lấy underlying target qua `Advised.getTargetSource().getTarget()` rồi ép kiểu về implementation. Cách này **bỏ qua proxy**, có nguy cơ bỏ qua transaction, cache, security hoặc `@Aspect` advice. Một số target source còn gắn với scope và có thể cung cấp target khác theo từng lần truy xuất.

Nếu caller cần một hành vi nghiệp vụ, hãy expose hành vi đó qua interface/bean được Spring cung cấp thay vì tháo proxy để gọi trực tiếp target.

### 8.7. Spring Data, scoped proxy và các proxy khác

Một Spring Data repository thường được dùng theo **repository interface**; nhưng đó có thể là proxy phục vụ truy vấn/implementation của Spring Data, không nhất thiết là Spring AOP proxy tạo từ một `@Aspect` cụ thể.

Scoped proxies có thể dùng Spring AOP machinery để tìm target đúng scope. Khi đang sửa lỗi injection, cần xác định **proxy của tính năng nào**; không kết luận chỉ từ một tên class sinh động. Nguyên tắc chung vẫn là **thực tế proxy assignable cho kiểu nào**.

## 9. Checklist chẩn đoán lỗi inject khi có AOP

### Bước 1: đọc exception và kiểu được yêu cầu

Ví dụ:

```text
BeanNotOfRequiredTypeException
Required type: example.GreetingService
Actual type: jdk.proxy...$Proxy...
```

Đây là **minh họa cấu trúc thông điệp**, không phải nguyên văn exception cố định của mọi phiên bản JDK/Spring. Nếu thấy actual type là JDK proxy, hãy kiểm tra concrete dependency hoặc cast.

### Bước 2: kiểm tra proxy mà context trả về

```java
// Snippet đặt trong mã có ApplicationContext context.
Object bean = context.getBean("paymentService");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(bean.getClass().getName());
System.out.println(AopUtils.getTargetClass(bean).getName());
```

Các import liên quan là `org.springframework.aop.support.AopUtils` và `org.springframework.context.ApplicationContext`. Không hard-code tên class proxy sinh động vào business code hoặc vào kiểm thử: JDK/Spring có thể thay đổi cách đặt tên.

### Bước 3: so sánh các interface của proxy với constructor parameter

- Nếu bean là JDK proxy, parameter là **interface được proxy expose**?
- Nếu parameter là concrete class, có lý do bắt buộc không?
- Nếu BeanFactory tìm nhiều candidates, hãy xử lý ambiguity riêng bằng qualifier/primary.
- Nếu class-based proxy đang được yêu cầu, class/method có `final`, `private` hay giới hạn truy cập không?

### Bước 4: kiểm tra cấu hình proxy

- Trong Spring Framework thuần, có `@EnableAspectJAutoProxy(proxyTargetClass=...)` hoặc XML AOP/auto-proxy settings nào?
- Trong Boot, `spring.aop.proxy-target-class` đang nhận giá trị nào, và auto-configuration có được bật không?
- Transaction/cache/security và những auto-proxy infrastructure khác có đang tham gia cấu hình proxy không?

### Bước 5: kiểm chứng hành vi advice

Sau khi sửa được injection, vẫn phải **gọi một method khớp pointcut qua bean reference** để xác nhận advice thực thi. Thành công về kiểu không đảm bảo lời gọi đã qua proxy: gọi `new ServiceImpl()` hoặc self-invocation `this.pay()` vẫn có thể bỏ qua advice.

## 10. Cách lựa chọn trong dự án Spring AOP

| Yêu cầu thực tế | Hướng tiếp cận |
| --- | --- |
| Caller chỉ cần hành vi đã có trên interface | **Inject interface**, phù hợp với cả JDK và CGLIB proxy |
| Có interface, muốn thay đổi implementation linh hoạt | **Inject interface** và cấu hình bean resolution bằng qualifier nếu cần |
| Cần method nằm ngoài interface | Cân nhắc bổ sung method vào một interface phù hợp hoặc thiết kế một bean chuyên trách; dùng class-based proxy khi có lý do |
| Ứng dụng legacy chủ yếu inject concrete classes | Có thể chọn CGLIB với kiểm thử đầy đủ cho giới hạn `final` và tác động cấu hình toàn context |
| Bị `ClassCastException` từ JDK proxy → implementation | **Không cast**; nhận diện proxy và chuyển dependency sang interface tương thích |
| Bean có nhiều implementation cùng interface | Xử lý bằng `@Qualifier`/`@Primary` hoặc một chiến lược chọn bean, không đổi proxy tùy tiện |
| Thêm aspect khiến injection concrete đang hoạt động trở thành lỗi | Kiểm tra bean trước đây chưa có proxy; advisor mới khiến Spring tạo JDK proxy, từ đó lộ ra sự phụ thuộc kiểu cụ thể |
| Cần test chính xác AOP | Test kiểu proxy và lời gọi qua **bean từ context**, không test riêng `new Target()` |

Điều đáng nhớ nhất: **Dependency injection nhận object mà Spring thực tế cung cấp, không nhất thiết là object target ban đầu.** Khi Spring AOP tạo JDK proxy, contract đối với caller là interface; khi tạo CGLIB proxy, contract có thể bao gồm concrete class. Chọn kiểu dependency theo API mà caller cần và xác minh loại proxy đang chạy.

## 11. Tự kiểm tra

**Câu 1.** `OrderServiceImpl implements OrderService`. Spring tạo JDK proxy cho `OrderServiceImpl`. Constructor `CheckoutController(OrderServiceImpl service)` có tương thích với object proxy không?

**Đáp án:** Không. JDK proxy không extends implementation class. Dùng `CheckoutController(OrderService service)` nếu API đó đáp ứng nhu cầu.

**Câu 2.** Cùng bean chuyển sang CGLIB proxy; constructor nhận `OrderServiceImpl` có thể hoạt động không?

**Đáp án:** Có, nếu `OrderServiceImpl` được proxy subclass hợp lệ và Spring có thể resolve đúng bean. Tuy nhiên các phương thức `final/private` vẫn không được can thiệp theo cơ chế override.

**Câu 3.** `AopUtils.getTargetClass(bean)` là `OrderServiceImpl.class`. Có thể cast `bean` thành `OrderServiceImpl` không?

**Đáp án:** Chưa thể kết luận. Cần kiểm tra runtime proxy type; nếu bean là JDK proxy, cast vẫn sai.

**Câu 4.** Một ứng dụng Spring Boot có `spring.aop.proxy-target-class=false`, bean có interface và pointcut khớp. Cần tiêm theo loại nào để không phụ thuộc vào class-based proxy?

**Đáp án:** Tiêm qua interface được proxy expose.

**Câu 5.** Bean được inject bằng concrete type hợp lệ, nhưng `this.pay()` trong cùng target không chạy `@Before`. Có phải CGLIB proxy bị lỗi?

**Đáp án:** Không. Đây là **self-invocation**: lời gọi nội bộ qua `this` bỏ qua proxy Spring AOP, bất kể JDK hay CGLIB.

## 12. Tài liệu Spring chính thức

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK dynamic proxies và CGLIB, `proxy-target-class`, `final` methods, giới hạn `this`.
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html): quy tắc chọn JDK proxy khi có interface và dùng CGLIB khi cần proxy theo class.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy` và điều kiện aspect bean.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): cấu hình `spring.aop.proxy-target-class` và lựa chọn mặc định.
- [Spring Framework — AopUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): cách nhận diện proxy, target class.
