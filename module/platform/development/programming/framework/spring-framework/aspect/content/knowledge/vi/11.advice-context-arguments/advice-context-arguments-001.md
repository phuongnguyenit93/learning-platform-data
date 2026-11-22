# Spring AOP: sử dụng `JoinPoint` để đọc đối số, chữ ký và ngữ cảnh lời gọi

## 1. `JoinPoint` giải quyết vấn đề gì trong Spring Aspect?

Khi viết advice trong Spring AOP, đôi khi chỉ biết một lời gọi khớp pointcut là chưa đủ: bạn còn muốn biết **đang thực thi method nào**, **những đối số nào đã được truyền**, **Spring proxy nào nhận lời gọi** và **target bean nào thực hiện nghiệp vụ**.

Spring cung cấp đối tượng `org.aspectj.lang.JoinPoint` cho advice đang được gọi. Đây là **ảnh chụp ngữ cảnh của method execution hiện tại** do Spring AOP proxy quan sát, không phải đối tượng đại diện cho toàn bộ stack trace hoặc mọi thao tác Java trong JVM.

Ví dụ ngắn:

```java
@Aspect
@Component
public class OrderAuditAspect {
    @Before("execution(* demo.joinpoint.OrderService.place(..))")
    public void beforePlace(JoinPoint joinPoint) {
        System.out.println("method=" + joinPoint.getSignature().getName());
        System.out.println("args=" + Arrays.toString(joinPoint.getArgs()));
    }
}
```

Đây là **fragment** để hiểu API: nó cần imports, một target Spring bean, hạ tầng Spring AOP và một consumer gọi target qua proxy. Với lời gọi `place("ORD-7", 2)`, `getSignature().getName()` cho `"place"`, còn `getArgs()` mô tả các đối số `["ORD-7", 2]` theo thứ tự tham số.

**Trọng tâm:** đây là cách dùng `JoinPoint` trong **Spring Aspect**, không phải giải thích AOP nói chung hoặc full AspectJ bytecode weaving. `JoinPoint` của Spring AOP chỉ xuất hiện trong advice khi một **method execution của Spring-managed bean** đã được proxy chặn và pointcut khớp.

## 2. Sơ đồ: ngữ cảnh được tạo ở đâu?

```text
Một consumer
      |
      | orderOperations.place("ORD-7", 2)
      v
Spring AOP proxy
      |
      | kiểm tra advisor / pointcut
      v
@Before advice nhận JoinPoint
      |
      +-- getArgs()       -> ["ORD-7", 2]
      +-- getSignature()  -> thông tin method place(...)
      +-- getThis()       -> đối tượng Spring AOP proxy
      +-- getTarget()     -> đối tượng OrderService target
      |
      v
Target OrderService.place("ORD-7", 2)
      |
      v
Caller nhận kết quả
```

Các mốc cần phân biệt:

- Đối số của biểu thức gọi method đã được Java **đánh giá trước** khi lời gọi chạm proxy. `getArgs()` không cho biết đối số được tạo bằng expression nào trong source code.
- Spring AOP tạo ngữ cảnh advice trong luồng **method execution đã được intercept**. Nó không tạo một `JoinPoint` mới cho những lời gọi nội bộ `this.someMethod()` bỏ qua proxy.
- `JoinPoint` cung cấp **thông tin invocation ở ranh giới proxy**. Nó không cung cấp sẵn tên controller, file nguồn hoặc dòng mã Java ở nơi caller gõ lệnh gọi.
- Nếu không có aspect/advice áp dụng, target vẫn có thể thực thi nhưng không có advice để nhận `JoinPoint`.

Ví dụ kiểu lời gọi `new OrderService().place(...)` tạo object Java ngoài Spring container; nó không có Spring AOP proxy tự động, nên advice trên không chạy.

## 3. Bốn API cốt lõi

| API `JoinPoint` | Thông tin nhận được | Lưu ý trong Spring |
| --- | --- | --- |
| `getArgs()` | Mảng đối số của invocation theo vị trí | Có thể chứa `null`, wrapper của primitive, DTO hoặc đối tượng nhạy cảm; không phải tên biến nguồn |
| `getSignature()` | Mô tả method đang được advice | Dùng `MethodSignature` khi cần return type, parameter types, `Method` |
| `getThis()` | **Spring AOP proxy** đại diện cho lời gọi | Với JDK proxy, thường implement interface nhưng không phải instance của target concrete class |
| `getTarget()` | **Target object** nằm sau proxy | Là đối tượng nghiệp vụ, có thể `null` với một số trường hợp target source đặc biệt; không tự gọi target nếu muốn advice |
| `getKind()` | Loại join point, thường `method-execution` trong Spring AOP | Không phải tên operation hay tên caller |
| `toShortString()`, `toLongString()` | Mô tả chữ của join point | Phù hợp debug, không coi output là schema log ổn định |
| `getStaticPart()` | Phần thông tin tĩnh của join point | Ít cần trong business advice; không phải Java stack frame của caller |
| `getSourceLocation()` | Giao diện source location của AspectJ JoinPoint | **Không dùng như định danh tin cậy của caller**; Spring proxy không cung cấp call-site source tracking tương đương weaving |

