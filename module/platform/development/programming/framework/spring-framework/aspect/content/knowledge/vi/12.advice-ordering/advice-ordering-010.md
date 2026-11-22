# Bảng vết thực thi để xác nhận thứ tự khi thành công và khi lỗi trong Spring AOP

## 1. Mục tiêu của bảng vết

Khi có nhiều Spring `@Aspect` cùng can thiệp vào một method của Spring bean, chỉ nhìn tên `@Before`, `@After`, `@AfterReturning` hoặc `@AfterThrowing` chưa đủ để biết **dòng nào xuất hiện trước**. Một phương thức có thể đi qua nhiều lớp interceptor; thứ tự ở **chiều vào** khác thứ tự ở **chiều thoát**, và khi method ném exception thì một số callback thành công hoàn toàn không chạy.

**Bảng vết thực thi** (*execution trace table*) là cách ghi lại từng mốc theo thứ tự quan sát được, ví dụ:

~~~text
Caller
  -> Spring AOP proxy
       -> OuterAspect @Around: enter
            -> InnerAspect @Around: enter
                 -> OutcomeAspect @AfterReturning / @AfterThrowing
                 -> method đích
            <- InnerAspect @Around: finally
       <- OuterAspect @Around: finally
  <- Caller nhận giá trị hoặc ngoại lệ
~~~

Lưu ý hình trên là **sơ đồ tầng**, không phải thứ tự log: callback `@AfterReturning` hoặc `@AfterThrowing` chạy **sau khi method đích kết thúc**, trước khi chuỗi trả quyền điều khiển về các around advice ở bên ngoài.

Bài học này tập trung **riêng Spring Aspect/Spring AOP proxy-based**, trong nhóm **Thứ tự thực thi**. Người học sẽ:

1. Xây dựng trace với cột **bước, tầng, sự kiện, nguyên nhân, nhánh kết quả**.
2. Hiểu `@Order`/`Ordered`: **số nhỏ hơn = precedence cao hơn**, vào trước và thoát sau.
3. Lập bảng riêng cho **normal return** và **exceptional exit**.
4. Phân biệt `@AfterReturning`, `@AfterThrowing`, `@After` và `finally` trong `@Around`.
5. Viết ví dụ **Maven + Java 17+** có ba Spring aspect được sắp xếp tường minh, collector sự kiện và assertions tự kiểm tra.
6. Debug các trường hợp log thiếu, log lặp, advice kết thúc sớm, tự gọi `this.method()` hoặc exception bị xử lý bên trong method.

**Mục tiêu không phải** học lý thuyết Aspect tổng quát mà là xác minh **trình tự thực tế trên Spring AOP proxy của một Spring-managed bean**.

## 2. Luật đọc bảng vết của Spring

Trước khi ghi bảng, phải xác định **ai là caller và caller giữ object nào**. Nếu caller gọi một plain Java object do `new` tạo ngoài Spring, hoặc một lời gọi nội bộ `this.method()` của target bypass proxy, advice có thể hoàn toàn không xuất hiện.

Giả sử ba aspect có thứ tự:

| Aspect | Cách khai báo | Thứ tự/precedence | Vai trò |
| --- | --- | --- | --- |
| `OuterTraceAspect` | `@Aspect @Order(10)` | **Cao nhất** trong ba aspect | `@Around`, log enter, after, finally |
| `InnerTraceAspect` | `@Aspect @Order(20)` | Ở giữa | `@Around`, log enter, after, finally |
| `OutcomeAspect` | `@Aspect @Order(30)` | Thấp nhất | `@AfterReturning` khi thành công; `@AfterThrowing` khi lỗi |

Khi **cả ba pointcut đều match cùng invocation**:

- 10 được vào trước 20; 20 được vào trước 30.
- Outer(10) bao ngoài Inner(20), còn Outcome(30) nằm sâu hơn.
- Khi result hoặc exception đi ngược ra, Outcome(30) xử lý nhánh phù hợp trước.
- Sau đó Inner(20) chạy phần code ở phía sau `proceed()` nếu thành công, rồi `finally`.
- Cuối cùng Outer(10) chạy phần code sau `proceed()` nếu thành công, rồi `finally`.
- Caller chỉ nhận result/exception sau khi các interceptor đã đi qua hoàn tất.

**Điểm dễ sai:** “10 ưu tiên cao hơn 20” không nghĩa rằng **mọi câu lệnh của aspect 10** xuất hiện trước **mọi câu lệnh của aspect 20**. Về cấu trúc, aspect 10 là **wrapper ngoài**, nên phần sau của nó diễn ra **sau** aspect 20.

## 3. Từ interceptor chain đến bảng có thể kiểm chứng

Mô hình một Spring proxy:

~~~text
                       ====== CHIỀU VÀO ======>
Caller -> [A: order 10] -> [B: order 20] -> [C: order 30] -> Target
Caller <- [A: finally] <- [B: finally] <- [C: outcome] <- Target result/throw
                       <====== CHIỀU RA =======
~~~

Trong ví dụ, C không dùng `@Around`; nó có hai lời advice **chọn một nhánh**:

- `@AfterReturning` khi target execution trả về bình thường.
- `@AfterThrowing` khi target execution ném exception thoát ra.

Vì C là interceptor trong hơn B và A, cả callback C thành công lẫn callback C thất bại đều xuất hiện **trước** phần thoát của B và A.

### 3.1. Bảng vết thành công lý tưởng

| Bước | Vị trí | Sự kiện | Vì sao |
| ---: | --- | --- | --- |
| 1 | A(10) | `A: enter` | Spring proxy đi vào aspect ưu tiên cao |
| 2 | B(20) | `B: enter` | A gọi `proceed()` để vào tầng B |
| 3 | Target | `target: begin` | B gọi `proceed()`, chuỗi tới method |
| 4 | Target | `target: return OK` | Method hoàn tất bình thường |
| 5 | C(30) | `C: returned OK` | `@AfterReturning` nhận giá trị String |
| 6 | B(20) | `B: after` | `proceed()` của B đã trả bình thường |
| 7 | B(20) | `B: finally` | Java finally của B được thực thi |
| 8 | A(10) | `A: after` | `proceed()` của A đã trả bình thường |
| 9 | A(10) | `A: finally` | Java finally của A được thực thi |
| 10 | Caller | `caller result: OK` | Lời gọi proxy đã trả kết quả |

