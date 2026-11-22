# Hành vi khi không gọi proceed() trong @Around Advice của Spring AOP

## 1. Điều quan trọng nhất

Trong **Spring AOP**, một advice khai báo bằng `@Around` có quyền quyết định **có tiếp tục lời gọi đang được chặn hay không**. Phương thức `ProceedingJoinPoint.proceed()` là bước tiếp tục **phần còn lại của chuỗi interceptor/advice** tiến tới phương thức target. Nếu một nhánh của `@Around` **không gọi `proceed()`**, nhánh đó **short-circuit** lời gọi: không chuyển quyền điều khiển xuống phần còn lại của chuỗi ở phía trong advice ấy, nên **phương thức nghiệp vụ đích không chạy theo đường gọi đó**.

Điều này là hành vi **hợp lệ theo API của Spring AOP**, không mặc nhiên là lỗi. Tuy nhiên, nó mang ý nghĩa nghiệp vụ rất lớn: target method không được thực thi, side effect dự kiến không xảy ra, và người gọi có thể nhận **giá trị do aspect tự trả về** hoặc **ngoại lệ do aspect ném ra**.

Mục tiêu của bài:

1. Hiểu chính xác `proceed()` trong Spring `@Around` có vai trò gì.
2. Phân biệt **không gọi proceed**, **gọi một lần** và **gọi nhiều lần**.
3. Biết caller nhận gì khi advice tự `return` hoặc `throw`.
4. Viết fallback phù hợp với phương thức trả `String`, primitive `int` và `void`.
5. Nhìn ra hệ quả đối với audit, transaction, persistence, cache, external API, exception và interceptor ordering.
6. Kiểm chứng bằng ví dụ chạy được trên **Spring Framework thuần** với Java 17+, Maven và Spring AOP proxy.

**Phạm vi:** Chỉ tập trung vào `@Around` và `ProceedingJoinPoint` trong **Spring-managed `@Aspect`**, không chuyển thành bài về AspectJ weaving nói chung.

## 2. Luồng gọi khi có và không có proceed

Một Spring service bean có thể được expose dưới dạng proxy:

~~~text
Client
  |
  v
Spring AOP proxy
  |
  v
@Around advice
  |
  +-- NHÁNH A: pjp.proceed()
  |                 |
  |                 v
  |       Các interceptor còn lại
  |                 |
  |                 v
  |           Target method
  |                 |
  |                 v
  |        Kết quả hoặc ngoại lệ
  |                 |
  |                 v
  |        @Around tiếp tục chạy
  |                 |
  |                 v
  |               Caller
  |
  +-- NHÁNH B: return fallback, không proceed
  |                 |
  |                 v
  |     Bỏ qua chuỗi phía trong và target
  |                 |
  |                 v
  |               Caller
  |
  +-- NHÁNH C: throw exception, không proceed
                    |
                    v
         Ngoại lệ lan ra caller
         (trừ khi lớp ngoài xử lý)
~~~

Ví dụ tối giản:

~~~java
@Around("execution(* demo.CheckoutApi.checkout(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("Before");

    if (maintenanceMode) {
        return "temporarily-unavailable";
    }

    Object result = pjp.proceed();
    System.out.println("After");
    return result;
}
~~~

Đây là **fragment trong một class aspect**, cần biến `maintenanceMode`, import `@Around` và `ProceedingJoinPoint`, Spring AOP config và bean phù hợp. Trong nhánh bảo trì:

- Advice vẫn chạy nên có dòng `Before`.
- `proceed()` không được gọi.
- Không có lời gọi tới method `checkout(...)` của target qua continuation đó.
- Dòng `After` không được thực hiện do nhánh `return` sớm.
- Caller nhận chuỗi `temporarily-unavailable`, miễn là giá trị ấy phù hợp với chữ ký return của method.

Trong nhánh bình thường, `proceed()` tiếp tục gọi method, kết quả đi ngược về advice, rồi advice chuyển tiếp kết quả cho caller.

## 3. proceed() không phải một method nghiệp vụ thông thường

`ProceedingJoinPoint` là tham số bắt buộc theo quy ước của Spring `@Around`. Ví dụ:

~~~java
@Around("execution(* demo.CheckoutApi.checkout(..))")
public Object intercept(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
~~~

Trong Spring AOP:

- `pjp.proceed()` **tiếp tục lời gọi hiện tại** với các tham số gốc.
- `pjp.proceed(new Object[] { ... })` có thể dùng để tiếp tục với một mảng argument khác, với số lượng, kiểu và thứ tự phù hợp method target.
- `pjp.getArgs()` cung cấp argument hiện tại.
- `pjp.getSignature()` mô tả method/join point đang được advice.
- `pjp.getThis()` trả về Spring AOP proxy; `pjp.getTarget()` trả về đối tượng target, nhưng **gọi trực tiếp method trên target không thay thế việc gọi proceed**.

Quan trọng: `proceed()` không đơn thuần tương đương `target.method()`. Nó chuyển việc thực thi **xuống chain** mà proxy đã chuẩn bị. Nếu còn interceptor/advice khác ở phía trong, chúng cũng có cơ hội chạy khi `proceed()` được gọi. Một lệnh `return` sớm có thể bỏ qua cả chúng.

Tài liệu Spring nêu rõ `proceed()` có thể được gọi **không lần nào, một lần hoặc nhiều lần** bên trong `@Around`. Cả ba trường hợp đều hợp lệ về mặt cơ chế; **hợp lệ không đồng nghĩa hợp lý cho mọi nghiệp vụ**.

## 4. Bảng so sánh ba trường hợp

| Trong @Around | Target chạy? | Giá trị người gọi nhận | Rủi ro |
| --- | --- | --- | --- |
| `return pjp.proceed();` | Có, nếu chain bên trong cũng tiếp tục | Thường là giá trị target | Hành vi bình thường |
| `return fallback;` không gọi proceed | Không, qua nhánh này | Fallback do aspect cung cấp | Bỏ qua side effect, che giấu công việc chưa làm |
| `throw new IllegalStateException(...);` không gọi proceed | Không, qua nhánh này | Caller nhận exception | Thay đổi exception contract của method |
| Gọi `pjp.proceed()` hai lần | Có thể thực thi target hai lần | Do code advice quyết định | Nhân đôi giao dịch hoặc side effect |
| Không gọi proceed nhưng `return null;` | Không | null, nếu return contract cho phép | Với primitive, có thể lỗi khi proxy unbox/khôi phục return |
| Không gọi proceed nhưng `return 0;` cho method trả int | Không | Integer được proxy unbox thành `int` | Dễ biến “chưa thực thi” thành kết quả hợp lệ giả |

Không được kết luận “không proceed thì **không có bất kỳ advice nào chạy**”. Chính around advice đó đã chạy; các interceptor **bọc phía ngoài nó** vẫn có thể chạy trước/sau khi lời gọi trả về hoặc ném lỗi. Chỉ các bước **nằm phía trong tại vị trí continuation bị bỏ qua** và target method không được đi tới qua nhánh đó.

Khi có nhiều advisor, kết quả quan sát được phụ thuộc vào thứ tự chain. Không suy luận rằng tất cả `@Before` đều bị bỏ qua hoặc tất cả `@AfterReturning` đều sẽ chạy nếu chưa xác định advisor ở phía nào.

## 5. Return contract khi bỏ qua target

### 5.1. Method trả đối tượng

Giả sử service interface:

~~~java
String checkout(String orderId);
~~~

Aspect có thể trả:

~~~java
if (orderId.startsWith("SKIP-")) {
    return "skipped:" + orderId;
}
~~~

Caller nhận String này thay cho kết quả của target. Không có gì trong Java compiler tự xác nhận nhánh `@Around` trả đúng kiểu String của mọi method mà pointcut match, vì method `@Around` thường khai báo **Object**.

Nếu pointcut quá rộng và cùng nhánh `return "skipped"` áp dụng cho phương thức trả `int`, bạn có thể gặp lỗi runtime do kiểu giá trị trả không phù hợp.

### 5.2. Method trả primitive

Giả sử:

~~~java
int fee(String orderId);
~~~

Aspect nên trả giá trị có thể chuyển thành `int`, ví dụ:

~~~java
if (shouldSkip(orderId)) {
    return 0;
}
~~~

Với advice trả `Object`, giá trị `0` được boxing thành `Integer` rồi proxy trả về cho caller theo chữ ký `int`.

**Không trả null** cho method có primitive return type. Vì null không thể chuyển thành primitive, quá trình hoàn tất invocation có thể thất bại (Spring AOP có đường kiểm tra trường hợp null cho primitive, và tùy proxy còn có nguy cơ unboxing lỗi).

Cũng cần xem xét ý nghĩa nghiệp vụ: `fee = 0` có thể có nghĩa “miễn phí hợp lệ”, **không phải** “chưa tính phí”. Nếu đây là hai trạng thái khác nhau, hãy thiết kế return type biểu diễn được sự khác biệt, chẳng hạn kết quả có status, hoặc ném ngoại lệ phù hợp.

### 5.3. Method trả void

Giả sử:

~~~java
void notifyCustomer(String orderId);
~~~

Advice khai báo kiểu `Object` có thể dùng:

~~~java
if (shouldSkip(orderId)) {
    return null;
}
return pjp.proceed();
~~~

Với phương thức target trả `void`, caller không nhận một giá trị Java có ý nghĩa. `return null` của advice chỉ là kết thúc continuation qua proxy.

**Nhưng return void không đồng nghĩa có thể bỏ qua tùy ý.** Nếu thông báo là bắt buộc, caller vẫn tưởng call đã hoàn thành bình thường. Cần quy ước rõ rằng việc bỏ qua được chấp nhận, hoặc thể hiện kết quả bằng return type/exception.

### 5.4. Vì sao @Around nên trả Object, không trả void?

Spring khuyến nghị phương thức `@Around` **khai báo `Object` làm return type** và thường `return` kết quả của `proceed()`. Nếu method advice lại khai báo `void`, caller sẽ không nhận được giá trị trả từ continuation theo cách mong đợi.

Để một aspect áp dụng cho cả String, int và void methods, dùng `public Object around(ProceedingJoinPoint pjp) throws Throwable`, rồi đảm bảo các nhánh trả về hợp đồng phù hợp từng method. Khi logic trở nên phức tạp, nên chia thành **nhiều pointcut/advice có kiểu và trách nhiệm rõ ràng** thay vì viết một switch chứa hàng trăm method.

## 6. Ví dụ hoàn chỉnh: bỏ qua ba kiểu method có kiểm chứng

Ta tạo ứng dụng **Spring Framework 6.2.12**, **Java 17+** và **Maven 3.9+**. Không cần Spring Boot hoặc cơ sở dữ liệu.

Một Spring `CheckoutService` cung cấp ba method:

- `String checkout(String orderId)`: thực hiện checkout và trả kết quả.
- `int fee(String orderId)`: tính phí.
- `void notifyCustomer(String orderId)`: gửi thông báo.

Một Spring `GateAspect` có `@Around` cho cả ba. Nếu orderId bắt đầu bằng `SKIP-`, advice **không gọi proceed** và cung cấp fallback tương ứng; ngược lại, advice gọi `proceed()` đúng một lần.

Một `ExecutionProbe` được target inject để đếm số lần **target method thật sự chạy**. Điều này giúp kiểm chứng rõ rằng dòng `AOP bypass` không chỉ là một log trong khi target vẫn chạy ngầm.

### 6.1. Cấu trúc thư mục

~~~text
spring-aop-around-shortcircuit/
├── pom.xml
└── src/main/java/demo/
    ├── CheckoutApi.java
    ├── CheckoutService.java
    ├── ExecutionProbe.java
    ├── GateAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-around-shortcircuit</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp ApplicationContext và các module Spring AOP cần thiết. `aspectjweaver` cung cấp các annotation/pointcut type mà Spring sử dụng cho `@AspectJ` style. Ví dụ hoạt động bằng **Spring proxy**, không có compile-time hoặc load-time weaving.

### 6.3. Interface công bố ba phương thức

**src/main/java/demo/CheckoutApi.java**

~~~java
package demo;

public interface CheckoutApi {
    String checkout(String orderId);
    int fee(String orderId);
    void notifyCustomer(String orderId);
}
~~~

Có interface giúp Spring Framework thuần mặc định có thể chọn **JDK dynamic proxy**. App sẽ lấy bean theo `CheckoutApi`, không cast proxy sang implementation.

### 6.4. Probe đếm số lần target được thực thi

**src/main/java/demo/ExecutionProbe.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class ExecutionProbe {

    private final AtomicInteger targetCalls = new AtomicInteger();

    public void increment() {
        targetCalls.incrementAndGet();
    }

    public int count() {
        return targetCalls.get();
    }
}
~~~

Đây là **bean phụ trợ**, không phải target của pointcut `CheckoutApi`. Nó không bị `GateAspect` match chỉ vì cũng được Spring quản lý. `AtomicInteger` làm phép tăng/đọc bộ đếm an toàn về mặt đồng thời cho minh họa.

### 6.5. Target thực hiện nghiệp vụ

**src/main/java/demo/CheckoutService.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService implements CheckoutApi {

    private final ExecutionProbe probe;

    public CheckoutService(ExecutionProbe probe) {
        this.probe = probe;
    }

    @Override
    public String checkout(String orderId) {
        probe.increment();
        System.out.println("TARGET checkout " + orderId);
        return "paid:" + orderId;
    }

    @Override
    public int fee(String orderId) {
        probe.increment();
        System.out.println("TARGET fee " + orderId);
        return 25;
    }

    @Override
    public void notifyCustomer(String orderId) {
        probe.increment();
        System.out.println("TARGET notifyCustomer " + orderId);
    }
}
~~~

Target tăng bộ đếm ở đầu mỗi method. Nếu `GateAspect` không gọi `proceed()`, các lệnh `probe.increment()` **không được target thực hiện**. Kết quả quan sát không chỉ dựa vào lời in từ advice.

Trong một ứng dụng thật, target có thể ghi database, gọi external API hoặc phát sự kiện; bỏ qua proceed đồng nghĩa các side effect ấy **không xảy ra ở invocation bị chặn**, trừ các hoạt động ngoài target đã thực hiện từ trước ở một nơi khác.

### 6.6. GateAspect: ba kiểu fallback, không proceed

**src/main/java/demo/GateAspect.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class GateAspect {

    @Around("execution(* demo.CheckoutApi.*(..))")
    public Object aroundCheckoutApi(ProceedingJoinPoint pjp)
            throws Throwable {

        String methodName = pjp.getSignature().getName();
        String orderId = (String) pjp.getArgs()[0];

        System.out.println("AOP enter " + methodName + " " + orderId);

        if (orderId.startsWith("SKIP-")) {
            System.out.println("AOP bypass " + methodName);

            return switch (methodName) {
                case "checkout" -> "skipped:" + orderId;
                case "fee" -> 0;
                case "notifyCustomer" -> null;
                default -> throw new IllegalStateException(
                        "No fallback for " + methodName);
            };
        }

        Object result = pjp.proceed();
        System.out.println("AOP proceeded " + methodName);
        return result;
    }
}
~~~

Đây là trọng tâm:

1. `@Aspect @Component` làm class vừa khai báo aspect vừa được Spring đăng ký thành bean.
2. `@Around("execution(* demo.CheckoutApi.*(..))")` chọn những method execution phù hợp với interface CheckoutApi mà Spring proxy xử lý.
3. `pjp.getArgs()[0]` đọc orderId đầu tiên; demo giả định ba method có cùng signature `(String)`. **Không được chép một cách máy móc** sang interface có method không tham số hoặc tham số đầu không phải String.
4. Khi orderId có prefix `SKIP-`, nhánh `return switch` **không gọi proceed**.
5. `checkout` trả String `"skipped:" + orderId` phù hợp contract.
6. `fee` trả literal `0` (được boxing thành Integer), tương thích method trả primitive int.
7. `notifyCustomer` trả null ở tầng advice, phù hợp method đích trả void.
8. Các orderId khác dùng `pjp.proceed()` **chính xác một lần**, trả kết quả target.
9. `System.out.println("AOP proceeded ...")` ở sau proceed chỉ chạy nếu continuation hoàn tất bình thường; nếu target ném exception và advice không bắt, dòng ấy không xuất hiện.

**Lưu ý thiết kế:** Việc chọn fallback theo tên method là cách trình diễn ngắn gọn cho ba return types. Trong production, nên tách thành các advice có pointcut hẹp hơn hoặc một policy riêng có test, để khi thêm method vào interface không vô tình có fallback thiếu/không đúng kiểu.

### 6.7. Kích hoạt Spring AOP

**src/main/java/demo/AppConfig.java**

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

`@ComponentScan` đăng ký `CheckoutService`, `ExecutionProbe` và `GateAspect`. `@EnableAspectJAutoProxy` bật hạ tầng đọc `@Aspect` và xây dựng Spring AOP proxy khi có advisor phù hợp. `@Aspect` **không tự đăng ký bean nếu thiếu component registration hoặc `@Bean`**.

### 6.8. Main: gọi đủ nhánh bình thường và bỏ qua

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    private static void invokeAll(CheckoutApi checkout, String orderId) {
        String result = checkout.checkout(orderId);
        System.out.println("CALLER checkout=" + result);

        int fee = checkout.fee(orderId);
        System.out.println("CALLER fee=" + fee);

        checkout.notifyCustomer(orderId);
        System.out.println("CALLER notified");
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            CheckoutApi checkout = context.getBean(CheckoutApi.class);
            ExecutionProbe probe = context.getBean(ExecutionProbe.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(checkout));

            System.out.println("=== NORMAL ===");
            invokeAll(checkout, "OK-1");

            System.out.println("=== SKIP ===");
            invokeAll(checkout, "SKIP-9");

            System.out.println("TARGET_CALLS " + probe.count());
        }
    }
}
~~~

