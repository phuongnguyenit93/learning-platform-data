# ThreadLocal trong aspect và trách nhiệm dọn dữ liệu trong Spring AOP

## 1. Vấn đề cần giải quyết

Một Spring `@Aspect` dùng để logging, profiling hoặc gắn operation context thường được đăng ký thành **singleton Spring bean**. Nhiều request trên nhiều thread cùng đi qua instance aspect đó. Lưu thông tin invocation vào một field mutable bình thường có thể gây **race condition**. Lưu nó trong `ThreadLocal<T>` giúp mỗi thread truy cập giá trị riêng, nhưng không có nghĩa Spring tự tạo, truyền hoặc dọn context cho từng request.

Hai lỗi thường xảy ra:

1. **Không gọi `remove()`:** một thread trong pool giữ dữ liệu của request trước, khiến request sau thấy sai operation, tenant hoặc correlation ID.
2. **Luôn gọi `remove()` trong lời advice lồng nhau:** khi một Spring proxy gọi Spring proxy khác trên cùng thread, inner advice có thể xóa context mà outer advice vẫn cần.

Mẫu an toàn cho scope được sở hữu bởi Spring `@Around` advice là:

~~~java
String previous = context.get();
context.set(operation);
try {
    return pjp.proceed();
} finally {
    if (previous == null) {
        context.remove();
    } else {
        context.set(previous);
    }
}
~~~

Mẫu này **lưu trạng thái cũ trước khi set, chỉ tiếp tục interceptor chain một lần, luôn restore/remove khi invocation thoát**, đồng thời giữ nguyên return value hoặc exception mà `proceed()` cung cấp.

Bài học tập trung vào **Spring Aspect và Spring AOP proxy-based** theo Special Note của module, không lặp lại kiến thức Aspect tổng quát. Mục tiêu là giải thích lifecycle của ThreadLocal, nested interception, cleanup trên exception, self-invocation, thread reuse và context propagation khi dùng Spring async/reactive.

## 2. ThreadLocal trong singleton aspect hoạt động ra sao?

Aspect sai về concurrency:

~~~java
@Aspect
public class UnsafeAspect {
    private String activeOperation;
}
~~~

Nếu hai threads chạy cùng advice, T1 có thể set `activeOperation="pay"` rồi T2 set `"report"` trước khi T1 đọc. Một object aspect singleton có **một shared field** cho mọi thread.

Với:

~~~java
@Aspect
public class ScopedAspect {
    private final ThreadLocal<String> activeOperation = new ThreadLocal<>();
}
~~~

Aspect vẫn có một field `ThreadLocal` được chia sẻ, nhưng mỗi thread sử dụng entry gắn với riêng thread đó. T1 và T2 có thể thấy các value độc lập.

Điều này **không** biến ThreadLocal thành:

- Request scope do Spring quản lý;
- Transaction scope;
- Security context đã được xác thực;
- Context cho mọi tác vụ CompletableFuture hoặc `@Async`;
- Reactor subscriber context;
- Một giá trị khác nhau cho mọi nested method trên cùng thread;
- Một cơ chế tự cleanup khi Spring method trả về.

Các API quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `get()` | Đọc value của ThreadLocal trên thread hiện tại |
| `set(value)` | Đặt hoặc ghi đè value trên thread hiện tại |
| `remove()` | Xóa entry hiện tại trên chính thread đang gọi |
| `ThreadLocal.withInitial(...)` | Tạo value ban đầu khi thread chưa có entry; cần quản lý lifetime của object được cấp phát |

Nếu bạn set một value rồi không remove, entry có thể tồn tại xuyên nhiều lượt sử dụng **cùng thread**. Với web server hoặc executor có thread pool, đó là rủi ro contamination và memory retention.

## 3. Vì sao cleanup phải nằm trong finally?

Cách sai:

~~~java
@Around("execution(* example.work..*.*(..))")
public Object track(ProceedingJoinPoint pjp) throws Throwable {
    operation.set(pjp.getSignature().getName());
    Object result = pjp.proceed();
    operation.remove();
    return result;
}
~~~

