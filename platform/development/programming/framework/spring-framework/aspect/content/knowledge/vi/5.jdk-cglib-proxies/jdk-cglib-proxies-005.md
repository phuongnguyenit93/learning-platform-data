# Giới hạn lớp final và phương thức final khi dùng CGLIB trong Spring AOP

## 1. Vấn đề cần nhận diện

Trong Spring AOP, một target bean có thể được Spring tạo **JDK dynamic proxy** qua interface, hoặc **class-based proxy** bằng CGLIB. Khi cấu hình Spring dùng class-based proxy, Spring phải tạo một **subclass** của class đích để intercept các phương thức có thể override.

Hai giới hạn quan trọng xuất phát trực tiếp từ cách Spring sử dụng CGLIB:

- **`final class`:** không thể tạo subclass, nên **không thể tạo CGLIB AOP proxy** cho class ấy. Khi bean thực sự cần áp advisor và Spring buộc class proxy, quá trình tạo proxy/khởi tạo context có thể thất bại.
- **`final method` trong class không final:** Spring vẫn có thể tạo CGLIB proxy cho class, **nhưng không thể intercept/advice chính method final** vì subclass không override được. Các method khác không final vẫn có thể được advice.

Bài tập trung vào **hành vi Spring AOP**, điều kiện phát sinh lỗi, cách cấu hình và kiểm chứng proxy. Những khái niệm Java `final` cơ bản chỉ được nhắc ở mức cần thiết để hiểu ràng buộc của proxy Spring.

Điểm cần nhớ ngay: **“Bean được proxy” khác “mọi method trên bean đều được advise”.** Nếu chỉ kiểm tra `AopUtils.isAopProxy(bean) == true`, bạn chưa chứng minh `finalMethod()` có advisor chạy.

## 2. Spring tạo JDK proxy và CGLIB proxy trong trường hợp nào?

| Điều kiện trong Spring | Kiểu proxy có thể chọn | Hệ quả với `final` |
| --- | --- | --- |
| Target implement một business interface, `proxyTargetClass=false`, cấu hình không ép class proxy | Thường **JDK dynamic proxy**, object proxy implement interface | Target class có thể là `final`; Java class target không cần bị subclass. Method public `final` của target có thể được advice **qua phương thức interface được proxy**, nếu advisor match. |
| Target không có interface phù hợp | **CGLIB/class-based proxy** được sử dụng khi cần proxy | Class không thể `final`; `final` method không thể được advice qua subclass. |
| `@EnableAspectJAutoProxy(proxyTargetClass=true)` hoặc cấu hình ép class proxy | **CGLIB** dù target có interface | `final class` không được subclass; `final method` bỏ qua interception. |
| Spring Boot dùng class proxy theo cấu hình mặc định | Thường class-based, tùy `spring.aop.proxy-target-class` và các cấu hình liên quan | Một target `final` có thể gặp giới hạn CGLIB dù đã khai báo interface. |
| Đổi sang JDK proxy mà caller chỉ biết concrete implementation | Caller không thể inject/cast JDK proxy thành implementation class | Cần inject bằng interface; JDK proxy chỉ expose các phương thức thuộc interface được proxy. |

Trong **Spring Framework** cấu hình `@EnableAspectJAutoProxy`, tham số `proxyTargetClass` mặc định là `false`; với target có business interface, Spring thường ưu tiên JDK proxy. Với **Spring Boot** có AOP auto-configuration, thuộc tính `spring.aop.proxy-target-class` thường mặc định `true`, nên cần kiểm tra môi trường cụ thể.

### Sơ đồ đường đi lời gọi

```text
CGLIB cho class không final:

Client
  |
  v
ClassService$$SpringCGLIB$$...
  ├─ open()         -> method override được -> advice -> target.open()
  └─ final locked() -> không override được -> không đi qua advice

CGLIB cho final class:

final class FinalService
  |
  └─ Spring không thể tạo subclass => class-based proxy không khả thi

JDK interface proxy cho final target class:

Client (giữ interface ServicePort)
  |
  v
jdk.proxy...$Proxy
  |
  +-- ServicePort.call() -> advice -> final target implementation.call()
```