Hai dòng “after” trong bảng là **code đặt sau `proceed()` trong `@Around`**, không phải annotation `@After`. Nếu không phân biệt, người đọc dễ tưởng Spring đang sắp xếp advice sai.

### 3.2. Bảng vết khi target ném exception

| Bước | Vị trí | Sự kiện | Vì sao |
| ---: | --- | --- | --- |
| 1 | A(10) | `A: enter` | Aspect ngoài nhận lời gọi |
| 2 | B(20) | `B: enter` | A đã proceed |
| 3 | Target | `target: begin` | B đã proceed |
| 4 | Target | `target: throw boom` | Method ném IllegalStateException |
| 5 | C(30) | `C: throwing IllegalStateException` | `@AfterThrowing` match exception |
| 6 | B(20) | `B: finally` | `proceed()` của B ném lỗi; finally vẫn chạy |
| 7 | A(10) | `A: finally` | `proceed()` của A ném lỗi; finally vẫn chạy |
| 8 | Caller | `caller caught: boom` | Caller bắt exception gốc |

**Không có `B: after`, `A: after` hoặc `C: returned OK`** vì `proceed()` không trả bình thường. Thay vào đó, finally của những around advice **đã được đi vào** vẫn chạy khi stack unwind.

**Đây là khác biệt trung tâm cần có trong trace:** Khi test chỉ xác minh rằng “A enter trước B enter”, bạn chưa kiểm tra được trật tự ở nhánh lỗi. Phải assert riêng **chuỗi hoàn chỉnh** của cả hai nhánh.

## 4. Những điều kiện để trace trên thật sự đúng

Một bảng vết đáng tin cần ghi rõ các tiền đề:

1. `OuterTraceAspect`, `InnerTraceAspect` và `OutcomeAspect` đều là **Spring-managed aspect beans**.
2. Spring Framework có `@EnableAspectJAutoProxy` hoặc hạ tầng AOP tương đương được bật.
3. Target là **Spring bean** có Spring AOP proxy, không phải object tự tạo bằng `new`.
4. Cả ba pointcut đều match đúng method được caller gọi.
5. Các aspects có order **khác nhau**: 10, 20, 30.
6. Cả hai `@Around` gọi `ProceedingJoinPoint.proceed()` **đúng một lần**.
7. Advice không làm biến đổi result/exception, không shortcut và không tự ném lỗi logging.
8. Project minh họa không đăng ký advisor transaction/cache/security khác cho target.
9. Mọi lời gọi trong demo là **đồng bộ** và thực hiện trên cùng thread.
10. Sự kiện được ghi theo đúng thứ tự lời gọi đồng bộ, không dùng asynchronous logging làm thay đổi thứ tự hiển thị.

Nếu thay đổi tiền đề, bảng vết có thể cần thay đổi. Đừng tuyên bố một thứ tự cố định khi các aspect không khai báo `@Order`/`Ordered` hoặc một advisor phía ngoài có thể kết thúc sớm.

## 5. Project Maven/Java 17+ chạy được

Ta xây dựng ứng dụng Spring Framework nhỏ để **quan sát** và **xác nhận bằng code** thứ tự nêu ở hai bảng.

### 5.1. Cấu trúc thư mục

~~~text
spring-aop-trace-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── TraceEvents.java
    ├── TransferService.java
    ├── OuterTraceAspect.java
    ├── InnerTraceAspect.java
    ├── OutcomeAspect.java
    └── Main.java
~~~

Môi trường minh họa: **Java 17+**, Maven, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**. Spring AOP sử dụng AspectJ annotation syntax/pointcut expression nhưng **không dùng compile-time hoặc load-time bytecode weaving** trong ví dụ.

### 5.2. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-trace-demo</artifactId>
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

Spring Framework BOM giữ các module Spring cùng phiên bản. Với ứng dụng Spring Boot, sử dụng dependency management của Boot thay vì buộc một bộ version lấy từ project ví dụ.

### 5.3. Bộ ghi sự kiện `TraceEvents.java`

~~~java
package example;

import java.util.ArrayList;
import java.util.List;

public final class TraceEvents {
    private final List<String> events = new ArrayList<>();

    public void record(String event) {
        events.add(event);
        System.out.println(event);
    }

    public List<String> drain() {
        List<String> result = List.copyOf(events);
        events.clear();
        return result;
    }
}
~~~

Class này lưu lại đúng chuỗi events rồi in ra console. `Main` sẽ lấy snapshot bằng `drain()` và dùng `List.equals(...)` để kiểm tra **thứ tự**, không chỉ kiểm tra sự kiện có tồn tại.

**Phạm vi:** Demo gọi đồng bộ, một thread, một invocation tại một thời điểm; `ArrayList` và `drain()` **không an toàn** để trộn nhiều request concurrent. Với production/integration tests song song nên dùng collector tách theo invocation ID (hoặc thread-local scope được cleanup đúng cách), và chỉ assert trên event sequence thuộc **cùng một invocation**. Một global `Collections.synchronizedList` đơn độc cũng không giải quyết vấn đề events từ nhiều invocation xen kẽ.

### 5.4. Target `TransferService.java`

~~~java
package example;

public class TransferService {

    private final TraceEvents trace;

    public TransferService(TraceEvents trace) {
        this.trace = trace;
    }

    public String transfer(boolean fail) {
        trace.record("target: begin");

        if (fail) {
            trace.record("target: throw boom");
            throw new IllegalStateException("boom");
        }

        trace.record("target: return OK");
        return "OK";
    }
}
~~~

Một target duy nhất có hai nhánh:

- `transfer(false)` trả `String "OK"`;
- `transfer(true)` ném `IllegalStateException("boom")`.

Dữ liệu nghiệp vụ và lời exception được giữ nguyên trong mọi aspect. Không có sleep, random, network call hay concurrency để stdout bị nondeterministic.

