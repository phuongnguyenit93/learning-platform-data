# Spring AOP `@Before` — hành vi trước khi thực thi phương thức đích

## 1. Ý nghĩa của `@Before` trong Spring Aspect

`@Before` thuộc `org.aspectj.lang.annotation.Before`, dùng trong Spring AOP theo kiểu `@AspectJ` để khai báo **advice chạy trước một method execution mà pointcut chọn**, khi lời gọi thực tế đi qua **Spring AOP proxy**.

```java
@Aspect
@Component
public class TraceAspect {
    @Before("execution(* demo.before.SubmissionService.submit(..))")
    public void beforeSubmit() {
        System.out.println("[advice] before submit");
    }
}
```

Đoạn trên là **fragment minh họa** chưa gồm imports/package và đối tượng Spring target. Ý nghĩa:

- `@Aspect` đánh dấu class khai báo aspect; `@Component` hoặc phương thức `@Bean` làm aspect trở thành **Spring-managed bean**.
- Expression `execution(* demo.before.SubmissionService.submit(..))` chọn method `submit(..)` ở class đích tương ứng; không chọn tất cả method của ứng dụng.
- Khi một consumer gọi method **qua proxy** và pointcut khớp, Spring chạy `beforeSubmit()` trước khi cho execution tiếp tục đến method đích.
- Nếu advice hoàn thành bình thường, Spring tiếp tục chuỗi interceptor và thông thường đi đến target method, trừ trường hợp interceptor khác thay đổi luồng.
- Nếu `beforeSubmit()` **ném exception**, lời gọi không tiếp tục bình thường đến method đích; exception được truyền lên caller, trừ khi một interceptor khác xử lý nó.

**Phạm vi:** Spring AOP proxy-based, Spring IoC bean, pointcut và `@Aspect`. Đây không phải khái niệm AOP tổng quát hoặc cơ chế AspectJ compile-time/load-time weaving.

## 2. “Trước khi gọi phương thức đích” là trước thời điểm nào?

Trong Spring AOP, join point chính được hỗ trợ là **method execution** trên Spring-managed bean. Advice `@Before` chạy trước khi thân method đích được thực thi trong invocation được proxy chặn, không phải trước mọi thao tác Java dẫn tới method call.

```text
Consumer / controller (được Spring inject service)
             |
             | service.submit("S-001")
             v
       Spring AOP proxy
             |
     kiểm tra advisor/pointcut
             |
       interceptor chain
             |
         @Before advice
             |
       (advice kết thúc bình thường)
             |
             v
       Target.submit("S-001")
             |
             v
          Return / throw
             |
             v
         Quay lại caller
```

Quan sát cụ thể:

1. **Argument expression ở call site** đã được Java đánh giá trước khi method invocation đến proxy. `@Before` không chạy trước việc tạo ra argument, ví dụ `service.submit(buildRequest())`.
2. Target Spring bean đã trải qua khởi tạo và được proxy công bố (theo lifecycle thông thường); `@Before` **không phải** callback trước constructor hay trước `@PostConstruct`.
3. Trong chain có thể có các advice/interceptor khác. `@Before` được chạy **trước target execution**, nhưng không có bảo đảm nó là thành phần đầu tiên chạy trên toàn bộ request.
4. Advice được gọi cho **mỗi invocation được intercept và match**, không chỉ một lần khi context khởi động.
5. Nếu target có method đã match nhưng caller tự gọi `this.submit()` bên trong target, lời gọi này **không đi qua Spring proxy** và `@Before` sẽ không được kích hoạt riêng cho lời gọi nội bộ đó.

Một Spring method có thể được gọi bình thường dù **không** có advice nếu bean không được proxy, pointcut không khớp, hoặc lời gọi bypass proxy.

## 3. Điều kiện để `@Before` hoạt động

Trong một ứng dụng Spring Framework dùng annotation-style AOP, cần tất cả yếu tố sau:

1. **Target là Spring bean**: ví dụ class có `@Service` được component scan hoặc được đăng ký qua `@Bean`.
2. **Aspect cũng là Spring bean**: thường `@Aspect @Component` hoặc `@Bean`. `@Aspect` một mình không đồng nghĩa component scanner tự đăng ký bean.
3. **Hạ tầng Spring AOP được bật**: ví dụ `@EnableAspectJAutoProxy` trong `@Configuration` của Spring Framework thuần; Spring Boot có cơ chế auto-configuration khi dependency thích hợp sẵn có.
4. **Pointcut match phương thức**: phương thức đích phải thuộc class/package, tên, visibility, argument/annotation constraints do expression mô tả.
5. **Lời gọi đi qua proxy**: consumer dùng tham chiếu do Spring cung cấp (qua DI hoặc `ApplicationContext.getBean(...)`), không dùng object tự `new` rồi gọi trực tiếp.
6. **Method có thể intercept bằng loại proxy thực tế**: JDK dynamic proxy chủ yếu chặn public interface methods; CGLIB class proxy phụ thuộc khả năng subclass/override và có giới hạn với `final`/`private`.

### Cấu hình trong Spring Framework thuần

```java
package demo.before;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

Với ứng dụng Java 17+ Spring Framework 6.x và `@AspectJ`, thường dùng dependency Spring Context, Spring AOP và `aspectjweaver` để Spring phân tích pointcut. Không cần AspectJ compiler hoặc AspectJ load-time weaver để chạy **Spring AOP proxy**.

Trong Spring Boot, starter AOP có thể bật hạ tầng AOP. Spring Boot thường mặc định dùng CGLIB class-based proxy khi auto-configured AOP; Spring Framework thuần với `@EnableAspectJAutoProxy(proxyTargetClass=false)` ưu tiên JDK proxy nếu target có interface. Dù loại proxy nào, vẫn phải gọi **qua proxy** và có pointcut khớp.

## 4. Cách viết expression cho `@Before`

Giá trị annotation nhận **pointcut expression** trực tiếp hoặc tên của `@Pointcut` đã khai báo.

### 4.1. Inline pointcut

```java
@Before("execution(public * demo.before.SubmissionService.submit(..))")
public void beforeSubmit() {
    System.out.println("before submit");
}
```

Trong biểu thức:

- `execution(...)`: chọn method execution.
- `public`: chỉ public methods.
- `*`: return type bất kỳ.
- `demo.before.SubmissionService.submit`: type và method name.
- `(..)`: chấp nhận mọi danh sách argument types.

Nếu cần chính xác một argument kiểu `String`, có thể dùng:

```java
@Before("execution(* demo.before.SubmissionService.submit(java.lang.String))")
public void beforeSubmitString() {
    System.out.println("before String submit");
}
```

Các snippets này là phương án minh họa riêng, không dùng đồng thời với advice khác của cùng ví dụ nếu không chủ ý chạy nhiều advice.

### 4.2. Dùng named pointcut

```java
@Pointcut("execution(* demo.before.SubmissionService.submit(..))")
private void submissionOperation() {}

