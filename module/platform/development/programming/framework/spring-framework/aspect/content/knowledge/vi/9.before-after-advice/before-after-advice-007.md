# Giới hạn của `@AfterReturning` khi muốn thay đối tượng trả về trong Spring AOP

## 1. Vấn đề: đã lấy được return value nhưng có thay được object caller nhận không?

Trong Spring AOP, `@AfterReturning` là **advice chạy khi một method execution được chọn kết thúc bình thường**. Nó thường dùng để ghi log kết quả, audit, cập nhật metric hoặc kiểm tra giá trị trả về.

Ví dụ:

```java
@AfterReturning(
    pointcut = "execution(* com.example.order.OrderService.find(..))",
    returning = "result",
    argNames = "result"
)
public void afterFind(Object result) {
    // Quan sát kết quả từ phương thức được advice.
}
```

Đây là **method fragment** cần đặt bên trong một class `@Aspect` đã được Spring quản lý. Thuộc tính `returning = "result"` bind giá trị được method trả về vào tham số `result` của advice.

Câu hỏi dễ gây nhầm lẫn: nếu trong advice viết `result = new Result(...)`, caller có nhận object mới không?

**Không.** Tài liệu Spring Framework nêu rõ `@AfterReturning` **không thể trả về một reference hoàn toàn khác** cho caller. Tham số được bind chỉ giúp advice **quan sát giá trị đã trả về**; gán lại biến Java cục bộ trong advice không thay thế return value nằm trong interceptor chain.

Tuy nhiên, nếu return value là một **object mutable** và advice sửa trạng thái của chính object đó, caller vẫn có thể thấy trạng thái đã thay đổi, vì advice và caller đang tham chiếu cùng object. Đây là **mutation của object đang được trả về**, không phải **thay object được trả về**. Sự phân biệt này rất quan trọng khi thiết kế Spring Aspect.

Nếu yêu cầu thật sự là **thay object/reference kết quả**, hãy dùng `@Around` (hoặc thiết kế lại logic return trong service/mapper), vì `@Around` có thể gọi `ProceedingJoinPoint.proceed()` rồi **trả về một object khác** cho caller.

Bài này chỉ tập trung vào **advice Spring `@AspectJ` trên Spring-managed beans qua proxy**, theo phạm vi Spring Aspect. Không bàn các cơ chế AspectJ weaving độc lập.

## 2. So sánh ba thao tác nhìn gần giống nhau

Giả sử method đích trả về:

```java
ResultBox returned = service.load("A");
```

Trong `@AfterReturning`:

| Thao tác | Ví dụ trong advice | Caller nhìn thấy gì? |
| --- | --- | --- |
| **Đọc kết quả** | `System.out.println(result)` | Object/reference đã được target trả về, không đổi vì việc đọc. |
| **Sửa trạng thái object mutable** | `result.setStatus("checked")` | Có thể thấy `status` mới trên **chính object cũ**. |
| **Gán lại biến parameter** | `result = new ResultBox("other")` | **Không nhận object mới**; phép gán chỉ đổi local variable của advice. |
| **Thử `return result` từ `@AfterReturning`** | Đổi advice từ `void` sang trả object để mong thay kết quả | Không phải cơ chế thay return value của Spring `@AfterReturning`; không nên dùng. |
| **`@Around` trả object mới** | `return new ResultBox("other")` | Caller nhận object được `@Around` trả, nếu method contract và chain cho phép. |

Hãy tách hai khái niệm:

- **Reference identity**: `a == b` kiểm tra có cùng Java object không.
- **Object state**: `a.getStatus()` cho biết dữ liệu hiện tại trong object.

Một `@AfterReturning` có thể tác động đến **state** nếu object mutable; nó **không có quyền thay thế reference cuối cùng** qua phép gán lại tham số advice.

## 3. Spring `@AfterReturning` chạy vào thời điểm nào?

Luồng thông thường của một lời gọi qua Spring AOP proxy:

```text
Calling bean / ApplicationContext client
                 |
                 v
         Spring AOP proxy
                 |
          advisor chain
                 |
                 v
         target business method
                 |
                 +--> return resultRef (normal completion)
                 |
                 v
        @AfterReturning advice
         |       |       |
         |       |       +-- log/audit/metric
         |       +---------- có thể mutate resultRef nếu object mutable
         +------------------ local assignment KHÔNG thay returned ref
                 |
                 v
            caller nhận resultRef
```

Sơ đồ này mô tả một `@AfterReturning` phù hợp, trong một chuỗi advice đơn giản. Trong ứng dụng có nhiều `@Around`, `@AfterReturning` hoặc advisor khác, **thứ tự và object cuối cùng có thể bị thay bởi một `@Around` bên ngoài**. Điều đó **không thay đổi** giới hạn của bản thân `@AfterReturning`.

Các điều kiện cần nhớ:

1. **Chỉ chạy khi method được chọn trả về bình thường.** Nếu target method ném exception đi ra ngoài, `@AfterReturning` không phải callback dành cho trường hợp đó. Nếu cần xử lý exception, xem `@AfterThrowing` hoặc `@Around` tùy yêu cầu.
2. **Chỉ có hiệu lực nếu lời gọi đi qua Spring AOP proxy phù hợp.** `new Service().run()` hoặc self-invocation `this.run()` thường bỏ qua advice.
3. **`@AfterReturning` có thể được khai báo không bind return value.** Cần biết method chạy thành công nhưng không cần result thì dùng `@AfterReturning("pointcut...") public void afterSuccess()`.
4. **Binding theo `returning` có điều kiện kiểu.** Tham số advice càng cụ thể, tập những return values/method executions có thể match càng hẹp.
5. **Thay thế giá trị trả về** và **quan sát giá trị trả về** là hai trách nhiệm khác nhau; hãy chọn loại advice tối thiểu đáp ứng mục tiêu.

## 4. `returning` bind đối số thế nào và những giới hạn thường gặp?

Ví dụ Spring `@Aspect`:

```java
@AfterReturning(
    pointcut = "execution(public * com.example.report.ReportService.load(..))",
    returning = "result",
    argNames = "result"
)
public void observe(ResultBox result) {
    System.out.println(result.getValue());
}
```

Ý nghĩa:

- `pointcut`: chọn method execution được advice.
- `returning`: tên của **parameter trong method advice**, ở đây là `result`.
- `argNames`: chỉ rõ tên binding để Spring không phải phụ thuộc hoàn toàn vào compiler parameter metadata.
- `ResultBox`: kiểu tham số advice; Spring dùng nó để ràng buộc các return values tương thích.
- `observe(...)`: chạy **sau normal return**; không nhận `ProceedingJoinPoint` và không có cơ chế `return` thay thế kết quả.

Đoạn này chỉ là fragment: cần imports, class `ResultBox`, class `ReportService`, annotation `@Aspect` và Spring configuration.

### 4.1. Binding bằng `Object` và bằng kiểu cụ thể

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.*(..))",
    returning = "value",
    argNames = "value"
)
public void observeAnything(Object value) {
    // Đọc result của những lời gọi return phù hợp.
}
```

so với:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.*(..))",
    returning = "box",
    argNames = "box"
)
public void observeBoxes(ResultBox box) {
    // Chỉ áp dụng khi kết quả có kiểu tương thích ResultBox.
}
```

**Hai advice fragments này là lựa chọn thay thế, không phải yêu cầu đăng ký cùng lúc.** Binding không đơn thuần ép kiểu rồi hy vọng an toàn: kiểu của parameter advice ảnh hưởng đến matching. Với `void`, `null`, primitive boxing hoặc generic return types, nên chạy integration test trên phiên bản Spring thực tế thay vì mặc định mọi kiểu return đều bind được như nhau.

### 4.2. Chữ `returning` không phải tên biến ở target

Target:

```java
public ResultBox load() {
    ResultBox internal = new ResultBox("value");
    return internal;
}
```

Aspect:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.load(..))",
    returning = "answer",
    argNames = "answer"
)
public void after(ResultBox answer) {}
```

Điều này hoàn toàn hợp lệ về mặt **tên**: `answer` không phải trùng với `internal`. Thuộc tính `returning` chỉ phải tương ứng tham số **của advice**, và giá trị binding lấy từ object target return.

### 4.3. Không thể sửa bằng cách đổi return type của advice

Một thử nghiệm sai:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.load(..))",
    returning = "result"
)
public ResultBox after(ResultBox result) {
    return new ResultBox("replacement");
}
```

**Đây là anti-pattern minh họa, không phải code khuyến nghị chạy.** Return value của method advice `@AfterReturning` không được dùng làm return value của method target. Spring có thể yêu cầu các dạng signature cụ thể; dù Java method có trả được `ResultBox`, nó **không cung cấp một hợp đồng thay thế reference** tương tự `@Around`.

Nên khai báo advice `void` và đặt logic transformation tại đúng tầng.

## 5. Sửa mutable object khác hoàn toàn với thay reference

Giả sử một service trả về một object mutable:

```java
public final class ResultBox {
    private String value;

    public ResultBox(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public void setValue(String value) {
        this.value = value;
    }
}
```

Target:

```java
ResultBox original = new ResultBox("origin");
return original;
```

