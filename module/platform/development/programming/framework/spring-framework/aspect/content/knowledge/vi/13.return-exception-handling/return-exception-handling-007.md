# Không dùng @AfterThrowing như bằng chứng mọi lỗi đều đã được xử lý trong Spring AOP

## 1. Ý tưởng trọng tâm: quan sát ngoại lệ khác với xử lý ngoại lệ

Trong Spring Framework, một advice khai báo bằng `@AfterThrowing` có thể chạy khi **method execution khớp pointcut** trên một Spring-managed bean **kết thúc bằng việc ném ngoại lệ** qua Spring AOP proxy. Đây là một thời điểm phù hợp để ghi nhận lỗi, metrics, audit hoặc chẩn đoán; **không phải bằng chứng rằng lỗi đã được giải quyết**.

Ví dụ:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.OrderService.submit(..))",
    throwing = "error",
    argNames = "error"
)
public void observedFailure(IllegalArgumentException error) {
    System.out.println("observed: " + error.getMessage());
}
~~~

Giả sử `OrderService.submit(...)` ném `IllegalArgumentException("invalid-order")`. Trong một ứng dụng Spring AOP cấu hình hợp lệ, advice có thể in `observed: invalid-order`, **rồi caller vẫn nhận chính ngoại lệ đó**. Việc ghi nhận một exception không tự động chuyển nó thành kết quả thành công, thông báo HTTP, phản hồi người dùng, transaction rollback hay bản ghi đã được sửa.

**Ba khái niệm phải tách biệt:**

- **Observed (được quan sát):** advice thấy Throwable đi ra từ một method execution phù hợp.
- **Handled (được xử lý):** một thành phần thực sự quyết định cách khôi phục, dịch lỗi, trả phản hồi hay propagate có kiểm soát.
- **Resolved (đã giải quyết):** hệ thống thỏa hợp đồng nghiệp vụ sau lỗi, ví dụ trạng thái hợp lệ, tài nguyên nhất quán hoặc quy trình retry/fallback thành công.

`@AfterThrowing` chủ yếu cung cấp **tín hiệu quan sát exceptional exit**; nó không chứng minh hai trạng thái sau.

Bài chỉ tập trung vào **Spring Aspect/Spring AOP proxy-based**, phù hợp Special Note của module. Không lặp lại lý thuyết Aspect chung.

## 2. Ngữ nghĩa chính thức của @AfterThrowing trong Spring

Spring Framework mô tả `@AfterThrowing` là advice chạy khi một **matched method execution exits by throwing an exception**. Cụ thể:

1. Lớp chứa advice phải được Spring đăng ký làm một **`@Aspect` bean**.
2. Spring AOP cần được bật (ví dụ `@EnableAspectJAutoProxy` khi dùng Spring Framework thuần).
3. Pointcut phải match **method execution** trên target bean.
4. Caller phải đi qua **Spring AOP proxy**, không gọi trực tiếp target ngoài container.
5. Invocation phải kết thúc bằng exception **thoát ra tại boundary được advice**, không chỉ một exception được tạo rồi catch bên trong.
6. Nếu có `throwing = "error"` và tham số có kiểu cụ thể, Throwable phải **tương thích kiểu đó**.

Nếu tất cả điều kiện thỏa, advice có thể chạy. Nhưng khi method advice chỉ log rồi return bình thường, **exception gốc vẫn tiếp tục lan truyền**, trừ khi có một interceptor/caller khác chủ động xử lý nó.

~~~text
Caller
   |
   v
Spring AOP proxy
   |
   +--> matched target method
   |        |
   |        +-- throw IllegalArgumentException("invalid-order")
   |        |
   +--> @AfterThrowing advice
   |        |
   |        +-- log / metrics / audit (KHÔNG tự handle)
   |
   +--> exception đi ra khỏi proxy
   |
   v
Caller phải catch hoặc tiếp tục propagate
~~~

Điểm mấu chốt là **`@AfterThrowing` diễn ra trên đường truyền ngoại lệ**, không tự biến một *exceptional exit* thành *normal return*. Đây cũng không phải nơi bao quát mọi lỗi từ các advice khác: tài liệu Spring lưu ý nó không phải **general exception handling callback** cho exceptions do `@After` hoặc `@AfterReturning` đi kèm gây ra.

## 3. Một dòng log nói được và không nói được điều gì?

Giả sử quan sát được:

~~~text
AOP observed: submit -> invalid-order
~~~

Kết luận hợp lệ:

- Có một invocation mà advice đã được kích hoạt.
- Tại boundary quan sát, method execution đã kết thúc theo nhánh exception mà binding phù hợp.
- Code trong advice đã in được dòng log.
- Nếu log đến từ tham số `Throwable`, ta biết throwable được chuyển vào advice **theo ngữ nghĩa của binding**.

**Không thể kết luận chỉ từ dòng này rằng:**

- Caller đã catch exception.
- HTTP endpoint đã trả status phù hợp.
- Transaction đã rollback hoặc commit theo ý định.
- Cơ sở dữ liệu đã được phục hồi.
- Client đã nhận được thông báo hữu ích.
- Có một retry thành công.
- Tất cả các exceptions khác của ứng dụng đều được quan sát.
- Lỗi đã biến mất khỏi hệ thống.
- Mọi inner/outer interceptor đã chạy.
- Sự kiện đã được gửi thành công đến log/metrics backend bên ngoài.

