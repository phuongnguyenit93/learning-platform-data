# getThis() và getTarget(): phân biệt Spring AOP proxy với đối tượng đích

## 1. Câu hỏi cốt lõi trong một @Aspect

Trong một Spring `@Aspect`, khi một method được gọi qua proxy, ta có thể đang nhìn thấy **hai đối tượng Java khác nhau**:

1. **Spring AOP proxy**: object mà client lấy từ `ApplicationContext` hoặc được inject vào một bean khác. Nó nhận lời gọi, tìm các advisor/interceptor phù hợp và điều phối execution.
2. **Target object**: object thật chứa logic nghiệp vụ, được proxy chuyển lời gọi đến sau khi chạy các advice cần thiết.

Spring cung cấp hai API trên `JoinPoint`/`ProceedingJoinPoint`:

- **`joinPoint.getThis()` trả về Spring AOP proxy hiện hành.**
- **`joinPoint.getTarget()` trả về Spring AOP target hiện hành**, tức đối tượng nằm phía sau proxy (trong trường hợp đặc biệt proxy không có target, kết quả có thể là `null`).

Đây không chỉ là hai cách lấy tên lớp. Chúng có **identity, runtime class, interface exposure và đường gọi method khác nhau**. Chọn nhầm có thể khiến logging sai kiểu, code ép kiểu thất bại, lời gọi bỏ qua aspect hoặc thậm chí vô tình gọi advice đệ quy.

Ví dụ hình dung:

```text
ApplicationContext
      |
      v
 Spring AOP proxy  <-------------  joinPoint.getThis()
      |
      |  Advisor A -> Advisor B -> ...
      |
      v
 Business target   <-------------  joinPoint.getTarget()
      |
      v
 Method implementation
```

**Phạm vi bài:** `getThis()`/`getTarget()` và ý nghĩa **trong Spring AOP dựa trên proxy**, đặc biệt khi dùng `@Aspect` với Spring Framework. Ta không mở rộng sang semantics của AspectJ compiler/weaver độc lập, vì chính việc Spring dùng proxy mới tạo ra khác biệt quan trọng giữa hai object này.

### Sau bài học, bạn sẽ

- Hiểu `this`, `target` và các object mà Spring AOP dùng khi chặn một method.
- Phân biệt `getThis()`/`getTarget()` với Java keyword `this` trong target và trong aspect.
- Dự đoán kết quả với JDK dynamic proxy so với class-based CGLIB proxy.
- Hiểu `this(TypePattern)` và `target(TypePattern)` trong Spring pointcut.
- Biết vì sao **không dùng `getTarget()` rồi gọi method để “proceed”**, và vì sao gọi qua `getThis()` trong advice có nguy cơ đệ quy.
- Tự chạy ví dụ Java 17/Spring Framework với hai context riêng và kết quả quan sát được.
- Chẩn đoán self-invocation, proxy casting, targetless proxy và target source động mà không suy luận sai về identity.

## 2. Cơ chế Spring AOP: client gọi proxy, proxy gọi target

Một Spring bean có thể được tạo trước dưới dạng target, rồi `BeanPostProcessor` thuộc hạ tầng auto-proxy creator quyết định có cần trả một proxy thay cho target khi bean được công bố qua container hay không.

Trong trường hợp một bean cần advice:

```text
Caller
   |
   | injected JobApi bean
   v
Proxy [identity P]
   |
   | interceptor chain
   v
Target JobService [identity T]
   |
   | thực thi perform("A")
   v
Return
```

Thông thường, `P !== T` xét theo **reference identity (`==` trong Java)**. Proxy đại diện cho target trước caller nhưng không phải là chính target. Hai đối tượng có thể có cách biểu diễn `equals`/`hashCode` đặc biệt; khi học ranh giới AOP, dùng `==` thay vì `equals` để so sánh identity.

### Vai trò khác nhau

| Thuộc tính | `getThis()` | `getTarget()` |
| --- | --- | --- |
| Trả về gì trong Spring AOP? | Proxy hiện hành | Target hiện hành phía sau proxy |
| Gọi method qua reference này | Có thể đi qua Spring AOP advisor chain | Gọi trực tiếp trên target, bỏ qua các advisor của proxy đó |
| Runtime class thường gặp | JDK-generated proxy hoặc CGLIB subclass | Implementation class thực |
| Có giống `context.getBean(...)`? | Trong trường hợp Spring proxy thông thường, là reference proxy mà client dùng | Thường không, khi bean được proxy |
| Có thể bằng `null`? | Không đối với `MethodInvocationProceedingJoinPoint` của Spring AOP | Có thể khi proxy không có target object |
| Có luôn được ép thành implementation class? | **Không** đối với JDK proxy | Thường là instance target implementation nếu target tồn tại |
| Có luôn là một singleton cố định mãi mãi? | Không nên suy luận ngoài cấu hình bean/proxy cụ thể | Không: target source/scopes có thể thay target theo invocation |
| Dùng để tiếp tục current `@Around`? | Không phải API tiếp tục chain | Không phải API tiếp tục chain |
| API đúng để tiếp tục `@Around` | **`ProceedingJoinPoint.proceed()`** | **`ProceedingJoinPoint.proceed()`** |

