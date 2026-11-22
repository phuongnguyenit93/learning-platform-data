# Ảnh hưởng của ngoại lệ do chính advice phát sinh trong Spring AOP

## 1. Vì sao ngoại lệ bên trong advice đặc biệt nguy hiểm?

Trong Spring Framework, lời gọi tới một Spring bean có thể đi qua **một chuỗi các advisors/interceptors** trước khi đến method nghiệp vụ (*target method*). Mỗi advice do `@Aspect` khai báo cũng chạy trên đường đi này. Vì vậy, nếu **code trong advice tự ném exception**, kết quả caller quan sát được có thể khác hoàn toàn với kết quả target dự định trả về hoặc lỗi gốc target đã ném.

Các câu hỏi thực tế:

- Nếu một `@Before` advice ném lỗi, target có được gọi không?
- Target đã `return "OK"`, nhưng `@AfterReturning` bị lỗi khi ghi metric: caller nhận gì?
- Target ném `IllegalArgumentException`, nhưng `@AfterThrowing` ném tiếp `IllegalStateException`: lỗi nào đi tới client?
- `@After` như `finally` ném lỗi trên nhánh thành công và trên nhánh đang xử lý lỗi thì có gì khác?
- `@Around` bắt/đổi/ném exception từ `proceed()` có thể che mất lỗi ban đầu như thế nào?
- Một outer aspect có thể quan sát được lỗi từ advice bên trong hay không, và điều gì quyết định điều đó?

**Thông điệp quan trọng:** một advice không tự động trở thành “ngoài luồng” đối với đường trả về của lời gọi. Exception trong advice có thể **dừng phần thực thi phía trong, làm một normal return thành exceptional return, hoặc thay thế exception gốc**. Trong Spring AOP, hiệu quả cụ thể phụ thuộc **vị trí advice trong proxy interceptor chain**.

Bài tập trung vào **Spring Aspect (@AspectJ style trên Spring AOP proxy)**. Những kiến thức chung về ngoại lệ Java và AspectJ weaving chỉ nhắc đến khi cần phân biệt với hành vi thực tế của Spring.

## 2. Mô hình gọi qua proxy: nơi exception có thể xuất hiện

Một proxy có thể sắp xếp các interceptors thành những tầng lồng nhau:

```text
Caller
  |
  v
Spring AOP proxy
  |
  +-- Outer @Around: enter
        |
        +-- @Before
        |     |
        |     +-- nếu throw -> phần phía trong chưa chạy
        |
        +-- Target business method
        |     |
        |     +-- return hoặc throw
        |
        +-- @AfterReturning / @AfterThrowing
        |     |
        |     +-- nếu advice này throw -> kết quả phía ngoài thay đổi
        |
        +-- @After (finally)
        |     |
        |     +-- nếu throw -> có thể che cả return lẫn lỗi cũ
        |
        +-- Outer @Around: return / catch / finally
  |
  v
Caller nhận value hoặc exception cuối cùng
```

Sơ đồ là **mô hình khái niệm**, không phải thứ tự tuyệt đối của mọi cấu hình. Từng `@Aspect` có mức precedence, có thể thêm transaction/cache/async advisor, và advice có thể short-circuit hoặc gọi `proceed()` nhiều lần. Với một lời gọi nhất định, chỉ các advisors có pointcut phù hợp mới tham gia.

Điều chắc chắn của cơ chế Java call stack: **exception được ném trong một tầng sẽ đi ra phía ngoài cho tới khi có tầng bắt nó**. Nếu một tầng trong quá trình thoát lại ném exception mới, tầng ngoài có thể chỉ nhìn thấy exception mới ấy.

### Ví dụ tuyến lỗi đơn giản

```text
Target:         throw BusinessException("business failed")
After advice:   throw TelemetryException("log unavailable")
Outer advice:   catch TelemetryException
Caller:         nhận TelemetryException
```

Nếu `TelemetryException` không giữ `BusinessException` làm `cause` hoặc `suppressed`, thông tin nguyên nhân gốc có thể rất khó truy vết. Đó là lý do việc ném lỗi từ logging, metrics hay cleanup advice phải được thiết kế có chủ đích.

## 3. Bảng tổng quan theo từng loại advice

Bảng giả định code advice thực sự được kích hoạt, có pointcut phù hợp và không có tầng phía ngoài chuyển lỗi thành fallback:

| Advice tự ném exception | Điều xảy ra với target | Caller thường thấy |
| --- | --- | --- |
| `@Before` | Nếu advice throw **trước khi đi vào target**, target không được thực thi | Exception từ `@Before` |
| `@AfterReturning` | Target **đã return bình thường**; advice chạy rồi throw | Exception từ `@AfterReturning` thay vì return value |
| `@AfterThrowing` | Target **đã ném lỗi phù hợp**; advice nhận lỗi rồi throw lỗi khác | Exception mới do advice ném, trừ khi tầng ngoài biến đổi |
| `@After` | Phần thực thi bên trong đã đi tới nhánh finally; advice throw | Có thể che normal return **hoặc** exception ban đầu |
| `@Around` trước `proceed()` | Chưa gọi phần chain bên trong, target có thể không chạy | Exception từ around advice |
| `@Around` sau `proceed()` trả bình thường | Target/inner chain có thể đã hoàn thành bình thường | Exception từ around advice |
| `@Around` catch rồi throw mới | Target/inner chain đã phát sinh Throwable | Throwable mới, có thể giữ lỗi cũ làm cause |
| `@Around` catch rồi return fallback | Target/inner chain đã có lỗi | Caller nhận fallback, không nhận lỗi gốc nếu outer chain không phát sinh lỗi khác |

Bảng này **không** nói rằng advice luôn bị ép phải ném lại ngoại lệ gốc. Trong Java, `@Before`/`@AfterReturning`/`@AfterThrowing`/`@After` thường là method `void`; nhưng body của chúng vẫn có thể ném unchecked exception. Spring không tự cô lập mọi lỗi advice khỏi caller.

### Ba điều phải luôn tách

1. **Lỗi target:** exception được target method tạo ra khi thực thi nghiệp vụ.
2. **Lỗi advice:** exception phát sinh từ chính việc kiểm tra quyền, ghi log, tăng metric, cleanup, transform hoặc retry.
3. **Lỗi caller quan sát:** exception cuối cùng thoát khỏi **toàn bộ Spring proxy chain**. Đây có thể là lỗi target, lỗi advice, wrapper exception hoặc không có lỗi nếu outer around đã trả fallback.

Không dùng `@AfterThrowing` để suy luận đơn giản rằng “mọi exception caller nhận đều do target ném”.

## 4. `@Before` ném exception: target không được gọi