Advice:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.load(..))",
    returning = "result",
    argNames = "result"
)
public void after(ResultBox result) {
    result.setValue("changed");          // Mutation: caller có thể thấy.
    result = new ResultBox("new-object"); // Rebinding: caller KHÔNG nhận ref mới.
}
```

Đây là những fragments có thể đặt vào project Spring hoàn chỉnh. Hai thao tác trong cùng advice có hệ quả riêng:

- `setValue("changed")` đổi dữ liệu **trong instance đã có**.
- `result = new ResultBox(...)` chỉ đổi tham số Java **cục bộ** của advice.
- Caller nhận **cùng reference object trước mutation**, và `getValue()` có thể trả `"changed"`.
- Nếu caller đang giữ reference tới object ấy từ nơi khác, bên đó cũng có thể thấy mutation; đây là shared mutable state, không phải một “bản copy đã sửa”.

**Có thể mutate không có nghĩa nên mutate.** Một aspect dùng chung âm thầm sửa DTO, entity hoặc collection có thể phá invariant, thay dữ liệu cache, gây race condition và làm logic nghiệp vụ khó hiểu. Nếu chính sách thật sự cần đổi response, ưu tiên thiết kế transformation rõ ràng bằng `@Around` hoặc một service/mapper chuyên trách.

### 5.1. Object immutable: gán lại càng không có tác dụng

Với `String`, record bất biến hoặc DTO immutable:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.message(..))",
    returning = "text",
    argNames = "text"
)
public void afterMessage(String text) {
    text = "rewritten:" + text;
}
```

`String` immutable nên không có `setValue()` để đổi nội dung object cũ. Phép gán lại `text` chỉ tạo hoặc trỏ đến một `String` khác trong phạm vi local của advice. **Caller vẫn nhận `String` mà target (hoặc advisor thích hợp khác) quyết định trả về**.

Với collection mutable, `list.add(...)` trong `@AfterReturning` có thể làm caller thấy thêm phần tử; nhưng `list = new ArrayList<>(...)` không thay reference của kết quả. Nếu collection unmodifiable/immutable, cố mutation còn có thể ném exception. Không viết `@AfterReturning` thay dữ liệu kiểu này theo giả định mọi return type đều mutable.

## 6. Muốn thay object trả về thì dùng `@Around`

Theo Spring Framework, `@Around` nhận **`ProceedingJoinPoint`** và bao quanh lời gọi method. Nó có thể:

1. Thực hiện logic trước method.
2. Gọi `proceed()` để cho target (hoặc phần chain bên trong) thực thi.
3. Quan sát object được trả về.
4. Trả về **chính object đó**, object đã wrap, object đã biến đổi, hoặc object thay thế khác cho caller.

Ví dụ fragment:

```java
@Around("execution(* com.example.report.ReportService.load(..))")
public Object replaceResult(org.aspectj.lang.ProceedingJoinPoint pjp)
        throws Throwable {

    ResultBox original = (ResultBox) pjp.proceed();
    ResultBox replacement =
            new ResultBox("wrapped:" + original.getValue());

    return replacement; // Return value mà caller nhìn thấy.
}
```

Ngược với `@AfterReturning`, **giá trị return của `@Around` chính là giá trị Spring proxy trả cho caller**, miễn phù hợp với contract method và các advisors bao ngoài.

Spring cũng cho phép `@Around` không gọi `proceed()` trong những trường hợp có chủ đích như cache hit; tuy nhiên khi mục tiêu là **transform kết quả của method**, thông thường **phải gọi `proceed()` đúng số lần** và xử lý return/exception rõ ràng.

### 6.1. Các ràng buộc quan trọng của `@Around`

- **Đúng kiểu return:** nếu method khai báo trả `ResultBox`, không được trả một `String` bất kỳ rồi mong Java caller hoạt động bình thường. Spring/JVM có thể ném lỗi kiểu khi proxy trả kết quả không tương thích.
- **`null` và primitive:** khi method return primitive, return null thường không hợp lệ; cẩn thận boxing/unboxing.
- **Giữ contract nghiệp vụ:** wrapping/transforming response có thể thay identity, equality và serialization, khiến cache hoặc API consumers thay đổi hành vi.
- **Exception:** `proceed()` có thể ném `Throwable`. Chỉ thay đổi/nuốt exception nếu policy yêu cầu và đã được test.
- **Đi qua Spring proxy:** `@Around` cũng không tự áp dụng cho object được tạo bằng `new` hoặc lời gọi self-invocation `this.method()`.
- **Không phải lúc nào cũng cần `@Around`:** nếu chỉ ghi log/metrics sau thành công, giữ `@AfterReturning` là phù hợp và dễ bảo trì hơn.

## 7. Ví dụ chạy được Java 17+: chứng minh identity và replacement

Ví dụ dùng Spring Framework **6.1.14**, `aspectjweaver` **1.9.22.1**, Maven và JDK 17+. Đây là phiên bản mẫu cố định; code dùng **Spring proxy-based AOP**, không bật AspectJ weaving.

Nó thực hiện ba trường hợp trên **cùng một Spring service proxy**:

1. `loadPlain("A")`: target trả mutable `ResultBox`; `@AfterReturning` **mutate object** rồi gán lại biến local. Caller vẫn nhận reference gốc đã đổi state.
2. `loadWrapped("B")`: `@Around` gọi target rồi **trả về object khác**. Caller thấy reference mới.
3. `message("C")`: `@AfterReturning` quan sát `String` và gán lại biến local. Caller vẫn nhận `String` gốc.

### 7.1. Cấu trúc project