Sơ đồ CGLIB là mô hình khái niệm của interception; cơ chế proxy chi tiết do Spring quản lý. Đừng dựa vào tên class proxy sinh tự động, vì tên có thể thay đổi theo phiên bản runtime.

## 3. Vì sao `final class` và `final method` gây hai hiện tượng khác nhau?

### 3.1. Toàn bộ class `final`: thường lỗi khi bắt buộc tạo CGLIB proxy

Giả sử trong Spring:

```java
public final class FinalInvoiceService {
    public String issue(String id) {
        return "issued:" + id;
    }
}
```

Một advisor muốn chặn `issue(..)`, nhưng `@EnableAspectJAutoProxy(proxyTargetClass=true)` ép Spring tạo class proxy. Vì class là `final`, CGLIB không thể tạo subclass. Khi Spring **thực sự phải áp AOP proxy** cho bean này, ứng dụng có thể báo lỗi dạng `AopConfigException` / `BeanCreationException`, nguyên nhân sâu thường nói không thể subclass `final class`.

**Không khẳng định Spring luôn lỗi chỉ vì có `final` bean.** Nếu bean `final` không được bất kỳ advisor nào nhắm đến và Spring không cần tạo proxy, bean vẫn có thể hoạt động bình thường. Lỗi xuất hiện ở nhu cầu class-proxy thực tế, không phải khi compiler đọc từ khóa `final`.

### 3.2. Class không final, một method `final`: proxy tồn tại nhưng advice bỏ qua method đó

```java
public class InvoiceService {
    public String issue(String id) {
        return "issued:" + id;
    }

    public final String summary(String id) {
        return "summary:" + id;
    }
}
```

Một CGLIB proxy có thể override `issue(..)` để chạy advisor, nhưng **không thể override** `summary(..)`. Bởi vậy, pointcut có thể phù hợp **về tên/chữ ký** mà lời gọi `summary()` vẫn **không kích hoạt Spring AOP advice**.

Đây là lỗi nguy hiểm hơn vì **ứng dụng có thể vẫn khởi động**, nhiều phương thức được advice như mong đợi, riêng `final` method không có side effect của advice.

Cần đặc biệt cẩn trọng khi dùng `@Transactional`, `@Cacheable`, method security hoặc `@Async` theo cơ chế proxy: một final method dưới class proxy có thể không đi qua interceptor mà người viết code tưởng là đã kích hoạt. Không dùng trạng thái “bean là AOP proxy” để suy rằng transaction/security/cache trên final method đã an toàn.

### 3.3. Không chỉ có `final`

Cùng nguyên lý subclass:

- `private` method không thể override nên không thể advice bằng CGLIB.
- Method không nhìn thấy từ subclass, ví dụ package-private ở parent class khác package, cũng có thể không được intercept.
- `this.otherMethod()` bên trong target là **self-invocation**: không quay qua proxy; bỏ qua advice ngay cả khi `otherMethod()` không final.
- Constructor invocation hoặc field read/write không trở thành method join point của Spring AOP proxy.
- Java Platform Module System có thể giới hạn class-proxy đối với package không được mở; đó là ràng buộc riêng, không thể giải quyết bằng việc xóa `final` đơn thuần.

Các vấn đề trên khác nhau về nguyên nhân. Đừng tự động bật `proxyTargetClass=true` hoặc `exposeProxy=true` khi gặp method không có advice.

## 4. Chạy demo CGLIB: advice chạy ở method thường, không chạy ở method final

Đây là một dự án **Spring Framework thuần** với **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**. Ví dụ dùng Java configuration với `@EnableAspectJAutoProxy` nên không phụ thuộc Spring Boot auto-configuration.

### 4.1. Cấu trúc project

```text
spring-final-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/finalproxy/
    ├── App.java
    ├── ClassProxyConfig.java
    ├── CglibService.java
    └── TraceAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-final-proxy-demo'
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
    mainClass = 'com.example.finalproxy.App'
}
```

