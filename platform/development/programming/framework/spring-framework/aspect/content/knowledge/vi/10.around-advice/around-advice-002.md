# proceed() để tiếp tục chuỗi interceptor và phương thức đích trong Spring AOP

## 1. Vấn đề cốt lõi

Trong **Spring AOP proxy-based**, `@Around` advice có quyền chạy mã trước và sau một lời gọi phương thức được pointcut chọn, đồng thời quyết định **có tiếp tục đường gọi ấy hay không**. Điểm quyết định quan trọng nhất chính là:

~~~java
Object result = pjp.proceed();
~~~

Trong đoạn này, `pjp` là `org.aspectj.lang.ProceedingJoinPoint`, do Spring chuyển vào phương thức advice. `proceed()` **chuyển điều khiển tới phần còn lại của chuỗi Spring AOP interceptor/advice**, và cuối chuỗi sẽ tới method thực của target **nếu không có một interceptor phía trong chủ động trả về hoặc ném lỗi trước đó**.

Đặc biệt, không nên hiểu `proceed()` là một lệnh đơn giản tương đương `target.method()`:

- Nó đi qua **những advisor/interceptor còn lại** có liên quan tới invocation hiện tại.
- Một interceptor phía trong có thể ghi log, bắt đầu transaction, cache hit, chặn lời gọi hoặc ném exception.
- Chỉ khi chuỗi bên trong chuyển tiếp tới cuối thì method target mới thật sự được gọi.
- Giá trị trả về và exception đi ngược từ chuỗi phía trong về `@Around`, rồi cuối cùng tới caller, trừ khi advice ngoài thay đổi chúng.
- `proceed()` có thể được gọi **một lần, nhiều lần hoặc không lần nào** về mặt API; lựa chọn này thay đổi hành vi nghiệp vụ rất đáng kể.

**Phạm vi bài học:** chỉ tập trung vào `@Around` và chuỗi Spring Aspect/Spring AOP trên Spring-managed beans; không lặp lại kiến thức Aspect tổng quát hay giải thích AspectJ bytecode weaving như một cơ chế tương đương.

## 2. Ranh giới của một lời gọi Spring AOP

Sơ đồ minh họa một bean `GreetingService` được hai advisor can thiệp:

~~~text
Caller
   |
   v
Spring AOP proxy
   |
   +--> Outer @Around advice
   |      |
   |      +--> trước proceed()
   |      |
   |      +--> pjp.proceed()
   |                |
   |                +--> Inner @Before advice
   |                |
   |                +--> Advisor/interceptor khác, nếu có
   |                |
   |                +--> target.greet(...)
   |                |
   |                +--> trả result hoặc ném Throwable
   |      |
   |      +--> sau proceed() / catch / finally
   |
   v
Caller nhận result hoặc Throwable
~~~

Lúc Spring chuẩn bị bean, auto-proxy creator tìm **advisor phù hợp** dựa trên `@Aspect` beans, pointcut và type/method. Khi client gọi method **qua proxy**, Spring triển khai interceptor chain cho invocation đó. Thứ tự các advisors có thể ảnh hưởng ai nằm ngoài, ai nằm trong.

Tại `pjp.proceed()`:

1. Chuỗi xử lý tiến tới advisor kế tiếp có thể áp dụng.
2. Nếu advisor kế tiếp là `@Before`, logic của nó chạy trước khi chuyển tiếp.
3. Nếu một `@Around` bên trong **không gọi proceed**, lời gọi có thể dừng tại đây mà target không chạy.
4. Khi không còn interceptor nào, Spring gọi method đích trên target.
5. Kết quả hoặc exception quay về qua các interceptor đã đi vào.

Vì vậy nên nói **“proceed tiếp tục chuỗi interceptor hướng tới target”**, không nói “proceed chắc chắn gọi trực tiếp target ngay lập tức”.

## 3. Một @Around advice đúng cấu trúc

Ví dụ trong một Spring-managed `@Aspect`:

~~~java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TimingAspect {

    @Around("execution(* example.GreetingService.greet(..))")
    public Object aroundGreet(ProceedingJoinPoint pjp) throws Throwable {
        long start = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            long elapsed = System.nanoTime() - start;
            System.out.println("duration nanos: " + elapsed);
        }
    }
}
~~~

Điểm cần hiểu:

- `@Around` khai báo pointcut để Spring biết **lời gọi nào được bao quanh**.
- Tham số **đầu tiên** của around advice phải là `ProceedingJoinPoint`.
- Kiểu trả về `Object` cho phép advice truyền hoặc biến đổi return value. Với method target có giá trị trả về, không nên khai báo around advice trả về `void` vì Spring có thể trả `null` cho caller.
- `throws Throwable` cho phép exception từ method/advisor bên trong tiếp tục truyền ra ngoài; tránh bắt rồi nuốt lỗi vô ý.
- `pjp.proceed()` là điểm đi vào chuỗi phía trong.
- `finally` vẫn chạy khi chuỗi phía trong trả về hoặc ném exception, miễn là invocation đã đi vào advice này.
- Biến `start` là biến cục bộ **theo từng invocation**, không bị nhiều thread ghi đè như một field mutable chung trên singleton aspect.