**Đặc biệt:** phương thức `JoinPoint.getTarget()` không có nghĩa trả lại một “cổng vào advice”. Nếu dùng `joinPoint.getTarget()` để gọi method khác trên target, bạn có thể chủ động **bypass Spring AOP proxy**. Nếu cần một bean collaboration đi qua Spring AOP, hãy inject Spring bean phù hợp.

## 4. Đọc đối số với `getArgs()`

### 4.1. Vị trí trong mảng tương ứng tham số method

Xét một method nghiệp vụ:

```java
public String place(String orderId, int quantity) {
    return "RCPT-" + orderId + "-" + quantity;
}
```

Trong advice:

```java
Object[] args = joinPoint.getArgs();
String orderId = (String) args[0];
int quantity = (Integer) args[1];
```

Đây là fragment chỉ đúng nếu pointcut đã giới hạn đến method có đúng các tham số `(String, int)`. Với primitive `int`, phần tử tương ứng trong `Object[]` được biểu diễn bằng wrapper `Integer`. Không được suy đoán mảng luôn đủ phần tử: method không tham số trả mảng rỗng, và pointcut rộng có thể bắt method có signature khác.

Một cách chỉ dùng để debug:

```java
System.out.println(Arrays.toString(joinPoint.getArgs()));
```

Lệnh cần import `java.util.Arrays`; kết quả phụ thuộc `toString()` của object. Nó có thể vô tình in secrets hoặc kích hoạt logic tốn kém trong `toString()`. Ví dụ chạy ở mục 8 dùng các giá trị thử nghiệm không nhạy cảm.

### 4.2. `getArgs()` không cho biết **tên tham số ở source**

Từ `getArgs()` bạn biết có giá trị `"ORD-7"` và `2`, nhưng **không biết** caller đã viết `place(orderId, quantity)` hay `place("ORD-" + i, 1 + 1)`. Tên parameter `orderId`, `quantity` là metadata của method definition; nó không nằm trong array đối số.

Để xem parameter types và metadata reflection, dùng `MethodSignature`. Để thấy **tên parameter** qua reflection một cách đáng tin, cần compiler flags/metadata phù hợp (ví dụ `-parameters`); nếu thiếu, có thể chỉ nhận tên tổng quát hoặc metadata không có.

### 4.3. Với pointcut rộng phải tránh ép kiểu mù quáng

```java
@Before("execution(* demo.joinpoint..*Service.*(..))")
public void unsafe(JoinPoint jp) {
    String orderId = (String) jp.getArgs()[0]; // Có thể lỗi.
}
```

Trong code trên, method no-arg gây `ArrayIndexOutOfBoundsException`; method có tham số đầu tiên là `Long` có thể gây `ClassCastException`. Chỉ ép kiểu sau khi expression hoặc runtime checks thực sự xác nhận signature.

Ví dụ quan sát an toàn hơn:

```java
Object[] args = jp.getArgs();
System.out.println("argument count=" + args.length);
if (args.length > 0 && args[0] instanceof String first) {
    System.out.println("first argument length=" + first.length());
}
```

Đoạn này giả định method `jp` là một `JoinPoint` argument của advice. Ngay cả khi kiểu hợp lệ, trước khi ghi log hãy xem dữ liệu có phải token, password, email, số tài khoản, địa chỉ hoặc thông tin nhạy cảm không.

### 4.4. Có nên gán lại phần tử `getArgs()`?

Không sử dụng thao tác:

```java
jp.getArgs()[0] = "FORCED"; // Không phải hợp đồng để thay argument của target.
```

để kỳ vọng target tự nhận argument mới. Trong Spring AOP, `getArgs()` phục vụ **quan sát**; implementation có thể trả một bản sao/snapshot. Khi thật sự cần điều chỉnh arguments trước khi tiếp tục invocation, dùng `@Around` với `ProceedingJoinPoint.proceed(Object[] args)` và tuân thủ đúng số lượng/kiểu tham số.

Tránh thay trực tiếp các DTO mutable chỉ để logging; ngay cả khi mảng riêng, đối tượng được tham chiếu bên trong có thể là instance mutable của nghiệp vụ.

## 5. Đọc chữ ký bằng `getSignature()`

`joinPoint.getSignature()` có kiểu chung `org.aspectj.lang.Signature`. Với method-execution join point trong Spring AOP, có thể chuyển sang `org.aspectj.lang.reflect.MethodSignature` để lấy API dành riêng cho method.

