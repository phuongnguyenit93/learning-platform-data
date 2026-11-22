# Chia sẻ pointcut giữa các aspect trong Spring AOP

## 1. Vấn đề cần giải quyết

Trong một ứng dụng Spring, nhiều `@Aspect` có thể quan tâm đến cùng tập lời gọi, chẳng hạn các method public trong lớp service:

- `AuditAspect` ghi dấu trước khi một operation chạy.
- `MetricsAspect` ghi nhận kết quả operation.
- Một aspect khác có thể đo thời gian hoặc bổ sung thông tin truy vết.

Nếu mỗi aspect sao chép chuỗi `execution(...)` riêng, chỉ cần đổi package hoặc tên method là rất dễ xuất hiện các bản pointcut không nhất quán. Spring AOP cho phép **định nghĩa pointcut có tên** bằng annotation `@Pointcut` rồi **tái sử dụng tên này trong nhiều advice, kể cả ở các aspect khác nhau**.

Điều cần nhớ:

1. Method mang `@Pointcut` đại diện cho **signature của pointcut**; expression trong annotation quyết định method execution nào được chọn.
2. Phần thân method pointcut thường **để trống**, return type `void`.
3. Advice có thể dùng `"package.ClassName.pointcutName()"` thay vì copy biểu thức dài.
4. Điểm cắt chung không làm các advice trở thành một advice duy nhất: Spring vẫn tạo và sắp thứ tự advisor tương ứng với từng advice.
5. Dù dùng chung pointcut, giới hạn proxy của Spring AOP vẫn áp dụng: chỉ những method execution được gọi qua Spring proxy và được matcher chọn mới được advice.

Bài này chỉ xét **cơ chế Spring Framework/Spring AOP**. Các kiến thức AspectJ weaving và lý thuyết Aspect tổng quát không được mở rộng.

## 2. Pointcut có tên được khai báo như thế nào?

Cú pháp `@Pointcut` đặt tên cho một biểu thức, để các advice khác dùng **cùng định nghĩa** mà không chép nguyên chuỗi:

```java
public class SharedPointcuts {
    @Pointcut("execution(public * demo.service..*.*(..))")
    public void serviceMethod() {}

    @Pointcut("execution(* demo.service..*.submit(..))")
    public void submitMethod() {}

    @Pointcut("serviceMethod() && submitMethod()")
    public void submission() {}
}
```

Trong một aspect khác, tham chiếu `@Before("demo.pointcut.SharedPointcuts.submission()")` nếu class thực ở package `demo.pointcut`. Method signature phải là `void`, có `()` khi tham chiếu và body thường trống. Bài **“Khai báo pointcut có tên bằng @Pointcut”** giải thích chi tiết cấu tạo và binding tham số.

## 3. Tổ chức một thư viện pointcut dùng chung

Một ứng dụng lớn thường có các ranh giới kiến trúc rõ ràng: public service operations, repository operations, method cần audit, hoặc một tập method của subsystem cụ thể. Tài liệu Spring khuyên tạo **class chuyên dụng** để mô tả những ranh giới này bằng named pointcuts.

Một cấu trúc tham khảo:

```text
com.example.app/
├── pointcut/
│   └── ApplicationPointcuts.java
├── aspect/
│   ├── AuditAspect.java
│   └── MetricsAspect.java
└── service/
    ├── OrderService.java
    └── OrderServiceImpl.java
```

Trong catalog nên ưu tiên:

- Tên diễn đạt **ý nghĩa nghiệp vụ hoặc kiến trúc**: `serviceOperation()`, `orderSubmission()`.
- Các pointcut nhỏ có thể kết hợp bằng `&&`, `||` và `!`.
- Phạm vi đủ chặt: ưu tiên giới hạn method signature và package/type, tránh vô tình chọn mọi method của toàn bộ ứng dụng.
- Không inject business services chỉ để “thực hiện” pointcut. Catalog là nơi chứa **metadata expression**, không phải nơi chạy nghiệp vụ.
- Có integration test để biết các method thực sự được chọn khi package hoặc service APIs thay đổi.

### Cách ghép named pointcuts

```java
@Pointcut("execution(public * com.example.app..service..*.*(..))")
public void publicServiceMethod() {
}

@Pointcut("execution(* com.example.app..*.submit(..))")
public void submitMethod() {
}

@Pointcut("publicServiceMethod() && submitMethod()")
public void publicSubmission() {
}

@Pointcut("publicServiceMethod() && !submitMethod()")
public void serviceOtherThanSubmit() {
}
```

