# Phân biệt đường thành công, đường ngoại lệ và kết thúc phương thức trong Spring AOP

## 1. Cùng một Spring method nhưng có ba kết cục cần quan sát

Một Spring service có thể **trả kết quả bình thường**, **ném ngoại lệ ra cho caller** hoặc **kết thúc theo một trong hai cách trên và cần dọn dẹp/ghi nhận việc đã kết thúc**. Khi dùng Spring Aspect để log, đo metric, audit hoặc theo dõi lỗi, cần chọn đúng loại advice ứng với kết cục mà hệ thống thật sự muốn biết.

Ví dụ một method `checkout(String id)` có các đường:

```text
Client
  |
  v
Spring AOP proxy
  |
  +-- @Before: khi lời gọi sắp được thực thi
  |
  v
Target checkout(...)
  |
  +-- return "OK" ---------> đường hoàn thành bình thường
  |                           +-- @AfterReturning
  |                           +-- @After (finally)
  |
  +-- throw Exception ------> đường kết thúc bằng ngoại lệ
                              +-- @AfterThrowing
                              +-- @After (finally)
```

`@After` không phải dạng viết khác của `@AfterReturning`: nó có semantics gần `finally` của Java, chạy khi **method execution phù hợp kết thúc**, bất kể hoàn thành bình thường hay có ngoại lệ thoát ra. `@AfterReturning` chỉ phản ánh **normal completion**; `@AfterThrowing` chỉ phản ánh **exceptional completion**.

Trong Spring AOP, các advice này được nối thành **interceptor chain trên Spring-managed proxy**. Một điều kiện tối quan trọng: **pointcut có khớp mà lời gọi không đi qua proxy thì advice vẫn không chạy**. Lời gọi `this.method()` giữa hai method của cùng target, constructor hoặc đối tượng được tạo bằng `new` không tự nhận Spring AOP advice.

**Phạm vi bài:** Cơ chế advice dựa trên sự kiện hoàn tất **method execution trong Spring Framework / Spring `@Aspect`**. Không mở rộng sang AspectJ weaving của constructor hoặc field join points ngoài Spring.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt chính xác `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After` và `@Around`.
2. Hiểu “thành công” trong `@AfterReturning` là **không ném ngoại lệ**, không đồng nghĩa kết quả kinh doanh đã đạt mục tiêu.
3. Hiểu một exception **bị bắt và xử lý bên trong target** không phải “exceptional completion” của proxy invocation.
4. Bind giá trị trả về bằng `returning` và bind ngoại lệ bằng `throwing`, tránh vô tình thu hẹp type.
5. Chạy ví dụ Java 17/Spring Framework với kết quả bình thường, `null`, checked exception và unchecked exception.
6. Chẩn đoán tại sao cùng một invocation có `@After` nhưng chỉ có một trong `@AfterReturning` hoặc `@AfterThrowing`; khi nào `@Around` thay đổi kết cục.

## 2. Bảng ngữ nghĩa các advice trong Spring

| Advice | Khi nào chạy? | Có thấy normal return? | Có thấy exception? | Vai trò chính |
| --- | --- | --- | --- | --- |
| `@Before` | Trước method execution khớp, khi proxy chain đi tới advice | Chưa biết kết quả | Chưa biết kết quả | Kiểm tra tiền điều kiện, bắt đầu log/metric đơn giản |
| `@AfterReturning` | Method execution khớp **trả về bình thường** | Có, có thể bind giá trị | Không chạy khi exception thoát ra | Ghi nhận hoàn thành, đọc kết quả, metric success |
| `@AfterThrowing` | Method execution khớp **thoát ra bằng ngoại lệ** | Không chạy khi trả bình thường | Có, có thể bind exception | Ghi nhận failure/exception, cảnh báo |
| `@After` | Khi method execution khớp kết thúc theo một trong hai đường | Có chạy | Có chạy | Cleanup, ghi nhận “completed”, giải phóng trạng thái |
| `@Around` | Bao quanh method invocation và kiểm soát có gọi `proceed()` hay không | Có thể quan sát/chỉnh kết quả | Có thể catch/rethrow/chuyển ngoại lệ | Tracing duration, thử lại có kiểm soát, fallback có chủ đích |

