# `args` theo kiểu đối số thực tế trong Spring AOP

## 1. Mục tiêu của `args(...)` khi viết Spring Aspect

Trong Spring AOP, pointcut `args(...)` chọn **lần thực thi phương thức trên Spring bean thông qua proxy** dựa trên **các đối số thực sự được truyền ở thời điểm gọi**. Khác với `execution(...)`, vốn có thể giới hạn theo chữ ký của phương thức được khai báo, `args` là một điều kiện có thể phụ thuộc vào dữ liệu runtime của từng invocation.

Ví dụ một bean có method:

```java
public void send(Object payload) {
    // ...
}
```

Cùng method `send(Object)` có thể được gọi với `"hello"` (một `String`), `Integer.valueOf(7)`, hoặc một đối tượng tùy chỉnh không triển khai `Serializable`. Một pointcut `args(java.io.Serializable)` có thể chọn những lần gọi mang **đối số thực tế thuộc kiểu `Serializable`**, dù method đã khai báo tham số là `Object`.

Điểm khác biệt cốt lõi:

```text
Method khai báo: send(Object value)

send("hello")           -> runtime value là String, implements Serializable
send(Integer.valueOf(7)) -> runtime value là Integer, implements Serializable
send(new PlainPayload()) -> runtime value là PlainPayload, không Serializable

execution(* *.send(java.io.Serializable)) -> xét tham số khai báo
args(java.io.Serializable)                -> xét đối số thực tế tại lời gọi
```

**Phạm vi:** Bài chỉ giải thích `args` trong **Spring @AspectJ-style AOP, áp dụng lên các Spring-managed beans được gọi qua AOP proxy**. Đây không phải bài AspectJ weaving độc lập, không bàn chung chung về pointcut ngoài phạm vi Spring.

## 2. Phân biệt chính xác `args` và `execution`

Hai biểu thức trông giống nhau nhưng không tương đương:

```java
// Chỉ áp dụng cho method có đúng một tham số khai báo kiểu Serializable:
execution(* *.send(java.io.Serializable))

// Xét một đối số được truyền lúc chạy có kiểu phù hợp với Serializable:
args(java.io.Serializable)
```

Giả sử một `MessageGateway` khai báo:

```java
void send(Object payload);
```

Khi caller đưa `String` vào, chữ ký Java **vẫn là** `send(Object)`; JVM không đổi chữ ký phương thức thành `send(String)`. Vì vậy:

- `execution(* *.send(java.io.Serializable))` **không khớp** chữ ký `send(Object)` chỉ vì caller truyền `String`.
- `args(java.io.Serializable)` có thể **khớp lần thực thi** khi giá trị runtime implements `Serializable`.
- Lần gọi tiếp theo truyền đối tượng không implements `Serializable` có thể **không khớp**, dù method và proxy vẫn là những đối tượng cũ.

Tài liệu chính thức Spring đưa đúng sự phân biệt này qua `args(java.io.Serializable)` và `execution(* *(java.io.Serializable))`: cái thứ nhất xét argument runtime, cái thứ hai xét khai báo chữ ký.

| Tiêu chí | `execution(...)` | `args(...)` |
| --- | --- | --- |
| Thông tin trọng tâm | Method execution, tên method, return type, kiểu tham số **khai báo** | Kiểu các **đối số thực tế** được truyền |
| Một method nhận các kiểu object khác nhau | Điều kiện chữ ký vẫn vậy | Kết quả match có thể khác giữa hai lần gọi |
| Thời điểm Spring đánh giá | Nhiều phần có thể xác định trước khi invoke | Phần cần runtime args phải kiểm tra ở mỗi invocation |
| Dùng để giới hạn package/class/method | Rất phù hợp | Không thay thế được scoping theo class/method |
| Dùng để lấy giá trị argument trong advice | Không trực tiếp bind giá trị chỉ nhờ chữ ký | Dùng `args(name)` kết hợp tham số advice để bind |
| Đối tượng ngoài Spring container | Không được Spring AOP auto-proxy | Cũng không được Spring AOP auto-proxy |

**Đừng dùng `args` để thay thế toàn bộ `execution`.** Thực hành tốt trong Spring là kết hợp một điều kiện tĩnh hẹp với điều kiện runtime:

```java
@Before(
  "execution(public * com.example.app.MessageGateway.send(..))" +
  " && args(java.io.Serializable)"
)
public void beforeSerializable() {
    // ...
}
```

Đây là **fragment minh họa** cần được đặt trong một Spring `@Aspect` đã đăng ký. Biểu thức ngoài giới hạn đến method `send` của service, còn `args` chỉ lọc kiểu runtime. Tránh `args(java.io.Serializable)` đứng đơn lẻ trên toàn bộ application nếu không có lý do rõ: nó có thể chọn nhiều method ngoài dự kiến.

## 3. Cú pháp `args` trong Spring pointcut expressions

### 3.1. Một đối số thuộc kiểu nhất định

```text
args(java.io.Serializable)
args(com.example.domain.OrderRequest)
```

`args(java.io.Serializable)` chọn join point có **đúng một đối số** phù hợp với `Serializable`. Tương tự, `args(com.example.domain.OrderRequest)` dùng kiểu `OrderRequest` mà ứng dụng khai báo.

AspectJ type matching xét quan hệ assignability: đối tượng `String` implements `Serializable`; một subclass của `OrderRequest` cũng phù hợp nếu có quan hệ kiểu phù hợp. Spring đánh giá điều kiện đó trên lời gọi method của Spring bean mà proxy có thể intercept, chứ không phải mọi lời gọi Java trong JVM.

### 3.2. Nhiều đối số và dấu `..`

```text
args(java.io.Serializable, java.lang.String)
args(java.io.Serializable, ..)
args(.., java.lang.String)
args(*, java.lang.String)
args(..)
```

- `args(Serializable, String)`: phương thức được gọi với **đúng hai** arguments phù hợp theo thứ tự đó.
- `args(Serializable, ..)`: **đối số đầu tiên** có kiểu phù hợp với `Serializable`, sau đó có thể có **không hoặc nhiều** đối số khác.
- `args(.., String)`: đối số **cuối cùng** có kiểu phù hợp với `String`, trước đó có thể có bất kỳ số lượng arguments nào.
- `args(*, String)`: có đúng hai arguments; `*` là pattern một argument bất kỳ trong vị trí đầu.
- `args(..)`: không giới hạn kiểu hoặc số arguments; đứng một mình thường không phải một bộ lọc đủ hẹp.

Khi pattern có nhiều đối số, **vị trí rất quan trọng**. Với method `save(String id, Object payload)`, `args(Serializable, ..)` xét `id`, không tự nhảy sang `payload` ở vị trí thứ hai. Chọn pattern hoặc bind theo đúng vị trí cần kiểm tra.

### 3.3. `args(type)` và `args(variable)` là hai hình thức sử dụng khác nhau

Trong annotation pointcut:

```java
args(java.io.Serializable)
```

là **type pattern**. Còn:

```java
args(payload)
```

có thể là **binding** khi `payload` được khai báo là tham số trong phương thức advice hoặc named pointcut. Type của tham số Java được bind góp phần quyết định kiểu argument hợp lệ.

Đừng viết `args(payload)` trong annotation nhưng lại quên khai báo `payload` trong advice hoặc không cung cấp thông tin binding mà Spring có thể xác định. Kết quả thường là lỗi khởi tạo aspect/pointcut, không phải lời advice bí mật bỏ qua mọi invocation.

### 3.4. `args` khác `@args`

`args(com.example.domain.OrderRequest)` xét **kiểu đối số** có tương thích với `OrderRequest` không.

`@args(com.example.annotations.Classified)` xét **annotation có trên kiểu runtime của đối số** theo cơ chế AspectJ, không phải kiểu `Classified` của đối số và cũng không phải annotation đặt trên tham số trong chữ ký method.

Đây là **hai pointcut designators riêng biệt được Spring AOP hỗ trợ**. Nếu mục tiêu là annotation của method đang được gọi, hãy xem `@annotation`, không nhầm với `@args`.

## 4. Binding giá trị argument vào phương thức advice

Một tính năng rất hữu ích trong Spring `@Aspect` là đưa đối số runtime vào method advice dưới dạng Java parameter có kiểu rõ ràng.

Ví dụ fragment:

```java
@Aspect
public class AuditAspect {
    @Before(
        value = "execution(public * com.example.app.MessageGateway.send(..))"
              + " && args(payload)",
        argNames = "payload"
    )
    public void before(Serializable payload) {
        System.out.println(payload.getClass().getSimpleName());
    }
}
```

