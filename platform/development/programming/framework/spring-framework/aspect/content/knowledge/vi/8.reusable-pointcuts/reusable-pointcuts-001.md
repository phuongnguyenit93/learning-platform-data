# Khai báo pointcut có tên bằng `@Pointcut` trong Spring AOP

## 1. Vì sao nên đặt tên cho pointcut?

Trong Spring AOP, các annotation như `@Before`, `@Around`, `@AfterReturning` thường cần một biểu thức để xác định **lời gọi phương thức nào trên Spring bean sẽ được advice**. Nếu viết trực tiếp biểu thức dài ở mọi advice, mã rất dễ bị lặp và khó bảo trì:

```java
@Before("execution(public * com.example.shop.service.*.*(..))")
public void audit() { /* ... */ }

@AfterReturning("execution(public * com.example.shop.service.*.*(..))")
public void recordSuccess() { /* ... */ }
```

Hai lời advice này lặp cùng một chính sách chọn phương thức. Khi đổi phạm vi package hoặc tên service, cần sửa nhiều chỗ và dễ bỏ sót. Spring hỗ trợ cú pháp khai báo **pointcut có tên** bằng `org.aspectj.lang.annotation.Pointcut`. Bạn khai báo một method `void` có `@Pointcut("...")`, rồi **tham chiếu tên method** trong các advice hoặc trong một pointcut khác.

```java
@Pointcut("execution(public * com.example.shop.service.*.*(..))")
public void serviceOperation() {}

@Before("serviceOperation()")
public void audit() { /* ... */ }

@AfterReturning("serviceOperation()")
public void recordSuccess() { /* ... */ }
```

Đây là **fragment** trong một class `@Aspect` đã đăng ký làm Spring bean, không phải file Java độc lập.

Điều quan trọng nhất: **`serviceOperation()` là tên một pointcut được Spring phân tích và tham chiếu, không phải phương thức chứa logic nghiệp vụ để gọi lúc chạy.** Thân phương thức pointcut thường rỗng và Spring không gọi thân phương thức đó mỗi khi có join point khớp.

Phạm vi bài này là **Spring Aspect dùng `@AspectJ` annotation-style trên các Spring-managed beans qua proxy**, theo yêu cầu chỉ tập trung Aspect trong Spring. Không đi sâu vào AspectJ weaving ngoài Spring hoặc các loại join point không được Spring AOP hỗ trợ.

## 2. Cấu tạo một named pointcut

Một khai báo điển hình:

```java
import org.aspectj.lang.annotation.Pointcut;

@Pointcut("execution(public * com.example.shop.OrderService.submit(..))")
public void orderSubmission() {}
```

Có ba phần cần phân biệt:

| Thành phần | Ý nghĩa |
| --- | --- |
| `@Pointcut("execution(...)")` | **Pointcut expression**: diễn tả method executions nào khớp. |
| `public void orderSubmission()` | **Pointcut signature**: tên và các tham số hình thức (nếu có) để nơi khác tham chiếu. |
| `{}` | **Thân phương thức**: thông thường rỗng, không phải nơi để xử lý lời gọi thực tế. |

### Các quy tắc cú pháp

1. Phương thức được đánh dấu `@Pointcut` **phải trả về `void`**.
2. Tên method là tên pointcut: viết `orderSubmission()` trong expression của advice **với cặp dấu ngoặc** ngay cả khi signature không có tham số.
3. Nếu pointcut cần bind đối số, signature có thể có Java parameters; chúng là **các tham số dùng cho binding**, không có nghĩa Spring sẽ gọi method body.
4. Java visibility như `private`, `protected`, `public` quyết định **nơi được tham chiếu tên pointcut** theo quy tắc thông thường; nó **không thay đổi phạm vi method execution mà pointcut expression khớp**.
5. Biểu thức nằm trong annotation là AspectJ pointcut expression được Spring hỗ trợ và phân tích. Spring AOP chỉ hỗ trợ **method execution join points trên các bean được quản lý qua Spring proxy**.

Ví dụ minh họa khác:

