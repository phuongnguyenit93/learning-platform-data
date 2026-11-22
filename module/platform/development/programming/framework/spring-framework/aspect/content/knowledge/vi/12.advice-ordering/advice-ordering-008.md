# Không suy diễn thứ tự thực thi từ vị trí phương thức trong mã nguồn Spring Aspect

## 1. Kết luận cốt lõi

Trong Spring AOP, việc một phương thức advice nằm **phía trên** phương thức advice khác trong cùng class `@Aspect` **không bảo đảm** phương thức thứ nhất sẽ chạy trước phương thức thứ hai.

Đặc biệt, **hai advice cùng loại** trong **cùng một `@Aspect`** mà đều khớp một method execution có **thứ tự không xác định**. Spring Framework không thể dùng thứ tự khai báo Java source như một hợp đồng, vì Java reflection trên mã đã biên dịch bằng `javac` không cung cấp thứ tự source declaration đáng tin cậy.

Ví dụ:

```java
@Aspect
public class DangerousAuditAspect {
    @Before("execution(* com.example.ordering.TaskService.run(..))")
    public void validate() {
        System.out.println("VALIDATE");
    }

    @Before("execution(* com.example.ordering.TaskService.run(..))")
    public void audit() {
        System.out.println("AUDIT");
    }
}
```

**Không được kết luận** `VALIDATE` luôn xuất hiện trước `AUDIT` chỉ vì `validate()` được khai báo trước `audit()` trong file Java. Đây là **fragment minh họa lỗi thiết kế ordering**, chưa phải ứng dụng độc lập. Nếu audit bắt buộc chỉ xảy ra sau validation, cần một cơ chế sequencing có hợp đồng rõ ràng.

Để thiết lập thứ tự:

- Khi các thao tác thuộc **cùng một trách nhiệm**, gom vào **một advice method** và gọi các helper theo thứ tự Java tường minh.
- Khi chúng thuộc **các cross-cutting concerns độc lập**, tách thành **nhiều aspect classes** và dùng Spring `@Order` hoặc `Ordered`.
- Khi có các advice **khác loại** trong cùng `@Aspect`, hiểu **quy tắc precedence theo loại advice** và ngữ nghĩa `finally` của `@After`, không suy từ vị trí khai báo.
- Với cấu hình **Spring XML AOP**, nhận biết ngoại lệ: thứ tự của các advice elements trong **cùng `<aop:aspect>`** có ý nghĩa, không giống Java `@Aspect` declaration order.

Bài này chỉ tập trung **Spring Aspect bằng `@AspectJ` annotations trên Spring-managed beans thông qua Spring AOP proxy** và điểm khác biệt liên quan tới cấu hình Spring XML, không đi sâu vào AspectJ compile-time/load-time weaving độc lập.

## 2. Vì sao source position không phải quy tắc thứ tự?

Java code có thể hiển thị methods theo thứ tự rất rõ trong IDE, nhưng Spring đọc annotation metadata từ class đã được JVM nạp. Phương thức `Class.getDeclaredMethods()` và những cơ chế reflection tương tự **không cam kết giữ nguyên thứ tự methods trong tệp `.java`**.

Những thông tin sau **không được** dùng làm căn cứ ordering advice:

1. Số dòng của method trong source.
2. Thứ tự class methods mà IDE hiển thị.
3. Tên method theo alphabet, như `aValidate()` trước `zAudit()`.
4. Thứ tự các `@Bean` methods trong `@Configuration`.
5. Thứ tự các class được `@ComponentScan` tìm thấy.
6. Thứ tự import các aspect classes.
7. Thứ tự các log quan sát trong **một lần chạy thử** mà chưa có ordering contract.

Đổi chỗ hai methods trong class rồi thấy log “có vẻ đúng” không phải là cách ổn định để điều khiển Spring AOP. Một bản JDK, compiler, Spring version hoặc class layout khác có thể cho kết quả khác nếu bạn dựa vào thứ tự mà framework không hứa hẹn.

**Ngoại lệ cần ghi rõ:** Spring Framework từ **5.2.7** có quy tắc precedence giữa **các advice khác loại trong cùng class**. Điều đó **không** bảo đảm thứ tự giữa hai `@Before` hoặc hai `@After` trong cùng `@Aspect`.

