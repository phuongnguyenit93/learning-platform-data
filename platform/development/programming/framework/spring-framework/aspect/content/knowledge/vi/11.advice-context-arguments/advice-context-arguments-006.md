# Ràng buộc kết quả `returning` và ngoại lệ `throwing` trong Spring AOP

## 1. Mục tiêu và phạm vi

Trong Spring Framework, khi khai báo advice bằng `@Aspect`, hai thuộc tính quan trọng là **`returning`** của `@AfterReturning` và **`throwing`** của `@AfterThrowing`. Chúng không chỉ cho biết Spring nên chuyển **giá trị trả về** hoặc **ngoại lệ thoát khỏi method** vào tham số Java nào, mà kiểu tham số advice còn ảnh hưởng **lời gọi nào đủ điều kiện kích hoạt advice**.

Bài học tập trung vào **Spring Aspect/Spring AOP proxy-based** và trả lời các câu hỏi:

1. Làm thế nào để truy cập giá trị trả về của một method Spring bean bằng `returning = "result"`?
2. Làm thế nào để nhận exception qua `throwing = "error"`?
3. Tại sao `String result`, `Object result`, `IllegalArgumentException error` và `Throwable error` có phạm vi áp dụng khác nhau?
4. Cách Spring xác định tên tham số advice, khi nào dùng `argNames` hoặc `javac -parameters`?
5. Khi nào advice không chạy: method `void`, kiểu không phù hợp, exception bị bắt trong target, invocation qua `this`, object ngoài Spring?
6. Làm sao viết code có thể chạy bằng Maven/Java 17+, dự đoán stdout và kiểm thử cả trường hợp match lẫn không match?

Đây **không phải** bài lý thuyết Aspect tổng quát. Nội dung hướng vào điều kiện thực tế để **Spring tạo advisor, chọn method và truyền thông tin ngữ cảnh vào Spring-managed `@Aspect` bean**.

## 2. Hai kiểu binding cơ bản

### 2.1. `returning`: kết quả từ method kết thúc bình thường

Ví dụ:

~~~java
@Aspect
public class ResultAspect {

    @AfterReturning(
        pointcut = "execution(* example.PaymentService.find(..))",
        returning = "result",
        argNames = "result"
    )
    public void afterFind(String result) {
        System.out.println("payment result: " + result);
    }
}
~~~

Đây là **snippet**, giả định có `example.PaymentService.find(..)`, aspect được đăng ký thành Spring bean và Spring AOP đã bật.

- `pointcut` chọn **method execution** phù hợp.
- `returning = "result"` yêu cầu Spring **bind kết quả trả về** vào tham số advice có tên `result`.
- Tham số `String result` vừa cho phép code đọc kết quả dưới dạng String, vừa hạn chế advice vào những kết quả kiểu String phù hợp.
- `argNames = "result"` chỉ rõ tên binding để không phải phụ thuộc hoàn toàn vào việc compiler lưu tên tham số.
- Advice này chỉ chạy khi method đã **trả về bình thường** qua lời gọi được Spring AOP can thiệp.

**Không thể** dùng `@AfterReturning` để trả một reference mới thay thế kết quả đã được method trả về. Advice có thể quan sát giá trị nhận được; nếu object mutable và bạn gọi phương thức làm thay đổi trạng thái của chính object ấy thì nội dung object có thể thay đổi — đó là tác dụng phụ cần đặc biệt tránh nếu chỉ muốn ghi log/audit.

### 2.2. `throwing`: exception thoát khỏi method

Ví dụ:

~~~java
@Aspect
public class FailureAspect {

    @AfterThrowing(
        pointcut = "execution(* example.PaymentService.pay(..))",
        throwing = "error",
        argNames = "error"
    )
    public void afterFailedPayment(IllegalArgumentException error) {
        System.out.println("invalid payment: " + error.getMessage());
    }
}
~~~

Đây cũng là **snippet**, không phải project hoàn chỉnh.

- `throwing = "error"` bind throwable được ném ra từ method execution vào tham số có tên `error`.
- Kiểu `IllegalArgumentException` làm advice chỉ áp dụng cho throwable **tương thích với kiểu này**; một `IllegalStateException` không được advice này nhận.
- Spring chỉ chạy `@AfterThrowing` khi join point đi theo **exceptional exit**, không phải bất kỳ nơi nào code đã từng tạo rồi bắt exception.
- Advice không tự biến exception thành normal return. Nếu chỉ log và return `void`, ngoại lệ gốc tiếp tục lan truyền qua proxy theo hành vi thông thường.

Một advice `@AfterThrowing` cũng **không phải exception handler toàn cục** của tất cả exceptions từ những advice khác. Theo tài liệu Spring, nó dành cho exception đến từ method join point được advice, **không mặc nhiên nhận exception do một `@After` hay `@AfterReturning` khác phát sinh**.

