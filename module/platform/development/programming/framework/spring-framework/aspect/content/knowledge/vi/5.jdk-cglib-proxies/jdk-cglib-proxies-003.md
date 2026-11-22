# Quy tắc chọn cơ chế proxy trong Spring Framework

## 1. Câu hỏi cần trả lời trước khi cấu hình Spring AOP

Khi Spring AOP áp dụng một advice cho Spring bean, caller thường không nhận trực tiếp target object: container cung cấp một **proxy** để chuyển lời gọi qua interceptor chain. Spring có hai kiểu proxy chủ yếu:

- **JDK dynamic proxy:** proxy triển khai các interface cần thiết của target.
- **Class-based proxy (CGLIB):** proxy là subclass được sinh ra từ class đích.

Điều người học phải xác định là **Spring quyết định chọn kiểu nào, cấu hình nào có thể thay đổi quyết định đó, và hậu quả với những method được advice hoặc những kiểu có thể inject**.

Trong Spring Framework thuần, quy tắc mặc định thường gặp là:

> Nếu target có interface phù hợp để proxy, Spring ưu tiên **JDK dynamic proxy**. Nếu target không có interface để proxy, Spring dùng **class-based proxy (CGLIB)**. Khi `proxyTargetClass = true`, Spring **ép dùng class-based proxy**, kể cả nếu target có interface.

Đây là **quy tắc cho cơ chế Spring AOP proxy trong cấu hình thông thường**, không phải khẳng định mọi dạng proxy trong Spring (scoped proxy, custom `TargetSource`, proxy được lập trình bằng `ProxyFactory`) đều có lựa chọn giống hệt nhau.

**Spring Boot khác Spring Framework thuần ở mặc định cấu hình:** auto-configuration của Boot thông thường đặt **class-based proxy làm mặc định**. Nếu muốn JDK proxy ở Boot, dùng `spring.aop.proxy-target-class=false` và bảo đảm target có interface phù hợp.

Bài này tập trung vào lựa chọn proxy của **Spring AOP trên Spring-managed beans**, không triển khai kiến thức proxy Java thuần hoặc AspectJ weaving độc lập với Spring.

## 2. Vì sao Spring cần chọn giữa hai loại proxy?

Trong Spring AOP, một aspect hoặc Spring advisor mô tả hành vi cần áp dụng cho lời gọi phương thức. Auto-proxy creator kiểm tra bean đang được tạo, tìm các advisor phù hợp và tạo proxy nếu cần. Việc chọn JDK/CGLIB xảy ra khi **tạo proxy**, trước khi caller thực sự gọi method.

```text
ApplicationContext đăng ký bean definitions
                    |
                    v
    Tạo target bean + xác định advisors
                    |
                    v
     Target có cần Spring AOP proxy?
             /                \
           Không               Có
            |                   |
      Bean thông thường   Có ép class proxy?
                            /          \
                          Có           Không
                           |             |
                         CGLIB     Target có interface
                                        phù hợp?
                                       /        \
                                      Có        Không
                                       |          |
                                      JDK        CGLIB
                                       \          /
                                        v        v
                                   Caller nhận proxy
                                        |
                                        v
                                  method invocation
                                        |
                                        v
                                 advice -> target
```

Sơ đồ thể hiện **quy tắc chọn mặc định và việc ép class proxy** ở Spring Framework trong một môi trường chưa có cấu hình override khác. Spring còn xét interfaces được cấu hình tường minh, hạ tầng transaction/AOP đồng thời, chế độ `optimize`, kiểu proxy riêng và giới hạn class đích. Vì vậy kết quả thực tế phải được đo trên bean trong `ApplicationContext`.

Quan trọng: **có interface không có nghĩa bean chắc chắn bị proxy**. Spring phải có advisor/advice có thể áp dụng; nếu không có nhu cầu AOP, bean có thể được trả về nguyên vẹn.

## 3. Bảng quyết định thực tế

