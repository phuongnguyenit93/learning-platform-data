# Ràng buộc đối số bằng `args` và tham số advice trong Spring AOP

## 1. Mục tiêu: đưa giá trị đối số của lời gọi Spring bean vào advice có kiểu rõ ràng

Khi viết một Spring `@Aspect`, nhiều lời advice cần biết **giá trị nào caller thực sự truyền vào method đích**. Ví dụ một advice audit muốn lấy `accountId` và `channel` mà không phải tự duyệt `Object[]`, ép kiểu bằng tay rồi đoán vị trí phần tử.

Spring AOP hỗ trợ **argument binding** bằng `args(...)` trong AspectJ-style pointcut expression. Khi dùng **tên của một formal parameter** thay vì tên kiểu Java trong `args`, Spring có thể **truyền giá trị argument được chọn vào tham số của advice**.

```java
@Before(
    value = "execution(* com.example.payment.PaymentService.pay(..))"
          + " && args(accountId, amount)",
    argNames = "accountId,amount"
)
public void beforePay(String accountId, java.math.BigDecimal amount) {
    System.out.println("accountId=" + accountId);
    System.out.println("amount=" + amount);
}
```

Đây là **method fragment** trong một class `@Aspect` được Spring quản lý, không phải chương trình Java độc lập. Giả định `PaymentService.pay(String, BigDecimal)` là method được caller gọi **qua Spring AOP proxy**.

Các thành phần có trách nhiệm riêng:

- `execution(...PaymentService.pay(..))`: giới hạn join point vào method nghiệp vụ mong muốn.
- `args(accountId, amount)`: lấy **hai arguments thực tế theo thứ tự** và đưa chúng vào những biến được đặt tên trong pointcut expression.
- `String accountId` và `BigDecimal amount`: kiểu Java Spring/AspectJ dùng để bind và kiểm tra tương thích.
- `argNames="accountId,amount"`: ánh xạ chính xác tên xuất hiện trong expression với formal parameters của method advice.
- Body `beforePay`: logic audit thực sự, **không** nằm trong expression.

**Phạm vi:** Bài tập trung vào Spring Aspect, `@AspectJ` annotation-style và **Spring proxy-based AOP**. Các khái niệm AspectJ ngoài Spring chỉ được nêu để tránh nhầm API, không mở rộng sang compile-time/load-time weaving.

## 2. `args` có hai cách sử dụng: type pattern và binding

Điểm dễ nhầm nhất là biểu thức `args(...)` **không phải lúc nào cũng có cùng ý nghĩa**.

### 2.1. Dùng kiểu Java để chọn invocation

```text
args(java.io.Serializable)
```

Đây là **type pattern**: nó chọn lời gọi có **đúng một argument** có kiểu runtime phù hợp với `Serializable`, trong phạm vi Spring proxy join points.

Ví dụ target method khai báo:

```java
public String send(Object payload) { /* ... */ }
```

Nếu truyền `"hello"`, argument runtime là `String` và implements `Serializable`. Nếu truyền `new PlainPayload()` không implements interface đó, điều kiện khác đi dù chữ ký `send(Object)` vẫn y nguyên.

### 2.2. Dùng tên parameter để bind giá trị

```text
args(payload)
```

Nếu `payload` được khai báo trong signature của named pointcut hoặc method advice, nó là **binding identifier**. Ví dụ:

```java
@Before(
    value = "execution(* com.example.msg.MessageService.send(..))"
          + " && args(payload)",
    argNames = "payload"
)
public void inspect(java.io.Serializable payload) {
    System.out.println(payload.getClass().getSimpleName());
}
```

Khi runtime argument phù hợp `Serializable`, `payload` nhận **chính argument đang được truyền**, không phải một `Serializable` instance Spring tự tạo.

**Điểm so sánh:**

| Cú pháp | Ý nghĩa | Có bind giá trị vào advice parameter không? |
| --- | --- | --- |
| `args(java.io.Serializable)` | Runtime type filter | Không, vì đây là tên kiểu đầy đủ |
| `args(payload)` với `Serializable payload` | Runtime type filter **và** binding | Có, lấy object tương ứng |
| `args(payload, channel)` | Bind hai arguments theo vị trí | Có nếu signature/kiểu tương thích |
| `args(payload, ..)` | Bind argument đầu, cho phép phần còn lại | Có |
| `args(.., channel)` | Bind argument cuối, cho phép phần trước | Có |
| `execution(* *.send(java.io.Serializable))` | Lọc kiểu tham số **khai báo trong method signature** | Không tự bind argument |

Spring docs nhấn mạnh `args(java.io.Serializable)` khác `execution(* *(java.io.Serializable))`: `args` có thể dựa trên **đối số thực tế tại runtime**, còn `execution` xét **chữ ký phương thức khai báo**. Đây là điểm cần kiểm tra trước khi sửa một pointcut đang “không chạy”.

## 3. Tên binding phải khớp nhau ở ba nơi

Một advice binding đầy đủ có ba chỗ cần thống nhất:

