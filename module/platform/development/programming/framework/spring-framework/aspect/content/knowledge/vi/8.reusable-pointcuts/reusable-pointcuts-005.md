# Spring AOP — Phân biệt visibility của khai báo pointcut với phương thức được khớp

## 1. Hai loại visibility thường bị nhầm lẫn

Trong Spring AOP dùng `@AspectJ` annotation style, một **named pointcut** gồm hai phần:

1. **Khai báo method `@Pointcut`:** một method Java có tên, tham số (nếu cần), visibility `private`/package-private/`protected`/`public` và body thông thường để trống. Method này đại diện cho một **tên có thể được các pointcut/advice khác tham chiếu**; signature của nó phải trả về `void`.
2. **Biểu thức `@Pointcut("...")`:** quy tắc **matching method execution** mà Spring AOP phân tích để chọn nơi có thể áp dụng advice.

Đây là hai chiều độc lập. Visibility đặt trước từ khóa `void` quyết định **ai được tham chiếu tên pointcut** theo các quy tắc visibility Java; visibility nằm **trong expression** như `execution(public * *(..))` mới giới hạn **những method được khớp**.

```java
@Pointcut("execution(public * demo.visibility..*Service.*(..))")
private void servicePublicOperations() {}
```

- `private` ở khai báo chỉ nói named pointcut `servicePublicOperations()` được dùng trong phạm vi khai báo tương ứng, thường trong chính aspect.
- `public` nằm trong `execution(public * ...)` mới là điều kiện yêu cầu **target method public**.
- Method `servicePublicOperations()` không được gọi để chạy business logic; nó chỉ đặt tên cho biểu thức.

Ngược lại:

```java
@Pointcut("execution(* demo.visibility..*Service.*(..))")
public void serviceOperations() {}
```

- `public void serviceOperations()` cho phép các aspect/class khác **tham chiếu named pointcut** nếu dùng cú pháp truy cập phù hợp.
- Ký tự `*` trong expression không giới hạn visibility method thành `public`. Nó là wildcard cho return type, và không có visibility modifier explicit trong method pattern.
- Dù expression có thể mô tả một tập method rộng hơn, Spring AOP **vẫn chỉ intercept được lời gọi đi qua Spring proxy** và những method mà loại proxy hỗ trợ. Public của declaration **không** biến private/static/final method thành interceptable.

**Kết luận cốt lõi:** *visibility của pointcut declaration ảnh hưởng việc **tham chiếu tên**; không thay đổi **matching** của expression.* Đây là quy tắc được Spring Framework nêu trực tiếp trong tài liệu “Declaring a Pointcut”.

Bài chỉ tập trung vào Spring AOP proxy và cách tổ chức/reuse named pointcut trong Spring; không đi sâu vào AOP nói chung hay full AspectJ weaving.

## 2. Cú pháp `@Pointcut` và vai trò của method khai báo

Trong cú pháp `@AspectJ`, method khai báo named pointcut phải trả về `void`; tên method là symbol được các pointcut/advice khác tham chiếu. Ví dụ:

```java
@Pointcut("execution(public * com.example.service..*.*(..))")
private void selectedPublicServiceMethods() {}
```

`private` đứng trước `void` thuộc **Java method khai báo pointcut**. `public` nằm bên trong `execution(...)` là **modifier yêu cầu ở method đích**. Gọi body `selectedPublicServiceMethods()` như Java method thường không kích hoạt advice. Bài khai báo named pointcut phân tích toàn bộ signature và binding.

## 3. Visibility khai báo chỉ ảnh hưởng cách tái sử dụng named pointcut

Quy tắc Java visibility quyết định **quyền tham chiếu symbol**: `private` trong declaring type; package-private trong cùng Java package; `protected` theo package/subclass access; `public` từ các package khác khi declaring class cũng accessible. Không modifier nào trong số đó thêm hoặc bớt method execution được expression match.

Như vậy, `@Pointcut("execution(public * *(..))") private void p() {}` vẫn chọn **public target methods** khi được advice trong cùng class tham chiếu; `@Pointcut("execution(private * *(..))") public void p() {}` dù công khai symbol cũng không thể intercept private target methods bằng Spring proxy. Bài **“Visibility của phương thức pointcut và phạm vi tái sử dụng”** có ma trận access và ví dụ chia sẻ liên module.

## 4. Visibility của target method được mô tả bằng expression

**Target method visibility** phải xét ở **bên trong** biểu thức Spring AOP, ví dụ:

```java
@Pointcut("execution(public * demo.visibility.OrderService.*(..))")
private void onlyPublicServiceMethods() {}
```