Nếu target hoặc advisor phía trong ném `Throwable`, lệnh `remove()` sau `proceed()` bị bỏ qua. Caller vẫn thấy lỗi, còn ThreadLocal có thể giữ giá trị cũ.

Cách sửa đơn giản khi **không có scope trước đó cần bảo toàn**:

~~~java
operation.set(pjp.getSignature().getName());
try {
    return pjp.proceed();
} finally {
    operation.remove();
}
~~~

`finally` được thực thi trên normal return và exceptional exit thông thường một khi đã vào khối try. Tuy nhiên, nếu có **nested invocation trên cùng ThreadLocal**, remove vô điều kiện trong inner advice sẽ xóa mất context của outer advice.

**Quy tắc:** Cleanup không chỉ là “xóa”. Cleanup là **khôi phục trạng thái thread trước khi scope được mở**; xóa chỉ là trường hợp trước đó chưa có value.

## 4. Nested Spring proxy calls: lỗi remove vô điều kiện

Giả sử:

~~~text
Caller -> Spring proxy của PrimaryService.process()
           @Around outer: set("process")
             target PrimaryService.process()
               -> Spring proxy SecondaryService.check()
                    @Around inner: set("check")
                      target SecondaryService.check()
                    @Around inner: finally
               target PrimaryService cần lại "process"
           @Around outer: finally
~~~

Cả hai lời gọi cùng dùng một thread và một OperationContext bean.

Nếu inner `finally` gọi `remove()`, khi trở về outer target, `get()==null` thay vì `"process"`. Outer còn đang chạy nhưng scope đã bị phá.

Cách đúng:

~~~java
String previous = context.get();  // Inner nhớ "process".
context.set("check");
try {
    return pjp.proceed();
} finally {
    if (previous == null) {
        context.remove();
    } else {
        context.set(previous);      // Inner trả lại "process".
    }
}
~~~

Outer vào từ thread trống nên `previous=null`, cuối cùng `remove()`. Inner vào lúc outer đang active nên `previous="process"`, cuối cùng restore previous. Cấu trúc này bảo toàn **cả normal và exceptional exits**.

Nếu null có nghĩa là một value hợp lệ trong domain, không được tùy tiện suy `null=không có entry`; nên dùng representation riêng cho presence hoặc scope stack. Trong bài này null là “không có current operation”.

## 5. Spring AOP proxy boundary quan trọng thế nào?

Spring AOP dùng **JDK dynamic proxy hoặc CGLIB class-based proxy**. Khi client gọi method qua Spring-managed proxy và pointcut match, around advice có thể được gọi; ngược lại:

- Object tạo bằng `new Service()` bên ngoài Spring **không** tự được advice.
- Lời gọi `this.someMethod()` bên trong target **không quay lại proxy**, nên không tạo một lượt advice mới cho method đó.
- Chuyển JDK sang CGLIB **không khắc phục self-invocation** trong Spring AOP.
- Một outer `@Around` advisor khác có thể shortcut không gọi `proceed()`, khiến inner advice chưa được vào.
- Một bean có Spring AOP proxy không đồng nghĩa **mọi method** đều match cùng advisor.
- Các method `final` và `private` không được CGLIB override/intercept như method bình thường.

**Ownership:** Một advice chỉ dọn state do chính nó đặt. Nếu inner advice chưa bao giờ được vào do outer shortcut, inner không có nghĩa vụ cleanup state mà nó chưa tạo. Nếu một component khác đặt value, scope này phải restore đúng previous value của component đó.

## 6. Ví dụ Maven/Java 17+ hoàn chỉnh

Demo sử dụng **Spring Framework 6.2.19**, Java **17+**, AspectJ Weaver **1.9.25.1**. Hai Spring-managed services đều match cùng aspect, nên chúng có thể tạo **nested interception**. Bốn tình huống được kiểm chứng:

1. Normal nested call;
2. Inner target ném exception, lỗi lan đến caller;
3. Inner ném lỗi nhưng outer target catch và recover;
4. Self-invocation `this.local()` không tạo nested advice mới.

Project dùng một `OperationContext` bean chứa ThreadLocal. `ScopeAspect` là Spring-managed `@Aspect`, dùng save/restore trong `try/finally`. Dòng stdout ổn định và `Main` có assertion để xác minh caller thread không còn context sau từng lời gọi.

