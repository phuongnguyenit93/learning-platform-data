# Đăng ký aspect bằng @Component hoặc phương thức @Bean trong Spring

## 1. Vấn đề cần giải quyết

Trong Spring AOP với kiểu khai báo `@AspectJ`, một class có `@Aspect` **chưa tự động trở thành Spring bean**. Để Spring đọc các advice và dùng chúng khi tạo proxy cho bean đích, ta phải **đăng ký instance của class aspect vào đúng Spring `ApplicationContext`**. Hai cách Java configuration thường dùng là:

1. **`@Aspect` + `@Component`**, cho phép `@ComponentScan` tìm và đăng ký aspect theo convention.
2. **`@Aspect` + phương thức `@Bean`**, cho phép cấu hình Spring chủ động tạo, đặt tên và cung cấp dependency cho aspect.

Cả hai đều phục vụ **cùng một hạ tầng Spring AOP**. Chọn một cách phù hợp với cách quản lý bean của ứng dụng; chỉ cần một instance aspect được đăng ký cho một cấu hình mẫu, tránh tạo hai instance có cùng advice rồi khiến advice chạy lặp.

Ranh giới bài: tập trung vào **đăng ký bean aspect trong Spring**, tương tác với component scan, cấu hình và dependency injection, kiểm chứng proxy/advice. Không lặp lại AOP tổng quát hoặc chuyển sang cơ chế weaving của AspectJ.

## 2. Phân biệt ba vai trò dễ nhầm

| Thành phần | Chức năng chính trong Spring | Có đủ để advice chạy không? |
| --- | --- | --- |
| `@Aspect` trên class | Khai báo class chứa pointcut/advice theo kiểu `@AspectJ`. | **Không**. Không phải stereotype mà component scan mặc định xem là ứng viên bean. |
| `@Component` trên class aspect | Đánh dấu class là một ứng viên Spring component để scan và tạo bean. | **Chưa đủ** nếu không có `@Aspect`, hạ tầng auto-proxy hoặc pointcut/lời gọi phù hợp. |
| `@Bean` trên method của `@Configuration` | Đăng ký object do factory method trả về làm Spring bean, không cần class của object có `@Component`. | **Chưa đủ** nếu object không thuộc class `@Aspect` hoặc chưa bật @AspectJ support. |
| `@EnableAspectJAutoProxy` | Trong Spring Framework Java config, kích hoạt nhận diện advisor của aspect bean và tạo proxy cho target khi match. | Cần cấu hình đúng context, AspectJ Weaver trên classpath và target/lời gọi phù hợp. |
| `@Service`, `@Repository`, `@Controller` trên target | Đưa nghiệp vụ/adapter vào container qua component scan tương ứng. | Target phải được Spring quản lý và lời gọi cần đi qua proxy để được intercept. |

**Hai chiều kiểm tra tách biệt:**

- **Đã có aspect bean chưa?** `context.getBeansOfType(AuditAspect.class)` hoặc danh sách bean names chứng minh container đã biết aspect.
- **Hạ tầng Spring AOP có sử dụng aspect đó chưa?** Một target có thể được proxy và lời gọi method khớp advice chạy. Cần quan sát hành vi, không suy từ việc tạo bean một cách đơn độc.

Ngay cả khi aspect là Spring bean, method trên target vẫn có thể không được advice vì không match pointcut, do lời gọi nội bộ, do target không phải Spring bean hoặc do cấu hình AOP chưa bật.

## 3. Cách 1: `@Aspect` kết hợp `@Component`

Dùng khi aspect là một lớp do ứng dụng sở hữu, phù hợp cơ chế component scanning vốn đã dùng để đăng ký `@Service` và các Spring components khác.

```java
package com.example.aspectdemo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        System.out.println("audit:place");
    }
}
```

Điều kiện quan trọng:

1. `@Aspect` làm Spring nhận diện metadata pointcut/advice trên class.
2. `@Component` cho phép **component scan mặc định** đăng ký class đó như một bean.
3. Cần bật `@ComponentScan` cho đúng package hoặc, với Spring Boot, đặt class dưới package được `@SpringBootApplication` quét.
4. `@EnableAspectJAutoProxy` trong Spring Framework thuần (hoặc auto-configuration tương ứng trong Boot) giúp chuyển metadata từ aspect bean thành advisor của Spring AOP.
5. Target phải là Spring bean, điểm cắt đúng và caller phải đi qua Spring proxy.

