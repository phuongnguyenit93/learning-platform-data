# Kết hợp pointcut theo tầng kiến trúc hoặc nhóm chức năng trong Spring AOP

## 1. Mục tiêu tổ chức pointcut

Trong ứng dụng Spring, một `@Aspect` thường chỉ được phép can thiệp một phần hệ thống. Ví dụ, một aspect ghi log lời gọi thuộc **tầng service**, aspect khác đo thời gian cho **repository**, còn audit chỉ nhắm tới những **lệnh ghi dữ liệu**. Nếu mỗi advice sao chép trực tiếp một biểu thức dài, việc đổi package, quy tắc đặt tên hoặc annotation sẽ dễ gây lệch hành vi giữa các aspect.

Giải pháp của Spring AOP là **định nghĩa các named pointcut nhỏ có ý nghĩa, sau đó kết hợp chúng theo phép logic**. Một pointcut mô tả tầng kiến trúc, một pointcut mô tả nhóm chức năng, một pointcut mô tả điều kiện method. Các pointcut được hợp thành quy tắc như “public command trong service” và được tái sử dụng từ nhiều aspect.

Ví dụ đọc như một câu:

```java
@Pointcut("serviceLayer() && commandMethod()")
public void serviceCommand() {}
```

`serviceCommand()` có nghĩa method execution **thuộc service layer VÀ thuộc nhóm command**. Tách các điều kiện giúp dễ đọc và dễ sửa hơn nhồi tất cả vào một `@Before` hoặc `@Around`.

**Phạm vi:** Tổ chức pointcut trong **Spring Framework với `@AspectJ` và Spring AOP proxy-based**. Bài không giảng lại toàn bộ AspectJ độc lập: mọi biểu thức ở đây chỉ có ý nghĩa khi Spring phát hiện aspect, Spring bean có proxy, method được gọi qua proxy và pointcut khớp.

### Kết quả học tập

Sau bài học, bạn có thể:
- Phân loại pointcut theo **tầng kiến trúc**, **nhóm chức năng**, **kiểu method** và **metadata**.
- Dùng `&&`, `||`, `!` với ngoặc để tổ hợp phạm vi chính xác.
- Tổ chức một lớp `CommonPointcuts` dùng chung giữa các `@Aspect`.
- Phân biệt `within`, `execution`, `bean`, `@annotation` trong việc phân nhóm.
- Chạy ví dụ Spring AOP hoàn chỉnh với service, package con, repository và hai aspect.
- Kiểm thử điều kiện khớp/không khớp, xử lý self-invocation và tránh advice chạy trùng ngoài dự kiến.

## 2. Trục kiến trúc và trục chức năng khác nhau thế nào?

Một cấu trúc giả định:

```text
com.example.shop
├── web/
│   └── OrderController
├── service/
│   ├── CheckoutService
│   └── pricing/PricingService
├── repository/
│   └── OrderRepository
└── aop/
    ├── ArchitecturePointcuts
    ├── AuditAspect
    └── TraceAspect
```

| Trục | Câu hỏi | Ví dụ Spring AOP |
| --- | --- | --- |
| Tầng kiến trúc | Type/method ở package nào? | `within(com.example.shop.service..*)`, `within(com.example.shop.repository..*)` |
| Nhóm chức năng | Thao tác có phải đọc, ghi, thanh toán, quản trị? | `execution(public * load*(..))`, `execution(public * place*(..))` |
| Chữ ký | Method public, return type hoặc tham số nào? | `execution(public * *(..))` |
| Annotation | Method hoặc target type có marker nghiệp vụ? | `@annotation(com.example.shop.aop.Audited)` |
| Tên bean | Spring bean có naming convention nào? | `bean(*Service)` |