Ở đây:

1. `execution(...send(..))` giới hạn phạm vi method.
2. `args(payload)` yêu cầu một đối số khớp và **bind** đối số đó vào tên `payload`.
3. Advice khai báo `Serializable payload`, vì vậy kiểu bind được kiểm tra theo Java type đó.
4. `argNames = "payload"` làm rõ tên tham số dùng khi liên kết advice; không phải tên field hay bean trong container.
5. Khi advice chạy, `payload` chính là object được truyền lúc gọi, không phải một object Spring tự tạo để hợp với pointcut.

**Spring phải tìm được tên parameter cho binding.** Có thể dùng `argNames`, compile giữ thông tin tên tham số thích hợp hoặc những cơ chế khám phá tên mà phiên bản Spring hỗ trợ. Việc khai báo `argNames` rõ ràng là cách giảm phụ thuộc build flags trong ví dụ.

### 4.1. `JoinPoint.getArgs()` và `args(name)`

Hai cách lấy arguments thường gặp:

```java
@Before("execution(* com.example.app.MessageGateway.send(..))")
public void observe(org.aspectj.lang.JoinPoint jp) {
    Object[] arguments = jp.getArgs();
    // Tự kiểm tra argument types khi cần.
}
```

và:

```java
@Before(
    value = "execution(* com.example.app.MessageGateway.send(..))"
          + " && args(payload)",
    argNames = "payload"
)
public void observe(Serializable payload) {
    // Có argument được bind theo kiểu.
}
```

Đây là **hai fragments thay thế nhau**, không phải hai advice bắt buộc chạy cùng lúc.

- `JoinPoint.getArgs()` cung cấp mảng đối số cho lời gọi mà advice đã match, giúp inspect tùy điều kiện.
- `args(payload)` làm việc **lọc và bind** ngay trong pointcut, giảm số kiểm tra kiểu thủ công trong advice.
- Nếu ứng dụng cần lọc theo **giá trị** (ví dụ `amount > 1000`) chứ không chỉ kiểu, vẫn phải kiểm tra giá trị trong advice hoặc thiết kế predicate khác; `args(java.lang.Number)` không tự kiểm tra khoảng giá trị.

### 4.2. Ví dụ hai đối số

Với method `reserve(String orderId, Object data)`:

```java
@Before(
    value = "execution(* com.example..ReservationService.reserve(..))"
          + " && args(orderId, data)",
    argNames = "orderId,data"
)
public void beforeReserve(String orderId, Serializable data) {
    // Runtime data phải thỏa điều kiện Serializable.
}
```

Đây là fragment cần class/package thích hợp. Nó bind **hai vị trí** theo thứ tự. Nếu signature method có thêm tham số thứ ba, expression `args(orderId,data)` không còn khớp vì nó mô tả đúng hai arguments. Khi muốn giữ phần cuối linh hoạt, dùng dấu `..` hợp lý và đối chiếu vị trí thực tế.

## 5. Ví dụ chạy được: `send(Object)` nhưng advice chọn kiểu runtime

Ví dụ đầy đủ sau sử dụng **Java 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1 và Maven**.

Thiết kế có chủ đích:

- `MessageGateway.send(Object)` luôn có **chữ ký tham số Object**.
- Caller lần lượt truyền `String`, `PlainPayload` không implements `Serializable`, và `Integer`.
- Một advice **dùng `args(payload)` với tham số `Serializable`** để chọn `String`/`Integer` theo kiểu runtime.
- Một advice đối chứng dùng `execution(...send(java.io.Serializable))` để cho thấy phương thức khai báo `Object` không đột ngột biến thành chữ ký `Serializable`.
- Spring AOP dùng **JDK proxy** qua business interface; target không tự gọi nội bộ để tránh nhiễu ranh giới proxy.

### 5.1. Cấu trúc project

```text
spring-aop-runtime-args/
├── pom.xml
└── src/main/java/com/example/argsdemo/
    ├── AppConfig.java
    ├── MessageGateway.java
    ├── MessageService.java
    ├── ArgsAuditAspect.java
    └── DemoApp.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-runtime-args</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp Spring container và kéo các module Spring AOP nền tảng theo cây dependency phù hợp của bộ ví dụ. `aspectjweaver` cho phép Spring xử lý khai báo `@Aspect`/pointcut. Mục tiêu là **Spring proxy-based AOP**; không bật AspectJ compiler hay weaving agent.

### 5.3. `src/main/java/com/example/argsdemo/MessageGateway.java`

```java
package com.example.argsdemo;