```java
@Before(
    value = "execution(* com.example.order.OrderService.create(..))"
          + " && args(request, source)",
    argNames = "request,source"
)
public void before(OrderRequest request, String source) {
    // ...
}
```

| Vị trí | Ký hiệu | Tác dụng |
| --- | --- | --- |
| Pointcut string | `args(request, source)` | Tham chiếu các tên binding từ invocation |
| Advice annotation | `argNames="request,source"` | Cung cấp ánh xạ tên tham số tường minh |
| Advice Java method | `OrderRequest request, String source` | Kiểu và tham số thực sự nhận giá trị |

Đây là **fragment**: `OrderRequest` là lớp cần tồn tại trong project. Đặt tên `request` trên cả ba vị trí giúp người đọc không phải suy diễn bằng reflection.

Ví dụ đổi tên **chỉ** trong Java:

```java
@Before(
    value = "execution(* com.example.order.OrderService.create(..))"
          + " && args(request, source)",
    argNames = "request,source"
)
public void before(OrderRequest payload, String channel) {}
```

Java vẫn có thể biên dịch vì annotation là chuỗi. Nhưng `argNames` khai báo tên binding khác tên source parameters; một số cấu hình vẫn bind được theo **thứ tự danh sách tường minh**, nhưng điều này dễ gây nhầm khi refactor. Cách an toàn là **đồng bộ tên ở cả ba nơi** và chạy context test. Đặc biệt nếu xóa `argNames`, việc Spring tìm parameter names từ build metadata có thể thay đổi kết quả.

Nếu sai **số lượng**, **thứ tự binding**, **type** hoặc identifier không thể resolve, Spring thường báo lỗi khi tạo advisor/khởi động context hoặc advice không áp dụng như mong muốn. Không được coi annotation expression string là được Java compiler type-check đầy đủ.

## 4. `argNames`, `-parameters` và cơ chế tìm tên argument

`args(payload)` trong pointcut dùng **tên binding** `payload`, không phải tên parameter của target method. Spring phải nối tên này với đúng tham số của lời advice. Cách dễ kiểm soát nhất là khai báo `argNames = "payload"`; Java `-parameters` là nguồn metadata khác cho Spring tìm tên tham số khi không khai báo tường minh. Nếu còn nhiều biến hoặc annotation/return bindings, việc để Spring suy luận có thể mơ hồ.

### 4.1. Trường hợp có `JoinPoint` đầu tiên

Tham số đầu tiên đặc biệt `JoinPoint`, `ProceedingJoinPoint` (cho `@Around`) hoặc `JoinPoint.StaticPart` có thể **bỏ tên khỏi `argNames`**. Ví dụ:

```java
@Before(value = "execution(* com.example.payment.PaymentService.pay(..))"
        + " && args(accountId, amount)",
        argNames = "accountId,amount")
public void audit(JoinPoint jp, String accountId, BigDecimal amount) {
    System.out.println(jp.getSignature().getName() + ": " + accountId);
}
```

Đây là đoạn minh họa nằm trong Spring-managed `@Aspect`, cần imports `JoinPoint`, `BigDecimal` và `@Before`; `jp` do Spring cấp, hai tham số còn lại đến từ binding. Khi không bind biến nào khác, lời advice chỉ nhận `JoinPoint` không cần `argNames`. `getArgs()` đọc mảng giá trị theo vị trí; `args(name)` ràng buộc giá trị có kiểu và tham gia điều kiện match. Bài **argNames, tên tham số và `-parameters`** ở chương này đi sâu vào cấu hình Maven/Gradle và thứ tự phát hiện tên.

## 5. `args` dựa trên vị trí: một, hai hoặc nhiều tham số

Giả sử target method:

```java
public Receipt charge(String accountId, BigDecimal amount, String channel);
```

Mỗi biểu thức dưới đây có ý nghĩa khác nhau:

```text
args(accountId, amount, channel)
args(accountId, ..)
args(.., channel)
args(accountId, *, channel)
args(java.lang.String, java.math.BigDecimal, java.lang.String)
```

- `args(accountId, amount, channel)`: bind đủ **ba vị trí**, signature của named pointcut/advice cũng phải tương ứng.
- `args(accountId, ..)`: bind **tham số đầu**; phía sau có thể là không hoặc nhiều arguments.
- `args(.., channel)`: bind **tham số cuối**; phần trước có thể nhiều vị trí.
- `args(accountId, *, channel)`: bind vị trí đầu và cuối, giữa là **một** argument bất kỳ. Nếu dùng pattern có wildcard và binding phức tạp, chạy context test để bảo đảm parser/type matching tương thích.
- `args(String, BigDecimal, String)`: chỉ kiểm tra kiểu theo vị trí, **không tạo named bindings**.

Ví dụ chỉ quan tâm `accountId` đầu tiên dù method có thêm parameters:

```java
@Before(
    value = "execution(* com.example.billing.BillingService.charge(..))"
          + " && args(accountId, ..)",
    argNames = "accountId"
)
public void beforeCharge(String accountId) {
    // ...
}
```