### Phạm vi quét là điều kiện thực tế

Ví dụ:

```java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan(basePackages = "com.example.aspectdemo")
class AppConfig {
}
```

Giả sử `AuditAspect` thuộc `com.example.aspectdemo`, config trên cho phép tìm aspect. Nếu chỉ quét `com.example.api`, aspect ở `com.example.aspectdemo` không tự xuất hiện. Khi chạy Spring Boot, package chứa class `@SpringBootApplication` quyết định vùng scan mặc định; aspect nằm ngoài phạm vi đó cần khai báo scan/import rõ ràng.

**Lưu ý:** `@Aspect` **không** là meta-annotation của `@Component`; một class chỉ có `@Aspect` không được component scan đăng ký theo mặc định. Có thể định nghĩa stereotype tùy biến dựa trên `@Component`, nhưng không cần làm thế cho ví dụ thông thường.

### Dependency injection khi dùng `@Component`

Aspect là Spring bean nên có thể nhận dependency bằng **constructor injection** giống các component khác:

```java
@Aspect
@Component
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        sink.record("place");
    }
}
```

Ở đây `AuditSink` cũng phải được Spring đăng ký. Spring giải constructor khi tạo bean aspect. Không cần tạo aspect bằng `new` trong code nghiệp vụ. Constructor injection giúp dependency rõ ràng, dễ test và tránh field injection mơ hồ.

## 4. Cách 2: khai báo aspect bằng phương thức `@Bean`

Dùng khi muốn **quản lý việc tạo aspect một cách tường minh**: cần constructor phức tạp, dependency cấu hình, chọn aspect theo profile/condition, hoặc class aspect không muốn/không thể gắn `@Component`.

```java
package com.example.aspectdemo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        sink.record("place");
    }
}
```

Class trên **cố ý không gắn `@Component`**. Trong Java configuration:

```java
package com.example.aspectdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public AuditAspect auditAspect(AuditSink sink) {
        return new AuditAspect(sink);
    }
}
```

Đây là đoạn **cấu hình minh họa**, giả sử `AuditSink` và target service đã được đăng ký ở chính context này. Spring sẽ inject `AuditSink` vào **tham số factory method** khi gọi `auditAspect(...)`. Object trả về trở thành Spring bean có tên mặc định là `auditAspect`; Spring đọc `@Aspect` trên class của object để phát hiện các advisor.

Chú ý: phương thức `@Bean` phải được Spring xử lý trong context, ví dụ nằm trong một `@Configuration` đã được đăng ký. Việc gọi `new AuditAspect(sink)` **bên trong factory method `@Bean`** là hợp lệ vì **giá trị trả về được container đăng ký**. Ngược lại, tự chạy `new AuditAspect(sink)` ngoài container rồi không đăng ký bean sẽ không khiến Spring AOP tự nhận diện aspect đó.

### Dependency của `@Bean` cũng phải là Spring bean

Hai lựa chọn hợp lệ:

- Component scan tạo `AuditSink` và `OrderService`, còn `@Bean` chỉ tạo `AuditAspect`.
- Không dùng component scan; khai báo cả sink, service và aspect bằng các `@Bean` method riêng.

Ví dụ cách thứ hai, trong một `@Configuration`:

```java
@Bean
AuditSink auditSink() {
    return new AuditSink();
}

@Bean
OrderService orderService() {
    return new OrderService();
}

@Bean
AuditAspect auditAspect(AuditSink sink) {
    return new AuditAspect(sink);
}
```

Khi Spring tạo `AuditAspect`, nó lấy `AuditSink` bean để truyền vào tham số. Với `@Configuration` đầy đủ, các factory method có thể được container quản lý về scope và dependency như bean definitions khác; ưu tiên method-parameter injection để mối phụ thuộc minh bạch.

### Scope, bean name, lifecycle

Cả `@Component` và `@Bean` mặc định tạo **singleton theo bean definition** của Spring. Tên bean mặc định thường là tên class với chữ đầu thường cho component (`auditAspect`), và tên phương thức cho `@Bean` (`auditAspect`). Có thể chỉ định tên rõ:

```java
@Component("businessAuditAspect")
@Aspect
class AuditAspect {
    // ...
}
```

hoặc:

```java
@Bean("businessAuditAspect")
AuditAspect auditAspect(AuditSink sink) {
    return new AuditAspect(sink);
}
```

Hai ví dụ là **các phương án độc lập**; không áp dụng đồng thời để tạo hai bean có tên giống nhau. Tên bean tác động đến việc tra cứu và một số lựa chọn pointcut theo bean name, nhưng không làm `@Aspect` được chấp nhận nếu chưa được container tạo. Nếu aspect giữ trạng thái mutable, singleton có thể gây race condition trong ứng dụng đa luồng; trong đa số trường hợp aspect nên **stateless** và delegate lưu trữ/audit sang service riêng. Đừng đổi scope sang prototype tùy tiện: Spring AOP có cách xử lý aspect instantiation đặc thù, cần kiểm tra rõ behavior.

## 5. Demo đầy đủ, có thể chạy: đăng ký bằng `@Component` rồi đổi sang `@Bean`

Ví dụ dùng **Spring Framework 6.2.15**, **AspectJ Weaver 1.9.24**, Gradle và **Java 17+**. Không dùng Spring Boot để thấy rõ vai trò của `@EnableAspectJAutoProxy`, `@ComponentScan` và `@Bean`.

Mục tiêu test: với đúng **một** aspect bean, một method target được chặn và method khác không được chặn. Hai cách đăng ký cho **cùng một kết quả** khi các bean khác và pointcut giữ nguyên.

### 5.1. Cây thư mục

```text
aspect-registration-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/aspectdemo/
    ├── Application.java
    ├── AppConfig.java
    ├── OrderService.java
    ├── AuditSink.java
    └── AuditAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'aspect-registration-demo'
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
    implementation 'org.springframework:spring-context:6.2.15'
    implementation 'org.springframework:spring-aop:6.2.15'
    implementation 'org.aspectj:aspectjweaver:1.9.24'
}

application {
    mainClass = 'com.example.aspectdemo.Application'
}
```

Spring Framework 6.x yêu cầu Java 17 trở lên. Những dependency được khóa để ví dụ độc lập và dễ tái lập; dự án Spring Boot thực tế nên dựa trên dependency management/BOM của Boot để chọn phiên bản tương thích.

### 5.2. Target service

**`OrderService.java`**

```java
package com.example.aspectdemo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String place(String orderId) {
        return "placed:" + orderId;
    }

    public String status() {
        return "status:ok";
    }
}
```

Service là Spring bean do component scan tạo. Method `place` khớp pointcut; method `status` không khớp. Hai method đều public để dễ chứng minh interception qua class proxy.

### 5.3. Dependency của aspect

**`AuditSink.java`**

```java
package com.example.aspectdemo;

import org.springframework.stereotype.Component;

@Component
public class AuditSink {
    public void record(String operation) {
        System.out.println("audit:" + operation);
    }
}
```

Tách sink ra khỏi aspect cho thấy một Spring-managed aspect cũng có dependency như bean bình thường.

### 5.4. Aspect đăng ký qua `@Component`

**`AuditAspect.java`**

```java
package com.example.aspectdemo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        sink.record("place");
    }
}
```

Spring quét được class này nhờ `@Component`. Spring AOP phân tích advice nhờ `@Aspect`. Không cần tạo `AuditAspect` bằng một factory method khác.

**`AppConfig.java`**

```java
package com.example.aspectdemo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = OrderService.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
}
```

`basePackageClasses = OrderService.class` làm Spring quét **package chứa `OrderService`**, cũng là package của `AuditSink` và `AuditAspect` trong demo. `@EnableAspectJAutoProxy` bật xử lý aspect bean thành các Spring AOP advisors; `proxyTargetClass=true` cho phép tra `OrderService` qua kiểu concrete class. Trong demo đơn giản này, lựa chọn subclass proxy giữ kết quả dễ dự đoán.

### 5.5. Bootstrap, kiểm tra số aspect và hiệu lực proxy

**`Application.java`**