## 3. So sánh chính xác ngữ nghĩa

| Khía cạnh | `@AfterReturning(..., returning = "x")` | `@AfterThrowing(..., throwing = "x")` |
| --- | --- | --- |
| Thời điểm | Method execution được advice **trả về bình thường** | Method execution được advice **ném Throwable thoát ra** |
| Giá trị được bind | Return value | Throwable được ném |
| Cần tên tham số tương ứng | `x` phải trùng binding name của tham số advice | `x` phải trùng binding name của tham số advice |
| Kiểu tham số tác động matching | Ví dụ `String` chỉ nhận kết quả tương thích String | Ví dụ `IllegalArgumentException` chỉ nhận exception tương thích |
| Cách diễn tả phạm vi rộng | `Object x` khi cần kết quả dưới dạng Object, với điều kiện nhận giá trị phù hợp | `Throwable x` khi cần nhiều loại throwable |
| Nếu target bắt lỗi rồi return | Chạy nếu giá trị trả về match | **Không chạy** vì không có exception thoát join point |
| Nếu target trả `void` bình thường | Có thể dùng `@AfterReturning` **không có binding** | Không chạy vì không có throwable |
| Nếu target ném exception | Không chạy | Chạy khi kiểu exception khớp |
| Tự đổi return của caller | Không thay reference trả về bằng return của advice | Không chuyển exceptional exit thành success chỉ bằng return `void` |

**Điểm cốt lõi:** `returning` và `throwing` vừa là **tên để bind ngữ cảnh**, vừa kích hoạt **type-sensitive matching** dựa trên kiểu tham số advice. Chỉ khác mỗi kiểu Java của tham số có thể thay đổi tập invocation mà advice áp dụng.

## 4. Tên binding phải khớp tên tham số advice

Cấu hình đúng:

~~~java
@AfterReturning(
    pointcut = "execution(* example.ReportService.read(..))",
    returning = "value",
    argNames = "value"
)
public void afterRead(String value) {
    // Tên "value" nhất quán ở thuộc tính và tham số advice.
}
~~~

Cấu hình có lỗi:

~~~java
// Ví dụ SAI, không sao chép làm code chạy.
@AfterReturning(
    pointcut = "execution(* example.ReportService.read(..))",
    returning = "result",
    argNames = "value"
)
public void afterRead(String value) {
    // "result" không tương ứng binding name "value".
}
~~~

Khi cấu hình sai, Spring có thể ném exception trong quá trình phân tích/tạo advisor hoặc khi resolve parameters; **đừng dựa vào một tên exception duy nhất** cho mọi phiên bản Spring.

Quy trình kiểm tra:

1. Xác định giá trị thuộc tính `returning = "..."` hoặc `throwing = "..."`.
2. Kiểm tra method advice có tham số tương ứng không.
3. Nếu sử dụng `argNames`, tên trong đó phải tương thích với các biến được bind.
4. Kiểm tra đúng **kiểu** tham số: String, Object, loại exception cụ thể hoặc Throwable.
5. Kiểm tra expression không bỏ sót target method hoặc bị loại do pointcut khác.
6. Kiểm tra Spring AOP đã nhận diện advice method và đã tạo proxy phù hợp.

Nếu method advice có nhiều tham số, bạn có thể kết hợp `JoinPoint`, `args(...)`, `target(...)`, `@annotation(...)` và giá trị `returning`/`throwing`, nhưng cần đặt tên không xung đột và khai báo chính xác.

## 5. Spring tìm tên tham số lời advice bằng cách nào?

`returning = "value"` và `throwing = "error"` là **tên binding** phải ánh xạ được tới tham số advice có kiểu phù hợp. Ví dụ `@AfterReturning(pointcut = "execution(* example.PaymentService.find(..))", returning = "value", argNames = "value")` có thể đi với `afterFind(JoinPoint jp, String value)`; tên `jp` được lược bỏ khỏi `argNames` vì `JoinPoint` đứng đầu.

Trong Java, chọn `argNames` tường minh khi có nhiều binding, hoặc biên dịch với `-parameters` để giữ tên tham số cho Java reflection. Spring cũng có chiến lược suy luận trong những trường hợp rõ ràng; đừng xem debug symbols cũ là cách thay thế chắc chắn. `ProceedingJoinPoint` chỉ được dùng để `proceed()` trong `@Around`, không phải trong `@AfterReturning` hay `@AfterThrowing`.

Phần chuyên sâu **argNames, tên tham số và tùy chọn biên dịch `-parameters`** trình bày Maven/Gradle, named pointcut, thứ tự phát hiện tên và cách gỡ ambiguity. Riêng bài này tập trung vào **khi nào result/error được bind theo kiểu dữ liệu**, độc lập với việc tìm tên.

## 6. Kiểu tham số hạn chế những lời gọi nào được chọn?