Spring chính thức ghi rõ `getThis()` trả proxy, `getTarget()` trả target là POJO phía sau proxy, không mang các advice của proxy trên reference đó. Với `@Around`, muốn tiếp tục invocation hiện tại thì **`proceed()` mới đúng**.

## 3. getThis() không đồng nghĩa Java this của target hoặc aspect

Có ba ngữ cảnh `this` dễ nhầm:

### 3.1. this trong @Aspect class

```java
@Aspect
public class InspectAspect {

    @Around("execution(* com.example.service..*.*(..))")
    public Object inspect(ProceedingJoinPoint pjp) throws Throwable {
        Object aspectInstance = this;
        Object proxy = pjp.getThis();
        Object target = pjp.getTarget();

        System.out.println(aspectInstance == proxy); // thường false
        System.out.println(proxy == target);         // thường false
        return pjp.proceed();
    }
}
```

Đây là snippet minh họa; cần các imports, Spring bean registration và target khớp. `this` trong source của `InspectAspect` là **aspect instance**. `pjp.getThis()` lại là **proxy của Spring bean được advice**. Hai đối tượng này phục vụ hai vai trò hoàn toàn khác nhau.

### 3.2. this trong target implementation

```java
public class JobService {
    public void outer() {
        this.inner();
    }

    public void inner() {
        System.out.println("inner");
    }
}
```

Khi `outer()` đã được proxy điều phối tới target, `this` bên trong `JobService.outer()` trỏ vào **target object**. Lời gọi `this.inner()` **không quay trở lại Spring proxy**, nên advice dành riêng cho `inner()` không tự chạy.

### 3.3. this trong Spring pointcut expression

```java
@Pointcut("this(com.example.api.JobApi)")
public void proxyImplementsJobApi() {}
```

Designator `this(TypePattern)` xét **proxy object** trong Spring AOP, không xét biến `this` của source Java trong aspect. `target(TypePattern)` lại xét **target object**. Phần 6 đi sâu vào sự khác biệt này.

## 4. JDK dynamic proxy: proxy và implementation có kiểu khác nhau

Khi target triển khai một interface phù hợp và Spring không bị buộc dùng class-based proxy, Spring AOP thường tạo **JDK dynamic proxy**.

Ví dụ:

```java
package demo.identity;

public interface JobApi {
    String perform(String id);
}
```

```java
package demo.identity;

public class JobService implements JobApi {
    @Override
    public String perform(String id) {
        return "done:" + id;
    }
}
```

Bean được tiêm qua `JobApi`. Với JDK proxy:
- `getThis() instanceof JobApi` là `true`.
- `getThis() instanceof JobService` là `false`: JDK proxy triển khai interface nhưng **không phải subclass của `JobService`**.
- `getTarget() instanceof JobService` là `true` nếu target là `JobService`.
- `getThis() == getTarget()` thường là `false`.
- Dù proxy không phải instance của implementation, pointcut Spring vẫn có thể match execution của target method phù hợp.

Một lỗi thực tế:

```java
JobService service = (JobService) context.getBean(JobApi.class);
```

Nếu bean thực tế là JDK proxy, cast trên có thể ném `ClassCastException`. Đó không phải lỗi của `getTarget()`, mà là do **client đang ép kiểu proxy thành implementation**. Cách sử dụng thông thường là inject/get bean theo **interface `JobApi`** hoặc xem lại lý do cần proxy theo class.

### JDK proxy chỉ expose method qua interface phù hợp

Nếu implementation có thêm method `internalOnly()` không được khai báo trên interface proxy, client không thể gọi method đó qua `JobApi` reference. Không dùng `getTarget()` làm đường vòng để gọi method ngoài interface mà vẫn mong Spring advice chạy. Nếu nghiệp vụ cần method được advice, thiết kế service contract và proxy boundary cho phù hợp.

## 5. CGLIB class-based proxy: instanceof giống nhưng identity vẫn khác