@Before("submissionOperation()")
public void auditSubmission() {
    System.out.println("before submission");
}
```

Đây là các method nằm **bên trong aspect**. Method `submissionOperation()` chỉ là tên khai báo pointcut; Java code trong body của nó không được gọi như business logic khi Spring đánh giá pointcut.

Visibility `private` của method `@Pointcut` chỉ ảnh hưởng quyền tham chiếu named pointcut theo luật Java, **không giới hạn target methods thành private**.

### 4.3. Ghép nhiều điều kiện với `&&`, `||`, `!`

```java
@Before(
    "within(demo.before..*)"
  + " && (execution(* submit*(..)) || execution(* cancel*(..)))"
  + " && !execution(* *Internal(..))"
)
public void beforePublicApi(JoinPoint joinPoint) {
    System.out.println(joinPoint.getSignature().getName());
}
```

Snippet này minh họa logic điều kiện. Muốn **chỉ public** hãy thêm `&& execution(public * *(..))`; việc đặt tên `beforePublicApi` không tự tạo ràng buộc visibility trong expression.

Dấu ngoặc quan trọng: `A || B && !C` được hiểu là `A || (B && !C)`, **khác** `(A || B) && !C`. Một điều kiện phủ định thiếu ngoặc có thể loại nhầm hoặc bỏ sót method.

### 4.4. Match theo Spring bean hoặc annotation

Spring có pointcut designator riêng `bean(...)` (lọc theo bean name):

```java
@Before("bean(*SubmissionService) && execution(* submit(..))")
public void beforeNamedBeans() {
    System.out.println("before named bean");
}
```

Đây chỉ là ví dụ expression: bean name thực tế phải khớp mẫu; mặc định `@Service` trên `SubmissionService` thường cho tên bean `submissionService`, khác hoa/thường. Mẫu `*SubmissionService` không tự match bean `submissionService` nếu quy tắc ký tự không phù hợp. Với tên bean theo mặc định, có thể thay bằng `bean(submissionService)`. Do đó phải kiểm tra bean name thực tế.

Với method annotation tùy chỉnh, có thể dùng `@annotation(com.example.Audited)` để chọn những method có annotation được nhận diện theo quy tắc pointcut. Annotation phải là một type hợp lệ, được đăng ký/đặt nơi framework có thể quan sát; ví dụ không tuyên bố custom annotation tự có behavior trước khi có aspect.

## 5. Dữ liệu advice có thể đọc bằng `JoinPoint`

Spring AOP có thể truyền `org.aspectj.lang.JoinPoint` làm **tham số đầu tiên** trong before advice:

```java
@Before("execution(* demo.before.SubmissionService.submit(..))")
public void beforeSubmit(JoinPoint joinPoint) {
    String methodName = joinPoint.getSignature().getName();
    Object[] args = joinPoint.getArgs();
    System.out.println("[advice] " + methodName + ": " + args.length);
}
```

Với `JoinPoint`:

| API | Ý nghĩa trong Spring AOP |
| --- | --- |
| `joinPoint.getSignature()` | Method signature, trong đó có tên method |
| `joinPoint.getArgs()` | Array chứa argument values của invocation hiện tại |
| `joinPoint.getThis()` | Reference **Spring AOP proxy** |
| `joinPoint.getTarget()` | Target object đứng sau proxy |

Lưu ý `getThis()` và `getTarget()` có thể là **hai object khác nhau** khi Spring dùng proxy. Với JDK proxy, `getThis()` có kiểu proxy interface, không phải concrete implementation. Không cast tùy ý sang implementation class.

`getArgs()` cho phép đọc argument để ghi log, metric hoặc kiểm tra; đừng tự ý log mật khẩu, token, dữ liệu cá nhân hoặc toàn bộ payload nhạy cảm. Nó không tạo một contract ổn định để **thay đổi argument mà target sẽ nhận** bằng cách gán lại phần tử trong array do `getArgs()` trả về.

### Bind argument qua `args(...)`

Thay vì tự đọc array, có thể bind argument vào advice parameter:

```java
@Before(
    value = "execution(* demo.before.SubmissionService.submit(..)) && args(orderId)",
    argNames = "orderId"
)
public void beforeSubmit(JoinPoint joinPoint, String orderId) {
    System.out.println("[advice] submit " + orderId);
}
```

Đây là một fragment alternative. `JoinPoint` là tham số đặc biệt đầu tiên; `argNames` ghi rõ cách bind `orderId` cho các trường hợp không có Java parameter-name metadata. Nếu pointcut thực tế có nhiều arguments, cần biểu thức `args(...)` và signature tương ứng. Không suy đoán rằng annotation tự biết tên argument khi không được cung cấp metadata/binding thích hợp.

### Dữ liệu nào không sẵn trước execution?

Before advice không có **giá trị trả về** hoặc **exception do target sắp ném** vì target chưa chạy. Do đó:

- Muốn xử lý return value sau khi method thành công, dùng `@AfterReturning`.
- Muốn xử lý exception do target method ném, dùng `@AfterThrowing`.
- Muốn code chạy sau method dù thành công/thất bại, dùng `@After` với finally semantics.
- Muốn chủ động kiểm soát có `proceed()` hay không, thay arguments khi proceed hoặc thay return value theo contract, cân nhắc `@Around`.

`@Before` là lựa chọn rõ nhất khi chỉ cần chuẩn bị, log, bắt đầu đo, validate một điều kiện và cho method tiếp tục bình thường.

## 6. Nếu `@Before` ném ngoại lệ thì sao?

Điều kiện “advice chạy trước method” dễ khiến người học nghĩ before advice **không thể** ngăn method thực thi. Spring mô tả chính xác: trước advice **không thể chủ động quyết định bỏ qua execution** như `@Around`; **ngoại lệ duy nhất là khi advice ném exception**, khiến luồng execution bình thường bị ngắt.

Ví dụ:

```java
@Before("execution(* demo.before.SubmissionService.submit(..))")
public void validateBefore(JoinPoint jp) {
    String id = (String) jp.getArgs()[0];
    if ("DENY".equals(id)) {
        throw new IllegalArgumentException("blocked by before advice");
    }
}
```

Đoạn này là một phương án advice minh họa, không phải ví dụ đầy đủ độc lập. Khi caller gọi `service.submit("DENY")` qua proxy:

1. Pointcut match và advice bắt đầu.
2. Advice ném `IllegalArgumentException`.
3. Target `submit("DENY")` **không được gọi** trong luồng bình thường của invocation này.
4. Exception được truyền ngược qua interceptor chain, nơi những interceptor bao ngoài có thể quan sát/xử lý nó.
5. Advice `@AfterThrowing` đang áp dụng lên **target method** cũng có hành vi phụ thuộc chuỗi interceptor/advice và loại exception; không nên mặc định mọi after-throwing advice đều có log theo đúng một thứ tự nếu chưa cấu hình ordering.

**Điểm không được nhầm:** ném exception trong before advice có thể từ chối cuộc gọi, nhưng điều này không biến before advice thành `@Around`. Before advice không có `ProceedingJoinPoint.proceed()`, không thể tự chọn return value thay thế cho caller.

Cần thận trọng nếu dùng `@Before` để làm authorization: các phương thức không đi qua proxy (self-invocation, object tự tạo) **không được aspect kiểm tra**. Bảo đảm an ninh nên dùng kiến trúc ranh giới đáng tin và Spring Security hoặc các kiểm soát bổ trợ thích hợp, thay vì coi custom `@Before` là chốt bảo vệ duy nhất.

## 7. Ví dụ chạy được — Java 17 + Spring Framework 6.2 + Maven

Ví dụ dưới đây không dùng Spring Boot để thể hiện rõ điều kiện tạo Spring AOP proxy. Các hành vi được kiểm chứng qua log:

1. `@Before` chạy trước `submit("OK")`.
2. `@Before` có thể **ném exception**, khiến `submit("DENY")` không chạy.
3. Nếu **target tự ném exception** sau khi before advice kết thúc, before advice vẫn đã chạy.
4. Pointcut không khớp `cancel(...)` thì không có advice.
5. Target `runBatch()` tự gọi `this.submit("INNER")` nên lời gọi nội bộ bypass proxy.

### 7.1. Cấu trúc file

```text
spring-before-advice/
├── pom.xml
└── src/main/java/demo/before/
    ├── AppConfig.java
    ├── SubmissionOperations.java
    ├── SubmissionService.java
    ├── AuditAspect.java
    └── Main.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-before-advice</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Các thư viện này đủ cho ứng dụng Spring Framework thuần dùng `@AspectJ` theo kiểu Spring AOP proxy. Cần Maven và JDK 17+ có khả năng tải dependencies từ repository.

