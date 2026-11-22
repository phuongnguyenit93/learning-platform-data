# Spring AOP Pointcut: kết hợp điều kiện bằng `&&`, `||` và `!`

## 1. Mục tiêu và phạm vi

Khi cấu hình aspect trong **Spring AOP**, một biểu thức pointcut thường cần mô tả nhiều điều kiện cùng lúc: chỉ advice service trong một package, chọn hai nhóm method và loại bỏ phương thức nội bộ. Spring hỗ trợ kết hợp các pointcut expression bằng ba toán tử logic:

- `&&` — **AND (giao)**: tất cả điều kiện phải khớp.
- `||` — **OR (hợp)**: ít nhất một điều kiện khớp.
- `!` — **NOT (phủ định)**: loại bỏ các join point mà điều kiện phía sau khớp.

Ví dụ diễn đạt yêu cầu “advice method công khai thuộc service, có tên bắt đầu bằng create hoặc cancel, nhưng loại bỏ method kết thúc bằng Internal”:

```java
@Before(
    "within(demo.pointcuts.OrderService)"
  + " && execution(public * *(..))"
  + " && (execution(* create*(..)) || execution(* cancel*(..)))"
  + " && !execution(* *Internal(..))"
)
public void beforeOperation(JoinPoint joinPoint) {
    System.out.println("[advice] " + joinPoint.getSignature().getName());
}
```

Đây là fragment bên trong một class `@Aspect`. Các chuỗi được Java nối bằng `+` trước khi Spring phân tích thành một pointcut expression. Điều kiện trên là:

```text
Nằm trong OrderService
         AND
Là phương thức public
         AND
 (tên bắt đầu create OR tên bắt đầu cancel)
         AND
Tên không kết thúc bằng Internal
```

**Phạm vi bài:** đây là cú pháp pointcut được Spring AOP diễn giải bằng ngôn ngữ biểu thức AspectJ. Spring AOP dựa trên **proxy** và chỉ hỗ trợ các *method-execution join points* trên Spring-managed beans; không vì thêm toán tử logic mà trở thành bytecode weaving hay chặn được mọi lời gọi Java.

## 2. Hiểu ý nghĩa AND, OR, NOT ở thời điểm Spring chọn lời gọi

Gọi A, B, C là những điều kiện pointcut đã hợp lệ trên **một method execution mà Spring AOP có thể quan sát**:

| A | B | `A && B` | `A \|\| B` | `!A` |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

Trong bảng, `A \|\| B` dùng escape trong ô Markdown để không bị hiểu nhầm là dấu phân tách cột; biểu thức pointcut thật sự viết `A || B`.

### 2.1. `&&`: nhiều điều kiện phải cùng đúng

```java
@Pointcut("within(demo.pointcuts.OrderService)"
        + " && execution(public * *(..))")
private void publicOrderServiceMethods() {}
```

Điều này chỉ match method execution được xác định nằm trong `OrderService` **và** là public. Một public method ở service khác không khớp; một private helper cũng không trở thành Spring AOP advised method chỉ vì khai báo cùng class.

Ứng dụng thực tế:

- Giao điều kiện `execution(...)` với `within(package..*)` để giới hạn tầng service.
- Giao method pattern với `@annotation(...)` để chỉ advice những method được đánh dấu.
- Giao `bean(*Service)` với một method pattern khi muốn lọc theo tên Spring bean.

### 2.2. `||`: gom hai nhóm lời gọi

```java
@Pointcut("execution(* create*(..)) || execution(* cancel*(..))")
private void mutatingOperations() {}
```

Các method có tên bắt đầu `create` **hoặc** `cancel` có thể khớp, nếu chúng là những execution mà Spring proxy có thể intercept. Không phải cả hai điều kiện phải đồng thời đúng.

**Lưu ý:** `||` là OR logic, không phải “chạy advice hai lần”. Nếu cả hai vế cùng khớp, **một advice được khai báo một lần** trên biểu thức hợp vẫn chỉ được áp dụng như một advice cho một invocation; việc có nhiều advice độc lập là tình huống khác.

### 2.3. `!`: loại trừ một nhóm