Chạy trong thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java
~~~

### 6.9. Stdout logic kỳ vọng

~~~text
IS_PROXY true
=== NORMAL ===
AOP enter checkout OK-1
TARGET checkout OK-1
AOP proceeded checkout
CALLER checkout=paid:OK-1
AOP enter fee OK-1
TARGET fee OK-1
AOP proceeded fee
CALLER fee=25
AOP enter notifyCustomer OK-1
TARGET notifyCustomer OK-1
AOP proceeded notifyCustomer
CALLER notified
=== SKIP ===
AOP enter checkout SKIP-9
AOP bypass checkout
CALLER checkout=skipped:SKIP-9
AOP enter fee SKIP-9
AOP bypass fee
CALLER fee=0
AOP enter notifyCustomer SKIP-9
AOP bypass notifyCustomer
CALLER notified
TARGET_CALLS 3
~~~

**Phân tích output:**

- Ở nhóm `NORMAL`, có ba dòng `TARGET`, tương ứng ba lần `proceed()` được thực hiện.
- Ở nhóm `SKIP`, có các dòng `AOP enter` và `AOP bypass` nhưng **không có dòng `TARGET`**.
- Mỗi caller vẫn tiếp tục chạy: nhận String fallback, int fallback hoặc kết thúc method void không có ngoại lệ.
- `TARGET_CALLS 3` xác nhận chỉ ba method trong nhánh bình thường chạm target. Ba lời gọi ở nhánh SKIP **không** tăng counter.
- `IS_PROXY true` chỉ chứng minh bean được Spring proxy; chính output advice/target và probe chứng minh behavior của `@Around` cụ thể.