Đây là **snippet minh họa**, chưa phải toàn bộ project độc lập; project đầy đủ ở mục 6 sẽ cho stdout xác định được.

## 4. So sánh “có proceed” và “không proceed”

### 4.1. Có `proceed()`

~~~java
@Around("execution(* example.GreetingService.greet(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("before");
    Object value = pjp.proceed();
    System.out.println("after");
    return value;
}
~~~

Với một target `greet()` trả về bình thường, chuỗi log thường có dạng:

~~~text
before
<advice phía trong, nếu có>
<method target>
after
~~~

Đoạn “after” sau `proceed()` **không chạy nếu `proceed()` ném exception**, trừ khi bạn xử lý riêng qua `catch` hoặc `finally`.

### 4.2. Không gọi `proceed()`

~~~java
@Around("execution(* example.GreetingService.cached(..))")
public Object cachedValue(ProceedingJoinPoint pjp) {
    return "CACHED";
}
~~~

Nếu advice này được gọi và trả về `"CACHED"` mà **không proceed**:

- Caller nhận giá trị do advice tạo ra.
- Các interceptor/advice **ở phía trong** chưa được gọi qua lần invocation này.
- Method target **không được gọi** trong đường đi đó.
- Đây có thể là hành vi **có chủ đích** của cache hit, policy chặn lời gọi hoặc mock/test interception.
- Nếu bỏ quên `proceed()` do lỗi lập trình, nghiệp vụ có thể bị “biến mất” một cách rất khó nhận diện.

**Không nhầm**: nếu một outer advice đã chạy, logic “after/finally” của chính outer vẫn có thể chạy dù nó shortcut. Câu “mọi advice bị bỏ qua” là sai; chỉ những tầng không được chuyển tiếp tới mới không chạy.

### 4.3. Có `proceed()` nhưng không trả lại kết quả

~~~java
// Cách viết này không phù hợp với method có return value:
@Around("execution(* example.GreetingService.greet(..))")
public Object incorrect(ProceedingJoinPoint pjp) throws Throwable {
    pjp.proceed();
    return null;
}
~~~

Method target **có thể đã chạy thành công**, nhưng caller nhìn thấy `null` thay vì kết quả thật. Nếu return type bên ngoài là primitive, việc Spring cố chuyển `null` về primitive có thể gây lỗi. Mặc định nên dùng `return pjp.proceed();`, trừ khi **cố ý** biến đổi hoặc thay thế kết quả theo hợp đồng rõ ràng.

## 5. Giá trị trả về và exception đi qua proceed()

### 5.1. Trả về bình thường

~~~java
Object result = pjp.proceed();
return result;
~~~

Giá trị từ các tầng phía trong được truyền về caller. Một around advice cũng có thể làm hậu xử lý:

~~~java
Object result = pjp.proceed();
return ((String) result).trim();
~~~

Đoạn trên **chỉ an toàn** khi pointcut thực sự giới hạn vào method trả `String` không null và việc trim nằm trong hợp đồng nghiệp vụ. Không cast/trimming một cách mù quáng trên pointcut chọn mọi method.

### 5.2. Target hoặc interceptor phía trong ném exception

~~~java
@Around("execution(* example.GreetingService.fail(..))")
public Object traceFailure(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("before");
    try {
        return pjp.proceed();
    } finally {
        System.out.println("finally");
    }
}
~~~

Nếu `fail()` ném `IllegalStateException`, khối `finally` chạy rồi exception tiếp tục đi tới caller. Có thể bắt exception để log:

~~~java
try {
    return pjp.proceed();
} catch (Throwable failure) {
    System.out.println("failed: " + failure.getClass().getSimpleName());
    throw failure; // Giữ nguyên hành vi lan truyền lỗi.
}
~~~

**Không nên** thay exception bằng kết quả thành công trong một advice dùng chung nếu không có chính sách nghiệp vụ cụ thể. Việc nuốt lỗi có thể phá vỡ transaction rollback, retry policy, HTTP error mapping hoặc các cơ chế infrastructure khác.

### 5.3. Thứ tự xử lý khi xảy ra lỗi

Nếu có outer `@Around` và inner `@Before`:

- Outer có thể đã in “before”.
- Inner `@Before` chạy khi outer `proceed()`.
- Target ném exception.
- Không có log “after” đặt ngay sau `proceed()` nếu không xử lý exception.
- Outer `finally` vẫn chạy.
- Caller nhận exception nếu outer không chuyển đổi nó.

Nếu **inner advice ném exception trước khi target chạy**, outer `finally` vẫn có thể thực thi, nhưng target method **không được gọi**. Không lấy sự xuất hiện của outer finally làm bằng chứng target đã thực thi.

