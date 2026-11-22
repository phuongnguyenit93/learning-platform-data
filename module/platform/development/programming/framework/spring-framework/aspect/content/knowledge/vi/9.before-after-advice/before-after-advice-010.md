# Ví dụ ghi nhận lời gọi trên Spring bean bằng từng loại advice

## 1. Mục tiêu bài học

Trong Spring Framework, một `@Aspect` có thể khai báo advice để **ghi nhận việc gọi phương thức của Spring bean** ở nhiều thời điểm: trước lời gọi, khi trả về thành công, khi ném ngoại lệ, khi kết thúc bất kể kết quả và trong toàn bộ quá trình thực thi. Các loại tương ứng:

- `@Before` — trước method execution.
- `@AfterReturning` — khi method execution hoàn thành bình thường.
- `@AfterThrowing` — khi method execution thoát bằng exception phù hợp.
- `@After` — sau method execution theo ngữ nghĩa *finally*.
- `@Around` — bao quanh method execution; có thể tự quyết định có gọi tiếp hay không qua `ProceedingJoinPoint.proceed()`.

Bài tập trung vào **cách dùng năm loại advice trong Spring AOP**, Spring-managed beans, pointcut áp dụng và log quan sát được. Không trình bày lại lý thuyết Aspect tổng quát hay AspectJ weaving ngoài Spring.

**Điều quan trọng đầu tiên:** Spring AOP là cơ chế **proxy-based**. Mọi trace trong bài được tạo khi một client gọi method **trên Spring bean proxy**, không phải khi gọi object được tạo thủ công bằng `new` ở ngoài container.

## 2. Một lời gọi qua Spring AOP proxy diễn ra thế nào?

```text
Client
  |
  | gọi method trên bean nhận từ ApplicationContext
  v
Spring AOP proxy
  |
  | chọn advisor/interceptor có pointcut khớp method
  v
Advice chain
  |
  | chạy logic BEFORE/AROUND ở nhánh vào
  v
Target.method()
  |
  | normal return hoặc exception
  v
Advice chain
  |
  | AFTER_RETURNING / AFTER_THROWING / AFTER / AROUND tương ứng
  v
Client nhận result hoặc exception
```

Trong Spring, `@Aspect` class phải được **đăng ký thành Spring bean** để các advice được nhận diện (ví dụ `@Component` được quét hoặc `@Bean` trong cấu hình). Với Spring Framework thuần, có thể bật xử lý `@AspectJ` bằng `@EnableAspectJAutoProxy`.

Khi aspect có pointcut:

```java
@Before("execution(* demo.service..*.*(..))")
public void beforeAnyServiceCall() {
    System.out.println("BEFORE service");
}
```

Spring không chèn mã vào mọi class theo cách compile-time weaving. Nó tạo proxy cho các target beans có advisors phù hợp; **lời gọi đi qua proxy** mới kích hoạt advice. Snippet trên chỉ là một method cần đặt trong Spring-managed `@Aspect` bean, không phải chương trình Java độc lập.

### Năm loại advice trong một bảng

| Loại advice | Sự kiện nhận biết | Có thể quan sát | Có quyền gọi `proceed()`? |
| --- | --- | --- | --- |
| `@Before` | Trước method target | Join point signature, arguments, proxy/target | Không |
| `@AfterReturning` | Method trả bình thường | Return value qua `returning` | Không |
| `@AfterThrowing` | Method ném ngoại lệ phù hợp | Throwable qua `throwing` | Không |
| `@After` | Sau method, dù thành công/lỗi | Cleanup/log kết thúc | Không |
| `@Around` | Bao quanh toàn bộ thực thi còn lại | Trước, sau, return hoặc exception | **Có**, qua `ProceedingJoinPoint` |

**Chọn loại advice đơn giản nhất đáp ứng mục tiêu.** Nếu chỉ cần in một dòng trước method, ưu tiên `@Before` thay vì `@Around`, vì around advice có thể vô tình chặn luôn lời gọi nếu quên `proceed()`.

## 3. Ví dụ 1 — ghi nhận trước lời gọi với `@Before`

Một `@Before` advice chạy **trước khi method được chọn thực thi**.

