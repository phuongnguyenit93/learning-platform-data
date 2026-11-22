# Giá trị order nhỏ hơn và vị trí trong chuỗi advice của Spring AOP

## 1. Kết luận cần nhớ

Khi **nhiều Spring Aspect** cùng có advice khớp một method execution của Spring bean, việc xác định thứ tự thực thi rất quan trọng. Spring AOP hỗ trợ `@Order` của Spring và interface `Ordered` để khai báo mức ưu tiên giữa **các aspect khác nhau**.

**Giá trị `order` càng nhỏ → độ ưu tiên (precedence) càng cao.** Với hai aspect:

~~~java
@Aspect
@Order(10)
public class AuditAspect { /* ... */ }

@Aspect
@Order(20)
public class MetricsAspect { /* ... */ }
~~~

`AuditAspect` có precedence **cao hơn** `MetricsAspect` vì `10 < 20`. Điều đó không có nghĩa **mọi dòng code** trong `AuditAspect` chạy trước mọi dòng code của `MetricsAspect`: Spring AOP advice được lồng vào **interceptor chain**:

- Khi **đi vào** join point, advice có precedence cao hơn chạy **trước** advice có precedence thấp hơn.
- Khi **đi ra** join point (sau return hoặc khi exception truyền ngược), advice có precedence cao hơn chạy **sau** phần xử lý đi ra của advice precedence thấp hơn.

Với hai `@Around` advice, hình dung:

~~~text
Caller
  |
  v
Order 10: trước proceed()
    |
    v
  Order 20: trước proceed()
      |
      v
   Target method
      |
      v
  Order 20: sau proceed()
    |
    v
Order 10: sau proceed()
  |
  v
Caller
~~~

**Quy tắc ngắn gọn:** số nhỏ đứng **ngoài** chuỗi (outer), số lớn hơn đứng **trong** chuỗi (inner). **Vào trước – ra sau.**

Trong Spring AOP, chuỗi này áp dụng khi caller thực sự gọi **Spring-managed bean qua AOP proxy** và các advisor cùng match method. `@Order` không làm mọi bean tự xuất hiện proxy, không thay đổi pointcut và không sửa vấn đề self-invocation.

## 2. Phân biệt “order”, “precedence” và “thứ tự hoàn thành”

Ba khái niệm cần được gọi đúng tên:

| Thuật ngữ | Ý nghĩa trong Spring Aspect | Ví dụ `10` so với `20` |
| --- | --- | --- |
| `order value` | Con số do `@Order` hoặc `Ordered.getOrder()` trả về | `10` nhỏ hơn `20` |
| `precedence` | Ưu tiên của advice/aspect khi tạo chuỗi xử lý | `10` có precedence cao hơn `20` |
| `on the way in` | Giai đoạn trước khi chuỗi đi đến target method | `10` chạy trước `20` |
| `on the way out` | Giai đoạn kết quả/exception đi ngược ra caller | `20` chạy phần “ra” trước `10` |
| `completion time` | Thời điểm code advice hoàn tất | Aspect ngoài (`10`) thường hoàn tất cuối cùng nếu thực hiện logic bao quanh |

Nếu chỉ quan sát hai `@Before` advices, dễ nói thiếu chính xác rằng “order nhỏ chạy trước”. Câu đó đúng **trong trường hợp before/on-the-way-in**, nhưng không diễn tả quy tắc tổng thể khi có `@After`, `@AfterReturning`, `@AfterThrowing` hoặc `@Around`.

Đặc biệt, với hai `@Around` và `try/finally`, chương trình quan sát được nesting chính xác, không phải thứ tự ngẫu nhiên phụ thuộc thread scheduling. Ví dụ đầy đủ ở phần 5 sẽ dùng `@Order(10)`, `@Order(20)` và `@Order(30)` trên ba aspect khác nhau.

### Ví dụ không có thứ tự rõ

~~~java
@Aspect
public class AuditAspect { /* advice cùng match */ }

@Aspect
public class MetricsAspect { /* advice cùng match */ }
~~~

Khi **hai aspect khác nhau** cùng khớp một join point mà không khai báo precedence, Spring **không bảo đảm một thứ tự xác định** giữa chúng. Kết quả hiện tại có vẻ ổn trên máy dev vẫn có thể thay đổi sau khi sửa cách đăng ký bean, build hoặc nâng framework. Nếu thứ tự có ý nghĩa nghiệp vụ, phải cấu hình `@Order`/`Ordered` và viết test.

## 3. Thiết lập order trong Spring Aspect

### 3.1. `@Order` ở cấp aspect class

Dạng dễ đọc nhất:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.ProceedingJoinPoint;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAspect {
    @Around("execution(* demo.WorkService.execute(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        return pjp.proceed();
    }
}
~~~