| Bối cảnh Spring AOP | Target implement business interface? | Thiết lập class proxy | Kết quả thông thường |
| --- | --- | --- | --- |
| Spring Framework thuần, mặc định | Có | `proxyTargetClass=false` | **JDK dynamic proxy**. |
| Spring Framework thuần, mặc định | Không | `proxyTargetClass=false` | **CGLIB**, vì JDK proxy không thể đại diện cho một class không có interface phù hợp. |
| Spring Framework thuần, ép class | Có hoặc không | `proxyTargetClass=true` | **CGLIB**, nếu class có thể subclass/proxy. |
| Spring Boot auto-configuration mặc định | Có hoặc không | Mặc định class-based | **CGLIB**, khi bean thực sự cần AOP proxy và có thể proxy. |
| Spring Boot đặt `spring.aop.proxy-target-class=false` | Có | Cho phép interface proxy | Thường **JDK dynamic proxy**, nếu không có cấu hình khác ép class proxy. |
| Spring Boot đặt `spring.aop.proxy-target-class=false` | Không | Cho phép mặc định Spring quyết định | **CGLIB**, vì thiếu interface phù hợp cho JDK proxy. |
| Spring proxy factory tùy chỉnh | Tùy target | Tùy danh sách `proxyInterfaces`, `proxyTargetClass`, `TargetSource` | Phải đọc cấu hình factory; không suy từ bảng mặc định. |

Đặt `proxyTargetClass=false` **không đồng nghĩa ép dùng JDK proxy bằng mọi giá**. Nó chỉ không bắt buộc class-based proxy; Spring vẫn phải chọn cách hợp lệ cho target.

Nếu không có advisor nào áp dụng, `AopUtils.isAopProxy(bean)` có thể là `false` bất kể class đó có interface hay Spring Boot đã cấu hình AOP.

## 4. Cách nhận diện JDK proxy và CGLIB proxy trong Spring

### 4.1. JDK dynamic proxy: giao diện là contract để caller đi qua proxy

Ví dụ interface:

```java
public interface PaymentOperations {
    String pay(String orderId);
}
```

Class triển khai:

```java
public class PaymentService implements PaymentOperations {
    @Override
    public String pay(String orderId) {
        return "paid:" + orderId;
    }

    public String implementationOnly() {
        return "internal";
    }
}
```

Hai đoạn trên là **fragments minh họa**, không có package/import; ví dụ chạy hoàn chỉnh nằm ở phần 8.

Khi Spring tạo **JDK dynamic proxy** cho `PaymentService` theo `PaymentOperations`:

- Caller có thể nhận proxy qua `PaymentOperations` và gọi `pay()`.
- Proxy **không phải instance của `PaymentService`**, do đó cast proxy sang concrete implementation thường thất bại.
- `implementationOnly()` **không có trong interface `PaymentOperations`**, nên không thể được gọi qua tham chiếu JDK proxy đó.
- Việc Spring AOP có thể advice một method còn tùy method thuộc contract interface, pointcut và đường gọi qua proxy; không suy rằng cứ có method trong implementation thì caller đã truy cập được trên JDK proxy.

Tại ranh giới dependency injection, Spring khuyến khích inject **kiểu interface** khi chọn interface proxy. Nếu một component lại yêu cầu `PaymentService` theo kiểu implementation, proxy JDK không đáp ứng trực tiếp yêu cầu type đó; ứng dụng có thể gặp lỗi inject/lookup tùy kiểu khai báo.

### 4.2. CGLIB: class proxy kế thừa class đích

Với class-based proxy, Spring tạo một lớp con ở runtime. Vì proxy là subclass của `PaymentService`, nên biểu thức `proxy instanceof PaymentService` có thể là `true`, và các method có thể override được có thể nhận advice qua proxy.

Điểm giới hạn:

- Class **`final` không thể bị subclass** để tạo CGLIB class proxy.
- Method **`final` không thể bị override**, vì vậy không thể được advice theo mô hình class proxy.
- Method **`private` không thể override**, vì vậy không phải điểm chặn khả dụng.
- Method không nhìn thấy với subclass (ví dụ package-private trên superclass khác package) không thể được advice bằng class proxy.
- Constructor không phải method execution được Spring AOP proxy bao quanh; self-invocation trong target vẫn bỏ qua proxy.

