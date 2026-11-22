# @args trong Spring AOP: lọc lời gọi theo annotation trên kiểu đối số runtime

## 1. Ý nghĩa thực tế của @args trong Spring

Một Spring service có thể nhận tham số khai báo rất rộng như `Object`, một interface, hoặc lớp cha. Khi ứng dụng gọi service, đối số thực tế có thể là nhiều lớp khác nhau. Có lúc ta muốn advice chỉ chạy nếu **lớp thực tế của đối số được đánh dấu bằng annotation**, thay vì chọn theo kiểu khai báo trong method signature.

Trong Spring AOP, pointcut designator `@args` giải quyết chính xác yêu cầu này:

> `@args` giới hạn những method-execution join point mà **kiểu runtime của các đối số thực tế được truyền vào** mang annotation tương ứng.

Ví dụ:

```java
@Before("execution(* com.example.app.service..*.*(..))" +
        " && @args(com.example.app.aop.Reviewed)")
public void beforeReviewedArgument() {
    // Áp dụng cho method nhận đúng một đối số,
    // khi lớp runtime của đối số mang @Reviewed.
}
```

Đây là snippet minh họa, giả sử annotation `Reviewed` có tồn tại và aspect đã được đăng ký là Spring bean. Biểu thức `@args(Reviewed)` một vị trí yêu cầu **một đối số**, có kiểu runtime mang `@Reviewed`. Phần `execution(...)` đồng thời giới hạn các Spring service method cần xét.

**Trọng tâm:** `@args` không kiểm tra annotation trên **tham số method** (`@Target(PARAMETER)`), cũng không kiểm tra annotation trên **chính method** (`@annotation`). Nó dựa vào annotation trên **kiểu runtime của giá trị đối số**. Vì vậy, dù method khai báo `submit(Object value)`, lần gọi truyền `new ReviewedOrder()` có thể khớp, trong khi `new PlainOrder()` thì không.

Bài học chỉ tập trung vào `@args` trong **Spring Framework / Spring AOP dựa trên proxy**, không mở rộng sang những join point của AspectJ weaving ngoài cơ chế Spring.

### Kết quả mong đợi sau bài học

Bạn có thể:
1. Viết annotation dùng với `@args` có `@Target(TYPE)` và `@Retention(RUNTIME)`.
2. Phân biệt kiểu tham số khai báo với lớp runtime của đối số khi Spring chọn advice.
3. Viết `@args` cho method một đối số, hiểu yêu cầu số lượng/vị trí và cách kết hợp với `execution`.
4. Phân biệt `@args` với `args`, `@annotation`, `@within`, `@target` và annotation trực tiếp trên parameter.
5. Kiểm chứng bằng Java 17 + Spring Framework ví dụ hoàn chỉnh gồm đối số có/không có annotation.
6. Nhận biết các hạn chế thực tế: `null`, proxy làm đối số, subtype, retention, self-invocation và chi phí matching runtime.

## 2. Trước tiên: annotation nằm ở đâu?

Giả sử có annotation dùng để đánh dấu **lớp dữ liệu nhạy cảm**:

```java
package com.example.app.aop;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface Reviewed {
    String value() default "review";
}
```

Và hai lớp payload:

```java
@Reviewed("sensitive")
public class ReviewedOrder {
}

public class PlainOrder {
}
```

Trong Spring service:

```java
public void submit(Object payload) {
    // Xử lý payload.
}
```

Hai lời gọi có cùng method signature nhưng khác **lớp runtime**:

```java
service.submit(new ReviewedOrder()); // @args(Reviewed) có thể khớp.
service.submit(new PlainOrder());    // @args(Reviewed) không khớp.
```

Các snippet trên không phải project độc lập; project biên dịch được ở phần 7.

Vì sao `@Target(TYPE)` quan trọng? Annotation phải gắn với **type** của đối số để `@args` có thể tìm thấy nó. `@Retention(RUNTIME)` giúp annotation còn khả dụng khi chương trình đang chạy. Một annotation chỉ tồn tại ở mức `SOURCE` hoặc `CLASS` không cung cấp thông tin phản chiếu runtime tương ứng mà Spring AOP cần cho ví dụ này.

**Một điều dễ nhầm:** Annotate lên field chứa object, biến cục bộ chứa object, hay tham số trong định nghĩa method không có nghĩa lớp runtime của object đã được annotate.

## 3. Kiểu khai báo và kiểu runtime: khác nhau quyết định kết quả

Xem method:

```java
public void publish(Object event) {
    System.out.println(event);
}
```

Kiểu khai báo của parameter `event` là `Object`, nhưng tại runtime:

```java
Object first = new ReviewedOrder();
Object second = new PlainOrder();

service.publish(first);
service.publish(second);
```

Đối số thứ nhất vẫn có lớp runtime là `ReviewedOrder`; đối số thứ hai là `PlainOrder`. `@args(Reviewed)` sẽ phân biệt được hai lời gọi dù bytecode signature của method giống hệt nhau.

Ta có thể mô tả:

```text
Caller -> Spring AOP proxy -> publish(Object event)
                         |
                         +-- actual argument: ReviewedOrder instance
                         |       |
                         |       +-- runtime class has @Reviewed?
                         |               YES -> advice can run
                         |
                         +-- actual argument: PlainOrder instance
                                 |
                                 +-- runtime class has @Reviewed?
                                         NO -> advice skipped
```

Trong Spring, cả hai lời gọi cần qua **proxy của service** trước đã. Nếu client tạo target bằng `new` hoặc service tự gọi `this.publish(...)` từ method khác, advice có thể không chạy bất kể annotation của đối số.

### Bảng dự đoán đơn giản

Giả sử method nhận **một** đối số, Spring AOP đã bật, `@Before("@args(com.example.app.aop.Reviewed)")` được áp dụng qua proxy và không có ràng buộc pointcut khác:

| Đối số runtime | Đối số có lớp runtime mang @Reviewed? | Advice tương ứng |
| --- | --- | --- |
| `new ReviewedOrder()`, lớp được đánh dấu `@Reviewed` | Có | Có thể chạy |
| `new PlainOrder()`, lớp không đánh dấu | Không | Không chạy |
| Biến kiểu `Object` chứa `new ReviewedOrder()` | Có | Có thể chạy, vì xét giá trị runtime |
| Biến kiểu interface chứa instance annotated implementation | Phụ thuộc annotation của runtime class | Dựa vào runtime class, không chỉ interface |
| `null` | Không có runtime class để đọc annotation | Không dùng để suy ra được kiểu annotated; kiểm tra runtime và thiết kế rõ chính sách null |

Ở dòng cuối, tránh viết logic nghiệp vụ dựa trên giả định rằng `null` “mang annotation” của kiểu khai báo. Với pointcut ràng buộc kiểu runtime, không có object để lấy annotation khi đối số là `null`. Nếu hành vi trên null quan trọng, xử lý null bằng validation trong method/advice riêng và kiểm thử trên phiên bản Spring/AspectJ thực tế.

## 4. @args so với những pointcut dễ nhầm

### 4.1. @args và args không giống nhau

Cả hai đều nhìn vào actual arguments, nhưng kiểm tra khác nhau:

```java
@Pointcut("args(com.example.app.model.ReviewedOrder)")
public void hasReviewedOrderRuntimeType() {
}
```

`args(TypePattern)` xem **kiểu runtime của đối số**, ví dụ một object có kiểu `ReviewedOrder` hoặc subtype phù hợp.

```java
@Pointcut("@args(com.example.app.aop.Reviewed)")
public void hasReviewedAnnotationOnRuntimeType() {
}
```

`@args(AnnotationTypePattern)` xem **annotation trên kiểu runtime của đối số**, không đòi đúng một class cụ thể. Nếu cả `ReviewedOrder` và `FlaggedDocument` đều mang `@Reviewed`, `@args(Reviewed)` có thể khớp cả hai mà không cần viết hai type patterns.

| Thiết kế | Chọn theo | Ví dụ |
| --- | --- | --- |
| `args(com.example.app.model.ReviewedOrder)` | Class/interface runtime của actual argument | Object thuộc `ReviewedOrder`/subtype phù hợp |
| `@args(com.example.app.aop.Reviewed)` | Annotation trên runtime class của actual argument | Bất kỳ runtime class mang `@Reviewed` |
| `execution(* *.publish(com.example.app.model.ReviewedOrder))` | Chữ ký method khai báo kiểu parameter | Method declaration nhận `ReviewedOrder`; không tương đương xét object runtime |
| `execution(* *.publish(Object))` | Chữ ký method khai báo `Object` | Cùng một method có thể nhận cả annotated/unannotated objects |

Ví dụ `execution(* *.publish(Object))` tự nó không biết actual payload class được annotate hay không. Vì thế `@args` có thể bổ sung khả năng lọc dynamic cho một method signature chung.

### 4.2. @args và @annotation

`@annotation` kiểm tra annotation trên **method đang được thực thi**:

```java
@Before("@annotation(com.example.app.aop.AuditedOperation)")
public void beforeAnnotatedMethod() {
}
```

Đây là snippet, giả sử `AuditedOperation` là annotation dành cho `ElementType.METHOD`. Method được annotate có thể khớp bất kể đối số là `ReviewedOrder` hay `PlainOrder`.