### 7.3. `AppConfig.java`

```java
package demo.before;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` phát hiện target `@Service` và aspect `@Component`. `@EnableAspectJAutoProxy` kích hoạt hạ tầng tạo AOP proxy. Với target có interface và `proxyTargetClass=false`, ví dụ dùng **JDK dynamic proxy**.

### 7.4. `SubmissionOperations.java`

```java
package demo.before;

public interface SubmissionOperations {
    void submit(String id);
    void cancel(String id);
    void runBatch();
}
```

Spring có thể tạo JDK proxy triển khai interface này. Consumer nhận dependency theo `SubmissionOperations` chứ không giả định proxy kế thừa class `SubmissionService`.

### 7.5. `SubmissionService.java`

```java
package demo.before;

import org.springframework.stereotype.Service;

@Service
public class SubmissionService implements SubmissionOperations {
    @Override
    public void submit(String id) {
        System.out.println("[target] submit " + id);
        if ("TARGET_FAIL".equals(id)) {
            throw new IllegalStateException("target failed");
        }
    }

    @Override
    public void cancel(String id) {
        System.out.println("[target] cancel " + id);
    }

    @Override
    public void runBatch() {
        System.out.println("[target] batch");
        this.submit("INNER");
    }
}
```

Method `submit("TARGET_FAIL")` **in ra dòng target trước**, rồi ném exception. Điều này cho phép đối chiếu thứ tự `@Before` với logic target. `this.submit("INNER")` là self-invocation, nên sẽ không tự đi qua proxy.

