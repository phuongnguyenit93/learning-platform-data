# Phân biệt ngoại lệ từ phương thức đích và từ advice khác trong Spring AOP

## 1. Mục tiêu và tình huống

Trong Spring Framework AOP, một lần gọi service qua proxy có thể thất bại vì **target method** hoặc vì **một advisor/advice đứng trước, sau hay bao quanh target**. Ví dụ:

- `@Before` kiểm tra quyền và ném exception **trước khi target chạy**.
- Target method tự ném exception trong quá trình xử lý nghiệp vụ.
- Target **trả kết quả bình thường**, nhưng `@AfterReturning` tự ném exception khi xử lý kết quả.
- `@Around` bắt exception từ continuation rồi **đổi thành một exception khác**, hoặc nuốt lỗi và trả fallback.
- `@After` chạy cleanup rồi ném lỗi mới, đôi khi che đi exception gốc.
- `TransactionInterceptor` hoặc exception-translation interceptor có thể tạo/chuyển đổi exception **bên ngoài thân method target**.

Vì vậy, **exception cuối mà caller nhận từ Spring proxy không chứng minh target body đã ném exception ấy**. Điều này ảnh hưởng logging, audit, metrics, retry và chẩn đoán lỗi.

Sau bài này, bạn sẽ biết:

1. Phân biệt **throw site**, **observation site**, **exception cuối** và **target execution outcome**.
2. Hiểu `@AfterThrowing` được Spring thiết kế cho method execution ném lỗi, **không phải một global catch cho mọi advice khác**.
3. Biết `@Around` bắt được exception từ **continuation phía trong**, có thể gồm cả inner advice.
4. Dùng `@Order` để kiểm soát phạm vi mà từng advice quan sát được.
5. Thử bốn kịch bản với Spring Framework 6.2.x, Java 17+, Maven: bình thường; target throw; before advice throw; after-returning advice throw.
6. Thiết kế instrumentation để không ghi nhầm “target failed” khi thực tế một advice bị lỗi.
7. Nhận diện giới hạn proxy, checked exception wrapping, transaction commit và secondary exception.

**Giới hạn phạm vi:** Chỉ tập trung vào **Spring-managed `@Aspect` và Spring proxy-based AOP**, không đi sang AspectJ weaving hoặc các khái niệm AOP tổng quát không cần cho tình huống Spring.

## 2. Đặt từng nguồn lỗi vào đúng vị trí của interceptor chain

Demo ở mục 6 sử dụng **bốn aspect tách biệt**, có `@Order` rõ ràng:

~~~text
Client → Spring proxy
       → OuterTraceAspect @Around (0)
       → BeforeGateAspect @Before (10)
       → AfterResultAspect @AfterReturning (20)
       → TargetFailureAspect @AfterThrowing (30)
       → JobService.execute(...) (target)
~~~

Các aspect nằm ở tầng ngoài có thể nhìn thấy lỗi xuất hiện từ tầng trong khi gọi `proceed()`. Nhưng nếu `BeforeGateAspect` ném lỗi, target và các advisor nằm sâu hơn chưa chạy; nếu `AfterResultAspect` ném sau khi target return, `TargetFailureAspect` nằm phía trong đã kết thúc bình thường. Đây là **thứ tự có chủ đích của demo**, không phải thứ tự mặc định của mọi Spring application.

| Scenario | Nơi đầu tiên phát sinh lỗi | Target đã chạy? | Observer trong cùng demo thấy gì? |
| --- | --- | --- | --- |
| `BEFORE` | `@Before` ngoài | Không | Outer `@Around` catch; inner `@AfterThrowing` không được enter |
| `TARGET` | `JobService.execute()` | Có, nhưng throw | Inner `@AfterThrowing` log; outer `@Around` catch |
| `AFTER` | `@AfterReturning` ngoài | Có, đã return | Outer `@Around` catch; inner `@AfterThrowing` đã hoàn tất |
| `OK` | Không có lỗi | Có, đã return | Outer `@Around` trả kết quả bình thường |

## 3. Truy nguyên lỗi: phân biệt nguồn ném, nơi quan sát và kết quả caller

| Tín hiệu | Câu hỏi cần xác minh |
| --- | --- |
| **Throw site** | Java code nào thực sự tạo và ném Throwable gốc? |
| **Target outcome** | Thân method đã chạy, và nó return hay throw? |
| **Observation site** | Advisor nào nhìn thấy lỗi khi Throwable đi qua tầng đó? |
| **Final exception** | Throwable nào cuối cùng ra khỏi Spring proxy tới caller? |