### 6.1. Trường hợp `String` và `Object` ở `returning`

~~~java
// Chỉ quan sát return value phù hợp String.
@AfterReturning(
    pointcut = "execution(* example.CatalogService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterString(String result) {
    // ...
}
~~~

Một target method trả `String` phù hợp sẽ được advice. Một method trả `Integer` không thuộc phạm vi binding `String` chỉ vì chúng đều là Object trong Java.

Nếu đổi advice thành:

~~~java
@AfterReturning(
    pointcut = "execution(* example.CatalogService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterAnyResult(Object result) {
    // ...
}
~~~

thì kiểu `Object` nhận phạm vi kết quả rộng hơn. Từ góc nhìn Java reflection/Spring AOP, kết quả primitive được boxing ở ranh giới cần thiết khi được chuyển qua advice. Tuy nhiên, nếu mục tiêu của bạn là nhận callback cho **mọi method normal completion kể cả `void`**, hãy dùng dạng `@AfterReturning` **không khai báo `returning`**, thay vì cố ép một giá trị trả về cho method không có return value.

**Tránh ví dụ mơ hồ về `null` hoặc method khai báo Object nhưng runtime String:** ngữ nghĩa static/dynamic matching, kiểu được khai báo và giá trị runtime có thể phụ thuộc cơ chế matching. Với bài kiểm tra quan trọng, hãy thử bằng **Spring context và phương thức thật** thay vì suy luận đơn thuần từ kiểu source.

### 6.2. Trường hợp `IllegalArgumentException` và `Throwable` ở `throwing`

~~~java
@AfterThrowing(
    pointcut = "execution(* example.CatalogService.*(..))",
    throwing = "problem",
    argNames = "problem"
)
public void whenInvalidInput(IllegalArgumentException problem) {
    // ...
}
~~~

Phạm vi bị giới hạn vào exception tương thích với `IllegalArgumentException`, gồm các subclass của nó. Ngược lại:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.CatalogService.*(..))",
    throwing = "problem",
    argNames = "problem"
)
public void whenAnyThrowable(Throwable problem) {
    // ...
}
~~~

Dạng `Throwable` bao quát các throwable đi ra từ matched method. Nếu cần hẹp hơn, có thể dùng `Exception`, `RuntimeException` hoặc custom exception type. Đừng dùng `Throwable` chỉ để ghi log **mọi exception từ mọi bean**; expression nên giới hạn package/operation phù hợp.

**Đặc biệt:** `throwing` **không phụ thuộc** method có khai báo `throws IllegalArgumentException` trong signature hay không. Runtime exception unchecked vẫn có thể thoát method và được Spring AOP quan sát nếu invocation đi qua proxy, phù hợp pointcut và throwable type.

### 6.3. Không thể suy nhánh kết quả chỉ từ tên callback

Một callback `@AfterReturning` không được chạy khi method ném lỗi; một callback `@AfterThrowing` không chạy nếu target đã catch exception rồi return. Đừng viết business logic giả định rằng hai callback luôn xuất hiện thành cặp cho mỗi lời gọi. Với một invocation cụ thể, normal và exceptional exit là hai nhánh khác nhau.

## 7. Kết hợp `JoinPoint` với dữ liệu bound

Ví dụ advice quan sát method signature và return value:

~~~java
@AfterReturning(
    pointcut = "execution(* example.InvoiceService.load(..))",
    returning = "invoice",
    argNames = "invoice"
)
public void recordLoadedInvoice(JoinPoint jp, Invoice invoice) {
    String operation = jp.getSignature().getName();
    // Log tên operation và một identifier được phép.
}
~~~

Đây là **snippet**, `Invoice` và `InvoiceService` là type nghiệp vụ minh họa, không phải project chạy độc lập. Nó thể hiện:

- `JoinPoint.getSignature()` cung cấp mô tả method đang được advice.
- Giá trị `invoice` là **return value được bind**, không phải phần tử `jp.getArgs()`.
- `jp.getArgs()` cho biết **input arguments** của invocation, không phải kết quả trả về.
- `jp.getThis()` là Spring AOP proxy, `jp.getTarget()` là target object; chúng có thể không phải cùng object (đặc biệt với JDK proxy).
- Không log nguyên object `invoice` bằng `toString()` khi có thông tin nhạy cảm.

Cách sử dụng tương tự với lỗi:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.InvoiceService.load(..))",
    throwing = "failure",
    argNames = "failure"
)
public void recordFailure(JoinPoint jp, RuntimeException failure) {
    String operation = jp.getSignature().getName();
    String type = failure.getClass().getSimpleName();
    // Log operation và loại exception theo policy.
}
~~~

Advice có thể kiểm tra nội dung error để phân loại, nhưng **không nên đưa toàn bộ exception message/stack trace vào metric labels** hoặc mặc định coi chúng an toàn để public.

