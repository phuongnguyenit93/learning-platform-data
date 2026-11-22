# Hành vi khi gọi `proceed()` nhiều lần trong Spring AOP

## 1. Câu trả lời trọng tâm

Trong **Spring AOP**, phương thức `@Around` nhận một `ProceedingJoinPoint` và có quyền quyết định **có chuyển tiếp lời gọi tới phần còn lại của interceptor chain hay không, chuyển tiếp bao nhiêu lần và trả về kết quả nào**.

Tài liệu Spring Framework xác nhận: trong body của `@Around`, gọi `proceed()` **không lần nào, một lần hoặc nhiều lần đều hợp lệ**. Gọi nhiều lần là nền tảng của một số chính sách như **retry khi có lỗi tạm thời**. Tuy nhiên, nó **không phải** một thao tác quan sát vô hại: mỗi lần chuyển tiếp có thể khiến **target method và những advice nằm bên trong advice hiện tại thực thi thêm một lần**.

```java
@Around("execution(* com.example.service.PaymentService.charge(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    Object first = pjp.proceed();   // Một lượt vào phần chain phía trong.
    Object second = pjp.proceed();  // Một lượt nữa vào phần chain phía trong.
    return second;                  // Caller chỉ nhận kết quả advice trả ra.
}
```

Đây là **fragment minh họa**, cần imports và một class `@Aspect` được Spring đăng ký. Nếu cả hai lần `proceed()` thực sự đến target và target không lỗi, `charge()` có thể bị gọi **hai lần**, tạo **hai khoản phí** nếu nghiệp vụ không được thiết kế an toàn.

Do đó, câu trả lời đúng không chỉ là “được phép gọi nhiều lần” mà còn phải trả lời:

- Những advice nào chạy một lần, những advice nào chạy lại?
- Nếu lần đầu ném exception thì lần sau có thể chạy được không?
- Caller nhận return value của lần nào?
- Có tạo lại Spring bean, proxy hoặc transaction không?
- Có thực hiện lại các tác dụng phụ như ghi database, gửi email, publish event hoặc trừ tiền không?
- Có thể truyền **arguments mới** cho mỗi lần `proceed` không?
- Khi nào không nên dùng kỹ thuật này?

Bài chỉ tập trung vào **Spring Aspect / Spring proxy-based AOP**, không triển khai lý thuyết AspectJ weaving độc lập như một chủ đề riêng.

## 2. Mô hình thực thi: lặp phần chain **phía trong**, không khởi chạy lại toàn bộ

Giả sử cùng một Spring service được bao bởi hai `@Around` advices:

- **RetryAspect** có precedence cao hơn nên nằm **ngoài**.
- **TraceAspect** có precedence thấp hơn nên nằm **trong**.
- Target bean là `WorkService`.

```text
Caller
  |
  v
Spring AOP proxy
  |
  v
RetryAspect.around()            <-- vào MỘT lần từ caller
  |
  +---- proceed() lần 1 ----> TraceAspect.around()
  |                              |
  |                              +--> target.execute() lần 1
  |                              |
  |                          return hoặc throw
  |
  +---- proceed() lần 2 ----> TraceAspect.around()
  |                              |
  |                              +--> target.execute() lần 2
  |                              |
  |                          return hoặc throw
  |
  +---- RetryAspect chọn kết quả/exception cuối
  |
  v
Caller
```

Khi `RetryAspect` gọi `proceed()`, Spring chuyển sang **phần invocation chain nằm sau advice đó**. Nếu `TraceAspect` và target nằm phía trong, chúng được thực thi lại mỗi lần chuyển tiếp.

**Không suy luận rằng một `proceed()` thứ hai sẽ tự gọi lại advice bên ngoài hoặc toàn bộ caller.** `RetryAspect.around()` tiếp tục thực thi trong **cùng Java invocation** do caller tạo; local variables như `attempt` vẫn thuộc lần gọi đó.

Cần phân biệt:

1. **Một lần caller gọi proxy:** `service.execute("retry")).
2. **Một lần vào outer around advice:** `RetryAspect.around(...)`.
3. **Hai lần `proceed()`:** có thể vào downstream advices hai lần.
4. **Hai lần target method được thực thi:** nếu mỗi lần `proceed` đến target và không bị một downstream advice khác short-circuit.

Cụm “có thể đến target” là quan trọng: một advice phía trong cũng có quyền **không gọi `proceed()`**, chẳng hạn trả về cached value. Vì vậy số lần `proceed()` của outer advice là **số lần chuyển tiếp vào downstream chain**, không phải một cam kết toán học rằng target luôn thực thi đúng chừng đó lần.

## 3. Bảng hành vi khi gọi `proceed()` 0, 1 hoặc nhiều lần

| Số lần `proceed()` trong một `@Around` | Downstream chain | Target method | Caller nhận gì? |
| --- | --- | --- | --- |
| **0 lần** | Không được chuyển tiếp từ advice đó. | Không chạy qua đường này. | Giá trị do `@Around` tự trả hoặc exception nó ném; ví dụ cache hit. |
| **1 lần** | Được chuyển tiếp một lượt. | Thường chạy một lần nếu không bị short-circuit. | Giá trị `@Around` chọn trả; thường là giá trị của `proceed()`. |
| **2 lần** | Có hai lượt chuyển tiếp độc lập. | Có thể chạy hai lần; mọi side effect có thể lặp. | Không tự động nhận “cả hai”; caller nhận **một** giá trị do advice trả. |
| **N lần có điều kiện** | Lặp theo loop/branch của advice. | Có thể chạy đến N lần nếu attempts tiếp tục và xuống được target. | Kết quả của lần thành công được `return`, fallback value hoặc exception cuối theo code. |
| **Gọi lần đầu ném exception** | Lượt đầu bị gián đoạn do exception. | Target đã có thể thực thi một phần. | Nếu `@Around` bắt lỗi rồi gọi lại, caller có thể thấy kết quả lượt sau; nếu không bắt, exception truyền ra. |

**`proceed()` không tự động retry, không tự rollback và không tự quyết định return value.** Chính code trong `@Around` phải lựa chọn điều kiện lặp, số lần lặp, loại exception được phép retry và giá trị trả ra.

## 4. `proceed()` nhiều lần có gọi lại các advice khác không?

Có, **nếu các advice đó nằm phía trong** current around advice và vẫn match invocation.

Ví dụ thứ tự xác định bằng `@Order`:

```java
@Aspect
@Order(0)
public class OuterRetryAspect {
    @Around("execution(* com.example..WorkService.execute(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        try {
            return pjp.proceed();
        } catch (TemporaryFailure ex) {
            return pjp.proceed();
        }
    }
}
```

```java
@Aspect
@Order(10)
public class InnerTraceAspect {
    @Around("execution(* com.example..WorkService.execute(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("trace-in");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("trace-out");
        }
    }
}
```

Đây là **fragments minh họa** cần các imports, các type `WorkService`/`TemporaryFailure` và Spring configuration; bản chạy hoàn chỉnh ở phần 7.

Trong Spring, `@Order` có **giá trị nhỏ hơn thì precedence cao hơn**. Aspect precedence cao hơn nằm ngoài: chạy trước trên đường vào, chạy sau trên đường ra. Vì thế với `@Order(0)` và `@Order(10)`, `InnerTraceAspect` có thể in **hai cặp log** dù caller chỉ gọi service **một lần** và `OuterRetryAspect` được vào một lần.

Nếu đảo thứ tự, để trace nằm **ngoài** retry, trace thường in một cặp log cho một lần proxy invocation; phần retry bên trong có thể gọi target nhiều lần. Khi giải thích số lần advice chạy, phải hỏi **advice nằm ở đâu trong chain**, không chỉ đếm annotation.

Đừng dựa vào **thứ tự khai báo source code** giữa các aspects. Với nhiều aspects, dùng `@Order` hoặc `Ordered` và kiểm chứng chain trong integration test. Những advisors do transaction, security hoặc caching tạo ra cũng có ordering riêng.

## 5. Nếu lần đầu thành công nhưng vẫn gọi lần hai thì sao?

Đây là khác biệt giữa **retry** và **replay**:

### Retry có điều kiện

```java
Object result;
try {
    result = pjp.proceed();
} catch (TemporaryFailure ex) {
    result = pjp.proceed();
}
return result;
```

Nếu lượt đầu thành công, lượt thứ hai **không diễn ra**. Nếu lượt đầu ném đúng loại lỗi được bắt, lời gọi được thử lại. Đây là fragment áp dụng khi lỗi **có thể retry an toàn** và lời gọi qua Spring proxy đúng.

### Replay cố ý, kể cả thành công

```java
Object first = pjp.proceed();
Object second = pjp.proceed();
return second;
```

Nếu hai lượt đều thành công, method phía trong vẫn có thể chạy **hai lần**. Caller thấy kết quả thứ hai vì `@Around` trả `second`, nhưng tác dụng phụ của **lần thứ nhất không tự bị xóa**.

Nếu đổi thành `return first`, caller sẽ nhận kết quả thứ nhất dù target có thể đã thực thi lần thứ hai. Nếu `return new SomeResult(...)`, caller lại nhận giá trị hoàn toàn do aspect dựng lên, miễn tương thích method return type. `@Around` có quyền **chọn return value**; không có quy tắc bắt buộc nó trả giá trị từ lời `proceed` cuối cùng.

### Nếu lần hai thất bại?

```java
Object first = pjp.proceed();
Object second = pjp.proceed(); // Nếu ném lỗi, lệnh return ở dưới không chạy.
return second;
```

Một lỗi ở lượt thứ hai có thể khiến caller nhận exception, **dù lượt thứ nhất đã hoàn thành thành công và gây side effect**. Không xem `proceed` nhiều lần như một transaction tự động bao trọn nhiều lượt.

## 6. `proceed(Object[] args)`: thay tham số ở mỗi lượt

Spring AOP cung cấp hai overload:

```java
Object proceed() throws Throwable;
Object proceed(Object[] args) throws Throwable;
```

`proceed()` chuyển tiếp theo arguments hiện có của join point. `proceed(Object[] args)` cho phép chuyển tiếp với **một bộ arguments mới** đến method phía trong.

Ví dụ một service có method `String send(String value)`:

```java
Object originalResult = pjp.proceed();