## 3. Thứ tự trên đường vào và đường ra khác nhau

Spring proxy AOP dùng interceptor chain. Hãy hình dung hai `@Around` advices ở hai aspects khác nhau:

```text
Caller
  -> Spring AOP proxy
     -> OuterAspect.around()       @Order(1)
        -> InnerAspect.around()    @Order(10)
           -> Target.run()
        <- InnerAspect returns
     <- OuterAspect returns
  <- Caller receives return value
```

Trong Spring, **giá trị `@Order` nhỏ hơn có precedence cao hơn**. Aspect precedence cao hơn thực thi **sớm hơn trên đường vào** và **muộn hơn trên đường ra**. Đây là mô hình lồng nhau, không phải danh sách callbacks chạy theo thứ tự tuyến tính một chiều.

```text
[OUTER] enter
[INNER] enter
[TARGET] run
[INNER] exit
[OUTER] exit
```

Khi caller nhận exception, luồng trở ra cũng unwind ngược chiều:

```text
[OUTER] enter
[INNER] enter
[TARGET] throw
[INNER] catch/finally
[OUTER] catch/finally
```

Vì vậy, **không thể đọc `@Order(1)` và kết luận mọi dòng log của aspect đó sẽ luôn xuất hiện trước mọi dòng log của `@Order(10)`**.

### `@Order` dùng cho aspect classes

```java
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(1)
public class HighPriorityAspect {
    // Các advice thuộc aspect này.
}
```

Một aspect khác:

```java
@Aspect
@Order(10)
public class LowPriorityAspect {
    // Các advice thuộc aspect này.
}
```

Đây là class fragments. Thứ tự nằm ở **cấp aspect**, không phải lời hứa rằng `@Order` đặt trên từng method advice riêng sẽ quyết định thứ tự hai `@Before` trong cùng một class.

Spring cũng hỗ trợ aspect bean implement `org.springframework.core.Ordered`:

```java
@Aspect
public class HighPriorityAspect implements org.springframework.core.Ordered {
    @Override
    public int getOrder() {
        return 1;
    }
}
```

Chọn **một cơ chế ordering rõ ràng** cho aspect. Nếu có nhiều aspects trùng order mà lại cần thứ tự bắt buộc giữa chúng, nên dùng **các order values khác nhau** và integration-test kết quả.

## 4. Thứ tự advice khác loại trong cùng `@Aspect`

Theo tài liệu Spring Framework 6.x, khi nhiều advice **khác loại** trong **cùng một `@Aspect` class** cùng khớp một join point, mức precedence **cao xuống thấp** là:

| Precedence | Advice | Chức năng |
| --- | --- | --- |
| 1 | `@Around` | Bao quanh invocation; có thể gọi `proceed()`. |
| 2 | `@Before` | Chạy trước method execution phía trong. |
| 3 | `@After` | After-finally advice. |
| 4 | `@AfterReturning` | Quan sát normal return. |
| 5 | `@AfterThrowing` | Quan sát exception path. |

**Chú ý `@After`:** dù nằm trước `@AfterReturning`/`@AfterThrowing` trong bảng precedence, do ngữ nghĩa **after-finally**, `@After` **thực tế thực thi sau** `@AfterReturning` hoặc `@AfterThrowing` trong cùng aspect, tương tự khối Java `finally`.

Ví dụ:

```java
@Aspect
public class OutcomeAspect {
    @After("execution(* com.example.ordering.TaskService.run(..))")
    public void cleanup() {
        System.out.println("FINALLY");
    }

    @AfterReturning("execution(* com.example.ordering.TaskService.run(..))")
    public void success() {
        System.out.println("SUCCESS");
    }

    @Before("execution(* com.example.ordering.TaskService.run(..))")
    public void before() {
        System.out.println("BEFORE");
    }
}
```

Cố ý viết `cleanup()` **trước** `before()` trong source. Trong một method trả bình thường và không có advisor bổ sung làm thay đổi điều khiển, các sự kiện chính của aspect vẫn theo nghĩa:

```text
BEFORE
target execution
SUCCESS
FINALLY
```

Khi target ném exception, `@AfterReturning` không chạy; `@AfterThrowing` tương thích (nếu có) chạy rồi `@After` finally chạy.