```java
package com.example.aspectdemo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Application {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);

            System.out.println(
                "aspectBeans=" + context.getBeansOfType(AuditAspect.class).size()
            );
            System.out.println(
                "serviceProxied=" + AopUtils.isAopProxy(service)
            );
            System.out.println(service.place("INV-1"));
            System.out.println(service.status());
        }
    }
}
```

Chạy tại thư mục project sau khi có Gradle và JDK 17+:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows). Những dòng do ứng dụng in ra **theo thứ tự chính xác** là:

```text
aspectBeans=1
serviceProxied=true
audit:place
placed:INV-1
status:ok
```

Giải thích:

- `aspectBeans=1`: context nhận diện **một** bean `AuditAspect` từ component scan.
- `serviceProxied=true`: target `OrderService` khớp advisor của aspect nên được Spring trả về dưới dạng AOP proxy.
- `audit:place` xuất hiện **trước** `placed:INV-1` vì advice `@Before` chạy khi gọi `place` qua proxy.
- `status:ok` không có thêm dòng `audit` vì pointcut chỉ match `place(..)`.
- `System.out` của demo không bao gồm log framework hay Gradle phát sinh riêng bởi môi trường.

**Điểm chứng minh:** Aspect chạy vì **đã được đăng ký thành Spring bean**, hạ tầng AOP được bật và caller gọi một target method phù hợp **qua Spring proxy**.

### 5.6. Chuyển cùng demo sang cách `@Bean`

Giữ nguyên `Application.java`, `OrderService.java`, `AuditSink.java`, `build.gradle` và `settings.gradle`. Thay **toàn bộ** hai tệp sau; đây là **biến thể thay thế**, không chạy đồng thời với biến thể `@Component`.

**`AuditAspect.java` — bỏ `@Component`, vẫn giữ `@Aspect`:**

```java
package com.example.aspectdemo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        sink.record("place");
    }
}
```

**`AppConfig.java` — thêm một factory method `@Bean`:**

```java
package com.example.aspectdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = OrderService.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public AuditAspect auditAspect(AuditSink sink) {
        return new AuditAspect(sink);
    }
}
```

`@ComponentScan` vẫn tạo `OrderService` và `AuditSink`; **không tạo `AuditAspect` qua scan** vì class aspect không có `@Component`. Ngược lại, `@Bean auditAspect(...)` tạo chính xác một aspect bean, được container quản lý và inject `AuditSink`. Câu lệnh `new AuditAspect(sink)` ở trong bean factory method hoàn toàn đúng.

Chạy lại:

```bash
gradle run --quiet
```

**Stdout do chương trình in không thay đổi**:

```text
aspectBeans=1
serviceProxied=true
audit:place
placed:INV-1
status:ok
```

Như vậy, hai phương án chỉ khác **cơ chế đăng ký aspect bean**. Điểm cắt, advice, dependency, loại proxy và lời gọi nghiệp vụ vẫn giữ nguyên nên hiệu ứng quan sát giống nhau.

## 6. So sánh và chọn cách đăng ký

| Tiêu chí | `@Aspect` + `@Component` | `@Aspect` + `@Bean` |
| --- | --- | --- |
| Ai khởi tạo bean? | Spring container tạo từ class được component scan phát hiện. | Spring container dùng giá trị trả về của factory method. |
| Cần class aspect có `@Component`? | **Có**, hoặc custom stereotype meta-annotated `@Component`. | **Không**; chỉ cần aspect class được đánh dấu `@Aspect`. |
| Điều kiện tìm thấy aspect | Scan phải bao phủ package và không loại trừ class. | `@Configuration`/`@Bean` phải được context nạp. |
| Constructor injection | Spring tự resolve constructor parameters. | Spring resolve parameters của factory method; method có thể truyền các dependency vào constructor. |
| Kiểm soát cách tạo instance | Thường dựa vào constructor và component model. | Tường minh tại factory method, dễ chọn factory/dependency dựa trên cấu hình. |
| Bean name mặc định | Thường là tên class với chữ cái đầu hạ thấp. | Theo tên factory method. |
| Điều kiện/feature flag | Có thể dùng `@Profile`, `@Conditional` trên component khi phù hợp. | Có thể đặt `@Profile`/`@Conditional` trên `@Bean` hoặc config, dễ theo dõi khi tạo bean. |
| Nhúng aspect từ module/library khác | Cần package được scan hoặc import. | Phù hợp khi người dùng library chủ động đăng ký một class `@Aspect` bằng `@Bean`. |
| Thường dùng khi | Aspect là mã ứng dụng và dự án có convention scanning nhất quán. | Muốn wiring rõ ràng, có nhiều cấu hình hoặc muốn tránh phụ thuộc vào package scan. |