```java
@Pointcut("within(com.example.shop.service..*)")
private void inServiceLayer() {}

@Pointcut("execution(public * *(..))")
private void publicMethod() {}

@Pointcut("inServiceLayer() && publicMethod()")
private void publicServiceMethod() {}
```

Khi tham chiếu `publicServiceMethod()`, Spring kết hợp **cả hai điều kiện**. Bạn không cần copy expression `within(...)` và `execution(...)` sang mọi advice.

## 3. Named pointcut không phải advice và không tự kích hoạt logic

Một lỗi hiểu sai phổ biến là cho rằng:

```java
@Pointcut("execution(* com.example..service.*.*(..))")
public void businessOperation() {
    System.out.println("pointcut invoked");
}
```

sẽ in log ở mỗi lần service method chạy. **Không phải vậy.** Thân method chỉ là Java body thông thường; Spring AOP dùng **annotation metadata**, không gọi body để quyết định match.

Nếu một đoạn code thực sự gọi `businessOperation()` như method Java bình thường, nó chỉ gọi body Java như mọi method khác. Nó **không kích hoạt advice, không thực hiện query để tìm các join points và không tự chạy các method mà expression mô tả**.

Thực hành chuẩn:

```java
@Pointcut("execution(* com.example..service.*.*(..))")
public void businessOperation() {}

@Before("businessOperation()")
public void traceServiceCall(org.aspectj.lang.JoinPoint joinPoint) {
    System.out.println(joinPoint.getSignature().getName());
}
```

Đây là **fragment** nằm trong aspect, cần `@Before`, `@Pointcut` imports và bean registration. `businessOperation()` là tên được tham chiếu; việc in log phải đặt trong **advice method**, không đặt trong body pointcut.

Cũng cần phân biệt `@Pointcut` với Spring `org.springframework.aop.Pointcut` **interface**. Annotation `@Pointcut` thuộc phong cách khai báo `@AspectJ`; interface `Pointcut` thuộc API hạ tầng Spring AOP. Cùng diễn đạt “chọn join point”, nhưng không phải hai cách viết tùy ý thay cho nhau ở cùng vị trí annotation.

## 4. Cách tham chiếu named pointcut trong cùng một aspect

Một aspect có thể đặt `@Pointcut` và nhiều advice cùng class:

```java
package com.example.shop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class ServiceAspect {

    @Pointcut("execution(public * com.example.shop.OrderService.*(..))")
    private void orderServiceOperations() {}

    @Before("orderServiceOperations()")
    public void beforeOrderService(JoinPoint jp) {
        System.out.println("before " + jp.getSignature().getName());
    }

    @AfterReturning("orderServiceOperations()")
    public void afterSuccess() {
        System.out.println("success");
    }
}
```

Class trên là Java class có đủ imports, nhưng **chưa là ví dụ chạy độc lập** vì còn thiếu `OrderService`, `@EnableAspectJAutoProxy` và cách đăng ký aspect bean.

Vì `orderServiceOperations()` là **private method trong cùng class**, cả `@Before` và `@AfterReturning` có thể tham chiếu nó bằng tên ngắn. Không cần `public` chỉ vì advice nằm trong cùng aspect.

Ưu điểm cụ thể:

- Một thay đổi phạm vi `OrderService` tác động nhất quán cả hai advice.
- Tên `orderServiceOperations` dễ hiểu hơn expression dài lặp đi lặp lại.
- Review có thể nhìn expression để biết **chọn gì**, nhìn advice để biết **làm gì**.
- Bạn có thể viết integration test kiểm tra một điểm chặn dùng chung cho nhiều advice.

**Lưu ý về số lần thực thi:** nếu có cả `@Before` và `@AfterReturning` cùng named pointcut, một lần gọi method trả về bình thường có thể kích hoạt **hai advice khác loại**. Đây là hành vi được thiết kế, không phải Spring đăng ký pointcut hai lần.

## 5. Chia sẻ pointcut giữa nhiều aspect bằng class riêng

Khi nhiều aspect cùng quan tâm một tập method, hãy công bố một named pointcut trong class chuyên trách và tham chiếu bằng tên đầy đủ:

```java
public class CommonPointcuts {
    @Pointcut("execution(public * com.example.shop.service..*.*(..))")
    public void serviceOperation() {}
}

// Bên trong một @Aspect bean:
@Before("com.example.shop.aop.CommonPointcuts.serviceOperation()")
public void audit() {}
```

Hai mảnh code minh họa nằm ở các file/package tương ứng. Class chỉ chứa khai báo `@Pointcut` không cần là Spring bean; class chứa advice phải là aspect bean. Với pointcut dùng liên package, declaring class và method cần truy cập được (thường là `public`). Bài **“Chia sẻ pointcut giữa các aspect”** đi sâu vào hợp đồng dùng chung, nhiều advice và cách kiểm thử.

## 6. Ghép named pointcuts bằng `&&`, `||`, `!`

Các named pointcuts có thể kết hợp bằng `&&` (giao), `||` (hợp) và `!` (phủ định). Ví dụ:

```java
@Pointcut("within(com.example.shop.service..*)")
private void serviceLayer() {}

@Pointcut("execution(public * *(..))")
private void publicMethod() {}

@Pointcut("serviceLayer() && publicMethod()")
private void publicServiceMethod() {}
```

Trong ví dụ, advice tham chiếu `publicServiceMethod()` chỉ chọn public method executions thuộc service layer; visibility `private` của các method khai báo pointcut không phải điều kiện match. Khi kết hợp AND/OR phức tạp, dùng ngoặc nhóm và test các ca chỉ thỏa một vế. Bài **“Kết hợp pointcut theo tầng kiến trúc hoặc nhóm chức năng”** phân tích các kiểu nhóm, ví dụ runnable và kết quả matching.

## 7. Binding tham số qua named pointcut

Một named pointcut có thể khai báo **tham số hình thức** để đưa dữ liệu của invocation vào advice. Ví dụ:

```java
@Pointcut(
    value = "execution(public * com.example.shop.OrderService.submit(..))"
          + " && args(orderId)",
    argNames = "orderId"
)
public void submittingOrder(String orderId) {}

@Before(
    value = "submittingOrder(orderId)",
    argNames = "orderId"
)
public void traceSubmission(String orderId) {
    System.out.println("submitting " + orderId);
}
```

Đây là **fragment trong `@Aspect`**. Nó khác named pointcut không tham số:

- `args(orderId)` là **binding expression**, yêu cầu một đối số phù hợp và bind giá trị thực tế.
- Method `submittingOrder(String orderId)` khai báo kiểu của đối số được bind.
- `submittingOrder(orderId)` trong `@Before` **truyền binding theo tên**, không phải gọi một Java method trả `void`.
- `argNames` làm rõ tên tham số cho Spring/AspectJ binding và giảm phụ thuộc compiler parameter metadata.
- Advice nhận **giá trị đối số của invocation**, không nhận một object do `@Pointcut` tạo ra.

Nếu method `submit(String orderId)` được gọi từ client qua Spring proxy với `"A-01"`, `traceSubmission` nhận `"A-01"`.

Một pointcut có tham số phải được tham chiếu với **đúng số lượng binding arguments**. Đừng dùng `submittingOrder()` cho một pointcut signature yêu cầu `String orderId`, hoặc khai báo sai tên trong `argNames`.

### `args` lọc kiểu runtime, không phải kiểm tra giá trị

`args(orderId)` có khả năng match theo type của advice parameter; nó không kiểm tra `orderId.startsWith("VIP")` chỉ bởi có chữ `orderId`. Nếu nghiệp vụ cần chọn giá trị đặc biệt, đặt điều kiện đó trong advice/business policy phù hợp, và kiểm thử kết quả.

### Trường hợp nhiều tham số

```java
@Pointcut(
    value = "execution(public * com.example.shop.OrderService.submit(..))"
          + " && args(orderId, request)",
    argNames = "orderId,request"
)
public void submittingOrder(String orderId, OrderRequest request) {}
```

Đây là **fragment** cần class `OrderRequest` và method tương ứng, không phải project độc lập. Method `submit` cần có hai arguments phù hợp để expression khớp, hoặc phải điều chỉnh `args(...)` bằng dấu `..` nếu muốn cho phép nhiều arguments hơn.

