# Chuyển cấu hình Spring AOP từ XML sang annotation và kiểm tra tương đương

Trong ứng dụng Spring Framework, cấu hình AOP bằng XML và cấu hình aspect qua annotation đều có thể tạo **Spring AOP proxy** để chạy advice quanh các method của Spring bean. Khi chuyển đổi, mục tiêu không chỉ là xóa XML: cần **giữ nguyên bean được áp dụng, biểu thức pointcut, kiểu advice, thứ tự thực thi, loại proxy, kết quả trả về và hành vi khi phát sinh exception**.

Có hai tình huống XML khác nhau, nên xác định đúng trường hợp trước khi sửa:

1. **XML định nghĩa cả pointcut và advice**, chẳng hạn `<aop:config>`, `<aop:aspect ref="...">`, `<aop:around>`: chuyển định nghĩa đó sang class Java có `@Aspect`, `@Pointcut`, `@Around`... và kích hoạt proxy bằng `@EnableAspectJAutoProxy`.
2. **XML đã dùng aspect annotation** (class có `@Aspect`, XML có `<aop:aspectj-autoproxy/>`): định nghĩa advice đã ở Java; chỉ cần chuyển cách **đăng ký bean và bật auto-proxy** sang Java configuration, không viết lại advice chỉ để thay cú pháp XML.

Bài học tập trung vào **Spring Aspect/Spring AOP**: các ví dụ dùng phương thức Spring bean thông qua proxy, không thực hiện compile-time hoặc load-time weaving của AspectJ.

## 1. Bảng ánh xạ XML → annotation/Java configuration

| Cấu hình XML | Cấu hình Java tương ứng | Cần bảo toàn |
| --- | --- | --- |
| `<aop:config>` (khai báo AOP theo schema) | `@Aspect` trên class advice và `@EnableAspectJAutoProxy` trong `@Configuration` | Bean nào khớp, phương thức nào được intercept |
| `<aop:aspect ref="traceAdvice">` | Spring bean có class `@Aspect`; tạo bằng `@Bean` hoặc `@Component` | Cùng lifecycle và dependencies của advice |
| `<aop:pointcut id="pc" expression="..."/>` | `@Pointcut("...")` trên method không có body, hoặc biểu thức trực tiếp trong advice | Giữ nguyên biểu thức, các điều kiện runtime |
| `<aop:before method="before" pointcut-ref="pc"/>` | `@Before("pc()")` | Thời điểm chạy trước method |
| `<aop:after method="after" pointcut-ref="pc"/>` | `@After("pc()")` | Chạy sau khi method kết thúc, bao gồm cả lỗi |
| `<aop:after-returning method="success" returning="result" .../>` | `@AfterReturning(pointcut="pc()", returning="result")` | Chỉ nhánh trả về bình thường, cách bind kết quả |
| `<aop:after-throwing method="failure" throwing="error" .../>` | `@AfterThrowing(pointcut="pc()", throwing="error")` | Chỉ nhánh ném exception, loại exception bind |
| `<aop:around method="around" pointcut-ref="pc"/>` | `@Around("pc()")` trên method nhận `ProceedingJoinPoint` | Số lần `proceed()`, return value, lỗi được ném lại |
| `<aop:aspect order="10" ...>` | `@Order(10)` trên class `@Aspect` hoặc `Ordered` | Thứ tự ưu tiên giữa các aspect; test thứ tự thật |
| `proxy-target-class="true/false"` ở `<aop:config>` hoặc `<aop:aspectj-autoproxy>` | `@EnableAspectJAutoProxy(proxyTargetClass = true/false)` | Loại proxy JDK hay class-based, kiểu bean có thể inject |
| `expose-proxy="true"` | `@EnableAspectJAutoProxy(exposeProxy = true)` | Khả năng dùng `AopContext.currentProxy()` nếu ứng dụng đang phụ thuộc vào nó |
| `<bean .../>` hoặc `<context:component-scan .../>` | `@Bean` hoặc `@ComponentScan` với `@Component`/`@Service` | Bean target và bean aspect đều được đăng ký đúng context |

