# Ràng buộc annotation vào tham số advice trong Spring AOP

## 1. Bài học giải quyết vấn đề gì?

Trong **Spring Framework AOP sử dụng cú pháp @AspectJ**, một pointcut không chỉ có thể hỏi “method execution này có annotation phù hợp không?”, mà còn có thể **truyền chính annotation instance đó vào tham số của advice**. Advice nhờ vậy đọc được metadata như mã audit, nhóm nghiệp vụ, nhãn metric hoặc cấp độ theo dõi mà không phải tự tìm annotation bằng reflection.

Một ví dụ:

```java
@AuditAction("create")
public String create(String orderId) {
    return "created:" + orderId;
}
```

Và trên Spring-managed aspect:

```java
@Before(
    value = "execution(public * com.example.binding.BillingService.*(..))"
          + " && @annotation(action)",
    argNames = "action"
)
public void beforeAction(JoinPoint jp, AuditAction action) {
    System.out.println(action.value() + ":" + jp.getSignature().getName());
}
```

Trong biểu thức, **`action` không phải tên một class annotation**. Nó là **biến binding**, được nối với tham số Java `AuditAction action` của advice. Khi một Spring AOP proxy intercept method phù hợp, Spring/AspectJ pointcut machinery đưa annotation object vào advice để đọc `action.value()`.

**Phạm vi bài:** cơ chế binding annotation **trong Spring AOP cho Spring-managed beans**, cách khai báo annotations và advice parameters, dùng `@annotation`/`@within`/`@target`/`@args` khi thích hợp, `argNames`, Spring proxy và kiểm thử. Các ý niệm AOP tổng quát và AspectJ weaving không phải trọng tâm; `@EnableAspectJAutoProxy` **không** bật compile-time/load-time weaving.

## 2. Phân biệt chọn method theo annotation và bind annotation

Cả hai biểu thức sau có thể chọn method được đánh dấu `@AuditAction`, nhưng vai trò của chúng khác nhau.

**Dạng kiểm tra annotation có tồn tại:**

```java
@Before("@annotation(com.example.binding.AuditAction)")
public void beforeAnnotatedMethod() {
    // Biết method execution match marker, không nhận annotation object.
}
```

**Dạng binding để đọc metadata:**

```java
@Before(
    value = "@annotation(action)",
    argNames = "action"
)
public void beforeAnnotatedMethod(AuditAction action) {
    String auditCode = action.value();
}
```

Dạng thứ nhất dùng **fully qualified annotation type name**. Dạng thứ hai dùng **tên biến `action`**, được suy từ chữ ký advice/`argNames`; kiểu Java `AuditAction` của tham số ràng buộc annotation sẽ được bind.

Điểm nhớ:

- `@annotation(SomeType)`: yêu cầu **method join point** mang annotation có type ấy.
- `@annotation(action)` và `AuditAction action`: yêu cầu annotation type `AuditAction` và **truyền annotation instance** vào advice.
- `action.value()`: đọc metadata được khai báo trên annotation; không cần `method.getAnnotation(...)` thủ công trong case đơn giản.
- **Binding không tự tạo Spring proxy**. Method phải thuộc target Spring bean, aspect là bean và invocation đi qua proxy thích hợp.
- **Tên biến phải khớp chính xác**; annotation attribute như `value`, `code` không phải tên binding trừ khi advice parameter thật sự mang tên đó.

Không nhầm annotation type của Java `@Target` (chỉ nơi có thể đặt annotation) với pointcut expression `@target(...)` (xét annotation ở class của target object Spring).

## 3. Annotation Java cần khai báo đúng cho Spring AOP

Một annotation cho **method**:

```java
package com.example.binding;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditAction {
    String value();
}
```

Một annotation cho **class/type**:

```java
package com.example.binding;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ServiceGroup {
    String value();
}
```

Từng annotation nằm trong file Java riêng có cùng tên public type. Trong ví dụ `ServiceGroup` là annotation trên target class; `AuditAction` trên method.

### Vì sao dùng RUNTIME retention?

Spring/AspectJ pointcut matching và binding cần thông tin annotation lúc chạy. Với bài học này dùng `@Retention(RetentionPolicy.RUNTIME)` để các annotations có sẵn trên runtime class/method.

- `SOURCE`: annotation không tồn tại trong compiled class file ở runtime.
- `CLASS`: thông tin có thể nằm trong bytecode, nhưng không có bảo đảm nhìn thấy theo Java reflection thông thường; **không chọn** nó cho bài binding runtime.
- `RUNTIME`: annotation sẵn có để runtime matcher/binding sử dụng.
- `@Target(METHOD)` chọn vị trí gắn trên method; `@Target(TYPE)` chọn class/interface/type. Đặt đúng loại annotation tương ứng pointcut designator.

Các annotation trên là Java annotation bình thường; **chúng không tự tạo Spring bean hoặc tự chạy advice**. `@Aspect` cần là Spring-managed bean, target cũng cần Spring-managed, và AOP infrastructure phải được bật.

### Có cần @Inherited?

`@Inherited` (Java) áp dụng cho việc kế thừa **annotation trên class** trong một số lookup trên subclass; nó **không** có tác dụng làm annotation trên method tự được thừa kế, cũng **không truyền annotation từ interface xuống implementing class**.

Không lạm dụng `@Inherited` như lời giải cho mọi mismatch `@annotation`/`@target`. Với interface, overridden methods, Kotlin types hoặc composed annotations, hãy kiểm tra actual Spring advisor matching trên proxy mode thực tế.

## 4. Bốn nhóm pointcut annotation mà Spring AOP hỗ trợ