```java
@Aspect
public class CallTraceAspect {
    @Before("execution(* demo..*.beforeCase(..))")
    public void beforeCall(JoinPoint jp) {
        System.out.println("BEFORE " + jp.getSignature().getName());
    }
}
```

Trong đoạn minh họa này, `JoinPoint.getSignature().getName()` cho biết tên method tại join point; có thể lấy `jp.getArgs()` để xem tham số khi cần.

**Ví dụ đường thành công:**

```text
BEFORE beforeCase
TARGET beforeCase false
CLIENT value=BEFORE-OK
```

**Ví dụ đường lỗi:**

```text
BEFORE beforeCase
TARGET beforeCase true
CLIENT caught IllegalStateException:before failed
```

Điểm cần nhớ:

1. `@Before` chạy trước target **ở cả nhánh thành công và nhánh thất bại**, nếu lời gọi đã đi qua proxy và match pointcut.
2. Advice có thể ném exception làm lời gọi dừng lại; nhưng nó không dùng `proceed()` để quyết định phần còn lại như `@Around`.
3. Nếu target tự gọi `this.beforeCase(...)` trong nội bộ, lời gọi đó không tự vào lại proxy; do đó không có một lần `@Before` mới cho riêng lời gọi nội bộ.
4. Khi log arguments, tránh đưa mật khẩu, access token hoặc dữ liệu nhạy cảm vào log.

Các code blocks ngắn ở từng mục là **mã minh họa**, còn ví dụ Maven hoàn chỉnh có thể chạy được đặt ở mục 8.

## 4. Ví dụ 2 — chỉ ghi khi thành công với `@AfterReturning`

`@AfterReturning` chạy khi **method execution kết thúc bình thường**, kể cả method trả `null` (với binding tương thích), chứ không dựa vào tên status code hoặc giá trị return có nghĩa “thất bại” ở nghiệp vụ.

```java
@AfterReturning(
    pointcut = "execution(* demo..*.successCase(..))",
    returning = "result",
    argNames = "result"
)
public void afterSuccess(String result) {
    System.out.println("AFTER_RETURNING result=" + result);
}
```

Ở đây:

- `pointcut` chọn method execution.
- `returning = "result"` bind kết quả vào tham số có tên `result`.
- Kiểu `String` của tham số cũng **giới hạn kiểu giá trị trả về** có thể match. Nếu muốn nhận kiểu rộng hơn, dùng `Object`.
- `argNames` chỉ rõ binding name, tránh phụ thuộc vào khả năng suy tên tham số từ bytecode.

**Nhánh thành công:**

```text
TARGET successCase false
AFTER_RETURNING result=SUCCESS-OK
CLIENT value=SUCCESS-OK
```

**Nhánh ném lỗi:**

```text
TARGET successCase true
CLIENT caught IllegalStateException:return failed
```

Ở nhánh lỗi, dòng `AFTER_RETURNING` không xuất hiện. Một method trả về `"FAIL"` nhưng không ném exception vẫn là **normal return** và có thể kích hoạt `@AfterReturning`.

### `@AfterReturning` không dùng để thay return value

Method `afterSuccess(...)` là một advice nhận kết quả, không phải một factory method thay kết quả của target. Trả một value mới từ advice này **không thay đổi reference mà client nhận**. Nếu cần đổi kết quả (ví dụ fallback/cache), dùng `@Around`.

## 5. Ví dụ 3 — ghi ngoại lệ với `@AfterThrowing`

`@AfterThrowing` chạy khi execution được chọn **thoát bằng exception**; thuộc tính `throwing` cho phép bind đối tượng exception và giới hạn kiểu nó nhận.

```java
@AfterThrowing(
    pointcut = "execution(* demo..*.throwingCase(..))",
    throwing = "error",
    argNames = "error"
)
public void afterInvalid(IllegalArgumentException error) {
    System.out.println(
        "AFTER_THROWING "
            + error.getClass().getSimpleName()
            + ":" + error.getMessage()
    );
}
```

Trong ví dụ, advice chỉ nhận `IllegalArgumentException` hoặc subclass, không nhận `IllegalStateException`, dù cả hai đều là runtime exceptions. Nếu muốn quan sát mọi loại throwable, có thể dùng `Throwable` (và cần xử lý trường hợp `Error` phù hợp).