Nếu target không có interface, hoặc cấu hình `proxyTargetClass=true` yêu cầu class proxy, Spring thường dùng **CGLIB** tạo subclass của implementation.

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
```

Đây là snippet cấu hình, không phải ứng dụng độc lập. Khi `JobService` được Spring AOP class-proxy:
- `getThis() instanceof JobApi` là `true` nếu implementation có interface đó.
- `getThis() instanceof JobService` cũng là `true` vì CGLIB proxy là subclass.
- `getTarget() instanceof JobService` là `true`.
- **`getThis() == getTarget()` vẫn thường là `false`**: quan hệ kế thừa không làm proxy và target thành cùng object.
- `getThis().getClass()` có thể trả một CGLIB-generated class; `getTarget().getClass()` trả implementation class.

Do `getThis() instanceof JobService` là true với CGLIB, người học dễ kết luận `getThis()` và `getTarget()` là một. Kết luận này sai: **`instanceof` kiểm tra quan hệ kiểu, còn `==` kiểm tra identity**.

### Giới hạn class-based proxy

CGLIB phải tạo subclass để override method. Nó không thể advice bằng override đối với:
- class `final`;
- method `final`;
- method `private`;
- một số method không visible để subclass override.

Ngoài ra, self-invocation từ target vẫn bypass Spring AOP dù proxy là CGLIB. Đổi JDK proxy thành CGLIB **không phải cách sửa** vấn đề `this.inner()`.

## 6. this(TypePattern) so với target(TypePattern) trong Spring pointcut

Spring Framework nêu rõ sự khác biệt giữa **proxy** và **target**:

- `this(TypePattern)`: match khi **proxy** là instance của type được chỉ định.
- `target(TypePattern)`: match khi **target object** là instance của type được chỉ định.

### 6.1. Với interface

```java
@Pointcut("this(demo.identity.JobApi)")
public void proxyIsJobApi() {}

@Pointcut("target(demo.identity.JobApi)")
public void targetIsJobApi() {}
```

Khi target `JobService implements JobApi` và proxy triển khai interface `JobApi`, cả hai thường match. Không nên dùng ví dụ này để chứng minh chúng tương đương **trong mọi cấu hình**.

### 6.2. Với implementation class

```java
@Pointcut("this(demo.identity.JobService)")
public void proxyIsJobService() {}

@Pointcut("target(demo.identity.JobService)")
public void targetIsJobService() {}
```

Với **JDK proxy**:
- `this(JobService)` thường không match vì proxy không subclass `JobService`.
- `target(JobService)` có thể match vì target chính là `JobService`.

Với **CGLIB proxy**:
- Cả `this(JobService)` và `target(JobService)` thường match vì proxy là subclass và target là instance implementation.

### 6.3. Ma trận nhanh

Giả sử target là `JobService implements JobApi` và có Spring AOP proxy như mô tả:

| Câu hỏi/điều kiện | JDK proxy | CGLIB proxy |
| --- | --- | --- |
| `getThis() instanceof JobApi` | `true` | `true` |
| `getTarget() instanceof JobApi` | `true` | `true` |
| `getThis() instanceof JobService` | `false` | `true` |
| `getTarget() instanceof JobService` | `true` | `true` |
| `getThis() == getTarget()` | `false` | `false` |
| `this(JobService)` | Không match | Có thể match |
| `target(JobService)` | Có thể match | Có thể match |
| `this(JobApi)` | Có thể match | Có thể match |
| `target(JobApi)` | Có thể match | Có thể match |

“Có thể match” ở các dòng pointcut còn phụ thuộc việc method thực sự được Spring AOP intercept, type pattern hợp lệ và bean/advisor configuration phù hợp. Ma trận mô tả **quan hệ type của hai object**, không tự khẳng định mọi lời gọi trong Java đều có advice.

### 6.4. Khi chọn type pattern, tránh dùng nhầm @target

`target(SomeType)` kiểm tra quan hệ kiểu của target. Trong khi đó:
- `@target(MyAnnotation)` xét **annotation** trên runtime target type.
- `@within(MyAnnotation)` xét annotation theo declaring type của method execution.
- `within(PackageOrTypePattern)` giới hạn theo type/package khai báo execution.
- `@annotation(MyAnnotation)` xét method annotation.

Các designator này giải quyết yêu cầu khác nhau. Nếu chỉ muốn log loại Spring bean được advice, dùng `pjp.getTarget()` để quan sát object; nếu muốn ràng buộc advisor theo target type, dùng `target(...)` theo semantics của Spring pointcut.

## 7. Ví dụ chạy đầy đủ: so sánh JDK proxy và CGLIB ở hai context

Ví dụ Spring Framework thuần dưới đây dùng **Java 17**, **Spring Framework 6.1.14**, **AspectJ Weaver 1.9.22.1** và Gradle. Ta tạo hai `ApplicationContext` tách biệt để không bị một cấu hình `proxyTargetClass=true` trong context CGLIB ảnh hưởng context JDK.

Mục tiêu:
- In loại proxy mà Spring tạo (qua `AopUtils`, không in tên generated class ngẫu nhiên).
- Trong chính `@Around`, so sánh `pjp.getThis()` và `pjp.getTarget()`.
- Kiểm tra `instanceof JobService` của proxy/target.
- Chạy một method gọi từ bên ngoài và một method tự gọi method khác bên trong target.
- Quan sát self-invocation không tạo advice lồng thêm.

### 7.1. Cấu trúc project

```text
spring-aop-proxy-identity/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/identity/
    ├── JobApi.java
    ├── JobService.java
    ├── InspectAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Cấu hình Gradle

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-proxy-identity'
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
    mainClass = 'demo.identity.DemoApplication'
}
```

`spring-context` cung cấp `AnnotationConfigApplicationContext`; `spring-aop` chứa AOP proxy infrastructure, `AopUtils` và interceptor integration; `aspectjweaver` giúp Spring phân tích `@Aspect` pointcut expression.

### 7.3. Public interface

Tệp `src/main/java/demo/identity/JobApi.java`:

```java
package demo.identity;

