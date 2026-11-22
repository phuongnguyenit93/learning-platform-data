# Tái cấu trúc để chuyển lời gọi sang một bean cộng tác trong Spring AOP

## 1. Mục tiêu: tạo ranh giới lời gọi thực sự đi qua Spring proxy

Khi một service Spring gọi method khác **trên chính target instance** bằng `this.method()`, lời gọi đó không quay qua proxy mà Spring AOP tạo. Advice của `@Aspect` trên method được gọi nội bộ có thể **không chạy**, dù cùng method ấy được chặn khi một bean khác gọi tới qua proxy.

Một hướng sửa dễ hiểu và ít phụ thuộc hạ tầng là **tách phần công việc cần interception sang một Spring bean cộng tác**, rồi để service gốc **inject** bean đó và gọi method qua reference Spring-managed.

```text
TRƯỚC (không có boundary proxy cho method nội bộ)

Caller --> Spring proxy của OrderService --> target OrderService.place()
                                               |
                                               +--> this.validate() --X--> proxy
                                                  (không chạy advice dành cho validate)

SAU (boundary proxy của collaborator)

Caller --> Spring bean OrderApplicationService.place()
                         |
                         +--> injected ValidationService proxy
                                      |
                                      +--> advice cho ValidationService.validate()
                                      |
                                      +--> target ValidationService.validate()
```

**Điều kiện then chốt không phải chỉ là có hai class.** Bean cộng tác phải được Spring tạo/quản lý, caller phải giữ **tham chiếu proxy do Spring inject**, method phải được proxy kiểu tương ứng chặn được, pointcut phải match và aspect phải được đăng ký/bật trong cùng context thích hợp.

Bài chỉ tập trung vào **Spring AOP @AspectJ và lời gọi qua Spring bean/proxy**, vì đó là phạm vi của chủ đề Spring Aspect. Tách bean là kỹ thuật tổ chức code, nhưng động cơ và cách kiểm chứng ở đây là **sửa ranh giới interception của Spring**, không phải giới thiệu nguyên lý AOP tổng quát.

## 2. Chẩn đoán đúng self-invocation trước khi refactor

Ví dụ ban đầu:

```java
@Service
public class OrderService {
    public String place(String id) {
        return validate(id); // tương đương this.validate(id)
    }

    public String validate(String id) {
        return "validated:" + id;
    }
}
```

Giả sử Spring có aspect:

```java
@Aspect
@Component
public class ValidationAspect {
    @Before("execution(public * com.example.orders.OrderService.validate(..))")
    public void beforeValidation() {
        System.out.println("audit:validate");
    }
}
```

Hai đoạn là **minh họa**, chưa phải ứng dụng chạy độc lập vì cần đúng package, Spring context, `@EnableAspectJAutoProxy` hoặc Boot AOP auto-configuration và dependencies tương ứng.

Nếu `OrderService` đã được Spring proxy và pointcut match:

- Một bean khác gọi `orderService.validate("A")` qua injected proxy → **có thể** in `audit:validate`.
- Gọi `orderService.place("A")` qua proxy → target thực thi `place`, nhưng trong target lời gọi `this.validate("A")` đi **trực tiếp**, không trở về proxy; advice chỉ nhắm `validate` **không chạy** cho lời gọi ấy.
- `AopUtils.isAopProxy(orderService) == true` không chứng minh `validate` đã được chặn trên mọi đường gọi.
- Chuyển `validate` thành `public` hoặc bật `proxyTargetClass=true` không làm self-invocation quay qua proxy.
- Thêm `@Transactional`, `@Cacheable`, `@Async` hoặc annotation dùng proxy vào method nội bộ cũng không thay thế đường gọi qua proxy; các tính năng ấy còn có cơ chế activation riêng.

**Vì sao cần refactor thay vì thêm một annotation?** Trong mô hình Spring AOP proxy, interceptor áp dụng khi một caller gọi **qua reference proxy**. `this` bên trong target là reference của đối tượng đang thực thi, không phải vòng quay qua proxy Spring. Tài liệu Spring gọi đây là self-invocation bypassing advice.

## 3. Mẫu refactor: chuyển một trách nhiệm sang collaborator

Giữ API nghiệp vụ `place(..)` trên service điều phối, đưa method cần advice sang bean `ValidationService`:

```java
@Service
public class ValidationService {
    public String validate(String id) {
        return "validated:" + id;
    }
}
```

