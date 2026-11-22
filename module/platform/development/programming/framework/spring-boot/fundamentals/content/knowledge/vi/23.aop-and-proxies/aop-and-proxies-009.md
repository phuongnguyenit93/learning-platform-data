# @EnableAspectJAutoProxy so với tự cấu hình AOP của Spring Boot

Trong một ứng dụng Spring Boot, có những hành vi cần áp dụng cho nhiều service mà không nên sao chép vào từng method: ghi log thời gian xử lý, đo metrics, theo dõi lời gọi, kiểm tra một quy tắc chung hoặc đặt một cơ chế giám sát tại ranh giới service. **Aspect-Oriented Programming (AOP)** giúp tách những mối quan tâm xuyên suốt (*cross-cutting concerns*) này khỏi logic nghiệp vụ.

Khi học Spring AOP, lập trình viên thường thấy annotation `@EnableAspectJAutoProxy`. Nhưng trong một ứng dụng Spring Boot có `spring-boot-starter-aop`, nhiều ví dụ `@Aspect` lại hoạt động mà **không hề đặt annotation đó**.

Đây không phải hai hệ thống AOP hoàn toàn khác nhau. Spring Boot thường tự cấu hình hạ tầng **Spring AOP dựa trên proxy** khi các dependency cần thiết có mặt. `@EnableAspectJAutoProxy` là cách Spring Framework cho phép ta chủ động bật hạ tầng xử lý những aspect viết theo cú pháp `@AspectJ`. Vì vậy, khác biệt chủ yếu là **ai đăng ký hạ tầng AOP, khi nào nó được kích hoạt và cách chọn cấu hình proxy**, không phải khác nhau về bản chất advice.

Bài học sẽ giải thích:

- Vì sao `@Aspect` trong Spring Boot có thể hoạt động mà không cần `@EnableAspectJAutoProxy`.
- Annotation của Spring Framework làm gì và khi nào nên khai báo tường minh.
- Vai trò của `spring-boot-starter-aop`, `spring.aop.auto` và `spring.aop.proxy-target-class`.
- Sự khác nhau giữa proxy JDK và CGLIB.
- Những giới hạn của AOP dựa trên proxy, đặc biệt là **self-invocation**.
- Cách bật, tắt, kiểm thử và chẩn đoán các aspect trong một project Spring Boot.

## 1. Trước tiên: Spring AOP giải quyết vấn đề gì?

Giả sử một service tạo đơn hàng và nhiều method khác cũng cần đo thời gian:

~~~java
@Service
public class OrderService {

    public String placeOrder(String customerId) {
        long start = System.nanoTime();
        try {
            // Logic tạo đơn hàng...
            return "order-created-for-" + customerId;
        } finally {
            long elapsed = System.nanoTime() - start;
            System.out.println("Time: " + elapsed);
        }
    }
}
~~~

Nếu mọi service đều chép lại đoạn đo thời gian, code nghiệp vụ bị trộn với logic quan sát hệ thống. Khó đổi cách log, khó kiểm soát quy tắc nào cần được áp dụng và dễ bỏ sót method.

Với Spring AOP, ta có thể định nghĩa một **aspect**:

~~~java
@Aspect
@Component
public class TimingAspect {

    @Around("execution(* com.example.orders..*Service.*(..))")
    public Object measure(ProceedingJoinPoint joinPoint)
            throws Throwable {

        long start = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - start;
            System.out.println(
                    joinPoint.getSignature() + " took " + elapsed + " ns"
            );
        }
    }
}
~~~

Spring có thể tạo một **proxy** bao quanh những service bean phù hợp. Khi caller gọi qua proxy, advice chạy trước/sau lời gọi nghiệp vụ.

~~~text
Consumer / Controller
        |
        v
   Spring AOP proxy
        |
        +--> TimingAspect (@Around)
        |         |
        |         v
        |     target method
        |         |
        +<--------+
        |
        v
     Result
~~~

Điểm quan trọng: Spring AOP thông thường **không chỉnh sửa bytecode của mọi lời gọi trong chương trình**. Nó dùng đối tượng proxy tại ranh giới bean. Đây là nguồn gốc của nhiều giới hạn và lỗi cấu hình sẽ được phân tích ở các phần sau.

## 2. Những thuật ngữ cốt lõi

| Thuật ngữ | Ý nghĩa trong Spring AOP |
| --- | --- |
| **Aspect** | Module gom một hoặc nhiều advice và quy tắc pointcut |
| **Advice** | Logic chạy tại một điểm được chỉ định, ví dụ trước hoặc quanh method |
| **Join point** | Điểm thực thi có thể được tác động; Spring AOP chủ yếu hỗ trợ method execution |
| **Pointcut** | Biểu thức xác định method nào được áp dụng advice |
| **Target** | Object nghiệp vụ mà proxy gọi đến |
| **Proxy** | Object trung gian do Spring tạo để áp dụng advice |
| **Weaving** | Khái niệm kết nối aspect với chương trình; Spring AOP proxy-based khác AspectJ bytecode weaving |
| **Auto-configuration** | Cơ chế Spring Boot đăng ký cấu hình có điều kiện dựa trên classpath, properties và bean hiện có |

Ví dụ:

~~~java
@Around("execution(* com.example.orders..*Service.*(..))")
~~~

Đây là advice dạng **around** và một pointcut expression dùng designator `execution`.

`joinPoint.proceed()` trong advice là lời gọi cho phép thực thi phần tiếp theo trong chain, cuối cùng có thể đến target method. Nếu advice `@Around` không gọi `proceed()`, target có thể không chạy; đây là khả năng mạnh nhưng cần sử dụng có chủ đích.

## 3. @EnableAspectJAutoProxy là annotation của Spring Framework

Annotation:

~~~java
import org.springframework.context.annotation.EnableAspectJAutoProxy;
~~~

thuộc **Spring Framework**, không phải Spring Boot.

Ví dụ:

~~~java
@Configuration
@EnableAspectJAutoProxy
public class AopConfiguration {
}
~~~

Ý nghĩa: yêu cầu Spring đăng ký hạ tầng auto-proxy phù hợp để nhận diện các aspect kiểu `@AspectJ` và tạo proxy cho những Spring bean khớp pointcut.

Một cấu hình Framework thuần có thể gồm:

~~~java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("com.example.orders")
public class ApplicationConfiguration {
}
~~~

Khi tạo `AnnotationConfigApplicationContext` với cấu hình này, Spring có cơ sở để đăng ký các aspect bean và tạo proxy cho các bean mục tiêu.

### 3.1. @EnableAspectJAutoProxy không tự đăng ký mọi aspect

Annotation chỉ kích hoạt cơ chế AOP. Nó **không thay thế component scan** và cũng không tự biến mọi class có `@Aspect` thành bean.

Để Spring phát hiện aspect, có thể dùng:

~~~java
@Aspect
@Component
public class TimingAspect {
    // ...
}
~~~

và bảo đảm package của class nằm trong phạm vi scan.