Bảng diễn đạt outcome của **method execution đã đi qua những advisor phù hợp**; nó không đảm bảo callback được chạy trong các tình huống hủy process đột ngột, lỗi VM nghiêm trọng hoặc khi một advisor *khác* short-circuit trước khi chain đi đến advice tương ứng.

### Một cách nhớ ngắn

```text
Target return normally?
    YES -> @AfterReturning; @After
    NO  -> nếu exception thoát ra -> @AfterThrowing; @After

@After: không chọn một đường; quan sát kết thúc chung.
@Around: có thể tự tạo đường đi bằng proceed / return / throw.
```

Trong cùng một invocation đã chạy tới các advice này, `@AfterReturning` và `@AfterThrowing` đại diện hai điều kiện kết thúc khác nhau; **không phải hai hook cần chạy đồng thời**.

## 3. @AfterReturning: hoàn thành bình thường, không nhất thiết “nghiệp vụ thành công”

Định nghĩa:

```java
@Aspect
public class CompletionAspect {

    @AfterReturning(
        pointcut = "execution(* com.example.app.service..*.*(..))"
    )
    public void completedNormally() {
        // Method execution đã return bình thường.
    }
}
```

### 3.1. Ba kết quả vẫn là normal return

Ví dụ method có thể:

```java
public String evaluate(String mode) {
    if ("ok".equals(mode)) {
        return "OK";
    }
    if ("missing".equals(mode)) {
        return null;
    }
    return "DECLINED";
}
```

Cả ba trường hợp trên đều **return bình thường**:
- `"OK"` là thành công theo hợp đồng nghiệp vụ;
- `null` có thể là “không có dữ liệu”, nhưng vẫn return bình thường;
- `"DECLINED"` có thể là “từ chối thanh toán”, nhưng vẫn không phải exception.

`@AfterReturning` chạy cho cả ba khi invocation khớp và đi qua proxy. Vì thế đặt tên metric là `technical_normal_completion` thường chính xác hơn coi mọi lần `@AfterReturning` đều là `business_success`.

Nếu một method `void` kết thúc mà không ném exception, đó cũng là **normal completion**; advice `@AfterReturning` không có ràng buộc `returning` vẫn có thể chạy.

### 3.2. Bind giá trị trả về với returning

```java
@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    returning = "result",
    argNames = "result"
)
public void captureResult(Object result) {
    System.out.println("return=" + result);
}
```

Đây là snippet minh họa trong một lớp `@Aspect`; cần import và cấu hình thật để chạy. Tên `result` trong `returning` phải khớp tên tham số advice. `argNames` làm tên binding tường minh khi biên dịch Java không bảo toàn parameter names theo kỳ vọng.

Vì tham số advice là `Object`, nó chấp nhận đa số giá trị trả về; nếu thay thành `String`, việc bind có thể **thu hẹp phạm vi advice** tới những kết quả/method phù hợp với kiểu `String`. Đừng vô tình ràng buộc kiểu chỉ để in một giá trị.

**Giới hạn:** `@AfterReturning` có thể quan sát hoặc tương tác với object kết quả, nhưng **không được dùng để thay reference trả về** cho caller bằng cách `return` giá trị khác từ advice. Nếu yêu cầu là biến đổi kết quả trả ra cho caller, dùng `@Around` với `ProceedingJoinPoint.proceed()` và trả lại giá trị mong muốn.