Bài mô tả **stdout logic** theo chương trình, không tính thông báo Maven hoặc Spring logging. Ví dụ dùng một aspect và một set advisor cố định nên không yêu cầu suy đoán thứ tự giữa nhiều aspects.

## 7. Điều gì vẫn chạy khi target bị bỏ qua?

Một nhầm lẫn là cho rằng “không proceed tức là toàn bộ ứng dụng không làm gì”. Không đúng.

Khi advice bỏ qua target:

- **Code đã chạy trong chính advice trước `return`** vẫn tạo side effect, ví dụ log `AOP enter`, tăng metric hoặc đọc cache.
- **Code của caller trước khi gọi service** đã chạy.
- **Code của caller sau khi lời gọi proxy trả về bình thường** có thể tiếp tục chạy.
- **Interceptor/advice nằm phía ngoài trong chain** có thể chạy và quan sát kết quả/exception theo thứ tự thực tế.
- **Target và những interceptor nằm phía trong vị trí bị short-circuit** không được continuation đi tới qua nhánh đó.

Ví dụ một `@Around` ở phía ngoài ghi thời gian gọi proxy, còn một `@Around` phía trong trả fallback. Outer around vẫn có thể nhận kết quả khi nó gọi proceed để chuyển quyền tới inner around, trong khi target không chạy. Không thể từ việc thiếu dòng `TARGET` mà suy ra “không có transaction/security/logging advice nào chạy”.