**Chọn `@Component`** nếu aspect là một component bình thường của module, nằm trong vùng scan có kiểm soát và dependency injection đơn giản.

**Chọn `@Bean`** nếu muốn Spring configuration nêu rõ “aspect nào được kích hoạt”, muốn cấu hình constructor theo từng môi trường, hoặc đang tích hợp một aspect class không nên gắn Spring stereotype.

Hai cách **không khác nhau về mức độ chặn của Spring AOP**: sau khi đã đăng ký đúng cách, Spring proxy vẫn có các giới hạn như self-invocation, method `private`/`final`, proxy interfaces/class, pointcut và thời điểm target được gọi. Không nên dùng việc đổi từ `@Component` sang `@Bean` để cố sửa một lỗi tự gọi nội bộ.

## 7. Những trường hợp gây đăng ký trùng hoặc mất aspect

### 7.1. Gắn `@Component` và đồng thời viết `@Bean`

Ví dụ **không nên làm** trong cùng context đã scan package:

```java
@Aspect
@Component
class AuditAspect {
    // advice...
}

@Configuration
@ComponentScan("com.example.aspectdemo")
class AppConfig {
    @Bean
    AuditAspect customAuditAspect() {
        return new AuditAspect();
    }
}
```

Đây là **mã minh họa sai cách đăng ký**, không phải project runnable từ demo vì class có constructor khác. Nếu factory method tạo bean tên `customAuditAspect`, đồng thời component scan tạo `auditAspect`, context có **hai bean** có cùng loại aspect. Nếu cả hai cùng có advice match target, có thể khiến side effect chạy hai lần. Nếu chọn cùng một tên, kết quả lại phụ thuộc chính sách bean-definition overriding/collision và có thể làm startup lỗi. Không trông cậy vào tên trùng để loại bỏ một bean. Hãy chọn đúng một nguồn đăng ký và kiểm tra số instance.

### 7.2. Chỉ gắn `@Aspect`

```java
@Aspect
public class AuditAspect {
    // advice...
}
```

Class này không tự động xuất hiện khi component scan mặc định chạy. Cần thêm stereotype `@Component` **hoặc** khai báo `@Bean`. Điều này có thể gây tình huống application startup bình thường nhưng không có advice.

### 7.3. Aspect nằm ngoài vùng scan

`@ComponentScan("com.example.web")` không tự quét `com.example.audit`. Cân nhắc:

- Điều chỉnh package được scan để bao gồm aspect mà không quét bừa vùng ngoài dự kiến.
- Đăng ký aspect bằng `@Import` cấu hình hoặc `@Bean`.
- Trong Spring Boot, kiểm tra package gốc của `@SpringBootApplication` và vùng scan mặc định trước khi sửa.

### 7.4. `@Bean` nằm trong config không được import

Viết factory method trên một class cấu hình nhưng không đưa class đó vào ApplicationContext cũng không tạo ra aspect bean. Kiểm tra nơi khai báo `@SpringBootApplication`, `@Import` hoặc các lớp cấu hình đã đăng ký qua `AnnotationConfigApplicationContext`.

### 7.5. Gọi method qua `this` hoặc object ngoài container

Ngay cả khi `AuditAspect` được đăng ký đúng:

```java
@Service
class OrderService {
    public String batch() {
        return place("INV-2");  // self-invocation: bỏ qua proxy của place()
    }

    public String place(String id) {
        return "placed:" + id;
    }
}
```

Đây là **đoạn minh họa**, không thay các file demo trước đó. Điểm cắt vào `place(..)` sẽ không chạy cho lời gọi từ `batch()` trên target. Tương tự, `new OrderService().place("INV-2")` không được tự động chặn. Nếu cần advice, hãy gọi qua Spring bean/proxy (thường qua một bean khác), không thêm thêm bean aspect để hy vọng sửa self-invocation.