## 4. @AfterThrowing: ngoại lệ phải thoát khỏi join point

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void captureFailure(Throwable error) {
    System.out.println("exception=" +
        error.getClass().getSimpleName());
}
```

Trong Spring AOP, `@AfterThrowing` chạy khi method execution khớp **kết thúc bằng exception được ném ra ngoài**. `throwing` có thể bind exception object cho advice.

### 4.1. Checked và unchecked exceptions

Ví dụ:

```java
public String load(String mode) throws IOException {
    if ("checked".equals(mode)) {
        throw new IOException("offline");
    }
    if ("unchecked".equals(mode)) {
        throw new IllegalStateException("broken");
    }
    return "OK";
}
```

Nếu các exception thực sự thoát khỏi method execution và lời gọi đi qua proxy, `@AfterThrowing` có `Throwable error` có thể quan sát **cả `IOException` và `IllegalStateException`**. Exception không nhất thiết phải là `RuntimeException`.

Ngược lại, nếu advice khai báo:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void captureIllegalState(IllegalStateException error) {
    // Chỉ khớp kiểu ngoại lệ thích hợp.
}
```

thì ràng buộc `IllegalStateException` làm advice không chạy cho `IOException`. Đây là **lọc theo loại exception**, không có nghĩa Spring chỉ hỗ trợ unchecked exceptions.

### 4.2. Exception được target tự bắt thì không phải exceptional completion

```java
public String loadSafely() {
    try {
        return fetchRemote();
    } catch (IOException ex) {
        return "FALLBACK";
    }
}
```

Đây là snippet giả định `fetchRemote()` có thể ném `IOException`. Nếu target bắt exception bên trong và return `"FALLBACK"`, từ góc nhìn method execution do proxy quan sát, kết cục là **normal return**:
- `@AfterReturning` có thể chạy;
- `@AfterThrowing` trên `loadSafely` không chạy vì `IOException` không thoát khỏi method;
- `@After` vẫn chạy.

Nếu nghiệp vụ cần quan sát mỗi exception được **bắt nội bộ**, Spring AOP proxy không tự chặn từng câu lệnh `throw`/`catch` bên trong method. Hãy log tại catch block hoặc thiết kế instrumentation thích hợp.

### 4.3. @AfterThrowing không phải bộ xử lý ngoại lệ tổng quát

Nó chỉ nhận những exception thuộc lời gọi method execution tương ứng. Tài liệu Spring nêu rõ `@AfterThrowing` không phải callback tổng quát cho exception do advice `@After`/`@AfterReturning` khác ném ra. Cũng không thể dùng kiểu `void` advice này để **swallow exception** và trả kết quả mới như một fallback thông thường.

Muốn thay đổi exception và kết quả do caller nhìn thấy, dùng `@Around` khi thật sự cần, cân nhắc tác động lên transaction và các advice khác.

## 5. @After: kết thúc bình thường hay ngoại lệ đều cần đi qua

```java
@After("execution(* com.example.app.service..*.*(..))")
public void afterAnyCompletion() {
    System.out.println("completed");
}
```

`@After` trong `@AspectJ` tương đương ý tưởng **finally**:

```java
try {
    // target method execution
} finally {
    // cleanup
}
```

Nó thích hợp cho việc:
- Gỡ trạng thái local của tracing;
- Ghi metric tổng lượt kết thúc;
- Giải phóng tài nguyên thuộc phạm vi advice, nếu ownership rõ;
- Bỏ dấu hiệu “đang xử lý” được thiết lập trước đó.

### 5.1. Không phải nơi kết luận method “success”

Nếu increment counter `completed` trong `@After`, counter ấy có thể bao gồm **cả method trả bình thường và method ném exception**. Không đặt tên là `successfulRequests` nếu giá trị đến từ `@After`.

Một phép kiểm tra logic:

```text
totalCompleted ≈ normalReturns + thrownCompletions
```

Đẳng thức có ý nghĩa khi ba counter quan sát **cùng tập method invocation**, tất cả advice đều được áp dụng, không có short-circuit/lỗi trong advice và không có code thay đổi outcome ngoài phạm vi quan sát. Trong một proxy chain phức tạp hoặc hệ thống concurrent, phải tính toán theo design thực tế.

### 5.2. @After và finally của Java không phải bảo đảm tuyệt đối

`@After` chạy khi execution đến advice và hoàn tất qua những đường return/throw. Nếu JVM bị `System.exit`, process bị kill, thread chết bởi sự kiện nghiêm trọng hoặc một advisor đứng **ngoài** chain đã bỏ qua việc proceed, callback có thể không được gọi. Tương tự, nếu không có AOP proxy hoặc pointcut không khớp, không có hook để chạy.

