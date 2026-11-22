# Spring AOP: Kết quả `null` và phương thức trả về kiểu nguyên thủy

## 1. Vì sao kết quả `null` trở thành lỗi tại ranh giới Spring AOP proxy?

Trong Spring Aspect, một `@Around` advice có thể **thay đổi kết quả cuối cùng** mà consumer nhận từ một method execution. Đây là tính năng hữu ích khi xử lý cache hoặc fallback, nhưng cũng tạo một lỗi đặc trưng: **advice trả `null` cho phương thức có kiểu trả về nguyên thủy**.

```java
@Around("execution(* demo.results.ResultService.count(..))")
public Object incorrect(ProceedingJoinPoint pjp) throws Throwable {
    pjp.proceed();
    return null; // SAI: count() được khai báo trả int.
}
```

Đây là **fragment sai để phân tích**, không phải implementation được khuyến nghị. Cho dù `count()` thật sự trả `int 7`, Spring AOP proxy nhận giá trị `null` từ advice và không thể chuyển nó thành `int` hợp lệ cho caller.

Với Spring Framework 6.x, cả hai họ proxy đều có kiểm tra kiểu này:

- `JdkDynamicAopProxy` kiểm tra kết quả khi method có primitive return type (ngoại trừ `void`).
- `CglibAopProxy` cũng kiểm tra kết quả trong quá trình xử lý return value.
- Khi kết quả là `null` nhưng method signature yêu cầu primitive như `int`, Spring có thể ném `org.springframework.aop.AopInvocationException`. Thông điệp điển hình nói rằng null return value từ advice không khớp primitive return type.

**Đừng nhầm `int 0` với `null`:** `0` là giá trị `int` hợp lệ; `null` không phải một `int`. Spring proxy không tự invent giá trị mặc định `0`, `false` hoặc `0.0` để cứu một advice trả sai.

Bài học này chỉ tập trung vào **Spring Aspect/Spring AOP**, lời gọi qua proxy, outcome mà advice trả về và giới hạn Java return contract. Không bàn AOP tổng quát hoặc AspectJ weaving bên ngoài Spring.

## 2. Cần phân biệt ba “kiểu kết quả”

### 2.1. Declared return type của target

Java method định nghĩa một hợp đồng trả về:

```java
public int count() { return 7; }
public Integer boxedCount() { return null; }
public String nullableName() { return null; }
public void complete() { System.out.println("done"); }
```

- `int` là primitive; không có null.
- `Integer` là reference type; có thể null.
- `String` cũng là reference type; có thể null về mặt Java, dù business contract có thể không cho phép.
- `void` biểu thị method **không có return value**; nó khác với “method có một giá trị null”.

### 2.2. Return type của `ProceedingJoinPoint.proceed()`

Spring AOP `@Around` truy cập kết quả phần còn lại của interceptor chain qua `Object`:

```java
Object result = pjp.proceed();
```

Với method trả `int 7`, trong advice `result` là một object tương thích `Integer(7)` (boxing). Với reference-type method trả null, `result == null`. Với `void`, `proceed()` thông thường cũng trả null, nhưng ý nghĩa ở API level khác nhau.

Vì `Object` không chứa thông tin primitive trực tiếp, **cần xem method signature** để biết null có hợp lệ hay không. Không thể suy từ `result == null` rằng method nhất định trả `String`, `Integer`, hoặc `void`.

### 2.3. Actual return value của around advice

```java
@Around("execution(* demo.results.ResultService.*(..))")
public Object preserving(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    return result;
}
```

**Đây là hình thức mặc định nên dùng khi advice chỉ quan sát:** giá trị của `proceed()` được chuyển tiếp nguyên vẹn (trừ trường hợp advice khác nằm trong chain đã chủ đích transform). Caller cuối cùng nhận kết quả theo return contract của method được proxy công bố.

Ngược lại, nếu advice viết `return null`, `return "OK"` hoặc `return 0`, đó là một **quyết định thay đổi result**, không phải hành động vô hại. Với primitive, return khác type có thể gây exception; với reference type, return khác value có thể phá semantic contract.

## 3. Ma trận null, primitive, wrapper và void trong Spring proxy