Đây là method fragment hợp lệ về ý tưởng: `accountId` bind vào argument đầu, không yêu cầu advice khai báo các parameters còn lại.

**Không nhầm vị trí với tên tham số method đích.** Caller không truyền “argument tên `accountId`”; JVM truyền một **dãy values có thứ tự**. Tên `accountId` trong pointcut chỉ là **tên binding** mà advice tác giả đặt. Đổi tên tham số `id` trong target Java không tự khiến `args(accountId,..)` sai nếu vị trí và kiểu vẫn hợp lệ.

### 5.1. Overloads

Với hai overload:

```java
void submit(Object payload);
void submit(String payload);
```

Java compiler quyết định overload dựa trên **kiểu biểu thức ở call site**, trước khi Spring AOP áp dụng pointcut. Sau đó `args(payload)` quan sát **runtime argument** của method execution đã được chọn.

Nếu code viết `Object value = "hello"; service.submit(value);`, Java gọi overload `submit(Object)` dù `value` trỏ tới `String`. Advice `args(payload)` với `String payload` có thể vẫn bind được runtime `String` khi method execution đi qua proxy phù hợp. Nó không làm method đang được gọi chuyển thành overload `submit(String)`.

## 6. Ràng buộc đối số cùng với named `@Pointcut`

Khi nhiều advice cần cùng điều kiện chọn method và cùng formal argument types, tạo named pointcut:

```java
@Pointcut(
    value = "execution(* com.example.order.OrderService.place(..))"
          + " && args(orderId, channel)",
    argNames = "orderId,channel"
)
public void orderPlaced(String orderId, String channel) {}
```

Rồi tham chiếu lại:

```java
@Before(
    value = "orderPlaced(orderId,channel)",
    argNames = "orderId,channel"
)
public void beforeOrder(String orderId, String channel) {
    // ...
}
```

```java
@AfterReturning(
    pointcut = "orderPlaced(orderId,channel)",
    returning = "receipt",
    argNames = "orderId,channel,receipt"
)
public void afterOrder(
        String orderId, String channel, Receipt receipt) {
    // ...
}
```

Đây là các **fragments** của một class `@Aspect`; `Receipt` và `OrderService.place(..)` phải có thật trong project. Named pointcut có formal parameters nhưng **body của `orderPlaced(...)` rỗng**: Spring không gọi Java body này để lấy arguments. Nó là khai báo metadata về cách bind values.

Chú ý `returning="receipt"` bind **return value** của method, trong khi `args(orderId,channel)` bind **input arguments**. Không dùng cùng một identifier cho hai đối tượng có ý nghĩa khác nhau.

### 6.1. Binding names ở nhiều tầng

Khi pointcut trong class chung:

```java
@Pointcut(
    value = "execution(* com.example.order.OrderService.place(..))"
          + " && args(orderId, channel)",
    argNames = "orderId,channel"
)
public void placed(String orderId, String channel) {}
```

Aspect khác có thể dùng:

```java
@Before(
    value = "com.example.aop.CommonPointcuts.placed(orderId,channel)",
    argNames = "orderId,channel"
)
public void audit(String orderId, String channel) {}
```

**Fully-qualified class + method reference** giúp Spring tìm named pointcut bên ngoài class. Method trong `CommonPointcuts` cần Java visibility phù hợp (thường `public`). Không cần khởi tạo `CommonPointcuts` thành bean chỉ vì nó chứa public named pointcuts được tham chiếu bằng tên; còn class `@Aspect` chứa advice phải là Spring bean.

## 7. Binding ở các loại advice khác nhau

`args` không chỉ dùng cho `@Before`. Trong Spring, advice methods có thể nhận values từ pointcut bindings, với điều kiện lựa chọn đúng signature/annotation:

| Advice | Dùng `args` để nhận input? | Binding bổ sung | Điều đáng lưu ý |
| --- | --- | --- | --- |
| `@Before` | Có | Có thể nhận `JoinPoint` đầu tiên | Không thay argument caller chỉ bằng gán lại parameter local. |
| `@After` | Có | Có thể nhận `JoinPoint` | Chạy theo semantics của after (finally), không phải chỉ sau thành công. |
| `@AfterReturning` | Có | `returning="result"` | `result` là return value; gán lại advice parameter không thay value caller nhận. |
| `@AfterThrowing` | Có | `throwing="error"` | Binding exception; chỉ chạy khi lời gọi kết thúc bằng lỗi phù hợp. |
| `@Around` | Có | `ProceedingJoinPoint` là tham số đầu tiên | Có thể `proceed()` hoặc `proceed(Object[])`; advice quyết định có và khi nào chuyển tiếp. |

Ví dụ kết hợp args với return result:

```java
@AfterReturning(
    pointcut = "execution(* com.example.order.OrderService.place(..))"
             + " && args(orderId, ..)",
    returning = "result",
    argNames = "orderId,result"
)
public void afterPlace(String orderId, String result) {
    // orderId: input từ lời gọi, result: giá trị trả về bình thường.
}
```

