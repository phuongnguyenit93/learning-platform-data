# Bật hỗ trợ @AspectJ bằng @EnableAspectJAutoProxy trong Spring

## 1. Mục đích của cấu hình

Khi dùng **Spring Framework** với Java configuration, annotation `@EnableAspectJAutoProxy` yêu cầu Spring nhận diện các **Spring bean** được đánh dấu `@Aspect`, chuyển khai báo pointcut/advice thành advisor của Spring AOP và **tự tạo proxy** cho các bean có method được advisor áp dụng.

Đây là bước thiết lập hạ tầng **Spring AOP sử dụng cú pháp @AspectJ**. Chữ “AspectJ” trong tên annotation nói về **kiểu khai báo aspect**, không có nghĩa ứng dụng tự động dùng AspectJ compile-time weaving hoặc load-time weaving. Khi được bật theo cách này, cơ chế chặn thông thường vẫn là **Spring proxy tại các lời gọi method của Spring-managed bean**.

Ví dụ tối thiểu:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
```

Đây là **đoạn cấu hình**, chỉ phát huy tác dụng khi `AopConfig` được đăng ký trong một `ApplicationContext` phù hợp; riêng annotation này chưa tạo ra lời gọi advice nếu không có `@Aspect` bean và target bean/pointcut khớp.

**Khi nào cần học cách bật thủ công?** Chủ yếu trong ứng dụng Spring Framework tự cấu hình, những module dùng `AnnotationConfigApplicationContext`, các context con có cấu hình độc lập, hoặc khi cần hiểu rõ kiểu proxy. Với dự án **Spring Boot đã bật AOP auto-configuration**, thông thường không cần lặp lại annotation này; xem mục 7.

## 2. Điều kiện tiên quyết để cấu hình thực sự hoạt động

Để `@EnableAspectJAutoProxy` có tác dụng, phải đồng thời có:

1. **Spring context xử lý annotation cấu hình:** class mang `@Configuration` và `@EnableAspectJAutoProxy` được đăng ký, chẳng hạn `new AnnotationConfigApplicationContext(AopConfig.class)`. Đặt annotation trên class bất kỳ không được Spring nạp sẽ không thay đổi container.
2. **Hạ tầng Spring AOP và thư viện AspectJ pointcut:** phải có `spring-aop` và `org.aspectj:aspectjweaver` tương thích trên classpath. `aspectjweaver` được Spring dùng cho biểu thức pointcut của `@AspectJ`; không cần khởi động JVM với `-javaagent` để chạy ví dụ proxy.
3. **Có aspect được khai báo dưới dạng Spring bean:** `@Aspect` mô tả class là aspect, **không tự làm class đó được component scan đăng ký**. Dùng `@Aspect` + `@Component` (khi có `@ComponentScan` phù hợp) hoặc một `@Bean` trả về instance aspect.
4. **Có target Spring bean:** class nghiệp vụ do container quản lý, không phải object tạo bằng `new` từ code ngoài container.
5. **Pointcut khớp method và lời gọi đi qua proxy:** advice chỉ thực thi nếu bean/method khớp và caller thực sự gọi đến proxy được Spring trả về.

Ví dụ hai cách đăng ký **aspect**, chọn **một** cách cho một instance:

```java
// Cách A: component scan tìm class có cả @Aspect và @Component
@Aspect
@Component
public class LoggingAspect {
    // advice
}
```

```java
// Cách B: đăng ký explicit, cho phép không gắn @Component
@Configuration
@EnableAspectJAutoProxy
class AopConfig {
    @Bean
    LoggingAspect loggingAspect() {
        return new LoggingAspect();
    }
}
```

Các đoạn trên minh họa cách đăng ký, chưa phải chương trình độc lập. Nếu đã đăng ký `LoggingAspect` bằng component scan thì không thêm `@Bean` trùng lặp một cách vô ý. **Không dùng `@Aspect` đơn độc thay cho `@Component`** trong cấu hình component-scan.

## 3. `@EnableAspectJAutoProxy` làm gì trong Spring container?

Khi `ApplicationContext` đọc class `@Configuration`, `@EnableAspectJAutoProxy` import `AspectJAutoProxyRegistrar` để đăng ký cơ chế auto-proxy phù hợp (thường là `AnnotationAwareAspectJAutoProxyCreator`). Spring dùng hạ tầng bean post-processing để xem xét các bean và các advisor xuất phát từ Spring `@Aspect`.

Tổng quan:

```text
@Configuration + @EnableAspectJAutoProxy
             |
             v