Giải nghĩa từng phần:

- `execution(...)`: chọn method **execution join point** mà Spring AOP hỗ trợ.
- `public`: method modifier được yêu cầu khớp.
- `*` đầu tiên: return type bất kỳ.
- `demo.visibility.OrderService`: declaring/target type expression.
- `*` trước `(..)`: tên method bất kỳ.
- `(..)`: chấp nhận mọi danh sách tham số.

Một expression khác:

```java
@Pointcut("execution(* demo.visibility.OrderService.*(..))")
private void anyDeclaredServiceMethod() {}
```

không ràng buộc `public` ở vị trí modifier. Về mặt mô tả, biểu thức rộng hơn trường hợp chỉ public. Nhưng **Spring AOP vẫn có giới hạn của proxy** — không nên suy ra mọi `private`/`static` method mà text của expression có thể mô tả đều được advice.

### 4.1. `within(...)` không tự đồng nghĩa với public

```java
@Pointcut("within(demo.visibility..*)")
public void inVisibilityModule() {}
```

`within` giới hạn type/package mà method execution thuộc về; nó **không có điều kiện method phải public**. Nếu yêu cầu chỉ public, viết:

```java
@Pointcut("within(demo.visibility..*)"
        + " && execution(public * *(..))")
public void publicMethodsInModule() {}
```

Một public pointcut declaration kết hợp `within` cũng không tự làm điều kiện `execution(public...)` xuất hiện.

### 4.2. Named pointcut giống macro biểu thức có tên

Ví dụ:

```java
@Pointcut("execution(public * *(..))")
private void publicMethods() {}

@Pointcut("within(demo.visibility..*)")
private void inModule() {}

@Pointcut("publicMethods() && inModule()")
public void publicModuleMethods() {}
```

Khi Spring phân tích `publicModuleMethods()`, điều kiện thực chất là **public method** VÀ **nằm trong module**. Modifier `private` của hai helper pointcut không bị “truyền” thành một phần điều kiện matching. Modifier `public` của pointcut tổng hợp chỉ giúp module khác tham chiếu symbol pointcut.

## 5. Phạm vi Spring proxy còn quan trọng hơn expression visibility

Spring Framework hỗ trợ chủ yếu những **method execution** mà proxy có thể nhận. Điều này tạo một bộ lọc **độc lập** với Java visibility của method `@Pointcut`:

### 5.1. JDK dynamic proxy

JDK proxy thực hiện interface. Trong Spring AOP, nó intercept các **public interface method calls** qua reference proxy. Nếu target có public method chỉ trên implementation nhưng không được interface công bố, caller giữ interface proxy không thể gọi method ấy như một business API.

Ví dụ:

```java
interface WorkPort {
    void execute();
}

class WorkService implements WorkPort {
    @Override
    public void execute() {}

    private void helper() {}
}
```

Với JDK proxy triển khai `WorkPort`, lời gọi `port.execute()` qua proxy có thể được advice nếu pointcut phù hợp. `helper()` không thuộc interface nên không có lời gọi public nào trên proxy để intercept.

Điều này **không** liên quan đến việc named pointcut của advice được khai báo `public` hay `private`.

### 5.2. CGLIB class-based proxy

CGLIB tạo subclass của target (nếu class có thể subclass). Spring AOP có thể intercept public và protected method calls trên proxy; một số package-visible methods cũng có thể được intercept nếu visibility cho phép. Tuy nhiên:

- `private` method không thể override, không thể được CGLIB advice.
- `final` instance method không thể override, không thể được CGLIB advice.
- `static` method không phải instance dispatch trên proxy.
- `final class` không thể được tạo subclass CGLIB.
- Một package-private method không visible với subclass ở package khác không thể được override theo cách thông thường.
- Self-invocation `this.method()` vẫn bypass proxy kể cả method đó public và override được.

Tài liệu Spring nêu rõ: nếu pointcut **chỉ** muốn public methods, hãy viết điều kiện public thật sự trong expression, ngay cả khi app dùng CGLIB có thể intercept một số non-public methods. Không dùng visibility của named pointcut làm bộ lọc proxy.

### 5.3. Hai chiều kiểm soát độc lập