```java
MethodSignature signature = (MethodSignature) jp.getSignature();

String name = signature.getName();
Class<?> returnType = signature.getReturnType();
Class<?>[] parameterTypes = signature.getParameterTypes();
Method method = signature.getMethod();
```

Đoạn trên là fragment bên trong advice, cần imports:

```java
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.reflect.MethodSignature;
import java.lang.reflect.Method;
```

Các trường:

- `getName()`: tên method, ví dụ `place`.
- `getReturnType()`: kiểu trả về **khai báo**, ví dụ `String.class` hoặc `int.class`, không phải return value thực tế.
- `getParameterTypes()`: những kiểu tham số khai báo theo thứ tự; khác với runtime types trong `getArgs()`.
- `getMethod()`: reflective method của invocation được Spring AOP biết đến. **Không luôn đồng nghĩa với method declaration trực tiếp trên implementation class** nếu đang dùng JDK interface proxy.
- `getDeclaringTypeName()`: thông tin declaring type của signature, nhưng có thể là interface type trong trường hợp JDK proxy; không dùng nó để đoán caller class.

### 5.1. Interface method và implementation method có thể khác nhau

```java
public interface OrderOperations {
    String place(String orderId, int quantity);
}

@Service
public class OrderService implements OrderOperations {
    @Override
    public String place(String orderId, int quantity) {
        return "RCPT-" + orderId + "-" + quantity;
    }
}
```

Khi caller giữ **JDK dynamic proxy** dưới kiểu `OrderOperations`, signature của invocation có thể liên quan method khai báo trên interface, dù logic thực thi nằm tại `OrderService.place(...)`.

Nếu mục đích là tìm annotation hoặc method implement cụ thể, Spring có helper:

```java
MethodSignature sig = (MethodSignature) jp.getSignature();
Method invoked = sig.getMethod();

Object target = jp.getTarget();
if (target != null) {
    Method specific = AopUtils.getMostSpecificMethod(
            invoked, target.getClass());
    System.out.println(specific.getDeclaringClass().getSimpleName());
}
```

Đây là fragment minh họa, cần import `org.springframework.aop.support.AopUtils`. Với các kiểu bridge/generic method và annotation mapping phức tạp, còn phải xét quy tắc lookup của framework liên quan thay vì chỉ đọc một annotation từ `sig.getMethod()`.

### 5.2. Chữ ký **không** phải địa chỉ source của caller

Method signature cho biết invocation **đang thực thi method nào**. Nó **không** nói:

- Java class nào gọi method đó trước khi vào proxy;
- source file và dòng call site ở controller/service khác;
- HTTP endpoint, user identity, request ID hoặc transaction ID;
- nơi object argument được tạo ra.

Những giá trị này nếu cần phải đi qua các cơ chế riêng: explicit request context, correlation ID, tracing/observation infrastructure, hoặc business parameters. Không ép `getSignature().getDeclaringTypeName()` thành “caller class”.

## 6. `getThis()` và `getTarget()`: phân biệt Spring proxy với bean đích

Trong Spring AOP, hai phương thức này **khác nhau về ngữ nghĩa**:

```java
Object proxy = jp.getThis();
Object target = jp.getTarget();
```

- `proxy` là **Spring AOP proxy** mà lời gọi hiện tại đi qua.
- `target` là **Spring AOP target** đang được advice; trong các trường hợp thông thường là instance service thật.
- `proxy == target` **không phải điều phải luôn đúng**. Với một AOP proxy thực, chúng thường là hai Java object khác nhau.
- `getTarget()` có thể `null` với trường hợp đặc biệt không có target object; code hạ tầng/generic aspect phải chịu được khả năng đó.
- JDK proxy thực hiện interface, không phải subclass của concrete class. Ví dụ `proxy instanceof OrderOperations` true nhưng `proxy instanceof OrderService` false.
- CGLIB proxy thường là subclass có thể assign sang concrete class nếu target class không bị final; vẫn là **proxy** với interceptor chain.

**Không gọi thẳng business method trên `getTarget()` để cố kích hoạt advice.** Target invocation không qua proxy sẽ không tạo một interception mới. Nếu thật sự phải gọi operation được advice, thiết kế consumer nhận bean khác qua constructor injection là cách ưu tiên; không lạm dụng tự gọi proxy từ aspect.

### 6.1. `getThis()` cũng không phải caller object

Tên `getThis()` dễ khiến bạn tưởng nó trả Java `this` của class gọi service. Trong Spring AOP, nó trả **proxy object của chính bean đang được intercept**, không phải controller, workflow hoặc REST endpoint gọi bean này.

Ví dụ:

```text
CheckoutController -> OrderOperations proxy -> OrderService target
                           |                      |
                   jp.getThis()             jp.getTarget()
```