```java
@Pointcut("execution(* demo.pointcuts.OrderService.*(..))"
        + " && !execution(* *Internal(..))")
private void publicApiExceptInternal() {}
```

Trong fragment này, vế phủ định loại những method có tên kết thúc bằng `Internal`. Tên `publicApiExceptInternal` chỉ là ví dụ tên method `@Pointcut`; phần `execution(* ...*)` đầu tiên **không tự giới hạn public**. Muốn chắc chắn chỉ public, thêm `&& execution(public * *(..))`.

Đây là nguyên tắc quan trọng: **phủ định không có nghĩa phép lọc security hoặc một “danh sách cấm tuyệt đối”**. `!B` chỉ là điều kiện logic trên tập những method execution nằm trong phạm vi Spring AOP, và có thể làm tập match rộng hơn nếu không gắn thêm điều kiện dương để giới hạn.

## 3. Dấu ngoặc và độ ưu tiên của toán tử

Trong cú pháp pointcut của AspectJ được Spring hỗ trợ, cách hiểu thông thường của các toán tử logic là:

1. `!` có độ ưu tiên cao nhất.
2. `&&` ưu tiên hơn `||`.
3. `||` có độ ưu tiên thấp nhất.

Vì vậy, các biểu thức sau **khác nhau**:

```text
A || B && C
```

tương đương:

```text
A || (B && C)
```

nhưng không tương đương:

```text
(A || B) && C
```

**Hệ quả dễ mắc:** nếu muốn “(create hoặc cancel) và không phải Internal”, hãy viết:

```java
@Pointcut("(execution(* create*(..)) || execution(* cancel*(..)))"
        + " && !execution(* *Internal(..))")
private void allowedMutations() {}
```

Không nên dùng:

```java
@Pointcut("execution(* create*(..))"
        + " || execution(* cancel*(..))"
        + " && !execution(* *Internal(..))")
private void riskyMutations() {}
```

Vế sau được hiểu là **create OR (cancel AND NOT Internal)**. Method `createInternal()` vẫn khớp do nhánh `create*` ở bên trái `||` được chọn, mặc dù tên method kết thúc `Internal`. Dấu ngoặc tránh biến một điều kiện chung thành điều kiện chỉ áp dụng cho nhánh thứ hai.

### Bảng kiểm tra trường hợp loại trừ Internal

Giả sử `A = create*`, `B = cancel*`, `C = *Internal`:

| Method | A | B | C | `(A \|\| B) && !C` | `A \|\| (B && !C)` |
| --- | --- | --- | --- | --- | --- |
| `createOrder()` | true | false | false | true | true |
| `cancelOrder()` | false | true | false | true | true |
| `createInternal()` | true | false | true | **false** | **true** |
| `cancelInternal()` | false | true | true | false | false |
| `findOrder()` | false | false | false | false | false |

Bảng này mô tả **điều kiện tên method**. Trong ứng dụng Spring AOP, lời gọi còn cần đi qua Spring-managed bean proxy và phù hợp với các điều kiện khác.

**Khuyến nghị:** luôn thêm dấu ngoặc khi phối hợp `||` với `&&` hoặc `!`, ngay cả khi đã nhớ độ ưu tiên. Nó khiến ý định rõ ràng khi review hoặc sửa pointcut sau này.

## 4. Kết hợp các pointcut designator của Spring

Ba toán tử logic được đặt **giữa các biểu thức pointcut hoặc các named pointcut**, không viết vào chữ ký method Java thông thường. Những pointcut designator Spring AOP thường dùng gồm:

| Designator | Điều kiện được diễn giải trong Spring AOP | Ví dụ |
| --- | --- | --- |
| `execution(...)` | Chữ ký method execution | `execution(public * demo.shop..*Service.*(..))` |
| `within(...)` | Loại/type trong phạm vi thực thi | `within(demo.shop.service..*)` |
| `this(...)` | Type của **Spring AOP proxy** | `this(demo.shop.OrderOperations)` |
| `target(...)` | Type của **target object** | `target(demo.shop.OrderService)` |
| `args(...)` | Kiểu runtime của argument | `args(java.lang.String)` |
| `@annotation(...)` | Annotation của method execution | `@annotation(demo.shop.Audited)` |
| `@within(...)`, `@target(...)` | Annotation liên quan type/target | `@within(demo.shop.Secured)` |
| `bean(...)` | Tên Spring bean (phần mở rộng của Spring) | `bean(*Service)` |