Một test chỉ assert `logs.contains("AOP observed")` là **test quan sát**, không phải test nghiệp vụ thành công hay test exception handling.

## 4. So sánh @AfterThrowing với các cơ chế Spring khác

| Công cụ / vị trí | Chức năng chính | Có tự biến lỗi thành kết quả hợp lệ không? |
| --- | --- | --- |
| `@AfterThrowing` trên `@Aspect` | Quan sát ngoại lệ thoát method execution theo pointcut và kiểu binding | **Không** |
| `@After` | Chạy after-finally khi method trả bình thường hoặc ném lỗi | Không |
| `@AfterReturning` | Nhận callback khi method execution trả bình thường | Không; không chạy nếu lỗi thoát method |
| `@Around` với `try/catch` và `proceed()` | Có thể bắt, rethrow, translate hoặc return fallback theo contract | **Có thể**, khi code chủ động làm như vậy |
| `try/catch` trong service | Xử lý lỗi tại nơi chủ sở hữu logic nghiệp vụ | **Có thể** |
| Caller `try/catch` | Xử lý exception tại ranh giới gọi method | **Có thể** |
| Spring MVC `@ExceptionHandler` hoặc `@ControllerAdvice` | Chuyển exception trong vòng đời web request thành HTTP response phù hợp | **Có thể**, theo cấu hình |
| Spring transaction interceptor | Áp dụng rollback/commit policy tại transaction boundary | Có thể rollback; **không đồng nghĩa exception đã được handle** |
| Spring Retry / resilience policy | Có thể retry/fallback theo quy tắc riêng | Tùy cấu hình, idempotency và kết quả thực tế |

**Không gộp các khái niệm:** “exception đã được logged”, “exception đã bị caught”, “request đã có HTTP response”, “transaction đã rollback” và “business operation đã recovered” là **các sự kiện khác nhau**.

Ví dụ Spring MVC có thể biến một ngoại lệ thành HTTP 400 bằng `@ExceptionHandler` trong khi Spring AOP `@AfterThrowing` vẫn chỉ làm nhiệm vụ ghi nhận lỗi ở service layer. Hoặc caller tự catch exception mà không có web layer nào tham gia.

## 5. Binding `throwing` chỉ quan sát loại lỗi tương thích

Một advice:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.OrderService.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterInvalidOrder(IllegalArgumentException error) {
    // Chỉ các exceptions tương thích IllegalArgumentException.
}
~~~

bị giới hạn bởi **cả hai điều kiện**:

1. Pointcut chọn các method executions của `OrderService`.
2. Exception thoát method phải tương thích với `IllegalArgumentException`.

So sánh:

| Advice parameter | Những lỗi có thể bind | Không tự nhận |
| --- | --- | --- |
| `IllegalArgumentException error` | IllegalArgumentException và subclasses | IllegalStateException không cùng nhánh |
| `IllegalStateException error` | IllegalStateException và subclasses | IllegalArgumentException |
| `RuntimeException error` | RuntimeException và subclasses | Checked IOException, AssertionError |
| `Exception error` | Exception và subclasses | Error không phải Exception |
| `Throwable error` | Các Throwable phù hợp từ method join point | Không chứng minh mọi lỗi ở nơi khác đều đi qua pointcut |

**Dùng `Throwable` không biến advice thành global handler.** Nó chỉ mở rộng **loại exception có thể bind**, không mở rộng thành mọi bean, mọi join point hoặc mọi invocation vượt ngoài Spring proxy.

Tên trong `throwing = "error"` phải khớp tên tham số Java advice. `argNames = "error"` khai báo rõ binding để tránh phụ thuộc cách compiler lưu tên tham số. Nếu có `JoinPoint` ở vị trí đầu tiên, Spring cho phép bỏ tên tham số `JoinPoint` khỏi `argNames` theo quy tắc binding documented.

## 6. Ngoại lệ nội bộ đã được catch: @AfterThrowing không nhận tín hiệu

Một target Spring bean:

~~~java
public String recoverInternally() {
    try {
        throw new IllegalArgumentException("temporary");
    } catch (IllegalArgumentException ex) {
        return "RECOVERED";
    }
}
~~~

Nếu caller gọi `recoverInternally()` qua proxy:

- Trong target có một exception được ném ra rồi **catch ngay trong method**.
- Từ góc nhìn Spring AOP method execution, method **trả về `"RECOVERED"` bình thường**.
- `@AfterThrowing` **không chạy** cho exception đã được xử lý nội bộ.
- `@AfterReturning` phù hợp có thể chạy, vì có normal return.
- Điều đó **không** chứng minh bên trong method chưa từng có lỗi.

Vì thế, **không có log `@AfterThrowing` không có nghĩa không có lỗi**, đặc biệt khi code có catch/fallback.

Mặt ngược lại cũng quan trọng: **có log `@AfterThrowing` không có nghĩa lỗi đã được handle**. Hai quan sát này không được suy luận theo hai chiều đơn giản.

## 7. Caller catch và @AfterThrowing không mâu thuẫn

Code caller:

~~~java
try {
    service.submit(true);
} catch (IllegalArgumentException ex) {
    System.out.println("caller caught: " + ex.getMessage());
}
~~~

Nếu `submit(true)` là lời gọi qua Spring proxy và có pointcut/throwing type phù hợp, thứ tự có thể là:

~~~text
target: submit
advice observed: submit -> invalid-order
caller caught: invalid-order
~~~