Object[] newArgs = {"normalized"};
Object replacementResult = pjp.proceed(newArgs);

return replacementResult;
```

Đây là fragment trong `@Around` của Spring `@Aspect`. Nếu cả hai lượt đến target:

- Lượt đầu nhận arguments đang có của invocation.
- Lượt hai nhận argument `"normalized"`.
- Caller thấy giá trị do advice `return`; không tự động nhận hai kết quả.

**Các ràng buộc:**

- Array phải tương thích **số lượng và kiểu** arguments của underlying method; sai kiểu hoặc sai độ dài có thể dẫn tới lỗi invocation.
- `null` không hợp lệ cho tham số primitive mà cơ chế gọi cần unbox.
- Nếu dự định thử lại với **cùng dữ liệu**, tạo snapshot an toàn của arguments nếu cần; đừng âm thầm mutate một `Object[]` dùng chung và giả định hai lượt đồng nhất.
- Khi arguments chứa **mutable objects**, `proceed()` không copy sâu các objects đó. Nếu target sửa argument tại lượt đầu, lượt sau có thể quan sát state mới dù array reference không đổi.
- Spring docs lưu ý semantics của `proceed(Object[])` trong Spring proxy AOP **khác chi tiết** so với AspectJ weaving thuần; bài này chỉ sử dụng quy tắc Spring: array ứng với **arguments của underlying method**.

Không gọi `proceed` để “xem thử” target sẽ trả gì rồi gọi lại “cho thật” trừ khi operation thực sự cho phép lặp mà không gây thiệt hại.

## 7. Ví dụ runnable Java 17+: retry lỗi một lần và gọi thành công hai lần

Ví dụ này chỉ dùng **Spring Framework 6.1.14**, `aspectjweaver 1.9.22.1`, **JDK 17+** và Maven. Đây là bộ phiên bản cố định để minh họa, không khẳng định phiên bản mới nhất.

Mục tiêu quan sát:

1. Một caller gọi `service.execute("retry")` đúng **một lần**.
2. `ReplayAspect` bên ngoài gọi `proceed()` lần thứ nhất; target **ném `TemporaryFailure`**.
3. Aspect bắt lỗi và gọi `proceed()` lần hai; target thành công.
4. `TraceAspect` ở phía trong chạy **hai lần** cho hai attempts.
5. Caller gọi `service.execute("twice")` đúng **một lần** nhưng advice cố ý gọi `proceed()` **hai lần dù cả hai đều thành công**.
6. Đếm tổng số lần target method được thực thi: **4**, dù caller chỉ có **hai** lời gọi.

Ví dụ `"twice"` chỉ dùng để phơi bày rủi ro **duplicate successful execution**, không phải pattern khuyến nghị cho ghi dữ liệu sản xuất.

### 7.1. Cấu trúc project

```text
spring-multiple-proceed/
├── pom.xml
└── src/main/java/com/example/replay/
    ├── WorkService.java
    ├── ReplayAspect.java
    ├── TraceAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-multiple-proceed</artifactId>
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

`spring-context` mang container và các Spring AOP dependencies phù hợp theo cây phụ thuộc của ví dụ; `aspectjweaver` cần để Spring xử lý `@Aspect`/pointcut. Đây vẫn là **proxy-based Spring AOP**, không yêu cầu AspectJ weaving agent.

### 7.3. `src/main/java/com/example/replay/WorkService.java`

```java
package com.example.replay;

import java.util.concurrent.atomic.AtomicInteger;

public class WorkService {
    private final AtomicInteger calls = new AtomicInteger();

    public static class TemporaryFailure extends RuntimeException {
        public TemporaryFailure(String message) {
            super(message);
        }
    }

    public String execute(String label) {
        int n = calls.incrementAndGet();
        System.out.println("[TARGET] " + label + " call=" + n);

        if ("retry".equals(label) && n == 1) {
            throw new TemporaryFailure("once");
        }

        return label + "#" + n;
    }

    public int invocationCount() {
        return calls.get();
    }
}
```

Target chủ động ném một `TemporaryFailure` **chỉ ở lần thực thi đầu tiên của `execute("retry")`**. Trạng thái `calls` có thể được kiểm tra qua method `invocationCount()`.

