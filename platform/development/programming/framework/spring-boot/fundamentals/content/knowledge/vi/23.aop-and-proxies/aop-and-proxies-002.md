# Aspect, advice, pointcut, join point và đối tượng đích

Trong Spring Boot, một ứng dụng có thể có hàng chục service và repository cùng cần log, đo thời gian thực thi, theo dõi lỗi hoặc quản lý giao dịch. Nếu viết code cho những việc đó trong mọi phương thức nghiệp vụ, chương trình dễ trùng lặp và khó bảo trì.

**Aspect-Oriented Programming (AOP)** giúp tách các mối quan tâm *cắt ngang* (cross-cutting concerns) khỏi logic nghiệp vụ. Spring AOP phổ biến dựa trên **proxy**: khi một bean được áp dụng AOP, lời gọi từ bên ngoài đi vào proxy trước khi tới đối tượng thực.

Năm khái niệm trung tâm:

- **Aspect:** một đơn vị tổ chức mối quan tâm cắt ngang, ví dụ log hoặc timing.
- **Advice:** mã được chạy trước, sau hoặc bao quanh method execution.
- **Pointcut:** quy tắc chọn các method execution được advice áp dụng.
- **Join point:** vị trí trong quá trình thực thi có thể được gắn hành vi AOP. Trong Spring AOP, join point được hỗ trợ là **method execution**.
- **Target object (đối tượng đích):** object thực hiện nghiệp vụ, được proxy ủy quyền tới.

Ngoài năm khái niệm trên, cần hiểu **AOP proxy**: object trung gian nhận lời gọi của consumer và chạy các interceptor/advice phù hợp trước khi chuyển tiếp tới target.

## 1. Vì sao cần AOP?

Giả sử service xử lý đơn hàng:

```java
@Service
public class OrderService {

    public String placeOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing orderId");
        }
        return "Placed " + orderId;
    }
}
```

Bạn muốn đo thời gian method. Cách truyền thống:

```java
public String placeOrder(String orderId) {
    long start = System.nanoTime();

    try {
        return doPlaceOrder(orderId);
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println("Elapsed: " + elapsed + " ns");
    }
}
```

Nếu có một trăm method cần đo, bạn có thể phải thêm và sửa một trăm đoạn tương tự. Service sẽ chứa cả nghiệp vụ lẫn logging/monitoring.

AOP cho phép khai báo một lần: “mọi phương thức service phù hợp với quy tắc X sẽ được đo thời gian bằng hành vi Y”.

Điều này không có nghĩa mọi loại hành vi đều nên đưa vào AOP. Business rule phụ thuộc rõ vào domain thường nên nằm trong service; AOP phù hợp hơn với logic cắt ngang và có thể diễn đạt nhất quán.

## 2. Hình dung mối quan hệ giữa các khái niệm

Một lời gọi khi bean được proxied có thể đi như sau:

```text
Controller / Consumer
        │
        │ service.placeOrder("A01")
        ▼
   Spring AOP Proxy
        │
        ├── Pointcut: method có phù hợp không?
        │
        ├── Advice trước khi thực thi
        │
        ▼
   Target Object (OrderService)
        │
        ▼
   placeOrder("A01")
        │
        ▼
   Trả kết quả hoặc ném exception
        │
        ▼
   Advice sau / around
        │
        ▼
Controller / Consumer
```

Trong ví dụ này:

| Thuật ngữ | Ý nghĩa |
|---|---|
| Aspect | `TimingAspect` — thành phần chứa logic đo thời gian |
| Advice | `measure(...)` có `@Around` |
| Pointcut | Biểu thức chọn phương thức của `OrderService` |
| Join point | Lần thực thi `placeOrder("A01")` đi qua proxy |
| Target object | Instance `OrderService` thực hiện logic |
| Proxy | Object do Spring cung cấp để điều phối lời gọi |

**Pointcut chọn nơi áp dụng; advice xác định làm gì; aspect đóng gói chúng; target vẫn xử lý nghiệp vụ.**

## 3. Aspect là gì?

Aspect đại diện cho một concern riêng biệt. Ví dụ:

- `ExecutionTimeAspect`: ghi nhận thời gian.
- `AuditAspect`: tạo sự kiện audit.
- `FailureMetricAspect`: đếm lỗi theo loại.
- `TracingAspect`: hỗ trợ trace/span.
- `AccessCheckAspect`: áp dụng kiểm tra bổ sung tại ranh giới phương thức.

Cách khai báo Spring AOP thường gặp:

```java
package com.example.orders.aop;

import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ExecutionTimeAspect {
    // Các advice và pointcut nằm tại đây.
}
```

`@Aspect` khai báo class mang metadata của aspect theo phong cách AspectJ annotations. `@Component` giúp component scanning tạo Spring bean.

**Chỉ có `@Aspect` chưa đủ để chắc chắn class được Spring quản lý**. Aspect cần được đăng ký làm bean bằng `@Component`, `@Bean` hoặc cơ chế tương ứng, đồng thời phải có hạ tầng Spring AOP phù hợp.

Một aspect có thể có nhiều method advice, và nhiều advice có thể dùng chung một pointcut.

## 4. Advice là gì?

Advice là mã của concern cắt ngang được thực hiện khi một join point phù hợp với pointcut.

Ví dụ:

```java
@Aspect
@Component
public class LoggingAspect {

    @Before(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public void beforeServiceCall() {
        System.out.println("Entering service method");
    }
}
```

Ở đây:

- `@Before` quyết định advice chạy trước method.
- Chuỗi trong annotation là pointcut expression.
- Thân method `beforeServiceCall()` là hành vi thực tế.