Ngược lại:

```java
@Before("@args(com.example.app.aop.Reviewed)")
public void beforeAnnotatedArgumentType() {
}
```

chọn theo runtime annotation của đối số, không yêu cầu method có `@AuditedOperation`. Hai điều kiện có thể kết hợp nếu cần.

### 4.3. @args và @within / @target

- `@within(TypeAnnotation)`: chọn những method executions được khai báo trong các type có annotation đó, tùy cách Spring xét type/declaring type.
- `@target(TypeAnnotation)`: nhìn annotation trên **runtime target object type** phía sau Spring proxy.
- `@args(TypeAnnotation)`: nhìn annotation trên **runtime type của actual arguments** truyền vào method, không phải target.

Giả sử Spring target `OrderService` không mang `@Reviewed`, nhưng input `ReviewedOrder` mang annotation: `@args(Reviewed)` có thể khớp; `@target(Reviewed)` không khớp bởi target service không được đánh dấu. Đổi vị trí annotation từ payload class sang service class sẽ làm thay đổi semantics.

### 4.4. Annotation trên tham số method không phải @args

Ví dụ:

```java
public void publish(@NotNull Object event) {
}
```

`@NotNull` được gắn vào **parameter declaration**, không gắn lên `event.getClass()`. Vì vậy, nó **không tạo điều kiện** để `@args(NotNull)` khớp như annotation trên runtime argument type. Bản thân `@NotNull` ở ví dụ cũng là khái niệm validation khác, không phải lý do Spring AOP tự áp dụng một aspect.

Nếu mục tiêu là kiểm tra annotation trực tiếp trên parameter của Java method, cần thiết kế giải pháp phù hợp (ví dụ validation hay reflection trong advisor riêng), không dùng `@args` để kỳ vọng nó kiểm tra `Method.getParameterAnnotations()`.

## 5. Số lượng và vị trí của đối số trong @args

### 5.1. Một vị trí: method có một argument

```java
@Pointcut("@args(com.example.app.aop.Reviewed)")
public void oneAnnotatedArgumentType() {
}
```

Đây là trường hợp tài liệu Spring mô tả tường minh: method execution có **một** argument, với runtime type mang `@Reviewed`. Nó không có nghĩa “method có bao nhiêu đối số cũng được, miễn có một đối số annotated”.

### 5.2. Nhiều vị trí và dấu đại diện

AspectJ-style annotation pattern hỗ trợ tổ hợp vị trí. Một ví dụ định hướng:

```java
@Pointcut("@args(*, com.example.app.aop.Reviewed)")
public void secondArgumentAnnotated() {
}
```

Mục tiêu của biểu thức là chọn method có **hai** đối số, trong đó runtime type của đối số **thứ hai** mang `@Reviewed` và vị trí đầu được dùng wildcard. Ví dụ này là snippet minh họa cho cú pháp vị trí, không phải một phần của project chạy ở mục 7.

Trong những hệ thống có nhiều overload, varargs, nested collections hoặc mixed annotations, hãy **xác minh cú pháp pattern cụ thể và test trên Spring/AspectJ version đang dùng**; đừng dùng ý tưởng “bất kỳ một argument nào annotated là được” như thể mọi biến thể `@args` đều có semantics đó.

### 5.3. Trường hợp List<T>, mảng, varargs

Nếu method nhận `List<Object>` chứa một `ReviewedOrder`, actual argument duy nhất ở runtime là một **List implementation**, không phải từng phần tử bên trong. `@args(Reviewed)` sẽ xét runtime type của chính List object; nó **không tự duyệt** từng item tìm annotation.

Tương tự, khi method nhận một mảng `ReviewedOrder[]`, actual argument runtime là **array class**, không tự coi nó tương đương annotation trên kiểu thành phần của mảng. Varargs trong Java có thể được biên dịch thành array parameter; do đó cần phân biệt call-site syntax và actual arguments mà Spring AOP nhìn thấy.

Nếu yêu cầu là “bất kỳ item nào trong collection được annotate”, viết business validation/advice logic duyệt collection hoặc dùng cơ chế validation phù hợp. Không kỳ vọng `@args` tự làm việc đó.

## 6. Ràng buộc @args vào phạm vi Spring service

`@args` có tính chất động: annotation của runtime argument có thể thay đổi giữa những lời gọi đến cùng một method.

Nên giới hạn trước bằng điều kiện **ổn định**:

```java
@Aspect
public class ReviewedPayloadAspect {

    @Pointcut("within(com.example.app.service..*)")
    public void serviceLayer() {
    }

    @Pointcut("execution(public * *(..))")
    public void publicMethods() {
    }

    @Pointcut("@args(com.example.app.aop.Reviewed)")
    public void reviewedArgumentType() {
    }

    @Before("serviceLayer() && publicMethods() && reviewedArgumentType()")
    public void beforeReviewed() {
        // Chỉ chạy cho lời gọi phù hợp cả layer, chữ ký và runtime arg.
    }
}
```

Đoạn trên là snippet phụ thuộc package/annotation của ứng dụng, không phải một program standalone. Nó diễn giải ba lớp điều kiện:

1. `within(service..*)`: target method execution thuộc service layer.
2. `execution(public * *(..))`: method public.
3. `@args(Reviewed)`: actual arguments tương ứng có runtime annotation phù hợp.

**Tránh dùng `@args` như một quy tắc ủy quyền bảo mật duy nhất.** Nếu kiểu đối số được tạo hoặc điều khiển từ bên ngoài, runtime annotation là thông tin metadata, không phải bằng chứng caller được phép thực hiện nghiệp vụ. Validation, authentication và authorization phải có ranh giới tin cậy phù hợp. Spring AOP proxy cũng có các hạn chế về self-invocation, final/private methods.

## 7. Ví dụ chạy được: một Object parameter, hai runtime payload types

Ví dụ này dùng **Java 17, Spring Framework 6.1.14 và Gradle**, không cần Spring Boot, web server hoặc database. Ta cố tình cho method khai báo `submit(Object payload)` để chứng minh `@args` nhìn vào **class của actual payload** thay vì kiểu khai báo `Object`.

Các điều kiện được kiểm soát:
- Chỉ một `AnnotationConfigApplicationContext`.
- Aspect được đăng ký bằng `@Bean`.
- `@EnableAspectJAutoProxy(proxyTargetClass = true)` tạo class-based proxy cho `OrderProcessor`.
- Có một payload class mang `@Reviewed` và một class không có.
- Mọi lời gọi đến `submit(...)` trong `main` đều qua Spring-managed service proxy.

### 7.1. Cấu trúc project

```text
spring-aop-at-args/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── AppConfig.java
    ├── annotations/Reviewed.java
    ├── model/FlaggedPayload.java
    ├── model/PlainPayload.java
    ├── service/OrderProcessor.java
    └── aop/ArgumentAspect.java
```

### 7.2. Build Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'spring-aop-at-args'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.DemoApplication'
}
```

`spring-context` cung cấp `AnnotationConfigApplicationContext` và `@Configuration`/`@Bean`; `spring-aop` chứa hạ tầng Spring AOP proxy; `aspectjweaver` giúp Spring phân tích pointcut expression của `@Aspect`. Bài này dùng bản Spring cố định để tránh phụ thuộc vào các cấu hình AOP mặc định có thể thay đổi theo Spring Boot.

### 7.3. Annotation nằm trên type và còn tồn tại ở runtime

Tệp `src/main/java/demo/annotations/Reviewed.java`:

```java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface Reviewed {
    String value() default "review";
}
```

- `@Target(ElementType.TYPE)`: annotation được gắn vào class/type declaration.
- `@Retention(RetentionPolicy.RUNTIME)`: annotation có thể được kiểm tra tại runtime.
- `value` là metadata minh họa; pointcut chỉ cần annotation hiện diện. Nếu muốn đọc giá trị annotation trong advice, xem phần binding ở mục 8.

### 7.4. Hai kiểu payload đối lập

Tệp `src/main/java/demo/model/FlaggedPayload.java`:

```java
package demo.model;

import demo.annotations.Reviewed;

@Reviewed("sensitive")
public final class FlaggedPayload {
}
```

Tệp `src/main/java/demo/model/PlainPayload.java`:

```java
package demo.model;

public final class PlainPayload {
}
```

Hai class đều `final` vẫn dùng được **làm đối số** cho service. Spring chỉ cần proxy **service target**, chứ không cần tạo CGLIB proxy cho `FlaggedPayload` hoặc `PlainPayload`. Đừng nhầm `final` của *argument object* với `final` của *Spring bean cần proxy*.

### 7.5. Spring service nhận Object

Tệp `src/main/java/demo/service/OrderProcessor.java`:

```java
package demo.service;

public class OrderProcessor {
    private int targetCalls;

    public void submit(Object payload) {
        targetCalls++;
        String type = payload.getClass().getSimpleName();
        System.out.println("target:" + type);
    }