Một target có thể throw `IllegalArgumentException` nhưng inner `@Around` chuyển thành `ServiceException` và giữ lỗi cũ ở `cause`. Khi đó observer ở ngoài và caller nhìn thấy `ServiceException`; điều này **không chứng minh** target đã ném loại lỗi mới. Dùng `getCause()`, suppressed exceptions và structured trace/correlation ID để truy nguyên. `JoinPoint.getSignature()` chỉ định danh join point đang được advice, **không cung cấp throw site**.

## 4. Ranh giới của `@AfterThrowing`

~~~java
@AfterThrowing(
    pointcut = "execution(* demo.JobApi.execute(..))",
    throwing = "ex"
)
public void onFailure(RuntimeException ex) {
    System.out.println("AFTER_THROWING " + ex.getClass().getSimpleName());
}
~~~

Đây là fragment trong một Spring `@Aspect`. `throwing = "ex"` phải khớp tên tham số advice; kiểu `RuntimeException` chỉ bind lỗi thuộc kiểu ấy (có thể dùng `Throwable` nếu cần phạm vi rộng hơn). Advice ghi log rồi trả `void` **không tự nuốt lỗi**.

Theo Spring Framework, `@AfterThrowing` phục vụ exception từ method execution được advice, **không phải callback tổng quát cho ngoại lệ phát sinh từ companion `@After`/`@AfterReturning`**. Nó quan sát Throwable nào còn phụ thuộc vị trí advisor, typed binding và việc continuation có đi tới advisor đó hay không. Nếu chính observer ném thêm lỗi, caller có thể thấy lỗi mới và mất nguyên nhân ban đầu.

## 5. `@Around` quan sát continuation, không suy ra nguồn lỗi

~~~java
@Around("execution(* demo.JobApi.execute(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (RuntimeException ex) {
        System.out.println("OUTER caught " + ex.getClass().getName());
        throw ex;
    }
}
~~~

Khi đây là advisor ngoài cùng, `catch` có thể nhận lỗi từ inner `@Before`, target, inner `@AfterReturning`, `@After`, transaction commit hoặc interceptor khác. Log `OUTER caught` chỉ chứng minh **continuation bên trong thất bại**, chưa chứng minh thân target thất bại. Nếu chính outer `@Around` ném trước `proceed()`, phía trong có thể chưa hề chạy.

## 6. Demo hoàn chỉnh Spring Framework: ba nguồn lỗi rõ ràng

Môi trường:

- **Java 17+**
- **Maven 3.9+**
- **Spring Framework 6.2.12**
- **AspectJ Weaver 1.9.24**

Mỗi concern đặt ở một Spring `@Aspect` class riêng với `@Order` khác nhau, tránh phụ thuộc thứ tự không được bảo đảm giữa hai advice cùng loại trong một aspect. Dự án dùng **Spring Framework thuần**, không cần Spring Boot/DB/server.

### 6.1. Cấu trúc

~~~text
spring-aop-exception-origin/
├── pom.xml
└── src/main/java/demo/
    ├── JobApi.java
    ├── Failures.java
    ├── JobService.java
    ├── OuterTraceAspect.java
    ├── BeforeGateAspect.java
    ├── AfterResultAspect.java
    ├── TargetFailureAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-exception-origin</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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

`spring-context` kéo các module Spring AOP cần thiết; `aspectjweaver` hỗ trợ annotations/pointcut expression cho Spring `@AspectJ` style. Không dùng AspectJ compiler/weaving ở đây.

### 6.3. JobApi.java

~~~java
package demo;

public interface JobApi {
    String execute(String scenario);
}
~~~

Interface bảo đảm caller có thể lấy bean theo kiểu `JobApi`. Spring AOP có thể dùng JDK dynamic proxy với implementation có interface.

### 6.4. Failures.java

~~~java
package demo;

public final class Failures {

    private Failures() {
    }

    public static final class TargetFailure
            extends RuntimeException {
    }

    public static final class BeforeFailure
            extends RuntimeException {
    }

    public static final class AfterFailure
            extends RuntimeException {
    }
}
~~~

Ba custom exceptions riêng giúp demo nhận diện **nguồn throw theo thiết kế**. Trong production, type name không tự chứng minh nguồn throw: bất kỳ component nào cũng có thể ném cùng type, hoặc exception có thể bị translate.