Trong Spring Framework 6.x, CGLIB đã được Spring repackaged trong `spring-core`; không phải tự thêm một dependency CGLIB riêng. `aspectjweaver` là dependency dùng bởi Spring AOP cho `@AspectJ` pointcut parsing, **không có nghĩa ứng dụng dùng AspectJ load-time weaving**.

### 4.2. Target class không final, có một method final

**`CglibService.java`**

```java
package com.example.finalproxy;

public class CglibService {
    public String open(String id) {
        return "open:" + id;
    }

    public final String locked(String id) {
        return "locked:" + id;
    }
}
```

`open(..)` có thể được subclass override. `locked(..)` không thể override. Để quan sát giới hạn một cách rõ ràng, cả hai method trả về chuỗi đơn giản, không phụ thuộc instance fields.

**Một lưu ý nâng cao:** một final method được gọi trực tiếp trên CGLIB proxy có thể truy cập trạng thái trên **proxy object** thay vì đường dispatch được Spring dùng để gọi target. Do đó, khi class có state, việc gọi final method trên proxy có thể gây hành vi gây ngạc nhiên, thậm chí thấy giá trị field chưa được khởi tạo như mong đợi. Không chỉ là “thiếu log advice”; tránh triển khai bean stateful rồi kỳ vọng final method trên CGLIB proxy hoạt động giống mọi public method khác.

### 4.3. Đăng ký Spring aspect và pointcut

**`TraceAspect.java`**

```java
package com.example.finalproxy;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(public * com.example.finalproxy.CglibService.*(..))")
    public void beforeService(JoinPoint joinPoint) {
        System.out.println("advice:" + joinPoint.getSignature().getName());
    }
}
```

Biểu thức `execution(...)` bao trùm **chữ ký của cả `open(..)` và `locked(..)`**, nhưng advice chỉ thực sự chạy khi invocation được Spring proxy intercept. Đây chính là khác biệt mà ví dụ muốn minh họa.

### 4.4. Bật class-based proxy

**`ClassProxyConfig.java`**

```java
package com.example.finalproxy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassProxyConfig {
    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    CglibService cglibService() {
        return new CglibService();
    }
}
```

`TraceAspect` là Spring bean nhờ `@Bean`, không cần `@Component`. `@EnableAspectJAutoProxy(proxyTargetClass=true)` yêu cầu class proxy cho bean phù hợp. `CglibService` không `final`, nên Spring có thể tạo subclass proxy.

### 4.5. Main, lệnh chạy và stdout

**`App.java`**

```java
package com.example.finalproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(ClassProxyConfig.class)) {
            CglibService service = context.getBean(CglibService.class);

            System.out.println(
                "classProxy=" + AopUtils.isCglibProxy(service)
            );
            System.out.println(service.open("A"));
            System.out.println(service.locked("B"));
        }
    }
}
```

Chạy tại thư mục dự án, với Gradle đã cài:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper: `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows).

**Các dòng do code chương trình in ra theo đúng thứ tự** (không tính thông báo logger/build tool):

```text
classProxy=true
advice:open
open:A
locked:B
```

Giải thích:

1. `classProxy=true`: Spring trả về một CGLIB Spring AOP proxy.
2. `advice:open`: `open(..)` không final, CGLIB override và chuyển qua advice.
3. `open:A`: phương thức target vẫn được gọi và trả kết quả.
4. `locked:B`: `locked(..)` vẫn được gọi nhưng **không có `advice:locked`**, dù pointcut match signature của nó.

Nếu đổi cả class thành `final` nhưng vẫn giữ class proxy và advisor phù hợp, hãy coi đó là **thử nghiệm lỗi startup riêng**, không phải chỉnh sửa cần làm để ví dụ chuẩn chạy được.

## 5. Khi target class final: cân nhắc JDK interface proxy

JDK dynamic proxy khác CGLIB ở một điểm quyết định: Spring tạo **object implement interface** rồi delegate vào target. Nó **không cần subclass** của target. Vì vậy, một target class `final` vẫn có thể làm việc với Spring AOP nếu:

- Target **implement business interface** phù hợp.
- Cấu hình Spring sử dụng interface-based proxy (`proxyTargetClass=false` và không bị phần cấu hình khác ép class-based proxy).
- Caller lấy/inject bean bằng **interface type**.
- Advice match lời gọi method trên proxy interface; nếu một method chỉ có trên implementation nhưng không thuộc interface được proxy thì caller không thể gọi nó qua JDK proxy theo cách thông thường.

### 5.1. Interface và class final

Bổ sung **ba file** vào cùng package `com.example.finalproxy` của dự án trên.

**`Api.java`**

```java
package com.example.finalproxy;