Spring đăng ký @AspectJ auto-proxy infrastructure
             |
     Đăng ký @Aspect beans
             |
             v
Tạo / khởi tạo Spring target beans
             |
             v
Xét advisor + pointcut đối với target bean
             |
     +-------+-----------------+
     |                         |
Có advice phù hợp         Không có advice phù hợp
     |                         |
     v                         v
Trả bean dưới dạng proxy   Bean thông thường
     |
Caller gọi method qua proxy
     |
Advice -> target method -> advice/kết quả
```

Các ý nghĩa kỹ thuật cần phân biệt:

- Annotation **bật hạ tầng**; nó **không biến mọi bean thành proxy** và không làm mọi method đều có advice. Điều kiện match còn phụ thuộc pointcut và target.
- Aspect phải là **Spring-managed bean**; một class chỉ có `@Aspect` ngoài context sẽ không được auto-proxy infrastructure sử dụng.
- Việc proxy được tạo diễn ra trong lifecycle container, nên tránh coi phương thức gọi từ constructor hay logic khởi tạo bean là lời gọi được bảo đảm intercept. Tập trung vào lời gọi qua reference bean đã được khởi tạo và inject/tra cứu từ context.
- Khi target được proxy, **lời gọi nội bộ kiểu `this.otherMethod()` không đi vòng qua proxy**, nên advice gắn ở `otherMethod()` có thể không chạy cho đường gọi ấy.
- `@EnableAspectJAutoProxy` tự nó **không bật** `@Transactional`, `@Async`, method security hay cache annotations; các khả năng đó có cơ chế kích hoạt riêng. Chúng có thể cùng tồn tại và dùng cơ sở proxy của Spring.

### Khác biệt với AspectJ weaving

| Câu hỏi | Bật Spring `@AspectJ` bằng `@EnableAspectJAutoProxy` |
| --- | --- |
| Cơ chế chặn | Spring AOP tạo JDK proxy hoặc subclass proxy |
| Đối tượng áp dụng | Bean do Spring quản lý, với method call đi qua proxy |
| Chặn constructor/field access? | Không, nằm ngoài khả năng proxy-based Spring AOP |
| Chặn `this.method()` nội bộ? | Không; lời gọi không quay qua proxy |
| Có cần AspectJ compiler/agent? | Không; cần thư viện hỗ trợ khai báo/pointcut (`aspectjweaver`) trên classpath |
| Có tự bật `@Aspect` ngoài container? | Không; vẫn phải đăng ký bean |

Nếu mục tiêu cần bytecode weaving, cấu hình của bài này là chưa đủ. Đó là một lựa chọn kỹ thuật khác, cần thiết lập riêng.

## 4. Hai tham số quan trọng của annotation

`@EnableAspectJAutoProxy` có hai thuộc tính boolean:

```java
@Configuration
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = false
)
public class AopConfig {
}
```

### `proxyTargetClass`

Mặc định của chính `@EnableAspectJAutoProxy` là `false`. Đây là lựa chọn ưu tiên proxy qua interface khi có interface phù hợp; nếu target không có interface để proxy, Spring vẫn có thể phải dùng subclass proxy.

| Giá trị | Cách hiểu | Ảnh hưởng thực tế |
| --- | --- | --- |
| `proxyTargetClass = false` (mặc định của annotation) | Ưu tiên JDK dynamic proxy khi có interface phù hợp | Caller thường sử dụng kiểu interface mà proxy triển khai; các method ngoài interface không được đưa ra qua JDK proxy. |
| `proxyTargetClass = true` | Yêu cầu proxy dựa trên class (Spring dùng CGLIB) | Có thể inject/gọi theo kiểu class nhưng vẫn chịu giới hạn class/method `final`, method `private` và khả năng subclassing. |

Mẫu:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ClassProxyConfig {
}
```

Điều này **không** sửa được self-invocation. Không lạm dụng proxy dựa trên class khi muốn chặn `private` hoặc `final`: subclass không thể override những method đó. Một số hạn chế JVM/module path cũng có thể ảnh hưởng khả năng tạo subclass proxy.

