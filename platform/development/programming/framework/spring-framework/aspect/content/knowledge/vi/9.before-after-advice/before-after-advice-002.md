# @AfterReturning và ràng buộc kết quả trả về trong Spring AOP

## 1. Mục tiêu và phạm vi

Trong **Spring AOP với cú pháp @AspectJ**, `@AfterReturning` là advice thực thi **sau khi một method execution được pointcut chọn kết thúc bình thường** và quyền điều khiển chuẩn bị trở về caller. Advice có thể chỉ ghi nhận sự kiện, hoặc nhận chính giá trị trả về bằng thuộc tính `returning`.

Ví dụ thực tế: ghi nhận một kết quả tra cứu thành công, cập nhật metric của service call hoàn tất, hoặc quan sát dữ liệu trả về khi một Spring service được gọi **qua AOP proxy**.

Điểm quan trọng của bài không chỉ là thời điểm advice chạy mà còn là:

1. **Khi nào được xem là “return normally”?** Method trả về bình thường (kể cả `null` và method `void` nếu biểu thức/điều kiện advice phù hợp), không phải method thoát ra bằng exception.
2. **Cách viết `@AfterReturning(pointcut = "...", returning = "result")`:** tên `result` phải tương ứng với tham số advice; kiểu tham số trở thành điều kiện giới hạn matching.
3. **`@AfterReturning` có đổi được kết quả về caller không?** Nó không thay thế reference/value trả về. Muốn chủ động đổi kết quả phải thiết kế `@Around` hoặc logic nghiệp vụ khác.
4. **Điều kiện của Spring:** aspect và target phải được container quản lý, có hạ tầng auto-proxy, pointcut match và caller phải đi qua proxy. Tên annotation đúng mà gọi `this.method()` thì vẫn có thể bỏ qua advice.

Bài tập trung vào **Spring Aspect/Spring AOP**: Java configuration, Spring bean, proxy boundary, cách bind return value và những lỗi thường gặp. Không ôn lại AOP tổng quát hoặc chuyển sang AspectJ bytecode weaving.

## 2. Thời điểm @AfterReturning chạy

Một đường gọi đơn giản khi Spring AOP áp advisor:

```text
Consumer / Controller / Service khác
         |
         | service.lookup("A")
         v
Spring AOP proxy
         |
         +-- Pointcut match method?
         |       |
         |       +-- Có: invocation đi qua interceptor chain
         |
         v
Target bean: ResultService.lookup("A")
         |
         +-- Nếu RETURN bình thường
         |        |
         |        +-- @AfterReturning advice được gọi nếu điều kiện return binding hợp lệ
         |        |
         |        +-- Giá trị ban đầu tiếp tục trở về caller
         |
         +-- Nếu THROW exception
                  |
                  +-- @AfterReturning KHÔNG chạy cho lần thoát bằng lỗi ấy
                  |
                  +-- Exception tiếp tục qua proxy/interceptor chain

Lưu ý: Các advice khác trong chain có thể thay đổi thứ tự và outcome.
```

Đây là sơ đồ **khái quát** cho invocation phù hợp; với nhiều advisors, `@Around`, transaction hoặc asynchronous execution, thời điểm caller quan sát kết quả còn phụ thuộc interceptor chain. Spring docs định nghĩa `@AfterReturning` bằng **normal return của join point**, chứ không khẳng định giao dịch dữ liệu đã commit hoặc một tác vụ bất đồng bộ đã kết thúc.

### 2.1. So sánh ngắn các loại advice Spring liên quan

| Annotation | Khi target method execution đã đi qua proxy | Có nhận return value trực tiếp? |
| --- | --- | --- |
| `@Before` | Trước lời gọi target khi pointcut match | Không, vì target chưa trả về. |
| `@AfterReturning` | Sau khi method hoàn tất bình thường | Có, bằng `returning`. |
| `@AfterThrowing` | Khi method ném exception ra ngoài join point | Có thể bind exception bằng `throwing`, không phải normal return value. |
| `@After` | Theo nghĩa after-finally: khi join point thoát bình thường **hoặc** bất thường | Không dùng `returning` để bind kết quả. |
| `@Around` | Bao quanh invocation; có thể dùng `ProceedingJoinPoint.proceed()` | Có thể quan sát và quyết định giá trị trả về caller khi thiết kế đúng. |

**Hai nhầm lẫn cần tránh:**

- `@AfterReturning` **không** có nghĩa “luôn chạy ở cuối method”, vì method ném exception thì advice này không chạy.
- `@After` **không** phải tên khác của `@AfterReturning`: `@After` có semantics tương tự `finally`.

## 3. Cấu hình tối thiểu trong Spring Framework

Annotation đến từ AspectJ annotations API:

```java
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.AfterReturning;
```

Class aspect phải được Spring đăng ký. Ví dụ **phần cấu hình minh họa**, chưa phải project chạy độc lập:

```java
@Aspect
@Component
public class ResultAuditAspect {
    @AfterReturning(
        "execution(public * com.example.orders..*Service.*(..))"
    )
    public void afterNormalReturn() {
        System.out.println("service completed normally");
    }
}
```