## 8. Khi nào callback không chạy dù biểu thức đúng?

Trong Spring AOP, sự xuất hiện của `@AfterReturning` hoặc `@AfterThrowing` trong source không đủ bảo đảm callback chạy. Cần:

1. **Aspect bean được đăng ký trong Spring container.** Class `@Aspect` đơn lẻ không đồng nghĩa `@Component`; cần `@Component` trong component scan hoặc `@Bean`.
2. **Hạ tầng Spring AOP hoạt động.** Có thể là `@EnableAspectJAutoProxy` trong Spring Framework thuần hoặc AOP auto-configuration của Spring Boot khi được bật.
3. **Pointcut match đúng method execution** trên bean cần advice.
4. **Lời gọi thực sự đi qua Spring AOP proxy.**
5. **Outcome khớp annotation:** normal return với `@AfterReturning`, exception exit với `@AfterThrowing`.
6. **Kiểu giá trị/exception phù hợp** với tham số Java được bind.

Ví dụ:

~~~java
public String outer() {
    return this.find();
}
~~~

Nếu `outer()` được gọi qua proxy, một advice nhắm vào `outer` vẫn có thể chạy. Nhưng `this.find()` bên trong target không tự quay lại proxy, nên advice riêng cho `find()` **bị bỏ qua tại lời gọi nội bộ**. Điều này áp dụng cho cả JDK proxy và CGLIB proxy Spring AOP.

**Một kết quả đặc biệt cần nhớ:** Nếu `outer()` trả về String nhờ gọi `this.find()`, một `@AfterReturning` với pointcut match **cả outer** vẫn có thể nhận String của outer, **dù invocation nội bộ find không được advice riêng**. Ví dụ runnable dưới đây có chính tình huống ấy.

## 9. Ví dụ Maven + Java 17+ hoàn chỉnh

### 9.1. Mục tiêu kiểm chứng

Dự án sử dụng **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Java **17+** và Maven. Các tình huống:

- `find()` trả `String`: kích hoạt `@AfterReturning` có tham số `String`.
- `count()` trả `int`: **không** kích hoạt advice trả về String.
- `ping()` là `void`, hoàn thành bình thường: kích hoạt `@AfterReturning` **không binding** cho đúng method ấy.
- `failInput()` ném `IllegalArgumentException`: kích hoạt `@AfterThrowing` bound `IllegalArgumentException`.
- `failState()` ném `IllegalStateException`: **không** kích hoạt advice giới hạn `IllegalArgumentException`, nhưng kích hoạt advice bound `Throwable` có pointcut riêng.
- `recover()` tự bắt `IllegalArgumentException` rồi return String: kích hoạt after-returning String, **không** kích hoạt after-throwing.
- `selfCall()` gọi `this.find()`: callback chỉ nhận **kết quả của selfCall** mà proxy đã thấy, không nhận thêm invocation của find bên trong.

Các advice không chỉnh return value, không nuốt exception và không có hai callback **cùng loại trên cùng một join point** để stdout tránh thứ tự không xác định.

### 9.2. Cấu trúc

~~~text
spring-binding-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── DemoService.java
    ├── BindingAspect.java
    └── Main.java
~~~

### 9.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-binding-demo</artifactId>
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
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
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

BOM giúp các dependency Spring dùng version thống nhất. Trong dự án Spring Boot thật, ưu tiên starter/BOM của Boot thay vì copy version của demo vào nơi đang được Boot quản lý.

### 9.4. `DemoService.java`

~~~java
package example;

public class DemoService {

    public String find() {
        System.out.println("target: find");
        return "FOUND";
    }

    public int count() {
        System.out.println("target: count");
        return 3;
    }

    public void ping() {
        System.out.println("target: ping");
    }

    public void failInput() {
        System.out.println("target: failInput");
        throw new IllegalArgumentException("invalid");
    }

    public void failState() {
        System.out.println("target: failState");
        throw new IllegalStateException("state");
    }

    public String recover() {
        System.out.println("target: recover begin");
        try {
            throw new IllegalArgumentException("invalid");
        } catch (IllegalArgumentException ignored) {
            System.out.println("target: handled invalid");
            return "RECOVERED";
        }
    }

    public String selfCall() {
        System.out.println("target: selfCall");
        return this.find();
    }
}
~~~

Điểm học chính: `recover()` có một exception **nội bộ đã bị bắt**, nên nó trả về bình thường. `selfCall()` sử dụng `this.find()`, không tạo invocation mới qua Spring AOP proxy cho method find.

