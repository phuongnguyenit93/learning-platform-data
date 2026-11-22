# Chọn loại advice ít quyền can thiệp nhất đáp ứng yêu cầu trong Spring AOP

## 1. Nguyên tắc thiết kế

Trong Spring AOP, một aspect có thể gắn hành vi vào **method execution của Spring bean** bằng các loại advice khác nhau: `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After` và `@Around`.

**Quy tắc thiết kế được Spring Framework khuyến nghị: chọn loại advice ít quyền can thiệp nhất nhưng vẫn thực hiện đúng yêu cầu.** Ví dụ, chỉ cần ghi log trước khi method chạy thì dùng `@Before`, không dùng `@Around` để chủ động gọi `proceed()`. Chỉ cần ghi nhận giá trị trả về thành công thì dùng `@AfterReturning`, không tự triển khai một wrapper toàn bộ quá trình gọi.

Vì sao? Advice có quyền can thiệp càng lớn thì càng nhiều khả năng gây lỗi:

- Bỏ quên `proceed()` làm business method không chạy.
- Gọi `proceed()` nhiều lần làm ghi dữ liệu hoặc gửi sự kiện lặp.
- Trả sai kiểu hoặc nuốt exception thay đổi hợp đồng service.
- Ghi đè kết quả của method hoặc gây bất ngờ trong transaction/cache.
- Dùng cùng một advice cho quá nhiều tình huống khiến khó kiểm soát thứ tự và dễ vi phạm nguyên tắc đơn trách nhiệm.

Tuy nhiên, **“ít quyền” không phải thứ tự xếp hạng tuyến tính tuyệt đối** của năm annotation. Mỗi loại ứng với **thời điểm và dữ liệu** nó cần quan sát. Việc lựa chọn trước tiên dựa trên yêu cầu: trước khi chạy, sau khi thành công, khi có exception, khi kết thúc bất kể kết quả, hay cần chủ động điều khiển việc thực thi.

**Phạm vi bài:** cách chọn advice đúng trong **Spring Framework AOP**, nơi các Spring bean được bọc bằng JDK/CGLIB proxy và advice chạy khi method call đi qua proxy. Không phân tích lại lý thuyết AspectJ weaving độc lập.

## 2. Bảng quyết định chọn advice

| Yêu cầu | Advice ưu tiên | Quyền can thiệp tương ứng | Điều cần tránh |
| --- | --- | --- | --- |
| Ghi audit/log trước khi gọi service method | `@Before` | Chạy trước, quan sát method/arguments; không điều khiển `proceed()` | Không dùng `@Around` chỉ để in một dòng trước method |
| Kiểm tra đầu vào và **từ chối bằng cách ném lỗi** trước khi xử lý | `@Before` có thể đủ | Có thể ném exception, ngăn method tiếp tục | Đừng nghĩ `@Before` hoàn toàn không thể làm thay đổi luồng chạy |
| Ghi số liệu khi method **trả về bình thường** | `@AfterReturning` | Nhận kết quả trả về và quan sát sau thành công | Không mong nó chạy khi method ném exception |
| Ghi log giá trị thực sự được trả về | `@AfterReturning(returning = "...")` | Bind return value theo type | Không cố trả một reference khác từ advice để thay kết quả |
| Ghi metrics/lỗi khi target **ném exception** | `@AfterThrowing` | Quan sát exception mà target ném | Không coi nó là `catch` có thể tự nuốt lỗi của target |
| Giải phóng tài nguyên/cập nhật trạng thái khi method kết thúc bằng mọi cách | `@After` | Hành vi kiểu `finally` ở join point | Không dùng khi chỉ muốn chạy sau thành công |
| Đo thời gian bằng một biến bắt đầu và một biến kết thúc **trong cùng lượt gọi** | `@Around` có cơ sở sử dụng | Bọc trước và sau; có thể giữ local state an toàn theo invocation | Phải gọi `proceed()`, thường kèm `finally` |
| Cần trả kết quả cache mà **không gọi target** | `@Around`, hoặc tốt hơn là hạ tầng cache của Spring nếu phù hợp | Có thể bỏ qua target hoặc thay kết quả | Không tự viết cache trừ khi hạ tầng chuẩn không đáp ứng |
| Cần điều chỉnh arguments/return value, retry có kiểm soát hoặc shortcut | `@Around` nếu thực sự bắt buộc | Can thiệp mạnh nhất vào method invocation | Không bỏ qua idempotency, exception và giao dịch |
| Chỉ cần hành vi transaction/cache/security đã có framework hỗ trợ | Ưu tiên `@Transactional`/`@Cacheable`/cơ chế tích hợp phù hợp | Để Spring quản lý advisor chuyên dụng | Không tự dùng `@Around` để tái hiện transaction manager hoặc cache |

Một câu hỏi giúp quyết định nhanh:

> **Có cần tự quyết định method gốc được gọi lúc nào, bao nhiêu lần, với tham số nào và trả về cái gì không?** Nếu **không**, ưu tiên advice cụ thể (`@Before`, `@AfterReturning`, `@AfterThrowing` hoặc `@After`). Nếu **có**, `@Around` có thể cần thiết, nhưng phải giải thích được vì sao loại hẹp hơn không đáp ứng.

## 3. Hiểu chính xác năm loại advice trong Spring

### 3.1. `@Before`: chỉ cần xử lý trước method

~~~java
@Before("execution(* demo.OrderService.begin(..))")
public void beforeBegin() {
    System.out.println("BEFORE: begin");
}
~~~

Advice chạy **trước** một method execution khớp pointcut trên Spring proxy. Dùng cho audit marker, tracing context, quan sát tên method hoặc kiểm tra điều kiện đầu vào có thể ném exception để từ chối.

Quy tắc quan trọng:

- Không có `ProceedingJoinPoint` hay quyền tự gọi `proceed()`.
- Nếu `@Before` hoàn thành bình thường, Spring AOP tiếp tục lời gọi tới advice tiếp theo/target.
- **Nếu `@Before` ném exception**, method đích có thể không chạy; vì vậy loại này không phải “hoàn toàn không thể thay đổi hành vi”. Sử dụng nó cho validation có chủ ý, không ném lỗi vô tình từ logging.
- Muốn đọc argument, có thể nhận `JoinPoint` làm tham số đầu hoặc bind bằng `args(...)`; không cần chuyển sang `@Around` chỉ để đọc.
- Chỉ log trước khi thực hiện không có lý do bắt buộc phải bọc kết quả hay exception.

Ví dụ một audit logger không đáng tin có thể ném exception do formatter/remote sink; nếu điều đó không được phép làm fail business request, hãy đặt chính sách xử lý riêng trong advice, không vô thức để lỗi logging trở thành lỗi nghiệp vụ.

### 3.2. `@AfterReturning`: chỉ xử lý khi method thành công

~~~java
@AfterReturning(
    pointcut = "execution(String demo.OrderService.quote(..))",
    returning = "result",
    argNames = "result"
)
public void afterQuote(String result) {
    System.out.println("AFTER_RETURNING: " + result);
}
~~~

Method advice chỉ được gọi khi method đích **trả về bình thường**, có thể cả khi kết quả là `null` nếu type binding phù hợp. Trong ví dụ, `returning = "result"` bind giá trị method trả về vào biến advice tên `result`. `argNames` làm việc liên kết tên tham số tường minh hơn.

Đây là lựa chọn phù hợp khi:

- Cần đếm số lần thành công;
- Muốn quan sát return value để audit hoặc cập nhật metrics;
- Cần log mã kết quả sau khi business logic đã chạy.

Giới hạn then chốt: **không thể thay hẳn reference được trả về bằng một reference mới thông qua giá trị `return` của `@AfterReturning`**. Method advice loại này thường có kiểu trả về `void`. Nếu nó nhận một **object mutable**, về mặt Java có thể sửa state của object đang được trả về (nguy cơ side effect), nhưng đây không phải cùng việc thay object reference cho caller. Nếu yêu cầu bắt buộc **transform kết quả trả về**, hãy cân nhắc thiết kế lại service hoặc dùng `@Around` khi hợp lý.

`@AfterReturning` không chạy khi method đích kết thúc bằng exception. Nếu yêu cầu quan sát mọi kết quả, phải chọn hoặc kết hợp loại advice khác thích hợp.

### 3.3. `@AfterThrowing`: chỉ xử lý khi target ném exception

~~~java
@AfterThrowing(
    pointcut = "execution(* demo.OrderService.fail(..))",
    throwing = "error",
    argNames = "error"
)
public void afterFailure(IllegalStateException error) {
    System.out.println("AFTER_THROWING: " + error.getMessage());
}
~~~

Advice chạy khi method đích được advice **thoát bằng exception phù hợp**. Thuộc tính `throwing` gắn exception vào tham số method advice, và **type của tham số cũng lọc exception**. Trong ví dụ, chỉ exception thuộc `IllegalStateException` (hoặc subtype) được bind; muốn bắt nhiều loại để chỉ ghi log, có thể dùng `Throwable`, nhưng nên rõ ràng về mục tiêu.

Điểm thường nhầm:

- `@AfterThrowing` **không tương đương** một khối `catch` làm exception biến mất. Sau khi advice hoàn thành bình thường, exception của target vẫn được propagate tới caller.
- Nếu muốn **recover và trả về kết quả thay thế**, `@AfterThrowing` không có quyền làm việc đó; cân nhắc bắt exception ở business/service boundary hoặc `@Around` nếu thực sự cần xử lý xuyên các bean.
- Theo tài liệu Spring, `@AfterThrowing` được định nghĩa để nhận exception phát ra từ **target join point**, không xem nó như listener cho mọi exception do các `@After`/`@AfterReturning` khác ném.
- Nếu method target tự `try/catch` và không rethrow, phía Spring AOP quan sát một lần trở về bình thường, không phải thrown exit.