Đoạn trên **phải nằm trong class `@Aspect` tương ứng**, không phải chương trình Java độc lập. Khi một pointcut khác dùng `publicSubmission()`, Spring xử lý nó như biểu thức kết hợp; method body không cần và không nên chứa logic.

Nếu chỉ một aspect cần một điều kiện riêng, aspect đó có thể thêm `&& bean(*Service)` hoặc `&& @annotation(...)` vào tham chiếu catalog. Các advice không bắt buộc có **tập matching y hệt nhau** chỉ vì có chung một phần pointcut.

## 4. Quy tắc visibility khi dùng chung pointcut

Điều kiện tái sử dụng named pointcut từ một class khác là **tên pointcut và declaring type phải truy cập được** theo Java visibility. Một method `private @Pointcut` phù hợp khi advice ở cùng declaring class dùng nội bộ; package-private và `protected` có giới hạn package/hierarchy; `public` phù hợp cho catalog ở package khác.

Modifier của method `@Pointcut` không làm thay đổi tập method được match; muốn chọn public target method phải có điều kiện như `execution(public * *(..))` trong expression. Hai bài **“Visibility của phương thức pointcut và phạm vi tái sử dụng”** và **“Phân biệt visibility…”** phân tích đầy đủ phạm vi Java và giới hạn JDK/CGLIB proxy.

## 5. Ví dụ runnable: hai aspect chia sẻ một pointcut catalog

Project dùng **Java 17+, Maven và Spring Framework 6.2.6**. Ta tạo:

- `SharedPointcuts` với hai pointcut cơ bản và một pointcut kết hợp.
- `AuditAspect` sử dụng named pointcut ấy trong `@Before`.
- `MetricsAspect` sử dụng **cùng named pointcut** trong `@AfterReturning`.
- `OrderServiceImpl` có `submit()` và `status()`. Chỉ `submit()` được hai advice chọn.

Ví dụ dùng `AnnotationConfigApplicationContext`, không cần Spring Boot. Aspect và catalog đều được đăng ký thành Spring beans bằng `@Bean`, giúp tránh các giả định về component-scan.

### 5.1. Cấu trúc file

```text
spring-shared-pointcuts/
├── pom.xml
└── src/main/java/demo/
    ├── SharedPointcutDemo.java
    ├── pointcut/
    │   └── SharedPointcuts.java
    ├── service/
    │   ├── OrderService.java
    │   └── OrderServiceImpl.java
    └── aspect/
        ├── AuditAspect.java
        └── MetricsAspect.java
```

### 5.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-shared-pointcuts</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
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
                    <mainClass>demo.SharedPointcutDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Tệp src/main/java/demo/pointcut/SharedPointcuts.java

```java
package demo.pointcut;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class SharedPointcuts {

    @Pointcut("execution(public * demo.service..*.*(..))")
    public void serviceMethod() {
    }

    @Pointcut("execution(* demo.service..*.submit(..))")
    public void submitMethod() {
    }

    @Pointcut("serviceMethod() && submitMethod()")
    public void submission() {
    }
}
```

Ba methods này trả `void`, có body rỗng và đều là `public`. Expression `submission()` chọn **phần giao**: method public thuộc service package và có tên `submit`. Catalog là class khai báo pointcut chứ không phải service chạy nghiệp vụ.

### 5.4. Tệp src/main/java/demo/service/OrderService.java

```java
package demo.service;

public interface OrderService {
    String submit(String id);
    String status();
}
```

### 5.5. Tệp src/main/java/demo/service/OrderServiceImpl.java

```java
package demo.service;

public class OrderServiceImpl implements OrderService {

    @Override
    public String submit(String id) {
        System.out.println("TARGET submit " + id);
        return "ACCEPTED:" + id;
    }

    @Override
    public String status() {
        System.out.println("TARGET status");
        return "READY";
    }
}
```

### 5.6. Tệp src/main/java/demo/aspect/AuditAspect.java

```java
package demo.aspect;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {

    @Before("demo.pointcut.SharedPointcuts.submission()")
    public void before(JoinPoint joinPoint) {
        System.out.println(
            "AUDIT " + joinPoint.getSignature().getName()
        );
    }
}
```