```java
@Configuration
@ComponentScan("com.example.orders")
@EnableAspectJAutoProxy
public class AopConfiguration {
}
```

Điều kiện để advice thật sự chạy:

- `@Aspect` khai báo class chứa advice; `@Component` (nằm trong package scan) **hoặc** một `@Bean` factory method đăng ký class đó làm Spring bean.
- `@EnableAspectJAutoProxy` trong Spring Framework Java configuration kích hoạt auto-proxy cho các `@Aspect` bean; thường cần `aspectjweaver` tương thích trên classpath.
- Một method **thuộc Spring-managed target bean** và match `execution(...)` phải được gọi **qua Spring proxy**.
- Với JDK dynamic proxy, caller gọi method được expose trên interface; với class-based proxy, class/method phải proxy được (`final` có giới hạn).
- Code gọi `new Service()` hoặc `this.method()` bên trong target không được Spring AOP intercept theo cách thông thường.

Spring Boot có auto-configuration AOP khi ứng dụng mang dependency phù hợp; điều đó không thay yêu cầu `@Aspect` là Spring bean. Không cần tự bật weaving agent chỉ để dùng `@AfterReturning` theo Spring AOP proxy.

## 4. Cú pháp 1 — không bind kết quả

Dạng gọn nhất:

```java
@AfterReturning(
    "execution(public * com.example.orders..*Service.*(..))"
)
public void afterSuccessfulServiceMethod() {
    // Ghi nhận một lời gọi service kết thúc bình thường.
}
```

Ở đây:

- `@AfterReturning` dùng một biểu thức pointcut theo thuộc tính `value` của annotation.
- Method advice `afterSuccessfulServiceMethod()` **không nhận result**, nên không thể dựa vào chữ ký tham số để ràng buộc kiểu giá trị trả về.
- Method có return type `String`, `int`, object hoặc `void` có thể được chọn nếu **pointcut match method execution** và execution thoát bình thường.
- Một method có lời gọi target thất bại bằng exception sẽ không chạy lời advice này.
- Advice có return type `void` là lựa chọn tự nhiên vì bản thân nó không biến đổi kết quả của target.

Ví dụ `@AfterReturning` không bind phù hợp với metric `successfulMethodReturns++`. Tuy nhiên “method trả bình thường” **không đồng nghĩa** “business transaction thành công”, “HTTP response 2xx” hoặc “database commit chắc chắn thành công”.

## 5. Cú pháp 2 — ràng buộc return value bằng thuộc tính returning

Muốn nhận giá trị mà method trả về:

```java
@AfterReturning(
    pointcut = "execution(public * com.example.orders..*Service.*(..))",
    returning = "result"
)
public void afterReturningValue(Object result) {
    System.out.println("result=" + result);
}
```

**Tên `result` trong `returning = "result"` phải khớp với tên tham số advice** `Object result`. Spring/AspectJ binding đưa giá trị đã trả về vào tham số này. Bài học chính là: `returning` **không phải tên field**, không phải tên biến trong method đích và không phải chuỗi bất kỳ.

Khi muốn chắc việc ánh xạ tham số hoạt động với cấu hình biên dịch/metadata khác nhau, có thể khai báo `argNames`:

```java
@AfterReturning(
    pointcut = "execution(public * com.example.orders..*Service.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterReturningValue(Object result) {
    // Đọc giá trị result nhận từ method return bình thường.
}
```

`argNames` thuộc annotation `@AfterReturning`, được Spring dùng khi xác định tên tham số binding. Nó đặc biệt hữu ích khi xây code Java không giữ parameter names trong bytecode hoặc advice bind nhiều biến. Trong các ví dụ đơn giản Spring có thể suy luận tên, nhưng đừng phụ thuộc vào một cấu hình compiler ngầm định trong bài học/bộ test chuẩn.

### 5.1. Trường hợp returning không trùng tên

```java
// Sai ý nghĩa binding: returning="value" nhưng advice chỉ khai báo "data".
@AfterReturning(
    pointcut = "execution(* com.example.orders..*Service.*(..))",
    returning = "value",
    argNames = "data"
)
public void wrongBinding(Object data) {
}
```

Đây là **đoạn minh họa lỗi**, không chép vào một Spring context cần chạy thành công. Trong cấu hình thực tế, advisor có thể không được khởi tạo vì pointcut/binding không hợp lệ. **Cách sửa** là thống nhất tên: `returning="data"`, `argNames="data"` và tham số `Object data`, hoặc đổi toàn bộ sang `value`.

### 5.2. returning đồng thời là bộ lọc kiểu

**Điểm rất quan trọng:** kiểu khai báo của tham số advice không chỉ phục vụ đọc giá trị; nó còn **giới hạn tập method executions phù hợp với advice**.

```java
@AfterReturning(
    pointcut = "execution(public * com.example.orders..*Service.*(..))",
    returning = "text",
    argNames = "text"
)
public void afterText(String text) {
    // Chỉ những lần return có kiểu tương thích với String mới được binding.
}
```

Nếu cùng biểu thức `execution(public * ...)` bao phủ các method trả `String` và `Integer`:

- Advice với tham số `String text` được dùng cho kết quả tương thích `String`, không được coi là “mọi method trong package”.
- Advice với tham số `Object result` rộng hơn: có thể nhận nhiều kết quả reference và những primitive value được boxing khi phù hợp.
- `void` method **không có giá trị result để bind theo `String`**; nếu muốn đếm method `void` hoàn tất bình thường, dùng advice **không bind return**.

Spring docs mô tả rõ: thêm `returning` làm advice chỉ match những method executions trả giá trị của kiểu đã nêu trong tham số advice. Điều này dễ gây hiểu nhầm khi cùng pointcut có hai advice mà một advice đếm ít lần hơn advice còn lại.

### 5.3. Kết quả là null thì sao?

`null` **không phải exception**: một method trả `null` vẫn hoàn tất bình thường. Nếu dùng advice **không bind result**, nó vẫn có thể chạy theo pointcut. Nếu dùng returning-bound advice với kiểu reference, code nên **xử lý null**:

```java
@AfterReturning(
    pointcut = "execution(public java.lang.String com.example.orders..*Service.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterString(String result) {
    if (result == null) {
        System.out.println("returned:null");
        return;
    }
    System.out.println("returned:length=" + result.length());
}
```

Đây là đoạn minh họa, không phải project độc lập. Với typed binding, việc advisor được chọn còn phụ thuộc vào kiểu trả về được khai báo/được match theo Spring AOP. **Không** dùng `result.length()` trực tiếp mà thiếu null-check chỉ vì phương thức khai báo trả `String`. Nếu method có generic bridge/covariant return hoặc `Object` return type nhưng giá trị thực thay đổi, cần integration test trên đúng Spring version thay vì tự suy luận từ signature.

## 6. Demo chạy được: không bind và bind String cùng một pointcut

Demo Java 17+ dưới đây cho thấy:

1. `@AfterReturning` **không bind** đếm các normal returns của nhiều method types.
2. `@AfterReturning(returning="result")` với tham số `String result` chỉ đếm kiểu kết quả phù hợp.
3. Một method `void` hoàn tất bình thường được tính bởi advice không bind.
4. Method ném exception **không được tính** bởi `@AfterReturning`.
5. `@AfterReturning` không thay đổi giá trị mà caller nhìn thấy.

Môi trường: **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, **Java 17+**, Gradle. Dùng Spring Framework thuần để minh bạch role của `@EnableAspectJAutoProxy`.

### 6.1. Cấu trúc dự án

```text
spring-after-returning-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/returning/
    ├── Main.java
    ├── AppConfig.java
    ├── ResultService.java
    └── ReturnAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-after-returning-demo'
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
    mainClass = 'com.example.returning.Main'
}
```

Spring Framework 6.x yêu cầu Java 17 hoặc mới hơn. `spring-context` mang hạ tầng tạo container; `spring-aop` và `aspectjweaver` hỗ trợ Spring @AspectJ proxy-based configuration. Khi chuyển sang Spring Boot, dùng dependency management của đúng Boot major version.

### 6.2. Target Spring service với nhiều kiểu outcome

**`ResultService.java`**

```java
package com.example.returning;

public class ResultService {
    public String lookup(String id) {
        return "found:" + id;
    }

    public Integer available() {
        return 7;
    }

    public void warmUp() {
        System.out.println("target:warmUp");
    }

    public String fail() {
        throw new IllegalStateException("missing");
    }
}
```

Bốn method đều public/non-final và class không final. Vì vậy, tình huống này **không bị lẫn với lỗi CGLIB final/private**. Method `fail()` khai báo trả `String` nhưng thực tế ném exception; normal-return advice không chạy cho invocation đó.

### 6.3. Một aspect, hai @AfterReturning advices

**`ReturnAspect.java`**

```java
package com.example.returning;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ReturnAspect {
    private final AtomicInteger normalReturns = new AtomicInteger();
    private final AtomicInteger stringReturns = new AtomicInteger();

    @AfterReturning(
        "execution(public * com.example.returning.ResultService.*(..))"
    )
    public void afterAnyNormalReturn() {
        normalReturns.incrementAndGet();
    }

    @AfterReturning(
        pointcut = "execution(public * com.example.returning.ResultService.*(..))",
        returning = "result",
        argNames = "result"
    )
    public void afterStringReturn(String result) {
        stringReturns.incrementAndGet();
    }

    public int normalCount() {
        return normalReturns.get();
    }

    public int stringCount() {
        return stringReturns.get();
    }
}
```

Các đếm `AtomicInteger` dùng cho demo; không phải hệ thống metrics production. Advice không in log nên output **không phụ thuộc thứ tự chạy giữa hai advices**. Spring không hứa thứ tự cố định giữa nhiều advice cùng loại trong cùng aspect nếu không có thứ tự được khai báo/áp dụng thích hợp.

**Logic các counters:**

- `lookup("A")`: trả `String` bình thường → `normalReturns` và `stringReturns` cùng tăng.
- `available()`: trả `Integer` bình thường → `normalReturns` tăng; `stringReturns` không tăng vì binding kiểu `String` không tương thích.
- `warmUp()`: `void` hoàn tất bình thường → advice **không bind** tăng `normalReturns`; advice bind `String` không tăng.
- `fail()`: ném `IllegalStateException` → không có normal return; cả hai `@AfterReturning` advices không tăng.

