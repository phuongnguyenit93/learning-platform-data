# `@After` như `finally` so với `@AfterReturning` và `@AfterThrowing` trong Spring AOP

## 1. Phân biệt đúng ba loại advice

Trong **Spring Framework AOP**, một method của Spring bean có thể kết thúc theo hai hướng:

1. **Normal return:** phương thức trả giá trị hoặc hoàn thành bình thường đối với method `void`.
2. **Exceptional exit:** phương thức thoát bằng cách ném một `Throwable` ra khỏi ranh giới method execution mà Spring AOP đang intercept.

Ba annotation dễ bị nhầm vì đều chứa chữ “After”:

- **`@AfterReturning`:** chỉ chạy khi method execution được chọn **kết thúc bình thường**. Có thể bind return value bằng `returning`.
- **`@AfterThrowing`:** chỉ chạy khi method execution được chọn **thoát bằng exception**. Có thể bind exception bằng `throwing` và dùng kiểu tham số để lọc exception.
- **`@After`:** chạy khi method execution được chọn **kết thúc theo cả hai hướng**; trong Spring AOP, nó là **after (finally) advice**, tương tự một khối `finally`.

Vì vậy, nếu mục tiêu là “luôn giải phóng tài nguyên hoặc ghi nhận đã kết thúc một method”, `@After` thích hợp. Nếu mục tiêu là “chỉ ghi kết quả thành công” hoặc “chỉ ghi thông tin lỗi”, hai loại còn lại rõ ý định hơn.

**Giới hạn của bài:** nội dung tập trung vào **Spring Aspect, thứ tự Spring AOP advice và phương thức gọi qua Spring proxy**, không trình bày lại kiến thức AOP tổng quát hoặc AspectJ compile-time weaving.

## 2. Bảng sự kiện — loại nào thực sự chạy?

Giả sử cả ba advice dùng **cùng một pointcut**, không tự ném exception và method được gọi từ client **qua Spring AOP proxy**:

| Kết quả method | `@AfterReturning` | `@AfterThrowing` | `@After` |
| --- | --- | --- | --- |
| `return "OK"` | Chạy | Không chạy | Chạy |
| `return null` | Chạy nếu binding tương thích | Không chạy | Chạy |
| Method `void` hoàn thành | Chạy nếu không có binding/kiểu hạn chế loại bỏ | Không chạy | Chạy |
| `throw IllegalArgumentException` | Không chạy | Chạy nếu kiểu exception match | Chạy |
| `throw IOException` | Không chạy | Chạy nếu kiểu exception match | Chạy |
| Method bắt lỗi bên trong rồi `return "RECOVERED"` | Chạy | Không chạy | Chạy |
| Method trả một object báo lỗi, nhưng không `throw` | Chạy | Không chạy | Chạy |
| Method chưa được gọi qua proxy, hoặc pointcut không match | Không có advice cho lời gọi đó | Không có advice cho lời gọi đó | Không có advice cho lời gọi đó |

**Điều kiện ở dòng cuối là tối quan trọng:** `@After` không phải cơ chế Java tự động chen vào bất cứ method nào. Spring AOP tạo **proxy/advisor chain**; nếu method không đi qua proxy được advice, không loại nào được kích hoạt bởi lời gọi đó.

### Minh họa đơn giản theo nhánh

```text
                      Client gọi proxy.method()
                                  |
                                  v
                           Spring AOP proxy
                                  |
                                  v
                           Target.method()
                             /         \
                            /           \
                     NORMAL RETURN    THROWS ERROR
                           |              |
                           v              v
                  @AfterReturning    @AfterThrowing
                           |              |
                           +-------+------+
                                   |
                                   v
                            @After (finally)
                                   |
                                   v
                        Client nhận value/error
```

Sơ đồ mô tả thứ tự **các advice cùng một `@Aspect` trong Spring hiện đại**, với pointcut và điều kiện binding đều phù hợp. Khi có nhiều aspects, around advice hay advisor hạ tầng xen vào, cần xét thêm **thứ tự thực sự của interceptor chain**; không được dùng hình này như cam kết mọi advice ở mọi aspect luôn chạy theo thứ tự tuyệt đối.

## 3. `@After` thật sự giống `finally` ở điểm nào?

Spring document gọi `@After` là **after finally advice**. Một ví dụ:

```java
@Aspect
public class CompletionAspect {

    @After("execution(* com.example.app.service..*.*(..))")
    public void completed(JoinPoint jp) {
        System.out.println("COMPLETED " + jp.getSignature().getName());
    }
}
```

Đây là **snippet cần được đăng ký thành Spring `@Aspect` bean**; `JoinPoint` đến từ `org.aspectj.lang.JoinPoint`, `@After` từ `org.aspectj.lang.annotation.After`.

Dòng `COMPLETED` xuất hiện khi một method execution phù hợp:

- Trả bình thường, kể cả khi return value là `null`.
- Kết thúc do unchecked exception.
- Kết thúc do checked exception được propagate theo contract của Java/proxy.
- Bắt một exception nội bộ và vẫn trả bình thường: chỉ thấy **normal completion** của method, nhưng `@After` vẫn chạy vì đó cũng là một kiểu kết thúc.

### So với Java `finally`

Một Java method có thể dùng:

```java
try {
    // business operation
} finally {
    // dọn dẹp trong chính method
}
```

Còn Spring `@After` là logic **ngoài method target**, được kích hoạt bởi proxy khi pointcut match. Hai thứ giống nhau ở ý nghĩa “chạy sau khi phần thực thi liên quan hoàn tất theo bất kỳ hướng thoát nào”, nhưng **không giống nhau về cơ chế**:

| Đặc điểm | Java `finally` | Spring AOP `@After` |
| --- | --- | --- |
| Nằm ở đâu? | Trong mã Java của khối `try/finally` | Trong Spring `@Aspect` bean |
| Có cần Spring proxy? | Không | Có (trong proxy-based Spring AOP) |
| Áp dụng cho method được chọn bằng pointcut? | Không phải mục đích của syntax | Có |
| Tự chạy khi `new Target().method()`? | Nếu code target có `finally` thì có | Không, nếu đối tượng không đi qua Spring AOP proxy |
| Tự chạy khi target gọi `this.inner()`? | Theo control flow của mã trong target | Advice trên `inner()` không được kích hoạt thêm nếu self-invocation bypass proxy |
| Có bind return value qua `returning`? | Không theo annotation này | Không; dùng `@AfterReturning` |
| Có bind thrown exception qua `throwing`? | Không theo annotation này | Không; dùng `@AfterThrowing` |

**Quan trọng:** `@After` không có attribute `returning` hay `throwing` giống hai advice chuyên dụng. Nếu cần phân biệt thành công/thất bại và dữ liệu tương ứng, hãy chọn đúng advice hoặc `@Around`.

### Chọn đúng mục đích

- **Release resource / “method đã kết thúc” audit:** `@After`.
- **Chỉ đếm success / quan sát return value:** `@AfterReturning`.
- **Chỉ đếm failure / quan sát thrown exception:** `@AfterThrowing`.
- **Cần điều khiển execution, catch để trả fallback, thay return value:** `@Around`.

Nên chọn loại advice ít quyền lực nhất đủ để giải quyết nhu cầu, nhằm tránh vô tình thay đổi flow của business method.

## 4. `@AfterReturning`: chỉ chạy khi return bình thường

Khai báo:

```java
@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.confirm(..))",
    returning = "result",
    argNames = "result"
)
public void successful(Object result) {
    System.out.println("SUCCESS result=" + result);
}
```

Đây là **method mẫu trong `@Aspect` bean**.

- `returning = "result"` là **tên binding parameter** của advice method, không phải tên trường hay tên method của target.
- `argNames = "result"` giúp Spring giải quyết binding name rõ ràng trong trường hợp compiler không giữ parameter names.
- `Object result` nhận reference của return value nếu kiểu phù hợp. Đặt kiểu cụ thể hơn có thể giới hạn methods/value được match.
- Return value được bind cho advice **không phải điểm để thay object trả cho client**. Muốn thay kết quả, dùng `@Around`.

Ví dụ target:

```java
public String confirm(String mode) {
    if ("bad".equals(mode)) {
        throw new IllegalArgumentException("invalid");
    }
    return "OK:" + mode;
}
```

Khi `confirm("good")` trả `OK:good`, advice có thể ghi `SUCCESS result=OK:good`. Nhưng với `confirm("bad")`, advice này không chạy.

### “Thành công” ở đây là thành công theo Java method exit

Nếu method trả `"DECLINED"` hay một `Result.failure(...)` nhưng không `throw`, Spring vẫn coi là **normal return** và `@AfterReturning` có thể chạy. Điều này không có nghĩa giao dịch kinh doanh thực tế thành công.

Muốn phân biệt status nghiệp vụ trong return object, kiểm tra dữ liệu trả về trong advice phù hợp và đặt tên metric rõ ràng, ví dụ `method.completedNormally` thay vì mặc định dùng `business.success`.

## 5. `@AfterThrowing`: chỉ chạy khi exception thoát khỏi method

Khai báo:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.confirm(..))",
    throwing = "failure",
    argNames = "failure"
)
public void failed(IllegalArgumentException failure) {
    System.out.println(
        "FAILURE " + failure.getClass().getSimpleName()
            + ":" + failure.getMessage()
    );
}
```

Đây là **method mẫu**, không phải class độc lập.

Điểm cần nhớ:

1. `throwing="failure"` ràng buộc throwable vào tham số Java tên `failure`.
2. **Kiểu tham số** `IllegalArgumentException` còn là điều kiện filter. Nếu method thoát bằng `IllegalStateException`, advice này không chạy.
3. Nếu muốn bao phủ mọi subtype của `Exception`, dùng `Exception`. Nếu muốn bao phủ mọi subtype của `Throwable` (kể cả `Error`), dùng `Throwable` — nhưng cần cân nhắc nội dung log cho lỗi nghiêm trọng.
4. Lời gọi target tự catch lỗi rồi trả bình thường **không kích hoạt** advice này.
5. Trong mẫu thông thường, advice này **không nuốt exception**; caller vẫn nhận exception gốc sau khi advice thực thi nếu advice không tự làm thay đổi flow.

### Không dùng `@AfterThrowing` làm catch/recovery thay cho caller

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.confirm(..))",
    throwing = "failure"
)
public void pretendRecovery(RuntimeException failure) {
    System.out.println("RECOVER?");
}
```