    public int targetCallCount() {
        return targetCalls;
    }
}
```

`submit` khai báo parameter là `Object`. Method này không bị annotation `@Reviewed` đánh dấu, nhưng actual payload class có thể mang annotation đó. Biến `targetCalls` đếm các lần method target chạy; mọi lời gọi trong demo đều tuần tự nên dùng `int` để output đơn giản.

Để tập trung vào `@args`, chương trình không truyền `null` vào `submit`. Nếu đưa `null` vào thì code `payload.getClass()` phải được sửa xử lý null trước.

### 7.6. Aspect lọc theo runtime annotation

Tệp `src/main/java/demo/aop/ArgumentAspect.java`:

```java
package demo.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ArgumentAspect {
    private int adviceCalls;

    @Before(
        "execution(public void demo.service.OrderProcessor.submit(..))" +
        " && @args(demo.annotations.Reviewed)"
    )
    public void beforeReviewed(JoinPoint joinPoint) {
        adviceCalls++;
        Object argument = joinPoint.getArgs()[0];
        System.out.println(
            "advice:" + argument.getClass().getSimpleName());
    }

    public int adviceCallCount() {
        return adviceCalls;
    }
}
```

Trong lời khai báo:
- `execution(public void demo.service.OrderProcessor.submit(..))` chỉ chọn method phù hợp trong service.
- `@args(demo.annotations.Reviewed)` chỉ chọn lời gọi có **một actual argument**, runtime class mang `@Reviewed`.
- `JoinPoint.getArgs()[0]` đọc object đã được truyền vào lần invocation đang được advice.
- Lời gọi đến `PlainPayload` không làm advice chạy; do đó `beforeReviewed` không được gọi với payload đó.

Advice là `@Before` nên in log **trước** phần method target. Ta dùng một aspect singleton để đếm số lần advice chạy; bài chỉ chạy tuần tự, không dùng bộ đếm mutable này làm mô hình concurrency production.

### 7.7. Đăng ký bean và bật Spring AOP

Tệp `src/main/java/demo/AppConfig.java`:

```java
package demo;

import demo.aop.ArgumentAspect;
import demo.service.OrderProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OrderProcessor orderProcessor() {
        return new OrderProcessor();
    }

    @Bean
    public ArgumentAspect argumentAspect() {
        return new ArgumentAspect();
    }
}
```

Spring bean `orderProcessor` được xử lý bởi auto-proxy creator sau khi Spring phân tích advisor từ `ArgumentAspect`. `@Aspect` không tự đăng ký bean, nhưng `@Bean argumentAspect()` bảo đảm aspect nằm trong context. `proxyTargetClass=true` dùng class-based proxy để `context.getBean(OrderProcessor.class)` có thể trả đúng kiểu.

### 7.8. Entry point

Tệp `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import demo.aop.ArgumentAspect;
import demo.model.FlaggedPayload;
import demo.model.PlainPayload;
import demo.service.OrderProcessor;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderProcessor processor =
                context.getBean(OrderProcessor.class);
            ArgumentAspect aspect =
                context.getBean(ArgumentAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(processor));

            processor.submit(new FlaggedPayload());
            processor.submit(new PlainPayload());

            Object polymorphic = new FlaggedPayload();
            processor.submit(polymorphic);

            System.out.println("adviceCount=" + aspect.adviceCallCount());
            System.out.println("targetCount=" + processor.targetCallCount());
        }
    }
}
```

Dòng `Object polymorphic = new FlaggedPayload();` là kiểm chứng quan trọng: kiểu khai báo biến là `Object`, còn runtime class vẫn là `FlaggedPayload` được annotate. Spring AOP nên xử lý giống lời gọi thứ nhất.

### 7.9. Chạy và kiểm tra kết quả

Ở thư mục chứa `build.gradle`, chạy với một bản Gradle hỗ trợ Java 17:

```bash
gradle run
```

Nếu đã có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

**Các dòng ứng dụng Java in ra**, không kể log/banner của Gradle hoặc logging môi trường:

```text
proxy=true
advice:FlaggedPayload
target:FlaggedPayload
target:PlainPayload
advice:FlaggedPayload
target:FlaggedPayload
adviceCount=2
targetCount=3
```

Diễn giải:
1. `proxy=true` chứng minh `OrderProcessor` được Spring AOP proxy.
2. Lời gọi có `FlaggedPayload` thứ nhất in `advice` rồi `target`.
3. Lời gọi với `PlainPayload` **chỉ** in `target` vì runtime class không có `@Reviewed`.
4. Lời gọi qua biến `Object polymorphic` lại được advice vì runtime class thực tế vẫn là `FlaggedPayload`.
5. `adviceCount=2` và `targetCount=3` chứng minh chỉ hai trong ba method invocations khớp `@args`, mặc dù cả ba đều vào cùng method signature `submit(Object)`.

Nếu thử thay `@args(demo.annotations.Reviewed)` bằng chỉ `execution(...)`, advice có thể chạy cho cả ba lời gọi vì điều kiện runtime annotation không còn. Đây là cách phân biệt rõ vai trò của từng mảnh pointcut.

## 8. Binding trong @args: lấy annotation object hoặc đối số

Spring cho phép những pointcut binding như `args` và `@args` đưa dữ liệu đến advice method. Đây là cơ chế **khác** với chỉ kiểm tra annotation có tồn tại.

### 8.1. Bind annotation

Giả sử `@Reviewed` có `value()`, có thể dùng tên tham số trong pointcut:

```java
@Before(
    value = "execution(public void demo.service.OrderProcessor.submit(..))" +
            " && @args(reviewed)",
    argNames = "reviewed"
)
public void beforeReviewed(Reviewed reviewed) {
    System.out.println("label=" + reviewed.value());
}
```

Snippet này thay thế method advice ở mục 7, không đăng ký thêm song song nếu chỉ muốn một log. Cần import `demo.annotations.Reviewed`. Tên `reviewed` trong `@args(reviewed)` được bind vào **annotation instance**, còn giá trị đối số thật không phải chính annotation đó.

`argNames="reviewed"` biểu thị tên binding tường minh; có ích khi mã biên dịch không lưu parameter names, dù Spring cũng có các cơ chế phát hiện tên khác.

### 8.2. Bind actual argument cùng annotation

Khi cần cả đối số và metadata của annotation, biểu thức có thể kết hợp `args(payload)` với `@args(reviewed)`:

```java
@Before(
    value = "execution(public void demo.service.OrderProcessor.submit(..))" +
            " && args(payload) && @args(reviewed)",
    argNames = "payload,reviewed"
)
public void before(Object payload, Reviewed reviewed) {
    System.out.println(payload.getClass().getSimpleName());
    System.out.println(reviewed.value());
}
```

Đây cũng là **snippet thay thế** trong một `@Aspect`, không phải code cần dán bổ sung đồng thời vào project đang chạy. Với phương thức có một đối số, `args(payload)` lấy actual object còn `@args(reviewed)` lấy annotation trên runtime type. Khi dùng annotation/binding trong production, nên có integration test cho advice parameter binding và loại proxy của version Spring đang chạy.

Nếu chỉ cần xem object mà không cần bind annotation, `JoinPoint.getArgs()` như ở ví dụ chính ít có yêu cầu discovery tên tham số hơn.

## 9. Những giới hạn phải kiểm tra trong hệ thống thật

### 9.1. Annotation phải tồn tại ở runtime

Một annotation định nghĩa như sau không thích hợp cho `@args`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface SourceOnlyFlag {
}
```