Ví dụ kết hợp args với exception:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.order.OrderService.place(..))"
             + " && args(orderId, ..)",
    throwing = "error",
    argNames = "orderId,error"
)
public void onFailure(String orderId, RuntimeException error) {
    // ...
}
```

Cả hai là **fragments**. Trong ứng dụng thật, return type, exception type và signature của `place` phải tương thích. `@AfterThrowing` không có nhiệm vụ tự “nuốt lỗi”; nếu cần fallback result cho caller, cân nhắc `@Around` với contract rõ.

### 7.1. `@Around` và `ProceedingJoinPoint` đi cùng binding

```java
@Around(
    value = "execution(* com.example.order.OrderService.place(..))"
          + " && args(orderId, channel)",
    argNames = "orderId,channel"
)
public Object around(
        org.aspectj.lang.ProceedingJoinPoint pjp,
        String orderId,
        String channel) throws Throwable {

    System.out.println("channel=" + channel);
    return pjp.proceed();
}
```

`ProceedingJoinPoint` đứng đầu, **không cần nằm trong danh sách `argNames`**. Hai Java parameters còn lại được bind từ arguments đang được truyền qua proxy.

Nếu muốn **thực sự đổi arguments chuyển cho target**, cần `proceed(newArgs)` với array đúng số lượng/kiểu của underlying method. Ví dụ trong Spring AOP:

```java
Object[] newArgs = pjp.getArgs().clone();
newArgs[1] = "normalized-channel";
Object outcome = pjp.proceed(newArgs);
return outcome;
```

Chỉ dùng khi underlying method **thực sự có tham số thứ hai kiểu tương thích với `String`**. Gán `channel = "..." ` trong advice chỉ sửa **biến cục bộ**; nó không thay argument của invocation đang được proceed như `proceed(newArgs)`.

Spring docs nêu `proceed(Object[])` ở Spring proxy AOP sử dụng array phù hợp với **arguments của underlying method**, có khác biệt cần phân biệt với AspectJ weaving thuần. Không dùng để âm thầm thay sensitive inputs mà không có policy rõ ràng.

## 8. Ví dụ đầy đủ Java 17+: bind input, nhận `JoinPoint`, bind cả return value

Ví dụ tập trung vào ba mục tiêu:

1. Target có `send(Object payload, String channel)`. Method signature cố định `Object` nhưng runtime payload có thể khác kiểu.
2. Named pointcut `serializableMessages(...)` bind một `Serializable payload` và một `String channel`.
3. `@Before` nhận `JoinPoint` đầu tiên + input bindings; `@AfterReturning` nhận input bindings + `String result`.
4. Gọi cùng method ba lần với `String`, một record không implements `Serializable`, và `Integer`.
5. Chỉ hai lần có Serializable payload kích hoạt cả hai advice. Cả ba lần target vẫn chạy và caller đều nhận result.

Dự án dùng **Java 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1, Maven**, không bật AspectJ weaving. Các version được cố định để minh họa chứ không khẳng định là mới nhất.

### 8.1. Cấu trúc thư mục

```text
spring-aop-args-binding/
├── pom.xml
└── src/main/java/com/example/binding/
    ├── MessageService.java
    ├── BindingAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-args-binding</artifactId>
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
                <configuration>
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
```

`spring-context` cung cấp `ApplicationContext` và các Spring AOP dependencies phù hợp trong cây phụ thuộc; `aspectjweaver` cho phép Spring parse/match `@AspectJ` expressions. `parameters=true` giữ parameter-name metadata theo yêu cầu khi cần; ví dụ cũng đặt `argNames` tường minh để không phụ thuộc riêng việc tự suy luận.

### 8.3. `src/main/java/com/example/binding/MessageService.java`

```java
package com.example.binding;

public class MessageService {

    public String send(Object payload, String channel) {
        String typeName = payload.getClass().getSimpleName();
        System.out.println("[TARGET] channel=" + channel
                + ", type=" + typeName);

        return "sent:" + channel + ":" + typeName;
    }
}
```

Method cố ý khai báo parameter đầu là `Object`, nhưng gọi với `String`, `Integer` và một record không implements `Serializable`. Trong project demo, `payload` luôn non-null để output xác định; nếu production API cho phép null, cần kiểm tra trước `getClass()`.

### 8.4. `src/main/java/com/example/binding/BindingAspect.java`

```java
package com.example.binding;