### 7.6. `AuditAspect.java`

```java
package demo.before;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* demo.before.SubmissionService.submit(..))")
    public void beforeSubmit(JoinPoint joinPoint) {
        String id = (String) joinPoint.getArgs()[0];

        System.out.println("[advice] before submit " + id);

        if ("DENY".equals(id)) {
            throw new IllegalArgumentException("blocked by before advice");
        }
    }
}
```

Advice có đúng một declaration và chỉ match `submit(..)`. Nó không match `cancel()` hay `runBatch()`. Để minh họa từ chối lời gọi, advice ném exception khi `id` là `"DENY"`. Trong production, không dùng in log dữ liệu người dùng tùy tiện và không xem custom aspect là thay thế đầy đủ cho bảo mật.

### 7.7. `Main.java`

```java
package demo.before;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            SubmissionOperations service =
                    context.getBean(SubmissionOperations.class);

            System.out.println("[main] jdkProxy="
                    + AopUtils.isJdkDynamicProxy(service));

            service.submit("OK");

            try {
                service.submit("DENY");
            } catch (IllegalArgumentException ex) {
                System.out.println("[caller] " + ex.getMessage());
            }

            try {
                service.submit("TARGET_FAIL");
            } catch (IllegalStateException ex) {
                System.out.println("[caller] " + ex.getMessage());
            }

            service.cancel("C-1");
            service.runBatch();
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.before.Main
```

**Stdout từ các câu lệnh `System.out` của chương trình** (không tính log Maven/Spring có thể phát sinh tùy môi trường):

```text
[main] jdkProxy=true
[advice] before submit OK
[target] submit OK
[advice] before submit DENY
[caller] blocked by before advice
[advice] before submit TARGET_FAIL
[target] submit TARGET_FAIL
[caller] target failed
[target] cancel C-1
[target] batch
[target] submit INNER
```

### 7.8. Phân tích stdout từng lời gọi

| Lời gọi từ `Main` | Advice `@Before` | Target | Kết quả |
| --- | --- | --- | --- |
| `submit("OK")` | In `before submit OK` | In `submit OK` | Hoàn tất bình thường |
| `submit("DENY")` | In `before submit DENY` rồi ném exception | **Không chạy** | Caller bắt `IllegalArgumentException` |
| `submit("TARGET_FAIL")` | In `before submit TARGET_FAIL` | In `submit TARGET_FAIL` rồi ném exception | Caller bắt `IllegalStateException` |
| `cancel("C-1")` | Không khớp pointcut | In `cancel C-1` | Hoàn tất bình thường |
| `runBatch()` | Không khớp pointcut của chính method này | In `batch` | Gọi nội bộ `this.submit("INNER")` |
| `this.submit("INNER")` trong target | **Không chạy** | In `submit INNER` | Self-invocation bypass proxy |

Ví dụ cố ý chỉ có một advice cho method `submit()` để tránh phụ thuộc vào thứ tự của nhiều before advices. Code không tự chạy advice khi `this.submit()` từ target vì đây là lời gọi không đi qua Spring proxy.

### 7.9. Thử nghiệm tự kiểm tra

**Thử nghiệm A — Đổi pointcut sang `cancel(..)`**

Thay annotation trong `AuditAspect` bằng:

```java
@Before("execution(* demo.before.SubmissionService.cancel(..))")
```

Khi chạy lại, chỉ `cancel("C-1")` từ caller qua proxy mới kích hoạt advice. Chú ý ví dụ hiện tại vẫn có tên log “before submit” và logic DENY: **đó chỉ là nhãn/logic cũ của advice**; khi thực hiện thí nghiệm thật nên đổi tên log và validation tương ứng với `cancel`. Không suy ra dữ liệu log tự đổi theo pointcut.

**Thử nghiệm B — Bỏ `@Component` trên aspect**

Nếu aspect không còn được Spring quản lý qua `@Component` hoặc `@Bean`, advice không được đăng ký. Target vẫn có thể là Spring bean, nhưng không còn before advice này.

