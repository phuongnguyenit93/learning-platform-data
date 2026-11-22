# `@AfterThrowing` và ràng buộc kiểu ngoại lệ trong Spring AOP

## 1. `@AfterThrowing` dùng để làm gì?

Trong Spring AOP, `@AfterThrowing` khai báo **advice được chạy khi một method execution được pointcut chọn kết thúc bằng cách ném exception**. Nó thường phục vụ log lỗi, ghi metric, audit sự cố hoặc gửi tín hiệu quan sát *sau khi* method đích thất bại.

Ví dụ:

```java
@Aspect
@Component
public class FailureAspect {

    @AfterThrowing(
        pointcut = "execution(* com.example.app.service..*.*(..))",
        throwing = "error"
    )
    public void recordFailure(Exception error) {
        System.out.println("SERVICE FAILED: " + error.getMessage());
    }
}
```

Đây là **đoạn code Spring AOP minh họa**, chưa phải chương trình chạy độc lập: cần imports, Spring context và các service beans thật.

Trong đoạn này:

- `@Aspect` đánh dấu class khai báo advice; `@Component` giúp component scanning đăng ký aspect thành Spring bean khi package được scan.
- `pointcut` chỉ định những method executions thuộc nhóm service có thể được chọn.
- `throwing = "error"` **bind ngoại lệ được ném** vào tham số có tên `error` của advice.
- Kiểu tham số `Exception` còn đóng vai trò **lọc loại ngoại lệ**. Advice này không nhận những throwable không phải subtype của `Exception`, chẳng hạn một số `Error`.

**Kết luận cốt lõi:** `@AfterThrowing` kết hợp **điều kiện method execution** và **điều kiện loại exception thoát khỏi method**. Chỉ khi cả hai phù hợp, advice mới chạy.

Bài chỉ tập trung vào Spring Framework và Spring AOP proxy-based advice; không mở rộng sang kiến thức Exception hoặc Aspect tổng quát.

## 2. Luồng chạy khi method ném ngoại lệ

Hình dung client gọi Spring bean thông qua proxy:

```text
Client
  |
  | service.placeOrder(...)
  v
Spring AOP proxy
  |
  +--> các advice/interceptor phù hợp
  |
  v
Target.placeOrder(...)
  |
  +--> xử lý thành công --> return
  |                         |
  |                         +--> @AfterThrowing KHÔNG chạy
  |
  +--> throw IllegalArgumentException
                            |
                            v
               @AfterThrowing có pointcut
               và kiểu exception tương thích?
                      /              \
                    CÓ              KHÔNG
                     |                 |
                     v                 |
               advice chạy            |
                     |                 |
                     +--------+--------+
                              |
                              v
                  Exception tiếp tục ra caller
                   nếu advice không thay đổi nó
```

Với cách sử dụng thông thường, Spring gọi `@AfterThrowing` **khi target execution thoát bằng exception phù hợp**, rồi exception tiếp tục đi ra phía client. Method advice không cần gọi `proceed()`.

### Trường hợp không kích hoạt

`@AfterThrowing` không chạy khi:

1. Method trả về bình thường, dù giá trị trả về là `null`, `false` hay một object báo thất bại.
2. Method tự bắt exception bên trong, xử lý xong rồi **trả về bình thường**.
3. Exception được ném nhưng **pointcut không khớp method execution**.
4. Exception thoát ra không tương thích với **kiểu tham số của advice**.
5. Lời gọi không đi qua Spring AOP proxy, ví dụ object tự tạo bằng `new` hoặc một lời gọi nội bộ `this.method()` trên target.
6. Một interceptor phía ngoài short-circuit trước khi đến join point, khiến method đích không được thực thi.

**Lưu ý quan trọng từ tài liệu Spring:** `@AfterThrowing` không phải callback bắt tất cả lỗi trong interceptor chain. Về ngữ nghĩa, nó xử lý lỗi xuất phát từ **join point (method đích)**, không được hiểu là cơ chế tự bắt exception được ném bởi `@After` hoặc `@AfterReturning` advice đi kèm.