### 9.5. `BindingAspect.java`

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class BindingAspect {

    @AfterReturning(
        pointcut = "execution(* example.DemoService.*(..))",
        returning = "value",
        argNames = "value"
    )
    public void whenStringReturned(JoinPoint jp, String value) {
        System.out.println("returning String: "
            + jp.getSignature().getName() + " -> " + value);
    }

    @AfterReturning("execution(* example.DemoService.ping(..))")
    public void afterVoidPing() {
        System.out.println("returning ping: normal exit");
    }

    @AfterThrowing(
        pointcut = "execution(* example.DemoService.*(..))",
        throwing = "error",
        argNames = "error"
    )
    public void whenIllegalArgument(JoinPoint jp, IllegalArgumentException error) {
        System.out.println("throwing IAE: "
            + jp.getSignature().getName() + " -> " + error.getMessage());
    }

    @AfterThrowing(
        pointcut = "execution(* example.DemoService.failState(..))",
        throwing = "failure",
        argNames = "failure"
    )
    public void whenFailState(Throwable failure) {
        System.out.println("throwing Throwable: failState -> "
            + failure.getClass().getSimpleName());
    }
}
~~~

Các điểm cần kiểm tra:

- `whenStringReturned` có `returning = "value"`, `String value` và `argNames = "value"` **trùng tên**.
- `whenIllegalArgument` có `throwing = "error"`, `IllegalArgumentException error` và `argNames = "error"` **trùng tên**.
- `whenFailState` có `Throwable failure` nên nhận `IllegalStateException` do target ném từ `failState()`.
- `afterVoidPing()` không ràng buộc return value nên có thể chạy sau method `void` kết thúc bình thường.
- `JoinPoint` là tham số đầu tiên trong hai advice, và không phải đưa tên của nó vào `argNames`.
- `@Aspect` không tự đăng ký làm Spring bean; `AppConfig` sẽ khai báo `@Bean` cho `BindingAspect`.
- Không có advice nào biến giá trị trả về hoặc exception thành một kết quả khác.

### 9.6. `AppConfig.java`

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public DemoService demoService() {
        return new DemoService();
    }

    @Bean
    public BindingAspect bindingAspect() {
        return new BindingAspect();
    }
}
~~~

Spring AOP nhận diện `BindingAspect` là aspect bean, tạo advisors cho các phương thức được annotate và áp dụng chúng lên `DemoService`. `proxyTargetClass = true` sử dụng class-based CGLIB proxy để code demo lấy bean bằng `DemoService.class`. Điều này không làm self-invocation chạy advice.

### 9.7. `Main.java`

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            DemoService service = context.getBean(DemoService.class);

            System.out.println("spring AOP proxy: " + AopUtils.isAopProxy(service));

            System.out.println("-- string return --");
            System.out.println("caller: " + service.find());

            System.out.println("-- primitive return --");
            System.out.println("caller: " + service.count());

            System.out.println("-- void normal return --");
            service.ping();

            System.out.println("-- illegal argument --");
            try {
                service.failInput();
            } catch (IllegalArgumentException e) {
                System.out.println("caller caught: " + e.getMessage());
            }

            System.out.println("-- other exception --");
            try {
                service.failState();
            } catch (IllegalStateException e) {
                System.out.println("caller caught: " + e.getMessage());
            }

            System.out.println("-- exception caught in target --");
            System.out.println("caller: " + service.recover());

            System.out.println("-- self invocation --");
            System.out.println("caller: " + service.selfCall());
        }
    }
}
~~~

Chạy ở thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 9.8. Stdout dự kiến

Các dòng do chính mã ví dụ in ra theo thứ tự, không kể log tùy cấu hình của Maven/JVM:

~~~text
spring AOP proxy: true
-- string return --
target: find
returning String: find -> FOUND
caller: FOUND
-- primitive return --
target: count
caller: 3
-- void normal return --
target: ping
returning ping: normal exit
-- illegal argument --
target: failInput
throwing IAE: failInput -> invalid
caller caught: invalid
-- other exception --
target: failState
throwing Throwable: failState -> IllegalStateException
caller caught: state
-- exception caught in target --
target: recover begin
target: handled invalid
returning String: recover -> RECOVERED
caller: RECOVERED
-- self invocation --
target: selfCall
target: find
returning String: selfCall -> FOUND
caller: FOUND
~~~

**Tại sao output ổn định?** Mỗi trường hợp được thiết kế chỉ có một advice **của loại phù hợp thực sự in log** trên mỗi invocation, không dựa vào thứ tự không xác định giữa hai advice cùng loại cùng match join point. Không log proxy class name cụ thể vì JDK/Spring có thể thay đổi tên sinh động.

### 9.9. Đọc kết quả từng trường hợp

**1) `find()`:** method trả `String "FOUND"`. Advice có `String value` chạy; caller vẫn nhận `FOUND` vì `@AfterReturning` không thay reference trả về.

**2) `count()`:** method trả primitive `int 3`. Kiểu trả về không phù hợp `String`; không có dòng `returning String`. Caller nhận `3`.