Không có API `JoinPoint.getCaller()` phổ quát trong Spring AOP.

### 6.2. Cần source/caller provenance thì làm gì?

“**Nguồn lời gọi được hỗ trợ**” trong Spring proxy có nghĩa thực tế bạn có thể xác định method, đối số, proxy và target liên quan. Nó không có nghĩa Spring JoinPoint tự thu thập call-site location.

Nếu muốn biết luồng request nào dẫn tới service, nên:

- Đặt **trace/span/correlation ID** ở ranh giới request và truyền qua hạ tầng quan sát phù hợp.
- Nếu cần danh tính nghiệp vụ caller, truyền một thông tin caller rõ ràng trong domain API hoặc context được bảo đảm.
- Với Spring MVC, có thể lấy metadata tuyến request trong interceptor/filter/web layer phù hợp, thay vì đoán từ method signature của service.
- Với thread hops/async, phải tính đến việc context propagation cần cấu hình thích hợp.
- Nếu chỉ đang debug, stack trace có thể cho manh mối, nhưng không phải API bền vững: proxy, inlining, threads, async hoặc refactoring khiến call stack thay đổi.

Một `SourceLocation` trong AspectJ API **không nên được coi là vị trí mà consumer đã gọi service** trong Spring AOP. Nên hiểu Spring AOP chủ yếu quan sát **execution join point**, không phải join point kiểu source `call(...)` được weaving tại call site.

## 7. Quy tắc khai báo tham số advice

### 7.1. `JoinPoint` đứng đầu trong advice thường

Các loại advice như `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing` có thể nhận `org.aspectj.lang.JoinPoint` là **tham số đầu tiên**:

```java
@Before("execution(* demo.joinpoint.OrderService.place(..))")
public void audit(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
```

Không cần khai báo `JoinPoint` trên business method; Spring tự cung cấp nó cho advice khi execution match pointcut. Không thể inject `JoinPoint` như một singleton bean rồi dùng để suy ra mọi lời gọi đang diễn ra; nó là ngữ cảnh của invocation trong advice.

### 7.2. `@Around` phải dùng `ProceedingJoinPoint`

Với `@Around`, tham số đầu tiên phải là `ProceedingJoinPoint`, subtype của `JoinPoint` có `proceed()`:

```java
@Around("execution(* demo.joinpoint.OrderService.place(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("calling " + pjp.getSignature().getName());
    return pjp.proceed();
}
```

Điều kiện để target thật chạy là advice thực hiện `proceed()`. Nếu quên `return pjp.proceed()`, return value hoặc control flow tới caller có thể sai. Trong khi đó, `JoinPoint` thông thường không có `proceed()`; `@Before` không thể chủ động bỏ qua invocation rồi return một kết quả thay thế như `@Around`.

### 7.3. Khi nào nên bind parameter trực tiếp thay vì dùng `Object[]`?

Nếu pointcut chỉ chọn method có một argument `String`:

```java
@Before(
    value = "execution(* demo.joinpoint.OrderService.cancel(..))"
          + " && args(orderId)",
    argNames = "orderId"
)
public void beforeCancel(JoinPoint jp, String orderId) {
    System.out.println("cancel length=" + orderId.length());
}
```

Đây là fragment minh họa cần method `OrderService.cancel(String)` tồn tại và đúng một đối số. `args(orderId)` vừa kiểm tra/bind argument theo quy tắc pointcut, còn `argNames="orderId"` mô tả tên binding khi compiler không lưu metadata tham số phù hợp. Spring không đòi tự cast `jp.getArgs()[0]` trong trường hợp này.

**Không gộp snippet này vào dự án ở mục 8** vì dự án đó không định nghĩa `cancel(..)`; đây là hướng mở rộng API riêng.

Với nhiều tham số, khai báo tên và thứ tự đúng với expression, ví dụ `args(orderId, quantity)`; không suy đoán `argNames` hay Java parameter names là luôn có trong bytecode.

### 7.4. Return value và thrown exception là ngữ cảnh khác

`JoinPoint.getArgs()` trả input arguments. Nó **không** trả kết quả của target hay exception chưa ném. Spring hỗ trợ:

- `@AfterReturning(pointcut=..., returning="result")` để bind giá trị return khi method kết thúc bình thường;
- `@AfterThrowing(pointcut=..., throwing="ex")` để bind exception phù hợp;
- `@Around` để truy cập outcome của `proceed()` trong try/catch/finally.

`getSignature()` cho biết **declared return type**; nó không tương đương với **actual returned value**.

## 8. Ví dụ độc lập chạy được: đọc signature, args, proxy và target

