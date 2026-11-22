# Phân biệt lớp proxy, lớp đích và kiểu khai báo của bean trong Spring AOP

## 1. Vì sao cần phân biệt ba kiểu?

Trong ứng dụng Spring, một bean có thể được khai báo bằng một interface, được tạo từ một class cụ thể, nhưng đối tượng mà client nhận từ `ApplicationContext` lại thuộc **lớp proxy được sinh trong runtime**. Các khái niệm này có nhiệm vụ khác nhau:

1. **Kiểu khai báo của bean (declared bean type):** kiểu xuất hiện trong bean definition, ví dụ return type `PaymentService` của một phương thức `@Bean`. Spring dùng thông tin khai báo này cho type prediction, xác định candidate injection và các xử lý trước khi bean được tạo.
2. **Lớp đích (target class):** lớp của đối tượng thật thực thi nghiệp vụ sau khi Spring AOP cho interceptor tiếp tục lời gọi, ví dụ `PaymentServiceImpl`.
3. **Lớp proxy (proxy class):** lớp runtime của đối tượng được Spring trả cho client khi bean bị AOP proxy, ví dụ JDK dynamic proxy class hoặc subclass CGLIB được tạo tại runtime.

Đừng kết luận ba kiểu này là một chỉ vì chúng đại diện cho cùng một bean name. **Declared type không tự chọn cơ chế proxy; runtime proxy class không nhất thiết là target class; injection type của client cũng là một khái niệm riêng.**

Bài tập trung vào **Spring AOP proxy-based interception**, container, `@Bean` và Java dependency injection. Không mở rộng các nguyên lý Aspect tổng quát hay AspectJ weaving.

## 2. Ví dụ một bean có ba kiểu

Giả sử có interface và implementation:

```java
public interface PaymentService {
    String pay(String orderId);
}

public class PaymentServiceImpl implements PaymentService {
    @Override
    public String pay(String orderId) {
        return "PAID:" + orderId;
    }
}
```

Đăng ký Spring bean:

```java
@Configuration
public class PaymentConfig {
    @Bean
    public PaymentService paymentService() {
        return new PaymentServiceImpl();
    }
}
```

Đây là các đoạn khai báo minh họa; phần 5 có project chạy được. Từ hai đoạn trên:

- `PaymentService` là **kiểu khai báo** trong chữ ký `@Bean`.
- `PaymentServiceImpl` là **lớp đích** do method `@Bean` tạo ra.
- Nếu Spring AOP áp advice lên bean, reference mà consumer nhận sẽ là **proxy**: lớp runtime của reference đó có thể khác cả hai kiểu vừa nêu.

```text
@Bean PaymentService paymentService()
           |
           | declared bean type: PaymentService
           v
    Spring BeanFactory
           |
           | gọi factory method
           v
  new PaymentServiceImpl()
           |
           | target class: PaymentServiceImpl
           v
   Spring AOP auto-proxy
          / \
         /   \
        v     v
   JDK proxy   CGLIB proxy
   implements  extends
   interface   implementation
        \       /
         \     /
          v   v
  Client nhận bean reference,
  gọi pay() qua proxy rồi tới target
```

**Một lưu ý quan trọng:** Spring có thể thực thi `BeanPostProcessor` sau khi tạo object từ `@Bean` để thay object được cấp cho consumer bằng proxy. Do đó method `@Bean` có thể thật sự trả implementation, trong khi `context.getBean(...)` lại trả proxy.

## 3. So sánh theo kiểu proxy

Cùng một target `PaymentServiceImpl implements PaymentService` có advisor Spring AOP phù hợp:

| Thuộc tính | JDK dynamic proxy | CGLIB class-based proxy |
| --- | --- | --- |
| Lớp proxy runtime | Lớp sinh bởi JDK, implement interface được công bố | Subclass runtime của target class |
| Lớp đích | `PaymentServiceImpl` | `PaymentServiceImpl` |
| `@Bean` return type ví dụ | `PaymentService` | `PaymentService` |
| `bean instanceof PaymentService` | `true` | `true` |
| `bean instanceof PaymentServiceImpl` | `false` | `true` |
| `bean.getClass() == PaymentServiceImpl.class` | `false` | `false` |
| `AopUtils.isJdkDynamicProxy(bean)` | `true` | `false` |
| `AopUtils.isCglibProxy(bean)` | `false` | `true` |
| `AopUtils.getTargetClass(bean)` | `PaymentServiceImpl.class` | `PaymentServiceImpl.class` |

Trong bảng, bean **đã được Spring AOP tạo proxy**. Nếu không có advisor phù hợp, bean có thể được trả trực tiếp là `PaymentServiceImpl`, khi đó các kết quả liên quan proxy thay đổi.

### 3.1. JDK proxy có interface nhưng không phải implementation

Với JDK dynamic proxy, Spring tạo object implement các interface được expose. Vì vậy:

```java
PaymentService service = context.getBean(PaymentService.class);
// Phù hợp với interface của JDK proxy.

// Không được giả định kiểu ép sau luôn hợp lệ:
PaymentServiceImpl impl = (PaymentServiceImpl) service;
```

Khi `service` là JDK proxy thực tế, dòng cast thường ném `ClassCastException`. Việc target phía sau proxy thuộc `PaymentServiceImpl` **không làm proxy trở thành subtype của implementation**.

### 3.2. CGLIB proxy kế thừa target class

Với CGLIB, Spring tạo subclass để intercept method có thể override:

```text
PaymentServiceImpl             <- target class
        ^
        | extends
        |
Generated CGLIB proxy class    <- proxy runtime class
        |
        +-- intercept call via advisor chain
        |
        +-- delegate to target PaymentServiceImpl instance
```

CGLIB proxy `instanceof PaymentServiceImpl` là `true`, nhưng `proxy.getClass() == PaymentServiceImpl.class` vẫn là `false`. Hai kiểm tra trả lời **hai câu hỏi khác nhau**: quan hệ kế thừa và lớp runtime chính xác.

Spring AOP proxy có object target riêng trong cấu hình tiêu chuẩn. Do vậy, sau khi target thực thi một method và gọi `this.otherMethod()`, lời gọi nội bộ không quay lại proxy, dù proxy là subclass CGLIB.

## 4. Kiểu khai báo của bean khác kiểu injection point

Nhìn lại một phương thức factory:

```java
@Bean
PaymentService paymentService() {
    return new PaymentServiceImpl();
}
```

Có ít nhất hai thứ dễ nhầm:

- **Return type `PaymentService`:** thông tin ở bean definition. Trước khi singleton được khởi tạo, Spring thường sử dụng kiểu này để dự đoán candidate của `@Autowired` hoặc `getBeanNamesForType(...)`.
- **Object thực tế `new PaymentServiceImpl()`:** chỉ được biết hoàn toàn khi factory method chạy. Sau đó Spring có thể áp AOP proxy.

Đối với client:

```java
@Service
class CheckoutService {
    private final PaymentService paymentService;

    CheckoutService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
```

Đây là đoạn sử dụng Spring DI minh họa, cần import tương ứng. Constructor parameter ở đây là **injection point type**. Khi kiểu injection là interface, cả JDK và CGLIB AOP proxy phù hợp đều có thể được inject.

Nếu constructor lại yêu cầu `PaymentServiceImpl`, phải xét hai điều kiện **riêng**:

1. BeanFactory có nhận diện bean này là candidate của kiểu implementation ở thời điểm giải quyết dependency không? Return type `@Bean` khai báo interface có thể giới hạn dự đoán kiểu trước khi singleton tồn tại.
2. **Object cuối cùng** có assignable tới implementation không? JDK proxy **không phải** `PaymentServiceImpl`; CGLIB proxy là subclass của `PaymentServiceImpl` trong trường hợp được tạo thành công.

