# Spring AOP: JDK dynamic proxy dựa trên interface và bề mặt phương thức được cung cấp

## 1. Vai trò của JDK proxy trong Spring AOP

Trong Spring AOP, **JDK dynamic proxy** là proxy Java được Spring tạo để chặn lời gọi đến **các phương thức public được công bố qua interface của bean**. Nếu Spring chọn JDK proxy cho một target có interface, caller nhận đối tượng proxy **triển khai interface**, còn đối tượng nghiệp vụ thật nằm phía sau proxy.

Ví dụ:

```java
public interface BillingPort {
    void pay(String orderId);
}

public class BillingService implements BillingPort {
    @Override
    public void pay(String orderId) {
        System.out.println("paid " + orderId);
    }

    public void implementationOnly() {
        System.out.println("internal API");
    }
}
```

Đây là fragment minh họa, chưa phải chương trình chạy độc lập. Với **JDK proxy cho `BillingService`**, caller có thể dùng `BillingPort.pay(...)` trên reference proxy. Phương thức `implementationOnly()` chỉ khai báo ở implementation nên **không được JDK proxy cung cấp qua interface**; ngay cả khi public và pointcut mô tả nó, Spring AOP qua JDK proxy cũng không có lời gọi bên ngoài nào đến phương thức này để intercept.

Luồng xử lý:

```text
Spring IoC container
    |
    +-- đăng ký bean target BillingService
    |           |
    |           v
    |      khởi tạo target
    |           |
    |       Spring AOP
    |           |
    |    advisor/pointcut khớp
    |           |
    |   JDK proxy implements BillingPort
    |           |
    +------ inject proxy vào consumer
                |
          port.pay("A1")
                |
            JDK proxy
                |
         interceptor/advice
                |
       BillingService.pay("A1")
```

**Điều kiện cần nhớ:** không phải cứ có interface là Spring tự tạo proxy. Target cần là Spring bean, hạ tầng AOP phải được cấu hình và có advisor/advice áp dụng. JDK proxy chỉ là **cách tạo proxy khi cần**, không phải cơ chế đăng ký bean.

Bài này chỉ phân tích JDK dynamic proxy trong **Spring AOP dựa trên proxy**. Không mở rộng sang các cơ chế weaving bytecode của AspectJ.

## 2. “Dựa trên interface” có nghĩa chính xác là gì?

### 2.1. Proxy triển khai interface, không kế thừa implementation class

Khi cấu hình chọn JDK proxy, object mà Spring công bố thường có các tính chất:

- `proxy instanceof BillingPort` là `true`: proxy thực hiện hợp đồng interface.
- `proxy instanceof BillingService` là `false`: JDK proxy không phải subclass của `BillingService`.
- Nếu ép `(BillingService) proxy`, một runtime cast không phù hợp sẽ ném `ClassCastException`.
- Nếu bean được inject vào constructor nhận `BillingPort`, kiểu tương thích. Nếu constructor bắt buộc nhận `BillingService` trong khi Spring trả JDK proxy, việc resolve dependency có thể thất bại do không tương thích kiểu.

Trong ứng dụng Spring, mã consumer nên nhận **interface mà proxy thực sự triển khai**:

```java
@Component
public class CheckoutHandler {
    private final BillingPort billing;

    public CheckoutHandler(BillingPort billing) {
        this.billing = billing;
    }

    public void checkout(String orderId) {
        billing.pay(orderId);
    }
}
```

Đoạn này minh họa constructor injection. Một constructor duy nhất thường không cần `@Autowired`. Muốn JDK proxy hoạt động, `CheckoutHandler` và `BillingService` phải được container quản lý và Spring AOP phải được bật.

### 2.2. Proxy hỗ trợ những phương thức business nào?

**Bề mặt phương thức business** của JDK proxy được xác định bởi các interface mà proxy được cấu hình để triển khai:

| Phương thức / thành viên | Gọi được từ reference JDK proxy? | Ý nghĩa với Spring AOP |
| --- | --- | --- |
| `public void pay(...)` khai báo trong `BillingPort` | Có | Có thể bị advice nếu pointcut khớp và caller đi qua proxy |
| `default String channel()` trong interface | Có | Là public interface method; có thể được advice khi có pointcut tương ứng |
| Method kế thừa từ superinterface | Có | Thuộc hợp đồng public interface của proxy |
| Một method từ interface thứ hai mà proxy cũng triển khai | Có | Spring có thể proxy nhiều interface; consumer phải có kiểu phù hợp để gọi |
| `public void implementationOnly()` chỉ nằm trên class target | Không, qua bề mặt interface JDK proxy | Pointcut đúng tên cũng không làm proxy tự xuất bản method này |
| Method `protected` hoặc package-private chỉ có trên implementation | Không | Không phải public interface contract của JDK proxy |
| Method `private` của target | Không | Không được expose và không thể gọi bên ngoài qua JDK proxy |
| `static` method trên interface/class | Không như lời gọi instance proxy | Gọi theo tên type; không đi qua AOP instance proxy |
| `private` helper method trong interface | Không từ bên ngoài | Chỉ được dùng nội bộ interface; không phải API của proxy |

**Ngoại lệ quan trọng về phạm vi quan sát:** Một JDK proxy là một Java object nên còn có các phương thức thuộc `Object` và đôi khi các interface hạ tầng Spring AOP. Không nên phát biểu rằng `proxy.getClass().getMethods()` chứa **đúng và chỉ đúng** các method trong một interface nghiệp vụ. Phần cần quan tâm là **những phương thức ứng dụng có thể gọi theo hợp đồng business interface**.

Không phải cứ method nằm trong interface là advice chắc chắn chạy: nó còn phải được advisor/pointcut chọn. Interface quyết định **method có thể được caller gọi trên proxy**; pointcut quyết định **lời gọi nào được advice**.

### 2.3. Nhiều interface và kế thừa interface

Một target có thể triển khai nhiều interface:

```java
interface PaymentOperations {
    void pay(String id);
}

interface AuditOperations {
    void audit(String id);
}

class PaymentEngine implements PaymentOperations, AuditOperations {
    public void pay(String id) { /* ... */ }
    public void audit(String id) { /* ... */ }
    public void internalRebuild() { /* ... */ }
}
```

Nếu Spring dùng JDK proxy mặc định cho các interface của target, proxy có thể triển khai cả `PaymentOperations` và `AuditOperations`. Vì vậy:

- Consumer theo `PaymentOperations` gọi `pay`; consumer theo `AuditOperations` gọi `audit`.
- Consumer đang giữ biến kiểu `PaymentOperations` không thể gọi `audit` qua biến đó trừ khi đổi kiểu sang interface tương thích mà proxy thực sự thực hiện.
- `internalRebuild` không thuộc hai interface nên không thể gọi qua JDK proxy.
- Với cấu hình Spring AOP cấp thấp hoặc giới hạn exposed interfaces có chủ đích, danh sách interface được proxy thực sự cung cấp có thể được tùy chỉnh. Hãy kiểm tra object được inject thay vì giả định.

Bề mặt API của JDK proxy không phải **toàn bộ public methods** của implementation class. Đây là điểm khác biệt quan trọng với class-based proxy (CGLIB).

## 3. Spring chọn JDK proxy như thế nào?

### 3.1. Spring Framework thuần với `@EnableAspectJAutoProxy`