Đây là **phản ví dụ về kỳ vọng sai**. Log `RECOVER?` không biến exception thành return value. Nếu muốn bắt `IllegalArgumentException` và trả giá trị khác, dùng `@Around` với `try/catch` và `pjp.proceed()`; phải bảo đảm return value tương thích method signature.

**Lưu ý chính thức của Spring:** `@AfterThrowing` không được định nghĩa như một callback bắt mọi exception do mọi advice trong chuỗi tạo ra. Đặc biệt, advice trong cùng `@Aspect` không được suy rằng `@AfterThrowing` sẽ nhận lỗi do `@After` hoặc `@AfterReturning` của chính aspect đó ném ra. Ngữ nghĩa dự kiến là lỗi thoát ra từ **join point (target method execution)**.

## 6. Quan hệ precedence và thứ tự thực thi thực tế

Đây là trọng tâm của bài: **mức ưu tiên advisor** khác với **thứ tự dòng log khi method trở về**.

Theo tài liệu Spring Framework 6.2, với các advice **khác loại trong cùng một `@Aspect`** đang match một join point, độ ưu tiên từ cao đến thấp là:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

Tuy nhiên, **`@After` dùng ngữ nghĩa finally**, nên khi execution thoát ra, một `@After` trong cùng aspect **thực tế được gọi sau `@AfterReturning` hoặc `@AfterThrowing`**.

Điều này không mâu thuẫn. Precedence quyết định cách những interceptors được **lồng vào nhau**. Advice mang ý nghĩa `finally` hoàn thành khi phần thực thi nằm **bên trong nó** đã kết thúc:

```text
LỜI GỌI THÀNH CÔNG, cùng một aspect
----------------------------------
@Around enter
  @Before
    TARGET returns normally
    @AfterReturning
  @After (finally)
@Around exit normally
CLIENT receives result

LỜI GỌI THẤT BẠI, cùng một aspect
----------------------------------
@Around enter
  @Before
    TARGET throws
    @AfterThrowing (nếu kiểu exception match)
  @After (finally)
@Around rethrows/handles
CLIENT receives exception or fallback
```

Đây là **mô hình thứ tự từ semantics Spring 6.2** với advisor hợp lệ, không phải bảo đảm tự động về mọi aspect trong một hệ thống có hạ tầng transaction/cache/async và advisor tùy biến.

### Phân biệt ba loại “thứ tự”

| Thuật ngữ | Ý nghĩa | Không được nhầm với |
| --- | --- | --- |
| Precedence giữa **các loại advice cùng aspect** | Thứ tự thiết lập và lồng advisor theo type | Thứ tự method xuất hiện trong file Java |
| Precedence giữa **các aspect** | Được điều khiển bằng `@Order` hoặc `Ordered` | Có chung pointcut nghĩa là tự có thứ tự |
| Thời điểm chạy trên **nhánh return/throw** | Finally logic diễn ra khi phần phía trong hoàn tất | Một advice có precedence cao chắc chắn in log trước trên mọi chiều |

Với nhiều aspects, quy tắc phổ quát là: **aspect có precedence cao hơn chạy trước ở chiều vào và sau ở chiều ra** (đối với những advice tương ứng), giống các tầng interceptor lồng nhau.

### `@Order` dùng thế nào?

```java
@Aspect
@Order(1)
public class OuterAspect {
    // advice bao ngoài
}

@Aspect
@Order(2)
public class InnerAspect {
    // advice nằm phía trong khi cả hai cùng match
}
```

Các class là **ví dụ annotation**, cần Spring-managed aspect beans và imports phù hợp. Giá trị số nhỏ hơn có precedence cao hơn.

Khi `OuterAspect` có `@Around`, phía trong là `InnerAspect` có `@AfterReturning` và `@After`, log có thể diễn ra:

```text
OUTER enter
TARGET
INNER afterReturning
INNER afterFinally
OUTER return
OUTER finally
```

Không nên dự đoán thứ tự giữa hai `@After` trong **cùng aspect** chỉ dựa trên thứ tự khai báo source Java; Spring không bảo đảm reflection giữ declaration order. Nếu cùng loại advice cần thứ tự rõ, gộp chúng hoặc tách thành các aspects khác nhau kèm `@Order`.

## 7. Demo Maven Java 17+: ghi log cả thành công và lỗi

Ví dụ dưới đây là **project Spring Framework 6.2.6 runnable**, không cần Spring Boot. Nó tạo:

- Spring-managed bean `CheckoutService` với implementation `CheckoutServiceImpl`.
- `LifecycleAspect` mang **`@Before`, `@AfterReturning`, `@AfterThrowing` và `@After`** trên cùng method `confirm(..)`.
- `OuterTraceAspect` mang `@Around`, được `@Order(1)` để bao bên ngoài `LifecycleAspect` (`@Order(2)`).
- Bốn đường gọi: success, exception bị bắt ngay trong target, `IllegalArgumentException` thoát khỏi target, và `IllegalStateException` không khớp kiểu của `@AfterThrowing`.
- Trace phân biệt *normal completion*, *exceptional exit* và *finally completion*.

### 7.1. Cấu trúc project

```text
spring-after-advice-order/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AfterAdviceOrderDemo.java
```