Ví dụ, `CheckoutService` thuộc service layer nhưng có cả `loadOrder` (query) và `placeOrder` (command). `OrderRepository` thuộc repository, có thể có method `save` mà tên cũng biểu thị ghi dữ liệu. Nếu mục tiêu là “audit command ở service”, không nên dùng riêng `within(service..*)`, vì như vậy sẽ audit cả query. Cũng không nên dùng riêng `execution(* place*(..))` nếu có những method tên như vậy ở layer không liên quan.

**Điểm thiết kế cốt lõi:** Một pointcut mô tả **lớp đối tượng quan tâm**, pointcut khác mô tả **thao tác cần quan sát**. Dùng AND để lấy giao của hai tập.

## 3. Kết hợp với AND, OR, NOT

### 3.1. AND — `&&`

```java
@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {}

@Pointcut("execution(public * *(..))")
public void publicOperation() {}

@Pointcut("serviceLayer() && publicOperation()")
public void publicServiceOperation() {}
```

`publicServiceOperation` yêu cầu method vừa thuộc service layer vừa public. Dấu `..` trong `service..*` bao gồm package `service` và các package con (ví dụ `service.pricing`). `service.*` chỉ chọn type trực tiếp trong package đó.

Một yêu cầu khác:

```java
@Pointcut("execution(public * load*(..))")
public void queryMethod() {}

@Pointcut("serviceLayer() && queryMethod()")
public void serviceQuery() {}
```

`queryMethod()` được định nghĩa qua naming convention; Spring không tự biết method có side effect hay không. `serviceQuery()` giới hạn riêng các method `load...` thuộc service.

### 3.2. OR — `||`

```java
@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {}

@Pointcut("within(com.example.shop.repository..*)")
public void repositoryLayer() {}

@Pointcut("serviceLayer() || repositoryLayer()")
public void applicationLayer() {}
```

`applicationLayer` chọn method execution ở **service hoặc repository**. Đây là hợp của hai tập. Nó phù hợp khi muốn ghi metric cho cả hai layer, không phù hợp nếu chỉ muốn các method `save` của repository.

### 3.3. NOT — `!`

```java
@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {}

@Pointcut("within(com.example.shop.service.internal..*)")
public void internalServicePackage() {}

@Pointcut("serviceLayer() && !internalServicePackage()")
public void serviceExceptInternal() {}
```

Phủ định nên đi kèm **phạm vi dương**. `!within(service.internal..*)` đứng một mình có thể bao gồm gần như tất cả các bean khác trong ứng dụng.

### 3.4. Dấu ngoặc khi kết hợp nhiều điều kiện

```java
@Pointcut("(serviceLayer() || repositoryLayer())"
        + " && execution(public * *(..))"
        + " && !within(com.example.shop.internal..*)")
public void visibleApplicationOperations() {}
```

Ý nghĩa: **(service HOẶC repository)** VÀ **public method** VÀ **không nằm trong package internal**. Dấu ngoặc thể hiện chủ đích rõ ràng và giúp review tránh nhầm precedence.

**Nhớ rằng** phép logic xác định những method execution được chọn; nó không quyết định thứ tự chạy nhiều advice. Thứ tự advice thuộc `@Order`/`Ordered` và cơ chế advisor ordering của Spring.

## 4. Named pointcut để dùng lại

Đặt các điều kiện theo lớp chức năng/tầng thành pointcut nhỏ rồi tham chiếu bằng tên trong điểm cắt tổng hợp:

```java
public class ArchitecturePointcuts {
    @Pointcut("within(com.example.shop.service..*)")
    public void serviceLayer() {}

    @Pointcut("execution(public * place*(..))")
    public void commandMethod() {}

    @Pointcut("serviceLayer() && commandMethod()")
    public void serviceCommand() {}
}
```

Trong aspect bean, `@Before("com.example.shop.aop.ArchitecturePointcuts.serviceCommand()")` chỉ chọn public `place*` tại service layer. Đây là đoạn code của lớp chuyên trách, cần đặt tại package đã nêu. Public named pointcut giúp tái sử dụng giữa aspects; các `@Pointcut` methods không chạy logic lúc match. Chi tiết cấu trúc thư viện và hợp đồng chia sẻ nằm ở bài **“Chia sẻ pointcut giữa các aspect”**.