## 6. Ví dụ Java 17+ chạy được: bốn trường hợp của proceed()

Đây là project Maven độc lập để kiểm tra thực tế:

- `GreetingService` là Spring bean.
- `FlowAspect`: outer `@Around`, cố ý dùng `@Order(1)`.
- `TraceAspect`: inner `@Before`, dùng `@Order(2)` để bảo đảm thứ tự **giữa hai aspect khác nhau**.
- `greet(String)`: outer gọi `proceed(Object[])` với đối số đã biến đổi.
- `cached()`: outer **không proceed**, trả về kết quả shortcut.
- `fail()`: `proceed()` đưa lời gọi đến target ném exception; outer `finally` vẫn chạy.
- `callInternally()`: outer proceed cho method ngoài; method target gọi `this.greet(...)` nên invocation bên trong **không đi lại qua Spring proxy**.

Sử dụng **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1** và **Java 17+**. Không cần database, web server hay Spring Boot.

### 6.1. Cấu trúc thư mục

~~~text
spring-around-proceed-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── GreetingService.java
    ├── FlowAspect.java
    ├── TraceAspect.java
    └── Main.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-around-proceed-demo</artifactId>
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

Spring Framework BOM quản lý các phiên bản module Spring nhất quán; AspectJ Weaver phục vụ phân tích biểu thức `@AspectJ` trong Spring AOP. Sự hiện diện của `aspectjweaver` **không tự bật AspectJ bytecode weaving**.

### 6.3. `GreetingService.java` — đối tượng nghiệp vụ

~~~java
package example;

public class GreetingService {

    public String greet(String name) {
        System.out.println("target: greet " + name);
        return "Hello " + name;
    }

    public String cached() {
        System.out.println("target: cached");
        return "FRESH";
    }

    public String fail() {
        System.out.println("target: fail");
        throw new IllegalStateException("boom");
    }

    public String callInternally() {
        System.out.println("target: callInternally");
        return this.greet("Self");
    }
}
~~~

Method `cached()` **có code thật** để kiểm tra rằng target không được gọi khi shortcut. Với `callInternally()`, lời gọi `this.greet("Self")` sẽ giúp nhận diện self-invocation đã vượt ngoài đường gọi qua AOP proxy.

### 6.4. `FlowAspect.java` — outer around advice

~~~java
package example;

import java.util.Locale;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(1)
public class FlowAspect {

    @Around("execution(* example.GreetingService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("outer: before " + method);

        try {
            if ("cached".equals(method)) {
                System.out.println("outer: shortcut");
                return "CACHED"; // Không proceed: inner/target không chạy.
            }

            Object result;
            if ("greet".equals(method)) {
                Object[] args = pjp.getArgs().clone();
                args[0] = ((String) args[0]).toUpperCase(Locale.ROOT);
                result = pjp.proceed(args);
            } else {
                result = pjp.proceed();
            }

            System.out.println("outer: after " + method);
            return result;
        } finally {
            System.out.println("outer: finally " + method);
        }
    }
}
~~~

**Điểm học chính:**

- Với `greet`, advice tạo một **bản sao** array arguments, sửa argument đầu và gọi `pjp.proceed(args)`. Trong **Spring AOP**, mảng truyền vào phải tương ứng với các **tham số của method đích**.
- Với `cached`, advice trả `CACHED`, không có `proceed`. `finally` của chính outer vẫn chạy theo quy tắc Java.
- Với `fail` và `callInternally`, `pjp.proceed()` không đối số giữ nguyên arguments của caller.
- Dòng `outer: after` chỉ chạy khi `proceed` trả về bình thường; dòng `outer: finally` chạy cả khi target/advisor bên trong ném exception.
- `@Order(1)` đặt aspect này **ngoài** aspect `@Order(2)` trong đường đi vào của cùng join point.

**Giới hạn minh họa:** Chương trình intentionally dựa vào tên method để chọn branch cho dễ nhìn stdout. Trong mã production, nên đặt pointcut hẹp/annotation/bean scope và tách advice theo hợp đồng method, không đặt một switch lớn trên tên mọi method của service.

### 6.5. `TraceAspect.java` — advisor phía trong

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;

@Aspect
@Order(2)
public class TraceAspect {

    @Before("execution(* example.GreetingService.*(..))")
    public void before(JoinPoint jp) {
        System.out.println("inner: before "
            + jp.getSignature().getName());
    }
}
~~~

Aspect này giúp chứng minh `proceed()` **không gọi thẳng vào target**. Đường đi bình thường sẽ thấy `inner: before ...` **sau** `outer: before ...` và **trước** dòng `target: ...`.

Nếu outer quyết định shortcut thì inner advice không được gọi cho invocation ấy. Không có mặc định rằng tất cả advisors luôn thực thi.