| Target method | Kết quả từ target | Advice return | Outcome kỳ vọng |
| --- | --- | --- | --- |
| `int count()` | `7` | `Integer(7)` qua `proceed()` | Caller nhận `int 7` |
| `int count()` | `7` | `null` | **Lỗi** do null không tương thích primitive |
| `int count()` | `7` | `Integer(0)` | Caller nhận `0`: đúng kiểu nhưng **đã thay đổi giá trị** |
| `boolean active()` | `true` | `Boolean.TRUE` | Caller nhận `true` |
| `boolean active()` | `true` | `null` | **Lỗi** null không tương thích primitive |
| `long total()` | `9L` | `Long(9L)` | Caller nhận `9L` |
| `long total()` | `9L` | `Integer(9)` | Không bảo đảm hợp lệ; wrapper khác kiểu |
| `Integer boxedCount()` | `null` | `null` | Hợp lệ theo Java reference type |
| `String nullableName()` | `null` | `null` | Java cho phép; caller phải biết nullability |
| `Optional<String> find()` | `Optional.empty()` | `Optional.empty()` | Hợp lệ và khác với null |
| `Optional<String> find()` | `Optional.empty()` | `null` | Java có thể nhận nhưng phá Optional contract |
| `void complete()` | Không có value | `null` từ `proceed()` | Lời gọi `void` hợp lệ |

**Chú ý về lỗi:** `AopInvocationException` là một outcome phổ biến được Spring thực hiện rõ ràng khi **proxy thấy null cho primitive**, không phải lời hứa rằng mọi loại sai kiểu đều ném chính exception này. Trả `String` cho `int` có thể dẫn tới `ClassCastException` hoặc lỗi type conversion ở nơi khác. Trong Kotlin/coroutines hay custom proxy stack, cơ chế khác có thể tham gia; bài này xét Java 17 và Spring AOP proxy thông thường.

### 3.1. Boxing và unboxing có giải quyết null được không?

Không. Java có thể boxing `int 7` thành `Integer.valueOf(7)` và unboxing `Integer(7)` trở lại `int 7`, nhưng `null` không có trạng thái primitive tương ứng.

```java
Integer boxed = null;
// int primitive = boxed; // Nếu chạy sẽ lỗi NullPointerException khi unboxing.
```

Đây là lỗi **ngôn ngữ Java tại điểm unboxing**. Spring AOP có thêm lớp kiểm tra **ở proxy return boundary**, nên với advice trả null cho target primitive, lỗi có thể là `AopInvocationException` ngay tại proxy, trước khi code caller tự unbox.

### 3.2. `void` khác `Void`

- `void complete()`: không có return value; Spring AOP biểu diễn kết quả bên trong advice bằng null.
- `java.lang.Void completeReference()`: đây là **reference type**, có thể trả null về mặt Java, dù `Void` không có value thông thường để khởi tạo.
- `CompletableFuture<Void> asyncComplete()`: trả một **future object**; một future completed với value null vẫn là một future, không phải advice trả null thay future.

Không dùng kiểu `Void` như một cách diễn tả rằng `void` không cần giữ contract. Trong Spring `@Around`, advice tốt vẫn trả chính result từ `proceed()`.

### 3.3. Primitive `char`, `byte`, `short`, `float`, `double` cũng không nhận null

Nguyên tắc áp dụng cho tất cả các primitive có giá trị: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Wrapper cần tương thích; đừng đoán Spring luôn thực hiện primitive widening khi advice trả một wrapper khác type.

## 4. Vì sao `@Around` nên trả `Object` thay vì `void`?

Spring Framework hướng dẫn method `@Around` **nên khai báo kiểu trả về `Object`**, và tham số đầu tiên phải là `ProceedingJoinPoint`.

**Đúng với một advice logging áp dụng cho nhiều return types:**

```java
@Around("execution(* demo.results..*Service.*(..))")
public Object logResult(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    System.out.println("completed " + pjp.getSignature().getName());
    return result;
}
```

**Sai khi target có non-void methods:**

```java
@Around("execution(* demo.results..*Service.*(..))")
public void logResultWrong(ProceedingJoinPoint pjp) throws Throwable {
    pjp.proceed(); // Giá trị của target bị bỏ qua.
}
```

Tài liệu Spring nêu rằng một advice `@Around` khai báo kiểu trả về `void` khiến caller thấy `null`, **bất kể** target đã return gì. Với `int`, `boolean`... điều này có thể khiến Spring proxy ném lỗi null-primitive; với `String`, nó có thể âm thầm đổi kết quả thành null.