public interface MessageGateway {
    void send(Object payload);
}
```

Method chỉ có một tham số **khai báo `Object`**, bất kể caller sau này truyền object thuộc class nào. Interface giúp ví dụ sử dụng JDK dynamic proxy mà không cần class-based proxy.

### 5.4. `src/main/java/com/example/argsdemo/MessageService.java`

```java
package com.example.argsdemo;

public class MessageService implements MessageGateway {
    @Override
    public void send(Object payload) {
        String type = payload.getClass().getSimpleName();
        System.out.println("[TARGET] " + type + ": " + payload);
    }
}
```

Để in output ổn định và tránh lẫn với quy tắc `null`, ví dụ chỉ truyền các objects khác `null`. Với ứng dụng thật, nếu API cho phép null thì target phải kiểm tra `payload == null` trước khi gọi `getClass()`.

### 5.5. `src/main/java/com/example/argsdemo/ArgsAuditAspect.java`

```java
package com.example.argsdemo;

import java.io.Serializable;
import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ArgsAuditAspect {
    private final AtomicInteger runtimeMatches = new AtomicInteger();
    private final AtomicInteger signatureMatches = new AtomicInteger();

    @Before(
        value = "execution(public * com.example.argsdemo.MessageGateway.send(..))"
              + " && args(payload)",
        argNames = "payload"
    )
    public void runtimeSerializable(Serializable payload) {
        runtimeMatches.incrementAndGet();
        System.out.println("[AOP args] " + payload.getClass().getSimpleName());
    }

    @Before(
        "execution(public * com.example.argsdemo.MessageGateway.send(java.io.Serializable))"
    )
    public void declaredSerializableSignature() {
        signatureMatches.incrementAndGet();
        System.out.println("[AOP execution] Serializable signature");
    }

    public int runtimeMatches() {
        return runtimeMatches.get();
    }

    public int signatureMatches() {
        return signatureMatches.get();
    }
}
```

Phương thức `runtimeSerializable` bind giá trị kiểu `Serializable` được truyền qua `args(payload)`. Spring phải xem argument runtime của từng lời gọi để quyết định advice có chạy không. Phương thức `declaredSerializableSignature` chỉ khớp nếu method thật sự **khai báo một parameter kiểu Serializable**, điều không đúng với `MessageGateway.send(Object)`.

Hai biến đếm giúp test minh bạch: số lần `@Before` được gọi cho từng quy tắc, không phải số lần object aspect được tạo.

### 5.6. `src/main/java/com/example/argsdemo/AppConfig.java`

```java
package com.example.argsdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
    @Bean
    public MessageGateway messageGateway() {
        return new MessageService();
    }

    @Bean
    public ArgsAuditAspect argsAuditAspect() {
        return new ArgsAuditAspect();
    }
}
```

`@EnableAspectJAutoProxy` bật Spring auto-proxy creator. `MessageGateway` được Spring quản lý; `ArgsAuditAspect` vừa có `@Aspect` vừa được khai báo `@Bean` để Spring nhận diện. Cờ `false` cho phép JDK proxy khi có interface thích hợp, không có cấu hình khác ép CGLIB.

### 5.7. `src/main/java/com/example/argsdemo/DemoApp.java`

```java
package com.example.argsdemo;

import java.io.Serializable;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    private static final class PlainPayload {
        @Override
        public String toString() {
            return "payload";
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            MessageGateway gateway = context.getBean(MessageGateway.class);
            ArgsAuditAspect aspect = context.getBean(ArgsAuditAspect.class);

            System.out.println("isJdkProxy="
                    + AopUtils.isJdkDynamicProxy(gateway));

            gateway.send("hello");
            gateway.send(new PlainPayload());
            gateway.send(Integer.valueOf(7));

            System.out.println("runtimeMatches=" + aspect.runtimeMatches());
            System.out.println("signatureMatches=" + aspect.signatureMatches());
        }
    }
}
```

`PlainPayload` không khai báo `implements Serializable`. `String` và `Integer` đều triển khai `Serializable` trên JDK 17+. Nếu thấy import `java.io.Serializable` trong `DemoApp` mà không được dùng trực tiếp, có thể bỏ import đó mà không ảnh hưởng kết quả; Java compiler cho phép unused imports nên project vẫn biên dịch.

### 5.8. Chạy và output dự kiến

Từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.argsdemo.DemoApp
```