Ví dụ một advice kiểm tra điều kiện trước method execution:

```java
@Aspect
public class PermissionAspect {
    @Before("execution(* com.example.app.service..*.submit(..))")
    public void check() {
        throw new IllegalStateException("permission unavailable");
    }
}
```

Đây là **snippet trong Spring `@Aspect` bean**, chưa phải chương trình độc lập. Nếu advice khớp và ném lỗi trước khi invocation được tiếp tục:

```text
CLIENT -> Spring proxy -> @Before throws
                             |
                             +--> TARGET.submit() không chạy
                             |
                             +--> exception đi ra bên ngoài
```

Điều này có thể **là chủ đích** nếu advice thực hiện authorization và dùng exception để từ chối lời gọi. Nhưng cũng có thể là **lỗi ngoài ý muốn** khi advice chỉ có nhiệm vụ log, ví dụ `logger.info(...)` hoặc một formatter tự ném exception.

### Có chắc mọi `@After` khác vẫn chạy khi `@Before` throw?

**Không.** Nếu `@Before` nằm ở tầng ngoài và ném lỗi **trước khi một after/finally interceptor ở phía trong được gọi**, interceptor phía trong chưa được tham gia nên không thể tự chạy cleanup. Ngược lại, một outer `@Around` đã bắt đầu trước before advice có thể dùng `try/finally` để ghi nhận sự cố.

Thứ tự giữa các advice trong Spring được quyết định bởi precedence và nesting; không được hiểu `@After` là “global finally bắt mọi lỗi ở bất kỳ tầng nào”.

Nếu cần áp dụng một hành động cleanup **ngay cả khi precondition trước target thất bại**, đặt cleanup ở một tầng ngoài đã thực sự được enter, và test thứ tự advisor cụ thể.

### Kiểm tra bảo toàn side effects

Nếu `@Before` thất bại trước target, target không thực hiện side effects của method đó. Nhưng một advice **ở tầng ngoài** có thể đã làm side effects trước khi lỗi xuất hiện, ví dụ ghi audit request-start hoặc mở span tracing. Không dùng câu “target không chạy” để khẳng định “không có gì đã xảy ra”.

## 5. `@AfterReturning` ném exception: biến thành công thành thất bại

`@AfterReturning` được gọi **chỉ khi phần method execution tương ứng trả về bình thường**. Nó có thể bind giá trị trả về:

```java
@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.complete(..))",
    returning = "result",
    argNames = "result"
)
public void recordSuccess(String result) {
    System.out.println("BUSINESS RETURNED " + result);
    throw new IllegalStateException("metrics unavailable");
}
```

Đây là **snippet minh họa**. Sau khi target thực thi và trả `"OK"`:

```text
Target.complete()       -> return "OK"
@AfterReturning         -> throw IllegalStateException
Outer caller            -> nhận IllegalStateException, không nhận "OK"
```

**Đây là một bẫy quan trọng:** business operation đã thực thi thành công, có thể đã ghi dữ liệu hoặc gửi thông điệp, nhưng client lại nghĩ operation thất bại vì telemetry advice tự ném lỗi.

Hệ quả:

- Client có thể retry request vì nhận 5xx; nếu operation không idempotent, retry có thể tạo **duplicate side effects**.
- Nếu có transaction advisor, exception từ advice **có thể ảnh hưởng transaction** tùy vị trí tương đối của advice và transaction interceptor. Không suy rằng dữ liệu đã commit hoặc rollback chỉ từ dòng log.
- `@AfterReturning` không có chức năng thay return object bằng cách `return` một value từ advice; nhưng **throw exception** vẫn làm đường thoát kết quả trở thành exceptional nếu không có outer handler.

### Advice ném sau khi target return khác exception target

Một outer `@Around` nhìn thấy exception từ `proceed()` trong trường hợp này có thể bắt `IllegalStateException("metrics unavailable")`, dù target hoàn toàn không ném lỗi. Vì vậy outer observer cần phân biệt **lỗi infrastructure/advice** với **lỗi nghiệp vụ**, thông qua typing, cause chain, structured events hoặc design logging thích hợp.

**Spring documentation lưu ý:** `@AfterThrowing` đi kèm trong cùng aspect **không được coi là callback bắt lỗi do một `@AfterReturning` khác trong aspect đó ném ra**. Nếu muốn giám sát lỗi từ toàn chain, thiết kế một outer `@Around` rõ ràng.

## 6. `@AfterThrowing` ném exception mới: che lỗi nghiệp vụ gốc

Giả sử target method ném:

```java
throw new IllegalArgumentException("invalid order");
```

