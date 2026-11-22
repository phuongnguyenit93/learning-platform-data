# Visibility của phương thức pointcut và phạm vi tái sử dụng trong Spring AOP

## 1. Mục tiêu của bài

Trong Spring AOP theo cú pháp `@AspectJ`, bạn có thể đặt tên cho một pointcut expression bằng một phương thức `@Pointcut` rồi tham chiếu lại từ các advice khác. Phương thức pointcut có thể khai báo `private`, package-private, `protected` hoặc `public`.

**Hai vấn đề cần phân biệt tuyệt đối:**

1. **Visibility của phương thức khai báo named pointcut** quyết định **nơi những biểu thức pointcut khác được phép tham chiếu tới tên này**, theo quy tắc truy cập Java.
2. **Phạm vi method mà pointcut khớp** do **biểu thức trong `@Pointcut("...")`** quyết định; `private`/`public` của phương thức **khai báo pointcut** không tự thay đổi target methods được advice.

Ví dụ:

```java
@Aspect
public class TraceAspect {
    @Pointcut("execution(public * com.example.orders..*Service.*(..))")
    private void publicServiceOperations() { }

    @Before("publicServiceOperations()")
    public void beforeService() {
        // Advice áp dụng cho những public service method có invocation qua proxy.
    }
}
```

Pointcut method `publicServiceOperations()` là **`private`**, nhưng biểu thức `execution(public * ...)` vẫn có thể match **public methods của Spring service beans**. Từ `private` ở đây **không đồng nghĩa “chỉ chặn private method”**.

Tương tự, một `@Pointcut` method được khai báo `public` không tự động chặn tất cả public target methods. Tập method vẫn phụ thuộc chính biểu thức pointcut.

**Phạm vi nội dung:** cách Spring Framework tổ chức và tái sử dụng named pointcuts, Java visibility, Spring proxy boundary, cùng cách kiểm chứng bằng Spring `ApplicationContext`. Đây không phải bài về AspectJ weaving hoặc accessibility tổng quát của Java.

## 2. Named pointcut trong Spring có cấu tạo gì?

Một named pointcut gồm **method signature** (tên, tham số binding, Java visibility, kiểu trả về `void`) và **expression trong `@Pointcut`**. Spring đọc annotation metadata và tham chiếu tên như `@Before("serviceMethods()")`; thân method thường để trống, không phải callback thực thi nghiệp vụ.

Ví dụ `@Pointcut("execution(public * com.example..*Service.*(..))") private void serviceMethods() {}` có *private declaration* nhưng biểu thức chọn *public target methods*. Đây là điểm phân biệt cần kiểm chứng khi chia sẻ tên qua những phạm vi truy cập khác nhau.

## 3. Ma trận visibility và phạm vi tham chiếu

| Visibility của method `@Pointcut` | Ai có thể tham chiếu named pointcut? | Tình huống Spring AOP nên dùng |
| --- | --- | --- |
| `private` | Các advice/pointcut declarations trong **cùng declaring type** | Đóng gói predicate dành riêng cho một aspect; ngăn aspect khác phụ thuộc vào implementation detail. |
| Package-private (không modifier) | Code declarations trong **cùng Java package** theo quy tắc visibility | Nhóm một số aspects cùng package có convention nội bộ; ít thích hợp nếu package cần thay đổi thường xuyên. |
| `protected` | Declaring type, code cùng package và hierarchy/subclasses theo quy tắc `protected` | Chia sẻ pointcut qua cấu trúc aspect/class hierarchy có chủ đích; cần kiểm tra đúng ngữ cảnh kế thừa và khả năng resolve. |
| `public` | Bất cứ nơi nào **declaring class/method được truy cập**, kể cả package khác | Named pointcut dùng chung giữa nhiều aspects và nhiều module; tạo API pointcut ổn định. |

**Quy tắc từ Spring Framework:** khi tham chiếu pointcut **bằng tên**, các quy tắc Java visibility thông thường được áp dụng. Visibility **không ảnh hưởng pointcut matching**.

Một vài điều kiện cần nói thêm:

1. Nếu class chứa pointcut là package-private, việc cho method `public` **không tự biến declaring class thành public API** cho package khác.
2. `protected` không có nghĩa “aspect nào cũng dùng được”; đặc biệt ngoài package, phải xét quan hệ kế thừa/access hợp lệ, không chỉ dựa vào chữ `protected`.
3. `private` **không cho phép aspect khác tham chiếu tên đó** chỉ vì chúng cùng Spring context. Spring container không bỏ qua Java visibility để biến named pointcut private thành shared API.
4. Một aspect có thể dùng **nhiều private named pointcuts** để xây biểu thức phức tạp nội bộ, sau đó công bố **một public named pointcut** nếu có nhu cầu chia sẻ.
5. Visibility không phải biện pháp authorization/security đối với target methods. Nó kiểm soát **tái sử dụng tên định nghĩa**, không kiểm soát quyền caller thực thi Spring service.

## 4. Pointcut private: tái sử dụng bên trong một aspect

```java
package com.example.orders.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class OrderAuditAspect {
    @Pointcut("execution(public * com.example.orders..*Service.*(..))")
    private void orderServiceOperations() {}

    @Pointcut("execution(* com.example.orders..*Service.submit(..))")
    private void submitOperations() {}

    @Before("orderServiceOperations() && submitOperations()")
    public void beforeSubmit() {
        System.out.println("audit:submit");
    }
}
```

Đây là **đoạn minh họa**, cần các Spring service tương ứng và hạ tầng Spring AOP để chạy. Nó cho thấy:

- `orderServiceOperations()` và `submitOperations()` là **hai named pointcuts private**.
- `beforeSubmit()` ở **cùng class** có thể tham chiếu cả hai và kết hợp bằng `&&`.
- `private` giúp quy tắc nội bộ không vô tình trở thành contract công khai cho module khác.
- Dù pointcut private, `@Before` vẫn có thể advice một `public submit(..)` của bean khác khi method call đi qua Spring proxy.

Nếu aspect thứ hai muốn tái sử dụng `orderServiceOperations()`, nó **không được** tham chiếu `com.example.orders.aop.OrderAuditAspect.orderServiceOperations()` vì declaration private. Khi thực sự cần reuse, hãy **công khai điểm cắt hợp lý** hoặc chuyển predicate dùng chung sang một class định nghĩa pointcuts riêng.

### Private là lựa chọn mặc định tốt khi nào?

- Predicate có ý nghĩa chỉ trong một aspect.
- Tên pointcut gắn với cách triển khai cục bộ và có thể thay đổi thường xuyên.
- Bạn không muốn một module khác tạo coupling vô tình vào chi tiết biểu thức.
- Nhiều advice trong **cùng aspect** cần sử dụng lại expression hoặc ghép thành `&&`, `||`, `!`.

Đừng biến mọi pointcut thành public chỉ vì “đề phòng tương lai”. Visibility hẹp giúp người bảo trì biết cái gì là implementation detail.

## 5. Pointcut public: chia sẻ giữa nhiều aspects bằng CommonPointcuts

Khi nhiều aspects cùng nhắm các method thuộc **service layer**, Spring Framework khuyến nghị định nghĩa những **named pointcut expressions trong một class dùng chung**.

```java
package com.example.orders.aop;

import org.aspectj.lang.annotation.Pointcut;

public class CommonPointcuts {
    @Pointcut("execution(public * com.example.orders..*Service.*(..))")
    public void serviceOperations() {}

    @Pointcut("execution(* com.example.orders..*Service.submit(..))")
    public void submitOperations() {}
}
```

Đây là **một class mang các định nghĩa pointcut**, không chứa advice. Theo mẫu `CommonPointcuts` trong tài liệu Spring Framework, class này **không cần `@Aspect` hoặc Spring bean riêng** chỉ để các biểu thức pointcut khác tham chiếu các phương thức `@Pointcut` bằng fully qualified name.

Một aspect có thể tham chiếu:

```java
@Aspect
public class AuditAspect {
    @Before("com.example.orders.aop.CommonPointcuts.serviceOperations()")
    public void beforeService() {
        // ...
    }
}
```