```java
@Service
public class OrderApplicationService {
    private final ValidationService validationService;

    public OrderApplicationService(ValidationService validationService) {
        this.validationService = validationService;
    }

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

Hai đoạn minh họa giả sử chúng ở package được component scan bao phủ. Điểm thay đổi quan trọng:

1. `ValidationService` là **bean riêng**, có thể được Spring áp advisor để tạo proxy.
2. `OrderApplicationService` nhận dependency qua **constructor injection**; không tự gọi `new ValidationService()`.
3. `place(..)` gọi `validationService.validate(..)` trên reference đã inject; nếu reference là Spring AOP proxy, advice của `ValidationService.validate(..)` được đánh giá trước target.
4. API entry của application không phải đổi vì validation nay được ủy quyền sang collaborator.
5. Các rule về dữ liệu, exception và transaction boundary phải được xem lại theo trách nhiệm thực tế, không mặc nhiên giả định refactor thuần cấu trúc bảo toàn mọi semantics.

Spring không cần Spring bean riêng cho **mọi** private helper. Chỉ tách khi method có nhiệm vụ rõ ràng, là entry cần proxy advice, cần tái sử dụng/kiểm thử riêng hoặc tạo boundary đúng cho transaction, validation, audit, metric và security.

### 3.1. Đặt advice vào đúng lớp sau khi tách

Điểm cắt cũ nhắm method của `OrderService` phải được cập nhật nếu muốn advice đi theo phần trách nhiệm được chuyển:

```java
@Aspect
@Component
public class ValidationAspect {
    @Before(
        "execution(public * com.example.orders.ValidationService.validate(..))"
    )
    public void beforeValidation() {
        System.out.println("audit:validate");
    }
}
```

**Không coi thay đổi tên class là chi tiết tùy chọn.** Với pointcut dùng `execution(...)` trên fully-qualified class, sau refactor method đã chuyển sang type khác; nếu không đổi pointcut, advisor sẽ không match collaborator mới. Tương tự, nếu dùng pointcut `within(..)`, `bean(..)` hay annotation trên old service, cần xác nhận biểu thức có còn nhắm đúng bean/method hay không.

Có thể dùng **annotation đặc thù** trên collaborator method để giảm phụ thuộc tên class, nhưng annotation đó cũng phải được Spring AOP pointcut nhận diện ở đúng method thực hiện và vẫn cần caller đi qua proxy. Không nên quét pointcut quá rộng để “bắt bằng được” vì có thể chặn các bean ngoài ý muốn.

## 4. Demo chạy được: trước–sau trong cùng một Spring ApplicationContext

Demo dùng **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Gradle và Java configuration thuần. Một context chứa cả legacy service lẫn collaborator version để so sánh bằng cùng aspect. Không dùng Spring Boot để tự động bật proxy ngầm: chính `@EnableAspectJAutoProxy` thể hiện điều kiện Spring-specific.

### 4.1. Cấu trúc dự án

```text
spring-aop-collaborator-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/boundary/
    ├── Main.java
    ├── AppConfig.java
    ├── LegacyOrderService.java
    ├── ValidationService.java
    ├── OrderApplicationService.java
    └── TraceAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-collaborator-demo'
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
    mainClass = 'com.example.boundary.Main'
}
```

Spring Framework 6.x chạy trên Java 17+. Trong project Spring Boot thực tế nên để BOM/dependency management chọn versions tương thích, thay vì sao chép các phiên bản demo vào project đang dùng Boot major khác.

### 4.2. Legacy service — lời gọi nội bộ

**`LegacyOrderService.java`**

```java
package com.example.boundary;

public class LegacyOrderService {
    public String place(String id) {
        return validate(id); // self-invocation: bypass advice trên validate
    }

    public String validate(String id) {
        return "validated:" + id;
    }
}
```

Trong class này, `place` và `validate` đều public để thử nghiệm Spring proxy được phép can thiệp theo method signature. **Nguyên nhân thiếu advice không phải do visibility mà do call path.**

### 4.3. Bean cộng tác — method cần advice có entry riêng

**`ValidationService.java`**

```java
package com.example.boundary;

public class ValidationService {
    public String validate(String id) {
        return "validated:" + id;
    }
}
```

### 4.4. Service điều phối — inject collaborator thay vì self-call

**`OrderApplicationService.java`**

```java
package com.example.boundary;

public class OrderApplicationService {
    private final ValidationService validationService;

    public OrderApplicationService(ValidationService validationService) {
        this.validationService = validationService;
    }

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

`OrderApplicationService` không có method `validate`; mọi đường vào `place` dùng duy nhất dependency Spring inject vào constructor.

### 4.5. Aspect đếm điểm cắt thật sự được intercept

**`TraceAspect.java`**

```java
package com.example.boundary;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before(
        "execution(public * com.example.boundary.LegacyOrderService.validate(..))"
        + " || execution(public * com.example.boundary.ValidationService.validate(..))"
    )
    public void beforeValidation(JoinPoint point) {
        System.out.println(
            "advice:" + point.getSignature().getDeclaringType().getSimpleName()
            + "." + point.getSignature().getName()
        );
    }
}
```

Biểu thức pointcut dùng **phép OR** để đối chứng cùng một advice với hai method cụ thể. `getSignature().getDeclaringType().getSimpleName()` giúp nhận diện method chạy advice ở class nào. Không có advice trên `place(..)`, vì mục tiêu test là **method validate(..)` ở hai call paths**.

### 4.6. Spring config — xác định bean và proxy

**`AppConfig.java`**

```java
package com.example.boundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    LegacyOrderService legacyOrderService() {
        return new LegacyOrderService();
    }