```text
spring-after-returning-limit/
├── pom.xml
└── src/main/java/com/example/returnadvice/
    ├── ResultBox.java
    ├── ReportService.java
    ├── ResultAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-after-returning-limit</artifactId>
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

`spring-context` quản lý `ApplicationContext` và mang dependency Spring AOP phù hợp với bộ Spring đã chọn; `aspectjweaver` hỗ trợ parser/matching cho `@Aspect` pointcut expressions. Không cần cấu hình `-javaagent` hay AspectJ compiler.

### 7.3. `src/main/java/com/example/returnadvice/ResultBox.java`

```java
package com.example.returnadvice;

public final class ResultBox {
    private String value;

    public ResultBox(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public void setValue(String value) {
        this.value = value;
    }
}
```

`ResultBox` được thiết kế **mutable**. Class `final` này là **return value**, không phải Spring target bean cần CGLIB subclassing; việc class `ResultBox` là `final` không ngăn proxy bao quanh `ReportService`.

### 7.4. `src/main/java/com/example/returnadvice/ReportService.java`

```java
package com.example.returnadvice;

public class ReportService {
    private ResultBox lastPlain;
    private ResultBox lastWrapped;

    public ResultBox loadPlain(String id) {
        lastPlain = new ResultBox("plain:" + id);
        System.out.println("[TARGET plain] " + lastPlain.getValue());
        return lastPlain;
    }

    public ResultBox loadWrapped(String id) {
        lastWrapped = new ResultBox("source:" + id);
        System.out.println("[TARGET wrapped] " + lastWrapped.getValue());
        return lastWrapped;
    }

    public String message(String id) {
        return "text:" + id;
    }

    public ResultBox rawPlainReference() {
        return lastPlain;
    }

    public ResultBox rawWrappedReference() {
        return lastWrapped;
    }
}
```

Hai method `rawPlainReference()` và `rawWrappedReference()` chỉ để **thí nghiệm so sánh reference** mà target đã tạo; chúng không expose raw target của chính `ReportService`. Ứng dụng thực tế không nên cố giữ mutable response state trong singleton service nếu nhiều thread/request có thể gọi đồng thời. Ví dụ chạy tuần tự để so sánh chính xác hai tham chiếu.

### 7.5. `src/main/java/com/example/returnadvice/ResultAspect.java`

```java
package com.example.returnadvice;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ResultAspect {
    private final AtomicInteger afterBoxCalls = new AtomicInteger();
    private final AtomicInteger afterTextCalls = new AtomicInteger();
    private final AtomicInteger aroundCalls = new AtomicInteger();

    @AfterReturning(
        pointcut = "execution(public com.example.returnadvice.ResultBox "
                 + "com.example.returnadvice.ReportService.loadPlain(..))",
        returning = "result",
        argNames = "result"
    )
    public void afterPlain(ResultBox result) {
        afterBoxCalls.incrementAndGet();

        // Mutation của chính object target đã trả về:
        result.setValue("observed:" + result.getValue());

        // Chỉ thay đổi local variable trong advice:
        result = new ResultBox("local-only");
        System.out.println("[AFTER box] local=" + result.getValue());
    }

    @AfterReturning(
        pointcut = "execution(public java.lang.String "
                 + "com.example.returnadvice.ReportService.message(..))",
        returning = "text",
        argNames = "text"
    )
    public void afterMessage(String text) {
        afterTextCalls.incrementAndGet();
        text = "rewritten:" + text;
        System.out.println("[AFTER text] local=" + text);
    }

    @Around(
        "execution(public com.example.returnadvice.ResultBox "
        + "com.example.returnadvice.ReportService.loadWrapped(..))"
    )
    public Object aroundWrapped(ProceedingJoinPoint pjp) throws Throwable {
        aroundCalls.incrementAndGet();

        ResultBox source = (ResultBox) pjp.proceed();
        ResultBox replacement = new ResultBox("replaced:" + source.getValue());
        System.out.println("[AROUND] new-reference");
        return replacement;
    }

    public int afterBoxCalls() {
        return afterBoxCalls.get();
    }

    public int afterTextCalls() {
        return afterTextCalls.get();
    }

    public int aroundCalls() {
        return aroundCalls.get();
    }
}
```

Các pointcuts được giới hạn theo **đúng một method** để tránh thứ tự của nhiều advices làm sai phép so sánh:

- `@AfterReturning` số một chỉ chọn `loadPlain`.
- `@AfterReturning` số hai chỉ chọn `message`.
- `@Around` chỉ chọn `loadWrapped`.

Vì chúng **không cùng match một method**, stdout trong demo không phụ thuộc vào thứ tự giữa `@Around` và `@AfterReturning` trên một lời gọi. `AtomicInteger` đo số lần từng advice được thực thi; `argNames` giúp Spring bind tên `result`/`text` một cách tường minh.

### 7.6. `src/main/java/com/example/returnadvice/AppConfig.java`

```java
package com.example.returnadvice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public ReportService reportService() {
        return new ReportService();
    }