Aspect khác có thể dùng chính named pointcut ấy:

```java
@Aspect
public class MetricsAspect {
    @Before("com.example.orders.aop.CommonPointcuts.serviceOperations()")
    public void recordInvocation() {
        // ...
    }
}
```

Các snippets trên **chỉ minh họa reuse**, không phải project chạy đầy đủ. Hai aspect classes **phải là Spring beans** (chẳng hạn `@Aspect` + `@Component` với component scan hoặc `@Bean` trong configuration) để advice hoạt động.

**Không cần sao chép nguyên văn chuỗi `execution(...)` sang mọi aspect.** Nếu service package đổi, sửa expression một nơi trong `CommonPointcuts`; những references hợp lệ sẽ dùng biểu thức mới khi Spring xây advisors.

### Cú pháp tham chiếu ở cùng class và ở class khác

| Vị trí sử dụng | Cú pháp | Điều kiện |
| --- | --- | --- |
| Advice trong cùng declaring type | `@Before("serviceOperations()")` | Named pointcut có thể `private`, package-private, `protected` hoặc `public`. |
| Aspect khác tham chiếu public pointcut | `@Before("com.example.orders.aop.CommonPointcuts.serviceOperations()")` | Declaring class và method có visibility hợp lệ, class được đưa vào classpath, tên chính xác. |
| Từ pointcut khác, ghép hai public declarations | `@Pointcut("com.example.orders.aop.CommonPointcuts.serviceOperations() && execution(* *.submit(..))")` | Mỗi tên tham chiếu được resolve, biểu thức đúng cú pháp; cần giới hạn scope để tránh match quá rộng. |
| Dùng tên private của aspect khác | `@Before("OtherAspect.privatePointcut()")` | **Không hợp lệ** theo quy tắc visibility; không được biến thành công khai chỉ vì cùng Spring context. |

Khi refactor package, đổi tên class/method của `CommonPointcuts`, các references bằng fully-qualified name có thể hỏng trong lúc Spring parse advisor. Do đó hãy coi public named pointcuts là **API cấu hình AOP cần test**, không chỉ là những string literals vô nghĩa.

## 6. Demo độc lập Spring Framework: private pointcut và public pointcut cùng áp lên service

Demo này xác nhận rõ hai phạm vi:

- `TraceAspect` chứa **private named pointcut** `processOnly()` chỉ dùng bên trong chính aspect đó.
- `PointcutCatalog` công bố **public named pointcut** `serviceCalls()`; `AuditAspect` ở một class khác dùng nó bằng fully qualified name.
- **Một Spring service bean** có hai public methods. `process(..)` match cả hai biểu thức; `inspect()` chỉ match public pointcut chung. Kết quả được in bằng counters sau khi tất cả calls kết thúc để không phụ thuộc thứ tự thực thi advice.

Môi trường: **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Gradle có plugin `application`. Đây là Spring Framework thuần, không sử dụng Boot AOP auto-configuration.

### 6.1. Cấu trúc project

```text
named-pointcut-visibility/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/visibility/
    ├── Main.java
    ├── AppConfig.java
    ├── OrderService.java
    ├── PointcutCatalog.java
    ├── AuditAspect.java
    └── TraceAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'named-pointcut-visibility'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.visibility.Main'
}
```

Các versions được khai báo cho demo độc lập. Khi áp dụng vào Spring Boot, hãy dùng BOM/dependency management của phiên bản Boot dự án đang chạy thay vì trộn các Spring module versions tùy ý.

### 6.2. Target bean có hai method

**`OrderService.java`**

```java
package com.example.visibility;

public class OrderService {
    public String process(String id) {
        return "processed:" + id;
    }

    public String inspect() {
        return "inspected";
    }
}
```

Cả hai methods đều public/non-final. Tên class kết thúc bằng `Service` để match biểu thức `*Service` của common pointcut.

### 6.3. Class giữ public pointcut dùng chung

**`PointcutCatalog.java`**