**Thử nghiệm C — Dùng `new SubmissionService()`**

```java
SubmissionOperations outsideSpring = new SubmissionService();
outsideSpring.submit("OK");
```

Snippet trên tạo object Java không phải Spring bean proxy. Dòng `[target] submit OK` vẫn xuất hiện, nhưng không có `[advice]` trước nó.

**Thử nghiệm D — Chuyển sang CGLIB**

Thay `@EnableAspectJAutoProxy(proxyTargetClass = true)`. Target không final nên class proxy hợp lệ. Trong `Main`, `isJdkDynamicProxy(service)` sẽ thành `false`, nhưng `@Before` vẫn có thể chạy qua proxy; `this.submit("INNER")` vẫn bypass.

## 8. `@Before` so với các loại advice khác trong Spring

| Advice trong Spring AOP | Thời điểm | Có return/exception của target? | Khả năng kiểm soát |
| --- | --- | --- | --- |
| `@Before` | Trước method execution được pointcut chọn | Chưa có return/exception của target | Không chủ động `proceed()`/thay return; có thể ngắt bằng exception |
| `@AfterReturning` | Sau khi target hoàn tất bình thường | Có thể bind return value | Quan sát kết quả thành công; không dùng như `@Around` để tự thay return |
| `@AfterThrowing` | Khi execution kết thúc bằng exception | Có thể bind exception | Ghi log/thực hiện handling liên quan lỗi |
| `@After` | Sau execution bất kể kết thúc bình thường hay exceptional, theo finally semantics | Không dùng để thay return | Dọn dẹp/tác vụ cuối |
| `@Around` | Bao quanh join point | Có thể quan sát return/exception qua `proceed()` | Chủ động chọn thời điểm/có gọi `proceed()` và return gì |

Mục tiêu trước method **thực sự cần làm gì?**

- Nếu chỉ cần log/metric trước khi target bắt đầu, `@Before` có ý nghĩa rõ ràng.
- Nếu cần đo chính xác duration **bao gồm kết quả method**, một `@Around` với `try/finally` có thể phù hợp hơn.
- Nếu cần đổi return value, bỏ qua method mà không ném exception, hoặc thay arguments khi proceed, đó là hành vi của `@Around`, không phải `@Before`.
- Nếu cần xử lý exception sau target, đừng cố đoán exception tương lai trong before advice; dùng loại advice phù hợp.

Dùng loại advice **ít quyền lực nhất đáp ứng yêu cầu** để dễ đọc và giảm sai sót trong Spring application.

## 9. Thứ tự của nhiều before advices

Khi một method được nhiều aspects/advisors match, bạn không thể suy ra thứ tự log từ vị trí class trong thư mục, thứ tự bean được scan, hoặc thứ tự khai báo source code.

Spring hỗ trợ chỉ định precedence cho các aspect khác nhau bằng `@Order` hoặc interface `Ordered`. **Giá trị order nhỏ hơn thể hiện precedence cao hơn** ở những nơi Spring áp dụng quy tắc ordering này.

```java
@Aspect
@Component
@Order(1)
public class FirstAspect {
    @Before("execution(* demo.before.SubmissionService.submit(..))")
    public void first() {
        System.out.println("[first] before");
    }
}
```

```java
@Aspect
@Component
@Order(2)
public class SecondAspect {
    @Before("execution(* demo.before.SubmissionService.submit(..))")
    public void second() {
        System.out.println("[second] before");
    }
}
```

Đây là hai fragments cần imports `org.springframework.core.annotation.Order`, `org.aspectj.lang.annotation.Aspect`, `org.aspectj.lang.annotation.Before` và `org.springframework.stereotype.Component`. Nếu đăng ký cả hai và target method khớp, aspect precedence cao hơn thường chạy trước trong đường vào. Nhưng còn các interceptor như transaction/security và thứ tự advisor chain cần xét trong hệ thống thật.

Đối với nhiều advices trong **cùng aspect class**, không nên trông cậy vào **thứ tự source code** như một hợp đồng ổn định. Khi order có ý nghĩa nghiệp vụ, hãy tổ chức rõ trách nhiệm và kiểm thử chain thực tế.

**Không đồng nhất `@Order` với thứ tự khởi tạo bean.** Nó dùng trong cơ chế ordering áp dụng, không bảo đảm constructor hay `@PostConstruct` theo thứ tự đó.