Khi dùng cách khai báo `@Aspect`, cần đăng ký aspect làm Spring bean và kích hoạt auto-proxy:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
@ComponentScan("demo.springjdk")
class AopConfiguration {
}
```

Đây là snippet cấu hình. Trong Spring Framework thuần, `proxyTargetClass=false` là mặc định của `@EnableAspectJAutoProxy`; với target có interface phù hợp, Spring thường tạo JDK proxy. Nếu target không có interface, Spring có thể dùng CGLIB dù giá trị cấu hình là `false`.

Để dùng `@Aspect` trong Spring Framework thuần cần các dependency Spring Context/AOP và thư viện AspectJ cho việc phân tích pointcut. Không cần chạy AspectJ compiler hoặc load-time weaving để dùng Spring AOP proxy.

### 3.2. Spring Boot có mặc định khác

Spring Boot có AOP auto-configuration khi dependency thích hợp (chẳng hạn `spring-boot-starter-aop`) hiện diện. Theo mặc định, Boot ưu tiên **CGLIB class-based proxies**. Nếu muốn JDK proxy đối với bean có interface, cấu hình:

```properties
spring.aop.proxy-target-class=false
```

Trong Spring Framework thuần, `@EnableAspectJAutoProxy(proxyTargetClass=false)` thường đã đủ để ưu tiên JDK proxy. Trong Spring Boot, hãy kiểm tra property trên và các cấu hình proxy khác trước khi kết luận loại proxy.

Spring có thể hợp nhất nhiều yêu cầu auto-proxy cùng context; cấu hình ép class-based proxy từ một thành phần khác có thể khiến giá trị thực tế khác mong đợi. Vì thế `AopUtils.isJdkDynamicProxy(bean)` là phép kiểm tra thực nghiệm tốt hơn việc chỉ đọc một annotation.

### 3.3. So sánh đúng phạm vi với CGLIB

| Tiêu chí | JDK proxy trong Spring AOP | CGLIB trong Spring AOP |
| --- | --- | --- |
| Hình thức | Tạo object triển khai interface | Tạo subclass của target class |
| Cần interface trên target? | Có interface để công bố qua JDK proxy | Không bắt buộc |
| Consumer nên inject | Interface | Interface hoặc class tương thích |
| Method public chỉ có ở implementation | Không được proxy công bố | Có thể được intercept nếu lời gọi đi qua proxy và phương thức có thể override |
| Target là `final class` | Có thể dùng JDK proxy nếu target triển khai interface thích hợp | Không subclass được `final class` |
| Target có `final` implementation method công bố trong interface | JDK proxy vẫn có thể intercept lời gọi **vào interface** do không cần override target method | Không override được final method nên không advice theo cách class proxy |
| Self-invocation `this.method()` | Bỏ qua proxy | Cũng bỏ qua proxy |

Chọn loại proxy vì **hợp đồng dependency và bề mặt method cần advice**; tránh ép CGLIB chỉ để sửa một lỗi injection nếu interface đã mô tả đúng API nghiệp vụ.

## 4. Điểm dễ nhầm giữa “interface method” và “pointcut match”

### 4.1. Pointcut có thể nói đến implementation method được interface công bố

Spring AOP có thể xử lý pointcut mô tả method thực thi trên concrete target:

```java
@Before("execution(* demo.springjdk.BillingService.pay(..))")
public void beforePay() {
    System.out.println("[aop] before pay");
}
```

Dù caller đang gọi `BillingPort.pay(...)` qua JDK proxy, method thực thi đằng sau là `BillingService.pay(...)`. Spring dùng thông tin target class khi đánh giá pointcut; nên biểu thức dựa trên concrete implementation như trên vẫn có thể khớp.

Ngược lại, nếu pointcut chọn `BillingService.implementationOnly()` mà method ấy **không có trên proxy interface**, không có lời gọi bên ngoài qua JDK proxy để kích hoạt advice cho nó. Đổi riêng pointcut không mở rộng bề mặt interface của JDK proxy.

### 4.2. `this` và `target` trong Spring AOP không nhất thiết cùng kiểu

Trong Spring AOP, `this(...)` trong biểu thức pointcut diễn tả **proxy object**; `target(...)` diễn tả **target object**. Với JDK proxy cho `BillingService implements BillingPort`:

- `this(demo.springjdk.BillingPort)` có thể khớp vì proxy triển khai `BillingPort`.
- `this(demo.springjdk.BillingService)` không khớp đối với JDK proxy vì proxy không kế thừa class ấy.
- `target(demo.springjdk.BillingService)` có thể khớp vì đối tượng thực thi là target class.

Đây là ý nghĩa **cụ thể của Spring proxy**. Cần hiểu chúng khi chuyển một cấu hình AOP từ CGLIB sang JDK proxy hoặc ngược lại.

### 4.3. Annotation trên interface và implementation

Khi làm việc với các annotation được Spring xử lý qua AOP như `@Transactional` hoặc custom marker kết hợp `@annotation`, đừng coi việc annotation nằm trên interface và nằm trên implementation là luôn tương đương trong **mọi cấu hình proxy, advice và pointcut**.

- Một advice có thể kiểm tra annotation trên method và target class theo quy tắc riêng.
- Một số hạ tầng Spring (ví dụ transaction metadata) tìm annotation theo cả method triển khai và class.
- Một biểu thức pointcut cụ thể như `@annotation(...)` có cách match riêng; cần kiểm tra thực tế khi annotation được đặt ở interface nhưng method thực thi ở class.
- Đặt annotation tại nơi framework liên quan có thể nhận diện rõ ràng và viết integration test cho lời gọi qua proxy.

Phạm vi của JDK proxy vẫn dựa vào interface được công bố, bất kể annotation xuất hiện trên method hay class nào.

## 5. Ví dụ đầy đủ: interface công bố hai method, implementation còn method thứ ba

Ví dụ dùng **Java 17**, **Maven** và **Spring Framework 6.2.x** không cần Spring Boot. Hạ tầng Spring AOP tạo **JDK proxy** cho bean `BillingService` có interface `BillingPort`. Người dùng sẽ quan sát:

1. Reference được Spring inject là JDK proxy và không phải instance của concrete class.
2. Lời gọi `pay(...)` trên proxy chạy advice.
3. Method `implementationOnly(...)` có trên target nhưng không có trong bề mặt JDK proxy.
4. Lời gọi `this.pay(...)` bên trong target bỏ qua proxy (self-invocation).

Cấu trúc file:

```text
spring-jdk-proxy/
├── pom.xml
└── src/main/java/demo/springjdk/
    ├── AppConfig.java
    ├── BillingPort.java
    ├── BillingService.java
    ├── BillingAspect.java
    ├── ClientJob.java
    └── Main.java