Tại thời điểm `@AfterThrowing` log, exception đang **đi ra từ matched method execution**. Caller vẫn có thể catch nó **sau đó**. Do đó advice chạy và caller catch **không loại trừ nhau**.

**Không suy sai rằng advice đã xử lý lỗi thay caller.** Nếu xóa `try/catch` ở caller mà không có tầng khác xử lý, exception vẫn lan truyền theo quy tắc Java/Spring thông thường.

Cũng đừng kết luận caller đã catch đúng loại exception chỉ vì advice có binding typed. Mỗi tầng có thể có contract khác; caller nên có test riêng cho propagation và error response.

## 8. Ví dụ Spring AOP với một interceptor bên ngoài xử lý fallback

Một `@Around` advice có thể chủ động catch exception:

~~~java
// Snippet trong một class @Aspect đã là Spring bean.
@Around("execution(* example.OrderService.submit(..))")
public Object recoverAtBoundary(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalArgumentException ex) {
        return "FALLBACK";
    }
}
~~~

Snippet này minh họa điều mà `@AfterThrowing` **không làm theo mặc định**: chuyển exception thành một normal return. Nhưng nếu áp dụng, nó **thay đổi business contract**, nên chỉ đúng khi fallback được nghiệp vụ chấp nhận.

Còn phải xét **vị trí trong advisor chain**:

- Nếu `@Around` nằm **ngoài** `@AfterThrowing`, inner after-throwing advice có thể thấy exception trước, sau đó outer catch và trả fallback; caller chỉ thấy thành công.
- Nếu `@Around` nằm **trong** `@AfterThrowing` và catch exception rồi trả fallback, outer after-throwing advice có thể **không chạy** vì thấy normal return.
- Nếu nhiều aspects có cùng precedence hoặc không khai báo order, không nên dựa vào thứ tự ngẫu nhiên.

**Cảnh báo:** Một `@Around` fallback không nên tự ý nuốt mọi `Throwable` trong một shared aspect. Nó có thể che giấu lỗi hệ thống, thay đổi HTTP status, phá vỡ retry/rollback semantics và làm dữ liệu ở trạng thái không mong muốn.

## 9. Project Maven/Java 17+ chạy được: quan sát ≠ xử lý

Project dùng **Java 17+**, Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**. Một Spring service có năm đường gọi được thiết kế để phân biệt:

1. Normal return: không có exceptional exit.
2. Ném `IllegalArgumentException` tới caller: `@AfterThrowing` ghi nhận nhưng **không catch thay caller**.
3. Catch exception bên trong target: aspect không thấy exceptional exit.
4. Ném exception khác kiểu `IllegalStateException`: typed advice không match.
5. Method ngoài gọi `this.submit(true)` nội bộ: proxy chỉ thấy exceptional exit của **method ngoài**, không tạo thêm invocation riêng cho method inner.

Project không cần Spring Boot, HTTP server, database hoặc transaction manager.

### 9.1. Cấu trúc thư mục

~~~text
spring-after-throwing-not-handled/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── OrderService.java
    ├── FailureObserverAspect.java
    └── Main.java
~~~

### 9.2. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-after-throwing-not-handled</artifactId>
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

Project dùng Spring Framework BOM để các module Spring thống nhất phiên bản. Với ứng dụng Spring Boot thực tế, ưu tiên để Boot quản lý versions/starter phù hợp; không buộc phiên bản của project học tập lên ứng dụng khác.

### 9.3. `OrderService.java` — target nghiệp vụ

~~~java
package example;

public class OrderService {

    public String submit(boolean invalid) {
        System.out.println("target: submit");
        if (invalid) {
            throw new IllegalArgumentException("invalid-order");
        }
        return "ACCEPTED";
    }

    public String recoverInternally() {
        System.out.println("target: recover");
        try {
            throw new IllegalArgumentException("temporary");
        } catch (IllegalArgumentException ex) {
            System.out.println("target: recovered temporary");
            return "RECOVERED";
        }
    }

    public void failState() {
        System.out.println("target: failState");
        throw new IllegalStateException("storage");
    }

    public String forwardInternally() {
        System.out.println("target: forwardInternally");
        return this.submit(true);
    }
}
~~~

Ở đây `submit(true)` ném lỗi, `submit(false)` thành công. `recoverInternally()` bắt lỗi ngay bên trong. `failState()` ném một loại exception khác. `forwardInternally()` gọi trực tiếp `this.submit(true)`, tức là lời gọi **nội bộ trên target**, không đi qua Spring AOP proxy lần thứ hai.

### 9.4. `FailureObserverAspect.java` — aspect chỉ quan sát

~~~java
package example;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class FailureObserverAspect {

    private final CopyOnWriteArrayList<String> observed =
        new CopyOnWriteArrayList<>();

    @AfterThrowing(
        pointcut = "execution(* example.OrderService.*(..))",
        throwing = "failure",
        argNames = "failure"
    )
    public void observe(JoinPoint jp, IllegalArgumentException failure) {
        String method = jp.getSignature().getName();
        String value = method + ":" + failure.getMessage();
        observed.add(value);
        System.out.println("advice observed: " + method
            + " -> " + failure.getMessage());
    }

    public List<String> observations() {
        return List.copyOf(observed);
    }
}
~~~

**Tại sao advice không “handle” exception?**