### 6.5. JobService.java

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class JobService implements JobApi {

    @Override
    public String execute(String scenario) {
        System.out.println("TARGET enter " + scenario);

        if ("TARGET".equals(scenario)) {
            throw new Failures.TargetFailure();
        }

        return "done:" + scenario;
    }
}
~~~

Target chỉ ném ở kịch bản `TARGET`. Với `AFTER`, nó **đã chạy và trả bình thường**, trước khi một advice khác có thể gây exception.

### 6.6. OuterTraceAspect.java

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(0)
public class OuterTraceAspect {

    @Around("execution(* demo.JobApi.execute(..))")
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        String scenario = (String) pjp.getArgs()[0];

        System.out.println("OUTER enter " + scenario);

        try {
            Object result = pjp.proceed();
            System.out.println("OUTER success " + scenario);
            return result;
        } catch (RuntimeException ex) {
            System.out.println(
                    "OUTER caught " + ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
~~~

Vì `@Order(0)` có precedence cao hơn các aspects còn lại trong demo, outer around nằm ngoài và quan sát cả **before**, **target**, **after-returning** ở continuation.

`pjp.proceed()` được gọi đúng một lần; advice không short-circuit. `catch` ở đây cố ý chỉ nhận RuntimeException của ba kịch bản, không phải chính sách bắt `Error`/checked exception tổng quát.

### 6.7. BeforeGateAspect.java

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(10)
public class BeforeGateAspect {

    @Before("execution(* demo.JobApi.execute(..))")
    public void before(JoinPoint jp) {
        String scenario = (String) jp.getArgs()[0];
        System.out.println("BEFORE enter " + scenario);

        if ("BEFORE".equals(scenario)) {
            throw new Failures.BeforeFailure();
        }
    }
}
~~~

Với input `BEFORE`, advice ném **trước khi target hoặc các inner advisors được đi tới**. Caller vẫn thấy exception khi gọi JobApi, nhưng target không ném lỗi vì target chưa chạy.

### 6.8. AfterResultAspect.java

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(20)
public class AfterResultAspect {

    @AfterReturning(
        pointcut = "execution(* demo.JobApi.execute(..))",
        returning = "result"
    )
    public void after(JoinPoint jp, Object result) {
        String scenario = (String) jp.getArgs()[0];
        System.out.println("AFTER_RETURNING " + scenario);

        if ("AFTER".equals(scenario)) {
            throw new Failures.AfterFailure();
        }
    }
}
~~~

Với `AFTER`, target trả về `done:AFTER` rồi advice ném `AfterFailure`. Vì thế **target thành công nhưng proxy invocation thất bại**. `returning="result"` bind kết quả trả về vào tham số cùng tên; `Object` cho phép nhận String trong project này.

### 6.9. TargetFailureAspect.java

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(30)
public class TargetFailureAspect {

    @AfterThrowing(
        pointcut = "execution(* demo.JobApi.execute(..))",
        throwing = "ex"
    )
    public void afterThrow(JoinPoint jp, RuntimeException ex) {
        System.out.println(
                "AFTER_THROWING " + ex.getClass().getSimpleName());
    }
}
~~~

Aspect này được đặt **phía trong** before và after-returning aspects của demo:

- `TARGET`: target ném, exception đi qua `@AfterThrowing`, log xuất hiện.
- `BEFORE`: lời gọi bị chặn trước khi đến advisor này, nên không có log.
- `AFTER`: advisor này đã hoàn tất bình thường khi target trả về; after-returning advice đứng ngoài nó mới ném exception, nên không có log.
- `OK`: target trả bình thường, không có log.

Đây là **kết quả của thứ tự được thiết kế và kiểm chứng trong demo**, không phải tuyên bố mọi `@AfterThrowing` đều tự biết nguồn throw trong mọi Spring context.

### 6.10. AppConfig.java

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
~~~

`@Aspect` không tự đăng ký object thành bean. Mỗi aspect trong demo có thêm `@Component` và `@ComponentScan` bao phủ package. `@EnableAspectJAutoProxy` bật hạ tầng tạo proxy.

### 6.11. App.java

~~~java
package demo;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JobApi jobs = context.getBean(JobApi.class);
            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(jobs));

            for (String scenario :
                    List.of("OK", "TARGET", "BEFORE", "AFTER")) {
                System.out.println("=== " + scenario + " ===");

                try {
                    String result = jobs.execute(scenario);
                    System.out.println("CALLER result " + result);
                } catch (RuntimeException ex) {
                    System.out.println(
                            "CALLER caught " +
                            ex.getClass().getSimpleName());
                }
            }
        }
    }
}
~~~