## 3. Cú pháp của annotation và tham số `throwing`

### 3.1. Chỉ muốn biết method thất bại

Nếu chỉ cần thực hiện side-effect khi method ném exception, không cần lấy exception:

```java
@AfterThrowing("execution(* com.example.app.service..*.*(..))")
public void countFailure() {
    System.out.println("FAILED");
}
```

Đây là **method mẫu** phải đặt trong bean `@Aspect`. Nó áp dụng cho bất kỳ loại throwable nào có thể làm method execution đã chọn kết thúc bất thường, trong phạm vi semantics của advice.

### 3.2. Cần truy cập đối tượng exception

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "cause"
)
public void afterFailure(Throwable cause) {
    System.out.println(cause.getClass().getSimpleName());
}
```

Trong Spring, chuỗi `"cause"` ở thuộc tính `throwing` phải khớp **tên tham số** nhận exception của Java advice method. Đây là **tên binding variable**, không phải tên class Exception và không phải một tên tùy ý Spring bỏ qua.

Có thể chỉ rõ `argNames` để tăng độ rõ ràng khi compiler không lưu parameter names:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "cause",
    argNames = "cause"
)
public void afterFailure(Throwable cause) {
    System.out.println(cause.getMessage());
}
```

**Ý nghĩa của kiểu `Throwable`:** đây là supertype của các nhóm `Exception` và `Error` nên **không thu hẹp exception type** như các tham số cụ thể hơn. Tuy nhiên method vẫn phải phù hợp với pointcut, đi qua proxy và kết thúc bằng throwable.

### 3.3. `throwing` khác `throws` của method Java

So sánh:

```java
public void importFile() throws IOException {
    // ...
}
```

với:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.importFile(..))",
    throwing = "error"
)
public void onImportError(IOException error) {
    // ...
}
```

`throws IOException` trong chữ ký method Java là **khai báo khả năng ném checked exception**. `throwing = "error"` trong advice là **binding name** cho throwable thực tế thoát khỏi lời gọi. Kiểu `IOException` trong advice là điều kiện match theo kiểu runtime, không phải chỉ là việc Java method có khai báo `throws IOException` hay không.

Một method có `throws IOException` nhưng trả về bình thường **không kích hoạt** advice. Ngược lại, một unchecked exception không cần nằm trong `throws` vẫn có thể được advice bắt match theo loại.

## 4. Ràng buộc kiểu ngoại lệ hoạt động ra sao?

Khi dùng `throwing`, **kiểu khai báo của advice parameter** thu hẹp các exception có thể match:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error"
)
public void onInvalidInput(IllegalArgumentException error) {
    System.out.println("INVALID: " + error.getMessage());
}
```

Nếu method đích ném `new IllegalArgumentException(...)`, advice trên có thể chạy; nếu ném `new IllegalStateException(...)`, advice đó **không chạy**, dù cả hai đều là `RuntimeException`.

| Kiểu tham số advice | Những throwable tương thích về kiểu | Ví dụ không match |
| --- | --- | --- |
| `Throwable` | Bất kỳ subtype của `Throwable` | Không có subclass của `Throwable` nào bị loại chỉ vì kiểu |
| `Exception` | Checked exceptions, `RuntimeException` và các subtype | `Error` không phải `Exception` |
| `RuntimeException` | Các runtime exceptions và subtype | `IOException`, `Error` |
| `IllegalArgumentException` | `IllegalArgumentException` và subclass | `IllegalStateException` |
| `IOException` | `IOException` và subclass | `IllegalArgumentException` |
| `FileNotFoundException` | `FileNotFoundException` và subclass | `IOException` không thuộc subtype `FileNotFoundException` |

**So sánh bằng quan hệ kế thừa, không nhất thiết trùng class chính xác.** Ví dụ nếu `MissingFieldException extends IllegalArgumentException`, advice nhận `IllegalArgumentException` vẫn có thể được gọi khi runtime throwable là `MissingFieldException`.