public interface JobApi {
    String perform(String task);
    void runInside();
}
```

Cả `perform` và `runInside` được khai báo trên interface để **JDK dynamic proxy** có thể expose cả hai method. Trong CGLIB case, proxy còn là subclass của implementation.

### 7.4. Target implementation

Tệp `src/main/java/demo/identity/JobService.java`:

```java
package demo.identity;

public class JobService implements JobApi {

    @Override
    public String perform(String task) {
        System.out.println("target:perform:" + task);
        return "done:" + task;
    }

    @Override
    public void runInside() {
        System.out.println("target:runInside");
        perform("inside");
    }
}
```

`perform("inside")` là lời gọi nội bộ trên target (`this.perform(...)`), không phải một lời gọi quay lại Spring proxy. Vì vậy, dù pointcut có thể khớp method `perform`, lời gọi này không phát sinh một `@Around` lần nữa.

### 7.5. Aspect quan sát proxy và target bằng ProceedingJoinPoint

Tệp `src/main/java/demo/identity/InspectAspect.java`:

```java
package demo.identity;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.aop.support.AopUtils;

@Aspect
public class InspectAspect {

    @Around(
        "execution(public * demo.identity..*.perform(..))"
        + " || execution(public * demo.identity..*.runInside(..))"
    )
    public Object inspect(ProceedingJoinPoint pjp) throws Throwable {
        Object proxy = pjp.getThis();
        Object target = pjp.getTarget();

        System.out.println("aspect:" + pjp.getSignature().getName());
        System.out.println("proxyKind="
            + (AopUtils.isJdkDynamicProxy(proxy) ? "JDK" : "CGLIB"));
        System.out.println("sameObject=" + (proxy == target));
        System.out.println("proxyIsJobService="
            + (proxy instanceof JobService));
        System.out.println("targetIsJobService="
            + (target instanceof JobService));
        System.out.println("targetAopProxy="
            + AopUtils.isAopProxy(target));

        return pjp.proceed();
    }
}
```

**Giải thích kỹ:**
- `pjp.getThis()` là proxy. `AopUtils.isJdkDynamicProxy(proxy)` giúp in nhãn **JDK** hoặc **CGLIB** ổn định trong hai cấu hình thử nghiệm; không lấy string từ tên generated class.
- `pjp.getTarget()` là `JobService` target trong ví dụ, không phải một proxy lồng khác.
- `sameObject=false` cho biết proxy và target không có cùng Java reference identity.
- `proxyIsJobService` khác nhau giữa JDK và CGLIB: JDK proxy không kế thừa implementation; CGLIB subclass có quan hệ `instanceof`.
- `targetIsJobService=true` trong cả hai vì Spring dùng `JobService` làm target.
- `targetAopProxy=false` vì target là plain object của ví dụ, không phải Spring AOP proxy; không lấy đó làm quy luật tuyệt đối cho mọi custom nested-proxy setup.
- `return pjp.proceed();` mới **tiếp tục invocation hiện hành**. Ta không gọi trực tiếp `((JobService) target).perform(...)` và không dùng `((JobApi) proxy).perform(...)` để thay `proceed()`.

Pointcut dùng `execution(public * demo.identity..*.perform(..))` hoặc `runInside(..)`; chỉ các method có tên tương ứng và package/type phù hợp mới được advice. Hai method trên cùng target đều được match khi client gọi qua proxy.

### 7.6. Hai context cấu hình hai kiểu proxy

Tệp `src/main/java/demo/identity/AppConfig.java`:

```java
package demo.identity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class AppConfig {

    @Configuration(proxyBeanMethods = false)
    public static class CommonBeans {

        @Bean
        public JobApi jobService() {
            return new JobService();
        }

        @Bean
        public InspectAspect inspectAspect() {
            return new InspectAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CommonBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class JdkConfig {
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CommonBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class CglibConfig {
    }
}
```

- `CommonBeans` đăng ký `JobService` qua kiểu interface `JobApi` và đăng ký aspect bằng `@Bean`. `@Aspect` một mình không khiến class được Spring tạo thành bean.
- `JdkConfig` bật Spring AOP với `proxyTargetClass=false`. Vì target triển khai `JobApi`, trường hợp thông thường này dùng JDK dynamic proxy.
- `CglibConfig` ép class-based proxy bằng `proxyTargetClass=true`.
- Hai context được tạo **riêng** chứ không import đồng thời hai configs vào một context. Nếu nhiều hạ tầng Spring cùng request class-based proxy trong một context, thiết lập `true` có thể chi phối lựa chọn chung.
- `@Bean` khai báo return type `JobApi` vẫn cho Spring giữ concrete target `JobService` để tạo proxy theo lớp khi cần. Client trong demo lấy bean theo `JobApi.class`, hợp lệ ở cả hai context.

### 7.7. Main và lệnh chạy

Tệp `src/main/java/demo/identity/DemoApplication.java`:

```java
package demo.identity;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        run("JDK", AppConfig.JdkConfig.class);
        run("CGLIB", AppConfig.CglibConfig.class);
    }

    private static void run(String label, Class<?> config) {
        System.out.println("==" + label + "==");

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(config)) {

            JobApi bean = context.getBean(JobApi.class);
            System.out.println("isAopProxy=" + AopUtils.isAopProxy(bean));
            System.out.println("result=" + bean.perform("outside"));
            bean.runInside();
        }
    }
}
```

Chạy tại thư mục chứa `build.gradle`:

```bash
gradle run
```

Nếu đã có Gradle Wrapper, chạy `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