    @Bean
    ValidationService validationService() {
        return new ValidationService();
    }

    @Bean
    OrderApplicationService orderApplicationService(
            ValidationService validationService) {
        return new OrderApplicationService(validationService);
    }
}
```

Chính factory method nhận `ValidationService` khiến Spring inject bean đã được xử lý bởi container. Target method `validate` khớp aspect nên `ValidationService` thường được Spring wrap bởi class-based proxy. Không có `new ValidationService()` trong `OrderApplicationService`.

`TraceAspect` là `@Aspect` **Spring-managed bean** do `@Bean` tạo. `@EnableAspectJAutoProxy` cho phép Spring xem advice và auto-proxy các target phù hợp. Cấu hình `proxyTargetClass=true` giúp các target không có interface vẫn được truy xuất theo concrete class trong ví dụ.

### 4.7. Main — quan sát hai đường gọi

**`Main.java`**

```java
package com.example.boundary;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            LegacyOrderService legacy =
                    context.getBean(LegacyOrderService.class);
            ValidationService validation =
                    context.getBean(ValidationService.class);
            OrderApplicationService refactored =
                    context.getBean(OrderApplicationService.class);

            System.out.println("legacyProxy=" + AopUtils.isAopProxy(legacy));
            System.out.println(
                    "collaboratorProxy=" + AopUtils.isAopProxy(validation)
            );

            System.out.println("legacyInternal=" + legacy.place("A"));
            System.out.println("legacyExternal=" + legacy.validate("B"));
            System.out.println("afterRefactor=" + refactored.place("C"));
        }
    }
}
```

Tại thư mục project, chạy:

```bash
gradle run --quiet
```

Nếu đã có Gradle Wrapper: `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

**Các dòng do `System.out` của demo in ra, theo đúng thứ tự:**

```text
legacyProxy=true
collaboratorProxy=true
legacyInternal=validated:A
advice:LegacyOrderService.validate
legacyExternal=validated:B
advice:ValidationService.validate
afterRefactor=validated:C
```

Đây là output của code ứng dụng, không tính warning/log ngoài ý muốn do JVM/build tool hoặc logging configuration.

### 4.8. Vì sao stdout thể hiện đúng vấn đề và đúng cách sửa?

| Lời gọi | Spring proxy entry thực tế | Kết quả advice trên `validate(..)` |
| --- | --- | --- |
| `legacy.place("A")` | Caller đi qua proxy `LegacyOrderService` cho method `place`, sau đó target dùng `this.validate` | **Không có** `advice:LegacyOrderService.validate` cho case này |
| `legacy.validate("B")` | Caller trực tiếp vào proxy `LegacyOrderService` trên method `validate` | Có `advice:LegacyOrderService.validate` |
| `refactored.place("C")` | Caller vào `OrderApplicationService` (không nhất thiết proxy); service gọi **injected proxy** `ValidationService.validate` | Có `advice:ValidationService.validate` |

Cả hai phép thử `legacyProxy=true` và `collaboratorProxy=true` đều chứng minh **proxy có tồn tại**, nhưng chúng **không thay thế** phép kiểm tra advice trên call path cụ thể. Chính việc advice chỉ xuất hiện ở lời gọi ngoài (legacy) và collaborator (refactored) là bằng chứng cho sự khác biệt.

Method `OrderApplicationService.place` trong demo **không cần AOP proxy** vì không có advisor match vào nó. Điều quan trọng là nó nắm được **dependency reference** tới Spring proxy của `ValidationService`. Đó là lý do “tách bean cộng tác” có hiệu quả mà không cần self-injection hay `AopContext.currentProxy()`.

## 5. Vì sao việc chuyển sang một class Java thường chưa đủ?

Thí dụ **vẫn sai** nếu tự tạo cộng tác viên:

```java
public class OrderApplicationService {
    private final ValidationService validationService =
            new ValidationService(); // không do Spring quản lý

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

Code có hai class thật, nhưng reference không phải Spring-managed proxy. `@Aspect` Spring không tự intercept object tạo bằng `new`; chuyển method sang file mới mà vẫn tự tạo instance chỉ thay đổi cấu trúc, **không tạo ranh giới AOP**.

**Cách đúng** là inject constructor từ container:

```java
public class OrderApplicationService {
    private final ValidationService validationService;