Các loại advice thường gặp:

| Loại | Annotation | Khi nào chạy |
|---|---|---|
| Before | `@Before` | Trước khi target method được thực thi |
| After returning | `@AfterReturning` | Sau khi method trả về bình thường |
| After throwing | `@AfterThrowing` | Sau khi method ném exception phù hợp |
| After/finally | `@After` | Sau khi method kết thúc, thành công hoặc lỗi |
| Around | `@Around` | Bao quanh lời gọi, điều khiển việc tiếp tục thực thi |

Advice không đồng nghĩa pointcut. **Advice là hành vi; pointcut là điều kiện chọn method.**

## 5. Pointcut là gì?

Pointcut là biểu thức cho biết advice cần áp dụng vào những join point nào.

```java
@Before("execution(* com.example.orders.service..*.*(..))")
public void beforeServiceMethod() {
    System.out.println("Starting service operation");
}
```

Phần:

```text
execution(* com.example.orders.service..*.*(..))
```

chọn những method có signature phù hợp trong package `com.example.orders.service` và các package con.

Pointcut có thể được đặt tên để dùng lại:

```java
@Aspect
@Component
public class ServiceLoggingAspect {

    @Pointcut(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public void serviceOperations() {
        // Thân method dùng để đặt tên pointcut.
    }

    @Before("serviceOperations()")
    public void logStart() {
        System.out.println("Service started");
    }

    @AfterReturning("serviceOperations()")
    public void logSuccess() {
        System.out.println("Service succeeded");
    }
}
```

Method `serviceOperations()` không được gọi như một bước kiểm tra nghiệp vụ mỗi lần method chạy; Spring đọc `@Pointcut` để biết expression.

Lợi ích của named pointcut là tránh lặp biểu thức, giảm lỗi gõ lại và diễn đạt phạm vi bằng tên dễ hiểu.

## 6. Join point là gì?

Theo lý thuyết AOP, join point là một điểm trong quá trình thực thi mà logic cắt ngang có thể được áp dụng.

Trong **Spring AOP proxy-based**, join point được hỗ trợ là **method execution**. Hệ thống AspectJ weaving rộng hơn có thể hỗ trợ constructor execution, field get/set và những loại join point khác; không được suy ra rằng Spring proxy AOP hỗ trợ chúng.

Ví dụ:

```java
orderService.placeOrder("A01");
```

Nếu lời gọi đi qua Spring AOP proxy và pointcut match, **lần thực thi** phương thức `placeOrder` là join point được advice xử lý.

Phân biệt:

- Class `OrderService` là nơi định nghĩa target behavior.
- Pointcut expression xác định loại method sẽ chọn.
- Join point là điểm thực thi method xảy ra.
- Advice là hành vi thực hiện tại điểm đó.

Nhiều lần gọi cùng một method có thể tạo ra nhiều lần thực thi advice.

## 7. Target object và proxy

**Target object** là object chứa method nghiệp vụ; **proxy** là object đứng trước target.

```text
Consumer
    │
    ▼
Proxy implement/extend API của bean
    │
    ├── Logging advice
    │
    ├── Timing advice
    │
    ▼
Target object: OrderService
    │
    ▼
Business method
```

Điều quan trọng là consumer thường inject một Spring bean reference. Reference này có thể là proxy, không phải target object thô.

Proxy khác với target ở những điểm:

- Proxy giữ logic intercept và chuyển tiếp lời gọi.
- Target thực hiện hành vi nghiệp vụ.
- Proxy có thể có runtime class khác target.
- Target có thể không nhận được lời gọi đi qua proxy khi tự gọi method của chính nó.

Spring proxy không nhất thiết thay đổi source của target. Logic service vẫn có thể được viết như Java class thông thường.

## 8. Ví dụ chạy trong Spring Boot

Một dự án Spring Boot có hạ tầng AOP phù hợp thường dùng starter AOP theo phiên bản của dự án. Ví dụ dependency Gradle phổ biến:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Tên starter và module có thể thay đổi theo dòng Spring Boot; cần dùng dependency tương thích với version thực tế.

Các import `org.aspectj.lang.annotation.*` đến từ API AspectJ annotation. **Việc dùng `@Aspect` không đồng nghĩa tự động có compile-time weaving**: Spring AOP thông thường sử dụng proxy.

### 8.1. Lớp ứng dụng

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

### 8.2. Target service

```java
package com.example.orders.service;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public String placeOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        return "Placed order " + orderId;
    }
}
```

### 8.3. Aspect đo thời gian

```java
package com.example.orders.aop;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TimingAspect {

    @Around(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public Object measure(ProceedingJoinPoint joinPoint)
            throws Throwable {

        long start = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - start;

            System.out.println(
                joinPoint.getSignature().toShortString()
                    + " elapsed " + elapsed + " ns"
            );
        }
    }
}
```

Vai trò từng phần:

1. `@Aspect` đánh dấu aspect.
2. `@Component` đăng ký nó thành bean.
3. `@Around` khai báo advice bao quanh method.
4. `execution(...)` là pointcut chọn các service methods.
5. `ProceedingJoinPoint` đại diện join point với khả năng tiếp tục lời gọi.
6. `proceed()` tiếp tục interceptor chain và cuối cùng tới target.
7. `finally` giúp ghi thời gian cả khi target ném lỗi.
8. `return` giữ nguyên kết quả method.

`System.out.println` dùng để minh họa. Production nên dùng logger và observability system tương ứng.

### 8.4. Controller gọi qua proxy

```java
package com.example.orders.web;

import com.example.orders.service.OrderService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public String place(@PathVariable String id) {
        return orderService.placeOrder(id);
    }
}
```