### 7.8. Stdout từ Java code

```text
==JDK==
isAopProxy=true
aspect:perform
proxyKind=JDK
sameObject=false
proxyIsJobService=false
targetIsJobService=true
targetAopProxy=false
target:perform:outside
result=done:outside
aspect:runInside
proxyKind=JDK
sameObject=false
proxyIsJobService=false
targetIsJobService=true
targetAopProxy=false
target:runInside
target:perform:inside
==CGLIB==
isAopProxy=true
aspect:perform
proxyKind=CGLIB
sameObject=false
proxyIsJobService=true
targetIsJobService=true
targetAopProxy=false
target:perform:outside
result=done:outside
aspect:runInside
proxyKind=CGLIB
sameObject=false
proxyIsJobService=true
targetIsJobService=true
targetAopProxy=false
target:runInside
target:perform:inside
```

Đây là các dòng do code tự in; không tính Gradle, logging hệ thống hay banner môi trường.

### 7.9. Giải thích từng kết quả

**Ở nhánh JDK:**

`isAopProxy=true` chứng minh reference từ Spring là proxy. `proxyKind=JDK` cho thấy proxy triển khai interface chứ không subclass `JobService`. Vì vậy `proxyIsJobService=false` nhưng `targetIsJobService=true`. Spring vẫn chạy advice rồi chuyển đến `JobService.perform("outside")`.

**Ở nhánh CGLIB:**

`proxyKind=CGLIB` cho biết proxy là class-based. `proxyIsJobService=true` nhờ kế thừa, nhưng `sameObject=false`: proxy và target vẫn là hai object khác nhau. Đây là điểm cần nhớ khi kiểm tra code bằng `instanceof`.

**Ở cả hai:**

`aspect:runInside` xuất hiện vì caller gọi `bean.runInside()` qua Spring proxy. Sau đó có `target:runInside` và `target:perform:inside` nhưng **không có `aspect:perform` thứ hai**: lời gọi `perform("inside")` phát sinh trong target nên không đi qua proxy.

Nếu chỉ kiểm tra target method logs mà không xem advice logs, bạn có thể tưởng `perform` đã được advice hai lần. Output tách riêng hai loại log để chứng minh thực tế không phải vậy.

## 8. Không dùng getTarget() để tiếp tục method trong @Around

Một lỗi nghiêm trọng là dùng target reference để tự gọi lại method:

```java
@Around("execution(* demo.identity.JobService.perform(..))")
public Object broken(ProceedingJoinPoint pjp) {
    JobService target = (JobService) pjp.getTarget();
    return target.perform("manually");
}
```

Đây là **anti-pattern minh họa**, không đặt vào project chạy. Method này bỏ qua `pjp.proceed()` và gọi trực tiếp `target.perform`. Vì vậy:
- Invocation từ caller đã tới advice nhưng **không tiếp tục những interceptors nằm phía trong**.
- Nếu có transaction, cache, security, tracing hoặc advisor khác phía trong, chúng có thể bị bỏ qua.
- Nó tự thay argument bằng `"manually"`, có thể vi phạm method contract và business expectations.
- Nếu có target source đặc biệt hoặc targetless proxy, cast hoặc dereference có thể thất bại.

Muốn giữ nguyên flow:

```java
return pjp.proceed();
```

Muốn thay argument có chủ đích:

```java
Object[] modified = pjp.getArgs().clone();
modified[0] = "normalized";
return pjp.proceed(modified);
```

Với Spring AOP, `proceed(Object[])` nhận bộ method arguments phù hợp số lượng/thứ tự/kiểu; không phải lý do để gọi trực tiếp target reflection. Đây là snippet minh họa bên trong `@Around` có method nhận ít nhất một String parameter.

## 9. Cẩn thận khi gọi lại qua getThis()