import java.io.Serializable;
import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class BindingAspect {

    private final AtomicInteger beforeCount = new AtomicInteger();
    private final AtomicInteger afterCount = new AtomicInteger();

    @Pointcut(
        value = "execution(public java.lang.String "
              + "com.example.binding.MessageService.send(..))"
              + " && args(payload,channel)",
        argNames = "payload,channel"
    )
    public void serializableMessages(
            Serializable payload, String channel) {}

    @Before(
        value = "serializableMessages(payload,channel)",
        argNames = "payload,channel"
    )
    public void before(
            JoinPoint jp,
            Serializable payload,
            String channel) {

        beforeCount.incrementAndGet();
        System.out.println("[BEFORE] method="
                + jp.getSignature().getName()
                + ", channel=" + channel
                + ", type=" + payload.getClass().getSimpleName());
    }

    @AfterReturning(
        pointcut = "serializableMessages(payload,channel)",
        returning = "result",
        argNames = "payload,channel,result"
    )
    public void after(
            Serializable payload,
            String channel,
            String result) {

        afterCount.incrementAndGet();
        System.out.println("[AFTER] type="
                + payload.getClass().getSimpleName()
                + ", result=" + result);
    }

    public int beforeCount() {
        return beforeCount.get();
    }

    public int afterCount() {
        return afterCount.get();
    }
}
```

Phân tích cụ thể:

- Named pointcut nhận **hai formal parameters**: `Serializable payload`, `String channel`.
- `args(payload,channel)` giới hạn đúng **hai arguments** trong `send(Object,String)` và bind theo vị trí.
- `Serializable payload` khiến điều kiện **dynamic runtime type** của payload quan trọng: `String` và `Integer` phù hợp; `PlainPayload` trong main không phù hợp.
- `@Before` có `JoinPoint` đầu tiên. `argNames` **chỉ liệt kê** `payload,channel`, đúng khả năng đặc biệt của Spring.
- `@AfterReturning` tham chiếu cùng named pointcut nhưng còn bind `result` qua `returning="result"`.
- `String result` là return value do target tạo khi method kết thúc bình thường; việc nhận thêm input arguments không thay đổi giá trị trả về.
- Hai counters giúp phân biệt việc advice thật sự chạy với việc Spring chỉ có một aspect bean singleton.

Ví dụ không dùng `payload.toString()` để tránh log dữ liệu message thực tế; chỉ in **kiểu payload**, channel và string result vốn được tạo có chủ đích. Với ứng dụng production, cần kiểm tra cả channel/result có chứa thông tin nhạy cảm không.

### 8.5. `src/main/java/com/example/binding/AppConfig.java`

```java
package com.example.binding;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public MessageService messageService() {
        return new MessageService();
    }

    @Bean
    public BindingAspect bindingAspect() {
        return new BindingAspect();
    }
}
```

`@EnableAspectJAutoProxy` kích hoạt hạ tầng Spring auto-proxy. `proxyTargetClass=true` chọn CGLIB class proxy vì `MessageService` không implement business interface. `BindingAspect` phải được đăng ký thành bean — `@Aspect` riêng lẻ **không phải** `@Component`.

### 8.6. `src/main/java/com/example/binding/DemoApp.java`

```java
package com.example.binding;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public record PlainPayload(String label) {
        // Java record không tự implements Serializable.
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            MessageService service = context.getBean(MessageService.class);
            BindingAspect aspect = context.getBean(BindingAspect.class);

            System.out.println("isAopProxy="
                    + AopUtils.isAopProxy(service));

            System.out.println("result1="
                    + service.send("hello", "web"));

            System.out.println("result2="
                    + service.send(new PlainPayload("plain"), "queue"));

            System.out.println("result3="
                    + service.send(Integer.valueOf(7), "batch"));

            System.out.println("beforeCount=" + aspect.beforeCount());
            System.out.println("afterCount=" + aspect.afterCount());
        }
    }
}
```

`PlainPayload` là `record` trong `DemoApp` nhưng **không** implement `Serializable`. `String` và `Integer` implement `Serializable` trên JDK 17+; vì thế hai lời gọi đầu/cuối tạo những kết quả match khác nhau từ **cùng một method và cùng một Spring proxy**.

### 8.7. Chạy và stdout dự kiến

Trong thư mục chứa `pom.xml`, với Maven và JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.binding.DemoApp
```

Những dòng do code chương trình và aspect in ra, theo đúng thứ tự (không tính thông báo Maven/SLF4J tùy môi trường):

```text
isAopProxy=true
[BEFORE] method=send, channel=web, type=String
[TARGET] channel=web, type=String
[AFTER] type=String, result=sent:web:String
result1=sent:web:String
[TARGET] channel=queue, type=PlainPayload
result2=sent:queue:PlainPayload
[BEFORE] method=send, channel=batch, type=Integer
[TARGET] channel=batch, type=Integer
[AFTER] type=Integer, result=sent:batch:Integer
result3=sent:batch:Integer
beforeCount=2
afterCount=2
```

**Tại sao đúng như vậy?**