```

### 5.1. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-jdk-proxy</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Tệp `src/main/java/demo/springjdk/BillingPort.java`

```java
package demo.springjdk;

public interface BillingPort {
    void pay(String orderId);
    void submit(String orderId);
}
```

Hai phương thức public này thuộc **API nghiệp vụ của proxy**. Vì được interface công bố, cả `pay` và `submit` đều có thể được gọi trên reference `BillingPort`; tuy nhiên aspect bên dưới chỉ advice `pay`.

### 5.3. Tệp `src/main/java/demo/springjdk/BillingService.java`

```java
package demo.springjdk;

import org.springframework.stereotype.Service;

@Service
public class BillingService implements BillingPort {
    @Override
    public void pay(String orderId) {
        System.out.println("[service] pay " + orderId);
    }

    @Override
    public void submit(String orderId) {
        System.out.println("[service] submit " + orderId);
        this.pay(orderId); // Self-invocation: không đi qua AOP proxy.
    }

    public void implementationOnly(String orderId) {
        System.out.println("[service] implementationOnly " + orderId);
    }
}
```

Lưu ý: `implementationOnly` là public method của class, nhưng **không nằm trong `BillingPort`**; bởi vậy JDK proxy không expose method này ra business surface.

### 5.4. Tệp `src/main/java/demo/springjdk/BillingAspect.java`

```java
package demo.springjdk;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class BillingAspect {
    @Before("execution(* demo.springjdk.BillingService.pay(..))")
    public void beforePay() {
        System.out.println("[aspect] before pay");
    }
}
```

Aspect được Spring component scan phát hiện vì có `@Component`. Biểu thức `execution` chọn method `pay` trên target class. Các method không khớp, ví dụ `submit`, sẽ không được advice chỉ vì cùng nằm trên proxy.

### 5.5. Tệp `src/main/java/demo/springjdk/AppConfig.java`

```java
package demo.springjdk;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