**Phân biệt hai quy tắc:** precedence giữa **các loại advice** trong cùng aspect có bảo đảm của Spring từ 5.2.7; giữa **hai advice cùng loại** trong cùng aspect thì **không xác định**. Không gom cả hai thành kết luận sai “mọi advice cùng class đều không có thứ tự”.

## 5. Hai `@Before` cùng class: sửa thiết kế thế nào?

Giả sử quy tắc nghiệp vụ yêu cầu **validate trước audit**. Thay đổi vị trí hoặc tên Java methods chỉ thay đổi source code; nó không tạo ra ràng buộc thứ tự trong Spring.

**Nếu cùng một trách nhiệm**, dùng một advice điều phối các helper theo thứ tự tường minh:

```java
@Before("execution(* com.example.ordering.TaskService.run(..))")
public void before(JoinPoint jp) {
    validate(jp.getArgs());
    audit(jp.getSignature().getName());
}
```

Đây là fragment trong lớp `@Aspect`, giả định có hai helper `validate` và `audit` được định nghĩa cùng lớp. Nếu validation ném lỗi, bước audit và target không tiếp tục trừ khi code chủ động xử lý exception.

**Nếu là hai trách nhiệm độc lập**, khai báo hai lớp `@Aspect` riêng: `ValidationAspect @Order(10)` và `AuditAspect @Order(20)`, mỗi lớp có `@Before` match cùng method và đều được đăng ký làm Spring bean. Spring chọn ValidationAspect trước trên đường vào nếu advice không dừng chain.

Đổi thứ tự `@Bean`, đổi tên method theo alphabet hoặc thêm `@Order` lên một advice method trong cùng aspect đều không thay thế được hai cách trên. Bài về **giới hạn giữa các advice cùng loại** giải thích sâu hai phương án và cách kiểm thử.

## 6. Ví dụ Maven/Java 17+ có thể chạy: hai `@Around` và một aspect kết quả

Ví dụ dùng **Spring Framework 6.1.14**, **AspectJ Weaver 1.9.22.1**, **JDK 17+** và Maven. Mã chỉ dùng **Spring proxy-based AOP**, không yêu cầu AspectJ compile-time/load-time weaving.

Thiết kế:

- `OuterAspect` dùng `@Around`, `@Order(1)`.
- `InnerAspect` dùng `@Around`, `@Order(10)`.
- `OutcomeAspect` dùng `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After` và `@Order(20)`.
- Các advice ở `OutcomeAspect` được viết **không theo thứ tự cần chạy**, nhằm chứng minh source position không quyết định.
- `TaskService.run("ok")` trả bình thường; `run("fail")` ném `IllegalStateException`.
- Client chỉ gọi trên **bean được lấy từ `ApplicationContext`**, do đó lời gọi đi qua Spring proxy.

### 6.1. Cấu trúc thư mục

```text
spring-aspect-order/
├── pom.xml
└── src/main/java/com/example/ordering/
    ├── TaskService.java
    ├── OuterAspect.java
    ├── InnerAspect.java
    ├── OutcomeAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aspect-order</artifactId>
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

`spring-context` cung cấp `ApplicationContext` và các Spring AOP dependencies phù hợp trong cây phụ thuộc của ví dụ; `aspectjweaver` giúp Spring hiểu pointcut expressions `@AspectJ`.

### 6.3. `src/main/java/com/example/ordering/TaskService.java`

```java
package com.example.ordering;