Các dòng chương trình in ra theo đúng thứ tự; thông báo Maven/SLF4J nếu có không nằm trong phần output minh họa:

```text
isJdkProxy=true
[AOP args] String
[TARGET] String: hello
[TARGET] PlainPayload: payload
[AOP args] Integer
[TARGET] Integer: 7
runtimeMatches=2
signatureMatches=0
```

**Giải thích đầu ra:**

1. Spring tạo JDK proxy vì bean implement `MessageGateway` và advisor có thể áp dụng vào method `send(Object)`.
2. `"hello"` là `String`, implements `Serializable`, nên lời gọi qua proxy chạy `runtimeSerializable` trước khi target in nội dung.
3. `PlainPayload` không implements `Serializable`, vì vậy advice có điều kiện `args(payload)` với parameter `Serializable` không chạy; target vẫn thực hiện method.
4. `Integer.valueOf(7)` là `Integer`, cũng implements `Serializable`, nên advice chạy lần thứ hai.
5. `signatureMatches=0` vì method **khai báo Object**, bất kể runtime arguments là gì. Không có lời gọi nào thay đổi method signature ở bytecode.
6. Việc target chạy cả ba lần nhưng advice chỉ chạy hai lần cho thấy `args` đánh giá **mỗi invocation**; kết quả không phải cấu hình cố định của target object.

Code này là demo về **type matching**. Trong production, không coi `Serializable` là dấu hiệu đối số an toàn để ghi log hoặc serialize; nó là một interface marker của Java, không đại diện cho mức độ bảo mật hoặc độ tin cậy của payload.

## 6. Tại sao phải hiểu sự phụ thuộc vào runtime?

Một phần pointcut có thể được Spring đánh giá bằng class/method metadata khi dựng proxy. Nhưng với `args`, **cùng một method trên cùng một proxy** có thể cho kết quả khác nhau theo argument đang được truyền.

Trong API pointcut của Spring, một `MethodMatcher` có:

```java
boolean matches(Method method, Class<?> targetClass);
boolean isRuntime();
boolean matches(Method method, Class<?> targetClass, Object... args);
```

Đây là **các chữ ký giao diện được giản lược để giải thích**, không phải một class có thể biên dịch riêng. Khi `isRuntime()` đúng, Spring có thể cần phương thức kiểm tra có arguments cho từng method invocation. Điều này phản ánh chi phí thực tế của pointcut động, dù Spring còn tối ưu bằng static matching để loại nhanh những target methods không thể khớp.

Thực hành hữu ích:

- **Khoanh class/method bằng `execution` hoặc `within`**, rồi mới bổ sung `args` để lọc kiểu argument.
- Tránh chỉ khai báo `args(java.io.Serializable)` trên toàn application nếu chỉ muốn audit một business API cụ thể.
- Nếu yêu cầu là một method với chữ ký xác định, hãy cân nhắc chỉ dùng `execution` — có thể đơn giản hơn và tránh dynamic matching không cần thiết.
- Không dựa vào lời đồn rằng `args` tự check giá trị, nội dung object hoặc annotation trên class: các yêu cầu đó cần điều kiện khác.

**Vấn đề không chỉ là performance.** Pointcut rộng có thể khiến một advice phụ thuộc dữ liệu runtime được áp dụng tới nhiều module không mong đợi, làm tăng coupling hoặc tạo audit log chứa thông tin không phù hợp.

## 7. Kiểu kế thừa, interface và polymorphism

Giả sử:

```java
interface Event {}

class OrderEvent implements Event {}

class PaymentEvent implements Event {}
```

Đây là fragments minh họa; đặt trong file/package phù hợp khi triển khai.

Khi method khai báo `void handle(Object event)`, pointcut:

```text
args(com.example.domain.Event)
```

có thể khớp runtime arguments là `OrderEvent` hoặc `PaymentEvent` vì chúng implement `Event`. Với:

```text
args(com.example.domain.OrderEvent)
```