Khi request:

```text
GET /orders/O-123
```

đi tới controller, lời gọi tới Spring bean `OrderService` có thể đi qua proxy. Aspect ghi thời gian, target trả:

```text
Placed order O-123
```

Log có thể có dạng:

```text
OrderService.placeOrder(..) elapsed 38000 ns
```

Con số chỉ minh họa định dạng. Thời gian thực tế tùy máy và workload.

## 9. @Before

`@Before` chạy trước method execution được pointcut chọn.

```java
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class BeforeLoggingAspect {

    @Before(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public void before(JoinPoint joinPoint) {
        System.out.println(
            "Entering " + joinPoint.getSignature().toShortString()
        );
    }
}
```

`@Before` không có `proceed()` và không trực tiếp thay thế kết quả trả về. Nếu method advice ném exception, lời gọi có thể thất bại trước khi target chạy.

Phù hợp cho log/kiểm tra đơn giản trước lời gọi. Khi cần đo tổng thời gian hoặc kiểm soát việc thực thi target, `@Around` thường thích hợp hơn.

## 10. @AfterReturning

`@AfterReturning` chỉ chạy khi method hoàn thành bình thường.

```java
@Aspect
@Component
public class SuccessAspect {

    @AfterReturning(
        pointcut = "execution(* com.example.orders.service..*.*(..))",
        returning = "result"
    )
    public void afterSuccess(JoinPoint joinPoint, Object result) {
        System.out.println(
            "Success: " + joinPoint.getSignature().getName()
        );
    }
}
```

`returning = "result"` liên kết kết quả method với tham số tên `result`.

Lưu ý:

- Method ném exception sẽ không kích hoạt `@AfterReturning` cho lời gọi đó.
- Advice có thể quan sát result.
- `@AfterReturning` không phải API để thay thế trực tiếp return value mà caller nhận.
- Nếu muốn thay đổi kết quả có chủ đích, dùng `@Around` với return type tương thích.

Không nên log `result` nguyên vẹn nếu có thông tin nhạy cảm.

## 11. @AfterThrowing

`@AfterThrowing` chạy khi method ném exception phù hợp.

```java
@Aspect
@Component
public class FailureAspect {

    @AfterThrowing(
        pointcut = "execution(* com.example.orders.service..*.*(..))",
        throwing = "error"
    )
    public void afterFailure(
            JoinPoint joinPoint,
            Throwable error) {

        System.out.println(
            "Failed method: " + joinPoint.getSignature().getName()
                + ", error type: " + error.getClass().getSimpleName()
        );
    }
}
```

`throwing = "error"` liên kết exception với tham số advice.

Advice này phù hợp để ghi failure metrics hoặc audit lỗi. Nó không tự động nuốt exception hay biến một lần gọi thất bại thành thành công.

Nếu cần fallback, retry hoặc biến đổi exception, phải thiết kế riêng trong `@Around` hoặc một tầng xử lý phù hợp, và cân nhắc transaction cùng idempotence.

## 12. @After

`@After` chạy khi method execution kết thúc, bất kể return bình thường hay ném exception.

```java
@Aspect
@Component
public class CompletionAspect {

    @After(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public void after(JoinPoint joinPoint) {
        System.out.println(
            "Completed " + joinPoint.getSignature().toShortString()
        );
    }
}
```

Nó có ý nghĩa gần với `finally`, phù hợp cho cleanup/ghi dấu kết thúc.

| Kết quả method | `@AfterReturning` | `@AfterThrowing` | `@After` |
|---|---:|---:|---:|
| Return bình thường | Chạy | Không chạy | Chạy |
| Ném exception phù hợp | Không chạy | Chạy | Chạy |
| Không match pointcut | Không chạy | Không chạy | Không chạy |

Bảng xét các advice được cấu hình hợp lệ và lời gọi đã đi qua proxy. Khi có nhiều advice có thứ tự khác nhau, exception có thể đã được xử lý hoặc biến đổi ở tầng khác trong interceptor chain.

## 13. @Around và ProceedingJoinPoint

`@Around` linh hoạt nhất vì có thể chạy code trước/sau, quyết định khi nào gọi `proceed()` và xử lý return/exception.

Mẫu:

```java
@Around(
    "execution(* com.example.orders.service..*.*(..))"
)
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    long startedAt = System.nanoTime();

    try {
        Object value = pjp.proceed();
        return value;
    } catch (Throwable error) {
        // Ghi nhận thất bại, sau đó giữ nguyên exception.
        throw error;
    } finally {
        long elapsed = System.nanoTime() - startedAt;
        System.out.println("Elapsed: " + elapsed);
    }
}
```

### 13.1. Không gọi proceed thì sao?

Nếu advice không gọi `proceed()`, phần còn lại của interceptor chain và target method có thể không được thực thi.

Điều đó đôi khi là mục tiêu của một cơ chế chặn/caching, nhưng cũng dễ gây lỗi khó tìm. Ví dụ method ghi dữ liệu mà bị bỏ qua sẽ không thực hiện side effect dự kiến.

### 13.2. Gọi proceed nhiều lần thì sao?

Nếu advice gọi `proceed()` nhiều lần trong trường hợp được hỗ trợ, nghiệp vụ có thể được thực thi nhiều lần. Với thao tác gửi email, trừ tiền hoặc insert dữ liệu, hậu quả có thể nghiêm trọng.

Đừng dùng retry AOP nếu chưa xác định chính sách exception, transaction, giới hạn số lần và tính idempotent của nghiệp vụ.

### 13.3. Bảo toàn kiểu và exception

