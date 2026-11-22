# Giữ pointcut ổn định khi đổi gói, tên lớp hoặc tên phương thức trong Spring AOP

## 1. Vì sao refactor dễ làm Spring Aspect ngừng hoạt động?

Trong Spring AOP, nhiều pointcut được viết dưới dạng **chuỗi biểu thức** bên trong `@Pointcut`, `@Before`, `@Around`... Chẳng hạn:

```java
@Before("execution(* com.example.orders.OrderService.submit(..))")
public void auditSubmission() {
    // ...
}
```

Biểu thức này phụ thuộc vào **tên package**, **tên class** và **tên method**. Khi đội phát triển refactor:

- `com.example.orders` chuyển sang `com.example.fulfillment`.
- `OrderService` đổi thành `FulfillmentCoordinator`.
- `submit()` đổi thành `dispatch()`.

Java source code của bean và caller có thể được IDE cập nhật để vẫn **biên dịch thành công**, nhưng chuỗi pointcut có thể **không được cập nhật tương ứng**. Kết quả nguy hiểm nhất là: ứng dụng vẫn chạy nghiệp vụ bình thường, trong khi Spring Aspect không còn áp dụng audit, metrics hoặc các chính sách dùng chung tại method mới.

Cần phân biệt hai tình huống:

1. **Biểu thức không hợp lệ:** Spring có thể báo lỗi khi parse pointcut/khởi tạo advisor, khiến application context không khởi động.
2. **Biểu thức vẫn hợp lệ nhưng không còn khớp:** Spring không nhất thiết báo lỗi. Bean có thể không được tạo proxy vì không còn advisor phù hợp, hoặc có proxy vì advisor khác nhưng advice đang quan tâm **không chạy**. Đây là nguy cơ mà integration test phải bắt.

Mục tiêu không phải viết một biểu thức sẽ tự hiểu **mọi refactor trong tương lai**. Mục tiêu là thiết kế **hợp đồng chọn join point rõ ràng, ít phụ thuộc chi tiết dễ đổi**, tập trung chỗ sửa và kiểm thử được.

**Giới hạn:** Bài này chỉ nói về **Spring Aspect và pointcut trong Spring proxy-based AOP**. Spring AOP hỗ trợ method execution trên Spring-managed beans; không dùng lời gọi Java thuần ngoài proxy hoặc AspectJ weaving làm đối tượng chính.

## 2. Mức độ phụ thuộc refactor của các loại pointcut

| Cách chọn method | Ví dụ | Khi đổi package | Khi đổi class | Khi đổi method | Đánh đổi |
| --- | --- | --- | --- | --- | --- |
| Tên đầy đủ cố định | `execution(* com.example.orders.OrderService.submit(..))` | Dễ mất match | Dễ mất match | Dễ mất match | Rất cụ thể nhưng brittle. |
| Package convention | `execution(public * com.example..service.*.*(..))` | Phụ thuộc cấu trúc package | Ít phụ thuộc tên class | Ít phụ thuộc tên method | Dễ ăn rộng hoặc bỏ sót package mới. |
| Stable interface contract | `target(com.example.api.OrderOperations)` | Bền hơn nếu interface giữ nguyên | Không buộc tên implementation | Không lọc riêng method | Cần API ổn định và điều kiện method bổ sung. |
| Annotation trên method | `@annotation(com.example.aop.MonitoredOperation)` | Không phụ thuộc package của target | Không phụ thuộc tên class target | Không phụ thuộc tên method target | Phải giữ annotation trên đúng method. |
| Annotation trên class | `@target(com.example.aop.MonitoredComponent)` | Không phụ thuộc package target | Không phụ thuộc tên class target | Chọn tập method rộng nếu không kết hợp điều kiện khác | Hợp đồng ở cấp class. |
| Bean-name convention | `bean(*Service)` | Có thể không bị ảnh hưởng | Phụ thuộc tên bean thực tế | Không lọc riêng method | Spring-specific, phụ thuộc bean naming. |
| Named pointcut | `@Pointcut("...") void businessOperation() {}` | Tập trung nơi sửa | Tập trung nơi sửa | Tập trung nơi sửa | Tự nó **không** làm nội dung expression bất biến. |

Không có công thức nào luôn tốt nhất. Nếu chính sách thật sự chỉ áp dụng riêng một method cụ thể, việc đổi tên method có thể **cần** cập nhật pointcut; đó là thay đổi có chủ đích. Nếu chính sách áp dụng cho một **vai trò nghiệp vụ ổn định**, chọn theo annotation, interface hoặc convention rõ nghĩa thường bền hơn so với tên class cụ thể.

**Một named pointcut chỉ giảm số nơi phải chỉnh sửa.** Ví dụ `@Pointcut("execution(* OldService.save(..))")` vẫn bị ảnh hưởng khi `OldService` đổi tên, dù 10 advice cùng dùng `businessSave()`.

## 3. Chiến lược nền tảng: đặt tên cho ý định, không cho cú pháp

Spring Framework khuyến nghị ghép các biểu thức phức tạp từ những **named pointcuts nhỏ**. Một class chia sẻ thường có ba lớp ý nghĩa:

```text
publicMethod()           -> method signature phù hợp
inBusinessLayer()        -> ranh giới module/kiểu bean
businessOperation()      -> vai trò nghiệp vụ dùng cho aspect

businessOperation() = publicMethod() && inBusinessLayer()
```

Ví dụ:

```java
package com.example.aop;

import org.aspectj.lang.annotation.Pointcut;

public class CommonPointcuts {

    @Pointcut("execution(public * *(..))")
    public void publicMethod() {}

    @Pointcut("within(com.example..service..*)")
    public void inServiceLayer() {}

    @Pointcut("publicMethod() && inServiceLayer()")
    public void serviceOperation() {}
}
```

Đây là Java class khai báo pointcuts; **không cần tạo `@Bean` của `CommonPointcuts`** chỉ để các aspect khác tham chiếu tên pointcut.

Trong aspect khác:

```java
@Before("com.example.aop.CommonPointcuts.serviceOperation()")
public void beforeService() {
    // ...
}
```

Lợi ích: khi di chuyển package service, chỉ sửa `inServiceLayer()` tại một nơi. Các advice sử dụng `serviceOperation()` giữ nguyên tên và vai trò.

Hạn chế: nếu package mới **không** còn thuộc `com.example..service..`, `inServiceLayer()` vẫn bỏ sót method cho đến khi bạn sửa expression. **Đặt tên không tạo tính ổn định tự động; nó tạo một điểm quản trị tập trung.**

Một lưu ý Java visibility: pointcut method `private` đủ dùng trong cùng aspect; pointcut chia sẻ giữa nhiều class nên `public`. Visibility quyết định **nơi được tham chiếu**, không quyết định target method được match có `public` hay không. Muốn chỉ match public target methods phải viết `execution(public ...)` trong expression.

## 4. Chiến lược annotation: gắn chính sách với ý nghĩa của method