public class TaskService {
    public String run(String mode) {
        System.out.println("[TARGET] " + mode);
        if ("fail".equals(mode)) {
            throw new IllegalStateException("simulated");
        }
        return "ok:" + mode;
    }
}
```

Target là một class có public method không `final`, cho phép class-based proxy của Spring intercept.

### 6.4. `src/main/java/com/example/ordering/OuterAspect.java`

```java
package com.example.ordering;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(1)
public class OuterAspect {
    @Around("execution(public * com.example.ordering.TaskService.run(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[OUTER] enter");
        try {
            Object result = pjp.proceed();
            System.out.println("[OUTER] return");
            return result;
        } catch (Throwable error) {
            System.out.println("[OUTER] throw "
                    + error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

`@Order(1)` cho outer aspect precedence cao nhất trong demo. Lệnh in `return` nằm **sau `proceed()`** nên sẽ chạy trên đường trở ra, không phải đầu chuỗi.

### 6.5. `src/main/java/com/example/ordering/InnerAspect.java`

```java
package com.example.ordering;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class InnerAspect {
    @Around("execution(public * com.example.ordering.TaskService.run(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[INNER] enter");
        try {
            Object result = pjp.proceed();
            System.out.println("[INNER] return");
            return result;
        } catch (Throwable error) {
            System.out.println("[INNER] throw "
                    + error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

Inner aspect nằm sau `OuterAspect` trên đường vào và trước `OuterAspect` trên đường ra.

### 6.6. `src/main/java/com/example/ordering/OutcomeAspect.java`

```java
package com.example.ordering;

import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;

@Aspect
@Order(20)
public class OutcomeAspect {
    // Phương thức finally xuất hiện ĐẦU file có chủ đích.
    @After("execution(public * com.example.ordering.TaskService.run(..))")
    public void onFinally() {
        System.out.println("[EVENT] finally");
    }

    @AfterThrowing(
        pointcut = "execution(public * com.example.ordering.TaskService.run(..))",
        throwing = "error",
        argNames = "error"
    )
    public void onError(Throwable error) {
        System.out.println("[EVENT] after-throwing "
                + error.getClass().getSimpleName());
    }

    @AfterReturning("execution(public * com.example.ordering.TaskService.run(..))")
    public void onSuccess() {
        System.out.println("[EVENT] after-returning");
    }

    // Phương thức before xuất hiện CUỐI file có chủ đích.
    @Before("execution(public * com.example.ordering.TaskService.run(..))")
    public void before() {
        System.out.println("[EVENT] before");
    }
}
```

Các loại advice **khác nhau** có semantics precedence đã được Spring quy định. Trên normal return: `before` → target → `after-returning` → `finally`. Trên exception: `before` → target throw → `after-throwing` → `finally`. Không cần giả định về thứ tự methods trong file.

### 6.7. `src/main/java/com/example/ordering/AppConfig.java`

```java
package com.example.ordering;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public TaskService taskService() {
        return new TaskService();
    }

    @Bean
    public OuterAspect outerAspect() {
        return new OuterAspect();
    }

    @Bean
    public InnerAspect innerAspect() {
        return new InnerAspect();
    }

    @Bean
    public OutcomeAspect outcomeAspect() {
        return new OutcomeAspect();
    }
}
```

`@EnableAspectJAutoProxy` bật Spring auto-proxy infrastructure. `proxyTargetClass=true` chọn CGLIB cho `TaskService` không có business interface. Các class `@Aspect` được đăng ký thành **Spring beans** bằng `@Bean`; `@Aspect` một mình không tự đăng ký bean.

Thứ tự `@Bean` definitions trong `AppConfig` **không phải** điều kiện tạo thứ tự advice. Đừng chỉnh vị trí ba `@Bean` methods để điều khiển execution chain.

### 6.8. `src/main/java/com/example/ordering/DemoApp.java`

```java
package com.example.ordering;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            TaskService service = context.getBean(TaskService.class);
            System.out.println("isAopProxy="
                    + AopUtils.isAopProxy(service));

            System.out.println("[CALLER] success");
            String result = service.run("ok");
            System.out.println("[CALLER] result=" + result);

            System.out.println("[CALLER] failure");
            try {
                service.run("fail");
            } catch (IllegalStateException ex) {
                System.out.println("[CALLER] caught " + ex.getMessage());
            }
        }
    }
}
```

### 6.9. Chạy và stdout dự kiến

Tại thư mục chứa `pom.xml` với JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.ordering.DemoApp
```

Kết quả do code tự in ra, bỏ qua các log khác của Maven/Spring nếu có:

```text
isAopProxy=true
[CALLER] success
[OUTER] enter
[INNER] enter
[EVENT] before
[TARGET] ok
[EVENT] after-returning
[EVENT] finally
[INNER] return
[OUTER] return
[CALLER] result=ok:ok
[CALLER] failure
[OUTER] enter
[INNER] enter
[EVENT] before
[TARGET] fail
[EVENT] after-throwing IllegalStateException
[EVENT] finally
[INNER] throw IllegalStateException
[OUTER] throw IllegalStateException
[CALLER] caught simulated
```