Dưới đây là các tổ hợp **minh họa**; class hoặc annotation được nhắc tới phải thật sự tồn tại trong ứng dụng.

**Chọn API service công khai trong package:**

```java
@Pointcut("execution(public * demo.shop.service..*.*(..))"
        + " && !execution(* demo.shop.service..*.healthCheck(..))")
void serviceApiExceptHealthCheck() {}
```

**Chọn method có annotation trong một type cụ thể:**

```java
@Pointcut("within(demo.shop.OrderService)"
        + " && @annotation(demo.shop.Audited)")
void auditedOrderMethod() {}
```

**Chọn một trong hai nhóm operation nhưng không phải bean thử nghiệm:**

```java
@Pointcut("(execution(* *Service.save*(..))"
        + " || execution(* *Service.delete*(..)))"
        + " && !bean(test*Service)")
void productionWriteOperations() {}
```

`bean(...)` là Spring-specific pointcut designator, có thể lọc theo tên bean chứa wildcard. Ví dụ tên `test*Service` chỉ là quy ước; nếu không có bean cùng tên, vế phủ định không loại gì. Đừng dùng logic tên bean làm cơ chế security; pointcut vốn là cách chọn lời gọi advice.

### Chú ý `this` và `target` khi phối hợp

Với JDK dynamic proxy:

- `this(demo.shop.OrderOperations)` có thể khớp vì proxy triển khai interface.
- `this(demo.shop.OrderService)` có thể **không** khớp nếu proxy JDK không phải subclass của implementation.
- `target(demo.shop.OrderService)` có thể khớp vì target object là implementation class.

Do đó, `execution(...) && this(...)` và `execution(...) && target(...)` có thể chọn tập method khác nhau. Nên viết pointcut theo interface/target một cách chủ đích và test trên **loại proxy thực tế**.

## 5. Named pointcut: cách tổ chức biểu thức phức tạp

Spring khuyến nghị ghép các pointcut nhỏ, được đặt tên rõ ràng. Thay vì một chuỗi `@Before` dài khó bảo trì, tạo những method `@Pointcut` **không có logic Java**:

```java
@Aspect
@Component
public class PolicyAspect {
    @Pointcut("within(demo.pointcuts.OrderService)")
    private void orderServiceType() {}

    @Pointcut("execution(public * *(..))")
    private void publicMethod() {}

    @Pointcut("execution(* create*(..))")
    private void createOperation() {}

    @Pointcut("execution(* cancel*(..))")
    private void cancelOperation() {}

    @Pointcut("execution(* *Internal(..))")
    private void internalOperation() {}

    @Pointcut("orderServiceType() && publicMethod()")
    private void servicePublicMethod() {}

    @Before("servicePublicMethod()"
          + " && (createOperation() || cancelOperation())"
          + " && !internalOperation()")
    public void before(JoinPoint jp) {
        System.out.println("[advice] " + jp.getSignature().getName());
    }
}
```

Đây là fragment class, chưa gồm imports/package; ví dụ đầy đủ ở mục 7.

Cách đọc:

- `servicePublicMethod()` là một **named pointcut**, không phải Java method thực sự chạy khi business method được gọi.
- `createOperation() || cancelOperation()` là **hợp hai tập match**.
- `!internalOperation()` **loại** cả `createInternal()` và `cancelInternal()`.
- Advice `before(...)` chỉ chạy khi toàn bộ điều kiện cuối match một invocation qua Spring AOP proxy.

Khi tham chiếu named pointcut ở **cùng aspect class**, cú pháp `servicePublicMethod()` là đủ. Khi chia sẻ từ class khác, dùng tên fully qualified phù hợp và đảm bảo method pointcut có **visibility Java** cho phép tham chiếu (ví dụ public). Visibility của method `@Pointcut` chỉ điều khiển khả năng tham chiếu nó trong source, không làm tập method matched thay đổi.