Chú ý: điều kiện runtime exception type **khác** điều kiện subtype/class của target service trong `target(Type)` hoặc `this(Type)`. `throwing` nói về đối tượng throwable rời khỏi join point, không nói về class của target bean.

## 5. Demo Java 17+: match theo `IllegalArgumentException` và `IOException`

Ví dụ này tạo một Spring AOP proxy cho service và sử dụng **hai method advice có pointcut khác nhau** để tránh nhầm thứ tự giữa các advice:

- `onIllegalArgument(...)` chọn execution của `process(..)`, chỉ nhận `IllegalArgumentException`.
- `onIOException(...)` chọn execution của `load(..)`, chỉ nhận `IOException`.
- Method `process("ok")` thành công.
- Method `process("handled")` có exception nội bộ nhưng **bắt lỗi trước khi return**; advice không chạy.
- Method `process("bad")` ném `IllegalArgumentException`, advice thứ nhất chạy.
- Method `process("state")` ném `IllegalStateException`, advice thứ nhất **không** chạy vì không đúng subtype.
- Method `load()` ném checked `IOException`, advice thứ hai chạy.

Ứng dụng sử dụng **Java 17+, Maven, Spring Framework 6.2.6**; không cần Spring Boot. Dùng `@Bean` để Spring đăng ký các bean một cách tường minh.

### 5.1. Cấu trúc tệp

```text
spring-aop-after-throwing/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AfterThrowingDemo.java
```

### 5.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-after-throwing</artifactId>
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
                    <mainClass>demo.AfterThrowingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Tệp `src/main/java/demo/AfterThrowingDemo.java`

```java
package demo;

import java.io.IOException;

import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class AfterThrowingDemo {

    public interface TaskService {
        String process(String scenario);
        void load() throws IOException;
    }

    public static class TaskServiceImpl implements TaskService {
        @Override
        public String process(String scenario) {
            System.out.println("TARGET process " + scenario);

            if ("bad".equals(scenario)) {
                throw new IllegalArgumentException("missing id");
            }

            if ("state".equals(scenario)) {
                throw new IllegalStateException("unavailable");
            }

            if ("handled".equals(scenario)) {
                try {
                    throw new IllegalArgumentException("internal");
                } catch (IllegalArgumentException ex) {
                    return "RECOVERED";
                }
            }

            return "OK";
        }

        @Override
        public void load() throws IOException {
            System.out.println("TARGET load");
            throw new IOException("cannot read file");
        }
    }

    @Aspect
    public static class FailureAspect {
        @AfterThrowing(
            pointcut = "execution(* demo..*.process(..))",
            throwing = "failure",
            argNames = "failure"
        )
        public void onIllegalArgument(IllegalArgumentException failure) {
            System.out.println("ADVICE illegal " + failure.getMessage());
        }

        @AfterThrowing(
            pointcut = "execution(* demo..*.load(..))",
            throwing = "failure",
            argNames = "failure"
        )
        public void onIOException(IOException failure) {
            System.out.println("ADVICE io " + failure.getMessage());
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
        public FailureAspect failureAspect() {
            return new FailureAspect();
        }
    }

    private static void callProcess(TaskService service, String scenario) {
        try {
            System.out.println(
                "CLIENT result=" + service.process(scenario)
            );
        } catch (RuntimeException ex) {
            System.out.println(
                "CLIENT caught " + ex.getClass().getSimpleName()
                        + ":" + ex.getMessage()
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

            callProcess(service, "ok");
            callProcess(service, "handled");
            callProcess(service, "bad");
            callProcess(service, "state");

            try {
                service.load();
            } catch (IOException ex) {
                System.out.println(
                    "CLIENT caught IOException:" + ex.getMessage()
                );
            }
        }
    }
}
```

### 5.4. Chạy project

Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Các dòng **do chương trình tự in, theo thứ tự** (không tính logging Maven/Spring nếu có):

```text
AOP_PROXY=true
TARGET process ok
CLIENT result=OK
TARGET process handled
CLIENT result=RECOVERED
TARGET process bad
ADVICE illegal missing id
CLIENT caught IllegalArgumentException:missing id
TARGET process state
CLIENT caught IllegalStateException:unavailable
TARGET load
ADVICE io cannot read file
CLIENT caught IOException:cannot read file
```