Giải thích:

1. `OuterAspect @Order(1)` ở ngoài `InnerAspect @Order(10)`, cả hai ở ngoài `OutcomeAspect @Order(20)`.
2. Dòng `[EVENT] before` xuất hiện **trước target**, dù method `before()` viết ở **cuối class**.
3. Dòng `[EVENT] finally` xuất hiện **sau after-returning** trên normal return, dù method `onFinally()` viết ở đầu class.
4. Trường hợp exception dùng `@AfterThrowing` và `@After`, không dùng `@AfterReturning`.
5. Catch blocks của `InnerAspect` rồi `OuterAspect` chạy theo thứ tự **unwind**; precedence cao hơn **không** đồng nghĩa log cuối của outer được in sớm.
6. Mọi lời gọi đi qua **Spring AOP proxy**; nếu client tự `new TaskService()` để gọi trực tiếp, các advice Spring không áp dụng như demo.

Output được lập theo các rules của Spring 6.1 và code đã viết; **chưa phải kết quả Maven đã chạy thực tế**. Khi triển khai project, hãy xác minh với Spring/JDK version đang sử dụng.

## 7. Ngoại lệ cấu hình XML: thứ tự các advice elements trong cùng `<aop:aspect>`

Không được nói “Spring **không bao giờ** dùng thứ tự khai báo”. Với **Spring AOP XML schema**, tài liệu chính thức chỉ rõ:

> Trong cùng một `<aop:aspect>`, precedence giữa các advice declarations được xác định theo thứ tự các **XML advice elements** (từ trước tới sau).

Ví dụ:

```xml
<aop:config>
    <aop:pointcut id="operation"
        expression="execution(* com.example.ordering.TaskService.run(..))"/>

    <aop:aspect ref="xmlLoggingAspect">
        <aop:around method="around" pointcut-ref="operation"/>
        <aop:before method="before" pointcut-ref="operation"/>
    </aop:aspect>
</aop:config>
```

Đây là **XML fragment**, chưa có `beans` root, namespaces/schema declarations hoặc bean `xmlLoggingAspect`. Trong cùng `<aop:aspect>` này, `<aop:around>` được đặt trước `<aop:before>` và được Spring XML AOP diễn giải có precedence cao hơn.

Điều đó **khác bản chất** với hai Java methods mang `@Before` trong cùng `@Aspect`; không thể lấy XML rule áp dụng ngược cho annotation-style.

Với nhiều XML aspects, Spring còn hỗ trợ `order` trên `<aop:aspect>` hoặc `@Order`/`Ordered` trên backing aspect bean theo cấu hình được hỗ trợ. `<aop:advisor>` cũng có thuộc tính `order`. Khi dự án dùng hỗn hợp Java `@Aspect` và XML advisors, cần xét **tổng advisor chain trong cùng `ApplicationContext`**, không suy từ vị trí text trong một file.

## 8. Khi có `@Transactional`, caching hoặc security advice

Một service có thể đồng thời được áp dụng `@Transactional`, `@Cacheable`, method security và custom Spring `@Aspect`. Thứ tự ở đây không tự được quyết định bởi vị trí annotation trong source.

Ví dụ:

```java
@Transactional
public String pay(String paymentId) {
    // ...
}
```

và:

```java
@Aspect
@Order(10)
public class AuditAspect {
    @Before("execution(* com.example.payment.PaymentService.pay(..))")
    public void audit() {
        // ...
    }
}
```

Đây là **fragments**, không phải runnable demo. Câu hỏi “audit diễn ra trước, trong hay sau transaction?” cần đối chiếu:

1. Order của **transaction advisor** trong ứng dụng.
2. Order của custom audit aspect.
3. Transaction đã có ở **caller** chưa.
4. Advisor nào **ở ngoài** advisor nào.
5. Có `@Around` nào short-circuit, catch exception hoặc retry bằng multiple `proceed()` không.

Ví dụ nếu retry aspect ở **ngoài** transaction interceptor và không có ambient transaction, mỗi lần retry có thể có transaction boundary mới. Nếu transaction interceptor ở **ngoài** retry, nhiều attempts có thể chạy trong **một** transaction. Việc đổi vị trí methods trong class `@Aspect` không giải quyết câu hỏi này.