Đặc biệt với `null`, primitive/boxing, varargs hoặc generic collection, hãy test trực tiếp trên Spring version của ứng dụng vì runtime/type-matching có các quy tắc mà một biểu thức tên ngắn không thể thay thế.

## 8. Ví dụ Java 17+ hoàn chỉnh: dùng `@Pointcut` chia sẻ giữa các advice

Ví dụ Maven sau đây chạy Spring Framework thuần và cố ý tách named pointcut ra **class `CommonPointcuts`** để thể hiện khả năng tái sử dụng từ một `@Aspect` khác.

Chọn phiên bản minh họa: **JDK 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1**. Đây là một bộ version mẫu nhất quán, không khẳng định là mới nhất.

Yêu cầu quan sát:

1. `CommonPointcuts.orderSubmissions()` ghép hai pointcuts nhỏ.
2. `CommonPointcuts.submissionWithId(String)` bind tham số từ lời gọi thật.
3. `AuditAspect` khai báo `@Before` cho submission binding và `@AfterReturning` cho pointcut có tên chung.
4. Gọi `OrderService.submit(...)` qua Spring AOP proxy chạy hai advice đúng trách nhiệm; gọi `preview(...)` không chạy các advice.
5. `@Pointcut` methods có thân rỗng; không có output nào từ chúng.

### 8.1. Cấu trúc thư mục

```text
spring-named-pointcuts/
├── pom.xml
└── src/main/java/com/example/named/
    ├── AppConfig.java
    ├── OrderService.java
    ├── CommonPointcuts.java
    ├── AuditAspect.java
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
    <artifactId>spring-named-pointcuts</artifactId>
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

`spring-context` cung cấp ApplicationContext và các module Spring cơ bản (bao gồm Spring AOP trong dependency graph bản mẫu); `aspectjweaver` cung cấp pointcut parser/matching cho `@AspectJ`. Không có AspectJ compiler hoặc weaving agent: đây là **Spring proxy-based AOP**.

### 8.3. `src/main/java/com/example/named/OrderService.java`

```java
package com.example.named;

public class OrderService {
    public String submit(String orderId) {
        System.out.println("[SERVICE] submit " + orderId);
        return "accepted:" + orderId;
    }

    public String preview(String orderId) {
        System.out.println("[SERVICE] preview " + orderId);
        return "preview:" + orderId;
    }
}
```

Class `OrderService` là một target bean với hai public methods. Pointcut bài này cố tình chỉ chọn `submit`, không chọn `preview`.

### 8.4. `src/main/java/com/example/named/CommonPointcuts.java`

```java
package com.example.named;

import org.aspectj.lang.annotation.Pointcut;

public class CommonPointcuts {

    @Pointcut("execution(public * com.example.named.OrderService.*(..))")
    public void orderServiceMethods() {}

    @Pointcut("execution(public * com.example.named.OrderService.submit(..))")
    public void submitMethods() {}

    @Pointcut("orderServiceMethods() && submitMethods()")
    public void orderSubmissions() {}