### 5.5. Giải thích từng nhánh

**Nhánh `ok`:** target trả bình thường, nên không có `@AfterThrowing`. Điều này vẫn đúng nếu method trả `null` hoặc một object thể hiện lỗi ở mức nghiệp vụ mà không ném exception.

**Nhánh `handled`:** target đã ném `IllegalArgumentException` **trong nội bộ**, nhưng tự bắt rồi trả `"RECOVERED"`. Từ ranh giới method execution mà Spring AOP thấy, method kết thúc bình thường, nên advice không nhận exception nội bộ đó.

**Nhánh `bad`:** target ném `IllegalArgumentException`. Pointcut `process(..)` khớp, kiểu tham số `IllegalArgumentException` phù hợp, nên `onIllegalArgument(...)` chạy trước khi caller nhận exception. Advice chỉ log rồi return `void`; nó **không nuốt lỗi**. Vì vậy caller vẫn bắt được đúng exception.

**Nhánh `state`:** target ném `IllegalStateException`. Đây là subtype của `RuntimeException` nhưng **không phải** subtype của `IllegalArgumentException`. `onIllegalArgument(...)` không chạy; exception vẫn thoát ra client.

**Nhánh `load`:** target ném `IOException`, method đã khai báo `throws IOException` cho Java compiler. Advice `onIOException(IOException failure)` chạy vì cả method matching và thrown exception type đều phù hợp.

Ví dụ có hai `@AfterThrowing` advices trong một aspect nhưng chúng khớp **hai method khác nhau**, nên không phụ thuộc thứ tự bất định của nhiều advice cùng loại trên một join point.

## 6. Hiểu sâu: exception hierarchy và cách chọn tham số

Một bảng ví dụ về quan hệ kiểu:

```text
Throwable
├── Error
└── Exception
    ├── IOException
    │   └── FileNotFoundException
    └── RuntimeException
        ├── IllegalArgumentException
        └── IllegalStateException
```

Khi khai báo:

```java
@AfterThrowing(
    pointcut = "execution(* com.example..service..*.*(..))",
    throwing = "failure"
)
public void onFailure(RuntimeException failure) {
    System.out.println(failure.getClass().getName());
}
```

advice được chọn cho những method match pointcut và ném **RuntimeException hoặc subclass**, chẳng hạn `IllegalArgumentException` / `IllegalStateException`. Nhưng nó không chạy cho checked `IOException`.

Nếu cần phân biệt nhiều nhóm mà không tranh chấp thứ tự advice, có thể:

1. Dùng một advice với tham số kiểu rộng `Throwable` và phân nhánh xử lý theo subtype khi cần.
2. Dùng nhiều aspects với pointcut/throwing type riêng, xác lập thứ tự bằng `@Order` nếu cùng một join point có nhiều advice match.
3. Chọn kiểu đủ hẹp nếu behavior chỉ phục vụ một nhóm ngoại lệ.

Ví dụ một advice chung:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "failure"
)
public void report(Throwable failure) {
    if (failure instanceof IllegalArgumentException) {
        System.out.println("BAD-INPUT");
    } else if (failure instanceof IOException) {
        System.out.println("IO");
    } else {
        System.out.println("OTHER-FAILURE");
    }
}
```

Đây là **snippet** cho bean `@Aspect`, không phải chương trình standalone. Đừng dùng `Throwable` theo phản xạ nếu hệ thống chỉ quan tâm đến nhóm `Exception`; bạn có thể vô tình log các `Error` nghiêm trọng mà không có chiến lược ứng phó phù hợp.

### Subclass exception vẫn match

```java
public class InvalidOrderException extends IllegalArgumentException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Khi method đích ném `InvalidOrderException`, advice có tham số `IllegalArgumentException` **vẫn match** vì subtype hợp lệ. Việc binding không đòi thrown exception có class chính xác bằng parameter type.