public interface Api {
    String call(String id);
}
```

**`FinalApi.java`**

```java
package com.example.finalproxy;

public final class FinalApi implements Api {
    @Override
    public final String call(String id) {
        return "api:" + id;
    }
}
```

Ở đây **cả class và method implementation đều final**; nhưng JDK proxy implement `Api` và chặn `Api.call(..)` **trước khi delegate** tới target. `final` của target không ngăn interface proxy intercept lời gọi.

**`InterfaceProxyConfig.java`**

```java
package com.example.finalproxy;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class InterfaceProxyConfig {
    @Bean
    Api api() {
        return new FinalApi();
    }

    @Bean
    ApiTraceAspect apiTraceAspect() {
        return new ApiTraceAspect();
    }

    @Aspect
    public static class ApiTraceAspect {
        @Before("execution(* com.example.finalproxy.Api+.call(..))")
        public void beforeCall() {
            System.out.println("advice:api");
        }
    }
}
```

`Api+` trong biểu thức AspectJ chọn interface `Api` và các subtype/implementation phù hợp. `@Bean` đăng ký aspect vào Spring context; `proxyTargetClass=false` bảo đảm ta không chủ động ép class proxy cho target. **Không import cả `ClassProxyConfig` và `InterfaceProxyConfig` vào cùng một context**, vì các thiết lập auto-proxy có thể hợp nhất và thiết lập ép class proxy sẽ thắng.

### 5.2. Main riêng cho JDK proxy

**`InterfaceApp.java`**

```java
package com.example.finalproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class InterfaceApp {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                InterfaceProxyConfig.class)) {
            Api service = context.getBean(Api.class);

            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(service));
            System.out.println(service.call("C"));
        }
    }
}
```

Tạo task Gradle bổ sung trong `build.gradle`:

```gradle
tasks.register('runJdkProxy', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.finalproxy.InterfaceApp'
}
```

Chạy:

```bash
gradle runJdkProxy --quiet
```

**Stdout của demo JDK proxy:**

```text
jdkProxy=true
advice:api
api:C
```

Dù `FinalApi` và `FinalApi.call(..)` đều `final`, advice có thể chạy vì entry call đi qua **JDK interface proxy**, không phải một subclass của `FinalApi`.

Không thử:

```java
FinalApi service = context.getBean(FinalApi.class);
```

trong cấu hình JDK proxy này và mong có target bean gán trực tiếp được theo implementation type. Spring trả về một proxy implement `Api`; kiểu runtime của proxy không phải subclass `FinalApi`. Nếu client cần inject bằng concrete class, phải thay đổi thiết kế/chọn loại proxy phù hợp; target `final` khiến class proxy không khả thi.

**Giới hạn:** JDK proxy chỉ can thiệp tại **method trên interface của proxy**. Một `final` method khác chỉ được khai báo ở implementation class, không nằm trong interface, không được đưa ra trên JDK proxy cho caller sử dụng.

## 6. Thử nghiệm thất bại khi ép CGLIB cho final class

Đây là **đoạn minh họa tình huống thất bại**, không thêm nó vào project chạy chuẩn ở mục 4 hoặc mục 5:

```java
// Ví dụ cố tình sai: final class bị yêu cầu tạo class proxy
public final class FinalBillingService {
    public String bill(String id) {
        return id;
    }
}

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class InvalidConfig {
    @Bean
    FinalBillingService finalBillingService() {
        return new FinalBillingService();
    }

    @Bean
    Object tracingAspect() {
        // Chỉ là placeholder giải thích, KHÔNG dùng làm @Aspect thật.
        return new Object();
    }
}
```

Đoạn trên **chỉ minh họa class final và cấu hình ép proxy; chưa phải test gây lỗi** vì chưa có advisor match `FinalBillingService`. Muốn tái hiện lỗi, cần một **Spring advisor thực sự match bean final**. Ví dụ logic:

```java
@Aspect
class BillingAspect {
    @Before("execution(* FinalBillingService.bill(..))")
    public void beforeBilling() {
        // ...
    }
}
```

Đây cũng là **cú pháp minh họa**, không phải file độc lập: type phải dùng tên fully qualified đúng package và class aspect phải được đăng ký thành Spring bean.

Với advisor thực sự áp dụng, Spring phải proxy bean cuối cùng ấy; CGLIB không thể subclass class `final`. Kết quả phụ thuộc phiên bản và đường cấu hình nên **không khóa một thông báo exception nguyên văn**; kiểm tra chuỗi `BeanCreationException` / `AopConfigException` và root cause liên quan tới class cuối cùng `final`.

**Quan trọng:** Không dùng `@EnableAspectJAutoProxy(proxyTargetClass=false)` để “tự sửa” mọi `final class`. Nếu class không có interface thì Spring vẫn cần class proxy; nếu ứng dụng đồng thời dùng các cấu hình ép class proxy (ví dụ transaction/cache AOP hoặc một context Boot) thì thiết lập thực tế vẫn có thể là CGLIB.

## 7. Cấu hình của Spring Boot và các auto-proxy advisors

Với **Spring Boot** có AOP auto-configuration, property thường gặp:

```properties
# Spring Boot AOP: mặc định thường là true
spring.aop.proxy-target-class=true
```

Đối với target `final` đã triển khai interface, có thể xét:

```properties
spring.aop.proxy-target-class=false
```

để ưu tiên JDK proxy khi hạ tầng và các cấu hình khác cho phép. **Kiểm tra proxy thực tế bằng `AopUtils.isJdkDynamicProxy`/`isCglibProxy`**, vì một Spring context có thể hợp nhất các yêu cầu auto-proxy từ nhiều nơi và lấy cấu hình proxy mạnh hơn.

Dependency chọn theo Spring Boot major version (ví dụ Gradle đã dùng BOM/dependency management của Boot):

```gradle
// Boot 3.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