**Không cần khai báo dependency CGLIB riêng chỉ để bật Spring AOP class proxy**: Spring Framework đã tích hợp biến thể CGLIB trong `spring-core`. Khi dùng `@Aspect`, vẫn cần những dependency Spring AOP và hỗ trợ annotation/pointcut phù hợp, thường qua Spring Boot starter hoặc `spring-context` và `aspectjweaver`.

### 4.3. Trường hợp class final nhưng có interface

Một class `final` implement interface có thể hoạt động qua **JDK interface proxy** vì proxy không cần subclass class đó. Method triển khai là `final` cũng không nhất thiết cản trở interception qua JDK proxy: proxy chặn lời gọi ở **interface**, sau đó ủy quyền đến target.

Tuy nhiên, nếu cấu hình đã **ép class proxy bằng `proxyTargetClass=true`**, việc target là class `final` có thể khiến Spring không tạo được proxy và ứng dụng thất bại khi khởi tạo. Do đó, không sử dụng `proxyTargetClass=true` làm “cách sửa mọi lỗi AOP” mà không xem class hierarchy.

## 5. Thiết lập quyết định proxy trong Spring Framework thuần

### 5.1. Annotation `@EnableAspectJAutoProxy`

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class InterfaceProxyConfig {
    // @Bean definitions hoặc @ComponentScan
}
```

Khi không ép class proxy, các bean có interface phù hợp thường được proxy bằng JDK; các bean không có interface phù hợp phải dùng CGLIB nếu Spring cần proxy.

Ép class-based:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassProxyConfig {
    // @Bean definitions hoặc @ComponentScan
}
```

Đây là hai **config fragments thay thế nhau**, không nên kích hoạt đồng thời rồi đoán annotation nào “thắng”. Cấu hình Spring còn xét những nơi bật AOP/transaction khác trong context.

### 5.2. XML namespace `aop`

Với XML đã khai báo đúng namespace `aop`:

```xml
<aop:aspectj-autoproxy proxy-target-class="false"/>
```

hoặc:

```xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
```

Nếu dùng Spring AOP XML schema advisors:

```xml
<aop:config proxy-target-class="true">
    <!-- Các advisor/aspect XML của ứng dụng -->
</aop:config>
```

Các đoạn trên là **fragments XML**, không phải toàn bộ tài liệu XML có namespace/schema. Thuộc tính `proxy-target-class` có tác dụng tương tự việc yêu cầu dùng class-based proxy, nhưng phải hiểu rằng Spring có thể hợp nhất cấu hình proxy với những tính năng khác trong cùng context.

### 5.3. Khi cấu hình AOP được hợp nhất

Nếu trong cùng `ApplicationContext` có cả thiết lập interface proxy (`false`) và một yêu cầu class proxy (`true`) từ Java config, XML AOP hoặc hạ tầng transaction, Spring có thể hợp nhất chúng và áp dụng **thiết lập mạnh hơn (`true`)** cho auto-proxy creator. Vì vậy, bảng chọn proxy ở mục 3 chỉ đúng sau khi xác minh cấu hình đang có hiệu lực. Nên kiểm tra tất cả nguồn cấu hình liên quan và loại proxy runtime bằng `AopUtils`, nhất là khi dùng Spring Framework và Spring Boot cùng với transaction AOP.

## 6. Spring Boot: vì sao kết quả mặc định khác Spring Framework thuần?

Spring Boot cung cấp **auto-configuration** cho Spring AOP và mặc định thường dùng class-based proxy. Cấu hình ví dụ trong `application.properties`:

```properties
# Dùng interface-based proxy khi khả thi:
spring.aop.proxy-target-class=false
```

Nếu không có cấu hình khác ép class-based, Spring sẽ cân nhắc JDK proxy cho target có interface. Nếu target không implement interface thích hợp, Spring vẫn cần CGLIB khi phải tạo proxy.