1. Aspect có pointcut `execution(...MessageService.send(..))`; Spring tạo proxy vì method có thể được advice.
2. Khi nhận `String`, runtime payload type tương thích `Serializable` nên Spring bind `payload="hello"`, `channel="web"` và chạy `@Before`.
3. Target chạy và trả `sent:web:String`; `@AfterReturning` bind **cả input** và **output** rồi in dòng `[AFTER]`.
4. Khi nhận `PlainPayload`, runtime payload không tương thích `Serializable`, nên **hai advice không chạy**, nhưng target vẫn chạy bình thường và trả `sent:queue:PlainPayload`.
5. Khi nhận `Integer`, runtime payload tương thích `Serializable`; cả hai advice chạy lần thứ hai.
6. Counter cuối là `2` cho mỗi advice trong khi target chạy `3` lần. Điều này chứng minh **binding và type filter được xét theo từng invocation**, không phải một điều kiện cố định bằng tên method.

**Lưu ý kiểm chứng:** Code/output được thiết kế theo API của Spring Framework 6.1; đây là stdout **dự kiến từ source**. Trước khi dùng trong dự án sản xuất, hãy chạy Maven/integration test trên JDK và Spring version mục tiêu, vì classpath/proxy configuration và advisor order thực tế có thể khác.

## 9. Những góc cạnh cần kiểm thử khi binding arguments

### 9.1. `null`

`null` không có runtime class cụ thể, nhưng matching của `args` còn liên quan **kiểu khai báo của method, logic binder và Spring/AspectJ implementation**. Không đưa ra một quy tắc tuyệt đối kiểu “`args(SomeType)` luôn match null” hoặc “luôn bỏ null” cho mọi chữ ký.

Cách an toàn:

- Nếu method cho phép `null`, viết integration test với **đúng pointcut và Spring version**.
- Không gọi `payload.getClass()`, `payload.toString()` hoặc unbox nếu `payload` có thể null.
- Nếu advice cần kiểm tra **null/non-null value**, cân nhắc `JoinPoint.getArgs()` và logic explicit sau khi pointcut giới hạn method hợp lý.
- Dùng `args` cho **ràng buộc kiểu**; đừng giả định nó là một validator đầy đủ cho mọi business input.

### 9.2. Primitive và wrapper types

Method có `void submit(int count)` khai báo primitive, còn object arguments của interception API có thể liên quan boxing. Đối với `args(count)` và advice parameter `Integer` hoặc `int`, hãy xác minh matching/binding khi ứng dụng có primitive method signatures. Nếu chỉ cần chọn method khai báo `int`, biểu thức `execution(* *.submit(int))` phù hợp hơn.

Khi thay arguments trong `@Around` bằng `proceed(Object[])`, `null` không thể được unbox thành primitive. Không dựa vào phép chuyển kiểu ngầm để bỏ qua kiểm tra validity của input.

### 9.3. Varargs là một array parameter tại JVM

Method:

```java
void submit(String... ids);
```

có JVM parameter tương ứng một array `String[]`. Dù caller viết `submit("A","B")`, không tự suy rằng pointcut `args(id1,id2)` sẽ có hai method arguments tách biệt. Cần đối chiếu varargs/array matching của Spring/AspectJ version sử dụng và thiết kế binding theo JVM signature khi cần.

### 9.4. Generic type erasure

Spring docs cảnh báo không thể dùng `args` để xác minh đầy đủ generic element type của một collection, ví dụ bind `Collection<MyType>` rồi hy vọng Spring kiểm tra mọi phần tử `MyType` ở runtime.

Nếu cần nhận collection:

```java
@Before(
    value = "execution(* com.example..BatchService.process(..))"
          + " && args(items)",
    argNames = "items"
)
public void beforeBatch(java.util.Collection<?> items) {
    for (Object item : items) {
        // Tự kiểm tra loại phần tử nếu policy thật sự cần.
    }
}
```

Đây là **method fragment** cần bean/class `BatchService`. `Collection<?>` tránh lời cam kết generic element type không thể kiểm tra tại runtime. Đừng đọc generic `Collection<Order>` trên advice signature như một bộ lọc tự động của Spring AOP.

### 9.5. Annotation binding khác `args`

`args(payload)` bind method input value. `@args(SomeAnnotation)` là một **pointcut designator khác**: nó xét annotation trên kiểu runtime của arguments, không phải binding tương đương với `args`.

`@annotation(audited)` có thể bind **annotation instance gắn với method** vào advice parameter; `target(bean)` có thể bind target object; `this(proxy)` có thể bind Spring proxy object. Khi kết hợp các binding này, danh sách `argNames` phải đúng với **tất cả ordinary formal parameters** mà advice cần bind.

Ví dụ fragment:

```java
@Before(
    value = "execution(* com.example..Service.*(..))"
          + " && args(payload,..)"
          + " && target(bean)",
    argNames = "payload,bean"
)
public void inspect(Object payload, Object bean) {
    // payload: một argument, bean: target instance.
}
```

Không nhầm `bean` trong `target(bean)` với Spring-specific `bean(namePattern)` pointcut: hai ký hiệu này có chức năng khác nhau.

## 10. Spring proxy boundary: điều kiện bắt buộc trước cả binding

Dù `args` và `argNames` viết đúng, advice **không tự chạy** nếu method không đi qua Spring AOP proxy:

```text
Spring Bean A -> Spring proxy của Bean B -> advice binding args -> target method
Spring Bean B -> this.method(...)         -> bỏ qua Spring AOP proxy
new BeanB().method(...)                   -> đối tượng ngoài Spring proxy
```

Cần xác minh:

- **Aspect được đăng ký thành Spring bean** qua `@Component` hoặc `@Bean`, chứ không chỉ có `@Aspect`.
- `@EnableAspectJAutoProxy` hoặc Spring Boot AOP auto-configuration tương ứng đã hoạt động.
- Bean đích nằm trong đúng `ApplicationContext` có hạ tầng auto-proxy.
- Caller dùng reference Spring cấp; không tự `new` service hoặc giữ raw reference.
- Với JDK proxy, method cần khả dụng theo interface proxy; với CGLIB, `final`/`private` method không được proxy override theo cách thông thường.
- Method đang được gọi thực sự khớp pointcut `execution`/scope **và** `args` dynamic conditions.

**Một `AopUtils.isAopProxy(bean) == true` chưa chứng minh `args(payload)` match invocation.** Proxy có thể tồn tại vì advisor khác; còn kiểu runtime của argument thay đổi trên từng lời gọi.

## 11. Vì sao nên kết hợp `execution` với `args`?

Spring có các phép kiểm pointcut tĩnh và động. `execution` giúp Spring xác định nhanh **method/class signatures** có liên quan; `args` có thể cần kiểm tra arguments ở **mỗi invocation**.

Biểu thức quá rộng:

```java
@Before("args(java.io.Serializable)")
public void anySerializable() {}
```

có thể chọn nhiều method không liên quan trên các Spring beans được proxy. Nếu advice thực hiện logging/audit, điều này làm tăng chi phí và nguy cơ ghi dữ liệu nhạy cảm.

Biểu thức hẹp hơn:

```java
@Before(
    "execution(public * com.example.billing.BillingService.submit(..))"
    + " && args(java.io.Serializable,..)"
)
public void chosenSerializable() {}
```

chỉ xem những lời gọi có method signature/mục tiêu đúng phạm vi cần thiết, rồi lọc theo runtime argument type.

**Không đưa business value logic vào `args` một cách tưởng tượng.** Ví dụ `args(java.math.BigDecimal)` không kiểm tra `amount > 100000`; cần bind `BigDecimal amount` rồi kiểm tra giá trị trong advice hoặc validation/service tương ứng.

Cân nhắc hiệu năng khi có nhiều advice pointcuts động, nhưng **ưu tiên độ đúng và phạm vi rõ** trước khi tối ưu vi mô. Với Spring `MethodMatcher`, có static matching và khả năng runtime matching; không nên khẳng định mỗi biểu thức `args` nhất thiết làm Spring kiểm tra mọi method của mọi bean ở mỗi lời gọi.

## 12. Lỗi thường gặp khi bind arguments

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Spring báo không tìm được parameter name | Thiếu `argNames`/`-parameters`, expression phức tạp không suy luận được | Khai báo `argNames` đủ, biên dịch Java với `-parameters` khi phù hợp. |
| Named pointcut có 2 parameters nhưng advice tham chiếu không có arguments | Không khớp số lượng bindings | Dùng `pointcutName(payload,channel)` và signature tương ứng. |
| Binding `payload` bị null gây NPE | Advice giả định mọi argument non-null | Kiểm tra null, test API có nullable values. |
| `args(Serializable)` chạy với `String` dù method khai báo `Object` | Đây là runtime type matching, hành vi đúng | Phân biệt `args` với `execution` static signature. |
| Cùng method, một lần advice chạy và lần khác không | Actual argument types khác nhau | Đo đầu vào trên cùng Spring proxy; kiểm tra binding type. |
| Advice nhận sai argument position | Biểu thức và Java signature khác thứ tự | Kiểm tra `args(first,second)`, `argNames` và thứ tự parameters. |
| `argNames` khai báo thiếu `JoinPoint` đầu tiên | Đây có thể là hành vi được Spring cho phép | Phân biệt first `JoinPoint`/ `ProceedingJoinPoint` với parameters bình thường. |
| `@AfterReturning` bị nhầm với input binding | `returning="result"` là return value, không phải method input | Dùng `args(input)` riêng và khai báo cả input/result trong `argNames`. |
| `@AfterThrowing` không nhận exception | Tên `throwing` khác tham số advice, type không tương thích hoặc method không ném lỗi | Đồng bộ `throwing`, advice parameter và test failure paths. |
| Gán `payload = replacement` trong advice nhưng target vẫn nhận giá trị cũ | Gán lại local advice parameter không sửa invocation arguments | Dùng `@Around` + `proceed(newArgs)` nếu policy yêu cầu và type hợp lệ. |
| Bind collection generic không lọc được item type | Erasure và giới hạn matching generic types | Dùng `Collection<?>` rồi kiểm tra phần tử hoặc thiết kế typed request object. |
| Có `@Aspect` nhưng advice không chạy | Aspect chưa là bean, proxy không bật, caller đi qua `this`/`new` hoặc pointcut không match | Kiểm tra context, proxy, advisor, method và đường gọi. |
| `args` match nhiều nơi ngoài dự kiến | Pointcut chỉ dựa vào kiểu argument chung | Giới hạn `execution`/package/class, bổ sung negative tests. |
| `@args` được dùng nhầm thay `args` | `@args` xét annotation của runtime argument type | Dùng đúng designator theo nhu cầu binding. |