    public OrderApplicationService(ValidationService validationService) {
        this.validationService = validationService;
    }

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

Đăng ký `ValidationService` bằng `@Component`/`@Service` kèm component scan đúng package, hoặc bằng `@Bean`. Caller cũng nên nhận `OrderApplicationService` từ context thay vì `new` một object tự lắp dependency, nhằm nhất quán với lifecycle và cấu hình của ứng dụng.

### 5.1. Hai cách đăng ký collaborator hợp lệ

**Component scan:**

```java
@Service
public class ValidationService {
    public String validate(String id) {
        return "validated:" + id;
    }
}
```

```java
@Service
public class OrderApplicationService {
    private final ValidationService validationService;

    public OrderApplicationService(ValidationService validationService) {
        this.validationService = validationService;
    }

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

Với component scan, `@Service` tạo bean candidates. Nếu aspect class dùng `@Aspect`, cần thêm `@Component` hoặc `@Bean` để chính nó cũng là Spring bean.

**Đăng ký bằng `@Bean`:** như `AppConfig` trong demo hoàn chỉnh, class không cần `@Service` và bean được wiring qua tham số factory method. Chọn một phương thức đăng ký rõ ràng, tránh đồng thời component-scan và `@Bean` tạo hai instance cùng loại gây injection ambiguity hoặc advisor side effect khác dự kiến.

### 5.2. Scope và context phải phù hợp

Bean collaborator cần tồn tại trong context thích hợp. Với ứng dụng có root/child `ApplicationContext`, proxy infrastructure và advisor có phạm vi của context; không tự suy bật AOP ở context này thì mọi target trong context khác đều được proxy.

Một collaborator singleton có thể dùng chung cho nhiều callers; không cần tạo bản sao cho từng caller chỉ để advice chạy. Nếu collaborator chứa mutable request state, việc trở thành singleton bean tạo **rủi ro concurrency riêng**, cần thiết kế stateless hoặc truyền trạng thái qua tham số. Không cất user/order hiện tại vào field của aspect/collaborator singleton.

## 6. Giữ nguyên semantics khi đổi ranh giới bean

Kỹ thuật refactor chỉ an toàn khi xem xét **contract nghiệp vụ** trước và sau, chứ không đơn thuần chuyển code dòng nào sang class nào.

### 6.1. Input, output và exception

- Giữ chữ ký nghiệp vụ mà caller đang dựa vào hoặc có kế hoạch thay đổi API rõ ràng.
- Không vô tình swallow/đổi exception chỉ vì thêm wrapper bean.
- Nếu advice là `@Around` có `proceed()`, giữ đúng số lần gọi target và đúng semantics truyền args/return/exception. Refactor làm advice xuất hiện thêm có thể khiến logic retry, timeout hoặc logging chạy **thực sự** lần đầu; cần review side effects.
- Nếu helper trước đây dùng field private của lớp cũ, **đừng tự động expose mutable field**, mà truyền dữ liệu cần thiết vào collaborator qua method arguments hoặc một dependency rõ ràng.

### 6.2. Transaction boundary có thể đổi

Spring `@Transactional` là một ví dụ điển hình của proxy interception. Cần phân biệt:

```java
@Service
public class ImportService {
    public void runBatch() {
        savePart(); // self-call: transaction advice của savePart không chạy
    }

