# @After với ngữ nghĩa finally trong Spring AOP

## 1. Kết quả học tập và phạm vi

Trong **Spring AOP dùng annotation kiểu @AspectJ**, `@After` định nghĩa **after (finally) advice**: advice chạy khi một **method execution khớp pointcut** kết thúc, bất kể method trả về thành công hay ném ngoại lệ ra ngoài. Đây là ngữ nghĩa *tương tự khối `finally` của Java* — một hook để dọn dẹp hoặc thực hiện công việc hậu xử lý cần xảy ra ở cả hai nhánh.

Ví dụ Spring Aspect:

~~~java
@Aspect
public class CleanupAspect {
    @After("execution(* example.TaskService.run*(..))")
    public void afterTask() {
        System.out.println("cleanup: method finished");
    }
}
~~~

Nếu `runOk()` trả về bình thường, lời advice vẫn chạy. Nếu `runFail()` ném exception, advice cũng chạy **khi lời gọi khớp thực sự đi qua Spring AOP proxy**. Bản thân `@After` không phân loại thành công/thất bại, không trả về kết quả thay method và cũng không phải một exception handler có chức năng tự chữa lỗi.

Sau bài, người học cần:

1. Mô tả chính xác khi nào `@After` được kích hoạt trên **Spring-managed target bean**.
2. Phân biệt `@After` với `@Before`, `@AfterReturning`, `@AfterThrowing` và `@Around` trong ứng dụng Spring.
3. Dự đoán kết quả của **thành công, exception thoát khỏi method và exception bị bắt ngay trong method**.
4. Sử dụng `JoinPoint` để log tên method mà không nhầm với việc lấy return value/exception.
5. Hiểu giới hạn Spring **proxy boundary**, thứ tự advice, các trường hợp advice tự ném exception hoặc method trả về giá trị bất đồng bộ.
6. Viết và chạy một dự án Maven/Java 17+ độc lập chứng minh ngữ nghĩa này.

**Special Note của module:** chỉ tập trung vào **Spring Aspect/Spring AOP**; kiến thức Aspect tổng quát nằm ở chủ đề khác. Các ví dụ có @Aspect dùng **Spring AOP proxy-based**, không cần cấu hình AspectJ compile-time hoặc load-time weaving.

## 2. Ngữ nghĩa `@After` theo tài liệu Spring Framework

Đọc một advice như sau:

~~~java
@After("execution(* example.TaskService.run*(..))")
public void afterCompletion(JoinPoint jp) {
    System.out.println("finished: " + jp.getSignature().getName());
}
~~~

Điều kiện đầu tiên là expression phải match **method execution** trên **target bean được Spring AOP can thiệp**. Điều kiện thứ hai là caller phải gọi method **qua Spring AOP proxy**, để interceptor/advisor tương ứng có thể được thực thi.

Nếu hai điều kiện thỏa, khi method execution **thoát theo một trong hai hướng**, advice chạy:

~~~text
Caller --> Spring AOP proxy --> target method
             |                    |
             |        return bình thường hoặc throw exception
             |                    |
             +--> @After advice <--+
             |
             +--> caller nhận kết quả hoặc exception
~~~

Hãy hiểu cụm "finally" chính xác:

- **Trả về thành công:** `@After` chạy sau khi target method hoàn tất, trước khi caller nhận kết quả từ đường gọi proxy.
- **Ném exception ra ngoài:** `@After` vẫn chạy trong quá trình stack unwinding của lời gọi đang được advice.
- **Bắt exception ngay bên trong method:** từ góc nhìn proxy, method có thể **trả về bình thường**; `@After` vẫn chạy, nhưng không thể tự suy ra rằng một exception đã từng xuất hiện và bị bắt trong target.
- **Method không được thực thi qua proxy:** không có lời gọi advisory phù hợp, nên `@After` của Spring AOP không được kích hoạt cho đường gọi đó.
- **Caller quyết định bắt exception hay không:** đây là bước nằm ngoài lời gọi advice; `@After` không tự thay hành vi lan truyền exception.

Spring documentation mô tả `@After` là after-finally advice, thường dùng cho releasing resources và các công việc tương tự. Không nên dùng nó như thay thế tổng quát cho mọi cơ chế vòng đời tài nguyên hoặc transaction.

## 3. So sánh các loại advice trên cùng một method

| Annotation | Khi nào chạy? | Có biết nhánh cụ thể không? | Vai trò phù hợp |
| --- | --- | --- | --- |
| `@Before` | Trước khi method execution phù hợp được chạy qua proxy | Chưa có kết quả hay exception của method | Kiểm tra/tracing trước khi gọi |
| `@AfterReturning` | Sau khi method execution **trả về bình thường** | Có thể bind return value bằng `returning` | Hậu xử lý cho nhánh thành công |
| `@AfterThrowing` | Khi method execution **ném exception thoát ra ngoài** | Có thể bind throwable bằng `throwing` | Ghi nhận thất bại theo loại exception |
| **`@After`** | **Sau method execution, cả return và throw** | Không tự nhận tham số `returning` hoặc `throwing` | Dọn dẹp/hậu xử lý cần luôn thực hiện |
| `@Around` | Bao quanh method execution nếu invocation đi vào advice | Chủ động gọi `proceed()`, có thể quan sát cả return/throw | Kiểm soát luồng, timing với state per-invocation, retry/short-circuit |