### 6.6. `AppConfig.java` — đăng ký Spring beans

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }

    @Bean
    public FlowAspect flowAspect() {
        return new FlowAspect();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
~~~

Cả hai lớp `@Aspect` được **đăng ký Spring beans bằng `@Bean`**, vì vậy không cần thêm `@Component`. Spring AOP phát hiện advice và tạo proxy cho `GreetingService` vì pointcut phù hợp.

`proxyTargetClass = true` khiến ví dụ dùng class-based proxy để có thể lấy service trực tiếp bằng `GreetingService.class`. Dù dùng JDK hay CGLIB, **cách `proceed` chuyển tiếp chuỗi advisor vẫn theo nguyên tắc Spring AOP proxy-based**.

### 6.7. `Main.java` — gọi bốn trường hợp

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            GreetingService service = context.getBean(GreetingService.class);

            System.out.println("proxy: " + AopUtils.isAopProxy(service));

            System.out.println("-- greet with modified argument --");
            System.out.println("caller: " + service.greet("An"));

            System.out.println("-- shortcut --");
            System.out.println("caller: " + service.cached());

            System.out.println("-- exception --");
            try {
                service.fail();
            } catch (IllegalStateException failure) {
                System.out.println("caller caught: " + failure.getMessage());
            }

            System.out.println("-- self invocation --");
            System.out.println("caller: " + service.callInternally());
        }
    }
}
~~~

Tại thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 6.8. Stdout mong đợi của chương trình

Các dòng in bởi chính những class trong project, theo đúng thứ tự:

~~~text
proxy: true
-- greet with modified argument --
outer: before greet
inner: before greet
target: greet AN
outer: after greet
outer: finally greet
caller: Hello AN
-- shortcut --
outer: before cached
outer: shortcut
outer: finally cached
caller: CACHED
-- exception --
outer: before fail
inner: before fail
target: fail
outer: finally fail
caller caught: boom
-- self invocation --
outer: before callInternally
inner: before callInternally
target: callInternally
target: greet Self
outer: after callInternally
outer: finally callInternally
caller: Hello Self
~~~

Maven/Spring có thể xuất thêm log của môi trường; đoạn trên chỉ bao gồm các `System.out.println` của ví dụ.

### 6.9. Giải thích lần lượt

**Greet, có proceed(Object[]):**

1. Outer in `outer: before greet`.
2. Outer đổi argument `"An"` thành `"AN"` và gọi `pjp.proceed(args)`.
3. Spring chạy inner `@Before` rồi target `greet("AN")`.
4. Method trả `"Hello AN"`, đi về outer.
5. Outer in `after`, rồi `finally`, sau đó caller nhận `Hello AN`.

Đây là bằng chứng trực tiếp rằng `proceed` đã chuyển qua **advisor khác rồi mới tới target**, không chỉ gọi target ngay lập tức.

**Cached, không proceed:**

- Outer nhận invocation rồi trả `CACHED`.
- Không có `inner: before cached` hoặc `target: cached`.
- `finally` của outer vẫn chạy trước khi caller thấy kết quả.
- Đây là **short-circuit có chủ đích**, không phải lỗi Spring quên gọi target.

**Fail, exception:**

- Outer gọi `proceed()`, inner chạy, target in `target: fail` rồi ném `IllegalStateException("boom")`.
- Dòng `outer: after fail` **không xuất hiện** vì `proceed` không trả bình thường.
- `outer: finally fail` vẫn xuất hiện.
- Caller bắt exception và in `caller caught: boom`; advice không nuốt lỗi.

**CallInternally, self-invocation:**

- Caller gọi `callInternally()` qua proxy, nên outer và inner chạy cho **method ngoài này**.
- Trong target, `this.greet("Self")` là lời gọi nội bộ; nó **không quay lên AOP proxy**.
- Vì thế không có `outer: before greet`, không có `inner: before greet`, và đối số vẫn là `Self` (không bị upper-case).
- Kết quả `Hello Self` minh họa ranh giới proxy; việc outer từng gọi `proceed()` **không biến các self-call sau đó thành các invocation qua proxy**.

## 7. proceed() và proceed(Object[]) khác nhau ra sao?

Theo tài liệu Spring Framework:

| API | Đối số truyền tiếp | Ứng dụng |
| --- | --- | --- |
| `pjp.proceed()` | Dùng arguments gốc của invocation đang được advice | Tiếp tục bình thường mà không can thiệp tham số |
| `pjp.proceed(new Object[] { ... })` | Trong Spring AOP, dùng các phần tử của mảng làm **method arguments** của phần invocation được chuyển tiếp | Normalize input, điều chỉnh tham số có kiểm soát |
| Không gọi proceed | Không gửi invocation tới chain phía trong | Cache hit, access denial, fallback có chủ đích |
| Gọi proceed nhiều lần | Chạy lại phần chain phía trong nhiều lần nếu cấu hình cho phép | Retry, nhưng dễ nhân đôi side effects |