- Nó ghi một entry và in log; không có `try/catch` bao quanh target execution.
- Method advice trả `void` không biến exception từ target thành success.
- Không có `return` của advice để thay thế return value của target.
- Với `IllegalStateException`, typed parameter `IllegalArgumentException` **không tương thích**, nên advice không chạy.
- Trong `recoverInternally()` không có exception thoát ra, nên cũng không chạy.
- `observations()` chỉ trả bản sao danh sách các sự kiện **đã được observer ghi**, không trả một danh sách **mọi lỗi đã xử lý**.

`CopyOnWriteArrayList` làm ví dụ dễ dùng khi kiểm tra, nhưng trong production không nên giữ vô hạn toàn bộ error messages trong bộ nhớ, và không nên log message thô nếu dữ liệu có thể nhạy cảm.

### 9.5. `AppConfig.java` — đăng ký Spring-managed beans

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public FailureObserverAspect failureObserverAspect() {
        return new FailureObserverAspect();
    }
}
~~~

- `@EnableAspectJAutoProxy` bật Spring AOP hỗ trợ `@AspectJ` trong context thuần.
- `@Bean` đưa cả target và aspect vào Spring container; chỉ có `@Aspect` trên class không tự đăng ký bean.
- `proxyTargetClass = true` cho phép demo lấy bean theo concrete class thông qua CGLIB proxy.
- Pointcut được giới hạn ở `OrderService`, không tự áp dụng cho tất cả beans.
- Spring AOP proxy-based vẫn có giới hạn self-invocation dù chọn CGLIB.

### 9.6. `Main.java` — năm tình huống và assertions

~~~java
package example;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService orders = context.getBean(OrderService.class);
            FailureObserverAspect observer =
                context.getBean(FailureObserverAspect.class);

            System.out.println("spring AOP proxy: "
                + AopUtils.isAopProxy(orders));

            System.out.println("-- normal return --");
            System.out.println("caller: " + orders.submit(false));

            System.out.println("-- exception still reaches caller --");
            try {
                orders.submit(true);
            } catch (IllegalArgumentException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            System.out.println("-- exception caught inside target --");
            System.out.println("caller: " + orders.recoverInternally());

            System.out.println("-- different exception type --");
            try {
                orders.failState();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            System.out.println("-- self invocation --");
            try {
                orders.forwardInternally();
            } catch (IllegalArgumentException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            List<String> expected = List.of(
                "submit:invalid-order",
                "forwardInternally:invalid-order"
            );
            if (!expected.equals(observer.observations())) {
                throw new AssertionError(
                    "Unexpected observations: " + observer.observations()
                );
            }
            System.out.println("verified observed count: "
                + observer.observations().size());
        }
    }
}
~~~

Các dòng `caller caught` chứng minh **caller** đã bắt exception, không phải aspect. Assertion xác minh chính xác các exceptional exits **mà Spring aspect đã quan sát**.

### 9.7. Lệnh chạy

Tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

**Stdout của các `System.out.println` trong project:**

~~~text
spring AOP proxy: true
-- normal return --
target: submit
caller: ACCEPTED
-- exception still reaches caller --
target: submit
advice observed: submit -> invalid-order
caller caught: invalid-order
-- exception caught inside target --
target: recover
target: recovered temporary
caller: RECOVERED
-- different exception type --
target: failState
caller caught: storage
-- self invocation --
target: forwardInternally
target: submit
advice observed: forwardInternally -> invalid-order
caller caught: invalid-order
verified observed count: 2
~~~

Maven hoặc runtime có thể phát thêm log ngoài mã ví dụ; các dòng trên mô tả chính xác chuỗi in từ các class mẫu.

### 9.8. Phân tích từng tình huống

**Normal return:** `submit(false)` trả `ACCEPTED`; không có `@AfterThrowing`. Điều này chỉ chứng minh method **không thoát bằng exception** tại proxy boundary; nó chưa chứng minh rằng mọi side effect đều thành công ở những thành phần bên ngoài.

**Ngoại lệ vẫn tới caller:** `submit(true)` ném `IllegalArgumentException`. Aspect ghi nhận nó, sau đó caller mới catch. Nếu xóa catch ở `Main`, exception có thể lan lên tầng gọi bên ngoài; advice không chịu trách nhiệm “giải quyết” ngoại lệ.

**Catch trong target:** `recoverInternally()` có lỗi bên trong nhưng xử lý bằng một `catch` cục bộ rồi trả `RECOVERED`. Không có observation ở after-throwing vì exception đã không thoát method. Đây là phản ví dụ cho suy luận **“không log @AfterThrowing ⇒ không xảy ra lỗi”**.

**Khác kiểu:** `failState()` ném `IllegalStateException`, không hợp với tham số `IllegalArgumentException failure`; aspect không ghi nhận, nhưng caller vẫn nhận lỗi. Đây là phản ví dụ cho suy luận **“observer này nhìn thấy mọi ngoại lệ”**.

**Self-invocation:** caller gọi `forwardInternally()` qua proxy. Target gọi `this.submit(true)` trực tiếp, **không qua proxy cho method submit**; exception lại thoát khỏi chính `forwardInternally()`. Vì thế callback ghi tên **`forwardInternally`**, không ghi một callback riêng cho `submit` nội bộ. Điều này minh họa cần quan sát **method join point ở ranh giới proxy**, không chỉ nơi Throwable được tạo.

## 10. Bảng kết quả: có log hay không, ai thực sự xử lý?