## 13. Checklist kiểm thử binding đúng trong Spring

Một integration test đáng tin cần xác minh **cả registration, type matching, value binding và hành vi nghiệp vụ**:

1. Spring `ApplicationContext` có target bean và aspect bean như thiết kế.
2. `AopUtils.isAopProxy(target)` đúng khi advisors có thể áp dụng, nhưng không chỉ dựa vào kiểm tra này.
3. Method được caller gọi qua Spring proxy, không qua self-invocation hoặc instance tự `new`.
4. Với argument thuộc kiểu match, advice nhận **đúng object và vị trí**, không chỉ đúng tên class.
5. Với argument thuộc kiểu không match, target vẫn chạy nhưng advice counter không tăng.
6. Nếu dùng hai arguments, kiểm thử đảo thứ tự/khác kiểu khi API cho phép để phát hiện binding nhầm.
7. Nếu có `JoinPoint`, `getSignature().getName()`, `getArgs()`, `getThis()`, `getTarget()` có đúng nghĩa không.
8. Nếu kết hợp `@AfterReturning`/`@AfterThrowing`, test normal return và exception separately, bao gồm tên binding input/output.
9. Nếu có `@Around` sửa arguments, assert target nhận **newArgs** thật và caller nhận return value hợp lệ.
10. Thử null, primitive, varargs, generic collections nếu business API có các trường hợp ấy.
11. Bảo vệ thông tin nhạy cảm: không log toàn bộ payload, password, token chỉ vì `args(payload)` cho truy cập dễ dàng.
12. Khi refactor tên tham số advice, named pointcut, method signatures hoặc nâng Spring version, chạy lại tests cho binding annotations và build metadata.

Ví dụ ma trận của project ở phần 8:

```text
send("hello", "web")             -> target +1, BEFORE +1, AFTER +1
send(new PlainPayload(...), ...) -> target +1, BEFORE +0, AFTER +0
send(Integer.valueOf(7), ...)   -> target +1, BEFORE +1, AFTER +1

Total target = 3; beforeCount = 2; afterCount = 2
```

Các con số này phụ thuộc **named pointcut đã khai báo**, chứ không phải mọi Spring Aspect có `args` đều chạy đúng 2 lần.

## 14. Tóm tắt cơ chế và tài liệu chính thức

| Câu hỏi | Trả lời ngắn |
| --- | --- |
| `args(java.io.Serializable)` làm gì? | Lọc theo kiểu **argument runtime** phù hợp, không tự bind named value. |
| `args(payload)` làm gì? | Bind giá trị argument vào formal parameter có tên `payload` với kiểu đã khai báo. |
| `argNames` dùng để làm gì? | Cung cấp ánh xạ parameter names rõ ràng cho Spring Aspect binding. |
| `JoinPoint` có cần xuất hiện trong `argNames` không? | Có thể bỏ tên của **leading JoinPoint/ProceedingJoinPoint/StaticPart** theo quy tắc Spring. |
| Named `@Pointcut` có bind values không? | Có, bằng formal parameters và `args(...)`, rồi tham chiếu pointcut kèm parameters từ advice. |
| `@AfterReturning` nhận input và output cùng lúc được không? | Có: `args(input)` và `returning="result"`. |
| `@Around` có đổi arguments chuyển đến target không? | Có: dùng `proceed(Object[])` với đúng số lượng/kiểu; gán lại local parameter không đủ. |
| `args` có lọc theo giá trị như `amount > 100` không? | Không; cần kiểm tra value trong advice/validation. |
| Code bên ngoài Spring hoặc self-invocation có chạy binding advice không? | Không theo cơ chế Spring proxy AOP thông thường. |

Tài liệu Spring Framework để đối chiếu:

- Declaring Advice — Advice Parameters, Passing Parameters to Advice, Determining Argument Names: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Declaring a Pointcut — Supported Pointcut Designators, `args`: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Pointcut API — Static and Dynamic MethodMatcher: https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html
- Proxying Mechanisms — Spring proxy boundary: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Kết luận:** `args` trong Spring Aspect là cầu nối giữa **runtime invocation arguments** và **formal parameters có kiểu của advice**. Để dùng đúng, phải hiểu `args(type)` khác `args(name)`, ràng buộc **đúng vị trí/kiểu/tên**, phối hợp `argNames` hoặc `-parameters` hợp lý và kiểm thử trên **Spring AOP proxy thực tế**. Khi cần thêm return value hay exception, dùng `returning`/`throwing` độc lập với input binding; khi cần thay arguments đến target, dùng `@Around` và `proceed(newArgs)` theo contract method.