Dùng `try/finally` ngay trong code sở hữu tài nguyên nếu cần bảo đảm giải phóng trong phạm vi method nội bộ, không giả định `@After` thay thế mọi quy tắc quản lý tài nguyên.

## 6. Thứ tự advice: điều dễ bị hiểu sai

Trong cùng một `@Aspect`, Spring áp dụng precedence theo loại advice. Tài liệu Spring Framework mô tả thứ tự loại advice từ mức precedence cao đến thấp: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`. **Nhưng `@After` thực tế được gọi *sau* `@AfterReturning` hoặc `@AfterThrowing` của cùng aspect**, phù hợp semantics “finally”.

Không nên đọc bảng precedence rồi kết luận rằng log `@After` luôn in **trước** log `@AfterReturning`: đó là nhầm giữa thứ tự interceptor chain và thứ tự callback khi unwind.

Nếu advice nằm ở **hai aspect khác nhau**, khi cả hai cùng match một join point, thứ tự không được đảm bảo nếu không cấu hình `@Order`/`Ordered`. Aspect có order value thấp hơn thường có precedence cao hơn: đi vào trước và đi ra sau.

### Minh họa đường normal completion

```text
proxy.method()
    |
    +-- @Before            [đường đi vào]
    |
    +-- target returns     [normal completion]
    |
    +-- @AfterReturning    [nhánh normal]
    |
    +-- @After             [finally, cùng aspect]
    |
    +-- caller sees return
```

### Minh họa đường exceptional completion

```text
proxy.method()
    |
    +-- @Before
    |
    +-- target throws
    |
    +-- @AfterThrowing     [nhánh exception]
    |
    +-- @After             [finally, cùng aspect]
    |
    +-- caller receives exception
```

Hai flow trên giúp phân biệt **ý nghĩa các sự kiện** trong Spring AOP; chúng không thay thế việc inspect advisor ordering khi có nhiều aspect, transaction, cache, retry hoặc `@Around` chuyên biệt.

## 7. Ví dụ Spring Framework chạy được: bốn đường kết thúc

Ví dụ sau dùng:
- **Java 17+**;
- **Spring Framework 6.1.14**;
- **AspectJ Weaver 1.9.22.1**;
- **Gradle**;
- Một `@Aspect` ghi các bộ đếm advice.

Ta chủ động **không in log từ bên trong advice** mà tăng counter và in snapshot sau mỗi method invocation. Cách này chứng minh đủ ba loại outcome mà không phụ thuộc vào chi tiết thứ tự in log giữa các advice.

Bốn input:
1. `"ok"` → return `"OK"`;
2. `"empty"` → return `null`;
3. `"unchecked"` → throw `IllegalStateException`;
4. `"checked"` → throw `IOException`.

### 7.1. Cấu trúc thư mục

```text
spring-aop-outcomes/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/outcomes/
    ├── OutcomeService.java
    ├── OutcomeAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Gradle configuration

Tệp `settings.gradle`:

```groovy
rootProject.name = 'spring-aop-outcomes'
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
    mainClass = 'demo.outcomes.DemoApplication'
}
```

`spring-context` cung cấp IoC/configuration; `spring-aop` chứa proxy infrastructure; `aspectjweaver` hỗ trợ parser cho pointcut trong `@Aspect`.

### 7.3. Target method với bốn kết cục

Tệp `src/main/java/demo/outcomes/OutcomeService.java`:

```java
package demo.outcomes;

import java.io.IOException;

public class OutcomeService {

    public String evaluate(String mode) throws IOException {
        System.out.println("target:" + mode);

        if ("ok".equals(mode)) {
            return "OK";
        }
        if ("empty".equals(mode)) {
            return null;
        }
        if ("unchecked".equals(mode)) {
            throw new IllegalStateException("broken");
        }
        if ("checked".equals(mode)) {
            throw new IOException("offline");
        }
        return "UNKNOWN";
    }
}
```