```java
package com.example.visibility;

import org.aspectj.lang.annotation.Pointcut;

public class PointcutCatalog {
    @Pointcut(
        "execution(public * com.example.visibility..*Service.*(..))"
    )
    public void serviceCalls() {}
}
```

Class này **không có `@Aspect`, không có `@Component`, không có `@Bean`**, đúng vai trò chỉ **định nghĩa một named pointcut public**. Spring/AspectJ pointcut expression có thể resolve định nghĩa theo class/method name. Bạn không cần gọi `new PointcutCatalog()` hay inject object catalog vào `AuditAspect` để dùng cú pháp biểu thức pointcut.

Không đặt code thực thi trong body của `serviceCalls()`: Spring không dùng nó như một method helper runtime.

### 6.4. Aspect dùng lại public pointcut từ class khác

**`AuditAspect.java`**

```java
package com.example.visibility;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("com.example.visibility.PointcutCatalog.serviceCalls()")
    public void beforeServiceMethod() {
        calls.incrementAndGet();
    }

    public int count() {
        return calls.get();
    }
}
```

Advice tham chiếu **fully qualified public named pointcut** dù nó được khai báo trên một Java class khác. Method `process(..)` và `inspect()` đều match vì chúng là public methods của `OrderService`. Không in trong advice để tránh thứ tự của hai aspects làm stdout không tất định.

### 6.5. Aspect dùng private named pointcut nội bộ

**`TraceAspect.java`**

```java
package com.example.visibility;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class TraceAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Pointcut(
        "execution(public * com.example.visibility.OrderService.process(..))"
    )
    private void processOnly() {}

    @Before("processOnly()")
    public void beforeProcess() {
        calls.incrementAndGet();
    }

    public int count() {
        return calls.get();
    }
}
```

Pointcut `processOnly()` là **private**, nhưng advice `beforeProcess()` của chính `TraceAspect` dùng được. Biểu thức chỉ match `OrderService.process(..)`; `inspect()` không match.

Nếu chuyển nguyên `@Before("processOnly()")` sang `AuditAspect` mà không định nghĩa lại/bind theo visibility, nó không tự nhận diện named pointcut của aspect khác. Muốn share, công bố một public named pointcut riêng hoặc dùng class catalog.

### 6.6. Cấu hình Spring tạo một bean target và hai aspect beans

**`AppConfig.java`**

```java
package com.example.visibility;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    OrderService orderService() {
        return new OrderService();
    }

    @Bean
    AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@EnableAspectJAutoProxy` bật hạ tầng Spring AOP `@AspectJ` cho context. `AuditAspect`/`TraceAspect` trở thành Spring beans qua `@Bean`, không cần `@Component`. `OrderService` là target Spring bean. `proxyTargetClass=true` làm ví dụ dùng CGLIB class-based proxy để main có thể tra cứu `OrderService` bằng concrete class.

**Không đăng ký `PointcutCatalog`** vì class đó chỉ định nghĩa các pointcut signatures và không chứa advice hay state cần quản lý bởi Spring.

### 6.7. Main quan sát kết quả

**`Main.java`**

```java
package com.example.visibility;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            AuditAspect audit = context.getBean(AuditAspect.class);
            TraceAspect trace = context.getBean(TraceAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println(service.process("A"));
            System.out.println(service.inspect());
            System.out.println("publicPointcutCalls=" + audit.count());
            System.out.println("privatePointcutCalls=" + trace.count());
        }
    }
}
```