    @Bean
    public ResultAspect resultAspect() {
        return new ResultAspect();
    }
}
```

`@EnableAspectJAutoProxy` bật hỗ trợ Spring `@AspectJ` proxy; `proxyTargetClass=true` dùng CGLIB cho `ReportService` không triển khai business interface. `@Aspect` đơn lẻ không đăng ký bean; `@Bean resultAspect()` làm việc đó.

### 7.7. `src/main/java/com/example/returnadvice/DemoApp.java`

```java
package com.example.returnadvice;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            ReportService service = context.getBean(ReportService.class);
            ResultAspect aspect = context.getBean(ResultAspect.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));

            ResultBox plain = service.loadPlain("A");
            System.out.println("plainCaller=" + plain.getValue());
            System.out.println("plainSameReference="
                    + (plain == service.rawPlainReference()));

            ResultBox wrapped = service.loadWrapped("B");
            System.out.println("wrappedCaller=" + wrapped.getValue());
            System.out.println("wrappedSource="
                    + service.rawWrappedReference().getValue());
            System.out.println("wrappedSameReference="
                    + (wrapped == service.rawWrappedReference()));

            String message = service.message("C");
            System.out.println("messageCaller=" + message);

            System.out.println("afterBoxCalls=" + aspect.afterBoxCalls());
            System.out.println("afterTextCalls=" + aspect.afterTextCalls());
            System.out.println("aroundCalls=" + aspect.aroundCalls());
        }
    }
}
```

Tất cả calls đều qua **Spring bean proxy** lấy từ `ApplicationContext`; demo không sử dụng `new ReportService()` bên ngoài Spring. Hai getter trên proxy không có advice nào match nên chỉ trả dữ liệu đang lưu trong raw target.

### 7.8. Chạy Maven và kết quả kỳ vọng

Trong thư mục chứa `pom.xml`, với JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.returnadvice.DemoApp
```

Các dòng được in bởi code ví dụ, theo thứ tự (không bao gồm thông báo Maven/SLF4J nếu có):

```text
isAopProxy=true
[TARGET plain] plain:A
[AFTER box] local=local-only
plainCaller=observed:plain:A
plainSameReference=true
[TARGET wrapped] source:B
[AROUND] new-reference
wrappedCaller=replaced:source:B
wrappedSource=source:B
wrappedSameReference=false
[AFTER text] local=rewritten:text:C
messageCaller=text:C
afterBoxCalls=1
afterTextCalls=1
aroundCalls=1
```

**Đọc kết quả theo từng kỹ thuật:**

1. `isAopProxy=true`: target service do Spring quản lý và đã được bọc bởi AOP proxy.
2. `[TARGET plain]` xảy ra trước `[AFTER box]` vì `@AfterReturning` chỉ thực thi sau khi `loadPlain` trả về bình thường.
3. `[AFTER box] local=local-only` chứng minh phép gán `result = new ResultBox(...)` đã thay local variable bên trong advice. Nhưng `plainCaller=observed:plain:A` chứng minh caller **không nhận object `local-only`**.
4. `plainSameReference=true`: caller nhận **cùng reference** mà target đã return; advice chỉ mutate `value` của object đó.
5. `wrappedSameReference=false`: `@Around` đã tạo và return **reference khác** với object `loadWrapped` gốc. `wrappedSource=source:B` cho thấy source object vẫn giữ state cũ.
6. `messageCaller=text:C`: gán lại biến `text` trong `@AfterReturning` không làm caller nhận `"rewritten:text:C"`.
7. Các counters bằng `1` vì mỗi advice chỉ khớp một trong ba lần gọi đã định.

Điểm học tập cốt lõi nằm ở **so sánh identity bằng `==`**, không chỉ nhìn chuỗi `getValue()`. Một object mutable có thể có nội dung thay đổi mà reference hoàn toàn không đổi.

*Ghi chú xác minh:* lệnh và stdout trên được thiết kế và rà soát theo các Spring API đã nêu; khi dùng trong project thực, nên chạy Maven trên JDK và Spring version mục tiêu để xác nhận môi trường, không suy từ ví dụ rằng các plugin/logging luôn phát sinh cùng thông báo phụ.

## 8. Những trường hợp không nên dùng `@AfterReturning` để “biến đổi kết quả”

### 8.1. Đổi DTO sang DTO khác

Ví dụ service trả `OrderDto`, nhưng muốn thêm một trường và trả một **new immutable DTO**:

```java
@AfterReturning(
    pointcut = "execution(* com.example..OrderService.get(..))",
    returning = "dto"
)
public void after(OrderDto dto) {
    dto = new OrderDto(dto.id(), "audited");
}
```

Đây là **anti-pattern fragment**; `OrderDto` phải được định nghĩa trong ứng dụng. `dto = new ...` chỉ đổi local parameter của advice, không thay object caller nhận. Nếu `OrderDto` là immutable record, cách đúng thường là **service/mapper tạo DTO cần trả**, hoặc `@Around` thực sự `return new OrderDto(...)`.

