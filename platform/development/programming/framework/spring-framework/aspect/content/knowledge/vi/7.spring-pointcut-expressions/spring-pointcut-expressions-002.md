# Dùng within để giới hạn lớp hoặc gói của bean đích trong Spring AOP

## 1. within giải quyết vấn đề gì trong Spring?

Khi dùng `@Aspect` để thêm logging, tracing, auditing hoặc kiểm tra quy ước cho Spring service, ta thường không muốn advice áp dụng lên mọi Spring bean. Cần giới hạn chính xác **nhóm lớp hoặc package chứa những phương thức sẽ được chặn**.

Trong Spring AOP, `within(TypePattern)` là một **pointcut designator** dùng để giới hạn method-execution join point nằm trong những type khớp với `TypePattern`. Theo mô tả của Spring Framework, đó là **việc thực thi phương thức được khai báo trong một type phù hợp**. Trong ứng dụng được tổ chức theo package, `within` đặc biệt hữu ích để giới hạn logic của aspect vào service, controller hoặc repository layer.

Ví dụ:

```java
@Pointcut("within(com.example.orders.service..*)")
public void serviceLayer() {
}
```

Biểu thức trên chọn những method-execution join point thuộc các type trong package `com.example.orders.service` **và các package con**. Nó chỉ có tác dụng trong Spring AOP khi lời gọi phương thức đi qua **Spring AOP proxy của một Spring-managed bean** và đáp ứng những điều kiện đi kèm.

**Điểm quan trọng:** `within` là điều kiện theo **type/phạm vi khai báo method**, không phải điều kiện trực tiếp theo **tên Spring bean**, không phải phép quét file Java trên ổ đĩa và không phải cơ chế tự đăng ký thêm Spring bean. Một lớp có tên/package khớp nhưng không được Spring quản lý sẽ không tự nhận advice từ Spring AOP.

Bài này tập trung vào `within` trong Spring Framework theo cơ chế proxy, không ôn lại cú pháp AspectJ tổng quát hoặc weaving constructor/field access bên ngoài Spring AOP.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Viết `within` đúng để chọn một lớp, một package hoặc nhiều package con.
2. Giải thích sự khác nhau giữa `within`, `execution`, `target`, `this`, `bean` và `@within` khi dùng Spring AOP.
3. Kết hợp `within` với `execution` để lọc cả **layer/type** và **chữ ký method**.
4. Hiểu vì sao một method nằm trong package khớp vẫn có thể không chạy advice nếu lời gọi bypass proxy.
5. Viết và chạy ví dụ Spring Framework/Java 17 kiểm tra một service ở package gốc, một service ở package con và một repository nằm ngoài phạm vi.

## 2. Cú pháp TypePattern của within

Biểu thức thường dùng:

```text
within(com.example.app.service..*)
```

Trong đó:
- `within(...)` đặt ràng buộc lên type chứa method-execution join point.
- `com.example.app.service` là đường package.
- `..` cho phép các mức package con, kể cả không có mức con.
- `*` là wildcard khớp tên type theo mẫu tương ứng.

Ví dụ đối chiếu:

| Pointcut | Ý nghĩa trong Spring AOP | Lưu ý |
| --- | --- | --- |
| `within(com.example.app.service.OrderService)` | Những method-execution join point trong type `OrderService` | Chọn một type cụ thể; lớp đó vẫn phải là target phù hợp của AOP proxy |
| `within(com.example.app.service.*)` | Những type trực tiếp trong package `service` | Không tự bao phủ package `service.internal` |
| `within(com.example.app.service..*)` | Type trong `service` và các package con ở mọi độ sâu | Mẫu thường dùng cho service layer |
| `within(com.example.app..*)` | Những type trong toàn bộ package cây `com.example.app` | Dễ quá rộng nếu ứng dụng có nhiều layer |
| `within(com.example.app.service..*) && execution(public * *(..))` | Chỉ public method execution thuộc service layer | Kết hợp điều kiện phạm vi và method signature |
| `within(com.example.app.service..*) && !within(com.example.app.service.internal..*)` | Service layer, trừ một cây package cụ thể | Loại trừ nhóm type bằng toán tử `!` |

### 2.1. Khác biệt giữa dấu chấm đơn và hai dấu chấm

Giả sử code có cấu trúc:

```text
com.example.app.service.OrderService
com.example.app.service.OrderQuery
com.example.app.service.internal.PriceService
com.example.app.service.internal.impl.LocalCalculator
com.example.app.repository.OrderRepository
```

- `within(com.example.app.service.*)` nhắm tới các type trực tiếp trong `service`, ví dụ `OrderService` và `OrderQuery`.
- `within(com.example.app.service..*)` còn bao phủ `service.internal.PriceService` và `service.internal.impl.LocalCalculator`.
- Cả hai biểu thức đều **không** chọn `com.example.app.repository.OrderRepository` vì repository nằm ngoài cây package service.

Dấu `..` không có nghĩa “chỉ thêm đúng một package con”. Nó cho phép nhiều mức package; trong mẫu `service..*` cũng bao gồm type ngay trong `service`.

### 2.2. Một lớp cụ thể

```java
@Before("within(com.example.app.service.OrderService)")
public void beforeOrderService() {
    System.out.println("inside OrderService");
}
```

Đây là snippet minh họa, giả định có một `@Aspect` Spring bean và lớp `OrderService` thích hợp. Pointcut không tự yêu cầu method tên `save`, `cancel` hay `find`; nó thu hẹp theo type. Nếu muốn chỉ một API cụ thể, kết hợp thêm `execution`.

### 2.3. Không dùng within để diễn tả tên bean

Tên Spring bean như `orderService` hoặc `pricingService` không xuất hiện trong biểu thức `within`; package Java cũng không bắt buộc trùng bean name. Nếu yêu cầu là chọn những bean có tên khớp mẫu `*Service`, Spring AOP có pointcut designator riêng là `bean(*Service)`. Hai cách chọn có thể kết hợp, nhưng chúng kiểm tra những điều kiện khác nhau.

## 3. within chỉ là điều kiện chọn, không phải cơ chế tạo proxy

Một aspect trong Spring thường được khai báo như sau:

```java
@Aspect
@Component
public class ServiceAspect {

    @Pointcut("within(com.example.app.service..*)")
    public void serviceLayer() {
    }

    @Before("serviceLayer()")
    public void beforeServiceMethod() {
        System.out.println("service call");
    }
}
```

Trong một Spring application đã bật `@AspectJ` support:
1. `@Component` hoặc `@Bean` khiến `ServiceAspect` được đăng ký thành Spring bean. `@Aspect` **không** tự hoạt động như `@Component`.
2. Spring phân tích `@Pointcut` và phương thức advice, rồi xây dựng advisor thích hợp.
3. Auto-proxy creator xét những Spring bean mà advisor có thể áp dụng.
4. Khi code khác gọi qua proxy, Spring kiểm tra method execution hiện tại có nằm trong `within(com.example.app.service..*)` hay không.
5. Chỉ khi pointcut và proxy boundary cùng cho phép, `beforeServiceMethod()` mới chạy.

**Không phải mọi object do `new` tạo ra đều được Spring AOP quản lý.** Chẳng hạn:

```java
new OrderService().placeOrder();
```

không đi qua Spring proxy, dù class nằm trong package `service`. Tương tự, một Spring bean có thể nằm trong package phù hợp nhưng không được proxy do chưa bật AOP, aspect chưa được đăng ký hoặc không có phương thức nào đủ điều kiện.

### Điều kiện Spring AOP hỗ trợ

Spring AOP dựa trên proxy hỗ trợ các **method-execution join point trên Spring beans**. Nó không dùng `within` để chặn field access (`get`/`set`), constructor execution hoặc lời gọi giữa hai phương thức nằm trong cùng target theo nghĩa Java source code. Đây là ranh giới hoạt động của Spring proxy, không phải lỗi cú pháp `within`.

## 4. within so với execution, target, this, bean và @within

Các designator này dễ bị nhầm vì đều có thể dùng để giới hạn phạm vi aspect.

| Designator | Spring AOP quan tâm điều gì? | Khi nào nên dùng? |
| --- | --- | --- |
| `within(TypePattern)` | Method execution được khai báo trong type khớp mẫu | Giới hạn theo package, lớp, layer |
| `execution(MethodPattern)` | Chữ ký/kiểu thực thi method khớp mẫu | Chọn tên method, return type, visibility, parameters, declaring type |
| `target(TypePattern)` | **Target object phía sau proxy** là instance của type | Chọn theo kiểu thực tế của đối tượng target |
| `this(TypePattern)` | **Spring proxy** là instance của type | Cần xét kiểu hoặc interface mà proxy expose |
| `bean(NamePattern)` | Spring bean name khớp mẫu | Chọn nhóm bean theo convention đặt tên |
| `@within(AnnotationType)` | Method execution được khai báo trong type có annotation phù hợp | Chọn theo marker annotation của type |
| `@annotation(AnnotationType)` | Method execution có annotation phù hợp trên method | Chọn thao tác theo method annotation |