Đừng viết một advice kiểu `void` chỉ vì nó “chỉ log”. Đối với `@Before`, method advice kiểu `void` là bình thường, vì nó không chịu trách nhiệm đưa return value cho caller. Còn `@Around` trực tiếp kiểm soát outcome, nên cần return rõ ràng.

### 4.1. `return` bên trong `finally` có thể phá cả return lẫn exception

```java
@Around("execution(* demo.results..*Service.*(..))")
public Object dangerous(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        return null; // Sai: ghi đè cả return hoặc exception bên trong.
    }
}
```

Java `finally` có lệnh `return` có thể chặn exception đã ném, khiến proxy chỉ thấy null. Đây là lỗi nguy hiểm nếu đang dùng `@Transactional` hoặc caller dựa vào exception để rollback/retry.

**Đúng:**

```java
@Around("execution(* demo.results..*Service.*(..))")
public Object safe(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        System.out.println("end");
    }
}
```

Dù target return null hay throw, cleanup/ghi log cuối vẫn có thể chạy; advice không âm thầm thay outcome. Cần thiết kế cleanup sao cho bản thân nó không tùy tiện ném exception che lỗi gốc.

## 5. Cách xác định return type được khai báo trong Spring Aspect

Trong `@Around` có thể dùng `MethodSignature`:

```java
import org.aspectj.lang.reflect.MethodSignature;
import java.lang.reflect.Method;

MethodSignature signature = (MethodSignature) pjp.getSignature();
Class<?> declaredReturnType = signature.getReturnType();
Method method = signature.getMethod();

System.out.println("returnType=" + declaredReturnType.getName());
```

Đây là **fragment** trong advice, không phải file Java độc lập. Với một Spring-managed bean có method `int count()`, `declaredReturnType == int.class`. Nếu method `void complete()`, result type là `void.class`.

Có thể kiểm tra null-primitive một cách minh bạch khi một advice định thay đổi kết quả:

```java
Object result = pjp.proceed();
Class<?> returnType =
        ((MethodSignature) pjp.getSignature()).getReturnType();

if (result == null && returnType.isPrimitive()
        && returnType != void.class) {
    throw new IllegalStateException(
            "null is incompatible with primitive return type " + returnType);
}
return result;
```

Đây là **fragment phòng vệ**, không bắt buộc khi bạn không thay đổi kết quả của `proceed()`; Spring proxy đã có kiểm tra trường hợp null–primitive. Một target Java method có primitive return và chạy bình thường tự nó không thể return null, nên null xuất hiện thường do advice/interceptor bên trong đã làm biến dạng kết quả.

### 5.1. Method trên JDK proxy có thể là interface method

Với JDK dynamic proxy, `MethodSignature.getMethod()` có thể biểu diễn method trên interface thay vì implementation. Khi cần annotation hoặc return type cụ thể trên implementation, dùng:

```java
MethodSignature signature = (MethodSignature) pjp.getSignature();
Method invoked = signature.getMethod();
Object target = pjp.getTarget();

if (target != null) {
    Method specific = AopUtils.getMostSpecificMethod(
            invoked, target.getClass());
    System.out.println(specific.getReturnType().getName());
}
```

Fragment này cần import `org.springframework.aop.support.AopUtils`. Với bridge/generic methods, còn phải cân nhắc metadata và `BridgeMethodResolver`. Tuy nhiên null–primitive compatibility vẫn được xét theo **return contract của method invocation**, không suy ra chỉ bằng cách xem một DTO generic.

### 5.2. Method return `Integer` có nhất thiết được phép null?

Về **Java type system**, có. Nhưng business API có thể yêu cầu non-null. Spring proxy chỉ không có căn cứ để coi một `Integer null` là không hợp lệ như `int null`. Nếu muốn bảo đảm non-null reference, đặt validation ở boundary phù hợp (ví dụ annotation validation có cơ chế thực thi) hoặc kiểm tra cụ thể trong service/around advice.

## 6. Kết quả null của `@AfterReturning` khác với kết quả null của `@Around`

Spring `@AfterReturning` chạy khi method execution kết thúc **bình thường**, kể cả khi method reference type return null. Nhưng có hai kiểu advice cần phân biệt:

**Không bind return value:**

```java
@AfterReturning("execution(* demo.results.ResultService.nullableName(..))")
public void afterNormal() {
    System.out.println("completed normally");
}
```