| Trường hợp | Visibility khai báo pointcut | Expression match | Spring AOP intercept? |
| --- | --- | --- | --- |
| `private void api()` với `execution(public * *(..))` | Private: chỉ reference trong type khai báo | Public methods | Có thể, khi caller dùng proxy và advice khớp |
| `public void api()` với `execution(public * *(..))` | Public: chia sẻ được | Vẫn public methods | Tương tự dòng trước |
| `public void broad()` với `execution(* *(..))` | Public: chia sẻ được | Không giới hạn modifier | Chỉ các method calls mà proxy hỗ trợ |
| `private void narrow()` với `execution(private * *(..))` | Private: helper nội bộ | Mô tả private methods | Không thể intercept private methods bằng Spring AOP proxy |
| `public void p()` với `within(demo.visibility..*)` | Public: có thể reuse | Type/package scope | Có thể cả non-public trong CGLIB nếu interceptable |
| `public void p()` với `execution(public * *(..)) && within(...)` | Public: có thể reuse | Chỉ public trong scope | Chỉ các lời gọi qua proxy phù hợp |

*“Có thể” không phải chắc chắn: còn cần target bean được quản lý, aspect/advisor được đăng ký, pointcut khớp và lời gọi qua proxy.*

## 6. Ví dụ Maven chạy được: private named pointcut match public target

Ví dụ đầy đủ dùng **Java 17, Maven, Spring Framework 6.2.x** không cần Spring Boot. Mục tiêu:

- Dùng `private @Pointcut` để chọn **public method** và quan sát advice chạy.
- Dùng `public @Pointcut` để công bố một named pointcut có expression **không ghi điều kiện visibility**.
- Aspect khác sử dụng named pointcut `public` bằng tên đầy đủ.
- Một private helper của target không chạy advice, dù nó nằm trong class mà public pointcut mô tả.
- Một lời gọi `this.pay()` từ target không đi qua AOP proxy, dù target method public.

Ta dùng hai aspects với advice khác nhau áp dụng trên **hai method khác nhau** để stdout không phụ thuộc thứ tự chạy của nhiều advice trên cùng một invocation.

### 6.1. Cấu trúc dự án

```text
spring-pointcut-visibility/
├── pom.xml
└── src/main/java/demo/visibility/
    ├── AppConfig.java
    ├── OrderService.java
    ├── LocalAspect.java
    ├── CommonPointcuts.java
    ├── SharedAspect.java
    └── Main.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-pointcut-visibility</artifactId>
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

### 6.3. `AppConfig.java`

```java
package demo.visibility;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

`@ComponentScan` tìm target service và các aspect có `@Component`. `@EnableAspectJAutoProxy` bật AOP proxying. Target không triển khai interface nên Spring Framework sẽ dùng class-based proxy cho target trong ví dụ. Tất cả method cần quan sát từ bên ngoài là public/non-final.

### 6.4. `OrderService.java` — target có public methods và private helper

```java
package demo.visibility;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public void pay() {
        System.out.println("[target] pay");
    }

    public void notifyCustomer() {
        System.out.println("[target] notify");
        privateHelper();
    }

    public void batch() {
        System.out.println("[target] batch");
        this.pay(); // Self-invocation: không đi qua proxy.
    }

    private void privateHelper() {
        System.out.println("[target] privateHelper");
    }
}
```

`pay()` và `notifyCustomer()` là public method mà Spring AOP proxy có thể intercept từ caller bên ngoài; `privateHelper()` không thể override/intercept; `batch()` dùng để minh họa self-invocation.

### 6.5. `LocalAspect.java` — private named pointcut chọn public `pay()`

```java
package demo.visibility;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class LocalAspect {
    // private là visibility của METHOD KHAI BÁO pointcut.
    // public bên trong execution là visibility của TARGET METHOD.
    @Pointcut("execution(public * demo.visibility.OrderService.pay(..))")
    private void payPublicMethod() {}

    @Before("payPublicMethod()")
    public void beforePay() {
        System.out.println("[local advice] before pay");
    }
}
```

Đây là ví dụ trung tâm: method `payPublicMethod()` **private** vẫn là một named pointcut hợp lệ và match **public** `OrderService.pay()`. Spring không cố gọi `payPublicMethod()` như logic Java để chạy advice. Method declaration chỉ cung cấp **tên** được `@Before` sử dụng trong cùng aspect.

### 6.6. `CommonPointcuts.java` — public named pointcut chia sẻ liên aspect

```java
package demo.visibility;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class CommonPointcuts {
    // Method pointcut PUBLIC để aspect khác có thể tham chiếu.
    // Expression không có điều kiện public/protected/private.
    @Pointcut("execution(* demo.visibility.OrderService.*(..))")
    public void anyOrderServiceMethod() {}
}
```

Class này đóng vai trò thư viện named pointcuts. Một `public @Pointcut` cho phép reuse giữa các aspect. Nó không có nghĩa tự động advice mọi method, cũng không tạo advice khi không có `@Before`/`@After`/`@Around` sử dụng expression.