Spring Javadoc lưu ý: nếu **muốn một lời gọi nhận advice**, gọi qua proxy chứ không gọi trực tiếp target. Tuy nhiên, **không có nghĩa lời khuyên đúng là thay `proceed()` bằng gọi method trên `pjp.getThis()` ngay trong chính @Around advice**.

Ví dụ nguy hiểm:

```java
@Around("execution(* demo.identity.JobService.perform(..))")
public Object recursive(ProceedingJoinPoint pjp) {
    JobApi proxy = (JobApi) pjp.getThis();
    return proxy.perform("again");
}
```

Lời gọi `proxy.perform("again")` tạo một invocation **mới** đi qua cùng proxy. Nếu pointcut vẫn match, advice lại chạy, lại gọi proxy và có thể tạo đệ quy không dừng, cuối cùng `StackOverflowError`.

`pjp.proceed()` là API tiếp tục **lời gọi hiện tại**; gọi qua proxy chỉ thích hợp khi bạn thực sự cần tạo **một lời gọi mới** từ nơi khác và đã thiết kế tránh đệ quy/circular aspect behavior.

### getThis() có cần exposeProxy=true không?

**Không.** Trong method `@Aspect` đang chạy qua Spring AOP, `pjp.getThis()` cung cấp current proxy như một phần `JoinPoint`.

Cơ chế khác là:

```java
Object proxy = AopContext.currentProxy();
```

`AopContext.currentProxy()` truy cập proxy từ thread-local context và thường cần bật `exposeProxy=true`; nó gây coupling rõ ràng với Spring AOP và không được khuyến nghị như cách thiết kế business logic thông thường. **Đừng nhầm điều kiện của `AopContext.currentProxy()` với `pjp.getThis()`.**

## 10. getTarget() có thể null hoặc thay đổi theo invocation

### 10.1. Targetless proxy

Spring AOP Javadoc cho phép `getTarget() == null` nếu không có target instance. Đây không phải trường hợp service target trong demo, nhưng quan trọng khi có custom proxy/`TargetSource` không cung cấp target.

Vì thế, trong logging/library infrastructure tránh code:

```java
String targetClass = pjp.getTarget().getClass().getName();
```

nếu bạn không bảo đảm target tồn tại. Một cách chẩn đoán an toàn hơn:

```java
Object target = pjp.getTarget();
String name = target != null
    ? target.getClass().getName()
    : "<no target>";
```

### 10.2. Scoped target và dynamic TargetSource

Với những cấu hình proxy đặc biệt như scoped proxy hoặc custom `TargetSource`, một proxy có thể đại diện cho **những target instances khác nhau tại những thời điểm khác nhau**. Ví dụ request-scoped target có thể khác giữa requests, dù dependency inject vào singleton service là một proxy ổn định.

Do đó:
- Không cache `pjp.getTarget()` từ invocation đầu rồi dùng như target vĩnh viễn.
- Không giả định `getTarget()` luôn trả cùng identity trên mọi lời gọi.
- Không tự biến target reference thành một Spring bean mới được inject vào nơi khác.
- Cẩn thận với object lifecycle/scopes: giữ raw target có thể kéo dài reference ngoài phạm vi vốn được dự tính.

**Trong demo singleton thông thường**, target là `JobService` ổn định, nhưng đây là đặc điểm cấu hình demo, không phải hợp đồng chung của mọi Spring proxy.

### 10.3. Nested/custom proxies

Trong hệ thống tự thêm `ProxyFactory`, custom `BeanPostProcessor` hoặc proxy layers từ library khác, object nằm ngay sau proxy ngoài có thể **bản thân là một proxy khác**. Khi đó một lần `getTarget()` không chắc trả “business POJO cuối cùng”.

`AopUtils.isAopProxy(target)` hoặc `Advised` có thể giúp phân tích cấu trúc, nhưng cần tôn trọng target source lifecycle; không tự liên tục unwrap/cast trong business advice. Với mục tiêu ghi log type thông thường, có thể dùng các utility Spring để xác định target class, song **đọc type metadata không tương đương lấy target object rồi gọi trực tiếp**.

## 11. Quan sát class, bean name và method signature đúng cách

### 11.1. Class của proxy không phải class nghiệp vụ

`pjp.getThis().getClass().getName()` có thể tạo output kiểu generated class của JDK hoặc CGLIB, thay đổi theo version và runtime. Không dùng các substring từ tên class generated làm điều kiện nghiệp vụ.

Để kiểm tra loại proxy:

```java
Object proxy = pjp.getThis();

boolean jdk = AopUtils.isJdkDynamicProxy(proxy);
boolean cglib = AopUtils.isCglibProxy(proxy);
Class<?> targetClass = AopUtils.getTargetClass(proxy);
```

Đây là snippet trong advice cần import `org.springframework.aop.support.AopUtils`. `getTargetClass` trả **type metadata** từ proxy khi có thể, không phải object business target; `pjp.getTarget()` mới trả target object tại join point.