**Bind return value với kiểu cụ thể:**

```java
@AfterReturning(
    pointcut = "execution(* demo.results.ResultService.nullableName(..))",
    returning = "value"
)
public void inspect(String value) {
    System.out.println("value=" + value);
}
```

Các đoạn là **fragment** thay thế lẫn nhau. Khi có `returning="value"`, Spring dùng kiểu tham số advice để giới hạn matching/binding của return value. Cần hiểu semantics matching đối với `null` và loại tham số cụ thể theo phiên bản/cấu hình; đừng coi `String value` luôn được gọi với một String non-null. Với mục tiêu chỉ biết method hoàn tất, `@AfterReturning` **không cần binding** là lựa chọn đơn giản nhất.

**Đặc biệt:** method `@AfterReturning` không phải nơi để trả một reference mới thay target result. Nếu advice có method return `String`, giá trị return từ advice không trở thành kết quả mới cho caller. Khi cần thay kết quả, dùng `@Around` và đảm bảo return type tương thích.

### 6.1. `null` không nhất thiết nghĩa là exception

Nếu method trả `String null` qua proxy và không có advisor cấm null, invocation vẫn kết thúc **bình thường**. `@AfterThrowing` không chạy chỉ vì return value null. Ngược lại, khi advice trả null cho `int` khiến Spring proxy ném exception, đó là lỗi **ở ranh giới proxy/advice**, không phải một exception tự nhiên do target method ném.

### 6.2. `@AfterThrowing` không là bộ giám sát mọi lỗi trong interceptor chain

Một advice `@AfterThrowing` được định nghĩa cho exceptional exit từ method execution được advice; tài liệu Spring lưu ý nó **không phải general exception callback** bắt mọi lỗi của các advice khác. Khi Spring proxy tự ném `AopInvocationException` vì null–primitive ở lớp ngoài chain, không được mặc định một `@AfterThrowing` dành cho method đích sẽ nhìn thấy lỗi đó. Cần quan sát tại caller hoặc dùng `@Around` ngoài thích hợp, có chú ý advisor precedence.

## 7. Ví dụ Java 17 + Spring Framework 6.2: đúng null và sai null

Ví dụ hoàn chỉnh sau dùng Maven, Java 17, Spring Framework 6.2 và **Spring AOP proxy** (không cần Spring Boot). Dùng interface `ResultPort` để JDK dynamic proxy thể hiện rõ return contract.

Dự án có một Spring-managed service với:

- `nullableName()` trả String null **hợp lệ về Java**;
- `count()` trả primitive `int 7`;
- `zero()` trả primitive `int 0` **hợp lệ**, không phải null;
- `boxedCount()` trả `Integer null`;
- `emptyResult()` trả `Optional.empty()` (khác null);
- `complete()` trả `void`;
- `brokenPrimitive()` trả primitive `int 9`, nhưng **một advice cố tình trả null**, khiến proxy ném lỗi.

Các pointcuts cho trường hợp bảo toàn và trường hợp lỗi **không chồng nhau**, do đó không cần dựa vào advisor precedence để dự đoán stdout.

### 7.1. Cấu trúc thư mục

```text
spring-aop-null-primitive/
├── pom.xml
└── src/main/java/demo/results/
    ├── AppConfig.java
    ├── ResultPort.java
    ├── ResultService.java
    ├── ResultAspect.java
    └── Main.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-null-primitive</artifactId>
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
                <version>3.14.0</version>
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

### 7.3. `AppConfig.java`

```java
package demo.results;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` phát hiện service và aspect trong package `demo.results`. `@EnableAspectJAutoProxy` bật Spring AOP proxying. Target triển khai interface; `proxyTargetClass=false` ưu tiên JDK dynamic proxy.

### 7.4. `ResultPort.java`

```java
package demo.results;

import java.util.Optional;

