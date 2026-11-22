# Kiểm thử việc thay đổi kết quả hoặc ánh xạ ngoại lệ bằng @Around trong Spring AOP

## 1. Bài toán và tiêu chí thành công

Trong Spring Framework, `@Around` là loại advice có khả năng can thiệp lớn nhất vào một method execution của **Spring-managed bean**: advice quyết định có gọi `ProceedingJoinPoint.proceed()`, truyền tham số nào, trả kết quả nào cho caller và xử lý exception ra sao. Do đó, kiểm thử `@Around` không thể dừng ở việc “advice đã được gọi”. Phải kiểm tra **hợp đồng mà caller thực sự quan sát** và các tác động lên target.

Bài học này tập trung vào hai hành vi **có chủ đích**:

1. **Thay đổi kết quả trả về**: method đích tạo một giá trị, advice chuyển đổi giá trị đó rồi trả một giá trị *cùng kiểu hợp đồng* cho caller. Ví dụ target trả `100`, policy giảm `10`, caller nhận `90`.
2. **Ánh xạ ngoại lệ**: method đích ném một loại lỗi hạ tầng hoặc lỗi thấp tầng đã biết; advice chuyển thành exception thuộc contract công bố ở service boundary và giữ **original cause**. Ví dụ `IllegalArgumentException("unknown:missing")` được ánh xạ sang `CatalogException("catalog-missing")` với `getCause()` trỏ về lỗi ban đầu.

Đồng thời phải chứng minh **những thứ không được biến đổi**:

- Method trả kết quả bình thường mà không cần chuyển đổi vẫn cho caller thấy chính kết quả đó.
- Exception không thuộc quy tắc mapping vẫn truyền qua, không bị gói/trả fallback tùy tiện.
- Method không khớp pointcut không tự có advice.
- Lời gọi `this.method()` nội bộ và object do `new` ở ngoài Spring không tự đi qua Spring proxy.
- Target được gọi đúng **một lần** trong các trường hợp không có chính sách retry hoặc short-circuit.
- Không có hành vi “test pass” chỉ vì câu lệnh in log: các assertions cần đánh giá **giá trị, kiểu, exception, cause và side effects**.

**Phạm vi:** Spring Aspect được áp dụng bằng Spring AOP proxy; cú pháp `@AspectJ` được Spring hỗ trợ, nhưng bài không yêu cầu AspectJ compile-time/load-time weaving.

## 2. Quyền của @Around và vì sao phải kiểm thử ở boundary

Khi caller lấy service từ `ApplicationContext`, Spring có thể tạo AOP proxy nếu advisor khớp. `@Around` bao phần còn lại của interceptor chain:

~~~text
Caller gọi service.total(100)
       |
       v
Spring AOP proxy
       |
       v
@Around: before
       |
       | pjp.proceed()
       v
Target.total(100) --> 100
       |
       v
@Around: đổi 100 thành 90
       |
       | return Integer.valueOf(90)
       v
Caller nhận int 90
~~~

Một ví dụ khác về exception:

~~~text
Caller gọi service.load("missing")
       |
       v
Spring AOP proxy
       |
       v
@Around: try { pjp.proceed(); }
       |
       v
Target.load(...) throws IllegalArgumentException
       |
       v
@Around: catch (IllegalArgumentException original)
       |
       | throw new CatalogException("catalog-missing", original)
       v
Caller bắt CatalogException
       |
       +-- getMessage() = "catalog-missing"
       +-- getCause()   = IllegalArgumentException
       +-- cause message = "unknown:missing"
~~~

Trong Spring AOP, `pjp.proceed()` tiếp tục qua **các interceptor/advice bên trong** trước khi đến target, nên exception được bắt bởi `@Around` có thể đến từ một inner interceptor chứ không chỉ từ thân target. Nếu ứng dụng có nhiều advisors, cần kiểm tra vị trí và trách nhiệm exception mapping dựa trên chain thực tế.

### Quy tắc lựa chọn advice

`@AfterReturning` phù hợp khi **chỉ quan sát** một giá trị trả về thành công; nó không thay thế reference trả về. `@AfterThrowing` phù hợp khi **chỉ ghi nhận** exception, không biến nó thành kiểu lỗi khác hay normal return. `@Around` được sử dụng ở đây vì requirement thực sự là **thay return value và ánh xạ exception**. Đừng dùng `@Around` cho mọi nhiệm vụ logging chỉ vì nó có nhiều quyền can thiệp.

Một advice chỉ cần quan sát nên viết:

~~~java
@Around("execution(* demo.PricingService.*(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
~~~

Đây là snippet minh họa trong Spring bean `@Aspect`, không phải class chạy độc lập. Nó giữ return/exception của chain. Nếu requirement không cần logic “trước và sau” trên cùng invocation, cân nhắc advice hẹp hơn.

## 3. Ma trận yêu cầu trước khi viết test

Ta có service `PricingService` và hai pointcut riêng: một cho `total(int)`, một cho `load(String)`. Ma trận được định nghĩa **trước khi chạy chương trình**:

| Lời gọi | Hành vi của target | Hành vi Spring @Around mong đợi | Caller cần thấy |
| --- | --- | --- | --- |
| `service.total(100)` | Trả primitive `100` | `proceed()` đúng một lần, trừ 10 | `int 90` |
| `service.load("ready")` | Trả `"item:ready"` | Không chuyển đổi result | `String "item:ready"` |
| `service.load("missing")` | Ném `IllegalArgumentException("unknown:missing")` | Ánh xạ đúng một lỗi đã biết, giữ cause | `CatalogException("catalog-missing")` |
| `service.load("down")` | Ném `IllegalStateException("backend-down")` | Không match quy tắc catch | Vẫn là `IllegalStateException` |
| `service.peek()` | Trả `"peek-ok"` | Không pointcut nào match | Không có marker advice |
| `service.loadInside("missing")` | `this.load("missing")` ném lỗi gốc | Internal call bypass Spring proxy | `IllegalArgumentException` không được map |
| `new PricingService(trace).total(100)` | Trả 100 | Không Spring auto-proxy | `int 100` |
| `new PricingService(trace).load("missing")` | Ném lỗi gốc | Không advice | `IllegalArgumentException` |

Các ca dương xác nhận transformation/mapping đúng, trong khi ca âm xác nhận **phạm vi thay đổi không lan ngoài yêu cầu**. Nếu chỉ kiểm tra `total(100) == 90`, có thể vẫn còn bug nuốt exception; nếu chỉ assert `CatalogException`, bạn có thể bỏ mất stack/cause gốc.

## 4. Project Maven Java 17+ đầy đủ

Project Spring Framework thuần, không cần Spring Boot, server, database hay mock library.

~~~text
spring-around-contract-test/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── App.java
    │   ├── EventTrace.java
    │   ├── PricingService.java
    │   ├── CatalogException.java
    │   └── ResultMappingAspect.java
    └── test/java/demo/
        └── AroundContractTest.java
~~~

Yêu cầu: Java 17+, Maven 3.9+ và khả năng lấy dependencies. Phiên bản minh họa cố định: **Spring Framework 6.2.0**, **AspectJ Weaver 1.9.22**, **JUnit Jupiter 5.11.0**. Đây là version cho ví dụ, không khẳng định phiên bản mới nhất.

### 4.1. Maven pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-around-contract-test</artifactId>
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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
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

`spring-context` cung cấp bean container/Java config. `spring-aop` cung cấp proxy, advisors và `AopUtils`. `aspectjweaver` được Spring dùng cho biểu thức `@AspectJ`; chỉ thêm dependency đó **không kích hoạt AspectJ weaving**. JUnit Jupiter và Surefire cho phép chạy các test tự động.

### 4.2. EventTrace: quan sát cả advice và target

Tạo `src/main/java/demo/EventTrace.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

public class EventTrace {
    private final List<String> events = new ArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

Trong ví dụ, mỗi test tạo một context/trace riêng và chạy tuần tự, vì thế `ArrayList` phù hợp. Nếu code thật ghi audit đồng thời nhiều threads, cần collector hoặc logging framework thread-safe. `snapshot()` giúp assertions so nội dung trace mà không sửa danh sách gốc.

Trace được ghi **bên trong method advice và target**, cho phép phân biệt `"advice chạy"` với `"target chạy"`; chỉ dùng `AopUtils.isAopProxy` không chứng minh advisor cụ thể đã khớp.

### 4.3. Lỗi cấp contract: CatalogException

Tạo `src/main/java/demo/CatalogException.java`:

~~~java
package demo;

public class CatalogException extends RuntimeException {
    public CatalogException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

`CatalogException` là runtime exception của ví dụ, **không phải built-in exception của Spring**. Constructor nhận `cause` là yếu tố bắt buộc trong policy đã đề ra: caller và observability có thể truy ngược lỗi gốc. Không chuyển lỗi thành chuỗi message rồi đánh mất stack/cause.

Một contract tốt nên giải thích vì sao ánh xạ `IllegalArgumentException` thành `CatalogException` ở service boundary có ý nghĩa. Ở ví dụ học tập, `IllegalArgumentException("unknown:missing")` tượng trưng cho lỗi “không tìm thấy” từ tầng nội bộ; production không nên bắt **mọi `IllegalArgumentException`** trong mọi service vì nó còn có thể biểu thị **programming bug**. Hãy thu hẹp pointcut và dùng loại lỗi cụ thể hơn nếu module có cơ chế error code rõ.

### 4.4. Target PricingService

Tạo `src/main/java/demo/PricingService.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class PricingService {
    private final EventTrace trace;
    private final AtomicInteger totalCalls = new AtomicInteger();
    private final AtomicInteger loadCalls = new AtomicInteger();

    public PricingService(EventTrace trace) {
        this.trace = trace;
    }

    public int total(int base) {
        totalCalls.incrementAndGet();
        trace.add("TARGET:total:" + base);
        return base;
    }

    public String load(String code) {
        loadCalls.incrementAndGet();
        trace.add("TARGET:load:" + code);

        if ("missing".equals(code)) {
            throw new IllegalArgumentException("unknown:missing");
        }
        if ("down".equals(code)) {
            throw new IllegalStateException("backend-down");
        }
        return "item:" + code;
    }

    public String peek() {
        trace.add("TARGET:peek");
        return "peek-ok";
    }

    public String loadInside(String code) {
        trace.add("TARGET:loadInside");
        return this.load(code);
    }

    public int totalCalls() {
        return totalCalls.get();
    }

    public int loadCalls() {
        return loadCalls.get();
    }
}
~~~

Các method có chủ đích:

- `total(int)` trả đúng tham số `base`. Nếu caller nhận 90 khi đưa vào 100, chứng tỏ **phép biến đổi return thuộc advice**, không phải target.
- `load("ready")` trả bình thường; `load("missing")` ném một lỗi đúng policy; `load("down")` ném loại lỗi khác để thử passthrough.
- `peek()` không match bất kỳ pointcut nào ở phần 4.5.
- `loadInside(String)` gọi `this.load(code)` **bên trong cùng target**, là ví dụ self-invocation không qua Spring proxy.
- `totalCalls()/loadCalls()` là các bộ đếm **số lần thực thi method target**. Một test có thể assert số lần bằng 1 để phát hiện retry/double proceed không được yêu cầu.

Code chạy với Java 17; class và methods không `final`, nên Spring có thể dùng CGLIB class proxy. Tránh hiểu rằng `new PricingService(...)` ở ngoài context cũng được advice; việc đối tượng là Spring-managed bean và caller đi qua proxy mới là điều kiện cần.

### 4.5. Spring @Aspect: biến đổi giá trị và map exception

Tạo `src/main/java/demo/ResultMappingAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ResultMappingAspect {
    private final EventTrace trace;
    private final AtomicInteger adviceCalls = new AtomicInteger();

    public ResultMappingAspect(EventTrace trace) {
        this.trace = trace;
    }

    @Around("execution(int demo.PricingService.total(int))")
    public Object discount(ProceedingJoinPoint point) throws Throwable {
        adviceCalls.incrementAndGet();
        trace.add("ADVICE:total:before");

        int original = (Integer) point.proceed();
        int transformed = original - 10;

        trace.add("ADVICE:total:after");
        return transformed;
    }

    @Around("execution(String demo.PricingService.load(String))")
    public Object mapLoadError(ProceedingJoinPoint point) throws Throwable {
        adviceCalls.incrementAndGet();
        trace.add("ADVICE:load:before");

        try {
            Object result = point.proceed();
            trace.add("ADVICE:load:return");
            return result;
        } catch (IllegalArgumentException original) {
            trace.add("ADVICE:load:map");
            throw new CatalogException("catalog-missing", original);
        }
    }

    public int adviceCalls() {
        return adviceCalls.get();
    }
}
~~~

Cơ chế và ý nghĩa kiểm thử:

1. `@Around` trả `Object`, có tham số `ProceedingJoinPoint` đầu tiên và khai báo `throws Throwable` để cho phép chain truyền exception.
2. `discount(...)` chặn đúng `int PricingService.total(int)`. Vì target trả primitive `int`, result của `proceed()` tại advice được boxed thành `Integer`, nên phép cast/unbox `(Integer)` là phù hợp trong **project này**.
3. `return transformed;` được auto-box thành `Integer` trên đường AOP interceptor; caller của method `int total(int)` nhận `int` sau unboxing. Không trả `String "90"` hoặc `null`.
4. `point.proceed()` được gọi **một lần**, không phải hai lần. Nếu target ghi DB hoặc gửi thông báo, hai lần proceed sẽ tạo side effects ngoài yêu cầu.
5. `mapLoadError(...)` có scope **duy nhất `PricingService.load(String)`**, không áp dụng cho `peek` hay toàn bộ Spring beans. Khi không có exception, nó trả **chính result** của `proceed()`.
6. Chỉ `IllegalArgumentException` bị map thành `CatalogException`. Exception `IllegalStateException` không khớp `catch`, nên **tự propagate** qua advice tới caller.
7. Constructor `CatalogException("catalog-missing", original)` giữ cause gốc; không ép lỗi thành normal return hoặc thay bằng exception thiếu nguyên nhân.
8. `adviceCalls` đếm các lần enter advice, bao gồm invocation sẽ ném exception. Mỗi test kiểm tra cả counter lẫn trace, không dựa duy nhất vào log.
9. Bốn advice pointcut ở đây **không tồn tại**: chỉ có hai `@Around` methods, trên hai method đích khác nhau. Vì vậy không có ambiguity về thứ tự multiple advices trên cùng target method.
10. Trong ứng dụng thật, việc biến đổi giá bằng trừ 10 và map exception cần **business contract rõ ràng**. Ví dụ cố ý đơn giản để kiểm chứng cơ chế Spring AOP, không phải một giải pháp tính giá hoặc error mapping sản xuất hoàn chỉnh.

### 4.6. Java configuration và main

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
    public EventTrace eventTrace() {
        return new EventTrace();
    }

    @Bean
    public PricingService pricingService(EventTrace trace) {
        return new PricingService(trace);
    }

    @Bean
    public ResultMappingAspect resultMappingAspect(EventTrace trace) {
        return new ResultMappingAspect(trace);
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);

            boolean proxy = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxy);

            int total = service.total(100);
            System.out.println("TOTAL: " + total);

            String loaded = service.load("ready");
            System.out.println("LOAD_OK: " + loaded);

            boolean mapped = false;
            try {
                service.load("missing");
            } catch (CatalogException error) {
                Throwable cause = error.getCause();
                mapped = "catalog-missing".equals(error.getMessage())
                        && cause instanceof IllegalArgumentException
                        && "unknown:missing".equals(cause.getMessage());
                System.out.println(
                        "MAPPED: " + error.getClass().getSimpleName()
                        + " <= " + cause.getClass().getSimpleName());
            }

            boolean passedThrough = false;
            try {
                service.load("down");
            } catch (IllegalStateException error) {
                passedThrough = "backend-down".equals(error.getMessage());
                System.out.println(
                        "PASSTHROUGH: " + error.getClass().getSimpleName());
            }

            int calls = aspect.adviceCalls();
            int totalTargets = service.totalCalls();
            int loadTargets = service.loadCalls();

            System.out.println(
                    "COUNTS: advice=" + calls
                    + ",total=" + totalTargets
                    + ",load=" + loadTargets);

            if (!proxy
                    || total != 90
                    || !"item:ready".equals(loaded)
                    || !mapped
                    || !passedThrough
                    || calls != 4
                    || totalTargets != 1
                    || loadTargets != 3) {
                throw new IllegalStateException(
                        "Spring AOP contract verification failed");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Bài chạy trong `AnnotationConfigApplicationContext`, không cần Spring TestContext hoặc Spring Boot.

- `@EnableAspectJAutoProxy(proxyTargetClass = true)` bật hạ tầng Spring AOP proxy và yêu cầu class-based proxy cho bean phù hợp. Target không phải `final`.
- `@Bean` factory tạo service/aspect/trace đều là Spring-managed beans; aspect cũng phải được **đăng ký làm bean**, chỉ `@Aspect` chưa đủ.
- `context.getBean(PricingService.class)` trả Spring reference; `AopUtils.isAopProxy` xác nhận proxy tồn tại.
- `total(100)` chứng minh caller nhận **90** do advice chứ không phải **100** của target.
- `load("ready")` chứng minh result bình thường không bị thay khi advice chỉ có policy map exception.
- `load("missing")` chứng minh **kiểu exception mới, message và cause gốc**.
- `load("down")` chứng minh **loại exception không được map** vẫn truyền thẳng.
- `adviceCalls=4` và các bộ đếm target cho thấy bốn invocation advice đều dẫn tới target đúng một lần: một total và ba load.
- Chỉ sau khi tất cả điều kiện đều đúng, code mới in `CHECK: PASS`. Một lỗi return type, mapping sai, bỏ `proceed()` hoặc proceed trùng có thể khiến chương trình fail.

### 4.7. Chạy Maven và stdout mong đợi

Tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do mã trong `App.main` in ra:

~~~text
PROXY: true
TOTAL: 90
LOAD_OK: item:ready
MAPPED: CatalogException <= IllegalArgumentException
PASSTHROUGH: IllegalStateException
COUNTS: advice=4,total=1,load=3
CHECK: PASS
~~~

Maven hoặc logging framework có thể in thêm thông báo khác. Đây là **stdout mong đợi theo code**, không phải báo cáo Maven đã chạy trên máy thật. Nếu gặp lỗi khi lấy dependencies hoặc fail điều kiện, chương trình không thể in dòng `CHECK: PASS` theo nhánh thành công.

## 5. JUnit 5 integration tests: ca được đổi, ca không được đổi

Đây là phần quan trọng nhất. Test thực sự **gọi service bean qua Spring proxy** và assert cả output, exception lẫn trace. Mỗi test tạo một context riêng nên recorder/counter không bị rò rỉ giữa các test.

Tạo `src/test/java/demo/AroundContractTest.java`:

~~~java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AroundContractTest {
    @Test
    void transformsReturnValueAndCallsTargetOnce() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals(90, service.total(100));
            assertEquals(1, service.totalCalls());
            assertEquals(1, aspect.adviceCalls());
            assertEquals(
                    List.of("ADVICE:total:before",
                            "TARGET:total:100",
                            "ADVICE:total:after"),
                    trace.snapshot());
        }
    }

    @Test
    void successfulReturnPassesThroughUnchanged() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertEquals("item:ready", service.load("ready"));
            assertEquals(1, service.loadCalls());
            assertEquals(1, aspect.adviceCalls());
            assertEquals(
                    List.of("ADVICE:load:before",
                            "TARGET:load:ready",
                            "ADVICE:load:return"),
                    trace.snapshot());
        }
    }

    @Test
    void knownExceptionIsMappedAndCauseIsPreserved() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            CatalogException mapped = assertThrows(
                    CatalogException.class,
                    () -> service.load("missing"));

            assertEquals("catalog-missing", mapped.getMessage());
            IllegalArgumentException cause =
                    assertInstanceOf(IllegalArgumentException.class,
                            mapped.getCause());
            assertEquals("unknown:missing", cause.getMessage());
            assertEquals(1, service.loadCalls());
            assertEquals(1, aspect.adviceCalls());
            assertEquals(
                    List.of("ADVICE:load:before",
                            "TARGET:load:missing",
                            "ADVICE:load:map"),
                    trace.snapshot());
        }
    }

    @Test
    void unrelatedExceptionIsNotMapped() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            IllegalStateException original = assertThrows(
                    IllegalStateException.class,
                    () -> service.load("down"));

            assertEquals("backend-down", original.getMessage());
            assertEquals(1, service.loadCalls());
            assertEquals(1, aspect.adviceCalls());
            assertEquals(
                    List.of("ADVICE:load:before",
                            "TARGET:load:down"),
                    trace.snapshot());
        }
    }

    @Test
    void nonMatchingMethodIsNotInterceptedByTheseAdvices() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertEquals("peek-ok", service.peek());
            assertEquals(0, aspect.adviceCalls());
            assertEquals(List.of("TARGET:peek"), trace.snapshot());
        }
    }

    @Test
    void selfInvocationDoesNotApplyTheMappingAdvice() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            IllegalArgumentException raw = assertThrows(
                    IllegalArgumentException.class,
                    () -> service.loadInside("missing"));

            assertEquals("unknown:missing", raw.getMessage());
            assertEquals(1, service.loadCalls());
            assertEquals(0, aspect.adviceCalls());
            assertEquals(
                    List.of("TARGET:loadInside",
                            "TARGET:load:missing"),
                    trace.snapshot());
        }
    }

    @Test
    void manualObjectOutsideSpringDoesNotGetAutoProxy() {
        EventTrace trace = new EventTrace();
        PricingService plain = new PricingService(trace);

        assertFalse(AopUtils.isAopProxy(plain));
        assertEquals(100, plain.total(100));

        IllegalArgumentException raw = assertThrows(
                IllegalArgumentException.class,
                () -> plain.load("missing"));

        assertEquals("unknown:missing", raw.getMessage());
        assertEquals(1, plain.totalCalls());
        assertEquals(1, plain.loadCalls());
        assertEquals(
                List.of("TARGET:total:100",
                        "TARGET:load:missing"),
                trace.snapshot());
    }
}
~~~

Chúng ta có **bảy test methods**. Điểm quan trọng nhất: các test không chỉ assert kết quả “có vẻ đúng”, mà còn assert **số lượt gọi target, số lượt advice và chuỗi sự kiện**:

- Test 1 chứng minh transform thành công và chỉ gọi target một lần; biến đổi không được thực hiện ở target.
- Test 2 chứng minh `@Around` **không đổi kết quả** khi không có lý do đổi.
- Test 3 chứng minh exception mapping đúng type/message/cause; không đánh mất thông tin lỗi gốc.
- Test 4 chứng minh exception khác đi qua; giúp bắt lỗi `catch(Throwable)` rồi map tất cả.
- Test 5 chứng minh `peek()` không bị các pointcut ngoài phạm vi can thiệp.
- Test 6 chứng minh **self-invocation** là giới hạn proxy-based Spring AOP, không phải lỗi parser pointcut.
- Test 7 chứng minh object thường ngoài Spring không tự được auto-proxy, dù gọi cùng method Java.

Chạy:

~~~bash
mvn clean test
~~~

Khi tất cả test pass, báo cáo của Maven Surefire sẽ có dòng tương đương:

~~~text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
~~~

File báo cáo thường nằm tại:

~~~text
target/surefire-reports/demo.AroundContractTest.txt
~~~

Nếu test fail, đọc **assertion failure và root cause**. Không sửa expected values cho khớp output sai; hãy tìm lỗi trong pointcut, bean registration, return contract, exception mapping và số lần proceed. Đây là kết quả **mong đợi**, không phải xác nhận đã chạy test thật trong môi trường hiện tại.

## 6. Vì sao phải assert đúng kiểu return và đúng cause?

### 6.1. Trả một giá trị có vẻ đúng nhưng sai declared type

Với method:

~~~java
public int total(int base) {
    return base;
}
~~~

Spring AOP `@Around` thường trả `Object`, nhưng caller vẫn gọi **method khai báo `int`**. `return "90";` từ advice là `String`, không tương thích `int`; `return null;` cũng không hợp lệ vì primitive không có `null`. Framework có thể báo `AopInvocationException`/lỗi unboxing hoặc kiểu không tương thích tùy cách proxy/chain xử lý.

Ví dụ đúng cho contract minh họa:

~~~java
@Around("execution(int demo.PricingService.total(int))")
public Object discount(ProceedingJoinPoint point) throws Throwable {
    int raw = (Integer) point.proceed();
    return raw - 10;  // Auto-box thành Integer; caller nhận int.
}
~~~

Snippet này là **phương án rút gọn** của advice trong project chính, không thêm cả hai vào cùng aspect. Nếu dùng một around advice wildcard match `String`, `boolean`, `Optional` lẫn `int`, không thể ép mọi result thành `Integer`. Phải thu hẹp pointcut hoặc xử lý đúng declared return type cho từng method.

### 6.2. Giá trị đổi đúng nhưng target không chạy

Một quanh advice:

~~~java
@Around("execution(int demo.PricingService.total(int))")
public Object misleading(ProceedingJoinPoint point) {
    return 90;
}
~~~

Có thể làm `assertEquals(90, service.total(100))` pass, nhưng **không gọi `proceed()`**. Điều này sẽ phá side effects của target nếu business method thực sự cần chạy. Test của chúng ta còn kiểm tra `service.totalCalls() == 1` và event `TARGET:total:100`, vì requirement là **chuyển đổi kết quả sau khi target chạy**, không phải short-circuit.

Short-circuit đôi khi là thiết kế hợp lệ (ví dụ cache hit) nhưng phải được tuyên bố ngay trong contract/test. Không thể suy nó từ một test chỉ so giá trị.

### 6.3. Exception mới có type đúng nhưng mất nguyên nhân

Mẫu sai:

~~~java
catch (IllegalArgumentException original) {
    throw new CatalogException("catalog-missing", null);
}
~~~

Caller thấy đúng `CatalogException` nhưng `getCause() == null`. Điều đó làm khó việc tìm lỗi từ tầng dưới. Mẫu đúng:

~~~java
catch (IllegalArgumentException original) {
    throw new CatalogException("catalog-missing", original);
}
~~~

Nếu module có API mapping error code chi tiết hơn, giữ thêm request ID/status code theo contract (và không log thông tin nhạy cảm). Không cần sao chép nguyên văn message lỗi thấp tầng cho người dùng cuối; giữ cause là khác với **phơi bày toàn bộ thông tin nội bộ**.

### 6.4. Catch quá rộng biến lỗi không liên quan thành lỗi “known”

~~~java
try {
    return point.proceed();
} catch (Throwable error) {
    throw new CatalogException("catalog-missing", error);
}
~~~

Đây là mẫu **không phù hợp** nếu policy chỉ định map một loại lỗi. Nó có thể che `IllegalStateException`, lỗi programming và cả những `Error` nghiêm trọng thành một category giả. Test `unrelatedExceptionIsNotMapped` phát hiện bug đó.

Đôi khi application cần ánh xạ nhiều loại lỗi sang một exception API chung; hãy **chỉ định rõ nhóm lỗi được phép**, bảo toàn cause, và có integration tests kiểm chứng từng nhánh. Không đưa catch rộng vào mọi service chỉ vì nó thuận tiện.

### 6.5. Biến lỗi thành normal return không nằm trong yêu cầu

~~~java
try {
    return point.proceed();
} catch (IllegalArgumentException error) {
    return "item:unknown";
}
~~~

Đoạn này không ném `CatalogException` mà trả một `String` bình thường. Đây là **fallback**, không phải **exception mapping**. Với business policy cho phép fallback, nó có thể có ý nghĩa, nhưng sẽ khiến caller không nhận được lỗi và có thể làm transaction/cache/metrics diễn giải request là thành công. Test phải phân biệt **map-to-exception** và **recover-to-value**.

Trong bài này, mapping là **throw new CatalogException(...)**, không phải trả fallback.

## 7. Phương pháp thiết kế test để bắt regression

Để không bỏ sót lỗi, xây một ma trận theo **đường đi của lời gọi** và **outcome**:

| Trục | Ca dương cần chứng minh | Ca âm cần chứng minh |
| --- | --- | --- |
| Result transform | Target trả 100, caller nhận 90 | Target phải thực sự chạy; không được đổi method khác |
| Error map | Lỗi known được chuyển đúng exception API | Lỗi không thuộc policy không bị map |
| Success passthrough | `load("ready")` trả bình thường đúng value | Không tự bọc result trong container sai type |
| Cause preservation | `CatalogException.getCause()` là lỗi gốc | Không bỏ `cause` hoặc thay bằng lỗi unrelated |
| Proxy boundary | Spring bean được proxy; advice chạy | Raw `new` object không auto-proxy |
| Self-invocation | External caller gọi `load` được map | `this.load` trong target bypass proxy |
| Invocation count | Mỗi lượt gọi target đúng một lần | Không quên `proceed()`, không retry vô hạn |
| Advice scope | `total` và `load` được advice | `peek` không bị advice |
| Error semantics | Exception ném qua caller | Không tự chuyển thrown exit thành normal return |

Bộ test không cần tạo mọi tổ hợp của cả ứng dụng. Nhưng một requirement có **hai điều kiện độc lập** (match pointcut và xử lý đúng outcome), nên có ít nhất một ca bảo đảm từng điều kiện và một ca âm riêng chống việc mở rộng không chủ ý.

Nếu nhiều `@Around`/transaction/cache advisors cùng match một method, việc quan sát **event trace** và số lần gọi target là quan trọng vì `proceed()` chuyển qua phần còn lại của advisor chain. Đối với một target được cache, cache hit có thể khiến target không chạy; trong trường hợp đó **test expected invocation count phải tuân contract cache** chứ không mặc định một lần target ở mọi lời gọi.

## 8. Mutation testing thủ công: cố ý làm sai và xem test fail

Các thay đổi sau được làm **từng cái một**, chỉ cho học tập. Sau mỗi lần thử, hoàn nguyên `ResultMappingAspect.java` rồi chạy lại `mvn clean test`.

### Mutation A: quên gọi proceed

Thay đoạn transform bằng:

~~~java
trace.add("ADVICE:total:before");
trace.add("ADVICE:total:after");
return 90;
~~~

Nếu chỉ assert `service.total(100)==90`, mutation sẽ lọt. Trong bộ test thật, `service.totalCalls()==1` và `TARGET:total:100` biến mất nên test dương fail.

### Mutation B: return sai kiểu

~~~java
return "90";
~~~

Với `int total(int)`, không tương thích contract. Lời gọi proxy có thể ném exception thay vì trả số nguyên. Kiểm thử caller-facing result bắt được, thay vì chỉ kiểm tra advice đã được gọi.

### Mutation C: map mọi exception

~~~java
catch (Throwable original) {
    throw new CatalogException("catalog-missing", original);
}
~~~

Ca `load("down")` phải nhận `IllegalStateException`; mutation biến nó thành `CatalogException`, nên `unrelatedExceptionIsNotMapped` fail.

### Mutation D: mất cause

~~~java
throw new CatalogException("catalog-missing", null);
~~~

Ca map exception vẫn bắt đúng `CatalogException` và message, nhưng assertion `assertInstanceOf(IllegalArgumentException.class, mapped.getCause())` fail. Đây là lý do không nên assert chỉ exception class.

### Mutation E: nới pointcut quá rộng

Đổi:

~~~java
@Around("execution(String demo.PricingService.load(String))")
~~~

thành một biểu thức match cả các method khác có `String` return, ví dụ:

~~~java
@Around("execution(String demo.PricingService.*(..))")
~~~

Method `peek()` vốn không thuộc chính sách sẽ có `ADVICE:load:before` và advice counter tăng, khiến `nonMatchingMethodIsNotInterceptedByTheseAdvices` fail. Nếu future method có String arguments khác nhau, pointcut còn có thể chặn ngoài dự kiến.

### Mutation F: nuốt exception và trả fallback

~~~java
catch (IllegalArgumentException original) {
    return "item:unknown";
}
~~~

Ca `knownExceptionIsMappedAndCauseIsPreserved` fail vì không nhận `CatalogException`. Contract thay đổi từ thrown exit thành normal return, khác hoàn toàn mapping yêu cầu.

Điểm chung: **một positive test không đủ**. Các negative tests giúp giữ đúng *phạm vi và loại can thiệp*, tránh vô tình thay đổi hợp đồng khi refactor pointcut/advice.

## 9. Phân biệt @AfterThrowing và @Around khi ánh xạ exception

Trong Spring AOP:

~~~java
@AfterThrowing(
    pointcut = "execution(String demo.PricingService.load(String))",
    throwing = "error",
    argNames = "error"
)
public void logError(IllegalArgumentException error) {
    System.out.println(error.getMessage());
}
~~~

`@AfterThrowing` là lựa chọn thích hợp **nếu chỉ muốn log** khi target invocation ném lỗi. Nó **không có cơ chế thay exception đang truyền qua thành exception object khác** theo cách khai báo trong mẫu này. Để chủ động catch và throw một exception mới, `@Around` là loại advice phù hợp khi requirement thật sự là mapping.

Mặt khác, `@Around` có thể bọc các advisors bên trong; lỗi bắt được từ `point.proceed()` có thể đến từ **interceptor/advice ở trong**, không nhất thiết chỉ từ target method. Cần xác định order/precedence nếu ánh xạ lỗi liên quan transaction, security hoặc cache. Đừng catch `Throwable` rộng rồi coi mọi lỗi là từ target.

Nếu cần áp dụng exception mapping thống nhất ở HTTP API boundary, Spring MVC có `@ExceptionHandler`/`@ControllerAdvice` cho presentation-level exception translation. Đó là một **cơ chế khác** với Spring AOP, không nên sử dụng chỉ để chứng minh một `@Around` có thể map lỗi. Bài này vẫn xét **method boundary của Spring bean**.

## 10. Ràng buộc về checked exception và proxy type

Ví dụ chính ánh xạ từ `IllegalArgumentException` sang **runtime `CatalogException`**. Đây là lựa chọn có chủ ý để tránh một vấn đề khác làm nhiễu bài học.

Nếu `@Around` ném một **checked exception** mà method khai báo qua JDK proxy **không cho phép trong throws declaration**, caller có thể gặp wrapper như `UndeclaredThrowableException` theo cơ chế Java proxy. Với CGLIB và các adapters khác, biểu hiện có thể khác. Vì vậy:

- Nếu API cần mapped checked exception, xem **throws declaration của interface/implementation** và proxy strategy;
- Kiểm thử trên đúng Spring context thực tế (JDK vs CGLIB), không chỉ invoke raw target;
- Đừng đổi exception class rồi mặc định caller luôn thấy đúng class đó dù method signature không công bố nó;
- Nếu mapping nhằm thống nhất business API lỗi và không muốn checked exception wrappers, một runtime exception được thiết kế rõ thường đơn giản hơn, nhưng cần thống nhất contract toàn ứng dụng.

`@Around` khai báo `throws Throwable` vì đó là API `ProceedingJoinPoint.proceed()`; điều này **không tự thay đổi throws clause** của interface method mà caller gọi. Advice signature có `throws Throwable` không đồng nghĩa target method được phép ném mọi checked exception qua proxy mà không có hệ quả.

## 11. Thứ tự advisors và giao dịch

Nếu một Spring bean còn sử dụng transaction/cache/security advisors, advice mới có thể nằm ở **bên ngoài hoặc bên trong** những advisors đó. Với Spring `@Order`, số nhỏ hơn có precedence cao hơn, nên outer advice đi vào trước và đi ra sau inner advice theo mô hình nesting.

Ví dụ:

~~~text
Caller
  |
  v
ResultMapping @Around (outer)
  | proceed()
  v
Transaction advisor (inner)
  | proceed()
  v
Target throws IllegalArgumentException
  |
  v
Transaction advisor xử lý lỗi theo rollback rules
  |
  v
ResultMapping catch -> throw CatalogException
  |
  v
Caller
~~~

Ở trường hợp khác, transaction advisor có thể nằm **bên ngoài** mapping advice; khi đó transaction logic nhìn thấy exception đã được map. Điều này có thể ảnh hưởng rollback/metrics/status policy. Không khẳng định một order cố định cho transaction advisor nếu không kiểm tra cấu hình.

Muốn test đúng tương tác:

1. Tạo context có **các advisors thực tế** của ứng dụng.
2. Khai báo order rõ nếu nghiệp vụ yêu cầu.
3. Gọi qua Spring proxy, xác nhận kết quả mapping và trạng thái transaction/rollback bằng integration test phù hợp.
4. Không giả định “cứ exception mới extends RuntimeException thì mọi transaction luôn rollback”: Spring transaction có cấu hình rollback rules riêng.
5. Tránh tự gọi `method.invoke(target,...)` trong advice vì nó có thể bypass những advisors ở phần còn lại của chain; dùng `point.proceed()`.

## 12. Các lỗi kiểm thử dễ gặp

**Lỗi 1: Test tự `new PricingService` nhưng mong aspect chạy.**  
Object tự tạo ngoài container không được auto-proxy. Test `manualObjectOutsideSpringDoesNotGetAutoProxy` là ca âm; test chính phải lấy bean từ `AnnotationConfigApplicationContext`.

**Lỗi 2: Chỉ dùng `AopUtils.isAopProxy`.**  
Proxy có thể được tạo vì advisor khác. Phải assert **marker trong advice cần test**, kết quả caller và target invocation count.

**Lỗi 3: Chỉ kiểm tra exception class mới.**  
Nếu mất cause, test vẫn có thể pass. Assert **message/error code, cause type và cause message** theo contract.

**Lỗi 4: Không test exception không được map.**  
Một catch rộng sẽ biến mọi lỗi thành lỗi known. Đối chứng `IllegalStateException` là ca âm quan trọng.

**Lỗi 5: Self-invocation bị đọc sai thành lỗi mapping.**  
`this.load("missing")` từ trong target không đi qua Spring proxy nên mapping không chạy; không chuyển `@Around` thành một advice khác để chữa self-invocation. Nếu cần policy áp dụng, chuyển method sang collaborator bean và gọi qua injected proxy.

**Lỗi 6: Quên kiểm tra số lần proceed.**  
Advice có thể gọi `proceed()` hai lần rồi chỉ trả kết quả cuối, tạo side effects trùng. Assert target counter để khóa yêu cầu exactly-once trong ví dụ.

**Lỗi 7: Test state dùng chung giữa các ca.**  
Nếu dùng static counter hoặc tái dùng context mà không reset, test ảnh hưởng nhau. Ví dụ tạo một context mới cho mỗi test và trace instance riêng.

**Lỗi 8: Logging ném exception làm outcome thay đổi.**  
Nếu việc ghi log trong catch thất bại, caller có thể nhận exception của logger thay vì exception mapping đã thiết kế. Trong production, định nghĩa error policy cho logging/metrics; test cả logging failure nếu đó là yêu cầu thực tế.

**Lỗi 9: Mapping sai loại hoặc sai contract return.**  
`@Around` trả `Object`, nhưng method `int` cần wrapper số tương thích, `String` cần String/reference hợp lệ; không tự trả `null` cho primitive hoặc trả một chuỗi lỗi thay exception khi policy không cho phép.

**Lỗi 10: Test chỉ dựa vào console output.**  
Console chứa stdout của Maven/framework và không phải interface ổn định. Dùng assertions đối với result, exception, trace và counters; console chỉ để quan sát khi học.

## 13. Các bài tập mở rộng

### 13.1. Chuyển phép transform thành có điều kiện

Thay yêu cầu từ “trừ 10 mọi lần” thành “chỉ giảm nếu result lớn hơn hoặc bằng 10”. Khi đó, `discount` có thể kiểm tra result sau `proceed()`, nhưng phải xác định contract với số âm, overflow và bất kỳ transformation nào không còn hợp lệ về nghiệp vụ.

Viết test dương cho `total(100)` → `90` và ca âm `total(5)` → `5`. Đừng sửa target method nếu điều cần kiểm tra là **result transformation bởi aspect**.

### 13.2. Ánh xạ một exception type chuyên biệt

Thay vì dùng `IllegalArgumentException`, tạo `ItemNotFoundException` riêng ở tầng nội bộ và chỉ `catch(ItemNotFoundException original)`. Đây là contract có ý nghĩa hơn trong production vì không vô tình map các `IllegalArgumentException` phát sinh từ bug lập trình.

Viết test rằng `IllegalArgumentException` không mang “item not found” vẫn propagate, còn lỗi chuyên biệt được map. Giữ cause.

### 13.3. Kiểm thử trả fallback có chủ đích

Nếu requirement thay đổi từ **throw mapped exception** sang **trả fallback `"item:unknown"`**, hãy viết một `@Around` mới với contract rõ ràng và test khẳng định:
- Method đích được gọi hay không;
- Caller nhận đúng String fallback;
- Exception không còn truyền tới caller **vì chính sách mới**, không phải do bị nuốt tình cờ;
- Các exception ngoài policy vẫn propagate.

Đừng đổi một dòng catch rồi để tên test `knownExceptionIsMappedAndCauseIsPreserved` trở nên sai nội dung.

### 13.4. Thêm nhiều advisors vào cùng join point

Tạo một `@Before` audit aspect và một `@Around` mapping aspect cùng khớp `load`, đặt `@Order` tường minh và ghi trace hai chiều. Thử hai cách ordering. Quan sát exception nào đi qua từng advisor và khẳng định code không vô tình map lỗi do **audit advice** ném nếu requirement chỉ muốn lỗi từ business target.

Đây là bài tập Spring AOP advice-chain, không cần AspectJ weaving.

## 14. Checklist QA trước khi đưa @Around lên production

- [ ] Đã có requirement cụ thể cho **result transformation** hoặc **exception mapping**; không dùng `@Around` chỉ để log.
- [ ] Target và aspect là Spring-managed beans; caller dùng proxy.
- [ ] Pointcut đủ hẹp cho từng loại result/exception; không bắt nhầm mọi method.
- [ ] `@Around` trả `Object`, khai báo `throws Throwable` khi gọi `proceed()`.
- [ ] Normal return sau transformation tương thích kiểu khai báo, nullability, primitive/generics.
- [ ] Một invocation gọi `proceed()` đúng số lần đã thiết kế; không skip/retry tình cờ.
- [ ] Không có catch rộng làm thay lỗi không liên quan thành lỗi known.
- [ ] Mapping giữ type/message/error code/cause theo contract; không lộ lỗi nội bộ ngoài ý muốn.
- [ ] Known exception bị map; unrelated exception được truyền nguyên; successful result không bị sửa khi không cần.
- [ ] Integration test assert **caller-facing output**, target counter, advice counter và trace.
- [ ] Có test negative cho method không match, raw object và self-invocation nếu chúng là rủi ro thực tế.
- [ ] Đã đánh giá tác động đối với transaction/cache/security advisors và thứ tự trong chain.
- [ ] Logging/metrics trong advice không vô ý ném exception làm phá hợp đồng.
- [ ] Nếu API dùng checked exceptions, đã kiểm tra interface throws declaration và loại proxy.
- [ ] Không dùng `Method.invoke(target)` để thay `ProceedingJoinPoint.proceed()` nếu cần giữ chain Spring AOP.

## 15. Tài liệu chính thức

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `@Around`, `proceed()`, handling return/exception và quyền thay giá trị trả về.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxy, self-invocation và ranh giới lời gọi.
- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): giới hạn method execution và thiết kế pointcut expression.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): đăng ký Spring aspect bean và auto-proxy.
- [Spring Framework 6.2 — Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html#advice-ordering): precedence khi nhiều advices cùng match.
- [JUnit 5.11.0 — User Guide](https://junit.org/junit5/docs/5.11.0/user-guide/): JUnit Jupiter `@Test`, `assertThrows`, `assertInstanceOf` và test lifecycle.