### 5.5. Aspect ngoài `OuterTraceAspect.java`

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterTraceAspect {

    private final TraceEvents trace;

    public OuterTraceAspect(TraceEvents trace) {
        this.trace = trace;
    }

    @Around("execution(public * example.TransferService.transfer(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        trace.record("A: enter");

        try {
            Object result = pjp.proceed();
            trace.record("A: after");
            return result;
        } finally {
            trace.record("A: finally");
        }
    }
}
~~~

Giải thích:

1. Order 10 là precedence cao nhất trong ba aspect của demo.
2. `A: enter` được in **trước** việc gọi `proceed()`.
3. `proceed()` tiến sang những advisors phía trong, không nhất thiết gọi target ngay lập tức.
4. `A: after` được in **chỉ khi proceed trả bình thường**.
5. `A: finally` được in ở cả success/failure khi around advice đã được vào.
6. Method dùng `return result` để trả nguyên giá trị, không biến đổi.
7. Method khai báo `throws Throwable` và không nuốt exception của target.

Khi exception thoát từ B/C/target, lệnh `trace.record("A: after")` bị bỏ qua, nhưng Java `finally` vẫn được thực thi.

### 5.6. Aspect giữa `InnerTraceAspect.java`

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(20)
public class InnerTraceAspect {

    private final TraceEvents trace;

    public InnerTraceAspect(TraceEvents trace) {
        this.trace = trace;
    }

    @Around("execution(public * example.TransferService.transfer(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        trace.record("B: enter");

        try {
            Object result = pjp.proceed();
            trace.record("B: after");
            return result;
        } finally {
            trace.record("B: finally");
        }
    }
}
~~~

Aspect B có cấu trúc giống A, chỉ khác order 20. Vì `20 > 10` nên B được A **bao bên ngoài**. Cách viết rõ ràng giúp thấy:

- Trên đường vào: A enter rồi B enter.
- Trên đường ra thành công: B after/finally rồi A after/finally.
- Trên đường ra thất bại: B finally rồi A finally.

**Không** nhầm nhãn code `B: after` với một lời advice `@After`. Đây là một câu lệnh trong `@Around` chạy sau `proceed()`.

### 5.7. Aspect phân biệt outcome `OutcomeAspect.java`

~~~java
package example;

import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(30)
public class OutcomeAspect {

    private final TraceEvents trace;

    public OutcomeAspect(TraceEvents trace) {
        this.trace = trace;
    }

    @AfterReturning(
        pointcut = "execution(public * example.TransferService.transfer(..))",
        returning = "result",
        argNames = "result"
    )
    public void onReturned(String result) {
        trace.record("C: returned " + result);
    }

    @AfterThrowing(
        pointcut = "execution(public * example.TransferService.transfer(..))",
        throwing = "error",
        argNames = "error"
    )
    public void onThrown(IllegalStateException error) {
        trace.record("C: throwing " + error.getClass().getSimpleName());
    }
}
~~~

Vì `OutcomeAspect` có precedence 30, các callbacks C nằm trong A và B trên một invocation bình thường của demo.

- Khi target trả `String "OK"`, `@AfterReturning` với `returning = "result"` bind kết quả vào `String result`, in `C: returned OK`.
- Khi target ném `IllegalStateException`, `@AfterReturning` **không chạy**, còn `@AfterThrowing` với `throwing = "error"` bind exception vào `IllegalStateException error` và in loại exception.
- Hai advice **khác loại** dùng để xử lý hai nhánh **loại trừ nhau** của cùng target method, nên demo không dựa vào thứ tự của hai advice cùng loại trong một class.
- `argNames` chỉ rõ tên binding theo thuộc tính `returning` / `throwing`, tránh phụ thuộc vào việc compiler có lưu tên method parameters.
- `@AfterThrowing` **không nuốt exception** chỉ vì method advice trả `void`; exception của target vẫn đi lên A/B/caller nếu không được interceptor khác xử lý.

**Phạm vi typed binding:** `String` và `IllegalStateException` thu hẹp điều kiện của từng advice; không nên tuyên bố rằng chúng sẽ chạy cho **mọi** return type hoặc throwable type trong ứng dụng.

### 5.8. Spring configuration `AppConfig.java`

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TraceEvents traceEvents() {
        return new TraceEvents();
    }

    @Bean
    public TransferService transferService(TraceEvents trace) {
        return new TransferService(trace);
    }

    @Bean
    public OuterTraceAspect outerTraceAspect(TraceEvents trace) {
        return new OuterTraceAspect(trace);
    }

    @Bean
    public InnerTraceAspect innerTraceAspect(TraceEvents trace) {
        return new InnerTraceAspect(trace);
    }

    @Bean
    public OutcomeAspect outcomeAspect(TraceEvents trace) {
        return new OutcomeAspect(trace);
    }
}
~~~

**Quan trọng với Spring:**

- `@Aspect` đánh dấu class chứa advice, nhưng bản thân nó **không tự đăng ký Spring bean**. Các method `@Bean` tạo aspect instances.
- `@EnableAspectJAutoProxy` bật annotation-style AOP trong Spring Framework.
- `proxyTargetClass = true` chọn class-based Spring proxy để demo có thể yêu cầu bean bằng `TransferService.class`. **Không nên hiểu CGLIB làm thay đổi logic của `@Order`.**
- `TraceEvents` chỉ là collector; pointcut trong ba aspects chỉ match `TransferService.transfer(..)`, không match methods của TraceEvents.
- Thứ tự `@Bean` xuất hiện trong file **không quyết định** order của advice. Precedence dựa trên `@Order(10)`, `@Order(20)` và `@Order(30)`.
- Nếu thêm advisor transaction/cache/security ở một ứng dụng lớn, actual chain có thể thêm tầng cần quan sát; project này chủ động không khai báo chúng.

### 5.9. Kiểm tra tự động và chạy: `Main.java`