public interface ResultPort {
    String nullableName();
    int count();
    int zero();
    Integer boxedCount();
    Optional<String> emptyResult();
    void complete();
    int brokenPrimitive();
}
```

Method `int brokenPrimitive()` có primitive return; không thể return null trong Java source của target. Lỗi sẽ đến từ advice return `Object null`.

### 7.5. `ResultService.java`

```java
package demo.results;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class ResultService implements ResultPort {
    @Override
    public String nullableName() {
        System.out.println("[target] nullableName");
        return null;
    }

    @Override
    public int count() {
        System.out.println("[target] count");
        return 7;
    }

    @Override
    public int zero() {
        System.out.println("[target] zero");
        return 0;
    }

    @Override
    public Integer boxedCount() {
        System.out.println("[target] boxedCount");
        return null;
    }

    @Override
    public Optional<String> emptyResult() {
        System.out.println("[target] emptyResult");
        return Optional.empty();
    }

    @Override
    public void complete() {
        System.out.println("[target] complete");
    }

    @Override
    public int brokenPrimitive() {
        System.out.println("[target] brokenPrimitive");
        return 9;
    }
}
```

Target minh họa các kết quả Java hợp lệ. `null` ở `nullableName()` và `boxedCount()` là null reference. `emptyResult()` trả **một Optional object rỗng**, không phải null. `zero()` trả số 0 hợp lệ.

### 7.6. `ResultAspect.java`

```java
package demo.results;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ResultAspect {
    @Around(
        "execution(* demo.results.ResultService.*(..))"
      + " && !execution(* demo.results.ResultService.brokenPrimitive(..))"
    )
    public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
        String name = pjp.getSignature().getName();
        Object result = pjp.proceed();

        String kind = result == null
                ? "null"
                : result.getClass().getSimpleName();

        System.out.println("[advice] " + name + " kind=" + kind);
        return result;
    }

    @Around("execution(* demo.results.ResultService.brokenPrimitive(..))")
    public Object breakPrimitive(ProceedingJoinPoint pjp) throws Throwable {
        Object result = pjp.proceed();
        System.out.println("[advice] brokenPrimitive discarded=" + result);
        return null; // Chủ đích minh họa lỗi Spring proxy.
    }
}
```

Hai advices có expression tách biệt:

- `preserve(...)` nhận các method còn lại của `ResultService`, gọi `proceed()` một lần, log runtime kind khi result không null, **trả nguyên value**.
- `breakPrimitive(...)` chỉ match `brokenPrimitive()`, vẫn gọi target nên log target xuất hiện, rồi **return null** bất chấp declared `int`.
- `@Aspect @Component` tạo aspect bean; method target cũng phải đi qua proxy Spring để các advice này chạy.
- `result.getClass()` được bảo vệ bởi kiểm tra `result == null` nên không gây NPE khi reference null/void.

Lưu ý `@Around` phải khai báo `Object` để đảm bảo trả result. Nếu advice có `void` return, caller sẽ nhận null dù target method đã chạy.

### 7.7. `Main.java`

```java
package demo.results;

import org.springframework.aop.framework.AopInvocationException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            ResultPort port = context.getBean(ResultPort.class);
            System.out.println("[main] jdkProxy="
                    + AopUtils.isJdkDynamicProxy(port));

            System.out.println("[caller] name=" + port.nullableName());
            System.out.println("[caller] count=" + port.count());
            System.out.println("[caller] zero=" + port.zero());
            System.out.println("[caller] boxed=" + port.boxedCount());
            System.out.println("[caller] optional=" + port.emptyResult());

            port.complete();
            System.out.println("[caller] complete returned void");

            try {
                System.out.println("[caller] broken="
                        + port.brokenPrimitive());
            } catch (AopInvocationException ex) {
                System.out.println("[caller] primitive null rejected");
            }
        }
    }
}
```

Lệnh biên dịch và chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.results.Main
```

**Stdout dự kiến** từ các lệnh `System.out` của ứng dụng (bỏ qua log riêng của Maven/Spring nếu môi trường phát sinh):

```text
[main] jdkProxy=true
[target] nullableName
[advice] nullableName kind=null
[caller] name=null
[target] count
[advice] count kind=Integer
[caller] count=7
[target] zero
[advice] zero kind=Integer
[caller] zero=0
[target] boxedCount
[advice] boxedCount kind=null
[caller] boxed=null
[target] emptyResult
[advice] emptyResult kind=Optional
[caller] optional=Optional.empty
[target] complete
[advice] complete kind=null
[caller] complete returned void
[target] brokenPrimitive
[advice] brokenPrimitive discarded=9
[caller] primitive null rejected
```

### 7.8. Đọc kết quả theo từng trường hợp