## 10. Bẫy thường gặp trong Spring

### 10.1. `@Aspect` chưa phải Spring bean

```java
@Aspect
public class BeforeAspect {
    @Before("execution(* demo.before..*Service.*(..))")
    public void log() {}
}
```

Nếu chỉ tạo class như trên mà không đăng ký nó là Spring bean, AOP auto-proxy creator không nhất thiết sử dụng aspect đó. Cần `@Component` trong phạm vi scan hoặc đăng ký qua `@Bean`. Đừng gọi `new BeforeAspect()` từ code riêng để hy vọng Spring tự biết.

### 10.2. Self-invocation và đối tượng ngoài Spring

```java
public void outer() {
    this.inner(); // Không đi qua AOP proxy.
}
```

Dù `inner()` có public và pointcut match, self-invocation bypass. Giải pháp dễ bảo trì là tách `inner()` thành method của **bean khác**, inject và gọi qua Spring reference, thay vì chỉ bật CGLIB.

### 10.3. Private, static, final và method không công bố qua interface

- Private method không thể được advice bằng JDK proxy hoặc CGLIB.
- Static method không phải instance proxy invocation.
- Với CGLIB, `final method` không thể được override để intercept; `final class` không thể subclass.
- Với JDK proxy, **public method thuộc interface** có thể được intercept dù implementation method là final, vì proxy chặn interface boundary.
- Public method chỉ có ở implementation (không thuộc interface) không được JDK proxy công bố cho consumer interface.

Không thể sửa các ranh giới này chỉ bằng cách viết `@Before("execution(...")` rộng hơn.

### 10.4. Pointcut không khớp target

Nếu dùng `execution(* demo.before.OtherService.submit(..))` nhưng bean thật là `SubmissionService`, Spring không chạy advice cho method mong muốn. Kiểm tra class/package cụ thể, loại proxy, method signature, visibility và điều kiện bổ sung.

### 10.5. Bẫy khi log input trong before advice

Trong production, dùng structured logging và **redaction** cho tham số nhạy cảm. `JoinPoint.getArgs()` có thể chứa đối tượng mutable, stream, file, token hoặc request data lớn. Không gọi `toString()` tùy tiện trên toàn bộ arguments và không dùng logging như cơ chế kiểm soát quyền truy cập.

### 10.6. Ngoại lệ của before advice không phải ngoại lệ của target

Nếu `@Before` ném exception, target chưa chạy. Khi debug cần phân biệt stack trace và log cho biết lỗi phát sinh **từ advice** hay **sau đó trong target**. Nếu lỗi target diễn ra, before advice vẫn đã hoàn thành trước nó. Đừng kết luận “advice không chạy” chỉ vì method cuối cùng ném exception.

### 10.7. `@Before` chạy một lần hay nhiều lần?

Nó chạy trên mỗi matched invocation **qua proxy**. Ví dụ một API endpoint bị gọi 10 lần khiến business method chạy qua proxy 10 lần thì before advice có thể chạy tương ứng 10 lần; không phải “khởi động Spring chạy trước một lần”. Tuy nhiên, nếu nội bộ target gọi cùng method bằng `this`, các lời gọi đó không được tính như lần intercept mới của Spring proxy.

### 10.8. Không mặc định `@Before` và `@Transactional` có order cố định

Spring declarative transaction thường cũng dùng proxy/interceptor. Nếu một before advice nằm **ngoài** transaction interceptor, nó có thể chạy trước khi transaction bắt đầu; nếu nằm **bên trong**, nó có thể chạy khi transaction đã mở. Thứ tự phụ thuộc advisor ordering, không thể tự suy ra chỉ từ việc cả hai annotation cùng tồn tại. Nếu aspect cần transaction đang active, phải thiết kế order rõ ràng và test.

## 11. Checklist chẩn đoán “@Before không chạy”