**Điều kiện của `proceed(Object[])`:**

1. Mảng phải có số phần tử **phù hợp với số method parameters** tại join point; ví dụ target `greet(String)` cần đúng một phần tử.
2. Các phần tử phải có kiểu tương thích; `greet(String)` không thể nhận một `Integer` tùy ý.
3. Không dùng `pjp.getArgs()` rồi sửa trực tiếp nếu mục đích chỉ là biến đổi cục bộ và bạn không muốn gây side effect lên array tham số đang được các interceptor khác quan sát. Trong ví dụ dùng `clone()`.
4. Nếu pointcut match nhiều method có chữ ký khác nhau, việc tự sửa phần tử `args[0]` có thể ném `ArrayIndexOutOfBoundsException` hoặc `ClassCastException`. Hãy giới hạn pointcut và kiểm tra chữ ký rõ ràng.
5. Khi method nhận primitive parameter, mảng `Object[]` chứa các wrapper values phù hợp như `Integer` cho `int`; không truyền null cho primitive.
6. Việc thay args có thể thay đổi dữ liệu nhìn thấy bởi các interceptor phía trong; nên áp dụng chỉ khi business contract cho phép.

**Khác biệt cần nhớ giữa Spring AOP và AspectJ compiler/weaver:** Với Spring AOP proxy-based, mảng `proceed(Object[])` tương ứng với **arguments của method phía dưới**. Với một số dạng around advice được biên dịch bằng AspectJ truyền thống, ngữ nghĩa binding/thay thế vị trí có thể khác. Đừng sao chép code `proceed(args)` từ cơ chế weaving khác mà không đọc hướng dẫn tương thích của Spring Framework. Bài này chỉ sử dụng **Spring AOP**.

## 8. “Tiếp tục chuỗi” chứ không nhất thiết tới target

Xem đường đi:

~~~text
Outer @Around
   |
   | proceed()
   v
Inner @Around
   |
   +-- cache hit --> return cached value
   |
   +-- cache miss --> proceed()
                        |
                        v
                    Inner @Before
                        |
                        v
                   Target method
~~~

Nếu cache hit ở inner:

- Outer **đã gọi `proceed()`**.
- Inner đã nhận lời gọi và quyết định return sớm.
- Target không được gọi.
- Outer vẫn có thể nhận giá trị và in log `after`.

Do đó khẳng định “outer đã gọi proceed nên target chắc chắn chạy” là **sai**.

Ngược lại, nếu inner `@Before` ném exception, outer `proceed()` cũng ném ra ngoài, nhưng target chưa được gọi. Cần debug **từng tầng**, không chỉ kiểm tra một lệnh proceed trong source.

Một bean còn có thể chịu infrastructure advisors phục vụ transaction, caching, security hoặc tracing. Thứ tự thực tế cần được kiểm tra từ Spring context/proxy advisor chain; **không giả định tất cả advisor đều đến từ @Aspect người dùng viết**.

## 9. Có thể gọi proceed nhiều lần không?

Spring Framework documentation nêu rõ around advice có thể gọi `proceed()` **không lần nào, một lần hoặc nhiều lần**. Điều này hợp lệ về mặt API, nhưng mỗi lần proceed có thể kích hoạt lại **cả phần chuỗi phía trong**.

Ví dụ **snippet minh họa**, không thuộc project chạy độc lập ở mục 6:

~~~java
@Around("execution(* example.PaymentService.send(..))")
public Object retryOnce(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (TransientOperationException ex) {
        return pjp.proceed();
    }
}
~~~

Đoạn trên giả định `TransientOperationException` và `PaymentService` tồn tại. Nó minh họa điều gì?

- Nếu lần đầu fail, lần thứ hai có thể chạy lại **inner interceptors và target**.
- Nếu operation có side effects như tạo đơn hàng, trừ tiền, gửi email hoặc publish message, lặp lại invocation có thể gây **thực thi hai lần**.
- Nếu các interceptor có transaction boundary, retry nằm **ngoài hoặc trong** transaction interceptor có thể mang ngữ nghĩa rất khác.
- Không phải mọi exception là transient; lọc đúng lỗi và quy định số lần retry, delay/backoff, idempotency, observability.
- Một `@Around` chứa retry thiếu kiểm soát có thể nguy hiểm hơn nhiều so với dùng Spring Retry/Resilience infrastructure được cấu hình đúng.

**Không dùng code mẫu này nguyên xi trong production**. Không nên dùng while vô hạn hoặc gọi proceed lặp lại chỉ để “chắc chắn method chạy”. Những nghiệp vụ không idempotent phải thiết kế retry cẩn trọng, không dựa duy nhất vào cú pháp của AOP.

## 10. Thứ tự advisor và @Order

Khi nhiều advice ở các aspect khác nhau cùng match một method, Spring có các quy tắc precedence. Trong ví dụ:

~~~java
@Aspect
@Order(1)
public class FlowAspect { /* outer @Around */ }

@Aspect
@Order(2)
public class TraceAspect { /* inner @Before */ }
~~~

Với @Order:

- **Số nhỏ hơn** có precedence cao hơn.
- Aspect precedence cao hơn thường chạy **trước khi đi vào join point**, và **sau khi đi ra**.
- Vì vậy outer around ghi `before` trước inner before; outer after/finally chạy khi chuỗi phía trong đã trả về hoặc ném lỗi.

Nếu không quy định order giữa hai aspects, không nên cam kết stdout cố định cho các log tương ứng. Với nhiều advice cùng loại trong cùng một aspect, Java reflection không bảo đảm giữ thứ tự khai báo method; không dùng thứ tự code nguồn để suy ra thứ tự runtime.

### 10.1. Thay @Order có làm proceed gọi target khác đi không?

`@Order` chủ yếu ảnh hưởng **vị trí tương đối của advisor/aspect trong chuỗi**, không thay pointcut và không sửa target bean. Nhưng điều này có thể thay đổi việc một shortcut xảy ra **trước hay sau** các infrastructure advisors.

Ví dụ với transaction/caching, thứ tự advisor có thể ảnh hưởng việc around advice chạy bên trong hay bên ngoài transaction; từ đó exception/rollback/commit có thể được quan sát ở những thời điểm khác nhau. Không thay toàn bộ ordering trong ứng dụng chỉ vì muốn log in theo thứ tự đẹp. Hãy kiểm thử ngữ nghĩa nghiệp vụ khi điều chỉnh precedence.

## 11. Khi nào nên dùng @Around thay vì advice đơn giản hơn?

Spring Framework khuyến nghị **chọn loại advice ít quyền lực nhất đáp ứng yêu cầu**.

| Nhu cầu | Advice nên cân nhắc | Lý do |
| --- | --- | --- |
| Ghi log trước khi method chạy | `@Before` | Không cần chủ động gọi proceed |
| Xử lý kết quả thành công | `@AfterReturning` | Chỉ nhận nhánh normal return |
| Theo dõi exception thoát ra | `@AfterThrowing` | Chỉ nhận nhánh exceptional exit |
| Dọn dẹp khi method kết thúc cả hai nhánh | `@After` | Finally semantics không cần thao tác proceed |
| Đo thời gian bằng biến start/end cục bộ cùng invocation | **`@Around`** | Dùng proceed và try/finally với state riêng |
| Có cache hit/shortcut chủ đích | **`@Around`** | Có quyền bỏ qua proceed và trả kết quả thay thế |
| Thay đối số trước khi gọi method | **`@Around`** | Có `proceed(Object[])` |
| Retry có chính sách và idempotency | `@Around` hoặc hạ tầng chuyên dụng | Mỗi proceed có thể chạy lại chuỗi phía trong |
| Chỉ thay message log | Thường `@Before` hoặc `@After` | Không cần xâm nhập return/throw path |

Không phải mọi advice logging đều cần @Around. Việc quên proceed trong một @Around logging có thể **ngăn thực thi nghiệp vụ** — rủi ro mà @Before đơn giản không tạo ra theo cách này.

## 12. Điểm lưu ý với method trả về void, primitive, Future

### 12.1. Method trả về void

Với method target `void doWork()`, thông thường `pjp.proceed()` trả về `null` ở dạng Object; advice khai báo `Object` rồi `return pjp.proceed();` vẫn là cấu trúc phù hợp. Không tùy tiện biến thành `void` around advice khi cùng pointcut còn match method có return value.

### 12.2. Method trả về primitive

Nếu target trả `int`, giá trị đi qua advice là đối tượng wrapper thích hợp (ví dụ `Integer`) ở mức giao diện `Object`. Nếu advice return null cho primitive return type, caller/proxy có thể ném exception vì không thể unbox null. Nếu shortcut, giá trị thay thế phải có kiểu tương thích với method.

### 12.3. Method trả CompletableFuture hoặc Publisher

Giả sử method trả một `CompletableFuture<T>` hoặc `Mono<T>`. `pjp.proceed()` có thể trả **đối tượng đại diện cho công việc** trước khi công việc phía trong thật sự hoàn tất.

- Around advice đo thời gian từ trước proceed đến sau proceed có thể chỉ đo **thời gian tạo/trả Future/Publisher**, không phải toàn bộ latency nghiệp vụ.
- Lỗi từ asynchronous computation có thể xuất hiện khi future hoàn thành hoặc khi stream được subscribe, không nhất thiết bị catch bởi `try/catch` xung quanh chính `pjp.proceed()`.
- Khi cần metrics hoặc cleanup gắn với completion, dùng callback/operator đúng cho abstraction trả về, hoặc sử dụng Spring integration phù hợp.
- Không gọi proceed nhiều lần chỉ để “chờ kết quả” của future.