**Tương tác với cấu hình khác:** trong cùng context, nhiều phần của Spring cùng cấu hình auto-proxy (ví dụ `@EnableTransactionManagement`) có thể hợp nhất thành một auto-proxy creator và dùng thiết lập proxy mạnh hơn. Trong Spring Boot, cấu hình mặc định proxy target class có thể khác mặc định của annotation. Vì vậy, kết luận loại proxy dựa trên **cấu hình thực tế hoặc kiểm tra runtime**, không dựa vào một annotation đơn lẻ.

### `exposeProxy`

Mặc định `false`: Spring không công khai proxy hiện tại qua `AopContext.currentProxy()` để code nghiệp vụ truy cập. Nếu đặt:

```java
@Configuration
@EnableAspectJAutoProxy(exposeProxy = true)
class ExposedProxyConfig {
}
```

Spring có thể cung cấp proxy hiện tại trong **ngữ cảnh một lời gọi đang đi qua proxy** bằng một `ThreadLocal` của Spring AOP. Đây là cấu hình nâng cao, dùng khi đã hiểu sự phụ thuộc vào context proxy; **không phải điều kiện để advice thông thường hoạt động**.

Ví dụ phương thức tự gọi cần nhận interception:

```java
// Minh họa cách truy cập proxy đã expose; không phải file Java độc lập
((MyService) AopContext.currentProxy()).otherMethod();
```

Đoạn trên còn đòi hỏi import `org.springframework.aop.framework.AopContext`, `MyService` là kiểu có thể truy cập qua proxy, `exposeProxy=true` và đang ở trong lời gọi qua proxy. Ngoài ngữ cảnh ấy, `currentProxy()` có thể ném `IllegalStateException`. Cách thiết kế thường dễ bảo trì hơn là **tách method được intercept sang một Spring bean khác rồi inject**, tạo ranh giới proxy tường minh. ThreadLocal này cũng không tự truyền xuyên thread/task bất đồng bộ.

## 5. Demo Spring Framework thuần: bật @AspectJ bằng annotation

Ví dụ sau chạy được với **Java 17+**, Spring Framework **6.2.19**, Gradle và AspectJ Weaver **1.9.25.1**. Nó chứng minh ba điều: bật hạ tầng bằng `@EnableAspectJAutoProxy`, Spring tạo proxy cho target phù hợp và self-invocation bỏ qua proxy.

### 5.1. Cấu trúc tệp

```text
aspectj-enable-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/lesson/
    ├── Main.java
    ├── AppConfig.java
    ├── BillingService.java
    └── AuditAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'aspectj-enable-demo'
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
    mainClass = 'com.example.lesson.Main'
}
```

Đây là ứng dụng Spring Framework độc lập, **không cần Spring Boot**. Một dự án Spring Boot nên để BOM/dependency management của Boot quản lý versions thay vì copy versions cố định này sang project khác.

### 5.2. Tạo Spring configuration

**`AppConfig.java`**

```java
package com.example.lesson;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = Main.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
}
```

`@ComponentScan` tìm `BillingService` và `AuditAspect` trong cùng package. `proxyTargetClass=true` làm ví dụ xác định rõ class proxy, vì `BillingService` không định nghĩa interface. Có thể bỏ tham số trong trường hợp này và Spring vẫn có thể chọn class proxy.

### 5.3. Tạo service làm target

**`BillingService.java`**

```java
package com.example.lesson;

import org.springframework.stereotype.Service;

@Service
public class BillingService {
    public String charge(String orderId) {
        return "charged:" + orderId;
    }

    public String internalCharge(String orderId) {
        // Lời gọi trên chính target, không qua Spring proxy của charge().
        return charge(orderId);
    }
}
```

### 5.4. Tạo Spring-managed aspect

**`AuditAspect.java`**

```java
package com.example.lesson;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* com.example.lesson.BillingService.charge(..))")
    public void beforeCharge(JoinPoint joinPoint) {
        System.out.println("intercepted:" + joinPoint.getSignature().getName());
    }
}
```

`@Aspect` đánh dấu class cung cấp advice; `@Component` đưa nó vào component scan. Pointcut nhắm **duy nhất method `BillingService.charge(..)`**. `@Before` in một dòng khi lời gọi đi qua proxy đến đúng method.