**3) `ping()`:** method `void` hoàn tất bình thường; `@AfterReturning` không có `returning` của riêng ping chạy và in `returning ping: normal exit`. Không có giá trị trả về nào cần bind.

**4) `failInput()`:** target ném `IllegalArgumentException("invalid")` ra ngoài. `@AfterThrowing` có tham số `IllegalArgumentException error` được gọi. Caller vẫn bắt ngoại lệ gốc sau advice.

**5) `failState()`:** target ném `IllegalStateException("state")`. Advice chỉ nhận `IllegalArgumentException` **không chạy** cho exception này; advice có `Throwable failure` và pointcut riêng match method `failState` sẽ chạy. Caller vẫn bắt `IllegalStateException`.

**6) `recover()`:** exception `IllegalArgumentException` được **catch trong chính target method**, rồi method trả String `RECOVERED`. Spring AOP thấy normal return, nên advice bound String chạy; `@AfterThrowing` không thấy exception bị catch nội bộ.

**7) `selfCall()`:** caller gọi `selfCall` qua proxy. Trong target, `this.find()` bypass proxy, nhưng kết quả `FOUND` của `selfCall` vẫn được trả về qua proxy, nên `@AfterReturning` in **một lần** cho `selfCall`. Không có dòng returning riêng cho method `find` nội bộ.

## 10. Nếu muốn lấy cả arguments và result/error?

Spring AOP cho phép binding đối số method qua `args(...)` kết hợp với `returning` hoặc `throwing`. Ví dụ minh họa dành cho method `lookup(String key)`:

~~~java
@AfterReturning(
    pointcut = "execution(* example.KeyService.lookup(..)) && args(key)",
    returning = "result",
    argNames = "key,result"
)
public void afterLookup(String key, String result) {
    System.out.println("lookup completed");
}
~~~

Đây là **snippet**, không thuộc project demo. Các tên `key` và `result` đều có thể được bind nếu expression và signature đúng. `args(key)` ràng buộc đối số đầu vào; `returning = "result"` ràng buộc giá trị **đầu ra**.

Tương tự:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.KeyService.lookup(..)) && args(key)",
    throwing = "failure",
    argNames = "key,failure"
)
public void afterLookupFailed(String key, RuntimeException failure) {
    System.out.println("lookup failed");
}
~~~

Tuy nhiên:

- Không đưa toàn bộ `key`, return object, exception message hoặc stack trace vào log nếu chứa bí mật.
- Kiểu `String key` hạn chế những invocation có argument phù hợp.
- Kiểu `String result` và `RuntimeException failure` tiếp tục giới hạn kết quả/exception được binding.
- Khi có overloads, generics hoặc interfaces, hãy test binding bằng **context thật**, không đoán chỉ từ tên method.
- Nếu có `JoinPoint` đứng đầu signature, có thể không ghi tên `JoinPoint` trong `argNames`.

## 11. Tại sao `@AfterReturning` không dùng để đổi kết quả?

Ví dụ sai về ý định:

~~~java
// Advice method có thể thực thi, nhưng String trả từ method này
// KHÔNG trở thành return value thay thế cho caller.
@AfterReturning(
    pointcut = "execution(* example.DemoService.find(..))",
    returning = "value",
    argNames = "value"
)
public void changeResult(String value) {
    value = "OVERRIDDEN";
}
~~~

Thay local variable `value` không thay giá trị caller nhận. Nếu bạn thực sự phải sửa result theo một policy rõ ràng, cần cân nhắc `@Around` để:

~~~java
@Around("execution(* example.DemoService.find(..))")
public Object transform(ProceedingJoinPoint pjp) throws Throwable {
    Object original = pjp.proceed();
    return transformUnderBusinessContract(original);
}
~~~

Đây là **snippet minh họa**, `transformUnderBusinessContract(...)` cần được ứng dụng định nghĩa. Dùng `@Around` với `return` thay thế có khả năng thay đổi contract, không nên dùng chỉ để audit hoặc log.

Lưu ý: nếu `@AfterReturning` nhận một **mutable object**, gọi method sửa object đó có thể tạo thay đổi quan sát được ở caller dù không thay reference. Đây vẫn là **mutation side effect** và có thể trái với yêu cầu “advice chỉ đọc kết quả”.

## 12. Tại sao `@AfterThrowing` không phải `catch` toàn cục?

Một advice kiểu:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.DemoService.failInput(..))",
    throwing = "error",
    argNames = "error"
)
public void logError(IllegalArgumentException error) {
    System.out.println("invalid input");
}
~~~

không biến việc ném exception thành một normal return. Khi advice return `void`, exception ban đầu tiếp tục lan truyền. Nó chỉ quan sát **exception thoát khỏi method execution được match**.