Đây là **class Java minh họa hợp lệ** nếu project có Spring AOP/AspectJ dependency và `WorkService` tương ứng. Bản chạy với logging đầy đủ sẽ ở phần 5.

`@Order` đánh dấu **thứ tự aspect**, không phải một cách lọc bean. Class này vẫn cần được **đăng ký thành Spring bean** qua `@Bean` hoặc `@Component` + component scanning; chỉ đặt `@Aspect`/`@Order` không tự đăng ký object vào `ApplicationContext`.

### 3.2. Interface `Ordered`

Một aspect có thể tự khai báo:

~~~java
@Aspect
public class ConfigurableAuditAspect
        implements org.springframework.core.Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Before("execution(* demo.WorkService.execute(..))")
    public void before() {
        // ...
    }
}
~~~

Đây là class minh họa; cần import `org.aspectj.lang.annotation.Before` và đăng ký bean trong Spring context. `Ordered.getOrder()` hữu ích khi mức ưu tiên cần được biểu diễn bằng API của Spring thay vì một annotation hằng số.

**Không cần dùng cả `@Order` và `Ordered` cho cùng một aspect** trong ví dụ học tập. Nếu kết hợp, phải xem quy tắc giải quyết precedence của Spring và cấu hình bean thực tế để tránh hiểu nhầm. Hãy chọn một cơ chế, nhất quán giữa các aspect.

### 3.3. Giá trị âm, 0 và các hằng

Spring dùng `int` để mô tả order. Ví dụ:

| Giá trị | So với 0 | Độ ưu tiên tương đối |
| --- | --- | --- |
| `-100` | Nhỏ hơn | Cao hơn `0`, `10`, `100` |
| `0` | Trung gian | Cao hơn `10`, thấp hơn `-100` |
| `10` | Lớn hơn `0` | Thấp hơn `0`, cao hơn `20` |
| `20` | Lớn hơn `10` | Thấp hơn `10` |
| `Ordered.HIGHEST_PRECEDENCE` | `Integer.MIN_VALUE` | Giá trị precedence cao nhất theo convention |
| `Ordered.LOWEST_PRECEDENCE` | `Integer.MAX_VALUE` | Giá trị precedence thấp nhất theo convention |

`@Order(0)` **không phải** “không có thứ tự”; nó là một mức ưu tiên cụ thể. Cũng không có quy tắc “order âm chỉ dành cho framework”. Chọn giá trị thể hiện tương quan mà ứng dụng cần, tránh sử dụng số tuyệt đối mang ý nghĩa thần kỳ.

**Nhớ:** precedence cao là **order nhỏ**; đừng đọc “order 100 lớn hơn order 10 nên chạy trước”.

### 3.4. `@Order` không sắp xếp thứ tự tạo bean

Trong Spring Framework, `@Order` được dùng nhiều nơi, nhưng trong bài này ta xét **thứ tự các Spring AOP aspects**. Không được nhầm với:

- Thứ tự gọi constructor hoặc `@Bean` factory method;
- Thứ tự dependency injection, vốn phụ thuộc dependency graph và container lifecycle;
- Thứ tự đăng ký `BeanPostProcessor`;
- Thứ tự methods trong source file của một class `@Aspect`;
- Thứ tự thực thi giữa hai lời gọi service độc lập hoặc giữa các thread.

Muốn xác định bean nào phải khởi tạo trước bean nào, đó là vấn đề dependencies/lifecycle (ví dụ constructor injection, `@DependsOn` khi phù hợp), **không phải cách sử dụng `@Order` của aspect**.

## 4. Vị trí thực tế trong chuỗi Spring AOP

Spring AOP kết hợp các `Advisor` khớp với method execution thành một interceptor chain. Một lời gọi bình thường qua Spring proxy đi từ caller vào các advice, đến target, rồi truyền return value hoặc exception ra ngoài.

Với ba `@Around` aspects:

~~~text
                         PRECEDENCE HIGH
Caller                   Order 10 (outermost)
  |                         |
  |                         v
  |                      Order 20
  |                         |
  |                         v
  |                      Order 30
  |                         |
  |                         v
  |                    WorkService.execute()
  |                         |
  |                    Order 30: finally
  |                         |
  |                    Order 20: finally
  |                         |
  |                    Order 10: finally
  v
Caller observes result/error
                         PRECEDENCE LOW at core
~~~

Trong đó:

- `@Order(10)` bọc **cả** `@Order(20)`, `@Order(30)` và target.
- `@Order(20)` nằm giữa.
- `@Order(30)` nằm gần target nhất, tức **inner**.
- Khi method trả thành công, kết quả truyền theo chiều `30 → 20 → 10 → caller`.
- Khi method ném exception, nếu các aspects dùng `try/finally`, khối `finally` cũng chạy theo chiều `30 → 20 → 10` trước khi exception đến caller.
- Một aspect `@Around` có quyền **không gọi `proceed()`**. Nếu outer aspect short-circuit, target và các advice inner **không chạy**; `@Order` không thể buộc inner được gọi.

Đây là **chuỗi advice của cùng một invocation**, không phải một hàng đợi phân công công việc theo thời gian hoặc thứ tự hoàn thành toàn ứng dụng.

## 5. Project Java 17+ kiểm chứng order nhỏ đi vào trước/đi ra sau

Một project Maven Spring Framework thuần kiểm tra hai nhánh:

1. Method trả kết quả bình thường: cả ba around advices và target chạy.
2. Method ném exception: cả ba `finally` thoát theo thứ tự ngược, exception vẫn đến caller.

Chúng ta ghi lại sự kiện vào một **trace bean** rồi assert **toàn bộ chuỗi** trước khi in kết quả. Không cần Spring Boot, database hoặc công cụ mock.

Phiên bản minh họa: Java 17+, Maven 3.9+, Spring Framework **6.2.0**, AspectJ Weaver **1.9.22**. Đây là phiên bản khóa cho tính tái lập bài học, không khẳng định mới nhất.

~~~text
spring-aop-order-chain/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── App.java
    │   ├── EventTrace.java
    │   ├── WorkService.java
    │   ├── OuterAspect.java
    │   ├── MiddleAspect.java
    │   └── InnerAspect.java
    └── test/java/demo/
        └── AdviceOrderTest.java
~~~

### 5.1. Maven dependencies và plugins

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-order-chain</artifactId>
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

`spring-context` có Java config/`ApplicationContext`; `spring-aop` có proxy và `AopUtils`; `aspectjweaver` cung cấp những type/API cần cho Spring diễn giải `@AspectJ` pointcut. Chỉ có dependency `aspectjweaver` không bật AspectJ bytecode weaving. `junit-jupiter` và `maven-surefire-plugin` hỗ trợ bộ test thật ở mục 5.8.

### 5.2. Trace bean dùng chung

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

    public void clear() {
        events.clear();
    }
}
~~~

Project tạo **một `EventTrace` singleton trong mỗi ApplicationContext**. Service và ba aspects cùng inject trace này. Ví dụ chỉ chạy tuần tự, nên `ArrayList` đủ; production có concurrent requests cần logger hoặc collector thread-safe. `snapshot()` trả bản sao để phép so sánh thứ tự không bị ảnh hưởng bởi lần add sau đó.

### 5.3. Target method có hai đường kết thúc

Tạo `src/main/java/demo/WorkService.java`:

~~~java
package demo;

public class WorkService {
    private final EventTrace trace;

    public WorkService(EventTrace trace) {
        this.trace = trace;
    }

    public String execute(boolean fail) {
        trace.add("TARGET:enter");

        if (fail) {
            trace.add("TARGET:throw");
            throw new IllegalStateException("boom");
        }

        trace.add("TARGET:return");
        return "ok";
    }
}
~~~

`execute(false)` thêm `TARGET:enter` rồi `TARGET:return` và trả `"ok"`. `execute(true)` thêm `TARGET:enter` rồi `TARGET:throw` và ném `IllegalStateException("boom")`. Không có self-invocation hoặc thread khác trong ví dụ, giúp quan sát đúng thứ tự advice trên một lời gọi.

### 5.4. Aspect order 10 — ngoài cùng

Tạo `src/main/java/demo/OuterAspect.java`:

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAspect {
    private final EventTrace trace;

    public OuterAspect(EventTrace trace) {
        this.trace = trace;
    }

    @Around("execution(* demo.WorkService.execute(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        trace.add("10:in");
        try {
            return point.proceed();
        } finally {
            trace.add("10:out");
        }
    }
}
~~~

`10:in` chạy khi vào đầu outer aspect. `point.proceed()` chuyển invocation vào phần còn lại của chain, nơi có `@Order(20)` và `@Order(30)`. `finally` đảm bảo `10:out` chạy **sau khi inner chain hoàn tất** hoặc truyền exception ngược lên, ngay cả khi target ném `boom`.

### 5.5. Aspect order 20 — lớp giữa

Tạo `src/main/java/demo/MiddleAspect.java`:

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(20)
public class MiddleAspect {
    private final EventTrace trace;

    public MiddleAspect(EventTrace trace) {
        this.trace = trace;
    }

    @Around("execution(* demo.WorkService.execute(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        trace.add("20:in");
        try {
            return point.proceed();
        } finally {
            trace.add("20:out");
        }
    }
}
~~~

