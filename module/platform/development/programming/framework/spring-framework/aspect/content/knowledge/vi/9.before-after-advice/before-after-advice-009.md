# Chữ ký phương thức advice và cấu hình returning, throwing trong Spring AOP

## 1. Bài toán và kết quả cần nắm

Với **Spring AOP dùng cú pháp @AspectJ**, class có `@Aspect` khai báo các advice như `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing` và `@Around`. Chữ ký Java của **phương thức advice** quyết định Spring có thể truyền cho advice những dữ liệu nào: thông tin `JoinPoint`, argument của target, return value, exception hoặc quyền `proceed()`.

Hai thuộc tính đặc biệt:

- **`returning = "result"`** của `@AfterReturning`: đưa **giá trị trả về khi target kết thúc bình thường** vào một tham số advice tên `result`; **kiểu tham số** cũng ràng buộc tập kết quả được chọn.
- **`throwing = "error"`** của `@AfterThrowing`: đưa **exception thoát ra khỏi target method execution** vào một tham số advice tên `error`; **kiểu tham số** ràng buộc loại exception được chọn.

Đây không phải hai tham số đặt tên tùy ý. Chúng tham gia vào **binding và matching** của Spring @AspectJ; thiếu tên hoặc tên/kiểu không phù hợp có thể khiến advice không áp dụng hoặc ứng dụng lỗi khi tạo advisor.

**Điểm mấu chốt:** `returning` và `throwing` không thuộc Java method signature của *target*; chúng là metadata trên annotation của *advice* và phải khớp **tham số Java của advice**.

Bài chỉ tập trung Spring Aspect: đăng ký Spring-managed aspect bean, Spring proxy, cú pháp advice, parameter binding, kết quả thực tế, lỗi cấu hình và kiểm thử. Không lặp lại lý thuyết AOP chung hay dùng AspectJ bytecode weaving.

## 2. Phân biệt method của target và method của advice

Hai methods dưới đây làm hai nhiệm vụ khác nhau:

```java
// Method của Spring target bean
public String find(String id) {
    return "found:" + id;
}
```

```java
// Method advice nằm trong Spring-managed @Aspect
@AfterReturning(
    pointcut = "execution(public String com.example.advice.OutcomeService.find(..))",
    returning = "result",
    argNames = "result"
)
public void afterFind(String result) {
    System.out.println("result=" + result);
}
```

Đây là các đoạn minh họa rút gọn; muốn chạy thực tế cần đúng packages/imports, config và bean registration.

| Thành phần | Ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `String find(String id)` | Target service | Khai báo nghiệp vụ: input `id`, output `String`. |
| `execution(...)` | Pointcut trên advice | Chọn target method executions có thể được Spring proxy intercept. |
| `returning = "result"` | Attribute của `@AfterReturning` | Bind giá trị trả về vào tham số advice tên `result`. |
| `String result` | Chữ ký Java của advice | Spring truyền return value tương thích `String`; type này còn giới hạn matching. |
| `void afterFind(...)` | Chữ ký Java của advice | Advice phục vụ quan sát; giá trị trả về từ advice không thay giá trị target trả. |
| `argNames = "result"` | Annotation của advice | Làm tên biến binding tường minh khi cần. |

Mục tiêu của `@AfterReturning` là chạy **sau normal return**, không cần đặt tên advice giống target method. Method advice có thể được đặt tên `observeResult`, `recordSuccess`, `afterFind` hoặc tên Java hợp lệ bất kỳ.

### 2.1. Hai nguồn giới hạn matching

Một lời advice muốn chạy cần đáp ứng **cả hai**:

1. **Pointcut expression**: chọn đúng execution của method Spring-managed target.
2. **Binding condition** (nếu có): `returning`/`throwing` và kiểu tham số advice tương thích với outcome.

Vì thế, **hai advice dùng cùng pointcut** có thể chạy số lần khác nhau nếu một advice dùng `returning = "text"` với `String text`, còn advice kia không bind kết quả hoặc dùng `Object result`.

## 3. Bảng chữ ký advice thường dùng trong Spring

| Annotation | Chữ ký advice Java thông dụng | Data được bind | Điều kiện execution |
| --- | --- | --- | --- |
| `@Before("...")` | `public void before()` | Không cần tham số | Ngay trước invocation match. |
| `@Before("...")` | `public void before(JoinPoint jp)` | Metadata method/args, proxy/target | Khi join point sắp được gọi. |
| `@After("...")` | `public void afterFinally()` | Có thể lấy `JoinPoint` | Sau khi join point thoát, bình thường hoặc exception. |
| `@AfterReturning("...")` | `public void afterNormal()` | Không bind return | Method thoát bình thường. |
| `@AfterReturning(pointcut="...", returning="value")` | `public void afterReturn(String value)` | Giá trị trả về kiểu tương thích `String` | Normal return và type binding phù hợp. |
| `@AfterThrowing("...")` | `public void afterThrow()` | Không bind exception | Method thoát bằng exception. |
| `@AfterThrowing(pointcut="...", throwing="error")` | `public void afterThrow(IllegalArgumentException error)` | Exception tương thích `IllegalArgumentException` | Throwing exit đúng kiểu exception. |
| `@Around("...")` | `public Object around(ProceedingJoinPoint pjp) throws Throwable` | Quyền gọi `proceed()` và quyết định kết quả | Bao quanh invocation. |

Các chữ ký là **mẫu phổ biến**, không phải khẳng định chỉ có đúng một chữ ký hợp lệ cho mỗi advice. Spring @AspectJ hỗ trợ binding argument, annotation, `this`/`target` và `JoinPoint` khi expression/tham số tương ứng.