Spring AOP hỗ trợ các pointcut designators sau với method execution join points của Spring beans:

| Designator | Annotation được xét trên đâu? | Dạng binding có thể dùng | Điểm cần nhớ |
| --- | --- | --- | --- |
| `@annotation` | **Method đang được execution** | `@annotation(action)` → `AuditAction action` | Phù hợp nhất để nhận metadata gắn ở từng operation. |
| `@target` | **Class của target object** đằng sau Spring proxy | `@target(group)` → `ServiceGroup group` | Gắn annotation ở implementation/target class thực tế. |
| `@within` | **Type mà trong đó method execution được khai báo** và có annotation | `@within(group)` → `ServiceGroup group` | Khác `@target` trong trường hợp inheritance/declaring type. |
| `@args` | **Runtime types của arguments được truyền** mang type annotations tương ứng | `@args(marker)` → type-annotation object phù hợp | Không phải annotation đặt trực tiếp lên parameter declaration. |

Tất cả các designators này đều **xét annotation như một điều kiện matching**, và có **binding form** để truyền annotation vào advice.

### 4.1. @annotation — annotation trên target method

```java
@Before(
    value = "execution(public * com.example.binding..*Service.*(..))"
          + " && @annotation(action)",
    argNames = "action"
)
public void inspectMethod(AuditAction action) {
    System.out.println("code=" + action.value());
}
```

Đoạn này là minh họa đặt trong `@Aspect` được Spring quản lý. Nó chỉ xét method execution trong package/type pattern và bind annotation kiểu `AuditAction`. Nếu method không có annotation phù hợp, advice không được gọi do biểu thức đó.

Đây là lựa chọn tự nhiên cho metadata của từng public operation: `create` có tag `"create"`, `refund` có tag `"refund"`, trong khi method `health` không mang marker thì không bị advice `@annotation` này chọn.

### 4.2. @target — annotation trên runtime target class

```java
@Before(
    value = "execution(public * com.example.binding..*Service.*(..))"
          + " && @target(group)",
    argNames = "group"
)
public void inspectTarget(ServiceGroup group) {
    System.out.println("serviceGroup=" + group.value());
}
```

Khi object đích của Spring AOP proxy thuộc class có `@ServiceGroup("billing")`, advice có thể nhận annotation của **class target ấy**. `@target` không có nghĩa “annotation trên return type” và cũng không đồng nghĩa Java meta-annotation `@Target`.

Một Spring proxy có runtime class sinh tự động; **đừng kiểm tra `proxy.getClass()` rồi nghĩ đó chắc là nơi đặt marker**. Khi debug, kiểm tra target type bằng `AopUtils.getTargetClass(proxy)`.

### 4.3. @within — annotation trên type khai báo method

```java
@Before(
    value = "execution(public * com.example.binding..*Service.*(..))"
          + " && @within(group)",
    argNames = "group"
)
public void inspectWithin(ServiceGroup group) {
    // Bind annotation của type liên quan đến @within.
}
```

So với `@target`, Spring docs mô tả `@within` về **method execution được khai báo trong annotated types**. Nếu method inherited từ superclass, annotation nằm ở subclass hay interface, ý nghĩa declaring type/runtime target có thể phân kỳ; luôn kiểm thử version và loại proxy của dự án trước khi dùng annotation làm policy quan trọng.