Ví dụ dùng **Java 17 + Maven + Spring Framework 6.2.x**, không cần Spring Boot. Target có interface nên với `@EnableAspectJAutoProxy(proxyTargetClass=false)` Spring ưu tiên **JDK dynamic proxy**. Aspect chỉ advice `place(String,int)`; một method khác không match, lời gọi `this.place()` bypass, và object tạo bằng `new` không qua Spring proxy.

### 8.1. Cấu trúc thư mục

```text
spring-joinpoint-context/
├── pom.xml
└── src/main/java/demo/joinpoint/
    ├── AppConfig.java
    ├── OrderOperations.java
    ├── OrderService.java
    ├── ContextAspect.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-joinpoint-context</artifactId>
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

### 8.3. `AppConfig.java`

```java
package demo.joinpoint;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` phát hiện Spring service và aspect. `@EnableAspectJAutoProxy` bật auto-proxy creator. Với interface `OrderOperations` và cấu hình này trong Spring Framework thuần, proxy của bean service là JDK dynamic proxy.

### 8.4. `OrderOperations.java`

```java
package demo.joinpoint;

public interface OrderOperations {
    String place(String orderId, int quantity);
    String health();
    void batch();
}
```

Hợp đồng consumer chỉ gồm public interface methods, tương thích JDK dynamic proxy.

### 8.5. `OrderService.java`

```java
package demo.joinpoint;

import org.springframework.stereotype.Service;

@Service
public class OrderService implements OrderOperations {
    @Override
    public String place(String orderId, int quantity) {
        System.out.println("[target] place " + orderId + " qty=" + quantity);
        return "RCPT-" + orderId + "-" + quantity;
    }

    @Override
    public String health() {
        System.out.println("[target] health");
        return "UP";
    }

    @Override
    public void batch() {
        System.out.println("[target] batch");
        this.place("INNER", 1); // Target tự gọi: bypass AOP proxy.
    }
}
```

Pointcut bên dưới chỉ áp dụng cho `place(..)` khi lời gọi **đi qua proxy**. Method `health()` và `batch()` không thuộc pointcut. `this.place("INNER", 1)` vẫn chạy Java method bình thường nhưng không có before advice riêng.

### 8.6. `ContextAspect.java`

```java
package demo.joinpoint;