Khai báo `@Bean PaymentServiceImpl paymentService()` làm thông tin type prediction cụ thể hơn, **nhưng không tự ép AOP chọn CGLIB**. Nếu AOP vẫn chọn JDK proxy thì final bean reference không thể ép sang `PaymentServiceImpl`.

## 5. Chương trình hoàn chỉnh: cùng target, hai loại proxy

Ví dụ sử dụng **Java 17+, Maven, Spring Framework 6.2.19**. Hai context được tạo lần lượt và hoàn toàn độc lập:

- `JdkConfig` kích hoạt `@EnableAspectJAutoProxy(proxyTargetClass=false)`.
- `CglibConfig` kích hoạt `@EnableAspectJAutoProxy(proxyTargetClass=true)`.
- Cả hai context import cùng `SharedBeans`; method `@Bean` trả kiểu interface, trong khi implementation là một class cụ thể.
- `TraceAspect` có advice trước `deliver()` để Spring thực sự cần tạo AOP proxy.

Cấu trúc project:

```text
spring-proxy-bean-types/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanTypeDemo.java
```

### 5.1. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-proxy-bean-types</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.19</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BeanTypeDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Tệp src/main/java/demo/BeanTypeDemo.java

```java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class BeanTypeDemo {

    public interface MessageService {
        String deliver(String id);
    }

    public static class MessageServiceImpl implements MessageService {
        @Override
        public String deliver(String id) {
            System.out.println("TARGET deliver " + id);
            return "ACK:" + id;
        }
    }

    @Aspect
    public static class TraceAspect {
        @Before("execution(* demo..*.deliver(..))")
        public void beforeCall() {
            System.out.println("ADVICE deliver");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SharedBeans {
        @Bean
        public MessageService messageService() {
            return new MessageServiceImpl();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    @Import(SharedBeans.class)
    public static class JdkConfig {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    @Import(SharedBeans.class)
    public static class CglibConfig {
    }

    static void inspect(String label, Object bean) {
        System.out.println(label + " aop=" + AopUtils.isAopProxy(bean));
        System.out.println(label + " jdk="
                + AopUtils.isJdkDynamicProxy(bean));
        System.out.println(label + " cglib="
                + AopUtils.isCglibProxy(bean));
        System.out.println(label + " proxy-is-impl="
                + (bean instanceof MessageServiceImpl));
        System.out.println(label + " target="
                + AopUtils.getTargetClass(bean).getSimpleName());
    }

    public static void main(String[] args) {
        try (var jdk =
                new AnnotationConfigApplicationContext(JdkConfig.class)) {
            MessageService bean = jdk.getBean(MessageService.class);
            inspect("JDK", bean);
            System.out.println("JDK result=" + bean.deliver("A"));
        }

        try (var cglib =
                new AnnotationConfigApplicationContext(CglibConfig.class)) {
            MessageService bean = cglib.getBean(MessageService.class);
            inspect("CGLIB", bean);
            System.out.println("CGLIB result=" + bean.deliver("B"));
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Các dòng do chương trình in theo đúng thứ tự** (chưa tính log của Maven hoặc Spring):

```text
JDK aop=true
JDK jdk=true
JDK cglib=false
JDK proxy-is-impl=false
JDK target=MessageServiceImpl
ADVICE deliver
TARGET deliver A
JDK result=ACK:A
CGLIB aop=true
CGLIB jdk=false
CGLIB cglib=true
CGLIB proxy-is-impl=true
CGLIB target=MessageServiceImpl
ADVICE deliver
TARGET deliver B
CGLIB result=ACK:B
```

### 5.3. Đọc kết quả

Ở **cả hai context**, `SharedBeans.messageService()` khai báo return type `MessageService` và tạo target `MessageServiceImpl`. Nhưng:

- **JDK context:** `isJdkDynamicProxy=true`, object proxy không phải instance của `MessageServiceImpl`; gọi method qua interface vẫn chạy advice.
- **CGLIB context:** `isCglibProxy=true`, proxy là subclass của `MessageServiceImpl`; object proxy là instance của implementation về mặt Java type.
- **Cả hai:** `getTargetClass(bean)` trả tên `MessageServiceImpl` và advice chạy trên `deliver()`.

Cơ chế chọn proxy thay đổi mà không hề thay chữ ký `@Bean`. Đồng thời, một proxy dùng interface không có nghĩa target class đã biến thành interface.

### 5.4. Thí nghiệm thay đổi declared type

Thay đúng một phương thức trong `SharedBeans`:

```java
@Bean
public MessageServiceImpl messageService() {
    return new MessageServiceImpl();
}
```

Đây là **phiên bản thay thế**, không khai báo đồng thời với bản cũ trong cùng context. Khi đó declared type cụ thể hơn, giúp type prediction theo implementation. Nhưng nếu `JdkConfig` vẫn dùng JDK proxy, `MessageServiceImpl` vẫn không phải kiểu của runtime proxy. Nếu application tiêm implementation, nó có thể thất bại sau post-processing. Phải xem cả khai báo bean **và** kiểu proxy hiệu lực.

## 6. Spring suy kiểu bean tại những thời điểm nào?

Trong ứng dụng thực, câu hỏi “Spring biết bean có type nào?” phụ thuộc vào **thời điểm**:

| Giai đoạn | Thông tin quan trọng |
| --- | --- |
| Biên dịch Java | Signature `@Bean` và kiểu biến tại client |
| Đăng ký bean definition | Declared return type, class metadata và các điều kiện đăng ký |
| Dự đoán candidate injection | Kiểu có thể suy ra từ bean definition, factory method, một số BeanPostProcessor |
| Tạo target instance | Runtime type thực sự do `@Bean` hoặc constructor tạo |
| Spring AOP tạo proxy | Proxy strategy; kiểu được công bố cho client |
| Client gọi method | Object reference thực tế; method execution đi qua proxy/interceptor nếu phù hợp |

Ví dụ `@Bean PaymentService service()` làm Spring biết interface trước khi singleton khởi tạo. Spring có thể chỉ biết implementation sau khi method được gọi để tạo instance. Tài liệu Spring cảnh báo type prediction theo kiểu implementation chưa được khai báo có thể phụ thuộc thời điểm singleton ra đời.

Do đó, **truy vấn bean names theo implementation class** lúc khởi động có thể khác sau khi khởi tạo. Điều này cần phân tích theo context thực tế; không nên dựa trên một lần gọi `getBeanNamesForType(Implementation.class)` như kết luận tuyệt đối.

Chọn declared return type theo nhu cầu: interface khi consumer chỉ cần contract, kiểu cụ thể khi container cần dự đoán type cho điểm inject cụ thể; nhưng nếu muốn inject implementation khi có Spring AOP, còn phải bảo đảm proxy cuối cùng tương thích kiểu ấy.

## 7. Dùng công cụ Spring nào để nhận diện đúng lớp?

### 7.1. Runtime class

```java
Object bean = context.getBean("messageService");
Class<?> runtimeClass = bean.getClass();
```

Đây là lớp thực tế của reference mà client nhận. Nếu bean đã được AOP proxy, đây thường là class do JVM/Spring sinh động, **không phải target implementation class**. Tên lớp sinh ra không phải API ổn định; đừng viết logic phụ thuộc vào tiền tố như `$Proxy` hoặc `$$SpringCGLIB$$`.

### 7.2. Kiểm tra Spring AOP proxy và target class

```java
boolean aop = AopUtils.isAopProxy(bean);
boolean jdk = AopUtils.isJdkDynamicProxy(bean);
boolean cglib = AopUtils.isCglibProxy(bean);
Class<?> targetClass = AopUtils.getTargetClass(bean);
```

Đây là **đoạn minh họa thêm** cho ví dụ phần 5, cần `import org.springframework.aop.support.AopUtils;`. Các câu trả lời khác nhau:

- `isAopProxy` hỏi object có phải Spring AOP proxy không.
- `isJdkDynamicProxy` và `isCglibProxy` giúp phân biệt chiến lược tạo proxy.
- `getTargetClass` trả target class mà Spring AOP biết; với object thường, trả class của object đó.

`AopProxyUtils.ultimateTargetClass(bean)` có thể hữu ích khi có những proxy lồng nhau với static target source, nhưng không cần thiết để chẩn đoán ví dụ một proxy thông thường. Cũng không nên nhầm nó với thao tác lấy một object target rồi bypass AOP.

### 7.3. Khi nào không nên dùng ClassUtils.getUserClass?

Tiện ích `ClassUtils.getUserClass(...)` hữu ích để nhận diện class gốc khi đối tượng đã được CGLIB-enhance. Nhưng với **JDK dynamic proxy**, đừng giả định nó luôn suy ra business implementation nằm sau proxy. Muốn tìm target class của Spring AOP proxy, hãy dùng `AopUtils.getTargetClass(bean)`.

### 7.4. BeanFactory.getType không nhất thiết bằng bean.getClass

`applicationContext.getType("messageService")` hỏi Spring về kiểu của bean dưới góc nhìn BeanFactory tại thời điểm truy vấn. `context.getBean("messageService").getClass()` hỏi lớp runtime của object hiện tại. Việc trả về khác nhau có thể liên quan `@Bean` declaration, lifecycle, proxying, `FactoryBean` và type prediction.

Khi chẩn đoán injection không tìm được candidate, kiểm tra cả bean definition lẫn object cuối cùng. Khi chẩn đoán advice, kiểm tra proxy và target class từ Spring AOP utils.

## 8. Những hệ quả thường gặp trong Spring AOP

### 8.1. Proxy JDK làm injection concrete implementation thất bại

Đoạn consumer sau:

```java
@Service
public class BillingFacade {
    private final PaymentServiceImpl paymentService;