### 4.1. within và execution

Hai pointcut sau nhìn có vẻ tương tự nhưng khác mục tiêu thiết kế:

```java
@Pointcut("within(com.example.app.service..*)")
public void inServiceLayer() {
}

@Pointcut("execution(public * com.example.app.service..*.*(..))")
public void publicServiceSignatures() {
}
```

- `within` nhấn mạnh **vùng type**, không trực tiếp yêu cầu public method.
- `execution` chỉ rõ method signature, ở ví dụ là public method với mọi return type, tên và arguments trong phạm vi declaring type được chỉ ra.
- Do Spring AOP chặn lời gọi qua proxy, phương thức nào thực sự được intercept còn phụ thuộc JDK/CGLIB và đường gọi.

Một mẫu **dễ đọc và dễ bảo trì** là tách hai điều kiện:

```java
@Pointcut("within(com.example.app.service..*)")
public void serviceLayer() {
}

@Pointcut("execution(public * *(..))")
public void publicMethod() {
}

@Pointcut("serviceLayer() && publicMethod()")
public void publicServiceMethod() {
}
```

Ở đây `serviceLayer` là điều kiện phạm vi, `publicMethod` là điều kiện chữ ký, `publicServiceMethod` kết hợp cả hai. Có thể tái sử dụng named pointcut này cho nhiều advice mà không nhân bản biểu thức dài.

### 4.2. within và target

Giả sử `com.example.app.service.SpecialOrderService` kế thừa một method từ superclass nằm **ngoài** package service. Cần phân biệt:
- `within(service..*)` mô tả **type khai báo nơi method execution thuộc về**.
- `target(SpecialOrderService)` mô tả **type instance của target runtime**.

Không nên viết một câu tuyệt đối “mọi method có thể gọi trên instance SpecialOrderService đều chắc chắn khớp within(service..*)”. Với **method kế thừa từ superclass được khai báo ở package khác**, hành vi xét method/declaring type có thể làm kết quả khác kỳ vọng. Nếu cần ràng buộc theo runtime target class/hierarchy, `target(...)` hoặc một `execution(...)` được thiết kế cẩn thận có thể phù hợp hơn; hãy kiểm thử với JDK/CGLIB proxy đang dùng.

### 4.3. within và this

Trong Spring proxy AOP:
- `this(Type)` nhìn vào **proxy**.
- `target(Type)` nhìn vào **target object**.

JDK proxy chỉ implements các interface thích hợp và thường **không** là instance của implementation class. CGLIB class proxy là subclass của implementation class. Vì vậy, một pointcut `this(com.example.app.service.OrderService)` có thể phụ thuộc proxy type trong khi `target(...)` được xét trên target thật.

`within` có ý nghĩa phân loại **method execution theo type pattern**. Nó không phải cú pháp thay thế cho `this` hoặc `target`.

### 4.4. within và bean

Ví dụ:

```java
@Pointcut("within(com.example.app.service..*) && bean(*Service)")
public void namedServiceInServicePackage() {
}
```

Ý nghĩa: chỉ chọn những invocation vừa thuộc layer service về type pattern, vừa xuất phát từ bean có tên Spring phù hợp `*Service`. Trong Spring AOP, `bean(...)` là phần mở rộng đặc thù cho bean instances, không phải designator chuẩn cho AspectJ weaving.

Cần xét naming convention thật: bean tên `orderGateway` có thể nằm trong package `service` nhưng không khớp `bean(*Service)`.

### 4.5. within và @within

`within(com.example.app.service..*)` lọc bằng **tên type/package**. Trong khi đó `@within(com.example.app.Monitored)` lọc các method executions được khai báo trong type có annotation phù hợp. Marker annotation cho phép type nằm ở nhiều package khác nhau mà vẫn được chọn.

Dạng:

```java
@Pointcut("within(com.example.app.service..*)"
        + " && @annotation(com.example.app.Audited)")
public void auditedServiceOperation() {
}
```