### 6.1. Cấu trúc project

~~~text
spring-aop-threadlocal-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── Main.java
    ├── aop/ScopeAspect.java
    ├── context/OperationContext.java
    └── work/
        ├── PrimaryService.java
        └── SecondaryService.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-threadlocal-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
~~~

Với ứng dụng Spring Boot thực tế, nên để Spring Boot parent/BOM quản lý các Spring dependencies thay vì cố sao chép version của demo.

### 6.3. OperationContext.java

~~~java
package example.context;

public final class OperationContext {
    private final ThreadLocal<String> value = new ThreadLocal<>();

    public String get() {
        return value.get();
    }

    public void set(String operation) {
        value.set(operation);
    }

    public void remove() {
        value.remove();
    }

    public String label() {
        String current = get();
        return current == null ? "(none)" : current;
    }
}
~~~

Đây là singleton bean do `@Bean` ở AppConfig tạo. Nó sở hữu ThreadLocal, không tự set hoặc cleanup ngoài các method đã công bố. Aspect sẽ quản lý scope, còn service có thể đọc context khi đang thực thi.

### 6.4. ScopeAspect.java

~~~java
package example.aop;

import example.context.OperationContext;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ScopeAspect {

    private final OperationContext context;

    public ScopeAspect(OperationContext context) {
        this.context = context;
    }

    @Around("execution(public * example.work..*.*(..))")
    public Object withOperation(ProceedingJoinPoint pjp) throws Throwable {
        String operation = pjp.getSignature().getName();
        String previous = context.get();

        context.set(operation);
        try {
            System.out.println("aspect enter " + operation
                + " previous " + (previous == null ? "(none)" : previous));
            return pjp.proceed();
        } finally {
            if (previous == null) {
                context.remove();
            } else {
                context.set(previous);
            }
            System.out.println("aspect exit " + operation
                + " restored " + context.label());
        }
    }
}
~~~

Lưu ý:

- `@Around` nhận `ProceedingJoinPoint` và gọi `proceed()` đúng **một lần**.
- Advice trả nguyên result hoặc truyền tiếp exception (không catch/biến đổi).
- Pointcut chỉ áp dụng các **public method executions trong package example.work**; không intercept getter/setter của OperationContext hoặc method advice của ScopeAspect.
- `finally` restore/remove trước khi in log exit.
- Tên method dùng làm operation label để stdout minh họa đơn giản. Trong production, sử dụng key có phạm vi rõ ràng, tránh chứa user input hoặc PII.

### 6.5. SecondaryService.java

~~~java
package example.work;

import example.context.OperationContext;

public class SecondaryService {

    private final OperationContext context;

    public SecondaryService(OperationContext context) {
        this.context = context;
    }

    public String check() {
        System.out.println("secondary check sees " + context.label());
        return "CHECKED";
    }

    public void crash() {
        System.out.println("secondary crash sees " + context.label());
        throw new IllegalStateException("boom");
    }
}
~~~

Vì được inject qua Spring, SecondaryService là bean proxy khi advisor match. Caller khác cũng có thể gọi check/crash trực tiếp qua proxy; ở demo các lượt gọi đến từ PrimaryService.

### 6.6. PrimaryService.java

~~~java
package example.work;

import example.context.OperationContext;

public class PrimaryService {

    private final SecondaryService secondary;
    private final OperationContext context;

    public PrimaryService(SecondaryService secondary, OperationContext context) {
        this.secondary = secondary;
        this.context = context;
    }

    public String process() {
        System.out.println("primary process sees " + context.label());
        String result = secondary.check();
        System.out.println("primary resumed sees " + context.label());
        return "DONE:" + result;
    }

    public void fail() {
        System.out.println("primary fail sees " + context.label());
        secondary.crash();
    }

    public String recover() {
        System.out.println("primary recover sees " + context.label());
        try {
            secondary.crash();
        } catch (IllegalStateException ex) {
            System.out.println("primary caught " + ex.getMessage()
                + " sees " + context.label());
        }
        return "RECOVERED";
    }

    public String selfCall() {
        System.out.println("primary selfCall sees " + context.label());
        return this.local();
    }