### 7.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-after-advice-order</artifactId>
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
                    <mainClass>demo.AfterAdviceOrderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Tệp `src/main/java/demo/AfterAdviceOrderDemo.java`

```java
package demo;

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
import org.springframework.core.annotation.Order;

public class AfterAdviceOrderDemo {

    public interface CheckoutService {
        String confirm(String mode);
    }

    public static class CheckoutServiceImpl implements CheckoutService {
        @Override
        public String confirm(String mode) {
            System.out.println("TARGET confirm " + mode);

            if ("bad".equals(mode)) {
                throw new IllegalArgumentException("invalid order");
            }
            if ("state".equals(mode)) {
                throw new IllegalStateException("unavailable");
            }
            if ("handled".equals(mode)) {
                try {
                    throw new IllegalArgumentException("internal failure");
                } catch (IllegalArgumentException ignored) {
                    System.out.println("TARGET handled internally");
                    return "RECOVERED";
                }
            }
            return "OK:" + mode;
        }
    }

    @Aspect
    @Order(1)
    public static class OuterTraceAspect {
        @Around("execution(* demo..*.confirm(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            String mode = String.valueOf(pjp.getArgs()[0]);
            System.out.println("OUTER enter " + mode);

            try {
                Object result = pjp.proceed();
                System.out.println("OUTER return " + result);
                return result;
            } catch (Throwable ex) {
                System.out.println(
                    "OUTER throw "
                        + ex.getClass().getSimpleName()
                        + ":" + ex.getMessage()
                );
                throw ex;
            } finally {
                System.out.println("OUTER finally");
            }
        }
    }

    @Aspect
    @Order(2)
    public static class LifecycleAspect {
        @Before("execution(* demo..*.confirm(..))")
        public void before() {
            System.out.println("BEFORE");
        }

        @AfterReturning(
            pointcut = "execution(* demo..*.confirm(..))",
            returning = "result",
            argNames = "result"
        )
        public void returned(String result) {
            System.out.println("AFTER_RETURNING " + result);
        }

        @AfterThrowing(
            pointcut = "execution(* demo..*.confirm(..))",
            throwing = "failure",
            argNames = "failure"
        )
        public void thrown(IllegalArgumentException failure) {
            System.out.println(
                "AFTER_THROWING "
                    + failure.getClass().getSimpleName()
                    + ":" + failure.getMessage()
            );
        }

        @After("execution(* demo..*.confirm(..))")
        public void finished() {
            System.out.println("AFTER_FINALLY");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {
        @Bean
        public CheckoutService checkoutService() {
            return new CheckoutServiceImpl();
        }

        @Bean
        public OuterTraceAspect outerTraceAspect() {
            return new OuterTraceAspect();
        }

        @Bean
        public LifecycleAspect lifecycleAspect() {
            return new LifecycleAspect();
        }
    }

    private static void runCase(CheckoutService service, String mode) {
        System.out.println("=== " + mode + " ===");
        try {
            System.out.println("CLIENT result=" + service.confirm(mode));
        } catch (RuntimeException ex) {
            System.out.println(
                "CLIENT caught "
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage()
            );
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            CheckoutService service = context.getBean(CheckoutService.class);
            System.out.println("AOP=" + AopUtils.isAopProxy(service));

            runCase(service, "good");
            runCase(service, "handled");
            runCase(service, "bad");
            runCase(service, "state");
        }
    }
}
```

Điểm triển khai:

1. `@EnableAspectJAutoProxy(proxyTargetClass=false)` bật Spring AOP trong context thuần. Vì target implement `CheckoutService`, bean có thể được JDK dynamic proxy.
2. Các aspects đều được đăng ký tường minh qua `@Bean`. `@Aspect` **không tự đăng ký Spring bean** nếu không có component scan hoặc factory method.
3. `@Order(1)` khiến `OuterTraceAspect` được ưu tiên hơn `LifecycleAspect @Order(2)` ở chiều vào; nhờ đó outer around advice bao quá trình xử lý phía trong.
4. Trong `LifecycleAspect`, các advice dùng cùng `execution(* demo..*.confirm(..))`. Chỉ những nhánh exit thích hợp được áp dụng cho `@AfterReturning` hoặc `@AfterThrowing`, còn `@After` áp dụng cho cả hai.
5. `@AfterThrowing` nhận riêng `IllegalArgumentException`, nên `IllegalStateException` không kích hoạt advice đó.
6. Cả code kinh doanh lẫn các advice đều in những prefix riêng để quan sát trực tiếp thứ tự.

### 7.4. Chạy chương trình

Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Các dòng **stdout do chương trình tự in** dựa trên flow và thứ tự aspect được khai báo (không tính log riêng từ Maven/Spring):

```text
AOP=true
=== good ===
OUTER enter good
BEFORE
TARGET confirm good
AFTER_RETURNING OK:good
AFTER_FINALLY
OUTER return OK:good
OUTER finally
CLIENT result=OK:good
=== handled ===
OUTER enter handled
BEFORE
TARGET confirm handled
TARGET handled internally
AFTER_RETURNING RECOVERED
AFTER_FINALLY
OUTER return RECOVERED
OUTER finally
CLIENT result=RECOVERED
=== bad ===
OUTER enter bad
BEFORE
TARGET confirm bad
AFTER_THROWING IllegalArgumentException:invalid order
AFTER_FINALLY
OUTER throw IllegalArgumentException:invalid order
OUTER finally
CLIENT caught IllegalArgumentException:invalid order
=== state ===
OUTER enter state
BEFORE
TARGET confirm state
AFTER_FINALLY
OUTER throw IllegalStateException:unavailable
OUTER finally
CLIENT caught IllegalStateException:unavailable
```