### 5.7. Tệp src/main/java/demo/aspect/MetricsAspect.java

```java
package demo.aspect;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.AfterReturning;

@Aspect
public class MetricsAspect {

    @AfterReturning(
        pointcut = "demo.pointcut.SharedPointcuts.submission()",
        returning = "result"
    )
    public void after(Object result) {
        System.out.println("METRIC return " + result);
    }
}
```

Cả `AuditAspect` và `MetricsAspect` dùng đúng cùng **qualified pointcut reference**. Việc thực thi advice khác nhau do annotation: `@Before` trước target, `@AfterReturning` sau khi method hoàn thành bình thường.

### 5.8. Tệp src/main/java/demo/SharedPointcutDemo.java

```java
package demo;

import demo.aspect.AuditAspect;
import demo.aspect.MetricsAspect;
import demo.pointcut.SharedPointcuts;
import demo.service.OrderService;
import demo.service.OrderServiceImpl;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class SharedPointcutDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {

        @Bean
        public OrderService orderService() {
            return new OrderServiceImpl();
        }

        @Bean
        public SharedPointcuts sharedPointcuts() {
            return new SharedPointcuts();
        }

        @Bean
        public AuditAspect auditAspect() {
            return new AuditAspect();
        }

        @Bean
        public MetricsAspect metricsAspect() {
            return new MetricsAspect();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                new AnnotationConfigApplicationContext(Config.class)) {

            OrderService service = ctx.getBean(OrderService.class);
            System.out.println(
                "AOP_PROXY=" + AopUtils.isAopProxy(service)
            );
            System.out.println("CLIENT " + service.submit("A01"));
            System.out.println("CLIENT " + service.status());
        }
    }
}
```

Chạy tại thư mục `spring-shared-pointcuts`:

```bash
mvn -q compile exec:java
```

Các dòng **do chương trình in ra**, không bao gồm logging riêng của Maven hoặc Spring:

```text
AOP_PROXY=true
AUDIT submit
TARGET submit A01
METRIC return ACCEPTED:A01
CLIENT ACCEPTED:A01
TARGET status
CLIENT READY
```

Giải thích kết quả:

1. `@EnableAspectJAutoProxy` bật Spring AOP với kiểu khai báo @AspectJ; các `@Bean` đăng ký target, catalog và hai advice aspects.
2. Advisor của `AuditAspect` và `MetricsAspect` đều dùng `SharedPointcuts.submission()`. Target `submit()` match nên có proxy, và cả hai advice tham gia vào lời gọi.
3. `@Before` chạy trước target; sau khi target trả `ACCEPTED:A01`, `@AfterReturning` quan sát kết quả; cuối cùng client in kết quả.
4. `status()` nằm trong service package nhưng không phải `submit()`. Nó không match `SharedPointcuts.submitMethod()`, nên hai advice không chạy cho lời gọi `status()`.
5. Tên/lớp proxy runtime không được hardcode vào output. `AopUtils.isAopProxy(...)` kiểm tra bean thực tế do context cấp.

**Lưu ý:** với context phức tạp hơn, một bean vẫn có thể có advisor khác như transaction hoặc caching. Trong demo chỉ có các aspect đã khai báo để kết quả minh họa rõ ràng.

## 6. Tổ chức thêm điều kiện riêng mà không sửa catalog

Aspect A có thể sử dụng toàn bộ catalog, còn aspect B bổ sung điều kiện:

```java
@Aspect
public class BeanScopedAudit {

    @Before(
        "demo.pointcut.SharedPointcuts.serviceMethod() " +
        "&& bean(*Service)"
    )
    public void auditNamedBeans() {
        System.out.println("AUDIT NAMED SERVICE");
    }
}
```

Đây là **snippet**; muốn chạy phải đăng ký thành Spring bean và có tên bean khớp pattern. `bean(*Service)` là pointcut designator **riêng của Spring AOP**, chọn theo Spring bean name thay vì method/class.

Một snippet khác chỉ chọn execution được gắn annotation:

```java
@Aspect
public class AnnotatedAudit {

    @Before(
        "demo.pointcut.SharedPointcuts.serviceMethod() " +
        "&& @annotation(com.example.app.Audited)"
    )
    public void auditAnnotated() {
        System.out.println("AUDITED");
    }
}
```