Nếu biểu thức có tham số binding như `args(orderId)` hay `@annotation(audited)`, pointcut method và advice method cần khai báo/bind tên tham số tương thích; toán tử logic không tự truyền Java method arguments vào advice. Ví dụ minh họa:

```java
@Pointcut("execution(* demo.shop.OrderService.submit(..)) && args(orderId)")
private void submitOrder(String orderId) {}

@Before("submitOrder(orderId)")
public void beforeSubmit(String orderId) {
    System.out.println(orderId);
}
```

Đây là fragment, cần class `demo.shop.OrderService` và cấu hình biên dịch giữ parameter names hoặc khai báo tên binding rõ ràng khi cần. Với `||` và parameter binding, hai nhánh phải thống nhất binding cần thiết; không tham chiếu biến chỉ có ở một nhánh rồi giả định nhánh kia cũng truyền biến đó.

## 6. Phạm vi mà toán tử logic **không** thay đổi

### 6.1. Chỉ method execution trên Spring AOP proxy

Dù biểu thức là `A && B`, `A || B` hay `!A`, Spring AOP vẫn chỉ thấy các method-execution join points có thể intercept bằng proxy. Các pointcut designator như `call`, `get`, `set`, `initialization`, `cflow` không được Spring AOP proxy hỗ trợ như trong full AspectJ weaving.

Một biểu thức phủ định như `!execution(* privateHelper(..))` **không** biến private method thành advised method: Spring proxy đã không thể intercept lời gọi đó từ đầu. Tương tự, static calls không đi qua instance proxy.

### 6.2. Self-invocation vẫn bypass advice

```java
@Service
class OrderService {
    public void runBatch() {
        this.createOrder(); // Gọi trực tiếp target, bypass Spring AOP proxy.
    }

    public void createOrder() {
        // ...
    }
}
```

Đây là fragment minh họa. Dù `createOrder()` phù hợp `execution(* create*(..))`, lời gọi `this.createOrder()` bên trong target không đi qua proxy. Việc mở rộng `||` hoặc phủ định `!` không giải quyết được self-invocation. Nên đặt boundary ở một Spring bean khác và inject dependency nếu operation thực sự cần advice riêng.

### 6.3. Không tạo proxy chỉ vì viết `@Pointcut`

Method `@Pointcut` định nghĩa **điều kiện**. Để có proxy/interceptor còn cần:

1. Spring quản lý target bean.
2. Aspect được đăng ký thành Spring bean (ví dụ `@Aspect @Component`).
3. Hạ tầng Spring AOP được bật: `@EnableAspectJAutoProxy` trong Spring Framework thuần hoặc auto-configuration thích hợp.
4. Có một advice thực sự tham chiếu pointcut và phù hợp target.
5. Consumer gọi bean thông qua **tham chiếu proxy**.

Nếu một trong các yếu tố đó thiếu, việc viết biểu thức logic hợp lệ vẫn có thể không tạo kết quả quan sát được.

## 7. Dự án Java 17 chạy được: chứng minh `&&`, `||`, `!` bằng log

Ví dụ chạy bằng **Java 17, Maven và Spring Framework 6.2.x** (không cần Spring Boot). Có một Spring-managed `OrderService` với những method có tên khác nhau; Spring tự tạo AOP proxy khi advisor match. Aspect dùng named pointcuts để kết hợp các điều kiện.

### 7.1. Cấu trúc thư mục

```text
spring-pointcut-operators/
├── pom.xml
└── src/main/java/demo/pointcuts/
    ├── AppConfig.java
    ├── OrderService.java
    ├── PolicyAspect.java
    └── Main.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-pointcut-operators</artifactId>
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

`spring-context` cung cấp IoC/annotation context, `spring-aop` hỗ trợ proxy/advisor, và `aspectjweaver` giúp Spring phân tích các biểu thức @AspectJ. Không cần áp dụng AspectJ compile-time hay load-time weaving trong ví dụ.

### 7.3. `AppConfig.java`

```java
package demo.pointcuts;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

`@EnableAspectJAutoProxy` bật hạ tầng AOP; `@ComponentScan` phát hiện service/aspect. Target ví dụ không khai báo interface nên Spring sẽ chọn class-based proxy cho nó. Việc dùng `&&`/`||`/`!` là độc lập với lựa chọn JDK proxy hay CGLIB, nhưng lời gọi được intercept vẫn phải đi qua proxy.