**Ghi chú:** đây là stdout dự kiến từ mã Spring Framework 6.2 trình bày, không phải khẳng định một phiên Maven đã được chạy tại đây. Thư viện logging hoặc phiên bản/configuration khác có thể bổ sung log; ví dụ không hardcode tên lớp proxy runtime.

### 7.5. Phân tích từng tình huống

**Nhánh `good`:** method target trả `OK:good`. `@AfterReturning` nhận giá trị; `@AfterThrowing` bỏ qua; `@After` in `AFTER_FINALLY` **sau** dòng `AFTER_RETURNING`. Sau đó outer around advice mới ghi return và finally, rồi caller nhận result.

**Nhánh `handled`:** method target có ném `IllegalArgumentException` bên trong, nhưng bắt ngay tại `catch` và trả `RECOVERED`. Vì exception **không thoát khỏi method execution**, Spring AOP quan sát một normal return: `@AfterReturning` chạy, `@AfterThrowing` không chạy, và `@After` vẫn chạy.

**Nhánh `bad`:** target ném `IllegalArgumentException` ra ngoài. `@AfterReturning` không chạy; `@AfterThrowing` được bind đúng exception type nên in log; `@After` chạy tiếp theo dù method thất bại. Outer advice bắt chỉ để in rồi **ném lại nguyên lỗi**, nên caller vẫn bắt được.

**Nhánh `state`:** target ném `IllegalStateException`. Pointcut của `@AfterThrowing` match method nhưng **không match exception type**, vì vậy không có dòng `AFTER_THROWING`. Tuy nhiên `@After` vẫn chạy do semantics finally. Caller nhận exception như cũ.

Chính sự khác biệt của hai nhánh lỗi cho thấy: **`@After` không cần biết kiểu exception**, trong khi `@AfterThrowing(IllegalArgumentException)` lọc kiểu ngoài điều kiện pointcut.

## 8. Tại sao `@After` phải thực thi sau `@AfterReturning` / `@AfterThrowing`?

Spring dựng mỗi advice thành advisor/interceptor để sắp vào một **invocation chain**. Với advice của cùng một aspect, Spring 6.2 tài liệu hóa precedence của các type khác nhau. Vì `@After` có semantics giống finally, implementation của nó thực hiện cleanup sau khi phần invocation phía trong hoàn tất — bao gồm cả after-returning/after-throwing phù hợp ở phía trong.

Có thể hình dung như Java pseudocode (không phải mã của Spring):

```java
Object invokeInnerAdviceAndTarget() throws Throwable {
    try {
        // before advice
        // target execution
        Object result = target();
        // after-returning advice nếu normal return
        return result;
    } catch (Throwable targetFailure) {
        // after-throwing advice nếu targetFailure phù hợp
        throw targetFailure;
    }
}

Object invokeAfterFinally() throws Throwable {
    try {
        return invokeInnerAdviceAndTarget();
    } finally {
        // @After chạy ở đây
        afterFinally();
    }
}
```

Đây là **pseudocode về ý nghĩa lồng nhau**, không phải API hoặc source code Spring; không dùng nó để biên dịch. Nó nhấn mạnh hai điều:

1. Cleanup cuối cùng nằm trong `finally` chạy **sau** khi phần gọi bên trong đã hoàn tất hoặc đang thoát vì lỗi.
2. Một thứ có precedence cao hơn ở **chiều vào** không nhất thiết in log trước trên **chiều ra**.

### Không nhầm `@After` với callback “sau khi client đã nhận kết quả”

Dòng `AFTER_FINALLY` chạy **trước khi lời gọi proxy trả quyền điều khiển hoàn toàn cho client**, không phải callback chạy bất đồng bộ sau khi client nhận kết quả. Advice synchronous nằm trong invocation stack của lời gọi hiện tại. Trừ khi code advice tự thiết kế async handoff, mọi side effect xảy ra trước khi client tiếp tục sau lời gọi đó.

## 9. Khi có nhiều aspects: `@Order` và nesting

Giả sử có hai aspects:

```java
@Aspect
@Order(1)
class SecurityTracingAspect {
    // @Around
}

@Aspect
@Order(2)
class BusinessEventsAspect {
    // @After, @AfterReturning, @AfterThrowing
}
```

Đây là **snippet** không chạy độc lập. Trong Spring, order số nhỏ hơn ưu tiên cao hơn:

```text
SecurityTracingAspect @Order(1)
     |
     +-- enter
     |
     +---- BusinessEventsAspect @Order(2)
     |             |
     |             +-- TARGET
     |             +-- @AfterReturning hoặc @AfterThrowing
     |             +-- @After (finally)
     |
     +-- exit
```

Nếu đảo precedence, thứ tự log có thể thay đổi vì interceptor chain lồng nhau theo chiều khác.

### `@Order` không sắp từng method advice riêng lẻ trong cùng aspect