## 7. `@AfterThrowing` không phải khối `catch` xử lý lỗi

Một hiểu lầm thường gặp: đặt `@AfterThrowing` để **bắt lỗi rồi trả fallback cho caller**.

```java
@AfterThrowing(
    pointcut = "execution(* com.example..*.find(..))",
    throwing = "error"
)
public void recover(IllegalStateException error) {
    System.out.println("FALLBACK?");
}
```

Đây là **snippet không có logic fallback**. Method advice trả `void` và không có quyền thay thế kết quả của target bằng một giá trị return của advice. Nó được thiết kế để chạy sau khi join point thoát bằng lỗi.

Nếu cần **chặn exception, chuyển đổi exception hoặc trả fallback**, dùng `@Around`:

```java
@Around("execution(* com.example.app.service..*.find(..))")
public Object fallback(ProceedingJoinPoint joinPoint) throws Throwable {
    try {
        return joinPoint.proceed();
    } catch (IllegalStateException ex) {
        return "FALLBACK";
    }
}
```

Đoạn `@Around` trên là **mẫu minh họa**: cần đặt trong `@Aspect` bean và kiểu return `String` phải tương thích với method target. Nó cho phép lời gọi đi tiếp bằng `proceed()`, bắt exception được ném từ phía trong và trả một giá trị khác.

Nếu around advice nuốt exception ở một vị trí trong chain, advice `@AfterThrowing` nằm **ngoài** nó có thể không quan sát được lỗi gốc, vì phần phía trong đã trả bình thường. Do đó khi có nhiều advisors, cần xét **thứ tự nesting** và xem mỗi advice nhìn thấy kết quả/exception nào.

### Việc ném một exception khác trong advice

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.save(..))",
    throwing = "error"
)
public void logFailure(RuntimeException error) {
    // Có thể log, gửi metric; tránh tùy tiện throw exception mới ở đây.
}
```

Nếu advice tự ném exception, exception mới có thể ảnh hưởng đường lỗi client nhận. Đây không phải cách mặc định để wrap/recover lỗi nghiệp vụ. Khi cần ánh xạ exception rõ ràng, `@Around` làm chủ control flow thường dễ đọc và dễ kiểm thử hơn.

## 8. So sánh `@AfterThrowing` với những loại advice khác

| Advice | Khi nào chạy trong Spring AOP? | Có bind exception? | Có điều khiển flow bằng `proceed()`? |
| --- | --- | --- | --- |
| `@Before` | Trước matched method execution | Không phải binding throwable từ method outcome | Không |
| `@AfterReturning` | Method execution trả bình thường | Không, bind return qua `returning` nếu cần | Không |
| `@AfterThrowing` | Method execution ném exception phù hợp | **Có, qua `throwing`** | Không |
| `@After` | Sau method execution, bất kể normal hay exceptional exit | Không phải dạng bind exception như `@AfterThrowing` | Không |
| `@Around` | Bao quanh phần execution/interceptors phía trong | Có thể tự `catch` exception từ `proceed()` | **Có** |

Trong Spring, `@After` được dùng theo ý nghĩa **finally**: phù hợp với cleanup luôn phải chạy. `@AfterThrowing` chỉ chạy trên nhánh lỗi, thích hợp cho error-only logging/metrics. Nếu cần biến lỗi thành kết quả hoặc thực hiện retry, cân nhắc around advice.

### Thứ tự các advice có ảnh hưởng

Ví dụ nếu một method được nhiều aspects advice:

```text
Outer @Around: enter
    Target: throws IllegalArgumentException
    Inner @AfterThrowing: log error (nếu điều kiện khớp)