### 11.2. getSignature() để biết method

```java
String methodName = pjp.getSignature().getName();
```

Khi cần kiểu trả về, parameter types hoặc method annotation, có thể dùng:

```java
import org.aspectj.lang.reflect.MethodSignature;

MethodSignature sig = (MethodSignature) pjp.getSignature();
Class<?> returnType = sig.getReturnType();
Class<?>[] parameterTypes = sig.getParameterTypes();
```

Đây là snippets trong Spring `@Around` method-execution advice. Với JDK proxy, method được mô tả có thể gắn với interface declaration trong khi implementation method có metadata khác. Khi đọc annotation ở implementation, cần resolve method cụ thể trong target type đúng bằng utility phù hợp và có tests.

### 11.3. getArgs() không phải getTarget()

`pjp.getArgs()` trả các **actual arguments** của invocation, không trả bean target. Trong ví dụ `perform("outside")`, `getArgs()[0]` là chuỗi `"outside"`. Không nhầm “đối tượng đích” của Spring proxy với “object đối số” truyền vào method.

### 11.4. getThis() cũng không phải Spring bean name

`getThis()` trả proxy reference, không trả bean name. Một target class có thể được đăng ký dưới nhiều Spring bean definitions hoặc với aliases. Nếu nghiệp vụ cần phân loại theo tên Spring bean, cân nhắc `bean(namePattern)` pointcut của Spring AOP hoặc API bean metadata phù hợp; không đoán bean name từ proxy generated class.

## 12. Ảnh hưởng tới transaction, cache và những advice khác

Một service method có thể được bao bởi nhiều advisors: `@Aspect` logging, Spring transaction và caching. Hai điều cần giữ rõ:

1. **Proxy** nhận lời gọi từ client và điều phối toàn bộ chain.
2. **Target** thực thi business method khi phần chain tới được nó.

Ví dụ:

```text
Caller
  |
  v
Spring AOP proxy (getThis)
  |
  +-- Audit @Around
  +-- TransactionInterceptor
  +-- CacheInterceptor
  |
  v
Service target (getTarget)
```

Đây là sơ đồ **thứ tự minh họa**, không phải precedence mặc định bắt buộc.

Nếu bạn gọi thẳng `pjp.getTarget().perform(...)` trong logging advice, transaction/cache advisors phía trong có thể bị bỏ qua. Nếu bạn gọi `pjp.proceed()`, phần interceptor chain tiếp tục với thứ tự đã cấu hình. Nếu cache interceptor đứng ngoài và có cache hit, logging advice có thể **không được gọi** ở invocation đó.

### Có thể tự gọi một method khác trên target để tránh AOP không?

Có thể gọi method trực tiếp trên raw target theo Java semantics, nhưng làm vậy **bỏ qua cross-cutting concerns** và không nên dùng như “tối ưu” ngầm. Nếu một method thực sự không cần advice, chọn pointcut hẹp hơn hoặc thiết kế interface/service boundary phù hợp.

### Self-invocation và @Transactional

`this.saveTransactional()` từ target cũng bypass transaction proxy trong `AdviceMode.PROXY`. Điều này có thể làm annotation `@Transactional` “không hoạt động” dù bean đã được proxy đúng. Thiết kế tốt là chuyển transactional operation sang một Spring bean cộng tác, inject proxy của bean đó và gọi qua dependency.

Tương tự với `@Cacheable` và `@Async` ở proxy mode: việc gọi trên raw target không tự đi qua interceptors của bean ấy.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| `getThis() instanceof Implementation` false | Đang dùng JDK dynamic proxy | Dùng interface để inject/call hoặc xem nhu cầu class-based proxy |
| `getThis() instanceof Implementation` true nhưng `getThis()==getTarget()` false | CGLIB proxy là subclass khác instance | Phân biệt `instanceof` với reference identity |
| Cast Spring bean proxy thành class implementation lỗi | JDK proxy không subclass implementation | Inject interface, tránh cast không cần thiết |
| Dùng `getTarget()` gọi method mà transaction/audit không chạy | Bỏ qua advisor chain | Trong `@Around` dùng `pjp.proceed()` |
| Dùng `getThis()` gọi lại method đang được advice và stack overflow | Invocation mới lặp cùng advisor | Không thay `proceed()` bằng lời gọi qua proxy |
| `AopContext.currentProxy()` báo không có proxy | Chưa bật `exposeProxy` hoặc không ở lời gọi qua proxy | Dùng `pjp.getThis()` trong advice; tránh phụ thuộc thread-local nếu không cần |
| `getTarget().getClass()` ném `NullPointerException` | Targetless proxy/custom target source | Null-check trước khi dereference |
| Target instance thay đổi giữa requests | Scoped proxy/dynamic target source | Không cache target reference, quản lý scope đúng |
| `this(JobService)` không match nhưng `target(JobService)` match | Proxy JDK chỉ triển khai interface | Dùng type pattern đúng ý nghĩa proxy vs target |
| CGLIB proxy không advice method `final` | Method không override được | Đổi thiết kế class/method hoặc dùng proxy interface phù hợp |
| Method A được advice nhưng A tự gọi B không thấy advice của B | Self-invocation trên target | Di chuyển B sang Spring bean cộng tác và gọi qua proxy |
| Logger in tên class có ký hiệu generated proxy khác nhau | Log runtime proxy class thay vì target type | Dùng `AopUtils.getTargetClass`/metadata được hỗ trợ |
| Aspect không chạy dù class đúng package | Aspect không phải Spring bean, chưa bật AOP hoặc không qua proxy | Kiểm tra registration, `AopUtils.isAopProxy`, pointcut, call path |
| Proxy/target đều là proxy | Nested proxies do custom infrastructure | Xem các proxy layers; không giả định single-level unwrap |
| Quan sát `pjp.getTarget()` rồi lưu lâu trong singleton | Target scope có thể thay đổi | Chỉ sử dụng reference trong phạm vi invocation khi thật sự cần |