`OutcomeService.evaluate` là public non-final method, có thể được CGLIB proxy chặn. Method khai báo `throws IOException` để checked exception **được phép thoát ra**; `IllegalStateException` là unchecked.

`return null` vẫn là normal completion. Code ngoài `evaluate` là caller chịu trách nhiệm phân biệt exception và return value.

### 7.4. Aspect đếm before, after-returning, after-throwing, after

Tệp `src/main/java/demo/outcomes/OutcomeAspect.java`:

```java
package demo.outcomes;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class OutcomeAspect {
    private final AtomicInteger before = new AtomicInteger();
    private final AtomicInteger normal = new AtomicInteger();
    private final AtomicInteger failed = new AtomicInteger();
    private final AtomicInteger finished = new AtomicInteger();

    @Before("execution(public * demo.outcomes.OutcomeService.evaluate(..))")
    public void onEnter() {
        before.incrementAndGet();
    }

    @AfterReturning(
        pointcut = "execution(public * demo.outcomes.OutcomeService.evaluate(..))",
        returning = "result",
        argNames = "result"
    )
    public void onNormalReturn(Object result) {
        normal.incrementAndGet();
        // result có thể là null; không mặc định kết quả == thành công nghiệp vụ.
    }

    @AfterThrowing(
        pointcut = "execution(public * demo.outcomes.OutcomeService.evaluate(..))",
        throwing = "error",
        argNames = "error"
    )
    public void onException(Throwable error) {
        failed.incrementAndGet();
        // error có thể là checked hoặc unchecked exception.
    }

    @After("execution(public * demo.outcomes.OutcomeService.evaluate(..))")
    public void onAnyCompletion() {
        finished.incrementAndGet();
    }

    public String counts() {
        return "before=" + before.get()
            + " returned=" + normal.get()
            + " thrown=" + failed.get()
            + " after=" + finished.get();
    }
}
```

Giải thích điểm quyết định:
- `onEnter()` được chạy khi proxy đưa invocation qua `@Before`.
- `onNormalReturn(Object result)` dùng `Object` để không tự ràng buộc quá hẹp vào một return class cụ thể; `null` vẫn normal.
- `onException(Throwable error)` dùng `Throwable` để bao cả `IOException` và `IllegalStateException`. Nếu đổi thành `IllegalStateException`, bộ đếm không còn đại diện mọi exception.
- `onAnyCompletion()` đếm tất cả lời gọi đã kết thúc qua advice `@After`.
- Các counter là `AtomicInteger` để tránh lỗi tăng số khi nhiều thread sử dụng cùng singleton aspect; demo gọi tuần tự để stdout xác định.

Các method advice **không trả kết quả thay cho target**, cũng không swallow exception. Chúng chỉ đo lường sự kiện.

### 7.5. Đăng ký bean và bật Spring AOP

Tệp `src/main/java/demo/outcomes/AppConfig.java`:

```java
package demo.outcomes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OutcomeService outcomeService() {
        return new OutcomeService();
    }

    @Bean
    public OutcomeAspect outcomeAspect() {
        return new OutcomeAspect();
    }
}
```

`@Aspect` **không tự** đăng ký Spring bean. Trong ví dụ, `@Bean` cung cấp aspect instance; `@EnableAspectJAutoProxy` kích hoạt hạ tầng phân tích advisor. `proxyTargetClass=true` chọn class-based proxy để lấy service theo `OutcomeService.class`.

### 7.6. Main gọi bốn tình huống qua proxy

Tệp `src/main/java/demo/outcomes/DemoApplication.java`:

```java
package demo.outcomes;

import java.io.IOException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OutcomeService service = context.getBean(OutcomeService.class);
            OutcomeAspect aspect = context.getBean(OutcomeAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            invoke(service, aspect, "ok");
            invoke(service, aspect, "empty");
            invoke(service, aspect, "unchecked");
            invoke(service, aspect, "checked");
        }
    }

    private static void invoke(
            OutcomeService service, OutcomeAspect aspect, String mode) {

        try {
            String result = service.evaluate(mode);
            System.out.println("caller:" + mode + "=" + result);
        } catch (IOException | IllegalStateException ex) {
            System.out.println(
                "caller:" + mode + " threw "
                + ex.getClass().getSimpleName()
                + ":" + ex.getMessage()
            );
        }
        System.out.println("counts " + aspect.counts());
    }
}
```