### 7.4. `OrderService.java`

```java
package demo.pointcuts;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public void createOrder() {
        System.out.println("[service] createOrder");
    }

    public void cancelOrder() {
        System.out.println("[service] cancelOrder");
    }

    public void createInternal() {
        System.out.println("[service] createInternal");
    }

    public void findOrder() {
        System.out.println("[service] findOrder");
    }

    public void batch() {
        System.out.println("[service] batch");
        this.createOrder(); // Self-invocation: không qua AOP proxy.
    }
}
```

Nhóm method: `createOrder` và `cancelOrder` được phép; `createInternal` bị phủ định; `findOrder` không thuộc create/cancel; `batch` dùng để minh họa self-invocation.

### 7.5. `PolicyAspect.java`

```java
package demo.pointcuts;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class PolicyAspect {
    @Pointcut("within(demo.pointcuts.OrderService)")
    private void inOrderService() {}

    @Pointcut("execution(public * *(..))")
    private void publicMethods() {}

    @Pointcut("execution(* create*(..))")
    private void createMethods() {}

    @Pointcut("execution(* cancel*(..))")
    private void cancelMethods() {}

    @Pointcut("execution(* *Internal(..))")
    private void internalMethods() {}

    @Pointcut("inOrderService() && publicMethods()")
    private void orderPublicApi() {}

    @Before("orderPublicApi()"
          + " && (createMethods() || cancelMethods())"
          + " && !internalMethods()")
    public void beforeAllowedOperation(JoinPoint joinPoint) {
        System.out.println("[advice] "
                + joinPoint.getSignature().getName());
    }
}
```

Spring gọi advice khi method execution **thuộc `OrderService`**, **public**, tên **bắt đầu create hoặc cancel**, và **không kết thúc bằng Internal**.

Các method `@Pointcut` không được tự gọi như logic Java nghiệp vụ. Chúng là các định nghĩa mang tên để pointcut expression tham chiếu. `@Component` đăng ký aspect bean; nếu chỉ có `@Aspect` mà không đăng ký bean, Spring component scan không nhất thiết phát hiện aspect.

### 7.6. `Main.java`

```java
package demo.pointcuts;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService orders = context.getBean(OrderService.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(orders));
            orders.createOrder();
            orders.cancelOrder();
            orders.createInternal();
            orders.findOrder();
            orders.batch();
        }
    }
}
```

Lệnh chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.pointcuts.Main
```

**Dòng stdout do chương trình in** (bỏ qua log của Maven hoặc Spring nếu có):

```text
isAopProxy=true
[advice] createOrder
[service] createOrder
[advice] cancelOrder
[service] cancelOrder
[service] createInternal
[service] findOrder
[service] batch
[service] createOrder
```

Giải thích chính xác:

1. `isAopProxy=true` cho thấy Spring cấp proxy khi advisor áp dụng cho các method.
2. `createOrder()` match `createMethods()`, không match `internalMethods()`; advice chạy trước service.
3. `cancelOrder()` match vế `cancelMethods()`; advice chạy trước service.
4. `createInternal()` match `createMethods()` **nhưng** cũng match `internalMethods()`, nên `!internalMethods()` là false; không có advice.
5. `findOrder()` không match vế `create || cancel`; không có advice.
6. `batch()` không match `create/cancel`; không có advice cho chính method `batch()`.
7. Bên trong `batch()`, target gọi `this.createOrder()` trực tiếp; dù chữ ký method có thể khớp, **không đi qua Spring AOP proxy**, nên lần `createOrder()` này không in dòng advice.

### 7.7. Thử nghiệm: bỏ ngoặc gây match sai

Giữ các named pointcuts như trên, thay biểu thức advice bằng:

```java
@Before("orderPublicApi() && createMethods()"
      + " || cancelMethods() && !internalMethods()")