Một after-throwing advice có thể bind throwable gốc:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.placeOrder(..))",
    throwing = "original",
    argNames = "original"
)
public void onFailure(IllegalArgumentException original) {
    System.out.println("FAILED " + original.getMessage());
    throw new IllegalStateException("audit system failed", original);
}
```

Đây là snippet, chưa phải project độc lập. Khi advice ném exception mới, Java control flow thoát **từ advice** bằng `IllegalStateException`:

```text
Target:           IllegalArgumentException("invalid order")
Advice:           receives original
Advice:           throws IllegalStateException("audit system failed", original)
Caller/outer:     sees IllegalStateException
Cause chain:      IllegalArgumentException -> "invalid order"
```

So với việc ném:

```java
throw new IllegalStateException("audit system failed");
```

việc dùng constructor có `cause` giúp giữ đường truy tìm lỗi ban đầu. Nhưng **lựa chọn tốt hơn** đối với một advice chỉ phục vụ audit/log là không ném exception mới làm mất lỗi nghiệp vụ nếu telemetry hỏng.

### Tên `throwing` và kiểu ngoại lệ vẫn quan trọng

- `throwing = "original"` phải khớp tên tham số advice; `argNames = "original"` giúp binding rõ ràng.
- Kiểu `IllegalArgumentException` chỉ match runtime throwable thuộc class đó hoặc subclass.
- Nếu target ném `IOException` và advice chỉ nhận `IllegalArgumentException` thì advice không chạy, nên nó **không thể ném lỗi thứ cấp từ body advice đó** cho trường hợp ấy.
- Nếu dùng `Throwable original`, advice có thể nhận cả `Error` — cân nhắc rất kỹ trước khi gọi hệ thống log/metric có nguy cơ lỗi trong đường xử lý lỗi nghiêm trọng.

### Vì sao `@AfterThrowing` không phải “bộ xử lý mọi lỗi của proxy”?

Tài liệu Spring Framework 6.2 phân biệt rõ: advice này phục vụ **exception từ join point (user-declared target method)**, không được hiểu như general callback bắt exception phát sinh từ các companion `@After` hoặc `@AfterReturning` trong cùng `@Aspect`. Thứ tự advisor/nesting là lý do một exception mới từ advice **không nhất thiết** đi qua mọi `@AfterThrowing` khác.

Muốn xử lý lỗi từ toàn chain, sử dụng một **outer around interceptor/aspect** được xếp thứ tự rõ ràng, rồi kiểm thử những đường gọi thực tế.

## 7. `@After` ném exception: rủi ro của logic trong finally

Trong Spring AOP, `@After` có ngữ nghĩa **after-finally advice**. Nó chạy khi method execution tương ứng kết thúc bình thường hoặc bằng exception:

```java
@After("execution(* com.example.app.service..*.store(..))")
public void release() {
    System.out.println("RELEASING");
    throw new IllegalStateException("cleanup failed");
}
```

Snippet trên cố ý chứa lỗi để minh họa hai nhánh:

### 7.1. Target đã thành công

```text
Target.store()     -> return "STORED"
@After.release()   -> throw IllegalStateException("cleanup failed")
Caller             -> nhận cleanup exception thay vì "STORED"
```

Giống trường hợp `@AfterReturning`, target có thể đã làm side effects nhưng caller nhận lỗi từ việc cleanup.

### 7.2. Target đã ném exception

```text
Target.store()     -> throw IllegalArgumentException("storage rejected")
@After.release()   -> throw IllegalStateException("cleanup failed")
Caller             -> nhận cleanup exception
Original exception -> có nguy cơ không còn trong cause chain
```

Đây là ngữ nghĩa tương tự khi một Java `finally` block ném exception mới và che exception đang lan truyền. Với `@After`, bạn **không có thuộc tính `throwing`** để tự nhận exception gốc. Vì thế, nếu code `@After` throw không gắn nguyên nhân cũ, thông tin lỗi gốc rất dễ bị mất trên đường đi ra client.

### Không được nhầm với `try-with-resources`

Java `try-with-resources` có quy tắc riêng để giữ lỗi từ `try` là primary exception và đưa lỗi `close()` vào **suppressed exceptions**. Spring `@After` tự ném exception **không tự động áp dụng cơ chế suppressed như try-with-resources**. Nếu cần giữ cả hai lỗi, phải thiết kế chính sách giữ cause/suppressed rõ ràng ở tầng có cả hai throwable, ví dụ một outer `@Around`.

### Cleanup nên fail-safe trong phạm vi yêu cầu

Một advice chỉ ghi metric hoặc dọn trạng thái tracing thường nên tránh làm thất bại business operation chỉ vì hệ thống telemetry tạm thời unavailable. Nhưng **không được nuốt mọi lỗi một cách máy móc**: nếu advice thực sự chịu trách nhiệm enforce một invariant bắt buộc, failure cần một contract nghiệp vụ rõ ràng và được test.

## 8. `@Around`: có thể bắt, chuyển đổi, ném mới hoặc nuốt exception

`@Around` nhận `ProceedingJoinPoint` và có quyền điều khiển lời gọi qua `proceed()`. Vì vậy, nó ảnh hưởng mạnh nhất tới exception flow.

### 8.1. Giữ nguyên lỗi và chạy finally

```java
@Around("execution(* com.example.app.service..*.dispatch(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        System.out.println("TRACE finished");
    }
}
```

Nếu phần phía trong ném exception và `finally` không ném thêm lỗi, exception gốc được propagate. Nếu phần phía trong trả bình thường, giá trị đó cũng được giữ.

### 8.2. Chuyển exception nhưng giữ cause

```java
@Around("execution(* com.example.app.service..*.dispatch(..))")
public Object wrapFailure(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalArgumentException original) {
        throw new IllegalStateException(
            "dispatch failed in proxy chain", original
        );
    }
}
```

Ở đây `IllegalStateException` được caller nhận; `original` còn nằm trong `getCause()`. Cần bảo đảm kiểu mới thực sự phù hợp với contract của service/API, không wrap tùy tiện rồi làm lỗi client khó xử lý.

### 8.3. Catch rồi return fallback

```java
@Around("execution(* com.example.app.service..*.lookup(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException original) {
        return "FALLBACK";
    }
}
```

Snippet này hợp lý **chỉ khi method được advice trả kiểu tương thích `String`** và contract nghiệp vụ cho phép fallback. Nếu `pjp.proceed()` ném exception từ một advice phía trong, `catch` ở đây cũng có thể bắt lỗi đó, **không chỉ lỗi target**.

**Cảnh báo:** catch rộng mọi `RuntimeException` trong around advice có thể vô tình biến lỗi authorization, validation, transaction hoặc telemetry thành success. Khi cần fallback, hãy match đúng class exception và kiểm soát phạm vi pointcut.

### 8.4. Tự ném lỗi trước `proceed()`

```java
@Around("execution(* com.example.app.service..*.lookup(..))")
public Object deny(ProceedingJoinPoint pjp) {
    throw new IllegalStateException("precondition failed");
}
```

Target không được gọi vì advice không `proceed()`. Điều này có thể có chủ đích (policy/security), nhưng không phù hợp cho một aspect chỉ ghi log.

### 8.5. Ném lỗi sau `proceed()` thành công

```java
@Around("execution(* com.example.app.service..*.lookup(..))")
public Object postValidate(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    if (result == null) {
        throw new IllegalStateException("unexpected null");
    }
    return result;
}
```

Trong trường hợp này, target có thể đã hoàn thành bình thường, nhưng caller nhận exception do post-validation advice. Hãy phân biệt **đánh giá kết quả của advice** và **business method success** trong logs/metrics.

## 9. Demo runnable: năm loại lỗi advice và một lời gọi thành công

Ví dụ hoàn chỉnh sử dụng **Java 17+, Maven, Spring Framework 6.2.19**. Một Spring bean có các methods cố ý riêng biệt để mỗi method chỉ kích hoạt **một loại failing advice** trong aspect bên trong:

1. `scenarioBefore()`: `@Before` ném lỗi, target không chạy.
2. `scenarioReturning()`: target trả bình thường; `@AfterReturning` ném lỗi.
3. `scenarioThrowing()`: target ném `IllegalArgumentException`; `@AfterThrowing` ném `IllegalStateException` mới **có cause gốc**.
4. `scenarioFinallyNormal()`: target trả bình thường; `@After` ném lỗi.
5. `scenarioFinallyError()`: target ném lỗi; `@After` ném lỗi mới **che mất lỗi gốc**.
6. `scenarioAround()`: target ném lỗi; `@Around` của inner aspect bắt và wrap thành lỗi khác.
7. `scenarioHealthy()`: không có failing advice bên trong, nên target trả bình thường.

Một aspect quan sát bên ngoài mang `@Order(1)`; aspect cố ý gây lỗi bên trong mang `@Order(2)`. Do đó log của **outer around** cho biết exception nào thực sự thoát khỏi nội bộ. **Không chạy riêng các snippet minh họa trước đó cùng demo**, vì chúng có thể tạo advisor bổ sung và thay đổi trace.

### 9.1. Cấu trúc project

```text
spring-aop-advice-exceptions/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AdviceFailureDemo.java
```

### 9.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-advice-exceptions</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.19</version>
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
                    <mainClass>demo.AdviceFailureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. Tệp `src/main/java/demo/AdviceFailureDemo.java`

```java
package demo;