| Triệu chứng | Cách kiểm tra / giải pháp |
| --- | --- |
| Method service chạy nhưng không có log `@Before` | Kiểm tra target có phải Spring bean, aspect có được đăng ký, `@EnableAspectJAutoProxy` hoặc Boot AOP auto-config |
| `@Aspect` tồn tại nhưng không có advice | Đăng ký aspect qua `@Component`/`@Bean`, bảo đảm component scan đúng package |
| Có AOP proxy nhưng `@Before` không chạy cho method A | Pointcut không match A, hoặc lời gọi A bypass proxy |
| `this.method()` không có advice | Self-invocation, cần gọi qua bean khác được inject |
| `new SomeService().method()` không có advice | Object ngoài container, không có Spring proxy |
| JDK proxy không expose method cụ thể | Inject qua interface chứa method hoặc cân nhắc CGLIB phù hợp |
| CGLIB method `final`/`private` không advice | Không override được; đổi ranh giới method/bean |
| Method bị chặn mà không thấy log target | Before advice có thể ném exception trước target |
| Before log xuất hiện nhưng target ném exception | Đây là hành vi bình thường: before chạy trước target |
| Cần return value trong before advice | Chuyển sang `@AfterReturning` hoặc `@Around` |
| Muốn advice điều chỉnh argument hoặc bỏ qua target | Cân nhắc `@Around` và `ProceedingJoinPoint` |
| Nhiều advice chạy không theo thứ tự mã nguồn | Dùng `@Order`/`Ordered` giữa aspects và integration test |
| Chỉ thấy advice trên direct call mà không có trên lời gọi từ batch | Lời gọi nội bộ trong target dùng `this`, bypass proxy |

**Quy trình điều tra hữu ích:**

1. Xác định bean đích có được tạo/tra cứu bởi Spring chứ không phải `new`.
2. Xác nhận aspect cũng là Spring bean và `@Before` reference pointcut đúng.
3. Kiểm tra auto-proxy creator/enable AOP và `AopUtils.isAopProxy(bean)` trên **reference consumer thực nhận**.
4. Nếu dùng JDK, kiểm tra method nằm trên interface; nếu CGLIB, kiểm tra method có thể override.
5. Kiểm tra caller gọi **qua proxy** hay từ `this` trong target.
6. Đặt điểm quan sát trong advice và method target; thử case bình thường, case advice ném exception và case target ném exception.
7. Nếu nhiều advices/interceptors, kiểm tra ordering thực tế trước khi kết luận sai thứ tự.
8. Giữ logic trong before advice nhỏ, dễ kiểm soát side effects và log an toàn.

## 12. Câu hỏi tự đánh giá

**1. `@Before` chạy trước khi argument của Java call được tạo ra không?** Không. Nó chạy sau khi invocation tới proxy với arguments đã được Java đánh giá, nhưng trước khi method đích bắt đầu thực thi.

**2. Advice `@Before` có thể lấy return value của target để log không?** Không, target chưa chạy. Dùng `@AfterReturning` hoặc `@Around` khi yêu cầu return value.

**3. `@Before` có thể ngăn method chạy không?** Nó không có `proceed()` để chọn bỏ qua execution, nhưng nếu advice **ném exception** thì target không được gọi theo đường execution bình thường.

**4. Vì sao có `@Before` rồi mà `this.submit()` không bị intercept?** Spring AOP chỉ nhận lời gọi qua proxy; `this.submit()` là lời gọi trên target.

**5. `@Aspect` có đủ để Spring tự đăng ký aspect bean không?** Không. Phải đăng ký bằng component scan qua `@Component` hoặc bean definition/`@Bean` phù hợp.

**6. Khi có ba lần gọi `submit()` qua proxy, before advice chạy mấy lần?** Nếu cả ba match và không bị interceptor trước đó bỏ qua, before advice thường chạy ba lần (mỗi invocation một lần); không phải một lần khi khởi động.

**7. `JoinPoint.getThis()` và `getTarget()` có luôn giống nhau không?** Không. Với Spring AOP proxy, `getThis()` biểu diễn proxy, `getTarget()` biểu diễn target; có thể là hai Java objects khác nhau.

**8. Có thể dùng `@Order` để bảo đảm toàn bộ constructor, postconstruct, transaction và before advice theo cùng một thứ tự không?** Không. Ordering advice/advisors khác với lifecycle bean initialization; cần hiểu từng cơ chế và test.

## Tham khảo tài liệu Spring chính thức

- [Spring Framework — Declaring Advice / Before Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — AOP Concepts, Before Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-defn.html)
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — Ordering Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html#advice-ordering)