## 5. Chọn pattern theo kiến trúc Spring thật

### 5.1. Package scope bằng within

```java
@Pointcut("within(com.example.shop.web..*)")
public void webLayer() {}

@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {}

@Pointcut("within(com.example.shop.repository..*)")
public void repositoryLayer() {}
```

`within` trong Spring AOP mô tả method execution được khai báo trong matching type. Cẩn thận với method **kế thừa từ superclass nằm ngoài package**: tiêu chí declaring type và runtime target type không hoàn toàn giống nhau. Nếu ý nghĩa thực sự là “bean triển khai service interface”, một `target(ServiceInterface)` hoặc `execution(* ServiceInterface.*(..))` có thể chính xác hơn, tùy kiến trúc.

### 5.2. Nhóm dựa trên chữ ký method

```java
@Pointcut("execution(public * load*(..))"
        + " || execution(public * find*(..))")
public void queryMethods() {}

@Pointcut("execution(public * place*(..))"
        + " || execution(public * cancel*(..))")
public void commandMethods() {}
```

Đây là convention do nhóm phát triển đề ra, không phải ngữ nghĩa tự động do Spring gán. Method `loadAndMutate` có side effect vẫn match nhóm query nếu tên bắt đầu `load`. Đối với audit yêu cầu chính xác hơn, dùng marker annotation có review/test rõ ràng.

### 5.3. Nhóm qua annotation

Giả sử đã định nghĩa `@AuditedCommand` với `@Target(ElementType.METHOD)` và `@Retention(RetentionPolicy.RUNTIME)`. Có thể viết:

```java
@Pointcut("serviceLayer()"
        + " && @annotation(com.example.shop.aop.AuditedCommand)")
public void auditedServiceCommand() {}
```

Điều kiện này chọn annotation trên **method** chứ không phải package hay tên method. Nó tách phân loại command khỏi naming convention, nhưng vị trí đặt annotation trên interface/implementation và lựa chọn JDK/CGLIB proxy cần được kiểm tra trên runtime.

Phân biệt `@annotation` (annotation trên method) với `@within` (trên declaring type), `@target` (trên runtime target type) và `@args` (trên runtime type của actual arguments).

### 5.4. Nhóm theo bean name

Spring AOP có `bean(*Service)`: chọn Spring beans theo **tên**, ví dụ `orderService` hay `pricingService`, khi naming convention phù hợp. Nó không giống `within(...service..*)` xét type/package. Khi bean được đặt tên `paymentGateway` dù class tên `PaymentService`, biểu thức `bean(*Service)` có thể không khớp. `bean` là Spring-specific designator, không phải cú pháp portable cho AspectJ weaving độc lập.

### 5.5. Các bounded contexts khác nhau

Khi code có `com.example.orders.service`, `com.example.catalog.service` và `com.example.billing.service`, có thể dùng một scope pattern như `within(com.example..service..*)` **chỉ khi** package naming thật sự ổn định. Nếu muốn audit chỉ orders, hãy định nghĩa thêm `ordersServiceLayer()` thay vì mở rộng chung tới tất cả bounded contexts.

## 6. Ví dụ Java 17 chạy độc lập trên Spring Framework

Ví dụ gồm hai Spring aspects dùng chung `ArchitecturePointcuts`. Nó minh họa:

1. Audit chỉ các **service commands**.
2. Trace chỉ các **service queries** và **repository operations**.
3. Service ở package con vẫn khớp `within(demo.service..*)`.
4. Self-invocation không tạo thêm một lần advice, dù method nội bộ sẽ khớp nếu được gọi qua proxy.

**Môi trường:** Java 17+, Spring Framework `6.1.14`, Gradle và AspectJ Weaver `1.9.22.1`. Đây là ứng dụng Spring Framework thuần, không dùng Spring Boot auto-configuration.