### 6.4. Cấu hình Spring AOP

**`AppConfig.java`**

```java
package com.example.returning;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    ResultService resultService() {
        return new ResultService();
    }

    @Bean
    ReturnAspect returnAspect() {
        return new ReturnAspect();
    }
}
```

`ResultService` là Spring-managed target qua `@Bean`; `ReturnAspect` là Spring-managed `@Aspect` bean, cũng qua `@Bean`. `@EnableAspectJAutoProxy(proxyTargetClass=true)` bật advisor scanning và class proxy. Không cần `@ComponentScan` vì đã khai báo đủ bean cần thiết.

### 6.5. Bootstrap và in số lần advice thực thi

**`Main.java`**

```java
package com.example.returning;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            ResultService service = context.getBean(ResultService.class);
            ReturnAspect aspect = context.getBean(ReturnAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("lookup=" + service.lookup("A"));
            System.out.println("available=" + service.available());
            service.warmUp();

            try {
                service.fail();
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("normalReturns=" + aspect.normalCount());
            System.out.println("stringReturns=" + aspect.stringCount());
        }
    }
}
```

Chạy ở thư mục project sau khi cài JDK 17+ và Gradle:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper: `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

**Các dòng `System.out` của chương trình theo thứ tự** (không tính logging riêng của JVM/Spring/Gradle):

```text
proxy=true
lookup=found:A
available=7
target:warmUp
caught=missing
normalReturns=3
stringReturns=1
```

### 6.6. Tại sao hai counters khác nhau?

**Cùng pointcut** `execution(public * com.example.returning.ResultService.*(..))` được dùng cho cả hai advice. Nhưng:

| Lần gọi target | Outcome | Advice không bind | Advice bind `String` |
| --- | --- | --- | --- |
| `lookup("A")` | `String`, normal return | Có | Có |
| `available()` | `Integer`, normal return | Có | Không |
| `warmUp()` | `void`, normal return | Có | Không |
| `fail()` | Exception thoát khỏi method | Không | Không |

Sau các lời gọi, `normalReturns=3` và `stringReturns=1`. **Không phải advisor của `String` lỗi**; chính kiểu tham số trong returning-bound advice thu hẹp matching.

Các giá trị returned từ target được giữ nguyên: `lookup=found:A`, `available=7`. `@AfterReturning` ở ví dụ chỉ quan sát và tăng counters, không sửa return value.

Nếu không thấy dòng tương ứng trong ứng dụng thực, kiểm tra trước Spring proxy và bean registration, sau đó mới xem xét `returning` name/type.

## 7. Kết hợp return binding và method argument binding

Với Spring @AspectJ, có thể cần biết **tham số vào** và **kết quả ra** của một lời gọi service. Sử dụng `args(...)` bên trong pointcut và `returning` để bind cả hai.

Ví dụ **minh họa độc lập**, không thêm vào project demo mục 6 nếu muốn giữ nguyên counters/stdout:

```java
@Aspect
public class LookupAuditAspect {
    @AfterReturning(
        pointcut =
            "execution(public java.lang.String com.example.returning.ResultService.lookup(..))"
            + " && args(id)",
        returning = "result",
        argNames = "id,result"
    )
    public void afterLookup(String id, String result) {
        System.out.println("lookup:" + id + "=" + result);
    }
}
```

Ở đây:

- `args(id)` bind tham số đầu vào của method được chọn vào `String id`.
- `returning="result"` bind kết quả trả về vào `String result`.
- `argNames="id,result"` làm thứ tự và tên các binding rõ ràng; nếu thêm tham số `JoinPoint`, cần xem quy tắc tên tham số theo tài liệu Spring.
- Kiểu tham số `String id` còn giúp ràng buộc argument type; method với chữ ký không tương thích sẽ không match.
- `ResultService.lookup("A")` của demo trả `"found:A"`, vì vậy nếu aspect này **được đăng ký thay thế/thêm độc lập trong context phù hợp**, nó in:

```text
lookup:A=found:A
```

Đoạn này chưa là file Java chạy độc lập: cần package, imports, `@Bean`/`@Component` đăng ký aspect, và target/result service trong context.

**Không lưu raw password/token/thông tin nhạy cảm** vào log chỉ vì `args` và `returning` cho phép truy cập. Cần policy che giấu dữ liệu và tránh logging quá nhiều trong hot path.

### 7.1. Khi dùng JoinPoint

Advice có thể khai báo `JoinPoint` để đọc chữ ký method cùng result:

```java
@AfterReturning(
    pointcut = "execution(public java.lang.String com.example.returning.ResultService.lookup(..))",
    returning = "result",
    argNames = "result"
)
public void afterLookup(JoinPoint joinPoint, String result) {
    System.out.println(joinPoint.getSignature().getName() + "=" + result);
}
```

Đây là **đoạn minh họa**, cần import `org.aspectj.lang.JoinPoint` và đặt trong class `@Aspect` được Spring quản lý. Tham số `JoinPoint` đứng đầu có cách bind đặc biệt trong `@AspectJ`. Chỉ sử dụng nó khi cần metadata; nếu chỉ quan sát kiểu result, method advice đơn giản hơn sẽ dễ test.

## 8. @AfterReturning có thay đổi return value của target không?

**Không thể dùng return value của chính advice để thay thế reference/value mà target method đã trả.**

Ví dụ **sai kỳ vọng**:

```java
@AfterReturning(
    pointcut = "execution(public java.lang.String com.example.returning.ResultService.lookup(..))",
    returning = "result",
    argNames = "result"
)
public String tryReplace(String result) {
    return "other:" + result;
}
```

Đây là đoạn **minh họa anti-pattern**, không đưa vào context demo như một cách sửa kết quả. Một advice `@AfterReturning` thông thường cần `void`; dù bạn viết logic tính một chuỗi khác trong body, nó **không biến chuỗi đó thành giá trị mà caller nhận được**. Spring docs nói rõ `@AfterReturning` không thể trả một reference hoàn toàn khác để thay đổi kết quả đã được target chọn.

Ngay cả khi đổi local parameter:

```java
@AfterReturning(
    pointcut = "execution(public java.lang.String com.example.returning.ResultService.lookup(..))",
    returning = "result",
    argNames = "result"
)
public void assignLocally(String result) {
    result = "replacement"; // Chỉ đổi biến local của advice!
}
```

Caller vẫn nhận chuỗi đã được target trả về. Java assignment tới biến local `result` không thay reference mà interceptor chain đang giữ.

### 8.1. Với object mutable: phân biệt quan sát và mutate

Nếu target trả một object mutable và `@AfterReturning` bind object ấy:

```java
@AfterReturning(
    pointcut = "execution(* com.example.orders..*Service.load(..))",
    returning = "result",
    argNames = "result"
)
public void observe(AccountDto result) {
    // Có thể đọc fields của result, nhưng không nên âm thầm sửa DTO.
}
```

Đoạn này **chỉ là minh họa**, giả sử `AccountDto` có thật. Nếu code cố mutate `result` bằng setters, vì nhiều references có thể cùng trỏ tới object, caller **có thể thấy nội dung object bị thay đổi**. Điều đó khác với thay thế reference trả về; nó là side effect trên shared object và có thể gây lỗi khó kiểm soát.

**Khuyến nghị Spring:** dùng `@AfterReturning` cho quan sát/audit/metric sau normal return; nếu nghiệp vụ cần transform result có chủ đích, sử dụng `@Around` một cách tường minh hoặc tốt hơn để business method trả đúng loại dữ liệu mong muốn.

### 8.2. Dùng @Around để quyết định return value

Đoạn sau chỉ minh họa cấu trúc, không ghép vào demo nếu muốn giữ output:

```java
@Around(
    "execution(public java.lang.String com.example.returning.ResultService.lookup(..))"
)
public Object decorateReturn(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    return "wrapped:" + result;
}
```

`ProceedingJoinPoint` đến từ `org.aspectj.lang.ProceedingJoinPoint`. Với method phù hợp, `@Around` có quyền trả một giá trị khác về caller, miễn tuân theo return type/contract thực tế. Nếu method có thể trả `null` hoặc ném exception, code production phải xử lý hai trường hợp đúng semantics.

**Đừng chuyển sang `@Around` chỉ vì muốn đếm normal returns:** `@AfterReturning` đơn giản và chính xác hơn cho observation.

## 9. @AfterReturning với void, null và kiểu đặc biệt

### 9.1. Method void

```java
public void refreshCache() {
    // kết thúc bình thường không có giá trị trả về
}
```

`@AfterReturning("execution(* ...refreshCache(..))")` **không bind return value** có thể chạy khi method hoàn thành bình thường. Nhưng `@AfterReturning(returning="result")` với tham số `String result` không có giá trị `String` để bind cho `void` invocation.

Nếu cần audit “đã chạy xong” của một method `void`, hãy dùng dạng **không bind** như `afterAnyNormalReturn()` trong demo.

### 9.2. Null từ method reference

```java
public String findOptionalText() {
    return null;
}
```

Đây là normal return, không phải exception. Advice **không bind** có thể chạy. Khi bind result vào kiểu reference, code cần null-safe. Nếu return type generic/erasure khác biệt hoặc binding có constraints bổ sung, kiểm tra trực tiếp trên phiên bản Spring đang dùng. Không tự kết luận “return null nghĩa là `@AfterReturning` không chạy”.

### 9.3. Primitive / wrapper

`int`, `long`, `boolean` và các wrappers có thể được biểu diễn theo boxed `Object` ở tầng reflection/interceptor thích hợp; nhưng advice `String result` **không** tương thích với kết quả kiểu `Integer`. Khi cần đo nhiều loại kết quả, có thể chọn `Object result` với điều kiện matching được xác nhận, hoặc chia pointcut/advice theo return type rõ ràng.

Không cast `Object` sang `String` nếu cùng pointcut bao phủ `Integer`, DTO và `null`. Nếu phải phân nhánh runtime, dùng `instanceof` và null-check hợp lý.

### 9.4. Optional

Nếu target trả `Optional<User>`, thứ mà advice nhận là object `Optional`, **không tự unwrap** thành `User`. Một `Optional.empty()` vẫn là normal return; nó không đồng nghĩa exception hay business success. Nếu quan tâm “có dữ liệu”, hãy inspect `Optional.isPresent()` trong code quan sát hoặc thiết kế result policy thích hợp.

### 9.5. CompletableFuture, CompletionStage, Mono và Flux

Nếu method trả `CompletableFuture<T>`, `CompletionStage<T>`, `Mono<T>` hoặc `Flux<T>`, `@AfterReturning` của Spring proxy thường được kích hoạt khi **method trả về wrapper/handle bình thường**, **không phải** khi computation hoặc publisher bất đồng bộ hoàn tất. Advice bind return value sẽ thấy **future hoặc publisher**, không mặc nhiên thấy dữ liệu cuối cùng `T`.

- Với `CompletableFuture`: muốn quan sát completion thành công/thất bại, dùng API như `whenComplete`/`handle` có chủ đích và cần thiết kế threading/context đúng.
- Với Reactor `Mono`/`Flux`: việc tạo publisher khác việc subscribe/completion; quan sát reactive signals cần Reactor operators/instrumentation phù hợp.
- Không gắn tên “businessSuccess” cho mỗi invocation của `@AfterReturning` khi kết quả là async handle.

## 10. @AfterReturning và exception: những trường hợp thực tế

### 10.1. Target ném exception

```java
public String load(String id) {
    throw new IllegalArgumentException("not found");
}
```

Nếu invocation `load` đi qua proxy nhưng ném exception ra khỏi join point, `@AfterReturning` không chạy. Muốn theo dõi exception, dùng `@AfterThrowing`:

```java
@AfterThrowing(
    pointcut = "execution(public * com.example.orders..*Service.*(..))",
    throwing = "failure",
    argNames = "failure"
)
public void afterFailure(Throwable failure) {
    // Log/metric lỗi; không tự đổi failure thành normal result.
}
```

Đây là đoạn minh họa, cần import `AfterThrowing` và class aspect Spring bean. `throwing` tương tự `returning` ở chỗ tên phải bind đúng vào tham số advice; kiểu tham số có thể giới hạn loại exception được chọn.

### 10.2. Method bắt exception rồi return fallback

```java
public String findOrFallback() {
    try {
        return repositoryLookup();
    } catch (RuntimeException ex) {
        return "fallback";
    }
}
```

Đây là đoạn minh họa, `repositoryLookup()` giả định tồn tại. Nếu method **bắt lỗi nội bộ và thực sự return `"fallback"`**, `@AfterReturning` thấy **normal return**. Nó không có nghĩa thao tác gốc chưa từng có lỗi, chỉ rằng lỗi không đi ra khỏi **join point đang được advice**.

Để phân biệt “fallback do lỗi” và “thành công đầy đủ”, có thể thiết kế return type chứa trạng thái domain (`Result<T>`, error code) hoặc dùng metric ở tầng xử lý lỗi. Không biến Spring AOP normal-return thành phép đo business success tuyệt đối.

### 10.3. Advice @AfterReturning tự ném exception

```java
@AfterReturning(
    "execution(public * com.example.orders..*Service.lookup(..))"
)
public void audit() {
    throw new IllegalStateException("audit unavailable");
}
```

Đây là **đoạn minh họa rủi ro**, không thêm vào project demo. Target có thể vừa hoàn thành bình thường nhưng **advice ném exception**, khiến caller **nhận lỗi** qua interceptor chain thay vì kết quả. Spring AOP không tự “nuốt” exception của advice chỉ vì nó chạy sau target.

Do đó, với audit/metrics không critical, hãy xác định chính sách lỗi: log/metric an toàn, không bất ngờ phá transaction hay API contract nếu đó không phải yêu cầu. Nếu audit bắt buộc phải thành công mới trả kết quả, xem xét nghiệp vụ/transaction semantics rõ ràng thay vì làm side effect tùy tiện trong advice.

### 10.4. Transaction commit không đồng nghĩa @AfterReturning

Nếu method có `@Transactional`, order của transaction interceptor và custom aspect có thể làm thời điểm `@AfterReturning` tương đối với commit khác nhau tùy advisor order/propagation. “Target method normal return” **không đủ bằng chứng** DB transaction đã commit. Nếu cần trigger hành động **sau khi commit thành công**, hãy sử dụng cơ chế transaction synchronization/`@TransactionalEventListener(phase = AFTER_COMMIT)` theo cấu hình transaction thực tế.

Nhắc lại: `@Transactional` cần transaction management/transaction manager riêng; chỉ `@EnableAspectJAutoProxy` không tự bật transaction behavior.

## 11. Khi method có nhiều advisors

Một target bean có thể có:

- Custom `@Around` biến đổi return value hoặc bắt exception;
- Spring transaction/cache/security advisor;
- `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After` của cùng hoặc các aspects khác;
- Interceptors từ thư viện quan sát/monitoring.

Vì vậy, khi debug phải hỏi **@AfterReturning đang quan sát normal return của join point ở vị trí nào trong chain?**, và **có interceptor bên ngoài đổi kết quả/lỗi không?**

Theo tài liệu Spring, thứ tự execution của các advice trong một aspect được điều phối dựa trên loại advice; `@After` có semantics after-finally; các advice **cùng một loại** trong cùng aspect không có thứ tự cố định chỉ do chúng xuất hiện ở dòng trước/sau trong source file.

Nếu ứng dụng cần thứ tự giữa **các aspects**, có thể dùng `@Order` hoặc `Ordered` và integration test trên service method thật. Không thiết kế để **hai `@AfterReturning` cùng loại** chạy theo một thứ tự nhất định chỉ vì tên method hay vị trí source.

Trong demo, hai advices dùng counters độc lập và không phụ thuộc vào ordering; đó là lý do stdout tất định.

## 12. Spring Boot và khác biệt giữa khai báo aspect với bật AOP

Với Spring Boot, khi có AOP starter/auto-configuration phù hợp, thường không cần tự viết `@EnableAspectJAutoProxy`. Nhưng phải bảo đảm:

1. `@Aspect` class là Spring bean, thường `@Aspect` + `@Component` nằm trong package được scan, hoặc được trả từ một `@Bean`.
2. Service target cũng nằm trong Spring container.
3. Pointcut expression thực sự match một method có thể intercept.
4. Caller đi qua Spring proxy; không tự gọi `this.method()`.
5. `returning` name và type phù hợp với method outcomes đang kiểm tra.

Dependency Gradle chọn theo **Boot major** và dependency management của Boot, không dùng đồng thời:

```gradle
// Spring Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Spring Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