Spring scan toàn bộ package chứa `AppConfig`. `BillingPort` là interface, còn `BillingService` có `@Service` nên được đăng ký bean. `@EnableAspectJAutoProxy` kích hoạt hạ tầng AOP, và `proxyTargetClass=false` ưu tiên JDK dynamic proxy cho bean này.

### 5.6. Tệp `src/main/java/demo/springjdk/ClientJob.java`

```java
package demo.springjdk;

import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Component
public class ClientJob {
    private final BillingPort billing;

    public ClientJob(BillingPort billing) {
        this.billing = billing;
        System.out.println("[client] injectedJdkProxy="
                + AopUtils.isJdkDynamicProxy(billing));
    }

    public void run() {
        System.out.println("[client] run");
        billing.pay("ORD-1");
        billing.submit("ORD-2");
    }
}
```

`ClientJob` yêu cầu dependency qua **interface**, nên reference JDK proxy tương thích với constructor. `pay` chạy advice; `submit` không được aspect này chọn, còn lời gọi `this.pay(...)` trong `submit` bypass proxy.

### 5.7. Tệp `src/main/java/demo/springjdk/Main.java`

```java
package demo.springjdk;

import java.util.Arrays;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            BillingPort port = context.getBean(BillingPort.class);

            System.out.println("[main] isJdkProxy="
                    + AopUtils.isJdkDynamicProxy(port));
            System.out.println("[main] isImplementation="
                    + (port instanceof BillingService));

            boolean exposesOnlyMethod =
                    Arrays.stream(port.getClass().getMethods())
                            .anyMatch(m -> m.getName().equals("implementationOnly"));
            System.out.println("[main] extraVisible=" + exposesOnlyMethod);

            context.getBean(ClientJob.class).run();

            // Tạo target Java riêng; không thuộc Spring AOP proxy.
            new BillingService().implementationOnly("ORD-3");
        }
    }
}
```

Dùng reflection ở đây chỉ để **quan sát proxy surface**, không phải cách business code nên gọi service. `getMethods()` cũng chứa những method khác từ Java Object và framework interfaces; phép kiểm tra chỉ hỏi riêng tên `implementationOnly`.

### 5.8. Lệnh chạy và kết quả

Trong thư mục có `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.springjdk.Main
```

Những dòng `System.out` của chương trình (không tính log của Maven hay Spring nếu môi trường in thêm):

```text
[client] injectedJdkProxy=true
[main] isJdkProxy=true
[main] isImplementation=false
[main] extraVisible=false
[client] run
[aspect] before pay
[service] pay ORD-1
[service] submit ORD-2
[service] pay ORD-2
[service] implementationOnly ORD-3
```

**Giải thích theo thứ tự:**

1. Khi tạo singleton `ClientJob`, Spring resolve `BillingPort` và inject proxy. Constructor in `injectedJdkProxy=true`.
2. `context.getBean(BillingPort.class)` nhận cùng loại reference Spring quản lý; `isJdkProxy=true` xác minh loại proxy thực tế.
3. `isImplementation=false` cho thấy object proxy không phải instance của concrete class; `extraVisible=false` cho thấy method chỉ trên implementation không được xuất bản trên JDK proxy.
4. `billing.pay("ORD-1")` qua JDK proxy khiến advice in `before pay`, rồi target thực thi `pay`.
5. `billing.submit("ORD-2")` đi vào proxy nhưng aspect không chọn `submit`. Target `submit` dùng `this.pay("ORD-2")`, bỏ qua proxy, nên **không có advice** trước dòng `pay ORD-2`.
6. `new BillingService().implementationOnly("ORD-3")` gọi phương thức trực tiếp trên một object Java tự tạo. Method vẫn chạy, nhưng không có Spring AOP advice.