Khi có nhiều advisor, việc xác định aspect nào ở ngoài hay ở trong phụ thuộc ordering thực tế. Có thể dùng `@Order` hoặc `Ordered` để xác định ưu tiên giữa các aspects/advisors phù hợp; cần kiểm thử khi logic short-circuit có ý nghĩa nghiệp vụ.

## 8. Throw exception thay vì trả fallback

Một lựa chọn khác là chặn lời gọi và ném ngoại lệ:

~~~java
@Around("execution(* demo.CheckoutApi.checkout(..))")
public Object guard(ProceedingJoinPoint pjp) throws Throwable {
    String orderId = (String) pjp.getArgs()[0];

    if (orderId.startsWith("DENY-")) {
        throw new IllegalStateException("Denied: " + orderId);
    }

    return pjp.proceed();
}
~~~

Đây là **fragment aspect thay thế**, không thêm cùng `GateAspect` trong demo chính nếu muốn giữ stdout mục 6. Nhánh `DENY-` **không gọi proceed**, target không được thực thi qua nhánh đó và caller nhận `IllegalStateException`, trừ khi một interceptor/caller phía ngoài bắt hoặc chuyển đổi ngoại lệ.

So sánh:

~~~java
return "skipped:" + orderId;
~~~

với:

~~~java
throw new IllegalStateException("Denied: " + orderId);
~~~

Trường hợp đầu báo cho caller **thành công ở mức Java call** với một giá trị thay thế; trường hợp sau **báo lỗi qua exception contract**. Chọn hướng nào phải dựa vào nghiệp vụ thật, không chỉ để khiến method chạy “êm”.

Nếu ứng dụng có transaction interceptor ở phía ngoài, một exception thoát ra có thể ảnh hưởng rollback theo transaction rules. Nếu around nuốt exception hoặc trả kết quả bình thường, hành vi transaction khác đi. Vì vậy Spring AOP short-circuit cần được review cùng advisor chain, không được suy luận rằng “không gọi target thì mọi transaction đã có cũng không tồn tại”.

## 9. Cache hit là ví dụ phổ biến của không proceed

Một use case hợp lệ của `@Around` là cache:

~~~java
@Around("execution(* demo.LookupService.find(..)) && args(key)")
public Object aroundFind(ProceedingJoinPoint pjp, String key)
        throws Throwable {

    Object cached = cache.getIfPresent(key);
    if (cached != null) {
        return cached; // Không proceed: trả thẳng kết quả trong cache
    }

    Object result = pjp.proceed();
    cache.put(key, result);
    return result;
}
~~~

Đây là **fragment minh họa**, giả định có `cache`, `LookupService` và cấu hình Spring AOP thích hợp; không phải file chạy được độc lập. Cache hit không gọi target, cache miss gọi target rồi lưu kết quả.

Những điều cần xác nhận khi áp dụng thật:

1. Giá trị trong cache **phải tương thích** return type được advise.
2. `null` trong cache có thể biểu thị “không có dữ liệu”, nhưng cũng có thể là kết quả cache hợp lệ; cần phân biệt **cache miss** với **cached null**.
3. Nếu caller kỳ vọng side effect ở mỗi invocation, không được tự ý trả cached result và bỏ side effect.
4. Nếu nhiều thread cùng cache miss, có thể có nhiều lần proceed; chính sách concurrency của cache cần được thiết kế.
5. Dùng annotation cache sẵn có của Spring khi phù hợp thay vì tự viết AOP cache khi không có yêu cầu đặc thù.

Một cache aspect độc lập vẫn phải loại trừ các bean cache-support thích hợp khỏi pointcut để tránh advice tái nhập qua chính collaborator của nó.

## 10. Authorization và maintenance: short-circuit nên rõ ràng

Với các thao tác bị từ chối vì quyền hoặc bảo trì, việc **không gọi target** có thể chính là mục tiêu. Tuy nhiên, không nên mặc định trả giá trị “trông như thành công” nếu hành động bị ngăn.

Ví dụ:

~~~java
if (!permissionService.allowed(user, operation)) {
    throw new SecurityException("Operation not allowed");
}

return pjp.proceed();
~~~

Đây là **fragment code**, các biến và bean `permissionService`/ `user`/`operation` cần được khai báo trong ngữ cảnh phù hợp. Từ chối bằng exception truyền tín hiệu rõ hơn `return true` trên một method thực chất chưa hoàn thành.

Nếu đây là Spring Security, nên cân nhắc các cơ chế bảo vệ method có sẵn thay vì tự tạo permission advice khó kiểm chứng. Nếu là maintenance mode, nên quy định cách trả về error/status chuẩn tại tầng API. Không nên dùng `@Around` để âm thầm bỏ qua ghi nhận thanh toán hoặc cập nhật dữ liệu bắt buộc.