Hoặc đăng ký aspect bằng `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
public class TimingAspectConfiguration {

    @Bean
    TimingAspect timingAspect() {
        return new TimingAspect();
    }
}
~~~

Trong trường hợp này, `TimingAspect` vẫn cần được đánh dấu `@Aspect`, nhưng không nhất thiết cần `@Component` vì đã có factory method tạo bean.

**Nhớ hai bước riêng:** có hạ tầng auto-proxy và có aspect bean được đăng ký. Thiếu một trong hai, advice có thể không chạy.

### 3.2. Hai thuộc tính thường gặp

`@EnableAspectJAutoProxy` có các thuộc tính quan trọng:

~~~java
@EnableAspectJAutoProxy(
        proxyTargetClass = true,
        exposeProxy = false
)
~~~

- `proxyTargetClass`: có yêu cầu ưu tiên class-based proxy thay vì JDK interface proxy hay không.
- `exposeProxy`: có cho phép lấy proxy hiện tại qua `AopContext.currentProxy()` hay không.

Nếu dùng `@EnableAspectJAutoProxy` đơn lẻ, giá trị mặc định của `proxyTargetClass` là `false` và `exposeProxy` là `false`.

Tuy nhiên, trong ứng dụng có **nhiều nguồn cấu hình auto-proxy**, lựa chọn cuối cùng có thể chịu tác động từ cấu hình khác. Đặc biệt, Spring Boot mặc định thiên về class-based proxies. Không nên suy luận rằng chỉ thêm `@EnableAspectJAutoProxy(proxyTargetClass = false)` sẽ luôn ép toàn bộ ứng dụng Boot chuyển sang JDK proxies.

## 4. Spring Boot làm gì khác?

Spring Boot cung cấp auto-configuration cho AOP thông qua cơ chế của `spring-boot-autoconfigure`, điển hình là `AopAutoConfiguration`.

Khi các dependency AspectJ/Spring AOP cần thiết có trên classpath, tính năng auto-configuration không bị tắt và điều kiện phù hợp, Boot sẽ đăng ký hạ tầng cần thiết để các aspect kiểu `@Aspect` có thể hoạt động.

Vì vậy trong Spring Boot, thường chỉ cần:

1. Có dependency AOP phù hợp.
2. Đăng ký một aspect bean.
3. Đăng ký target bean.
4. Gọi target bean qua proxy do Spring quản lý.

Không cần tự thêm `@EnableAspectJAutoProxy` trong trường hợp thông thường.

Ví dụ lớp main:

~~~java
@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Aspect:

~~~java
@Aspect
@Component
public class TimingAspect {

    @Before("execution(* com.example.orders..*Service.placeOrder(..))")
    public void beforePlaceOrder() {
        System.out.println("Before placeOrder");
    }
}
~~~

Service:

~~~java
@Service
public class DefaultOrderService {

    public String placeOrder(String customerId) {
        return "created-for-" + customerId;
    }
}
~~~

Nếu `spring-boot-starter-aop` đã có trong dependency graph và package scan phù hợp, Boot thường tự bật hạ tầng Spring AOP. Không cần viết:

~~~java
@EnableAspectJAutoProxy
~~~

trên class main.

### 4.1. Spring Boot không tự tạo advice cho logic tùy ý

Auto-configuration chỉ chuẩn bị hạ tầng. Nó không tự biết bạn muốn đo thời gian hay log method nào.

Bạn vẫn phải cung cấp một aspect (hoặc dùng những tính năng do các module khác cung cấp), pointcut và advice có ý nghĩa.

### 4.2. Auto-configuration là có điều kiện

Nếu module cần thiết không có trên classpath, Boot có thể không bật hỗ trợ `@AspectJ` như mong đợi. Nếu đặt property tắt AOP auto-configuration, Boot cũng không đăng ký hạ tầng này theo đường auto-configuration.

Do đó, khi aspect không chạy, cần kiểm tra **dependency**, **bean registration**, **auto-configuration** và **cách gọi qua proxy** trước khi kết luận pointcut sai.

## 5. Dependency: spring-boot-starter-aop gồm những gì?

Với ứng dụng Spring Boot dùng Maven, thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-aop")
}
~~~

Starter mang vào các thành phần cần thiết cho Spring AOP proxy và parsing những pointcut expression kiểu AspectJ, bao gồm Spring AOP và AspectJ Weaver ở dependency graph phù hợp.

Điểm cần phân biệt:

- **Spring AOP** cung cấp proxy, interceptor và integration với Spring bean lifecycle.
- **AspectJ annotations/pointcut parser** cho phép viết `@Aspect`, `@Around`, `@Before` và biểu thức pointcut tương ứng.
- **AspectJ Weaver dependency** có thể có mặt để hỗ trợ cú pháp và các type cần thiết cho Spring AOP, nhưng điều đó **không đồng nghĩa** ứng dụng đang thực hiện compile-time weaving hoặc load-time weaving.

Với một ứng dụng Framework thuần không dùng starter của Boot, bạn phải bảo đảm dependency `spring-aop` và các thư viện AspectJ liên quan phù hợp được đưa vào project. `@EnableAspectJAutoProxy` là một annotation, không tự tải dependency vào Maven/Gradle.

### 5.1. Không cần thêm cùng một dependency nhiều lần

Nếu một starter khác đã kéo `spring-boot-starter-aop` hoặc các module tương ứng vào classpath, không nhất thiết phải khai báo trùng. Tuy nhiên, khi project trực tiếp sử dụng AOP, khai báo rõ starter thường giúp mục đích dependency dễ hiểu hơn.

### 5.2. Không nhầm với aspectj-maven-plugin hay javaagent

Spring AOP proxy-based không yêu cầu compile-time weaving. Nếu dự án dùng `aspectj-maven-plugin`, `ajc` hoặc Java agent phục vụ AspectJ weaving, đó là một cơ chế khác với mặc định của Spring Boot AOP starter.

## 6. Hai con đường cấu hình: so sánh trực tiếp

### 6.1. Cấu hình bằng Spring Framework

~~~java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("com.example.orders")
public class FrameworkAopConfiguration {
}
~~~

Ứng dụng hoặc thư viện chủ động bật hạ tầng auto-proxy. Cách này phù hợp với ứng dụng Spring Framework không dựa vào auto-configuration của Boot hoặc các context tùy chỉnh.

### 6.2. Cấu hình bằng Spring Boot

~~~java
@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Kết hợp dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Boot tự bật AOP qua auto-configuration khi điều kiện phù hợp.

### 6.3. Bảng đối chiếu

| Câu hỏi | `@EnableAspectJAutoProxy` | Spring Boot AOP auto-configuration |
| --- | --- | --- |
| Thuộc về | Spring Framework | Spring Boot |
| Cách bật | Đặt annotation tường minh | Có dependency và điều kiện auto-config phù hợp |
| Có cần viết annotation kích hoạt? | Có, nếu dùng đường cấu hình này | Thường không |
| Có tự scan aspect? | Không thay thế scan | Không thay thế scan |
| Có cần aspect bean? | Có | Có |
| Có dùng Spring AOP proxy? | Có | Có |
| Có tự bật AspectJ bytecode weaving? | Không | Không |
| Cách chọn proxy | `proxyTargetClass` | `spring.aop.proxy-target-class` và cấu hình auto-proxy khác |
| Giá trị proxy target class mặc định riêng | `false` | `true` trong cấu hình Boot thông thường |
| Cách tắt tự động | Bỏ annotation/đổi cấu hình liên quan | `spring.aop.auto=false` |
| Phù hợp nhất | Spring Framework thuần, context được kiểm soát tường minh | Phần lớn ứng dụng Spring Boot có starter AOP |

Hai con đường có thể cùng xuất hiện trong một ứng dụng nhưng thường không cần thiết. Khi chúng cùng cấu hình hạ tầng auto-proxy, lựa chọn cuối cùng cần xét trên cấu hình tổng thể của context, không chỉ một annotation riêng lẻ.

## 7. Các property quan trọng của Spring Boot AOP

Spring Boot có hai property thường được hỏi nhất:

~~~properties
spring.aop.auto=true
spring.aop.proxy-target-class=true
~~~

### 7.1. spring.aop.auto

Property:

~~~properties
spring.aop.auto=true
~~~

điều khiển việc Spring Boot tự cấu hình hạ tầng Spring AOP khi dependency/điều kiện cần thiết có mặt.

Giá trị mặc định trong những ứng dụng Boot thông thường là bật tính năng auto-configuration nếu classpath phù hợp.

Muốn tắt AOP theo **đường auto-configuration của Boot**:

~~~properties
spring.aop.auto=false
~~~

Điểm rất quan trọng: nếu ứng dụng **chủ động khai báo** `@EnableAspectJAutoProxy` ở một cấu hình khác, property `spring.aop.auto=false` không thể được xem như công tắc tổng tuyệt đối “cấm mọi proxy AOP”. Nó tắt đường cấu hình tự động của Boot; một cấu hình Spring Framework tường minh vẫn có thể đăng ký hạ tầng AOP.

Tương tự, một số cơ chế proxy riêng như transaction hoặc method security có lifecycle/kích hoạt riêng; `spring.aop.auto=false` không nên được hiểu là “vô hiệu hóa tất cả proxy của Spring”.

### 7.2. spring.aop.proxy-target-class

Spring Boot thường mặc định sử dụng **class-based proxies**:

~~~properties
spring.aop.proxy-target-class=true
~~~

Nếu muốn ưu tiên JDK dynamic proxy khi target có interface:

~~~properties
spring.aop.proxy-target-class=false
~~~

Lưu ý: đặt `false` không bảo đảm mọi bean đều là JDK proxy. Nếu một target không cung cấp interface phù hợp, Spring AOP có thể phải dùng class-based proxy.

### 7.3. application.yml tương đương

~~~yaml
spring:
  aop:
    auto: true
    proxy-target-class: false
~~~

YAML chỉ là một cách biểu diễn property. Có thể override bằng environment, command-line hoặc profile-specific configuration theo thứ tự ưu tiên của Spring Boot.

### 7.4. Ma trận hành vi thực tế

| Dependency AOP | `spring.aop.auto` | Có `@EnableAspectJAutoProxy` tường minh | Kỳ vọng |
| --- | --- | --- | --- |
| Có | Mặc định/bật | Không | Boot thường tự cấu hình AOP |
| Có | Tắt | Không | Boot không tự bật hạ tầng `@AspectJ` qua AopAutoConfiguration |
| Có | Tắt | Có | Cấu hình Spring Framework tường minh vẫn có thể bật `@AspectJ` proxying |
| Không đủ | Bật | Không | Thiếu classpath có thể khiến auto-config không áp dụng |
| Không đủ | Tắt | Có | Annotation không tự giải quyết dependency thiếu; context có thể lỗi |

Ma trận chỉ tập trung vào hạ tầng aspect kiểu `@AspectJ`. Những tính năng như transaction advice có thể được cung cấp bởi các cấu hình khác và cần xét riêng.

## 8. Spring AOP tạo proxy bằng JDK hay CGLIB?

Proxy là đối tượng đứng giữa caller và target. Spring có hai cơ chế phổ biến:

**JDK dynamic proxy**: proxy triển khai những interface phù hợp của target.

**CGLIB class-based proxy**: proxy dựa trên subclass của target class (khi class và method cho phép).

Ví dụ contract:

~~~java
public interface OrderService {
    String placeOrder(String customerId);
}
~~~

Implementation:

~~~java
@Service
public class DefaultOrderService implements OrderService {

    @Override
    public String placeOrder(String customerId) {
        return "order-created-for-" + customerId;
    }
}
~~~

Cả JDK và class-based proxy đều có thể được dùng trong những điều kiện thích hợp, nhưng tính chất của object được inject khác nhau.

### 8.1. Khi dùng JDK dynamic proxy

Nếu bean được proxy bằng JDK, object proxy triển khai `OrderService`. Injection qua interface hoạt động:

~~~java
@Service
public class CheckoutService {

    private final OrderService orderService;

    public CheckoutService(OrderService orderService) {
        this.orderService = orderService;
    }
}
~~~

Nhưng cố inject `DefaultOrderService` trực tiếp có thể thất bại, vì JDK proxy không nhất thiết là instance của class implementation.

### 8.2. Khi dùng class-based proxy

Với class-based proxy, đối tượng thường là subclass proxy của `DefaultOrderService`. Điều này có thể cho phép injection theo implementation type, dù thiết kế phụ thuộc interface vẫn thường tốt hơn.

Spring Boot mặc định chọn class-based proxy cho AOP theo property của Boot. Đừng giả định ứng dụng Boot có interface thì chắc chắn dùng JDK proxy.

### 8.3. Class final và method final

CGLIB dựa trên subclass/override method. Vì vậy:

- Một class `final` không thể được subclass theo cách này.
- Method `final` không thể bị override để chặn lời gọi bằng class-based proxy.
- Method `private` không thể bị override bởi subclass.
- Method `static` không phải method instance được chặn qua proxy như một method target thông thường.

Nếu cần AOP với class `final` có interface, JDK proxy dựa trên interface có thể phù hợp cho những method được công bố qua interface.

Nếu một method không nằm trong phạm vi được proxy/intercept, pointcut dù nhìn đúng tên vẫn không làm advice chạy cho lời gọi đó.

### 8.4. Bảng lựa chọn

| Đặc điểm | JDK proxy | CGLIB proxy |
| --- | --- | --- |
| Phụ thuộc interface | Thường cần interface phù hợp | Có thể proxy class không có interface |
| Hình thức | Proxy triển khai interface | Proxy dạng subclass |
| Inject bằng interface | Phù hợp | Phù hợp nếu class triển khai interface |
| Inject bằng concrete class | Có thể không phù hợp | Thường phù hợp nếu target proxy được |
| Target class `final` | Có thể dùng qua interface | Không subclass được |
| Intercept method `final` qua subclass | Không áp dụng theo cơ chế này | Không intercept được |
| Property Boot liên quan | `spring.aop.proxy-target-class=false` | `spring.aop.proxy-target-class=true` |

Các giới hạn còn phụ thuộc khả năng truy cập method, thiết kế class và version Spring. Đối với AOP ứng dụng, cách an toàn là đặt advice trên method instance có thể được proxy và gọi qua Spring bean.

## 9. Vì sao đặt @EnableAspectJAutoProxy(proxyTargetClass=false) chưa chắc đổi được proxy của Boot?

Giả sử project Boot có:

~~~java
@SpringBootApplication
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class Application {
}
~~~

Và trong cấu hình mặc định Boot:

~~~properties
spring.aop.proxy-target-class=true
~~~

Hai nguồn này cùng tham gia cấu hình hạ tầng auto-proxy. Spring có cơ chế hợp nhất/escalate những auto-proxy creator settings. Khi một nguồn yêu cầu class proxy mạnh hơn, việc đặt `proxyTargetClass=false` ở một nơi khác không nhất thiết “hủy” lựa chọn đó.

Vì vậy, nếu mục tiêu là dùng JDK proxies trong ứng dụng Boot, hãy kiểm soát property Boot một cách tường minh:

~~~properties
spring.aop.proxy-target-class=false
~~~

Sau đó kiểm tra bằng API thay vì dựa trên suy đoán:

~~~java
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
~~~

Nếu application vẫn có một configuration khác yêu cầu class-based proxy, phải tìm nguồn cấu hình đó. Đừng cộng thêm nhiều annotation trái chiều rồi giả định cấu hình khai báo sau cùng sẽ thắng.

## 10. Ví dụ Spring Boot hoạt động mà không có @EnableAspectJAutoProxy

Giả sử package:

~~~text
src/main/java/com/example/orders/
├── OrderApplication.java
├── OrderService.java
├── DefaultOrderService.java
├── OrderController.java
└── LoggingAspect.java
~~~

### 10.1. Dependency

Dự án Spring Boot đã có parent/BOM tương ứng, thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Không cần `@EnableAspectJAutoProxy`.

### 10.2. Application

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

### 10.3. Service contract

~~~java
package com.example.orders;

public interface OrderService {
    String placeOrder(String customerId);
}
~~~

### 10.4. Service implementation

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;

@Service
public class DefaultOrderService implements OrderService {

    @Override
    public String placeOrder(String customerId) {
        return "order-created-for-" + customerId;
    }
}
~~~

### 10.5. Logging aspect

~~~java
package com.example.orders;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class LoggingAspect {

    private static final Logger log =
            LoggerFactory.getLogger(LoggingAspect.class);

    @Around("execution(* com.example.orders..*OrderService.placeOrder(..))")
    public Object logDuration(ProceedingJoinPoint joinPoint)
            throws Throwable {

        long start = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long durationNanos =
                    System.nanoTime() - start;

            log.info(
                    "Method {} completed in {} ns",
                    joinPoint.getSignature().toShortString(),
                    durationNanos
            );
        }
    }
}
~~~

Ở đây `@Around` được gắn vào lời gọi method `placeOrder` trên implementation có tên kết thúc bằng `OrderService`. Vì class target `DefaultOrderService` thỏa pattern và là Spring bean, advice có thể được áp dụng khi method được gọi qua proxy.

Trong production, nên cân nhắc metrics/tracing library phù hợp, dữ liệu nhạy cảm không được log, và mức độ chi tiết logging để tránh chi phí cho mỗi request.

### 10.6. Controller gọi service qua container

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/demo/order")
    public String createOrder(
            @RequestParam String customerId) {
        return orderService.placeOrder(customerId);
    }
}
~~~

Có thể chạy ứng dụng rồi gọi:

~~~bash
curl "http://localhost:8080/demo/order?customerId=abc"
~~~

Controller nhận `OrderService` từ Spring, do đó lời gọi đi qua bean được proxy. Aspect được đăng ký bằng `@Component`, nằm trong phạm vi component scan và tự được hạ tầng AOP của Boot xem xét.

### 10.7. Luồng thực hiện

~~~text
GET /demo/order
       |
       v
OrderController
       |
       v
OrderService proxy
       |
       v
LoggingAspect.logDuration()
       |
       v
DefaultOrderService.placeOrder()
       |
       v
Trả kết quả; advice ghi thời gian
       |
       v
HTTP response
~~~

**Không có `@EnableAspectJAutoProxy` ở class main.** Khi starter và auto-configuration hoạt động, đó là hành vi bình thường của Spring Boot.

## 11. Cùng ví dụ, nếu muốn chủ động bật bằng @EnableAspectJAutoProxy

Nếu không dùng auto-configuration để bật AOP hoặc đang thử nghiệm với Spring Framework thuần, có thể khai báo tường minh:

~~~java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("com.example.orders")
public class ManualAopConfiguration {
}
~~~

Hoặc trong một ứng dụng Boot cần cấu hình cụ thể:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(
        proxyTargetClass = true,
        exposeProxy = false
)
public class ExplicitAopConfiguration {
}
~~~

Nhưng trong một ứng dụng Boot đã có `spring-boot-starter-aop` và AOP auto-configuration, annotation này thường **không cần thiết**.

Nếu dùng nó vì muốn điều chỉnh proxy strategy, cần hiểu tương tác giữa `proxyTargetClass` và property Boot. Nếu chỉ muốn đổi từ class proxy sang JDK proxy trong app Boot, `spring.aop.proxy-target-class=false` thường là cấu hình rõ ràng và đồng nhất hơn.

### 11.1. Đừng thêm annotation chỉ để “cho chắc”

Một cấu hình có cả:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = false)
~~~

và:

~~~properties
spring.aop.proxy-target-class=true
~~~

gây khó hiểu cho người đọc. Khi một project dùng auto-configuration, hãy ưu tiên extension/configuration point của Boot, trừ khi có lý do kỹ thuật rõ ràng để bật thủ công.

### 11.2. Spring Framework thuần thực sự khác ở bước bootstrap

Ví dụ không dùng `SpringApplication`:

~~~java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(
                     ManualAopConfiguration.class
             )) {

    OrderService service = context.getBean(OrderService.class);
    System.out.println(service.placeOrder("customer-1"));
}
~~~

Ở đây không có Spring Boot auto-configuration trừ khi bạn chủ động import nó. `@EnableAspectJAutoProxy` là cách rõ ràng để bật xử lý aspect kiểu `@AspectJ` trong context do bạn tự dựng.

## 12. Điểm giới hạn quan trọng nhất: self-invocation

Spring AOP dựa trên proxy, vì vậy lời gọi chỉ được advice chặn khi đi **qua proxy**.

Xem service:

~~~java
@Service
public class OrderService {

    public void placeOrder() {
        validateOrder();
        // Lưu đơn hàng...
    }

    public void validateOrder() {
        // Kiểm tra dữ liệu...
    }
}
~~~

Giả sử một aspect có pointcut chỉ dành cho `validateOrder()`.

Nếu controller gọi:

~~~java
orderService.validateOrder();
~~~

thông qua bean proxy, advice có thể chạy.

Nhưng bên trong `placeOrder()`, lời gọi:

~~~java
validateOrder();
~~~

tương đương `this.validateOrder()` trên target. Lời gọi nội bộ này thường **không đi qua proxy**, nên advice của `validateOrder()` không chạy cho đường gọi đó.

~~~text
Controller -> proxy -> target.placeOrder()
                            |
                            +--> this.validateOrder()
                                 (bỏ qua proxy)
~~~

### 12.1. Vì sao thêm @EnableAspectJAutoProxy không sửa được?

Vì vấn đề không nằm ở việc thiếu annotation kích hoạt AOP, mà ở **đường đi của lời gọi**. Dù proxy đã được tạo đúng, target gọi method của chính nó bằng `this` vẫn bỏ qua proxy.

Tương tự, chuyển qua `spring.aop.proxy-target-class=true` không biến toàn bộ self-invocation thành lời gọi đi qua proxy.

### 12.2. Giải pháp ưu tiên: tách trách nhiệm sang bean khác

~~~java
@Service
public class OrderValidator {

    public void validate(String orderId) {
        // Kiểm tra đơn hàng...
    }
}
~~~

~~~java
@Service
public class OrderService {

    private final OrderValidator validator;

    public OrderService(OrderValidator validator) {
        this.validator = validator;
    }

    public void placeOrder(String orderId) {
        validator.validate(orderId);
        // Lưu đơn hàng...
    }
}
~~~

Khi `OrderValidator` là bean được Spring proxy và `OrderService` inject nó từ context, lời gọi `validator.validate(orderId)` có thể đi qua proxy và kích hoạt advice.

Đây là cách thiết kế dễ hiểu, ít phụ thuộc vào AOP infrastructure trong logic nghiệp vụ.

### 12.3. Giải pháp khác: gọi qua self proxy có chủ đích

Trong một số tình huống, có thể inject một proxy của chính kiểu service thông qua một abstraction/lazy provider được thiết kế cẩn thận. Tuy nhiên, phương án này dễ tạo circular dependency hoặc phức tạp lifecycle.

Không nên xem self-injection là hướng mặc định nếu có thể tách method được intercept sang một bean chuyên trách.

## 13. exposeProxy và AopContext.currentProxy()

`@EnableAspectJAutoProxy` có tùy chọn:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
~~~

Khi proxy hiện tại được expose, một method đang được gọi qua Spring AOP proxy có thể truy cập proxy đó bằng:

~~~java
AopContext.currentProxy()
~~~

Ví dụ:

~~~java
public interface OrderOperations {
    void placeOrder(String id);
    void validateOrder(String id);
}
~~~

~~~java
@Service
public class DefaultOrderOperations implements OrderOperations {

    @Override
    public void placeOrder(String id) {
        ((OrderOperations) AopContext.currentProxy())
                .validateOrder(id);
    }

    @Override
    public void validateOrder(String id) {
        // ...
    }
}
~~~

Ví dụ chỉ có ý nghĩa khi:

- `exposeProxy=true` đã được kích hoạt đối với proxy tương ứng.
- Lời gọi ban đầu vào `placeOrder` thực sự đi qua Spring AOP proxy.
- Có proxy hiện tại trong ngữ cảnh thực thi.
- Kiểu cast phù hợp với proxy (đặc biệt nếu là JDK proxy thì nên cast theo interface).

Nếu không có proxy đang được expose, `AopContext.currentProxy()` có thể ném `IllegalStateException`.

### 13.1. Vì sao đây không phải lựa chọn thiết kế ưu tiên?

- Logic nghiệp vụ bị phụ thuộc vào Spring AOP API.
- Lời gọi cần proxy exposure, có thêm overhead và điều kiện runtime.
- Cách truyền ngữ cảnh hiện tại thường gắn với thread đang thực thi.
- Việc sử dụng từ async task hoặc thread khác không nên dựa vào proxy hiện tại.
- Code khó test độc lập nếu không tạo Spring proxy context.

Vì vậy, khi có thể, nên tách hành vi cần advice sang một bean khác. `exposeProxy` là một công cụ đặc biệt để xử lý tình huống khó, không phải giải pháp tự động cho mọi self-invocation.

### 13.2. Có property spring.aop.expose-proxy không?

Các property thông dụng được Spring Boot hỗ trợ để điều khiển hạ tầng AOP ở đây là `spring.aop.auto` và `spring.aop.proxy-target-class`. Không nên tự giả định mọi thuộc tính của `@EnableAspectJAutoProxy` đều có property Boot tương ứng.

Nếu dự án cần `exposeProxy`, hãy cấu hình tường minh bằng API phù hợp và kiểm tra tương tác với hạ tầng proxy đang tồn tại.

## 14. @Aspect không đồng nghĩa AspectJ weaving

Tên `@EnableAspectJAutoProxy` dễ làm người mới hiểu rằng annotation này kích hoạt toàn bộ khả năng của AspectJ.

Cần phân biệt:

**Spring AOP theo phong cách `@AspectJ`:**

- Dùng annotation `@Aspect` và pointcut expression kiểu AspectJ.
- Advice áp dụng qua Spring-managed proxy.
- Chủ yếu chặn method execution trên bean được Spring quản lý.
- Không tự thay đổi mọi lời gọi trong bytecode.

**AspectJ weaving đầy đủ:**

- Có thể liên kết aspect vào bytecode ở compile time hoặc load time bằng cơ chế weaving phù hợp.
- Hỗ trợ nhiều loại join point hơn Spring AOP, ví dụ construction hoặc field access theo tính năng của AspectJ.
- Cần cách cấu hình build/runtime khác (compiler/weaver, agent hoặc tích hợp thích hợp).

Đặt `@EnableAspectJAutoProxy` **không tự bật AspectJ compile-time weaving hay load-time weaving**.

### 14.1. Không chặn constructor/field bằng Spring AOP như method execution

Pointcut expression cho Spring AOP phổ biến là:

~~~java
execution(* com.example.orders..*Service.*(..))
~~~

Điều này gắn với method execution. Nếu bạn cần intercept việc tạo object bằng `new`, field get/set hoặc những join point không được Spring AOP hỗ trợ, cần xem xét AspectJ weaving hoặc một thiết kế khác.

### 14.2. Spring bean boundary

Một object tạo trực tiếp:

~~~java
OrderService service = new OrderService();
service.placeOrder();
~~~

không tự trở thành Spring AOP proxy chỉ vì class có `@Service` hoặc package có `@Aspect`.

Để nhận advice theo Spring AOP, hãy lấy service từ Spring container hoặc sử dụng một cách tạo proxy tường minh thích hợp.

### 14.3. Không nên dùng weaving chỉ để “sửa” một thiết kế self-invocation đơn giản

Weaving có thể giải quyết một số hạn chế của proxy-based AOP, nhưng làm build, deployment và debugging phức tạp hơn. Trước hết hãy xem có thể tách logic thành các bean rõ ràng và gọi qua proxy như thiết kế Spring thông thường không.

## 15. Những method nào khó hoặc không thể được advice chặn?

Trong Spring AOP proxy-based, các trường hợp cần chú ý gồm:

- **Private methods**: không thể được intercept theo đường proxy override thông thường.
- **Final methods** với class-based proxy: không thể override, nên không thể được intercept qua CGLIB subclass theo cách này.
- **Final classes**: không thể subclass cho CGLIB proxy.
- **Static methods**: không đi qua instance proxy như method gọi trên bean.
- **Self-invocation**: gọi `this.someMethod()` bên trong target thường bypass proxy.
- **Object tạo bằng `new`**: không do Spring quản lý nên không tự được proxy.
- **Method ngoài interface khi dùng JDK proxy**: không thể được gọi qua JDK proxy như một method không thuộc interface đó.
- **Phạm vi component scan sai**: aspect hoặc target bean không được đăng ký.
- **Pointcut không khớp**: method có thể được proxy nhưng advice cụ thể vẫn không áp dụng.

Không phải mọi lỗi “AOP không chạy” đều do thiếu `@EnableAspectJAutoProxy`.

## 16. @Configuration(proxyBeanMethods=false) có liên quan không?

Một nguồn nhầm lẫn khác là:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfiguration {
}
~~~

Thuộc tính `proxyBeanMethods` của `@Configuration` nói về việc Spring có dùng cơ chế enhancement để chặn các lời gọi `@Bean` method trong class cấu hình nhằm duy trì semantics của bean container hay không.

Nó **không phải** property bật/tắt AOP advice cho toàn bộ service.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfiguration {
}
~~~

không tự làm mất advice của `LoggingAspect` trên `OrderService` khi hạ tầng AOP của ứng dụng vẫn hoạt động.

Cùng từ “proxy” được dùng ở nhiều tầng của Spring, nhưng không phải lúc nào cũng là cùng một cơ chế hoặc mục đích.

## 17. @Transactional, @Async, @Cacheable có phụ thuộc trực tiếp @EnableAspectJAutoProxy không?

Các tính năng này thường cũng dựa trên proxy, nhưng mỗi tính năng có **hạ tầng kích hoạt riêng**.

Ví dụ:

~~~java
@Transactional
public void transferMoney() {
    // ...
}
~~~

~~~java
@Async
public void sendMessage() {
    // ...
}
~~~

~~~java
@Cacheable("catalog")
public Product findProduct(String id) {
    // ...
}
~~~

Điểm phân biệt:

- Transaction management thường được bật/cấu hình qua hạ tầng giao dịch của Spring và auto-configuration liên quan trong Boot.
- `@Async` cần hạ tầng async, thường là `@EnableAsync` hoặc một cơ chế cấu hình phù hợp; không phải cứ có AOP starter là mọi `@Async` tự hoạt động.
- Cache abstraction cần caching được bật qua `@EnableCaching` và có cache manager phù hợp; Boot có thể auto-configure cache manager, nhưng phải phân biệt điều đó với việc kích hoạt caching advice.
- Method security có cấu hình riêng, ví dụ `@EnableMethodSecurity` trong các ứng dụng Spring Security hiện đại.

Thêm `@EnableAspectJAutoProxy` **không mặc nhiên bật tất cả** transaction, async, caching và security.

### 17.1. Vì sao self-invocation vẫn liên quan?

Dù mỗi tính năng có cơ chế kích hoạt riêng, khi implementation dùng Spring proxy, lời gọi nội bộ `this.method()` thường gặp cùng vấn đề bypass proxy.

Ví dụ:

~~~java
@Service
public class BillingService {

    public void process() {
        saveInvoice(); // Lời gọi nội bộ có thể bypass transaction proxy.
    }

    @Transactional
    public void saveInvoice() {
        // ...
    }
}
~~~

Khi `process()` gọi `saveInvoice()` bằng `this`, transaction advice có thể không được kích hoạt cho lời gọi nội bộ. Đừng thêm `@EnableAspectJAutoProxy` rồi kỳ vọng vấn đề biến mất; hãy thiết kế boundary bean và transaction phù hợp.

### 17.2. Proxy creator có thể được chia sẻ giữa nhiều tính năng

Spring có thể kết hợp nhiều advisor từ AOP, transaction và các module khác trên cùng một proxy. Cấu hình proxy target class ở cấp hạ tầng có thể tác động rộng hơn một aspect cụ thể. Vì vậy thay đổi proxy strategy nên được kiểm tra ở phạm vi ứng dụng, không chỉ một service.

## 18. Ordering khi có nhiều aspect

Nếu hai aspect cùng khớp một method, thứ tự thực thi có thể quan trọng.

Ví dụ một aspect ghi log và một aspect theo dõi metrics:

~~~java
@Aspect
@Component
@Order(10)
public class LoggingAspect {
    // Advice ghi log.
}
~~~

~~~java
@Aspect
@Component
@Order(20)
public class MetricsAspect {
    // Advice đo metrics.
}
~~~

Theo thứ tự ưu tiên thông thường của Spring, giá trị order nhỏ hơn có precedence cao hơn.

Đối với around advice, aspect có precedence cao hơn thường chạy **trước khi đi vào** lời gọi và chạy **sau cùng khi thoát ra** theo kiểu bao quanh:

~~~text
LoggingAspect (order 10) before
    MetricsAspect (order 20) before
        Target method
    MetricsAspect after
LoggingAspect after
~~~

Khi aspect phối hợp với transaction hoặc caching advisor, cần xét order của cả advisor khác ngoài các aspect người dùng định nghĩa.

### 18.1. Đừng dùng order để sửa pointcut không khớp

Nếu một advice không chạy vì self-invocation hoặc bean chưa được proxy, thêm `@Order` không làm nó xuất hiện. Ordering chỉ có ý nghĩa sau khi advisor/pointcut đã thực sự áp dụng.

### 18.2. Đừng dựa vào thứ tự không được khai báo

Nếu thứ tự thực thi quan trọng đối với tính đúng đắn, hãy khai báo chính sách rõ ràng và kiểm thử, thay vì dựa vào thứ tự class scan hoặc tên file Java.

## 19. Kiểm tra proxy bằng AopUtils

Khi chẩn đoán, có thể truy vấn đối tượng bean:

~~~java
import org.springframework.aop.support.AopUtils;
~~~

Ví dụ:

~~~java
@Component
public class ProxyReporter implements ApplicationRunner {

    private final OrderService orderService;

    public ProxyReporter(OrderService orderService) {
        this.orderService = orderService;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "isAopProxy: "
                        + AopUtils.isAopProxy(orderService)
        );

        System.out.println(
                "isJdkDynamicProxy: "
                        + AopUtils.isJdkDynamicProxy(orderService)
        );

        System.out.println(
                "isCglibProxy: "
                        + AopUtils.isCglibProxy(orderService)
        );

        System.out.println(
                "targetClass: "
                        + AopUtils.getTargetClass(orderService).getName()
        );
    }
}
~~~

Nếu `isAopProxy` trả `false`, bean đó không phải Spring AOP proxy theo phép kiểm tra hiện tại. Điều này **không tự động** chứng minh hạ tầng AOP bị tắt: có thể không có advisor nào áp dụng lên bean đó, hoặc bạn đang quan sát object không phải bean proxy.

Nếu `isAopProxy` trả `true` nhưng advice không chạy ở một method cụ thể, hãy kiểm tra pointcut, visibility, final method, self-invocation và đường gọi.

### 19.1. Không dùng getClass() để đoán kiểu gốc

Một proxy có thể có class sinh động với tên khác target. `orderService.getClass()` không nhất thiết là `DefaultOrderService.class`.

Khi cần tìm target class trong tình huống chẩn đoán, `AopUtils.getTargetClass(bean)` thường hữu ích hơn.

### 19.2. Phân biệt proxy tồn tại và pointcut match

Một bean có thể có proxy vì transaction hoặc advisor khác, trong khi aspect logging của bạn lại không khớp method. Vì vậy, thấy proxy tồn tại chưa đủ để khẳng định advice đang kiểm tra chắc chắn chạy.

Cần quan sát lời gọi thực tế hoặc viết test đếm số lần advice được kích hoạt.

## 20. Kiểm thử aspect trong một Spring Boot context

Một kiểm thử AOP có ý nghĩa cần gọi method **qua bean proxy**, không gọi thủ công method của aspect bằng Java thuần.

### 20.1. Aspect dùng counter để test

Ví dụ aspect kiểm tra lời gọi:

~~~java
package com.example.orders;

import java.util.concurrent.atomic.AtomicInteger;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class InvocationCountAspect {

    private final AtomicInteger invocations =
            new AtomicInteger();

    @Before("execution(* com.example.orders..*OrderService.placeOrder(..))")
    public void count(JoinPoint joinPoint) {
        invocations.incrementAndGet();
    }

    public int count() {
        return invocations.get();
    }
}
~~~

`AtomicInteger` cho phép tăng counter an toàn khi method được gọi đồng thời. Đây là công cụ minh họa cho test; trong hệ thống production, metrics library phù hợp thường hữu ích hơn việc giữ một counter trong singleton aspect.

### 20.2. Test với @SpringBootTest

~~~java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.aop.support.AopUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AopIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private InvocationCountAspect aspect;

    @Test
    void callsAspectAroundProxiedBean() {
        assertThat(AopUtils.isAopProxy(orderService)).isTrue();

        int before = aspect.count();

        orderService.placeOrder("customer-123");

        assertThat(aspect.count()).isEqualTo(before + 1);
    }
}
~~~

Test cần Spring Boot test dependencies, aspect trên classpath và đúng configuration/component scan. Trong một test suite lớn, nếu counter singleton bị nhiều test cùng thay đổi song song, cần cô lập context/fixture hoặc dùng chiến lược đo phù hợp để tránh test không ổn định.

### 20.3. Kiểm tra proxy type khi thay property

Với Boot default:

~~~properties
spring.aop.proxy-target-class=true
~~~

có thể kiểm tra:

~~~java
assertThat(AopUtils.isCglibProxy(orderService)).isTrue();
~~~

Khi dùng JDK proxy:

~~~properties
spring.aop.proxy-target-class=false
~~~

nếu target có interface phù hợp và không có nguồn cấu hình khác ép class proxy, có thể kiểm tra:

~~~java
assertThat(AopUtils.isJdkDynamicProxy(orderService)).isTrue();
~~~

Cần chú ý rằng test có thể nhìn thấy proxy do các advisor khác tạo; hãy chọn một bean đơn giản có thể kiểm soát được trong test.

### 20.4. Test khi tắt AOP auto-configuration

Có thể dùng test context chỉ bật:

~~~properties
spring.aop.auto=false
~~~

và không có cấu hình `@EnableAspectJAutoProxy` tường minh. Trong điều kiện phù hợp, aspect bean có thể vẫn tồn tại trong context nhưng các method không được proxy bởi hạ tầng `@AspectJ` do Boot tự cấu hình.

Nếu test vẫn có proxy, hãy kiểm tra các hạ tầng khác như transaction hoặc một cấu hình auto-proxy tường minh. Không kết luận ngay property đã bị bỏ qua.

## 21. Kiểm thử với Spring Framework thuần

Nếu muốn tách hành vi Framework khỏi Boot, có thể tạo context nhỏ chủ động bật AOP:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class ManualAopTestConfiguration {

    @Bean
    OrderService orderService() {
        return new DefaultOrderService();
    }

    @Bean
    InvocationCountAspect invocationCountAspect() {
        return new InvocationCountAspect();
    }
}
~~~

Sau đó tạo context:

~~~java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(
                     ManualAopTestConfiguration.class
             )) {

    OrderService service = context.getBean(OrderService.class);

    assertThat(AopUtils.isAopProxy(service)).isTrue();

    service.placeOrder("customer-1");

    InvocationCountAspect aspect =
            context.getBean(InvocationCountAspect.class);

    assertThat(aspect.count()).isEqualTo(1);
}
~~~

Ví dụ này giả định `DefaultOrderService` có constructor không tham số, và các class từ ví dụ trước được đặt trong phạm vi package/visibility tương ứng.

Bài kiểm thử chỉ dựa vào một Spring application context do bạn chủ động dựng. Nó minh họa rằng `@EnableAspectJAutoProxy` có thể dùng mà không cần `SpringApplication` hoặc Boot auto-configuration.

## 22. Debug: aspect không chạy thì tìm ở đâu?

Một quy trình chẩn đoán hợp lý:

### 22.1. Kiểm tra dependency

Dự án có `spring-boot-starter-aop` hoặc tối thiểu các module Spring AOP và AspectJ cần thiết không?

Nếu không, annotation `@Aspect` có thể compile được do một dependency lẻ, nhưng hạ tầng auto-configuration vẫn không hoạt động như mong đợi.

### 22.2. Kiểm tra auto-configuration

Trong Spring Boot:

~~~properties
spring.aop.auto=true
~~~

hoặc bỏ property để dùng giá trị mặc định khi các điều kiện phù hợp.

Nếu thấy `spring.aop.auto=false` trong profile, environment hoặc command-line, Boot có thể không tự bật hạ tầng `@AspectJ`.

Có thể bật debug startup:

~~~bash
java -jar application.jar --debug
~~~

Báo cáo điều kiện của Boot có thể giúp nhận biết vì sao `AopAutoConfiguration` có hoặc không được áp dụng. Nếu Actuator conditions endpoint được bật và bảo vệ đúng cách, nó cũng có thể hỗ trợ chẩn đoán condition evaluation.

### 22.3. Kiểm tra aspect là bean chưa

Class chỉ có:

~~~java
@Aspect
public class TimingAspect {
}
~~~

chưa bảo đảm được component scan đăng ký. Thêm `@Component` hoặc cung cấp `@Bean` và kiểm tra package scan.

### 22.4. Kiểm tra target là bean chưa

Nếu gọi:

~~~java
new DefaultOrderService().placeOrder("x");
~~~

lời gọi đó không đi qua Spring proxy. Hãy inject bean do context quản lý.

### 22.5. Kiểm tra pointcut

Ví dụ:

~~~java
@Before("execution(* com.example.billing..*Service.*(..))")
~~~

không khớp service thực tế nằm ở `com.example.orders`.

Hãy đối chiếu package, class, method name và tham số. Một pointcut quá rộng có thể chặn ngoài ý muốn; một pointcut quá hẹp có thể không chạy.

### 22.6. Kiểm tra lời gọi có đi qua proxy không

Dùng `AopUtils.isAopProxy(bean)`. Nếu proxy có mặt nhưng lời gọi từ một method khác trong cùng class, self-invocation có thể bỏ qua advice.

### 22.7. Kiểm tra method có thể intercept không

`final`, `private`, `static`, target không được quản lý hoặc method không qua interface với JDK proxy đều có thể ảnh hưởng.

### 22.8. Kiểm tra có cấu hình proxy khác không

Nếu JDK/CGLIB không như dự kiến, tìm:

~~~text
spring.aop.proxy-target-class
@EnableAspectJAutoProxy
@EnableTransactionManagement
@EnableCaching
@EnableMethodSecurity
~~~

và những cấu hình proxy khác phù hợp dự án. Nhiều feature của Spring có thể chia sẻ hoặc ảnh hưởng hạ tầng proxy.

## 23. Các lỗi thường gặp khi so sánh hai cách bật AOP

### 23.1. Nghĩ Spring Boot lúc nào cũng phải có @EnableAspectJAutoProxy

Không đúng. Với starter AOP và auto-configuration đủ điều kiện, Boot có thể bật cơ chế cần thiết tự động.

**Giải pháp:** chỉ thêm annotation khi có lý do cấu hình cụ thể hoặc đang làm việc với Spring Framework/context thủ công.

### 23.2. Có @Aspect nhưng không có @Component

Aspect class không thành bean nên advice không được đăng ký theo đường component scan.

**Giải pháp:** thêm `@Component` hoặc khai báo một bean aspect.

### 23.3. Thêm @EnableAspectJAutoProxy nhưng thiếu dependency

Annotation không tự cung cấp thư viện runtime cần thiết.

**Giải pháp:** thêm `spring-boot-starter-aop` trong Boot hoặc các dependency Framework/AspectJ tương ứng.

### 23.4. Đặt proxyTargetClass=false nhưng vẫn thấy CGLIB

Boot mặc định có thể yêu cầu class-based proxy; một feature khác cũng có thể ép class proxy.

**Giải pháp:** cấu hình `spring.aop.proxy-target-class=false` đồng nhất và kiểm tra toàn bộ nguồn cấu hình auto-proxy.

### 23.5. Tắt spring.aop.auto=false nhưng vẫn có proxy

Có thể ứng dụng có `@EnableAspectJAutoProxy` tường minh hoặc hạ tầng proxy của transaction/caching/security.

**Giải pháp:** phân biệt Boot AOP auto-configuration với các cơ chế proxy khác, không coi property này là công tắc toàn bộ hệ thống.

### 23.6. Lời gọi từ method nội bộ không chạy advice

**Nguyên nhân:** self-invocation bỏ qua proxy.

**Giải pháp:** tách method cần được chặn sang bean khác hoặc cân nhắc giải pháp proxy exposure có chủ đích.

### 23.7. Class final hoặc method final không được chặn

**Nguyên nhân:** class-based proxy không thể subclass/override như yêu cầu.

**Giải pháp:** dùng class/method có thể proxy, hoặc interface-based design khi phù hợp; đừng kỳ vọng `proxyTargetClass=true` khắc phục giới hạn của `final`.

### 23.8. Đổi @Configuration(proxyBeanMethods=false) rồi tưởng AOP tắt

**Nguyên nhân:** nhầm proxy cho cấu hình `@Bean` với Spring AOP proxy của service.

**Giải pháp:** xem hai cơ chế như các tầng khác nhau và kiểm tra AOP bằng `AopUtils`.

### 23.9. Cứ có aspectjweaver là AspectJ weaving chạy

**Nguyên nhân:** nhầm dependency dùng hỗ trợ pointcut với cấu hình weaving bytecode.

**Giải pháp:** phân biệt proxy-based Spring AOP và AspectJ compile-time/load-time weaving.

### 23.10. Dùng @Async hoặc @Transactional nhưng chỉ bật @EnableAspectJAutoProxy

Các annotation đó cần hạ tầng phù hợp riêng.

**Giải pháp:** bật transaction/async/caching/security theo cách của từng module và kiểm tra lời gọi qua proxy.

## 24. Quy trình chọn cấu hình AOP trong dự án thật

Khi bắt đầu sử dụng AOP, hãy đi theo quy trình:

1. **Xác định loại ứng dụng:** Spring Boot auto-configured hay Spring Framework context tự dựng?
2. **Chọn dependency:** với Boot, thường là `spring-boot-starter-aop`.
3. **Định nghĩa aspect bean:** dùng `@Aspect` kết hợp `@Component` hoặc `@Bean`.
4. **Chọn pointcut hẹp và rõ ràng:** dựa trên package, annotation hoặc contract phù hợp.
5. **Để Boot tự cấu hình nếu không có nhu cầu đặc biệt:** tránh thêm `@EnableAspectJAutoProxy` chỉ theo thói quen.
6. **Nếu cần JDK proxy, cấu hình property Boot:** `spring.aop.proxy-target-class=false`, rồi kiểm tra thực tế.
7. **Nếu cần thao tác đặc biệt với exposeProxy, cân nhắc thiết kế:** ưu tiên tách bean, chỉ bật thủ công khi cần.
8. **Không dựa vào self-invocation:** method được advice phải được gọi qua proxy.
9. **Kiểm tra transaction/async/caching riêng:** chúng có cơ chế kích hoạt và điều kiện riêng.
10. **Viết integration test cho advice:** gọi bean qua context, xác nhận advice thực sự chạy.
11. **Quan sát proxy type và condition:** sử dụng `AopUtils` và báo cáo điều kiện khi cần.
12. **Theo dõi overhead:** aspect quá rộng hoặc log quá nhiều có thể ảnh hưởng latency và lượng dữ liệu log.

Đừng quyết định “có cần `@EnableAspectJAutoProxy` không?” trước khi biết ứng dụng dùng Spring Boot auto-configuration hay một context Spring Framework thuần. Bối cảnh bootstrap mới quyết định lựa chọn phù hợp.

## 25. Bài thực hành

### Bài A: Boot AOP không khai báo @EnableAspectJAutoProxy

Tạo Spring Boot project có `spring-boot-starter-aop`. Tạo:

~~~java
@Aspect
@Component
public class LogAspect {

    @Before("execution(* com.example.demo..*Service.work(..))")
    public void before() {
        System.out.println("AOP invoked");
    }
}
~~~

Tạo `DemoService.work()` và gọi nó từ controller hoặc runner bằng bean inject từ context.

**Yêu cầu:** xác nhận advice chạy mà không cần đặt `@EnableAspectJAutoProxy` trên main class.

### Bài B: Tắt Boot AOP auto-configuration

Thêm:

~~~properties
spring.aop.auto=false
~~~

Khởi động lại và quan sát hành vi aspect. Giải thích tại sao annotation `@Aspect` vẫn có thể là một bean nhưng không còn advice proxy tương ứng khi không có đường kích hoạt nào khác.

### Bài C: Bật thủ công với Spring Framework

Dùng:

~~~java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("com.example.demo")
class ManualConfig {
}
~~~

Tạo `AnnotationConfigApplicationContext` và gọi service. So sánh hành vi với Boot auto-configuration ở bài A.

### Bài D: So sánh JDK proxy và CGLIB

Tạo `GreetingService` interface và `DefaultGreetingService` implementation.

Thử:

~~~properties
spring.aop.proxy-target-class=true
~~~

và:

~~~properties
spring.aop.proxy-target-class=false
~~~

Dùng:

~~~java
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
~~~

Ghi lại kiểu proxy và quan sát khi inject theo interface so với concrete class.

### Bài E: Tái hiện self-invocation

Tạo class với `outer()` gọi `inner()` qua `this`. Viết advice chỉ khớp `inner()`.

So sánh lời gọi `outer()` và lời gọi trực tiếp `inner()` từ một bean bên ngoài. Sau đó tách `inner()` sang bean mới và kiểm tra advice chạy như mong đợi.

### Bài F: exposeProxy

Bật:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
~~~

Tạo một tình huống gọi qua `AopContext.currentProxy()` trong lời gọi được proxy, sau đó thử gọi method bằng `new` để quan sát sự khác biệt.

Giải thích vì sao đây là cơ chế đặc biệt, không nên lạm dụng trong service nghiệp vụ.

### Bài G: Final method

Tạo class có method `final` và một aspect khớp method đó. Dùng class-based proxy và quan sát giới hạn. Thử đổi sang một method có thể override và so sánh.

### Bài H: Kiểm thử bằng @SpringBootTest

Viết aspect tăng `AtomicInteger` mỗi lần `placeOrder()` được gọi qua proxy. Dùng `@SpringBootTest` để assert số lần advice chạy sau khi gọi service.

Không gọi trực tiếp `aspect.count(...)` như một phép thay thế cho việc test AOP thực tế.

### Bài I: Phân biệt với @Transactional

Tạo service có `@Transactional` và một method gọi nội bộ. Giải thích vì sao self-invocation vẫn quan trọng và vì sao thêm `@EnableAspectJAutoProxy` không phải cách thay thế cấu hình transaction management.

## 26. Câu hỏi tự kiểm tra

**1. `@EnableAspectJAutoProxy` thuộc Spring Framework hay Spring Boot?**

Thuộc Spring Framework. Nó bật hạ tầng xử lý aspect kiểu `@AspectJ` bằng Spring AOP proxy.

**2. Vì sao Spring Boot không nhất thiết cần annotation đó?**

Vì khi có dependency AOP phù hợp và điều kiện auto-configuration thỏa mãn, Boot có thể tự đăng ký hạ tầng AOP.

**3. Dependency nào thường được thêm vào ứng dụng Boot để dùng Spring AOP?**

`spring-boot-starter-aop`.

**4. `spring.aop.auto=false` có bảo đảm mọi proxy trong ứng dụng biến mất không?**

Không. Nó điều khiển đường tự cấu hình AOP của Boot, không phải công tắc tắt mọi cơ chế proxy do các module hoặc annotation khác đăng ký.

**5. Spring Boot thường mặc định dùng proxy JDK hay class-based?**

Trong cấu hình AOP Boot thông thường, class-based proxy được ưu tiên theo `spring.aop.proxy-target-class=true`.

**6. `@EnableAspectJAutoProxy` đơn lẻ có mặc định `proxyTargetClass=true` không?**

Không. Mặc định riêng của annotation là `false`; nhưng trong một context có nhiều nguồn cấu hình proxy, lựa chọn cuối cùng cần xét cấu hình chung.

**7. `@Aspect` có tự trở thành bean được scan không?**

Không. Cần `@Component` hoặc một cách đăng ký bean phù hợp.

**8. Vì sao `this.innerMethod()` thường không chạy advice của method đó?**

Vì lời gọi nội bộ trên target bỏ qua Spring AOP proxy.

**9. `@EnableAspectJAutoProxy` có kích hoạt AspectJ bytecode weaving đầy đủ không?**

Không. Nó hỗ trợ cấu hình Spring AOP proxy-based dùng cú pháp `@AspectJ`.

**10. Tại sao CGLIB không chặn được final method theo proxy subclass?**

Vì subclass không thể override method `final`.

**11. `@Order` có sửa được một pointcut không khớp không?**

Không. Ordering chỉ sắp xếp advisor/advice khi chúng đã được áp dụng.

**12. Có thể kiểm tra một bean là JDK hay CGLIB proxy bằng gì?**

Các method như `AopUtils.isJdkDynamicProxy(bean)` và `AopUtils.isCglibProxy(bean)`.

**13. `@Configuration(proxyBeanMethods=false)` có tắt AOP của service không?**

Không. Nó liên quan đến cách enhancement xử lý `@Bean` methods trong configuration class, không phải công tắc cho service AOP.

**14. Chỉ thêm `@EnableAspectJAutoProxy` có tự bật `@Async`, `@Cacheable` và `@Transactional` không?**

Không. Mỗi khả năng cần hạ tầng kích hoạt/cấu hình phù hợp.

**15. Khi nào nên ưu tiên `@EnableAspectJAutoProxy` tường minh?**

Khi làm việc với Spring Framework context được cấu hình thủ công hoặc có yêu cầu rõ ràng về hạ tầng `@AspectJ` mà không dùng đường tự cấu hình của Boot.

## 27. Kết luận

`@EnableAspectJAutoProxy` và cấu hình AOP tự động của Spring Boot không tạo ra hai cách AOP đối lập. Cả hai đều có thể dẫn đến **Spring AOP dựa trên proxy** để chạy những advice được viết bằng `@Aspect` và các annotation như `@Before`, `@After`, `@Around`.

Sự khác biệt cốt lõi nằm ở **cơ chế bật AOP**. Với Spring Framework thuần hoặc context tự dựng, `@EnableAspectJAutoProxy` là công cụ cấu hình tường minh. Với phần lớn ứng dụng Spring Boot có `spring-boot-starter-aop`, auto-configuration đã xử lý bước bật hạ tầng nên không cần thêm annotation chỉ để các aspect hoạt động.

Hãy nhớ ba quy tắc khi triển khai:

1. **Có dependency và bean phù hợp:** starter AOP cung cấp hạ tầng; `@Aspect` vẫn phải được đăng ký như Spring bean.
2. **Hiểu cách tạo proxy:** Boot thường mặc định class-based; `spring.aop.proxy-target-class=false` cho phép ưu tiên JDK proxy khi có interface phù hợp. Không trộn các cấu hình proxy trái chiều mà không kiểm tra.
3. **Lời gọi phải đi qua proxy:** self-invocation, method `private`/`final`, object tạo bằng `new` và những pointcut không khớp đều có thể khiến advice không chạy.

Khi gặp lỗi AOP, đừng mặc định bổ sung `@EnableAspectJAutoProxy`. Hãy lần lượt kiểm tra dependency, condition của Boot, aspect bean, target bean, proxy type, pointcut và đường đi của lời gọi. Việc hiểu đúng ranh giới giữa **Spring Framework explicit configuration** và **Spring Boot auto-configuration** giúp code ngắn gọn hơn, tránh cấu hình trùng và sử dụng AOP đúng mục đích.

