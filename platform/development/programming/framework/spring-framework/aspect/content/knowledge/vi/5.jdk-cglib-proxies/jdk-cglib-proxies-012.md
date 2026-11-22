# Tình huống lỗi ép kiểu khi chuyển cơ chế proxy trong Spring AOP

## 1. Hiện tượng: bean vẫn hoạt động, nhưng cast sang lớp triển khai bị lỗi

Khi Spring AOP bọc một Spring bean bằng proxy, **kiểu runtime của reference mà caller nhận được có thể không còn là kiểu concrete của target**. Trong cấu hình dùng **JDK dynamic proxy**, proxy triển khai interface mà bean công bố, nhưng **không kế thừa implementation class**. Vì vậy mã ép kiểu từ interface reference sang implementation có thể ném `ClassCastException`, dù method gọi qua interface vẫn kích hoạt advice bình thường.

Ví dụ ý tưởng:

~~~java
PaymentOperations payment = context.getBean(PaymentOperations.class);
payment.pay("A-01");                 // Hợp lệ với JDK proxy và CGLIB proxy

PaymentService impl = (PaymentService) payment;
// ClassCastException nếu payment là JDK dynamic proxy
~~~

Đoạn trên thuộc ứng dụng Spring đã khai báo `PaymentOperations` và `PaymentService`, không phải chương trình chạy độc lập. Nó cho thấy **lỗi thuộc kiểu object runtime**, không phải do method `pay` hay pointcut sai. Ngược lại, nếu Spring tạo **CGLIB class-based proxy**, proxy là subclass của `PaymentService` và có thể cast về `PaymentService` khi class có thể được subclass thành công.

Tình huống thực tế thường xuất hiện sau khi đổi `proxyTargetClass`, sửa cấu hình `@EnableAspectJAutoProxy`, đổi thuộc tính Spring Boot `spring.aop.proxy-target-class`, thêm transaction AOP config hoặc nâng cấu hình Spring khiến proxy đã dùng trước đây được tạo theo cơ chế khác.

**Phạm vi bài:** phân tích lỗi ép kiểu do **Spring AOP proxy**, tái hiện với hai ApplicationContext, cách kiểm tra đúng loại proxy và sửa dependency/call site. Cú pháp `@AspectJ` được dùng chỉ để bật advice trong Spring; bài không bàn sâu AspectJ weaving bên ngoài Spring.

## 2. Hai proxy có quan hệ kiểu khác nhau

Giả sử có:

~~~java
public interface PaymentOperations {
    void pay(String orderId);
}

public class PaymentService implements PaymentOperations {
    @Override
    public void pay(String orderId) {
        System.out.println("SERVICE: paid " + orderId);
    }
}
~~~

Đây là **hai định nghĩa rút gọn**; các file hoàn chỉnh xuất hiện ở phần 4. Spring AOP có hai cách tạo wrapper phổ biến:

~~~text
Target class:
PaymentService implements PaymentOperations

JDK dynamic proxy:
         PaymentOperations
                ^
                |
          jdk.proxy...$Proxy...
                |
         [delegates to target PaymentService]

  proxy instanceof PaymentOperations -> true
  proxy instanceof PaymentService    -> false

CGLIB class proxy:
          PaymentService
                ^
                |
       PaymentService$$SpringCGLIB$$...
                |
         [delegates to target PaymentService]

  proxy instanceof PaymentOperations -> true
  proxy instanceof PaymentService    -> true
~~~

Các tên proxy phía trên chỉ mô tả ý tưởng: phần tiền tố/số hậu tố trong class name có thể đổi theo JDK và Spring version. Hãy kiểm tra bằng `instanceof` và `AopUtils` thay vì so khớp chuỗi tên class.