    public String local() {
        System.out.println("primary local sees " + context.label());
        return "LOCAL";
    }
}
~~~

Sự khác nhau quan trọng:

- `secondary.check()` đi qua một Spring-managed bean khác (proxy) nên sinh **nested advice invocation**: state chuyển process → check → process.
- `this.local()` ở trong target **bỏ qua proxy** nên không có nested enter/exit cho local; nó vẫn đọc context selfCall của thread hiện tại.

### 6.7. AppConfig.java

~~~java
package example;

import example.aop.ScopeAspect;
import example.context.OperationContext;
import example.work.PrimaryService;
import example.work.SecondaryService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OperationContext operationContext() {
        return new OperationContext();
    }

    @Bean
    public SecondaryService secondaryService(OperationContext context) {
        return new SecondaryService(context);
    }

    @Bean
    public PrimaryService primaryService(
            SecondaryService secondary,
            OperationContext context) {
        return new PrimaryService(secondary, context);
    }

    @Bean
    public ScopeAspect scopeAspect(OperationContext context) {
        return new ScopeAspect(context);
    }
}
~~~

Spring AOP khám phá aspect bean được đăng ký qua `@Bean`. `@EnableAspectJAutoProxy(proxyTargetClass = true)` bật Spring AOP và sử dụng CGLIB class-based proxy khi cần, giúp lấy target bean qua concrete class. **CGLIB không tự intercept self-invocation**.

### 6.8. Main.java

~~~java
package example;

import example.context.OperationContext;
import example.work.PrimaryService;
import example.work.SecondaryService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    private static void assertClean(OperationContext context) {
        if (context.get() != null) {
            throw new AssertionError("ThreadLocal leaked: " + context.get());
        }
    }

    public static void main(String[] args) {
        try (var spring =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            PrimaryService primary = spring.getBean(PrimaryService.class);
            SecondaryService secondary = spring.getBean(SecondaryService.class);
            OperationContext context = spring.getBean(OperationContext.class);

            System.out.println("primary proxy: " + AopUtils.isAopProxy(primary));
            System.out.println("secondary proxy: " + AopUtils.isAopProxy(secondary));

            System.out.println("-- normal nested --");
            System.out.println("caller: " + primary.process());
            assertClean(context);
            System.out.println("caller context: " + context.label());

            System.out.println("-- exceptional nested --");
            try {
                primary.fail();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }
            assertClean(context);
            System.out.println("caller context: " + context.label());

            System.out.println("-- caught inside outer --");
            System.out.println("caller: " + primary.recover());
            assertClean(context);
            System.out.println("caller context: " + context.label());

            System.out.println("-- self invocation --");
            System.out.println("caller: " + primary.selfCall());
            assertClean(context);
            System.out.println("caller context: " + context.label());
        }
    }
}
~~~

Chạy trong thư mục project chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 6.9. Stdout dự kiến

~~~text
primary proxy: true
secondary proxy: true
-- normal nested --
aspect enter process previous (none)
primary process sees process
aspect enter check previous process
secondary check sees check
aspect exit check restored process
primary resumed sees process
aspect exit process restored (none)
caller: DONE:CHECKED
caller context: (none)
-- exceptional nested --
aspect enter fail previous (none)
primary fail sees fail
aspect enter crash previous fail
secondary crash sees crash
aspect exit crash restored fail
aspect exit fail restored (none)
caller caught: boom
caller context: (none)
-- caught inside outer --
aspect enter recover previous (none)
primary recover sees recover
aspect enter crash previous recover
secondary crash sees crash
aspect exit crash restored recover
primary caught boom sees recover
aspect exit recover restored (none)
caller: RECOVERED
caller context: (none)
-- self invocation --
aspect enter selfCall previous (none)
primary selfCall sees selfCall
primary local sees selfCall
aspect exit selfCall restored (none)
caller: LOCAL
caller context: (none)
~~~

Các log khác của Maven/JVM có thể xuất hiện tùy môi trường; bảng chỉ liệt kê những dòng `System.out.println` trong ví dụ. Nếu context bị leak trên caller thread, `assertClean()` ném AssertionError thay vì in tiếp các dòng kế tiếp.

### 6.10. Giải thích bốn đường gọi