### 6.1. File và cấu hình Gradle

```text
spring-aop-pointcut-composition/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── config/AppConfig.java
    ├── aop/ArchitecturePointcuts.java
    ├── aop/AuditAspect.java
    ├── aop/TraceAspect.java
    ├── service/CheckoutService.java
    ├── service/pricing/PricingService.java
    └── repository/OrderRepository.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-pointcut-composition'
```

`build.gradle`:

```groovy
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
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.DemoApplication'
}
```

`spring-context` cung cấp Spring IoC và `AnnotationConfigApplicationContext`; `spring-aop` cung cấp auto-proxy infrastructure; `aspectjweaver` hỗ trợ Spring phân tích biểu thức `@AspectJ`.

### 6.2. Lớp chia sẻ named pointcuts

`src/main/java/demo/aop/ArchitecturePointcuts.java`:

```java
package demo.aop;

import org.aspectj.lang.annotation.Pointcut;

public class ArchitecturePointcuts {

    @Pointcut("within(demo.service..*)")
    public void serviceLayer() {}

    @Pointcut("within(demo.repository..*)")
    public void repositoryLayer() {}

    @Pointcut("execution(public * *(..))")
    public void publicOperation() {}

    @Pointcut("execution(public * load*(..))")
    public void queryOperation() {}

    @Pointcut("execution(public * place*(..))")
    public void commandOperation() {}

    @Pointcut("serviceLayer() && queryOperation()")
    public void serviceQuery() {}

    @Pointcut("serviceLayer() && commandOperation()")
    public void serviceCommand() {}

    @Pointcut("repositoryLayer() && publicOperation()")
    public void repositoryOperation() {}
}
```

`ArchitecturePointcuts` chỉ cung cấp definitions; **không cần là một Spring bean**. Named pointcut `serviceQuery` là AND của tầng service và method query; `serviceCommand` là AND của tầng service và command; `repositoryOperation` là AND của tầng repository và public method.

### 6.3. Target ở package service

`src/main/java/demo/service/CheckoutService.java`:

```java
package demo.service;

public class CheckoutService {

    public void placeOrder(String id) {
        System.out.println("target:placeOrder:" + id);
    }

    public void loadOrder(String id) {
        System.out.println("target:loadOrder:" + id);
    }

    public void placeWithInternalLoad(String id) {
        System.out.println("target:placeWithInternalLoad:" + id);
        loadOrder(id);
    }
}
```

`placeOrder` và `placeWithInternalLoad` là command theo prefix `place`; `loadOrder` là query theo prefix `load`. Khi `placeWithInternalLoad` gọi `loadOrder` trực tiếp, đó là self-invocation trên `this`: Spring AOP proxy không intercept lời gọi nội bộ.

### 6.4. Target ở package service con

`src/main/java/demo/service/pricing/PricingService.java`:

```java
package demo.service.pricing;

public class PricingService {

    public void loadPrice(String sku) {
        System.out.println("target:loadPrice:" + sku);
    }
}
```

`demo.service.pricing` khớp `within(demo.service..*)` nhờ `..*`, và `loadPrice` khớp `queryOperation`.

### 6.5. Target ở repository

`src/main/java/demo/repository/OrderRepository.java`:

```java
package demo.repository;

public class OrderRepository {

    public void save(String id) {
        System.out.println("target:save:" + id);
    }
}
```

Repository nằm ngoài service package, nhưng method `save` là public và khớp `repositoryOperation`. Nó không bị `serviceCommand` chọn chỉ vì tên có ý nghĩa thao tác ghi.

### 6.6. Hai aspect tham chiếu cùng pointcut library

`src/main/java/demo/aop/AuditAspect.java`:

```java
package demo.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {

    @Before("demo.aop.ArchitecturePointcuts.serviceCommand()")
    public void beforeCommand(JoinPoint joinPoint) {
        System.out.println(
            "audit:" + joinPoint.getSignature().getName());
    }
}
```