| Phép kiểm tra trên bean AOP proxy | JDK dynamic proxy | CGLIB class proxy |
| --- | --- | --- |
| `bean instanceof PaymentOperations` | `true` | `true` |
| `bean instanceof PaymentService` | `false` | `true` |
| `((PaymentService) bean)` | `ClassCastException` | Cast thành công nếu proxy đúng target class |
| `AopUtils.isJdkDynamicProxy(bean)` | `true` | `false` |
| `AopUtils.isCglibProxy(bean)` | `false` | `true` |
| `AopUtils.isAopProxy(bean)` | `true` | `true` |
| `bean.getClass() == PaymentService.class` | `false` | `false` |

Điều kiện áp dụng bảng: **cả hai object đều là Spring AOP proxy hợp lệ của cùng loại target**; CGLIB class proxy tạo được và bean thực sự được proxy. Nếu không có advisor nào áp dụng hoặc bean không được container xử lý, đối tượng có thể là target gốc và các kết quả khác đi.

Khi dùng JDK proxy, JVM không cho phép cast xuống `PaymentService` vì proxy không có quan hệ kế thừa với lớp đó. Việc target phía sau proxy là `PaymentService` **không làm chính đối tượng proxy trở thành `PaymentService`**.

## 3. Tại sao đổi cấu hình có thể làm code cũ vỡ?

### 3.1. `proxyTargetClass` chọn cơ chế proxy

Trong Spring Framework thuần:

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
class InterfaceProxyConfig {
}
~~~

Với target triển khai interface và có advisor phù hợp, Spring **thường** chọn JDK dynamic proxy. `false` nghĩa là không ép class-based proxy; khi target không có interface thích hợp, Spring vẫn có thể dùng CGLIB.

Cấu hình khác:

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ClassProxyConfig {
}
~~~

`true` buộc hạ tầng auto-proxy chọn **class-based proxy** khi bean cần AOP. Nếu hai cấu hình kích hoạt cùng một auto-proxy creator trong **cùng ApplicationContext**, thiết lập mạnh hơn (`true`) có thể được hợp nhất và ảnh hưởng **nhiều bean**, không chỉ bean “thuộc” class cấu hình đó.

Một luồng thay đổi dễ gặp:

~~~text
Trước:
bean implements interface
  |
@EnableAspectJAutoProxy(proxyTargetClass = true)
  |
Spring trả CGLIB subclass proxy
  |
(PaymentService) bean -> OK

Sau:
bỏ ép class proxy / đặt false
  |
Spring chọn JDK proxy cho bean có interface
  |
(PaymentService) bean -> ClassCastException
~~~

Chiều ngược lại cũng có thể ảnh hưởng ứng dụng: code vốn giả định `bean.getClass()` là kiểu JDK proxy, lấy method/field bằng reflection, hoặc so sánh chính xác proxy class name có thể không còn phù hợp khi chuyển sang CGLIB. Phần lớn ứng dụng nên phụ thuộc **interface/capability**, không dựa vào implementation runtime của proxy.

### 3.2. Spring Boot có mặc định riêng

Spring Boot khi có AOP auto-configuration thường ưu tiên class-based proxy. Có thể cấu hình:

~~~properties
spring.aop.proxy-target-class=true
~~~

hoặc:

~~~properties
spring.aop.proxy-target-class=false
~~~

Trong cấu hình tương ứng, `false` cho phép dùng interface-based proxy khi interface thích hợp. Tuy nhiên, các annotation hoặc XML AOP/transaction khác có thể đẩy thiết lập hợp nhất thành class proxy trong cùng context. Vì thế **đừng suy ra kiểu proxy cuối cùng chỉ từ một dòng properties**; kiểm tra bean thực tế.

### 3.3. Khi source code cast trực tiếp từ `getBean(...)`

Hai lối lấy bean cần phân biệt:

~~~java
Object bean = context.getBean("paymentService");
PaymentService impl = (PaymentService) bean; // Có thể ClassCastException
~~~

và:

~~~java
PaymentService impl = context.getBean(PaymentService.class);
// Có thể thất bại khi bean thực tế là JDK proxy.
~~~