Hai điểm dễ nhầm:

1. **`@After` không phải tên viết ngắn của `@AfterReturning`.** Khi target ném exception, `@AfterReturning` không chạy, nhưng `@After` vẫn chạy.
2. **`@AfterThrowing` không tự nuốt exception.** Nó là callback ở nhánh thất bại của join point; việc log một exception không biến lời gọi thành return thành công.

Spring khuyến nghị chọn **loại advice ít quyền lực nhất đủ cho mục đích**. Nếu chỉ cần thực thi logic sau khi method hoàn tất theo cả hai hướng, `@After` rõ ràng hơn `@Around` chỉ để dựng `try/finally`. Ngược lại, nếu phải đo thời gian bằng biến `startTime` riêng cho mỗi invocation hoặc kiểm soát return/throw, `@Around` với `try/finally` có thể phù hợp hơn.

## 4. Spring AOP làm gì với `@After` lúc chạy?

Để advice trở thành một phần đường gọi, ứng dụng phải có đầy đủ:

1. **Một Spring-managed aspect bean:** class có `@Aspect` và được đăng ký bằng `@Component` trong package được scan, `@Bean` hoặc bean definition khác.
2. **Hỗ trợ Spring AOP đang bật:** trong Spring Framework thuần thường dùng `@EnableAspectJAutoProxy` và classpath gồm các dependency cần thiết.
3. **Một advisor/pointcut phù hợp:** Spring đọc metadata `@After` và xác định method execution nào cần được advice.
4. **Một target bean có proxy hợp lệ:** Spring auto-proxy creator có thể bọc target bằng JDK dynamic proxy hoặc CGLIB tùy cấu hình.
5. **Lời gọi thực sự vượt qua ranh giới proxy:** client nhận bean reference do Spring cung cấp và gọi method tương ứng.

Luồng khái niệm:

~~~text
@Aspect bean
   -> Spring phát hiện @After + expression
   -> Advisor/interceptor phù hợp với target class/method
   -> Spring AOP proxy cho target bean
   -> Client gọi method qua proxy
   -> Target trả về hoặc ném exception
   -> @After advice chạy theo finally semantics
   -> Proxy hoàn tất lời gọi tới client
~~~

**`@Aspect` tự nó không tự đăng ký bean**; nếu thiếu `@Component`/`@Bean`, Spring có thể không tìm thấy aspect để tạo advisor. Và chỉ có `@After` trên một phương thức Java bất kỳ nhưng class không có `@Aspect` cũng không tự biến method thành Spring AOP advice.

Đừng nhầm việc đặt dependency `aspectjweaver` trong POM với việc bật weaving. Bài này dùng **Spring AOP proxy**, không dệt bytecode của target.

## 5. Ví dụ Java 17+ chạy được: success, failure, caught và self-invocation

Dự án sau sử dụng:

- **Java 17+** và Maven.
- Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**.
- Một `TaskService` là Spring bean với các method trả về bình thường, ném exception và bắt exception nội bộ.
- Một `LifecycleAspect` khai báo **cả `@AfterReturning`, `@AfterThrowing` và `@After` trong cùng aspect**. Điều này cho phép quan sát thứ tự theo Spring 6.2.
- Một lời gọi nội bộ `this.runOk()` để làm rõ giới hạn proxy.

Không dùng database, HTTP server, thread pool hay transaction manager.

### 5.1. Cấu trúc thư mục

~~~text
spring-after-finally-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── TaskService.java
    ├── LifecycleAspect.java
    └── Main.java
~~~

### 5.2. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-after-finally-demo</artifactId>
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

Spring Framework BOM giúp các module Spring sử dụng cùng bộ phiên bản. Nếu dự án dùng Spring Boot, ưu tiên BOM/parent và dependency do Boot quản lý thay vì chép những version này vào một dự án đang có cấu hình khác.

### 5.3. Target `TaskService.java`

~~~java
package example;

public class TaskService {

    public String runOk() {
        System.out.println("target: ok");
        return "OK";
    }

    public String runFail() {
        System.out.println("target: fail");
        throw new IllegalStateException("boom");
    }

    public String runRecovered() {
        System.out.println("target: recovered begin");
        try {
            throw new IllegalArgumentException("temporary");
        } catch (IllegalArgumentException ex) {
            System.out.println("target: caught temporary");
            return "RECOVERED";
        }
    }