### 8.2. Mask dữ liệu nhạy cảm

Dùng `@AfterReturning` rồi mutate object đang trả về để che dữ liệu có thể gây tác động phụ nếu object đó còn được giữ trong cache, persistence context hoặc một reference khác. Hướng an toàn hơn thường là tạo **response DTO mới** và return từ một tầng mapping minh bạch; nếu transformation phải là cross-cutting concern, `@Around` có thể phù hợp nhưng cần giới hạn pointcut và kiểm thử bảo mật.

Không coi `@AfterReturning` là cơ chế sanitizer tự động của mọi response: Spring AOP chỉ chặn method đi qua proxy, không tự chặn mọi trường hợp self-invocation hoặc object được tạo ngoài container.

### 8.3. Wrap collection hoặc thay immutable value

- `Collections.unmodifiableList(source)` tạo một **wrapper reference khác** (không nên cố `list = wrapper` trong `@AfterReturning`).
- `List.copyOf(source)` tạo một giá trị collection thích hợp theo contract, không nên giả định nó luôn là cùng reference.
- `String`, `BigDecimal`, Java record bất biến: phải tạo/return giá trị mới nếu muốn thay nội dung.
- Nếu object mutable, mutation trong `@AfterReturning` còn có thể tạo race conditions, lỗi cache hoặc dirty tracking ngoài ý định.

Nếu biến đổi return value là chức năng chính, `@Around` hoặc explicit mapper là sự lựa chọn có hợp đồng rõ hơn.

## 9. `@AfterReturning` có phù hợp với metrics, audit và validation không?

Rất phù hợp khi chỉ cần **quan sát sự kiện thành công**.

| Mục đích | `@AfterReturning` phù hợp? | Ghi chú |
| --- | --- | --- |
| Đếm số lần method trả về bình thường | Có | Advice chạy sau normal return, không bao gồm target ném exception. |
| Ghi event audit về type/ID của kết quả | Có | Cẩn thận thông tin nhạy cảm và `toString()` gây side effects. |
| Ghi metric giá trị trả về | Có | Dùng metadata cần thiết, không mutate object nếu không có yêu cầu. |
| Kiểm tra invariant và log cảnh báo | Có | Việc ném exception từ advice có thể làm caller không nhận normal return; phải là quyết định thiết kế. |
| Thêm một field vào object mutable tại chỗ | Về kỹ thuật có thể | Là state mutation, không phải đổi reference; cân nhắc side effects và concurrency. |
| Thay `ResultBox` bằng object mới | Không | Dùng `@Around` hoặc đổi logic target. |
| Thay `String` return bằng chuỗi khác | Không | `String` immutable; gán lại local không thay return. |
| Trả kết quả từ cache mà không chạy target | Không | `@Around` có thể quyết định không `proceed()`. |
| Can thiệp vào exception của target | Không phải vai trò chính | Dùng `@AfterThrowing` cho quan sát lỗi, `@Around` nếu phải chuyển hóa theo policy. |

Một quy tắc thực dụng của Spring: **chọn loại advice ít quyền nhất đủ đáp ứng nhu cầu**. Nếu chỉ cần kiểm tra kết quả để ghi log, `@AfterReturning` dễ đọc và ít làm thay đổi luồng điều khiển hơn `@Around`. Chỉ nâng lên `@Around` khi thực sự cần thay output, skip/retry method hoặc quản lý hành vi quanh invocation.

## 10. Các trường hợp biên dễ khiến kết luận sai

### 10.1. Method ném exception

`@AfterReturning` không chạy sau khi target method kết thúc bằng exception. Nếu một `@Around` nội bộ bắt exception và trả fallback value, advice `@AfterReturning` ở vị trí thích hợp trong interceptor chain có thể nhìn thấy **normal return từ phần chain phía trong**. Vì vậy nếu có nhiều advisors lồng nhau, cần test trên **chain thực tế**, không chỉ trên một method đơn lẻ.

`@AfterThrowing` dùng để quan sát exception được ném từ join point theo hợp đồng Spring, nhưng nó cũng **không phải** một cơ chế trực tiếp return replacement value. Muốn chuyển exception thành fallback value cho caller, thường cần `@Around` hoặc xử lý explicit ở application boundary.

### 10.2. `void`, primitive và `null`

- Advice `@AfterReturning("execution(* ..SomeService.doWork(..))")` không bind result vẫn có thể phù hợp cho một `void` method hoàn thành bình thường.
- Khi có `returning="result"` và tham số `ResultBox result`, runtime type filter của binding cần được xem xét; method `void` và các giá trị không tương thích sẽ không hành xử như method return `ResultBox`.
- Với `null`, cần test behavior trên Spring version thật và tuyệt đối không gọi `result.getValue()` khi chưa bảo đảm `result` khác null.
- Primitive methods thường liên quan boxing/unboxing tại interceptor boundary; advice với tham số primitive/wrapper cần được kiểm tra trong integration test.
- Nếu `@Around` thay giá trị, hãy trả về kiểu hợp lệ cho declared method signature, đặc biệt tránh `null` cho primitive return.