giới hạn theo layer và annotation **trên method**, nên khác `@within` là annotation **trên type**. Đây là minh họa cú pháp; ứng dụng thực tế phải có annotation `Audited` và aspect đã được đăng ký.

## 5. Kết hợp trong Spring: toán tử và named pointcut

Spring hỗ trợ kết hợp pointcut bằng:
- `&&`: cả hai điều kiện phải khớp.
- `||`: một trong hai điều kiện khớp.
- `!`: phủ định điều kiện.

Ví dụ:

```java
@Pointcut("within(com.example.app.service..*)"
        + " && execution(public * *(..))"
        + " && !within(com.example.app.service.internal..*)")
public void publicExternalServiceMethods() {
}
```

Biểu thức này chọn public method execution trong service layer, nhưng loại bỏ type nằm trong package `internal` và mọi package con. Ngoài việc xét pointcut, phương thức vẫn phải được gọi qua Spring proxy mới có advice.

Nếu có nhiều aspect cần dùng chung, có thể đặt pointcut vào một lớp chia sẻ:

```java
package com.example.app.aop;

import org.aspectj.lang.annotation.Pointcut;

public final class LayerPointcuts {
    private LayerPointcuts() {
    }

    @Pointcut("within(com.example.app.service..*)")
    public static void inService() {
    }
}
```

**Chú ý:** Đoạn trên chỉ minh họa khả năng chia sẻ định nghĩa pointcut, không phải mẫu khuyến nghị để đăng ký thành bean. Trong thực tế, các named pointcut được trình bày theo ví dụ chính thức là **phương thức trên lớp định nghĩa pointcut**, thường khai báo không static và có thân rỗng. Nếu chọn dùng `@Pointcut` trong một lớp không phải `@Aspect`, phải xác minh khả năng tham chiếu pointcut với cấu hình thư viện/phiên bản cụ thể. Cách đơn giản và chắc chắn hơn là khai báo named pointcut trong cùng lớp `@Aspect` như ví dụ chạy bên dưới.

## 6. Ví dụ chạy đầy đủ: package gốc, package con và repository ngoài phạm vi

Mục tiêu của ví dụ:
1. Một method trong `demo.service` nhận advice.
2. Một method trong `demo.service.internal` cũng nhận advice vì `..*` bao phủ package con.
3. Bean `demo.repository.InventoryRepository` không nhận advice vì ở ngoài `within(demo.service..*)`.
4. Lời gọi nội bộ `this.reserve(...)` trong target cho thấy Spring AOP chỉ chặn **lời gọi qua proxy**.

Ví dụ dùng **Java 17+, Spring Framework 6.1.14, Gradle**. Chúng ta tạo Spring Framework application thuần, dùng `@EnableAspectJAutoProxy(proxyTargetClass=true)` để đảm bảo các service không có interface cũng được class-based proxy. Không cần Spring Boot hoặc database.

### 6.1. Cấu trúc project

```text
spring-aop-within/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── config/AppConfig.java
    ├── aop/LayerAspect.java
    ├── service/InventoryService.java
    ├── service/internal/PricingService.java
    └── repository/InventoryRepository.java
```

### 6.2. Gradle configuration

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-within'
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

`spring-context` cung cấp `AnnotationConfigApplicationContext` và cấu hình Spring bean. `spring-aop` cung cấp AOP infrastructure, còn `aspectjweaver` cung cấp thư viện AspectJ cần để Spring phân tích `@AspectJ` pointcut expression.

### 6.3. Spring service trong package gốc

Tệp `src/main/java/demo/service/InventoryService.java`:

```java
package demo.service;

public class InventoryService {

    public String reserve(String sku) {
        System.out.println("service:reserve:" + sku);
        return "reserved:" + sku;
    }

    public void reserveInternally() {
        System.out.println("service:reserveInternally");
        reserve("SELF");
    }
}
```

Cả `reserve` và `reserveInternally` được khai báo trong type thuộc `demo.service`. Hai method đều public và không final, nên Spring CGLIB proxy có thể chặn lời gọi **từ client qua proxy**.

Trong `reserveInternally()`, dòng `reserve("SELF")` là **self-invocation trên target**; nó không quay lại proxy. Vì thế, trong trường hợp gọi `reserveInternally()` từ client, advice chỉ chạy cho `reserveInternally` (lời gọi ngoài), không chạy lần hai cho `reserve` bên trong.