    @Transactional
    public void savePart() {
        // cập nhật dữ liệu
    }
}
```

Nếu chuyển `savePart()` sang `ImportWriter` Spring bean và inject vào `ImportService`, lời gọi từ `runBatch()` qua injected proxy có thể kích hoạt transaction interceptor **khi transaction management được bật** và có `PlatformTransactionManager` phù hợp.

Điều đó làm **thay đổi semantics thật**, không chỉ khắc phục log advice:

- Với `Propagation.REQUIRED`, nếu outer có transaction thì inner thường tham gia transaction đang có; nếu không, transaction interceptor có thể bắt đầu transaction mới.
- Với `REQUIRES_NEW`, việc qua proxy có thể tạo transaction riêng với khả năng commit/rollback độc lập; trước refactor self-call có thể đã bỏ qua yêu cầu này.
- `@Transactional` trên method của collaborator chỉ hoạt động nếu activation/configuration Spring transaction đầy đủ, method intercept được và caller đi qua proxy. `@EnableAspectJAutoProxy` đơn lẻ **không kích hoạt** `@Transactional`.
- Exception translation/checked exceptions/rollback rules phụ thuộc cấu hình transaction; không suy mọi exception đều rollback.

Đây là **đoạn minh họa** không chứa DB configuration và không phải project runnable. Nếu thay đổi transaction boundary, phải viết integration test với database/test container phù hợp để kiểm chứng rollback/commit theo yêu cầu, thay vì chỉ đếm advice in console.

### 6.3. Security, caching và async cũng có boundary

| Spring capability | Nếu self-call ban đầu bypass proxy | Sau khi chuyển sang injected collaborator |
| --- | --- | --- |
| Spring `@Aspect` audit/metrics | Advice không chạy ở method nội bộ | Advisor có thể chạy trên entry method của collaborator nếu pointcut match |
| `@Transactional` | Inner transaction interceptor có thể bị bỏ qua | Có thể tạo/tham gia transaction theo propagation thực tế |
| `@Cacheable`/`@CacheEvict` | Cache advice của inner method bị bypass | Cache advice có thể hoạt động, thay đổi cache hit/miss/eviction |
| `@Async` | Inner method có thể chạy cùng caller thread thay vì qua executor | Method được gọi qua proxy có thể được submit sang executor; chú ý exception handling/context propagation |
| Method security như `@PreAuthorize` | Inner authorization advice bị bypass | Có thể được thực thi khi method-level security được bật và policy match |

Các tính năng ở bảng **có enable/configuration riêng**, không bật đồng loạt bởi một `@Aspect` annotation. Khi boundary mới làm interception thật sự chạy, hãy kiểm tra thay đổi về transaction, thread, latency, retry, audit logs và bảo mật. Đặc biệt không coi việc “trước đây pass test” là đủ nếu những test đó vô tình bỏ qua policy.

### 6.4. Nếu pointcut dùng bean name hoặc type

Khi chuyển code từ bean `orderService` sang `validationService`:

- `bean(orderService)` không tự match bean mới; cần cập nhật bean name expression nếu muốn advice theo collaborator.
- `within(com.example.orders.OrderService)` hoặc `execution(* OrderService.*(..))` có thể không còn match.
- `@annotation(...)` match annotation trên method thực tế: nếu annotation chuyển sang collaborator method, hãy xác minh type annotation, visibility và interface proxy tương ứng.
- `this(...)` nhắc tới proxy type; `target(...)` nhắc tới target type; JDK proxy và class proxy có thể làm kết quả type matching khác nhau.
- Nếu chặn một interface contract, public method phải thuộc interface được proxy khi dùng JDK dynamic proxy.

Dùng pointcut có scope chặt; sau refactor tránh làm biểu thức quá rộng chỉ để không phải sửa tên lớp.

## 7. Thiết kế ranh giới collaborator tốt

Một cách phân chia hợp lý là:

```text
OrderApplicationService (orchestrator)
  - gọi các bước nghiệp vụ và giữ API use case
  - phối hợp kết quả/exception
  - chỉ chứa logic orchestration cần thiết
          |
          +--> ValidationService (Spring-managed collaborator)
                 - một trách nhiệm dễ gọi qua proxy
                 - public validation operation
                 - pointcut/advisor đúng phạm vi
                 - dependency rõ ràng
```

Các tiêu chí:

1. **Cohesion:** collaborator nên đại diện một trách nhiệm/use case phụ có tên thật (validate, charge, persist, applyRule), không phải lớp `AopWorkaroundService` vô nghĩa.
2. **Constructor injection:** dependency explicit, dễ thay bằng test double và không tạo vòng phụ thuộc ẩn.
3. **Public entry contract:** trong thiết kế phổ biến, method cần interception là public và non-final để tương thích chắc chắn với class proxy. Với JDK proxy, method cần nằm trên interface.
4. **Không cyclic dependencies:** A → B rõ ràng; nếu B lại cần A, cân nhắc tách thêm trách nhiệm chứ đừng dùng circular proxy hoặc self-injection.
5. **Không chuyển toàn bộ private helpers chỉ vì AOP:** helper không cần advice có thể giữ private và được gọi trực tiếp.
6. **Scope phù hợp:** thường là stateless singleton; không lưu request-sensitive mutable data trong collaborator singleton.
7. **Không bỏ sót caller cũ:** cập nhật tất cả call paths cần policy, không chỉ đường gọi mới trong demo.
8. **Giữ xử lý lỗi:** bảo toàn contract ném exception/return value, trừ khi thay đổi đã được quyết định và test.

### Khi service gốc vẫn cần chính advice trên method của nó

Không nhất thiết mọi advice phải chuyển sang collaborator. Nếu concern áp dụng vào **toàn bộ operation `place()`**, thay vì riêng `validate()`, có thể cân nhắc gắn pointcut vào entry public method `place()` vốn đã được caller bên ngoài gọi qua proxy. Đó có thể là boundary tự nhiên hơn khi policy cần bao phủ cả quy trình.

Nhưng nếu yêu cầu là **chỉ validate step** phải có transaction/cache/audit riêng, đưa step đó sang collaborator là cách bảo đảm một entry proxy rõ ràng. Quyết định nên theo semantics mong muốn, không theo một thủ thuật proxy mặc định.

## 8. Những cách né self-invocation và vì sao collaborator thường tốt hơn

### 8.1. Self-injection

Một số code cố tiêm chính proxy vào bean:

```java
@Service
public class RiskyService {
    @Autowired
    private RiskyService self;

    public void outer() {
        self.inner();
    }