| Lời gọi | Exceptional exit tại proxy? | Typed `@AfterThrowing(IllegalArgumentException)` có chạy? | Người/điểm xử lý thật |
| --- | --- | --- | --- |
| `orders.submit(false)` | Không | Không | Return bình thường, không cần catch exception |
| `orders.submit(true)` | Có, IllegalArgumentException | **Có**, log `submit` | `Main.catch(IllegalArgumentException)` |
| `orders.recoverInternally()` | Không, method đã catch nội bộ | Không | `OrderService.recoverInternally()` |
| `orders.failState()` | Có, IllegalStateException | **Không** do kiểu binding | `Main.catch(IllegalStateException)` |
| `orders.forwardInternally()` | Có, IllegalArgumentException trên method ngoài | **Có**, log `forwardInternally` | `Main.catch(IllegalArgumentException)` |
| `new OrderService().submit(true)` ngoài Spring | Không qua Spring proxy | Không | Caller bên ngoài phải catch/propagate |

**Ý nghĩa:** Một observable callback không cho biết **lỗi đã được xử lý bởi ai**. Để chứng minh handling, phải xác minh behavior của tầng có trách nhiệm: service fallback, caller catch, web response, transaction rollback policy, v.v.

## 11. Exception từ chính advice có thể làm mọi việc tệ hơn

Một after-throwing advice có thể ném exception mới:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.OrderService.submit(..))",
    throwing = "failure",
    argNames = "failure"
)
public void dangerous(IllegalArgumentException failure) {
    throw new IllegalStateException("logging backend unavailable");
}
~~~

Đây là **snippet cảnh báo**, không thuộc demo mục 9. Nếu chạy:

- Target có thể đã ném `IllegalArgumentException("invalid-order")`.
- Lời advice tự ném `IllegalStateException("logging backend unavailable")`.
- Caller có thể thấy lỗi **của advice thay cho exception gốc**, làm mất khả năng chẩn đoán hoặc thay đổi transaction/retry semantics.

Vì vậy logging/metrics trong `@AfterThrowing` nên có **failure policy** rõ ràng. Nếu mục tiêu chỉ là best-effort observation, đừng để backend observability ném exception bừa bãi làm thay đổi nghiệp vụ. Nhưng cũng không nên dùng một `catch(Throwable)` im lặng trên toàn bộ hệ thống để che giấu mọi vấn đề; cân nhắc chính sách ghi nhận lỗi instrumentation phù hợp.

Điều tương tự áp dụng cho `@AfterReturning`, `@After` và quanh `@Around`: advice là code thật, nên nó có thể ném lỗi của chính mình.

## 12. @AfterThrowing không phải callback toàn cục cho lỗi của advice khác

Tài liệu Spring nêu rõ: after-throwing advice dùng để nhận exception từ **join point (user-declared target method)**, không phải một callback tổng quát bắt lỗi từ một `@After` hoặc `@AfterReturning` đi kèm.

Ví dụ:

~~~java
@Aspect
public class ConfusingAspect {

    @AfterReturning("execution(* example.OrderService.submit(..))")
    public void afterSuccess() {
        throw new IllegalStateException("observer failed");
    }

    @AfterThrowing(
        pointcut = "execution(* example.OrderService.submit(..))",
        throwing = "failure",
        argNames = "failure"
    )
    public void afterThrown(Throwable failure) {
        // Không được giả định sẽ được gọi chỉ vì afterSuccess() ném lỗi.
    }
}
~~~

Đây là **snippet giải thích**, không phải file của demo. Mặc dù một exception có thể thoát toàn bộ Spring proxy khi advice khác thất bại, Spring không bảo đảm rằng `@AfterThrowing` trong cùng aspect được dùng như một general exception observer cho lỗi từ những advice cùng aspect.

Nếu cần giám sát lỗi ở **ranh giới toàn bộ chain**, có thể xây một `@Around` observer bao ngoài các tầng cần quan sát, dùng `try/catch(Throwable t)` rồi `throw t`. Nhưng phải kiểm soát ordering để observer thật sự nằm ngoài, và việc bao ngoài như vậy vẫn **không phải giám sát mọi lỗi trong JVM**.

## 13. @AfterThrowing và Spring transactions: quan sát không chứng minh rollback

Trong Spring, transaction thường được thực hiện bằng advisor/interceptor riêng quanh method có `@Transactional`. Một trace có thể gồm:

~~~text
Caller
  -> Audit/Failure Aspect
      -> TransactionInterceptor
          -> TargetService.method()
          <- throw IllegalStateException
      <- TransactionInterceptor đánh dấu rollback/rollback theo policy
  <- Audit/Failure Aspect ghi nhận exception
  <- Caller
~~~

Nhưng **thứ tự có thể khác** nếu audit/failure aspect nằm bên trong transaction interceptor hoặc cấu hình infrastructure advisors khác. Không dựa vào một sơ đồ duy nhất cho mọi ứng dụng.

Quan trọng hơn:

- `@AfterThrowing` **không tự ra lệnh rollback**.
- Spring transaction rollback có **rule theo loại exception**, cấu hình `rollbackFor`/`noRollbackFor`, transaction manager và propagation.
- Một exception đã được **catch và không rethrow** trước khi tới transaction interceptor có thể khiến tầng transaction thấy normal return; cách xử lý phụ thuộc nghiệp vụ/cấu hình.
- Một transaction có thể thất bại ở **commit phase** sau khi target method trả về, vào vị trí khác trong interceptor chain.
- Có transaction rollback **không đồng nghĩa nghiệp vụ đã được phục hồi** hoặc HTTP request đã được handle.
- Một `@AfterThrowing` log exception **không thể một mình làm assertion rằng dữ liệu đã nhất quán**.