`@Order(20)` lớn hơn `10` nên có precedence thấp hơn `OuterAspect`. Code trong aspect này được vào **sau** `10:in`, nhưng `20:out` xuất hiện **trước** `10:out`.

### 5.6. Aspect order 30 — gần target nhất

Tạo `src/main/java/demo/InnerAspect.java`:

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(30)
public class InnerAspect {
    private final EventTrace trace;

    public InnerAspect(EventTrace trace) {
        this.trace = trace;
    }

    @Around("execution(* demo.WorkService.execute(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        trace.add("30:in");
        try {
            return point.proceed();
        } finally {
            trace.add("30:out");
        }
    }
}
~~~

Trong ba aspect này, `30` là order lớn nhất và thấp precedence nhất, nằm **trong cùng**. Nó đến ngay trước target trong chuỗi minh họa, và `30:out` là dòng “ra” đầu tiên khi kết thúc target.

### 5.7. Bật Spring AOP và xác nhận hai đường đi

Tạo `src/main/java/demo/App.java`:

~~~java
package demo;

import java.util.List;
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
    public WorkService workService(EventTrace trace) {
        return new WorkService(trace);
    }

    @Bean
    public OuterAspect outerAspect(EventTrace trace) {
        return new OuterAspect(trace);
    }

    @Bean
    public MiddleAspect middleAspect(EventTrace trace) {
        return new MiddleAspect(trace);
    }

    @Bean
    public InnerAspect innerAspect(EventTrace trace) {
        return new InnerAspect(trace);
    }

    public static List<String> expectedSuccess() {
        return List.of(
                "10:in", "20:in", "30:in",
                "TARGET:enter", "TARGET:return",
                "30:out", "20:out", "10:out");
    }

    public static List<String> expectedFailure() {
        return List.of(
                "10:in", "20:in", "30:in",
                "TARGET:enter", "TARGET:throw",
                "30:out", "20:out", "10:out");
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            WorkService service = context.getBean(WorkService.class);
            EventTrace trace = context.getBean(EventTrace.class);

            boolean proxied = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxied);
            if (!proxied) {
                throw new IllegalStateException("Missing Spring AOP proxy");
            }

            String result = service.execute(false);
            List<String> success = trace.snapshot();
            if (!"ok".equals(result) || !expectedSuccess().equals(success)) {
                throw new IllegalStateException("Success chain order wrong");
            }
            System.out.println("SUCCESS: " + String.join(" > ", success));

            trace.clear();

            try {
                service.execute(true);
                throw new IllegalStateException("Expected failure");
            } catch (IllegalStateException error) {
                if (!"boom".equals(error.getMessage())) {
                    throw error;
                }
            }

            List<String> failure = trace.snapshot();
            if (!expectedFailure().equals(failure)) {
                throw new IllegalStateException("Failure chain order wrong");
            }
            System.out.println("FAILURE: " + String.join(" > ", failure));

            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Vì sao ví dụ chứng minh đúng câu hỏi?

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` bật Spring AOP auto-proxying; ba `@Aspect` đều được đăng ký thành Spring bean, không chỉ được gắn annotation.
2. Cả ba advice dùng **chung một pointcut** `execution(* demo.WorkService.execute(..))`, nên cạnh tranh đúng một method join point.
3. Mỗi aspect có **order khác nhau**, không có hòa điểm gây mơ hồ. `10` phải được vào trước `20`, rồi `30`.
4. `try/finally` ở mỗi `@Around` mô tả **chiều đi ra** rõ ràng và còn hoạt động trên nhánh exception.
5. `expectedSuccess()` và `expectedFailure()` xác định toàn bộ chuỗi trước; chương trình chủ động ném lỗi khi trace sai, không chỉ in một câu `PASS` vô điều kiện.
6. `trace.clear()` loại bỏ sự kiện success trước khi thử failure, tránh ghi đè kết luận do dữ liệu cũ.
7. Exception `"boom"` được bắt **ở caller**, sau khi ba khối `finally` đã chạy; advice chỉ ghi dấu, không nuốt hay biến đổi exception.
8. Đây là **Spring proxy-based AOP**: không có AspectJ compiler/agent hay load-time weaving.

### Lệnh chạy

~~~bash
mvn -q compile exec:java
~~~

Các dòng do ứng dụng `System.out.println` in ra khi chạy thành công:

~~~text
PROXY: true
SUCCESS: 10:in > 20:in > 30:in > TARGET:enter > TARGET:return > 30:out > 20:out > 10:out
FAILURE: 10:in > 20:in > 30:in > TARGET:enter > TARGET:throw > 30:out > 20:out > 10:out
CHECK: PASS
~~~

Maven và logger có thể in thêm dòng bên ngoài các dòng ứng dụng này.

**Hai điều nổi bật nhất**: order nhỏ xuất hiện trước ở đoạn `in`, nhưng xuất hiện sau ở đoạn `out`. Nếu chỉ assert `10:in` trước `20:in` mà bỏ các dấu `out`, test mới xác nhận **một nửa** semantics ordering.

### 5.8. Chạy integration tests bằng JUnit Jupiter

File `src/test/java/demo/AdviceOrderTest.java`:

~~~java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AdviceOrderTest {
    @Test
    void smallerOrderEntersFirstAndExitsLast() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            WorkService service = context.getBean(WorkService.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals("ok", service.execute(false));
            assertEquals(App.expectedSuccess(), trace.snapshot());
        }
    }

    @Test
    void allFinallyBlocksExitInReverseOrderOnException() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            WorkService service = context.getBean(WorkService.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertTrue(AopUtils.isAopProxy(service));

            IllegalStateException error = assertThrows(
                    IllegalStateException.class,
                    () -> service.execute(true));

            assertEquals("boom", error.getMessage());
            assertEquals(App.expectedFailure(), trace.snapshot());
        }
    }
}
~~~

Chạy:

~~~bash
mvn clean test
~~~

Nếu cả hai test pass, trong báo cáo Surefire sẽ có chỉ số tương tự:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
~~~

Không coi đây là log từ máy của người đọc: đây là **kết quả mong đợi** khi đã cài Maven/JDK đúng và mã chạy như khai báo. Chương trình có thể hiển thị thêm log build/framework, nhưng assertion phải đúng trên cả success và exception.

## 6. Với @Before và @After, thứ tự thể hiện thế nào?

Đối với hai **aspects khác nhau** có order khác nhau:

| Loại advice | Order 10 vs order 20 | Cách hiểu |
| --- | --- | --- |
| Hai `@Before` cùng match | `@Before` của `10` chạy trước `20` | “On the way in” |
| Hai `@AfterReturning` cùng match và target return bình thường | `@AfterReturning` của `20` chạy trước `10` | “On the way out” |
| Hai `@AfterThrowing` cùng match và target ném lỗi phù hợp | `@AfterThrowing` của `20` chạy trước `10` | Exception truyền ngược ra outer |
| Hai `@After` cùng match | `@After` của `20` chạy trước `10` | After-finally ở chiều đi ra |
| Hai `@Around` cùng match | `10:in → 20:in → target → 20:out → 10:out` | Outer/inner nesting |

Bảng này là mô hình giải thích **khi các advice đều áp dụng và thật sự chạy**. Với target ném exception, `@AfterReturning` không chạy; với target return bình thường, `@AfterThrowing` không chạy. `@After` có thể chạy trên cả hai đường. Với `@Around`, nếu một advice chủ động short-circuit hoặc thay exception/return value, kết quả của phần inner chain có thể thay đổi; không suy một chuỗi cố định khi advice không gọi `proceed()`.

### Advice ordering khác với “chạy trước/sau cùng một phương thức Java”

Ví dụ:

~~~java
@Aspect
@Order(10)
class A {
    @Before("execution(* demo.WorkService.execute(..))")
    public void before() { /* ... */ }
}

@Aspect
@Order(20)
class B {
    @AfterReturning("execution(* demo.WorkService.execute(..))")
    public void after() { /* ... */ }
}
~~~

Hai class này là **snippet minh họa**, chưa bao gồm package/import/@Bean và không nên thêm đồng thời vào project chính. Ở đây `A.before` chạy trước method và `B.after` chạy sau method, nhưng **không thể** dùng ví dụ đó để kết luận order nhỏ luôn chạy trước mọi advice: hai loại advice có thời điểm kích hoạt vốn khác nhau. Muốn quan sát đúng precedence giữa các aspects, so sánh hai advice cùng loại hoặc trace đầy đủ một nested `@Around` chain.

## 7. Trong cùng một @Aspect class, @Order không sắp xếp từng method advice

Một lỗi rất phổ biến là hiểu `@Order(10)` trên aspect class sẽ khiến method advice nằm trên cùng của source chạy trước method advice nằm dưới.

~~~java
@Aspect
@Order(10)
public class MixedAspect {
    @Before("execution(* demo.WorkService.execute(..))")
    public void first() {
    }

    @Before("execution(* demo.WorkService.execute(..))")
    public void second() {
    }
}
~~~

Đây là **class minh họa** chưa được đăng ký Spring bean. Cả `first()` và `second()` là `@Before` có cùng type và cùng khớp một join point **trong cùng aspect**. Spring **không bảo đảm thứ tự giữa hai advice cùng loại** chỉ dựa trên vị trí khai báo trong source file: reflection Java không bảo toàn thứ tự method khai báo theo nghĩa cần thiết để suy precedence.

Theo tài liệu Spring Framework 6.2, với các advice **khác loại trong cùng `@Aspect`**, precedence được thiết lập theo advice type, từ cao đến thấp:

~~~text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
~~~

Nhưng `@After` có semantics **after-finally**, nên dù precedence type được liệt kê trước `@AfterReturning`/`@AfterThrowing`, khi join point đi ra nó **thực tế được gọi sau** các advice xử lý return/throw tương ứng. Đừng chỉ nhớ danh sách type precedence rồi suy máy móc thứ tự log.

Nếu cần thứ tự tường minh giữa hai lời xử lý `@Before`, lựa chọn thường dễ kiểm soát hơn là:

1. Gộp cả hai bước vào **một advice method** theo trình tự Java rõ ràng; hoặc
2. Đưa chúng vào **hai aspect classes** khác nhau, mỗi class một `@Order` rõ ràng và có integration test.

Không nên đặt `@Order` ở hai advice methods riêng rồi mặc định Spring AOP coi chúng như hai aspects khác nhau: ordering giữa aspects được định nghĩa theo annotation/`Ordered` của **aspect bean**, không phải các line number trong source.

## 8. Khi order bằng nhau hoặc không khai báo order

### 8.1. Hai aspect có cùng order

~~~java
@Aspect
@Order(10)
class FirstAspect { /* ... */ }

@Aspect
@Order(10)
class SecondAspect { /* ... */ }
~~~

Hai aspect này cùng precedence value. **Không dùng tên class, tên bean hoặc thứ tự method trong source để suy thứ tự luôn xác định**. Nếu logic cần `FirstAspect` bao `SecondAspect`, đặt giá trị order **khác nhau** và xác minh bằng test. Còn nếu thứ tự không có ý nghĩa, code phải độc lập với việc ai chạy trước.

### 8.2. Một aspect không khai báo order

Aspect không khai báo `@Order` hoặc `Ordered` không tạo ra cam kết precedence tương đối mà bạn có thể dựa vào với các aspect khác. Spring có convention default ordering, nhưng hệ thống còn có thể có advisors từ transaction, cache, security hoặc cơ chế tạo proxy khác.

Nếu order giữa custom aspects và infrastructure advisors có ý nghĩa, xác định **cấu hình order hiệu lực của từng advisor** (ví dụ một vài `@Enable...` infrastructure có thuộc tính `order` riêng) và test trên context thực, không dựa vào một “mặc định chắc chắn” chưa kiểm tra.

### 8.3. Đừng dùng mức order trùng nhau làm phụ thuộc ngầm

Một số thay đổi tưởng nhỏ như thêm aspect audit, đăng ký hạ tầng transaction hoặc sửa classpath có thể thay đổi thứ tự khi nhiều advisors có cùng precedence. Cách thiết kế an toàn hơn:

- Các advice có side effects nhạy cảm nên ít phụ thuộc thứ tự khi có thể.
- Nếu phải phụ thuộc thứ tự, đặt cấu hình tường minh, giải thích bằng test.
- Không dựa vào việc IDE liệt kê bean theo một thứ tự nào đó để suy thứ tự interceptor chain.

## 9. Tác động khi nhiều advisor cùng áp dụng: transaction, security, logging

Trong một ứng dụng Spring, không chỉ custom `@Aspect` mới tạo advice. Các cơ chế như `@Transactional`, cache và security có thể tham gia chuỗi proxy/advisor, tùy cấu hình.

Ví dụ lý thuyết (không phải project transaction chạy độc lập):

~~~text
Logging @Around        (outer)
    |
    v
Transaction interceptor (inner)
    |
    v
Business method
~~~

Nếu logging bao ngoài transaction interceptor:

- Phần `before` của logging xảy ra **trước khi** phần mở transaction ở trong được tiến hành.
- Phần `after/finally` của logging có thể xảy ra **sau khi** phần transaction interceptor trong cùng chain đã hoàn tất.
- Nếu đảo thứ tự, logger nằm **bên trong** transaction boundary và các dấu thời gian/phạm vi lỗi nó thấy có thể khác.

Không suy ra từ ví dụ này rằng **mọi cấu hình `@Transactional` đều tự động có order 20**. Order hiệu lực phụ thuộc Spring configuration, các advisor và ứng dụng. Spring Framework cho phép cấu hình thứ tự của transaction advisor thông qua hạ tầng transaction (ví dụ thuộc tính `order` ở `@EnableTransactionManagement` cho proxy advice), nhưng phải đọc cấu hình thực của dự án trước khi kết luận.

Khi cần xác minh:

1. Xác định bean target có thật sự là Spring AOP proxy.
2. Xác định các advisors nào match và thứ tự mà framework đã áp dụng.
3. Đặt `@Order` cho custom aspects nếu tương quan với advisor khác cần được ràng buộc.
4. Viết integration test qua Spring bean, không test object tự tạo bằng `new`.
5. Quan sát các mốc có ý nghĩa, ví dụ “transaction active trước/giữa/sau” bằng API phù hợp, thay vì suy qua một dòng log có thể chạy ở chỗ khác.

Thứ tự advisor không thay thế cấu hình transaction propagation/isolation/rollback. Đây là một khía cạnh của **chuỗi Spring AOP**, không phải toàn bộ ngữ nghĩa giao dịch.

## 10. Sai lầm và cách khắc phục

| Hiểu nhầm | Vì sao sai | Cách kiểm tra/sửa |
| --- | --- | --- |
| “`@Order(100)` ưu tiên hơn `@Order(1)` vì số lớn hơn.” | Quy tắc đảo lại: số **nhỏ hơn** precedence **cao hơn** | Dùng 10/20 test vào trước, ra sau |
| “Order nhỏ luôn là advice chạy xong trước.” | Outer advice hoàn tất sau inner nếu nó bao `proceed()` | Ghi cả `in` và `out` |
| “`@Order` thay thứ tự method trong cùng một `@Aspect`.” | `@Order` chủ yếu điều khiển precedence giữa aspects | Gộp advice hoặc tách thành aspects riêng |
| “Hai `@Before` trong cùng aspect chạy theo thứ tự dòng code.” | Reflection không cho phép dựa trên source declaration order | Không dựa vào line order |
| “Tôi đã đặt order nên aspect chắc chắn chạy.” | Vẫn cần aspect bean, Spring AOP proxy và pointcut match | Kiểm tra `AopUtils.isAopProxy` và event counter |
| “Order khác nhau bảo đảm target luôn chạy.” | `@Around` có thể không gọi `proceed()` | Test both target and advice events |
| “Order sửa được self-invocation.” | `this.otherMethod()` không qua Spring proxy | Gọi qua Spring-managed collaborator |
| “`@Order` định nghĩa bean nào được tạo trước.” | Đây không phải cơ chế quản lý dependency/lifecycle | Dùng constructor dependencies/bean lifecycle APIs |
| “Không đặt order vẫn có thứ tự cố định giữa mọi aspects.” | Không có guarantee đó cho precedence của khác aspects | Khai báo order và test |
| “Advice ngoài không liên quan exception.” | `@Around` outer có thể thấy/biến đổi exception của inner chain | Dùng `try/finally` và giữ error policy đúng |
| “Bật CGLIB thay cho JDK proxy sẽ sửa thứ tự.” | Proxy strategy khác ordering; mỗi vấn đề có cấu hình riêng | Kiểm tra `@Order`/`Ordered`, advisor chain |
| “Aspect order và transaction order luôn giống nhau.” | Transaction infrastructure có precedence configuration riêng | Inspect order trên context thật |

## 11. Cách debug khi thứ tự không như dự kiến

1. **Xác minh đúng method execution:** các pointcut có match cùng một Spring bean method không? Nếu một aspect không match, không có chuyện nó được xếp sai trong chain.
2. **Xác minh reference là proxy:** `AopUtils.isAopProxy(service)` trên reference caller dùng. Object tạo bằng `new` ngoài container không auto-proxy.
3. **Xem `@Order` trên class aspect**, không chỉ trên method advice hoặc file config chứa aspect.
4. **Xem cả `Ordered`** nếu aspect implement interface này; bảo đảm giá trị precedence mà Spring thực sự dùng.
5. **Kiểm tra trùng order:** hai aspects có cùng order sẽ không đáp ứng nhu cầu ordering cứng nếu thiếu cơ chế tie-break được công bố.
6. **Log đầy đủ cả đi vào lẫn đi ra:** với `@Around` in marker trước `proceed()` và trong `finally`. Chỉ log `@Before` không chứng minh được mô hình nesting.
7. **Thử nhánh exception:** success có thể đúng nhưng advice bỏ quên `finally`, thay exception hoặc return sớm khiến đường thất bại khác.
8. **Kiểm tra `proceed()`:** một outer aspect return sớm sẽ bỏ qua inner advisors. Order value không bắt buộc gọi target.
9. **Kiểm tra nhiều infrastructure advisors:** transaction/cache/security và custom aspects có thể nằm chung chain. Đừng chỉ so hai class do nhóm tự viết.
10. **Kiểm tra cùng aspect:** advice của cùng type trong một aspect không có order xác định dựa vào source line; tách class hoặc gom logic.
11. **Đừng suy từ bean creation time:** order trong chain không đồng nghĩa order tạo Spring beans.
12. **Đóng băng semantics bằng test:** assert toàn trace theo thứ tự trước/sau và exception propagation như project phần 5.

Đo proxy tại call site:

~~~java
Object bean = context.getBean("workService");

System.out.println(
        org.springframework.aop.support.AopUtils.isAopProxy(bean));
~~~

Đây chỉ là snippet để chèn vào method đã có `ApplicationContext context`. Nếu trả `false`, thứ tự aspects không phải nguyên nhân đầu tiên cần điều tra.

## 12. Bài tập tự kiểm tra

**Bài 1.** Hai Spring aspects cùng match method `execute()`: một có `@Order(-5)`, một có `@Order(100)`. Aspect nào đi vào trước?  
→ `-5` có precedence cao hơn, vào trước; nếu cả hai bao `proceed()`, nó đi ra sau.

**Bài 2.** Có ba around aspects 1/2/3. Nếu tất cả gọi `proceed()` một lần rồi mới thoát, thứ tự?  
→ `1:in → 2:in → 3:in → target → 3:out → 2:out → 1:out`.

**Bài 3.** `@Order(10)` @Around outer bỏ qua `proceed()`. Có chắc `@Order(20)` inner chạy không?  
→ Không. Inner chain/target chỉ được tiến vào khi outer chuyển tiếp bằng `proceed()` (hoặc thực hiện cơ chế khác ngoài ví dụ).

**Bài 4.** Tại sao hai `@AfterReturning` aspects order 10/20 thường được quan sát theo chiều 20 rồi 10?  
→ Đây là chiều kết quả đi **ra** khỏi target, aspect có precedence cao hơn ở outer nên chạy sau.

**Bài 5.** Hai `@Before` methods cùng nằm trong một `@Aspect @Order(10)`. Method khai báo trước trong source có luôn chạy trước không?  
→ Không có guarantee theo source declaration order. Gộp hoặc tách thành aspects có order riêng nếu thứ tự bắt buộc.

**Bài 6.** Nếu aspect order 10 và transaction advisor order 20 cùng bọc service method, logging ngoài transaction hay trong?  
→ Nếu cả hai advisor được sắp xếp theo precedence đó và đều match, logging `@Around` order 10 ở outer, transaction order 20 ở inner. Cần **xác minh cấu hình runtime** chứ không giả định transaction advisor luôn order 20.

**Bài 7.** Nếu chỉ đặt `@Order(10)` trên aspect nhưng không đăng ký aspect làm bean, advice chạy không?  
→ Không. `@Aspect`/`@Order` không tự đăng ký vào Spring IoC; phải có aspect bean và AOP enablement.

**Bài 8.** Vì sao cần test cả normal return lẫn thrown exception?  
→ Để chứng minh chain đi ra theo thứ tự ngược và outer advice có thể thực thi `finally` trên cả hai outcome.

## 13. Checklist nhanh

- [ ] Đã nêu rõ **giá trị nhỏ hơn = precedence cao hơn**.
- [ ] Đã phân biệt **on the way in** với **on the way out**.
- [ ] Các aspect liên quan đã đăng ký thành Spring beans và target là proxy.
- [ ] Order áp dụng cho **các aspects**, không suy từ vị trí method trong source.
- [ ] Không có tie order nếu ứng dụng đòi hỏi một thứ tự cứng.
- [ ] `@Around` gọi `proceed()` theo đúng business contract.
- [ ] Test trace cả `in`, target, `out` trên đường success.
- [ ] Test exception và `finally` trên đường failure.
- [ ] Nếu có transaction/cache/security advisors, đã xét thứ tự cấu hình thực tế.
- [ ] Không nhầm order với bean initialization hay self-invocation.
- [ ] Nội dung advice không làm rò rỉ dữ liệu hoặc vô tình thay exception khi chỉ cần logging.

## 14. Tài liệu chính thức

- [Spring Framework 6.2 — Declaring Advice / Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): quy tắc precedence, order nhỏ hơn, chiều vào/ra và thứ tự advice cùng aspect.
- [Spring Framework 6.2 — Schema-based AOP / Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html): ordering với `@Order`/`Ordered`, phạm vi XML và advisors.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring AOP sử dụng proxy với `@AspectJ` syntax.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): self-invocation, JDK/CGLIB proxy và các giới hạn.
- [Spring `Ordered` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/Ordered.html): `getOrder()`, `HIGHEST_PRECEDENCE`, `LOWEST_PRECEDENCE`.
- [Spring `@Order` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/annotation/Order.html): cách đánh dấu precedence bằng annotation.