Khi một chính sách audit/metrics cần tiếp tục áp dụng dù đội phát triển đổi tên package, class hoặc method, một **annotation có ý nghĩa** trên method có thể là hợp đồng ổn định:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface MonitoredOperation {
}
```

Và Spring aspect:

```java
@Pointcut(
    "execution(public * *(..))"
    + " && @annotation(com.example.aop.MonitoredOperation)"
)
public void monitoredOperation() {}
```

Đây là **các fragments** cần imports/package và Spring bean registration; project runnable ở phần 8 cung cấp phiên bản đầy đủ.

Giả sử:

```java
@MonitoredOperation
public String submit(String id) { /* ... */ }
```

được refactor thành:

```java
@MonitoredOperation
public String dispatch(String id) { /* ... */ }
```

Nếu annotation vẫn hiện diện trên method mới và method vẫn có thể được gọi qua Spring proxy, pointcut `@annotation(MonitoredOperation)` không phụ thuộc vào hai tên `submit` và `dispatch`.

### 4.1. Annotation là contract, không phải phép màu

Annotation marker chỉ có tác dụng nếu:

1. Annotation có **`@Retention(RetentionPolicy.RUNTIME)`** nếu cơ chế matching cần metadata runtime.
2. Marker được đặt ở **method/class thích hợp** và được duy trì khi refactor.
3. Aspect có `@Pointcut`/`@Before` hợp lệ, được đăng ký thành Spring bean trong context đang xử lý target.
4. Target là Spring bean và lời gọi đi qua AOP proxy.
5. Method nằm trong giới hạn có thể chặn của Spring proxy (JDK interface contract hoặc CGLIB subclassing theo cấu hình).

Nếu developer **xóa marker** khi đổi tên method, Spring không thể đoán rằng method mới vẫn phải được audit. Vì vậy annotation phải trở thành một phần của **review checklist và integration tests**.

Nếu annotation được khai báo trên interface method nhưng implementation method không có marker, việc có match hay không cần được kiểm tra theo loại proxy, cách Spring/AspectJ lấy metadata và phiên bản framework. **Không mặc định annotation method luôn được kế thừa từ interface.** Java `@Inherited` dành cho annotation trên class và không tạo tính kế thừa cho method annotations. Đối với policy quan trọng, nên có một quy ước đặt marker rõ ràng và test trên bean/proxy thật.

### 4.2. Dùng `@target` hay `@within` khi scope theo class?

Nếu policy áp dụng cho **mọi public method của một class có vai trò nhất định**, có thể dùng annotation ở **cấp class**:

```java
@Pointcut(
    "execution(public * *(..))"
    + " && @target(com.example.aop.MonitoredComponent)"
)
public void monitoredComponentOperation() {}
```

- `@annotation(...)` chọn method có annotation phù hợp.
- `@target(...)` chọn theo annotation trên class của **target object**.
- `@within(...)` chọn join points trong những type có annotation phù hợp; trong Spring AOP cần chú ý type/method đang được kiểm tra.
- `target(SomeInterface)` chọn target tương thích interface hoặc type, **không dựa vào annotation**.

Các designators đều thuộc phạm vi được Spring AOP hỗ trợ, nhưng **không thay thế nhau**. Nếu chỉ một vài method cần audit, method-level `@annotation` thường chính xác hơn type-level annotation vốn chọn rộng hơn.

### 4.3. Giữ annotation package ổn định

Dùng `@annotation(com.example.aop.MonitoredOperation)` loại phụ thuộc vào package của **target**, nhưng lại giới thiệu sự phụ thuộc mới vào **FQCN của annotation type**. Vì vậy:

- Đặt annotation policy ở package/module API ổn định, ví dụ `com.example.platform.aop`.
- Giữ tên và semantic của annotation rõ ràng; tránh đổi annotation theo từng refactor service.
- Khi phải đổi annotation type/package, sửa expression tương ứng và chạy lại integration tests.
- Không trộn tên annotation vào code domain nếu policy thuần kỹ thuật và kiến trúc yêu cầu domain module không phụ thuộc hạ tầng; khi đó cân nhắc stable interface contract hoặc convention khác.

**Tính bền vững là chọn thứ ít biến động để làm hợp đồng**, chứ không thể loại bỏ mọi phụ thuộc.

## 5. Chiến lược interface: bám contract thay vì class triển khai

Khi application đã có **business interface ổn định**:

```java
public interface PaymentOperations {
    Receipt process(PaymentRequest request);
}
```

Có thể viết pointcut dựa vào **type contract**:

```java
@Pointcut(
    "execution(public * *(..))"
    + " && target(com.example.api.PaymentOperations)"
)
public void paymentApiOperation() {}
```

Đây là fragment trong aspect; cần class interface tồn tại trong ứng dụng.

`target(PaymentOperations)` trong Spring AOP xét **target object** có thuộc type contract đó không. Vì vậy đổi concrete implementation `LegacyPaymentService` thành `NewPaymentCoordinator` vẫn có thể giữ match nếu hai class implement cùng interface và bean proxy hoạt động bình thường.

Nhưng có hai ranh giới:

1. **Nếu đổi chính interface FQCN**, pointcut vẫn phải sửa. Đặt contract ở API package ít biến động.
2. `target(PaymentOperations)` chọn các method executions phù hợp mà target thực hiện, **không chỉ `process`**. Nếu policy chỉ dành cho một subset, cần thêm điều kiện method hoặc marker.

Ví dụ:

```java
@Pointcut(
    "target(com.example.api.PaymentOperations)"
    + " && @annotation(com.example.aop.MonitoredOperation)"
)
public void monitoredPaymentOperation() {}
```

Khi kết hợp, interface giới hạn **đối tượng nhận chính sách**; annotation giới hạn **method mang ý nghĩa cần giám sát**.

### `this` và `target` trong Spring

Trong Spring AOP:

- `this(MyType)` xét **Spring proxy reference** có tương thích type hay không.
- `target(MyType)` xét **target object được proxy**.

Với JDK proxy theo interface, proxy không nhất thiết là instance của concrete implementation; do đó `this(ConcreteClass)` có thể khác `target(ConcreteClass)`. Khi refactor class/interface, phải xác định mục đích là chọn theo **proxy contract** hay theo **target type**. Đây là đặc thù của Spring proxy-based AOP cần kiểm thử trên proxy strategy thực tế.

## 6. Khi nào nên dùng naming convention theo package hoặc Spring bean name?

### 6.1. Package convention

Biểu thức:

```text
execution(public * com.example..service..*.*(..))
```

có ích nếu tổ chức có quy ước package **bền vững**, chẳng hạn mọi service đều nằm dưới các package `service` của module.

Ưu điểm: không cần đánh dấu từng method; đổi tên class/method trong package thường không ảnh hưởng match.

Điểm yếu:

- Chuyển class ra khỏi package thỏa pattern -> **âm thầm mất match**.
- Đặt một class không mong muốn vào package khớp -> **được advice ngoài dự kiến**.
- Nếu structure đổi từ layer-based sang feature-based (ví dụ `orders.application`), pattern cũ có thể không còn phù hợp.
- Broad wildcard có thể match các method không thuộc trách nhiệm thực tế của policy.

Cách cải thiện: dùng named pointcut `applicationServiceOperation()` tập trung expression, document package convention và thêm regression tests khi di chuyển module.

### 6.2. Spring-specific `bean(...)` pointcut

Spring AOP hỗ trợ `bean(namePattern)` để chọn theo **Spring bean name**, ví dụ:

```java
@Pointcut("bean(*Service) && execution(public * *(..))")
public void namedServiceOperation() {}
```

Đây là fragment trong Spring `@Aspect`. `bean` là **phần mở rộng Spring-specific**, chọn theo **bean instance name**, không dựa vào Java class FQCN. Nó hữu ích khi tên bean tuân thủ convention được kiểm soát.

Tuy nhiên, **đổi tên class có thể kéo theo đổi tên bean mặc định** trong component scanning:

```text
OrderService     -> bean name mặc định: orderService
OrderCoordinator -> bean name mặc định: orderCoordinator
```

Nếu pointcut dùng `bean(*Service)`, đổi class `OrderService` thành `OrderCoordinator` có thể khiến bean không còn match, dù class vẫn thực hiện nghiệp vụ cũ. Muốn convention bền hơn, khai báo bean name rõ ràng khi thật sự cần, hoặc dùng marker/interface contract.

`bean(...)` chỉ dành cho Spring AOP, **không phải AspectJ weaving pointcut designator chuẩn**. Không dựa vào `bean` nếu có kế hoạch chuyển cùng expression sang AspectJ weaving bên ngoài Spring.

### 6.3. So sánh điểm chịu tác động khi refactor

| Thao tác | Hard-coded `execution` FQCN | `within` package convention | `@annotation` policy marker | `target(StableApi)` | `bean(*Service)` |
| --- | --- | --- | --- | --- | --- |
| Đổi tên method | Dễ đứt match | Thường không ảnh hưởng | Không ảnh hưởng nếu giữ marker | Không ảnh hưởng nếu vẫn là method qua proxy | Thường không ảnh hưởng |
| Đổi tên implementation class | Dễ đứt match | Thường không ảnh hưởng | Không ảnh hưởng nếu giữ marker | Không ảnh hưởng nếu giữ interface | Có thể ảnh hưởng tên bean mặc định |
| Di chuyển package implementation | Dễ đứt match | Có thể đứt nếu ra ngoài pattern | Không ảnh hưởng nếu marker FQCN ổn định | Không ảnh hưởng nếu interface FQCN ổn định | Không ảnh hưởng khi bean name giữ nguyên |
| Chuyển policy sang method khác | Phải sửa expression | Dễ match quá rộng | Chủ động chuyển marker | Cần lọc method/marker thêm | Cần lọc method/marker thêm |
| Đổi chính annotation/interface/API | Không nhất thiết | Không nhất thiết | Phải cập nhật marker + expression | Phải cập nhật interface + expression | Không nhất thiết |

Cách đọc bảng: **“không ảnh hưởng” chỉ nói về text pattern**, không bảo đảm Spring AOP sẽ chạy nếu bean không còn do Spring quản lý hoặc lời gọi đi ngoài proxy.

## 7. Đừng dùng wildcard quá rộng chỉ để “sống sót qua refactor”

Một số lựa chọn tưởng là giải pháp:

```java
@Before("execution(* *(..))")
public void anyMethod() {}
```

hoặc:

```java
@Before("within(com.example..*)")
public void anyApplicationClassMethod() {}
```

Đây là fragments minh họa, không phải khuyến nghị áp dụng production.

Các điểm cần cảnh giác:

- Pattern rộng dễ áp dụng advisor lên những bean chưa từng có policy trước đây.
- Advice có thể xuất hiện ở những method không liên quan, làm tăng chi phí thực thi, logging volume và coupling.
- Policy bảo mật hoặc audit có thể vô tình đi vào infrastructure methods, dẫn đến hệ quả khó nhận biết.
- Nếu giữ chung với những dynamic conditions như `args(...)`, không đặt scope rõ còn có thể tăng chi phí matching trên nhiều beans.
- Một wildcard rất rộng không chứng minh nó “bền”: vẫn phụ thuộc **bean có đi qua proxy**, scope/context, method visibility và runtime mechanism.

Spring docs khuyến nghị **pointcut có scope đủ hẹp**, ưu tiên cấu thành bằng những named pointcuts có ý nghĩa. Khi dùng annotation marker ổn định trong nhiều package, biểu thức `execution(public * *(..)) && @annotation(Marker)` có thể hợp lý vì annotation đã là bộ lọc explicit. Nhưng phải kiểm tra annotation có bị dùng ngoài dự kiến và application có performance constraints hay không.

**Stability không đồng nghĩa với maximum match breadth.** Một refactor an toàn là refactor giữ nguyên **tập join points dự kiến**, không phải refactor làm advice chọn mọi thứ.

## 8. Ví dụ Java 17+ chạy được: class và method đổi tên, policy vẫn giữ

Ví dụ mô phỏng hai service thuộc **hai package khác nhau** và có **tên class/method khác nhau**:

- Service cũ: `com.example.orders.LegacyOrderService.submit()`.
- Service mới: `com.example.fulfillment.RenamedFulfillmentCoordinator.dispatch()`.
- Cả hai có method được đánh dấu `@MonitoredOperation`.
- Spring `@Aspect` dùng một **named pointcut có ý nghĩa** theo annotation, không hard-code hai tên class/method.
- Một method không mang marker là đối chứng âm: nó phải chạy nghiệp vụ **mà không chạy advice**.

Đây là mô phỏng *trước/sau refactor bằng hai service cùng tồn tại* để tiện so sánh, không phải yêu cầu triển khai song song hai implementation trên production.

Phiên bản project: Java 17+, Spring Framework **6.1.14**, `aspectjweaver` **1.9.22.1**, Maven. Các version này được cố định để học, **không tuyên bố là mới nhất**.

### 8.1. Cấu trúc thư mục

```text
spring-stable-pointcuts/
├── pom.xml
└── src/main/java/com/example/
    ├── aop/MonitoredOperation.java
    ├── aop/ObservationAspect.java
    ├── orders/LegacyOrderService.java
    ├── fulfillment/RenamedFulfillmentCoordinator.java
    └── app/AppConfig.java
    └── app/DemoApp.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-stable-pointcuts</artifactId>
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