import java.util.Arrays;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ContextAspect {
    @Before("execution(* demo.joinpoint.OrderService.place(..))")
    public void observe(JoinPoint jp) {
        MethodSignature signature = (MethodSignature) jp.getSignature();

        System.out.println("[advice] method=" + signature.getName());
        System.out.println("[advice] args=" + Arrays.toString(jp.getArgs()));
        System.out.println("[advice] returnType="
                + signature.getReturnType().getSimpleName());

        System.out.println("[advice] proxyImplementsPort="
                + (jp.getThis() instanceof OrderOperations));

        Object target = jp.getTarget();
        System.out.println("[advice] targetClass="
                + (target == null ? "<none>"
                                  : target.getClass().getSimpleName()));
    }
}
```

Quan sát cụ thể:

- `getSignature()` mô tả method `place`; ép sang `MethodSignature` để đọc declared return type.
- `getArgs()` chứa hai giá trị theo thứ tự, số `2` được boxing trong array.
- `getThis() instanceof OrderOperations` true với JDK proxy thực hiện interface.
- `getTarget()` là instance `OrderService` nên `targetClass=OrderService`.
- Aspect chỉ quan sát, không mutate args hoặc gọi lại method target/proxy.

### 8.7. `Main.java`

```java
package demo.joinpoint;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderOperations orders = context.getBean(OrderOperations.class);

            System.out.println("[main] jdkProxy="
                    + AopUtils.isJdkDynamicProxy(orders));

            System.out.println("[caller] receipt="
                    + orders.place("ORD-7", 2));

            System.out.println("[caller] health="
                    + orders.health());

            orders.batch();

            OrderOperations unmanaged = new OrderService();
            System.out.println("[caller] rawReceipt="
                    + unmanaged.place("RAW", 1));
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.joinpoint.Main
```

**Kết quả stdout của các lệnh `System.out` trong ví dụ** (bỏ qua log Maven/Spring nếu phát thêm):

```text
[main] jdkProxy=true
[advice] method=place
[advice] args=[ORD-7, 2]
[advice] returnType=String
[advice] proxyImplementsPort=true
[advice] targetClass=OrderService
[target] place ORD-7 qty=2
[caller] receipt=RCPT-ORD-7-2
[target] health
[caller] health=UP
[target] batch
[target] place INNER qty=1
[target] place RAW qty=1
[caller] rawReceipt=RCPT-RAW-1
```

### 8.8. Phân tích thứ tự log

1. `getBean(OrderOperations.class)` nhận Spring AOP bean reference, dùng JDK proxy nên dòng đầu là `jdkProxy=true`.
2. `orders.place("ORD-7",2)` vào proxy, pointcut match; Spring tạo `JoinPoint` cho advice. Advice in metadata **trước** target.
3. `getArgs()` trả mảng gồm `String "ORD-7"` và `Integer 2`; `Arrays.toString(...)` hiển thị `[ORD-7, 2]`.
4. `MethodSignature.getReturnType()` trả `String.class`; phương thức đích sau đó trả `"RCPT-ORD-7-2"` tới caller.
5. `orders.health()` không khớp pointcut và chỉ in dòng target.
6. `orders.batch()` không khớp pointcut. Bên trong target, `this.place("INNER",1)` bỏ qua Spring proxy; **không có** dòng advice cho INNER.
7. `new OrderService().place("RAW",1)` gọi object ngoài container; có dòng target nhưng không có advice. Caller vẫn nhận return value của Java method.

Ví dụ dùng **một before advice duy nhất**, vì vậy không cần suy đoán thứ tự giữa nhiều advisors. Không dùng `getSourceLocation()` để cố in “caller file” vì Spring proxy không bảo đảm cung cấp metadata call-site đáng tin.

## 9. Khi muốn nguồn lời gọi: phân biệt bốn loại “nguồn”

Từ “nguồn” có thể chỉ nhiều thứ rất khác nhau:

| Loại thông tin | Spring `JoinPoint` đáp ứng ra sao? | Phương án thích hợp |
| --- | --- | --- |
| Method **đang được advice** | Có: `getSignature()`, `MethodSignature` | Dùng method name, return/param types; bổ sung target type nếu cần |
| Đối tượng **proxy tiếp nhận invocation** | Có: `getThis()` | Phân biệt JDK/CGLIB, không coi đó là caller object |
| Đối tượng **thực thi target** | Có: `getTarget()` | Có thể dùng target class cho metadata, không gọi trực tiếp nếu cần advice |
| **Java caller object**, file/dòng nơi gọi method | Không có API chuẩn đáng tin của Spring JoinPoint cho call site | Tracing, context explicit, stack trace chỉ để debug |
| **HTTP/request origin** | Không nằm sẵn trong `JoinPoint` | Spring web filter/interceptor, request context/observation theo luồng |
| **User/principal** | Không thể suy ra chỉ từ signature/args | Spring Security context hoặc explicit application context phù hợp |
| **Transaction/tracing context** | Không đồng nhất với JoinPoint | Spring transaction/observability APIs theo đúng module |

Trong Spring AOP, `getThis()` biểu thị proxy **ở phía callee**, không phải object “this” ở caller. `getTarget()` biểu thị bean thực thi nghiệp vụ. Nếu một request bắt đầu từ `CheckoutController` rồi đến `OrderService.place()`, metadata tự nhiên của JoinPoint vẫn là method execution của `OrderService`, không phải tên controller.

### 9.1. Vì sao không nên lấy stack trace làm khóa nghiệp vụ?

Java stack trace cho biết những frame hiện diện tại một thời điểm, nhưng:

- Proxy layers và interceptors có thể thêm nhiều frames hạ tầng.
- Async execution, scheduling, reactive pipelines và thread pools làm caller logic không còn ở stack hiện tại.
- Refactor method, compiler optimizations, generated proxy classes có thể thay đổi frame.
- Stack capture tốn chi phí nếu thực hiện trên mọi request và có thể làm lộ chi tiết implementation.

Dùng stack trace khi cần debug lỗi, không tự gán nó thành “nguồn caller” ổn định cho audit hoặc authorization.

### 9.2. Có nên dùng `getSourceLocation()`?

`JoinPoint` theo AspectJ API có method `getSourceLocation()`. Nhưng Spring AOP **không weaving call-site bytecode**, vì vậy không có đủ thông tin để cung cấp file/dòng **nơi một consumer gọi bean** một cách tổng quát. Không dùng `getSourceLocation()` làm nguồn sự thật về controller, caller ID hay vị trí gọi.

Nếu yêu cầu nghiệp vụ thực sự cần các thông tin này, hãy thiết kế hạ tầng trace/span ID hoặc tham số context rõ ràng. Nếu muốn debug implementation method, reflection từ `MethodSignature` thường có ý nghĩa hơn dựa vào một “source location” không đúng phạm vi.

## 10. Gắn dữ liệu vào advice: typed binding và những lưu ý

### 10.1. Binding qua `args(...)` giúp type-safe hơn

Với một method:

```java
public String place(String orderId, int quantity) { /* ... */ }
```

một advice tương ứng có thể bind hai giá trị:

```java
@Before(
    value = "execution(* demo.joinpoint.OrderService.place(..))"
          + " && args(orderId, quantity)",
    argNames = "orderId,quantity"
)
public void auditArgs(JoinPoint jp, String orderId, int quantity) {
    System.out.println("orderId length=" + orderId.length());
    System.out.println("quantity=" + quantity);
}
```

Đây là một fragment **thay thế** advice `observe(...)`, không nên cùng đăng ký nếu chỉ muốn một dòng log cho mỗi invocation. Cú pháp `JoinPoint` là tham số đặc biệt đầu tiên; việc bind `orderId` và `quantity` là phần Spring @AspectJ xử lý theo expression, phù hợp Java signature.

Nếu tên trong `argNames` sai hoặc không tương ứng với variables trong pointcut/advice, context có thể lỗi lúc cấu hình. Khi pointcut có nhiều method overloads, nên kiểm tra kiểu/argument positions và test kỹ.

### 10.2. Annotation binding không tự suy ra giá trị caller

Ví dụ annotation custom `@Audited` có thể được dùng với `@annotation(...)` để chọn method. Điều đó giúp tìm method **được gắn annotation** theo quy tắc Spring pointcut, nhưng không cung cấp Java caller source. Annotation cần được giữ ở runtime, đặt nơi phù hợp và được aspect nhận diện. Khi dùng JDK proxy, method trên interface và method implementation có thể khác, nên kiểm tra cơ chế annotation lookup thực tế.

### 10.3. Không lưu `JoinPoint` trong singleton field

Aspect `@Component` thường được tạo như singleton Spring bean. Nếu đặt:

```java
private JoinPoint lastJoinPoint; // Không nên lưu invocation state lâu dài.