**Lưu ý:** các đoạn `@Before("pc()")` trong bảng giả định có một method `@Pointcut` tên `pc` cùng aspect. Nếu thay bằng biểu thức pointcut đầy đủ trong annotation thì không cần method đó. Cú pháp XML advice có thể khai báo `pointcut="..."` trực tiếp thay cho `pointcut-ref`; tương tự, annotation cũng cho phép biểu thức trực tiếp.

**Không tự động coi mọi điểm là một-một.** Thứ tự giữa nhiều advice cùng một aspect có thể khác khi đổi kiểu khai báo hoặc khi thêm advice mới; thông số proxy có thể bị ảnh hưởng bởi các cấu hình Spring khác trong cùng context. Vì thế phải kiểm tra hành vi chạy thực tế.

## 2. Ví dụ trước và sau có thể chạy để đối chiếu

Ta tạo **hai application context riêng biệt** với cùng interface/target, dùng Spring Framework 6, Java 17, Maven. Context thứ nhất định nghĩa advice trong XML `<aop:config>`. Context thứ hai định nghĩa advice bằng `@Aspect` và bật bằng `@EnableAspectJAutoProxy`. Mỗi context có một `TraceLog` độc lập để tránh kết quả thử nghiệm ảnh hưởng lẫn nhau.

Ca sử dụng có hai nhánh:

- `placeOrder("A-7")` trả về `"OK:A-7"` và ghi sự kiện vào audit.
- `placeOrder("bad")` ném `IllegalArgumentException`; advice ghi sự kiện lỗi và **ném lại nguyên exception**.

Bài kiểm tra so sánh cả kết quả, loại proxy, thứ tự sự kiện và exception giữa hai context. Việc dùng một `@Around` advice ở mỗi bên khiến luồng kiểm tra dễ quan sát.

### 2.1. Cấu trúc dự án Maven

```text
spring-aop-xml-migration/
├── pom.xml
└── src/main/
    ├── java/com/example/aopmigration/
    │   ├── OrderService.java
    │   ├── OrderServiceImpl.java
    │   ├── TraceLog.java
    │   ├── XmlTraceAdvice.java
    │   ├── AnnotatedTraceAspect.java
    │   ├── JavaAopConfig.java
    │   └── MigrationCheck.java
    └── resources/
        └── legacy-aop.xml
```

**`pom.xml`:** Maven và JDK 17 trở lên; Spring 6 tương thích Java 17. `aspectjweaver` cần cho các type AspectJ và khả năng phân tích pointcut mà Spring AOP sử dụng.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-xml-migration</artifactId>
    <version>1.0.0</version>

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
            </plugin>
        </plugins>
    </build>
</project>
```

Trong dự án Spring Boot đã có dependency management, thường dùng `spring-boot-starter-aop` và để Boot quản lý version thay vì sao chép toàn bộ cấu hình Maven trên.

### 2.2. Target bean dùng chung

**`OrderService.java`**

```java
package com.example.aopmigration;

public interface OrderService {
    String placeOrder(String orderId);
}
```

**`OrderServiceImpl.java`**

```java
package com.example.aopmigration;

public class OrderServiceImpl implements OrderService {
    @Override
    public String placeOrder(String orderId) {
        if ("bad".equals(orderId)) {
            throw new IllegalArgumentException("invalid order");
        }
        return "OK:" + orderId;
    }
}
```

**`TraceLog.java`**

```java
package com.example.aopmigration;

import java.util.ArrayList;
import java.util.List;

public class TraceLog {
    private final List<String> events = new ArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
```

Ví dụ chạy tuần tự trên một thread, nên `ArrayList` đủ để ghi nhận event; trong ứng dụng đa luồng, cần dùng recorder/logger có tính an toàn luồng phù hợp. Hai context tạo hai `TraceLog` khác nhau.

### 2.3. Trước: advice và pointcut khai báo bằng XML

**`XmlTraceAdvice.java`** là một POJO: chưa có `@Aspect` vì XML sẽ định nghĩa advice nào chạy.

```java
package com.example.aopmigration;

import org.aspectj.lang.ProceedingJoinPoint;

public class XmlTraceAdvice {
    private final TraceLog log;

    public XmlTraceAdvice(TraceLog log) {
        this.log = log;
    }