Trong một `@Aspect` bean, `@Order` đặt precedence của **aspect** so với aspect khác. Độ ưu tiên giữa các loại advice trong **cùng aspect** theo quy tắc của Spring; còn các advice **cùng loại** trong một aspect không có thứ tự xác định bằng vị trí method trong source code.

Để có sequence ổn định:

- Nếu nhiều `@After` cùng muốn làm cleanup trên một join point, cân nhắc **một** `@After` method điều phối theo thứ tự rõ ràng.
- Nếu hai cleanup concerns độc lập cần precedence khác nhau, đặt trong **hai aspects** và gắn `@Order` phù hợp.
- Viết integration test kiểm tra log/event sequence khi thứ tự thật sự ảnh hưởng hành vi.

Không coi tên method `firstAfter()`, `secondAfter()` hoặc vị trí xuất hiện trước/sau trong file Java là một ordering contract.

## 10. Những trường hợp đặc biệt liên quan exception

### 10.1. Exception bị target tự bắt

```java
public String work() {
    try {
        throw new IllegalStateException("transient");
    } catch (IllegalStateException ignored) {
        return "RECOVERED";
    }
}
```

Khi gọi qua Spring proxy:

- `@AfterReturning` chạy vì method trả bình thường.
- `@AfterThrowing` không nhận exception này.
- `@After` vẫn chạy.

**Đừng đếm “số exception được throw trong thân method” bằng `@AfterThrowing`.** Advice chỉ nhìn thấy exceptional exit của join point.