Cách đầu lấy reference theo tên rồi **ép kiểu Java**, nên `ClassCastException` là kết quả trực tiếp nếu proxy JDK không thể gán cho `PaymentService`. Cách sau là **type-based lookup trong BeanFactory**: tùy bean definition, cơ chế dự đoán kiểu và thời điểm tạo proxy, Spring có thể báo `NoSuchBeanDefinitionException`, `BeanNotOfRequiredTypeException` hoặc lỗi phù hợp khác. Không mặc định rằng mọi lỗi “ép kiểu” trong Spring đều là `ClassCastException`.

Với injection:

~~~java
public PaymentJob(PaymentService paymentService) {
    this.paymentService = paymentService;
}
~~~

Nếu chỉ có bean dạng JDK proxy expose `PaymentOperations`, dependency theo implementation class không còn hợp kiểu và có thể làm context không khởi động được với lỗi autowiring/creation liên quan. Đây là **đoạn constructor minh họa** trong một class có field tương ứng, chưa phải file Java độc lập.

## 4. Ứng dụng Java 17+ tái hiện cả lỗi lẫn cách hoạt động đúng

Ví dụ chạy bằng **Java 17+, Maven 3.9+, Spring Framework 6.2.0**. Hai ApplicationContext sử dụng **cùng định nghĩa service và aspect** nhưng khác cấu hình proxy. Ta chủ động bắt `ClassCastException` ở chế độ JDK để chương trình vẫn chạy và ghi nhận kết quả; ở chế độ CGLIB, cast thành công.

Cấu trúc dự án:

~~~text
spring-aop-proxy-cast/
├── pom.xml
└── src/main/java/example/
    ├── Demo.java
    ├── PaymentOperations.java
    ├── PaymentService.java
    └── AuditAspect.java
~~~

### 4.1. Tạo `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-proxy-cast</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
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
                    <mainClass>example.Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp `AnnotationConfigApplicationContext` và cấu hình bean, `spring-aop` chứa hạ tầng proxy cùng `AopUtils`; `aspectjweaver` cung cấp các kiểu AspectJ dùng khi Spring phân tích `@AspectJ` pointcut. Việc có `aspectjweaver` trong project **không** kích hoạt AspectJ bytecode weaving; mã dưới đây chỉ dùng Spring AOP proxy.

### 4.2. Interface được caller sử dụng

`src/main/java/example/PaymentOperations.java`:

~~~java
package example;

public interface PaymentOperations {
    void pay(String orderId);
}
~~~

### 4.3. Class triển khai interface

`src/main/java/example/PaymentService.java`:

~~~java
package example;

public class PaymentService implements PaymentOperations {
    @Override
    public void pay(String orderId) {
        System.out.println("SERVICE: paid " + orderId);
    }

    public void implementationOnly() {
        System.out.println("IMPLEMENTATION: called");
    }
}
~~~

Method `implementationOnly()` không thuộc interface. Nó dùng để chứng minh một class proxy có thể expose method ở implementation class, còn JDK proxy thì không. Bản thân method này **không được aspect phía dưới advice** vì pointcut chỉ khớp `pay(...)`.

### 4.4. Aspect đảm bảo service cần được proxy

`src/main/java/example/AuditAspect.java`:

~~~java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.PaymentService.pay(..))")
    public void beforePayment() {
        System.out.println("ADVICE: before pay");
    }
}
~~~

Spring nhận diện `AuditAspect` là aspect khi nó được đăng ký thành **Spring bean**. Biểu thức `execution(* example.PaymentService.pay(..))` khớp method execution `pay` trên target. Advisor này khiến `PaymentService` được auto-proxy khi Spring AOP bật, cho phép thử hành vi của cả hai loại proxy.

### 4.5. Chạy hai context với flag khác nhau