    public Object around(ProceedingJoinPoint joinPoint) throws Throwable {
        String method = joinPoint.getSignature().getName();
        log.add("enter:" + method);

        try {
            Object result = joinPoint.proceed();
            log.add("ok:" + result);
            return result;
        } catch (Throwable failure) {
            log.add("fail:" + failure.getClass().getSimpleName());
            throw failure;
        }
    }
}
```

**`src/main/resources/legacy-aop.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="traceLog" class="com.example.aopmigration.TraceLog"/>
    <bean id="orderService" class="com.example.aopmigration.OrderServiceImpl"/>

    <bean id="xmlTraceAdvice" class="com.example.aopmigration.XmlTraceAdvice">
        <constructor-arg ref="traceLog"/>
    </bean>

    <aop:config proxy-target-class="false">
        <aop:pointcut id="orderOperation"
            expression="execution(* com.example.aopmigration.OrderServiceImpl.placeOrder(..))"/>
        <aop:aspect ref="xmlTraceAdvice">
            <aop:around pointcut-ref="orderOperation" method="around"/>
        </aop:aspect>
    </aop:config>
</beans>
```

Ở đây `<aop:config>` kết nối method `XmlTraceAdvice.around(...)` với pointcut. Bean target `orderService` sẽ được Spring cung cấp dưới dạng proxy vì pointcut khớp. Do target có interface `OrderService` và XML đặt `proxy-target-class="false"`, Spring có thể tạo JDK dynamic proxy.

### 2.4. Sau: aspect annotation và Java configuration

**`AnnotatedTraceAspect.java`** mang định nghĩa advice trực tiếp trong Java:

```java
package com.example.aopmigration;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class AnnotatedTraceAspect {
    private final TraceLog log;

    public AnnotatedTraceAspect(TraceLog log) {
        this.log = log;
    }

    @Pointcut("execution(* com.example.aopmigration.OrderServiceImpl.placeOrder(..))")
    public void orderOperation() {
    }

    @Around("orderOperation()")
    public Object around(ProceedingJoinPoint joinPoint) throws Throwable {
        String method = joinPoint.getSignature().getName();
        log.add("enter:" + method);

        try {
            Object result = joinPoint.proceed();
            log.add("ok:" + result);
            return result;
        } catch (Throwable failure) {
            log.add("fail:" + failure.getClass().getSimpleName());
            throw failure;
        }
    }
}
```

Phần body của `around` giống bản XML: trước và sau `proceed()` ghi lại các sự kiện như nhau. Chỉ chuyển nơi khai báo **điểm cắt và kiểu advice** từ XML sang annotation.

**`JavaAopConfig.java`** thay XML đăng ký bean và bật proxy:

```java
package com.example.aopmigration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class JavaAopConfig {
    @Bean
    public TraceLog traceLog() {
        return new TraceLog();
    }

    @Bean
    public OrderService orderService() {
        return new OrderServiceImpl();
    }

    @Bean
    public AnnotatedTraceAspect annotatedTraceAspect(TraceLog traceLog) {
        return new AnnotatedTraceAspect(traceLog);
    }
}
```

- `@EnableAspectJAutoProxy` bật infrastructure proxy cho bean mang `@Aspect`.
- `proxyTargetClass = false` duy trì lựa chọn ưu tiên JDK proxy như XML ban đầu. Khi hệ thống có cấu hình proxy khác, phải kiểm tra loại proxy thực tế.
- `@Bean` đăng ký đủ **target**, **log** và **aspect** vào application context. `@Aspect` **không tự đăng ký bean**; ví dụ này không cần `@ComponentScan` hay `@Component`.
- `@Configuration(proxyBeanMethods = false)` phù hợp ví dụ vì các phương thức `@Bean` không gọi nhau trực tiếp; dependency được Spring truyền vào tham số `annotatedTraceAspect(TraceLog)`.

### 2.5. Chạy hai cấu hình và so sánh hành vi

**`MigrationCheck.java`**

```java
package com.example.aopmigration;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class MigrationCheck {
    record RunResult(
            boolean proxy,
            boolean jdkProxy,
            String successValue,
            String errorType,
            String errorMessage,
            List<String> events
    ) {
    }

    private static RunResult run(String label, ApplicationContext context) {
        OrderService service = context.getBean(OrderService.class);
        TraceLog log = context.getBean(TraceLog.class);

        boolean proxy = AopUtils.isAopProxy(service);
        boolean jdkProxy = AopUtils.isJdkDynamicProxy(service);
        String successValue = service.placeOrder("A-7");

        String errorType = null;
        String errorMessage = null;
        try {
            service.placeOrder("bad");
            throw new AssertionError("Expected a rejected order");
        } catch (IllegalArgumentException failure) {
            errorType = failure.getClass().getSimpleName();
            errorMessage = failure.getMessage();
        }

        RunResult result = new RunResult(
                proxy, jdkProxy, successValue, errorType,
                errorMessage, log.snapshot()
        );
        System.out.println(label + " " + result);
        return result;
    }

    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext xml =
                     new ClassPathXmlApplicationContext("legacy-aop.xml");
             AnnotationConfigApplicationContext java =
                     new AnnotationConfigApplicationContext(JavaAopConfig.class)) {

            RunResult before = run("XML", xml);
            RunResult after = run("JAVA", java);

            if (!before.equals(after)) {
                throw new AssertionError(
                        "AOP behavior changed after migration"
                );
            }
            if (!before.proxy() || !before.jdkProxy()) {
                throw new AssertionError("Expected JDK AOP proxy");
            }
            System.out.println("EQUIVALENT true");
        }
    }
}
```

Chạy trong thư mục dự án:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.aopmigration.MigrationCheck
```