    @Pointcut(
        value = "orderSubmissions() && args(orderId)",
        argNames = "orderId"
    )
    public void submissionWithId(String orderId) {}
}
```

**Tại sao tổ chức như vậy?**

- `orderServiceMethods()` mô tả phạm vi target class.
- `submitMethods()` mô tả thao tác nghiệp vụ.
- `orderSubmissions()` là **phép giao** của hai điều kiện, giúp nơi sử dụng không cần biết chi tiết expression.
- `submissionWithId(String)` đặt tên cho pointcut có thêm **binding argument**.
- Class `CommonPointcuts` chỉ chứa public named pointcuts dùng chung. Nó không phải aspect bean và **không cần đăng ký thành bean**.

`orderServiceMethods()` có thể khớp cả `submit` và `preview`; `orderSubmissions()` chỉ khớp `submit`. Về mặt demo, hai điều kiện có chủ ý dễ quan sát dù có thể gộp thành một expression ngắn hơn.

### 8.5. `src/main/java/com/example/named/AuditAspect.java`

```java
package com.example.named;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger beforeCount = new AtomicInteger();
    private final AtomicInteger successCount = new AtomicInteger();

    @Before(
        value = "com.example.named.CommonPointcuts.submissionWithId(orderId)",
        argNames = "orderId"
    )
    public void beforeSubmit(String orderId) {
        beforeCount.incrementAndGet();
        System.out.println("[AOP before] " + orderId);
    }

    @AfterReturning(
        pointcut = "com.example.named.CommonPointcuts.orderSubmissions()",
        returning = "result",
        argNames = "result"
    )
    public void afterSuccess(String result) {
        successCount.incrementAndGet();
        System.out.println("[AOP success] " + result);
    }

    public int beforeCount() {
        return beforeCount.get();
    }

    public int successCount() {
        return successCount.get();
    }
}
```

Ở đây một named pointcut **có tham số** cung cấp `orderId` cho `@Before`, còn named pointcut **không tham số** được dùng cho `@AfterReturning`. Chúng đều chọn `submit` theo ý đồ nhưng lấy dữ liệu khác nhau:

- `@Before`: lấy **input** `orderId`, trước lúc target method chạy.
- `@AfterReturning`: lấy **output** thông qua `returning="result"`, sau khi target method kết thúc bình thường.
- Hai counters đo đúng số lần từng advice chạy, không đo số lần pointcut body được gọi.

### 8.6. `src/main/java/com/example/named/AppConfig.java`

```java
package com.example.named;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

`@EnableAspectJAutoProxy(proxyTargetClass = true)` bật hỗ trợ Spring `@AspectJ` và dùng class-based proxy để `OrderService` không cần khai báo interface. `AuditAspect` được đăng ký bằng `@Bean`, bởi `@Aspect` **không tự biến class thành một bean Spring**. `CommonPointcuts` chỉ là class định nghĩa pointcut metadata và không cần `@Bean`.

### 8.7. `src/main/java/com/example/named/DemoApp.java`

```java
package com.example.named;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            AuditAspect aspect = context.getBean(AuditAspect.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));

            String result = service.submit("ORD-1");
            System.out.println("submitResult=" + result);

            String preview = service.preview("ORD-2");
            System.out.println("previewResult=" + preview);

            System.out.println("beforeCount=" + aspect.beforeCount());
            System.out.println("successCount=" + aspect.successCount());
        }
    }
}
```

### 8.8. Chạy ví dụ và kiểm tra stdout

Yêu cầu: JDK 17+, Maven có thể tải dependencies. Tại thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.named.DemoApp
```

Những dòng do code của ví dụ in ra theo thứ tự (không tính log Maven/SLF4J nếu có):

```text
isAopProxy=true
[AOP before] ORD-1
[SERVICE] submit ORD-1
[AOP success] accepted:ORD-1
submitResult=accepted:ORD-1
[SERVICE] preview ORD-2
previewResult=preview:ORD-2
beforeCount=1
successCount=1
```

**Giải thích:**

1. `isAopProxy=true`: auto-proxy creator đã áp dụng advisors từ `AuditAspect` lên `OrderService`.
2. Với `submit("ORD-1")`, `orderSubmissions()` đúng và `submissionWithId(orderId)` bind `"ORD-1"`. `@Before` in dòng đầu tiên.
3. Target in `[SERVICE] submit ...`, sau đó `@AfterReturning` in kết quả trả về.
4. `preview("ORD-2")` thuộc `orderServiceMethods()` nhưng **không thuộc `submitMethods()`**, nên phép giao `orderSubmissions()` là false: không có dòng `[AOP]` cho preview.
5. Hai counters đều bằng 1. Spring không phải chạy body của `CommonPointcuts.orderSubmissions()` mới xác định match.
6. `@AfterReturning` chỉ chạy nếu target method **trả về bình thường**. Nếu target ném exception, advice này không chạy; cần chính sách xử lý ngoại lệ riêng nếu ứng dụng yêu cầu.

Ví dụ hoàn chỉnh này ưu tiên kết quả dễ kiểm tra: **một business method được chọn, một method không được chọn, hai advice tái sử dụng pointcut có tên theo hai cách**.

## 9. Tham chiếu named pointcut ở aspect khác hoặc XML

### 9.1. Nhiều aspects tham chiếu cùng class

Giả sử `CommonPointcuts` có `public void orderSubmissions()`. Aspect audit và aspect metrics có thể cùng tham chiếu:

```java
@Before("com.example.named.CommonPointcuts.orderSubmissions()")
public void auditCall() {
    // ...
}
```

```java
@Around("com.example.named.CommonPointcuts.orderSubmissions()")
public Object timeCall(org.aspectj.lang.ProceedingJoinPoint pjp)
        throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - start;
        // Gửi elapsed vào metric recorder.
    }
}
```

Hai đoạn trên là **method fragments** thuộc các class `@Aspect` tương ứng (không chạy độc lập). Chúng chỉ tái sử dụng **quy tắc chọn method**; từng aspect vẫn chịu trách nhiệm cho logic riêng. Khi chạy cùng lúc, nhiều advices cùng chọn một method là bình thường, nhưng cần kiểm tra thứ tự khi có dependency giữa advices.

### 9.2. Tham chiếu từ Spring XML advisor

Tài liệu Spring cũng chỉ ra một named pointcut public có thể được tham chiếu bằng tên đầy đủ trong `<aop:advisor>`, ví dụ:

```xml
<aop:config>
    <aop:advisor
        pointcut="com.example.named.CommonPointcuts.orderSubmissions()"
        advice-ref="someAdvice"/>