`RetentionPolicy.SOURCE` không giữ annotation ở runtime để Spring/AspectJ matcher đọc. Dù code compile, lời gọi runtime sẽ không khớp như mong muốn. Với marker type cho `@args`, dùng `RUNTIME` trừ khi có lý do thiết kế khác.

### 9.2. Annotation trên interface và class không luôn tương đương

Nếu chỉ annotation lên một **interface**, không nên mặc định `getClass()` của implementation mang annotation đó. Java `@Inherited` (nếu sử dụng) tác động tới một số trường hợp **kế thừa annotation từ superclass**, không làm type annotation tự lan từ interface sang implementation class.

`@args` xét annotation theo kiểu runtime của actual argument; vì vậy cần kiểm tra:
- Annotation được đặt trên **implementation class thật** hay chỉ trên interface?
- Runtime class có phải một subclass hoặc proxy class không?
- Annotation có `@Inherited` hay không, và có áp dụng cho hierarchy đang xét không?
- Spring/AspectJ expression matcher sẽ xem runtime object như thế nào trên cấu hình thực tế?

Giải pháp an toàn là **thiết kế annotation boundary rõ ràng** và viết test trên class/runtime argument thực. Không lấy `@args` để thay thế mọi kiểu tra cứu annotation trong hierarchy.

### 9.3. Argument bản thân là một proxy

Nếu truyền **một Spring AOP proxy** làm đối số cho service khác, lớp runtime của đối số có thể là JDK dynamic proxy hoặc CGLIB subclass, không giống class implementation trong source. Sự hiện diện của annotation trên implementation không bảo đảm proxy class sẽ biểu lộ cùng metadata theo đúng cách `@args` matcher kỳ vọng.

Khi áp dụng `@args` lên những đối số là framework proxy:
1. Xác định kiểu proxy của **argument object**, không chỉ proxy của service được advice.
2. Kiểm chứng matcher bằng test với runtime argument thực.
3. Nếu nghiệp vụ cần annotation trên **target class phía sau proxy**, cân nhắc truy xuất target type bằng Spring utility trong code kiểm tra metadata có chủ đích, thay vì giả định `@args` đã unwrap mọi proxy.