### 6.4. Spring service trong package con

Tệp `src/main/java/demo/service/internal/PricingService.java`:

```java
package demo.service.internal;

public class PricingService {

    public int price(String sku) {
        System.out.println("service.internal:price:" + sku);
        return 10;
    }
}
```

Type `PricingService` nằm dưới `demo.service.internal`. Biểu thức `within(demo.service..*)` **bao phủ package con**, nên method `price` sẽ khớp khi client gọi qua Spring proxy.

### 6.5. Repository nằm ngoài service layer

Tệp `src/main/java/demo/repository/InventoryRepository.java`:

```java
package demo.repository;

public class InventoryRepository {

    public void save(String sku) {
        System.out.println("repository:save:" + sku);
    }
}
```

`InventoryRepository` cũng là Spring bean nhưng có package `demo.repository`, nằm ngoài cây `demo.service`. Vì vậy aspect giới hạn bằng `within(demo.service..*)` không advise method `save`. Đây là bằng chứng về **phạm vi pointcut**, không phải vì repository không được Spring quản lý.

### 6.6. Aspect khai báo trong package riêng

Tệp `src/main/java/demo/aop/LayerAspect.java`:

```java
package demo.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class LayerAspect {

    @Pointcut("within(demo.service..*)")
    public void serviceTypes() {
    }

    @Pointcut("execution(public * *(..))")
    public void publicMethods() {
    }

    @Before("serviceTypes() && publicMethods()")
    public void beforeServiceCall(JoinPoint joinPoint) {
        String type = joinPoint.getTarget().getClass().getSimpleName();
        String method = joinPoint.getSignature().getName();
        System.out.println("advice:" + type + "." + method);
    }
}
```

Ở đây:
- `serviceTypes()` chỉ định phạm vi Java type nằm trong service và subpackages.
- `publicMethods()` yêu cầu public method execution.
- `@Before("serviceTypes() && publicMethods()")` chỉ chạy nếu **cả hai** điều kiện khớp.
- `JoinPoint.getTarget()` trả về target object, nên `getClass().getSimpleName()` hiển thị tên implementation ổn định trong ví dụ.
- `LayerAspect` không cần nằm cùng package với service. **Package của aspect** không phải thứ mà `within(demo.service..*)` đem ra kiểm tra.

### 6.7. Đăng ký bean và bật Spring AOP

Tệp `src/main/java/demo/config/AppConfig.java`:

```java
package demo.config;

import demo.aop.LayerAspect;
import demo.repository.InventoryRepository;
import demo.service.InventoryService;
import demo.service.internal.PricingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public InventoryService inventoryService() {
        return new InventoryService();
    }

    @Bean
    public PricingService pricingService() {
        return new PricingService();
    }

    @Bean
    public InventoryRepository inventoryRepository() {
        return new InventoryRepository();
    }

    @Bean
    public LayerAspect layerAspect() {
        return new LayerAspect();
    }
}
```

`@EnableAspectJAutoProxy` cho phép Spring phát hiện khai báo `@Aspect`. `LayerAspect` được đăng ký bằng `@Bean`, vì bản thân `@Aspect` không tự tạo Spring bean. Không dùng component scanning để ví dụ có đúng các bean đã liệt kê.

Bật `proxyTargetClass=true` giúp các service class không interface vẫn có AOP proxy theo lớp, nhưng không buộc `InventoryRepository` trở thành AOP proxy nếu nó không có advisor khớp.

### 6.8. Chương trình main và lệnh chạy

Tệp `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import demo.config.AppConfig;
import demo.repository.InventoryRepository;
import demo.service.InventoryService;
import demo.service.internal.PricingService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            InventoryService inventory =
                    context.getBean(InventoryService.class);
            PricingService pricing =
                    context.getBean(PricingService.class);
            InventoryRepository repository =
                    context.getBean(InventoryRepository.class);

            System.out.println("result=" + inventory.reserve("P-7"));
            System.out.println("price=" + pricing.price("P-7"));
            repository.save("P-7");

            inventory.reserveInternally();

            System.out.println("serviceProxy=" +
                    AopUtils.isAopProxy(inventory));
            System.out.println("childProxy=" +
                    AopUtils.isAopProxy(pricing));
            System.out.println("repositoryProxy=" +
                    AopUtils.isAopProxy(repository));
        }
    }
}
```