Dạng an toàn cho advice quan sát là:

```java
return pjp.proceed();
```

`@Around` thường trả `Object` và khai báo `throws Throwable`, để có thể chuyển tiếp kết quả hoặc lỗi mà target tạo ra. Nếu advice trả object không tương thích với chữ ký method, caller có thể gặp lỗi kiểu runtime.

## 14. JoinPoint cung cấp những thông tin gì?

Advice `@Before`, `@After`, `@AfterReturning` và `@AfterThrowing` có thể nhận `JoinPoint`. `@Around` sử dụng `ProceedingJoinPoint`.

```java
@Before(
    "execution(* com.example.orders.service..*.*(..))"
)
public void inspect(JoinPoint jp) {
    String methodName = jp.getSignature().getName();
    String signature = jp.getSignature().toShortString();

    Object[] args = jp.getArgs();
    Object proxy = jp.getThis();
    Object target = jp.getTarget();

    System.out.println(methodName);
    System.out.println(signature);
    System.out.println("Argument count: " + args.length);
    System.out.println("Proxy type: " + proxy.getClass().getName());
    System.out.println("Target type: " + target.getClass().getName());
}
```

Ý nghĩa:

| API | Thông tin |
|---|---|
| `getSignature()` | Signature của method |
| `getArgs()` | Mảng arguments của lời gọi |
| `getThis()` | Reference đến proxy |
| `getTarget()` | Reference đến target object |
| `getKind()` | Loại join point |
| `getSourceLocation()` | Vị trí nguồn khi được hỗ trợ |

**getThis khác getTarget:** trong Spring proxy AOP, `getThis()` mô tả proxy, còn `getTarget()` mô tả object nghiệp vụ.

Không nên tự lấy `getTarget()` rồi gọi trực tiếp method để bỏ qua advice, vì có thể làm sai behavior của transaction, logging, security hoặc các interceptor khác.

Không log toàn bộ `getArgs()` theo mặc định: mảng có thể chứa password, access token, dữ liệu cá nhân hoặc payload lớn.

## 15. Viết pointcut bằng execution(...)

Cú pháp thường gặp:

```text
execution(modifiers-pattern? return-type-pattern declaring-type-pattern?method-name-pattern(parameter-pattern) throws-pattern?)
```

Ví dụ:

```java
@Pointcut(
    "execution(* com.example.orders.service..*.*(..))"
)
public void serviceMethods() {}
```

Trong đó:

- `execution` chọn method execution join points.
- `*` đầu: mọi return type.
- `com.example.orders.service..*`: type trong package/service subpackages.
- `.*`: mọi method name.
- `(..)`: mọi số lượng và kiểu tham số.

Ví dụ khác:

| Expression | Ý nghĩa |
|---|---|
| `execution(* com.example.orders.service.OrderService.placeOrder(..))` | Method placeOrder của OrderService |
| `execution(public * com.example.orders.service..*.*(..))` | Public service methods trong package và subpackages |
| `execution(* com.example.orders.service..*.find*(..))` | Method bắt đầu bằng find |
| `execution(* *(String))` | Method nhận đúng một tham số String trong phạm vi expression |
| `execution(* com.example.orders.service..*.*())` | Service methods không có tham số |
| `execution(* com.example.orders.service..*.*(..))` | Bất kỳ service method có signature phù hợp |

Điểm quan trọng: **signature match không bảo đảm advice chạy**. Lời gọi phải đi qua proxy và method phải có thể được proxy intercept.

### 15.1. Ký hiệu wildcard

- `*` là wildcard tại những vị trí expression cho phép.
- `()` là method không có tham số.
- `(*)` là method có một tham số kiểu bất kỳ.
- `(..)` là method có bất kỳ số lượng và kiểu tham số.
- `..` trong type pattern diễn đạt package hierarchy.
- Dấu chấm phân tách declaring type và method name.

Nên giữ pointcut ở phạm vi gọn. Một expression quá rộng có thể đánh vào method hạ tầng hoặc code không cần theo dõi.

## 16. Những pointcut designator khác

Spring AOP hỗ trợ một tập hợp expression designator hữu ích:

| Designator | Ví dụ | Tác dụng |
|---|---|---|
| `execution` | `execution(* com.example..service..*.*(..))` | Theo signature method |
| `within` | `within(com.example.orders.service..*)` | Giới hạn các type khai báo method |
| `this` | `this(com.example.orders.api.OrderOperations)` | Kiểm tra type của proxy |
| `target` | `target(com.example.orders.service.OrderService)` | Kiểm tra type của target |
| `args` | `args(java.lang.String,..)` | Theo runtime argument types |
| `@annotation` | `@annotation(com.example.orders.aop.TrackExecution)` | Theo annotation trên method |
| `@within` | `@within(com.example.orders.aop.Tracked)` | Theo annotation trên type khai báo |
| `@target` | `@target(com.example.orders.aop.Tracked)` | Theo annotation của runtime target type |
| `@args` | `@args(com.example.orders.aop.AuditedArgument)` | Theo annotation trên argument types |
| `bean` | `bean(orderService)` | Theo bean name; mở rộng của Spring AOP |

Không phải mọi designator AspectJ đều được Spring AOP hỗ trợ. Ví dụ `call`, `get` và `set` trong AspectJ weaving không đồng nghĩa với Spring proxy hỗ trợ intercept field access.

### 16.1. this() khác target()

Với JDK dynamic proxy:

- Proxy implement interface, có thể không phải instance của concrete target class.
- Target là concrete implementation.