### 9.4. null không có runtime class

Một biến `Object value = null` không có class runtime để đọc type annotation. Đừng giả định pointcut có thể suy ra rằng “đây là annotated type” chỉ từ parameter declaration hoặc từ generic type. Dùng null validation rõ ràng, và nếu null là input hợp lệ, kiểm tra hành vi Spring AOP và advice của phiên bản thực tế trước khi dựa vào đó.

### 9.5. Bộ sưu tập không được kiểm tra đệ quy

Method `submit(List<ReviewedOrder> values)` nhận một `List` object. `@args(Reviewed)` không tự duyệt phần tử để tìm `@Reviewed`. Tương tự, một wrapper `Envelope<ReviewedOrder>` không trở thành annotated runtime class chỉ vì generic argument của nó mang annotation. Nếu muốn kiểm tra nested contents, cần logic duyệt cụ thể hoặc validation layer thích hợp.

### 9.6. Spring AOP chỉ thấy lời gọi qua proxy

Trong Spring Framework, `@args` vẫn chịu mọi ranh giới của Spring AOP proxy:

- Target bean phải do Spring quản lý và được advice infrastructure phát hiện.
- Lời gọi phải qua Spring-managed proxy, không phải object tạo bằng `new`.
- Self-invocation như `this.submit(payload)` trong cùng target không đi qua advice.
- Class-based proxy không thể chặn method `final`/`private` qua override.
- JDK proxy chỉ expose các method thuộc interface proxy thích hợp; tính khả dụng của method có thể khác CGLIB.
- `@args` không biến Spring proxy AOP thành cơ chế intercept constructor, field access hay method calls không được proxy hóa.

**Đừng thay đổi pointcut để sửa self-invocation.** Nếu business rule cần advice trên cả method gọi nội bộ, tách thao tác sang bean cộng tác và gọi qua Spring bean proxy từ bên ngoài.

### 9.7. Match động có chi phí runtime

`@args` phụ thuộc **actual arguments**, có thể khác nhau giữa hai lời gọi cùng một method. Vì vậy điều kiện này thường không thể quyết định hoàn toàn chỉ từ method signature khi Spring tạo proxy. AOP infrastructure có thể phải đánh giá thêm trong từng invocation.

Tài liệu Spring AOP phân biệt `MethodMatcher` static và runtime; runtime matching nhận `Object... args` để xét argument values. Do đó:
- Giới hạn bằng `execution(...)`/`within(...)` cho những service methods thật sự cần thiết.
- Không lạm dụng `@args` cho toàn bộ application chỉ để kiểm tra annotation mà service có thể kiểm tra rõ ràng một lần.
- Đo hiệu năng trong workload thực nếu đây là hot path; không suy luận một con số overhead cố định.
- Không giữ business state thay đổi theo từng invocation trong field mutable của singleton aspect nếu hệ thống concurrent, trừ khi đã thiết kế thread safety.

## 10. Cách chọn pointcut đúng theo yêu cầu

| Yêu cầu | Công cụ phù hợp |
| --- | --- |
| Chọn method `submit` có parameter **khai báo** là `Object` | `execution(* *.submit(Object))` |
| Chọn lời gọi có runtime argument thuộc một class/interface cụ thể | `args(TypePattern)` |
| Chọn lời gọi mà **runtime class của actual argument** mang `@Reviewed` | `@args(Reviewed)` |
| Chọn method được đánh dấu `@AuditedOperation` | `@annotation(AuditedOperation)` |
| Chọn lời gọi trên service target type được annotate | `@target(Marker)` nếu semantics là target runtime annotation |
| Chọn method được khai báo trong annotated type | `@within(Marker)` |
| Chọn các Spring beans theo tên | `bean(namePattern)` |
| Chọn cả layer lẫn runtime argument annotation | `within(service..*) && @args(Reviewed)` |
| Kiểm tra annotation trực tiếp trên Java parameter declaration | Validation hoặc reflection/advisor logic riêng; `@args` không phải phép kiểm tra này |
| Kiểm tra từng item trong `List` hay nested object | Duyệt đối số hoặc dùng validation phù hợp; `@args` không tự duyệt sâu |

### Câu hỏi tự kiểm tra

**Tình huống A:** Service khai báo `void save(Object x)`, đối số thực tế là instance `AnnotatedInvoice` được gắn `@Reviewed`. Nếu lời gọi qua Spring proxy và pointcut là `@args(Reviewed)`, advice có thể chạy không?