Từ thư mục project, với Gradle và JDK 17+ đã cài:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper: `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows).

**Các dòng `System.out` do chương trình in, theo đúng thứ tự** (không tính thông báo bên ngoài do JVM/Gradle/logging):

```text
proxy=true
processed:A
inspected
publicPointcutCalls=2
privatePointcutCalls=1
```

Giải thích:

1. `proxy=true`: `OrderService` đã được Spring proxy vì có advisor áp dụng.
2. `processed:A` và `inspected`: cả hai target methods thực thi và trả giá trị.
3. `publicPointcutCalls=2`: biểu thức `PointcutCatalog.serviceCalls()` match **hai method invocations** qua proxy; advice trong `AuditAspect` chạy hai lần.
4. `privatePointcutCalls=1`: chỉ invocation `process("A")` match `TraceAspect.processOnly()`; `inspect()` không match.
5. Không có sự khác biệt vì `private` pointcut “ít khả năng AOP hơn” `public` pointcut; **hai biểu thức selection khác nhau**, còn modifier chỉ quyết định **khả năng tham chiếu** named pointcut.

Demo không dựa vào thứ tự advice execution giữa `TraceAspect` và `AuditAspect`, vì hai counters được in sau tất cả calls. Nếu cần thứ tự advice cụ thể trong production, xem `@Order` và kiểm thử toàn bộ advisor chain.

## 7. Các phạm vi reuse cụ thể trong codebase

### 7.1. Chỉ dùng bên trong một aspect

```java
@Aspect
public class ServiceTraceAspect {
    @Pointcut("execution(public * com.example.billing..*Service.*(..))")
    private void businessMethods() {}

    @Before("businessMethods()")
    public void before() {}

    @AfterReturning("businessMethods()")
    public void afterSuccess() {}
}
```

Hai advice trong cùng declaring class dùng cùng một private named pointcut. Không cần copy chuỗi biểu thức. Đây là **đoạn minh họa**, không thay demo `TraceAspect` ở trên.

### 7.2. Hai aspects trong cùng Java package

```java
package com.example.billing.aop;

public class InternalPointcuts {
    @Pointcut("execution(public * com.example.billing..*Service.*(..))")
    void businessMethods() {}
}
```

`businessMethods()` ở đây là **package-private**, có thể được tham chiếu từ nơi hợp lệ trong **cùng package**. Tuy nhiên, nếu hai aspects ở hai packages con khác nhau, hãy nhớ Java xem `com.example.billing.aop` và `com.example.billing.aop.audit` là **hai package khác nhau**. Package-private không tự cho phép tham chiếu chỉ vì package path có tiền tố giống nhau.

Đoạn minh họa trên cần import `org.aspectj.lang.annotation.Pointcut` nếu đặt vào file thực. Nếu muốn package nội bộ vẫn được mô-đun khác dùng bằng fully qualified name, hãy chọn một **public API pointcut** chủ động thay vì lách visibility.

### 7.3. Sử dụng `protected` trong hierarchy

```java
public abstract class BasePointcuts {
    @Pointcut("execution(public * com.example.billing..*Service.*(..))")
    protected void businessMethods() {}
}

// Minh họa một aspect kế thừa khai báo, cùng project.
@Aspect
public class ChildAspect extends BasePointcuts {
    @Before("businessMethods()")
    public void beforeBusiness() {}
}
```

Đây là **cú pháp minh họa**, không phải hai file Java chạy độc lập: cần packages/imports và bean registration phù hợp. `protected` có thể hỗ trợ pointcut reuse có chủ đích trong hierarchy, nhưng quan hệ inheritance của aspects/`@AspectJ` có các hạn chế riêng. Spring sử dụng normal Java visibility khi resolve tham chiếu; không được giả định một aspect bất kỳ ở package khác có quyền gọi tên `protected` này nếu không có quan hệ visibility hợp lệ.

Nếu nhiều aspects **không có quan hệ cha–con thực sự** cần reuse giống nhau, class `CommonPointcuts` với `public` named declarations thường đơn giản hơn một inheritance hierarchy chỉ để chia sẻ biểu thức.

### 7.4. Dùng giữa modules

Một module `platform-aop` có thể xuất bản:

```java
package com.example.platform.aop;

import org.aspectj.lang.annotation.Pointcut;

public final class PlatformPointcuts {
    private PlatformPointcuts() {}