**Ngoại lệ đúng kiểu:**

```text
TARGET throwingCase argument
AFTER_THROWING IllegalArgumentException:bad argument
CLIENT caught IllegalArgumentException:bad argument
```

**Ngoại lệ khác kiểu:**

```text
TARGET throwingCase state
CLIENT caught IllegalStateException:bad state
```

**Không có ngoại lệ:**

```text
TARGET throwingCase ok
CLIENT value=THROW-OK
```

Spring gọi advice cho exception phù hợp; method advice return `void` **không làm caller hết nhận exception**. `@AfterThrowing` dành cho ghi log/metrics, không phải cơ chế thay thế việc catch/recover bằng result mới.

Một ngoại lệ được target tự catch rồi trả bình thường **không kích hoạt** `@AfterThrowing`, vì nó không thoát khỏi method execution tại ranh giới Spring AOP.

## 6. Ví dụ 4 — luôn ghi khi kết thúc với `@After`

`@After` trong Spring @AspectJ AOP mang ý nghĩa **finally advice**: nó được thực thi bất kể method được chọn kết thúc bình thường hay bằng exception.

```java
@After("execution(* demo..*.finallyCase(..))")
public void afterCompletion(JoinPoint jp) {
    System.out.println("AFTER_FINALLY " + jp.getSignature().getName());
}
```

**Khi trả thành công:**

```text
TARGET finallyCase false
AFTER_FINALLY finallyCase
CLIENT value=FINALLY-OK
```

**Khi ném exception:**

```text
TARGET finallyCase true
AFTER_FINALLY finallyCase
CLIENT caught IllegalStateException:finally failed
```

`@After` thích hợp cho việc ghi nhận “đã kết thúc method execution”, giải phóng tài nguyên theo contract đã xác định, hoặc metric số lần thực thi. Nó **không cho biết kết quả bình thường hay lỗi theo mặc định**; muốn riêng từng nhánh, dùng `@AfterReturning` / `@AfterThrowing` hoặc `@Around`.

**Khác với `@AfterThrowing`:** `@After` vẫn chạy khi target trả bình thường. **Khác với `@AfterReturning`:** `@After` vẫn chạy khi target ném exception.

## 7. Ví dụ 5 — bao quanh và ghi cả hai nhánh với `@Around`

`@Around` có khả năng ghi trước, ghi sau, quan sát giá trị và lỗi, đồng thời kiểm soát phần chain tiếp theo bằng `ProceedingJoinPoint.proceed()`.

```java
@Around("execution(* demo..*.aroundCase(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("AROUND enter");
    try {
        Object value = pjp.proceed();
        System.out.println("AROUND return " + value);
        return value;
    } catch (Throwable error) {
        System.out.println(
            "AROUND throw " + error.getClass().getSimpleName()
                + ":" + error.getMessage()
        );
        throw error;
    } finally {
        System.out.println("AROUND finally");
    }
}
```

**Khi target thành công:**

```text
AROUND enter
TARGET aroundCase false
AROUND return AROUND-OK
AROUND finally
CLIENT value=AROUND-OK
```

**Khi target ném exception:**

```text
AROUND enter
TARGET aroundCase true
AROUND throw IllegalStateException:around failed
AROUND finally
CLIENT caught IllegalStateException:around failed
```

Điểm nổi bật:

- `pjp.proceed()` **tiếp tục qua các interceptor còn lại** trong chuỗi, cuối cùng đến target nếu không có interceptor nào short-circuit.
- Nếu bỏ `proceed()` mà return ngay, các advisor phía trong và target có thể **không thực thi**. Đây là điểm khác biệt lớn với những loại advice còn lại.
- Nếu `proceed()` bị gọi nhiều lần, phần chuỗi còn lại có thể được thực thi nhiều lần. Điều này chỉ phù hợp những trường hợp thiết kế rõ như retry có kiểm soát; không tùy tiện gọi lặp cho các method ghi dữ liệu.
- Advice trả `Object` nên hoàn trả kết quả thực của `proceed()` (hoặc kết quả khác nếu có chủ đích và tương thích với signature target).
- `catch Throwable` giúp ghi cả `Exception` và `Error` trong đoạn minh họa, **không nên nuốt lỗi nghiêm trọng**; ví dụ ném lại không thay đổi flow.