`src/main/java/demo/aop/TraceAspect.java`:

```java
package demo.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before("demo.aop.ArchitecturePointcuts.serviceQuery()")
    public void beforeQuery(JoinPoint joinPoint) {
        System.out.println(
            "trace:query:" + joinPoint.getSignature().getName());
    }

    @Before("demo.aop.ArchitecturePointcuts.repositoryOperation()")
    public void beforeRepository(JoinPoint joinPoint) {
        System.out.println(
            "trace:repository:" + joinPoint.getSignature().getName());
    }
}
```

Lớp `AuditAspect` dùng nhóm command, `TraceAspect` dùng query và repository. Chúng cùng tham chiếu named pointcuts ở một nơi; không cần copy `within(...)` vào từng advice.

### 6.7. Cấu hình Spring bean

`src/main/java/demo/config/AppConfig.java`:

```java
package demo.config;

import demo.aop.AuditAspect;
import demo.aop.TraceAspect;
import demo.repository.OrderRepository;
import demo.service.CheckoutService;
import demo.service.pricing.PricingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public CheckoutService checkoutService() {
        return new CheckoutService();
    }

    @Bean
    public PricingService pricingService() {
        return new PricingService();
    }

    @Bean
    public OrderRepository orderRepository() {
        return new OrderRepository();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@EnableAspectJAutoProxy` bật hạ tầng đọc advisor từ `@Aspect`. Hai aspect được tạo thành Spring beans qua `@Bean`; pointcut-only class không được đăng ký. `proxyTargetClass=true` giúp ba target class không có interface vẫn được Spring AOP proxy bằng lớp con (CGLIB). Trong một ứng dụng có interface, có thể dùng JDK proxy nếu cấu hình phù hợp.

### 6.8. Main và stdout

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import demo.config.AppConfig;
import demo.repository.OrderRepository;
import demo.service.CheckoutService;
import demo.service.pricing.PricingService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            CheckoutService checkout =
                context.getBean(CheckoutService.class);
            PricingService pricing =
                context.getBean(PricingService.class);
            OrderRepository repository =
                context.getBean(OrderRepository.class);

            checkout.placeOrder("O-1");
            checkout.loadOrder("O-1");
            pricing.loadPrice("P-2");
            repository.save("O-1");
            checkout.placeWithInternalLoad("O-2");

            System.out.println("checkoutProxy=" +
                AopUtils.isAopProxy(checkout));
            System.out.println("pricingProxy=" +
                AopUtils.isAopProxy(pricing));
            System.out.println("repositoryProxy=" +
                AopUtils.isAopProxy(repository));
        }
    }
}
```

Lệnh chạy từ thư mục có `build.gradle`:

```bash
gradle run
```

Nếu đã tạo Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows).

**Chỉ tính các dòng do chương trình Java in ra** (không gồm output Gradle/logger):

```text
audit:placeOrder
target:placeOrder:O-1
trace:query:loadOrder
target:loadOrder:O-1
trace:query:loadPrice
target:loadPrice:P-2
trace:repository:save
target:save:O-1
audit:placeWithInternalLoad
target:placeWithInternalLoad:O-2
target:loadOrder:O-2
checkoutProxy=true
pricingProxy=true
repositoryProxy=true
```

### 6.9. Giải thích theo ma trận pointcut

| Method invocation | Layer match | Nhóm chức năng | Kết quả |
| --- | --- | --- | --- |
| `checkout.placeOrder` | `serviceLayer` | `commandOperation` | `audit:placeOrder` trước target |
| `checkout.loadOrder` từ main | `serviceLayer` | `queryOperation` | `trace:query:loadOrder` trước target |
| `pricing.loadPrice` | `serviceLayer` (subpackage) | `queryOperation` | `trace:query:loadPrice` trước target |
| `repository.save` | `repositoryLayer` | `publicOperation` | `trace:repository:save` trước target |
| `checkout.placeWithInternalLoad` | `serviceLayer` | `commandOperation` | `audit:placeWithInternalLoad` trước target |
| `loadOrder` gọi nội bộ từ `placeWithInternalLoad` | Lẽ ra khớp query về type/signature | Nhưng là `this.loadOrder` | Không có advice query lần hai |

Ba dòng `...Proxy=true` xác nhận ba Spring beans được proxy. Mỗi bean có ít nhất một advisor phù hợp. Tuy nhiên, không phải mọi advice chạy trên mọi method; các điều kiện pointcut khác nhau lựa chọn nhóm invocation khác nhau.

**Kết quả self-invocation:** `target:loadOrder:O-2` có xuất hiện, nhưng không có `trace:query:loadOrder` ngay trước dòng đó, vì lời gọi từ `placeWithInternalLoad` không quay lại Spring proxy. Đây là giới hạn cố hữu của Spring AOP proxy, không sửa được chỉ bằng cách nới rộng `execution` hoặc `within`.

## 7. Khi nào dùng OR/NOT, khi nào tạo pointcut mới?

Giả sử hệ thống bắt đầu có thêm `cancelOrder` và `findOrder`:
- Nếu naming convention ghi dữ liệu là `place*` hoặc `cancel*`, có thể định nghĩa nhóm command bằng OR.
- Nếu query là `load*` hoặc `find*`, có thể định nghĩa nhóm query bằng OR.
- Nếu một package `service.internal` cần loại trừ, dùng AND với phủ định scoped `!within(service.internal..*)`.
- Nếu một nhóm đòi logic riêng (ví dụ chỉ audit nghiệp vụ thanh toán), tạo pointcut có tên riêng như `paymentCommand`. Không áp một “serviceCommand” quá rộng lên mọi quy tắc audit.

Ví dụ thay thế cho method `commandOperation`:

```java
@Pointcut("execution(public * place*(..))"
        + " || execution(public * cancel*(..))")