**Normal:** outer set process; inner set check; inner finally restore process; outer đọc process; cuối cùng outer remove, caller thấy (none).

**Exception:** outer set fail; inner set crash rồi ném boom; inner finally restore fail; outer finally remove; caller mới catch boom. Cleanup không đồng nghĩa exception đã được xử lý bởi aspect.

**Recover:** inner crash ném exception; inner finally restore recover trước khi outer target catch. Outer target có context recover để log/khôi phục; outer finally remove.

**Self-call:** target selfCall gọi this.local() trực tiếp. Context vẫn là selfCall và không có cặp enter/exit riêng cho local. Outer finally remove khi kết thúc.

## 7. Bảng lỗi và cách sửa

| Cách viết | Normal return | Exceptional exit | Nested |
| --- | --- | --- | --- |
| Chỉ set rồi proceed | Có thể để lại giá trị cũ | Có thể để lại giá trị cũ | Có thể làm nhiễu context |
| Set, proceed, remove ở phía sau | Dọn khi thành công | **Bỏ qua cleanup** khi lỗi | Inner remove làm mất outer |
| Set, try/finally, luôn remove | Dọn được ở top-level | Dọn được khi lỗi | **Xóa state outer khi inner thoát** |
| **Capture previous, set, try/finally, restore/remove** | Bảo toàn state trước scope | Bảo toàn state khi lỗi | **Đúng với nested calls trên cùng thread** |

Không có giá trị trước scope thì dùng `remove()`; có giá trị trước scope thì restore nó. Quy tắc ownership quan trọng hơn việc đếm số lần gọi `remove()`.

## 8. Stack-based alternative

Nếu cần **danh sách các nested operations** chứ không chỉ current operation, có thể dùng một stack per thread:

~~~java
// Snippet minh họa; không phải một file của project runnable mục 6.
private final ThreadLocal<Deque<String>> stack =
    ThreadLocal.withInitial(ArrayDeque::new);

public void enter(String value) {
    stack.get().push(value);
}

public void exit() {
    Deque<String> values = stack.get();
    values.pop();
    if (values.isEmpty()) {
        stack.remove();
    }
}
~~~

Cần import `java.util.Deque` và `java.util.ArrayDeque`. `exit()` phải chạy trong finally của đúng scope sau khi enter thành công. Sản phẩm thực cần guard cho empty pop, mismatch nesting, double-close và thread switch; tốt hơn có thể cung cấp một `Scope implements AutoCloseable` được đóng đúng một lần.

**Không truyền một reference Deque mutable sang thread khác** chỉ vì nó được lưu trong ThreadLocal. Và khi stack rỗng, hãy remove toàn bộ ThreadLocal entry để không giữ đối tượng rỗng trên thread pool quá lâu.

## 9. @Async và ThreadPoolTaskExecutor không tự truyền ThreadLocal

Ví dụ luồng:

~~~text
HTTP thread T1:
  aspect set "submit"
    method tạo hoặc submit @Async task
    method trả Future/handle
  aspect finally restore/remove

Worker thread T2:
  task thực thi sau đó
  ThreadLocal T2 độc lập với ThreadLocal T1
~~~

Task trên T2 không tự kế thừa đúng value từ T1. Ngược lại, nếu T2 đã giữ state cũ do một task trước quên cleanup, nó có thể thấy **value sai**.

Spring cung cấp `org.springframework.core.task.TaskDecorator` để trang trí task trên executor như `ThreadPoolTaskExecutor`. Khi cần truyền một context tự quản lý, phải **capture ở phía submit** rồi **restore worker context trong finally**.

~~~java
// Snippet bổ sung, không thuộc project demo ở mục 6.
@Bean
public ThreadPoolTaskExecutor decoratedExecutor(OperationContext context) {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);

    executor.setTaskDecorator(task -> {
        String submittedContext = context.get();
        return () -> {
            String workerPrevious = context.get();
            if (submittedContext == null) context.remove();
            else context.set(submittedContext);

            try {
                task.run();
            } finally {
                if (workerPrevious == null) context.remove();
                else context.set(workerPrevious);
            }
        };
    });
    return executor;
}
~~~