Chương trình lấy **Spring-managed proxy**; không tạo JobService bằng `new`. Mỗi exception được bắt ở caller để các scenario tiếp theo vẫn chạy.

Chạy trong thư mục có `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

### 6.12. Stdout logic kỳ vọng

~~~text
IS_PROXY true
=== OK ===
OUTER enter OK
BEFORE enter OK
TARGET enter OK
AFTER_RETURNING OK
OUTER success OK
CALLER result done:OK
=== TARGET ===
OUTER enter TARGET
BEFORE enter TARGET
TARGET enter TARGET
AFTER_THROWING TargetFailure
OUTER caught TargetFailure
CALLER caught TargetFailure
=== BEFORE ===
OUTER enter BEFORE
BEFORE enter BEFORE
OUTER caught BeforeFailure
CALLER caught BeforeFailure
=== AFTER ===
OUTER enter AFTER
BEFORE enter AFTER
TARGET enter AFTER
AFTER_RETURNING AFTER
OUTER caught AfterFailure
CALLER caught AfterFailure
~~~

Đây là **stdout logic dự kiến**, không tính logging riêng của Maven/Spring. Các aspects có precedence khác nhau để output không dựa trên thứ tự không xác định của nhiều advice cùng loại ở cùng class.

### 6.13. Bảng suy luận kết quả

| Kịch bản | `@Before` | Target chạy | Target throw | `@AfterReturning` | `@AfterThrowing` bên trong log | Caller |
| --- | --- | --- | --- | --- | --- | --- |
| **OK** | chạy | có | không | chạy | không | `done:OK` |
| **TARGET** | chạy | có | có | không chạy | **TargetFailure** | `TargetFailure` |
| **BEFORE** | chạy rồi throw | **không** | không | không chạy | không | `BeforeFailure` |
| **AFTER** | chạy | có và return | không | chạy rồi throw | không | `AfterFailure` |

Cả ba nhánh lỗi đều có `OUTER caught ...`. Như vậy **outer @Around quan sát lỗi từ nhiều thành phần**, còn inner `@AfterThrowing` chỉ quan sát lỗi target trong cấu hình có kiểm soát này.

## 7. Ghi log/metrics chính xác theo phase

Không nên dùng một counter `target_exception_count` để tăng mỗi khi generic outer `@Around` catch exception. Một phương án giàu thông tin hơn:

| Trường metadata | Ý nghĩa |
| --- | --- |
| `proxy.outcome` | Caller nhận result hay exception? |
| `target.reached` | Có bằng chứng đã đi vào target body chưa? |
| `target.outcome` | Body target return hay throw? |
| `advice.phase` | before, after-returning, after-throwing, around, transaction... |
| `exception.type` | Class exception quan sát được |
| `exception.cause` | Cause chain nếu có wrapper |
| `operation.id` | Correlation ID của logical invocation |
| `advisor.order` | Vị trí/precedence có liên quan |

`pjp.getTarget()` cho biết target object, **không chứng minh target method đã chạy**. `MethodSignature.getMethod()` nói tên/chữ ký method, **không cho biết nơi phát sinh exception**. Nếu cần chắc chắn target đã được thực thi, dùng instrumentation **ở bên trong target hoặc ranh giới target**, hoặc integration-test với spy/counter.

## 8. @Around đổi, nuốt hoặc giữ exception

### 8.1. Chuyển đổi và giữ cause

~~~java
@Around("execution(* demo.JobApi.execute(..))")
public Object translate(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (Failures.TargetFailure ex) {
        throw new IllegalStateException("Service failed", ex);
    }
}
~~~

Fragment này minh họa cách một aspect **tạo exception mới** nhưng giữ original dưới `getCause()`. Outer observer sẽ trực tiếp thấy `IllegalStateException`, không phải `TargetFailure`.

### 8.2. Nuốt exception và trả fallback

~~~java
@Around("execution(* demo.JobApi.execute(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (Failures.TargetFailure ex) {
        return "fallback";
    }
}
~~~

Nếu fallback được phép theo contract, caller có thể thấy **proxy success** dù target đã ném lỗi. Đừng ghi `target.success=true` chỉ dựa vào kết quả của outer `@Around`.

### 8.3. Lỗi mới trong finally

~~~java
try {
    return pjp.proceed();
} finally {
    auditWriter.write();
}
~~~

Đây là fragment. Nếu `pjp.proceed()` ném lỗi X nhưng `auditWriter.write()` cũng ném lỗi Y từ `finally`, Y có thể **che X**. Nếu audit là best-effort, có thể bắt riêng lỗi audit rồi giữ exception gốc; nếu audit là bắt buộc, cần quy tắc ưu tiên lỗi rõ ràng.

**Không chép ba fragment này cùng lúc vào demo mục 6** nếu muốn giữ expected stdout: chúng là các phương án thay thế dành cho thực hành.

## 9. @AfterThrowing tự ném cũng có thể che lỗi gốc

Ví dụ:

~~~java
@AfterThrowing(
    pointcut = "execution(* demo.JobApi.execute(..))",
    throwing = "original"
)
public void audit(RuntimeException original) {
    auditWriter.write(original);
}
~~~

Nếu target ném `TargetFailure`, nhưng `auditWriter.write` ném `AuditStorageFailure`, caller có thể nhận `AuditStorageFailure` thay lỗi ban đầu. `@AfterThrowing` không phải một observer vô hại nếu code bên trong có thể ném.

Với một chính sách **giữ nguyên lỗi nghiệp vụ**, có thể dùng fragment:

~~~java
try {
    return pjp.proceed();
} catch (RuntimeException original) {
    try {
        auditWriter.write(original);
    } catch (RuntimeException auditError) {
        original.addSuppressed(auditError);
    }
    throw original;
}
~~~

Mẫu này giữ original và đính lỗi audit vào suppressed list. Nhưng không phù hợp mọi hệ thống, đặc biệt nơi audit failure phải làm thay đổi business outcome; cần xác định policy rõ ràng.

Một Spring bean recorder được aspect gọi cũng phải **nằm ngoài pointcut của chính aspect ấy** để tránh advice lặp lại qua collaborator.

## 10. Transaction và exception translation: lỗi sau target

Trong Spring, ngoài custom `@Aspect` còn có những interceptors như:

- `TransactionInterceptor` cho các `@Transactional` phù hợp.
- Method security advisors.
- Spring persistence exception translation cho các repository đã được cấu hình.
- Cache/retry advisors do ứng dụng hoặc thư viện cung cấp.

Chẳng hạn:

~~~text
Client -> OuterTraceAspect -> TransactionInterceptor
                                   |
                                   +-- begin transaction
                                   +-- Target method RETURN
                                   +-- COMMIT throws exception
                    |
                    +-- OuterTraceAspect catches commit error
~~~

Target body **có thể đã return bình thường**, nhưng proxy trả lỗi vì commit thất bại. Vì vậy cần phân biệt:

- `target.body.success`
- `transaction.commit.success`
- `proxy.invocation.success`

Chúng không luôn giống nhau. Nếu `@AfterReturning` nằm **trong** transaction advisor, callback có thể chạy trước khi commit; nếu nó đứng **ngoài**, có thể quan sát một kết quả đã qua transaction. Thứ tự này cần được kiểm tra trên context thực.

Spring exception translation cũng có thể khiến caller thấy `DataAccessException` thay vì exception low-level đã phát sinh trong repository, tùy translator và configuration. Đừng khẳng định mọi `@Repository` tự dịch mọi exception nếu chưa có advisor/translator phù hợp.

## 11. Java checked exception và JDK proxy

Interface:

~~~java
public interface FileApi {
    String read(String path) throws java.io.IOException;
}
~~~

Đây là fragment interface, không phải file của demo mục 6. Nếu target ném `IOException` được khai báo, caller có thể catch type ấy bình thường.

Nếu một advice ném **checked exception không thuộc method throws contract**, JDK dynamic proxy có thể wrap vào `UndeclaredThrowableException`. Lúc đó exception cuối khác exception do advice ném, và caller nên kiểm tra cause có kiểm soát.

Hướng thực hành:

- Ưu tiên exception types tương thích Java interface contract.
- Không dùng `catch(Throwable)` rồi retry mọi thứ.
- Không giả định một class exception ở caller cho biết nơi lỗi bắt đầu.
- Khi log, giữ cause/suppressed data nếu domain cho phép.
- Test cả JDK và CGLIB proxies nếu application phụ thuộc vào proxy type.

Demo hoàn chỉnh chỉ dùng **unchecked exceptions** để dễ quan sát mà không làm lẫn checked-exception mechanics.

## 12. Short-circuit và self-invocation

Một outer `@Around` có thể chủ động ném lỗi hoặc trả fallback **không gọi `proceed()`**:

~~~java
if (maintenanceMode) {
    throw new IllegalStateException("Rejected by outer advice");
}
return pjp.proceed();
~~~

Đây là fragment. Trong nhánh bảo trì, các advisors phía trong và target không được đi tới. Một `@AfterThrowing` nằm phía trong sẽ **không quan sát được lỗi mà outer advice tự ném trước proceed**.

Ngược lại, self-invocation:

~~~java
public void outer() {
    this.inner();
}
~~~

có thể **bỏ qua Spring proxy**, nên advice cho inner không tự chạy, dù body inner vẫn thực thi. Đây không phải `@Around` short-circuit; ở đây AOP join point cho inner **không được proxy intercept ngay từ đầu**.

Hai tình huống phải phân biệt:

1. **Không vào proxy**: advice không chạy.
2. **Vào proxy rồi ném trước target**: một số advice đã chạy, target chưa chạy.

## 13. Advice ordering là một phần của kết luận

Trong Spring `@AspectJ` style:

- `@Order` hoặc `Ordered` giúp cấu hình precedence giữa các aspects.
- Số nhỏ hơn thường biểu thị precedence cao hơn.
- Trên đường vào, outer aspect chạy trước.
- Trên đường ra, inner aspects hoàn tất trước outer aspects khi continuation được gọi bình thường.
- Hai advice **cùng loại trong cùng một class `@Aspect`** và cùng match không có thứ tự source được bảo đảm.
- `@After` mang finally semantics; nó không có nghĩa “luôn chạy trước `@AfterReturning`” chỉ vì thứ tự precedence khác loại.

Một observer ở phía ngoài có thể nhìn thấy nhiều loại lỗi hơn một observer phía trong. Thay đổi `@Order` có thể thay đổi exception mà observer thấy, vì vậy test cần kết hợp **source, type, order và invocation path**.

## 14. Checklist debug khi proxy invocation thất bại

1. Xác nhận caller có gọi **Spring-managed proxy** không; `AopUtils.isAopProxy(bean)` là kiểm tra ban đầu hữu ích.
2. Liệt kê **mọi advisor** đang áp dụng: custom aspects, transaction, security, cache và translation.
3. Xác định precedence thực, không suy ra từ thứ tự method trong source.
4. Ghi nhận **target entry** và **target exit** nếu cần khẳng định target body có chạy.
5. Đặt một outer observer cho **proxy outcome**, đồng thời ghi stage của các advice nghi ngờ.
6. Thử riêng target throw, before throw, after-returning throw.
7. Xem `getCause()` / suppressed exceptions nếu có wrapping.
8. Kiểm tra transaction commit/rollback và external side effects.
9. Không thay exception gốc bằng lỗi ghi metrics/audit ngoài ý muốn.
10. Phân loại logs: target failure, advice failure, transaction failure và proxy outcome.

## 15. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Log “target error” khi before advice chặn quyền | Gán mọi proxy exception cho target | Theo dõi target-entry và phase |
| Target in “return” nhưng caller nhận exception | AfterReturning/transaction interceptor ném sau target | Kiểm tra advisors đường ra |
| `@AfterThrowing` không log dù caller catch lỗi | Exception phát sinh bên ngoài phạm vi advisor hoặc bị type-filter | Kiểm tra `@Order` và kiểu bind |
| `@AfterThrowing` không bắt lỗi từ một `@AfterReturning` khác | Không phải generic catch cho companion advice | Dùng outer `@Around` nếu cần quan sát continuation |
| Outer `@Around` bắt TargetFailure mà caller thấy ServiceException | Inner advice dịch lỗi | Giữ cause và log exception chain |
| Caller nhận success dù target lỗi | Inner around trả fallback | Tách proxy outcome khỏi target outcome |
| Lỗi audit che business failure | Audit advice ném exception thứ cấp | Chính sách priority, cause/suppressed |
| Exception type khác khi JDK proxy được dùng | Undeclared checked exception wrapping | Sửa contract và kiểm tra cause |
| Advisor chạy sai thứ tự sau refactor | `@Order` không rõ hoặc trùng | Cấu hình precedence và integration test |
| Không thấy advice trong self-call | `this.method()` bypass proxy | Refactor sang Spring bean dependency |
| Logging aspect lặp khi gọi recorder | Recorder cũng match pointcut | Loại technical collaborator |

## 16. Các bài test cần có

Với demo mục 6:

- **OK:** có dòng `TARGET enter OK`, `AFTER_RETURNING OK` và caller nhận `done:OK`.
- **TARGET:** có target entry, `AFTER_THROWING TargetFailure` và caller catch `TargetFailure`.
- **BEFORE:** có `BEFORE enter BEFORE` nhưng **không** có `TARGET enter BEFORE`.
- **AFTER:** có `TARGET enter AFTER`, `AFTER_RETURNING AFTER` nhưng caller catch `AfterFailure`.
- Outer around ghi nhận cả ba exceptions.
- `TargetFailureAspect` không log `BeforeFailure` hoặc `AfterFailure` trong ordering của demo.
- Nếu đổi order hoặc thêm advisors, expected events cần được đánh giá lại theo chain mới.

Một kiểm tra bằng code fragment:

~~~java
try {
    jobs.execute("BEFORE");
    throw new AssertionError("Should fail in before advice");
} catch (Failures.BeforeFailure expected) {
    // Use a spy/counter to assert that target was not invoked.
}
~~~

Đây là test fragment, chưa phải class độc lập. Đừng chỉ assert type của exception rồi suy rằng target chắc chắn không chạy; instrument target bằng counter/spy trong integration test để có bằng chứng.

## 17. Câu hỏi tự đánh giá

**1. Outer `@Around` catch một RuntimeException có chứng minh target ném không?**

Không. Inner before/after-returning/transaction advisor cũng có thể ném.

**2. `@AfterThrowing` có phải generic catcher cho mọi advice không?**

Không. Spring mô tả nó cho exception của method execution và lưu ý nó không phải callback tổng quát cho lỗi từ companion after/after-returning advice.

**3. Nếu `@Before` throw trước target, target có chạy không?**

Không qua invocation đang bị chặn đó.

**4. Target return bình thường nhưng `@AfterReturning` throw thì proxy trả gì?**

Proxy có thể trả exception của advice, dù target không ném exception.

**5. `@AfterThrowing` return void có nuốt lỗi target không?**

Không. Lỗi tiếp tục lan truyền nếu không được outer layer xử lý.

**6. Khi muốn catch, wrap, retry hoặc fallback, dùng advice nào?**

`@Around`, với `proceed()` và error-handling policy rõ ràng.

**7. Tại sao TargetFailureAspect trong ví dụ chỉ thấy lỗi target?**

Vì `@Order(30)` đặt nó bên trong before/after-returning aspects: lỗi BEFORE xảy ra trước khi đến nó, lỗi AFTER xảy ra sau khi nó hoàn tất bình thường.

**8. Transaction commit lỗi sau khi target return có phải target-body exception?**

Không. Đó là exception ở transaction interceptor/commit boundary.

**9. Vì sao exception cause quan trọng?**

Advice có thể wrap lỗi; cause giữ thông tin về failure ban đầu.

**10. Vì sao không dùng tên exception để xác định nguồn mọi lúc?**

Cùng type có thể được nhiều layer ném, hoặc exception có thể bị dịch/wrap.

## 18. Tài liệu Spring Framework chính thức

- **Spring Framework — Declaring Advice, After Throwing và Ordering:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html
- **Spring Framework — AOP Concepts:** https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- **Spring Framework — Advice API:** https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html
- **Spring Framework — Proxying Mechanisms:** https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework — @AspectJ Support:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- **Spring Framework — Declarative Transaction Management:** https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html

**Kết luận:** Một exception đi ra khỏi **Spring AOP proxy** không nhất thiết đến từ **method đích**. `@Before` có thể chặn trước target; `@AfterReturning` có thể thất bại sau target; `@Around` có thể quan sát, dịch, nuốt hoặc thay exception; transaction và các advisors khác cũng tham gia. Muốn phân loại đúng, hãy **đặt observer ở boundary thích hợp, kiểm soát `@Order`, ghi dấu target execution và bảo toàn exception cause** thay vì suy luận từ một catch hoặc một dòng log.