**Quan trọng:** Spring docs khuyên dùng **dạng advice ít quyền nhất đủ đáp ứng yêu cầu**. Nếu chỉ đọc exception, dùng `@AfterThrowing`; nếu chỉ đọc return, dùng `@AfterReturning`. Đừng thay mọi advice thành `@Around` nếu không có nhu cầu quyết định khi nào/how target được thực thi.

## 4. @AfterReturning: hai chữ ký khác nhau

### 4.1. Không có returning: chỉ quan sát normal completion

```java
@AfterReturning(
    "execution(public * com.example.advice.OutcomeService.*(..))"
)
public void afterAnyNormalReturn() {
    normalReturns.incrementAndGet();
}
```

- `@AfterReturning` chạy khi method được chọn **kết thúc bình thường**.
- Không có `returning` nên advice **không nhận giá trị** để inspect.
- Tập method được xét rộng: một `void` method cũng có thể kết thúc bình thường và được tính.
- Nếu target ném exception thoát ra khỏi method, advice này không chạy.

Với `@AfterReturning`, “return normally” là **outcome của method execution**, không tự động đồng nghĩa “đơn hàng được chấp nhận”, “HTTP status 2xx”, “transaction đã commit” hoặc “future hoàn tất thành công”.

### 4.2. Có returning: nhận return value

```java
@AfterReturning(
    pointcut = "execution(public * com.example.advice.OutcomeService.*(..))",
    returning = "value",
    argNames = "value"
)
public void afterString(String value) {
    System.out.println("text=" + value);
}
```

- `value` sau `returning` **chỉ tới** tham số Java `String value` của advice.
- `String` là một **ràng buộc kiểu**; advice không nhận kết quả `Integer` hoặc `void` như thể đó là `String`.
- Nếu dùng `Object value`, matching rộng hơn đối với những normal return values tương thích kiểu `Object`.
- `argNames` tạo ánh xạ tên explicit, tránh phụ thuộc vào build flags/thông tin tên tham số Java.
- Để nhận thêm `JoinPoint`, khai báo nó **đầu danh sách tham số** theo convention Spring; không dùng `ProceedingJoinPoint` ở advice thông thường.

### 4.3. Tên returning phải khớp tên tham số

Ví dụ sai:

```java
@AfterReturning(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    returning = "data",
    argNames = "result"
)
public void wrongAdvice(String result) {
}
```

Đây là **đoạn minh họa cấu hình sai**, không thêm vào một context cần chạy thành công. `returning` nói `data`, còn declaration/`argNames` cung cấp `result`; Spring/AspectJ không có binding hợp lệ cho `data`, có thể lỗi khi khởi tạo advice/advisor.

Cách đúng có thể là:

```java
@AfterReturning(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    returning = "result",
    argNames = "result"
)
public void correctAdvice(String result) {
    // ...
}
```

Không dùng tên method của target, tên field hay một alias tự nghĩ để điền `returning`. Dùng **tên tham số advice** sẽ nhận return value.

## 5. @AfterThrowing: hai chữ ký khác nhau

### 5.1. Không có throwing: sự kiện exceptional exit

```java
@AfterThrowing(
    "execution(public * com.example.advice.OutcomeService.*(..))"
)
public void afterAnyThrownExit() {
    failures.incrementAndGet();
}
```

Advice không có tham số này có thể ghi một failure event khi target method execution được chọn **thoát ra bằng exception**. Nó không biết exception object là gì nếu không bind dữ liệu tương ứng.

Nó **không chạy** khi target tự bắt lỗi và return fallback bình thường. `@AfterThrowing` quan sát **lỗi thoát khỏi join point**, không phải mọi exception từng được ném trong call stack.

### 5.2. Có throwing: nhận exception và lọc theo subtype

```java
@AfterThrowing(
    pointcut = "execution(public * com.example.advice.OutcomeService.*(..))",
    throwing = "problem",
    argNames = "problem"
)
public void afterIllegalArgument(IllegalArgumentException problem) {
    System.out.println("badArg=" + problem.getMessage());
}
```

- `throwing="problem"` bind exception vào **`problem`** của method advice.
- `IllegalArgumentException` giới hạn matching cho instance của kiểu đó (hoặc subtype).
- Nếu muốn chọn nhiều lỗi hơn, có thể dùng `RuntimeException`, `Exception` hoặc `Throwable`, tùy semantics và test.
- Trong Java, `IllegalArgumentException extends RuntimeException`; method ném `IllegalStateException` không match binding `IllegalArgumentException`.
- Tham số exception advice **không phải** object error response và không phải kiểu return value. `throwing` không thay cho `returning`.

### 5.3. @AfterThrowing không phải try/catch handler tổng quát

`@AfterThrowing` **quan sát** một exceptional return. Nó không nhận một `ProceedingJoinPoint` để `proceed()` hoặc tự chuyển một lỗi thành bình thường chỉ bằng return.

Nếu chỉ log exception rồi advice kết thúc bình thường, exception gốc vẫn đi tiếp đến caller. Nếu advice **tự ném exception khác**, caller có thể nhận exception mới thay cho exception gốc — là thay đổi behavior nguy hiểm, không nên dùng để “xử lý lỗi”.

Theo tài liệu Spring, `@AfterThrowing` tập trung vào lỗi từ **user-declared target join point**, không phải một callback bắt mọi exception phát sinh từ một advice `@After`/`@AfterReturning` đồng hành trong cùng aspect.