@Before("execution(* demo.joinpoint..*Service.*(..))")
public void before(JoinPoint jp) {
    lastJoinPoint = jp;
}
```

sẽ có nguy cơ **race condition** khi nhiều threads xử lý invocation đồng thời. `JoinPoint` và `getArgs()` liên quan một invocation, không phải state chung. Hãy dùng local variable, truyền dữ liệu tới telemetry đã được thiết kế concurrent-safe hoặc dùng context phù hợp với vòng đời một request.

## 11. Giới hạn Spring AOP ảnh hưởng trực tiếp đến thông tin JoinPoint

- Spring AOP thông thường intercept **method execution** trên Spring-managed beans, không chặn mọi method call trong JVM. `call(...)`, field access, constructor join points của full AspectJ không tự được hỗ trợ chỉ bằng Spring proxy.
- Với **JDK proxy**, chỉ những public interface methods được proxy công bố có thể bị caller gọi qua reference proxy. Public method chỉ nằm trên concrete implementation không tự xuất hiện trên JDK interface proxy.
- Với **CGLIB proxy**, method phải có thể được subclass override; private/final methods có giới hạn. Final class không được CGLIB subclass.
- **Self-invocation** như `this.place()` bypass proxy; advice không tạo `JoinPoint` riêng cho lời gọi đó.
- Một object tạo bằng `new` ngoài Spring không tự được AOP proxy; không có advice context chỉ vì class khác cùng tên là bean.
- `@Aspect` một mình chưa đăng ký aspect là Spring bean; cần `@Component` hoặc cấu hình `@Bean`, cùng AOP activation.
- `JoinPoint.getThis()`/`getTarget()` mô tả proxy/target **của invocation đang match**, không phải dependency graph hay toàn bộ Spring container.
- `@Before` thấy đối số đầu vào nhưng chưa thấy return/exception của target. Muốn outcome, cần đúng loại advice hoặc logic ở `@Around`.
- Vài tính năng AOP khác như introduction interfaces có thể làm proxy công bố interface bổ sung; không cast trực tiếp về implementation nếu đang dùng JDK proxy.
- Multiple application contexts có thể có các proxy/aspects khác nhau; kiểm tra reference thực tế từ consumer trước khi kết luận JoinPoint thuộc context nào.

## 12. Checklist xử lý sự cố

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `@Before` không nhận JoinPoint | Advice không match, aspect không đăng ký bean hoặc lời gọi bypass proxy | Xem `@Aspect @Component`, `@EnableAspectJAutoProxy`, AopUtils và call path |
| `getArgs()[0]` bị lỗi | Method không có tham số hoặc pointcut match nhiều signatures | Kiểm tra length, class và expression |
| ClassCastException khi ép arg | Runtime argument type khác giả định | Dùng `instanceof` hoặc `args(...)` binding đúng kiểu |
| `getSignature().getName()` đúng nhưng getMethod không chỉ implementation | JDK proxy biết interface method | Dùng target class + `AopUtils.getMostSpecificMethod(...)` khi cần |
| `getThis().getClass()` khác target class | Spring AOP trả proxy object | Đây là điều bình thường; dùng AopUtils để xác định loại proxy |
| `getTarget()` khác `getThis()` | Target và proxy là hai references khác nhau | Không so sánh identity để quyết định lỗi |
| Aspect in tên service, không in tên controller | Signature mô tả callee method execution | Dùng request tracing/correlation IDs, không coi JoinPoint là caller API |
| `getSourceLocation()` không cho dòng call-site | Spring AOP không weave vị trí caller | Tránh phụ thuộc; trace ở ranh giới request |
| `getArgs()` in lộ token/password | Logging không kiểm soát dữ liệu nhạy cảm | Redaction/allowlist metadata, không log toàn bộ args |
| Advice biến đổi args nhưng target nhận cũ | Gán vào array từ `getArgs()` không phải contract điều khiển invocation | `@Around` và `proceed(newArgs)` nếu thật sự cần |
| `this.method()` không có log advice | Self-invocation bypass proxy | Tách sang Spring bean khác/đổi boundary gọi |
| `new Service().method()` không có advice | Object ngoài container | Inject Spring-managed bean |
| Method được advice hai lần | Có nhiều advisors hoặc lần gọi qua proxy nhiều lần | Xem order/pointcut, tránh gắn trùng aspects |
| `JoinPoint` được lưu trong field rồi sai dữ liệu | Singleton aspect chia sẻ state giữa threads | Giữ dữ liệu invocation trong local variables |
| Thay `JoinPoint` bằng `ProceedingJoinPoint` trong `@Before` | Sai contract advice type | Chỉ dùng `ProceedingJoinPoint` làm param bắt buộc đầu cho `@Around` |

**Trình tự kiểm tra nhanh:**

1. Xác minh **target và aspect thuộc Spring context** và AOP đã bật.
2. Lấy **bean reference thực tế** từ DI/context, dùng `AopUtils.isAopProxy(...)` và kiểm tra JDK/CGLIB.
3. Xem pointcut có match **execution method** và caller có qua proxy không.
4. Dùng `getSignature()` trước để xác định method, rồi mới xử lý `getArgs()` dựa vào declared types.
5. Nếu cần implementation annotation/method, resolve method cụ thể theo target class, chú ý interface/generics.
6. Dùng `getThis()`/`getTarget()` đúng nghĩa proxy và callee target.
7. Nếu yêu cầu caller/request source, dùng tracing/context thật, không suy diễn từ signature hoặc getSourceLocation.
8. Thêm integration test chứng minh chính xác method nào được advice, dữ liệu nào được log và trường hợp nào bypass proxy.

## 13. Câu hỏi ôn tập

**1. `JoinPoint.getArgs()` chứa gì?** Mảng runtime values của invocation theo thứ tự method parameters; nó không chứa tên Java variables ở nơi gọi hoặc thông tin call-site.

**2. `getThis()` có phải caller object không?** Không. Với Spring AOP, đó là **AOP proxy** của bean đang được intercept.

**3. `getTarget()` và `getThis()` có luôn giống nhau không?** Không. Proxy và target thường là hai objects khác nhau; getTarget đôi khi có thể null trong các trường hợp target đặc biệt.

**4. Muốn biết return type `String` của method, dùng API nào?** Ép `jp.getSignature()` sang `MethodSignature` rồi dùng `getReturnType()`. Đây là kiểu khai báo, không phải actual returned value.

**5. Có thể biết Java controller gọi service ở file dòng nào bằng `getSignature()` không?** Không. Signature mô tả method execution ở phía callee; tracing hoặc context riêng mới thích hợp để suy ra nguồn request/caller.

**6. `getArgs()[0] = anotherValue` có thay argument target nhận không?** Không dựa vào contract Spring AOP. Nếu thật sự cần thay inputs, dùng around advice và `proceed(Object[])` với đúng signature.

**7. Vì sao `this.place()` không cho một JoinPoint advice riêng?** Target gọi trực tiếp method của nó, bỏ qua Spring AOP proxy; không có method interception mới.

**8. `@Around` có nhận `JoinPoint` giống `@Before` không?** Nó yêu cầu `ProceedingJoinPoint` làm tham số đầu tiên; subtype này cung cấp `proceed()`.

**9. Làm sao nhận typed argument an toàn hơn array cast?** Bind parameter bằng `args(name)` trong pointcut và parameter trong advice, kèm metadata/`argNames` phù hợp.

**10. Có nên lưu `JoinPoint` vào field của singleton aspect?** Không. Đó là state theo invocation; field chia sẻ tạo race condition, dễ lộ dữ liệu.

## Tham khảo tài liệu chính thức

- [Spring Framework 6.2 — Declaring Advice: Access to the Current JoinPoint](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Pointcuts và execution join points](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 API — MethodInvocationProceedingJoinPoint (getThis/getTarget)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/aop/aspectj/MethodInvocationProceedingJoinPoint.html)
- [Spring Framework 6.2 — @AspectJ annotation support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html)
- [Spring Framework 6.2 — Introduction to AOP proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html)