Trong Boot, class-based proxy thường được chọn theo `spring.aop.proxy-target-class=true`. Nếu dùng JDK interface proxy (`spring.aop.proxy-target-class=false`), method cần được expose trên interface. Nếu target có method `final` và CGLIB, Spring không intercept method đó. Dù chọn proxy loại nào, self-invocation vẫn không quay lại proxy theo cơ chế Spring AOP thông thường.

## 13. Phương pháp kiểm thử chính xác

### 13.1. Kiểm tra bean có Spring proxy chưa

```java
ResultService bean = context.getBean(ResultService.class);
System.out.println(AopUtils.isAopProxy(bean));
```

Đoạn minh họa dùng `context` và import `AopUtils` như `Main.java`. Kết quả true giúp xác nhận Spring trả proxy, **không chứng minh riêng `@AfterReturning` đã match**. Cần thêm recorder/counter.

### 13.2. Tách kiểm thử pointcut và type binding

Một integration test cho demo cần assert:

- Gọi `lookup("A")` qua proxy làm **normal** và **string** counters tăng.
- Gọi `available()` làm **normal** tăng nhưng **string** không tăng.
- Gọi `warmUp()` làm **normal** tăng.
- Gọi `fail()` ném exception nhưng không làm hai counters tăng.
- Kết quả return mà caller nhận đúng giá trị target trả; `@AfterReturning` không thay.
- Một lần gọi qua `new ResultService()` ở ngoài Spring không làm counters của Spring aspect thay đổi.