    public String callInternally() {
        System.out.println("target: callInternally");
        return this.runOk();
    }
}
~~~

Đây là class Java thông thường. `runOk`, `runFail` và `runRecovered` đều có tên bắt đầu bằng `run`; `callInternally` thì không. Nó gọi `this.runOk()` từ bên trong target nên **không quay qua Spring AOP proxy**.

### 5.4. Aspect `LifecycleAspect.java`

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class LifecycleAspect {

    private static final String METHODS =
        "execution(* example.TaskService.run*(..))";

    @AfterReturning(pointcut = METHODS, returning = "value")
    public void afterSuccess(JoinPoint jp, Object value) {
        System.out.println("after-returning: "
            + jp.getSignature().getName() + " => " + value);
    }

    @AfterThrowing(pointcut = METHODS, throwing = "problem")
    public void afterFailure(JoinPoint jp, Throwable problem) {
        System.out.println("after-throwing: "
            + jp.getSignature().getName() + " => " + problem.getMessage());
    }

    @After(METHODS)
    public void afterFinally(JoinPoint jp) {
        System.out.println("after-finally: "
            + jp.getSignature().getName());
    }
}
~~~

**Ý nghĩa từng phần:**

- `METHODS` là một hằng chuỗi compile-time, được sử dụng trong ba annotation, giúp bảo đảm chúng cùng nhắm đúng biểu thức.
- `@AfterReturning(... returning = "value")` bind giá trị trả về bình thường vào tham số có tên `value`.
- `@AfterThrowing(... throwing = "problem")` bind exception thoát khỏi target vào tham số `problem`; ở ví dụ dùng `Throwable` để không giới hạn một subtype exception duy nhất.
- `@After(METHODS)` không có `returning` hoặc `throwing`: nó không tự nhận thông tin hai outcome dưới dạng một binding như hai loại advice còn lại.
- `JoinPoint jp` cho phép biết method signature; ta chỉ log **tên method**, không in tất cả method arguments vì có thể chứa dữ liệu nhạy cảm.

**Tại sao đặt ba advice trong cùng aspect?** Spring Framework 6.2 document có quy tắc cho thứ tự advice **khác loại trong cùng một `@Aspect`**; trong các trường hợp mẫu, after-returning/after-throwing được quan sát **trước** after-finally. Nếu tách thành ba aspects độc lập mà không định nghĩa precedence, không nên cam kết những dòng log từ các aspect xuất hiện theo cùng thứ tự.

### 5.5. Cấu hình Spring `AppConfig.java`

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TaskService taskService() {
        return new TaskService();
    }

    @Bean
    public LifecycleAspect lifecycleAspect() {
        return new LifecycleAspect();
    }
}
~~~

- `TaskService` được đăng ký làm **Spring bean** bằng `@Bean`.
- `LifecycleAspect` cũng là bean; Spring nhận diện `@Aspect` của nó và khai báo advice.
- `@EnableAspectJAutoProxy(proxyTargetClass = true)` bật AOP và chọn class-based proxy (CGLIB) khi cần, để ứng dụng gọi trực tiếp concrete `TaskService`.
- **Chuyển từ JDK proxy sang CGLIB không làm `this.runOk()` tự có advice.** Đường gọi nội bộ vẫn bỏ qua proxy.