**Kiểm thử đúng:** dùng integration test với transaction manager và persistence thực; gọi Spring bean qua proxy, assert exception/HTTP behavior **và** trạng thái dữ liệu trước-sau transaction. Đừng chỉ assert có dòng log.

## 14. Web layer xử lý ngoại lệ bằng cơ chế khác

Với Spring MVC, nếu cần chuyển exception từ service thành HTTP response có chủ đích, có thể dùng `@ExceptionHandler` trong controller hoặc `@RestControllerAdvice`.

Ví dụ **snippet Spring MVC**:

~~~java
@RestControllerAdvice
public class ApiExceptionMapping {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> invalidInput(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("Invalid request");
    }
}
~~~

Đoạn này cần module Spring Web/MVC, imports thích hợp và một web application context; **không thuộc project Maven chạy độc lập ở mục 9**.

Những gì có thể xảy ra khi controller gọi `OrderService.submit(true)` qua Spring AOP proxy:

1. Target service ném `IllegalArgumentException`.
2. Spring `@AfterThrowing` ghi nhận exceptional exit của service.
3. Exception tiếp tục đi tới controller/web exception resolution layer.
4. `@ExceptionHandler` chuyển exception thành HTTP 400 với response cụ thể.

Ở đây **@ExceptionHandler** mới là tầng chuyển lỗi thành HTTP response. `@AfterThrowing` chỉ là observer ở service join point. Không nhầm trách nhiệm hai annotation chỉ vì đều liên quan tới exception.

Tương tự, command-line app, message consumer, scheduled task hay gRPC service phải có **cơ chế handling phù hợp ở boundary của chúng**; `@AfterThrowing` không tự thay thế các cơ chế đó.

## 15. AOP proxy boundary và những khoảng trống quan sát

### 15.1. Object tạo ngoài Spring

~~~java
new OrderService().submit(true);
~~~

Không có Spring-managed proxy ở lời gọi này. Bất kể một class `@Aspect` đã được đăng ký ở application context nào đó, **instance tự `new` này không tự được AOP advice**.

### 15.2. Self-invocation

~~~java
public String forwardInternally() {
    return this.submit(true);
}
~~~

Spring AOP không tự intercept một lời gọi method nội bộ trên `this` khi target code đang thực thi. Nếu `forwardInternally()` được gọi từ client qua proxy và cũng match pointcut, after-throwing có thể thấy **exception thoát từ forwardInternally**, không phải một join point mới cho `submit` bên trong.

### 15.3. JDK/CGLIB và method không thể advice

- JDK dynamic proxy dựa trên interface, caller thường inject qua interface được expose.
- CGLIB proxy dựa trên subclass; final/private methods không thể được override/advice theo cách thông thường.
- Việc đổi JDK sang CGLIB **không giải quyết self-invocation** trong Spring AOP proxy mode.
- Có bean proxy nhưng pointcut chỉ match một số method **không có nghĩa mọi method đều sinh after-throwing event**.

### 15.4. Asynchronous methods

Nếu method trả về `CompletableFuture<T>` hoặc reactive publisher, lỗi xuất hiện **sau khi method đã trả Future/Publisher** có thể không tạo exceptional exit ngay tại Spring AOP method boundary theo cách bạn đang quan sát. Với asynchronous/reactive application, cần instrumentation ở **future completion / reactive subscriber lifecycle** hoặc công cụ quan sát chuyên dụng.

**Không dùng số lượng `@AfterThrowing` callbacks làm tổng số lỗi end-to-end** trong một hệ thống có async tasks nếu chưa định nghĩa chính xác observation boundary.

## 16. Đếm lỗi bằng @AfterThrowing có thể sai theo cả hai chiều

### 16.1. Đếm thiếu (undercount)

- Exception bị catch **bên trong target**.
- Exception bị inner `@Around` xử lý và trả fallback.
- Exception khác kiểu `throwing` binding.
- Pointcut không match class/method.
- Invocation bypass Spring proxy.
- Lỗi phát sinh sau method return trong async/future/publisher.
- Lỗi phát sinh trong một infrastructure component hoặc advice khác, không phải user-declared target join point tương ứng.

### 16.2. Đếm trùng (overcount)

- Một error đi qua **nhiều service-layer proxy boundaries** cùng có aspect quan sát.
- Nhiều `@Aspect` beans hoặc advisors cùng ghi cùng một exception ở những tầng khác nhau.
- Retry gọi target nhiều lần, mỗi attempt ném lỗi và bị observer ghi riêng.
- Nested proxies gây cùng một failure xuất hiện trong nhiều interceptor chains.
- Một outer method và inner method **đều gọi qua Spring proxy** và đều quan sát cùng failure trong hai method invocations khác nhau.

**Do đó, metric “@AfterThrowing triggered N times” không tự bằng “N business operations failed”**. Cần xác định **đơn vị đếm**: method invocation, attempt, request, transaction, business command hay end-to-end outcome.

Để thống kê đáng tin cậy, dùng correlation ID/invocation ID (không chứa dữ liệu nhạy cảm), tránh trùng trên cùng logical operation và bổ sung end-to-end outcome metrics khi cần.