`spring-context` mang các thành phần Spring IoC và dependency Spring AOP cần thiết trong cây phụ thuộc; `aspectjweaver` phục vụ việc Spring phân tích các `@AspectJ` pointcut expressions. Ví dụ sử dụng **Spring proxy-based AOP**, không có AspectJ compiler hoặc weaving agent.

### 8.3. `src/main/java/com/example/aop/MonitoredOperation.java`

```java
package com.example.aop;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface MonitoredOperation {
}
```

Marker có retention ở runtime và chỉ áp dụng cho method. Đặt tại package `com.example.aop` ổn định, thay vì đặt nó trong package của service dự kiến sẽ đổi.

### 8.4. `src/main/java/com/example/orders/LegacyOrderService.java`

```java
package com.example.orders;

import com.example.aop.MonitoredOperation;

public class LegacyOrderService {

    @MonitoredOperation
    public String submit(String id) {
        System.out.println("[ORDER] submit " + id);
        return "submitted:" + id;
    }

    public String preview(String id) {
        System.out.println("[ORDER] preview " + id);
        return "preview:" + id;
    }
}
```

`submit` mang marker; `preview` không mang marker. Hai method đều public và được gọi ngoài bean qua Spring AOP proxy trong ví dụ.

### 8.5. `src/main/java/com/example/fulfillment/RenamedFulfillmentCoordinator.java`