### 6.7. `SharedAspect.java` — gọi lại pointcut từ class khác

```java
package demo.visibility;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class SharedAspect {
    // Reuse public pointcut từ một aspect khác bằng FQN.
    // Giao với method cụ thể để không trùng advice của LocalAspect.
    @Before("demo.visibility.CommonPointcuts.anyOrderServiceMethod()"
          + " && execution(public * demo.visibility.OrderService.notifyCustomer(..))")
    public void beforeNotify() {
        System.out.println("[shared advice] before notify");
    }
}
```

Đây là bằng chứng **public named pointcut có thể được tham chiếu từ aspect khác**. Modifier của `anyOrderServiceMethod()` cho phép cross-aspect reuse, trong khi **tập phương thức thực sự được chọn** là giao expression rộng với `execution(public * ...notifyCustomer(..))`.

Nếu đổi method trong `CommonPointcuts` thành `private` nhưng vẫn giữ tham chiếu FQN từ `SharedAspect`, cấu hình không còn quyền reference named pointcut như đang viết. Đó là vấn đề **visibility của declaration**, không phải lỗi matching của `notifyCustomer()`.

### 6.8. `Main.java`

```java
package demo.visibility;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService orders = ctx.getBean(OrderService.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(orders));
            orders.pay();
            orders.notifyCustomer();
            orders.batch();
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.visibility.Main
```

Các dòng stdout do chương trình in, không kể log Maven/Spring tùy môi trường:

```text
isAopProxy=true
[local advice] before pay
[target] pay
[shared advice] before notify
[target] notify
[target] privateHelper
[target] batch
[target] pay
```

**Vì sao có kết quả trên?**

1. `OrderService` là Spring bean; Spring có advisor từ hai aspects và có thể tạo CGLIB proxy (target không có interface). `isAopProxy=true`.
2. Caller gọi `orders.pay()` qua proxy. Advice tham chiếu private pointcut `payPublicMethod()` khớp public target method `pay()` và chạy.
3. Caller gọi `orders.notifyCustomer()` qua proxy. Advice ở `SharedAspect` tham chiếu public named pointcut của `CommonPointcuts`; nhánh kết hợp chọn `notifyCustomer()`.
4. `privateHelper()` được target gọi trực tiếp; không có advice vì private method không thể được CGLIB override.
5. `orders.batch()` không khớp advice nào trong ví dụ. Trong target `batch()`, `this.pay()` bypass proxy, nên in `[target] pay` mà không có `[local advice]` trước nó.
6. Không có hai advice cùng đánh vào một invocation trong ví dụ, nên không cần giả định thứ tự execution giữa nhiều advice trên một method.

Lưu ý nếu có advice khác trong ứng dụng thực, stdout sẽ thêm dòng tùy pointcut và advice order. Chương trình trên chỉ đăng ký các aspects được khai báo trong thư mục ví dụ.

## 7. Những thí nghiệm kiểm chứng hai chiều visibility

### Thí nghiệm A — Chuyển private pointcut thành public

Trong `LocalAspect`, chỉ đổi:

```java
@Pointcut("execution(public * demo.visibility.OrderService.pay(..))")
public void payPublicMethod() {}
```

Không đổi expression và advice. Khi chạy lại, các dòng `[local advice] before pay` vẫn xuất hiện **đúng như trước**. Tập matching của pointcut không phụ thuộc `private` hay `public` của declaration.

### Thí nghiệm B — Chuyển public pointcut thành private

Trong `CommonPointcuts`, đổi:

```java
@Pointcut("execution(* demo.visibility.OrderService.*(..))")
private void anyOrderServiceMethod() {}
```

Giữ nguyên tham chiếu FQN trong `SharedAspect`. Spring/AspectJ parser không có quyền tham chiếu một **private named pointcut** từ một type khác như public API. Kết quả có thể là **lỗi phân tích pointcut / khởi tạo ApplicationContext** thay vì một thay đổi số method match. Không dựa vào đúng tên exception vì thông báo phụ thuộc phiên bản thư viện.

Sửa bằng cách giữ method reusable `public`, hoặc đưa expression riêng vào cùng aspect khi chỉ cần sử dụng nội bộ.

### Thí nghiệm C — Giữ public declaration, giới hạn expression thành private

Đổi pointcut trong `CommonPointcuts` thành:

```java
@Pointcut("execution(private * demo.visibility.OrderService.*(..))")
public void onlyPrivateOrderMethods() {}
```