Lệnh chạy từ thư mục `spring-aop-outcomes`:

```bash
gradle run
```

Nếu project có Gradle Wrapper, có thể dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

### 7.7. Stdout kỳ vọng

Những dòng dưới đây là **stdout từ Java code**, không tính Gradle logs:

```text
proxy=true
target:ok
caller:ok=OK
counts before=1 returned=1 thrown=0 after=1
target:empty
caller:empty=null
counts before=2 returned=2 thrown=0 after=2
target:unchecked
caller:unchecked threw IllegalStateException:broken
counts before=3 returned=2 thrown=1 after=3
target:checked
caller:checked threw IOException:offline
counts before=4 returned=2 thrown=2 after=4
```

Kết quả được hiểu như sau:

| Sau input | Tổng `@Before` | Tổng `@AfterReturning` | Tổng `@AfterThrowing` | Tổng `@After` |
| --- | ---: | ---: | ---: | ---: |
| `ok` | 1 | 1 | 0 | 1 |
| `empty` | 2 | 2 | 0 | 2 |
| `unchecked` | 3 | 2 | 1 | 3 |
| `checked` | 4 | 2 | 2 | 4 |

- `empty` vẫn tăng `returned` vì `null` không phải exception.
- `unchecked` và `checked` đều tăng `thrown` vì advice bind `Throwable`.
- `after` tăng ở cả bốn lượt vì mỗi invocation kết thúc theo một trong hai đường.
- Caller chỉ in `caller:mode=...` trên normal completion; với exception nó đi vào `catch`. Aspect không chặn hoặc thay đổi exception.
- `proxy=true` xác nhận lời gọi từ `main` đi qua Spring-managed proxy; nếu `new OutcomeService()` bên ngoài Spring, các counter sẽ không tăng.

Đây là phép quan sát bằng số đếm để tránh hiểu lầm về precedence của advice khi đọc những log in liên tiếp.

## 8. @Around: loại advice có thể thay đổi đường kết thúc

`@Around` có quyền rộng hơn bốn advice còn lại vì nó kiểm soát `ProceedingJoinPoint.proceed()`.

Một `@Around` dùng để đo thời gian và **giữ nguyên** outcome:

```java
@Around("execution(* com.example.app.service..*.*(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println("durationNanos=" + elapsed);
    }
}
```

Đây là snippet minh họa trong lớp `@Aspect`, cần import `@Around`/`ProceedingJoinPoint` và có Spring bean/service khớp. `proceed()` được gọi **đúng một lần**; nếu target return thì value được trả về cho caller, nếu ném exception thì exception vẫn đi ra ngoài sau `finally`.

### 8.1. Return kết quả khác

```java
@Around("execution(* com.example.app.service..*.load*(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "FALLBACK";
    }
}
```

Đây là snippet **cố tình biến đổi outcome**: đối với caller của proxy, trường hợp `IllegalStateException` do inner chain/target ném ra đã được catch và chuyển thành **normal return**. Điều này có thể thay đổi cách những advice **nằm ngoài** `@Around` phân loại lần gọi. Những advice **nằm bên trong** đã nhìn thấy exception từ target trước khi `@Around` catch có thể vẫn ghi nhận failure.

Không đưa snippet `fallback` vào project chạy ở mục 7 trừ khi sửa cả kiểu method, cấu hình aspect và expected stdout tương ứng. Nó minh họa một lựa chọn chính sách khác, không phải cách dùng mặc định.

### 8.2. Không gọi proceed()

```java
@Around("execution(* com.example.app.service..*.load*(..))")
public Object shortCircuit(ProceedingJoinPoint pjp) {
    return "CACHED";
}
```