`AtomicInteger` ở đây tránh data race khi đếm; nhưng `execute` được chạy tuần tự trong ví dụ. Mọi kết quả stdout bên dưới giả định chỉ một `DemoApp` sử dụng instance và chạy các lệnh theo đúng thứ tự.

### 7.4. `src/main/java/com/example/replay/ReplayAspect.java`

```java
package com.example.replay;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(0)
public class ReplayAspect {

    @Around("execution(public * com.example.replay.WorkService.execute(..))")
    public Object replay(ProceedingJoinPoint pjp) throws Throwable {
        String label = (String) pjp.getArgs()[0];

        if ("retry".equals(label)) {
            for (int attempt = 1; attempt <= 2; attempt++) {
                System.out.println("[OUTER] attempt " + attempt);
                try {
                    return pjp.proceed();
                } catch (WorkService.TemporaryFailure ex) {
                    System.out.println("[OUTER] caught " + ex.getMessage());
                    if (attempt == 2) {
                        throw ex;
                    }
                }
            }
            throw new IllegalStateException("Unreachable retry branch");
        }

        if ("twice".equals(label)) {
            System.out.println("[OUTER] call A");
            Object first = pjp.proceed();

            System.out.println("[OUTER] call B");
            Object second = pjp.proceed();

            System.out.println("[OUTER] first=" + first
                    + "; return=" + second);
            return second;
        }

        return pjp.proceed();
    }
}
```

Aspect này mô tả **hai chính sách khác nhau chỉ để dạy về số lần `proceed()`**:

- Với `"retry"`, nó thử tối đa **hai lần**, chỉ retry khi gặp `TemporaryFailure`; nếu thành công sớm, `return` kết thúc loop ngay.
- Với `"twice"`, nó **cố ý gọi target hai lần** dù lượt đầu thành công. Điều đó phù hợp về mặt API, nhưng rất nguy hiểm cho method có side effects.
- Với label khác, nó chỉ gọi `proceed()` một lần.

Vì aspect có `@Order(0)`, nó được đặt **ngoài** `TraceAspect` có `@Order(10)` trong cùng Spring advisor chain của demo.

### 7.5. `src/main/java/com/example/replay/TraceAspect.java`

```java
package com.example.replay;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class TraceAspect {

    @Around("execution(public * com.example.replay.WorkService.execute(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[INNER] before");
        try {
            Object result = pjp.proceed();
            System.out.println("[INNER] after=" + result);
            return result;
        } catch (Throwable ex) {
            System.out.println("[INNER] threw="
                    + ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
```

`TraceAspect` chỉ cần gọi `proceed()` **một lần trong mỗi lần advice được kích hoạt**. Nhưng nó có thể được kích hoạt **hai lần** nếu outer aspect gọi `proceed()` hai lần.

Đây chính là điểm dễ nhầm: **một advice chỉ có một dòng `pjp.proceed()` vẫn có thể chạy nhiều lần cho một lời gọi proxy bên ngoài**, khi một around advice có precedence cao hơn lặp phần chain của nó.

### 7.6. `src/main/java/com/example/replay/AppConfig.java`

```java
package com.example.replay;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public WorkService workService() {
        return new WorkService();
    }

    @Bean
    public ReplayAspect replayAspect() {
        return new ReplayAspect();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@EnableAspectJAutoProxy` kích hoạt Spring auto-proxy creator. `proxyTargetClass = true` dùng CGLIB class proxy cho `WorkService` không implement business interface. Hai `@Aspect` classes được đăng ký **thành Spring beans** thông qua `@Bean`. Chỉ đặt `@Aspect` mà không đăng ký bean thì Spring chưa chắc nhận diện advice.

### 7.7. `src/main/java/com/example/replay/DemoApp.java`

```java
package com.example.replay;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            WorkService service = context.getBean(WorkService.class);
            System.out.println("isAopProxy="
                    + AopUtils.isAopProxy(service));

            String retryResult = service.execute("retry");
            System.out.println("caller.retry=" + retryResult);

            String twiceResult = service.execute("twice");
            System.out.println("caller.twice=" + twiceResult);

            System.out.println("targetCalls=" + service.invocationCount());
        }
    }
}
```

Caller dùng bean từ `ApplicationContext`, không tự tạo `new WorkService()` để gọi. Đây là điều kiện để lời gọi đi vào Spring AOP proxy, nơi hai aspects đã được tạo thành advisor chain.

### 7.8. Chạy và stdout dự kiến