Nếu chỉ cần một log trước method, `@Before` ngắn và an toàn hơn `@Around`. Chỉ dùng around khi thật sự cần điều phối logic trước/sau, thay return value, fallback hoặc timer có trạng thái cục bộ.

## 8. Project Java 17+ chạy độc lập — năm advice với trace tách biệt

Để không phải đoán thứ tự khi **nhiều loại advice cùng match một method**, demo này cố ý dùng **mỗi loại advice cho một nhóm method riêng**. Nhờ đó stdout minh họa năm contract độc lập, dễ kiểm thử. Cuối bài sẽ giải thích cách nhiều advice tương tác trên cùng một method thực tế.

Môi trường: **Java 17+, Maven, Spring Framework 6.2.6** với `spring-context`, `spring-aop` và `aspectjweaver`. Spring bean được đăng ký qua `@Bean`, aspect dùng `@Aspect` và `@EnableAspectJAutoProxy`.

### 8.1. Cấu trúc file

```text
spring-advice-tracing/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AdviceTracingDemo.java
```

### 8.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-advice-tracing</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
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
                    <mainClass>demo.AdviceTracingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. Tệp src/main/java/demo/AdviceTracingDemo.java

```java
package demo;

import java.util.function.Supplier;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class AdviceTracingDemo {

    public interface TaskService {
        String beforeCase(boolean fail);
        String successCase(boolean fail);
        String throwingCase(String kind);
        String finallyCase(boolean fail);
        String aroundCase(boolean fail);
    }

    public static class TaskServiceImpl implements TaskService {

        @Override
        public String beforeCase(boolean fail) {
            System.out.println("TARGET beforeCase " + fail);
            if (fail) {
                throw new IllegalStateException("before failed");
            }
            return "BEFORE-OK";
        }

        @Override
        public String successCase(boolean fail) {
            System.out.println("TARGET successCase " + fail);
            if (fail) {
                throw new IllegalStateException("return failed");
            }
            return "SUCCESS-OK";
        }

        @Override
        public String throwingCase(String kind) {
            System.out.println("TARGET throwingCase " + kind);
            if ("argument".equals(kind)) {
                throw new IllegalArgumentException("bad argument");
            }
            if ("state".equals(kind)) {
                throw new IllegalStateException("bad state");
            }
            return "THROW-OK";
        }

        @Override
        public String finallyCase(boolean fail) {
            System.out.println("TARGET finallyCase " + fail);
            if (fail) {
                throw new IllegalStateException("finally failed");
            }
            return "FINALLY-OK";
        }

        @Override
        public String aroundCase(boolean fail) {
            System.out.println("TARGET aroundCase " + fail);
            if (fail) {
                throw new IllegalStateException("around failed");
            }
            return "AROUND-OK";
        }
    }

    @Aspect
    public static class TraceAspect {

        @Before("execution(* demo..*.beforeCase(..))")
        public void before(JoinPoint jp) {
            System.out.println("BEFORE " + jp.getSignature().getName());
        }

        @AfterReturning(
            pointcut = "execution(* demo..*.successCase(..))",
            returning = "result",
            argNames = "result"
        )
        public void afterReturning(String result) {
            System.out.println("AFTER_RETURNING result=" + result);
        }

        @AfterThrowing(
            pointcut = "execution(* demo..*.throwingCase(..))",
            throwing = "error",
            argNames = "error"
        )
        public void afterThrowing(IllegalArgumentException error) {
            System.out.println(
                "AFTER_THROWING "
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage()
            );
        }

        @After("execution(* demo..*.finallyCase(..))")
        public void after(JoinPoint jp) {
            System.out.println(
                "AFTER_FINALLY " + jp.getSignature().getName()
            );
        }

        @Around("execution(* demo..*.aroundCase(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("AROUND enter");
            try {
                Object value = pjp.proceed();
                System.out.println("AROUND return " + value);
                return value;
            } catch (Throwable error) {
                System.out.println(
                    "AROUND throw "
                        + error.getClass().getSimpleName()
                        + ":" + error.getMessage()
                );
                throw error;
            } finally {
                System.out.println("AROUND finally");
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {

        @Bean
        public TaskService taskService() {
            return new TaskServiceImpl();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    static void runCase(String label, Supplier<String> action) {
        System.out.println("=== " + label + " ===");
        try {
            System.out.println("CLIENT value=" + action.get());
        } catch (RuntimeException error) {
            System.out.println(
                "CLIENT caught "
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage()
            );
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            TaskService service = context.getBean(TaskService.class);

            System.out.println(
                "AOP_PROXY=" + AopUtils.isAopProxy(service)
            );
            System.out.println(
                "JDK_PROXY=" + AopUtils.isJdkDynamicProxy(service)
            );

            runCase("BEFORE SUCCESS", () -> service.beforeCase(false));
            runCase("BEFORE FAILURE", () -> service.beforeCase(true));

            runCase("AFTER RETURNING SUCCESS",
                () -> service.successCase(false));
            runCase("AFTER RETURNING FAILURE",
                () -> service.successCase(true));

            runCase("AFTER THROWING INVALID",
                () -> service.throwingCase("argument"));
            runCase("AFTER THROWING STATE",
                () -> service.throwingCase("state"));
            runCase("AFTER THROWING SUCCESS",
                () -> service.throwingCase("ok"));

            runCase("AFTER FINALLY SUCCESS",
                () -> service.finallyCase(false));
            runCase("AFTER FINALLY FAILURE",
                () -> service.finallyCase(true));

            runCase("AROUND SUCCESS", () -> service.aroundCase(false));
            runCase("AROUND FAILURE", () -> service.aroundCase(true));
        }
    }
}
```