import java.util.function.Supplier;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.core.annotation.Order;

public class AdviceFailureDemo {

    public interface ScenarioService {
        String scenarioBefore();
        String scenarioReturning();
        String scenarioThrowing();
        String scenarioFinallyNormal();
        String scenarioFinallyError();
        String scenarioAround();
        String scenarioHealthy();
    }

    public static class ScenarioServiceImpl implements ScenarioService {
        @Override
        public String scenarioBefore() {
            System.out.println("TARGET before");
            return "BEFORE-OK";
        }

        @Override
        public String scenarioReturning() {
            System.out.println("TARGET returning");
            return "RETURNING-OK";
        }

        @Override
        public String scenarioThrowing() {
            System.out.println("TARGET throwing");
            throw new IllegalArgumentException("business throwing");
        }

        @Override
        public String scenarioFinallyNormal() {
            System.out.println("TARGET finally normal");
            return "FINALLY-OK";
        }

        @Override
        public String scenarioFinallyError() {
            System.out.println("TARGET finally error");
            throw new IllegalArgumentException("business finally");
        }

        @Override
        public String scenarioAround() {
            System.out.println("TARGET around");
            throw new IllegalArgumentException("business around");
        }

        @Override
        public String scenarioHealthy() {
            System.out.println("TARGET healthy");
            return "HEALTHY";
        }
    }

    @Aspect
    @Order(1)
    public static class OuterObserverAspect {

        @Around("execution(* demo..*.scenario*(..))")
        public Object observe(ProceedingJoinPoint pjp) throws Throwable {
            String name = pjp.getSignature().getName();
            System.out.println("OUTER enter " + name);

            try {
                Object result = pjp.proceed();
                System.out.println("OUTER returned " + result);
                return result;
            } catch (Throwable ex) {
                System.out.println(
                    "OUTER caught "
                        + ex.getClass().getSimpleName()
                        + ":" + ex.getMessage()
                );
                throw ex;
            }
        }
    }

    @Aspect
    @Order(2)
    public static class FailingAdviceAspect {

        @Before("execution(* demo..*.scenarioBefore(..))")
        public void failBefore() {
            System.out.println("ADVICE before throws");
            throw new IllegalStateException("before advice failed");
        }

        @AfterReturning(
            pointcut = "execution(* demo..*.scenarioReturning(..))",
            returning = "result",
            argNames = "result"
        )
        public void failAfterReturn(String result) {
            System.out.println(
                "ADVICE afterReturning result=" + result
            );
            throw new IllegalStateException("returning advice failed");
        }

        @AfterThrowing(
            pointcut = "execution(* demo..*.scenarioThrowing(..))",
            throwing = "original",
            argNames = "original"
        )
        public void failAfterThrow(IllegalArgumentException original) {
            System.out.println(
                "ADVICE afterThrowing original="
                    + original.getMessage()
            );
            throw new IllegalStateException(
                "throwing advice failed", original
            );
        }

        @After("execution(* demo..*.scenarioFinally*(..))")
        public void failAfterFinally() {
            System.out.println("ADVICE afterFinally throws");
            throw new IllegalStateException("after advice failed");
        }