bộ lọc hẹp hơn và chỉ chọn đối số thuộc kiểu `OrderEvent` hoặc kiểu con phù hợp.

Trường hợp method khai báo `handle(Event event)` nhưng caller thực tế truyền `OrderEvent`, `execution(* *.handle(com.example.domain.Event))` xét **kiểu khai báo Event**, còn `args(com.example.domain.OrderEvent)` xét **đối tượng thực tế OrderEvent**. Cả hai có thể được kết hợp nếu mục đích là chọn method theo API và subtype theo runtime:

```text
execution(* com.example..EventService.handle(com.example.domain.Event))
&& args(com.example.domain.OrderEvent)
```

Kết hợp này thường dễ diễn giải hơn một pointcut chỉ dựa vào tên method hoặc đối số runtime.

### 7.1. Overload vẫn được chọn trước khi Spring AOP xét `args`

Nếu class có:

```java
void process(Object value)
void process(String value)
```

Java compiler sẽ quyết định overload theo **kiểu compile-time của biểu thức tại call site** (cùng các quy tắc overload resolution); Spring AOP `args` không quyết định method overload nào được gọi. Sau khi method đã được chọn và invocation đi qua proxy, pointcut mới có thể xem runtime arguments.

Ví dụ `Object x = "abc"; service.process(x);` chọn overload `process(Object)` tại compile time, mặc dù giá trị runtime là `String`. `args(String)` vẫn có thể khớp giá trị runtime, nhưng `execution(* *.process(String))` không đổi chữ ký method đã được gọi.

Điều này đặc biệt quan trọng khi debug Spring aspects trên overloaded service APIs.

## 8. Những trường hợp biên cần kiểm thử

### 8.1. Đối số `null`

`null` không có một concrete runtime class để gọi `getClass()`, nhưng các cơ chế matching/binding của AspectJ và Spring còn có thể xem xét chữ ký khai báo và quy tắc tương thích. Vì vậy, **không nên suy luận một cách tuyệt đối** rằng `args(SomeType)` lúc nào cũng match hoặc lúc nào cũng không match khi đối số là null.

Nếu method cho phép `null`, cần:

1. Viết integration test trên **Spring version và pointcut thực tế**.
2. Xác nhận lời advice có chạy hay không với các signatures khác nhau.
3. Nếu advice nhận được `null`, không gọi `payload.getClass()` khi chưa kiểm tra.
4. Nếu logic cần phân biệt null/non-null, cân nhắc dùng advice với `JoinPoint.getArgs()` hoặc kiểm tra explicit trong business validation, thay vì giả định một điều kiện `args(Type)` tương đương `value != null`.

Ví dụ bảo vệ:

```java
String typeName = (payload == null)
        ? "<null>"
        : payload.getClass().getSimpleName();
```

Đây là fragment Java, không có hệ quả Spring AOP riêng nếu không đặt trong advice/bean đúng cách.

### 8.2. Primitive và boxing

Method khai báo `void count(int n)` sử dụng primitive ở signature, nhưng Spring advice binding nhận values qua hệ thống object arguments và có liên quan đến boxing/unboxing. Một ví dụ `args(Integer)` trên primitive method có thể cần kiểm tra chi tiết matching theo Spring/AspectJ version, thay vì suy giản rằng runtime luôn có cùng kiểu `Integer` như đối tượng do caller tạo.

**Khuyến nghị:** khi business API dựa trên primitive signature, hãy dùng `execution(...int)` để định danh signature nếu đó mới là thứ cần chọn; chỉ đưa `args` vào khi bạn thực sự cần điều kiện runtime và có integration tests.

### 8.3. Varargs

Method `void send(String... messages)` được biên dịch nhận **một mảng String[]** ở vị trí varargs; lời gọi có thể viết `send("a","b")` nhưng signature JVM là một array parameter. Không nên tự mặc định `args(String, String)` sẽ match như một method khai báo hai tham số riêng. Kiểm tra quy tắc matching varargs/array trên Spring version sử dụng; nhiều trường hợp cần biểu thức phù hợp với **array argument** hơn là số phần tử varargs.

### 8.4. Generic type erasure

Spring docs nêu hạn chế khi dùng `args` để ràng buộc kiểu generic của collection như `Collection<MyType>`: runtime không chứa thông tin generic đầy đủ để Spring/AspectJ tự kiểm tra mọi phần tử trong collection.