**Quy tắc nghiệp vụ:** Short-circuit có thể là một cơ chế đúng, nhưng luôn cần định nghĩa rõ **hành động nào không được thực hiện** và **caller được thông báo ra sao**.

## 11. Nguy cơ trả kết quả thay thế sai kiểu

Một advice kiểu Object không được Java compiler buộc mọi nhánh tương thích với mọi method match pointcut:

~~~java
@Around("execution(* demo.CheckoutApi.*(..))")
public Object bad(ProceedingJoinPoint pjp) {
    return "SKIPPED";
}
~~~

Đây là **fragment minh họa lỗi thiết kế**; không dùng chung với demo chính. Nó có thể trả String cho phương thức `fee(String)` trả int hoặc `notifyCustomer(String)` trả void. Với `fee`, kiểu trả về không tương thích có thể gây lỗi runtime khi proxy cố trả kết quả theo signature int.

Các cách tránh:

- Dùng pointcut hẹp cho **một method hoặc một nhóm có cùng return contract**.
- Thiết kế một kiểu kết quả riêng như `OperationResult` nếu caller cần biết `EXECUTED`, `SKIPPED` hoặc `DENIED`.
- Nếu method trả primitive, trả wrapper phù hợp và không dùng null.
- Nếu method trả void, nhớ rằng caller không thể đọc giá trị fallback; nên chọn exception/event rõ ràng khi bỏ qua không phải kết quả hợp lệ.
- Test **return type** ở cả nhánh proceed và nhánh không proceed.

## 12. Không gọi proceed không đồng nghĩa target đã bị hủy

Không gọi proceed **chặn một invocation cụ thể**. Nó không:

- Hủy bean trong `ApplicationContext`.
- Ngăn target được tạo hoặc inject dependencies lúc startup.
- Tự rollback mọi thao tác đã chạy trước đó.
- Dừng các công việc async đã được lên lịch từ trước ở những chỗ khác.
- Chặn method khác trên cùng bean nếu method đó không match pointcut.
- Biến private/internal self-invocation thành lời gọi qua proxy.
- Buộc những interceptor ở phía ngoài ngừng chạy.
- Đảm bảo những dữ liệu external đã được ghi trước lời gọi sẽ được phục hồi.

Trong ví dụ, Spring đã tạo một `CheckoutService` bean dù cả ba lời gọi SKIP không hề chạy body target. `ExecutionProbe` vẫn tồn tại và giữ số đếm từ ba lời gọi bình thường.

Nếu method vừa ghi database vừa phát message, việc không proceed sẽ bỏ qua **toàn bộ thân method target** trên đường gọi đó. Nhưng nếu trước khi đi qua proxy có một phần workflow khác đã ghi database, short-circuit không tự đảo ngược phần đó.

## 13. Proceed nhiều lần: khác hẳn không proceed

Spring cho phép `proceed()` được gọi nhiều lần:

~~~java
@Around("execution(* demo.TaskApi.run(..))")
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (TransientFailureException first) {
        return pjp.proceed();
    }
}
~~~

Đây là **fragment mô tả ý tưởng retry**, không compile độc lập nếu chưa định nghĩa `TaskApi` và `TransientFailureException`, và cần cấu hình AOP. Nó có thể thực thi target **hai lần**, kèm side effect lặp lại, nên chỉ dùng với tác vụ có chính sách retry/idempotency phù hợp.

Phân biệt ba policy:

~~~text
proceed 0 lần -> bypass target
proceed 1 lần -> thực hiện bình thường
proceed 2 lần -> có thể thực hiện lại target (nếu đi hết chain)
~~~

Retry còn phụ thuộc ngoại lệ được ném ra ở vị trí nào trong chain và advisor ordering; không suy luận target đã chạy một lần chỉ vì catch được exception.

Nếu method trả về thông tin về một giao dịch, việc chạy hai lần có thể tạo double charge hoặc double publish. Hãy cân nhắc retry framework chuyên dụng, kiểm tra idempotency và khóa giao dịch; không coi gọi proceed nhiều lần là “vô hại”.

## 14. Thứ tự advice: short-circuit có thể thay đổi những advice khác

Giả sử hai aspects:

- `MetricsAspect` đo duration.
- `GateAspect` quyết định không proceed với `SKIP-`.

Nếu MetricsAspect là advisor **bọc ngoài** GateAspect, nó có thể in metrics sau khi GateAspect trả fallback. Nếu GateAspect bọc ngoài MetricsAspect và không proceed, MetricsAspect không được gọi qua continuation.

Điểm cần nhớ:

| Vị trí so với short-circuit | Khả năng chạy |
| --- | --- |
| Around advice đang quyết định bypass | Đã chạy để đưa ra quyết định |
| Advice nằm phía ngoài và đã gọi proceed vào short-circuit advice | Có thể hoàn tất logic trước/sau như bình thường |
| Advice nằm phía trong short-circuit advice | Không được đi tới nếu không gọi proceed |
| Target method | Không được chạy qua invocation bị bypass |
| Caller sau proxy | Chạy tiếp nếu proxy trả bình thường; xử lý lỗi nếu exception |

**Không có quy tắc “mọi @Before đều chạy ngay cả khi @Around skip” hoặc “mọi @After đều không chạy”.** Thứ tự chain mới là dữ kiện quyết định.