```java
package com.example.fulfillment;

import com.example.aop.MonitoredOperation;

public class RenamedFulfillmentCoordinator {

    @MonitoredOperation
    public String dispatch(String id) {
        System.out.println("[FULFILLMENT] dispatch " + id);
        return "dispatched:" + id;
    }
}
```

Class mới nằm ngoài `com.example.orders`, không còn tên `OrderService` và method không còn tên `submit`. **Chỉ policy marker được giữ**. Một pointcut cứng `execution(* com.example.orders.LegacyOrderService.submit(..))` sẽ không khớp method `dispatch()`; pointcut theo marker vẫn có thể khớp.

### 8.6. `src/main/java/com/example/aop/ObservationAspect.java`

```java
package com.example.aop;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class ObservationAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Pointcut("execution(public * *(..))")
    public void publicMethod() {}

    @Pointcut(
        "publicMethod()"
        + " && @annotation(com.example.aop.MonitoredOperation)"
    )
    public void monitoredOperation() {}

    @Before("monitoredOperation()")
    public void beforeMonitoredCall(JoinPoint jp) {
        calls.incrementAndGet();
        System.out.println("[AOP] " + jp.getSignature().getName());
    }

    public int calls() {
        return calls.get();
    }
}
```

**Điểm ổn định nằm ở đâu?**

- `publicMethod()` mô tả loại method Spring AOP cần chặn.
- `monitoredOperation()` đặt tên cho điều kiện business/technical policy: method được đánh dấu marker.
- `@Before("monitoredOperation()")` không chứa tên `LegacyOrderService`, `RenamedFulfillmentCoordinator`, `submit` hay `dispatch`.
- Khi đổi class/package/method, chỉ cần giữ annotation trên method mục tiêu và bảo đảm bean vẫn được proxy đúng.
- `JoinPoint.getSignature().getName()` in **tên method thật đã được gọi**; vì vậy trước refactor in `submit`, sau refactor in `dispatch` mà không cần đổi logic advice.

`ObservationAspect` là Spring bean singleton trong context vì được đăng ký ở `AppConfig`; counter `AtomicInteger` đo số lần advice, không đo số bean target hay số lần pointcut signature method được gọi.

### 8.7. `src/main/java/com/example/app/AppConfig.java`

```java
package com.example.app;

import com.example.aop.ObservationAspect;
import com.example.fulfillment.RenamedFulfillmentCoordinator;
import com.example.orders.LegacyOrderService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public LegacyOrderService legacyOrderService() {
        return new LegacyOrderService();
    }

    @Bean
    public RenamedFulfillmentCoordinator fulfillmentCoordinator() {
        return new RenamedFulfillmentCoordinator();
    }

    @Bean
    public ObservationAspect observationAspect() {
        return new ObservationAspect();
    }
}
```

`@EnableAspectJAutoProxy` bật Spring auto-proxy infrastructure; `proxyTargetClass=true` chọn CGLIB để demo inject/look up hai concrete service classes không implement interface. **Đây không phải điều kiện bắt buộc cho marker policy**: hệ thống có business interfaces vẫn có thể dùng JDK proxy với những điều chỉnh phù hợp.

Khi refactor một bean, code đăng ký `@Bean` hoặc component scanning cũng phải được cập nhật, nếu không bean mới chưa chắc có mặt trong context. Pointcut bền vững **không thể bù cho bean registration sai**.

### 8.8. `src/main/java/com/example/app/DemoApp.java`

```java
package com.example.app;

import com.example.aop.ObservationAspect;
import com.example.fulfillment.RenamedFulfillmentCoordinator;
import com.example.orders.LegacyOrderService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            LegacyOrderService oldService =
                    context.getBean(LegacyOrderService.class);
            RenamedFulfillmentCoordinator newService =
                    context.getBean(RenamedFulfillmentCoordinator.class);
            ObservationAspect aspect =
                    context.getBean(ObservationAspect.class);

            System.out.println("oldProxy="
                    + AopUtils.isAopProxy(oldService));
            System.out.println("newProxy="
                    + AopUtils.isAopProxy(newService));

            System.out.println("oldResult=" + oldService.submit("O-1"));
            System.out.println("previewResult=" + oldService.preview("O-2"));
            System.out.println("newResult=" + newService.dispatch("F-3"));

            System.out.println("adviceCalls=" + aspect.calls());
        }
    }
}
```