### 8.4. Lệnh chạy

Ở thư mục `spring-advice-tracing`:

```bash
mvn -q compile exec:java
```

Các dòng stdout **do chính chương trình in**, theo thứ tự kỳ vọng (không tính thông báo riêng từ Maven hoặc framework logging):

```text
AOP_PROXY=true
JDK_PROXY=true
=== BEFORE SUCCESS ===
BEFORE beforeCase
TARGET beforeCase false
CLIENT value=BEFORE-OK
=== BEFORE FAILURE ===
BEFORE beforeCase
TARGET beforeCase true
CLIENT caught IllegalStateException:before failed
=== AFTER RETURNING SUCCESS ===
TARGET successCase false
AFTER_RETURNING result=SUCCESS-OK
CLIENT value=SUCCESS-OK
=== AFTER RETURNING FAILURE ===
TARGET successCase true
CLIENT caught IllegalStateException:return failed
=== AFTER THROWING INVALID ===
TARGET throwingCase argument
AFTER_THROWING IllegalArgumentException:bad argument
CLIENT caught IllegalArgumentException:bad argument
=== AFTER THROWING STATE ===
TARGET throwingCase state
CLIENT caught IllegalStateException:bad state
=== AFTER THROWING SUCCESS ===
TARGET throwingCase ok
CLIENT value=THROW-OK
=== AFTER FINALLY SUCCESS ===
TARGET finallyCase false
AFTER_FINALLY finallyCase
CLIENT value=FINALLY-OK
=== AFTER FINALLY FAILURE ===
TARGET finallyCase true
AFTER_FINALLY finallyCase
CLIENT caught IllegalStateException:finally failed
=== AROUND SUCCESS ===
AROUND enter
TARGET aroundCase false
AROUND return AROUND-OK
AROUND finally
CLIENT value=AROUND-OK
=== AROUND FAILURE ===
AROUND enter
TARGET aroundCase true
AROUND throw IllegalStateException:around failed
AROUND finally
CLIENT caught IllegalStateException:around failed
```

### 8.5. Vì sao ví dụ tạo ra các trace này?