Nếu advice tự ném một exception mới, exception đó có thể **thay đổi exception caller thấy**. Đừng throw một lỗi mới từ logic logging/metrics chỉ vì backend log không sẵn sàng. Nếu muốn chủ động catch/translate/fallback, bạn cần thiết kế tại tầng xử lý phù hợp hoặc dùng `@Around` có hợp đồng rõ ràng về `try/catch` và trả về.

**Một ngoại lệ không được advice nhìn thấy** không đồng nghĩa exception không tồn tại: có thể target bắt nội bộ, một interceptor phía trong đã xử lý rồi return fallback, hoặc caller không đi qua Spring AOP proxy.

## 13. Giới hạn đặc thù của Spring AOP proxy

### 13.1. JDK proxy và CGLIB

- **JDK dynamic proxy**: interface-based; caller nên inject qua interface được expose.
- **CGLIB class-based proxy**: subclass target; không thể proxy final class, final/private method không được advice theo cơ chế override.
- **Cả hai** cùng chịu giới hạn self-invocation trong Spring AOP. Chuyển sang CGLIB không tự làm `this.method()` đi qua proxy.

### 13.2. Aspect bean phải là Spring bean

Class `@Aspect` có thể được đăng ký bằng `@Component` dưới component scan, hoặc một method `@Bean` trả về aspect instance. Nếu aspect chỉ tồn tại dưới dạng class trên classpath, Spring không có nghĩa vụ nhận advice của nó.

Trong Spring Framework thuần, `@EnableAspectJAutoProxy` là cấu hình quen thuộc. Trong Spring Boot, auto-configuration AOP có thể cung cấp hạ tầng này tùy dependency và setting; vẫn cần aspect bean đúng.

### 13.3. Method không qua proxy

- `new DemoService().find()` ngoài container không tự có Spring advice.
- `this.find()` trong target không tạo thêm invocation qua proxy.
- Lấy underlying target từ `Advised.getTargetSource()` rồi gọi trực tiếp có thể bypass advice.
- Một around interceptor ở ngoài return sớm mà không `proceed()` có thể ngăn invocation đi vào các advice phía trong.

### 13.4. Kết quả async/reactive

Nếu method trả về `CompletableFuture` hoặc một reactive publisher, `@AfterReturning` có thể chạy khi **method trả về Future/Publisher object**, không có nghĩa công việc bất đồng bộ/pipeline đã hoàn tất. `@AfterThrowing` tại method boundary không mặc nhiên nhận những lỗi phát sinh **sau đó** trong future/stream.

Cần theo dõi completion qua callback/lifecycle của Future hoặc reactive operator phù hợp khi muốn quan sát kết quả bất đồng bộ cuối cùng; không biến `returning` thành cơ chế chờ future hoàn thành.

## 14. Lỗi thường gặp và phương pháp chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Spring báo lỗi binding tên tham số | `returning`/`throwing` không khớp tên tham số, `argNames` sai hoặc không có metadata tên | So thuộc tính annotation, Java parameter name; dùng `argNames` hoặc compile `-parameters` |
| `@AfterReturning` không chạy với một method `int` | Advice nhận `String`, kiểu không phù hợp | Đổi kiểu nếu mục đích nghiệp vụ cho phép hoặc dùng pointcut khác |
| Method `void` không kích hoạt advice có `returning` cụ thể | Không có return value để bind | Dùng `@AfterReturning` không binding cho normal completion |
| `@AfterThrowing(IllegalArgumentException)` không chạy với `IllegalStateException` | Typed throwing binding giới hạn throwable | Chọn type phù hợp hoặc `Throwable` nếu cần phạm vi rộng |
| Advice `@AfterThrowing` không thấy lỗi đã được `catch` | Target trả về bình thường | Kiểm tra exception thực sự thoát method |
| Exception vẫn tới caller sau `@AfterThrowing` | Đây là hành vi bình thường | Nếu cần handling/translation, thiết kế riêng; không coi after-throwing là catch |
| Bean có proxy nhưng method không chạy advice | Pointcut/returning/throwing không match hoặc advisor do tính năng khác | Kiểm tra eligible advisors và method signature |
| Advice chạy khi gọi trực tiếp service nhưng không chạy trong `this.method()` | Self-invocation không đi qua proxy | Tách method cần advice sang Spring bean khác khi phù hợp |
| JDK proxy không cast sang implementation | Runtime proxy type là interface-based | Inject interface hoặc xác minh class-based proxy có thể dùng |
| Dùng `JoinPoint.getArgs()` để tìm return value | Args là **tham số đầu vào** | Dùng `returning` để nhận return value |
| Đổi String bound value mà caller không thấy đổi | `@AfterReturning` không thay reference | Nếu cần biến đổi result, cân nhắc `@Around` có kiểm soát |
| Advice có hai tham số bind nhưng `argNames` chỉ ghi một | Binding thiếu hoặc mơ hồ | Liệt kê tên các bind variables và kiểm tra JoinPoint đầu tiên |
| Log về exception nhạy cảm bị lộ | In message/stack trace hoặc object bất kể policy | Giới hạn dữ liệu, chuẩn hóa labels và kiểm soát log |
| Advice chạy không theo thứ tự dự tính | Nhiều advisors/aspects, `@Order`/infrastructure order | Kiểm tra precedence và integration test cụ thể |