**Nếu muốn phục hồi hoặc trả fallback cho caller**, hãy xử lý trong business boundary hoặc dùng `@Around` với một `try/catch` thực sự và contract rõ ràng. Đừng gắn `@AfterThrowing` rồi kỳ vọng return của advice thay thế lỗi.

## 6. Các đặc điểm Java method signature cần hiểu

### 6.1. Return type của method advice

Các advice kiểu `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing` **nên khai báo `void`** vì return từ chính advice không được Spring dùng để thay kết quả business method.

`@Around` khác: thường dùng `Object` return type, nhận `ProceedingJoinPoint` và dùng `proceed()`. Giá trị `return` từ `@Around` chính là giá trị mà caller có thể nhìn thấy khi interceptor chain hoàn tất.

```java
@Around("execution(* com.example.advice.OutcomeService.find(..))")
public Object aroundFind(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    return result;
}
```

Đây là đoạn minh họa, cần import `org.aspectj.lang.ProceedingJoinPoint`, nằm trong Spring-managed `@Aspect`. Nếu return từ `@Around` không tương thích với declared return type của target method, ứng dụng có thể lỗi runtime.

### 6.2. Visibility của advice method

Advice methods trong ví dụ để `public`, giúp dễ đọc và giảm rủi ro truy cập khi Spring gọi chúng qua framework infrastructure. Đây là **visibility của method chứa logic advice**, **không phải** visibility của Spring target method trong `execution(public * ...)`.

Không nhầm với visibility của một **named `@Pointcut` method** dùng để tái sử dụng biểu thức. `@Pointcut` có thể được định nghĩa `private`/`protected`/`public` theo phạm vi reuse; điều đó không trực tiếp biến target method thành private hay public.

### 6.3. JoinPoint có thể đứng đầu method advice

```java
@Before("execution(public * com.example.advice.OutcomeService.*(..))")
public void beforeCall(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
```

`JoinPoint` đến từ `org.aspectj.lang.JoinPoint`. Spring có thể truyền metadata của intercepted method execution, target và args.

Ví dụ kết hợp `JoinPoint` và returning:

```java
@AfterReturning(
    pointcut = "execution(public String com.example.advice.OutcomeService.find(..))",
    returning = "result",
    argNames = "result"
)
public void afterFind(JoinPoint jp, String result) {
    System.out.println(jp.getSignature().getName() + "=" + result);
}
```

**Lưu ý:** tham số `JoinPoint` đầu tiên có binding đặc biệt; khi dùng `argNames`, Spring docs cho phép bỏ qua tên `JoinPoint` đầu tiên trong danh sách `argNames`. Không lấy `JoinPoint` làm argument business method.

`JoinPoint.getArgs()` là các arguments được chuyển đến invocation; đó là dữ liệu có thể chứa thông tin nhạy cảm. Log theo whitelist/redaction, không log password/token chỉ vì có thể truy cập.

### 6.4. ProceedingJoinPoint chỉ dành cho @Around

```java
@Around("execution(* com.example.advice.OutcomeService.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

Các advice ngoài `@Around` không nên khai báo `ProceedingJoinPoint` rồi kỳ vọng có thể `proceed()`. Mục tiêu của `@Before`/`@AfterReturning`/`@AfterThrowing` là observation ở thời điểm được định nghĩa, không thay thế call flow.

### 6.5. Một method advice không dùng cả returning và throwing

`@AfterReturning` có `returning`, `@AfterThrowing` có `throwing`. Chúng là **hai annotations khác nhau**, với outcomes **loại trừ nhau cho cùng một execution**: method kết thúc bình thường hoặc exception thoát ra.

Không tồn tại cấu hình `@AfterReturning(returning="result", throwing="error")` theo Spring @AspectJ. Khi cần ghi cả hai nhánh, dùng **hai advice methods** hoặc `@Around` tùy mục tiêu.

## 7. Java 17+ demo đầy đủ: 6 lời gọi, 6 phép đếm advice

Demo này dùng **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, **Java 17+**, Gradle và Spring Java configuration thuần. Ví dụ kiểm chứng cùng một pointcut trên nhiều methods nhưng binding khác nhau.

Để output đáng tin, advice **chỉ tăng counters** (không in trong advice). Vì thế chương trình không phụ thuộc thứ tự thực thi của những advice cùng join point.

Mục tiêu:

- `@Before` đếm tất cả sáu method executions qua proxy.
- `@After` đếm sáu lần kết thúc theo after-finally.
- `@AfterReturning` không bind đếm bốn normal returns.
- `@AfterReturning` bind `String` đếm hai text returns.
- `@AfterThrowing` bind `IllegalArgumentException` đếm một lỗi đúng subtype.
- `@AfterThrowing` bind `Throwable` đếm hai exceptional exits.

### 7.1. Thư mục dự án

```text
spring-advice-signatures-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/advice/
    ├── Main.java
    ├── AppConfig.java
    ├── OutcomeService.java
    └── OutcomeAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-advice-signatures-demo'
```

**`build.gradle`**

```gradle
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
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.advice.Main'
}
```

Spring Framework 6.x yêu cầu Java 17+. Với Spring Boot production, để BOM/dependency management của Boot chọn các versions Spring đồng bộ thay vì dùng lại thủ công các version của demo.

### 7.2. Target bean: các outcomes tách biệt

**`OutcomeService.java`**

```java
package com.example.advice;

public class OutcomeService {
    public String find(String id) {
        return "found:" + id;
    }

    public Integer count() {
        return 3;
    }

    public void refresh() {
        System.out.println("target:refresh");
    }

    public String rejected() {
        throw new IllegalArgumentException("bad-id");
    }

    public String crashed() {
        throw new IllegalStateException("storage-down");
    }