1. `Config` đăng ký `TaskServiceImpl` dưới interface `TaskService`. `@EnableAspectJAutoProxy(proxyTargetClass=false)` cho phép Spring dùng JDK dynamic proxy khi target có interface.
2. `TraceAspect` là Spring bean và mang `@Aspect`, nên Spring tìm được cả năm advice methods.
3. Mỗi method của service có **tên khác nhau** và mỗi advice có pointcut chỉ chọn đúng tên đó. Do vậy chỉ một loại advice áp dụng cho từng test case, không phải phụ thuộc thứ tự ngẫu nhiên giữa advice classes.
4. Caller luôn lấy `TaskService` từ context. Lời gọi `service.beforeCase(...)` và các lời gọi khác đều qua **Spring proxy**, không gọi trực tiếp `new TaskServiceImpl()`.
5. Với `@Before`, advice luôn in trước target khi method được match, kể cả target sẽ ném lỗi.
6. Với `@AfterReturning`, nếu target ném exception thì không có `AFTER_RETURNING`.
7. Với `@AfterThrowing(IllegalArgumentException)`, `IllegalStateException` không thỏa điều kiện type và không chạy advice.
8. Với `@After`, advice luôn in sau target, cả đường thành công và lỗi.
9. Với `@Around`, lời gọi `pjp.proceed()` dẫn đến target; khi thành công chạy nhánh return, khi lỗi chạy catch; `finally` luôn chạy trước khi client nhận kết quả/lỗi.

**Lưu ý về việc chạy:** đây là mã nguồn Maven độc lập và stdout dự kiến từ logic ví dụ. Nếu dự án thực tế có thêm advisor/aspect khác, logging hoặc proxy configuration khác, trace có thể bổ sung hoặc đổi thứ tự. Chỉ so khớp các dòng do chương trình của bài này in.

## 9. Muốn dùng đủ năm loại advice trên cùng một method thì sao?

Trong thực tế, có thể áp nhiều loại advice lên cùng một method, ví dụ:

```java
@Aspect
public class CombinedTraceAspect {
    @Before("execution(* com.example.app.service..*.save(..))")
    public void before() {
        System.out.println("BEFORE");
    }

    @AfterReturning("execution(* com.example.app.service..*.save(..))")
    public void success() {
        System.out.println("RETURNED");
    }

    @AfterThrowing("execution(* com.example.app.service..*.save(..))")
    public void failure() {
        System.out.println("THREW");
    }

    @After("execution(* com.example.app.service..*.save(..))")
    public void after() {
        System.out.println("FINALLY");
    }
}
```

Đây là **snippet minh họa**, chưa có `save(..)` service để biên dịch/chạy độc lập. Nó cho thấy Spring có thể đặt nhiều advice cùng một pointcut, nhưng cần hiểu thứ tự:

- **Đường vào:** advice chạy theo precedence trong interceptor chain; `@Before` thực thi trước phần target.
- **Đường ra bình thường:** `@AfterReturning` chạy, `@AfterThrowing` không chạy; `@After` theo nghĩa finally.
- **Đường ra lỗi:** `@AfterThrowing` chạy với ngoại lệ phù hợp, `@AfterReturning` không chạy; `@After` vẫn chạy.
- **Thứ tự giữa các aspects khác nhau:** không mặc định ổn định nếu không cấu hình; dùng `@Order` hoặc `Ordered` để xác định precedence.
- **Trong cùng aspect:** Spring quy định thứ tự ưu tiên theo loại advice (`@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`); `@After` có ngữ nghĩa finally nên thực tế hoàn tất **sau** after-returning/after-throwing khi các advice đó áp dụng.
- **Hai advice cùng loại trong cùng aspect:** Java reflection không đảm bảo thứ tự khai báo source; không dùng vị trí method trong file để suy order.

Nếu cần ví dụ mà stdout phải **chính xác tuyệt đối** để đưa vào README/test, cách ở mục 8 (các method độc lập) dễ kiểm chứng hơn. Nếu cần quan sát nested chain thực tế, đặt `@Order` cho các aspects và có integration test xác minh thứ tự gọi.

### Ưu tiên advice cao khác thời điểm chạy trước/sau

Với hai `@Around` advice A và B cùng match target, A ưu tiên cao hơn:

```text
A enter
  B enter
    TARGET
  B exit
A exit
```

Như vậy “ưu tiên cao” nghĩa là **đi vào trước, đi ra sau**. Shared pointcut hoặc đặt class theo thứ tự alphabetical không tự cung cấp precedence.

## 10. Ghi nhận thông tin join point đúng cách

Trong Spring AOP, advice có thể nhận `JoinPoint` làm tham số đầu tiên (riêng `@Around` dùng `ProceedingJoinPoint`). Các thông tin quan trọng:

```java
@Before("execution(public * com.example.app.service..*.*(..))")
public void log(JoinPoint jp) {
    String method = jp.getSignature().getName();
    Object proxy = jp.getThis();
    Object target = jp.getTarget();
    Object[] arguments = jp.getArgs();

    System.out.println("METHOD " + method);
    System.out.println("PROXY=" + proxy.getClass().getSimpleName());
    System.out.println("TARGET=" + target.getClass().getSimpleName());
    System.out.println("ARG_COUNT=" + arguments.length);
}
```

Đây là **snippet**, không phải file Java chạy độc lập. Nó có thể hỗ trợ debug:

- `jp.getSignature()`: thông tin method/join point.
- `jp.getArgs()`: arguments của invocation.
- `jp.getThis()`: Spring AOP proxy object.
- `jp.getTarget()`: target object đứng sau proxy.

Đừng đưa toàn bộ `arguments` vào log production mà không lọc. Nếu tham số chứa PII, password, token, file data hoặc object graph lớn, cần che/mask hoặc chỉ ghi metadata cần thiết. `toString()` trên input objects cũng có thể gây lộ dữ liệu hoặc thực hiện side effects ngoài ý muốn.

Khi log exception, dùng stacktrace khi cần debug, nhưng tránh lặp cùng lỗi ở nhiều tầng. Một service call qua nhiều proxy/advice có thể phát sinh nhiều sự kiện log cho cùng một exception.

## 11. Thí nghiệm đối chứng trên trace của project

Thử từng thay đổi độc lập đối với ví dụ ở mục 8 rồi phục hồi code trước khi thử tiếp:

| Thay đổi | Quan sát | Nguyên nhân |
| --- | --- | --- |
| Bỏ EnableAspectJAutoProxy trong Spring Framework thuần | Log target vẫn còn, log advice biến mất | Hạ tầng proxy chưa bật |
| Ngừng đăng ký TraceAspect bean | Log aspect biến mất | @Aspect không tự tạo Spring bean |
| Gọi new TaskServiceImpl() ngoài context | Chỉ in target | Raw object không có AOP proxy |
| Đổi pointcut beforeCase sang method khác | Before marker mất ở beforeCase | Method không còn match pointcut |
| Gọi this.innerMethod() bên trong target | Không có lần advice riêng | Self-invocation bypass proxy |
| Cho @Around return sớm không gọi proceed | Target không chạy | Around short-circuit |

Với mỗi lần thử, kiểm tra ba biến quan sát: target có chạy không, advice nào ghi log, caller nhận return/exception gì. Cách đó cô lập proxy, pointcut, outcome và thứ tự chain tốt hơn việc gắn đủ năm loại advice vào tất cả service methods.

Nếu còn transaction/cache/retry advisor, thực hiện integration test trên ApplicationContext thật và ghi events bằng recorder thay vì chỉ dựa vào thứ tự các dòng stdout.

## 12. Đưa tracing Spring AOP vào hệ thống thật

### 12.1. Log ít nhưng đủ để quan sát

Thông tin thường có ích:

- Method name và một operation identifier an toàn.
- Kết quả thuộc nhóm thành công/lỗi.
- Thời gian xử lý nếu đo trong `@Around`, không hardcode duration dự kiến.
- Trace/correlation ID do request context cung cấp.
- Exception class (và message đã được lọc hoặc che thông tin nhạy cảm).

**Không ghi trực tiếp credentials, token, dữ liệu cá nhân, toàn bộ request payload hoặc secrets** chỉ vì `JoinPoint.getArgs()` có thể truy cập chúng.

### 12.2. Dùng logger thay cho `System.out` khi triển khai production

Trong demo, `System.out.println` giúp xác định stdout. Ở dự án thực tế, nên dùng SLF4J/logging framework theo cấu hình ứng dụng:

```java
private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(TraceAspect.class);

@Before("execution(* com.example.app.service..*.*(..))")
public void logCall(JoinPoint jp) {
    log.debug("Invoking {}", jp.getSignature().toShortString());
}
```

Đây là **đoạn minh họa bổ sung**, cần SLF4J dependency, `TraceAspect` class và các imports thích hợp. Ưu tiên structured logging, levels và sampling để tránh tốn tài nguyên do advice chạy thường xuyên.