```

Đây là **fragment thay thế annotation**; trong thực tế nên nhóm các điều kiện chung lại để không vô tình mở rộng phạm vi. Vế `orderPublicApi()` không còn áp dụng cho toàn bộ nhánh `cancelMethods()`. Điều kiện được hiểu theo kiểu:

```text
(orderPublicApi AND createMethods)
OR
(cancelMethods AND NOT internalMethods)
```

Thậm chí `createInternal()` có thể được advice trở lại qua nhánh create vì `!internalMethods()` chỉ còn kiểm soát nhánh cancel. Nếu có bean khác trong context với method `cancel*`, vế thứ hai còn có nguy cơ chọn cả bean đó khi không bị khóa bởi `inOrderService()`.

Sửa bằng cách luôn đặt **toàn bộ phần OR trong ngoặc** rồi mới giao với các điều kiện chung:

```java
@Before("orderPublicApi()"
      + " && (createMethods() || cancelMethods())"
      + " && !internalMethods()")
```

### 7.8. Thử nghiệm: thay phủ định bằng điều kiện dương sai

Đổi `!internalMethods()` thành `internalMethods()`:

```java
@Before("orderPublicApi()"
      + " && (createMethods() || cancelMethods())"
      + " && internalMethods()")
```

Khi đó chỉ method tên create/cancel **và** kết thúc bằng Internal mới match. Với service trên, `createInternal()` được advice, còn `createOrder()` và `cancelOrder()` bị loại. Đây là cách kiểm chứng ý nghĩa phủ định của `!`, không phải lỗi Spring proxy.

## 8. Viết biểu thức trong annotation, XML và cấu hình khác

### 8.1. Trong Java annotation

```java
@Before("execution(* demo.pointcuts..*Service.create*(..))"
      + " && !execution(* demo.pointcuts..*Service.createInternal(..))")
public void beforeCreate() {
    // Advice.
}
```

`&&`, `||`, `!` được đặt **trong Java String** như trên. Không viết `&amp;&amp;` trong Java string; đó là escape của XML/HTML, không phải cú pháp cần cho annotation.

### 8.2. Trong Spring AOP XML

Ví dụ **fragment** AOP namespace:

```xml
<aop:config>
    <aop:pointcut
        id="safeCreate"
        expression="execution(* demo.pointcuts..*Service.create*(..)) and
                    !execution(* demo.pointcuts..*Service.createInternal(..))"/>
</aop:config>
```

Trong XML, dấu `&` là ký tự đặc biệt trong **attribute**, nên nếu dùng ký hiệu `&&` thì phải ghi `&amp;&amp;` để XML parser hiểu đúng:

```xml
<aop:pointcut
    id="safeCreate"
    expression="execution(* demo.pointcuts..*Service.create*(..))
                &amp;&amp; !execution(* demo.pointcuts..*Service.createInternal(..))"/>