Do vậy `this(SomeInterface)` và `target(SomeConcreteClass)` có thể cùng match ở một lời gọi, nhưng `this(SomeConcreteClass)` có thể không match JDK proxy. Hãy dùng những designator này khi thực sự muốn phân biệt proxy và target type.

### 16.2. bean() theo tên

```java
@Pointcut("bean(orderService)")
public void orderBeanOnly() {}
```

Hoặc dùng pattern:

```java
@Pointcut("bean(*Service)")
public void namedServiceBeans() {}
```

`bean` là cơ chế riêng của Spring AOP, nên behavior phụ thuộc tên bean được đăng ký. Đổi bean name có thể thay đổi phạm vi aspect.

## 17. Dùng annotation để chọn method

Chọn theo package tiện lợi nhưng có thể quá rộng. Annotation tùy chỉnh giúp đánh dấu những method thật sự cần tracking.

### 17.1. Khai báo annotation

```java
package com.example.orders.aop;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackExecution {
}
```

`RetentionPolicy.RUNTIME` cho phép hạ tầng quan sát annotation khi chạy.

### 17.2. Đánh dấu target

```java
package com.example.orders.service;

import com.example.orders.aop.TrackExecution;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    @TrackExecution
    public String settle(String paymentId) {
        return "Settled " + paymentId;
    }

    public String status(String paymentId) {
        return "PENDING";
    }
}
```

### 17.3. Pointcut và advice

```java
package com.example.orders.aop;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TrackingAspect {

    @Pointcut(
        "@annotation(com.example.orders.aop.TrackExecution)"
    )
    public void trackedMethods() {}

    @Around("trackedMethods()")
    public Object measure(ProceedingJoinPoint pjp)
            throws Throwable {

        long started = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            System.out.println(
                pjp.getSignature().getName() + " took "
                + (System.nanoTime() - started) + " ns"
            );
        }
    }
}
```

Nếu `PaymentService` được Spring quản lý và gọi qua proxy, `settle(...)` được advice chọn, còn `status(...)` không match annotation pointcut.

Lưu ý rằng placement của annotation trên interface/concrete class và kiểu proxy có thể ảnh hưởng cách matching hoạt động. Nên đặt annotation đúng nơi cần intercept và kiểm thử bằng context của dự án.

## 18. Kết hợp nhiều pointcut

Pointcut expression có thể kết hợp bằng:

- `&&`: AND.
- `||`: OR.
- `!`: NOT.

Đây là toán tử của **AspectJ pointcut expression**, không giống profile expressions của Spring (profile dùng `&` và `|`).

Ví dụ:

```java
@Aspect
@Component
public class ServiceTrackingAspect {

    @Pointcut(
        "within(com.example.orders.service..*)"
    )
    public void serviceLayer() {}

    @Pointcut(
        "@annotation(com.example.orders.aop.TrackExecution)"
    )
    public void trackedMethods() {}

    @Around("serviceLayer() && trackedMethods()")
    public Object track(ProceedingJoinPoint pjp)
            throws Throwable {

        long started = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            System.out.println(
                "Elapsed: " + (System.nanoTime() - started)
            );
        }
    }
}
```

Condition này yêu cầu method **nằm trong service layer** và **mang `@TrackExecution`**.

Một expression OR:

```java
@Pointcut(
    "within(com.example.orders.service..*)"
      + " || within(com.example.orders.repository..*)"
)
public void serviceOrRepository() {}
```

Một expression NOT (giả định có annotation `SkipTracking`):

```java
@Pointcut(
    "within(com.example.orders.service..*)"
      + " && !@annotation(com.example.orders.aop.SkipTracking)"
)
public void trackedServiceExceptOptOut() {}
```

Nếu expression trở nên quá dài, nên tách trách nhiệm hoặc dùng annotation đánh dấu rõ hơn.

## 19. JDK dynamic proxy và class-based proxy

Spring AOP chủ yếu dùng hai cơ chế proxy.

### 19.1. JDK dynamic proxy

- Proxy implement các interface.
- Consumer có thể gọi thông qua interface.
- Proxy không nhất thiết là instance của concrete implementation class.
- Chỉ những method được cung cấp qua interface proxy mới được intercept theo hình thức này.

```java
public interface OrderOperations {
    void submit(String orderId);
}

@Service
public class OrderService implements OrderOperations {

    @Override
    public void submit(String orderId) {
        System.out.println("Submit " + orderId);
    }
}
```

Nếu Spring sử dụng JDK proxy, thiết kế inject `OrderOperations` thường hợp lý hơn yêu cầu concrete type.

### 19.2. Class-based proxy (CGLIB)

- Proxy là subclass tạo động từ target class.
- Có thể proxy class không có interface.
- Cần target class và method tương thích quy tắc override.
- `final class` không thể được subclass.
- `final method` không thể được override/intercept.
- `private method` không thể override.

Một số dòng Spring Boot có property `spring.aop.proxy-target-class` để điều khiển kiểu proxy; default phụ thuộc phiên bản và cách cấu hình. Không nên giả định cách proxy chỉ từ việc class có interface hay không.

### 19.3. Giới hạn chung

Dù dùng JDK hay class-based:

1. Bean cần được Spring quản lý.
2. Hạ tầng AOP và aspect phù hợp phải hoạt động.
3. Pointcut phải match.
4. Lời gọi phải đi qua proxy.
5. Method phải là đối tượng có thể intercept.

Đó là lý do cùng một method có lúc advice chạy, lúc không, dù source code không thay đổi.

## 20. Self-invocation: gọi trong cùng class không đi qua proxy

Xem service:

```java
@Service
public class ReportService {

    public void generateAll() {
        generateOne();
    }

    @TrackExecution
    public void generateOne() {
        System.out.println("Generating report");
    }
}
```