Từ thư mục project, chạy bằng Gradle cài sẵn:

```bash
gradle run
```

Nếu project đã có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

Những dòng do **ứng dụng Java** in ra, không tính thông tin build/logging của Gradle hoặc môi trường:

```text
advice:InventoryService.reserve
service:reserve:P-7
result=reserved:P-7
advice:PricingService.price
service.internal:price:P-7
price=10
repository:save:P-7
advice:InventoryService.reserveInternally
service:reserveInternally
service:reserve:SELF
serviceProxy=true
childProxy=true
repositoryProxy=false
```

### 6.9. Giải thích kết quả

- `advice:InventoryService.reserve` xuất hiện trước `service:reserve:P-7`: phương thức thuộc `demo.service` và được client gọi qua Spring AOP proxy.
- `advice:PricingService.price` xuất hiện trước `service.internal:price:P-7`: `..*` bao phủ type trong package con `demo.service.internal`.
- `repository:save:P-7` không có dòng advice đi trước: repository nằm ngoài phạm vi `within(demo.service..*)`.
- `advice:InventoryService.reserveInternally` xuất hiện khi client gọi method công khai đó qua proxy.
- **Không có** `advice:InventoryService.reserve` lần hai trước `service:reserve:SELF`: lời gọi nội bộ `this.reserve(...)` không đi qua proxy.
- `serviceProxy=true` và `childProxy=true` chứng minh hai service thực sự nhận Spring AOP proxy.
- `repositoryProxy=false` cho thấy repository không cần AOP proxy trong cấu hình ví dụ. Nó vẫn là một Spring bean được context quản lý.

Với cấu hình đơn giản này, ví dụ không phụ thuộc vào thứ tự nhiều aspect hay trạng thái cache/transaction. Nếu ứng dụng thật còn có những advisor khác, một repository có thể được proxy vì lý do khác mặc dù không khớp pointcut của `LayerAspect`.

## 7. Khi nào within không khớp như bạn kỳ vọng?

### 7.1. Package phù hợp nhưng gọi trực tiếp bằng new

```java
InventoryService service = new InventoryService();
service.reserve("MANUAL");
```

Đây là một object Java thường. Spring AOP proxy không được dùng nên không có advice của `LayerAspect`, dù tên package hoàn toàn khớp. Hãy lấy Spring-managed reference từ context hoặc inject qua Spring.

### 7.2. Package phù hợp nhưng self-invocation

`within` có thể mô tả đúng cả `reserve()` và `reserveInternally()`. Tuy nhiên, khi target thực hiện `this.reserve(...)`, lời gọi không đi qua AOP proxy. Việc đổi sang `@Around` hay mở rộng package pattern không khắc phục giới hạn đó.

Nếu cần hai method đều nhận advice, thiết kế một bean cộng tác khác rồi gọi qua Spring-managed proxy của bean đó. Chỉ dùng self-proxy access khi có lý do rõ ràng và đã hiểu chi phí phụ thuộc Spring AOP.

### 7.3. Chỉ dùng một dấu chấm wildcard

`within(demo.service.*)` không chọn các type trong `demo.service.internal`. Với cấu trúc package con thường xuyên phát triển, hãy cân nhắc `within(demo.service..*)` nếu yêu cầu thực sự bao phủ toàn bộ service layer.

Ngược lại, nếu chỉ muốn classes trực tiếp trong `demo.service`, dùng `.*` có thể chính xác hơn. Đừng tự động dùng `..*` cho toàn bộ ứng dụng nếu có package tiện ích, infrastructure hoặc implementation nội bộ không muốn advise.

### 7.4. Type được khai báo ở package khác nhưng target kế thừa method

Ví dụ một method triển khai ở `com.example.common.BaseService` được thừa kế bởi target trong `com.example.app.service`. Điểm cắt `within(com.example.app.service..*)` và điều kiện chọn target runtime không phải luôn tương đương. Điểm cần kiểm tra là **method implementation/declaring type mà Spring xét** khi xây interceptor chain.

Muốn chọn **target có kiểu service** thay vì giới hạn phạm vi khai báo method, cân nhắc `target(com.example.app.service.SomeService)` hoặc thêm các ràng buộc khác rồi kiểm thử. Đối với JDK dynamic proxy, phương thức expose qua interface cũng có thể khác với method implementation, nên integration test trên proxy type thực tế là bằng chứng đáng tin hơn suy luận chỉ từ tên package.