Hãy phân biệt “ghi nhận thất bại” với “xử lý thất bại”: loại advice chỉ nên được trao quyền mà requirement thực sự cần.

### 3.4. `@After`: dọn dẹp kiểu finally, cho mọi đường kết thúc

~~~java
@After("execution(* demo.OrderService.release(..))")
public void afterRelease() {
    System.out.println("AFTER: release");
}
~~~

`@After` (after-finally advice) chạy khi method execution khớp **kết thúc bằng return hoặc exception**. Loại này thích hợp cho:

- Dừng một marker theo dõi hoặc thực hiện cleanup không phụ thuộc thành công/thất bại;
- Cập nhật số lần một method hoàn tất bất kể outcome;
- Release resource đã được quản lý theo một contract xác định.

**Không dùng `@After` chỉ để log giao dịch thành công.** Nếu method ném lỗi, `@After` vẫn chạy; log `SUCCESS` trong advice này sẽ tạo sự thật sai. Dùng `@AfterReturning` cho successful outcome và `@AfterThrowing` cho failure outcome nếu cần phân biệt.

`@After` tương tự khối Java `finally`, nhưng vẫn là Spring AOP advice và chỉ áp dụng qua proxy. Nếu bản thân việc cleanup của advice ném exception, nó có thể ảnh hưởng kết quả caller quan sát; hãy làm cleanup an toàn và đừng nhầm việc có `@After` với bảo đảm giải phóng mọi resource trong mọi tình huống JVM/process.

### 3.5. `@Around`: chỉ dùng khi cần kiểm soát invocation

~~~java
@Around("execution(* demo.OrderService.guard(..))")
public Object aroundGuard(ProceedingJoinPoint point) throws Throwable {
    boolean allowed = (Boolean) point.getArgs()[0];
    if (!allowed) {
        return "blocked";
    }
    return point.proceed();
}
~~~

`@Around` bao lấy method execution khớp; tham số đầu là `ProceedingJoinPoint`. Nó có khả năng:

- Làm việc trước và sau target;
- **Không gọi `proceed()`**, khiến target bị bỏ qua;
- Gọi `proceed()` một lần hoặc nhiều lần (khả năng retry); phải hiểu side effects;
- Thay argument cho target bằng `proceed(Object[])` trong các điều kiện API phù hợp;
- Bắt/rethrow/đổi exception hoặc trả một kết quả khác cho caller;
- Giữ local state xuyên trước/sau trong cùng invocation, ví dụ start/end time.

Đổi lại, rủi ro tăng mạnh. Để **không làm thay đổi hợp đồng business**, một `@Around` kiểu wrapper thường phải:

1. Khởi tạo dữ liệu trước lời gọi (ví dụ timer);
2. **Thực hiện `point.proceed()` chính xác một lần** nếu cần target chạy bình thường;
3. Trả **đúng `Object`** do `proceed()` trả về;
4. Không vô ý nuốt hoặc thay exception;
5. Dùng `finally` khi cleanup phải chạy dù method ném lỗi.

Ví dụ đo thời gian với cleanup đúng cả hai đường:

~~~java
@Around("execution(* demo..service..*.*(..))")
public Object measure(ProceedingJoinPoint point) throws Throwable {
    long started = System.nanoTime();
    try {
        return point.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - started;
        // Ghi metric ở đây; không thay kết quả hoặc exception từ target.
    }
}
~~~

Đây là **snippet minh họa**, không phải phương án bổ sung trực tiếp vào ví dụ hoạt động bên dưới; cần `@Aspect` bean và đúng package. `System.nanoTime()` đo khoảng thời gian, không phải wall-clock timestamp. Khi timer chỉ cần start/end của một method trong cùng context, `@Around` có cơ sở sử dụng vì các advice trước/sau tách riêng khó truyền local state per-invocation một cách đơn giản và an toàn.

Không viết `@Around` trả `void` cho method có return value nếu muốn giữ kết quả; advice quanh nên trả `Object` và trả kết quả của `proceed()` để giữ hợp đồng. Nếu chủ động trả giá trị thay thế, bảo đảm kiểu kết quả đúng với return type của method và caller.

## 4. Tại sao “loại nhỏ nhất” làm code an toàn hơn?

Một `@Around` có thể viết được mọi điều kiện ở bảng trên, nhưng nó cũng có những trách nhiệm mà các loại hẹp hơn không yêu cầu:

~~~java
@Around("execution(* demo.OrderService.begin(..))")
public Object tooPowerful(ProceedingJoinPoint point) throws Throwable {
    System.out.println("BEFORE: begin");
    return point.proceed();
}
~~~

Còn với nhu cầu chỉ ghi log trước method:

~~~java
@Before("execution(* demo.OrderService.begin(..))")
public void sufficient() {
    System.out.println("BEFORE: begin");
}
~~~