### 12.3. Không suy rollback từ advice

Một `@Transactional` method có thể được hạ tầng transaction tạo advisor riêng. `@AfterThrowing` chỉ quan sát exception phù hợp; nó **không tự cấu hình rollback**. Việc log xảy ra trước/sau commit hoặc rollback còn phụ thuộc vào thứ tự advisor của Spring.

### 12.4. Chú ý async và completion signals

Với `@Async`, một method có thể trả `CompletableFuture`, `Future` hoặc chạy trên thread khác. `@AfterReturning` ở một ranh giới proxy có thể quan sát **future object được trả về**, không đồng nghĩa tác vụ bất đồng bộ đã hoàn thành thành công. Muốn ghi thời điểm completion, cần quan sát completion stage hoặc cơ chế async-specific thích hợp.

### 12.5. Dùng integration test thay vì chỉ đọc code

Test tốt nên:

1. Dựng Spring context với aspect bean và target bean thật.
2. Assert `AopUtils.isAopProxy(service)` là `true`.
3. Gọi từ bean reference đã inject, không dùng `new` target object.
4. Kiểm tra case thành công, exception đúng/sai loại, và around return/throw.
5. Dùng recorder/spy hoặc capture log có kiểm soát để kiểm tra **advice nào đã chạy**, không chỉ assert business result.
6. Khi nhiều advice cùng match, cấu hình thứ tự rõ ràng và assert trace theo thứ tự đó.

## 13. Tự kiểm tra

**1.** Method trả `"FAIL"` mà không ném exception, `@AfterThrowing` có chạy không?  
**Trả lời:** Không; method đã trả bình thường. `@AfterReturning` có thể chạy.

**2.** `@AfterReturning(returning="value")` mà advice parameter đặt tên `result` có hợp lệ không?  
**Trả lời:** Tên binding phải khớp, hoặc cần cấu hình/khai báo tương thích; dễ nhất là dùng cùng tên `value` trong attribute và parameter (có thể thêm `argNames`).

**3.** `@AfterThrowing` nhận `IllegalArgumentException` có chạy khi target ném `IllegalStateException`?  
**Trả lời:** Không, vì không có quan hệ subtype phù hợp.

**4.** `@After` sẽ chạy khi target ném exception và không return bình thường?  
**Trả lời:** Có, vì semantics của `@After` tương tự finally.

**5.** `@Before` có gọi `proceed()` để tiếp tục target không?  
**Trả lời:** Không. Chỉ `@Around` dùng `ProceedingJoinPoint.proceed()`; Spring tự tiếp tục sau before advice nếu advice không ném lỗi.

**6.** Trong `@Around`, bỏ `proceed()` nhưng return một String, chuyện gì xảy ra?  
**Trả lời:** Có thể short-circuit phần chain còn lại và target; caller nhận giá trị advice trả nếu compatible.

**7.** Hai aspects cùng match một method nhưng không có `@Order`. Có nên dự đoán thứ tự log từ thứ tự class được khai báo trong code không?  
**Trả lời:** Không. Thứ tự tương đối giữa aspects cần được quy định bằng precedence nếu quan trọng.

**8.** Target service gọi `this.beforeCase()` trong một method khác của chính nó. Advice `@Before` chỉ khớp `beforeCase()` có chạy lại không?  
**Trả lời:** Không có proxy entry mới, nên Spring AOP không intercept lời gọi nội bộ đó.

**9.** Một `@Around` catch exception và trả fallback. `@AfterThrowing` nằm phía ngoài có chắc thấy exception gốc không?  
**Trả lời:** Không. Nếu inner advice đã xử lý và trả về bình thường, outer advice có thể chỉ thấy normal return.

**10.** Khi chuyển Spring Framework thuần sang Spring Boot, có nên giữ nguyên mọi giả định về JDK/CGLIB proxy default?  
**Trả lời:** Không. Boot auto-configuration có thể mặc định class-based proxy; nên kiểm tra cấu hình và runtime object thực tế.

## 14. Tài liệu Spring Framework chính thức

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): ví dụ và semantics của cả `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After` và `@Around`, binding và precedence.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): các loại advice và method-execution join points.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation và giới hạn interception.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): kích hoạt AOP và đăng ký aspect beans.