### Checklist nhanh

1. **Target là Spring bean?** Lấy qua context hoặc dependency injection.
2. **Aspect là bean?** Xem `@Component` scan hoặc `@Bean` và AOP setup.
3. **Pointcut đúng?** Kiểm tra package, class, method, visibility, JDK/CGLIB.
4. **Tên binding đúng?** `returning="value"` ↔ `value`, `throwing="error"` ↔ `error`.
5. **Kiểu binding đúng?** `String`, `Integer`, `Object`, `IllegalArgumentException`, `Throwable`.
6. **Nhánh đúng?** Normal return hay exceptional exit; exception có bị catch trong target không?
7. **Lời gọi qua proxy?** Không `new` hoặc self-invocation.
8. **Có infrastructure advisors hoặc quanh method shortcut?** Kiểm tra interceptor chain.
9. **Test negative cases?** Method `void`, return type khác, exception type khác, catch nội bộ.
10. **Preserve business contract?** Advice không đổi return reference, không mask exception, không log dữ liệu nhạy cảm.

## 15. Bài tập thực hành

**Tình huống A.** Aspect dùng `@AfterReturning(returning="result")` và `public void audit(String result)`; method trả `Integer`. Có chắc advice chạy?

**Đáp án:** Không. Typed binding String giới hạn kết quả tương thích String; Integer không tương thích String.

**Tình huống B.** `@AfterThrowing(throwing="failure")` bind `IllegalArgumentException failure`, nhưng method ném `IllegalStateException`. Lời advice có chạy không?

**Đáp án:** Không nếu không có exception phù hợp khác. Cả hai là RuntimeException nhưng không phải subtype của nhau.

**Tình huống C.** Method ném `IllegalArgumentException` rồi catch ngay bên trong và trả `"RECOVERED"`. Nhánh nào Spring AOP nhìn thấy?

**Đáp án:** Normal return. `@AfterReturning` có type tương thích sẽ chạy; `@AfterThrowing` không nhận exception đã bị target bắt.

**Tình huống D.** Tên advice method parameter là `value`, annotation ghi `returning="result"` và `argNames="value"`. Có hợp lệ không?

**Đáp án:** Không. Tên `returning` phải tương ứng binding name của tham số; hãy khai báo thống nhất.

**Tình huống E.** `@AfterReturning` không có `returning` được đặt riêng cho một method `void ping()` trả về bình thường. Nó có chạy không?

**Đáp án:** Có thể chạy khi pointcut match, Spring AOP proxy nhận invocation và method kết thúc bình thường. Không yêu cầu bind một return value.

**Tình huống F.** Một method `selfCall()` có `String` return, bên trong gọi `this.find()`. Aspect bound String match cả hai method. Caller gọi `selfCall()` trên proxy. Có mấy invocation đi qua proxy?

**Đáp án:** Một invocation cho `selfCall()`. `find()` nội bộ bị bypass, nhưng return String của `selfCall()` vẫn có thể được advice nhận.

**Tình huống G.** `@AfterThrowing` log lỗi và return `void`. Nó đã “handle exception” để caller không thấy lỗi chưa?

**Đáp án:** Chưa. Sau advice, exception gốc vẫn lan truyền khi không có tầng khác chủ động xử lý.

**Tình huống H.** Class `@Aspect` có advice đúng nhưng không đăng ký thành Spring bean. Có phải tất cả method có signature phù hợp sẽ được advice?

**Đáp án:** Không. Spring AOP cần aspect bean để nhận diện advisor; annotation trên class đơn độc không đủ.

**Tình huống I.** `@AfterReturning` nhận `String result` và gán `result = "new"`. Caller có nhận chuỗi mới không?

**Đáp án:** Không. Gán lại biến cục bộ trong advice không thay reference đã được method trả về. Muốn biến đổi return cần cân nhắc `@Around`.

## 16. Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): giải thích `@AfterReturning` và `@AfterThrowing` với `returning`, `throwing`, typed binding, naming, `JoinPoint` và advice ordering.
- [Spring Framework — Determining Argument Names](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html#_determining_argument_names): `argNames`, Java `-parameters` và cơ chế tìm tên tham số.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký aspect bean, bật `@EnableAspectJAutoProxy`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): ranh giới JDK/CGLIB proxies và self-invocation.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): cú pháp pointcut Spring hỗ trợ.
- [Spring Framework — Spring AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): normal và exceptional exits ở cấp method join point.