    public String recovered() {
        try {
            throw new IllegalArgumentException("transient");
        } catch (IllegalArgumentException ex) {
            return "fallback";
        }
    }
}
```

Tất cả methods đều `public`, không final, và class không final. Do đó các case được tách theo **outcome** và **binding** chứ không bị lẫn với hạn chế CGLIB final/private.

`recovered()` minh họa một exception đã bị bắt **bên trong target**: kết quả cuối cùng của method execution là normal return `"fallback"`, vì vậy `@AfterThrowing` trên `recovered` **không** chạy.

### 7.3. Aspect: signatures khác nhau trên cùng pointcut

**`OutcomeAspect.java`**

```java
package com.example.advice;

import java.util.concurrent.atomic.AtomicInteger;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class OutcomeAspect {
    private static final String SERVICE =
            "execution(public * com.example.advice.OutcomeService.*(..))";

    private final AtomicInteger before = new AtomicInteger();
    private final AtomicInteger afterFinally = new AtomicInteger();
    private final AtomicInteger normal = new AtomicInteger();
    private final AtomicInteger textReturn = new AtomicInteger();
    private final AtomicInteger illegalArgument = new AtomicInteger();
    private final AtomicInteger anyThrowable = new AtomicInteger();

    @Before(SERVICE)
    public void beforeMethod(JoinPoint jp) {
        before.incrementAndGet();
    }

    @After(SERVICE)
    public void afterMethod() {
        afterFinally.incrementAndGet();
    }

    @AfterReturning(SERVICE)
    public void afterNormal() {
        normal.incrementAndGet();
    }

    @AfterReturning(
        pointcut = SERVICE,
        returning = "value",
        argNames = "value"
    )
    public void afterString(String value) {
        textReturn.incrementAndGet();
    }

    @AfterThrowing(
        pointcut = SERVICE,
        throwing = "failure",
        argNames = "failure"
    )
    public void afterBadArgument(IllegalArgumentException failure) {
        illegalArgument.incrementAndGet();
    }

    @AfterThrowing(
        pointcut = SERVICE,
        throwing = "error",
        argNames = "error"
    )
    public void afterAnyFailure(Throwable error) {
        anyThrowable.incrementAndGet();
    }

    public int beforeCount() { return before.get(); }
    public int afterCount() { return afterFinally.get(); }
    public int normalCount() { return normal.get(); }
    public int textCount() { return textReturn.get(); }
    public int argumentErrorCount() { return illegalArgument.get(); }
    public int throwableCount() { return anyThrowable.get(); }
}
```

Các biến counter là **instance fields trong một aspect bean**, nên dùng `AtomicInteger` để tránh mất cập nhật nếu multiple threads gọi service. Đây chỉ là instrumentation demo trong một JVM, **không** thay thế metric registry/telemetry đa instance production.

Tất cả pointcuts dùng chung chuỗi `SERVICE`, do đó sự khác nhau của counters phản ánh **event semantics** và **ràng buộc returning/throwing type**.

**Vì sao `JoinPoint jp` không xuất hiện trong `argNames` của `@Before`?** Nó là tham số đặc biệt, Spring/AspectJ cung cấp theo quy tắc advice signature. Trong ví dụ, `jp` chưa được sử dụng để in signature, nhưng việc truyền vào cho thấy một advice có thể truy cập metadata join point. Nếu code style bật compiler warning cho tham số không dùng, có thể xóa tham số và import `JoinPoint` mà không thay các phép đếm; ở bản demo giữ nguyên để minh họa chữ ký.

### 7.4. Đăng ký Spring bean và bật @AspectJ

**`AppConfig.java`**

```java
package com.example.advice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    OutcomeService outcomeService() {
        return new OutcomeService();
    }

    @Bean
    OutcomeAspect outcomeAspect() {
        return new OutcomeAspect();
    }
}
```

`@Aspect` không tự động tạo Spring bean; `@Bean` trên `AppConfig` tạo instance `OutcomeAspect` được Spring quản lý. `@EnableAspectJAutoProxy` nhận diện advice metadata và thiết lập AOP proxies cho target beans match advisor.

`proxyTargetClass=true` khiến main tra cứu `OutcomeService` bằng concrete type được. Đây là lựa chọn cho demo, không phải điều kiện để `returning`/`throwing` hoạt động; có thể dùng JDK interface proxy nếu target expose suitable interface và Spring được cấu hình tương ứng.

### 7.5. Chạy calls và kiểm chứng số lần advice

**`Main.java`**

```java
package com.example.advice;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            OutcomeService service = context.getBean(OutcomeService.class);
            OutcomeAspect aspect = context.getBean(OutcomeAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("find=" + service.find("X"));
            System.out.println("count=" + service.count());
            service.refresh();

            try {
                service.rejected();
            } catch (IllegalArgumentException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            try {
                service.crashed();
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("recovered=" + service.recovered());

            System.out.println("before=" + aspect.beforeCount());
            System.out.println("normal=" + aspect.normalCount());
            System.out.println("string=" + aspect.textCount());
            System.out.println("illegalArgument=" + aspect.argumentErrorCount());
            System.out.println("anyThrowable=" + aspect.throwableCount());
            System.out.println("afterFinally=" + aspect.afterCount());
        }
    }
}
```

Chạy với Gradle đã cài và JDK 17+:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper thì dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

**Stdout do chương trình in, theo thứ tự** (không tính log JVM/Spring/Gradle do môi trường bật):

```text
proxy=true
find=found:X
count=3
target:refresh
caught=bad-id
caught=storage-down
recovered=fallback
before=6
normal=4
string=2
illegalArgument=1
anyThrowable=2
afterFinally=6
```

### 7.6. Giải thích theo từng invocation

| Lời gọi qua Spring proxy | Outcome của target method | `@Before` | `@AfterReturning` không bind | `@AfterReturning` bind String | `@AfterThrowing` bind IllegalArgumentException | `@AfterThrowing` bind Throwable | `@After` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `find("X")` | Return `"found:X"` | 1 | 1 | 1 | 0 | 0 | 1 |
| `count()` | Return `Integer(3)` | 1 | 1 | 0 | 0 | 0 | 1 |
| `refresh()` | `void`, normal exit | 1 | 1 | 0 | 0 | 0 | 1 |
| `rejected()` | Throw `IllegalArgumentException` | 1 | 0 | 0 | 1 | 1 | 1 |
| `crashed()` | Throw `IllegalStateException` | 1 | 0 | 0 | 0 | 1 | 1 |
| `recovered()` | Catch nội bộ, return `"fallback"` | 1 | 1 | 1 | 0 | 0 | 1 |
| **Tổng** | Sáu method executions | **6** | **4** | **2** | **1** | **2** | **6** |

Đây là **các giá trị tổng sau khi tất cả lời gọi hoàn tất**, không phải số lượng object bean, số HTTP requests hay số transaction commits. Cùng một execution ném `IllegalArgumentException` có thể được **cả hai @AfterThrowing advice** quan sát vì `IllegalArgumentException` cũng là `Throwable`. Advice thứ hai không phải retry invocation của target.

Lưu ý: không khóa thứ tự giữa hai `@AfterThrowing` advices; chúng chỉ thay đổi counters độc lập nên stdout đã chọn không phụ thuộc order.

## 8. Binding thêm method argument với args(...)

Nhiều ứng dụng muốn log input và kết quả hoặc input và exception của **cùng lời gọi**. Spring @AspectJ hỗ trợ binding target args trong pointcut bằng `args(...)`.

### 8.1. Input và return value

```java
@AfterReturning(
    pointcut =
        "execution(public String com.example.advice.OutcomeService.find(..))"
        + " && args(id)",
    returning = "result",
    argNames = "id,result"
)
public void afterFind(String id, String result) {
    System.out.println("find(" + id + ")=" + result);
}
```

Đây là **đoạn minh họa** nằm trong Spring-managed `@Aspect`. `args(id)` bind target argument vào `String id`. `returning="result"` bind normal return vào `String result`. `argNames="id,result"` nói rõ tên hai advice parameters.

Với `find("X")`, nếu thêm advice này thành bean riêng hoặc tạm thay code demo để chạy độc lập, nó có thể in:

```text
find(X)=found:X
```

**Đừng thêm advice này nguyên trạng vào demo muốn giữ stdout ở mục 7.5.** Nó tạo thêm output.

Nếu method có nhiều args, có thể dùng `args(id,..)` để bind tham số đầu hoặc `args(first,second)` với method có đúng hai arguments, tùy matching mong muốn. Số lượng/kiểu Java advice parameters phải tương ứng với các tên binding.

### 8.2. Input và exception

```java
@AfterThrowing(
    pointcut =
        "execution(public String com.example.advice.OutcomeService.find(..))"
        + " && args(id)",
    throwing = "error",
    argNames = "id,error"
)
public void afterFindFailure(String id, RuntimeException error) {
    System.out.println("failed:" + id + ":" + error.getClass().getSimpleName());
}
```

Đây cũng là **minh họa**. `find(..)` trong demo không ném lỗi cho input `"X"`, nên lời advice này **không chạy** ở case đó. Nếu target được thay đổi để ném exception phù hợp, và expression match, Spring mới bind `RuntimeException error`.

Điểm chính: **returning** và **throwing** bind hai kinds of outcomes khác nhau. Muốn dùng cả hai data sources, viết hai advices có cùng `args` nhưng khác outcome annotation, hoặc dùng `@Around` khi thực sự cần một interception body xử lý cả hai đường.

## 9. Kiểu tham số binding tạo ra ràng buộc matching

### 9.1. Object, String, Number và void

```java
// Chọn các normal returns có kiểu tương thích Object.
@AfterReturning(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterObject(Object result) {
    // ...
}
```

```java
// Chọn các normal returns có kiểu tương thích String.
@AfterReturning(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterText(String result) {
    // ...
}
```

Hai đoạn riêng ở trên **không** được ghép vào demo `OutcomeAspect` nếu muốn giữ các counters. Chúng cho thấy **`String` là điều kiện chặt hơn `Object`** đối với return binding. Method `void` không có `String` value; nếu chỉ cần đếm `void` normal completion, dùng `@AfterReturning` không bind.

Với generic/covariant return types, bridge methods, `null` và target declared return type `Object` nhưng runtime value thay đổi, matching có thể có chi tiết phụ thuộc cách Spring/AspectJ kiểm tra type. **Hãy test phiên bản Spring cụ thể** trước khi dùng typed-returning advice làm policy nghiệp vụ quan trọng.

### 9.2. Throwable, Exception và RuntimeException

```java
@AfterThrowing(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterFailure(Throwable error) {
    // Có thể quan sát RuntimeException, checked Exception hoặc Error theo matching.
}
```

`Throwable` là broad type, phù hợp khi cần telemetry các exceptional exits. `Exception` không bắt các `Error` như `OutOfMemoryError`; `RuntimeException` chỉ match unchecked runtime exceptions và subclasses. `IllegalArgumentException` là một subclass cụ thể.

**Không lạm dụng catch-all metrics để nuốt errors.** Advice `@AfterThrowing` không phải nơi chữa `OutOfMemoryError` hay đưa exception fatal thành normal business outcome.

### 9.3. Null từ target

Một method:

```java
public String optionalName() {
    return null;
}
```

kết thúc **bình thường**, nên `@AfterReturning` không bind được dùng nếu pointcut match. Với returning-bound reference type, **đọc result bằng null-safe logic** vì invocation có thể tạo `null`. Không gọi `result.length()` vô điều kiện.

Nếu khái niệm cần kiểm tra là “có dữ liệu” thay vì “method hoàn tất bình thường”, nên dùng `Optional`, business result object hoặc policy trong service; không gán mặc định `@AfterReturning` bằng nghiệp vụ thành công.

### 9.4. Future và reactive return

Spring @AspectJ advice nhìn vào **method execution được proxy**. Với `CompletableFuture<T>` hoặc `Mono<T>`, target có thể **trả future/publisher wrapper bình thường** ngay cả khi tác vụ/subscription sau đó lỗi.

Khi ấy:

- `@AfterReturning(returning="value")` bind **future/publisher object** (nếu parameter type match), không tự bind `T` sau khi computation hoàn tất.
- `@AfterThrowing` trên method proxy **không tự chạy** cho lỗi bất đồng bộ phát sinh sau khi method đã trả wrapper thành công.
- Nếu cần completion semantics, dùng completion callback như `whenComplete` cho future hoặc Reactor operators/instrumentation phù hợp; đừng đồng nhất wrapper return với eventual result.

## 10. Chữ ký quyết định dữ liệu được bind, không quyết định quyền thay outcome

| Advice signature | Điều Spring có thể cung cấp |
| --- | --- |
| void onReturn(String value), returning=value | Normal result tương thích String; không đổi reference trả caller |
| void onFailure(IOException error), throwing=error | Exception tương thích IOException; không trả fallback |
| Object around(ProceedingJoinPoint pjp) throws Throwable | Có quyền proceed rồi trả kết quả hoặc ném lỗi phù hợp contract |

Phần phân tích object identity, mutable state và replacement thuộc bài riêng về @AfterReturning; phần phục hồi exception thuộc bài riêng về @AfterThrowing. Thay return type của advice thông thường thành String hoặc Object không biến nó thành @Around.

## 11. Tách lỗi tên binding khỏi lỗi type matching

Với returning=result, argNames=result và advice method nhận String result, cả ba phải nhất quán. Nếu chỉ sửa argNames thành value, việc ánh xạ sai tên dù pointcut đúng; đây có thể là lỗi tạo advisor/binding.

Tương tự, throwing=failure với Throwable failure nhận loại exception rộng, còn IOException failure chỉ nhận IOException hoặc subtype. Khi test nên tách ba điều kiện: đúng target/pointcut, đúng tên tham số và đúng return/exception type. Trong một lời gọi ném lỗi, returning advice không chạy dù tham số return có kiểu hợp lệ.

## 12. Bài toán JoinPoint và binding annotation

Spring @AspectJ cũng hỗ trợ bind annotation, receiver/target và method args.

### 12.1. Advice chỉ cần tên method

```java
@Before("execution(public * com.example.advice.OutcomeService.*(..))")
public void before(JoinPoint jp) {
    String name = jp.getSignature().getName();
    System.out.println("enter:" + name);
}
```

Một `JoinPoint` đầu tiên là hợp lệ đối với non-around advice. Không dùng `ProceedingJoinPoint` ở đây vì `@Before` không điều khiển tiến trình `proceed()`.

### 12.2. Advice cần annotation của target method

Giả sử có annotation:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditedOperation {
    String category();
}
```

Đoạn minh họa cần Java imports `ElementType`, `Retention`, `RetentionPolicy`, `Target` và được đặt ở package thích hợp.

Binding:

```java
@Before(
    value = "@annotation(marker)",
    argNames = "marker"
)
public void beforeAudited(AuditedOperation marker) {
    System.out.println(marker.category());
}
```

Advice nhận `AuditedOperation` từ annotation trên method. `argNames` khớp tham số `marker`. Đây **không phải** `returning`/`throwing`, nhưng cùng mô hình binding theo tên/type của Spring @AspectJ. Đừng trộn annotation trên class (`@within`/`@target`) với annotation trên method (`@annotation`) nếu pointcut yêu cầu khác.

### 12.3. Khi nào cần argNames?

Spring có cơ chế khám phá argument names từ:

- Annotation `argNames` trên advice/`@Pointcut` khi được khai báo explicit.
- Java parameter name metadata nếu build giữ lại thông tin thích hợp.
- Các quy tắc suy luận binding của Spring @AspectJ trong một số trường hợp.

Để README/demo độc lập, `argNames` giúp code ít phụ thuộc build flags. Nhưng `argNames` không **cứu** một pointcut sai cú pháp hoặc type mismatch. Khi có nhiều parameters, thứ tự names phải tương ứng các parameters bind của advice.

Spring đặc biệt nhận diện `JoinPoint` tham số đầu tiên mà không cần kể tên nó trong `argNames`. Với `@Around`, `ProceedingJoinPoint` là tham số đầu tiên tương ứng.

## 13. Nhiều advice trên cùng một target: thứ tự và ngoại lệ

Một service method có thể đồng thời được:

- Spring-managed custom aspects audit/metrics;
- Transaction/cache/security proxy interceptors;
- Hai hay nhiều advice thuộc một `@Aspect`;
- `@Around` từ các frameworks khác.

**Advice ordering có thể ảnh hưởng loại outcome mà một advisor nhìn thấy.** `@Order`/`Ordered` giúp xác định precedence giữa các aspects, nhưng không nên suy rằng thứ tự khai báo code trong file luôn là thứ tự chạy giữa hai advice cùng loại.

Spring docs lưu ý:

- Cùng một join point, precedence quyết định thứ tự “vào” và “ra”.
- `@After` có nghĩa after-finally; nó có thể chạy sau `@AfterReturning`/`@AfterThrowing` theo semantics cleanup.
- Hai advice **cùng loại trong cùng aspect** không được đảm bảo có thứ tự cố định chỉ dựa theo vị trí source.
- `@AfterThrowing` của một aspect không phải callback bắt exception do `@AfterReturning`/`@After` đồng hành ném ra.

Ví dụ demo cố tình dùng **counters, không in log bên trong advice** để tránh khóa thứ tự giữa hai `@AfterThrowing` advice. Khi cần sequence chính xác để đáp ứng business policy, tách aspects có precedence rõ ràng hoặc sử dụng một advice body có điều khiển minh bạch, kèm integration test.

## 14. Spring Boot: điểm giống và điều cần kiểm tra

Với Spring Boot AOP auto-configuration khi dependencies phù hợp, thường không cần tự thêm `@EnableAspectJAutoProxy`. Nhưng quy tắc chữ ký advice **không thay đổi**:

1. Aspect có `@Aspect` **và** phải được Spring đăng ký làm bean qua `@Component` (nằm trong component scan) hoặc `@Bean`.
2. Target service là Spring-managed bean.
3. Advice annotations và `returning`/`throwing` names trùng advice parameters.
4. Type binding khớp normal return hoặc thrown exception.
5. Caller thực sự dùng Spring proxy; không dùng `new` hoặc self-invocation `this.method()`.
6. Spring Boot proxy configuration/JDK vs CGLIB không làm final methods trở nên interceptable khi dùng CGLIB.

Ví dụ dependencies theo Boot major (giả sử project dùng dependency management của Boot):

```gradle
// Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

Đây là **hai lựa chọn theo major version**, không chép cả hai vào cùng project. Boot 3/4 có thể khác nhau về API chuyển tiếp, nhưng `@AfterReturning` và `@AfterThrowing` vẫn thuộc `org.aspectj.lang.annotation` trong Spring @AspectJ support.

Nếu Boot đặt `spring.aop.proxy-target-class=true`, Spring thường dùng class proxy; cần kiểm tra method/class `final`, package scan và cấu hình AOP tổng hợp.

## 15. Lỗi phổ biến về chữ ký advice và binding

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Startup lỗi khi thêm `returning` | String `returning` không match tên tham số advice, hoặc `argNames` sai | Dùng tên giống nhau và types hợp lệ. |
| Startup lỗi khi thêm `throwing` | Không có parameter name được bind, hoặc annotation/pointcut sai | `throwing="error"` và `Throwable error`/subtype phù hợp. |
| `@AfterReturning` không bind vẫn chạy, bản bind `String` không chạy | Target trả kiểu khác `String`, `void` hoặc có mismatch | Kiểm tra declared/actual result types, dùng type chủ đích và integration test. |
| Advice `@AfterThrowing(IllegalArgumentException)` không chạy trên `IllegalStateException` | Kiểu exception không tương thích | Dùng subtype matching đúng yêu cầu, hoặc `RuntimeException`/`Throwable` rộng hơn. |
| Method ném lỗi nội bộ nhưng `@AfterThrowing` không chạy | Target bắt lỗi trước khi thoát join point | Quan sát outcome cuối cùng; nếu return fallback thì đó là normal return. |
| Một method có hai exception advices chạy | `IllegalArgumentException` cũng là `Throwable` | Không gọi là advice bị lặp; đó là hai advisors/bindings hợp lệ. |
| `@AfterReturning` không đổi kết quả dù advice trả/assign chuỗi khác | Advice này không thay returned reference | Dùng `@Around` hoặc sửa business method nếu cần đổi kết quả. |
| `@AfterThrowing` chỉ log nhưng exception vẫn được caller nhận | Đây là semantics đúng | Nếu cần recovery, dùng explicit handler hoặc `@Around` với contract đúng. |
| Advice chỉ thấy future/publisher thay vì data cuối cùng | Interception ở lúc method trả wrapper, không phải async completion | Theo dõi completion/reactive signal bằng API tương ứng. |
| `JoinPoint` đứng sai vị trí hoặc `argNames` sai thứ tự | Binding không phù hợp convention | Đưa `JoinPoint` đầu tiên; đặt names cho các biến binding còn lại. |
| `ProceedingJoinPoint` dùng trên `@Before` | `proceed()` là quyền của `@Around` | Đổi sang `JoinPoint` hoặc thực sự dùng `@Around`. |
| Có aspect bean nhưng advice không được gọi | AOP chưa bật, pointcut không match, target không qua proxy hoặc final/private | Kiểm tra bean/proxy/method boundary và actual outcome. |
| Advice trên phương thức inner không chạy từ outer | `this.inner()` bỏ qua proxy | Tách sang collaborator bean có injected proxy nếu thật sự cần interception. |
| Transaction rollback/commit không như kỳ vọng | Advice order và exception handling tác động chain | Test transaction với config thực; không suy từ normal-return log. |
| Advice tự ném exception và business call bắt đầu fail | Lỗi trong advice đi qua proxy tới caller | Thiết kế error policy cho telemetry/audit rõ ràng, tránh nuốt/đổi outcome bất ngờ. |

## 16. Một quy trình kiểm thử Spring AOP có ý nghĩa

### 16.1. Cấu hình context thật

Viết integration test sử dụng `AnnotationConfigApplicationContext`, Spring Test `@SpringJUnitConfig` hoặc `@SpringBootTest` đúng với project. Unit test gọi trực tiếp `new OutcomeAspect().afterString(...)` **không chứng minh Spring binding hoạt động**.

### 16.2. Kiểm tra proxy trước

```java
OutcomeService service = context.getBean(OutcomeService.class);
System.out.println(AopUtils.isAopProxy(service));
```

Trong demo kết quả `true`. Nhưng **proxy true không bảo đảm mọi advice method match**. Tiếp tục kiểm tra event/counters riêng cho các outcomes.

### 16.3. Kiểm chứng tất cả nhánh

- Normal String return → `afterNormal` và `afterString`.
- Normal Integer return → `afterNormal`, không có `afterString`.
- Normal void completion → `afterNormal`, không có `afterString`.
- IllegalArgumentException → `afterBadArgument` và `afterAnyFailure`.
- IllegalStateException → chỉ `afterAnyFailure`.
- Exception bị catch trong target rồi return fallback → normal-return advice, **không** exceptional advice.
- External Spring proxy call vs `new`/`this` internal call → xác nhận boundary.

### 16.4. Tự viết assertion không phụ thuộc stdout advice

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    OutcomeService service = context.getBean(OutcomeService.class);
    OutcomeAspect aspect = context.getBean(OutcomeAspect.class);

    service.find("X");
    service.count();
    service.refresh();
    try { service.rejected(); } catch (IllegalArgumentException ignored) {}
    try { service.crashed(); } catch (IllegalStateException ignored) {}
    service.recovered();

    if (aspect.beforeCount() != 6
            || aspect.normalCount() != 4
            || aspect.textCount() != 2
            || aspect.argumentErrorCount() != 1
            || aspect.throwableCount() != 2
            || aspect.afterCount() != 6) {
        throw new AssertionError("Advice binding or outcome counts differ");
    }
}
```

Đoạn này dùng các class của demo và cần import `AnnotationConfigApplicationContext`; nó chạy **trên một context mới**, không ghép vào `Main` nếu muốn giữ output mẫu. Trong project thực tế có thể thay `if` bằng JUnit assertions.

### 16.5. Đối với dữ liệu nhạy cảm và concurrency

- Đừng log toàn bộ `JoinPoint.getArgs()` hoặc result DTO chứa token, password, thông tin thanh toán.
- Aspect mặc định thường là singleton Spring bean, nên field mutable phải thread-safe hoặc tốt hơn là stateless.
- `AtomicInteger` chỉ bảo vệ một phép đếm; nó không bảo vệ một tập hợp nhiều fields cập nhật cùng nhau.
- Nếu advice gọi IO/remote service, cần timeout/error policy và quan sát performance tác động lên method call.
- Với `@AfterThrowing`, đừng bắt tất cả `Throwable` rồi dùng nó để quyết định “lỗi nào nên nuốt”. Binding quan sát không phải recovery policy.

## 17. Checklist cuối cùng

- [ ] Đã xác định rõ **chữ ký của target method** và **chữ ký của advice method** là hai thứ khác nhau?
- [ ] Aspect có `@Aspect` và được Spring đăng ký bean qua `@Component` hoặc `@Bean`?
- [ ] Hạ tầng Spring AOP @AspectJ và AspectJ Weaver được cấu hình đúng?
- [ ] `@Before`/`@After`/`@AfterReturning`/`@AfterThrowing` thường khai báo `void`?
- [ ] `@Around` có `ProceedingJoinPoint` đầu tiên, gọi `proceed()` phù hợp, return `Object` hoặc kiểu hợp lệ?
- [ ] Nếu dùng `@AfterReturning(returning="value")`, có tham số advice tương ứng `value`?
- [ ] Nếu dùng `@AfterThrowing(throwing="error")`, có tham số exception tương ứng `error`?
- [ ] Kiểu tham số `String`/`Throwable`/subtype có đúng tập outcomes cần match?
- [ ] Nếu dùng `argNames`, tên/thứ tự tương thích với các binding parameters và quy tắc đặc biệt của `JoinPoint`?
- [ ] Đã phân biệt normal return, caught exception, thrown exception, `void`, `null` và async-wrapper return?
- [ ] Không dùng `@AfterReturning` để thay returned reference hoặc `@AfterThrowing` để nuốt exception?
- [ ] Target thực sự đi qua Spring proxy; method proxy intercept được, không phải self-invocation?
- [ ] Nếu có nhiều advice, không phụ thuộc ordering ngẫu nhiên của hai advices cùng loại?
- [ ] Integration test xác nhận return bindings và exception bindings trên actual Spring-managed calls?
- [ ] Telemetry/advice có null-safety, privacy và error policy rõ ràng?

**Điểm nhớ:** Trong Spring AOP, `returning` của `@AfterReturning` và `throwing` của `@AfterThrowing` **phải trỏ đúng tham số của method advice**. Java type của tham số **lọc kết quả/exception được match**, còn `argNames` giúp Spring xác định binding tường minh. `JoinPoint` cung cấp metadata, `ProceedingJoinPoint` dành cho `@Around`. Mọi advice chỉ phát huy tác dụng khi **Spring bean, proxy và pointcut** đúng, và việc quan sát outcome không tự cho phép thay kết quả hoặc xử lý lỗi.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Declaring Advice: @AfterReturning, @AfterThrowing, @Around, advice parameters và ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Proxying Mechanisms / self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Advice API (phân biệt @AspectJ và chương trình hóa advisors)](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/advice.html)