1. `jdkProxy=true`: bean `ResultService` được Spring proxy qua interface `ResultPort`.
2. `nullableName()`: target trả reference null, around advice thấy null và trả nguyên; caller in `name=null`. Đây là **normal return**, không phải primitive lỗi.
3. `count()`: target trả primitive 7. Khi `proceed()` hoàn tất, advice nhận wrapper `Integer`, log `kind=Integer`, rồi trả wrapper; caller nhận primitive 7.
4. `zero()`: target trả `int 0`. Advice log `Integer`, caller nhận 0; **0 khác null**.
5. `boxedCount()`: declared `Integer` cho phép null, advice trả null nên proxy chấp nhận. Caller in `boxed=null`.
6. `emptyResult()`: giá trị là Optional object. `getClass().getSimpleName()` trong JDK thông thường in `Optional`, caller in `Optional.empty`.
7. `complete()`: target void; `proceed()` biểu diễn kết quả bằng null; advice return null hợp lệ vì declared type là `void`.
8. `brokenPrimitive()`: target đã trả `int 9`; advice cố tình **bỏ** `Integer(9)` và return null. Spring proxy phát hiện declared primitive type và ném `AopInvocationException`. Caller bắt và in dòng `primitive null rejected`.
9. Tất cả các invocation từ Main đi qua Spring-managed reference; nếu dùng `new ResultService()` thay cho DI/context, advice không chạy và `brokenPrimitive()` sẽ trả 9 bình thường.

**Cảnh báo:** dòng số 8 là lỗi được tạo **có chủ đích để học**. Trong production phải sửa advice, không bắt lỗi từ proxy rồi trả thành công giả.

## 8. Nếu mục tiêu là fallback, chọn giá trị tương thích và có ý nghĩa

Một `@Around` có thể catch exception và trả fallback:

```java
@Around("execution(int demo.results.ResultService.count(..))")
public Object fallbackCount(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return 0; // Integer(0) qua Object, tương thích int.
    }
}
```

Đây là **fragment riêng**, không được thêm vào dự án mục 7 nếu chưa thiết kế ordering giữa nhiều around advices. Về mặt kiểu Java, số 0 có thể đi qua proxy tới `int`. Nhưng **đúng kiểu không bảo đảm đúng nghiệp vụ**: với số lượng đơn hàng hay số tiền, 0 có thể là dữ liệu sai nghiêm trọng.

Nếu method thực tế trả `Optional<String>`, fallback thường thích hợp hơn là `Optional.empty()` (theo contract). Nếu method trả `CompletableFuture<String>`, fallback phải là một future tương thích, không phải String payload. Nếu method trả `String` có `@NonNull` contract, return null dù Java cho phép vẫn là vi phạm nghiệp vụ.

### 8.1. Quy tắc tránh silent data corruption

- **Không tự chuyển null thành 0** cho primitive nếu không có requirement nghiệp vụ.
- **Không dùng `return null` chung** cho mọi return type.
- **Không dùng `Object.class`** như lời giải cho vấn đề typed contract: method public vẫn có signature declared return type cố định.
- **Không gọi `proceed()` hai lần** để “lấy lại value” nếu invocation có thể có side effects.
- **Không trả wrapper khác type** rồi hy vọng runtime sẽ tự chuyển thành primitive tương ứng.
- **Không catch `Throwable` rồi return null** để che mọi lỗi; có thể nuốt exceptions nghiêm trọng và che rollback conditions.

## 9. Null, exception và transaction trong Spring AOP

### 9.1. Null reference return là normal completion

Một method `String lookup()` trả null không tự ném exception; Spring có thể cho invocation kết thúc bình thường. Vì thế `@AfterReturning` có thể chạy, còn `@AfterThrowing` thường không chạy chỉ vì kết quả null.

Nếu application yêu cầu null là lỗi, hãy tạo **validation policy** có căn cứ ở service/interface boundary; dùng `@NonNull`/validation cần framework thực sự thực thi, chứ chỉ tên annotation không tự bảo đảm Spring AOP biến mọi null thành exception.

### 9.2. Null primitive là lỗi được phát hiện tại proxy boundary

Nếu một `@Around` bên trong chain trả null cho method primitive, Spring proxy bên ngoài có thể ném `AopInvocationException`. Lỗi này không nhất thiết phát sinh từ thân target method; trong demo mục 7 target đã chạy xong và trả int đúng.

Điều này quan trọng khi debugging:

```text
[target] brokenPrimitive
[advice] brokenPrimitive discarded=9
[caller] primitive null rejected
```

**Không suy ra target đã ném exception** chỉ vì caller bắt được lỗi từ lời gọi proxy. Cần phân biệt target exception và proxy/advice return contract violation.

### 9.3. Transaction rollback không chữa return mismatch

Spring `@Transactional` có thể dùng một advisor khác trong chain. Nếu transaction interceptor thấy target trả bình thường nhưng một outer AOP layer sau đó ném null-primitive exception, rollback/commit đã có thể được quyết định ở boundary bên trong. Nếu lỗi phát sinh bên trong transaction boundary, nó có thể kích hoạt rollback tùy exception type và rollback rules.

Do đó không tuyên bố “primitive null làm transaction rollback” trong mọi cấu hình. Hãy xem advisor ordering, transaction interceptor position và test commit/rollback thực tế.

### 9.4. Async return wrappers

Method `CompletableFuture<Integer> countAsync()` có declared return type **future**, không phải `int`. Một `@Around` trả null có thể không bị kiểm tra null-primitive ngay, vì future là reference type, nhưng caller có thể NPE khi gọi `thenApply(...)`. Tương tự với `Mono<Integer>` hoặc `Flux<Integer>` nếu dùng Reactor.

Một future hoàn thành với kết quả null vẫn là **future object**; wrapper, completion/error behavior và value đều thuộc contract của async API. Không return payload trực tiếp thay future.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân chính | Cách xử lý |
| --- | --- | --- |
| `AopInvocationException` nói null không khớp primitive | Around advice (hoặc advisor) trả null cho `int`/`boolean`... | `return pjp.proceed()` khi chỉ quan sát; fallback phải cùng kiểu |
| Target đã in giá trị đúng nhưng caller vẫn lỗi | Result bị advice ghi đè sau khi target return | Kiểm tra mọi đường `return` của `@Around` |
| Method `String` trả null mà không lỗi proxy | Reference type cho phép null ở JVM | Kiểm tra business nullability contract |
| Method `Integer` trả null khác `int` thế nào? | Wrapper là reference, primitive không nhận null | Dùng type/API phù hợp |
| Method `void` có `result == null` | Không có business return value | Đây là biểu diễn bình thường của `proceed()` |
| `Optional.empty()` bị đổi thành null | Advice phá wrapper contract | Trả lại Optional nguyên bản |
| Advice khai báo `void` áp lên non-void target | Return bị loại bỏ theo semantics Spring `@Around` | Khai báo `Object` và return result |
| Catch error rồi `return null` | Che exception và phá primitive contract | Chỉ fallback khi contract cho phép |
| `return null` trong `finally` | Ghi đè return hoặc exception | Không return trong finally |
| Trả `Integer(5)` cho target `long` | Wrapper không phù hợp `Long` | Giữ nguyên boxed value của proceed |
| `@AfterReturning` không chạy theo dự kiến | Return binding type/pointcut không phù hợp | Kiểm tra declared/actual type, normal completion và annotation |
| Logging advice không chạy khi self-call | `this.method()` bypass proxy | Tách bean hoặc gọi qua Spring proxy đúng ranh giới |
| Return null xảy ra trên JDK proxy nhưng đổi sang CGLIB vẫn lỗi | Cả hai hỗ trợ kiểm tra primitive-null | Sửa advice, không đổi proxy mode để né lỗi |
| Unit test tạo service bằng `new` không tái hiện lỗi | Không có Spring AOP proxy trong unit test | Test tích hợp với ApplicationContext thật |
| Null primitive proxy exception nhưng transaction vẫn commit | Lỗi phát sinh ngoài transaction boundary | Xem advisor chain và transaction ordering |
| Future/Reactive return null gây lỗi ở caller | Reference wrapper bị mất | Giữ wrapper thích hợp |

## 11. Checklist code review và kiểm thử