Nếu dùng Windows PowerShell, có thể đặt argument trong dấu nháy nếu shell/Maven phiên bản hiện tại yêu cầu:

```powershell
mvn -q compile exec:java "-Dexec.mainClass=com.example.aopmigration.MigrationCheck"
```

**Các dòng do chính `MigrationCheck` in ra** (không bao gồm log Maven, Spring hoặc thư viện khác):

```text
XML RunResult[proxy=true, jdkProxy=true, successValue=OK:A-7, errorType=IllegalArgumentException, errorMessage=invalid order, events=[enter:placeOrder, ok:OK:A-7, enter:placeOrder, fail:IllegalArgumentException]]
JAVA RunResult[proxy=true, jdkProxy=true, successValue=OK:A-7, errorType=IllegalArgumentException, errorMessage=invalid order, events=[enter:placeOrder, ok:OK:A-7, enter:placeOrder, fail:IllegalArgumentException]]
EQUIVALENT true
```

`record RunResult` (Java 17) tự cung cấp `equals()` so sánh các thành phần, gồm cả danh sách event. Nếu thiếu aspect, sai pointcut, advice nuốt exception, khác loại proxy hoặc thay đổi return value, đối chiếu này sẽ phát hiện nhiều dạng sai khác. Ví dụ kiểm tra **hành vi cụ thể của hai lệnh gọi**; một hệ thống thật cần bổ sung tập ca thử cho các method và trường hợp của nghiệp vụ.

## 3. Nếu XML đã dùng `<aop:aspectj-autoproxy/>`

Đây là quá trình chuyển **bootstrap proxy** và bean registration, không cần thay đổi annotation advice.

**Trước, trong XML:**

```xml
<aop:aspectj-autoproxy proxy-target-class="false"/>
<bean id="orderService" class="com.example.aopmigration.OrderServiceImpl"/>
<bean id="annotatedTraceAspect"
      class="com.example.aopmigration.AnnotatedTraceAspect">
    <constructor-arg ref="traceLog"/>
</bean>
```

Ví dụ rút gọn ở trên giả định XML đã có bean `traceLog`; thiếu bean đó thì XML không hoàn chỉnh. Class `AnnotatedTraceAspect` đã có `@Aspect` và `@Around`, nên khi chuyển sang Java config có thể dùng cấu hình ở mục 2.4: `@EnableAspectJAutoProxy` và `@Bean` tương ứng. Không thêm `<aop:config>` để khai báo lại chính advice đó.

Có thể chọn `@Component` trên aspect, `@Service` trên target và `@ComponentScan` trên config thay cho `@Bean`; **chỉ chọn một cơ chế đăng ký cho mỗi bean**, tránh bean trùng làm pointcut được áp dụng ở nơi không mong muốn.

## 4. Tiêu chí kiểm tra tương đương trước khi loại bỏ XML