Outer @Around: catch -> trả fallback
Client: nhận fallback
```

Đây là **một kịch bản thứ tự có thể xảy ra**, không phải thứ tự mặc định cố định. Nếu `@Around` xử lý exception trước khi một outer `@AfterThrowing` nhận nó, outer advice có thể không chạy. Spring cho phép `@Order` / `Ordered` để xác định precedence giữa các aspects, nhưng cần kiểm thử với thứ tự cấu hình hiệu lực.

Không dựa vào thứ tự khai báo hai methods `@AfterThrowing` cùng loại trong cùng aspect để dự đoán thứ tự execution nếu chúng match cùng một join point. Tài liệu Spring nêu không có thứ tự ổn định dựa vào thứ tự source Java cho advice cùng loại; khi thứ tự quan trọng, refactor hoặc tách aspects và khai báo order.

## 9. Những lỗi binding thường gặp

### 9.1. Tên trong `throwing` không trùng tên advice parameter

Sai:

```java
@AfterThrowing(
    pointcut = "execution(* com.example..*.save(..))",
    throwing = "cause"
)
public void onFailure(IOException error) {
    // Tên trong throwing và tham số không đồng nhất.
}
```

Đây là **mã sai để minh họa**. Spring cần bind `cause` nhưng Java method khai báo tham số `error`. Nếu tên không được resolve/khớp đúng, context có thể báo lỗi binding/pointcut khi tạo advisor hoặc gọi.

Đúng:

```java
@AfterThrowing(
    pointcut = "execution(* com.example..*.save(..))",
    throwing = "error",
    argNames = "error"
)
public void onFailure(IOException error) {
    // Có thể đọc exception được bind.
}
```

Với tham số khác như `JoinPoint` hoặc nhiều binding, phải xét đầy đủ `argNames` và số lượng/kiểu tham số, tránh cho Spring suy tên sai khi Java bytecode không lưu parameter names.

### 9.2. Dùng method parameter type không phải Throwable

Không viết advice `throwing` nhận `String` rồi kỳ vọng `error.getMessage()` hay tự convert thrown exception thành chuỗi. Với `@AfterThrowing`, tham số `throwing` phải dùng kiểu phù hợp throwable mà bạn muốn match.

### 9.3. Dùng kiểu hẹp hơn exception thực tế

Ví dụ `onFailure(FileNotFoundException e)` không chạy với mọi `IOException`. Nó chỉ chạy khi runtime exception là `FileNotFoundException` hoặc subtype. Đây là feature chọn theo kiểu, không phải bug của Spring.

### 9.4. Quên đăng ký aspect thành Spring bean

Chỉ có `@Aspect` trên class không bảo đảm Spring tự quét và đăng ký. Có thể kết hợp `@Component` và component-scan hoặc đăng ký qua `@Bean`; đồng thời kích hoạt xử lý @AspectJ bằng `@EnableAspectJAutoProxy` trong Spring Framework thuần hoặc auto-configuration Spring Boot phù hợp.

### 9.5. Pointcut không khớp tên method/package

Nếu exception ném đúng loại nhưng `execution(...)` chỉ chọn một package khác, advice vẫn không chạy. Khi debug, tạm sử dụng một pointcut method rõ ràng rồi thu hẹp theo package/annotation để xác định điều kiện nào không match.

### 9.6. Phương thức tự bắt exception

Đây là ngữ nghĩa chuẩn của method execution, không phải lỗi binding. Spring AOP chỉ thấy **method kết thúc bình thường**, vì vậy không chạy `@AfterThrowing` cho exception đã được catch trong target rồi trả thành công.

## 10. Ứng dụng Spring thực tế: audit, metrics, transaction, async

### 10.1. Audit và metrics trên nhánh lỗi

Một advice có thể ghi sự kiện theo kiểu exception:

```java
@AfterThrowing(
    pointcut = "execution(public * com.example.app.service..*.*(..))",
    throwing = "error"
)
public void recordFailure(Exception error) {
    metrics.increment("service.failure", error.getClass().getSimpleName());
}
```

Đây là **mẫu kiến trúc**, cần một dependency `metrics` được inject qua Spring và API recorder phù hợp. Không nên giả định thư viện metrics nào cũng có chữ ký `increment(...)` như minh họa.

Nếu aspect gọi một collaborator được advice khác, cần kiểm tra pointcut không vô tình bao phủ chính collaborator đó và tạo vòng gọi lặp. Nên giới hạn pointcut đúng service boundary.

### 10.2. Spring transaction và ngoại lệ

Một method có `@Transactional` thường được intercept bởi transaction advisor riêng. `@AfterThrowing` của bạn chỉ là một advisor khác nếu pointcut khớp; **thời điểm log xảy ra so với transaction rollback** phụ thuộc thứ tự advisors. Không suy rằng cứ `@AfterThrowing` chạy thì transaction đã rollback.

Quy tắc rollback của Spring transaction còn tùy loại exception và cấu hình `rollbackFor` / `noRollbackFor`. `@AfterThrowing` không tự cấu hình rollback.

### 10.3. Checked exception và JDK dynamic proxy

Khi dùng JDK dynamic proxy, method có checked `IOException` được khai báo trên interface là cách trực tiếp để caller bắt `IOException` đúng contract. Với các checked exceptions **không khai báo** trên interface method mà bị đẩy qua một JDK dynamic proxy, Java proxy semantics có thể bọc chúng thành `UndeclaredThrowableException`. Điều đó khác với việc `@AfterThrowing` **nhìn thấy throwable tại target execution** và bind theo runtime type.

Tránh dùng ý tưởng “unchecked/checked được quyết định bởi `@AfterThrowing`”. Annotation này không làm Java bỏ luật khai báo checked exceptions.

### 10.4. Async execution

Nếu có `@Async`, method thực có thể chạy trên thread của executor và kết quả được biểu diễn qua `Future` / `CompletableFuture` hoặc handler riêng cho `void`. Một exception xảy ra trên async thread **không tự tương đương** với exception đồng bộ thoát ra từ lời gọi proxy mà advice phía ngoài nhìn thấy. Khi audit lỗi async, phải xét vị trí advisor, contract của async method và cơ chế completion/error handling của future.

### 10.5. Retry và fallback

Nếu dùng retry advice (ví dụ thông qua một `@Around` hoặc Spring Retry phù hợp), **một lời gọi từ client có thể dẫn đến nhiều lần target execution**. Một `@AfterThrowing` nằm bên trong retry loop có thể được gọi ở mỗi thất bại, trong khi advice nằm ngoài loop chỉ thấy lỗi cuối sau khi retry cạn. Khi metric cần “số attempt” hay “số failed client requests”, phải cấu hình đúng thứ tự advisors hoặc đếm tại đúng ranh giới.

## 11. Tối ưu thiết kế advice xử lý sự kiện lỗi

Một `@AfterThrowing` tốt thường:

1. **Giữ side-effect gọn và có giới hạn**, như log/metric/audit; không gọi network sync dài nếu đường lỗi latency quan trọng.
2. **Không chứa dữ liệu nhạy cảm không cần thiết** trong log. `Exception.getMessage()` có thể chứa input do client cung cấp hoặc chi tiết database/path nội bộ.
3. **Không ném exception mới tùy tiện** chỉ vì logging/metric thất bại. Nếu telemetry thất bại cũng phá error path, nguyên nhân thật có thể bị che khuất.
4. **Giữ pointcut đủ hẹp**, ví dụ chỉ public service methods, tránh ghi lặp trên proxy hoặc hạ tầng không chủ đích.
5. **Tránh duplicate logs** trên mỗi tầng service nếu pointcut phủ quá rộng và cùng một exception đi qua nhiều proxy calls. Chọn nơi ghi nhận phù hợp (một service boundary hoặc outer request boundary) và đưa correlation ID khi cần.
6. **Chọn exception type đúng ý định**: `IllegalArgumentException` cho nhóm validation cụ thể, `RuntimeException` cho runtime failure, `Throwable` chỉ nếu thật sự cần cả `Error`.
7. **Kiểm tra đường đi proxy** bằng integration test, đặc biệt với self-invocation và lựa chọn JDK/CGLIB.
8. **Có positive/negative test**: test lỗi đúng subtype, sai subtype, successful return và exception đã xử lý trong target.

Nếu muốn biến đổi exception thành API response, đặt xử lý ở tầng thích hợp (ví dụ exception handler web layer) thay vì trông chờ `@AfterThrowing` trả một giá trị mới cho method đã thất bại.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Method được advice trả về `"ERROR"` nhưng không ném exception. `@AfterThrowing` chạy không?  
**Đáp án:** Không. Đây là normal return ở Spring AOP method execution level.

**Câu 2.** Advice dùng `throwing="ex"`, nhưng method Java khai báo tham số `IOException error`. Có vấn đề gì?  
**Đáp án:** Tên binding không khớp. Cần `throwing="error"` hoặc đổi tên advice parameter tương ứng, kết hợp `argNames` nếu cần.

**Câu 3.** `@AfterThrowing` với tham số `IllegalArgumentException` có nhận `IllegalStateException` không?  
**Đáp án:** Không. Hai class là những nhánh khác nhau của `RuntimeException`.

**Câu 4.** Một `InvalidOrderException extends IllegalArgumentException` được target ném ra. Advice nhận `IllegalArgumentException` có match không?  
**Đáp án:** Có, miễn method execution và điều kiện pointcut phù hợp.

**Câu 5.** Target bắt `IOException` rồi trả `false`. Advice nhận `IOException` có chạy không?  
**Đáp án:** Không. Exception không thoát ra khỏi method execution.

**Câu 6.** Dùng `@AfterThrowing` để trả string `"FALLBACK"` cho caller được không?  
**Đáp án:** Không theo contract advice này. Muốn điều khiển return/exception flow, dùng `@Around` hoặc cách xử lý tại tầng nghiệp vụ phù hợp.

**Câu 7.** Khi method `process()` gọi `this.load()` trong cùng target, lời gọi `load()` có được Spring AOP advice riêng không?  
**Đáp án:** Không có proxy boundary mới nếu là self-invocation; advice chỉ khớp `load()` không tự chạy cho lời gọi nội bộ ấy.

**Câu 8.** Advice `@AfterThrowing` chạy thì chắc chắn transaction đã rollback chưa?  
**Đáp án:** Chưa thể kết luận. Cần xem transaction advisor order và rollback rules.

**Câu 9.** Một advice dùng `Throwable` và một advice dùng `RuntimeException` đều match lỗi `IllegalArgumentException`. Có thể dựa vào thứ tự khai báo source để xác định thứ tự của chúng không?  
**Đáp án:** Không. Nếu thứ tự quan trọng, hãy thiết kế/tách aspect rõ ràng và khai báo precedence thích hợp.

## 13. Checklist chẩn đoán nhanh

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| Advice không chạy khi method fail | Method có đi qua proxy? Pointcut `execution(...)` có đúng package/method? |
| Một loại exception chạy, loại khác không | Kiểu tham số của `throwing` có phải supertype của thrown exception không? |
| Advice nhận exception khác dự đoán | Có interceptor phía trong wrap exception? Có proxy JDK/checked-exception behavior? |
| Advice không chạy dù bên trong method có `throw` | Exception có bị catch trước khi method thoát? |
| Spring báo lỗi binding | Tên `throwing`, method parameter, `argNames` có đồng nhất không? |
| Log lỗi bị nhân đôi | Pointcut phủ nhiều service boundaries hoặc retry nhiều attempts? |
| Method đổi từ trả exception sang fallback | Có `@Around` ở trong đã catch/return thành công? |
| Lỗi cuối bị thay bằng lỗi log | Advice có tự throw exception khi logging/metric thất bại không? |
| Advice chạy nhưng rollback không như nghĩ | Xem transaction ordering và rollback rules; `@AfterThrowing` không điều khiển chúng |
| Chỉ xảy ra khác biệt ở async methods | Kiểm tra executor, future completion và thứ tự async/advisor |

## 14. Tài liệu Spring Framework chính thức

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@AfterThrowing`, `throwing` binding, exception type filtering, after-finally/around và precedence.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation và giới hạn phương thức.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): bật xử lý Spring AOP @AspectJ style và đăng ký aspect bean.
- [Spring Framework — AspectJ Advice API and Parameters](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): bind tham số advice, `argNames` và method arguments.