Không coi `@AfterReturning` của service là “sau commit” trong mọi cấu hình. Nếu nghiệp vụ thực sự yêu cầu action **after transaction commit**, dùng cơ chế transaction synchronization/event phù hợp của Spring, không suy từ advice name.

## 9. Những trường hợp khác không có bảo đảm thứ tự

### 9.1. Nhiều aspects không có `@Order`

Hai aspects khác nhau cùng match join point nhưng **không được khai báo precedence**: Spring docs nói thứ tự giữa chúng **không xác định**. Muốn một aspect có precedence rõ ràng, đặt `@Order` hoặc implement `Ordered`.

### 9.2. Hai aspects có cùng giá trị order

Nếu cả hai cùng `@Order(10)` và bạn vẫn cần A trước B, giá trị bằng nhau **không biểu thị yêu cầu đó**. Đưa ra distinct precedence values và test. Không suy ra tie-breaker từ tên bean hay thứ tự registration.

### 9.3. `@Around` gọi `proceed()` nhiều lần

Một outer `@Around` có thể gọi `proceed()` **0, 1 hoặc nhiều lần**. Khi gọi hai lần, các inner advices/target có thể chạy hai lần trong **một** proxy invocation từ caller. Điều này không mâu thuẫn với `@Order`: precedence quyết định **vị trí trong chain**, còn logic `proceed()` quyết định **số lần chuyển tiếp**.

### 9.4. Exception có thể thay đổi đường ra

Nếu target hoặc advice phía trong ném lỗi, những `@AfterReturning` tương ứng có thể không chạy; `@AfterThrowing` và `@After` có thể chạy theo contract. Một outer `@Around` có thể catch và biến exception thành một return value, làm thay đổi những advice bên ngoài nó quan sát được. Vì thế thứ tự log trên exception path khác normal path là điều bình thường.

### 9.5. Các bean/proxy khác context

Auto-proxy creator là infrastructure của **`ApplicationContext`**. Nếu aspects đăng ký ở context này còn target bean ở context khác, không thể dùng thứ tự `@Order` để kết luận rằng chúng cùng áp dụng lên một target. Trước khi debug order, phải xác nhận **advice thực sự có mặt trong proxy chain**.

## 10. Kiểm chứng precedence qua Spring AOP proxy

Khi debug, bắt đầu bằng bean do container trả về:

```java
Object bean = context.getBean("taskService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Đây là fragment, cần context có sẵn. Nếu `isAopProxy=false`, đừng bắt đầu tranh luận advice nào chạy trước: có thể aspect chưa là bean, pointcut không match hoặc caller không dùng proxy.

Với proxy implement Spring `Advised`, có thể xem advisors:

```java
Object bean = context.getBean("taskService");

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

Đây là fragment quan sát infrastructure. Thứ tự advisor listing có thể hỗ trợ chẩn đoán, nhưng cần **test invocation thực tế** để xác nhận nested `@Around`, dynamic matching, exception path và số lần `proceed()`.

### Sử dụng event recorder trong integration test

Một integration test nên thu events vào danh sách **cục bộ cho test invocation**, sau đó assert thứ tự:

```text
outer-enter
inner-enter
before
target
after-returning
finally
inner-return
outer-return
```

Đây là sequence đúng cho nhánh normal return của demo. Đừng dùng `ArrayList` mutable chung trong singleton aspect rồi chạy test concurrent và kết luận rằng Spring ordering bị lỗi khi events từ nhiều threads xen nhau.

Phân biệt **request-level correlation id** và **advice invocation**: nếu hệ thống xử lý song song, log của hai requests có thể interleave dù thứ tự trong **mỗi request** vẫn đúng theo precedence.

Một test đủ mạnh cần kiểm tra:

- Success và exception branches.
- Hai aspects với distinct `@Order`.
- Cùng một join point được cả hai aspects match.
- Advice types và `@After` finally semantics.
- Số lần target thực sự chạy.
- Lời gọi qua Spring-managed proxy, không qua `new` hoặc self-invocation.
- Sự hiện diện của transaction/cache/security advisors nếu ứng dụng có.

## 11. Các lỗi phổ biến