public void commandOperation() {}
```

Vì `serviceCommand` đã tham chiếu `commandOperation`, không cần sửa tất cả `@Before` trong các aspects. Đây là ích lợi trực tiếp của tổ chức pointcut.

## 8. Sự phối hợp với Spring AOP infrastructure

Một số chi tiết Spring-specific cần nhớ:

1. **Aspect phải là Spring bean.** `@Aspect` không tự thay `@Component` hoặc `@Bean`.
2. **AOP phải bật trong đúng context.** `@EnableAspectJAutoProxy` thuộc `ApplicationContext` chứa nó; context khác không tự được hậu xử lý nhờ context cha.
3. **Auto-proxy creator chọn advisor theo bean.** Nếu service không có method phù hợp hoặc không có advisor khác, Spring không bắt buộc tạo proxy cho nó chỉ vì bạn đã khai báo `@EnableAspectJAutoProxy`.
4. **Spring chỉ chặn method execution qua proxy.** Code gọi `new Service()`, constructor execution, field access hoặc `this.method()` không nhận advice giống lời gọi qua Spring proxy.
5. **Proxy type có hệ quả.** Với JDK dynamic proxy, client thường gọi qua interface; với CGLIB, class/method `final` không được override để advice. Không chọn pointcut dựa trên class implementation rồi mặc định mọi method đều intercept được.
6. **Nhiều aspects có thể match cùng một invocation.** `@Order`/`Ordered` và advisor precedence có ảnh hưởng thứ tự. Những pointcuts chồng nhau có thể cố ý hoặc do lỗi thiết kế.
7. **Spring-specific `bean` designator** hữu ích khi module tổ chức bean theo tên, nhưng không thể coi đó là tương đương `within`/`target`.
8. **Không dùng naming convention như security boundary duy nhất.** Nếu thao tác mang tính an ninh/ủy quyền, có thể cần Spring Security method authorization hoặc validation phù hợp và integration test thực.

## 9. Kiểm thử pointcut: cả trường hợp khớp và không khớp

Với `serviceLayer() && commandMethod()`, kiểm thử theo bảng tình huống: service có `placeOrder()` phải match; service có `loadOrder()` không match điều kiện command; bean ngoài service có `placeOrder()` không match điều kiện layer; method ở `service.pricing` cho biết `..*` có bao quát package con hay không. Chỉ quan sát proxy hiện diện là chưa đủ: phải assert đúng advice event/counter.

Bổ sung một ca self-invocation để chứng minh lời gọi nội bộ không quay qua proxy. Các phép thử này bảo vệ ý nghĩa phép giao trước/sau khi đổi expression; bài **“Kiểm thử ca được khớp và ca không được khớp”** triển khai bộ JUnit thực tế.

## 10. Hiệu năng, bảo trì và kiến trúc

Tài liệu Spring khuyên kết hợp một điều kiện **kinded** (đặc biệt `execution`) với điều kiện **scoping** (`within`) khi phù hợp để điểm cắt có phạm vi rõ và dễ tối ưu matching. Tên pointcut không tự tạo hiệu năng nhanh hơn; điều đáng giá là **ràng buộc đúng vùng cần advice** và có cấu trúc dễ kiểm chứng.

Nếu project chuyển từ cấu trúc `com.example.shop.service` sang các module như `com.example.orders.application` hoặc `com.example.billing.application`, việc tập trung layer definitions giúp sửa ở một nơi. Nhưng cần test xác nhận các target mới thực sự được Spring tạo và advice không bị mất ngoài ý muốn.

Một quy ước tổ chức nên có:
- **Tên mô tả ý nghĩa:** `serviceQuery`, `repositoryOperation`, `auditedCommand`, không chỉ `pc1`, `pc2`.
- **Không lẫn logic trong named pointcut method:** phần thân rỗng, logic chạy ở `@Before`/`@Around`.
- **Không sao chép package patterns trên nhiều aspects:** reuse bằng tên class/method.
- **Không gom mọi thứ thành một expression quá rộng:** chia theo layer và functional group.
- **Test phạm vi âm và dương:** đảm bảo lời gọi ngoài layer không bị advice.
- **Tách trách nhiệm:** lớp pointcuts mô tả *where*; các aspects mô tả *what to do*.

## 11. Checklist áp dụng

Trước khi áp dụng, đối chiếu architecture scope (`within`, `execution`, `bean`) với business scope (tên method/annotation); đặt ngoặc rõ khi phối hợp `&&`, `||`, `!`; bảo đảm aspect bean được đăng ký và caller dùng Spring proxy. Test cả service đúng tầng, service thuộc package con, repository và bean ngoài phạm vi. Nếu đổi convention `load*`/`place*`, chạy lại các ca dương và âm để phát hiện tác động.

## 12. Kết luận

**Tổ chức pointcut theo tầng kiến trúc và nhóm chức năng là cách biến một tập biểu thức AOP rời rạc thành những quy tắc rõ ràng, chia sẻ được và có thể kiểm thử.** Dùng `within` hoặc `execution` để mô tả tầng, sử dụng tên method hoặc annotation để phân loại nhóm nghiệp vụ, rồi kết hợp bằng `&&`, `||`, `!`. Đưa named pointcuts dùng chung vào một lớp chuyên trách để mỗi `@Aspect` tập trung vào phần advice.

Cuối cùng, luôn nhớ ranh giới Spring AOP: chỉ lời gọi method **qua Spring proxy** trên Spring bean được advice. Một pointcut đúng về package/chữ ký không khiến method gọi nội bộ trên `this` tự bị chặn.

### Tài liệu chính thức

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): kết hợp pointcuts, dùng tên, `CommonPointcuts`, `within`/`execution`/`bean` và quy tắc matching.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): khai báo `@Before`, `@Around` và thứ tự advice.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): kích hoạt Spring AOP và đăng ký `@Aspect`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB, proxy call boundary, self-invocation.