Hai snippet là **hai cách thay thế nhau** cho cùng nhu cầu, không nên thêm cả hai vào cùng một aspect để tránh log trùng. Dạng `@Before` rõ mục đích và không phải giữ kết quả, exception hay gọi `proceed()`.

Điều tương tự áp dụng cho `@AfterReturning`: một `@Around` có thể gọi target rồi in return value, nhưng sẽ phải chịu trách nhiệm chuyển đúng kết quả/exception. Một `@AfterReturning` chỉ chạy trên nhánh thành công và framework làm phần còn lại.

Nguyên tắc này gần với **least privilege** ở cấp API: mỗi advice được trao đúng cơ hội quan sát và thay đổi cần thiết, không phải thêm quyền chỉ vì API mạnh hơn dễ lạm dụng.

## 5. Ví dụ Spring Framework Java 17+ đủ năm loại advice

Project minh họa **năm nhu cầu khác nhau** qua năm method riêng biệt. Ta cố ý thiết kế các pointcut **không trùng nhau** để có output dễ dự đoán và không nhập nhằng thứ tự advice giữa các loại. Chương trình còn đếm số lần advice để chứng minh logic đúng.

Yêu cầu: Java 17+, Maven 3.9+, Spring Framework 6.2.0, AspectJ Weaver 1.9.22. Đây là phiên bản cố định để minh họa (không khẳng định mới nhất), chạy bằng Spring Framework thuần, không dùng Spring Boot hay AspectJ weaving.

Cấu trúc project:

~~~text
spring-advice-least-power/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── OrderService.java
    └── ChoiceAspect.java
~~~

### 5.1. Maven dependencies

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-advice-least-power</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cho Spring container/Java configuration; `spring-aop` chứa AOP proxy/`AopUtils`; `aspectjweaver` cung cấp thư viện cho cú pháp pointcut `@AspectJ` do Spring phân tích. **Dependency `aspectjweaver` không tự tạo AspectJ compiler/load-time weaving.**

### 5.2. Target có phương thức thành công, thất bại và cần điều khiển

Tạo `src/main/java/demo/OrderService.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class OrderService {
    private final AtomicInteger guardExecutions = new AtomicInteger();

    public void begin() {
        System.out.println("TARGET: begin");
    }

    public String quote() {
        System.out.println("TARGET: quote");
        return "USD-10";
    }

    public void fail() {
        System.out.println("TARGET: fail");
        throw new IllegalStateException("declined");
    }

    public void release(boolean failure) {
        System.out.println("TARGET: release " +
                (failure ? "failure" : "success"));
        if (failure) {
            throw new IllegalArgumentException("release-failed");
        }
    }

    public String guard(boolean allowed) {
        guardExecutions.incrementAndGet();
        System.out.println("TARGET: guard");
        return "accepted";
    }

    public int getGuardExecutions() {
        return guardExecutions.get();
    }
}
~~~

`begin()` đại diện cho trường hợp chỉ cần log trước thực thi. `quote()` trả `String` thành công. `fail()` cố tình ném `IllegalStateException` để kiểm tra `@AfterThrowing`. `release(boolean)` được gọi hai lần (trả về bình thường và ném exception) để kiểm chứng `@After` kiểu finally. `guard(boolean)` sẽ do `@Around` quyết định có gọi target không; bộ đếm `guardExecutions` nằm **trong target** giúp xác nhận nhánh shortcut thực sự bỏ qua target.

Đây là class Java đầy đủ, không cần `@Service` khi dùng `@Bean` để đăng ký trong config. Class không `final` và method có thể override, giúp Spring tạo CGLIB class proxy.

### 5.3. Aspect với pointcut riêng cho từng nhu cầu

Tạo `src/main/java/demo/ChoiceAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ChoiceAspect {
    private final AtomicInteger beforeCalls = new AtomicInteger();
    private final AtomicInteger returningCalls = new AtomicInteger();
    private final AtomicInteger throwingCalls = new AtomicInteger();
    private final AtomicInteger finallyCalls = new AtomicInteger();
    private final AtomicInteger aroundCalls = new AtomicInteger();

    @Before("execution(* demo.OrderService.begin(..))")
    public void beforeBegin() {
        beforeCalls.incrementAndGet();
        System.out.println("BEFORE: begin");
    }

    @AfterReturning(
        pointcut = "execution(String demo.OrderService.quote(..))",
        returning = "result",
        argNames = "result"
    )
    public void afterQuote(String result) {
        returningCalls.incrementAndGet();
        System.out.println("AFTER_RETURNING: " + result);
    }

    @AfterThrowing(
        pointcut = "execution(* demo.OrderService.fail(..))",
        throwing = "error",
        argNames = "error"
    )
    public void afterFail(IllegalStateException error) {
        throwingCalls.incrementAndGet();
        System.out.println("AFTER_THROWING: " + error.getMessage());
    }

    @After("execution(* demo.OrderService.release(..))")
    public void afterRelease() {
        finallyCalls.incrementAndGet();
        System.out.println("AFTER: release");
    }

    @Around("execution(* demo.OrderService.guard(..))")
    public Object aroundGuard(ProceedingJoinPoint point) throws Throwable {
        aroundCalls.incrementAndGet();
        boolean allowed = (Boolean) point.getArgs()[0];
        if (!allowed) {
            System.out.println("AROUND: short-circuit");
            return "blocked";
        }
        System.out.println("AROUND: proceed");
        return point.proceed();
    }

    public int getBeforeCalls() {
        return beforeCalls.get();
    }

    public int getReturningCalls() {
        return returningCalls.get();
    }

    public int getThrowingCalls() {
        return throwingCalls.get();
    }

    public int getFinallyCalls() {
        return finallyCalls.get();
    }

    public int getAroundCalls() {
        return aroundCalls.get();
    }
}
~~~