**Điểm cần phân biệt:** dòng cuối không chứng minh `implementationOnly` không thể chạy trong Java. Nó chỉ minh họa bề mặt JDK proxy của bean và việc tạo object riêng không chịu interception của Spring AOP.

## 6. Thử nghiệm mở rộng và kết quả cần quan sát

### 6.1. Muốn advice `implementationOnly` thì đổi gì?

Nếu vẫn giữ JDK proxy, chỉ thêm:

```java
@Before("execution(* demo.springjdk.BillingService.implementationOnly(..))")
public void beforeImplementationOnly() {
    System.out.println("[aspect] before implementationOnly");
}
```

vào `BillingAspect` sẽ **không đủ** để caller truy cập implementation-only method qua `BillingPort`. Snippet này là phần method bổ sung của aspect, không phải file Java chạy độc lập.

Hai hướng thiết kế hợp lệ:

1. **Đưa method vào interface nghiệp vụ thích hợp**, ví dụ thêm `void implementationOnly(String id)` vào `BillingPort` nếu nó thực sự thuộc API công khai. Khi ấy JDK proxy có thể expose method, pointcut phù hợp có thể advice lời gọi qua proxy.
2. **Dùng class-based proxy** cho những trường hợp cố ý expose public method của concrete class, miễn class/method có thể proxy. Với Spring Framework thuần, có thể cấu hình `@EnableAspectJAutoProxy(proxyTargetClass = true)`. Cân nhắc thiết kế interface trước khi ép loại proxy.

Thêm method vào interface là thay đổi hợp đồng API; không nên làm chỉ để đưa một helper nội bộ vào AOP.

### 6.2. Đổi sang CGLIB để so sánh surface

Trong `AppConfig` đổi:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

Với class `BillingService` không `final`, Spring tạo class-based proxy. Hai kết quả đầu khi kiểm tra sẽ khác:

```text
[main] isJdkProxy=false
[main] isImplementation=true
```

Và phép kiểm tra `implementationOnly` trong `Main` thành `extraVisible=true` vì proxy subclass kế thừa method public này. Để xác nhận advice cho method mới, cần thêm pointcut phù hợp **và gọi qua Spring proxy**; không phải cứ CGLIB là mọi method đều có advice.

Lưu ý đoạn constructor `ClientJob` sẽ in `injectedJdkProxy=false`, vì proxy class-based không được `isJdkDynamicProxy` nhận diện.

### 6.3. Đổi consumer sang inject implementation khi đang JDK proxy

Nếu thay constructor:

```java
public ClientJob(BillingService billing) {
    // ...
}
```

trong khi Spring đang tạo JDK proxy, có thể gặp lỗi tạo bean hoặc resolve dependency do object proxy không là `BillingService`. Đây là lỗi **hợp đồng kiểu**, không phải do pointcut `pay`. Cách ưu tiên: giữ `BillingPort` là kiểu dependency. Nếu cần concrete class thật sự, xem xét class proxy và giới hạn của nó.

### 6.4. Nếu class target là `final`?

Một `final class BillingService implements BillingPort` vẫn có thể được Spring AOP áp dụng **JDK interface proxy**, bởi proxy không cần subclass target. Tương tự, một implementation method `final` nhưng được public interface khai báo có thể bị advice khi caller gọi qua JDK proxy: proxy chặn lời gọi ở interface boundary, rồi ủy quyền đến target method.