Đừng dùng `Object` hoặc `ResultBox` trong một advice chung rồi ngầm coi nó là mọi trường hợp `void`, `null`, primitive và generic cùng lúc.

### 10.3. Reactive hoặc asynchronous return types

Với `CompletionStage<T>`/`CompletableFuture<T>` hay `Mono<T>`/`Flux<T>`, target method thường **trả về wrapper/handle** trước khi kết quả bất đồng bộ thực sự hoàn tất hoặc publisher được subscribe. `@AfterReturning` của Spring proxy AOP gắn với **normal return của Java method**, không tự trở thành callback “sau khi HTTP response hoàn tất” hoặc “sau khi future hoàn thành”.

Do đó:

- `@AfterReturning(returning="future")` có thể nhận **`CompletableFuture`**, không phải giá trị `T` sẽ được tính về sau.
- `@AfterReturning` không tự xử lý lỗi phát sinh trong quá trình future hoàn thành hoặc reactive stream phát tín hiệu.
- Muốn transform giá trị bất đồng bộ cần dùng đúng API `thenApply`, Reactor `map`/`onErrorResume`... ở tầng thích hợp; hoặc dùng `@Around` nếu chủ đích phải thay wrapper/reference trả cho caller.
- Phải kiểm tra riêng transaction/security/tracing semantics nếu ứng dụng sử dụng các subsystem Spring có tích hợp async/reactive đặc biệt.

Đây là ranh giới giữa **Java method return** và **asynchronous completion**, không phải một lỗi riêng của biểu thức `returning`.

### 10.4. `@AfterReturning` và `@Around` cùng match một method

Một `@Around` có thể thay return reference. Nếu cả `@AfterReturning` cũng match, **return value mà nó nhìn thấy tùy vào vị trí tương đối của advice trong chain**, không phải luôn luôn object gốc cuối cùng hoặc luôn object thay thế. Dùng `@Order`/Advisor ordering khi cần, đồng thời integration-test thứ tự thật, vì thứ tự của nhiều advices trong cùng aspect có quy tắc riêng.

Không đặt hai transformations cùng trách nhiệm trong nhiều aspects rồi hy vọng chúng áp dụng theo “source order”. Khi mục đích chính là return replacement, nên xác định **một nơi sở hữu transformation policy** để tránh wrap hai lần.

### 10.5. Self-invocation hoặc gọi raw object

```java
public class ReportService {
    public ResultBox outer() {
        return loadPlain("internal");
    }

    public ResultBox loadPlain(String id) {
        return new ResultBox(id);
    }
}
```

Đây là fragment minh họa. Nếu caller gọi `proxy.outer()`, nhưng target tự gọi `this.loadPlain()`, lời gọi nội bộ không đi qua proxy và `@AfterReturning` nhắm `loadPlain` không chạy nhờ interception thông thường. Đổi `@AfterReturning` thành `@Around` **không sửa được self-invocation**; cần đặt đường gọi qua Spring proxy phù hợp hoặc thiết kế lại bean boundary.

## 11. Kiểm thử đúng điều cần chứng minh

Khi xây dựng tests cho return-value advice trong Spring AOP, phải phân biệt:

1. **Có Spring proxy không?** Xác minh `AopUtils.isAopProxy(service)` và context/bean registration.
2. **Pointcut có khớp đúng method không?** Có thể có proxy do advisors khác nhưng advice này không chạy.
3. **Advice được gọi khi nào?** Dùng counter/event để phân biệt normal return với exception exit.
4. **Return reference có đổi không?** Sử dụng `==` trên hai references thích hợp, không dùng chỉ `equals`.
5. **State có đổi không?** Kiểm tra fields/properties của **chính object đã trả về** sau khi advice chạy.
6. **Caller nhìn thấy gì?** Assert trực tiếp return value tại call site, không chỉ log `result` trong advice.
7. **`@Around` có trả đúng type/exception không?** Test primitive, `null`, và các method có overload nếu cần.
8. **Ảnh hưởng side effects:** mutate object có làm đổi cached/shared instance hay entity được quản lý không?
9. **Thread safety:** aspect singleton và target singleton có thể được gọi đồng thời; không lưu per-call state vào mutable instance fields nếu không có cơ chế phù hợp.
10. **Boundary:** test cross-bean invocation qua Spring proxy, không dùng `new` target để kỳ vọng Aspect chạy.

Ví dụ assertions cho demo:

```java
ResultBox plain = service.loadPlain("A");
assert plain == service.rawPlainReference();
assert "observed:plain:A".equals(plain.getValue());

ResultBox wrapped = service.loadWrapped("B");
assert wrapped != service.rawWrappedReference();
assert "replaced:source:B".equals(wrapped.getValue());

String text = service.message("C");
assert "text:C".equals(text);
```