Bài này không mở rộng sang cấu hình Reactive/Async, chỉ nhấn mạnh rằng **Spring AOP proceed ở method execution boundary** không đồng nghĩa bảo đảm công việc bất đồng bộ đã kết thúc.

## 13. Proxy boundary và self-invocation

Ngay cả khi outer advice gọi `proceed()`, những lời gọi nội bộ của target bằng `this.innerMethod()` vẫn **không quay lại proxy**.

~~~java
public String callInternally() {
    return this.greet("Self");
}
~~~

Trong project mục 6, `callInternally()` được advice vì client gọi nó **qua proxy**, nhưng lệnh `this.greet("Self")` là lời gọi Java trực tiếp trong target. Do đó:

- Không có thêm một `FlowAspect.around` mới cho `greet` nội bộ.
- Không có `TraceAspect.before` cho `greet` nội bộ.
- Đối số `"Self"` không bị upper-case như khi gọi `service.greet("An")` trực tiếp từ bên ngoài proxy.

Cách khắc phục thông dụng là tách method cần Spring advice thành **Spring bean khác** và gọi qua tham chiếu bean được dependency injection cung cấp. Không dùng `new Bean()` rồi chờ advisor tự xuất hiện. Sử dụng `AopContext.currentProxy()` hoặc self-injection chỉ khi thật sự hiểu coupling và cấu hình proxy, không coi đó là mặc định.

Spring AOP hỗ trợ cả JDK dynamic proxy và CGLIB class-based proxy. **Chuyển chiến lược JDK ↔ CGLIB không tự sửa self-invocation**.

## 14. proceed() trong @Around và invocation.proceed() cấp thấp

Ngoài `@Aspect` style, Spring AOP còn cung cấp `org.aopalliance.intercept.MethodInterceptor`:

~~~java
// Snippet minh họa bên trong class Implements MethodInterceptor.
@Override
public Object invoke(MethodInvocation invocation) throws Throwable {
    System.out.println("interceptor: before");
    Object value = invocation.proceed();
    System.out.println("interceptor: after");
    return value;
}
~~~

Hai đường dùng khác nhau:

| Dạng Spring AOP | Tham số nhận | Lệnh chuyển tiếp | Điển hình |
| --- | --- | --- | --- |
| Annotation `@Around` trên Spring-managed `@Aspect` | `ProceedingJoinPoint` | `pjp.proceed()` / `pjp.proceed(Object[])` | AOP annotations, dùng pointcut expression |
| Spring AOP programmatic/Advisor infrastructure | `MethodInvocation` | `invocation.proceed()` | `ProxyFactory`, custom MethodInterceptor, infrastructure advice |

Chúng cùng ý tưởng chuyển tiếp chuỗi nhưng **không cùng kiểu API**. Đừng lẫn `ProceedingJoinPoint` và `MethodInvocation` khi viết signature advice. Ví dụ MethodInterceptor ở trên **không phải file Java độc lập**; cần implements interface, imports và đăng ký vào Spring AOP proxy qua `ProxyFactory`, advisor hoặc hạ tầng liên quan.

Một invocation có thể đi qua cả interceptor cấp thấp do framework đăng ký **và** advice khai báo bằng `@Aspect`. Vì vậy kết luận “proceed chỉ gọi advice do tôi tự viết” là thiếu chính xác.

## 15. Chẩn đoán khi proceed() không tạo kết quả mong muốn

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| Có log “outer: before”, không có log target | Outer bỏ qua proceed hoặc một inner interceptor shortcut | Kiểm tra branch `return` và tầng interceptors phía trong |
| Target chạy, caller nhận null | Advice quên `return pjp.proceed()` hoặc cố ý return null | So khớp return contract, đặc biệt primitive |
| Target chạy hai lần | `proceed()` bị gọi nhiều lần hoặc retry layer | Theo dõi invocation count và tính idempotent |
| `outer: after` mất khi target ném lỗi | Code sau proceed không nằm trong finally | Đưa cleanup vào try/finally, giữ nguyên exception |
| `outer: finally` có nhưng không thấy target | Inner advisor ném exception trước target hoặc đã shortcut | Log từng tầng, đừng suy finally ⇒ target |
| Gọi trực tiếp service qua Spring proxy có log, `this.greet()` không có | Self-invocation | Tách sang bean khác và gọi qua DI |
| `proceed(args)` ném lỗi do kiểu | Mảng arguments sai số phần tử/kiểu | Giới hạn pointcut và kiểm tra method signature |
| Nhiều aspects cho stdout khác dự kiến | Chưa đặt precedence hoặc infrastructure advisor khác | Xem `@Order` / `Ordered` và actual proxy advisor chain |
| `@Around` không chạy | Aspect chưa là bean, AOP chưa bật, pointcut không match | Kiểm tra `@Aspect @Component` / `@Bean`, dependency, proxy |
| `AopUtils.isAopProxy(bean) == true` nhưng advice không chạy cho method cụ thể | Proxy có thể do advisor khác hoặc method không match | Kiểm tra eligible advisors và method-level matching |
| Cache hit khiến lời gọi không xuống target | Around shortcut đúng theo thiết kế | Phân biệt hợp đồng caching với lỗi thiếu proceed |
| Retry làm trùng transaction/message | Nhiều proceed chạy lại side-effect | Dùng retry policy, idempotency, transaction boundaries phù hợp |