**Đáp án:** Có. Runtime type của actual argument được annotate.

**Tình huống B:** Service khai báo `void save(@Reviewed Object x)`, còn object truyền vào thuộc `PlainInvoice` không mang annotation ở type. Advice `@args(Reviewed)` có chạy do annotation trên parameter declaration không?

**Đáp án:** Không thể lấy annotation trên method parameter để làm căn cứ cho `@args`; hơn nữa `@Reviewed` dành cho `TYPE` trong ví dụ này nên cách annotate parameter như thế còn không hợp lệ. Nếu muốn đánh dấu parameter, cần annotation có `@Target(PARAMETER)` và một cơ chế kiểm tra khác.

**Tình huống C:** `@Reviewed` chỉ đặt trên `List` element type mà method nhận `List<Object>`. Có nên kỳ vọng `@args(Reviewed)` tự inspect mỗi item?

**Đáp án:** Không. Nó xét runtime type của actual argument là đối tượng List, không tự duyệt phần tử.

**Tình huống D:** Trong bean target, `process()` tự gọi `this.submit(new FlaggedPayload())`. Lớp payload có `@Reviewed`. Advice có chạy không?

**Đáp án:** Với Spring AOP theo proxy, self-invocation bỏ qua proxy nên không chạy advice cho lời gọi nội bộ đó, dù điểm cắt dựa trên runtime argument sẽ phù hợp nếu invocation đi qua proxy.

## 11. Quy trình debug một @args pointcut không chạy

1. **Xác nhận annotation definition.** Có `@Target(TYPE)` và `@Retention(RUNTIME)` chưa? Annotation được đặt trên runtime class thật chưa?
2. **Xác nhận số lượng đối số.** `@args(Reviewed)` một vị trí phù hợp method có một actual argument; nếu method nhận nhiều đối số cần pattern phù hợp vị trí.
3. **Xác nhận runtime class.** In `argument.getClass()` trong code test khi non-null; không chỉ nhìn kiểu khai báo của parameter.
4. **Xác nhận Spring bean/proxy.** Aspect là bean, `@EnableAspectJAutoProxy` hoặc Boot AOP auto-config đang hoạt động và target được gọi qua proxy.
5. **Xác nhận điều kiện static.** Nếu kết hợp `execution(...)` hoặc `within(...)`, method/service có khớp không?
6. **Xác nhận không self-invocation.** Nếu gọi từ method khác trên `this`, proxy advice bị bypass.
7. **Xác nhận argument không phải proxy bất ngờ.** Nếu argument object do Spring hoặc framework proxy, runtime class và metadata có thể khác dự kiến.
8. **Xác nhận null/collection semantics.** Không suy ra annotation của nested elements hoặc của biến null.
9. **Kiểm tra advice binding.** Nếu dùng `@args(reviewed)`, tham số advice phải có kiểu annotation tương ứng và tên binding phải được Spring xác định.
10. **Viết integration test** với ít nhất annotated input, unannotated input và biến khai báo kiểu rộng như `Object` để phát hiện nhầm static và runtime types.

## 12. Kết luận

Trong Spring Aspect, `@args` là pointcut designator để chọn lời gọi method dựa vào **annotation trên runtime type của actual arguments**. Nó phù hợp khi nhiều payload classes đi qua cùng một service API khai báo kiểu rộng nhưng chỉ một số loại payload được đánh dấu cần xử lý bổ sung.

Hãy nhớ ba ranh giới:

- **Type:** `@args` quan tâm runtime type annotation của đối số, không phải method annotation hay parameter-declaration annotation.
- **Shape:** `@args(Annotation)` một vị trí có ràng buộc số lượng/vị trí đối số; collection không được duyệt sâu.
- **Proxy:** Chỉ invocation qua Spring AOP proxy mới được advice; pointcut phù hợp nhưng self-invocation vẫn bỏ qua proxy.

Thiết kế bền vững thường kết hợp `execution`/`within` để thu hẹp layer và `@args` để kiểm tra điều kiện runtime, dùng annotation `RUNTIME`, và có integration tests cho subtype, proxy, null cũng như các method overload quan trọng.

### Tài liệu Spring tham khảo

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): mô tả `@args` là runtime annotation trên actual argument type, cùng ví dụ với một parameter; so sánh với `args`, `@target`, `@within` và `@annotation`.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): tham số advice, `JoinPoint.getArgs()` và binding của `@args`.
- [Spring Framework — Spring AOP Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): `MethodMatcher` tĩnh/động và kiểm tra `matches(Method, Class, Object...)`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy boundary, JDK/CGLIB và self-invocation.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): cấu hình Spring AOP và đăng ký `@Aspect` làm Spring bean.