Consumer gọi:

```java
reportService.generateOne();
```

Nếu `reportService` là Spring proxy, advice của `generateOne` có thể chạy.

Nhưng nếu consumer gọi:

```java
reportService.generateAll();
```

thì trong target, `generateAll` gọi `this.generateOne()`. Lời gọi nội bộ này **bỏ qua proxy**, nên advice dành riêng cho `generateOne` không chạy lần nữa.

```text
Consumer
   │
   ▼
Spring proxy
   │
   ▼
Target.generateAll()
   │
   └── this.generateOne()
            │
            └── Không đi qua proxy
```

### Cách giải quyết: tách bean

```java
@Service
public class SingleReportService {

    @TrackExecution
    public void generateOne() {
        System.out.println("Generating report");
    }
}
```

```java
@Service
public class BatchReportService {

    private final SingleReportService singleReportService;

    public BatchReportService(
            SingleReportService singleReportService) {
        this.singleReportService = singleReportService;
    }

    public void generateAll() {
        singleReportService.generateOne();
    }
}
```

Khi `SingleReportService` được inject như Spring bean proxy, lời gọi từ `BatchReportService` đi qua proxy, nên advice có thể áp dụng.

Có kỹ thuật self-injection hoặc `AopContext.currentProxy()`, nhưng chúng làm code phụ thuộc thêm vào AOP infrastructure. Tách bean thường dễ đọc, dễ test và dễ bảo trì hơn.

## 21. Final, private, static và new

Điều kiện match không đủ để advice hoạt động.

| Tình huống | Lý do advice có thể không chạy |
|---|---|
| Object được tạo bằng `new` ngoài Spring | Không phải Spring-managed AOP proxy |
| Method `private` | Không thể intercept như một method proxy có thể override |
| Method `final` với class-based proxy | Không thể override method |
| Class `final` với class-based proxy | Không thể subclass |
| Method `static` | Không là instance method được intercept qua Spring proxy |
| Self-invocation | Lời gọi không qua proxy |
| Aspect không được đăng ký làm bean | Không có advisor tương ứng |
| Pointcut không match | Advice không chọn join point |
| Bean bị loại bởi `@Profile`/condition | Không có bean phù hợp để proxy |

Đừng thay đổi visibility một cách tùy tiện chỉ để làm AOP chạy. Hãy xác định public service boundary phù hợp và chuyển hành vi cần advice đến method/bean dễ tiếp cận qua proxy.

## 22. Thứ tự nhiều aspect

Một method có thể match nhiều aspect:

- Tracing.
- Timing.
- Logging.
- Transaction interceptor.
- Security checks.

Các advice tạo thành interceptor chain. Thứ tự có thể ảnh hưởng thời gian đo, transaction boundary và cách lỗi được ghi nhận.

Có thể đặt `@Order`:

```java
@Aspect
@Component
@Order(10)
public class OuterAspect {

    @Around(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public Object around(ProceedingJoinPoint pjp)
            throws Throwable {

        System.out.println("Outer before");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("Outer after");
        }
    }
}
```

```java
@Aspect
@Component
@Order(20)
public class InnerAspect {

    @Around(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public Object around(ProceedingJoinPoint pjp)
            throws Throwable {

        System.out.println("Inner before");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("Inner after");
        }
    }
}
```

Aspect có `@Order` thấp hơn thường có precedence cao hơn: **đi vào trước, thoát ra sau**.

Thứ tự minh họa:

```text
Outer before
Inner before
Target method
Inner after
Outer after
```

Không nên dựa vào thứ tự khai báo method trong Java để suy luận thứ tự advice giữa nhiều aspect. Khi ordering là yêu cầu quan trọng, hãy cấu hình rõ và xác nhận qua integration test phù hợp.

## 23. AOP và các annotation Spring khác

Các tính năng như transaction, cache và async có thể dùng tư tưởng proxy/interceptor trong các cấu hình Spring tương ứng.

Ví dụ:

```java
@Service
public class CheckoutService {

    @Transactional
    public Receipt checkout(CheckoutCommand command) {
        // Thực hiện các thao tác dữ liệu.
        return new Receipt(command.orderId());
    }
}
```

Khi transaction management được bật và có transaction manager phù hợp, proxy có thể mở/commit/rollback transaction quanh method.

Tương tự:

- `@Cacheable` cần caching support và cache manager.
- `@Async` cần asynchronous execution được bật.
- `@Transactional` cần transaction infrastructure phù hợp.

**AOP starter không tự làm mọi annotation của mọi module hoạt động.** Mỗi tính năng có điều kiện/hạ tầng riêng.

Các tính năng này cũng thường chịu giới hạn self-invocation: lời gọi `this.innerMethod()` không đi qua proxy, nên advice được cấu hình riêng cho `innerMethod` có thể không chạy.

## 24. AOP và reactive/asynchronous execution

Một aspect đo thời gian:

```java
long start = System.nanoTime();
Object result = pjp.proceed();
long duration = System.nanoTime() - start;
```

đo thời gian **phần thực thi đồng bộ của lời gọi `proceed()`**.

Nếu method trả `Mono` hoặc `Flux`, method có thể chỉ tạo và trả publisher; công việc thực tế xảy ra lúc có subscription. Vì vậy timing quanh `proceed()` có thể kết thúc trước khi tác vụ reactive hoàn tất.

Ví dụ:

```java
public Mono<Order> loadOrder(String id) {
    return repository.findById(id);
}
```

Tương tự, với `CompletableFuture`, method có thể trả future trước khi xử lý bất đồng bộ kết thúc.