Thành công của một ca trả kết quả giống nhau chưa đủ chứng minh toàn bộ cấu hình đã tương đương. Đối chiếu có hệ thống:

| Tiêu chí | Phải kiểm tra |
| --- | --- |
| **Spring beans** | Target, aspect, collaborator đăng ký đầy đủ, cùng scope cần thiết; không bean bị trùng hoặc nằm sai application context |
| **Phạm vi pointcut** | Biểu thức giữ nguyên hoặc đã được chứng minh khớp cùng tập method; kiểm tra cả method phải chạy và method không được intercept |
| **Loại advice** | `before`, `after`, `after-returning`, `after-throwing`, `around` giữ đúng semantics và cách bind `JoinPoint`/return value/exception |
| **Kết quả/ngoại lệ** | `@Around` gọi `proceed()` đúng số lần, trả đúng kết quả, không nuốt hoặc tự thay exception nếu bản cũ không làm |
| **Thứ tự** | Nếu nhiều aspect, giữ `order` tương ứng bằng `@Order`/`Ordered`; kiểm tra thứ tự event thực tế khi cùng pointcut |
| **Proxy** | `proxy-target-class` → `proxyTargetClass`; kiểm tra `AopUtils.isAopProxy` và `isJdkDynamicProxy`/`isCglibProxy` |
| **Điểm gọi** | Client lấy bean từ Spring context và gọi qua proxy, không gọi object được tạo bằng `new` |
| **Lỗi đặc thù** | Các trường hợp exception, return `null`, tham số biên, method không khớp pointcut đều có test |
| **Tác dụng phụ** | Thứ tự log/metrics/audit, transaction, security advice và các interceptor khác không thay đổi trái kỳ vọng |

### Cách viết kiểm thử Spring AOP ở mức tích hợp

- **Kiểm tra pointcut dương và âm:** trong mỗi context, gọi method được chọn và method không được chọn, xác minh chỉ method được chọn có advice. Không chỉ test bằng cách gọi trực tiếp class target.
- **Kiểm tra đường lỗi:** buộc target ném exception; so loại lỗi, thông điệp hoặc error contract, và thứ tự advice.
- **Kiểm tra có nhiều aspect:** nếu dùng transaction, tracing, audit hoặc security cùng lúc, cần kiểm thử order thực tế. `@Order` quyết định precedence giữa aspect, không bảo đảm quy tắc thứ tự tùy ý giữa nhiều advice khai báo cùng một class.
- **Kiểm tra đúng proxy:** dùng `AopUtils` và kiểu injection hợp lệ. JDK proxy thường chỉ triển khai interface; code injection bằng concrete class có thể lỗi sau migration nếu đổi proxy type.
- **Kiểm tra context thực:** nếu ứng dụng có parent/child context (chẳng hạn root/web), bật proxy ở đúng context chứa bean cần xử lý; activation nằm ở context con không mặc nhiên áp dụng cho bean ở context cha.
- **Kiểm tra self-invocation:** `this.otherMethod()` trong cùng target bean thường bỏ qua Spring proxy cả trước và sau migration. Nếu yêu cầu advice, đổi luồng gọi qua Spring bean/proxy phù hợp.

Bộ kiểm tra ở mục 2 cho thấy cách so output và proxy tự động; khi refactor ứng dụng thật, có thể đưa cùng logic đối chiếu vào bài integration test JUnit và mở rộng theo mọi method trong danh sách pointcut.

## 5. Những khác biệt dễ tạo lỗi khi chuyển đổi

### 5.1. Quên bật `@EnableAspectJAutoProxy` hoặc quên khai báo bean `@Aspect`

`@Aspect` định nghĩa aspect nhưng không tự biến class thành Spring bean. Khi bỏ XML `<aop:aspectj-autoproxy/>`, ứng dụng dùng Spring Framework Java config cần bật proxy bằng `@EnableAspectJAutoProxy` (hoặc một cấu hình auto-proxy tương đương đã tồn tại). Sau đó đăng ký class aspect bằng `@Bean` hoặc `@Component` kết hợp component scanning.

Với Spring Boot có AOP auto-configuration, đừng thêm annotation chỉ vì quen tay: kiểm tra dependency/cấu hình Boot đang áp dụng, rồi đối chiếu proxy thực tế.

### 5.2. Thay đổi loại proxy