Đây là **test fragment**, giả định có biến `service` là Spring proxy, và Java assertions được enable khi chạy (ví dụ `-ea`). Nếu dùng JUnit, nên dùng `assertSame`/`assertNotSame` để kiểm tra identity và `assertEquals` cho state/value.

Quan trọng: `equals()` có thể được custom override; `assertEquals` không chứng minh return reference giữ nguyên. Khi yêu cầu là thay hay không thay **đối tượng trả về**, phép kiểm identity là bắt buộc.

## 12. Các lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Trong advice thấy `result = new Dto(...)` nhưng caller vẫn nhận Dto cũ | Gán lại local parameter trong `@AfterReturning` | Dùng `@Around` return reference mới hoặc tạo DTO ở service/mapper. |
| Advice sửa được field và tưởng đã thay object | State mutation của mutable instance | So `==`, kiểm tra cả reference và state; tránh mutate không chủ đích. |
| `@AfterReturning` không chạy khi target ném lỗi | Nó chỉ chạy khi normal return | Dùng `@AfterThrowing` cho quan sát lỗi hoặc `@Around` khi phải thay exception behavior. |
| Binding `returning="dto"` không resolve | Advice không có parameter `dto`, hoặc `argNames`/metadata sai | Đồng bộ tên binding với parameter advice và kiểm tra signature. |
| Advice dùng `ResultBox` không chạy với method trả kiểu khác | Typed return binding hạn chế matching | Chọn đúng type hoặc `Object` nếu thực sự cần một điểm chặn rộng. |
| `@Around` trả object không đúng kiểu khai báo | Method signature/return contract bị vi phạm | Return object compatible; integration-test callers và exceptions. |
| `@Around` quên gọi `proceed()` và nghiệp vụ không chạy | Advice đã thay luồng điều khiển | Gọi `proceed()` khi transformation cần result gốc; skip chỉ khi được thiết kế rõ. |
| Advice sửa cache/entity/list ngoài dự kiến | Mutable return object đang được chia sẻ | Chọn mapping/immutable return hoặc defensive copy và `@Around`. |
| Cùng method nhưng advice lúc chạy lúc không | Caller đi qua proxy khác nhau, hoặc pointcut/binding type khác | Kiểm tra Spring context, `AopUtils`, pointcut và invocation path. |
| `@AfterReturning` chạy khi method trả future nhưng chưa có dữ liệu | Return của Java method khác completion của future | Dùng async/reactive operators tại đúng tầng; không chờ `@AfterReturning` tự xử lý hoàn tất. |
| Lỗi sau khi thêm cả `@Around` và `@AfterReturning` | Advice ordering/return type mismatch | Giới hạn trách nhiệm, kiểm thử chain và dùng ordering rõ ràng. |
| Muốn thay `String` bằng gán lại tham số advice | `String` immutable và binding local | Dùng `@Around` hoặc đổi logic target để return `String` mới. |

## 13. Chọn giải pháp theo yêu cầu thực tế

**Chỉ muốn biết target đã hoàn thành và trả gì?** Dùng `@AfterReturning` để đo/ghi log/audit, kết hợp typed `returning` khi cần. Giữ advice không có side effects trên return object nếu có thể.

**Chỉ cần xác thực return value, không thay nó?** `@AfterReturning` có thể đọc rồi ghi cảnh báo. Nếu policy thực sự muốn ném lỗi khi vi phạm invariant, cần nêu rõ đây là hành vi làm caller thất bại sau khi method đã chạy; tránh dùng cho silent normalization.

**Muốn trả một immutable DTO/wrapper khác?** Ưu tiên mapping rõ ràng tại tầng service/adapter. Nếu là chính sách ngang nhiều beans và phải can thiệp tại proxy boundary, dùng `@Around` để return object khác có kiểu tương thích.

**Muốn sửa dữ liệu ngay trong mutable object?** Về kỹ thuật `@AfterReturning` có thể làm, nhưng cần quyết định về shared state, persistence dirty tracking, cache consistency, concurrency, ownership và tests. Đây không phải phương án an toàn mặc định chỉ vì code ít hơn `@Around`.

**Muốn thay giá trị một `CompletionStage` hoặc `Mono` khi xử lý xong?** Dùng operator trên asynchronous/reactive API, hoặc `@Around` trả một wrapper đã transform; không nhầm normal return của Java method với completion event.

### Tài liệu tham khảo Spring

- Spring Framework — Declaring Advice (After Returning, Around): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — Advice API and AfterReturningAdvice: https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html
- Spring Framework — AspectJAfterReturningAdvice Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/aspectj/AspectJAfterReturningAdvice.html

**Kết luận:** `@AfterReturning` được thiết kế để **quan sát một lần return thành công**, không phải thay reference trả về. Mutate object mutable chỉ đổi **trạng thái của reference cũ**, còn gán `result = new ...` trong advice không đến được caller. Để thực sự **thay object caller nhận**, chọn `@Around` với `return replacement` và kiểm thử cả type, identity, state và Spring proxy boundary.