`src/main/java/example/Demo.java`:

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class Demo {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class BaseConfig {
        @Bean
        public PaymentService paymentService() {
            return new PaymentService();
        }

        @Bean
        public AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class ForceClassProxyConfig {
    }

    private static void inspect(
            String label,
            AnnotationConfigApplicationContext context,
            boolean expectClassProxy) {

        PaymentOperations bean = context.getBean(PaymentOperations.class);

        boolean aop = AopUtils.isAopProxy(bean);
        boolean jdk = AopUtils.isJdkDynamicProxy(bean);
        boolean cglib = AopUtils.isCglibProxy(bean);
        boolean implementation = bean instanceof PaymentService;

        if (!aop || cglib != expectClassProxy
                || jdk == expectClassProxy
                || implementation != expectClassProxy) {
            throw new IllegalStateException("Unexpected proxy type: " + label);
        }

        System.out.println(label + "_JDK: " + jdk);
        System.out.println(label + "_CGLIB: " + cglib);
        System.out.println(label + "_IS_IMPLEMENTATION: " + implementation);

        bean.pay("A-01");

        if (expectClassProxy) {
            PaymentService service = (PaymentService) bean;
            System.out.println(label + "_CAST: OK");
            service.implementationOnly();
        } else {
            try {
                PaymentService service = (PaymentService) bean;
                service.implementationOnly();
                throw new IllegalStateException("JDK cast unexpectedly worked");
            } catch (ClassCastException expected) {
                System.out.println(label + "_CAST: ClassCastException");
            }
        }
    }

    public static void main(String[] args) {
        try (var jdk =
                new AnnotationConfigApplicationContext(BaseConfig.class)) {
            inspect("JDK", jdk, false);
        }

        try (var cglib = new AnnotationConfigApplicationContext(
                BaseConfig.class, ForceClassProxyConfig.class)) {
            inspect("CGLIB", cglib, true);
        }

        System.out.println("CHECK: PASS");
    }
}
~~~

**Vì sao hai context cho kết quả khác nhau?**

1. `BaseConfig` khai báo `@EnableAspectJAutoProxy(proxyTargetClass = false)`. `PaymentService` implements `PaymentOperations` và có advisor `@Before` áp dụng, nên ở Spring Framework thuần 6.2 ví dụ này dùng **JDK dynamic proxy**.
2. `ForceClassProxyConfig` chỉ bổ sung `@EnableAspectJAutoProxy(proxyTargetClass = true)`, không định nghĩa thêm service hay aspect. Khi nạp **cùng context** với `BaseConfig`, hạ tầng auto-proxy được hợp nhất với thiết lập `true` và tạo **CGLIB class proxy**.
3. Trong cả hai context, người gọi lấy `PaymentOperations` qua Spring container và `bean.pay("A-01")` đều đi qua advisor. Do đó vấn đề cast **không bắt nguồn từ việc Spring AOP advice bị mất**.
4. `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy` đo loại proxy runtime. `bean instanceof PaymentService` xác nhận tính gán kiểu trước khi cast.
5. Nhánh JDK cố tình cast `PaymentOperations` reference sang `PaymentService`. `ClassCastException` được bắt để in dòng giải thích ổn định, tránh phụ thuộc chuỗi exception message của JDK.
6. Nhánh CGLIB cast thành công và gọi được `implementationOnly()`, nhưng method này không match pointcut nên không in thêm `ADVICE`.
7. Điều kiện kiểm tra chủ động ném `IllegalStateException` nếu các giả định proxy không đúng, vì vậy `CHECK: PASS` không phải một dòng được in vô điều kiện ngay từ đầu.

### 4.6. Chạy và kiểm tra output

Chạy tại thư mục `spring-aop-proxy-cast`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do code ứng dụng in ra, đúng thứ tự:

~~~text
JDK_JDK: true
JDK_CGLIB: false
JDK_IS_IMPLEMENTATION: false
ADVICE: before pay
SERVICE: paid A-01
JDK_CAST: ClassCastException
CGLIB_JDK: false
CGLIB_CGLIB: true
CGLIB_IS_IMPLEMENTATION: true
ADVICE: before pay
SERVICE: paid A-01
CGLIB_CAST: OK
IMPLEMENTATION: called
CHECK: PASS
~~~

Maven, SLF4J hoặc Spring có thể phát thêm thông báo tùy môi trường. Chỉ các dòng trên do `System.out.println` của ví dụ tạo ra.

Kết quả đáng chú ý:

- **Cả hai chế độ đều có `ADVICE: before pay`** trước mã nghiệp vụ.
- **Chỉ JDK proxy không gán được về implementation class**; lỗi cast được tạo có chủ ý.
- **CGLIB proxy có thể gán về implementation class**, nhưng khả năng gọi method implementation **không đồng nghĩa method ấy sẽ được advice**.
- `CHECK: PASS` xác nhận loại proxy đúng trong cả hai context và chương trình tới cuối mà không gặp lỗi ngoài dự kiến.

## 5. Cách sửa đúng theo nhu cầu

### 5.1. Ưu tiên interface cho dependency mà caller cần

Nếu business code chỉ cần hợp đồng `pay(...)`, giải pháp có tính ổn định cao là inject/lấy bean theo interface:

~~~java
package example;

public final class PaymentJob {
    private final PaymentOperations payments;

    public PaymentJob(PaymentOperations payments) {
        this.payments = payments;
    }

    public void execute() {
        payments.pay("A-01");
    }
}
~~~

Đây là **class Java hoàn chỉnh**, nhưng để Spring tạo/inject nó cần đăng ký `PaymentJob` là bean trong application, chẳng hạn qua `@Bean` hoặc `@Component`. Kiểu `PaymentOperations` tương thích với JDK proxy và CGLIB proxy. Nếu có nhiều bean cùng interface, thêm `@Qualifier`/`@Primary` để lựa chọn bean phù hợp; các annotation đó **không đổi bản chất loại proxy**.

Với code đang có:

~~~java
PaymentOperations payments = context.getBean(PaymentOperations.class);
payments.pay("A-01");
~~~

Giữ interface xuyên suốt call chain giúp tránh ép kiểu xuống implementation chỉ để gọi method đã được khai báo trong contract.

### 5.2. Thật sự cần phương thức chỉ thuộc implementation?

Trong ví dụ, `implementationOnly()` chỉ thuộc `PaymentService`. Có ba hướng lựa chọn:

1. **Bổ sung method đó vào interface** nếu nó thực sự là hành vi công khai mà caller cần; khi đó JDK proxy có thể expose method đó. Hãy cập nhật interface contract rõ ràng và kiểm tra pointcut/advice nếu cần.
2. **Tách chức năng thành interface/service riêng** nếu implementation-only method không thuộc contract hiện có. Đây thường là giải pháp tốt hơn so với cast dựa trên lớp cụ thể.
3. **Yêu cầu class proxy bằng `proxyTargetClass = true`** khi có lý do bắt buộc làm việc qua implementation class. Cần đánh giá ảnh hưởng tới **các bean AOP khác cùng context**, final class/method, tính tương thích module/JDK và thiết lập AOP/transaction khác. Không nên coi đây là sửa một dòng chỉ tác động đến một bean.

Ép kiểu bằng `(PaymentService)` sau khi kiểm tra `instanceof` có thể tránh exception bằng logic điều kiện, nhưng **không giúp truy cập implementation-only method khi runtime là JDK proxy**. Điều cần sửa là contract hoặc cấu hình, không phải đặt thêm cast.

### 5.3. Tránh tìm implementation class khi không cần

Với JDK proxy, các cách sau có thể gây lỗi ở những giai đoạn khác nhau:

~~~java
Object bean = context.getBean("paymentService");
PaymentService cast = (PaymentService) bean;
~~~

Đây là cast Java trực tiếp có thể ném `ClassCastException`.

~~~java
PaymentService byType = context.getBean(PaymentService.class);
~~~

Đây là lookup theo kiểu concrete có thể thất bại do proxy không gán được về `PaymentService`; loại Spring exception cụ thể phụ thuộc vào việc BeanFactory phân giải và kiểm tra kiểu. Tránh “bắt `ClassCastException`” như cách xử lý duy nhất cho tình huống `getBean(Class)` hoặc autowiring.

Giải pháp interface:

~~~java
PaymentOperations byContract = context.getBean(PaymentOperations.class);
~~~

Tất cả snippet trong phần này đều **đặt trong method đã có biến `context`** và các class mẫu đã định nghĩa ở phần 4; không phải file chạy riêng.

### 5.4. Lấy thông tin target mà không cast proxy thành target

Khi cần phục vụ logging/debug:

~~~java
Object bean = context.getBean("paymentService");

System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(
    org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(
    org.springframework.aop.support.AopUtils.isCglibProxy(bean));
System.out.println(
    org.springframework.aop.support.AopUtils.getTargetClass(bean).getName());
~~~

`AopUtils.getTargetClass(bean)` giúp xem lớp target được Spring AOP biết đến, **không biến proxy thành instance của lớp đó**. Đây là đoạn kiểm tra chèn vào ứng dụng hiện có; nó không khuyên tháo proxy để gọi target trực tiếp. Lấy target object và gọi thẳng vào nó có thể bỏ qua advice, transaction và security.

## 6. Những “cách sửa” dễ tạo lỗi mới

| Cách thử | Vì sao chưa đúng hoặc chưa đủ? |
| --- | --- |
| Thêm `(PaymentService)` ở nhiều nơi | Không đổi type hierarchy của JDK proxy; vẫn `ClassCastException` |
| Dùng `@Qualifier("paymentService")` nhưng field/constructor type là `PaymentService` | `@Qualifier` chọn bean theo tên/metadata, không biến JDK proxy thành implementation |
| Đổi `proxyTargetClass = true` trên một config rồi cho rằng chỉ bean đó bị ảnh hưởng | Auto-proxy settings có thể hợp nhất, đổi loại proxy cho nhiều bean cùng context |
| Cho rằng `@Aspect` hoặc `@Before` tạo CGLIB proxy | Aspect khai báo advisor; loại proxy do hạ tầng và cấu hình quyết định |
| Thêm `aspectjweaver` hoặc `-javaagent` chỉ để chữa cast | Thay đổi sang weaving là vấn đề khác; class cast của Spring proxy cần xử lý ở contract/proxy strategy |
| Cast sau khi gọi `AopUtils.getTargetClass` | Metadata target class không làm reference trở thành object của class đó |
| Lấy trực tiếp target object bên trong proxy rồi gọi method | Có thể bỏ qua advice và những behavior dựa trên Spring AOP |
| Chuyển toàn bộ class/method thành `final` rồi ép CGLIB | CGLIB subclass proxy không thể override `final` method hoặc subclass `final` class |
| Kiểm tra `bean.getClass() == PaymentService.class` để xác nhận advice | Với cả JDK và CGLIB, proxy runtime class thường khác target class |
| Coi `this.pay()` được advice sau khi ép CGLIB | Self-invocation trên target vẫn không qua Spring proxy |

Bật CGLIB vì cast ở một vị trí có thể gây tác động phụ đối với các bean khác: class `final` không proxy hóa được bằng subclass, method `final`/`private` không thể override để intercept, và các điểm injection theo interface hoặc reflection có thể vận hành khác mong đợi. Cần xem toàn bộ các bean có advisor khi thay đổi cấu hình toàn context.

## 7. Quy trình xác định nguyên nhân trong ứng dụng Spring

Khi gặp `ClassCastException` chứa class name dạng `jdk.proxy...$Proxy...` hoặc lỗi inject/lookup theo implementation:

1. **Xác định reference thật:** bean đến từ `ApplicationContext` hay được tạo bằng `new`? Nếu từ Spring, ghi tên bean và phương thức dùng để lookup/inject. Với proxy, lỗi cast phụ thuộc type runtime.
2. **Kiểm tra interface và implementation:** target có interface nào? Điểm gọi đang cần contract method hay method chỉ nằm trong implementation?
3. **Đo ba trạng thái trên reference:** `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`, kết hợp `instanceof Interface` và `instanceof Implementation`.
4. **Tìm thiết lập proxy hiệu lực:** `@EnableAspectJAutoProxy`, `proxyTargetClass`, Spring Boot AOP properties, XML `<aop:aspectj-autoproxy/>`, transaction auto-proxy config, context cha/con và các thiết lập gộp.
5. **Kiểm tra vì sao bean được proxy:** advisor/`@Aspect` nào khớp; một bean không khớp advisor có thể là target thường và không tái hiện lỗi.
6. **Đổi đúng thiết kế dependency:** ưu tiên interface cho hành vi công khai, dùng `@Qualifier` nếu có nhiều implementation. Nếu bắt buộc method ở implementation, cân nhắc đổi contract hoặc class proxy.
7. **Kiểm tra lớp và method khi ép CGLIB:** `final`, `private`, visibility, Java modules và trạng thái subclassing.
8. **Chạy lại kiểm chứng:** assert đúng loại proxy, gọi method qua reference bean và xác nhận advice chạy; không dừng ở việc cast không còn ném exception.

### Phân biệt các loại lỗi

- **`ClassCastException` tại dòng `(PaymentService) object`**: reference runtime không phải instance của class ấy; nếu là JDK proxy thì đây là hệ quả tự nhiên.
- **`BeanNotOfRequiredTypeException` / lỗi lookup concrete type**: bean Spring không phù hợp kiểu mà client yêu cầu; xem dấu vết BeanFactory và injection point.
- **`NoSuchBeanDefinitionException`**: không tìm thấy bean đáp ứng kiểu/tên yêu cầu trong context được tra cứu; có thể là sai context, thiếu đăng ký hoặc kiểu expose khác.
- **`NoUniqueBeanDefinitionException`**: có nhiều bean cùng interface, cần chọn bằng `@Qualifier`/`@Primary` — đây không phải lỗi cast JDK/CGLIB.
- **Advice không chạy dù bean cast được**: cast thành công **không bảo đảm proxy tồn tại** hay pointcut khớp. Kiểm tra `AopUtils.isAopProxy` và lời gọi qua proxy.

## 8. Câu hỏi tự kiểm tra

1. **Tại sao JDK proxy có thể được gán cho `PaymentOperations` nhưng không cho `PaymentService`?**  
   Vì proxy thực thi interface, không phải subclass của implementation class.

2. **Dùng CGLIB là mọi cast xuống concrete class đều an toàn?**  
   Không. Chỉ an toàn khi reference thực sự là instance/subclass của class mong muốn, target đủ điều kiện subclass và không có nhầm lẫn bean.

3. **Một bean chỉ có method công khai qua interface cần sửa thế nào để không phụ thuộc loại proxy?**  
   Inject/lấy và gọi qua interface, tránh ép xuống implementation.

4. **`@Qualifier` có chữa ClassCastException do JDK proxy?**  
   Không. Nó chỉ giúp chọn bean, không sửa type hierarchy.

5. **Vì sao `getBean(PaymentService.class)` và `(PaymentService) getBean("paymentService")` có thể tạo exception khác nhau?**  
   Cách đầu là lookup/type checking do Spring thực hiện, còn cách sau là cast object ở JVM.

6. **Chỉ cần thêm `proxyTargetClass = true` để hết lỗi mọi nơi?**  
   Không. Cấu hình có phạm vi theo context/auto-proxy creator, có thể ảnh hưởng nhiều bean và có giới hạn subclassing; ưu tiên kiểm tra contract trước.

7. **CGLIB có sửa được self-invocation không?**  
   Không. `this.otherMethod()` trong target vẫn có thể đi vòng ngoài Spring proxy.

## Tài liệu Spring Framework

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK dynamic proxy, CGLIB proxy, giới hạn và self-invocation.
- [Spring Framework 6.2 — AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html): mô hình proxy của Spring AOP.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): cơ chế Spring dùng cú pháp khai báo aspect.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): cấu hình `@EnableAspectJAutoProxy`.
- [Spring Boot Reference — AOP](https://docs.spring.io/spring-boot/reference/features/aop.html): `spring.aop.proxy-target-class` trong Boot.