1. Xác nhận target là Spring-managed bean và aspect được đăng ký; nếu không có proxy, không có advice.
2. Xác định **declared return type** của method, đặc biệt primitive, wrapper, `void`, `Optional` và async wrapper.
3. Với `@Around` chỉ logging/metrics, dùng `Object result = pjp.proceed(); return result;`, gọi proceed đúng một lần.
4. Kiểm tra mọi nhánh `return`, `catch`, `finally`; không trả null ngoài policy.
5. Kiểm tra boxed primitive có đúng wrapper và giá trị hay không.
6. Kiểm tra null reference theo contract nghiệp vụ; `String null` không mặc nhiên là proxy error.
7. Xác nhận `@AfterReturning` và `@AfterThrowing` được dùng đúng outcome semantics.
8. Nếu có multiple advisors, cache, transaction, retry hoặc async, xác minh actual ordering và điểm phát sinh lỗi.
9. Viết integration tests trên **đúng Spring AOP proxy**, với cả value, null, zero, void, Optional và primitive violation.
10. Giữ log exception rõ nguồn: target throw, advice throw hay proxy return type check.
11. Với JDK proxy, gọi qua interface methods; với CGLIB, kiểm tra final/private restrictions và self-invocation.
12. Không sửa lỗi primitive-null bằng cách đặt return zero giả hoặc nuốt exceptions.

### Bảng ca kiểm thử nên có

| Case | Expected result |
| --- | --- |
| `String nullableName()` → null | Caller thấy null nếu contract cho phép |
| `Integer boxedCount()` → null | Caller thấy null |
| `int count()` → 7 | Caller thấy 7 |
| `int zero()` → 0 | Caller thấy 0, không xem là null |
| `void complete()` | Method chạy, không có business return value |
| `Optional.empty()` | Caller thấy Optional rỗng |
| `@Around` cố tình trả null cho `int` | Proxy ném lỗi loại primitive-null mismatch |
| Target ném exception thật | Advice không tự chữa lỗi trừ khi xử lý có chủ đích |
| Self-invocation `this.count()` | Không có interception riêng cho method gọi nội bộ |

## 12. Câu hỏi tự đánh giá

**1. Vì sao `Object result = pjp.proceed()` có thể là `Integer` với method trả `int`?** Vì `proceed()` sử dụng kiểu Object; primitive được boxing trong đường đi qua advice.

**2. `@Around` trả null cho `int` có làm caller nhận 0 không?** Không. Trong Spring AOP proxy thông thường, null không khớp primitive và có thể phát sinh `AopInvocationException`.

**3. `Integer boxedCount()` trả null có phải cùng lỗi không?** Không. Integer là reference type, nên null hợp lệ về Java. Business code vẫn có thể không cho phép.

**4. `void complete()` có `proceed()` trả null thì có lỗi primitive-null không?** Không. Spring loại trừ `void` khỏi kiểm tra null cho primitive có giá trị.

**5. Vì sao `@Around public void log(...)` có thể phá method `String` hoặc `int`?** Vì Spring sẽ trả null cho caller, bỏ qua kết quả `proceed()`.

**6. `@AfterReturning` có thể return String mới để thay result không?** Không theo hợp đồng advice này. Dùng `@Around` nếu cần cố ý thay value.

**7. Nếu `Optional<String>` trả `Optional.empty()`, có nên đổi thành null trong advice không?** Không theo Optional contract thông thường; đó là thay đổi API và có thể gây NPE.

**8. Vì sao dùng `return` trong `finally` nguy hiểm?** Nó ghi đè return và có thể nuốt exception trong Java, khiến proxy thấy outcome sai.

**9. Đổi JDK proxy sang CGLIB có sửa được advice trả null cho int không?** Không. Hai loại Spring proxy đều có giới hạn null-primitive.

**10. Nếu target return đúng nhưng caller nhận lỗi, cần kiểm tra đâu?** Kiểm tra `@Around`, advisors ở ngoài target, đường return sau `proceed()` và proxy return type contract trước khi quy lỗi cho method đích.

## Tài liệu chính thức

- [Spring Framework 6.2 — Declaring Advice: Around Advice và return contract](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — AOP Concepts và Advice types](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html)
- [Spring Framework 6.2 — Proxying Mechanisms: JDK/CGLIB, self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework source — JdkDynamicAopProxy kiểm tra null-primitive](https://github.com/spring-projects/spring-framework/blob/main/spring-aop/src/main/java/org/springframework/aop/framework/JdkDynamicAopProxy.java)
- [Spring Framework source — CglibAopProxy kiểm tra null-primitive](https://github.com/spring-projects/spring-framework/blob/main/spring-aop/src/main/java/org/springframework/aop/framework/CglibAopProxy.java)
- [Spring Framework — @AspectJ support, registration và advisors](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html)