### 5.5. Bootstrapping và gọi service qua context

**`Main.java`**

```java
package com.example.lesson;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            BillingService service = context.getBean(BillingService.class);

            System.out.println("isProxy=" + AopUtils.isAopProxy(service));
            System.out.println(service.charge("A-1"));
            System.out.println(service.internalCharge("B-2"));
        }
    }
}
```

Từ thư mục project, chạy bằng Gradle đã cài:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

**Ba lời gọi print và một advice tạo đúng bốn dòng sau** (không tính cảnh báo log từ JVM, Gradle hoặc môi trường):

```text
isProxy=true
intercepted:charge
charged:A-1
charged:B-2
```

Giải thích từng dòng:

1. `isProxy=true`: context đã trả về một Spring AOP proxy của `BillingService`, vì bean này có method khớp advisor.
2. `intercepted:charge`: `service.charge("A-1")` gọi từ `Main` vào Spring bean **qua proxy**, nên `@Before` chạy.
3. `charged:A-1`: lời gọi gốc vẫn thực thi và trả về chuỗi từ target.
4. `charged:B-2`: `service.internalCharge("B-2")` đi qua proxy ở entry method nhưng bên trong gọi `this.charge(..)` trực tiếp trên target, nên **không có dòng `intercepted:charge` thứ hai**.

**Đối chứng hợp lệ:** thử bỏ `@EnableAspectJAutoProxy` khỏi `AppConfig` trong project Spring Framework thuần này khi không có cấu hình AOP khác; aspect có thể vẫn là bean, nhưng không được xử lý thành advice của auto-proxy creator. Kết quả ứng dụng lúc này dự kiến:

```text
isProxy=false
charged:A-1
charged:B-2
```

Đó là cách phân biệt rõ **đăng ký aspect bean** và **bật hạ tầng auto-proxy**. Nếu cùng context còn phần khác đã bật AOP, đối chứng này không còn độc lập và có thể vẫn xuất hiện proxy.

## 6. Cách kiểm chứng cấu hình khi advice không chạy

Từng kiểm tra sau nhằm xác định nguyên nhân cụ thể, thay vì thêm annotation ngẫu nhiên.

| Biểu hiện | Cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không có dòng advice, `isAopProxy(bean) == false` | Class `@Configuration` chứa `@EnableAspectJAutoProxy` có được nạp trong context hiện tại không? | Đưa config đúng vào `@Import`, `@ComponentScan` hoặc `AnnotationConfigApplicationContext`. |
| Class có `@Aspect` nhưng không có advice | Aspect có là bean không? Có `@Component` và scan đúng package, hoặc `@Bean`? | Đăng ký aspect bean rõ ràng. |
| Startup lỗi thiếu class AspectJ | Có `org.aspectj:aspectjweaver` tương thích không? | Thêm dependency ở classpath đúng module/runtime. |
| `isAopProxy(bean)==false` dù hạ tầng đã bật | Pointcut có match method/class? Target có là Spring bean? | Sửa biểu thức/annotation và test một method có thể proxy. |
| Advice chạy cho lời gọi từ bean khác nhưng không chạy khi `this.method()` | Self-invocation bỏ qua proxy. | Tách nghiệp vụ sang Spring bean khác hoặc đổi ranh giới gọi. |
| Có proxy, nhưng ép cast sang concrete class bị lỗi | Có đang dùng JDK proxy theo interface không? | Inject bằng interface hoặc cân nhắc class-based proxy nếu thích hợp. |
| Proxy không chặn method như mong đợi | Method `private`/`final`, class `final`, method không public với JDK proxy? | Chọn public service contract intercept được; không trông cậy vào subclass để override `final`/`private`. |
| Có advice nhưng log xuất hiện nhiều lần | Có nhiều bean aspect/advisor trùng, nhiều rule match, hoặc nhiều context? | Kiểm tra bean registration, advisor chain, tránh đăng ký trùng aspect. |
| Chạy trong Spring Boot nhưng bỏ `@EnableAspectJAutoProxy` vẫn có advice | Boot đang tự bật AOP khi đủ classpath. | Đây là hành vi mong đợi; xem phần cấu hình Boot bên dưới. |

Để kiểm tra proxy khi debug:

```java
// Đoạn minh họa bên trong code có thể truy cập Spring bean
boolean anyProxy = AopUtils.isAopProxy(service);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(service);
boolean cglibProxy = AopUtils.isCglibProxy(service);
```

Import `org.springframework.aop.support.AopUtils`. Kết quả `isAopProxy` chỉ cho biết **bean có proxy hay không**, không khẳng định mọi method match pointcut. Kiểm tra advice bằng một hành vi quan sát cụ thể hoặc integration test chạy với context thật.

### Kiểm thử mẫu với context thực

Một kiểm thử phù hợp cần khởi tạo `AnnotationConfigApplicationContext` hoặc `@SpringJUnitConfig` để sử dụng bean từ Spring container, rồi assert cả **việc có proxy** và **hiệu ứng advice**. Test tạo `new BillingService()` chỉ kiểm tra code target, **không kiểm tra interception**. Khi aspect in console, demo dùng output cho dễ theo dõi; trong kiểm thử thực tế, nên thay `System.out` bằng recorder/mock/test sink có thể assert số lần advice chạy.

## 7. Spring Boot: vì sao thường không cần ghi @EnableAspectJAutoProxy?

Khi ứng dụng **Spring Boot** có dependency AspectJ/Spring AOP phù hợp và không tắt AOP auto-configuration, Boot tự cấu hình AOP tương đương việc bật `@EnableAspectJAutoProxy`. Do đó, một ứng dụng Boot điển hình có thể dùng `@Aspect` + `@Component` ngay mà không đặt annotation `@EnableAspectJAutoProxy` lên class main.

Ví dụ dependency **chọn theo major version của Boot**:

```gradle
// Trong Spring Boot 3.x, với plugin/BOM Boot đã cấu hình
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

```gradle
// Trong Spring Boot 4.x, với plugin/BOM Boot đã cấu hình
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

Chọn **đúng một cấu hình phù hợp phiên bản project**; hai khối trên là **ví dụ thay thế**, không đưa cả hai vào cùng `build.gradle`. Với Boot, dependency management quản lý version tương thích. Đừng hiểu tên `starter-aspectj` trong Boot 4.x là bằng chứng tự động bật AspectJ bytecode weaving: `@AspectJ` trong Spring AOP vẫn thường chạy qua proxy.

Cấu hình Boot liên quan:

```properties
# Thông thường mặc định auto-configure AOP khi đáp ứng điều kiện
spring.aop.auto=true

# Boot thường dùng subclass-based proxy theo mặc định
spring.aop.proxy-target-class=true
```

Đổi sang:

```properties
spring.aop.proxy-target-class=false
```

để Boot ưu tiên JDK interface proxy khi phù hợp. Thuộc tính `spring.aop.auto=false` vô hiệu hóa **phần AOP auto-configuration của Boot**, không phải mệnh lệnh xóa mọi auto-proxy creator do các cấu hình Spring khác tạo ra. Nếu ứng dụng tự thêm `@EnableAspectJAutoProxy`, Boot không còn là nơi duy nhất quyết định việc AOP có được bật hay không. Khi muốn chủ động quản lý AOP thủ công trong Boot, kiểm tra **tổng hợp** các cấu hình thực tế, tránh đặt hai cơ chế như các nút bật/tắt độc lập.

**Bảng đối chiếu:**

| Môi trường | Cách bật hỗ trợ `@AspectJ` | Điểm cần nhớ |
| --- | --- | --- |
| Spring Framework Java config độc lập | Thêm `@EnableAspectJAutoProxy` vào `@Configuration` được nạp | Phải có `aspectjweaver`, Spring AOP, aspect bean và target bean. |
| Spring Boot có AOP auto-configuration | Thường **không cần** khai báo thủ công | Dùng starter đúng major version và `spring.aop.*` nếu cần. |
| Cấu hình Spring XML truyền thống | `<aop:aspectj-autoproxy/>` | Cùng mục tiêu bật Spring AOP @AspectJ theo kiểu XML. |
| Nhiều ApplicationContext riêng | Đặt enable config tại context nơi các bean cần advice sống | Annotation có phạm vi ở local context, không tự lan tới mọi context khác. |

### Phạm vi nhiều ApplicationContext