Nếu advice này thực sự được áp dụng và **không gọi `proceed()`**, method target phía trong không chạy. Những advisor ở phía trong cũng có thể không chạy. Ví dụ, logging/transaction/caching đứng ở những vị trí khác nhau trong interceptor chain sẽ quan sát outcome khác nhau.

**Kết luận kỹ thuật:** “Target có return/throw gì” và “caller của proxy thấy return/throw gì” không phải luôn giống nhau khi có `@Around` hoặc interceptor có chức năng short-circuit. Phải chỉ rõ **ràng buộc quan sát ở vị trí nào trong chain**.

### 8.3. Nên ưu tiên advice ít quyền nhất

Nếu chỉ cần đếm normal return, dùng `@AfterReturning`. Nếu chỉ cần log exception thoát ra, dùng `@AfterThrowing`. Nếu chỉ cần cleanup, dùng `@After`. Chỉ dùng `@Around` khi cần truy cập cả trước và sau **trong một scope** hoặc cần điều khiển có tiếp tục chain hay không; mỗi lần quên `proceed()` có thể làm mất việc chạy target.

## 9. Tác động của Spring transaction, cache và retry

Khi một service có nhiều advisor, outcome phụ thuộc thứ tự interceptor.

### 9.1. Transaction

Nếu method `@Transactional` bị exception và exception thoát ra ngoài transaction interceptor, quy tắc rollback của Spring transaction có thể áp dụng theo **loại exception và cấu hình rollback**. Mặc định rollback thường xảy ra với `RuntimeException`/`Error`, không mặc định rollback với checked exception nếu không có `rollbackFor` phù hợp.

**Không suy ra** rằng cứ `@AfterThrowing` chạy thì database transaction chắc chắn rollback: hai cơ chế có rule khác nhau. Nếu một `@Around` catch exception và trả fallback **trước** khi transaction interceptor quan sát nó, transaction có thể xem invocation là bình thường tùy advisor ordering. Đây là lý do không swallow exception tùy tiện trong tracing aspect.

### 9.2. Caching

Một cache interceptor đứng ngoài advice có thể trả cache hit mà không chạy target và những advice phía trong. Khi đó:
- Bạn có thể không thấy `@AfterReturning` của inner aspect cho cache hit, vì advisor không được đi tới.
- Nếu advice đứng ngoài caching, nó có thể thấy normal return từ cache.
- Cùng một method signature và cùng một target bean không đảm bảo các advice có cùng số lượt chạy khi các advisor khác short-circuit.

### 9.3. Retry

Với retry interceptor hoặc một `@Around` cố ý gọi `proceed()` nhiều lần, một lời gọi ở caller có thể tương ứng **nhiều lần thử target**. Advice ở ngoài hoặc trong retry sẽ quan sát “một lần cuối cùng thành công” hay “nhiều lần throw trước đó” khác nhau.

Để metric có nghĩa, phải định nghĩa rõ:
- `attempt_failure`: lần thử target bị exception;
- `request_failure`: lời gọi cuối cùng ra ngoài proxy vẫn thất bại;
- `request_completed`: lời gọi hoàn tất bất kể outcome;
- `business_rejected`: target trả kết quả từ chối nhưng không ném exception.

Spring `@AfterReturning`/`@AfterThrowing` tự nó không quyết định metric thuộc lớp nào nếu bạn chưa xác định advisor order.

## 10. Ma trận phân loại outcome của cùng một Spring method

Phân biệt normal completion, exceptional completion và total completion bằng ba counter cùng áp dụng lên một tập invocation, cùng proxy boundary và cùng pointcut. Các giá trị dưới đây là một lượt lời gọi đã match đủ advice:

| Target outcome | Normal return | Throwing | Finally |
| --- | ---: | ---: | ---: |
| Trả chuỗi OK | 1 | 0 | 1 |
| Trả null | 1 | 0 | 1 |
| Trả DECLINED | 1 | 0 | 1 |
| Catch IOException rồi trả fallback | 1 | 0 | 1 |
| Ném IllegalStateException ra ngoài | 0 | 1 | 1 |
| Ném IOException ra ngoài | 0 | 1 | 1 |