Spring hỗ trợ thứ tự giữa aspects/advisors bằng `@Order` và cơ chế ordering tương ứng. Khi business requirement liên quan transaction/security/audit, phải kiểm thử thứ tự thực, không suy đoán từ thứ tự method khai báo trong source code.

## 15. Self-invocation là vấn đề khác

Nếu một method trên target gọi:

~~~java
public void outer() {
    this.inner();
}
~~~

thì Spring AOP **thông thường không intercept lời gọi `this.inner()`** vì nó không đi qua proxy. Đó là **giới hạn proxy**, khác với một `@Around` đã intercept method `inner` rồi chủ động không gọi proceed.

Hai tình huống:

1. **No interception:** không có lời gọi proxy cho `inner` nên advice của inner không được thực thi.
2. **Interception rồi skip:** advice `@Around` của inner đã chạy, nhưng không gọi continuation.

Điểm phân biệt là có hay không log/side effect **trong advice**. Nếu gặp case không thấy log `AOP enter`, đừng vội kết luận advice đã short-circuit; có thể pointcut không match hoặc lời gọi bypass proxy hoàn toàn.

## 16. Cách kiểm thử hành vi không proceed

### 16.1. Positive/negative test theo side effect

Với demo mục 6, cần assert:

~~~java
int before = probe.count();
String skipped = checkout.checkout("SKIP-T1");

if (!"skipped:SKIP-T1".equals(skipped)) {
    throw new AssertionError("Wrong fallback");
}

if (probe.count() != before) {
    throw new AssertionError("Target should not have executed");
}

String executed = checkout.checkout("OK-T2");

if (!"paid:OK-T2".equals(executed)) {
    throw new AssertionError("Wrong target result");
}

if (probe.count() != before + 1) {
    throw new AssertionError("Target should have executed once");
}
~~~

Đây là **fragment kiểm thử bổ sung** cần biến `checkout` (kiểu `CheckoutApi`) và `probe` (kiểu `ExecutionProbe`) được lấy từ context. Nó không phải một file Java độc lập.

Test chỉ nhìn dòng `AOP bypass` không đủ; cần xác minh **hành vi target thật sự bị bỏ qua** bằng counter, spy hoặc trạng thái persistence phù hợp.

### 16.2. Test return contract theo từng signature

- `checkout("SKIP-...")` phải trả String fallback phù hợp.
- `fee("SKIP-...")` phải trả đúng primitive int, không lỗi unboxing.
- `notifyCustomer("SKIP-...")` phải hoàn tất bình thường nếu skip được phép.
- Trong trường hợp từ chối bằng exception, caller phải nhận **exception đã thiết kế**.
- `checkout("OK-...")` phải chạy target đúng một lần.
- Nếu có nhiều aspects, cần test theo **cấu hình advisor order thật**.

### 16.3. Test điểm cắt có quá rộng không

Nếu `@Around` đang dùng `execution(* demo..*.*(..))` và trong lời advice lại gọi các Spring beans như `ExecutionProbe`, `AuditRecorder`, `GateService`, chúng cũng có nguy cơ bị advisor chọn, dẫn tới advice tái nhập hoặc kết quả không mong muốn. Trong demo, pointcut giới hạn theo interface `CheckoutApi`, nên `ExecutionProbe` nằm ngoài phạm vi.

Đừng dựa vào việc Spring loại `@Aspect` khỏi auto-proxying để suy ra mọi collaborator của aspect cũng được loại.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Không thấy log target nhưng caller vẫn nhận kết quả | Around advice tự trả fallback, không proceed | Tìm các nhánh return trong @Around và kiểm tra contract |
| Caller nhận `null` bất ngờ | Advice short-circuit mà không trả fallback hợp lý | Xác định return type và giá trị thay thế có chủ đích |
| Method trả int bị lỗi khi bypass | Advice trả null hoặc String không tương thích | Trả Integer hợp lệ hoặc thiết kế lại return type |
| Method void không chạy mà caller vẫn tưởng xong | Advice return null và giấu trạng thái skip | Thiết kế status/exception hoặc event phù hợp |
| Không có audit/transaction advice mong đợi | Around advisor phía ngoài đã short-circuit trước khi đi vào chain bên trong | Kiểm tra advisor order và continuation |
| Có một số advice vẫn chạy khi target bị skip | Chúng nằm phía ngoài vị trí short-circuit | Phân tích thứ tự chain, không suy đoán toàn bộ bị bỏ |
| Advice gây nhiều side effect hơn target | Advice tự chạy logic, dù không proceed | Kiểm tra code của advice và collaborators |
| Lời gọi tạo thanh toán hai lần | Retry gọi proceed nhiều lần với method không idempotent | Thiết kế idempotency/retry có kiểm soát |
| Không thấy `AOP enter` | Method không khớp pointcut, bean chưa proxy hoặc self-invocation | Kiểm tra bean, pointcut và caller path |
| Return fallback khác hợp đồng API | Aspect dùng một return cho nhiều signatures | Thu hẹp pointcut hoặc tách advice theo method |
| Không có exception khi nghiệp vụ bị từ chối | Advice trả success-like fallback | Trả status thể hiện skip hoặc ném exception thích hợp |
| Method target đã tạo bean/dependency nhưng không chạy | Bean lifecycle xảy ra trước invocation | Phân biệt bean construction và method execution |
| Advice gọi recorder rồi lặp vô hạn | Recorder cũng nằm trong pointcut | Loại collaborator khỏi pointcut hoặc dùng allowlist business |
| @Around có return type void làm mất kết quả | Advice không truyền return của proceed | Dùng Object và return kết quả phù hợp |