Ví dụ mong muốn không nên viết:

```java
@Before(
    "execution(* com.example..Repository.*(..)) && args(list)"
)
public void before(java.util.Collection<MyType> list) {
    // Không thể yêu cầu Spring AOP xác nhận generic element type bằng args.
}
```

Đây là **ví dụ không phù hợp**, không phải code được khuyến nghị để chạy. Nếu cần nhận collection, sử dụng `Collection<?>` rồi **kiểm tra phần tử thực tế** theo nhu cầu nghiệp vụ, hoặc thiết kế API với một concrete request type chứa contract rõ ràng.

### 8.5. Runtime proxies, JDK/CGLIB và Spring bean boundary

`args` chỉ được đánh giá khi lời gọi **đã vào một Spring AOP proxy phù hợp**:

- Caller dùng `new MessageService().send("x")`: Spring AOP không chặn vì object không được quản lý qua proxy.
- Bean tự gọi `this.send("x")`: self-invocation thường bypass Spring AOP proxy, nên `args` không có dịp được kiểm tra.
- Cùng method được gọi qua JDK proxy: method phải nằm trong proxied interface và advice/pointcut phải khớp.
- CGLIB class proxy: chịu giới hạn như class/method `final`, `private`, những method không thể override.
- `@PostConstruct` gọi method trên raw target lúc khởi tạo: không tự tạo một Spring AOP interception cho lời gọi nội bộ.

**Đừng chẩn đoán vấn đề đường gọi bằng cách đổi `args` sang `execution`.** Nếu caller không đi qua proxy, cả hai đều không biến lời gọi raw target thành một join point mà Spring AOP có thể advice.

## 9. Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách sửa/kiểm tra |
| --- | --- | --- |
| `args(Serializable)` chạy với `String` dù method nhận `Object` | Đây là runtime type matching, đúng thiết kế. | So sánh với `execution(* *.method(Serializable))` để thấy chữ ký vẫn Object. |
| Advice chạy với lần gọi này nhưng không với lần gọi sau trên cùng method | Runtime argument types khác nhau. | Log an toàn tên kiểu, kiểm tra arguments và pointcut trong integration test. |
| `args(payload)` báo không bind được tham số | Advice thiếu parameter có tên/kiểu phù hợp hoặc metadata tên không được xác định. | Dùng `argNames`, khai báo parameter đúng kiểu và thứ tự, kiểm tra Spring Aspect binding. |
| `args(String,..)` không khớp như dự kiến | Đối số String không ở vị trí đầu, hoặc signature không tương ứng. | Kiểm tra vị trí, dấu `..` và argument count. |
| Pointcut muốn lọc `String` nhưng lại dùng `execution(...String)` | `execution` lọc kiểu tham số khai báo. | Dùng `args(String)` nếu cần lọc giá trị runtime và giới hạn với `execution` method. |
| Khai báo `@args(Serializable)` thay `args(Serializable)` | `@args` xét annotation trên class runtime, không phải interface/type `Serializable`. | Phân biệt ký hiệu có `@` và yêu cầu bài toán. |
| `args(Collection<Payment>)` không lọc theo phần tử | Java type erasure và giới hạn matching generics. | Bind `Collection<?>`, kiểm tra elements bằng code nếu thật sự cần. |
| Pointcut chọn cả nhiều service không mong đợi | `args(...)` không giới hạn bean/class/method nếu đứng riêng. | Kết hợp `execution`/`within` hẹp theo package/service. |
| Có `@Aspect` nhưng không chạy với bất kỳ argument nào | Aspect chưa là Spring bean, auto-proxy chưa bật, hoặc caller bypass proxy. | Kiểm tra bean registration, `@EnableAspectJAutoProxy`, `AopUtils` và đường gọi. |
| Advice gây `NullPointerException` ở `getClass()` | Chưa bảo vệ dữ liệu null khi advice được gọi. | Kiểm tra null và test riêng hành vi của pointcut/binding. |
| Advice kỳ vọng lọc `amount > 1000` chỉ bằng `args(Number)` | `args` là điều kiện kiểu, không phải điều kiện giá trị. | Kiểm tra `number.doubleValue()` hoặc logic nghiệp vụ rõ ràng bên trong advice. |