Return DECLINED là business refusal nhưng vẫn là normal method completion. Nếu advice @AfterThrowing chỉ bind RuntimeException thì riêng nhánh IOException không được nó đếm; nếu @AfterReturning chỉ bind String, method void và return type khác có thể bị loại.

## 11. Khi nào công thức completed = normal + throwing sai?

Công thức chỉ hữu ích khi ba advice quan sát cùng một invocation boundary, không có short-circuit hay advice ném lỗi, và hai advice phân loại không bị thu hẹp bởi type binding khác nhau. Nếu có transaction, cache, retry hoặc @Around, kiểm tra thứ tự interceptor: một fallback trong around advice có thể chuyển exception bên trong thành normal return ở tầng ngoài.

Quy trình kiểm chứng: xác nhận outcome thực của target; kiểm tra proxy và pointcut; kiểm tra tên/kiểu returning hoặc throwing; sau cùng đối chiếu metric business với method completion. Đừng dùng normal return làm bằng chứng transaction đã commit hoặc Future đã hoàn tất.

## 12. Checklist khi thiết kế Spring Aspect đo outcome

- [ ] Chỉ dùng `@AfterReturning` để ghi nhận **normal completion**, không coi mọi giá trị trả về là business success.
- [ ] Dùng `@AfterThrowing` cho exception thoát khỏi method execution; lựa chọn `Throwable` hay subtype có chủ đích.
- [ ] Dùng `@After` cho cleanup hoặc total completed, không dùng để khẳng định request thành công.
- [ ] Dùng `@Before` cho bước trước khi gọi, không kết luận outcome tại đây.
- [ ] Chỉ dùng `@Around` khi cần can thiệp flow hoặc giữ scope trước/sau cùng một invocation, và kiểm soát `proceed()`.
- [ ] Kiểm tra outcome `return null`, return object, checked và unchecked exception.
- [ ] Kiểm tra khi target tự catch exception và return fallback.
- [ ] Kiểm tra sự khác nhau giữa outcome của target và outcome mà **caller proxy** thấy khi có cache/retry/fallback.
- [ ] Test qua Spring-managed proxy, không dùng `new`/`this` để chứng minh AOP.
- [ ] Nếu aspect concurrent, dùng dữ liệu local mỗi invocation hoặc primitive thread-safe cho counters.
- [ ] Tránh advice throwing exception không cần thiết vì có thể thay đổi exception/result mà business code nhìn thấy.
- [ ] Với transaction, tách quy tắc rollback và business status khỏi khái niệm “after throwing”.

## 13. Kết luận

Trong Spring Aspect, ba “sự kiện sau method” mang ngữ nghĩa khác nhau:

- **`@AfterReturning`:** phương thức kết thúc bình thường; kết quả có thể là object, `null`, mã trạng thái từ chối, hoặc không có giá trị ở method `void`.
- **`@AfterThrowing`:** phương thức kết thúc bằng exception thoát ra ngoài; checked hay unchecked đều có thể quan sát nếu type binding phù hợp.
- **`@After`:** phương thức kết thúc theo bất kỳ đường nào và advice này đã được áp dụng; semantics như `finally`.

`@Around` là công cụ mạnh hơn: nó có thể tiếp tục, bỏ qua, lặp lại hoặc chuyển kết quả/exception, làm thay đổi outcome tại những vị trí khác nhau trong Spring interceptor chain. Vì vậy **định nghĩa rõ vị trí đo lường và business policy** trước khi gắn nhãn success/failure.

Để áp dụng đúng, cần đồng thời kiểm tra **pointcut**, **Spring-managed proxy boundary** và **outcome thực sự của invocation**. Không một annotation advice riêng lẻ nào thay thế được hiểu biết về cả ba yếu tố đó.

### Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`, binding và ordering.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): các loại advice và cách Spring áp dụng method-execution join point.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký `@Aspect` và bật Spring auto-proxy.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, self-invocation, proxy boundary.
- [Spring Framework — Declarative Transaction Rolling Back](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): exception types và rollback rules, độc lập với việc advice đo throwing completion.