Hai bean đều được lookup từ `ApplicationContext` và gọi bằng references do Spring trả về. Không có `new` target trực tiếp trong caller và không có self-invocation làm nhiễu kết quả.

### 8.9. Lệnh chạy và stdout kỳ vọng

Yêu cầu JDK 17+, Maven tải được dependencies. Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.app.DemoApp
```

Các dòng do chương trình và advice in ra theo đúng thứ tự (không tính log Maven/Spring nếu môi trường có):

```text
oldProxy=true
newProxy=true
[AOP] submit
[ORDER] submit O-1
oldResult=submitted:O-1
[ORDER] preview O-2
previewResult=preview:O-2
[AOP] dispatch
[FULFILLMENT] dispatch F-3
newResult=dispatched:F-3
adviceCalls=2
```

Diễn giải:

1. Hai Spring beans có các marked methods nên auto-proxy creator đã tạo AOP proxies tương ứng.
2. `submit` được marker, advice chạy trước target.
3. `preview` không được marker, nên **không có dòng `[AOP]`** cho lời gọi đó dù `LegacyOrderService` đã là một proxy.
4. `dispatch` thuộc **class và package khác**, tên method cũng khác, nhưng marker giữ policy nên advice vẫn chạy.
5. `adviceCalls=2` chứng minh chỉ hai method được chọn; không phải cứ gọi mọi method trên một proxied bean thì advice chạy.
6. Nếu xóa `@MonitoredOperation` khỏi `dispatch` sau refactor, Spring có thể vẫn khởi động bình thường nhưng test **phải thất bại** khi kỳ vọng advice xuất hiện cho method mới.

Đây là thí nghiệm về **policy semantics tồn tại qua refactor**, không phải yêu cầu giữ hai service có vai trò tương tự trong cùng ứng dụng thực tế.

## 9. Phương án thay thế khi không muốn annotate từng method

Không phải codebase nào cũng muốn gắn custom annotation ở application/service code. Có ba chiến lược khác:

### 9.1. Dùng stable interface hoặc class annotation ở module API

Nếu nhiều implementations cùng tuân theo `BillingOperations`, dùng `target(com.example.api.BillingOperations)`. Khi đổi class implementation, pointcut có thể vẫn đúng.

Nếu policy áp dụng cho toàn bộ public methods của một bean class, annotation trên class + `@target` có thể giảm số marker so với annotate từng method.

Điểm cần kiểm tra: việc đổi interface/class annotation type, biến đổi bean scopes/proxy interfaces và số methods bị match có thể làm thay đổi tập join points.

### 9.2. Naming convention kèm test

Trong một kiến trúc module hóa ổn định, có thể chọn `execution(public * com.example..application.*.*(..))`. Quy tắc tổ chức package phải được ghi nhận thành contract và được enforce trong review, architecture tests hoặc code checks. Khi chuyển package khỏi pattern, test phải phát hiện thiếu advice.

Không nên để package name là một giả định ngầm mà chỉ người viết aspect ban đầu biết.

### 9.3. Explicit bean name cho Spring-specific selection

Một số ứng dụng muốn định danh một bean cụ thể bất kể implementation class:

```java
@Service("primaryBillingService")
public class BillingAdapter {
    // ...
}
```

Có thể kết hợp `bean(primaryBillingService)` với `execution(public * *(..))`. Nếu tiếp tục giữ Spring bean name ổn định trong refactor, đổi class/package không nhất thiết ảnh hưởng rule.

Đây là **fragments**, không phải project runnable. Chỉ phù hợp khi bean name thực sự là một phần contract được kiểm soát. Việc duplicate bean names hoặc nhiều aliases cần được xem xét; không coi `bean(...)` như giải pháp universal cho mọi aspect.

## 10. Thiết kế test để bắt regression khi refactor

Một test Spring AOP cần kiểm chứng **hành vi advice**, không chỉ application context load thành công. Nên có cả **positive** và **negative** cases.

### 10.1. Ma trận trước/sau

| Scenario | Trước refactor | Sau refactor | Kết quả advice mong đợi |
| --- | --- | --- | --- |
| Method có `@MonitoredOperation` | `LegacyOrderService.submit()` | `RenamedFulfillmentCoordinator.dispatch()` | Vẫn chạy 1 lần trên mỗi lời gọi qua proxy. |
| Method không có marker | `preview()` | Method tương đương không marker | Không chạy policy này. |
| Bean chuyển package | `orders` | `fulfillment` | Vẫn chạy nếu annotation/contract ổn định và bean được đăng ký. |
| Bean không còn thuộc Spring context | Trước: Spring-managed | Sau: instance `new` | Spring AOP không chạy; phải sửa kiến trúc bean boundary. |
| Method bị gọi qua `this` | Cross-bean call trước đây | Self-invocation sau refactor | Advice có thể bị bypass; test phát hiện. |
| Concrete method thành `final` trên class proxy | Method intercept được | CGLIB không override được | Test phải phát hiện thiếu interception hoặc lỗi proxying. |

Không cần kiểm tra mọi permutation của application nếu quá tốn kém. Nhưng **các method thực sự mang chính sách quan trọng** cần được đưa vào một tập regression tests có tên rõ ràng.

### 10.2. Test qua Spring proxy chứ không tạo target bằng `new`

Một test cần dùng:

```java
LegacyOrderService service = context.getBean(LegacyOrderService.class);
service.submit("T-1");
```

chứ không thay bằng:

```java
new LegacyOrderService().submit("T-1");
```

Đây là **fragments**. Trường hợp thứ hai chỉ kiểm tra logic target Java, **không chứng minh được gì về Spring AOP proxy**.

Nếu sử dụng JDK proxy, nên lookup/inject theo business interface thay vì concrete type, hoặc cấu hình class proxy có chủ đích. Đừng thay đổi kiểu proxy để làm test “xanh” mà không xét hợp đồng injection của production.

### 10.3. Kiểm tra chính xác số lần và scope lời gọi

Một integration test có thể dùng counter/event recorder an toàn để assert:

```text
markedOperation()    -> adviceCount +1
unmarkedOperation()  -> adviceCount +0
renamedMarkedMethod()-> adviceCount +1
```

Nếu có nhiều aspects/advisors, đếm riêng từng policy. Không lấy tổng số Spring proxies hoặc số advisor làm bằng chứng một `@Before` đang chạy đúng: một bean có thể được proxy vì transaction/security/metric advice khác.

Có thể dùng `AopUtils.isAopProxy(bean)` như kiểm tra bổ trợ, nhưng **assert hành vi invocation** mới xác minh được pointcut.

### 10.4. Kiểm tra build-time và static review

Chuỗi AspectJ pointcut ở `@Pointcut` không phải một Java symbol reference đơn giản. IDE rename refactoring có thể cập nhật một số chuỗi hoặc không, tùy IDE/tooling. Quy trình an toàn:

1. Tìm toàn bộ `@Pointcut`, `@Before`, `@After*`, `@Around`, XML `<aop:...>` chứa biểu thức.
2. Tìm exact old FQCN/method names trong pointcut expression strings, không chỉ ở Java imports/references.
3. Kiểm tra marker annotations, stable interfaces, bean names và module boundaries.
4. Chạy unit tests nghiệp vụ và **Spring AOP integration tests**.
5. Đọc Spring startup warnings, nhưng **không dựa vào việc startup thành công** để kết luận pointcut còn đúng.

Ví dụ tìm kiếm tại repository đang sử dụng `rg`:

```bash
rg -n '@Pointcut|@Before|@Around|@AfterReturning|@AfterThrowing' src/main/java
rg -n 'OldService|oldMethod|com\.example\.oldpackage' src/main/java src/main/resources
rg -n '<aop:|pointcut-ref|pointcut=' src/main/resources
```

Các lệnh này chỉ là ví dụ thao tác source code, không thay đổi bất kỳ file nào. Khi dùng PowerShell, `rg` cần được cài đặt riêng; có thể dùng IDE search tương đương.

## 11. Khi thay đổi package hoặc class name, thực hiện refactor theo từng bước

Một workflow Spring AOP refactor đáng tin:

1. **Định nghĩa policy:** xác định chính xác những method nào *phải* chạy advice và những method nào *không được* chạy.
2. **Chọn stable anchor:** marker annotation, stable interface, class annotation, hoặc package/bean convention có quản trị.
3. **Gom logic chọn vào named pointcut:** ví dụ `monitoredOperation()` thay vì sao chép expression khắp advice classes.
4. **Viết behavior tests trước khi refactor:** assert advice event/counter, target result, exception và trường hợp không match.
5. **Thực hiện rename/move** và cập nhật Spring bean registration/scan/import XML tương ứng.
6. **Xác minh marker/contract còn giữ nguyên:** đặc biệt annotation trên implementation methods, target class/interface và bean naming.
7. **Kiểm tra Spring proxy boundary:** đảm bảo caller vẫn đi qua Spring bean reference; không tạo `new` service, không biến cross-bean call thành self-invocation.
8. **Rà soát mọi expression còn tên cũ:** kể cả XML và strings trong Java annotations, chính sách khác `@Transactional`/caching nếu dựa vào proxy.
9. **Chạy lại integration tests** với đúng Spring version, proxy type và active profiles.
10. **Đo tác động ngoài dự kiến:** khi chuyển từ hard-coded class pattern sang annotation/marker, bảo đảm không có thêm bean/method được đánh dấu sai.

Một named pointcut **không ngăn việc đổi policy ngoài ý muốn**. Nó chỉ cung cấp một điểm neo để thảo luận, review và test. Đặc biệt với audit/security, thay đổi tập join points là thay đổi hành vi của hệ thống, cần được xem như một thay đổi functional quan trọng.

## 12. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng sau refactor | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| Spring vẫn khởi động nhưng audit advice không chạy | Expression chứa old class/method name không còn match | Tìm string pointcuts và chạy positive interception test. |
| Annotation marker đã giữ nhưng advice mất | Bean chưa được scan, marker đặt trên vị trí khác, proxy/call boundary đổi | Kiểm tra Spring bean registry, annotation metadata trên implementation, proxy và invocation path. |
| Method bị đổi tên nhưng named pointcut vẫn tên cũ | Tên `businessOperation()` ổn định nhưng expression bên trong hard-code old method | Chỉnh expression ở một nơi, chạy test; named pointcut không tự đổi nghĩa. |
| Advice bất ngờ áp dụng lên quá nhiều methods | Thay old exact signature bằng wildcard quá rộng | Giới hạn scope theo business policy/marker và thêm negative tests. |
| Dùng `within(com.example..service..*)` rồi chuyển class sang `application` | Package convention không còn khớp | Đổi named scope rule hoặc chọn stable annotation/interface. |
| Dùng `bean(*Service)` và đổi class thành `Coordinator` | Component-scan bean name mặc định cũng thay, không còn match pattern | Dùng explicit stable bean name hoặc chọn policy marker. |
| Pointcut `target(OldInterface)` không còn match | Target không còn implement interface cũ hoặc interface FQCN đã đổi | Đánh giá contract và sửa điểm neo có chủ đích. |
| `@annotation` không match sau khi chuyển annotation sang interface method | Method annotation metadata không được duy trì như giả định | Quy ước marker trên concrete implementation và test JDK/CGLIB theo cấu hình. |
| Method bị đổi thành `private` hoặc `final` | Proxy không intercept được như trước | Xem API/proxy contract, thiết kế lại public entry point khi cần. |
| Advice mất sau khi gộp hai services | Cross-bean call biến thành `this.method()` | Tách trách nhiệm qua bean khác hoặc redesign method boundary. |
| Pointcut expression không parse được | Tên referenced pointcut/type sai, cú pháp `&&`/`@annotation` hỏng | Đọc exception lúc context tạo advisor, sửa expression. |
| Bean vẫn `isAopProxy=true` nhưng policy audit không chạy | Proxy đang có advisor khác, audit pointcut không match | Quan sát policy counter/event và advisors, không chỉ proxy boolean. |
| Test cũ chỉ assert response nên không phát hiện mất audit | Không kiểm tra behavior advice | Bổ sung positive/negative interception assertions cho policy. |

## 13. Những giới hạn không thể “giải quyết” chỉ bằng pointcut ổn định

Dù dùng semantic marker và named pointcuts, Spring AOP vẫn có những ranh giới:

- **Chỉ Spring-managed beans** đi qua hạ tầng proxy mới được áp dụng kiểu advice này.
- **Self-invocation** trong target, như `this.someMethod()`, không đi qua Spring proxy.
- **Object tạo trực tiếp bằng `new`** ngoài container không được auto-proxy theo cấu hình thường dùng.
- **JDK proxy** dựa trên interfaces, vì thế method ngoài interface có thể không có đường gọi qua proxy.
- **CGLIB class proxy** không override được class/method `final`, method `private` và những method bị giới hạn bởi Java/module visibility.
- **Spring context boundary** quan trọng: auto-proxy creator trong một context không tự xử lý beans chỉ tồn tại ở context khác.
- **Annotation marker không tự đăng ký aspect bean:** class `@Aspect` cần được Spring quản lý, chẳng hạn `@Component` hoặc `@Bean`, cùng cơ chế AOP được bật.

Nếu một refactor thay đổi chính các ranh giới này, pointcut dù viết rất “bền” vẫn có thể không hoạt động. Cần thiết kế lại cách ứng dụng gọi method, không chỉ sửa chuỗi expression.

## 14. Checklist thiết kế trước khi merge refactor

- [ ] Pointcut biểu đạt **ý nghĩa ổn định** của policy thay vì phụ thuộc vào tên class/method tùy ý.
- [ ] Các biểu thức được gom thành **named pointcuts** có tên dễ hiểu khi tái sử dụng.
- [ ] Annotation/interface/bean-name convention được chọn làm anchor có chủ sở hữu và được document.
- [ ] Không có old FQCN/method names trong strings pointcuts hoặc XML còn hiệu lực.
- [ ] Marker annotations vẫn ở vị trí Spring AOP có thể nhận diện, với retention thích hợp.
- [ ] Bean mới vẫn được Spring đăng ký và lời gọi từ caller đi qua proxy.
- [ ] Proxy type JDK/CGLIB, method visibility, `final`, và context/scope không bị thay đổi trái ý.
- [ ] Positive test chứng minh advice chạy trên method đã đổi tên/di chuyển.
- [ ] Negative test chứng minh advice **không** chạy trên method không thuộc policy.
- [ ] Test kiểm tra đúng số lần advice, kết quả nghiệp vụ và exceptions.
- [ ] Không dùng wildcard rộng khiến chính sách lan ngoài phạm vi.
- [ ] Startup/logs được kiểm tra nhưng **không thay thế** behavior tests.

### Tài liệu Spring Framework chính thức

- Declaring a Pointcut, Combining Pointcut Expressions, Sharing Named Pointcut Definitions: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Declaring Advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html

**Kết luận:** Giữ pointcut ổn định khi refactor trong Spring AOP là thiết kế một **contract chọn method rõ ràng**: tên pointcut dùng lại được, anchor ít biến động (annotation/interface/convention) và integration tests kiểm chứng đúng những lời gọi phải được advice. Đừng đánh đổi tính ổn định bằng wildcard quá rộng; điều cần bảo toàn là **tập hành vi nghiệp vụ được Spring Aspect áp dụng**, không chỉ một chuỗi pointcut vẫn parse thành công.