### 7.6. Nhiều context

`@ComponentScan` và `@Bean` đăng ký bean trong ApplicationContext mà chúng chạy. Auto-proxy creator của `@EnableAspectJAutoProxy` cũng có phạm vi context cục bộ. Với ứng dụng có root/child contexts, cần kiểm tra aspect, target bean và hạ tầng AOP có cùng context phù hợp. Aspect tạo ở một context không có nghĩa tự áp dụng cho mọi target bean ở context khác.

### 7.7. Quá nhiều state trong aspect singleton

Aspect bean mặc định singleton giống các Spring bean thường. Không lưu `currentUser`, `currentOrderId` hay dữ liệu request mutable trực tiếp trong field của aspect singleton, vì nhiều request có thể cùng gọi advice. Nếu cần ngữ cảnh request, dùng API request/security/observation tương ứng; nếu cần ghi audit, giao cho một service/sink an toàn.

## 8. Spring Boot và tự động đăng ký aspect

Ở Spring Boot có AOP auto-configuration và dependency tương ứng, bạn thường không cần viết `@EnableAspectJAutoProxy` thủ công; nhưng **vẫn phải tạo aspect bean** bằng `@Component` (được scan) hoặc `@Bean` (trong config được nạp).

Ví dụ Boot:

```java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Nếu `AuditAspect` có cả `@Aspect` và `@Component`, nằm trong phạm vi component scan, Boot AOP có thể nhận diện nó khi dependency/hạ tầng phù hợp. Với phương án `@Bean`, một `@Configuration` được Boot nạp sẽ trả về `AuditAspect` và hạ tầng xử lý tương tự.

**Dependency tùy major version:**

```gradle
// Spring Boot 3.x, với dependency management của Boot
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