Muốn đo latency end-to-end, cần instrument đúng lifecycle: reactive signals như `doOnSubscribe`/`doFinally` hoặc cơ chế observation/tracing phù hợp, cũng như completion của future.

**Không mặc định số đo quanh `proceed()` là thời gian toàn bộ thao tác asynchronous.**

## 25. Kiểm tra proxy và gỡ lỗi

Spring AOP cung cấp utility để nhận biết Spring bean đã được proxy chưa:

```java
import org.springframework.aop.support.AopUtils;

boolean aopProxy = AopUtils.isAopProxy(orderService);
boolean jdk = AopUtils.isJdkDynamicProxy(orderService);
boolean cglib = AopUtils.isCglibProxy(orderService);
```

Một runner debug có thể in:

```java
@Component
public class ProxyInspector implements ApplicationRunner {

    private final OrderService orderService;

    public ProxyInspector(OrderService orderService) {
        this.orderService = orderService;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
            "Is proxy: " + AopUtils.isAopProxy(orderService)
        );
    }
}
```

Ví dụ cần import `ApplicationRunner`, `Component` và `AopUtils` tương ứng.

Nếu aspect không chạy, kiểm tra theo thứ tự:

1. Target có là Spring bean không?
2. AOP dependency và auto-configuration đã sẵn sàng chưa?
3. `@Aspect` class có được đăng ký thành bean không?
4. Bean có bị condition hoặc profile loại trừ không?
5. Pointcut có match method signature không?
6. Lời gọi có đi từ consumer vào proxy không?
7. Method có bị `private`, `final` hoặc self-invocation hạn chế không?
8. Kiểu proxy JDK/CGLIB có phù hợp với kiểu injection và method cần gọi không?
9. Có nhiều aspect làm thay đổi luồng hoặc exception không?
10. Code có chạy bất đồng bộ khiến thời điểm quan sát không như dự kiến không?

Đừng chỉ nhìn việc một class mang `@Aspect` để kết luận advice đã hoạt động.

## 26. Integration test xác nhận advice chạy

Unit test tạo target bằng `new` kiểm tra business logic, nhưng không tự tạo Spring proxy để test advice.

Có thể dùng bean đếm số lần advice chạy:

```java
@Component
public class AdviceCounter {

    private final AtomicInteger counter = new AtomicInteger();

    public void increment() {
        counter.incrementAndGet();
    }

    public int value() {
        return counter.get();
    }
}
```

Aspect:

```java
@Aspect
@Component
public class CountingAspect {

    private final AdviceCounter counter;

    public CountingAspect(AdviceCounter counter) {
        this.counter = counter;
    }

    @Before(
        "execution(* com.example.orders.service.OrderService.placeOrder(..))"
    )
    public void count() {
        counter.increment();
    }
}
```

Test:

```java
@SpringBootTest
class OrderServiceAopTest {

    @Autowired
    OrderService orderService;

    @Autowired
    AdviceCounter counter;

    @Test
    void adviceRunsWhenCallingProxiedBean() {
        int before = counter.value();

        orderService.placeOrder("A01");

        assertEquals(before + 1, counter.value());
    }
}
```

Ví dụ giả định các import JUnit/Spring Test, Spring AOP setup và class từ phần trước. Nếu chọn JDK dynamic proxy, nên inject interface được proxy thay cho concrete target class.

Test các trường hợp:

- Method match: counter tăng.
- Method không match: counter không tăng.
- Target ném exception: failure/finally advice hoạt động theo contract.
- Self-invocation: inner method không đi qua proxy.
- Hai aspects: thứ tự theo `@Order`.

## 27. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `@Aspect` được khai báo nhưng advice không chạy | Aspect chưa là bean hoặc thiếu AOP infrastructure | Kiểm tra `@Component`, `@Bean`, dependencies |
| Method được annotate nhưng không bị intercept | Object tạo bằng `new` | Dùng Spring-managed bean |
| Advice chạy từ controller nhưng không chạy khi method gọi nội bộ | Self-invocation | Tách method sang bean khác |
| Pointcut không match | Sai package, class hoặc method pattern | Kiểm tra expression |
| Target method final/private | Giới hạn proxy | Thay đổi thiết kế/ranh giới bean |
| Inject concrete class không được | Có thể đang dùng JDK proxy | Inject interface hoặc cấu hình proxy phù hợp |
| Advice không chạy khi method thành công | Đang dùng `@AfterThrowing` | Dùng `@AfterReturning` cho success |
| Advice không chạy khi method lỗi | Đang dùng `@AfterReturning` | Dùng `@AfterThrowing` hoặc `@After` |
| Thời gian đo bất thường ngắn với reactive method | `proceed()` chỉ trả publisher | Đo theo subscription/completion |
| Lỗi ClassCastException hoặc return sai | `@Around` trả object không tương thích | Trả đúng kết quả của `proceed()` |
| Thao tác ghi dữ liệu bị thực hiện nhiều lần | `proceed()` bị gọi lặp | Chỉ retry khi có contract rõ và idempotence |
| Log chứa thông tin mật | In nguyên args/result | Redact và chỉ log metadata an toàn |

## 28. Nguyên tắc thiết kế aspect

### 28.1. Một concern rõ ràng cho mỗi aspect

Aspect timing chỉ nên đo/ghi thời gian; aspect auditing chỉ nên ghi audit. Đừng trộn authorization, retry, database write và response transformation vào một lớp với pointcut quá rộng.

### 28.2. Pointcut đủ hẹp

So sánh:

```java
@Around("execution(* *(..))")
```

với:

```java
@Around("@annotation(com.example.orders.aop.TrackExecution)")
```