~~~java
package example;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    private static void check(
            String scenario,
            List<String> actual,
            List<String> expected) {

        if (!expected.equals(actual)) {
            throw new AssertionError(
                scenario + " trace mismatch.\n"
                + "expected: " + expected + "\n"
                + "actual:   " + actual
            );
        }
        System.out.println("verified: " + scenario);
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            TransferService service = context.getBean(TransferService.class);
            TraceEvents trace = context.getBean(TraceEvents.class);

            System.out.println("spring AOP proxy: "
                + AopUtils.isAopProxy(service));

            System.out.println("-- success --");
            String returned = service.transfer(false);
            System.out.println("caller result: " + returned);

            check("success", trace.drain(), List.of(
                "A: enter",
                "B: enter",
                "target: begin",
                "target: return OK",
                "C: returned OK",
                "B: after",
                "B: finally",
                "A: after",
                "A: finally"
            ));

            System.out.println("-- failure --");
            try {
                service.transfer(true);
                throw new AssertionError("Expected IllegalStateException");
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            check("failure", trace.drain(), List.of(
                "A: enter",
                "B: enter",
                "target: begin",
                "target: throw boom",
                "C: throwing IllegalStateException",
                "B: finally",
                "A: finally"
            ));
        }
    }
}
~~~

Phương thức `check` không chỉ xác minh tập events; `List.equals` còn xác minh **từng vị trí theo thứ tự** và **số lượng sự kiện**, nên phát hiện log thừa, log thiếu, đảo A/B, hoặc in “after” sai ở nhánh lỗi.

Bộ collector được `drain()` sau mỗi case nên trace của failure không bị lẫn với success. Cách phân đoạn theo case này là một cách thay thế đơn giản cho correlation ID **chỉ trong demo một luồng**.

### 5.10. Lệnh chạy

Tại thư mục `spring-aop-trace-demo` chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

Khi các dependency đã được giải quyết và project được chạy với Java 17+, các dòng `System.out.println` có thứ tự:

~~~text
spring AOP proxy: true
-- success --
A: enter
B: enter
target: begin
target: return OK
C: returned OK
B: after
B: finally
A: after
A: finally
caller result: OK
verified: success
-- failure --
A: enter
B: enter
target: begin
target: throw boom
C: throwing IllegalStateException
B: finally
A: finally
caller caught: boom
verified: failure
~~~

Maven hoặc framework có thể phát ra thông báo riêng không được liệt kê ở trên. Các dòng `verified` chỉ xuất hiện khi **toàn bộ thứ tự events đúng**; nếu sai, `Main.check(...)` ném `AssertionError` và in expected/actual để debug.

### 5.11. Kiểm chứng từng bước qua code

**Trường hợp success:**

1. Caller thực hiện `service.transfer(false)` qua Spring proxy.
2. A(10) in `enter`, rồi proceed.
3. B(20) in `enter`, rồi proceed.
4. C(30) không chạy trước target vì chỉ có after-returning/after-throwing advice; Spring chuyển tiếp đến method target.
5. Target ghi begin và return OK.
6. C nhận normal return và in `returned OK`.
7. B nhận kết quả trả về từ proceed, in after, rồi finally.
8. A nhận kết quả từ B, in after, rồi finally.
9. Caller nhận `OK` và check xác nhận đúng chín events trong collector.

**Trường hợp failure:**

1. A(10) enter rồi B(20) enter.
2. Target ghi begin, ghi throw, rồi ném `IllegalStateException("boom")`.
3. C(30) nhận exception trong `@AfterThrowing` và ghi loại ngoại lệ.
4. B không vào dòng after vì proceed ném lỗi; `finally` của B vẫn ghi.
5. A cũng không vào dòng after; `finally` của A vẫn ghi.
6. Caller bắt exception, rồi `check` so sánh đủ bảy events.
7. Cả hai trường hợp, target được gọi **một lần**; hai around advices không đổi arguments hoặc return/throw.

## 6. Phân biệt “after” trong bảng vết

Bốn khái niệm có thể xuất hiện cùng chữ “after” nhưng khác ngữ nghĩa:

| Hình thức | Khi nào xuất hiện? | Trong bảng vết |
| --- | --- | --- |
| Code đặt sau `pjp.proceed()` trong `@Around` | Chỉ khi proceed trả bình thường, nếu không có catch/finally bao ngoài | `A: after`, `B: after` |
| `@AfterReturning` | Method execution được advice trả về bình thường | `C: returned OK` |
| `@AfterThrowing` | Method execution được advice ném exception thoát ra và kiểu binding phù hợp | `C: throwing IllegalStateException` |
| `@After` | Method execution kết thúc bình thường **hoặc** exceptional exit | Có thể thêm vào trace, không có trong project để tránh nhiễu |
| `finally` của Java nằm trong `@Around` | Khối try trong advice được đi vào và rời theo normal/exception | `A: finally`, `B: finally` |

**Nhầm lẫn thường gặp:** Dòng `B: after` **không xuất hiện khi target lỗi** không phải vì Spring quên chạy `@After`. Trong demo không hề có annotation `@After` ở B; `B: after` là một lệnh Java bình thường sau proceed, nên khi proceed throw, Java bỏ qua lệnh đó.

**Muốn làm cleanup trong @Around:** dùng `try/finally`. **Muốn logic chạy sau method trên cả hai nhánh mà không cần biến trạng thái riêng:** cân nhắc `@After`. **Chỉ muốn outcome:** dùng `@AfterReturning` hoặc `@AfterThrowing`.

## 7. Nếu thêm @After vào cùng aspect thì sao?

Spring Framework mô tả advice ordering **trong cùng một class `@Aspect`**. Từ precedence cao xuống thấp:

1. `@Around`
2. `@Before`
3. `@After`
4. `@AfterReturning`
5. `@AfterThrowing`

Tuy nhiên, `@After` có **after-finally semantics** và **thực tế xuất hiện sau `@AfterReturning` hoặc `@AfterThrowing`** tương ứng khi join point kết thúc trong cùng aspect. Đây là lý do phải phân biệt **precedence lúc hình thành interceptor chain** với **thứ tự câu lệnh được in trên đường thoát**.

Ví dụ snippet bổ sung trong `OutcomeAspect`:

~~~java
@After("execution(public * example.TransferService.transfer(..))")
public void onFinished() {
    trace.record("C: finally");
}
~~~