## 17. Kiểm thử: đừng chỉ assert callback đã được gọi

Một bộ test cần nhiều lớp xác nhận.

### 17.1. Ma trận test bắt buộc

| Trường hợp | Advice có thể quan sát? | Hành vi nghiệp vụ cần assert |
| --- | --- | --- |
| Method trả bình thường | Không có `@AfterThrowing` | Return value đúng |
| Method ném đúng exception type | Có, nếu pointcut/proxy match | Caller vẫn nhận đúng Throwable khi chưa có handler |
| Method ném sai exception type | Typed observer không chạy | Caller vẫn thấy exception phù hợp |
| Exception được catch nội bộ | Không có exceptional exit ở method boundary | Fallback đúng, trạng thái nhất quán |
| Caller catch exception | Observer có thể chạy **trước** catch | Catch branch đã được thực hiện |
| Self-invocation | Không có thêm inner proxy invocation | Không ghi nhầm inner join point |
| Outer `@Around` trả fallback | Tùy advisor ordering | Return/fallback đúng contract |
| @AfterThrowing tự ném lỗi | Có rủi ro che ngoại lệ gốc | Instrumentation failure policy được kiểm thử |
| @Transactional service ném lỗi | Tùy pointcut, order và rollback policy | Assert database state/transaction outcome thực |
| Web controller gặp lỗi | Có thể observer ghi ở service | Assert HTTP response/status/body riêng |
| Retry cùng operation | Có thể log nhiều attempts | Assert chỉ một logical operation outcome khi phù hợp |
| Future/publisher thất bại muộn | Method boundary có thể không thấy | Assert completion/cancellation outcome bằng API tương ứng |

### 17.2. Kiểm thử đúng exception type và message

Ví dụ ý tưởng JUnit 5, cần thêm `junit-jupiter` và Spring test dependencies thích hợp nếu triển khai trong project thực:

~~~java
IllegalArgumentException ex = assertThrows(
    IllegalArgumentException.class,
    () -> orders.submit(true)
);
assertEquals("invalid-order", ex.getMessage());
~~~

Đây là **snippet kiểm thử**, không được chèn nguyên xi vào `Main.java` của project mục 9 khi muốn giữ stdout. Nếu test chỉ kiểm `observer.observations().size() == 1` mà không dùng `assertThrows` hoặc kiểm tra state/response, test sẽ không chứng minh propagation đúng.

### 17.3. Kiểm thử “xử lý thành công” ở nơi xử lý thật

Nếu service có `recoverInternally()`, hãy assert `"RECOVERED"` cùng các hậu điều kiện. Nếu controller dùng `@ExceptionHandler`, hãy dùng MockMvc/WebTestClient thích hợp để assert HTTP status. Nếu transaction rollback là yêu cầu, hãy chạy test có transaction/persistence config thật và xác nhận DB state; chỉ log `@AfterThrowing` không đủ.

**Nguyên tắc test:** Một test cho **observability** và một test cho **business handling** là hai kiểm chứng khác nhau.

## 18. Lỗi thường gặp và cách sửa

| Triệu chứng / suy luận sai | Giải thích đúng | Hành động phù hợp |
| --- | --- | --- |
| “Đã log ở @AfterThrowing nên lỗi được xử lý” | Logging không catch/translate/fallback | Xác định handler thật và kiểm thử kết quả caller |
| “Không có @AfterThrowing nên không hề xảy ra lỗi” | Lỗi có thể bị catch nội bộ, kiểu/pointcut không match | Kiểm tra boundary, exception paths và negative cases |
| “@AfterThrowing nhận tất cả exceptions” | Chỉ matched method executions và typed binding | Scope rõ pointcut/throwable, thêm observability ở tầng đúng |
| “throwing=error tự catch exception” | `throwing` chỉ bind ngoại lệ vào tham số advice | Đặt catch/fallback ở tầng sở hữu hợp đồng |
| “Advice trả void nghĩa là swallowed exception” | Void callback hoàn tất không biến exceptional exit thành success | Assert `assertThrows`/caller catch |
| “Throwable parameter đủ để monitor mọi lỗi JVM” | Không vượt proxy, pointcut và join point limits | Dùng application-level error handling/monitoring bổ sung |
| “Spring transaction chắc rollback khi after-throwing log” | Rollback do tx policy/order/config | Test transaction outcome, rollback rules |
| “@AfterThrowing sẽ catch lỗi từ @AfterReturning cùng aspect” | Không phải general exception callback | Xem tài liệu và dùng outer observer rõ scope nếu cần |
| “Self-call khiến method inner luôn có AOP advice” | Self-invocation bypass proxy | Tách sang bean khác hoặc đổi đường gọi qua proxy |
| “Nhiều log nghĩa là nhiều lỗi nghiệp vụ độc lập” | Một failure có thể đi qua nhiều boundaries/attempts | Correlate theo logical operation |
| “Không cần handler web vì đã có aspect” | AOP observer không tạo HTTP response | Dùng @ExceptionHandler/@ControllerAdvice thích hợp |
| “Thêm catch Throwable trong @Around là luôn an toàn” | Có thể nuốt Error/che lỗi/cản rollback | Chỉ catch theo policy đã xác định, rethrow khi cần |
| “Logged exception message luôn an toàn” | Có thể có PII/secrets | Chuẩn hóa event schema, giới hạn dữ liệu |
| “Đo exception trong async method giống synchronous” | Future/publisher có completion boundary khác | Hook vào lifecycle thực của async/reaction |
| “Pointcut match một bean là đủ” | Method nào đó mới là unit được advice | Kiểm tra method-level matching, proxy reference |