    @Pointcut("execution(public * com.example.app..*Service.*(..))")
    public void appServiceCalls() {}
}
```

Đây là **đoạn minh họa**, không ghép với demo ở mục 6. Khi một module khác tham chiếu `com.example.platform.aop.PlatformPointcuts.appServiceCalls()`, class/method phải truy cập được ở runtime, được đưa vào dependency/classpath phù hợp, đồng thời biểu thức nhắm đúng packages của ứng dụng thực. Không cần instantiate class chỉ chứa pointcut signatures để người tiêu dùng tham chiếu tên.

Khi xuất bản như API dùng chung, đổi tên FQCN/method hoặc ý nghĩa expression đều có thể làm các aspects bên tiêu dùng lỗi hoặc chọn tập target methods khác. Hãy quản lý thay đổi như một **compatibility contract**.

## 8. Kết hợp các named pointcuts: visibility kiểm soát reference, không kiểm soát tập match

Có thể giữ những building blocks của catalog là `private` nhưng công bố một pointcut tổng hợp `public` có hợp đồng rõ ràng:

```java
@Pointcut("within(com.example.billing..*)")
private void billingTypes() {}

@Pointcut("execution(public * save*(..))")
private void publicSave() {}

@Pointcut("billingTypes() && publicSave()")
public void billingSaveOperations() {}
```

Các method trên là fragments cùng declaring class. Người dùng bên ngoài chỉ tham chiếu `billingSaveOperations()` nếu declaring class public, trong khi thay đổi nội bộ `billingTypes()` không làm chúng phụ thuộc tên helper. Biểu thức quyết định matching, visibility chỉ quyết định nơi có thể tham chiếu.

## 9. Named pointcut có tham số: lưu ý khi chia sẻ binding

Named pointcut có thể mang **binding parameter**, ví dụ:

```java
@Pointcut(value = "args(orderId,..)", argNames = "orderId")
public void withOrderId(String orderId) {}
```

Aspect ngoài class tham chiếu `SomePointcuts.withOrderId(orderId)` từ advice có `argNames`/tham số tương ứng. Khi dùng liên package, method phải có visibility phù hợp; `public` không làm `args` tự match đối số không đúng kiểu. Đây là snippet, không phải method chạy độc lập; hãy test các kiểu tham số và số lượng đối số thực tế.

## 10. Registration, proxy và lifecycle: điều kiện để reuse có tác dụng thực tế

Để tham chiếu công khai thành công, class chứa named pointcut phải nằm trên classpath, type/method accessible, tên đầy đủ đúng và pointcut expression parse được. Nhưng advice chỉ chạy nếu **aspect có advice là Spring bean**, AOP support đã bật, target là Spring bean, method có thể intercept và caller đi qua proxy.

Một class catalog chỉ khai báo các `@Pointcut` public không cần trở thành Spring bean. Ngược lại, khai báo `@Aspect` mà chưa đăng ký qua `@Component` hoặc `@Bean` sẽ không khiến advice tự chạy.

## 11. Những lỗi thường gặp

Khi gặp lỗi, tách ba lớp nguyên nhân. **Không resolve được tên:** sai package/class/method hoặc named pointcut không accessible. **Resolve được nhưng không match:** `execution`, `within`, `bean` hay annotation không chọn đúng method thực tế. **Match đúng nhưng advice không chạy:** target ngoài context, self-invocation, hoặc JDK/CGLIB không intercept được lời gọi đó.

Đừng đổi `private @Pointcut` thành `public` như cách sửa một expression quá hẹp: Java visibility không thay đổi phạm vi matching. Đồng thời không giả định một public catalog khiến mọi Spring bean đều có AOP proxy.

## 12. Chiến lược tổ chức pointcut trong dự án lớn

Một cấu trúc dễ bảo trì:

```text
com.example.app
├── aop
│   ├── ServicePointcuts.java          # public names dùng lại
│   ├── AuditAspect.java               # advice, internal private pointcuts
│   └── MetricsAspect.java             # advice, tham chiếu ServicePointcuts
├── billing
│   └── BillingService.java
└── inventory
    └── InventoryService.java