```

Đây là các fragment, không phải file XML Spring application context hoàn chỉnh. Viết `and` và `or` như các từ khóa logic thường dễ đọc hơn trong XML, nhưng cần phân biệt biến thể cú pháp của nơi cấu hình. XML chưa được escape `&` có thể gây lỗi parse trước khi Spring AOP kịp xét pointcut.

### 8.3. Biểu thức được tạo từ properties/config text

Nếu application đọc một expression từ cấu hình riêng để cấp vào API Spring AOP, phải biết **lớp parser** nào nhận expression và cách escape của định dạng bao ngoài (XML, YAML, Java, properties). Toán tử pointcut khác với cú pháp ngôn ngữ của file chứa nó. Không coi một chuỗi hợp lệ trong `@Before(...)` đương nhiên là literal hợp lệ trong mọi loại file.

## 9. Những lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `createInternal()` vẫn được advice dù có `!internalMethods()` | Viết `A || B && !C` thay vì `(A || B) && !C` | Nhóm OR bằng dấu ngoặc |
| Advice chạy trên bean ngoài phạm vi mong muốn | `within(...)` đặt chỉ trong một nhánh OR | Đưa điều kiện phạm vi **ra ngoài** nhóm OR và nối bằng `&&` |
| Không có advice cho mọi method | Dùng `&&` giữa các điều kiện loại trừ nhau | Cân nhắc `||` khi ý định là hợp |
| Match quá nhiều method | Chỉ viết `!execution(...)` | Kèm điều kiện dương `execution(...) && within(...)` để giới hạn |
| Pointcut expression hợp lệ nhưng không có proxy | Aspect chưa đăng ký Spring bean hoặc không advisor nào khớp | Kiểm tra `@Aspect @Component`, auto-proxy và AOP advisor |
| XML báo lỗi parse `&` | Ghi `&&` nguyên văn trong attribute | Đổi sang `&amp;&amp;` hoặc dùng biểu thức từ khóa phù hợp |
| Spring ném lỗi unsupported pointcut | Dùng `call`, `get`, `set`, `cflow` hoặc designator ngoài phạm vi | Dùng designator được Spring AOP hỗ trợ, thường là `execution` |
| Method `this.createOrder()` không có advice | Self-invocation bypass proxy | Tách method cần advice sang Spring bean khác |
| Method private/static được pointcut “match trên giấy” | Spring proxy không intercept lời gọi đó | Chuyển policy sang public method trên bean proxy |
| `this(ImplementationClass)` không khớp với JDK proxy | `this` kiểm tra proxy, không phải target | Dùng interface phù hợp, hoặc `target(ImplementationClass)` có cân nhắc |
| `@annotation(...)` không khớp như dự kiến | Annotation đặt khác vị trí hoặc kiểu method/proxy ảnh hưởng lookup | Kiểm tra annotation trên method thực thi và test integration |
| Đổi tên named pointcut nhưng advice không chạy | Method tham chiếu sai tên/signature/visibility | Đảm bảo `@Pointcut` tồn tại, đúng tên và có thể tham chiếu |

**Checklist rà soát khi viết pointcut ghép:**

1. Ghi yêu cầu nghiệp vụ thành câu: “chỉ trong …; chọn A hoặc B; loại C”.
2. Viết theo cấu trúc `SCOPE && (A || B) && !C`, thay vì dồn toàn bộ vào một chuỗi chưa nhóm.
3. Khi điều kiện dài, đặt tên `@Pointcut` nhỏ, rõ và dùng lại được.
4. Kiểm tra thứ tự ưu tiên bằng bảng ví dụ **được chọn / bị loại** ít nhất 4–5 phương thức.
5. Bảo đảm target/aspect đã được Spring quản lý; caller gọi thông qua proxy.
6. Kiểm tra giới hạn JDK/CGLIB, self-invocation và method visibility.
7. Trong XML, escape ký tự `&` và kiểm tra định dạng file trước khi debug logic AOP.
8. Thêm integration test xác nhận method mục tiêu có advice, method bị phủ định không có advice.

## 10. Câu hỏi ôn tập

**1. Khác biệt giữa `A && B` và `A || B`?** Giao yêu cầu cả hai đúng, hợp yêu cầu ít nhất một đúng trên method execution được xét.

**2. `!internalMethods()` có làm Spring chặn private methods không?** Không. Nó chỉ phủ định điều kiện lọc; khả năng intercept phụ thuộc Spring proxy và phạm vi method-execution join point.

**3. `A || B && !C` có giống `(A || B) && !C` không?** Không. Biểu thức đầu được hiểu như `A || (B && !C)`; nhánh A thoát khỏi điều kiện phủ định C.

**4. Vì sao dùng named pointcuts?** Để tách điều kiện nhỏ, tái sử dụng, tránh lặp chuỗi và làm điểm giao/hợp/phủ định rõ ràng.

**5. Viết `&&` trong XML attribute như thế nào?** Cần escape thành `&amp;&amp;`, hoặc dùng dạng biểu thức từ khóa phù hợp; trong Java string dùng `&&` trực tiếp.

**6. Có thể dùng `@Before("A() || B()")` để chạy hai lần advice nếu cả A, B khớp không?** Không. Một advice declaration dùng một biểu thức OR được xét như một điều kiện match; nếu match thì áp dụng advice đó cho invocation.

**7. Vì sao `this.createOrder()` không chạy advice dù thỏa mọi điều kiện tên method?** Vì lời gọi nội bộ trực tiếp trên target bỏ qua Spring AOP proxy.

## Tài liệu Spring chính thức

- [Spring Framework — Declaring a Pointcut, Combining Pointcut Expressions](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Pointcut API (union/intersection)](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html)