    public void inner() {
        // mong advice chạy
    }
}
```

Đây là **mã minh họa**, không thuộc demo runnable. Self-injection có thể kéo theo circular dependency, khó hiểu thời điểm wiring, phụ thuộc config Boot/Spring và không giải quyết phân chia trách nhiệm. Dù có thể dùng proxy khi bean đã init, đây **không phải lựa chọn khuyến khích** cho thiết kế lâu dài.

### 8.2. `AopContext.currentProxy()`

```java
((RiskyService) AopContext.currentProxy()).inner();
```

Đây cũng chỉ là đoạn minh họa: cần `@EnableAspectJAutoProxy(exposeProxy=true)`, đang ở trong lời gọi qua proxy, kiểu cast phù hợp (có thể là interface với JDK proxy), và import `org.springframework.aop.framework.AopContext`. Nó làm code nghiệp vụ phụ thuộc API AOP của Spring, không thể gọi tùy ý trong constructor/`@PostConstruct` và không tự lan qua thread async.

**Khác biệt:** collaborator giữ code nghiệp vụ gần như không cần biết AOP đang được bật; chỉ biết một dependency interface/class được inject. Đây cũng là hướng refactor được tài liệu Spring khuyến nghị trước những phương án tự dùng proxy.

### 8.3. ApplicationContext.getBean chính mình

```java
MyService proxy = applicationContext.getBean(MyService.class);
proxy.inner();
```

Nếu class phải biết `ApplicationContext` để gọi lại chính nó, thiết kế đang tăng coupling vào container và có thể tạo lỗi init/circular dependency. Trong code startup, proxy còn có thể chưa hoàn tất. Trừ trường hợp infrastructure thực sự cần service locator, ưu tiên constructor injection collaborator.

### 8.4. AspectJ weaving

AspectJ compile-time/load-time weaving có cơ chế khác và có thể xử lý lời gọi không đi qua Spring proxy trong một số trường hợp. Tuy nhiên, `@EnableAspectJAutoProxy` **không bật weaving**. Nếu yêu cầu phù hợp với method call qua proxy, tái cấu trúc collaborator thường đơn giản hơn triển khai agent/compiler weaving. Chỉ đánh giá weaving riêng khi thật sự cần chặn hành vi ngoài khả năng proxy như constructor/field access hoặc internal call mà không thể thay cấu trúc.

## 9. Những lỗi Spring thường gặp sau refactor

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Tách class xong advice vẫn không chạy | Collaborator được tạo bằng `new`, không là Spring bean | Đăng ký `@Component`/`@Service` + scan, hoặc `@Bean`; inject từ context |
| Có Spring bean nhưng advice vẫn không chạy | Aspect không là bean, thiếu `@EnableAspectJAutoProxy`/Boot AOP auto-config hoặc pointcut cũ | Liệt kê aspect beans, kiểm tra config, match method/target mới |
| `AopUtils.isAopProxy(collaborator)==false` | Không có advisor match, target không đủ điều kiện proxy, context sai | Kiểm tra pointcut và auto-proxy infrastructure |
| Proxy true nhưng không thấy advice | Caller vẫn tự gọi helper trên target hoặc advice nhắm method khác | Trace call path, chạy test gọi thẳng collaborator qua Spring reference |
| Class final hoặc method final | Class-based Spring proxy không subclass/override được | Refactor entry method hoặc dùng JDK interface proxy nếu thích hợp |
| Inject bằng concrete implementation bị lỗi khi dùng JDK proxy | Proxy chỉ implement interface | Inject theo interface, hoặc cân nhắc class proxy nếu class đủ điều kiện |
| Spring báo circular dependency | Bean A inject B và B lại inject A, hoặc tự inject | Phá vòng, tách trách nhiệm, giữ graph phụ thuộc một chiều |
| Advice chạy hai lần | Pointcut bắt cả outer và inner, nhiều aspect/advisors/bean registrations cùng áp | Kiểm tra log join point, số bean aspect, advisor order và scope |
| Transaction/caching/async hành vi khác trước | Refactor làm method vốn không được proxy nay được intercept | Kiểm thử semantics mong muốn, propagation/cache keys/thread context |
| Logging bị mất sau đổi class | Pointcut phụ thuộc tên type/bean/annotation cũ | Cập nhật và test expression theo collaborator |
| Lời gọi từ `@PostConstruct` vẫn không có advice | Callback trong target initialization chưa đi qua proxy | Chọn startup hook phù hợp và gọi collaborator qua injected proxy sau khởi tạo |
| Test tạo object bằng `new` nhưng kỳ vọng AOP | Test bypass Spring container | Viết integration test có ApplicationContext thực |

### 9.1. Cách kiểm tra chính collaborator có thực sự là proxy

```java
ValidationService bean = context.getBean(ValidationService.class);
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Trong demo, hai kết quả là `true`. Đây là **đoạn minh họa** cần context và import như `Main.java`. Dùng thêm một recorder cho advice để kiểm tra lời gọi `bean.validate(..)` sinh event. **Proxy true không đồng nghĩa advice sẽ chạy trên bất cứ method nào.**

Với interface proxy, dùng `AopUtils.isJdkDynamicProxy(bean)` và tra cứu theo interface. Tránh cast sang concrete class khi runtime bean là JDK proxy.

## 10. Kiểm thử before/after để bảo đảm không đổi nghiệp vụ ngoài ý muốn

Chỉ nhìn stdout không đủ cho production. Một bộ test hợp lý gồm:

1. **Baseline nghiệp vụ:** cùng dữ liệu hợp lệ/không hợp lệ, cả legacy và refactored trả output/exception theo contract dự kiến.
2. **Bean wiring:** context có `ValidationService` và `OrderApplicationService` đúng một bean có chủ đích; dependency là bean Spring.
3. **Target proxy:** `AopUtils.isAopProxy(validationService)` true khi advisor cần thiết được đăng ký.
4. **Interception:** recorder test khẳng định `refactored.place(..)` kích hoạt đúng một event từ collaborator, trong khi legacy self-invocation không có event `validate`.
5. **Pointcut chính xác:** method khác trên collaborator không được advice nếu ngoài phạm vi; tránh advisor match ngoài ý muốn.
6. **Exception path:** lỗi từ collaborator được propagate/translate theo contract, không bị advice nuốt.
7. **Transaction/security/caching:** nếu có, test các hiệu ứng nghiệp vụ thật (rollback/deny/cache hit), không chỉ assert console log.
8. **Concurrent calls:** collaborator/aspect singleton không lưu trạng thái mutable theo request; kiểm tra thread-safety nếu dependency dùng chung.
9. **Context startup:** không tạo circular dependency hoặc gọi sớm trước proxy hoàn thành.
10. **Regression:** những caller cũ vẫn đi qua đúng public API; không có đường gọi bỏ qua collaborator để vi phạm policy.

### 10.1. Integration test bằng Spring context, không dựa vào `new`

Để test thật sự AOP, dùng `AnnotationConfigApplicationContext` như demo hoặc, nếu có Spring Test, `@SpringJUnitConfig` với cấu hình phù hợp. `new ValidationService()` test business method nhưng **không** chứng minh advice vì không có auto-proxy infrastructure.

Một test sink/recorder có thể thay lời `System.out`:

```java
public final class EventRecorder {
    private final java.util.List<String> events =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    public void record(String value) {
        events.add(value);
    }

    public java.util.List<String> events() {
        return java.util.List.copyOf(events);
    }
}
```

Đây là **đoạn Java minh họa** không ghép tự động vào demo; muốn chạy test hãy thêm bean `EventRecorder` và inject vào `TraceAspect`, sau đó assert số event và thứ tự trong luồng đồng bộ. Nếu lời gọi chạy qua `@Async`/nhiều thread, thứ tự event giữa các thread không cố định và cần đồng bộ/đợi hoàn thành trước khi assert.

### 10.2. Tránh kiểm thử chống lại cấu hình production

Đôi lúc unit test dùng một mock `ValidationService` trực tiếp trong constructor `OrderApplicationService`. Điều này tốt để kiểm tra orchestration, nhưng mock **không phản ánh Spring proxy**. Phải kết hợp test unit và integration test để chứng minh cả logic nghiệp vụ lẫn behavior của advisor.

Một bài kiểm thử thực tế nên fail nếu ai đó “tối ưu” bằng cách thay injected collaborator bằng `new` hoặc đưa method về self-call mà không biết rằng AOP sẽ bị bỏ qua.

## 11. Áp dụng trong Spring Boot

Với Spring Boot có AOP auto-configuration và dependency phù hợp, thường không cần tự ghi `@EnableAspectJAutoProxy`, nhưng cách refactor không đổi:

```java
@Service
public class OrderApplicationService {
    private final ValidationService validator;

    public OrderApplicationService(ValidationService validator) {
        this.validator = validator;
    }

    public String place(String id) {
        return validator.validate(id);
    }
}
```

```java
@Service
public class ValidationService {
    public String validate(String id) {
        return "validated:" + id;
    }
}
```

Với `@Aspect` class tương ứng có `@Component`, Spring Boot cần dependency AOP tương ứng để kích hoạt proxy. Ví dụ Gradle (chọn theo major version, dùng Boot dependency management):

```gradle
// Spring Boot 3.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

```gradle
// Spring Boot 4.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

Hai khối **là hai lựa chọn riêng**, không chép đồng thời. Việc có Spring AOP starter không tự tạo aspect bean: `@Aspect` phải được component scan tìm thấy qua `@Component` hoặc được đăng ký bằng `@Bean`. Đặt các classes dưới package scan của `@SpringBootApplication` hoặc import cấu hình phù hợp.

Spring Boot thường chọn class proxy theo `spring.aop.proxy-target-class=true`; nếu dùng interface và muốn JDK proxy, xét `spring.aop.proxy-target-class=false`. Kết quả còn có thể chịu tác động từ cấu hình proxy khác. Hãy kiểm tra proxy thực tế, nhất là khi refactor sang final class, Kotlin class mặc định final hoặc chỉ inject qua interface.

## 12. Quy trình refactor có thể áp dụng cho một codebase thật

### Bước 1 — Xác định đường gọi mất advice

Vẽ đường gọi **từ caller đến target** và đánh dấu reference thuộc Spring bean/proxy hay instance tự tạo. Lấy một case tái hiện được: gọi qua external Spring bean thì advice xuất hiện, gọi nội bộ thì không.

### Bước 2 — Xác định method và concern cần interception

Không mặc định tách mọi helper. Chọn phần công việc cần một Spring proxy boundary **thật sự**: audit của bước validation, transaction độc lập cho write, cache cho lookup, security policy ở public operation.

### Bước 3 — Tách method với contract rõ ràng

Tạo một collaborator có tên nghiệp vụ và public method có thể proxy. Chuyển input cần thiết sang tham số; giữ output/exception contract, tránh chia sẻ mutable state tùy tiện.

### Bước 4 — Đăng ký collaborator vào Spring

Dùng `@Service`/`@Component` trong package scan hoặc `@Bean` trong Spring configuration được nạp. Kiểm tra context có đúng instance/scope mong muốn.

### Bước 5 — Inject qua constructor

Sửa orchestrator để nhận dependency từ Spring, gọi collaborator reference, không tạo mới bằng `new`; tránh ngược chiều phụ thuộc sinh cycle.

### Bước 6 — Cập nhật pointcut và cấu hình AOP

Đổi pointcut nhắm method/type/bean/annotation đúng vị trí mới; aspect phải là Spring bean và Spring AOP support đã bật trong context thích hợp.

### Bước 7 — Chạy test hành vi và advice

Tái hiện trước–sau, dùng `AopUtils` và recorder. Chứng minh advice chạy qua collaborator, không chạy thừa ở phương thức không liên quan; kiểm tra transaction/security/cache/async nếu đang sử dụng.

### Bước 8 — Rà soát hiệu năng và release

Refactor có thể thêm một proxy hop nhưng thường không đáng kể so với IO; tuy vậy hãy đo nếu hot path rất nhạy. Quan trọng hơn, **interception trước đây bị bỏ qua nay thực sự chạy**, nên chi phí logging, transaction, cache/remote calls hoặc retry có thể thay đổi. Triển khai với regression tests và observability để phát hiện các side effect mới.

## 13. Checklist cuối cùng

- [ ] Đã chứng minh tình trạng cũ là **self-invocation** (`this.method()` trên target), không phải thiếu aspect bean/pointcut/enable config?
- [ ] Method cần advice đã chuyển sang một **collaborator Spring bean** với trách nhiệm rõ ràng?
- [ ] Collaborator do Spring tạo (`@Component`/`@Service` + scan hoặc `@Bean`); orchestrator không dùng `new`?
- [ ] Reference collaborator được **inject qua constructor**, không self-injection hay `ApplicationContext.getBean(self)`?
- [ ] Method entry public/non-final hoặc có interface tương thích; kiểu proxy JDK/CGLIB thích hợp?
- [ ] Aspect là Spring bean; `@EnableAspectJAutoProxy`/Boot auto-config được bật đúng context?
- [ ] Pointcut khớp type/method/bean mới; không chặn ngoài phạm vi?
- [ ] Integration test cho thấy advice chạy **một lần đúng chỗ** trên đường gọi refactored?
- [ ] Business output/exception tương thích trước–sau; không thay đổi transaction/cache/security semantics ngoài kế hoạch?
- [ ] Không đưa mutable request state vào collaborator/aspect singleton và không phát sinh circular dependency?
- [ ] Nếu luồng xảy ra trong startup, proxy đã hoàn tất, không dựa vào lời gọi từ constructor hoặc `@PostConstruct` của chính target?
- [ ] Đã kiểm tra mọi entry cũ để không còn đường vòng bypass policy?

**Ghi nhớ:** Cách sửa tự nhiên nhất cho self-invocation trong **Spring AOP proxy** thường là **tách phần công việc cần advice thành một Spring bean cộng tác rồi gọi qua dependency được Spring inject**. Tạo class riêng là chưa đủ; phải tạo được **proxy boundary thực**. Refactor nên bảo toàn contract nghiệp vụ, cập nhật pointcut và kiểm thử các side effects mới khi advice bắt đầu hoạt động.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Proxying Mechanisms, self-invocation và hướng refactor](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — Annotation-based Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