### 5.6. Chương trình `Main.java`

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService service = context.getBean(TaskService.class);

            System.out.println("proxy: " + AopUtils.isAopProxy(service));

            System.out.println("-- success --");
            System.out.println("caller: " + service.runOk());

            System.out.println("-- target throws --");
            try {
                service.runFail();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            System.out.println("-- caught inside target --");
            System.out.println("caller: " + service.runRecovered());

            System.out.println("-- self invocation --");
            System.out.println("caller: " + service.callInternally());
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 5.7. Kết quả mong đợi

Với các file trên, **những dòng do ví dụ in ra**, theo thứ tự:

~~~text
proxy: true
-- success --
target: ok
after-returning: runOk => OK
after-finally: runOk
caller: OK
-- target throws --
target: fail
after-throwing: runFail => boom
after-finally: runFail
caller caught: boom
-- caught inside target --
target: recovered begin
target: caught temporary
after-returning: runRecovered => RECOVERED
after-finally: runRecovered
caller: RECOVERED
-- self invocation --
target: callInternally
target: ok
caller: OK
~~~

Maven hoặc framework có thể xuất thêm log riêng; bảng trên chỉ liệt kê các `System.out.println` trong chương trình minh họa.

### 5.8. Đọc kết quả

**Case 1 — `runOk()` trả về thành công:**

1. Caller gọi `service.runOk()` trên **Spring AOP proxy**.
2. Target in `target: ok`, trả về chuỗi `OK`.
3. `@AfterReturning` chạy và in kết quả vì method trả về bình thường.
4. `@After` chạy ở nhánh finally dù không có exception.
5. Caller in `caller: OK` sau khi lời gọi proxy hoàn tất.

**Case 2 — `runFail()` ném exception:**

1. Target in `target: fail` rồi ném `IllegalStateException("boom")`.
2. `@AfterReturning` **không chạy**.
3. `@AfterThrowing` chạy và nhận thông tin exception.
4. `@After` vẫn chạy vì method đã thoát qua nhánh throw.
5. Caller bắt exception ban đầu và in `caller caught: boom`. Advice không tự nuốt exception.

**Case 3 — exception bị bắt trong `runRecovered()`:**

1. Target bắt một `IllegalArgumentException` ngay trong chính method.
2. Method trả về `RECOVERED` **bình thường**.
3. Spring AOP nhìn thấy **normal return**. Vì vậy `@AfterReturning` chạy, còn `@AfterThrowing` không chạy.
4. `@After` vẫn chạy. Chỉ đọc log `@After` **không thể suy ra** liệu có exception đã được catch bên trong target.

**Case 4 — `callInternally()` và `this.runOk()`:**

- `callInternally()` không match expression `run*`.
- Trong target, `this.runOk()` chạy trực tiếp, **không qua proxy**, nên không thấy các dòng after-returning/after-finally của `runOk` ở case này.
- Điều này không có nghĩa pointcut `runOk()` sai: nó đã chạy advice khi được client gọi trực tiếp **qua proxy** ở case 1.

## 6. `@After` thật sự tương đương `finally` ở mức nào?

Cú pháp Java quen thuộc:

~~~java
try {
    operation();
} finally {
    cleanup();
}
~~~

Tương tự, after-finally advice chạy ở bước method được advice hoàn tất, **bất kể normal return hay exception exit**. Tuy vậy, có hai khác biệt lớn:

### 6.1. Nó nằm bên ngoài method, tại Spring AOP interception boundary

`@After` chỉ có tác dụng khi Spring AOP đã tạo ra advisor và invocation **đi qua proxy**. Một khối `finally` nằm **ngay trong thân method Java** chạy theo ngữ nghĩa Java dù object có thuộc Spring container hay không.

Ví dụ:

~~~java
public void runCleanupLocally() {
    try {
        doWork();
    } finally {
        localResource.close();
    }
}
~~~

Đoạn code **chỉ minh họa**, giả định các identifier `doWork` và `localResource` đã được khai báo. Java `finally` ở đây được kiểm soát trực tiếp bởi owner của tài nguyên. Ngược lại, Spring `@After` không chạy khi bạn gọi target ngoài proxy hoặc self-invocation bỏ qua proxy.

### 6.2. Advice là một lời gọi Java và bản thân cũng có thể ném exception

Nếu code trong `@After` ném exception, kết quả caller nhận được có thể bị thay đổi: một lời gọi target vốn thành công có thể chuyển thành thất bại, hoặc ngoại lệ gốc có thể bị **che khuất** bởi exception từ advice.

Ví dụ **không nên dùng trong cleanup mặc định**:

~~~java
@After("execution(* example.TaskService.run*(..))")
public void riskyCleanup() {
    throw new IllegalStateException("cleanup failure");
}
~~~

Nếu advice này chạy và tự ném exception, Spring AOP không tự hứa sẽ bảo toàn outcome gốc. Hãy thiết kế cleanup sao cho đáng tin cậy, quan sát được thất bại, và kiểm tra nghiệp vụ có được phép propagate lỗi cleanup không.

**Không nên nuốt lỗi bừa bãi.** Có những hệ thống bắt buộc phải dừng khi cleanup thất bại, nhưng quyết định đó phải được định nghĩa rõ trong hợp đồng nghiệp vụ. Đừng biến một hook ghi log/metrics thành nguồn lỗi mới ngoài ý muốn.

## 7. Dùng `JoinPoint` như thế nào trong `@After`?

Một advice có thể nhận `org.aspectj.lang.JoinPoint` để quan sát thông tin method execution:

~~~java
@After("execution(* example.TaskService.run*(..))")
public void afterCompletion(JoinPoint jp) {
    String method = jp.getSignature().getName();
    System.out.println("completed: " + method);
}
~~~

Các thông tin thường dùng:

| Cách gọi | Ý nghĩa trong Spring AOP |
| --- | --- |
| `jp.getSignature().getName()` | Tên method được match |
| `jp.getSignature().getDeclaringTypeName()` | Tên type gắn với method signature |
| `jp.getArgs()` | Mảng đối số được trình bày cho join point |
| `jp.getThis()` | Proxy object tại join point, khi API/cấu hình cho phép quan sát |
| `jp.getTarget()` | Target object phía sau proxy (có thể khác proxy) |

**Không coi `getArgs()` là dữ liệu mặc định an toàn để log.** Đối số có thể chứa mật khẩu, token, số thẻ hoặc thông tin cá nhân. Trong advice dùng chung, ưu tiên tên operation, request/correlation ID được cho phép, metric labels có cardinality thấp và các trường đã được lọc.

**`JoinPoint` không phải `ProceedingJoinPoint`:** chỉ `@Around` mới dùng `ProceedingJoinPoint.proceed()` để quyết định chuyển tiếp invocation. `@After` không gọi `proceed()`, cũng không nên can thiệp trực tiếp vào việc thực thi method từ một after-finally callback.

### 7.1. `@After` không bind return value/exception như các annotation chuyên biệt

Không có thuộc tính `returning` hoặc `throwing` trên `@After`. Nếu yêu cầu nghiệp vụ là:

- **Chỉ log dữ liệu trả về thành công:** dùng `@AfterReturning(pointcut=..., returning="value")`.
- **Chỉ xử lý exception đi ra từ target:** dùng `@AfterThrowing(pointcut=..., throwing="problem")`.
- **Luôn giải phóng trạng thái sau execution, không cần phân biệt outcome:** dùng `@After`.
- **Cần biết cả outcome lẫn thời gian thực thi trong cùng một state per-invocation:** cân nhắc `@Around` với `try/catch/finally` rõ ràng.

Đừng cố suy outcome bằng cách nhìn vào tên method hoặc bằng một field mutable dùng chung của singleton aspect; nhiều lời gọi concurrent có thể can thiệp lẫn nhau.

## 8. Thứ tự giữa `@After`, `@AfterReturning` và `@AfterThrowing`

Spring Framework mô tả quy tắc precedence khi **nhiều advice khác loại trong cùng một @Aspect** cùng áp dụng một join point. Trong Spring Framework 6.2, `@After` có **finally semantics** và về thời điểm thực thi thực tế được gọi **sau `@AfterReturning` hoặc `@AfterThrowing`** trong chính aspect ấy.

Do đó trong ví dụ mục 5:

~~~text
Trả về bình thường:
  target -> @AfterReturning -> @After -> caller

Ném exception:
  target -> @AfterThrowing -> @After -> caller bắt exception
~~~

Nhưng đừng từ sơ đồ trên suy ra một quy tắc cứng cho **mọi advice ở mọi aspect**:

- Khi advice thuộc **hai aspect khác nhau**, precedence giữa aspects phụ thuộc `@Order` hoặc `Ordered` và quy tắc vào/ra interceptor chain.
- Nếu nhiều advice **cùng loại** trên một join point trong **cùng aspect**, thứ tự không nên được suy từ thứ tự khai báo method trong file Java.
- Spring AOP còn có thể có infrastructure advisors do transaction/caching/security, vì vậy kết quả ở ứng dụng thật có thêm tầng ngoài.
- Trong câu chuyện về "finally", **thứ tự thực thi thực tế** khác với việc liệt kê mức độ precedence trong tài liệu. Nên test version/cấu hình cụ thể khi order ảnh hưởng business behavior.
- `@AfterThrowing` không phải callback chung để bắt exception do một advice `@After` hoặc `@AfterReturning` khác ném ra. Mỗi advice type có ngữ nghĩa riêng quanh join point.

### 8.1. `@Order` không làm `@After` thành success-only

Có thể dùng `@Order(10)` trên một aspect để điều chỉnh precedence so với aspect khác, nhưng bản thân `@After` vẫn chạy cho **normal và exceptional exit** của matched method invocation. `@Order` không đổi tập method được pointcut match và không biến `@After` thành `@AfterReturning`.

## 9. Cleanup phù hợp và cleanup không phù hợp

### 9.1. Những tác vụ phù hợp với `@After`

- Ghi nhận rằng một **operation đã kết thúc** mà không cần đọc return value/exception.
- Xóa một marker theo thread/correlation context **do một thành phần phối hợp có vòng đời xác định** đặt trước đó.
- Giải phóng trạng thái/handle **do aspect hoặc hạ tầng AOP tương ứng quản lý**, nếu ownership rõ ràng và có thể cleanup ở cả hai nhánh.
- Đánh dấu kết thúc một instrumentation scope khi bản thân advice không cần lưu thời điểm bắt đầu cùng invocation.
- Hỗ trợ operational log ở mức method/operation, không thay đổi nghiệp vụ.

Với các ví dụ này, cần kiểm tra việc tạo, sở hữu và giải phóng tài nguyên; Spring `@After` không tự sinh hoặc quản lý tài nguyên giúp bạn.

### 9.2. Những trường hợp không nên lạm dụng

**Không dùng `@After` để quyết định chỉ-on-success.** Nếu cleanup là hành vi chỉ được phép sau khi commit thành công, `@After` ở method boundary không chứng minh một transaction đã commit. Với `@Transactional`, thời điểm transaction interceptor commit và advice @Aspect của bạn còn phụ thuộc thứ tự advisors.

**Không dùng `@After` để retry hoặc sửa giá trị trả về.** Những cơ chế ấy cần thiết kế `@Around`/chính sách retry, không phải callback after-finally không có `proceed()`.

**Không giải phóng tài nguyên không thuộc quyền sở hữu.** Ví dụ, khóa được giữ bởi caller qua nhiều method hoặc connection thuộc transaction manager không nên bị đóng bừa bãi từ một aspect chung.

**Không giả định mọi lời gọi method sẽ kích hoạt cleanup.** Self-invocation hoặc một lời gọi đến object được tạo bằng `new` bên ngoài Spring sẽ bỏ qua Spring AOP proxy.

### 9.3. Nếu cần mở và đóng resource cho riêng mỗi invocation

Khi cần tạo một handle trước lời gọi và đảm bảo đóng **chính handle ấy** sau lời gọi, `@Around` với biến cục bộ và `try/finally` thường rõ ràng hơn:

~~~java
// Snippet minh họa bên trong một Spring-managed @Aspect; không chạy độc lập.
@Around("execution(* example.TaskService.run*(..))")
public Object withScope(ProceedingJoinPoint pjp) throws Throwable {
    ScopeHandle handle = scopeManager.open();
    try {
        return pjp.proceed();
    } finally {
        handle.close();
    }
}
~~~

Các type `ScopeHandle` và `scopeManager` ở đây là abstraction minh họa, cần ứng dụng cung cấp. `@Around` được cân nhắc vì có **biến handle riêng cho từng lời gọi**, không phải vì `@After` kém an toàn trong mọi tình huống.

Nếu resource được mở **bên trong target method**, một khối `try-with-resources` ngay tại nơi tạo resource có thể là cách đúng hơn, dễ đọc hơn và không phụ thuộc AOP proxy boundary.

## 10. Giới hạn của "luôn chạy": proxy và đường gọi

Từ "finally" cần hiểu kèm tiền đề: **một invocation đã match và thực sự vào chuỗi Spring AOP**. `@After` không phải hook toàn cục chạy mỗi khi JVM xử lý bất kỳ method cùng tên nào.

### 10.1. Self-invocation qua `this`

~~~java
public void outer() {
    this.runOk();
}
~~~

Nếu `outer()` được gọi qua proxy và không có advice riêng cho `outer()`, target bắt đầu thực thi `outer()`; sau đó `this.runOk()` vẫn gọi nội bộ target. Advice nhắm `runOk()` **không chạy** cho lời gọi nội bộ ấy.

**Đổi sang CGLIB cũng không tự sửa self-invocation.** Đây là giới hạn Spring AOP proxy-based ở cả hai chiến lược JDK và CGLIB.

Cách sửa thông dụng: tách hành vi cần được advice sang một Spring bean khác, inject bean đó và gọi qua Spring-managed proxy. Không thêm `AopContext.currentProxy()` hoặc self-injection chỉ để tránh refactor nếu không hiểu tác động tới coupling/circular dependencies.

### 10.2. Object tự tạo với `new`

~~~java
TaskService service = new TaskService();
service.runFail();
~~~

Đây là Java object ngoài context; mặc dù trong mã nguồn có một Spring `@Aspect` tương ứng, **instance này không được Spring AOP auto-proxy**. `@After` không chạy cho lời gọi trên nó.

### 10.3. Pointcut không match

Nếu advice khai báo:

~~~java
@After("execution(* example.TaskService.run*(..))")
~~~

thì `TaskService.callInternally()` không thỏa method name pattern `run*`. Không có after advice cho invocation `callInternally()` chỉ vì bean là proxy.

### 10.4. Chặn sớm ở interceptor/advice ngoài

Một `@Around` advice ở tầng ngoài có thể **trả về mà không gọi `proceed()`**. Khi đó method execution phía trong không xảy ra; advice gắn với execution đó cũng không nhất thiết được gọi. Ví dụ cache hit có thể kết thúc tại một interceptor ngoài.

Tương tự, nếu một `@Before` advice phía ngoài ném exception trước khi chuỗi gọi đến target/@After, không có bảo đảm mọi after-finally advice ở các tầng trong đều đã được vào và phải chạy. Hãy phân biệt exception **do target method ném sau khi invocation tới target** với exception phát sinh **trước khi target được gọi**.

### 10.5. JVM/process termination

Dù Java `finally` cũng có những giới hạn (ví dụ process bị dừng cưỡng bức), Spring `@After` càng không nên bị mô tả là "bất biến trong mọi hoàn cảnh". Khi JVM crash, kill -9, mất máy hay container dừng bất thường, đừng kỳ vọng một AOP advice dọn dẹp vẫn chạy.

## 11. Hệ quả khi method trả về giá trị bất đồng bộ hoặc reactive

Ngữ nghĩa after-finally của Spring AOP gắn với **method execution được proxy can thiệp**, không phải một khái niệm business “công việc đã hoàn tất vĩnh viễn”.

Ví dụ trả về CompletableFuture:

~~~java
// Snippet trong một Spring-managed target bean, không phải chương trình độc lập.
public CompletableFuture<String> runAsyncStyle() {
    return CompletableFuture.supplyAsync(() -> performWork());
}
~~~

Nếu method **trả về CompletableFuture nhanh** và công việc chạy bên trong future vẫn đang tiếp diễn, `@After` của method execution có thể chạy **trước khi future hoàn thành**. Nó quan sát **thời điểm method đã trả về object Future**, không phải một lời hứa rằng asynchronous work đã thành công/thất bại.

Tương tự, với code reactive trả về `Mono` hoặc `Flux`, việc tạo publisher và thực thi pipeline khi subscribe có thể ở hai thời điểm khác nhau. `@After` trên method tạo publisher **không mặc nhiên chạy vào thời điểm subscription hoàn tất**.

**Cách thiết kế:** Nếu cần cleanup gắn với **vòng đời future/publisher**, hãy dùng callback/completion handler hoặc operator tương ứng (ví dụ CompletableFuture.whenComplete, Reactor.doFinally khi dùng Reactor), không coi `@After` của method factory là completion signal.

Các ví dụ về future/reactive chỉ nhằm nói rõ giới hạn của **Spring AOP advice timing**, không phải bài học chi tiết về concurrency hay reactive programming.

## 12. Spring Boot và cách bật advice

Trong Spring Framework thuần, cách bật quen thuộc là:

~~~java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
~~~

Đây là snippet minh họa, cần các imports Spring và một ApplicationContext phù hợp. Class `@Aspect` vẫn cần được đăng ký thành **Spring bean** để advisor được khám phá.

Trong ứng dụng Spring Boot:

- **Boot 3.x** thường sử dụng `spring-boot-starter-aop`.
- **Boot 4.x** sử dụng `spring-boot-starter-aspectj` theo tên starter mới.
- Nếu classpath và Spring Boot AOP auto-configuration hoạt động, không nhất thiết phải viết `@EnableAspectJAutoProxy` thủ công.
- `@Aspect @Component` phải nằm trong phạm vi component scanning; hoặc có một method `@Bean` đăng ký aspect.
- `spring.aop.proxy-target-class` điều chỉnh JDK/CGLIB strategy, **không đổi ngữ nghĩa finally của `@After`**.
- Nếu dự án tắt AOP auto-configuration hoặc loại dependency cần thiết, annotation `@After` trong mã nguồn không tự làm lời gọi bị can thiệp.

Điều quan trọng: framework có hỗ trợ AOP **không đồng nghĩa** mọi bean có proxy hay mọi method có `@After` advice. Cần advisor match đúng bean và invocation đi qua proxy.

## 13. Chẩn đoán `@After` không chạy hoặc chạy bất ngờ

| Hiện tượng | Khả năng nguyên nhân | Kiểm tra/sửa |
| --- | --- | --- |
| Method trả về thành công nhưng không thấy `@After` | Aspect không phải bean hoặc AOP chưa bật | Kiểm tra bean registration, @ComponentScan, @EnableAspectJAutoProxy/Boot auto-config |
| Method ném exception nhưng không thấy `@After` | Lời gọi không qua proxy, không match pointcut hoặc target chưa được gọi | Kiểm tra Spring bean reference, signature, interceptor chain |
| Gọi trực tiếp qua Spring bean có log; gọi bằng `this.method()` không có | **Self-invocation** | Tách method cần advice sang bean khác và gọi qua DI |
| Chỉ `@AfterReturning` chạy khi thành công | Đây là hành vi đúng | Dùng `@After` nếu cần cả hai outcome |
| `@AfterThrowing` không chạy khi exception được target bắt | Method kết thúc bình thường, không có throwable thoát ra | Phân biệt exception nội bộ với exception thoát method |
| `@After` in log sau exception nhưng caller vẫn thấy exception | Đây là hành vi đúng | @After không tự nuốt exception; caller xử lý tiếp |
| `@After` ném lỗi và caller mất kết quả thành công | Exception phát sinh trong chính advice | Thiết kế cleanup/logging không làm thay đổi hợp đồng ngoài ý muốn |
| `@After` có log cho method ngoài phạm vi | Pointcut quá rộng | Thu hẹp package, class, method, bean hoặc annotation |
| Nhìn `AopUtils.isAopProxy(bean) == true` nhưng advice không chạy | Proxy có thể do advisor khác tạo hoặc method không match | Kiểm tra advisor và pointcut cụ thể |
| Log `@After` đến trước/ sau transaction commit khác dự đoán | Thứ tự infrastructure advisors và @Aspect advice | Kiểm tra @Order/Ordered và integration test transaction thật |
| `@After` chạy trước khi background job kết thúc | Method trả future/publisher đã kết thúc sớm | Theo dõi completion của async/reactive work thay vì method return |
| Có hai dòng `@After` cho một lời gọi | Hai aspects/advisors cùng match, trùng bean registration hoặc nested proxies | Kiểm tra danh sách aspect beans và advisor chain |

### Checklist kiểm tra nhanh

1. **Có aspect bean chưa?** `ApplicationContext.getBeanNamesForType(LifecycleAspect.class)`.
2. **AOP đã bật?** Spring Framework: `@EnableAspectJAutoProxy`; Spring Boot: auto-configuration/starter theo version.
3. **Có target bean/proxy thực sự?** `AopUtils.isAopProxy(context.getBean(TaskService.class))`; kết quả `true` không đủ để khẳng định method match.
4. **Pointcut match method?** Kiểm tra package, method name pattern, overloaded method và visibility.
5. **Caller đang giữ proxy?** Không dùng object tự `new`, tránh lấy underlying target rồi gọi trực tiếp.
6. **Có self-invocation?** Xem những lời gọi `this.runX()` trong target.
7. **Có around advice short-circuit?** Kiểm tra `proceed()` có thực sự được gọi hay không.
8. **Advice tự ném exception?** Đừng nhầm exception của advice với exception của target.
9. **Có nhiều aspects/infrastructure advisors?** Điều tra thứ tự trước khi cam kết stdout.
10. **Có tác vụ async?** Method-return time không phải completion time của job.

## 14. Tự kiểm tra

**Câu 1.** `@After("execution(* TaskService.run*(..))")` có chạy khi `runFail()` ném `IllegalStateException` ra ngoài không?

**Đáp án:** Có, nếu invocation match và đi qua Spring AOP proxy như trong ví dụ. After-finally advice chạy cho exceptional exit của method.

**Câu 2.** `runRecovered()` bắt lỗi nội bộ rồi trả về `"RECOVERED"`. `@AfterThrowing` có chạy không? `@After` thì sao?

**Đáp án:** `@AfterThrowing` không chạy vì method không ném exception ra ngoài. `@After` chạy vì method execution đã kết thúc bình thường.

**Câu 3.** Có thể dùng `@After` với tham số `returning="value"` để lấy return value không?

**Đáp án:** Không. Thuộc tính `returning` là của `@AfterReturning`. Với `@After`, dùng `JoinPoint` để quan sát signature/arguments nhưng không tự nhận return value binding như success advice.

**Câu 4.** Method `runOk()` được gọi qua `this.runOk()` bên trong target. `@After` chạy không?

**Đáp án:** Không cho lời gọi nội bộ đó vì nó bỏ qua Spring AOP proxy. Gọi trực tiếp `service.runOk()` trên Spring proxy ở một caller khác lại có thể kích hoạt advice.

**Câu 5.** Một `@After` advice ném `IllegalStateException` sau khi target đã thành công. Caller còn chắc chắn nhận kết quả thành công không?

**Đáp án:** Không. Exception từ advice có thể biến lời gọi ngoài thành thất bại hoặc che khuất exception gốc nếu có. Dọn dẹp phải có chính sách xử lý lỗi rõ ràng.

**Câu 6.** Cần tính thời gian chạy một method bằng biến start riêng cho từng invocation. Nên dùng hai field mutable trong singleton aspect và `@Before`/`@After` không?

**Đáp án:** Không nên, vì nhiều invocation concurrent có thể ghi đè state. Dùng `@Around` với biến cục bộ `start` và `try/finally` hoặc instrumentation scope được quản lý riêng cho từng invocation.

**Câu 7.** Method trả về `CompletableFuture`, Future chưa xong nhưng `@After` đã chạy. Có sai không?

**Đáp án:** Không. Method execution có thể đã trả Future; Spring @After ở boundary method không tự chờ Future hoàn tất.

**Câu 8.** Có ba advice @After, @AfterReturning, @AfterThrowing trong cùng aspect. Có nên dựa vào thứ tự khai báo các method trong source file không?

**Đáp án:** Không. Hãy dựa trên quy tắc Spring cho advice type và chạy integration test. Với Spring 6.2, after-finally advice thực tế chạy sau after-returning hoặc after-throwing cùng aspect ở những invocation tương ứng.

## 15. Tài liệu Spring chính thức

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): phần "After (Finally) Advice", phân biệt after-returning/after-throwing, `JoinPoint` và thứ tự advice.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): phạm vi Spring AOP proxy và các loại advice.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): bật `@EnableAspectJAutoProxy`, yêu cầu aspect bean và dependency AspectJ.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation và ranh giới interception.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): điều kiện method execution và expression.
- [Spring Framework — Programmatic Advice API](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): hợp đồng advice và lưu ý khi advice tự ném exception.