        @Around("execution(* demo..*.scenarioAround(..))")
        public Object failAround(ProceedingJoinPoint pjp)
                throws Throwable {
            System.out.println("ADVICE around enters");
            try {
                return pjp.proceed();
            } catch (IllegalArgumentException original) {
                System.out.println(
                    "ADVICE around caught " + original.getMessage()
                );
                throw new IllegalStateException(
                    "around advice failed", original
                );
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {

        @Bean
        public ScenarioService scenarioService() {
            return new ScenarioServiceImpl();
        }

        @Bean
        public OuterObserverAspect outerObserverAspect() {
            return new OuterObserverAspect();
        }

        @Bean
        public FailingAdviceAspect failingAdviceAspect() {
            return new FailingAdviceAspect();
        }
    }

    private static void runCase(
            String label, Supplier<String> operation) {

        System.out.println("=== " + label + " ===");
        try {
            System.out.println("CLIENT value=" + operation.get());
        } catch (RuntimeException ex) {
            System.out.println(
                "CLIENT exception="
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage()
            );

            Throwable cause = ex.getCause();
            if (cause != null) {
                System.out.println(
                    "CLIENT cause="
                        + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage()
                );
            }
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            ScenarioService service =
                    context.getBean(ScenarioService.class);

            System.out.println(
                "AOP_PROXY=" + AopUtils.isAopProxy(service)
            );
            System.out.println(
                "JDK_PROXY=" + AopUtils.isJdkDynamicProxy(service)
            );

            runCase("before", service::scenarioBefore);
            runCase("returning", service::scenarioReturning);
            runCase("throwing", service::scenarioThrowing);
            runCase("finally normal", service::scenarioFinallyNormal);
            runCase("finally error", service::scenarioFinallyError);
            runCase("around", service::scenarioAround);
            runCase("healthy", service::scenarioHealthy);
        }
    }
}
```

**Điểm cần đọc kỹ:** tất cả method references `service::scenarioBefore` ... đều gọi **bean reference do context cấp**, không gọi trực tiếp `new ScenarioServiceImpl()`. Spring đang bật AOP auto-proxy và class implement interface, nên JDK proxy phù hợp. `@Order(1)` thấp hơn về giá trị số (cao hơn về precedence) so với `@Order(2)`, vì vậy observer ở ngoài failing aspect khi pointcuts cùng khớp.

### 9.4. Chạy ứng dụng

Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Các dòng stdout do chương trình in theo logic được trình bày** (không tính log Maven hoặc Spring):

```text
AOP_PROXY=true
JDK_PROXY=true
=== before ===
OUTER enter scenarioBefore
ADVICE before throws
OUTER caught IllegalStateException:before advice failed
CLIENT exception=IllegalStateException:before advice failed
=== returning ===
OUTER enter scenarioReturning
TARGET returning
ADVICE afterReturning result=RETURNING-OK
OUTER caught IllegalStateException:returning advice failed
CLIENT exception=IllegalStateException:returning advice failed
=== throwing ===
OUTER enter scenarioThrowing
TARGET throwing
ADVICE afterThrowing original=business throwing
OUTER caught IllegalStateException:throwing advice failed
CLIENT exception=IllegalStateException:throwing advice failed
CLIENT cause=IllegalArgumentException:business throwing
=== finally normal ===
OUTER enter scenarioFinallyNormal
TARGET finally normal
ADVICE afterFinally throws
OUTER caught IllegalStateException:after advice failed
CLIENT exception=IllegalStateException:after advice failed
=== finally error ===
OUTER enter scenarioFinallyError
TARGET finally error
ADVICE afterFinally throws
OUTER caught IllegalStateException:after advice failed
CLIENT exception=IllegalStateException:after advice failed
=== around ===
OUTER enter scenarioAround
ADVICE around enters
TARGET around
ADVICE around caught business around
OUTER caught IllegalStateException:around advice failed
CLIENT exception=IllegalStateException:around advice failed
CLIENT cause=IllegalArgumentException:business around
=== healthy ===
OUTER enter scenarioHealthy
TARGET healthy
OUTER returned HEALTHY
CLIENT value=HEALTHY
```

Đây là **stdout dự kiến từ code**, không phải tuyên bố đã thực thi Maven trong một runtime thực tế. Demo chỉ dùng các beans/aspects đã định nghĩa ở trên. Các logs do framework hoặc Maven phát sinh không thuộc chuỗi dự kiến.

### 9.5. Phân tích vì sao trace có thứ tự này

**Case `before`:** outer around đã chạy và in `OUTER enter`. Failing before advice ném lỗi ngay, nên **không có dòng `TARGET before`**. Observer phía ngoài bắt lỗi do advice và caller nhận lỗi đó.

**Case `returning`:** target trả thành công (có dòng `TARGET returning`), after-returning nhận `"RETURNING-OK"` rồi ném lỗi. Observer và caller thấy **returning advice failed**, không nhận `RETURNING-OK`. Điều này rất nguy hiểm nếu target đã có side effect.

**Case `throwing`:** target ném `IllegalArgumentException("business throwing")`, inner after-throwing nhận lỗi gốc rồi ném `IllegalStateException("throwing advice failed", original)`. Outer observer nhìn thấy lỗi mới, nhưng client vẫn truy ngược lỗi gốc qua `getCause()`.

**Case `finally normal`:** target hoàn thành bình thường, sau đó `@After` ném lỗi. Caller nhận failure, không nhận `FINALLY-OK`. Việc “finally” chạy sau return không có nghĩa nó vô hại với return path.

**Case `finally error`:** target ném `IllegalArgumentException("business finally")` nhưng `@After` ném `IllegalStateException("after advice failed")`. Vì code advice không preserve original, client không có dòng `CLIENT cause`. Đây là ví dụ **mất nguyên nhân gốc**.

**Case `around`:** target ném lỗi nghiệp vụ; inner around bắt rồi wrap có cause; outer nhận wrapper. Không có vấn đề mất cause vì code giữ `original`.

**Case `healthy`:** không có failing advice áp dụng cho method này; observer bên ngoài thấy target return bình thường. Dòng `OUTER returned HEALTHY` đối chiếu với sáu nhánh lỗi, giúp nhận ra outer observer không phải nguyên nhân gây failure.

### 9.6. Khi một method nhận nhiều failing advices thì sao?

Demo tách method theo loại advice **để kết quả rõ và không phụ thuộc thứ tự của nhiều advice cùng loại**. Trong ứng dụng thật, nếu nhiều advice cùng match một method, phải phân tích thứ tự nesting.

Ví dụ với hai aspects:

```text
OuterAspect @Order(1)
    |
    +-- @Around
          |
          +-- InnerAspect @Order(2)
                |
                +-- @AfterReturning hoặc @AfterThrowing
                +-- @After
                |
                +-- Target
```

Nếu inner advice ném exception, outer around có thể bắt exception đó vì `pjp.proceed()` bao trùm toàn bộ chain phía trong. Nếu **outer** advice lại ném exception mới sau khi nó đã `proceed()`, inner advice đã kết thúc trước đó không tự chạy lại để quan sát lỗi của outer.

Đừng giả định thứ tự dòng log khi một aspect chứa nhiều `@After` cùng loại chỉ dựa vào thứ tự khai báo source; tài liệu Spring không bảo đảm ordering như vậy.

## 10. Phân biệt “lỗi advice” và “lỗi target” trong hệ thống lớn

### 10.1. Dùng kiểu exception và cause chain

Một custom exception dành cho lỗi advice có thể phân biệt nguồn:

```java
public class AdviceInfrastructureException
        extends RuntimeException {

    public AdviceInfrastructureException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **class minh họa độc lập**. Không cần thiết phải khai báo exception mới cho mọi advice nhỏ, nhưng nếu hệ thống thật sự muốn propagate infrastructure failure, một kiểu rõ nghĩa và cause chain đầy đủ giúp:

- Phân biệt lỗi nghiệp vụ với lỗi telemetry/infrastructure.
- Tránh retry business operation sai lý do.
- Dễ tạo logging/alert rules.
- Giữ được stack trace của cả advice và target khi có lỗi gốc.

**Tuy nhiên, typed wrapper không thay thế quyết định thiết kế quan trọng hơn:** liệu một lỗi logging/metrics không thiết yếu có nên làm hỏng business call hay không?

### 10.2. Kiểm tra exception tại outer boundary

Một outer around có thể ghi thông tin context của exception:

```java
@Around("execution(public * com.example.app.service..*.*(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (Throwable failure) {
        System.out.println(
            "FAILED " + pjp.getSignature().toShortString()
                + " with " + failure.getClass().getSimpleName()
        );
        throw failure;
    }
}
```

Đây là **snippet** cần aspect bean riêng, đúng pointcut và ordering. Nó quan sát exception từ **phần chain nằm bên trong** nó. Nó không phải universal observer cho mọi bean hoặc mọi lỗi JVM nếu Spring proxy không được gọi.

Không suy rằng exception từ observer luôn là “target failure”; có thể là error của before/after/around advice khác ở phía trong.

### 10.3. Giữ nguyên Throwable bằng `throw failure`

Trong observer snippet, `throw failure;` ném lại đúng object đang có, không tạo exception khác. Nếu code ghi log thành công, caller vẫn nhận same throwable. Đây thường là lựa chọn an toàn khi trách nhiệm của aspect chỉ là giám sát.

Một ngôn ngữ quan trọng trong production logs:

- `method execution observed as failed` không có nghĩa lỗi do target.
- `proxy invocation failed` chính xác hơn khi nguyên nhân có thể là advice.
- `business rejected` chỉ nên dùng khi có bằng chứng từ service contract/type lỗi nghiệp vụ.

## 11. Thiết kế advice an toàn: khi nào nuốt lỗi, khi nào propagate?

Không có quy tắc “catch mọi exception trong advice” áp dụng cho mọi yêu cầu. Phải xét **mục đích advice**.

### Trường hợp không thiết yếu: logging hoặc metric best-effort

Một cách phòng ngừa:

```java
@Before("execution(* com.example.app.service..*.*(..))")
public void before(JoinPoint jp) {
    try {
        telemetryRecordSafely(jp.getSignature().toShortString());
    } catch (RuntimeException telemetryFailure) {
        // Gửi lỗi tới fallback diagnostic path nếu có;
        // không che business flow do telemetry không thiết yếu.
    }
}
```

Đây là **mẫu ý tưởng chưa biên dịch độc lập**, vì cần định nghĩa `telemetryRecordSafely(...)` và đăng ký `@Aspect` bean. Nếu bắt lỗi để bảo vệ business call, phải có **fallback reporting** hoặc health-monitoring phù hợp; nuốt lỗi rồi không ai biết logging/metrics đang hỏng sẽ gây mù quan sát.

Không catch `Throwable` và nuốt cả `OutOfMemoryError`/`StackOverflowError` chỉ để giữ một request “thành công”; những lỗi nghiêm trọng thường không nên được che giấu.

### Trường hợp thiết yếu: authorization hoặc invariant check

Nếu aspect chịu trách nhiệm **từ chối truy cập**, ném exception có thể chính là hành vi chủ đích:

```java
@Before("execution(* com.example.app.service..*.sensitive(..))")
public void denyIfNotAllowed() {
    if (!accessAllowed()) {
        throw new SecurityException("access denied");
    }
}
```

Đây là snippet có `accessAllowed()` cần được cài đặt phù hợp. Khi không đủ quyền, ngăn target chạy là chính xác. Không catch exception này rồi return success chỉ để tránh lỗi xuất hiện ở client.

**Cần phân biệt:** exception được thiết kế làm **policy decision** và exception ngoài ý muốn do telemetry/database/logger bị lỗi. Hai trường hợp không nên áp cùng một recovery policy.

### Trường hợp cleanup thất bại

Một `@After` chịu trách nhiệm cleanup cần làm rõ:

- Cleanup bắt buộc để bảo đảm consistency hay chỉ giải phóng phụ trợ?
- Nếu target đã thất bại, có muốn giữ exception gốc làm **primary** và ghi cleanup failure ở **suppressed/cause**?
- Nếu target thành công nhưng cleanup fail, có được báo business success không?
- Cleanup có thể retry/idempotent không?
- Có nên thực hiện resource management tại code business/try-with-resources thay vì ở một `@After` không có trực tiếp exception gốc?

Đừng mặc định dùng `@After` cho những tài nguyên mà lifecycle cần sự đảm bảo transactional/ownership cụ thể bên trong business method.

## 12. Nếu cần giữ cả lỗi target và lỗi cleanup

Một outer `@Around` có thể chủ động giữ cả primary và secondary exception khi **nó có quyền quản lý cả hai**:

```java
@Around("execution(* com.example.app.service..*.operate(..))")
public Object carefullyCleanup(ProceedingJoinPoint pjp)
        throws Throwable {

    Throwable primary = null;

    try {
        return pjp.proceed();
    } catch (Throwable failure) {
        primary = failure;
        throw failure;
    } finally {
        try {
            releaseOwnedResource();
        } catch (Throwable cleanupFailure) {
            if (primary != null) {
                if (cleanupFailure != primary) {
                    primary.addSuppressed(cleanupFailure);
                }
            } else {
                throw cleanupFailure;
            }
        }
    }
}
```

Đây là **pseudocode Java hợp lệ trong một advice body**, cần triển khai `releaseOwnedResource()` và aspect bean; dùng như mẫu tư duy, không tự động copy vào mọi hệ thống. Nó có chủ đích:

- Nếu phần chain bên trong ném lỗi, giữ **primary** và đính kèm lỗi cleanup trong `getSuppressed()`, thay vì mất primary.
- Nếu phần chain bên trong thành công nhưng cleanup thất bại, propagate cleanup failure vì không có primary lỗi khác.
- Tránh `addSuppressed` nếu cùng object throwable.

**Giới hạn:** code bắt `Throwable` chủ yếu để giữ và propagate, không để nuốt `Error`. Nếu `releaseOwnedResource()` không do aspect sở hữu lifecycle, đừng cố cleanup trong aspect.

Một lựa chọn đơn giản hơn là Java `try-with-resources` khi tài nguyên thuộc về **chính method business**, bởi Java có suppressed-exception semantics chuẩn cho lỗi đóng tài nguyên.

## 13. Interaction với thứ tự Spring advice

### 13.1. Precedence cùng aspect

Tài liệu Spring Framework 6.2 cho thứ tự precedence **từ cao đến thấp** giữa các loại advice thuộc cùng một `@Aspect`:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

Do `@After` dùng after-finally semantics, trên chiều thoát bình thường nó thực tế chạy **sau** `@AfterReturning`; trên chiều thoát lỗi chạy **sau** `@AfterThrowing`, khi những advice này thuộc cùng aspect và thỏa điều kiện.

Một exception ném từ một advice có thể thay đổi những tầng **bên ngoài** nhìn thấy gì, nhưng không làm các interceptors **đã đi qua** tự chạy lại.

### 13.2. Precedence giữa các aspects

`@Order(1)` có precedence cao hơn `@Order(2)`. Aspect có precedence cao hơn **vào trước, ra sau** trong các lời gọi lồng nhau. Vì vậy một outer `@Around` có thể bắt lỗi phát sinh từ target **lẫn các advice nằm bên trong**.

Khi không khai báo ordering giữa các aspects khác nhau mà chúng cùng match, thứ tự tương đối không được đảm bảo; không được dựa vào alphabetical class name hoặc thứ tự khai báo trong source.

### 13.3. Advice cùng loại trong cùng aspect

Hai `@After` cùng match một method, nhưng khai báo `first()` và `second()` trong cùng `@Aspect`, không có ordering contract dựa trên vị trí source. Nếu thứ tự ảnh hưởng kết quả/lỗi, gộp logic vào một advice method hoặc tách thành các aspects với `@Order` rõ ràng.

### 13.4. Outer aspect quan sát được gì?

| Vị trí lỗi | Outer around đã enter và bao phần lỗi? | Có thể catch trong outer? |
| --- | --- | --- |
| Target method phía trong | Có | Có |
| `@Before` phía trong | Có | Có |
| `@AfterReturning` phía trong | Có | Có |
| `@AfterThrowing` phía trong | Có | Có |
| `@After` phía trong | Có | Có |
| Advice nằm **bên ngoài** outer around | Không | Không |
| Một object khác không qua Spring AOP proxy | Không | Không |
| Task bất đồng bộ trên thread khác sau khi proxy đã trả | Không trực tiếp qua synchronous `proceed()` | Không thể giả định |

Chính vì vậy, tên “outer” chỉ có ý nghĩa khi **thứ tự chain đã được xác minh**.

## 14. Spring transaction, cache, async và retry: nơi lỗi advice gây nhầm lẫn

### 14.1. Transaction advisor và lỗi ném sau target

Với `@Transactional`, transaction behavior do một interceptor riêng quản lý. Nếu custom `@AfterReturning` ném exception:

- Nếu custom advice ở **bên trong transaction interceptor**, transaction interceptor có thể quan sát exceptional completion và quyết định rollback theo rollback rules.
- Nếu custom advice ở **bên ngoài transaction interceptor**, transaction interceptor có thể đã xử lý commit/rollback trước khi custom advice ném lỗi. Caller vẫn nhận exception, nhưng dữ liệu có thể đã commit.

Vì vậy, **không suy từ client nhận exception rằng transaction chắc chắn rollback**. Phải kiểm tra transaction advisor order, `rollbackFor`/`noRollbackFor` và integration test với database thật nếu tác động dữ liệu quan trọng.

### 14.2. Cache interceptor và advice thất bại

Nếu `@Cacheable` phục vụ cache hit, target method có thể không chạy. Một outer custom advice vẫn có thể quan sát kết quả từ cache, còn advice ở phía trong cache interceptor có thể không được enter. Nếu after-returning advice ném lỗi khi cache hit, client có thể thấy failure mặc dù cache có dữ liệu tốt.

Đừng coi `@AfterReturning` nhất thiết là bằng chứng “target method vừa chạy”.

### 14.3. Async interceptor

Với `@Async` hoặc `CompletableFuture`, một exception trong async task không đồng nhất với exception đồng bộ được outer advice bắt tại lời gọi proxy. Cần kiểm tra:

- Advisor có ở trước hay sau async boundary?
- Proxy method trả `Future`/`CompletableFuture` hay `void`?
- Lỗi phát sinh ngay khi scheduling hay sau đó khi task chạy?
- Caller quan sát exception bằng `join()`/`get()` hay handler async riêng?

Một outer synchronous `@Around` không thể tự bắt mọi lỗi hoàn thành muộn sau khi `proceed()` đã trả future bình thường.

### 14.4. Retry

Nếu một retry interceptor thử target nhiều lần, lỗi từ advice bên trong có thể **kích hoạt retry** như lỗi nghiệp vụ tùy cấu hình. Ví dụ target đã ghi dữ liệu rồi after-returning advice ném `IllegalStateException`; retry có thể gọi target một lần nữa, dẫn đến **duplicate writes**.

Ngược lại, nếu advice ở bên ngoài retry interceptor thì lỗi do advice ném sau khi retry đã hoàn tất có thể không được retry interceptor nhìn thấy.

Đặt câu hỏi: “Mình muốn retry lỗi nghiệp vụ, lỗi transport hay cả lỗi telemetry?”. Không gộp mọi `RuntimeException` thành retryable một cách mù quáng.

## 15. Ghi log, metrics và tracing mà không làm mất lỗi gốc

Một Spring aspect dùng trong production nên đáp ứng:

1. **Chỉ can thiệp đúng Spring bean và method cần thiết.** Pointcut quá rộng có thể intercept logger hoặc hạ tầng metrics của chính nó, gây vòng lặp.
2. **Không log secrets/PII.** `JoinPoint.getArgs()` có thể chứa passwords, tokens, payload nhạy cảm; chọn metadata cần thiết và mask có kiểm soát.
3. **Không ném lỗi chỉ vì formatter/toString() thất bại** nếu tracing là best-effort.
4. **Xác định contract của advice:** policy-enforcing (được phép fail closed) hay observability-only (nên cô lập lỗi thứ cấp).
5. **Bảo toàn cause chain** nếu quyết định wrap lỗi nghiệp vụ.
6. **Đừng lặng lẽ nuốt mọi exception** khiến hệ thống mất tín hiệu cần thiết; có thể báo lỗi telemetry qua channel riêng và health checks.
7. **Không giữ request state bằng mutable fields trong singleton aspect** nếu không có đồng bộ/hướng dẫn thread-safe rõ ràng.
8. **Không tự động retry cả target vì metric bị lỗi.** Đánh giá idempotency và transaction boundary.
9. **Sử dụng `@Order` khi exception flow giữa các aspects là yêu cầu.**
10. **Viết integration tests gọi bean từ context** để xác minh caller thấy gì, không chỉ mock lời gọi method advice trực tiếp.

### Khi log chính nó có thể ném exception

Các lỗi không chỉ từ network client. Một advice có thể fail khi:

- Gọi `toString()` của domain object (implementation tùy ý, có thể throw).
- Serialize object cyclic/không hợp lệ.
- Truy cập lazy-loaded property ngoài transaction.
- Truy cập một logger appender bị lỗi I/O.
- Ghi metric với tag cardinality cao hoặc backend client throw.
- Cast `JoinPoint.getArgs()[i]` sai kiểu hoặc truy cập index không tồn tại.
- Dùng `getCause().getMessage()` mà không kiểm tra `null`.
- Dùng shared mutable collection trong singleton aspect không thread-safe.

Vì vậy, “code advice chỉ có một dòng logging” không đồng nghĩa “advice không thể gây lỗi”.

## 16. Checklist debug khi client nhận exception bất ngờ

| Quan sát | Chẩn đoán ưu tiên |
| --- | --- |
| Không có log `TARGET`, chỉ có exception | `@Before` hay outer `@Around` đã throw/short-circuit trước target? |
| Target log thành công nhưng client nhận 5xx | `@AfterReturning` / `@After` / outer `@Around` có ném lỗi sau target không? |
| Target ném lỗi A nhưng caller nhận B | Advice có wrap hoặc override? Có giữ `cause`/`suppressed` không? |
| `@AfterThrowing` không log lỗi B từ companion advice | Spring không xem nó là global callback cho lỗi do các after advice khác ném |
| Cleanup log xuất hiện rồi lỗi gốc biến mất | `@After` có ném exception mới từ finally không? |
| Lỗi bị đổi thành success/fallback | `@Around` nào catch và return? |
| Có proxy nhưng advice không chạy | Pointcut không match, method không intercept được, self-invocation, hoặc order short-circuit |
| Retry operation dù target đã ghi xong | Lỗi after advice bị retry interceptor hiểu là lỗi target? |
| Spring transaction commit nhưng client nhận exception | Advice ném lỗi ngoài transaction interceptor sau commit? |
| Exception chỉ xuất hiện với Spring Boot, không có trong test thuần | Proxy strategy/advisor auto-configuration/ordering khác? |
| Outer log không thấy lỗi | Outer observer có thật sự bao advice/target lỗi theo `@Order`? |
| Async client không thấy lỗi ngay | Lỗi xảy ra sau proxy return trong future/executor? |

### Dụng cụ nhận diện proxy

```java
Object bean = context.getBean("scenarioService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

Đây là snippet, cần Spring context và import `org.springframework.aop.support.AopUtils`. Trong **demo đầy đủ**, bean đã có JDK dynamic proxy do interface và cấu hình cụ thể. Nhưng **có proxy** không chứng minh một advice nhất định match; cần kiểm tra cả pointcut và đường gọi.

## 17. Kiểm thử hành vi exception propagation

Khi viết test cho aspect, không chỉ assert target output. Test ít nhất:

- **Before error:** số lần target method thực thi bằng 0; caller thấy lỗi từ before advice.
- **After-returning error:** số lần target thực thi bằng 1 và trả nội bộ thành công; caller lại thấy lỗi advice.
- **After-throwing error:** target lỗi gốc, advice ném wrapper; caller nhận wrapper và `getCause()` đúng lỗi gốc.
- **After/finally trên normal return:** caller có thể thấy cleanup error.
- **After/finally trên target error:** kiểm tra có/không có cause gốc tùy chính sách của advice.
- **Around wrap:** caller nhận wrapper và exception gốc còn trong chain.
- **Healthy method:** không bị advice thất bại của method khác tác động.
- **Ordering:** observer bên ngoài nhận exception từ các advisors phía trong khi đã cấu hình đúng.
- **Không qua proxy:** lời gọi trên object `new` không kích hoạt Spring advice; self-invocation cần kiểm tra riêng.
- **Transaction/cache/retry:** test lại với các advisors thật nếu đó là ranh giới quan trọng.

Có thể dùng JUnit 5 với `assertThrows` và `assertSame` trên cause object, nhưng nên dùng một event recorder hoặc capture log để xác minh **thứ tự xảy ra**. Business return/exception đơn lẻ không chứng minh thứ tự toàn bộ advice.

Ví dụ ý tưởng:

```java
IllegalStateException seen = assertThrows(
    IllegalStateException.class,
    service::scenarioThrowing
);

assertEquals("throwing advice failed", seen.getMessage());
assertInstanceOf(IllegalArgumentException.class, seen.getCause());
assertEquals("business throwing", seen.getCause().getMessage());
```

Đây là **JUnit 5 snippet** cần dependencies/imports và Spring bean đã được lấy từ context, không phải file Java chạy độc lập. Test này xác minh rằng wrapper của after-throwing advice giữ lại exception gốc.

## 18. Câu hỏi tự kiểm tra

**1.** Target chưa chạy, `@Before` ném `SecurityException`. Caller có thể nhận gì?  
**Đáp án:** `SecurityException` từ before advice nếu không có outer handler; target không được chạy.

**2.** Target return `"OK"`, nhưng `@AfterReturning` ném `IllegalStateException`. Client chắc chắn thấy `"OK"` chứ?  
**Đáp án:** Không. Nếu lỗi advice không được catch, client nhận exception thay cho normal return.

**3.** Target ném `IllegalArgumentException`, `@AfterThrowing` ném `IllegalStateException` mới mà không có `cause`. Lỗi cũ có chắc còn trong `getCause()`?  
**Đáp án:** Không. Muốn preserve, dùng wrapper constructor có cause hoặc chính sách giữ suppressed ở tầng phù hợp.

**4.** `@After` ném lỗi trong đường `finally` khi target cũng đang ném lỗi. Exception nào có thể tới caller?  
**Đáp án:** Exception mới từ `@After` có thể che exception target.

**5.** `@AfterThrowing` cùng aspect có được đảm bảo bắt exception do companion `@AfterReturning` ném không?  
**Đáp án:** Không. Spring không định nghĩa nó là general exception callback cho companion after advice.

**6.** Một outer `@Around` có thể bắt lỗi `@Before` của aspect trong không?  
**Đáp án:** Có, nếu outer around đã enter, bao advice bên trong và `pjp.proceed()` ném lỗi đó.

**7.** Nếu outer `@Around` catch mọi `RuntimeException` và return `"FALLBACK"`, có thể vô tình nuốt lỗi authorization/advice không?  
**Đáp án:** Có. Catch cần hẹp và đúng contract.

**8.** Target đã ghi database thành công, client nhận lỗi từ metric advice, sau đó retry. Rủi ro gì?  
**Đáp án:** Duplicate side effects nếu operation không idempotent; transaction/retry ordering phải được kiểm tra.

**9.** Một aspect chứa hai `@After` cùng match. Source method nào viết trước thì chắc chạy trước?  
**Đáp án:** Không có ordering contract dựa trên vị trí khai báo Java source.

**10.** `@After` luôn chạy ngay cả khi `@Before` phía ngoài ném trước khi phần chain của after advice được enter?  
**Đáp án:** Không. Interceptor chưa được enter không thể chạy finally của nó.

**11.** Outer observer `@Order(1)` có thể quan sát lỗi do inner advice `@Order(2)` ném không?  
**Đáp án:** Có nếu cả hai match, outer around bao lời gọi phía trong và lỗi không bị xử lý trước khi ra tới observer.

**12.** Tại sao một lỗi log được wrap nên giữ `cause` nếu phải propagate?  
**Đáp án:** Để không mất thông tin lỗi gốc/stacktrace khi caller chỉ nhận wrapper exception.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`, exception semantics, `proceed()` và *Advice Ordering*. Chú ý ghi chú về giới hạn `@AfterThrowing` với lỗi do companion after advice ném.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): proxy boundary, JDK/CGLIB và self-invocation.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): aspect registration và Spring-managed auto-proxying.
- [Spring Framework 6.2 — Declarative Transactions](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative.html): transaction advice và quan hệ exception/transaction.
- [Spring Framework 6.2 — Understanding the Spring Transaction Abstraction](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html): nguyên tắc transaction và rollback tùy interceptor/configuration.