Với JDK 17+, Maven có thể tải dependencies, tại thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.replay.DemoApp
```

Các dòng do code ví dụ tự in theo đúng thứ tự (không bao gồm thông báo Maven/Spring/SLF4J khác tùy môi trường):

```text
isAopProxy=true
[OUTER] attempt 1
[INNER] before
[TARGET] retry call=1
[INNER] threw=TemporaryFailure
[OUTER] caught once
[OUTER] attempt 2
[INNER] before
[TARGET] retry call=2
[INNER] after=retry#2
caller.retry=retry#2
[OUTER] call A
[INNER] before
[TARGET] twice call=3
[INNER] after=twice#3
[OUTER] call B
[INNER] before
[TARGET] twice call=4
[INNER] after=twice#4
[OUTER] first=twice#3; return=twice#4
caller.twice=twice#4
targetCalls=4
```

**Giải thích theo số lần thực thi:**

- Caller gọi `execute("retry")` **một lần**, nhưng `ReplayAspect` thực hiện hai `proceed()` do lần đầu gặp lỗi. `TraceAspect` vào hai lần và target vào hai lần.
- Lần đầu target tăng `calls` thành 1 **trước khi ném exception**; retry không tự hoàn tác việc tăng counter đó. Lần hai tăng thành 2 và thành công.
- Caller chỉ nhận `retry#2`; exception đầu tiên đã được outer aspect bắt và không truyền ra nữa.
- Caller gọi `execute("twice")` **một lần**, outer aspect gọi `proceed()` hai lần dù lần đầu thành công, nên target tăng `calls` thành 3 rồi 4.
- Lần đầu của chế độ `twice` trả `twice#3`; lần hai trả `twice#4`. Outer aspect **trả `second`**, vì thế caller chỉ thấy `twice#4`, dù side effect tăng counter ở cả hai lượt.
- `targetCalls=4` chứng minh **số lời gọi từ caller (2)** không bằng **số lần target được chạy (4)**.

Ví dụ này kiểm chứng hành vi **Spring AOP trên một proxy được quản lý**, không mô tả AspectJ compile-time weaving. Stdout là kết quả dự kiến theo source code đã trình bày; khi mang vào dự án thật, chạy integration test trên đúng Spring/JDK version đang triển khai.

## 8. Ứng dụng thực tế: retry phải có giới hạn và điều kiện rõ

Spring Framework dùng retry các lỗi concurrency làm ví dụ tiêu biểu cho `@Around` gọi `proceed()` nhiều lần. Nhưng ứng dụng sản xuất cần nhiều bảo vệ hơn một vòng `for` đơn giản.

Một retry policy hợp lý cần trả lời:

1. **Lỗi gì có thể retry?** Chỉ bắt nhóm lỗi transient đã xác định, không tự retry `IllegalArgumentException`, lỗi validation hoặc lỗi logic vĩnh viễn.
2. **Bao nhiêu attempts tối đa?** Có limit rõ ràng; không `while (true)` vô hạn.
3. **Chờ giữa các attempts?** Dùng backoff/jitter hợp lý theo hệ thống; không bắt buộc ngủ với mọi lỗi.
4. **Operation có idempotent không?** Nếu gọi lại có thể trừ tiền/gửi email hai lần, retry cần idempotency key, transactional/outbox mechanism hoặc protocol cho phép deduplication.
5. **Attempt trước đã làm gì?** Lỗi xảy ra **sau khi** ghi DB hoặc gọi remote API có thể để lại side effect trước khi exception đến around advice.
6. **Exception cuối đi đâu?** Khi hết attempts, phải propagate hoặc chuyển thành lỗi có hợp đồng rõ ràng, không âm thầm nuốt lỗi.
7. **Retry có khả năng thành công không?** Lỗi vĩnh viễn không nên được lặp.
8. **Metrics thế nào?** Đếm caller requests, retry attempts, target executions và final outcome **riêng biệt**.
9. **Cancellation/timeouts?** Nếu invocation bị hủy hoặc deadline hết, không tiếp tục retry vô điều kiện.
10. **Thread safety?** Lưu attempt counter trong local variable của method advice, không trong mutable field của singleton aspect nếu state cần riêng cho từng request.

Một cấu trúc retry dạng fragment:

```java
@Around("execution(* com.example.service.SomeService.retryableOperation(..))")
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    int maxAttempts = 3;
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return pjp.proceed();
        } catch (TransientBusinessException ex) {
            if (attempt == maxAttempts) {
                throw ex;
            }
            // Áp dụng backoff/cancellation policy nếu cần.
        }
    }
    throw new IllegalStateException("Unreachable");
}
```

Đây là **fragment**, không chạy độc lập vì `SomeService` và `TransientBusinessException` phải được định nghĩa. Nó chỉ mô tả retry cho method **đã được xác nhận an toàn để thử lại**; đừng áp dụng pointcut quá rộng lên mọi `service.*` chỉ vì code có thể chạy.

### 8.1. Retry và side effect không an toàn

Ví dụ nguy hiểm:

```java
public Receipt charge(String paymentId) {
    remotePaymentGateway.charge(paymentId);
    database.saveAudit(paymentId);
    return new Receipt(paymentId);
}
```

Giả sử remote gateway đã xử lý thành công, nhưng database save thất bại và method ném lỗi. Nếu một `@Around` retry **toàn bộ method**, lượt tiếp theo có thể gọi remote gateway **lần hai**.