## 10. Cách chọn giữa `args`, `execution`, `@args` và việc đọc `JoinPoint`

| Yêu cầu thực tế trong Spring | Cơ chế nên cân nhắc |
| --- | --- |
| Chọn method `send` có chữ ký `send(Object)` | `execution(* ..MessageGateway.send(java.lang.Object))`. |
| Chỉ chạy advice khi runtime argument implements `Serializable` | `execution(* ..MessageGateway.send(..)) && args(java.io.Serializable)`. |
| Lấy đối số thực tế vào advice theo kiểu cụ thể | `args(payload)` và khai báo advice parameter `Serializable payload`, kèm `argNames` khi cần. |
| Chỉ chọn argument có class runtime mang một annotation | `@args(com.example.MyMarker)`, cần cấu hình annotation runtime phù hợp. |
| Chọn method có annotation `@Audit` | `@annotation(com.example.Audit)`, không phải `@args`. |
| Chọn method của service package trước khi lọc argument runtime | Dùng `execution` hoặc `within` như scope + `args`. |
| Cần so sánh giá trị/khoảng tiền/id | Advice dùng `JoinPoint.getArgs()` hoặc binding rồi kiểm tra giá trị, không chỉ `args(Type)`. |

Ví dụ cách khai báo pointcut có tên để tái sử dụng:

```java
@Pointcut(
    value = "execution(public * com.example..MessageGateway.send(..))"
          + " && args(payload)",
    argNames = "payload"
)
public void serializableMessages(Serializable payload) {}

@Before(value = "serializableMessages(payload)", argNames = "payload")
public void audit(Serializable payload) {
    // ...
}
```

Đây là **fragment trong một class `@Aspect`**, cần imports `@Pointcut`, `@Before` và `Serializable`. Nhiều advices có thể tham chiếu named pointcut để dùng chung logic, nhưng vẫn cần đặt tên binding nhất quán ở từng advice.

## 11. Kiểm thử cho `args` trong một ứng dụng Spring

Một integration test tốt nên dùng **Spring context thật** và một bean được trả về dưới dạng proxy:

1. Xác minh aspect bean và target bean được đăng ký đúng context.
2. Xác minh `AopUtils.isAopProxy(bean)`; nếu dùng JDK proxy, có thể kiểm tra `isJdkDynamicProxy(bean)`.
3. Chạy method một lần với argument **đúng kiểu runtime**; kỳ vọng counter advice tăng.
4. Chạy lại **cùng method/cùng proxy** với argument khác kiểu; kỳ vọng counter không tăng.
5. So với pointcut `execution` lọc chữ ký để chắc chắn không nhầm signature/runtime types.
6. Test polymorphism: interface/supertype và subtype runtime.
7. Test method overloads/varargs, primitive, null và generic collection nếu API hỗ trợ.
8. Kiểm tra values/exception của target không bị thay đổi vô tình khi thêm `@Before`/`@Around`.
9. Kiểm tra mỗi advice chạy **đúng số lần** nếu nhiều `@Aspect` cùng khớp method.
10. Giữ pointcut đủ hẹp để không áp dụng nhầm trên beans khác.

Ví dụ assertion khái quát cho ba lời gọi trong bài:

```text
send("hello")             -> runtime Serializable -> advice +1
send(new PlainPayload())  -> runtime không Serializable -> advice +0
send(Integer.valueOf(7)) -> runtime Serializable -> advice +1

Tổng: target chạy 3 lần; args advice chạy 2 lần.
```

Đây là một kết quả cho **cấu hình demo đã nêu**, không phải khẳng định rằng mọi pointcut `args` trong mọi Spring application đều có số lần advice tương tự.

### Tài liệu chính thức

- Spring Framework — Declaring a Pointcut / Supported Pointcut Designators: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework — Declaring Advice / Passing Parameters to Advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — Pointcut API / Static and Dynamic MethodMatcher: https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Kết luận:** Trong Spring Aspect, `args` lọc lời gọi theo **kiểu đối số được truyền thực tế** và có thể bind đối số đó vào method advice; `execution` chọn phương thức theo **chữ ký khai báo**. Kết hợp cả hai trên **Spring bean được gọi qua proxy** giúp định nghĩa pointcut vừa đúng ý nghiệp vụ, vừa tránh áp dụng advice quá rộng.