Spring có thể có **root context** và các **child context** độc lập (ví dụ mô hình web context cũ). Javadoc của `@EnableAspectJAutoProxy` quy định annotation áp dụng trong **local application context**. Nếu cần proxy ở nhiều context, phải cấu hình enable trong từng context tương ứng và bảo đảm aspect/target bean có mặt đúng chỗ. Không suy ra bật trên một context thì mọi bean ở context khác đều được advisor xử lý.

## 8. Sai lầm phổ biến khi thiết lập

1. **Nhầm `@Aspect` với Spring stereotype.** `@Aspect` không thay thế `@Component`/`@Bean`; aspect không có trong context thì không được dùng.
2. **Bật annotation nhưng thiếu `aspectjweaver`.** `@EnableAspectJAutoProxy` cần thư viện này để hỗ trợ khai báo pointcut.
3. **Thêm annotation vào class không được Spring quét/nạp.** Chỉ annotation nằm trong cấu hình có hiệu lực của context mới kích hoạt hạ tầng.
4. **Cho rằng mọi bean đều thành proxy.** Bean không được advisor áp dụng có thể giữ nguyên object.
5. **Dùng `proxyTargetClass=true` để mong chặn `this.method()`.** Self-invocation vẫn bỏ qua proxy dù chọn JDK hay subclass proxy.
6. **Bật `exposeProxy=true` để “sửa” mọi lời gọi.** Thuộc tính chỉ công khai proxy hiện tại trong ngữ cảnh hỗ trợ; không làm code bên ngoài container tự được intercept.
7. **Dùng `@EnableAspectJAutoProxy` như annotation bật transaction/cache/async.** Những khả năng đó có cấu hình activation riêng và có thể tương tác với auto-proxy, cần xem xét từng trường hợp.
8. **Coi `@EnableAspectJAutoProxy` là AspectJ weaving.** Nó bật cơ chế Spring proxy-based @AspectJ; không chặn constructor/field hay object tùy ý.
9. **Ghi annotation lặp lại trong Boot mà không xem auto-config.** Thường không cần và dễ gây nhầm lẫn lúc xử lý cấu hình proxy.
10. **Quên thứ tự advisor khi kết hợp nhiều Spring interception.** `@Order` trên aspect và order của các advisor khác có thể thay đổi thời điểm advice chạy so với transaction/security; hãy kiểm tra thứ tự thực tế trước khi suy luận điều kiện “thành công” hoặc rollback.

## 9. Checklist hoàn tất

- [ ] Class `@Configuration` mang `@EnableAspectJAutoProxy` được nạp vào đúng Spring `ApplicationContext`.
- [ ] Có Spring AOP và AspectJ Weaver tương thích trong dependencies; không vô tình trộn Spring Framework/Boot versions.
- [ ] Class `@Aspect` đã là Spring bean qua `@Component` + scan hoặc `@Bean`.
- [ ] Target method thuộc Spring bean; pointcut match chính xác phạm vi mong muốn.
- [ ] Caller nhận bean thông qua DI/context, gọi **qua proxy**; đã kiểm tra `this.method()` và object tạo bằng `new`.
- [ ] `proxyTargetClass` hợp với kiểu bean/API, `final`, `private`, interface và cách inject.
- [ ] Chỉ bật `exposeProxy` khi có trường hợp thực tế cần thiết và hiểu rõ ngữ cảnh `ThreadLocal`.
- [ ] Với Boot, đã kiểm tra AOP auto-configuration và `spring.aop.auto`/`spring.aop.proxy-target-class` trước khi thêm enable thủ công.
- [ ] Nếu có nhiều context, đã bật ở đúng nơi.
- [ ] Đã chạy integration test xác nhận proxy **và** side effect advice; kiểm tra đường gọi bình thường, self-invocation và trường hợp pointcut không match.

**Điểm nhớ:** `@EnableAspectJAutoProxy` giải quyết bước **cho phép Spring xử lý `@Aspect` bean và tạo proxy cho target phù hợp** trong một context. Nó không tự đăng ký mọi aspect, không biến tất cả bean thành proxy, không vượt giới hạn self-invocation và không cần khai báo lại khi Spring Boot đã auto-configure đúng.

## Tài liệu Spring tham khảo

- [Spring Framework — EnableAspectJAutoProxy Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableAspectJAutoProxy.html)
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Boot — AOP Auto-configuration](https://docs.spring.io/spring-boot/reference/features/aop.html)