```gradle
// Spring Boot 4.x, với dependency management của Boot
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

Hai khối là **lựa chọn theo phiên bản**, không dùng đồng thời. Tên dependency không thay thế yêu cầu **đăng ký một aspect bean**. Spring Boot có thể mặc định dùng class proxy; kiểm tra `spring.aop.auto` và `spring.aop.proxy-target-class` khi chẩn đoán, đồng thời nhớ rằng các cấu hình proxy khác có thể ảnh hưởng kết quả. Aspect vẫn là bean Spring, không phải bytecode weaving chỉ vì module có `aspectjweaver`.

## 9. Cách QA: phân biệt “bean tồn tại” và “advice thực thi”

Khi cần xác minh, kiểm tra theo thứ tự sau:

### Bước 1 — aspect đã được đăng ký đúng một lần chưa?

```java
String[] aspectBeanNames = context.getBeanNamesForType(AuditAspect.class);
System.out.println(java.util.Arrays.toString(aspectBeanNames));
```

Trong demo, tên mặc định của cả hai cách đăng ký là `auditAspect` nên dòng minh họa là:

```text
[auditAspect]
```

Nếu không có tên: quên `@Component`, scan sai package hoặc `@Bean` config chưa được nạp. Nếu có hai tên: có nguy cơ đăng ký trùng.

### Bước 2 — target có được Spring proxy không?

```java
OrderService service = context.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(service));
```

Trong demo kết quả là:

```text
true
```

Nếu false, xem lại cấu hình AOP, AspectJ Weaver classpath, pointcut và việc lấy target qua container. Proxy true chỉ nói có **ít nhất một** advisor áp dụng lên bean, chưa đủ chứng minh method cụ thể sẽ chạy advice.

### Bước 3 — method khớp pointcut có side effect không?

Gọi `service.place("INV-1")` qua reference lấy từ Spring container; xác nhận `audit:place` in ra đúng một lần trước kết quả, và `status()` không kích hoạt audit. Nếu dùng cả hai phương án đồng thời, số lần advice có thể khác; đó là lỗi đăng ký, không phải vấn đề Java method.

### Bước 4 — kiểm tra wiring như một integration test

Viết test tạo context thật và assert:

- Có đúng một bean `AuditAspect`.
- `OrderService` là AOP proxy.
- Gọi method có pointcut phát sinh đúng một audit event.
- Method ngoài pointcut không ghi audit.
- Khi đổi từ component scan sang `@Bean`, các xác nhận vẫn như nhau.
- Nếu có exception/transaction, kiểm tra thời điểm advice chạy và lỗi không bị nuốt.

Test chỉ dùng `new AuditAspect(...)` hay `new OrderService()` không thay cho integration test Spring proxy. Để test gọn, `AuditSink` nên có mock/test implementation thay cho in console.

## 10. Câu hỏi chẩn đoán nhanh

| Hiện tượng | Nguyên nhân Spring có khả năng | Cách xác minh |
| --- | --- | --- |
| Không có bean `AuditAspect` | Chỉ dùng `@Aspect`, thiếu `@Component` hoặc cấu hình `@Bean` chưa nạp. | `getBeanNamesForType(AuditAspect.class)`; kiểm tra scan/import. |
| Có aspect bean, advice không chạy | Thiếu AOP enable/auto-config, thiếu AspectJ Weaver, pointcut không match, self-invocation hoặc target không là bean. | `AopUtils.isAopProxy`, gọi ngoài qua proxy và quan sát advice. |
| Advice chạy hai lần | Đăng ký trùng bean aspect hoặc có advisor khác cùng áp dụng. | Liệt kê các bean names và advisor chain. |
| Spring báo `NoUniqueBeanDefinitionException` khi inject `AuditAspect` | Có nhiều beans cùng kiểu, thường từ scan cộng thêm `@Bean`. | Xem `getBeanNamesForType` và bỏ nguồn đăng ký thừa; `@Qualifier` chỉ giải quyết việc chọn bean khi thật sự cần nhiều instance. |
| Có `@Bean` nhưng thiếu `AuditSink` | Factory method có dependency chưa được tạo trong context. | Kiểm tra `@ComponentScan`/`@Bean` tạo sink, lỗi startup. |
| Đổi sang `@Bean` nhưng bean name/ordering khác | Method name hoặc `@Bean("...")` thay đổi; có nhiều aspect và `@Order`. | Kiểm tra tên bean, thứ tự advisor và pointcut. |
| Khi inject target theo concrete type bị lỗi | JDK interface proxy không gán được vào implementation type. | Inject bằng interface hoặc cấu hình class-based proxy phù hợp. |
| Advice không chạy từ call nội bộ | Lời gọi đi trên `this` của target. | Thử gọi method qua injected Spring bean từ class khác. |

## 11. Checklist trước khi hoàn tất

- [ ] Aspect class có `@Aspect`, chọn **một** nguồn đăng ký: `@Component` **hoặc** `@Bean`.
- [ ] Nếu chọn `@Component`: đúng package scan, không bị filter loại trừ.
- [ ] Nếu chọn `@Bean`: config có trong context; constructor/factory method inject dependency từ Spring.
- [ ] Có đúng số lượng aspect instance chủ đích (thường là một), tránh side effect advice trùng.
- [ ] Spring AOP `@AspectJ` support đã bật: `@EnableAspectJAutoProxy` với Framework thuần hoặc Boot AOP auto-configuration phù hợp.
- [ ] Có AspectJ Weaver trên classpath và phiên bản Spring tương thích.
- [ ] Target bean lấy từ container, pointcut match method, lời gọi ngoài đi qua proxy.
- [ ] Kiểu proxy, khả năng intercept method, bean scope và thứ tự advisor đáp ứng yêu cầu.
- [ ] Aspect không giữ mutable request state thiếu an toàn; dependency/sink dùng qua DI.
- [ ] Integration test xác nhận bean count **và** advice chạy đúng một lần, không chỉ kiểm tra class có annotation.

**Điểm nhớ:** Trong Spring AOP, `@Aspect` xác định **aspect là gì**, còn `@Component` hoặc `@Bean` quyết định **Spring quản lý instance aspect bằng cách nào**. Sau khi đã là Spring bean, hạ tầng `@AspectJ` của Spring mới dùng advice đó để tạo proxy cho những target bean phù hợp. Hai cách đăng ký là hai lựa chọn wiring, không thay đổi bản chất interception qua Spring proxy.

## Tài liệu chính thức

- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework — Component Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