Để tránh phụ thuộc log, có thể viết test bằng assertion trực tiếp:

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    ResultService service = context.getBean(ResultService.class);
    ReturnAspect aspect = context.getBean(ReturnAspect.class);

    service.lookup("X");
    service.available();
    service.warmUp();

    try {
        service.fail();
    } catch (IllegalStateException expected) {
        // Target ném lỗi, @AfterReturning không được tính cho lần gọi này.
    }

    if (aspect.normalCount() != 3 || aspect.stringCount() != 1) {
        throw new AssertionError("Wrong @AfterReturning counters");
    }
}
```

Đây là **đoạn test minh họa** có thể dùng trong package của demo với import `AnnotationConfigApplicationContext`; nó tạo một context mới, không thay `Main` và không nhằm tạo stdout ở mục 6.5. Trong test production, thay try/catch thủ công bằng JUnit `assertThrows` và test assertion framework được quản lý dependency.

### 13.3. Vì sao không nên test chỉ bằng mock hoặc new?

`new ReturnAspect()` + gọi trực tiếp `afterStringReturn("x")` chỉ test Java method của aspect, không chứng minh Spring đã đọc `@AfterReturning` và bind result đúng kiểu. `new ResultService()` thì không đi qua proxy; dù method trả về bình thường, Spring advice không có cơ hội chạy.

**Đúng mục tiêu:** integration test phải khởi tạo context với aspect bean, auto-proxy support, Spring target bean, gọi method qua Spring reference và xác nhận event/counter.

## 14. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có khả năng | Cách xác minh trong Spring |
| --- | --- | --- |
| Không có advice sau normal return | Aspect không là Spring bean, thiếu AOP enable/config, pointcut không match hoặc caller không qua proxy | Liệt kê beans, check `AopUtils.isAopProxy`, gọi public method qua Spring reference. |
| Advice không có tham số chạy, advice `returning` không chạy | Kiểu tham số binding không tương thích với returned value/declared return type | So sánh `Object` vs `String`, signature các methods, test từng type. |
| Startup lỗi khi thêm `returning` | `returning` name khác tên tham số, `argNames` sai, pointcut binding mâu thuẫn | Xem root cause của Spring/AspectJ binding, thống nhất tên và kiểu. |
| `@AfterReturning` vẫn chạy dù business fallback là lỗi | Method đã catch exception và return bình thường | Xem join point thật và business outcome; không đồng nhất normal return với success domain. |
| Advice không chạy trên method ném lỗi | Đây là behavior đúng của `@AfterReturning` | Dùng `@AfterThrowing` để theo dõi exception; `@After` nếu cần after-finally. |
| Advice không chạy khi method `void` | Advice đang bind `String` trong khi method không trả giá trị, hoặc pointcut không match | Dùng dạng không bind result, kiểm tra interception. |
| `@AfterReturning` có log nhưng return về client không đổi | `@AfterReturning` không thay reference trả về | Nếu thật sự cần transform, xem `@Around` hoặc business method. |
| Advice nhận `null` rồi lỗi NPE | Code tự dereference result không null-safe | Null-check; test method khai báo reference return. |
| Số advice invocations không bằng số request HTTP | Có cache/async/retry, nhiều method, self-call hoặc pointcut chỉ match một số bean | Đếm invocation ở method entry, không dùng request count làm proxy. |
| `@AfterReturning` chạy khi future được trả về nhưng task sau đó fail | Advice quan sát wrapper return, không phải async completion | Quan sát future completion/Reactive signals bằng API tương ứng. |
| Method là `final` và Spring dùng CGLIB | Proxy không override/intercept được method | Đổi entry method/class, hoặc JDK interface proxy khi thiết kế cho phép. |
| Gọi từ cùng service qua `this.method()` | Self-invocation bypass proxy | Tách sang bean cộng tác Spring và inject proxy, hoặc đặt advice ở entry operation phù hợp. |
| Metrics/audit trong advice tự throw | Caller có thể nhận exception dù target return bình thường | Chọn error policy rõ, test cả advice failures. |

## 15. Quy trình áp dụng vào dự án

1. **Chọn sự kiện đúng:** cần quan sát **normal method return** hay business success/transaction commit/async completion? Nếu không phải normal return, có thể cần cơ chế khác.
2. **Chọn tập method bằng pointcut:** giới hạn package, class, method và proxy contract. Tránh `execution(* *(..))` quá rộng.
3. **Chọn có bind hay không:** chỉ cần đếm normal returns thì dùng `@AfterReturning("...")`; cần đọc data thì dùng `returning`.
4. **Nếu bind, chọn type có chủ đích:** `String` giúp chỉ chọn kết quả text; `Object` linh hoạt hơn nhưng cần null/type checking.
5. **Đặt tên tham số nhất quán:** `returning="result"` khớp `result` của advice; thêm `argNames` khi cần.
6. **Đăng ký aspect với Spring:** `@Component` hoặc `@Bean`, đúng scope/context; bật Spring AOP support.
7. **Kiểm tra proxy boundary:** target là Spring bean, method chặn được, external call qua proxy. Loại trừ self-invocation/`new`.
8. **Viết test cho nhiều outcomes:** successful return, wrong return type, `void`, `null`, exception, async wrapper khi có liên quan.
9. **Xem lại side effects:** advice không thay return reference; audit/metrics có thể ném lỗi hoặc tác động performance/transaction.
10. **Chỉ tuyên bố success theo đúng nghĩa:** normal return của method không bảo đảm commit, delivery, authorization hay end-to-end success.

## 16. Checklist cuối bài

- [ ] Biểu thức pointcut chọn đúng Spring target bean/method cần quan sát?
- [ ] Aspect có `@Aspect` và được Spring đăng ký bằng `@Component`/`@Bean`?
- [ ] Spring @AspectJ proxy support đã bật và có AspectJ Weaver phù hợp?
- [ ] Caller thực sự gọi target qua Spring proxy; không phải `new` hoặc `this.method()`?
- [ ] Đã phân biệt normal return, caught exception, thrown exception và async completion?
- [ ] Nếu dùng `returning`, tên khớp tên parameter advice và `argNames` nếu được khai báo?
- [ ] Advice parameter type có chủ đích và tương thích với return values cần match?
- [ ] `void`/`null`/primitive/`Optional` được test khi có trong nghiệp vụ?
- [ ] Không cố thay thế returned reference bằng giá trị return của `@AfterReturning`?
- [ ] Side effects trên mutable returned objects, audit logging và exception trong advice được kiểm soát?
- [ ] Nếu còn transaction/cache/security/async advisors, đã xem xét thứ tự và semantics thực tế?
- [ ] Integration test xác nhận advice events/counters đúng số lần và business result không đổi?

**Điểm nhớ:** Trong Spring AOP, `@AfterReturning` dành cho **lời gọi qua proxy đã hoàn tất bình thường**. `returning="result"` cho phép advice **nhận giá trị trả về** và **ràng buộc thêm theo kiểu tham số**, nên một advice bind `String` có thể chạy ít lần hơn advice không bind dù cả hai dùng chung pointcut. Nó **không thay kết quả**; nếu muốn transform, dùng một thiết kế khác như `@Around`. Luôn kiểm tra đúng Spring bean, proxy, method outcome và contract nghiệp vụ.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Declaring Advice / After Returning Advice và return binding](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Proxying Mechanisms, self-invocation, JDK và CGLIB](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Advice API / AfterReturningAdvice](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/advice.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