Đoạn này **không nằm trong project nguyên bản**, vì nếu thêm nó thì bảng expected/output mục 5 phải được cập nhật.

Nếu thêm và chạy **trong cùng OutcomeAspect**, thứ tự nhánh thành công của lớp C về mặt outcome sẽ là:

~~~text
target: return OK
C: returned OK
C: finally
B: after
B: finally
A: after
A: finally
~~~

Nhánh lỗi:

~~~text
target: throw boom
C: throwing IllegalStateException
C: finally
B: finally
A: finally
~~~

Điểm học: `@After` ở đây **không** có nghĩa “chỉ after returning”; nó chạy ở cả hai nhánh. Điều này được Spring Framework mô tả rõ trong hướng dẫn chính thức về advice ordering.

**Không nhầm với hai lời advice cùng loại trong cùng aspect:** ví dụ hai `@After` methods cùng match một join point sẽ không có thứ tự bảo đảm chỉ nhờ vị trí khai báo trong source Java. Để trace xác định được, nên hợp nhất logic vào một advice hoặc tách thành các aspects có order rõ.

## 8. Nếu đổi @Order thì bảng vết phải đổi thế nào?

Giả sử thay:

~~~java
@Order(10)
public class OuterTraceAspect { /* ... */ }
~~~

bằng:

~~~java
@Order(40)
public class OuterTraceAspect { /* ... */ }
~~~

Mặc định ba lớp trong demo lúc đó có thứ tự:

~~~text
B: 20 (cao precedence nhất)
C: 30
A: 40 (thấp precedence nhất)
~~~

Vì C là after advice, A và B vẫn là around advice nhưng **B giờ bao ngoài A**. Trace khi success (sau khi cấu hình lại) có các sự kiện:

~~~text
B: enter
A: enter
target: begin
target: return OK
A: after
A: finally
C: returned OK
B: after
B: finally
~~~

Ở đây C(30) nằm **giữa B(20) và A(40)**. Vì C after-returning advice bao quanh lời gọi vào A(40), khi A hoàn tất thì C mới quan sát normal return. C không nhất thiết nằm sát target khi order đổi.

Đây là một phép thử suy luận hữu ích: **thứ tự thực thi không chỉ phụ thuộc vào loại advice**, mà còn phụ thuộc **lớp nào nằm ngoài/lớp nào nằm trong**.

**Không coi các dòng trên là stdout project mặc định**: chúng là dự đoán sau khi đổi order và khởi tạo **một ApplicationContext mới**. Không dựa vào thay annotation khi proxy đang sống để cho rằng chain tự cập nhật.

## 9. Khi có nhiều infrastructure advisors

Một Spring bean có thể có nhiều advisors hơn ba aspects do lập trình viên khai báo:

- Transaction interceptor qua `@Transactional`.
- Cache interceptor qua `@Cacheable`.
- Method security interceptor.
- Async/proxy infrastructure.
- Các `ProxyFactory` wrappers do code hoặc thư viện thứ ba tạo.

Giả sử:

~~~text
Caller
 -> Trace A
    -> TransactionInterceptor
       -> Trace B
          -> Target
       <- B finally
    <- commit/rollback
 <- A finally
~~~

Nếu A nằm **ngoài** transaction interceptor, A finally có thể xuất hiện **sau** transaction commit/rollback. Nếu A nằm **trong** transaction interceptor thì A finally có thể xuất hiện **trước** commit/rollback. Cách ghi bảng trace cần đánh dấu ranh giới này thay vì chỉ dựa vào “target trả OK” để kết luận transaction đã commit.

**Không tự khẳng định transaction có order cố định trong mọi Spring context.** Spring cung cấp cấu hình precedence cho một số infrastructure advisors (ví dụ `@EnableTransactionManagement(order = ...)`). Cần đọc cấu hình thật và kiểm tra advisor chain/test integration khi thứ tự ảnh hưởng nghiệp vụ.

Một trace chỉ dùng `System.out.println` từ các custom aspects **không cho thấy tự động** transaction begin/commit hoặc cache hit. Nếu mục tiêu là xác nhận ordering với transaction hoặc cache, nên thêm instrumentation/test transaction thật ở **lớp đúng** thay vì diễn giải quá mức từ log A/B.

## 10. Trường hợp có around advice kết thúc sớm

Giả sử một aspect ưu tiên cao hơn có logic:

~~~java
@Around("execution(public * example.TransferService.transfer(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    if (cached()) {
        return "CACHED";
    }
    return pjp.proceed();
}
~~~

Đây là **snippet minh họa**, với method `cached()` do ứng dụng tự định nghĩa, không thuộc project runnable.

Nếu tầng ngoài trả `"CACHED"` mà **không gọi proceed**, những tầng bên trong **không được đi vào**. Vì vậy bảng trace có thể là:

~~~text
outer: enter
outer: cache hit
caller result: CACHED
~~~

Không có dòng “target begin” không nhất thiết là lỗi; một lời advice đã có chủ đích short-circuit. Nhưng nếu bạn đang debug audit/security bắt buộc chạy, cần kiểm tra vị trí interceptor và tính đúng đắn của việc kết thúc sớm.

**Phân biệt ba trường hợp:**

1. Outer **chưa vào** → không có log outer.
2. Outer **đã vào nhưng không proceed** → chỉ có log từ outer hoặc các tầng đã vào trước đó.
3. Outer **đã proceed** nhưng một inner advisor shortcut → có log outer + một số tầng trong, **không có log target**.

Chỉ khi lập bảng vết đầy đủ mới phân biệt được “Spring AOP không hoạt động”, “pointcut không match”, “proxy bị bỏ qua” và “interceptor shortcut đúng thiết kế”.

## 11. Trường hợp exception không xuất phát từ target

Bảng failure ở mục 3 và 5 giả định **target method tự ném ngoại lệ**. Nhưng exceptional exit của một Spring AOP invocation có thể phát sinh ở nhiều vị trí:

| Nguồn exception | Target có nhất thiết đã chạy? | Các mốc có thể xuất hiện |
| --- | --- | --- |
| Target ném lỗi | Có, lời gọi đã tới target | target throw; callback on-throw phù hợp; outer finally |
| Inner `@Before` advice ném lỗi | **Không** | outer enter, có thể inner enter, rồi outer finally |
| Outer `@Around` ném lỗi trước `proceed()` | **Không** | các tầng ngoài đã vào; tầng trong có thể chưa vào |
| `@AfterReturning`/`@After` advice tự ném lỗi | Target có thể đã return bình thường | outer catch/finally có thể quan sát lỗi advice |
| Metrics backend/logging trong advice ném lỗi | Phụ thuộc vị trí ném | trace có thể bị thiếu hoặc ngoại lệ gốc bị che |
| Transaction commit ném lỗi sau target | Target có thể đã trả bình thường | Thứ tự tùy transaction advisor nằm ở đâu |

**Quy tắc an toàn:** `@AfterThrowing` không phải exception handler toàn cục cho mọi lỗi phát sinh từ các advice khác. Theo hướng dẫn Spring, `@AfterThrowing` hướng vào exceptional exit của **method join point** và không tự cam kết nhận exception do một `@After`/`@AfterReturning` khác sinh ra.

Nếu cần một trace phân biệt lỗi từ target, advice hay transaction commit, nên log rõ **vị trí exception được quan sát** và không chỉ nhìn loại exception. Một outer `@Around` có `catch(Throwable t)` có thể quan sát exception đi lên từ **bất kỳ phần chain phía trong** nào đã ném, không chỉ target.

## 12. “Ngoại lệ được bắt trong target” tạo trace nào?

Ví dụ:

~~~java
public String transferRecovering() {
    try {
        riskyOperation();
    } catch (IllegalStateException ex) {
        return "RECOVERED";
    }
}
~~~

Đoạn này là **snippet**, `riskyOperation()` là method minh họa chưa định nghĩa trong project mục 5.

Nếu method **bắt toàn bộ exception nội bộ rồi return `RECOVERED`**, từ góc nhìn Spring AOP method execution đã **kết thúc bình thường**. Hệ quả:

- `@AfterReturning` phù hợp có thể chạy với `"RECOVERED"`.
- `@AfterThrowing` không chạy cho exception đã bị bắt nội bộ.
- Code sau `proceed()` trong outer `@Around` có thể chạy.
- `finally` của những around advice đã vào vẫn chạy.

Không nên thấy dòng “operation failed internally” trong target rồi ngạc nhiên vì `@AfterThrowing` không xuất hiện; điểm phân biệt là **exception có thoát khỏi method join point hay không**.

Một outer interceptor cũng có thể bắt exception từ tầng trong rồi trả fallback. Khi ấy một aspect **ở ngoài** interceptor đó có thể quan sát **normal return**, còn tầng sâu hơn đã thấy exception. Chính vì thế bảng trace cần nêu rõ **tầng** quan sát outcome chứ không chỉ một nhãn “success/failure” toàn cục.

## 13. Self-invocation và những dòng trace bị thiếu

Trong Spring AOP proxy-based:

~~~java
public void outer() {
    this.inner();
}
~~~

Lời gọi `this.inner()` bên trong target **không tự quay trở lại Spring proxy**. Nếu pointcut của bạn chỉ nhắm `inner()`, nó có thể chạy advice khi caller gọi `service.inner()` trực tiếp qua proxy, nhưng **không** được advice cho lời gọi phát ra từ `this.inner()`.

Ví dụ bảng:

| Đường gọi | Trace AOP có thể thấy |
| --- | --- |
| `client -> springProxy.inner()` | aspect enter → inner target → aspect exit |
| `client -> springProxy.outer() -> target.this.inner()` | Có thể có aspect cho **outer**, nhưng **không tự có aspect riêng cho inner** |
| `client -> new Service().inner()` | Không có advice của Spring-managed proxy cho object tự tạo |

**@Order không giải quyết self-invocation.** Chuyển JDK proxy sang CGLIB cũng không tự sửa vì đây là ranh giới mô hình proxy của Spring AOP.

Cách sửa thường được ưu tiên: tách method cần advice sang **Spring bean khác** và gọi qua dependency injection. Đừng tự unwrap `Advised.getTargetSource()` rồi gọi target để debug; nó có thể cố tình bỏ qua tất cả lời advice bạn đang muốn xác minh.

## 14. @After và @AfterReturning/Throwing trong cùng aspect

Spring quy định precedence **bên trong một `@Aspect`** cho các advice khác loại, nhưng có **đặc thù về finally semantics**:

| Advice type | Chiều áp dụng chính | Ghi chú thứ tự |
| --- | --- | --- |
| `@Around` | Bao quanh invocation | Có thể chạy trước/sau `proceed()` |
| `@Before` | Trước join point | Không tự biết result |
| `@After` | Khi join point kết thúc theo hai nhánh | Về hiệu ứng, chạy **sau** after-returning/after-throwing cùng aspect |
| `@AfterReturning` | Khi join point trả bình thường | Không chạy nếu exception thoát method |
| `@AfterThrowing` | Khi join point ném exception | Không chạy khi method tự catch lỗi rồi return |