`proceed()` không cung cấp transaction phân tán, không suy ra một lần trước có side effect hay chưa và không tự tạo idempotency key. Phải thiết kế retries phù hợp nghiệp vụ, transaction boundaries và hành vi hệ thống bên ngoài.

## 9. Vị trí retry advice so với `@Transactional` rất quan trọng

Nếu một phương thức được áp dụng cả retry và transaction interceptor, ordering ảnh hưởng tới phạm vi transaction.

### Trường hợp A: retry **ở ngoài** transaction

```text
Caller
  -> RetryAround
       -> proceed attempt #1
            -> TransactionInterceptor (begin tx #1)
                 -> target
            -> rollback/commit tx #1
       -> proceed attempt #2
            -> TransactionInterceptor (begin tx #2)
                 -> target
            -> rollback/commit tx #2
```

Khi đúng cấu hình và **không có transaction bên ngoài đang được tham gia**, mỗi attempt có thể có transaction mới. Đây là cách tài liệu Spring minh họa retry concurrency failure để mong mỗi retry là một transaction độc lập.

### Trường hợp B: transaction **ở ngoài** retry

```text
Caller
  -> TransactionInterceptor (begin tx)
       -> RetryAround
            -> proceed attempt #1 -> target
            -> proceed attempt #2 -> target
  -> commit/rollback một tx bao ngoài
```

Các attempts nằm dưới một transaction boundary bên ngoài. Với exception đã khiến transaction bị đánh dấu rollback-only, việc retry ngay trong transaction ấy có thể không giúp transaction commit được. Do đó **không được coi hai sơ đồ là tương đương**.

**Những điều cần kiểm tra trong Spring:**

- Retry aspect có precedence đủ cao để ở **ngoài** transaction advisor không?
- `@EnableTransactionManagement(order = ...)` hoặc transaction infrastructure của ứng dụng đang có thứ tự nào?
- Có transaction từ caller đã tồn tại trước khi vào service không?
- Propagation mode là `REQUIRED`, `REQUIRES_NEW` hay mode khác?
- Có callback/DB connection/resource nào còn giữ state sau attempt lỗi không?
- Exception có bị bắt ở vị trí khiến transaction interceptor không quan sát được lỗi không?

Dù retry đứng ngoài transaction advisor, nếu caller đã có một transaction bao ngoài và transaction propagation tham gia transaction đó, không thể khẳng định mỗi attempt có một transaction độc lập. Phải kiểm thử transaction IDs/commit/rollback trong cấu hình thật.

Spring có những abstraction chuyên dụng như Spring Retry hoặc resilience patterns khác tùy stack; khi ứng dụng cần policy phức tạp, đừng tự triển khai một vòng lặp `proceed()` thiếu backoff, timeout và quan sát lỗi.

## 10. `proceed()` nhiều lần không đồng nghĩa lặp toàn bộ HTTP request

Trong một ứng dụng Spring MVC/REST:

```text
HTTP request -> Filter chain -> DispatcherServlet
              -> Controller -> Spring service proxy
                                  |
                                  +-- Around.proceed() #1 -> target
                                  +-- Around.proceed() #2 -> target
```

Nếu around advice áp dụng ở **service bean**, việc gọi lại `proceed()` thường chỉ lặp phần method invocation chain của **service**, không lặp:

- Toàn bộ Servlet filter chain.
- DispatcherServlet từ đầu.
- Mapping/authentication/request binding ở tầng controller đã hoàn tất.
- Những hoạt động trước khi caller gọi service proxy.

Tương tự, một transaction interceptor hoặc inner logging aspect **có thể** nằm bên trong method chain và bị lặp, nhưng middleware ở **ngoài** method advice không tự chạy lại.

Đây là lý do cần phân biệt **request-level metrics** và **attempt-level metrics**: một HTTP request có thể sinh một lời gọi service proxy, nhưng bốn lần target execution nếu retry/replay có bốn attempts.

## 11. Trường hợp asynchronous hoặc reactive return type

Nếu method được advice trả về `CompletableFuture<T>`, `CompletionStage<T>`, `Mono<T>` hoặc `Flux<T>`, `proceed()` chuyển tiếp **Java method invocation**; nó không tự biến thành một lệnh đợi toàn bộ công việc bất đồng bộ hoàn tất.

Ví dụ:

```java
CompletableFuture<Result> first =
        (CompletableFuture<Result>) pjp.proceed();
CompletableFuture<Result> second =
        (CompletableFuture<Result>) pjp.proceed();
return second;
```

Đây là fragment. Nó có thể tạo **hai futures / hai luồng xử lý bất đồng bộ**, tùy implementation của method, chứ không phải “thử lại sau khi future thứ nhất đã lỗi”. Future thứ nhất vẫn có thể đang chạy khi caller nhận future thứ hai.

Với Reactor publisher, việc gọi method trả về `Mono<T>` hai lần có thể tạo hai publishers; **subscription** sau đó mới kích hoạt công việc nếu publisher cold, còn hot publisher có hành vi khác. Vì vậy không được suy rằng hai lần `proceed()` bằng hai lần subscription hoặc hai lần kết quả cuối.