Dạng đầu rất rộng; dạng sau chọn chính xác method được đánh dấu. Chọn biểu thức theo ý định và ranh giới kiến trúc.

### 28.3. Bảo toàn return và exception

Với advice quan sát, nên:

```java
try {
    return pjp.proceed();
} finally {
    // Ghi số đo hoặc cleanup.
}
```

Không đổi số lần thực thi target hay nuốt lỗi trừ khi đó là yêu cầu nghiệp vụ đã được định nghĩa rõ.

### 28.4. Cân nhắc performance và bảo mật

Advice áp dụng rộng có thể tạo overhead. Log arguments/results có thể chứa secrets và dữ liệu cá nhân. Dùng sampling, metrics, redaction và hệ thống monitoring phù hợp với production.

### 28.5. Làm rõ thứ tự và transaction

Vị trí interceptor trong chain ảnh hưởng phần thời gian được đo và transaction boundaries. Nếu thứ tự quan trọng, thể hiện bằng `@Order` và kiểm tra trong setup thực tế.

## 29. Bài tập thực hành

### Bài tập A — Xác định năm khái niệm

Cho:

```java
@Aspect
@Component
public class LoggingAspect {

    @Before("execution(* com.example.shop.service..*.*(..))")
    public void log(JoinPoint jp) {
        System.out.println(jp.getSignature().getName());
    }
}
```

Hãy chỉ ra aspect, advice, pointcut, join point và target khi `ProductService.findById(...)` được consumer gọi qua proxy.

### Bài tập B — Timing với @Around

Tạo `BookService.findById` và aspect timing. Gọi qua Spring-managed consumer. Cho method ném exception và quan sát khối `finally`.

### Bài tập C — Các loại advice

Tạo `@Before`, `@AfterReturning`, `@AfterThrowing` và `@After` trên một service method. So sánh lần gọi thành công với lần gọi ném exception.

### Bài tập D — Named pointcut

Tạo `@Pointcut("within(com.example.shop.service..*)")`, rồi tái sử dụng trong hai advice. Đổi package và kiểm tra phạm vi.

### Bài tập E — Annotation pointcut

Tạo `@TrackExecution` với runtime retention. Đánh dấu một method trong hai method của service và viết pointcut `@annotation(...)` chỉ áp dụng vào method đã đánh dấu.

### Bài tập F — Self-invocation

Tạo `outer()` gọi `inner()` trong cùng class. Gắn advice vào `inner()`. So sánh lời gọi từ bean consumer với lời gọi nội bộ; sau đó tách `inner` sang một Spring bean khác.

### Bài tập G — Proxy type

Tạo interface và implementation; dùng `AopUtils` kiểm tra JDK/class-based proxy. Giải thích tại sao `getThis()` và `getTarget()` không đồng nhất.

### Bài tập H — Order và nested advice

Tạo hai `@Around` aspects với `@Order(10)` và `@Order(20)`. Ghi các thông báo trước/sau để quan sát nesting.

### Bài tập I — Reactive timing

Tạo method trả `Mono<String>` và công việc reactive trì hoãn. So sánh thời gian quanh `proceed()` với thời gian hoàn tất reactive chain.

### Bài tập J — Debug lỗi không match

Cố tình tạo bean bằng `new`, hoặc tạo self-invocation, hoặc sai package trong execution pattern. Đề xuất chẩn đoán từ target/proxy/pointcut và sửa từng lỗi.

## 30. Ghi nhớ

1. **Aspect** đóng gói một concern cắt ngang.
2. **Advice** là hành vi chạy trước/sau/bao quanh method.
3. **Pointcut** là quy tắc chọn join points, ví dụ `execution(...)` và `@annotation(...)`.
4. **Join point trong Spring AOP** là method execution.
5. **Target object** chứa business logic; **proxy** đứng trước target để intercept lời gọi.
6. `@Before` trước method; `@AfterReturning` sau success; `@AfterThrowing` sau exception; `@After` kiểu finally; `@Around` có quyền bao quanh và tiếp tục lời gọi.
7. `ProceedingJoinPoint.proceed()` là bước tiếp tục interceptor chain; không gọi có thể bỏ qua target, gọi nhiều lần có thể lặp side effects.
8. `JoinPoint.getThis()` mô tả proxy, còn `getTarget()` mô tả target.
9. Pointcut matching chưa đủ: lời gọi phải đi qua proxy và method phải intercept được.
10. JDK dynamic proxy dựa trên interface; class-based proxy dựa trên subclass và bị giới hạn bởi final/private.
11. Self-invocation là nguyên nhân phổ biến khiến advice không được kích hoạt.
12. Nhiều aspects có thể chồng lên nhau; cấu hình order khi cần.
13. `@Transactional`, caching và async có thể sử dụng proxy nhưng cần hạ tầng riêng.
14. Đo thời gian quanh `proceed()` của reactive/async method không đồng nghĩa đo đến khi tác vụ hoàn tất.
15. Test AOP cần gọi thông qua Spring bean proxy, không chỉ gọi object tự tạo.
16. Aspect nên quan sát an toàn, hạn chế đổi return/exception và tránh log dữ liệu nhạy cảm.

**Tư duy cốt lõi:** khi đọc một đoạn AOP, hãy hỏi lần lượt: *Concern nào được tách thành aspect? Advice làm gì? Pointcut chọn phương thức nào? Join point nào thực sự được thực thi? Target object nào chứa nghiệp vụ? Và lời gọi có đi qua proxy hay không?* Trả lời được những câu hỏi này sẽ giúp bạn hiểu đúng lúc nào Spring AOP hoạt động và vì sao.