Điểm cần quan sát:

1. **`@Before`** chỉ đánh dấu trước method `begin`; không giữ return value hoặc exception.
2. **`@AfterReturning`** chỉ chạy cho `quote` khi trả về thành công, bind `result` như một `String` và chỉ đọc/in giá trị.
3. **`@AfterThrowing`** chỉ chạy cho `fail` khi exception phù hợp; không catch/nuốt exception thay cho caller.
4. **`@After`** chạy cho `release` ở cả lần bình thường và lần bị exception.
5. **`@Around`** chỉ áp dụng cho `guard` bởi vì yêu cầu ở đây là có thể **bỏ qua target và trả `"blocked"`** khi input không được phép. Với input `true`, nó gọi `point.proceed()` và trả lại chính kết quả từ target.
6. Các pointcut tương ứng **tách biệt theo tên method**, nên không dựa vào thứ tự của nhiều advice cùng match một join point. Đây là cách cố ý giữ stdout đáng tin và giúp người học hiểu quyền của từng loại.
7. Mỗi advice có counter riêng; ngoài stdout, chương trình sẽ kiểm chứng số lần gọi. Không cần `ThreadLocal`/state toàn cục trong demo tuần tự.

Nếu chỉ muốn **kiểm tra được phép rồi từ chối bằng exception trước method**, `@Before` có thể đủ. `@Around` ở ví dụ `guard` được chọn vì requirement là **trả `"blocked"` nhưng không chạy target**, tức thay đổi flow/return value theo chủ đích. Đây là khác biệt quan trọng giữa chọn advice “vì tiện” và chọn advice do yêu cầu.

### 5.4. Khởi tạo Spring context và xác minh