Với CGLIB, final class không thể subclass và final method không thể override để intercept. Đây là khác biệt thiết kế có ý nghĩa, dù không nên cố tình lạm dụng `final` chỉ để chọn một công nghệ proxy.

### 6.5. Nếu gọi method từ chính target?

Ngay cả khi method nằm trong interface, tự gọi `this.pay()` bên trong target vẫn **không đi qua proxy**, nên advice không tự chạy. Có thể chuyển nghiệp vụ cần intercept sang Spring bean khác và inject dependency; đây là cách rõ ràng hơn so với lạm dụng `AopContext.currentProxy()`.

## 7. Những lưu ý khi thiết kế interface cho Spring AOP

### Chỉ đưa hành vi public cần thiết vào interface

Một interface nhỏ, ổn định, mô tả ranh giới nghiệp vụ làm consumer phụ thuộc ít hơn vào implementation. Đừng expose method hỗ trợ kỹ thuật/private concern chỉ để có thể advice qua JDK proxy.

Nếu ứng dụng có nhiều interface, hãy chú ý bean thực sự được Spring công bố có những interface nào; các interface kỹ thuật có thể vô tình làm API của proxy rộng hơn dự kiến. Hãy dùng kiểu interface cần thiết ngay tại điểm injection.

### Lưu ý default method của interface

Một interface có thể khai báo default method:

```java
public interface BillingPort {
    void pay(String orderId);

    default String providerName() {
        return "default";
    }
}
```

`providerName()` là public instance method thuộc interface nên caller của JDK proxy có thể gọi nó. Việc advice chạy vẫn phụ thuộc pointcut và lời gọi qua proxy. Trong trường hợp default method gọi một method khác trong cùng interface, cần kiểm tra thực tế đường dispatch/proxy trong Spring phiên bản sử dụng; không suy đoán advice chỉ từ việc method là `default`.

Ngược lại, `static` methods không phải instance method trên proxy; private interface helpers không thuộc API public.

### Exceptions, overload và generics vẫn theo hợp đồng Java

JDK proxy thể hiện signature của các interface. Khi caller giữ reference kiểu `BillingPort`, compiler kiểm tra tham số, kiểu trả về và checked exceptions theo interface ấy. Overloaded method cần được khai báo đủ trên interface để caller chọn overload tương ứng.

Spring AOP có thể thực hiện advice trên từng overload nếu pointcut khớp; việc generics được biên dịch thành erased types/bridge methods có thể ảnh hưởng cách một pointcut hoặc reflection nhìn method. Với tình huống phức tạp, viết integration test trên **bean được DI thực tế**, thay vì suy luận từ source signature một cách máy móc.

### Proxy không biến object tạo bằng `new` thành Spring bean

Nếu code sử dụng `new BillingService()` và giữ object ấy, Spring không tự cấp JDK proxy. Ngược lại, phương thức `@Bean` **được Spring gọi** có thể dùng `new BillingService()` rồi trả về object cho container; Spring vẫn có cơ hội hậu xử lý và tạo proxy. Điểm quyết định là reference object được quản lý và công bố qua container.

### Phân biệt proxy interface và target class khi debug

Dùng công cụ Spring:

```java
AopUtils.isAopProxy(bean);
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
```

Đây là các lời gọi API minh họa trên một biến `bean` lấy từ context. Không nên dựa vào tên class runtime, hậu tố của proxy hoặc việc `getClass()==Target.class` khi cần xác định chế độ AOP. Nếu aspect không chạy, kiểm tra cả **đường gọi** (qua proxy hay self-invocation), pointcut, giới hạn surface và cấu hình bean.