Với cấu hình muốn dùng class-based:

```properties
spring.aop.proxy-target-class=true
```

Không nên áp dụng lời khuyên “Spring luôn chọn JDK trước” một cách máy móc cho ứng dụng Spring Boot: **mặc định do Boot cấu hình có thể khác mặc định Spring Framework core**.

Một số điểm cần xác minh:

1. Ứng dụng đã thêm starter AOP phù hợp với dòng Spring Boot được sử dụng (ví dụ Boot 3.x dùng `spring-boot-starter-aop`; Boot 4.x có `spring-boot-starter-aspectj`).
2. Bean aspect đã được Spring quản lý, qua `@Aspect` + `@Component` hoặc `@Bean`; annotation `@Aspect` một mình không đăng ký bean.
3. Có cấu hình Java/XML khác như `@EnableAspectJAutoProxy(proxyTargetClass=true)` hoặc transaction auto-proxy ghi đè ý định chọn JDK hay không.
4. Bean thực sự được proxy vì có advisor; nếu không có advisor phù hợp thì so sánh JDK/CGLIB trên bean đó có thể không có ý nghĩa.

**Giới hạn của property:** `spring.aop.proxy-target-class` điều chỉnh auto-configuration của Boot. Nó không bảo đảm đổi mọi custom proxy do thư viện khác tự tạo hoặc mọi scoped proxy đã khai báo.

## 7. Spring Framework 7: điều chỉnh proxy theo từng bean khi thích hợp

Spring Framework **7.0+** bổ sung khả năng chọn loại proxy cho bean cụ thể bằng **`@Proxyable`** với các lựa chọn như `INTERFACES` và `TARGET_CLASS`, theo tài liệu chính thức. Đây là khả năng của **dòng 7**, không phải annotation có sẵn ở Spring Framework 6.1/6.2.

Khả năng này hữu ích khi toàn ứng dụng có mặc định class proxy nhưng một bean cụ thể cần interface proxy, hoặc ngược lại. Cần đối chiếu đúng phiên bản Spring hiện tại và contract của bean trước khi dùng; đừng sao chép cấu hình Spring 7 vào một project đang dùng Spring 6.

Bài thực hành ở phần tiếp theo **cố định Spring Framework 6.1.14** nhằm minh họa quy tắc phổ biến của `proxyTargetClass`, không sử dụng `@Proxyable`.

## 8. Ví dụ Java 17+ chạy được: so sánh JDK và CGLIB trên cùng target

Ví dụ chạy **hai `AnnotationConfigApplicationContext` độc lập** với cùng các bean definitions và aspect:

- Context thứ nhất: `proxyTargetClass=false`; `PaymentService` có interface nên dùng JDK, `ReportService` không có interface nên dùng CGLIB.
- Context thứ hai: `proxyTargetClass=true`; cả hai service dùng CGLIB.
- `TraceAspect` áp dụng `@Before` lên hai method; các lời gọi service đều đi qua proxy.
- Đọc kết quả bằng `AopUtils` thay vì đoán từ tên class được sinh tự động.

### 8.1. Cấu trúc thư mục

```text
spring-proxy-selection/
├── pom.xml
└── src/main/java/com/example/proxy/
    ├── PaymentOperations.java
    ├── PaymentService.java
    ├── ReportService.java
    ├── TraceAspect.java
    └── DemoApp.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-proxy-selection</artifactId>
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

`spring-context` đã kéo các module Spring nền tảng trong graph tương ứng, bao gồm Spring AOP; `aspectjweaver` hỗ trợ Spring đọc `@Aspect` và pointcut expressions. Chọn phiên bản bằng BOM/dependency management phù hợp khi chuyển ví dụ vào ứng dụng thực tế; không trộn ngẫu nhiên những dòng Spring Framework.

### 8.3. `src/main/java/com/example/proxy/PaymentOperations.java`

```java
package com.example.proxy;

public interface PaymentOperations {
    String pay(String orderId);
}
```

### 8.4. `src/main/java/com/example/proxy/PaymentService.java`

```java
package com.example.proxy;