```gradle
// Boot 4.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

Hai khối là **phương án theo phiên bản**, không áp dụng cùng lúc. CGLIB được Spring tích hợp qua `spring-core`; không cần khai báo riêng dependency `cglib:cglib` cho Spring AOP hiện đại.

Những annotation Spring thường sử dụng proxy/interceptor và chịu rủi ro final method tương tự khi ở chế độ class proxy:

| Spring feature | Nguy cơ với method final trên CGLIB proxy | Kiểm tra đúng |
| --- | --- | --- |
| `@Transactional` | Transaction interceptor không đi qua method final như mong đợi | Quan sát transaction đang hoạt động, kết quả rollback/commit, và đặt annotation trên entry method intercept được. |
| `@Cacheable`/`@CacheEvict` | Cache advice có thể không chạy ở method final | Kiểm tra cache hit/miss/eviction thực tế, không chỉ xem annotation. |
| `@Async` | Invocation final không chuyển vào async interceptor | Kiểm tra thread, loại return và completion thực tế. |
| Method security như `@PreAuthorize` | Security advice có thể bị bỏ qua ở method final | Cần test quyền truy cập qua đúng Spring proxy; trường hợp này đặc biệt nghiêm trọng. |
| Custom `@Aspect` logging/metrics/audit | Mất logging/audit ở method final | Kiểm tra event quan sát khi gọi method qua container. |

Các annotation trên **đều cần phần cấu hình activation riêng** (transaction management, cache, async, method security). `@EnableAspectJAutoProxy` chỉ bật hỗ trợ Spring AOP `@AspectJ`, không thay cho cấu hình của mọi tính năng khác.

Khi cần ràng buộc bảo mật, luôn có kiểm thử từ bên ngoài với quyền không hợp lệ và xác minh method được bảo vệ; một trace log thiếu hoặc đủ không thay thế bài test authorization.

## 8. Cách xử lý khi hệ thống buộc phải có final class

### Lựa chọn A — Giữ final, dùng interface proxy nếu đáp ứng được

Phù hợp khi:

- Public API được diễn tả bởi một interface rõ ràng.
- Caller inject/tra cứu theo interface.
- Những method cần interception nằm trong interface.
- Không có cấu hình khác buộc class-based proxy.
- Việc dùng JDK proxy đã được kiểm thử với tính năng AOP cụ thể của ứng dụng.

Ví dụ một Spring bean `final` implement `PaymentPort`. Client inject `PaymentPort`, và Spring dùng JDK proxy để chặn method trên contract. **Không dựa vào final implementation type để inject**.

### Lựa chọn B — Cho phép subclass, method cần advice không final

Nếu ứng dụng cần class proxy hoặc API chưa có interface, hãy thiết kế target class có thể subclass:

```java
public class PaymentService {
    public Receipt pay(String orderId) {
        // Public method được phép override, phù hợp entry method AOP.
        return new Receipt(orderId);
    }
}
```

Đoạn code minh họa, giả sử `Receipt` là type tự định nghĩa trong project. Để code test/ứng dụng thật hoạt động, cần thêm Spring bean registration và hạ tầng proxy tương ứng.

Bỏ `final` chỉ ở **entry method cần advice**, giữ tính bất biến nghiệp vụ bằng thiết kế dependency và encapsulation thay vì khóa method bị Spring cần override. Không cần bỏ `final` khỏi mọi helper nội bộ nếu chúng không được advisor chặn và không đi qua proxy.

### Lựa chọn C — Explicit decorator/service boundary

Khi class không thể sửa, không có interface, hoặc cần rõ trình tự thay vì interception ngầm:

```java
public final class FixedGateway {
    public String send(String text) {
        return "sent:" + text;
    }
}