```

Tách theo vai trò:

- **Pointcut catalog:** công bố tên theo ý nghĩa business/architecture (`businessServiceOperation()`, `billingWriteOperation()`), chỉ giữ những expression dùng lại nhiều nơi.
- **Aspect classes:** giữ advice và pointcuts nội bộ, khai báo `private` khi không cần chia sẻ.
- **Package-private:** dùng trong một package AOP đóng gói tốt; ghi rõ convention của team.
- **Protected:** chỉ khi thật sự có nhu cầu reuse trong hierarchy hợp lệ.
- **Public:** xem như API, có tài liệu/test cho ý nghĩa match; đổi expression là thay contract.
- **Test module:** kiểm tra các Spring proxy targets thật để phát hiện biểu thức chọn nhầm service hoặc mất advisor do move/rename.

Với Java module system (JPMS), ngoài modifier `public` còn có khả năng **đọc module/exported package** khi compile/runtime. Public method nằm trong class/module không accessible sẽ không tự nhiên trở thành cross-module API. Chạy integration test trong cách đóng gói production để phát hiện.

### Có nên tạo một CommonPointcuts duy nhất cho toàn hệ thống?

Không nhất thiết. Một catalog quá lớn chứa mọi điểm cắt của toàn công ty sẽ gây coupling giữa modules. Thay vào đó, một hoặc nhiều catalog có phạm vi rõ ràng như `BillingPointcuts`, `InventoryPointcuts` hay `PlatformServicePointcuts`; public API chỉ cho những rule thực sự dùng chung.

Cân nhắc tên theo **ý nghĩa method set**, không chỉ theo implementation pattern. Chẳng hạn `businessOperations()` tốt hơn `pointcut1()`, nhưng phải đảm bảo biểu thức trong đó thực sự match business operations ở package/module đang dùng.

## 13. Kiểm chứng tên pointcut và tập method match

Kiểm chứng hai hành vi **độc lập**: (1) Một external aspect tham chiếu public catalog pointcut thành công và advice chạy đúng; (2) Một private pointcut được dùng trong cùng aspect vẫn có thể chọn public target methods. Với mỗi case, thêm method đối chứng không được chọn và kiểm tra counter/event thực tế.

Nếu thay public thành private trong một catalog đang được tiêu thụ, giữ thí nghiệm lỗi cấu hình ở fixture riêng để không phá context chính. Sau khi rename class/method hoặc thay visibility, rà chuỗi FQCN và chạy integration tests trên proxy thực.

## 14. Bảng chọn nhanh

| Yêu cầu | Visibility nên cân nhắc | Kiểu khai báo |
| --- | --- | --- |
| Hai advice của cùng một aspect chia sẻ selection nội bộ | `private` | `@Pointcut` trong chính aspect; dùng `@Before("localName()")`. |
| Nhiều aspects cùng package, rule không dùng ngoài package | Package-private | Pointcut catalog trong package, test access/refs. |
| Aspect hierarchy thực sự cần dùng predicate từ base | `protected` | Named pointcut ở base type; bảo đảm Java inheritance/visibility và Spring @AspectJ parsing phù hợp. |
| Các aspects ở nhiều packages/modules cần một selection chung | `public` | Public `CommonPointcuts`/`PlatformPointcuts` với method public, tham chiếu FQCN. |
| Mỗi aspect chỉ có một rule không tái sử dụng | Không nhất thiết đặt tên | `@Before("execution(...)")` inline đơn giản là hợp lý. |
| Muốn thay tập method bị advice | Không xử lý bằng visibility | Sửa `@Pointcut("...")` expression/bean boundaries, rồi test proxy call paths. |
| Muốn chặn private/final method ở target | Visibility pointcut không giúp | Xem giới hạn Spring JDK/CGLIB proxy, refactor target entry; AspectJ weaving là cơ chế khác. |

## 15. Checklist trước khi dùng trong production

Trước khi chia sẻ, kiểm tra method `@Pointcut` trả `void`, body rỗng và tên thể hiện tập method cần chọn; declaring type và method public khi tiêu thụ từ package khác. Pointcut dùng nội bộ nên hạn chế visibility phù hợp. Đối chiếu expression (đặc biệt modifier trong `execution(public ...)`) với target methods và loại proxy JDK/CGLIB; kiểm tra đăng ký aspect bean, đường gọi qua proxy, ca match và không match.

Với public catalog được tiêu thụ giữa module, quản lý thay đổi tên/FQCN/expression như một contract cấu hình có regression tests.