public class PaymentService implements PaymentOperations {

    @Override
    public String pay(String orderId) {
        return "paid:" + orderId;
    }

    public String implementationOnly() {
        return "implementation-only";
    }
}
```

### 8.5. `src/main/java/com/example/proxy/ReportService.java`

```java
package com.example.proxy;

public class ReportService {
    public String generate(String id) {
        return "report:" + id;
    }
}
```

`ReportService` cố ý không implement interface nghiệp vụ nào để thấy Spring phải dùng class-based proxy khi method của nó được advice.

### 8.6. `src/main/java/com/example/proxy/TraceAspect.java`

```java
package com.example.proxy;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before(
        "execution(public * com.example.proxy.PaymentService.pay(..))"
        + " || execution(public * com.example.proxy.ReportService.generate(..))"
    )
    public void before(JoinPoint joinPoint) {
        System.out.println("[AOP] " + joinPoint.getSignature().getName());
    }
}
```

Biểu thức `execution(...)` được Spring AOP kiểm tra theo method/target class. Cả hai method đều public; advice không chạy cho `PaymentService.implementationOnly()` vì pointcut không chọn method đó.

### 8.7. `src/main/java/com/example/proxy/DemoApp.java`

```java
package com.example.proxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class DemoApp {

    @Configuration
    static class Beans {
        @Bean
        PaymentOperations paymentOperations() {
            return new PaymentService();
        }

        @Bean
        ReportService reportService() {
            return new ReportService();
        }

        @Bean
        TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    @Configuration
    @Import(Beans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    static class DefaultProxyConfig {
    }

    @Configuration
    @Import(Beans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class ClassProxyConfig {
    }

    private static void run(String label, Class<?> configClass) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(configClass)) {

            PaymentOperations payment =
                    context.getBean(PaymentOperations.class);
            ReportService report = context.getBean(ReportService.class);

            System.out.println("[" + label + "] paymentJdk="
                    + AopUtils.isJdkDynamicProxy(payment));
            System.out.println("[" + label + "] paymentCglib="
                    + AopUtils.isCglibProxy(payment));
            System.out.println("[" + label + "] reportCglib="
                    + AopUtils.isCglibProxy(report));
            System.out.println("[" + label + "] paymentIsConcrete="
                    + (payment instanceof PaymentService));

            System.out.println("[" + label + "] "
                    + payment.pay("P-1"));
            System.out.println("[" + label + "] "
                    + report.generate("R-1"));
        }
    }

    public static void main(String[] args) {
        run("DEFAULT", DefaultProxyConfig.class);
        run("CLASS", ClassProxyConfig.class);
    }
}
```

Hai context độc lập bảo đảm thiết lập `proxyTargetClass=false` và `proxyTargetClass=true` **không hợp nhất vào cùng một context**, tránh làm sai phép so sánh. `Beans` đóng vai trò lớp cấu hình dùng chung nhưng được import riêng vào từng context.

### 8.8. Chạy project và đối chiếu stdout

Tại thư mục `spring-proxy-selection` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.proxy.DemoApp
```

Các dòng do chính chương trình in ra theo thứ tự, không tính thông báo Maven/SLF4J tùy môi trường:

```text
[DEFAULT] paymentJdk=true
[DEFAULT] paymentCglib=false
[DEFAULT] reportCglib=true
[DEFAULT] paymentIsConcrete=false
[AOP] pay
[DEFAULT] paid:P-1
[AOP] generate
[DEFAULT] report:R-1
[CLASS] paymentJdk=false
[CLASS] paymentCglib=true
[CLASS] reportCglib=true
[CLASS] paymentIsConcrete=true
[AOP] pay
[CLASS] paid:P-1
[AOP] generate
[CLASS] report:R-1
```

**Giải thích:**

1. `PaymentService` implement `PaymentOperations`; trong context DEFAULT, Spring có thể dùng JDK proxy để cung cấp `PaymentOperations`. Vì thế `paymentJdk=true` và `paymentIsConcrete=false`.
2. `ReportService` không có business interface, nhưng advice khớp `generate()`; Spring tạo CGLIB subclass proxy cho bean này ngay cả khi cấu hình DEFAULT không ép class proxy.
3. Trong context CLASS, `proxyTargetClass=true` ép class proxy cho mọi bean đích cần AOP, nên `PaymentService` được bọc bằng CGLIB và `payment instanceof PaymentService` đúng.
4. Cả hai context đều có một bean `TraceAspect`, và cả hai method cần áp dụng advice đều thực thi qua proxy. **Chọn JDK hay CGLIB thay đổi loại proxy và các method/kiểu có thể thấy qua proxy; nó không tự làm thay đổi nội dung nghiệp vụ `paid:P-1` hay `report:R-1`.**
5. Không có dòng log advice cho `implementationOnly()`: pointcut không chọn method đó, dù khi dùng CGLIB method này có thể được gọi qua reference kiểu `PaymentService` nếu application được thiết kế truy cập như vậy.

**Lưu ý thực nghiệm:** nếu đổi `PaymentOperations paymentOperations()` thành return type `PaymentService`, cách Spring suy đoán kiểu lúc tạo bean có thể khác, nhưng quy tắc proxy chủ yếu vẫn dựa trên target class, interfaces và `proxyTargetClass`. Tránh phụ thuộc vào một kiểu implement khi bạn chủ động chọn JDK proxy.

## 9. Chiến lược proxy và khả năng inject bean

Đây là tác động dễ nhận ra nhất khi đổi cơ chế proxy trong một ứng dụng Spring.

### 9.1. Inject theo interface khi dùng JDK proxy

Ví dụ Spring-managed client:

```java
public class CheckoutController {
    private final PaymentOperations payment;

    public CheckoutController(PaymentOperations payment) {
        this.payment = payment;
    }
}
```

Fragment này an toàn theo contract interface khi Spring bean được proxy bằng JDK; không cần client biết `PaymentService` là implementation thật.

Ngược lại:

```java
public class CheckoutController {
    private final PaymentService payment;

    public CheckoutController(PaymentService payment) {
        this.payment = payment;
    }
}
```

Nếu bean được thay bằng **JDK proxy** chỉ triển khai `PaymentOperations`, injection yêu cầu concrete `PaymentService` có thể không thỏa mãn. Điều chỉnh injection sang interface hoặc cân nhắc class-based proxy có chủ đích; không phải mọi ứng dụng đều cần `proxyTargetClass=true`.

### 9.2. Interface method và implementation-only method

Khi dùng JDK proxy, caller theo contract `PaymentOperations` chỉ truy cập được `pay()`, không có `implementationOnly()`. Trong Spring AOP, nếu chỉ method ở implementation được advice nhưng caller không có đường gọi method đó qua interface proxy, hành vi cần thiết sẽ không xuất hiện theo cách mong muốn.

Hướng thiết kế thường là:

- Đưa method nghiệp vụ cần được gọi từ bên ngoài vào interface thích hợp.
- Nếu ứng dụng nhất thiết phải expose concrete type hoặc method không thuộc interface, chọn class-based proxy sau khi kiểm tra giới hạn class/final method.
- Nếu target chỉ có method nội bộ, nhận thức rằng self-invocation vẫn không đi qua proxy kể cả khi chọn CGLIB.

### 9.3. CGLIB không “sửa” được self-invocation

```java
public class PaymentService {
    public void checkout() {
        audit(); // this.audit(), không đi lại qua proxy.
    }

    public void audit() {
        // Phương thức cần advice.
    }
}
```

Đây là fragment minh họa. Khi caller gọi `proxy.checkout()`, Spring có thể intercept `checkout()`; nhưng bên trong target, `this.audit()` không tự đi lại qua proxy để kích hoạt advice của `audit()`. **Ép CGLIB cũng không giải quyết được self-invocation**. Thông thường nên tách trách nhiệm cần advice sang bean khác và gọi qua dependency Spring quản lý.

## 10. Phân biệt proxy lựa chọn bởi AOP với các proxy khác của Spring

Ứng dụng Spring có thể chứa nhiều cơ chế proxy:

| Cơ chế | Mục đích | Có áp dụng chính xác quy tắc ở bài này? |
| --- | --- | --- |
| Spring AOP auto-proxy cho `@Aspect` | Intercept lời gọi Spring bean methods theo advisors | Có, theo cấu hình AOP/auto-proxy creator. |
| Transaction advisor/proxy | `@Transactional` qua proxy | Dùng hạ tầng proxy gần gũi; cấu hình chung có thể ảnh hưởng lựa chọn. |
| Scoped proxy | Inject bean ngắn vòng đời vào bean dài vòng đời | Có cài đặt lựa chọn interface/class riêng; không đoán từ `@EnableAspectJAutoProxy` đơn lẻ. |
| `ProxyFactory` hoặc `ProxyFactoryBean` tự cấu hình | Tạo proxy theo yêu cầu cho một target cụ thể | Dựa vào `proxyTargetClass`, `proxyInterfaces` và cấu hình factory cụ thể. |
| AspectJ compile-time/load-time weaving | Can thiệp bằng weaving | **Không phải** JDK/CGLIB Spring proxy theo cách bài này mô tả. |

Một AOP proxy có thể chứa nhiều advisor (audit, transaction, security...), và Spring thường hợp nhất cấu hình auto-proxy creator chuẩn. Vì vậy **thấy bean là CGLIB proxy không chứng minh aspect audit cụ thể đã áp dụng**, và **thấy hai cấu hình bật AOP không chứng minh có hai proxy riêng**.

## 11. Kiểm tra loại proxy trong ứng dụng thực tế

Với bean đã lấy từ context:

```java
Object bean = context.getBean("paymentOperations");

System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isCglibProxy(bean));
```

Đây là fragment trong một chương trình có biến `context`, không phải Java file độc lập. Ba API trả lời ba câu hỏi khác nhau:

- `isAopProxy`: có phải Spring AOP proxy theo kiểm tra Spring?
- `isJdkDynamicProxy`: có phải proxy dựa trên JDK dynamic proxy?
- `isCglibProxy`: có phải Spring CGLIB class proxy?

Có thể xem thêm advisors trong `Advised` và chạy thực tế method cần kiểm tra. Không dùng `bean.getClass().getName()` như bằng chứng duy nhất: tên lớp proxy được sinh ra là chi tiết runtime, có thể thay đổi theo version.

Một test nên xác minh **cả loại proxy và hợp đồng hành vi**:

1. Aspect và target thực sự nằm trong context và hạ tầng auto-proxy đã được bật.
2. Bean có advisor áp dụng và `AopUtils` trả đúng kiểu proxy dự kiến.
3. Lookup/injection theo type interface/concrete đáp ứng thiết kế.
4. Advice chạy đúng số lần với method khớp, không chạy cho method không khớp.
5. Giá trị trả về và ngoại lệ của nghiệp vụ không bị đổi ngoài ý muốn.
6. Các method `final`, `private`, self-invocation hoặc outside-context không được coi là điểm chặn Spring AOP bình thường.
7. Nếu có nhiều context hoặc cấu hình Java/XML/Boot, xác nhận proxy type ở **context thực sự sở hữu bean**, không chỉ ở test context đơn lẻ.

## 12. Những lỗi thường gặp khi chọn proxy

| Dấu hiệu | Khả năng xảy ra | Hướng kiểm tra/sửa |
| --- | --- | --- |
| `@Autowired PaymentService` thất bại nhưng inject `PaymentOperations` được | Bean được thay bằng JDK proxy không phải implementation class. | Dùng interface injection, hoặc chuyển sang class proxy khi có lý do. |
| Đặt `proxyTargetClass=false` nhưng bean vẫn dùng CGLIB | Target không có interface, hoặc hạ tầng khác đã yêu cầu class proxy. | Kiểm tra interface và tất cả proxy configs trong context. |
| Dùng Spring Boot mà bean có interface vẫn là CGLIB | Boot auto-configuration mặc định ưu tiên class proxy. | Kiểm tra `spring.aop.proxy-target-class` và cấu hình AOP khác. |
| Ép CGLIB nhưng class `final` gây lỗi | Không thể subclass class `final`. | Thiết kế interface proxy hoặc bỏ ràng buộc `final` khi hợp lý. |
| Method `final` không được advice bằng CGLIB | Proxy không thể override method đó. | Chuyển điểm chặn sang method có thể override hoặc interface proxy tương thích. |
| Có `@Aspect` nhưng không tạo JDK/CGLIB proxy | Aspect chưa là bean, AOP chưa bật, hoặc không có advisor match. | Kiểm tra registration, auto-proxy creator, pointcut. |
| Tự gọi method trong cùng class mà advice không chạy | Self-invocation bypass proxy. | Gọi qua Spring-managed bean khác; đổi JDK/CGLIB không tự sửa lỗi. |
| Phương thức tồn tại trên implementation nhưng không gọi được qua JDK proxy | Không nằm trong proxy interface. | Đưa contract vào interface hoặc chọn class proxy có chủ đích. |
| Có dòng `proxyTargetClass=false` nhưng CGLIB vẫn được ép | XML/transaction/AOP config khác yêu cầu `true`. | Kiểm kê context; cấu hình unified auto-proxy creator dùng thiết lập mạnh hơn. |
| Dùng Java module system gặp vấn đề khi proxy class đặc biệt | CGLIB bị hạn chế bởi module visibility/open packages. | Xem class/module cần proxy; tránh mặc định ép subclass cho class không mở được. |
| Thấy class name lạ chứa `$$SpringCGLIB$$` | Đây có thể là proxy class hợp lệ của Spring. | Dùng `AopUtils` và kiểm tra advisor/method; không coi riêng class name là lỗi. |

## 13. Quy trình quyết định cho một project Spring cụ thể

Khi thêm một aspect hoặc sửa một bug proxy:

1. **Xác định có cần AOP proxy không.** Có Spring-managed target bean và advisor/pointcut nào thực sự khớp?
2. **Kiểm tra môi trường chạy:** Spring Framework thuần, Spring Boot hay custom proxy factory; đọc đúng defaults của môi trường đó.
3. **Xem interface contract:** service có business interface và caller có đang inject theo interface không?
4. **Chọn khả năng proxy phù hợp:** mặc định của Framework thường JDK nếu có interface; dùng CGLIB nếu không có interface hoặc khi được ép và class cho phép.
5. **Rà soát toàn bộ proxy settings của context:** `@EnableAspectJAutoProxy`, XML `<aop:aspectj-autoproxy>`, `<aop:config>`, transaction support, Spring Boot property; không xem mỗi một annotation.
6. **Kiểm tra giới hạn loại proxy:** concrete injection, implementation-only methods, class/method `final`, `private`, Java modules và self-invocation.
7. **Xác nhận bằng `AopUtils` và một lần gọi thật:** proxy type, đúng advice, giá trị trả về, exception, số lần gọi.
8. **Giữ lựa chọn có lý do:** chỉ ép CGLIB khi cần concrete type/class methods và class cho phép subclass; interface proxy phù hợp khi API contract tập trung vào interface.

### Tài liệu Spring chính thức

- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — AOP Proxies: https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html
- Spring Framework — @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — ProxyFactoryBean and JDK/CGLIB selection: https://docs.spring.io/spring-framework/reference/core/aop-api/pfb.html
- Spring Boot — Aspect-Oriented Programming: https://docs.spring.io/spring-boot/reference/features/aop.html

**Kết quả cần đạt không phải “càng nhiều CGLIB càng tốt” hay “luôn JDK cho nhanh”, mà là chọn được proxy Spring AOP phù hợp với interface contract, cách inject bean, pointcut và cơ chế cấu hình đang hoạt động.** Một khi đã xác nhận loại proxy và lời gọi thật, bạn sẽ phân biệt được lỗi proxy selection với lỗi đăng ký aspect, pointcut hoặc self-invocation.