### Quy trình chẩn đoán thực tế

1. **Xác minh aspect bean:** `@Aspect` được đăng ký bằng `@Component` hoặc `@Bean`; AOP đã bật.
2. **Xác minh target bean:** caller lấy đúng Spring-managed proxy, không dùng `new` hoặc unwrapped target.
3. **Xác minh pointcut:** method/class/package có thật sự match không?
4. **Xác minh kiểu throwing:** `Throwable`, `Exception` hay loại chuyên biệt?
5. **Xác minh source của lỗi:** target method, advice bên ngoài, transaction commit, async completion?
6. **Xác minh ai catch:** target, inner interceptor, outer `@Around`, caller, MVC exception resolver?
7. **Xác minh propagation:** test exception type, message, identity nếu cần.
8. **Xác minh side effects và trạng thái dữ liệu:** rollback/commit/fallback có đúng không?
9. **Xác minh counts:** một event observer có thể không tương ứng một logical error.
10. **Xác minh bảo mật log:** chỉ ghi thông tin cần thiết, không lộ request payload/credentials.

## 19. Bài tập vận dụng

**Câu 1.** Một `@AfterThrowing` log `IllegalArgumentException("bad")` rồi trả `void`. Nếu caller không catch, exception sẽ ra sao?

**Đáp án:** Exception vẫn tiếp tục lan truyền theo đường gọi Spring AOP bình thường, trừ khi một tầng khác chủ động xử lý. Việc advice return void không xóa exception.

**Câu 2.** Method target có `try/catch` bắt lỗi rồi trả `"RECOVERED"`. Vì sao observer after-throwing không chạy?

**Đáp án:** Tại Spring AOP method boundary đó là **normal return**, không phải exceptional exit. Lỗi tồn tại bên trong method nhưng đã được catch trước khi thoát.

**Câu 3.** Advice bind `IllegalArgumentException error`. Target ném `IllegalStateException`. Có chứng minh hệ thống không có lỗi chỉ vì observer không log không?

**Đáp án:** Không. Typed binding không tương thích exception đó; caller vẫn có thể nhận lỗi.

**Câu 4.** Một request đã trả HTTP 400, service after-throwing cũng log lỗi. Thành phần nào xử lý HTTP response?

**Đáp án:** Thành phần web exception resolution, ví dụ `@ExceptionHandler`/`@RestControllerAdvice`. Observer ở service không tự tạo HTTP 400.

**Câu 5.** Có @AfterThrowing log exception trong một `@Transactional` method. Có khẳng định DB chắc chắn rollback thành công không?

**Đáp án:** Không. Rollback chịu sự điều khiển của transaction interceptor, rollback rules, manager và advisor ordering; phải kiểm thử DB state và tx outcome.

**Câu 6.** Vì sao `this.submit(true)` có thể không sinh một log cho method submit nhưng vẫn sinh log cho method ngoài forwardInternally?

**Đáp án:** Self-invocation bỏ qua proxy đối với submit; khi exception thoát khỏi forwardInternally được caller gọi qua proxy, after-throwing quan sát **join point của forwardInternally**.

**Câu 7.** Một `@Around` outer bắt lỗi rồi trả fallback. @AfterThrowing inner có thể đã chạy không?

**Đáp án:** Có. Inner observer có thể đã thấy lỗi trước khi outer catch. Khi đó outer caller thấy normal return, dù inner đã ghi exception.

**Câu 8.** Một `@AfterThrowing` advice ném exception mới vì logging backend thất bại. Điều gì nguy hiểm?

**Đáp án:** Exception mới có thể che mất lỗi nghiệp vụ gốc và thay đổi behavior/transaction semantics. Instrumentation cần failure policy rõ.

**Câu 9.** Một method trả CompletableFuture ngay, rồi future mới hoàn tất thất bại. Có thể lấy @AfterThrowing ở method làm nguồn sự thật duy nhất cho failure không?

**Đáp án:** Không. Lỗi completion có thể xuất hiện sau method return và thuộc async lifecycle; phải quan sát completion với API thích hợp.

**Câu 10.** Phương pháp đúng để chứng minh một exception đã được xử lý là gì?

**Đáp án:** Xác định tầng sở hữu handling, rồi assert **kết quả thực tế**: caller nhận fallback, HTTP status đúng, transaction/DB state hợp lệ hoặc trạng thái nghiệp vụ đã phục hồi; không chỉ tìm dòng log từ AOP.

## 20. Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice: After Throwing Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): ngữ nghĩa khi method exits by throwing, `throwing` typed binding, và lưu ý **không phải general exception handling callback**.
- [Spring Framework — After Returning / After (Finally) Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): phân biệt normal return, exceptional exit và finally semantics.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB AOP proxies, self-invocation và ranh giới lời gọi.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký aspect bean và bật Spring AOP.
- [Spring Framework — Declaring Pointcuts](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): giới hạn method execution trong Spring-managed beans.
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules khác với việc aspect quan sát exception.
- [Spring Framework — MVC Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): dùng `@ExceptionHandler` để xử lý exceptions ở web layer.