Đoạn snippet cần imports Spring cho `@Bean` và `ThreadPoolTaskExecutor`, cùng configuration/lifecycle executor phù hợp. Nó chỉ minh họa **một loại OperationContext**, không tự xử lý Spring Security context, transactions hay mọi MDC keys.

**Không dùng `InheritableThreadLocal` như cách sửa mặc định cho thread pool.** Nó kế thừa theo thread creation, không theo mỗi task submission, nên worker tái sử dụng có thể giữ thông tin lỗi thời.

## 10. Reactive Spring: ThreadLocal không phải subscription context

Một Spring service trả `Mono<T>` hoặc `Flux<T>` có thể kết thúc **method execution** trước khi pipeline được subscribe. `@Around` advice quanh method đó chạy finally khi method trả publisher, chứ không mặc nhiên chờ stream hoàn tất.

Trong Reactor, các operators có thể chạy qua nhiều threads. Một `ThreadLocal` được đặt khi tạo publisher không tự theo subscriber tới mọi signal. Khi cần dữ liệu theo stream, hãy sử dụng **Reactor Context** hoặc cơ chế context propagation/observation phù hợp với phiên bản Spring/Reactor đang dùng.

Cần kiểm tra riêng các trường hợp completion, failure, cancellation và thread hopping. Không suy “finally của Spring @Around đã chạy” nghĩa là “tác vụ reactive đã hoàn tất và mọi state được dọn ở worker khác”.

## 11. Spring logging MDC và quyền sở hữu key

SLF4J MDC thường dùng để gắn `requestId`, `traceId` hoặc `operation` vào log trên thread hiện tại. Nếu custom aspect chỉ sở hữu key `operation`, không được xóa toàn bộ MDC trong finally vì có thể làm mất keys do thành phần khác đặt.

Ví dụ **snippet bổ sung**, cần SLF4J API/logging implementation và imports; không thuộc project Maven demo:

~~~java
@Around("execution(* com.acme.service..*.*(..))")
public Object withLoggingKey(ProceedingJoinPoint pjp) throws Throwable {
    String previous = MDC.get("operation");
    MDC.put("operation", pjp.getSignature().getName());

    try {
        return pjp.proceed();
    } finally {
        if (previous == null) MDC.remove("operation");
        else MDC.put("operation", previous);
    }
}
~~~

Ưu tiên `MDC.remove("operation")` và restore previous, **không gọi `MDC.clear()` bừa bãi** khi aspect chỉ quản lý một key.

Không đưa password, bearer token, dữ liệu tenant nhạy cảm, customer ID hoặc raw request body vào MDC/log. MDC cũng không tự động di chuyển sang thread khác; cần context propagation có chọn lọc nếu dùng executor.

## 12. @Before + @After so với @Around

Hai advice tách rời:

~~~java
@Before("serviceOperations()")
public void before() {
    operation.set("current");
}

@After("serviceOperations()")
public void after() {
    operation.remove();
}
~~~

có nguy cơ lệch ownership khi có nhiều aspects với thứ tự khác nhau, nesting, pointcut lệch nhau hoặc interceptor ở ngoài ném lỗi trước khi after advice được vào. Nó cũng khó truyền một biến previous riêng cho **đúng invocation** nếu lưu biến đó ở field singleton.

Với một context được mở và đóng trong **cùng invocation**, một `@Around` method chứa `try/finally` giúp pairing rõ ràng hơn. Tất nhiên, chính around advice đó phải thật sự được Spring AOP gọi; nếu một advisor bên ngoài shortcut trước khi around được vào, không có state từ around ấy cần dọn.

## 13. @Order, transaction và phạm vi context thực sự

Nếu có Spring transaction/cache/security advisors, một method có thể đi qua nhiều layers:

~~~text
Caller -> ScopeAspect @Around
            -> TransactionInterceptor
               -> TargetService
            <- TransactionInterceptor hoàn tất
         <- ScopeAspect finally dọn context
~~~

Nếu ScopeAspect ở ngoài transaction interceptor, nó bao phủ cả phần xử lý transaction **phía trong**; nếu order đảo, một phần transaction work có thể xảy ra ngoài ScopeAspect. Order number không tự chứng minh context có mặt tại mọi layer. Cần kiểm tra actual advisor chain và Spring transaction configuration khi scope là yêu cầu chức năng.