</aop:config>
```

Đây là **fragment XML**, cần file có namespace `aop` và bean `someAdvice` implements Spring `Advice` phù hợp. Nó minh họa khả năng tái sử dụng định nghĩa pointcut, **không có nghĩa bạn phải bật đồng thời XML advisor và Java advice cho cùng một hành vi**.

Nếu ứng dụng đang chuyển đổi từ XML sang Java configuration, kiểm tra **trùng chức năng advice** và bean registration; Spring có cơ chế hợp nhất auto-proxy creators chuẩn, nhưng không tự loại bỏ hai advice khác nhau chỉ vì dùng cùng named pointcut.

## 10. Những lỗi phổ biến khi dùng `@Pointcut`

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Viết logic trong method `@Pointcut` nhưng không chạy | Named method chỉ là signature/metadata, không phải advice callback. | Đưa logic vào `@Before`, `@Around`, `@AfterReturning`... |
| Đặt method `@Pointcut` trả `boolean` hoặc `String` | Signature sai; named pointcut phải trả `void`. | Đổi sang `void` với body rỗng. |
| Advice dùng `@Before("serviceOperation")` | Thiếu `()` ở tên pointcut không tham số. | Viết `@Before("serviceOperation()")`. |
| Aspect khác không tìm thấy named pointcut | Method `private`, thiếu fully-qualified class name hoặc sai package/type. | Dùng method `public` và `com.example.CommonPointcuts.name()` khi chia sẻ. |
| `args(id)` không bind đúng | Signature pointcut và `argNames` / advice parameter không đồng bộ. | Đối chiếu tên, thứ tự, kiểu và số arguments; thêm `argNames` rõ ràng. |
| Advice chạy với nhiều service không mong muốn | Named pointcut quá rộng, ví dụ `execution(* *(..))`. | Hạn chế package/class/method trong expression rồi ghép các điều kiện. |
| Khai báo `@Pointcut` nhưng không có advice nào chạy | Aspect không phải bean, Spring AOP chưa bật, pointcut không match hoặc caller bypass proxy. | Xác minh `@Bean`/`@Component`, `@EnableAspectJAutoProxy`, `AopUtils` và đường gọi. |
| Tưởng `@Pointcut` đặt trong class riêng phải là bean | Nhầm metadata definition với component lifecycle. | Named pointcut container không cần là bean để được tham chiếu theo type. |
| Thay `private` thành `public` làm pointcut “bắt” thêm methods | Nhầm visibility của pointcut method với visibility của target method. | Đặt `public` trong `execution(public ...)`, không dựa vào Java modifier của pointcut method. |
| Lấy tên `@Pointcut` nhưng thiếu `()` khi ghép | Pointcut reference không hợp lệ. | Viết `inServiceLayer() && publicMethod()`. |
| Dùng `@Pointcut` có `call(...)`/field access | Spring proxy AOP không hỗ trợ AspectJ call/get/set join points. | Dùng supported designators, chủ yếu `execution`, cho method execution qua Spring proxy. |
| Advice không chạy do self-invocation | Lời gọi `this.method()` từ target bypass proxy. | Tách business boundary sang bean khác và gọi qua proxy; named pointcut không sửa self-invocation. |
| Hai advice cùng chạy trên method và tưởng pointcut bị nhân đôi | Hai advice độc lập đều tham chiếu cùng named pointcut. | Kiểm tra advisors/bean instances và expected advice count theo từng chính sách. |

## 11. Thiết kế tên và vị trí pointcut dễ bảo trì

Một tên tốt mô tả **tập lời gọi cần chọn**: `serviceOperation()`, `orderSubmission()`, `auditedPaymentOperation()`. Tên `pointcut1()` hoặc tên chỉ mô phỏng ký tự `execution(...)` khiến nơi dùng khó hiểu mục đích. Tránh tên hứa hẹn bảo mật khi pointcut chỉ chọn method, không tự kiểm tra quyền.

Định nghĩa dùng riêng cho một aspect có thể giữ `private`; định nghĩa chia sẻ nên có class sở hữu và public API rõ. Đổi tên named pointcut hoặc package của class chứa nó phải rà mọi chuỗi tham chiếu trong advice/XML. Bài **“Đặt tên theo ý định thay vì chi tiết chuỗi biểu thức”** hướng dẫn đánh giá ý định và giữ tập match sau thay đổi.

## 12. Kiểm thử named pointcuts trong Spring

Để chứng minh một named pointcut hoạt động, hãy khởi tạo Spring context đã bật AOP, lấy target từ context và gọi qua proxy. Chạy ít nhất **một method phải match** và **một method không được match**; xác nhận advice event/counter thay đổi chính xác, đồng thời target trả kết quả mong đợi. Với `A && B`, cần các ca chỉ thỏa A, chỉ thỏa B và thỏa cả hai.

Đối chứng `this.method()` và đối tượng tạo bằng `new` khi kiến trúc có nguy cơ bypass proxy. `AopUtils.isAopProxy(bean)` chỉ cho biết bean có proxy, không chứng minh advice cụ thể đã chạy. Bài **“Kiểm thử ca được khớp và ca không được khớp”** có ma trận và JUnit integration tests đầy đủ.

## 13. Tóm tắt nhanh và tài liệu chính thức

| Câu hỏi | Câu trả lời |
| --- | --- |
| Named pointcut khai báo bằng gì? | Method `void` với annotation `@Pointcut("expression")`. |
| Thân method `@Pointcut` có chạy khi match? | Không; Spring sử dụng tên/signature và annotation metadata. |
| Tham chiếu trong cùng aspect thế nào? | `@Before("namedPointcut()")` hoặc advice khác tương đương. |
| Tham chiếu từ class khác thế nào? | `com.example.CommonPointcuts.namedPointcut()` với Java visibility phù hợp. |
| Kết hợp được điều kiện không? | Có: `&&`, `||`, `!`; đặt tên cho các biểu thức nhỏ. |
| Truyền argument vào advice được không? | Có: `args(name)`, formal parameter và `argNames` đúng. |
| Có cần `CommonPointcuts` là Spring bean không? | Không, nếu class chỉ chứa các named pointcut definitions dùng để tham chiếu. |
| `@Pointcut` có giải quyết self-invocation không? | Không; Spring AOP vẫn proxy-based. |

Tài liệu Spring Framework:

- Declaring a Pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Declaring Advice (Binding Parameters to Advice): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Kết luận:** `@Pointcut` biến điều kiện chọn lời gọi phương thức trong Spring AOP thành **một định nghĩa có tên, có thể tái sử dụng và kết hợp**. Named pointcut mô tả **nơi áp dụng**, còn advice chứa **logic được thực thi**; để advice chạy, target vẫn phải là Spring bean và lời gọi phải đi qua proxy phù hợp.