## 14. Quy trình debug getThis/getTarget

1. **Xác nhận đúng context.** Bean có được tạo bởi `ApplicationContext` sở hữu `@EnableAspectJAutoProxy` không?
2. **Xác nhận aspect là Spring bean.** `@Aspect` không tự đăng ký component; cần `@Component`/`@Bean`.
3. **Lấy proxy từ container.** Không tạo service bằng `new` rồi yêu cầu AOP hoạt động.
4. **Kiểm tra loại proxy.** `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`.
5. **Trong advice, in type an toàn.** Dùng `getThis()` cho proxy; null-check `getTarget()` nếu infrastructure có thể targetless.
6. **So sánh `==` thay vì `equals`** để xác minh object identity.
7. **Kiểm tra pointcut.** `this(Type)` đang chọn proxy hay `target(Type)` đang chọn target? Có match method execution thật?
8. **Quan sát call path.** Client gọi proxy hay target tự gọi `this.method()`?
9. **Không dùng raw target để “fix” việc cast.** Việc gọi method trên target sẽ bypass AOP.
10. **Không dùng proxy để mô phỏng proceed.** Trong `@Around` luôn cân nhắc `ProceedingJoinPoint.proceed()`.
11. **Nếu có scoped proxy/TargetSource**, xác định identity theo mỗi invocation, tránh assumption singleton.
12. **Nếu có caching/transaction/retry**, xem advisor ordering và method có thật sự được đi tới không.
13. **Viết integration test** trên Spring context với hai cấu hình JDK/CGLIB nếu ứng dụng có thể chạy ở cả hai chế độ.

### Một đoạn chẩn đoán dùng sau startup

```java
Object bean = context.getBean("jobService");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

Đây là snippet phụ thuộc biến `context` và import `AopUtils`, không phải Java file độc lập. Kết quả boolean giúp thấy loại proxy; `getTargetClass` cung cấp class metadata, không phải target instance.

## 15. Kết luận

Trong **Spring AOP**:

- **`getThis()` là Spring AOP proxy** — điểm client gọi vào, nơi advisors/interceptors có cơ hội hoạt động.
- **`getTarget()` là target object hiện hành** — object chứa method implementation thực, có thể `null` trong cấu hình targetless hoặc thay đổi theo dynamic target source.
- **`getThis() == getTarget()` thường false**, kể cả với CGLIB. JDK proxy không phải instance implementation; CGLIB proxy có thể là instance implementation nhờ subclassing, nhưng identity vẫn khác.
- **`this(TypePattern)` kiểm tra proxy**, còn **`target(TypePattern)` kiểm tra target** trong Spring pointcut.
- **`pjp.proceed()` mới là cách tiếp tục current around-advice invocation**. Gọi trực tiếp trên target bỏ qua advice; gọi lại trên proxy có thể tạo invocation mới và đệ quy.
- **Self-invocation của target bỏ qua proxy**; nó không được sửa chỉ bằng đổi JDK sang CGLIB.

Điểm cần nhớ sâu nhất không phải cách lấy tên class, mà là **đường đi của lời gọi**. Khi Spring proxy và target bị xem là một object, logging, transaction, caching, retry và các aspect khác có thể bị áp dụng thiếu hoặc trùng theo cách khó dự đoán.

### Tài liệu chính thức

- [Spring Framework 6.1 Javadoc — MethodInvocationProceedingJoinPoint](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/aop/aspectj/MethodInvocationProceedingJoinPoint.html): mô tả `getThis()` trả Spring proxy, `getTarget()` trả target và khả năng target bằng `null`.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): phân biệt `this`/`target` trong Spring AOP proxy-based system.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, quyền intercept và self-invocation.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `JoinPoint`, `ProceedingJoinPoint` và `proceed()`.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký `@Aspect` và bật Spring AOP.