Nếu một inner advisor shortcut không gọi proceed, finally của outer scope **vẫn cleanup sau khi inner trả về**. Nhưng nếu outer không proceed nên một inner scope chưa được vào, inner không set state và không có cleanup cần chạy.

## 14. Kiểm thử cleanup trên cùng worker thread

Một test chỉ kiểm:

~~~java
assertNull(context.get());
~~~

sau khi một job hoàn tất ở **test thread** không đủ để chứng minh worker thread đã dọn state. ThreadLocal thuộc về **thread chạy code**, nên phải đo trên đúng worker thread.

Ma trận kiểm thử nên có:

| Case | Bên trong lời gọi | Sau khi thoát lời gọi |
| --- | --- | --- |
| Return bình thường | Thấy operation đúng | Restore/remove đúng |
| Throwable thoát target | Thấy operation trước khi throw | Finally chạy, original error vẫn propagate |
| Nested service proxy | Inner thấy tên inner | Outer thấy lại tên outer |
| Inner throw, outer catch | Inner thấy tên inner | Outer catch thấy tên outer |
| Self-invocation | Inner Java method đọc context outer | Không có nested AOP scope riêng |
| Caller có context trước | Scope tạm thời override | Restore chính giá trị trước |
| Hai threads đồng thời | Value của mỗi thread riêng | Cleanup mỗi thread độc lập |
| Pool một worker, hai requests nối tiếp | Request 1 có value riêng | Request 2 không thấy state request 1 |
| Executor TaskDecorator | Worker thấy context capture được cho phép | Worker restore previous sau task |
| Reactive/async completion | Method boundary khác task completion | Đo lifecycle đúng abstraction |

Có thể dùng `Executors.newSingleThreadExecutor()` trong test để submit hai jobs liên tiếp và kiểm tra `context.get()` **ngay ở worker thread** sau mỗi job. Với nhiều luồng, một global mutable list sự kiện không có correlation ID không đủ để chứng minh thứ tự/ownership.

## 15. Khi nào không nên dùng ThreadLocal?

Không nên dùng ThreadLocal làm giải pháp mặc định nếu:

- Dữ liệu là business input cần truyền rõ qua service methods.
- Cần xác thực/ủy quyền/tenant isolation có security contract quan trọng.
- Dữ liệu phải tồn tại xuyên nhiều threads, futures, message queues hoặc processes.
- Hệ thống dùng Reactor/WebFlux và logical flow di chuyển theo subscriptions.
- Bạn không kiểm soát được boundary cleanup hoặc có nhiều nhóm cùng sửa một key.
- Dữ liệu lớn hoặc chứa secrets/PII và có nguy cơ bị giữ sống trên worker threads.
- Một thư viện như Micrometer Observation/context propagation đã cung cấp abstraction phù hợp, tránh tự viết propagation thiếu sót.

Thay vào đó có thể cân nhắc Spring request-scoped dependency, explicit parameter/context object, Reactor Context hoặc observability library phù hợp. **ThreadLocal là một công cụ theo thread, không phải một hợp đồng xuyên mọi tầng Spring.**

## 16. Các lỗi phổ biến

| Triệu chứng | Khả năng nguyên nhân | Cách sửa |
| --- | --- | --- |
| Request sau thấy state request trước | Không `remove()` ở thread pool thread | Dọn trong finally, test thread reuse |
| Outer mất context sau inner call | Inner remove vô điều kiện | Capture previous và restore |
| Context vẫn còn sau target throw | Cleanup đặt sau proceed, không trong finally | Dùng try/finally |
| Hai request ghi đè cùng field aspect | Shared mutable singleton field | Dùng local state / scoped context / ThreadLocal khi hợp lệ |
| @Async không thấy giá trị | ThreadLocal không tự đi sang worker | TaskDecorator hoặc context propagation |
| Worker thấy giá trị lạ | Worker cũ không cleanup | Restore/remove phía worker |
| MDC traceId bị mất | Custom aspect gọi `MDC.clear()` | Remove/restore đúng key sở hữu |
| WebFlux result hoàn tất sau cleanup | @Around dọn khi method trả Publisher | Reactor Context và reactive lifecycle |
| Self-call không tạo scope inner | `this.method()` bypass proxy | Gọi qua Spring bean khác khi cần advice |
| Bean là proxy nhưng method không vào advice | Pointcut không match method đó | Kiểm tra eligible advisor |
| Trạng thái sau method không null | Trước scope đã có context hợp lệ | Restore previous là đúng; không xóa bừa |
| Memory retention tăng | Thread pool giữ value/object lớn | Giảm lifetime và remove |
| Finally log làm che exception target | Instrumentation tự ném exception | Thiết kế failure policy cho logging/metrics |
| Scoped stack báo empty pop | Push/pop không cân xứng | Scope ownership và close đúng một lần |
| Dùng InheritableThreadLocal để truyền qua pool | Kế thừa theo thread creation, không task submission | Explicit propagation có cleanup |