XML `proxy-target-class="false"` tương ứng Java `proxyTargetClass = false`. Nếu thay thành `true`, proxy dựa trên class có thể intercept một tập method khác so với JDK proxy, nhưng có giới hạn ở method `private`/`final` và class `final`. Trong ứng dụng Boot, mặc định có thể ưu tiên class-based proxy tùy cấu hình; vì vậy migration cần kiểm tra giá trị hiệu lực, không chỉ đọc annotation.

### 5.3. Sửa pointcut trong lúc chuyển cú pháp

Đừng vừa migration vừa mở rộng từ `execution(* com.example.aopmigration.OrderServiceImpl.placeOrder(..))` sang biểu thức package rộng hơn như `execution(* com.example..*(..))`. Điều đó thay đổi các method được advice và làm mất khả năng kiểm chứng equivalence. Giữ nguyên biểu thức trước, sau đó mở rộng trong thay đổi riêng có test.

Điều tương tự xảy ra với `@annotation(...)`, `args(...)`, `this(...)`, `target(...)`: cú pháp có thể giống, nhưng matcher chịu ảnh hưởng của proxy type, annotation placement và runtime arguments. Test trong ngữ cảnh Spring thật nếu phụ thuộc vào chúng.

### 5.4. Thứ tự advice và transaction thay đổi

XML có thể quy định `order` tại `<aop:aspect>`; annotation tương ứng có thể sử dụng `@Order` tại class `@Aspect`. Nhưng một proxy có thể chứa cả advisor của Spring Transaction, Spring Security và các advisor khác. Bảo toàn một con số order chưa đủ nếu tập advisor thực tế thay đổi. Kiểm tra các event theo vòng vào/ra và transaction boundaries để xác nhận.

### 5.5. Cấu hình AOP trùng nhau

Đừng để lại advisor XML `<aop:config>` rồi thêm một `@Aspect` thực hiện **cùng concern** nếu cả hai đều chạy: bạn có thể ghi audit hai lần hoặc gọi logic hai lần. Trước khi xóa XML, đối chiếu để biết phần cũ nào được thay bằng class mới; sau khi đã xác nhận tương đương, chỉ giữ một nguồn định nghĩa mỗi advice. Nếu cần duy trì song song trong thời gian migration, đặt chúng trong **hai application context/test fixture độc lập** như ví dụ, không cùng production context.

## 6. Quy trình migration an toàn và tiêu chí hoàn tất

1. **Chụp trạng thái cũ:** liệt kê target bean, aspect, pointcut, kiểu advice, `order`, loại proxy, và các dependency/bean scope liên quan trong XML.
2. **Đóng băng hành vi bằng test:** lấy kết quả từ cấu hình cũ qua Spring proxy, gồm các nhánh thành công, lỗi, method khớp và không khớp, cùng thứ tự side effect.
3. **Ánh xạ XML sang annotation:** chuyển `<aop:aspect>` và advice sang `@Aspect`/`@Before`/`@Around`...; giữ nguyên biểu thức pointcut và logic; đăng ký đủ bean.
4. **Chuyển hạ tầng proxy:** dùng `@EnableAspectJAutoProxy` hoặc cấu hình Boot tương ứng; giữ proxy type và thứ tự advisor có chủ đích.
5. **Chạy cùng bộ kiểm tra trên cấu hình mới:** so return/exception/log/side effects, số advice được gọi, proxy type và đường self-invocation nếu có.
6. **Loại bỏ cấu hình trùng sau khi pass:** xóa advisor XML đã thay thế và XML bean definition không còn dùng; giữ những XML bean configuration khác nếu chưa thuộc phạm vi migration.
7. **Kiểm thử tích hợp ứng dụng:** xác nhận injection, transaction, security, exception handling và các lời gọi từ những entry point thật vẫn đúng.

Tiêu chí **tương đương** là: *cùng ca gọi vào Spring bean qua proxy cho cùng kết quả và side effect, cùng method được pointcut chọn, và cùng contract lỗi/thứ tự liên quan*. Ví dụ `MigrationCheck` cho một phép đo tự động có thể lặp lại; khi ứng dụng có nhiều aspect và method, cần mở rộng tập test tương xứng trước khi kết luận hoàn tất chuyển đổi.