### 7.5. Method private/final hoặc constructor

Spring AOP theo proxy không advice constructor execution. Class-based proxy không thể override `final` và `private` method; JDK proxy chỉ expose các method thuộc interface được proxy. `within` không biến những lời gọi không thể intercept thành join point được Spring chặn.

Để kiểm tra proxy type:

```java
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
```

Đây là snippet chẩn đoán; cần biến `bean` là Spring-managed bean và import `AopUtils`. Không nên dựa vào tên class proxy vì naming có thể thay đổi theo phiên bản.

### 7.6. Annotation/service scanning bị nhầm với pointcut

`@ComponentScan("com.example.app.service")` là cấu hình **khám phá bean**. `within(com.example.app.service..*)` là cấu hình **chọn method join point** của Spring AOP. Đặt pointcut đúng mà bean chưa được register cũng không tạo bean. Ngược lại, scan toàn service thành Spring bean cũng không tự bật Spring AOP nếu thiếu hạ tầng/aspect phù hợp.

## 8. Phối hợp within với kiến trúc phân lớp

Giả sử ứng dụng có ba layer:

```text
com.example.shop
├── web
│   ├── OrderController
│   └── admin/AdminController
├── service
│   ├── OrderService
│   └── pricing/PriceService
└── repository
    ├── OrderRepository
    └── jdbc/JdbcOrderRepository
```

Có thể tạo named pointcut theo layer:

```java
@Pointcut("within(com.example.shop.web..*)")
public void webLayer() {
}

@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {
}

@Pointcut("within(com.example.shop.repository..*)")
public void repositoryLayer() {
}

@Pointcut("serviceLayer() && execution(public * *(..))")
public void publicServiceOperation() {
}
```

Đây là **snippet trong một lớp `@Aspect`**, không phải chương trình độc lập; các method có thân rỗng và return type `void`. Điểm hay của việc đặt tên là nếu package layout thay đổi, chỉ cần chỉnh expression ở một nơi.

Tuy nhiên, “layer” là một quyết định thiết kế ứng dụng:
- Một lớp `OrderService` thuộc package service nhưng được đăng ký nhiều lần dưới các bean name khác nhau vẫn thuộc phạm vi `within` tương ứng.
- Một bean có tên `orderService` nhưng class thuộc package infrastructure **không tự** khớp `within(service..*)`.
- Một aspect được đặt trong `com.example.shop.aop` vẫn có thể advise service/repository, vì pointcut xét method execution của target chứ không bắt buộc aspect phải ở cùng package.

Nếu service API được định nghĩa bằng interface nằm ở các module/package khác implementation, kết hợp `within` với `execution`/`target` hoặc thiết kế pointcut theo business interface có thể rõ hơn. Tài liệu Spring chính thức cũng phân biệt pointcut theo **phạm vi layer** và pointcut theo **method trên service interface**.

## 9. Hiệu năng và phạm vi áp dụng

Pointcut `within` có thể giúp Spring/AspectJ expression matcher loại sớm những lớp không thuộc phạm vi cần xét, giảm phạm vi phải đánh giá các điều kiện khác. Điều này đặc biệt hữu ích khi aspect có nhiều advisor hoặc expression phức tạp.

Dù vậy, không nên xem `within` là giải pháp tối ưu hiệu năng duy nhất:
- Chi phí trong ứng dụng còn phụ thuộc số bean/proxy, số method được gọi, loại advice, logging I/O và công việc thực hiện trong advice.
- Pointcut quá rộng như `within(com.example..*)` có thể advise những bean không mong muốn.
- Các điều kiện runtime như `args` hoặc binding annotations có thể yêu cầu kiểm tra nhiều hơn so với các điều kiện type/method static.
- Cần đo trên workload thực khi có yêu cầu hiệu năng; đừng bịa ra mức tăng tốc cố định.

Thực hành tốt là **giới hạn theo type/package trước**, sau đó kết hợp điều kiện method signature hoặc annotation cho chính xác. Chẳng hạn:

```java
@Pointcut("within(com.example.shop.service..*)"
        + " && execution(public * *(..))"
        + " && @annotation(com.example.shop.Traceable)")
public void tracedPublicServiceMethod() {
}
```