### Checklist chẩn đoán

1. Lấy bean từ `ApplicationContext` hoặc constructor injection, không dùng instance `new` thay thế.
2. Kiểm tra `AopUtils.isAopProxy(bean)`, nhớ rằng boolean này **không đủ** để chứng minh mọi method bị advice.
3. Xác minh `@Aspect` class đã được đăng ký thành Spring bean và hỗ trợ `@AspectJ` đang bật.
4. Xem pointcut có match target class/method không.
5. Đặt log trước `proceed()`, trước target và sau `proceed()`; có branch return sớm không?
6. Nếu có nhiều advisors, xem thứ tự `@Order` và hạ tầng transaction/cache.
7. Nếu có exception, kiểm tra `catch`/`finally` và propagation tới caller.
8. Nếu gọi nhiều lần, đếm số proceed và số lần target thực thi.
9. Nếu thay args, so khớp argument count/type và dữ liệu mà inner interceptors nhìn thấy.
10. Kiểm thử success, shortcut, failure và self-invocation như ví dụ độc lập, không chỉ happy path.

## 16. Bài tập áp dụng

**Tình huống A:** Around advice in “before” rồi gọi `pjp.proceed()`; một inner cache advice trả giá trị cache và không proceed. Target method có chạy không?

**Đáp án:** Không ở lần gọi đó. Outer đã tiếp tục tới **inner interceptor**, nhưng inner chặn đường xuống target. Caller vẫn có thể nhận cached value.

**Tình huống B:** Target `sum(int,int)` trả primitive `int`; around advice gọi proceed nhưng trả `null`. Có đảm bảo caller nhận kết quả không?

**Đáp án:** Không. Null không tương thích với primitive return contract và có thể gây lỗi. Trả kết quả của proceed hoặc một value thay thế đúng kiểu.

**Tình huống C:** Một advice `@Around` gọi `proceed()` hai lần để “chắc chắc lưu thành công”. Có thể xảy ra tác động gì?

**Đáp án:** Target hoặc các inner advisors có thể chạy hai lần, gây duplicate writes/emails/transactions. Retry phải có chính sách và idempotency.

**Tình huống D:** Outer around đã in “before”, target ném exception. Code “after” nằm sau proceed không chạy. Làm sao bảo đảm một log cleanup vẫn xuất hiện?

**Đáp án:** Đặt cleanup trong `finally` bao quanh proceed. Nếu chỉ cần after-finally behavior, cân nhắc `@After` thay vì @Around.

**Tình huống E:** `pjp.proceed(new Object[]{"A"})` được gọi với method `greet(String)` trong Spring AOP. Target nhận argument nào?

**Đáp án:** Trong Spring AOP, method target phía dưới nhận `"A"` làm argument ở vị trí duy nhất. Mảng phải khớp signature của target.

**Tình huống F:** Một caller gọi `service.callInternally()` qua proxy. Trong target, nó gọi `this.greet("Self")`. Ngoài `callInternally`, có thêm một around invocation dành riêng cho `greet` không?

**Đáp án:** Không. Lời gọi nội bộ trên `this` không qua Spring proxy, nên không đi vào chuỗi advisor riêng cho `greet` lần nữa.

**Tình huống G:** Outer around shortcut nhưng vẫn in log “outer: finally”. Có mâu thuẫn không?

**Đáp án:** Không. `finally` thuộc chính outer advice đã chạy; những advisor phía trong và target mới là phần bị bỏ qua do không proceed.

**Tình huống H:** Một method trả CompletableFuture chưa hoàn tất, nhưng around advice đã in “after”. Có phải proceed đã chờ toàn bộ công việc chạy nền?

**Đáp án:** Không. Proceed có thể chỉ chờ method trả Future object. Hoàn tất async là một mốc khác, cần theo dõi bằng API completion phù hợp.

## 17. Nguồn tài liệu Spring chính thức

- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `ProceedingJoinPoint.proceed()`, return value, shortcut, proceed nhiều lần, `proceed(Object[])` và advice ordering.
- [Spring Framework — Spring AOP Advice API](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): `MethodInterceptor` và `MethodInvocation.proceed()` chuyển tiếp interceptor chain.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): ngữ nghĩa around advice và lời khuyên chọn loại advice ít quyền lực nhất.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB AOP proxies, self-invocation, giới hạn phương thức.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy` và đăng ký aspect bean.
- [Spring Framework — AspectJ Pointcuts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): Spring pointcut expression và phạm vi method execution.