Tạo `src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public ChoiceAspect choiceAspect() {
        return new ChoiceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            OrderService service = context.getBean(OrderService.class);
            ChoiceAspect aspect = context.getBean(ChoiceAspect.class);

            boolean proxied = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxied);

            service.begin();

            String quote = service.quote();
            System.out.println("RESULT_QUOTE: " + quote);

            try {
                service.fail();
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT: " + ex.getMessage());
            }

            service.release(false);
            try {
                service.release(true);
            } catch (IllegalArgumentException ex) {
                System.out.println("CAUGHT: " + ex.getMessage());
            }

            String blocked = service.guard(false);
            System.out.println("RESULT_BLOCKED: " + blocked);

            String allowed = service.guard(true);
            System.out.println("RESULT_ALLOWED: " + allowed);

            int before = aspect.getBeforeCalls();
            int returning = aspect.getReturningCalls();
            int throwing = aspect.getThrowingCalls();
            int finished = aspect.getFinallyCalls();
            int around = aspect.getAroundCalls();
            int actualGuards = service.getGuardExecutions();

            System.out.println("COUNTS: before=" + before
                    + ",returning=" + returning
                    + ",throwing=" + throwing
                    + ",finally=" + finished
                    + ",around=" + around
                    + ",targetGuard=" + actualGuards);

            if (!proxied || before != 1 || returning != 1
                    || throwing != 1 || finished != 2
                    || around != 2 || actualGuards != 1
                    || !"USD-10".equals(quote)
                    || !"blocked".equals(blocked)
                    || !"accepted".equals(allowed)) {
                throw new IllegalStateException(
                        "Unexpected Spring AOP advice behavior");
            }

            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Giải thích từng phần:

- `@EnableAspectJAutoProxy(proxyTargetClass = true)` đăng ký Spring auto-proxy creator, cho phép class proxy cho `OrderService`. Bean chỉ nhận proxy nếu advisor phù hợp, không phải mọi bean đều bị proxy hóa.
- `@Bean choiceAspect()` đăng ký `ChoiceAspect` vào context; **`@Aspect` riêng lẻ không tự trở thành Spring bean**.
- `service` là bean được lấy qua `ApplicationContext`, nên lời gọi bình thường đến những method khớp pointcut đi qua Spring AOP proxy.
- Các khối `try/catch` ở **caller** chứng minh exception từ target vẫn truyền tới caller sau khi `@AfterThrowing`/`@After` chạy.
- `service.getGuardExecutions()` đo số lần target `guard` được gọi: hai lần caller gọi qua proxy nhưng chỉ một lần target chạy, do `@Around` short-circuit ở lần đầu.
- Mỗi counter trong `ChoiceAspect` xác nhận semantics của từng advice, không chỉ nhìn thứ tự log.
- Điều kiện `if` cuối bảo đảm chương trình **ném lỗi nếu kết quả không đúng**, rồi mới in `CHECK: PASS`.

### 5.5. Lệnh chạy và output

Tại thư mục `spring-advice-least-power`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do mã Java chủ động in ra trong ví dụ:

~~~text
PROXY: true
BEFORE: begin
TARGET: begin
TARGET: quote
AFTER_RETURNING: USD-10
RESULT_QUOTE: USD-10
TARGET: fail
AFTER_THROWING: declined
CAUGHT: declined
TARGET: release success
AFTER: release
TARGET: release failure
AFTER: release
CAUGHT: release-failed
AROUND: short-circuit
RESULT_BLOCKED: blocked
AROUND: proceed
TARGET: guard
RESULT_ALLOWED: accepted
COUNTS: before=1,returning=1,throwing=1,finally=2,around=2,targetGuard=1
CHECK: PASS
~~~

Maven, SLF4J hoặc log framework có thể sinh thêm dòng ngoài ví dụ. Bản trên chỉ liệt kê `System.out.println` từ code. Nếu output lệch, kiểm tra aspect được đăng ký làm bean, Spring AOP bật, pointcut khớp, caller có đi qua proxy hay không, và code có ném exception bất ngờ trong advice không.

Từ output, kiểm chứng đúng **năm đặc trưng**:

- `BEFORE` xuất hiện trước `TARGET: begin`.
- `AFTER_RETURNING` xuất hiện sau `TARGET: quote` và nhận `USD-10`.
- `AFTER_THROWING` xuất hiện sau `TARGET: fail`, nhưng caller vẫn bắt được `declined`.
- `AFTER: release` xuất hiện cả khi `release(false)` thành công và khi `release(true)` ném exception.
- `AROUND: short-circuit` khiến `guard(false)` không in `TARGET: guard`; `guard(true)` có `proceed()` nên in `TARGET: guard`. Bộ đếm `targetGuard=1` xác nhận target thực thi đúng một lần.

Điều này chứng minh **tính phù hợp của loại advice với yêu cầu**, không chỉ khả năng viết ra cùng một hành vi bằng `@Around` cho mọi case.

## 6. Chọn advice cho từng yêu cầu thực tế

### 6.1. Ghi audit/tracing trước tác vụ

**Yêu cầu:** “Mỗi lần gọi `OrderService.submit(...)` qua Spring proxy, ghi nhận ai gọi và tham số.”

Lựa chọn: `@Before` có `JoinPoint` nếu cần argument/signature:

~~~java
@Before("execution(* demo.OrderService.submit(..))")
public void beforeSubmit(JoinPoint point) {
    String method = point.getSignature().getName();
    Object[] args = point.getArgs();
    // Ghi dữ liệu đã lọc, không log token/secret/PII tùy tiện.
}
~~~

Đoạn snippet cần đặt trong `@Aspect` và import `org.aspectj.lang.JoinPoint`; `OrderService.submit` là tên method minh họa, không có trong project chạy phần 5. Nó dùng `JoinPoint` (đọc thông tin), **không cần `ProceedingJoinPoint`**.

### 6.2. Đếm kết quả thành công

**Yêu cầu:** “Chỉ tăng successfulCounter nếu service thực sự trả kết quả.”

Lựa chọn: `@AfterReturning`. Một `@After` sẽ đếm cả thất bại; một `@Before` sẽ đếm cả những lời gọi sau đó ném exception. Nếu cần log return value, bind `returning`. Đây là ví dụ điển hình cho việc **semantics đầu ra quyết định loại advice**.

### 6.3. Ghi lỗi nhưng không thay exception

**Yêu cầu:** “Khi service ném lỗi nghiệp vụ, ghi mã lỗi để dashboard nhận biết; caller vẫn xử lý exception.”

Lựa chọn: `@AfterThrowing` với `throwing` typed binding. Đảm bảo logic log không ném lỗi mới làm thay đổi luồng caller. Không dùng `@Around` để `catch` rồi vô tình `return null` làm mất exception gốc.

### 6.4. Dọn dẹp dù thành công hay thất bại

**Yêu cầu:** “Luôn đánh dấu kết thúc một hoạt động được advice, kể cả khi method ném exception.”

Lựa chọn: `@After`. Phải phân biệt với tài nguyên có vòng đời từ trước invocation: nếu chỉ `@After` nhận biết resource không rõ nguồn tạo, đừng giả định nó có thể release an toàn. Với resource sinh ra ngay trong advice, một `@Around` có `try/finally` **có thể cần** để giữ handle local; với resource do business method sở hữu, để business method hoặc container quản lý lifecycle tại tầng đúng.

### 6.5. Chặn target nhưng trả fallback thay exception

**Yêu cầu:** “Nếu access policy trả false, không gọi target; trả đối tượng fallback có kiểu hợp lệ.”

Lựa chọn: `@Around` có lý do rõ ràng. `@Before` có thể ném exception để chặn nhưng **không thể tự trả fallback value thay target**. Nếu fallback là requirement, `@Around` có thể quyết định không gọi `proceed()`. Vẫn nên xem cơ chế security/caching được framework hỗ trợ trước khi tự triển khai chính sách xuyên ứng dụng.

### 6.6. Retry khi thất bại

**Yêu cầu:** “Một lời gọi idempotent có thể thử lại tối đa hai lần theo policy.”

Chỉ `@Around` mới trực tiếp có thể gọi `proceed()` nhiều lần trong cùng wrapper, nhưng **không có nghĩa luôn nên tự viết retry aspect**. Các method ghi DB/gửi thông báo/thanh toán thường không idempotent; retry có thể gây double writes/double charges. Cân nhắc cơ chế retry chuyên biệt (ví dụ Spring Retry), transaction boundary, backoff, timeout và idempotency key; phải định nghĩa được exception nào được retry. Nếu requirement không cần retry, tuyệt đối không thêm quyền gọi lại target.

### 6.7. Transaction và cache

Spring Framework có những module/annotation cấu hình transaction và cache dựa trên advisor phù hợp. Nếu mục tiêu thuần túy là `@Transactional` hoặc `@Cacheable` behavior chuẩn, **dùng tích hợp Spring tương ứng** thay vì tự dùng `@Around` để tái xây dựng transaction lifecycle, key semantics hoặc cache invalidation.

`@Around` phù hợp khi có yêu cầu cross-cutting đặc thù chưa được các extension point/framework đảm nhiệm, không phải khi chỉ muốn “một annotation chung”.

## 7. Thứ tự nhiều advice và tác động ngoài ý muốn

Ví dụ chính cố tình chọn **pointcut tách biệt cho từng loại advice**. Trong ứng dụng lớn, một join point có thể đồng thời khớp nhiều advice, kể cả từ nhiều aspects.

- Nếu các advice thuộc **những aspects khác nhau**, khi không chỉ định precedence, thứ tự có thể không xác định. Có thể dùng `@Order` hoặc `Ordered` để cấu hình thứ tự ở cấp aspect.
- Advice có precedence cao hơn thường chạy **trước khi đi vào** target và chạy **sau khi đi ra**; do đó thứ tự xuất hiện trong source code **không** bảo đảm thứ tự ở runtime.
- Spring/AspectJ có quy tắc nội bộ cho các loại advice trong cùng aspect; `@After` có semantics *after finally*, nên dù có precedence nội bộ cụ thể vẫn thường xuất hiện sau các advice trả về/throwing khi cùng match. **Đừng dựa vào thứ tự khai báo method trong file Java.**
- Hai advice cùng loại cùng match trong một aspect có thể không có thứ tự xác định chỉ vì nằm trên hay dưới nhau trong file nguồn.
- `@AfterThrowing` không được thiết kế như callback bắt exception do `@After`/`@AfterReturning` companion advice ném; xem scope exception ở **target method**.

Trong tình huống cần thứ tự mạnh, tạo **integration test** gọi đúng bean proxy, assert event trace và cấu hình ordering tường minh; đừng suy từ tên annotation hoặc vị trí khai báo.

Không cần tạo nhiều advice chỉ để “phòng xa” nếu nghiệp vụ thực sự cần một loại. Advice càng nhiều thì càng khó reason về tác động đến return/exception/transaction.

## 8. Kiểm tra điều kiện áp dụng trước khi chốt loại advice

Chọn đúng annotation chưa bảo đảm advice chạy: Spring chỉ áp dụng cho method invocation được proxy tiếp nhận và pointcut khớp. @Around không sửa được self-invocation qua this, đối tượng ngoài container, final/private method của class-based proxy, constructor hoặc field access.

Đặt sự kiện mong muốn tại đúng boundary: nếu cần sau transaction commit, dùng transaction synchronization hoặc sự kiện transaction phù hợp; nếu cần Future/Reactive completion, dùng completion callbacks/signals. @AfterReturning chỉ cho biết invocation trả bình thường. Nếu cần transformation hoặc fallback, cân nhắc explicit service/mapper hoặc @Around có kiểm soát. Transaction, security và cache nên ưu tiên extension point chính thức của Spring.

## 9. Review yêu cầu, lựa chọn và rủi ro

| Nhu cầu | Công cụ ưu tiên | Lỗi dễ gặp |
| --- | --- | --- |
| Log trước lời gọi | @Before | Dùng @Around nhưng quên proceed |
| Quan sát kết quả trả bình thường | @AfterReturning | Mong advice thay returned reference |
| Đo ngoại lệ theo subtype | @AfterThrowing | Mong advice swallow exception |
| Cleanup trên return và throw | @After | Nhầm finally với commit thành công |
| Đo duration theo từng invocation | @Around + local try/finally | Lưu start trong field aspect singleton |
| Retry/fallback | Business policy hoặc @Around có test | Thực thi side effects lặp thiếu idempotency |
| Chặn lời gọi nội bộ | Tách bean và inject proxy | Chỉ đổi JDK thành CGLIB |
| Theo dõi async task | Future/Reactive completion hook | Xem wrapper return là task completion |

Mỗi quyết định cần ghi rõ điểm gọi, proxy mode, pointcut, return/exception contract và thứ tự với các advisor hạ tầng. Đây là tiêu chí review quan trọng hơn chọn advice theo tên annotation.

## 10. Bài tập lựa chọn loại advice

Với từng yêu cầu, hãy chọn **loại hẹp nhất** rồi giải thích:

1. “Ghi tên method trước khi thực thi trên bean service.”  
   **`@Before`.** Không cần giữ kết quả hoặc tự gọi target.
2. “Chỉ tăng counter khi call hoàn tất thành công.”  
   **`@AfterReturning`.** `@After` sẽ đếm cả exception.
3. “Báo metrics lỗi với message của `IllegalStateException`; giữ exception tới caller.”  
   **`@AfterThrowing(throwing="error")`** và typed parameter tương ứng.
4. “Dọn marker/metric cả khi return và khi exception.”  
   **`@After`.** Nếu cần giữ local handle tạo ra trước invocation thì `@Around` có `try/finally` có thể phù hợp hơn.
5. “Đọc argument rồi từ chối bằng exception nếu policy cấm.”  
   **`@Before` có thể đủ.** Không nhất thiết phải kiểm soát `proceed()`.
6. “Trả cache hit mà không gọi target; cache miss thì gọi target.”  
   **`@Around`** có thể cần, nhưng ưu tiên `@Cacheable` và framework config nếu đáp ứng được.
7. “Ghi thời gian đúng của mỗi invocation, kể cả exception, bằng local started time.”  
   **`@Around`** với `try/finally` là cách trực tiếp; bảo đảm `proceed()` đúng một lần.
8. “Khi method ném exception, trả một giá trị fallback hợp lệ thay vì rethrow.”  
   **`@Around`** nếu đó là requirement ở cross-cutting boundary; `@AfterThrowing` không thay exception thành normal return.
9. “Ghi log đối tượng kết quả trả về, không sửa nó.”  
   **`@AfterReturning`** và bind `returning`.
10. “Bắt cả constructor/field access ở bất kỳ object nào.”  
    **Không advice Spring AOP nào đáp ứng.** Đây là giới hạn proxy method execution; cần đánh giá yêu cầu/cơ chế khác, không chọn `@Around` chỉ vì nó mạnh nhất.

## 11. Checklist trước khi review code Spring Aspect

- [ ] Requirement về **thời điểm và outcome** được ghi rõ trước khi chọn annotation advice.
- [ ] `@Before` được ưu tiên khi chỉ cần chạy trước method, không tự bọc `proceed()`.
- [ ] `@AfterReturning` dùng cho success; `@AfterThrowing` cho thrown exception; `@After` cho finally.
- [ ] Không dùng `@Around` trừ khi cần giữ local state trước/sau hoặc thay đổi invocation/return/fallback theo yêu cầu rõ ràng.
- [ ] Với `@Around`, tất cả nhánh có chính sách `proceed()`, return type, side effects và exception nhất quán.
- [ ] Advice không tự gây lỗi ngoài dự kiến khiến business contract đổi.
- [ ] Aspect và target được đăng ký làm Spring beans; lời gọi qua Spring AOP proxy.
- [ ] Pointcut đủ hẹp, không match nhầm method hoặc bean khác.
- [ ] Có kiểm thử cả normal return, thrown exception, case không match và self-invocation nếu liên quan.
- [ ] Không dựa vào thứ tự source code của nhiều advice; cấu hình ordering rõ ràng khi thực sự cần.
- [ ] Ưu tiên API sẵn có của Spring cho transaction/cache/security thay vì tự xây một `@Around` khó bảo trì.

## 12. Tài liệu chính thức của Spring Framework

- [Spring Framework 6.2 — AOP Concepts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-defn.html): các loại advice và nguyên tắc dùng **least powerful advice** đáp ứng yêu cầu.
- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): semantics `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`, return/exception binding và precedence.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): đăng ký hỗ trợ Spring AOP kiểu `@AspectJ`.
- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): chọn method executions trong Spring bean.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxy, self-invocation và giới hạn method.