| Biểu hiện | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Đổi vị trí hai `@Before` methods nhưng thứ tự không đổi | Source order không có precedence contract | Gộp steps hoặc tách thành aspects có `@Order`. |
| Test thỉnh thoảng thay đổi thứ tự log | Test đang dựa vào thứ tự không xác định hoặc events từ nhiều threads xen nhau | Khai báo order explicit và cô lập event collector theo invocation. |
| `@Order(1)` aspect in dòng “exit” sau `@Order(10)` | Aspect precedence cao nằm **ngoài**, unwind sau | Phân biệt đường vào và đường ra. |
| `@After` in sau `@AfterReturning` | `@After` là after-finally advice | Đây là semantics của Spring; đừng suy từ type precedence table thiếu ngữ cảnh. |
| Hai aspects khác nhau có thứ tự khó đoán | Không có `@Order` hoặc cùng order | Đặt distinct `@Order` values khi nghiệp vụ phụ thuộc order. |
| `@Order` đặt trên advice method không cho kết quả mong đợi | Điều khiển sai cấp | Đặt `@Order` trên aspect class/bean hoặc dùng `Ordered`. |
| XML aspect có thứ tự khác Java `@Aspect` | XML advice elements có precedence theo declaration order | Áp dụng đúng quy tắc cho đúng configuration style. |
| Đổi `@Bean` methods mà advice order vẫn vậy | Bean lifecycle không phải advice chain precedence | Đọc advisors, dùng `@Order`. |
| Method `@AfterReturning` không chạy trên lỗi | Chỉ áp dụng normal return | Dùng `@AfterThrowing` cho lỗi, `@After` cho finally. |
| Cùng một request nhưng target chạy hai lần | Outer `@Around` gọi `proceed()` nhiều lần | Kiểm tra retry/replay và side effects. |
| Custom audit xảy ra ngoài transaction | Transaction advisor có vị trí khác mong đợi | Cấu hình/test advisor precedence và transaction lifecycle. |
| Không có advice nào dù class có `@Aspect` | Aspect chưa là Spring bean, AOP chưa bật, pointcut không match, caller bypass proxy | Kiểm tra context, `AopUtils`, đường gọi và bean registration. |

## 12. Checklist trước khi merge thay đổi thứ tự advice

- [ ] Không dựa vào **vị trí khai báo methods** trong tệp `.java`.
- [ ] Không yêu cầu thứ tự cố định giữa **hai advice cùng loại trong cùng `@Aspect`**.
- [ ] Nếu cùng một concern cần sequence, đã gom steps vào **một advice method**.
- [ ] Nếu nhiều concerns cần precedence, đã dùng **nhiều aspects với `@Order`/`Ordered` rõ ràng**.
- [ ] Nhớ **order value nhỏ hơn nghĩa là precedence cao hơn**.
- [ ] Hiểu `@Around` bao ngoài và chạy sau trên đường unwind.
- [ ] Phân biệt quy tắc **advice-type precedence** với quy tắc không xác định giữa same-type advice.
- [ ] Hiểu `@After` mang **finally semantics**, không chỉ normal success.
- [ ] Phân biệt Spring annotation-style và XML `<aop:aspect>` ordering.
- [ ] Đã xét advisors từ transaction/cache/security nếu cùng proxy chain.
- [ ] Aspect và target đúng `ApplicationContext`; caller đi qua Spring proxy.
- [ ] Integration tests xác minh thứ tự trên cả success và exception paths.
- [ ] Nếu `@Around` có thể retry hoặc short-circuit, đã kiểm tra số lần `proceed()`.
- [ ] Không viết tests dựa trên những thứ tự Spring **không bảo đảm**.

### Tài liệu chính thức

- Spring Framework — **Declaring Advice / Advice Ordering**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework 6 Reference — **Advice type precedence từ Spring 5.2.7**: https://docs.spring.io/spring-framework/docs/6.0.2/reference/html/core.html
- Spring Framework — **Schema-based AOP Support / XML ordering**: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework — **Enabling @AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring `@Order` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/annotation/Order.html

**Kết luận:** Spring AOP xác định thứ tự bằng **advice type semantics, aspect precedence và interceptor chain**, chứ không phải vị trí các methods trong Java source. Với **hai advice cùng loại trong cùng class `@Aspect`**, thứ tự **không xác định**; hãy thay đổi thiết kế thay vì dựa vào thứ tự tình cờ quan sát được.