### 10.2. `@AfterThrowing` lọc theo kiểu

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app..*.work(..))",
    throwing = "failure",
    argNames = "failure"
)
public void onlyIo(IOException failure) {
    // Chỉ nhận IOException và các subtype.
}
```

Đây là snippet; cần import `java.io.IOException`. Nếu target ném `IllegalArgumentException`, advice không chạy. Trong khi đó, `@After` với cùng pointcut vẫn chạy nếu execution kết thúc bằng một exception thuộc bất kỳ kiểu nào.

**`throwing` không phải `throws`.** `throwing="failure"` là tên binding; `IOException` của advice parameter là điều kiện match kiểu throwable tại runtime. Method có `throws IOException` nhưng trả bình thường không làm `@AfterThrowing` chạy.

### 10.3. Nếu advice `@AfterReturning` tự ném exception

Một `@AfterReturning` có thể gặp lỗi nội bộ khi ghi metric, gửi network request hoặc truy cập recorder. Lỗi này là lỗi của **advice**, không phải exceptional exit nguyên thủy của target method. Spring documentation nói `@AfterThrowing` không được xem là callback tổng quát nhận exception từ `@After` hoặc `@AfterReturning` đồng hành trong cùng aspect.

Ở góc nhìn client, exception mới từ advice vẫn có thể làm lời gọi proxy kết thúc bất thường. Do đó:

- Đừng giả định `@AfterThrowing` đồng aspect chắc chắn log lỗi được ném bởi `@AfterReturning`.
- Đừng để một lỗi telemetry thứ cấp vô tình che mất kết quả/lỗi nghiệp vụ quan trọng.
- Nếu cần quản lý luồng lỗi **của toàn bộ interceptor chain**, một outer `@Around` với `try/catch/finally` và thứ tự được điều khiển rõ ràng có khả năng quan sát rộng hơn; đó vẫn không phải lý do để tùy tiện catch và nuốt exceptions.

### 10.4. Nếu `@After` tự ném exception

Trong Java `finally`, một exception ném tại `finally` có thể thay thế exception hoặc return đang được truyền đi. Với Spring `@After`, việc advice ném lỗi cũng có thể ảnh hưởng exception/result client nhận. Vì vậy cleanup trong `@After` nên đơn giản và có chiến lược xử lý lỗi rõ ràng.

Ví dụ **không nên làm một cách vô ý**:

```java
@After("execution(* com.example.app..*.work(..))")
public void cleanup() {
    throw new IllegalStateException("telemetry unavailable");
}
```

Đây là **mẫu phản ví dụ**: log/metric thất bại có thể biến một business call thành lỗi hoặc che lỗi gốc. Không dùng `@After` làm nơi tự ném exception bất kể kết quả.

### 10.5. `@After` có chạy khi `@Before` ném exception không?

Câu trả lời cần xét **vị trí trong interceptor chain**. Trong một aspect có precedence cho advice khác loại, một before advice có thể nằm ngoài after/finally advice. Nếu `@Before` ném exception **trước khi chain tiến vào `@After` advisor**, `@After` bên trong chưa được vào, nên không thể khẳng định nó chắc chắn chạy.

Do đó, phát biểu chuẩn là: `@After` chạy khi **matched join point execution mà nó bao quanh** kết thúc theo normal/exception path; không phải “luôn chạy cho bất kỳ lỗi nào phát sinh ở bất kỳ advice nào trong mọi cấu hình”.

Nếu cần dọn dẹp ngay cả khi **một outer precondition advice** thất bại trước khi target được gọi, hãy thiết kế một `@Around` outermost với `try/finally`, có order và test riêng.

## 11. Tình huống gắn với Spring transaction, cache và async

### 11.1. `@Transactional`: `@After` chạy khi nào so với commit/rollback?

Spring transaction dùng một **transaction interceptor/advisor** riêng. `@After` và `@AfterThrowing` do aspect custom của bạn khai báo là **những advisor khác** trong cùng hoặc khác proxy chain.

Nếu custom aspect nằm **bên trong** transaction advice, log after/finally có thể xuất hiện **trước khi transaction interceptor kết thúc commit/rollback**. Nếu nằm bên ngoài, nó có thể quan sát kết quả khác. Không suy từ chữ `After` rằng “transaction chắc chắn đã commit/rollback”.

Cũng không suy rằng một `@AfterThrowing` chạy thì Spring bắt buộc rollback. Transaction rollback rules phụ thuộc vào type exception và cấu hình như `rollbackFor` / `noRollbackFor`.

### 11.2. `@Cacheable`: cache hit có thể bỏ qua target

Caching advisor có thể trả giá trị từ cache mà **không gọi target method**. Kết quả custom after advice nhìn thấy phụ thuộc vị trí tương đối với caching interceptor:

- Nếu custom advice ở **bên ngoài** interceptor cache, nó có thể nhìn thấy cache hit như normal return từ phần chain bên trong.
- Nếu custom advice ở **bên trong** và cache hit làm phần bên trong không được gọi, custom advice có thể không chạy.

Không mặc định rằng `@AfterReturning` luôn đồng nghĩa “target method đã thực thi” khi có cache, fallback hoặc outer around advice.

### 11.3. `@Async`: return của proxy không nhất thiết là completion của task

Một `@Async` method có thể trả `Future` hoặc `CompletableFuture`, hay chạy trong thread executor. `@AfterReturning` tại một proxy boundary có thể được gọi khi nhận **future object** hoặc trạng thái mà advisor expose, không đồng nghĩa business task đã thực sự thành công.

Tương tự, `@After` “method execution tại ranh giới proxy đã kết thúc” không thay thế completion callback trên future. Khi muốn đo task hoàn tất, kết nối `whenComplete` hoặc cơ chế async-specific phù hợp.

### 11.4. Retry: có bao nhiêu lần `@After` chạy?

Một retry interceptor/outer around advice có thể gọi phần chain/target nhiều lần. Nếu custom `@After` nằm **bên trong vòng retry**, nó có thể chạy sau mỗi attempt. Nếu nằm **ngoài**, nó có thể chạy một lần cho lời gọi client sau khi retry kết thúc.

Vì vậy định nghĩa metric phải rõ: **attempt count** hay **logical client call count**, và order của các interceptor phải tương thích với mục tiêu đo lường.

## 12. Dùng `@After` để cleanup mà không phá nghiệp vụ

Một aspect cleanup cần chú ý:

1. **Tính idempotent:** side-effect cleanup có thể được thực thi nhiều lần khi có retry hoặc nhiều tầng service proxy.
2. **Không phá flow do lỗi logger/metric:** telemetry code cần có error policy riêng; tránh ném lỗi không chủ đích trong `finally`.
3. **Tránh giữ shared mutable state không an toàn:** `@Aspect` bean thường singleton; không lưu trạng thái “start time”/method-specific vào field dùng chung khi nhiều threads gọi đồng thời.
4. **Dữ liệu liên quan riêng invocation:** nếu cần đo thời gian, ưu tiên local variable trong `@Around` với `try/finally`. Trường hợp `@Before` và `@After` tách method cần thiết kế context storage/thread propagation đúng.
5. **Không log secrets:** `JoinPoint.getArgs()` có thể chứa credentials hoặc PII; chỉ ghi metadata an toàn, không dump toàn bộ argument objects.
6. **Hạn chế vùng pointcut:** target cụ thể, service package hay annotation cần thiết, tránh auto-proxy advice vô ý trên chính infrastructure logging.
7. **Có positive và negative tests:** normal return, checked/unchecked exception, exception bị catch trong target, advice riêng không match và self-invocation.
8. **Hiểu thứ tự transaction/cache/async:** “after method” không luôn đồng nghĩa “sau tất cả transaction/async business events”.

Một ví dụ cleanup thuần ghi event:

```java
@Aspect
public class CompletionAspect {
    @After("execution(public * com.example.app.service..*.*(..))")
    public void onExit(JoinPoint jp) {
        System.out.println(
            "COMPLETE " + jp.getSignature().toShortString()
        );
    }
}
```

Đây là snippet trong môi trường Spring đã bật `@AspectJ`; không phải cấu hình đầy đủ. Nó ghi event **trên cả hai nhánh return/throw**, nhưng không bind result hay exception.

## 13. Chẩn đoán khi log không đúng kỳ vọng

| Triệu chứng | Kiểm tra |
| --- | --- |
| `@After` không chạy dù method được gọi | Có proxy Spring AOP? Pointcut match? Caller có dùng `new` hoặc self-invocation không? |
| `@AfterReturning` không chạy | Method có ném exception? Kiểu tham số `returning` có hạn chế match không? |
| `@AfterThrowing` không chạy | Method có ném lỗi ra ngoài? Binding type có là supertype của exception không? |
| Có `AFTER_FINALLY` dù `@AfterThrowing` không chạy | Exception có kiểu không phù hợp với `throwing`? Đây có thể là hành vi đúng |
| Thấy `AFTER_FINALLY` sau `AFTER_RETURNING` | Đây là after-finally semantics theo Spring 6.2 trong cùng aspect |
| Thứ tự giữa hai aspects không như mong muốn | Kiểm tra `@Order`/`Ordered`, advisor precedence và thứ tự vào/ra |
| Có hai `@After` trong cùng aspect in không đúng source order | Source declaration order không là ordering contract; gộp hoặc tách aspects |
| Exception từ log che mất lỗi target | Advice `@After` hoặc advice khác có throw lỗi mới không? |
| `@After` báo hoàn tất nhưng transaction chưa commit | Kiểm tra relative ordering với transaction interceptor |
| Cache hit không in log giống cache miss | Check ordering giữa caching interceptor và custom advice |
| Async method log quá sớm | Proxy return khác task completion; quan sát future/executor |
| Retry tạo log nhiều lần | Advice ở trong hay ngoài retry loop? |
| Dùng JDK/CGLIB khác nhau | Kiểm tra interface methods/final/private, `AopUtils.isJdkDynamicProxy` / `isCglibProxy` |

### Cách kiểm chứng Spring bean có được proxy

```java
Object bean = context.getBean("checkoutService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

Đoạn này **không phải chương trình độc lập**. Nó dùng `org.springframework.aop.support.AopUtils`, và `context` phải là Spring context hợp lệ. Có proxy không có nghĩa **mọi method** trên bean đều được custom advice match; phải kiểm tra pointcut và actual caller path.

### Integration test quan trọng nhất

Để chứng minh semantics:

- Gọi Spring bean qua `ApplicationContext` thật.
- Kiểm tra success: `@AfterReturning` → `@After`.
- Kiểm tra matching failure: `@AfterThrowing` → `@After`.
- Kiểm tra non-matching failure: **chỉ `@After`**, không có `@AfterThrowing` cụ thể.
- Kiểm tra handled exception: `@AfterReturning` → `@After` vì target đã recover.
- Test thêm một aspect `@Order` cao hơn để xác minh nesting khi có nhiều aspects.
- Tránh khẳng định dựa chỉ trên business return value; dùng recorder/mock/spy hoặc capture logger để assert **các advice event**.

## 14. Tự kiểm tra

**Câu 1.** Method trả `null` bình thường. Loại advice nào có thể chạy?  
**Đáp án:** `@AfterReturning` (nếu binding tương thích) và `@After`. `@AfterThrowing` không chạy chỉ vì return là null.

**Câu 2.** Target ném `IllegalArgumentException` ra client; `@AfterThrowing` nhận `IllegalArgumentException` và `@After` dùng cùng pointcut. Advice nào chạy?  
**Đáp án:** Cả hai; trong cùng aspect Spring hiện đại, `@AfterThrowing` thích hợp chạy rồi `@After` như finally.

**Câu 3.** Target ném `IllegalStateException`, nhưng `@AfterThrowing` chỉ nhận `IllegalArgumentException`. `@After` có chạy không?  
**Đáp án:** Có, vì kiểu exception không hạn chế `@After`; `@AfterThrowing` bị lọc bởi parameter type.

**Câu 4.** Target ném exception trong khối `try` rồi tự `catch` và trả `"OK"`. `@AfterThrowing` có chạy không?  
**Đáp án:** Không; target method execution hoàn thành bình thường, `@AfterReturning` và `@After` có thể chạy.

**Câu 5.** Trong Spring 6.2, cùng một aspect có `@After` và `@AfterReturning`. `@After` có in log trước `@AfterReturning` chỉ vì nó có precedence cao hơn không?  
**Đáp án:** Không. Theo after-finally semantics, `@After` được gọi sau after-returning phù hợp trên đường ra.

**Câu 6.** `@AfterThrowing` có nhận mọi exception do advice `@AfterReturning` trong cùng aspect tự ném không?  
**Đáp án:** Không. Spring không định nghĩa nó như general exception callback cho companion after advice.

**Câu 7.** Đặt `@After` trong `@Aspect` bean có nghĩa mọi method Java trong chương trình đều được cleanup?  
**Đáp án:** Không. Cần Spring-managed target, AOP proxy entry và matching pointcut.

**Câu 8.** Hai `@After` trong cùng aspect có thể được sắp xếp bằng thứ tự viết trong file Java không?  
**Đáp án:** Không có bảo đảm. Gộp logic hoặc tách aspects với `@Order` rõ ràng.

**Câu 9.** Một outer `@Around` bắt lỗi và trả fallback. Outer `@AfterThrowing` có chắc thấy exception gốc không?  
**Đáp án:** Không, vì phần chain có thể đã chuyển exceptional exit thành normal return trước khi outer advice quan sát.

**Câu 10.** `@After` chạy có chứng minh database transaction đã commit hoặc rollback không?  
**Đáp án:** Không. Cần xét transaction interceptor relative order và rollback rules.

## 15. Tài liệu Spring Framework chính thức

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): semantics `@After`, `@AfterReturning`, `@AfterThrowing` và phần *Advice Ordering* mô tả precedence theo advice type và after-finally thực tế.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): phân biệt after returning, after throwing, after finally và around advice.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): đăng ký Spring `@Aspect` beans và kích hoạt Spring AOP.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): giới hạn proxy, JDK/CGLIB, self-invocation.
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html): rollback rules riêng với việc custom aspect quan sát exception.