Đây là **mẫu** cần định nghĩa annotation `com.example.app.Audited` và test cách matcher tra cứu method annotation. Nội dung chung `serviceMethod()` vẫn được tái sử dụng. Các aspect có thể **mở rộng/hạn chế** tập join point so với nhau mà không sửa ranh giới nền tảng.

Đừng cố nhồi mọi điều kiện đặc thù của một aspect vào catalog chung, nếu điều đó khiến các aspect khác phụ thuộc những chi tiết không liên quan.

## 7. Chia sẻ pointcut không phải chia sẻ lời thực thi advice

Một catalog chỉ xác định **tập join points**. Các aspect tham chiếu catalog vẫn có method advice riêng, thứ tự riêng, và mỗi advice được Spring thích ứng thành interceptor/advisor tương ứng.

```text
         SharedPointcuts.submission()
                    |
          +---------+----------+
          |                    |
          v                    v
    AuditAspect           MetricsAspect
    @Before               @AfterReturning
          |                    |
          +---------+----------+
                    |
             Spring AOP proxy
                    |
                    v
             OrderService.submit()
```

**Thứ tự advice không do shared pointcut quyết định.** Nếu hai `@Around` cùng match một method, Spring xử lý theo precedence/ordering; muốn thứ tự xác định giữa các aspects thì dùng `@Order` hoặc `Ordered` khi phù hợp. Trên đường vào, advice ưu tiên cao chạy trước; trên đường ra, thứ tự thường ngược lại do các interceptor lồng nhau.

Không dùng việc chia sẻ catalog để thay thế cơ chế sắp thứ tự advice.

## 8. Đặc điểm và giới hạn riêng của Spring AOP

### 8.1. Pointcut phải được Spring nhận diện trong context

Trong kiểu cấu hình @AspectJ, Spring quét/tìm các classes `@Aspect` được đăng ký thành Spring beans để xây advisor. Demo đăng ký `SharedPointcuts` và hai aspects bằng `@Bean`. Trong ứng dụng Boot có starter AOP, auto-configuration có thể bật xử lý tương đương, nhưng các aspect vẫn phải được container biết đến (ví dụ `@Component` trong vùng component scan).

### 8.2. Proxy boundary không đổi

Shared pointcut chỉ giúp **dùng lại biểu thức**, không mở rộng loại join point. Với Spring AOP, caller phải đi qua proxy; `this.otherMethod()` trong target (self-invocation) không tự trở thành một lần gọi mới qua proxy. Đổi JDK proxy thành CGLIB không giải quyết self-invocation.

### 8.3. JDK/CGLIB không tự khiến mọi method intercept được

JDK proxy công bố interface methods; CGLIB subclass proxy bị giới hạn bởi `final class`, `final/private method` và Java visibility. Nếu catalog match một method nhưng không có lời gọi qua Spring proxy hợp lệ, advice vẫn không chạy.

### 8.4. Spring `bean(...)` không thuộc native AspectJ weaving

Spring AOP có extension `bean(namePattern)` nhờ tích hợp với BeanFactory. Nó có thể được ghép với named pointcuts trong Spring @AspectJ configuration. Tuy nhiên, không copy một expression có `bean(...)` sang môi trường AspectJ compile-time/load-time weaving rồi cho rằng cú pháp sẽ hoạt động giống Spring AOP.

### 8.5. Không giải quyết vấn đề bảo mật chỉ bằng pointcut

Một pointcut dù được chia sẻ bởi nhiều aspects vẫn chỉ là cơ chế chọn lời gọi. Đừng coi nó là security boundary tuyệt đối khi caller có thể giữ target reference thô, gọi phương thức nội bộ hoặc một codepath bỏ qua Spring proxy. Với kiểm soát quyền, cần xác định ranh giới an toàn thực sự và có test cho những đường gọi đó.

## 9. Refactor catalog và các lỗi thường gặp

Khi đổi tên `SharedPointcuts`, tên method `submission()` hoặc package `demo.pointcut`, tìm mọi tham chiếu string trong `@Before`, `@AfterReturning`, `@Around` và cấu hình XML. Tên đầy đủ không được Java compiler tự bảo vệ như lời gọi method bình thường; một chuỗi sai có thể khiến advisor không khởi tạo hoặc mất matching.

Sau khi đổi chính expression trong catalog, kiểm thử lại **các advice của cả hai aspects**: `submit()` cần audit/metrics đúng số lần, `status()` không được chạy các policies ấy. Nếu một aspect thêm `&& @annotation(...)`, tập match của aspect đó có thể hẹp hơn catalog; giữ expectation riêng.