    public BillingFacade(PaymentServiceImpl paymentService) {
        this.paymentService = paymentService;
    }
}
```

là **mẫu cần import/scan**, không phải file độc lập. Nếu bean cuối cùng là JDK proxy, constructor yêu cầu `PaymentServiceImpl` không tương thích Java type. Tùy giai đoạn kiểm tra và kiểu khai báo bean, lỗi có thể xuất hiện khi chọn candidate hoặc sau khi Spring tạo proxy.

Thông thường nên inject interface mà client thực sự dùng:

```java
public BillingFacade(PaymentService paymentService) {
    this.paymentService = paymentService;
}
```

Không nên chuyển sang CGLIB chỉ để né một lần cast nếu interface đã đủ phục vụ nghiệp vụ.

### 8.2. CGLIB giữ subtype nhưng vẫn bị giới hạn interception

`proxy instanceof Implementation` là `true` không chứng minh mọi method trên implementation được advice. CGLIB không thể override `final`, `private` method; không thể tạo subclass cho `final class`. Ngoài ra, method `this.inner()` bên trong target không tự đi qua proxy một lần nữa.

### 8.3. Target không có business interface

Một target class không có interface thường cần CGLIB nếu Spring AOP tạo proxy. Cấu hình `proxyTargetClass=false` chỉ có ý nghĩa “không ép class proxy ở nơi interface proxy khả thi”, không phải “cấm CGLIB”.

### 8.4. Spring Framework khác Spring Boot về mặc định

Trong Spring Framework thuần, AOP mặc định chọn JDK proxy nếu target có interface. Spring Boot có thể kích hoạt class-based proxy mặc định qua auto-configuration AOP; trong cấu hình phổ biến property `spring.aop.proxy-target-class=true`. Muốn về chiến lược interface-based khi phù hợp, dùng:

```properties
spring.aop.proxy-target-class=false
```

Nhưng nếu nhiều cấu hình auto-proxy cùng tồn tại, lựa chọn target-class proxy từ nơi khác có thể chi phối. Vì vậy **xác minh trên bean runtime** đáng tin hơn chỉ đọc một property.

### 8.5. CGLIB của @Configuration không nhất thiết là AOP proxy

Một `@Configuration(proxyBeanMethods=true)` có thể được Spring enhance bằng subclass để điều phối lời gọi tới `@Bean` methods. Điều đó khác với proxy do Spring AOP tạo để chạy advisor. Không suy `AopUtils.isAopProxy(bean) == true` chỉ vì tên class chứa chuỗi `CGLIB`.

## 9. Quy trình chẩn đoán lỗi kiểu và proxy

Khi ứng dụng lỗi sau khi thêm `@Aspect` hoặc đổi proxy strategy:

1. **Xác định bean name và declaration**: return type của `@Bean` hoặc class của `@Component` đang là gì?
2. **Xác định lớp thật do factory tạo**: `new ...Impl()` hay component class nào?
3. **Kiểm tra advisor thực sự áp dụng không**: có aspect bean/pointcut nào chọn method của bean?
4. **Lấy bean từ chính ApplicationContext**: không dùng object tự tạo bằng `new` để kết luận về Spring proxy.
5. **Đo loại proxy**: `AopUtils.isAopProxy/isJdkDynamicProxy/isCglibProxy`.
6. **Đo target class**: `AopUtils.getTargetClass(bean)`.
7. **So kiểu injection point**: interface hay implementation? `type.isInstance(bean)` có đúng không?
8. **Đối chiếu type prediction**: `@Bean` return type có quá chung chung cho các injection point đặc biệt không?
9. **Xem cấu hình proxy**: `@EnableAspectJAutoProxy(proxyTargetClass=...)`, Boot properties và các auto-proxy creator khác.
10. **Kiểm tra đường gọi**: có đi qua proxy không, có self-invocation hay method `final/private` không?

Ghi ngắn gọn năm dữ liệu sau khi debug: declared type, target class, runtime proxy kind, requested injection type và method invocation path. Chúng giải quyết phần lớn nhầm lẫn mà không phụ thuộc tên proxy do Spring/JVM sinh.

## 10. Câu hỏi tự kiểm tra

**1.** `@Bean PaymentService paymentService()` trả `new PaymentServiceImpl()`; JDK AOP proxy được tạo. `bean.getClass() == PaymentServiceImpl.class` có đúng không?  
**Trả lời:** Không. `getClass()` trả lớp proxy runtime.

**2.** Cùng bean trên dùng CGLIB. `bean instanceof PaymentServiceImpl` là gì?  
**Trả lời:** `true` vì CGLIB proxy kế thừa target implementation.

**3.** JDK proxy không extends implementation. `AopUtils.getTargetClass(bean)` có phải luôn chỉ là interface không?  
**Trả lời:** Không. Trong ví dụ, Spring AOP biết target implementation là `PaymentServiceImpl`.

**4.** Đổi return type thành `@Bean PaymentServiceImpl paymentService()` có bắt buộc Spring dùng CGLIB không?  
**Trả lời:** Không. Return type khai báo và proxy strategy được quyết định bởi các cơ chế khác nhau.

**5.** Một dependency inject `PaymentServiceImpl`, bean AOP dùng JDK proxy. Lỗi chính là gì?  
**Trả lời:** JDK proxy không assignable sang implementation class; còn declared return type ảnh hưởng việc tìm candidate ở giai đoạn dự đoán kiểu.

**6.** Bean dùng CGLIB và `proxy instanceof PaymentServiceImpl` trả `true`. Có chắc method `private void audit()` chạy advice không?  
**Trả lời:** Không; private method không thể được subclass override.

**7.** Có được dựa vào tiền tố class name để nhận diện JDK/CGLIB proxy không?  
**Trả lời:** Không. Ưu tiên tiện ích `AopUtils` và kiểm tra type assignability theo Java.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB, quan hệ target và các giới hạn proxy.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): declared return type và type prediction.
- [Spring Framework — AopUtils Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): các hàm kiểm tra Spring AOP proxy và target class.
- [Spring Framework 6.2 — AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html): lựa chọn interface/class proxies.