Đồng thời đổi advice để tham chiếu tên mới, ví dụ:

```java
@Before("demo.visibility.CommonPointcuts.onlyPrivateOrderMethods()")
public void beforePrivate() {
    System.out.println("[shared advice] before private");
}
```

Hai fragment phải thay **đồng bộ** trong hai file để tham chiếu tên chính xác. Trên Spring AOP proxy thông thường, private `OrderService.privateHelper()` không thể được CGLIB intercept, nên lời gọi nội bộ đến helper vẫn không có advice. Việc named pointcut được khai báo `public` **không cấp thêm khả năng intercept private method**.

### Thí nghiệm D — Giữ private declaration, đổi expression rộng hơn

Trong `LocalAspect` đổi:

```java
@Pointcut("execution(public * demo.visibility.OrderService.*(..))")
private void payPublicMethod() {}
```

Tên `payPublicMethod` có thể không còn phản ánh chính xác ý nghĩa expression; đây là một **tên nên đổi** khi thật sự mở rộng pointcut. Nếu giữ tên và advice như cũ, nó có thể advice cả `pay()`, `notifyCustomer()` và `batch()` khi caller gọi từ ngoài proxy. Đây là thay đổi **matching do sửa expression**, không phải do method pointcut private.

Vì dễ nhầm khi debug, hãy đặt tên pointcut mô tả **điều kiện match**, tránh đặt tên theo modifier của declaration. Ví dụ tên tốt hơn là `publicOrderServiceMethods()`.

## 8. Tại sao private pointcut có thể match public method mà private target method không được advice?

Hai tình huống này khác hẳn nhau:

**Trường hợp 1 — private named pointcut:**

```java
@Pointcut("execution(public * demo.visibility.OrderService.pay(..))")
private void chosenPay() {}

@Before("chosenPay()")
public void beforePay() {
    System.out.println("before pay");
}
```

Method Java `chosenPay()` có visibility private, nhưng nó không phải method đích bị advice. Nó chỉ là cách đặt tên cho expression. Spring AOP không cần cho caller bên ngoài gọi `chosenPay()`.

**Trường hợp 2 — private target business method:**

```java
public class OrderService {
    private void privateHelper() {
        System.out.println("helper");
    }
}
```

Method `privateHelper()` là method nghiệp vụ/implementation bên trong target. Với Spring AOP proxy, private method không nằm trên JDK interface proxy surface và không thể được CGLIB subclass override. Dù named pointcut của aspect được `public`, Spring vẫn không intercept được lời gọi riêng tư này.

**Đừng nói “pointcut private thì không bắt được method”.** Phải hỏi **private của method khai báo pointcut hay private của method đích?**

## 9. Các lỗi khi tổ chức named pointcut trong dự án Spring

Ba nhóm lỗi thường bị nhập nhằng:

- **Visibility declaration:** aspect khác tham chiếu `OtherAspect.privatePc()` nên không resolve; cần công bố public named pointcut hoặc đưa rule về đúng nơi sở hữu.
- **Visibility target:** expression không có `public` có thể mô tả method rộng hơn, nhưng JDK proxy chỉ expose interface methods, CGLIB không override `private`/`final` target methods. Đổi modifier của named pointcut không sửa được giới hạn này.
- **Ranh giới lời gọi:** target có thể match expression mà `this.pay()` hoặc `new Service().pay()` không đi qua Spring proxy; aspect bean cũng phải được đăng ký đúng context.

Một Spring bean có proxy không đồng nghĩa mọi method được advice. Hãy assert output/counter của **advice cụ thể**, so sánh một public target method khớp với một private/final hoặc method ngoài scope không thể chặn.

## 10. Câu hỏi tự kiểm tra

**Tự kiểm tra:**

1. `@Pointcut("execution(public * *(..))") private void anyPublic() {}` có thể match public service method? **Có**, nếu advice cùng class tham chiếu và target được gọi qua proxy phù hợp.
2. Đổi `private` thành `public` ở named pointcut thì tập method match thay đổi? **Không**, khi expression/cấu hình giữ nguyên; chỉ phạm vi reference được mở rộng.
3. `@Pointcut("execution(* *(..))") public void allMethods() {}` có thể advice private target method? **Không** qua Spring AOP proxy thông thường.
4. `protected @Pointcut` có chọn protected target methods không? **Không tự động**; muốn lọc target modifier, đặt điều kiện trong expression.
5. Vì sao self-invocation vẫn không advice khi method public? Vì caller `this.method()` bypass Spring proxy.

**Tài liệu:** [Spring — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html), [Spring — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).