Nếu retry cần dựa trên **lỗi async completion**, sử dụng đúng cơ chế như `CompletionStage` composition, Reactor `retryWhen` hoặc một thư viện retry/resilience phù hợp, đồng thời xét idempotency và transaction semantics của reactive stack. Không viết một vòng `for` đồng bộ quanh `pjp.proceed()` rồi giả định nó xử lý mọi lỗi xảy ra về sau.

## 12. Những giới hạn của Spring proxy vẫn áp dụng

Việc `proceed()` hỗ trợ gọi nhiều lần **không khắc phục giới hạn proxy-based Spring AOP**:

- Chỉ áp dụng khi caller dùng **Spring-managed proxy**. `new WorkService().execute(...)` không được auto-proxy chỉ nhờ có `@Aspect`.
- **Self-invocation** như `this.execute()` bên trong target bypass Spring AOP proxy; pointcut của method nội bộ không được Spring gọi qua proxy chỉ nhờ `proceed()` trong một method khác.
- Với JDK dynamic proxy, method cần được gọi qua proxied interface thích hợp. Với CGLIB, `final`/`private` method không được intercept bằng subclass proxy như public overridable method.
- Các `@Aspect` classes phải là **Spring beans**; `@Aspect` một mình chưa đăng ký bean.
- Auto-proxy creator và aspects có **phạm vi ApplicationContext**; bật AOP ở context khác không bảo đảm bean hiện tại được proxy.
- Aspect singleton có thể phục vụ nhiều requests đồng thời; tránh giữ `attempt`, `lastError` hoặc `ProceedingJoinPoint` trong shared mutable fields.
- Không nên giữ `ProceedingJoinPoint` để gọi `proceed()` **sau khi advice đã return**, hoặc chuyển nó sang thread khác rồi kỳ vọng toàn bộ interceptor/transaction/thread-local context còn hợp lệ. Nó đại diện cho invocation đang được xử lý, không phải một “callback lâu dài” tùy ý chạy lại.

Một test chỉ gọi target trực tiếp bằng `new` sẽ không chứng minh gì về khả năng multiple-proceed của Spring AOP. Phải gọi qua bean/proxy trong `ApplicationContext`.

## 13. Kiểm thử và chẩn đoán số lần thực thi

Một integration test có thể tách ít nhất ba loại counter:

| Counter | Nó đếm gì? | Kết quả demo `retry` | Kết quả demo `twice` |
| --- | --- | --- | --- |
| Caller invocation count | Số lần code bên ngoài gọi service proxy | 1 | 1 |
| Outer around invocation count | Số lần chính retry/replay advice được vào từ proxy | 1 | 1 |
| `proceed()` attempt count | Số lần outer around chuyển tiếp vào chain | 2 | 2 |
| Inner trace count | Số lần advice phía trong chạy | 2 | 2 |
| Target execution count | Số lần target thực sự thực hiện body | 2 | 2 |
| Caller-visible result | Giá trị được outer around return | `retry#2` | `twice#4` |

Bảng áp dụng cho **project demo đã nêu**, nơi mỗi `proceed()` đều tới target. Nếu có cache/short-circuit phía trong, các counts có thể khác.

Kiểm thử nên gồm:

1. **Không lỗi:** retry policy `return pjp.proceed()` ngay ở attempt 1, target chạy một lần.
2. **Lỗi transient rồi thành công:** target chạy hai lần; caller chỉ nhận một thành công.
3. **Lỗi mãi:** dừng ở max attempts và propagate exception đúng loại.
4. **Lỗi không nằm trong allowlist:** không retry.
5. **Method có side effect:** xác nhận idempotency/deduplication và số lần ghi gửi thật.
6. **Nhiều aspects:** xác nhận `@Order`, log/metric ở inner và outer theo ý muốn.
7. **Arguments:** `proceed()` giữ input, `proceed(newArgs)` chuyển đúng arguments mong muốn.
8. **Return type:** caller nhận một value hợp lệ, không ép kiểu lỗi với primitive/generic.
9. **Transaction:** xác nhận từng attempt có commit/rollback đúng khi có Spring transaction advisor.
10. **Concurrency:** mỗi invocation có attempt counter riêng, không chia sẻ sai với invocation khác.
11. **Proxy boundary:** `AopUtils.isAopProxy(bean)` và lời gọi thật qua Spring bean.
12. **Timeout/cancel:** không chạy lại khi request/deadline đã hết theo policy nghiệp vụ.