## 18. Checklist trước khi chủ động bỏ proceed()

1. **Vì sao method không nên chạy?** Cache hit, maintenance, authorization denial hay một chính sách có chủ đích khác?
2. **Caller được thông báo thế nào?** Giá trị cached/fallback, status explicit hay exception?
3. **Return type có đúng không?** Đặc biệt primitive, void, kiểu nullable và generic?
4. **Những side effect nào bị bỏ qua?** Ghi database, gửi message, cập nhật trạng thái, metric?
5. **Có side effect nào đã xảy ra trước khi gọi proxy không?** Nếu có, short-circuit không tự hoàn tác.
6. **Advisor ordering có đúng không?** Transaction, security, audit và tracing ở vị trí nào?
7. **Aspect có nên chuyển trách nhiệm sang Spring feature chuyên dụng không?** Ví dụ caching, security hay retry?
8. **Pointcut đã giới hạn đúng business methods chưa?** Tránh chọn nhầm recorder hoặc infra beans.
9. **Đường gọi chắc chắn đi qua Spring proxy không?** Không được nhầm với self-invocation.
10. **Có test cả nhánh proceed và nhánh skip không?** Kiểm tra side effect và kết quả thật, không chỉ log.
11. **Nếu proceed gọi nhiều lần, target có idempotent không?** Đừng tự retry tác vụ có side effect không thể lặp.
12. **Logic fallback có rõ nghĩa không?** Không được giả định `0`, `null` hoặc chuỗi `"OK"` biểu diễn đúng tình trạng nghiệp vụ.

## 19. Câu hỏi tự đánh giá

**1. Một @Around không gọi proceed thì target có được chạy không?**

Không qua invocation bị short-circuit ấy. Advice có thể trực tiếp làm việc khác, nhưng continuation tới target không được thực hiện.

**2. Không gọi proceed có phải lỗi Spring AOP không?**

Không. Spring cho phép gọi `proceed()` 0, 1 hoặc nhiều lần. Đó là quyền lực của around advice nhưng cần dùng có chủ đích.

**3. Ai trả kết quả cho caller khi around không proceed?**

Giá trị mà advice tự `return`, hoặc ngoại lệ advice `throw`. Giá trị phải tương thích method return contract.

**4. Nếu target method trả void thì around nên trả gì khi skip?**

`@Around` vẫn nên có return type Object và có thể `return null`. Nhưng app phải coi đây là hành động bỏ qua có chủ đích, không mặc định xem như nghiệp vụ hoàn thành.

**5. Nếu target method trả int mà advice trả null thì sao?**

Kết quả không tương thích primitive, có thể phát sinh lỗi lúc proxy hoàn tất invocation. Cần trả một Integer thích hợp hoặc thiết kế kết quả rõ ràng hơn.

**6. Một advice phía ngoài có thể chạy khi advice bên trong skip target không?**

Có. Outer advice có thể đã chạy và sẽ tiếp tục xử lý giá trị/exception của inner advice. Không kết luận tất cả advice đều bị bỏ qua.

**7. Khác gì với self-invocation?**

Self-invocation có thể bỏ qua proxy ngay từ đầu nên @Around không được gọi. Short-circuit là @Around đã được gọi và không gọi `proceed()`.

**8. Có thể dùng proceed() hai lần không?**

Có về mặt cơ chế. Nhưng nó có thể thực thi target/side effect lặp lại và phải được quản lý như retry, với idempotency/transaction đúng.

**9. Vì sao một fallback `0` cho phí thanh toán dễ gây hiểu nhầm?**

Vì `0` có thể nghĩa “phí thật bằng không” thay vì “chưa tính phí”. Kết quả nên biểu thị chính xác trạng thái.

**10. Bằng chứng tốt nhất rằng target bị bỏ qua là gì?**

Dùng counter/spy/trạng thái hệ thống để so số lần target được thực thi ở nhánh proceed và skip, cộng với kiểm tra caller result.

## 20. Tài liệu Spring chính thức

- **Spring Framework — Declaring Advice / Around Advice**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- **Spring Framework — AOP Concepts / Around Advice**: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- **Spring Framework — Advice API / MethodInterceptor**: https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html
- **Spring Framework — Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework — @AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html

**Kết luận:** Trong Spring `@Around`, **không gọi `proceed()` là quyết định chủ động bỏ qua continuation và target method của invocation hiện tại**. Advice được phép trả fallback hoặc ném exception thay cho target, nhưng phải bảo toàn return contract, minh bạch trạng thái nghiệp vụ và kiểm thử side effect. Chỉ chọn cách này khi thật sự cần quyền kiểm soát “có thực hiện target hay không”; nếu chỉ cần xử lý trước/sau, hãy ưu tiên loại advice đơn giản hơn.