Spring mô tả precedence của distinct advice types trong cùng aspect theo thứ tự từ cao xuống thấp: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`. Nhưng **không** được chuyển bảng precedence thành một bảng stdout một chiều: vì tính chất `finally`, `@After` **thực tế được gọi sau** `@AfterReturning`/`@AfterThrowing` tương ứng trong cùng aspect.

Nếu có **hai advice cùng một loại** trong **cùng aspect** và cả hai match cùng method, thứ tự giữa chúng không được bảo đảm bằng thứ tự khai báo method trong source Java. Java reflection không cung cấp một thứ tự nguồn đủ tin cậy để dựa vào.

**Để trace xác định**, đừng thiết kế bài test cần thứ tự cố định giữa hai `@Before` cùng aspect; gộp xử lý tuần tự vào một advice hoặc tách thành hai aspects rồi đặt `@Order` khác nhau.

## 15. Mẫu bảng vết dùng cho integration test

Khi cần debug trong Spring Boot hay Spring Framework application thật, có thể tạo bảng với những cột sau:

| Trường | Ví dụ | Tác dụng |
| --- | --- | --- |
| `invocationId` | `op-17` | Phân nhóm events cùng một lời gọi, tránh trộn request |
| `sequence` | `1,2,3,...` | Thứ tự quan sát trong cùng invocation |
| `layer` | `outerAspect(10)` | Biết advisor/tầng nào ghi nhận |
| `phase` | `enter/after/throw/finally` | Phân biệt đường vào và ra |
| `method` | `TransferService.transfer` | Nhận diện method được advice |
| `outcome` | `normal/exceptional/unknown` | Tách loại kết quả quan sát |
| `exceptionType` | `IllegalStateException` | Phân loại loại lỗi, không cần log secrets |
| `thread` | Tên/ID thread | Hỗ trợ phát hiện events bị xen kẽ |
| `advisorOrder` | `10/20/30` | Giải thích precedence nếu cấu hình chính xác |

**Không biến bảng trace thành nơi ghi dữ liệu nhạy cảm:** tên operation và loại exception thường đủ. Không log mặc định mật khẩu, token, nội dung giao dịch, raw method arguments hoặc PII. Với trace production, dùng logging/tracing có correlation context đã được quản trị tốt.

### 15.1. Bảng expected/actual khi test sai

Một test nên đưa ra cả hai chuỗi:

~~~text
Expected:
[A: enter, B: enter, target: begin, C: ..., B: finally, A: finally]

Actual:
[B: enter, A: enter, target: begin, C: ..., A: finally, B: finally]
~~~

Nếu khác ở **chiều vào**, kiểm tra `@Order`/`Ordered` hoặc actual advisor chain. Nếu chỉ khác ở **chiều ra**, kiểm tra vị trí `finally`, lời `@After` và các nhánh `catch`. Nếu mất các dòng target, kiểm tra `proceed()` hoặc cache short-circuit. Nếu mất toàn bộ advice, kiểm tra pointcut, bean/proxy và self-invocation.

### 15.2. Assertions phải bao phủ cả nhánh lỗi

Sai lầm thường gặp là chỉ assert:

~~~java
assertTrue(events.contains("A: enter"));
assertTrue(events.contains("B: enter"));
~~~

Hai assertions ấy vẫn pass khi trình tự đảo ngược. Để xác minh ordering, dùng **so sánh cả danh sách theo thứ tự**, như `List.equals(...)` trong demo hoặc `assertEquals(expectedEvents, actualEvents)` trong JUnit.

Cần assert thêm:

- Result business vẫn chính xác trong normal path.
- Exception **type** và message/identity khi contract yêu cầu.
- Số lượt target được gọi đúng một lần nếu không có retry.
- Không xuất hiện callback `@AfterReturning` ở exceptional path.
- Không xuất hiện callback `@AfterThrowing` ở normal path.
- Finally của mỗi around advice **đã vào** xuất hiện đủ số lần.
- Không có events từ invocation khác lẫn vào.
- Những methods/beans ngoài pointcut không bị advice vô ý.

## 16. Những giới hạn khiến bảng vết khác kỳ vọng

### 16.1. Asynchronous logging và nhiều thread

Một lời gọi Spring AOP đồng bộ có thứ tự Java rõ ràng, nhưng log exporter bất đồng bộ có thể gửi hoặc hiển thị events với thứ tự khác. Nếu hai requests chạy song song, dòng `A: enter` của request 2 có thể nằm giữa `A: enter` và `B: enter` của request 1.

Vì vậy **không dùng một global list không đồng bộ** làm test cho nhiều lời gọi concurrently. Dùng collection per-invocation hoặc trace context mang correlation ID đúng vòng đời; phân nhóm trước rồi mới so sánh thứ tự.

### 16.2. Method trả Future/reactive publisher

`@AfterReturning` trên method trả `CompletableFuture` có thể chạy ngay khi method **trả Future object**, không có nghĩa công việc nền đã hoàn tất. `@AfterThrowing` không mặc nhiên quan sát lỗi phát sinh **sau đó** trong async computation. Tương tự, method trả `Mono`/`Flux` có thể kết thúc trước khi pipeline reactive được subscribe.

Nếu yêu cầu trace **toàn bộ** vòng đời async, phải dùng completion hooks hoặc lifecycle operators đúng abstraction; đừng đọc “method returned” thành “request fully completed”.

### 16.3. Cấu hình proxy và method không intercept được

- JDK proxy chỉ expose các interfaces thích hợp; class-based CGLIB proxy dùng subclass.
- Class/method final hoặc private có thể không được advice theo cơ chế class proxy.
- `@Aspect` class cần được đăng ký làm bean.
- Bean có AOP proxy không bảo đảm **mọi method** match mọi advisor.
- Self-invocation vẫn bỏ qua proxy với cả JDK/CGLIB.
- Infrastructure advisor bên thứ ba có thể ở ngoài custom @Aspect.

Một trace thiếu event không chứng minh Spring AOP bug; trước tiên xác nhận target bean, proxy reference và pointcut eligible.

## 17. Chẩn đoán theo triệu chứng

| Hiện tượng | Giả thuyết ưu tiên | Cách kiểm chứng |
| --- | --- | --- |
| A enter trước B enter nhưng A finally cũng trước B finally | Có thể log được ghi khác tầng hoặc code finally đặt khác kỳ vọng | Xem cấu trúc `proceed()` và thực tế interceptor chain |
| C returned xuất hiện khi tưởng target lỗi | Target hoặc inner interceptor đã bắt exception và trả fallback | Xác định outcome tại boundary của C |
| Không có C throwing khi target ném lỗi | Throwable type không match, caller bypass proxy hoặc một tầng đã xử lý | Kiểm tra throwing binding và target method execution |
| B after không xuất hiện nhưng B finally có | Lời `proceed()` của B ném exception | Đây có thể là hành vi đúng |
| A và B đều không có log | Aspect không là Spring bean, pointcut không match hoặc caller không qua proxy | Kiểm tra `@Bean`, AOP config, `AopUtils.isAopProxy` |
| Có A enter nhưng không có B enter | A chưa proceed hoặc advisor tầng trước B short-circuit | Xem early return, cache hit, precondition |
| Target chạy hai lần | Retry/multiple `proceed()`/duplicate caller | Đếm invocation và kiểm tra idempotency |
| Trace đúng success, sai failure | Bỏ sót `finally` hoặc xử lý exception khác nhau | Assert riêng exceptional path |
| Trace thay đổi sau thêm `@Transactional` | Thêm infrastructure advisor với order riêng | Kiểm tra advisor chain, transaction boundary |
| Chỉ thấy events khi gọi từ controller, không thấy khi service tự gọi | Self-invocation | Đường gọi `this.method()` bypass Spring proxy |
| Log bị đảo ngẫu nhiên giữa requests | Các request song song hoặc backend log async | Phân nhóm theo invocationId, không so toàn cục |
| Hai advice cùng loại trong cùng aspect đảo vị trí sau build | Thứ tự method source không được bảo đảm | Gộp advice hoặc tách aspect classes và gắn order |
| @Order nhỏ nhưng advice không chạy | Order không quyết định pointcut matching | Kiểm tra bean/method và đường gọi |
| Advice onThrow tự ném exception mới | Caller có thể thấy exception bị thay | Hạn chế lỗi instrumentation, kiểm tra exception contract |

### Checklist khắc phục có trình tự

1. Xác định **method, target bean và caller reference thực**.
2. Đọc cấu hình Spring AOP và tên `@Aspect` beans đã đăng ký.
3. Xác nhận pointcuts và những advisors eligible cho method.
4. Ghi order **số cụ thể** cho những aspects phải có precedence cố định.
5. Tách event thành **enter / target / result hoặc throw / after / finally**.
6. Chạy một invocation success, một invocation failure, không đồng thời.
7. So sánh **full expected vs actual sequences**, không chỉ sự hiện diện của log.
8. Thêm biến thể method tự catch exception rồi return nếu nghiệp vụ có fallback.
9. Khi có transaction/cache/async, mở rộng bảng trace cho các tầng thật.
10. Kiểm tra behavior: return value, exception, side effects, invocation count.
11. Chỉ sau khi đường gọi đơn luồng đúng mới mở rộng test concurrency/log aggregation.
12. Nếu thay đổi order, tạo context/test run mới và xác minh lại chain.

## 18. Câu hỏi luyện tập

**Câu 1.** A có `@Order(5)`, B có `@Order(50)` và hai around advice đều proceed. Aspect nào enter trước, aspect nào finally sau?

**Đáp án:** A(5) có precedence cao hơn, **enter trước** và **finally sau** B(50).

**Câu 2.** Có log A enter → B enter → target throw → B finally → A finally nhưng không có “A after”. Spring AOP bị lỗi?

**Đáp án:** Không. Lệnh after đặt **sau `proceed()`** trong around advice không chạy khi proceed ném lỗi. Finally của cả A/B vẫn chạy.

**Câu 3.** `@AfterReturning` và `@AfterThrowing` cùng match method signature nhưng target trả bình thường. Chạy cả hai?

**Đáp án:** Không. Chỉ after-returning phù hợp chạy ở normal exit; after-throwing chỉ chạy khi exception thoát method và kiểu throwable khớp.

**Câu 4.** Method target tự catch exception rồi return `"RECOVERED"`. Bảng trace nào đúng?

**Đáp án:** Từ góc nhìn Spring AOP, đó là **normal return**, nên after-returning phù hợp có thể chạy. Lỗi bị bắt nội bộ không tự kích hoạt after-throwing.

**Câu 5.** Outer around không gọi proceed vì cache hit. Có bắt buộc target và các inner advice chạy?

**Đáp án:** Không. Chỉ các tầng đã được đi vào trước khi shortcut mới có thể có events. Cần xác minh đây là hành vi có chủ đích hay quên proceed.

**Câu 6.** Có hai `@Before` cùng class `@Aspect`, cùng match join point. Code source khai báo first trước second; thứ tự được bảo đảm?

**Đáp án:** Không. Nếu cần thứ tự xác định, gộp logic hoặc dùng hai aspect classes có order khác nhau.

**Câu 7.** Trong một aspect có `@After` và `@AfterReturning` cùng match method thành công. Vì @After có precedence cao hơn nên dòng @After luôn in trước @AfterReturning?

**Đáp án:** Không. Spring quy định `@After` có **after-finally semantics** và thực tế chạy sau after-returning hoặc after-throwing phù hợp **trong cùng aspect**.

**Câu 8.** Chỉ cần assert `events.contains("A: enter")` và `events.contains("B: enter")` là chứng minh được A trước B?

**Đáp án:** Không. Phải assert **thứ tự phần tử**, ví dụ `List.equals(expectedSequence)` hoặc kiểm tra indexes có điều kiện rõ ràng.

**Câu 9.** Caller tạo `new TransferService(trace)` và gọi method. Bảng A/B/C có áp dụng không?

**Đáp án:** Không tự áp dụng. Instance ngoài Spring container không phải bean proxy được Spring AOP tạo.

**Câu 10.** Trace business có thể kết luận “transaction committed” chỉ vì `@AfterReturning` xuất hiện sau target?

**Đáp án:** Không. Commit có thể xảy ra trong transaction interceptor ở vị trí khác; phải kiểm tra actual transaction boundary và advisor ordering.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework — Declaring Advice / Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): quy tắc thứ tự giữa aspects, `@Order`/`Ordered`, đường vào/đường ra, after-returning/after-throwing và `@After` finally semantics.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, self-invocation, proxy boundaries.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký Spring aspect beans và bật proxy AOP.
- [Spring Framework — Declaring Pointcuts](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): lựa chọn method execution phù hợp, tránh tác động bean khác.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): Spring AOP join point và các advice type.
- [Spring Framework — Manipulating Advised Objects](https://docs.spring.io/spring-framework/reference/core/aop-api/advised.html): quan sát advisor chain của một Spring AOP proxy.
- [Spring Javadoc — Ordered](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html): thứ tự giá trị precedence.