public class AuditedGateway {
    private final FixedGateway delegate;

    public AuditedGateway(FixedGateway delegate) {
        this.delegate = delegate;
    }

    public String send(String text) {
        System.out.println("audit:send");
        return delegate.send(text);
    }
}
```

Đây là **đoạn minh họa về cấu trúc**, không phải ví dụ AOP chạy độc lập. Đăng ký `AuditedGateway` thành Spring bean và inject vào callers sẽ có một ranh giới tường minh để logging/audit. Nếu vẫn muốn Spring AOP trên decorator, bản thân lớp decorator và method entry phải proxy được.

### Lựa chọn D — Cần interception ngoài khả năng proxy

Nếu yêu cầu thực sự là chặn constructor, field access hoặc self-invocation trong class không thể sửa, Spring AOP proxy không đủ. Có thể cân nhắc **AspectJ compile-time/load-time weaving** với cấu hình riêng hoặc chuyển yêu cầu thành lời gọi explicit. Đây không phải tính năng được bật chỉ bằng `@EnableAspectJAutoProxy`. Cần đánh giá phức tạp triển khai, khả năng gỡ lỗi và giới hạn bytecode trước khi chọn weaving.

## 9. Lưu ý riêng với Kotlin, record và những kiểu class đặc biệt

- **Kotlin:** class/method mặc định là final nếu không khai báo `open`. Trong ứng dụng Spring dùng class proxy, có thể sử dụng Kotlin `kotlin-spring` compiler plugin (một preset của `all-open`) để mở những class/method mang annotation Spring thích hợp; hoặc thiết kế interface rõ ràng và dùng JDK proxy. Cần kiểm tra kết quả build/bytecode thực tế, đặc biệt với custom annotation không thuộc danh sách plugin xử lý.
- **Java record:** record là final class; không thể subclass để tạo CGLIB AOP proxy. Record thích hợp làm immutable data carrier hơn là business service Spring cần method interception.
- **Java sealed hierarchy:** một subclass proxy sinh động có thể gặp ràng buộc permitted subclasses; đừng suy rằng mọi sealed class đều proxy được. Kiểm tra loại proxy/thực nghiệm trên phiên bản Spring và JVM đang dùng.
- **JDK module path:** CGLIB đôi khi cần truy cập mở tới package; giới hạn module access là nguyên nhân độc lập với `final`.
- **Methods được khai báo final do bytecode tool khác:** Lombok, Kotlin compiler hoặc thư viện sinh bytecode có thể khiến class/method là final dù source code không thể hiện như kỳ vọng. Khi khó chẩn đoán, xem bytecode bằng `javap -p -v` và xác nhận modifiers.

Không dùng cùng một lời giải cho mọi nguyên nhân. Ví dụ Kotlin all-open giải quyết ràng buộc override ở build-time đối với các class được mở; nó không tự sửa self-invocation.

## 10. Chẩn đoán bằng Spring APIs

### 10.1. Kiểm tra loại proxy

```java
Object bean = context.getBean("serviceBean");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Đoạn code **minh họa**, cần import `org.springframework.aop.support.AopUtils` và có biến `context` phù hợp. Diễn giải:

- `isAopProxy`: object do container trả về là Spring AOP proxy hay không.
- `isJdkDynamicProxy`: proxy được tạo theo interface JDK.
- `isCglibProxy`: proxy class-based do Spring tạo.
- **Cả ba không xác nhận một method final đã được advice.** Hãy gọi method qua bean proxy và kiểm tra side effect/recorder.

### 10.2. Kiểm tra modifiers bằng reflection

```java
import java.lang.reflect.Modifier;

Class<?> type = CglibService.class;

System.out.println("classFinal=" + Modifier.isFinal(type.getModifiers()));
System.out.println(
    "lockedFinal=" + Modifier.isFinal(
        type.getMethod("locked", String.class).getModifiers()
    )
);
```

Đây là **đoạn Java minh họa**, không phải chương trình độc lập vì dựa trên `CglibService` của ví dụ. Trong demo, nó in:

```text
classFinal=false
lockedFinal=true
```

Lấy modifiers của **target type** trước/sau khi kiểm tra proxy: runtime type của một CGLIB proxy có thể mang tên sinh động, không phải class nguồn. Muốn biết target class thực, có thể sử dụng `AopUtils.getTargetClass(bean)`.

### 10.3. Ma trận kiểm chứng thực tế

| Kiểm chứng | Kỳ vọng với CGLIB | Kỳ vọng với JDK proxy |
| --- | --- | --- |
| Bean target class `final`, có advisor match | Không thể tạo class subclass proxy | Có thể hoạt động nếu target implement interface phù hợp. |
| Bean target class không final, method `final` match advisor | Proxy có thể tồn tại, nhưng final method không được advice | Nếu lời gọi vào method interface được proxy và advisor match: có thể advice dù implementation final. |
| Method nằm ngoài interface | CGLIB có thể intercept nếu override được | Không expose method ấy qua JDK proxy. |
| Self-invocation `this.method()` | Không chạy advice cho lời gọi nội bộ | Không chạy advice cho lời gọi nội bộ. |
| `AopUtils.isAopProxy(bean)` | Có thể true dù method final không được advice | Có thể true nhưng pointcut method còn phải match. |
| Caller inject theo implementation | Thường phù hợp khi class subclassable | Không nên; proxy chỉ implement interface. |

### 10.4. Checklist tìm lỗi trong dự án

1. Xác định Spring bean và **method entry** được caller gọi: annotation nằm ở đâu, target là bean nào?
2. Gọi `context.getBean(...)` theo type được hỗ trợ, xác nhận **kiểu proxy thực tế** trước khi nhận định.
3. Dùng reflection/bytecode xem **target class** có final, **entry method** có final/private hay không.
4. Xem tất cả cấu hình ảnh hưởng proxy: `@EnableAspectJAutoProxy`, `@EnableTransactionManagement`, Boot `spring.aop.proxy-target-class` và những module tạo advisor khác.
5. Xem caller có đi qua proxy hay tự gọi `this.method()`, hoặc gọi target object được tạo bằng `new`.
6. Kiểm tra method có thuộc interface nếu dùng JDK proxy; client nên inject interface.
7. Gọi một method bình thường và method final có cùng policy qua Spring bean; assert **advice xuất hiện đúng nơi**.
8. Với bảo mật/transaction/cache, test hậu quả nghiệp vụ thực tế (deny, rollback, hit/miss), không dựa vào log proxy.
9. Nếu không có cách proxy thích hợp, refactor entry point hoặc thay bằng decorator/lời gọi explicit.