### 4.4. @args — annotation trên runtime type của đối số

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface SensitivePayload {
}
```

```java
@SensitivePayload
public class TransferRequest {
}
```

```java
@Before(
    value = "execution(public * com.example.binding..*Service.process(..))"
          + " && @args(marker)",
    argNames = "marker"
)
public void beforeSensitivePayload(SensitivePayload marker) {
    // Thông tin annotation trên runtime class của argument.
}
```

Các đoạn `@args` là **minh họa**, không nằm trong project runnable mục 7; cần đúng imports, Spring beans, public types và chữ ký một argument thích hợp. `@args` khác hoàn toàn với Java `@Target(ElementType.PARAMETER)`: nó xét **type của giá trị argument tại runtime**, không xem annotation đặt trên parameter declaration.

`@args` có điều kiện phụ thuộc runtime arguments; nếu null, primitive, nhiều arguments, interface/subclass hoặc một annotation nằm trên declared parameter type nhưng không nằm trên actual argument class, kết quả matching cần thử trong context thật.

## 5. Cú pháp argNames và tham số lời advice

Spring dùng tên trong pointcut expressions và tên tham số advice để liên kết binding. Ví dụ:

```java
@Before(
    value = "@annotation(action)",
    argNames = "action"
)
public void beforeAction(AuditAction action) {
    // ...
}
```

Ba vị trí `action` là **cùng một binding name**. Nếu viết `@annotation(audit)` nhưng `argNames="action"`, Spring không thể liên kết tên `audit` như ví dụ dự kiến và có thể báo lỗi khi dựng advisor.

### 5.1. JoinPoint là tham số đặc biệt

Khi cần cả metadata của method và annotation:

```java
@Before(
    value = "@annotation(action)",
    argNames = "action"
)
public void beforeAction(JoinPoint jp, AuditAction action) {
    String methodName = jp.getSignature().getName();
    String actionName = action.value();
}
```

`JoinPoint` có import `org.aspectj.lang.JoinPoint` và **đặt đầu danh sách tham số**. Theo Spring, tên tham số `JoinPoint` đầu tiên **có thể bỏ khỏi `argNames`**, vì framework nhận diện kiểu đặc biệt đó. Bởi vậy `argNames="action"` là đúng cho signature `(JoinPoint jp, AuditAction action)`.

Một advice chỉ cần `JoinPoint` có thể khai báo:

```java
@Before("execution(* com.example.binding..*Service.*(..))")
public void inspect(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
```

Không cần `argNames` nếu không bind biến expression nào khác.

### 5.2. ProceedingJoinPoint dành cho @Around

```java
@Around(
    value = "execution(public * com.example.binding..*Service.*(..))"
          + " && @annotation(action)",
    argNames = "action"
)
public Object aroundAction(
        ProceedingJoinPoint pjp, AuditAction action) throws Throwable {
    // Có thể đọc action.value() trước hoặc sau.
    return pjp.proceed();
}
```

Đây là **mã minh họa** dùng trong Spring-managed `@Aspect` và cần import `org.aspectj.lang.ProceedingJoinPoint`, `Around`. `ProceedingJoinPoint` phải là tham số đầu của `@Around` và `proceed()` được gọi để target tiếp tục chạy. `argNames` không cần kể tên `pjp` đầu tiên.

Nếu chỉ đọc annotation/log, `@Before` ít quyền hơn và tránh nguy cơ quên gọi `proceed()`; dùng `@Around` khi thực sự cần quản lý thứ tự/thời gian hoặc biến đổi outcome theo contract.

### 5.3. Nhiều binding parameters

Có thể bind cả business argument, target và annotation:

```java
@Before(
    value = "execution(public * com.example.binding.BillingService.create(..))"
          + " && args(id)"
          + " && @annotation(action)",
    argNames = "id,action"
)
public void beforeCreate(
        JoinPoint jp, String id, AuditAction action) {
    System.out.println(
        action.value() + ":" + id + ":" + jp.getSignature().getName()
    );
}
```

- `args(id)` bind **runtime method argument** vào `String id`.
- `@annotation(action)` bind **method annotation** vào `AuditAction action`.
- `argNames="id,action"` tương ứng hai binding variables; không cần ghi `jp` vì nó là tham số `JoinPoint` đầu tiên.
- Advice chỉ chạy khi toàn bộ biểu thức match.
- Nếu giá trị đầu vào hoặc annotation metadata nhạy cảm, **không in thẳng** vào production logs.

`args(id)` khác với `@args(marker)`: cái trước bind **giá trị argument**, cái sau xét/bind **annotation trên type của argument**.

## 6. Spring infrastructure bắt buộc để annotation binding chạy

Một target method có annotation không tự được advice. Cần đủ bốn điều kiện:

1. **Aspect bean:** class `@Aspect` phải được đăng ký bằng `@Component` trong vùng component scan hoặc trả về từ `@Bean`.
2. **AOP support:** trong Spring Framework Java-config dùng `@EnableAspectJAutoProxy` và `aspectjweaver` tương thích; với Spring Boot sử dụng AOP auto-configuration khi starter phù hợp.
3. **Target bean:** business object là Spring-managed bean; nếu tạo `new BillingService()` bên ngoài context, Spring AOP không tự intercept.
4. **Proxy boundary:** caller lấy/inject target **qua proxy**, method phải nằm trên interface của JDK proxy hoặc override được trong CGLIB; `this.inner()` không quay lại proxy.

Đây là **Spring AOP proxy**, không phải AspectJ load-time weaving. Có dependency `aspectjweaver` để Spring parse `@AspectJ` expressions không đồng nghĩa đã thiết lập Java agent.

`@EnableAspectJAutoProxy(proxyTargetClass=true)` có thể ép class-based proxy. Với Java `final class`, CGLIB không subclass được; `final method` không override được, nên annotation trên method ấy không tự cứu interception. Nếu có interface và không ép class proxy, JDK dynamic proxy có thể phù hợp, nhưng method phải thuộc interface và annotation matching trên interface/implementation cần integration test.

### Hai cách tạo aspect bean

**Component scan:**

```java
@Aspect
@Component
public class AuditAspect {
    @Before("@annotation(action)")
    public void before(AuditAction action) {
        // ...
    }
}
```

**Bean factory method:**

```java
@Configuration
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

Các đoạn code này **minh họa**, không phải ví dụ project runnable; imports/classes sẽ đầy đủ ở mục 7. `@Aspect` **không tự mang nghĩa của `@Component`**: nếu dùng component scan mà thiếu registration, advice sẽ không được Spring dựng. Không đăng ký trùng cả scan và `@Bean` nếu không có lý do rõ ràng.

## 7. Demo chạy được: bind annotation trên method và class vào hai advice

Demo Spring Framework thuần với **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1** và Gradle. Một Spring target class mang `@ServiceGroup("billing")`, hai methods mang `@AuditAction`. Aspect dùng hai `@Before` advices riêng:

- `@annotation(action)` bind metadata của từng method và lưu event.
- `@target(group)` bind annotation của target class và tăng counter cho mọi method phù hợp trên target.

Ngoài ra, `selfCall` chứng minh một method nội bộ có `@AuditAction` **không được advice lần nữa** khi được gọi qua `this`, dù body Java vẫn chạy.

### 7.1. Cấu trúc thư mục

```text
spring-aop-annotation-binding/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/binding/
    ├── AuditAction.java
    ├── ServiceGroup.java
    ├── BillingService.java
    ├── BindingAspect.java
    ├── AppConfig.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-annotation-binding'
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
    mainClass = 'com.example.binding.Main'
}
```

Tài liệu Spring Framework 6.2.19 tương thích với Java 17+. Trong project Spring Boot, tránh ép các Spring module version thủ công trái BOM của phiên bản Boot đang dùng.

### 7.2. Định nghĩa annotation trên method

**`AuditAction.java`**

```java
package com.example.binding;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditAction {
    String value();
}
```

Annotation này không có logic runtime riêng; Spring AOP aspect sẽ bind và đọc `value()` khi pointcut match.

### 7.3. Định nghĩa annotation trên target type

**`ServiceGroup.java`**

```java
package com.example.binding;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ServiceGroup {
    String value();
}
```

`ServiceGroup` khác `AuditAction` ở `@Target`: một annotation dùng trên class, một annotation dùng trên method.

### 7.4. Spring service với hai methods được đánh dấu

**`BillingService.java`**

```java
package com.example.binding;

@ServiceGroup("billing")
public class BillingService {
    @AuditAction("create")
    public String create(String id) {
        return "created:" + id;
    }

    @AuditAction("reject")
    public String reject(String id) {
        throw new IllegalStateException("rejected:" + id);
    }

    public String health() {
        return "ok";
    }

    public String selfCall(String id) {
        return this.create(id);
    }
}
```

- `create`: có method annotation `@AuditAction("create")`; return bình thường.
- `reject`: có method annotation `@AuditAction("reject")`; ném exception. `@Before` vẫn được gọi trước khi target ném.
- `health`: không có method annotation `@AuditAction`, nhưng **class** có `@ServiceGroup("billing")`.
- `selfCall`: không có method annotation; nó gọi `this.create(...)` trên cùng target. Self-invocation bỏ qua proxy, nên `@Before` cho `create` không chạy thêm cho lời gọi nội bộ này.

Không method nào final/private và class không final để loại trừ nguyên nhân CGLIB không override được.

### 7.5. Aspect bind hai annotation kinds độc lập

**`BindingAspect.java`**

```java
package com.example.binding;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class BindingAspect {
    private final List<String> actionEvents =
            new CopyOnWriteArrayList<>();
    private final AtomicInteger groupCalls = new AtomicInteger();

    @Before(
        value = "execution(public * com.example.binding.BillingService.*(..))"
              + " && @annotation(action)",
        argNames = "action"
    )
    public void beforeAction(JoinPoint jp, AuditAction action) {
        actionEvents.add(
            action.value() + ":" + jp.getSignature().getName()
        );
    }

    @Before(
        value = "execution(public * com.example.binding.BillingService.*(..))"
              + " && @target(group)",
        argNames = "group"
    )
    public void beforeGroup(ServiceGroup group) {
        if ("billing".equals(group.value())) {
            groupCalls.incrementAndGet();
        }
    }

    public List<String> events() {
        return List.copyOf(actionEvents);
    }

    public int groupCount() {
        return groupCalls.get();
    }
}
```

Lưu ý:

- `argNames="action"` ánh xạ tới `AuditAction action`; tham số `JoinPoint jp` đầu tiên được nhận diện đặc biệt nên không cần liệt kê.
- `argNames="group"` ánh xạ tới `ServiceGroup group`.
- `group.value()` đọc metadata của annotation bind trên class target, không phải tên class Spring proxy.
- `CopyOnWriteArrayList` và `AtomicInteger` giúp các phép ghi quan sát không bị race cơ bản; demo gọi tuần tự, không dùng counters làm distributed metrics.
- **Không in log trong advice**, để stdout cuối cùng không phụ thuộc thứ tự hai `@Before` advices trên cùng join point.

Nếu project thực tế có thể gặp thêm advisors khác, nên test điều kiện pointcut và side effects trên đúng Spring context.

### 7.6. Spring config với class-based proxy

**`AppConfig.java`**

```java
package com.example.binding;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    BillingService billingService() {
        return new BillingService();
    }

    @Bean
    BindingAspect bindingAspect() {
        return new BindingAspect();
    }
}
```

`BillingService` và `BindingAspect` đều được Spring tạo như beans qua `@Bean`. `@EnableAspectJAutoProxy` bật hỗ trợ các `@AspectJ` annotations. Cấu hình `proxyTargetClass=true` chọn CGLIB class proxy để main có thể lấy Spring bean qua `BillingService.class`. Demo không cần `@ComponentScan`.

### 7.7. Main dùng Spring proxy và kiểm chứng output

**`Main.java`**

```java
package com.example.binding;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            BillingService service = context.getBean(BillingService.class);
            BindingAspect aspect = context.getBean(BindingAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("create=" + service.create("A"));

            try {
                service.reject("B");
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("health=" + service.health());
            System.out.println("selfCall=" + service.selfCall("C"));

            System.out.println("events=" + aspect.events());
            System.out.println("groupCalls=" + aspect.groupCount());
        }
    }
}
```

Lệnh chạy tại thư mục project, với Gradle và JDK 17+ đã cài:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper: `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

**Các dòng do chương trình in theo đúng thứ tự** (không tính log bên ngoài của JVM/Spring/Gradle):

```text
proxy=true
create=created:A
caught=rejected:B
health=ok
selfCall=created:C
events=[create:create, reject:reject]
groupCalls=4
```

### 7.8. Vì sao có hai action events nhưng bốn group calls?

| Invocation từ main | Annotation cấp method? | Annotation cấp target class? | `@annotation(action)` chạy? | `@target(group)` chạy? |
| --- | --- | --- | --- | --- |
| `service.create("A")` | `@AuditAction("create")` | `@ServiceGroup("billing")` | Có: `create:create` | Có: +1 |
| `service.reject("B")` | `@AuditAction("reject")` | `@ServiceGroup("billing")` | Có: `reject:reject` | Có: +1 |
| `service.health()` | Không | `@ServiceGroup("billing")` | Không | Có: +1 |
| `service.selfCall("C")` | Không ở method `selfCall` | `@ServiceGroup("billing")` | Không ở entry `selfCall` | Có: +1 |
| `this.create("C")` bên trong target `selfCall` | Có annotation ở method `create` | Class có annotation | **Không** vì self-invocation bypass proxy | **Không**, vì call không qua proxy |
| **Tổng trên lời gọi proxy** | Hai annotated entries | Bốn external entries | **2** | **4** |

Body `create(..)` thực thi hai lần (external `A` và internal `C`) nhưng method advice `@annotation(action)` chỉ chạy **một lần với create** ở external entry. Body `reject` ném lỗi nhưng `@Before` đã chạy trước đó; vì thế `reject:reject` vẫn xuất hiện.

Bảng cho thấy binding phụ thuộc **Spring interception**. Annotation còn tồn tại trên source method ở self-call; điều thiếu là **proxy boundary**, không phải metadata.

## 8. Named @Pointcut có annotation parameter và tái sử dụng

Nếu nhiều advice trong cùng aspect muốn dùng chung selection, có thể khai báo named pointcut có **tham số binding**:

```java
@Aspect
public class SharedAuditAspect {
    @Pointcut(
        value = "execution(public * com.example.binding.BillingService.*(..))"
              + " && @annotation(action)",
        argNames = "action"
    )
    private void annotatedAction(AuditAction action) {}

    @Before(
        value = "annotatedAction(action)",
        argNames = "action"
    )
    public void before(AuditAction action) {
        System.out.println("before=" + action.value());
    }

    @AfterReturning(
        value = "annotatedAction(action)",
        argNames = "action"
    )
    public void afterReturning(AuditAction action) {
        System.out.println("returned=" + action.value());
    }
}
```

Đây là **một biến thể minh họa**, cần imports `@Aspect`, `@Pointcut`, `@Before`, `@AfterReturning` và registration làm Spring bean; **không thêm** vào demo mục 7 nếu muốn giữ stdout đã nêu.

- `annotatedAction(AuditAction action)` là **signature của named pointcut**, không phải business method và body nên rỗng.
- `argNames="action"` trên `@Pointcut` xác định tên tham số được dùng bởi expression.
- `annotatedAction(action)` trong advice expression truyền **binding variable**, không phải gọi method Java để nhận annotation.
- `@Before` chạy trước method; `@AfterReturning` chỉ chạy nếu method kết thúc bình thường. `reject(..)` ném lỗi nên after-returning sẽ không xuất hiện cho case ấy.
- Nếu muốn dùng named pointcut từ **class aspect khác**, cần visibility Java hợp lệ và fully qualified reference; private chỉ dùng trong declaring type.
- Không dùng `@Pointcut` có signature trả `boolean` để hỏi annotation match; signature named pointcut phải trả `void`.

Nên giữ public catalog pointcuts với ý nghĩa ổn định khi nhiều modules cùng tham chiếu. Đối với một aspect duy nhất, private pointcut giúp giảm coupling.

## 9. Bind nhiều annotation trong cùng advice

Một method thuộc annotated target class và tự có method marker có thể bind cả hai:

```java
@Before(
    value = "execution(public * com.example.binding.BillingService.*(..))"
          + " && @target(group)"
          + " && @annotation(action)",
    argNames = "group,action"
)
public void beforeBoth(
        ServiceGroup group, AuditAction action) {
    System.out.println(group.value() + ":" + action.value());
}
```

Đây là **đoạn minh họa**, giả sử nó nằm trong Spring-managed `@Aspect`. Trong project mục 7, nó sẽ chọn `create(..)` và `reject(..)`, nhưng không chọn `health(..)` hay `selfCall(..)` vì hai method sau thiếu `@AuditAction`. Nó có thể in `billing:create` và `billing:reject` nếu được đăng ký; không thêm để tránh đổi stdout.

### Dùng thêm JoinPoint

```java
@Before(
    value = "execution(public * com.example.binding.BillingService.*(..))"
          + " && @target(group) && @annotation(action)",
    argNames = "group,action"
)
public void beforeBoth(
        JoinPoint jp, ServiceGroup group, AuditAction action) {
    System.out.println(
        jp.getSignature().getName()
        + ":" + group.value()
        + ":" + action.value()
    );
}
```

Spring nhận `JoinPoint` đầu tiên theo quy tắc đặc biệt. `argNames` chỉ khai báo các biến expression mà advice cần bind; với signature khác nhau, phải sửa `argNames` tương ứng.

Dùng nhiều annotation bindings hợp lý khi mỗi annotation mang metadata khác nhau. Đừng tạo pointcut quá rộng chỉ để “nhặt” mọi annotation trong hệ thống; giới hạn bằng `execution(...)`/package/type phù hợp.

## 10. Phân biệt reflection lookup và pointcut binding trong Spring

Một cách đọc annotation phổ biến bằng reflection:

```java
Method method = BillingService.class.getMethod("create", String.class);
AuditAction marker = method.getAnnotation(AuditAction.class);
System.out.println(marker.value());
```

Đây là đoạn Java **minh họa**; cần import `java.lang.reflect.Method` và context/try-catch cho checked reflection exceptions. Reflection trực tiếp hữu ích khi bạn **đã biết chính xác class và method**.

Trong Spring AOP, advice có thể nhận metadata thuận tiện hơn:

```java
@Before(
    value = "execution(* com.example.binding.BillingService.create(..))"
          + " && @annotation(action)",
    argNames = "action"
)
public void beforeCreate(AuditAction action) {
    System.out.println(action.value());
}
```

Ưu điểm là Spring/AspectJ matcher liên kết **đúng annotation tham gia join point matching** mà không cần advice tự viết code tra Java `Method`, bridge method hay tự quyết định tìm annotation ở target type nào.

**Không suy rằng binding thay thế mọi nhu cầu reflection:** nếu phải duyệt method overloads, annotations ở generic interface, composed/meta-annotations hoặc thông tin riêng của runtime proxy, có thể cần API `AopUtils.getMostSpecificMethod`, Spring `AnnotatedElementUtils`/`MergedAnnotations` theo bài toán. Những API đó có semantics tìm kiếm khác với pointcut expression; không gọi chúng là “mặc định tương đương `@annotation`”.

## 11. Các bẫy Spring proxy và annotation placement

### 11.1. Annotation chỉ đặt trên interface

```java
public interface PaymentPort {
    @AuditAction("pay")
    String pay(String id);
}

public class PaymentService implements PaymentPort {
    @Override
    public String pay(String id) {
        return "paid:" + id;
    }
}
```

Đây là đoạn minh họa. Annotation Java trên interface method **không tự được kế thừa lên implementation method** bằng Java `@Inherited`. Với Spring AOP, JDK interface proxy và CGLIB class proxy có đường resolve method khác nhau; Spring có các cơ chế annotation search ở một số tính năng nhưng không nên suy mọi `@annotation` expression đều tự tìm annotation trên interface giống mọi infrastructure.

**Khuyến nghị:** khi một audit policy quan trọng gắn vào method implementation, đặt annotation ở nơi đã được Spring aspect matcher kiểm chứng, hoặc thiết kế contract/pointcut theo interface một cách explicit. Viết integration tests riêng cho JDK proxy và class proxy nếu dự án hỗ trợ cả hai.

### 11.2. Annotation ở superclass/subclass

`@target` xét target class, còn `@within` mô tả declared type; method được kế thừa hay override có thể làm việc matching/binding khác mong đợi. `@Inherited` chỉ có ý nghĩa đối với **annotation cấp class** theo quy tắc Java; nó không tự biến inherited method thành method được annotate.

Nếu cần một annotation policy bao phủ mọi subclass, kiểm thử một class có annotation trực tiếp, subclass có/không `@Inherited`, override method và inherited method riêng biệt.

### 11.3. Annotation trên class nhưng dùng @annotation

`@ServiceGroup` gắn class và có `@Target(TYPE)`. Dùng `@annotation(group)` để chọn annotation cấp class **không đúng điểm cắt**; dùng `@target(group)` hoặc `@within(group)` phù hợp. Ngược lại, `@AuditAction` có `@Target(METHOD)` không tự làm `@target(action)` match.

### 11.4. Method annotation nhưng method không intercept được

Một method `final` trong class-based CGLIB proxy không override được; `private` cũng không thể advice bằng cơ chế proxy. Một `@AuditAction` đầy đủ metadata **không sửa** được hạn chế kỹ thuật này. Lời gọi `this.create()` bên trong target vẫn bypass dù method public/non-final.

### 11.5. Bean chưa được Spring quản lý

`@AuditAction` không đăng ký Spring bean; `@Aspect` cũng không tự biến thành `@Component`. Nếu service được tạo bằng `new` hoặc aspect không nằm trong bean registry thì không có interceptor tương ứng.

### 11.6. Không kết luận từ AopUtils.isAopProxy() đơn độc

`AopUtils.isAopProxy(bean)` cho biết bean có Spring proxy. Nó **không chứng minh** advisor cụ thể của `@annotation(action)` match mọi method invocation. Có thể proxy do advisor khác, method không có annotation hoặc caller thực sự dùng raw target.

Dùng **event recorder** hoặc counter như demo để xác minh annotation object đã được truyền vào đúng advice trên đúng call path.

## 12. Khi metadata annotation điều khiển audit, metrics hoặc security

Một annotation có thể mang metadata:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface ActionPolicy {
    String name();
    boolean sensitive() default false;
}
```

Một advice có thể bind `ActionPolicy policy` rồi quyết định **cách quan sát** method:

```java
@Before(
    value = "@annotation(policy)",
    argNames = "policy"
)
public void recordPolicy(ActionPolicy policy) {
    if (!policy.sensitive()) {
        System.out.println("action=" + policy.name());
    }
}
```

Đây là **mã minh họa**, cần imports và registration. Với annotation nói “sensitive”, chính policy **không log dữ liệu nhạy cảm** là hợp lý hơn việc log trọn `JoinPoint.getArgs()`.

Nhưng không xem một custom logging aspect là **ranh giới bảo mật duy nhất**:

- Spring method security cần cấu hình activation riêng và các interceptors chuyên dụng.
- Nếu custom security advice chỉ dựa trên `@annotation` nhưng caller dùng self-invocation, nó có thể bị bỏ qua.
- Pointcut quá rộng cũng có thể advice vào beans ngoài mục tiêu.
- `@Around` có quyền skip `proceed()`/return fallback; với authorization cần contract rõ và security integration tests.
- Annotation metadata không bảo đảm caller đã được xác thực/ủy quyền; đó là logic ở tầng security infrastructure.

Nếu dùng annotations cho tracing/metrics, phải tính cardinality của tags. Ví dụ biến `orderId` thành metric label sẽ tạo cardinality cao; nên tag theo `@AuditAction("create")` và service group ổn định, không theo từng customer/request ID.

## 13. Spring Boot áp dụng thế nào?

Trong Spring Boot có AOP auto-configuration đúng version, `@AspectJ` annotations vẫn hoạt động cùng quy tắc:

- Tạo annotation với `RUNTIME` retention.
- Đánh dấu method hoặc class mục tiêu.
- Tạo `@Aspect` **được Spring quản lý** (thường `@Aspect` + `@Component`) và đặt trong component-scan scope.
- Viết pointcut `execution(...) && @annotation(marker)` (hoặc `@target`/`@within`) và tham số advice đúng type/name.
- Dùng `argNames` khi muốn binding tường minh; `JoinPoint`/`ProceedingJoinPoint` đầu tiên có quy tắc riêng.
- Kiểm tra proxy kind/call path và viết integration tests, đặc biệt khi target class/method final, interface annotation hoặc Kotlin default-final.

Ví dụ dependencies Gradle (lựa chọn theo Boot major với dependency management phù hợp):

```gradle
// Spring Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Spring Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

Hai dòng thuộc **hai lựa chọn khác nhau**, không thêm cả hai vào project bất kể Boot version. `spring.aop.proxy-target-class` ảnh hưởng JDK/CGLIB proxy; việc dùng `@annotation` không loại bỏ giới hạn Spring proxy.

## 14. Kiểm thử Spring annotation binding một cách có ý nghĩa

### 14.1. Test trên Spring ApplicationContext thật

Tối thiểu một integration test phải tạo Spring context chứa:

1. Target service bean;
2. `@Aspect` bean;
3. `@EnableAspectJAutoProxy` hoặc Boot AOP auto-config;
4. Method call qua bean reference do Spring trả về.

Test Java method như `new BindingAspect().beforeAction(..., ...)` chỉ cho biết method advice Java chạy khi được gọi thủ công, **không chứng minh Spring bind annotation theo pointcut**.

### 14.2. Kiểm chứng các trường hợp từ demo

- `create("A")`: có một `AuditAction("create")` event và một `ServiceGroup("billing")` group count.
- `reject("B")`: `@Before` vẫn nhận marker `"reject"` dù method sau đó ném exception.
- `health()`: không có method annotation event, nhưng type annotation event vẫn được tính.
- `selfCall("C")`: group advice cho **entry method `selfCall`** được tính; nested `this.create()` không tạo thêm method event.
- Lời gọi trực tiếp tới `new BillingService().create("X")` (ngoài container) không làm aspect counters thay đổi.
- Khi bỏ annotation `@AuditAction` khỏi một method, advice `@annotation` không còn match method ấy; không nhất thiết bean mất proxy vì còn `@target` advisor.

Một assertion độc lập dùng các classes demo:

```java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    BillingService service = context.getBean(BillingService.class);
    BindingAspect aspect = context.getBean(BindingAspect.class);

    service.create("A");
    try {
        service.reject("B");
    } catch (IllegalStateException expected) {
        // Có lỗi nhưng @Before đã chạy.
    }
    service.health();
    service.selfCall("C");

    if (!aspect.events().equals(
            java.util.List.of("create:create", "reject:reject"))) {
        throw new AssertionError("Incorrect method annotation binding");
    }
    if (aspect.groupCount() != 4) {
        throw new AssertionError("Incorrect target type annotation binding");
    }
}
```

Đây là **biến thể test** khởi tạo context mới, cần import `AnnotationConfigApplicationContext` và đặt trong Java class test/main phù hợp; không thêm vào `Main.java` nếu muốn giữ stdout mục 7.7.

### 14.3. Test binding khi đổi tên parameter

Tạo một test fixture riêng cố ý đặt `@annotation(marker)` nhưng `argNames="action"`. Mục tiêu là khẳng định config không hợp lệ được phát hiện khi Spring dựng advisor. Không đưa một malformed advice vào production context hay demo chính vì nó có thể làm toàn context fail startup.

### 14.4. Kiểm thử proxy types

Nếu project dùng cả JDK dynamic proxies và CGLIB, viết test riêng với interface annotation và implementation annotation; kiểm tra `AopUtils.isJdkDynamicProxy(bean)` hoặc `isCglibProxy(bean)`, sau đó assert **advice invocation**, không chỉ proxy tồn tại. Đảm bảo caller inject bằng interface nếu bean là JDK proxy.

## 15. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Kiểm tra |
| --- | --- | --- |
| Khởi tạo Spring context lỗi khi bind annotation | `argNames` không khớp tên biến trong expression hoặc tham số advice | Đồng nhất `@annotation(marker)`, `argNames="marker"`, `AuditAction marker`. |
| Advice chạy nhưng không đọc được metadata mong muốn | Dùng dạng FQCN presence-only hoặc dùng sai annotation type | Dùng binding form `@annotation(marker)` và đúng parameter type. |
| Annotation ở class, `@annotation(marker)` không match | `@annotation` tìm method annotation, không phải type | Dùng `@target` hoặc `@within` thích hợp. |
| Annotation ở method, `@target(marker)` không match | `@target` tìm annotation trên target type | Dùng `@annotation`. |
| Annotation chỉ có `SOURCE` retention | Runtime không có annotation object để match/bind | Chọn `RUNTIME` cho marker của bài này. |
| Annotation chỉ trên interface nhưng class implementation khác | Java annotations không tự kế thừa từ interface theo cách mặc định | Kiểm thử actual Spring method resolution/JDK-CGLIB và đặt policy đúng nơi. |
| Aspect không được gọi | Aspect chưa là bean, AOP chưa bật, target ngoài container | Kiểm tra `@Bean`/`@Component`, `@EnableAspectJAutoProxy` và component scan. |
| Có proxy nhưng thiếu event ở nested call | `this.inner()` bypass proxy | Tách sang injected collaborator hoặc advice outer entry. |
| @Before method args khớp sai | `args(arg)` bind argument runtime nhưng type/name không tương thích | Xác nhận number/type of args và `argNames`. |
| Annotation không bind vào `JoinPoint` | Nhầm `JoinPoint` với binding variable | `JoinPoint` đầu tiên, marker được khai báo parameter riêng. |
| Code `@Around` có annotation nhưng target không chạy | Quên `pjp.proceed()` hoặc short-circuit | Gọi `proceed()` theo contract, test side effects. |
| Method `final` dưới CGLIB không được advice | Class proxy không override được method | Chọn proxy strategy/entry method phù hợp. |
| Method có annotation nhưng chỉ test `new Service()` | Không có Spring proxy | Test bằng Spring context và injected proxy. |
| Advice log sai mức nhạy cảm | Metadata dùng để log raw args/result không được kiểm soát | Whitelist/redact, giới hạn cardinality và áp dụng privacy policy. |

## 16. Quy trình áp dụng vào một dự án Spring thực

### Bước 1 — Định nghĩa metadata thực sự cần

Không thêm annotation chỉ để “cho đẹp”. Chọn thông tin ổn định ở compile time: operation name, audit category hoặc service family. Nếu metadata biến đổi theo từng request, nó nên đến từ argument/context chứ không phải một annotation constant.

### Bước 2 — Chọn đúng vị trí annotation

Method operation → `@Target(METHOD)` và `@annotation`; service target type → `@Target(TYPE)` và `@target`; type khai báo execution → `@within`; annotation trên runtime argument type → `@args`.

### Bước 3 — Bảo đảm RUNTIME retention

Khai báo `@Retention(RUNTIME)`, có tên method/class khớp nơi gắn marker. Kiểm tra annotation có thật trên concrete target hoặc method cần intercept; không mặc định kế thừa interface.

### Bước 4 — Bật Spring AOP đúng context

Aspect phải là Spring bean, target là Spring bean, bật `@EnableAspectJAutoProxy`/Boot AOP auto-configuration và có dependencies tương thích. Với multi-context applications, AOP support có phạm vi context; không tự giả định advisor ở root tự áp lên mọi child context.

### Bước 5 — Viết pointcut có scope

Kết hợp `execution(public * com.example.orders..*Service.*(..))` với binding designator. Tránh chỉ viết `@annotation(marker)` trên toàn application nếu nó vô tình chọn quá rộng hoặc tạo proxy không cần thiết.

### Bước 6 — Đặt argNames và chữ ký advice chính xác

Tên biến pointcut phải khớp tham số advice; `JoinPoint` đầu tiên được binding riêng, còn các biến khác cần có Java types đúng. Nếu có nhiều binding variables, khai báo `argNames` theo đúng thứ tự tham số binding.

### Bước 7 — Test qua Spring proxy

Gọi annotated method từ context, unannotated method, method ném lỗi, call path self-invocation, rồi đo events/metadata; bảo đảm annotation object nhận được đúng giá trị.

### Bước 8 — Rà soát side effects và vận hành

Không lưu request-sensitive mutable state trong singleton aspect; không log secrets; không dùng annotation marker để thay thế authorization; nếu advice có thể ném exception hoặc thay outcome (`@Around`), kiểm thử contract thật.

## 17. Checklist cuối bài

- [ ] Chọn chính xác `@annotation` (method), `@target` (target class), `@within` (declaring type) hay `@args` (runtime argument class)?
- [ ] Annotation có `@Target` phù hợp và `@Retention(RUNTIME)`?
- [ ] Biết khi nào dùng `@annotation(FQCN)` để match và `@annotation(marker)` để bind annotation instance?
- [ ] Tham số advice có kiểu annotation đúng và tên `marker` khớp `argNames`/pointcut?
- [ ] Nếu dùng `JoinPoint` hoặc `ProceedingJoinPoint`, nó là tham số đầu và không cần khai báo tên trong `argNames`?
- [ ] Aspect có `@Aspect` **và** là Spring-managed bean?
- [ ] Target là Spring-managed bean, hạ tầng AOP bật đúng context và AspectJ dependency có mặt?
- [ ] Pointcut expression được giới hạn bằng package/type/method contract phù hợp?
- [ ] Caller đi qua Spring proxy, không `new`/self-invocation, method proxy intercept được?
- [ ] Nếu annotation đặt ở interface/superclass, đã test với đúng JDK/CGLIB proxy và inheritance semantics?
- [ ] Annotation data được sử dụng an toàn, không log secret hoặc high-cardinality request IDs?
- [ ] Integration test assert metadata binding/events, không chỉ `AopUtils.isAopProxy(bean)`?
- [ ] Nếu bind thêm `args(...)`, tên, vị trí và Java types của arguments phù hợp?
- [ ] Nếu dùng `@Around`, có `proceed()` đúng semantics và giữ contract return/exception?

**Ghi nhớ:** Với Spring AOP, một annotation trên method/class có thể trở thành **giá trị tham số của advice** thông qua binding form như `@annotation(action)` hoặc `@target(group)`. Spring nối **tên biến trong expression**, `argNames` và **kiểu tham số Java**; advice nhận được annotation object để đọc metadata. Nhưng metadata chỉ được truyền khi có **Spring-managed aspect + Spring target bean + proxy invocation + pointcut match**. Đó là ranh giới quan trọng giữa annotation nằm trong source và advice thực sự chạy.

## Tài liệu Spring tham khảo

- [Spring Framework 6.2 — Declaring Advice: Passing Parameters to Advice và argNames](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Declaring a Pointcut: @annotation, @target, @within, @args](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Maven Central — AspectJ Weaver](https://central.sonatype.com/artifact/org.aspectj/aspectjweaver)