## 8. Checklist khắc phục sự cố thực tế

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra / xử lý |
| --- | --- | --- |
| Inject interface chạy, inject class cụ thể thất bại | Bean là JDK proxy chỉ triển khai interface | Dùng interface ở injection point; kiểm tra `AopUtils.isJdkDynamicProxy` |
| Service có public helper nhưng không gọi được trên proxy | Helper chỉ có ở implementation | Đưa vào interface nếu thật sự là API, hoặc cân nhắc class proxy |
| Tăng phạm vi pointcut vẫn không intercept implementation-only method | Method không được JDK proxy expose | Xác định trước surface của proxy và cách caller gọi |
| Có `@Aspect` nhưng bean không thành proxy | Aspect chưa được đăng ký thành Spring bean, chưa bật AOP hoặc pointcut không khớp | Kiểm tra `@Component`/`@Bean`, `@EnableAspectJAutoProxy` và context |
| Tưởng mặc định Spring Boot là JDK proxy | Boot thường mặc định CGLIB | Xem `spring.aop.proxy-target-class=false` và xác minh proxy |
| Spring Framework đã đặt `proxyTargetClass=false` nhưng vẫn CGLIB | Target không có interface hoặc có cấu hình auto-proxy khác ưu tiên class proxy | Kiểm tra target interfaces và các cấu hình chung |
| Interface có `pay` nhưng advice không chạy khi `this.pay()` | Self-invocation bỏ qua proxy | Gọi qua bean khác được DI |
| Aspect dùng `this(ImplementationClass)` không khớp | Với JDK proxy, `this` là proxy không kế thừa implementation | Xem `this(Interface)` hoặc `target(ImplementationClass)` phù hợp |
| Method `final` vẫn được advice qua JDK proxy | JDK proxy intercept interface method, không override target | Phân biệt giới hạn JDK proxy với CGLIB |
| API có nhiều interface nhưng consumer chỉ thấy một nhóm method | Kiểu biến tham chiếu chỉ công bố interface mà nó khai báo | Dùng kiểu interface phù hợp; xác minh proxy thực hiện các interface cần thiết |

Quy trình phân tích một lỗi cụ thể: xác định target và aspect có thuộc Spring container → xác nhận có proxy → xác nhận proxy là JDK hay CGLIB → kiểm tra caller giữ reference kiểu nào → so sánh method được gọi với interface proxy công bố → kiểm tra pointcut → kiểm tra lời gọi có đi qua proxy hay không.

## 9. Câu hỏi tự kiểm tra

**1. Một class có ba public methods nhưng interface chỉ khai báo một. Với JDK proxy, caller gọi được mấy public method nghiệp vụ qua interface ấy?** Một method theo hợp đồng interface đó (ngoài những method khác của `Object`/hạ tầng nếu xét reflection). Hai public method chỉ có ở implementation không tự được JDK proxy công bố.

**2. Vì sao `getBean(BillingPort.class)` thường hoạt động nhưng yêu cầu bean theo `BillingService.class` có thể lỗi?** Vì JDK proxy triển khai interface, không phải subclass của implementation.

**3. Một method implementation đánh dấu `final` có nhất thiết ngăn AOP advice qua JDK proxy không?** Không. Nếu method được interface công bố và caller gọi qua JDK proxy, việc final trên target không cản trở interception tại interface boundary.

**4. Có thể để pointcut nhắc tới concrete implementation khi đang dùng JDK proxy không?** Có. Spring xét thông tin target class khi match pointcut; nhưng chỉ những lời gọi qua các method mà proxy thực sự công bố mới được intercept.

**5. Bật `proxyTargetClass=false` có bảo đảm 100% là JDK proxy không?** Không, còn phụ thuộc target có interface, các cấu hình auto-proxy khác và loại bean. Kiểm tra reference thực tế với `AopUtils`.

**6. Interface có method `pay`; `submit()` bên trong target gọi `this.pay()`. Advice cho `pay` có chạy không?** Không qua self-invocation đó. Đưa lời gọi qua một reference Spring proxy khi thực sự cần advice.

## Tài liệu Spring chính thức

- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html)