## 10. Named pointcut có tham số

Một ứng dụng có thể muốn chia sẻ pointcut **bind runtime argument** để nhiều advice nhận cùng loại ngữ cảnh. Ví dụ một named pointcut với tham số `String`:

```java
@Aspect
public class ArgumentPointcuts {

    @Pointcut("args(orderId)")
    public void withOrderId(String orderId) {
    }
}
```

Sau đó một aspect khác dùng binding form:

```java
@Aspect
public class ArgumentAuditAspect {

    @Before(
        value =
            "demo.pointcut.ArgumentPointcuts.withOrderId(id) " +
            "&& execution(* demo.service..*.submit(..))",
        argNames = "id"
    )
    public void beforeSubmit(String id) {
        System.out.println("ID=" + id);
    }
}
```

Đây là **hai snippet nâng cao, không thuộc demo chạy độc lập**. Để chạy cần khai báo package/class đúng và đăng ký pointcut/aspect beans; `args(...)` bind runtime method arguments theo signature. Không phải Spring sẽ gọi Java method `withOrderId(String)` để lấy dữ liệu. Khi chia sẻ kiểu pointcut này, cần đặc biệt chú ý tên tham số, `argNames`, type compatibility và method signature của target.

## 11. Kiểm thử đúng cách

Một phép thử chia sẻ thực sự phải gọi target bean qua Spring proxy, ghi event/counter **riêng từng aspect**, và chứng minh method được chọn kích hoạt cả hai policies theo đúng loại advice. Gọi method ngoài rule để xác nhận không có event thừa. Kiểm tra thêm tình huống pointcut được đổi expression mà các aspects vẫn tham chiếu đúng symbol, cùng thứ tự `@Order` nếu nhiều advice có phụ thuộc về thứ tự.

`AopUtils.isAopProxy()` là kiểm tra phụ: proxy có thể tồn tại bởi advisor khác, vì thế không thay thế assertion trên từng advice.

## 12. Câu hỏi tự kiểm tra

**1.** Hai aspect muốn dùng cùng `execution(...)`, cách tránh lặp lại biểu thức dài là gì?  
**Đáp án:** Định nghĩa named `@Pointcut` trong catalog và tham chiếu bằng `package.ClassName.pointcutName()`.

**2.** Spring có gọi body của method `@Pointcut` khi method nghiệp vụ khớp không?  
**Đáp án:** Không. Method này là signature/metadata cho expression; advice mới là phần được Spring thực thi.

**3.** Đổi `public void serviceMethod()` thành `private void serviceMethod()` có làm expression match ít method hơn không?  
**Đáp án:** Bản thân expression không đổi, nhưng pointcut không còn có thể được aspect ở ngoài class tham chiếu theo quy tắc visibility.

**4.** Trong demo, vì sao `submit()` chạy audit và metrics, nhưng `status()` không?  
**Đáp án:** Catalog kết hợp `serviceMethod() && submitMethod()`; chỉ method `submit()` thỏa cả hai điều kiện.

**5.** Nếu một aspect dùng `SharedPointcuts.serviceMethod()`, aspect khác dùng `SharedPointcuts.serviceMethod() && @annotation(...)` thì hai tập method được chọn có như nhau không?  
**Đáp án:** Không nhất thiết, vì aspect thứ hai bổ sung điều kiện annotation.

**6.** Shared pointcut có quy định thứ tự chạy hai `@Around` advices không?  
**Đáp án:** Không. Sắp thứ tự advisor/advice là cơ chế riêng của Spring; dùng `@Order` nếu cần thứ tự.

**7.** Vì sao một pointcut chung không giải quyết được self-invocation?  
**Đáp án:** Lời gọi nội bộ trên target không đi qua Spring proxy, nên không có interception mới để pointcut đánh giá.

**8.** Có thể dùng expression Spring `bean(*Service)` trong mọi loại AspectJ weaving không?  
**Đáp án:** Không. Đây là designator đặc thù của Spring AOP gắn với bean naming.

## 13. Tài liệu chính thức

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): pointcut signatures, qualified references, visibility, shared pointcut definitions và composition.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): Spring đăng ký và đọc `@Aspect` beans.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Before`, `@AfterReturning`, precedence.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, proxy boundary và self-invocation.