## 11. Những nhầm lẫn gây lỗi khó phát hiện

1. **“Có `@Aspect`, pointcut match là mọi method đều được intercept.”** Spring AOP còn phụ thuộc proxy, chữ ký method và đường gọi.
2. **“Bật `proxyTargetClass=true` để chặn được cả method final.”** Sai: chọn class proxy khiến `final` trở thành giới hạn override trực tiếp.
3. **“Class final luôn không thể có Spring AOP.”** Sai: JDK dynamic proxy có thể bao quanh một **interface** của final target class.
4. **“Chỉ cần class có interface là Spring sẽ dùng JDK proxy.”** Chưa đủ: cấu hình ép CGLIB và Boot AOP default có thể thay đổi lựa chọn.
5. **“Final method gây lỗi khởi động giống final class.”** Thường sai: class còn subclass được, nên proxy có thể tạo; riêng final method bị bỏ qua interception.
6. **“Mọi lời gọi đến final method qua CGLIB proxy đều an toàn vì method gốc vẫn chạy.”** Không nên suy như vậy, nhất là với stateful target; final method không được Spring override/delegate theo đường advice và có thể thấy state trên proxy khác dự kiến.
7. **“CGLIB proxy = AspectJ weaving.”** Sai: vẫn là Spring proxy, không tự chặn bytecode bên trong target hoặc constructor.
8. **“Thử thấy `isAopProxy=true` thì `@Transactional` chắc chắn có tác dụng.”** Sai: cần kiểm tra actual invocation và kết quả giao dịch.
9. **“Không thấy advice do final method thì thêm `exposeProxy=true`.”** Không đúng nguyên nhân: expose proxy không biến một final method thành override-able.
10. **“Bỏ final trong Kotlin source luôn đủ.”** Cần xem compiler plugin, Java bytecode, method visibility, proxy config, interface injection và call path.

## 12. Quy tắc ra quyết định

- **Muốn giữ class `final` và vẫn dùng Spring AOP?** Thiết kế interface làm contract, chọn JDK proxy, inject bằng interface và xác nhận cấu hình thực tế không ép CGLIB.
- **Muốn class-based Spring proxy?** Class phải subclass được; method cần advice phải override được, không `final`/`private`, caller phải đi qua proxy.
- **Đang thấy bean là proxy nhưng policy trên final method không hoạt động?** Đây là kết quả có thể dự đoán của CGLIB; đổi entry boundary trước khi tăng thêm annotation.
- **Cần chặn nội bộ/field/constructor?** Spring proxy không đáp ứng; cân nhắc thiết kế khác hoặc AspectJ weaving riêng với cấu hình phù hợp.
- **Policy liên quan bảo mật hoặc transaction?** Đòi hỏi integration test xác nhận hành vi nghiệp vụ, đặc biệt kiểm tra các method final và cách inject bean.

**Ghi nhớ:** CGLIB của Spring AOP **cần subclass**. `final class` khiến việc tạo class proxy không thể thực hiện; `final method` khiến riêng method đó không được advice, dù bean vẫn có proxy. **JDK interface proxy** có thể giải quyết trường hợp final target khi API và cấu hình phù hợp, nhưng không giải quyết self-invocation hoặc method ngoài interface.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Proxying Mechanisms (giới hạn final và JDK/CGLIB)](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — ProxyFactoryBean and JDK/CGLIB](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/pfb.html)
- [Spring Boot — Spring AOP auto-configuration](https://docs.spring.io/spring-boot/reference/features/aop.html)