Khi chẩn đoán “một API call mà log target lặp”, kiểm tra **có outer `@Around` nào gọi `pjp.proceed()` nhiều lần không**, rồi mới xem HTTP client gửi trùng request. Log tương ứng request ID và **attempt number** giúp phân biệt replay trong cùng request với một request thứ hai thực sự.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Target chạy hai lần, caller chỉ gọi service một lần | Outer `@Around` gọi `proceed()` hai lần | Đếm attempts, kiểm tra branch và idempotency. |
| Trace `@Around` chạy hai lần dù chỉ có một caller | Trace nằm **trong** retry/replay around | Kiểm tra `@Order` và chain nesting. |
| Target không chạy dù lời gọi đã vào proxy | `@Around` không gọi `proceed()` hoặc inner advice short-circuit | Kiểm tra chính sách cache/guard/return sớm. |
| Caller nhận giá trị lượt hai, lượt một vẫn đã ghi DB | Return value và side effect là hai vấn đề khác nhau | Bảo đảm rollback/compensation/idempotency; không chỉ đổi `return first`. |
| Lỗi lần đầu biến mất | Around bắt exception và retry thành công | Đây là retry được viết rõ; cần logging/metrics attempts và policy cho lỗi cuối. |
| Hết retries nhưng caller lại nhận `null` | Advice tự trả null/nuốt exception sau loop | Propagate exception hoặc trả fallback có hợp đồng đúng. |
| Advice `void` quanh method có return làm mất giá trị | `@Around` không trả `Object` đúng contract | Dùng `Object` return và `return pjp.proceed()` hoặc replacement hợp lệ. |
| Retry trong một transaction vẫn rollback | Transaction advisor ở ngoài hoặc transaction hiện hành đã rollback-only | Xem ordering/propagation, test transaction boundaries. |
| Gửi email/charge hai lần | Operation không idempotent hoặc lỗi sau side effect | Dùng idempotency key, dedupe/outbox/compensation; giới hạn retry. |
| `proceed(newArgs)` ném lỗi | Arguments array sai số lượng, kiểu hoặc null primitive | Kiểm tra underlying method signature và kiểu runtime. |
| Retry future không bắt lỗi async | `proceed()` đã return future trước khi async task lỗi | Retry qua async/reaction operators hoặc return wrapper xử lý completion. |
| Không có `@Around` dù pointcut đúng | Caller bypass Spring proxy hoặc aspect chưa được đăng ký bean | Kiểm tra `@EnableAspectJAutoProxy`, context, bean refs, self-invocation. |
| Thấy outer logger chỉ in một lần nhưng target hai lần | Outer logger nằm ngoài replay advice | Phân biệt số lần caller, outer advice, downstream chain, target. |

## 15. Checklist trước khi đưa multiple-`proceed()` vào sản xuất

- [ ] Có lý do cụ thể để dùng `@Around` thay vì `@Before`/`@AfterReturning`.
- [ ] Operation được chọn bởi pointcut **hẹp và rõ**, không vô tình retry toàn bộ service layer.
- [ ] Chỉ retry những lỗi transient đã xác nhận có thể phục hồi.
- [ ] Có giới hạn attempts, backoff và deadline/cancellation policy.
- [ ] Đã đánh giá idempotency và mọi side effects của mỗi attempt.
- [ ] Đã phân biệt request-level metrics với attempt-level metrics.
- [ ] `@Order`/transaction advisor ordering đã được kiểm tra khi có transaction.
- [ ] Không có transaction ambient khiến các attempts vô tình chung một transaction không mong muốn.
- [ ] Arguments và mutable payload có chiến lược snapshot/khôi phục nếu cần.
- [ ] Exception cuối không bị nuốt; return value đúng kiểu method contract.
- [ ] Không lưu `ProceedingJoinPoint` hoặc per-call retry state trong mutable field của singleton aspect.
- [ ] Có integration tests chạy qua Spring proxy và xác minh số lần target thật sự chạy.
- [ ] Với async/reactive methods, retry được đặt ở đúng lifecycle của completion/subscription.
- [ ] Có cách quan sát attempts/side effects trên hệ thống thực tế.

### Tài liệu Spring chính thức

- Spring Framework — **Declaring Advice / Around Advice** (xác nhận `proceed()` có thể được gọi 0, 1 hoặc nhiều lần): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **An AOP Example** (retry lỗi concurrency bằng multiple `proceed()`, ordering với transaction advice): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/example.html
- Spring Framework — **Schema-based AOP Support** (around advice và retry example trong XML): https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework — **Proxying Mechanisms** (giới hạn lời gọi qua proxy): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — **AOP Concepts** (quyền điều khiển method invocation của around advice): https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html

**Kết luận:** Trong Spring AOP, `proceed()` nhiều lần là **lặp lại phần còn lại của invocation chain** tại vị trí của `@Around`, không phải tự động gọi lại toàn bộ request hoặc toàn bộ proxy từ bên ngoài. Kỹ thuật này giúp triển khai retry, nhưng cũng có thể làm downstream advices và target chạy nhiều lần, với side effects, transaction boundaries, exception và return values riêng. Chỉ sử dụng khi đã kiểm chứng đầy đủ khả năng retry an toàn của nghiệp vụ.