## 17. Bài tập kiểm tra

**Câu 1.** Vì sao singleton `@Aspect` có thể dùng một field `ThreadLocal<String>` mà không khiến tất cả threads cùng thấy một String?

**Đáp án:** ThreadLocal giữ entry riêng theo thread hiện tại. Nhưng nó không tự dọn khi method/request kết thúc, nên phải quản lý lifetime.

**Câu 2.** Inner advice gọi remove trong finally làm outer thấy null. Vì sao?

**Đáp án:** Outer và inner dùng chung ThreadLocal entry trên cùng thread; inner đã xóa context outer. Cần restore previous khi inner thoát.

**Câu 3.** Một target method ném IllegalStateException. Cleanup đặt ngay sau proceed có chạy không?

**Đáp án:** Không ở exceptional exit. Đưa cleanup vào finally; exception vẫn propagate nếu advice không nuốt lỗi.

**Câu 4.** `this.local()` trong target có tạo nested AOP scope không?

**Đáp án:** Không mặc nhiên. Self-invocation bypass Spring AOP proxy. Method local vẫn có thể đọc context outer trên cùng thread.

**Câu 5.** Thread T1 submit một task chạy trên T2; T2 có tự đọc ThreadLocal của T1 không?

**Đáp án:** Không. Cần propagation có chọn lọc tại task boundary và restore/remove ở T2.

**Câu 6.** Aspect quản lý MDC key operation nhưng gọi MDC.clear() trong finally. Sai ở đâu?

**Đáp án:** Nó có thể xóa các keys requestId/traceId do component khác sở hữu. Restore/remove đúng key.

**Câu 7.** Một method trả Mono đã xong, around advice finally đã chạy, nhưng publisher chưa có subscriber. Có mâu thuẫn không?

**Đáp án:** Không. Spring AOP method execution kết thúc khi trả publisher object, khác vòng đời reactive subscription.

**Câu 8.** Khi caller đã có context `"request"` trước method, after advice nên luôn remove?

**Đáp án:** Không. Sau invocation phải restore `"request"` theo ownership. Remove chỉ nếu trước đó trống.

**Câu 9.** Có thể chỉ kiểm tra ThreadLocal trên main thread để chứng minh worker pool không leak không?

**Đáp án:** Không. Phải kiểm tra trên worker thread được tái sử dụng.

**Câu 10.** Vì sao không nên gắn tenant/authorization policy chỉ vào một ThreadLocal chưa được validate?

**Đáp án:** Nó không tự xác thực provenance, có nguy cơ stale/missing data và không tự truyền xuyên async boundaries. Security/tenant state phải được xác thực và quản lý bằng cơ chế phù hợp.

## 18. Tài liệu chính thức

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): Spring proxy boundary, JDK/CGLIB và self-invocation.
- [Spring Framework — Declaring @Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `ProceedingJoinPoint.proceed()`, try/finally và giới hạn state per invocation.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): aspect phải là Spring bean, bật `@EnableAspectJAutoProxy`.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): TaskDecorator, ThreadPoolTaskExecutor và async execution.
- [Oracle Java 17 — ThreadLocal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): get/set/remove và giá trị riêng theo thread.
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/observability.html): các boundary của observation/context propagation.
- [Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): context theo subscription, không theo một thread cố định.