Nếu `Traceable` là annotation runtime trên những method cần quan sát, biểu thức trên hạn chế advice đúng những thao tác cụ thể trong service layer. Khi không cần annotation, không nên thêm điều kiện chỉ để có biểu thức phức tạp hơn.

## 10. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Service trong package con không có advice | Đã dùng `within(service.*)` thay vì `within(service..*)` | Kiểm tra đầy đủ package của target và expression |
| Repository cũng có advice dù đang lọc service | Aspect khác hoặc advisor khác cũng khớp; repository nằm nhầm trong package service | Inspect advisor chain và package thật |
| Bean thuộc service package nhưng không được proxy | Aspect chưa thành bean, AOP chưa bật hoặc không có advisor phù hợp | Kiểm tra Spring context, `@EnableAspectJAutoProxy`, `AopUtils` |
| Cùng method advice chạy từ controller nhưng không chạy từ method nội bộ | Self-invocation bypass proxy | So sánh call path và tách bean nếu cần |
| Bean tạo qua `new` không có advice | Object không được container quản lý | Inject hoặc `getBean` từ Spring |
| Lời gọi public của superclass không khớp kỳ vọng | Declaring type của method và target runtime type khác nhau | Thử `target` hoặc `execution`; test trên proxy thật |
| Chỉ muốn bean name kết thúc `Service` | `within` lọc type, không lọc bean name | Dùng `bean(*Service)` hoặc kết hợp điều kiện |
| Muốn lớp có annotation bất kể package | Lọc package bằng `within` không thể hiện yêu cầu annotation | Dùng `@within` hoặc `@target` theo semantics mong muốn |
| `private`/`final` method không có advice qua CGLIB | Không thể override | Thay boundary/API hoặc chọn mô hình phù hợp |
| Service được scan nhưng `@Before` không in | Scan bean khác với kích hoạt AOP; có thể pointcut sai | Kiểm tra aspect registration, proxy, method và package |
| AOP có JDK proxy nhưng client cố cast về implementation | JDK proxy triển khai interface, không subclass | Inject interface hoặc xem lại cấu hình proxy type |

## 11. Checklist trước khi đưa within vào ứng dụng

1. **Xác định đúng package tree.** Cần type trong đúng package hay cả subpackages?
2. **Xác định method cần advice.** Mọi public method hay chỉ một tên/annotation cụ thể?
3. **Đăng ký aspect thành Spring bean.** `@Aspect` không tự thay cho `@Component` hoặc `@Bean`.
4. **Bật AOP trong ApplicationContext sở hữu target.** Với Spring Framework thuần dùng `@EnableAspectJAutoProxy`; Spring Boot có thể tự cấu hình khi đủ dependency.
5. **Kiểm tra proxy type.** JDK/CGLIB ảnh hưởng method có thể intercept; đối với type inheritance, cần test cụ thể.
6. **Chạy test qua Spring-managed reference.** `new` và self-invocation không kiểm chứng advice có khớp.
7. **Quan sát một method khớp và một method không khớp.** Nên có cả ví dụ thuộc package con và ngoài service để chứng minh phạm vi.
8. **Giữ expression đủ hẹp.** Không áp dụng logging, security validation hoặc tracing lên toàn package tree nếu không có lý do.

## 12. Kết luận

`within` là cách diễn đạt rõ ràng **ranh giới lớp và package** cho Spring AOP. Mẫu `within(com.example.service..*)` cho phép giới hạn method-execution join point vào service layer, kể cả các subpackages, còn `within(com.example.service.*)` hẹp hơn ở đúng package. Kết hợp `within` với `execution` hoặc annotation giúp vừa giới hạn layer vừa giới hạn thao tác.

Tuy nhiên, **type pattern khớp chưa đủ để advice chạy**: bean phải được Spring quản lý, AOP được bật, proxy phải được tạo và lời gọi phải đi qua proxy. Với JDK/CGLIB, inherited methods và self-invocation, cần kiểm tra hành vi thực tế thay vì chỉ nhìn đường package trong mã nguồn.

### Tài liệu Spring chính thức

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): `within`, `execution`, `this`, `target`, `bean`, wildcard và cách kết hợp pointcut.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký `@Aspect` và kích hoạt Spring AOP.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): giới hạn Spring AOP proxy và self-invocation.
- [Spring Framework — Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): `ClassFilter`, `MethodMatcher` và `AspectJExpressionPointcut`.
