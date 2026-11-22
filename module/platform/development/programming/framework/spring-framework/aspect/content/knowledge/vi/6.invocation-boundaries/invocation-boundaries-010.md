# Phân biệt cùng phương thức đích nhưng khác đường đi của lời gọi trong Spring AOP

## 1. Câu hỏi trọng tâm: cùng method, vì sao advice chạy khác nhau?

Một method nghiệp vụ có thể trả đúng kết quả dù advice không chạy. Khi chẩn đoán Spring AOP, hãy ghi **receiver reference tại chính lệnh gọi**: Spring-injected proxy, `this` trên target, raw target được giữ riêng hay instance tạo bằng `new`. Sau đó mới kiểm tra method/pointcut, proxy type và thời điểm lifecycle.

Bài này tập trung **đối chiếu call paths có kiểm soát và điều tra khi log/transaction/audit biến mất**. Demo dùng cùng method `TaskService.run(String)` với các nhãn input khác nhau để phân biệt output; ba lượt đầu dùng cùng singleton target Spring, lượt `new` là đối chứng instance khác. Khi cần cô lập hoàn toàn ảnh hưởng của input, có thể giữ cùng chuỗi input cho từng lượt thử.

## 2. Vẽ caller → receiver → proxy → target

```text
Bean khác -> injected TaskService proxy -> advisor (nếu match) -> target.run()
Main      -> context TaskService proxy  -> advisor (nếu match) -> target.run()
Main      -> TaskService proxy.outer()  -> target.outer() -> this.run()
Main      -> new TaskService().run()    -> plain target.run()
```

Hai đường đầu vào `run` qua proxy; đường thứ ba chỉ qua proxy ở `outer`, còn `this.run` không quay qua đó; đường cuối hoàn toàn ở ngoài Spring container. Điều này tách **method body executed** khỏi **advice executed**. Có proxy thôi chưa đủ: bean phải có advisor phù hợp, method phải intercept được và call site phải dùng đúng reference. Bảng dưới đây đưa các tình huống lifecycle và proxy type vào cùng phép đối chiếu.

## 3. Đối chiếu cùng method `run(..)` theo đường đi lời gọi

| Đường gọi | Reference chứa ở caller | Có đi qua Spring AOP proxy vào `run(..)`? | Dự đoán với advice chỉ nhắm `run(..)` |
| --- | --- | --- | --- |
| `context.getBean(TaskService.class).run("A")` | Spring bean proxy từ context | Có, nếu bean được proxy và method intercept được | Advice chạy nếu pointcut match. |
| Bean X inject `TaskService` rồi gọi `taskService.run("A")` | Spring-injected proxy | Có | Advice chạy nếu pointcut match. |
| Controller inject `TaskService` rồi gọi `run("A")` | Spring-injected proxy | Có | Advice chạy nếu match. |
| `TaskService.outer()` gọi `this.run("A")` | `this` là target instance đang chạy | **Không**; self-invocation | Advice riêng của `run(..)` bị bypass. |
| `TaskService.outer()` gọi `run("A")` không ghi `this` | Vẫn là lời gọi nội bộ ngầm định trên `this` | **Không** | Kết quả giống dòng trên. |
| `new TaskService().run("A")` | Object thủ công ngoài container | Không có Spring proxy | Spring advice không chạy. |
| `@PostConstruct` trên chính TaskService gọi `run("A")` | Target đang initialization | Không nên coi đây là client call qua proxy hoàn chỉnh | Không trông đợi advice của `run(..)`. |
| `@PostConstruct` trên bean X gọi bean TaskService đã inject và được proxy | Tham chiếu sang **proxy của bean khác** | **Có thể có** | Advice có thể chạy nếu TaskService đã hoàn tất khởi tạo/proxy. |
| Caller dùng JDK proxy nhưng cố gọi method không thuộc interface proxy | Không có entry method tương ứng trên proxy | Không thể gọi trực tiếp theo kiểu interface ấy | Cần điều chỉnh contract hoặc proxy type. |
| Một method `final` trên class-based CGLIB proxy | Class proxy không override được method final | Không intercept method ấy | Advice không chạy dù bean có proxy. |

Bảng dùng các điều kiện đúng của Spring Framework; các trường hợp cụ thể có thể còn chịu tác động từ nhiều advisors, scope, target source và cấu hình hạ tầng. Không suy rằng “tên method giống nhau” thì Spring AOP phải hành xử giống nhau.

### Phân biệt “target method chạy” và “advice chạy”

Trong cả bốn đường gọi (proxy, internal, collaborator, `new`), **mã `run(..)` vẫn có thể chạy và trả cùng chuỗi**. Thứ khác nhau là sự hiện diện của **đoạn interception** trước/sau target method. Vì thế, kiểm tra return value đơn độc có thể khiến lỗi AOP bị bỏ sót: kết quả nghiệp vụ nhìn có vẻ đúng nhưng audit, metrics, transaction hoặc bảo mật dựa trên proxy đã bị bỏ qua.

## 4. Demo Spring Framework đầy đủ: một method đích, bốn đường gọi

Demo độc lập dùng **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Gradle. Đây là cấu hình Spring Framework thuần để chính `@EnableAspectJAutoProxy` bật hạ tầng; không phụ thuộc Spring Boot auto-configuration.

Mục tiêu: bốn lần thực thi **cùng method Java `TaskService.run(String)`** với cùng logic, nhưng `@Before` advice **chỉ thực thi hai lần** — tương ứng hai đường gọi thực sự đi qua Spring proxy.

### 4.1. Cấu trúc project

```text
spring-aop-call-path-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/callpath/
    ├── AppConfig.java
    ├── TaskService.java
    ├── OtherService.java
    ├── TraceAspect.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-call-path-demo'
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
    mainClass = 'com.example.callpath.Main'
}
```

Các version trên xác định một môi trường demo. Với Spring Boot, dùng starter/BOM tương ứng với Boot major version của ứng dụng, không ép version Spring riêng lẻ theo ví dụ này.

### 4.2. Target có phương thức đích và phương thức gọi nội bộ

**`TaskService.java`**

```java
package com.example.callpath;

public class TaskService {
    public String run(String source) {
        System.out.println("target:" + source);
        return "done:" + source;
    }

    public String outer(String source) {
        return this.run(source);
    }
}
```

Cả hai là public method và class không final; vì vậy giới hạn self-invocation không bị lẫn với vấn đề `private` hoặc `final`. Spring sẽ chỉ gắn một advisor của demo vào `run(..)`, **không gắn vào `outer(..)`**.

### 4.3. Bean khác được inject đúng Spring proxy

**`OtherService.java`**

```java
package com.example.callpath;

public class OtherService {
    private final TaskService taskService;

    public OtherService(TaskService taskService) {
        this.taskService = taskService;
    }

    public String callTask(String source) {
        return taskService.run(source);
    }
}
```

Điều cần nhận ra: `OtherService` không dùng `new TaskService()`; Spring config sẽ inject instance đã được xử lý bởi container. Nếu bean `TaskService` có proxy, dependency được inject chính là **proxy reference** phù hợp.

### 4.4. Aspect chỉ nhắm một method

**`TraceAspect.java`**

```java
package com.example.callpath;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger counter = new AtomicInteger();

    @Before("execution(public * com.example.callpath.TaskService.run(..))")
    public void beforeRun() {
        int value = counter.incrementAndGet();
        System.out.println("advice:run#" + value);
    }

    public int invocationCount() {
        return counter.get();
    }
}
```

`@Before` tăng counter **chỉ khi method `run(..)` thực sự đi qua advice**. Counter này dùng để minh họa trong một aspect bean singleton; nó không phải bộ đếm toàn cluster. `AtomicInteger` giúp mỗi lần increment có semantics thread-safe nếu gọi đồng thời.

### 4.5. Cấu hình Spring bean và AOP

**`AppConfig.java`**

```java
package com.example.callpath;

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
    TaskService taskService() {
        return new TaskService();
    }

    @Bean
    OtherService otherService(TaskService taskService) {
        return new OtherService(taskService);
    }
}
```

`TraceAspect` trở thành Spring-managed `@Aspect` bean thông qua `@Bean`, không cần `@Component`. `@EnableAspectJAutoProxy` bật xử lý `@AspectJ` và auto-proxy. `proxyTargetClass=true` chọn class-based proxy để `context.getBean(TaskService.class)` hợp lệ với concrete class không định nghĩa interface.

Hai `@Bean` methods còn lại tạo target và bean caller. Khi Spring tạo `OtherService`, tham số `TaskService` nhận Spring bean/proxy theo cơ chế injection. Đây là mối liên kết quan trọng để đường gọi giữa hai bean thật sự đi qua proxy.

### 4.6. Main in riêng từng đường gọi

**`Main.java`**

```java
package com.example.callpath;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService task = context.getBean(TaskService.class);
            OtherService other = context.getBean(OtherService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(task));

            System.out.println("path=direct-proxy");
            System.out.println("result=" + task.run("direct"));

            System.out.println("path=self-invocation");
            System.out.println("result=" + task.outer("internal"));

            System.out.println("path=another-bean");
            System.out.println("result=" + other.callTask("collaborator"));

            System.out.println("path=manual-new");
            TaskService plainObject = new TaskService();
            System.out.println("result=" + plainObject.run("plain"));

            System.out.println("adviceCount=" + aspect.invocationCount());
        }
    }
}
```

### 4.7. Chạy và kiểm tra stdout chính xác

Tại thư mục project, với Gradle đã cài:

```bash
gradle run --quiet
```

Nếu đã có Gradle Wrapper thì dùng `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows).

**Dòng do chương trình in, theo đúng thứ tự** (không tính warning/log của JVM, Gradle hoặc Spring nếu logging environment bật):

```text
proxy=true
path=direct-proxy
advice:run#1
target:direct
result=done:direct
path=self-invocation
target:internal
result=done:internal
path=another-bean
advice:run#2
target:collaborator
result=done:collaborator
path=manual-new
target:plain
result=done:plain
adviceCount=2
```

### 4.8. Đọc từng case theo đường đi thật

**Case 1 — direct-proxy**

`task.run("direct")` được gọi trên bean `TaskService` lấy từ `ApplicationContext`. Bean đã được auto-proxy, pointcut nhắm `run(..)`. Vì vậy có `advice:run#1` trước `target:direct`.

**Case 2 — self-invocation**

`task.outer("internal")` đi qua Spring proxy ở entry `outer(..)`; tuy nhiên aspect **không có advice dành cho `outer(..)`**. Sau khi code vào `TaskService` target, `this.run("internal")` gọi trực tiếp sang method trên chính target, không qua proxy của `TaskService`. Do đó **không có `advice:run#2` ở case này**.

**Case 3 — another-bean**

`other.callTask("collaborator")` chạy logic của `OtherService`. Field `taskService` đã được Spring inject bằng `TaskService` proxy. Lời gọi `taskService.run("collaborator")` đi **vào proxy từ bên ngoài target**, advice chạy. Counter tăng thành `2`, xuất hiện `advice:run#2` rồi `target:collaborator`.

**Case 4 — manual-new**

`plainObject.run("plain")` thực thi đúng thân method Java của `TaskService` nhưng trên object tạo bởi `new` **ngoài Spring container**. Không có proxy AOP ở reference này nên không xuất hiện advice.

**Kết luận từ demo:** cùng method `run(..)` được thực thi bốn lần, target body in `target:...` bốn lần, nhưng `@Before` advice chỉ chạy **hai lần**. Với ba case đầu, `TaskService` target bean được Spring quản lý là một; case cuối cố ý đổi object instance để làm đối chứng.

## 5. Cô lập biến “cùng target” trong phép thử

Để không nhầm việc đổi object với việc đổi đường gọi, hãy so sánh **ba case đầu** của mục 4. `TaskService` do `@Bean` tạo là singleton mặc định: `task.run("direct")` và `other.callTask("collaborator")` đều đi qua proxy tới bean ấy, còn `task.outer("internal")` đi vào cùng target nhưng tự gọi `this.run`. Bộ đếm advice bằng `2` trong khi thân `run` chạy ba lần trên Spring target.

Case `manual-new` chạy trên object khác và chỉ dùng để đối chứng phạm vi container. Một unit test `new TaskService()` có thể xác minh return value nhưng không chứng minh advice Spring đang hoạt động.

## 6. Đổi thời điểm gọi: constructor và init callback

Constructor hay `@PostConstruct` **trên chính TaskService target** gọi `run()` qua `this` trước khi proxy hoàn chỉnh được trao cho caller thông thường; không dùng các callback đó để xác nhận advice nhắm `run()`. Ngược lại, callback của **bean khác** có thể gọi qua proxy của TaskService nếu dependency đã hoàn tất khởi tạo. Đừng dùng `context.getBean` từ chính constructor để “lấy proxy sớm” vì có thể tạo circular dependency hoặc early reference.

Với startup work cần chạy qua advice, dùng một coordinator khác ở mốc context phù hợp, ví dụ `ContextRefreshedEvent` hoặc Boot runner, rồi kiểm chứng **receiver thực tế**. Bài chuyên về lifecycle phân tích sâu thứ tự các callback và điều kiện ngoại lệ.

## 7. Khi advice bọc outer(..) mà inner(..) không được bọc

Một ngộ nhận phổ biến là “caller đã qua proxy ở method ngoài, vậy mọi method bên trong cũng mặc nhiên qua AOP”.

Xét:

```java
@Aspect
@Component
class TwoMethodsAspect {
    @Before(
        "execution(* com.example.callpath.TaskService.outer(..))"
        + " || execution(* com.example.callpath.TaskService.run(..))"
    )
    public void beforeBoth(JoinPoint point) {
        System.out.println("advice:" + point.getSignature().getName());
    }
}
```

Đây là **biến thể minh họa riêng**, cần import `JoinPoint`, `Aspect`, `Before`, `Component` và component scan để được đăng ký; **không thêm vào demo chính**, tránh thay đổi stdout.

Khi caller gọi `taskProxy.outer("A")`:

1. Proxy intercept `outer(..)`, advice cho `outer` có thể chạy.
2. Target thực thi `outer(..)`.
3. `this.run("A")` chạy trực tiếp trên target.
4. Advice nhắm `run(..)` **không tự chạy lần nữa** chỉ vì `outer(..)` đã có advice.

Vì vậy, log có thể cho thấy `advice:outer`, sau đó method `run` vẫn được gọi, nhưng **không có `advice:run`**. Có proxy ở entry không tạo ra một “vòng proxy” tự động cho nested calls.

Ngược lại, nếu `outer(..)` chuyển sang gọi một **injected collaborator bean** có proxy và pointcut match, một advice khác có thể chạy ở ranh giới mới. Đây là ranh giới kiến trúc khác, không phải nested self-call trong cùng target.

## 8. Hệ quả nếu đường gọi bypass interceptor

| Concern được bật phù hợp | Qua proxy và advisor match | Self-call trên target |
| --- | --- | --- |
| Custom `@Aspect` audit | Có thể ghi audit event | Không chạy advice riêng của method inner. |
| `@Transactional` | Áp dụng propagation theo transaction interceptor | Inner không tự kích hoạt interceptor mới; có thể vẫn nằm trong transaction đã tồn tại. |
| `@Cacheable` | Có thể thực hiện cache lookup/put | Inner bỏ qua cache advice. |
| `@Async` hoặc method security | Có thể chạy executor/authorization rule | Không có interception riêng trên inner call. |

Mỗi concern đòi hỏi activation/configuration của chính nó; `@EnableAspectJAutoProxy` không tự bật hết những tính năng này. Nếu refactor đổi đường đi, hãy kiểm thử transaction outcome, cache hit, thread thực thi hoặc quyết định authorization thực tế. Return value giống nhau chưa đủ để chứng minh policy đã chạy.

## 9. Receiver và khả năng intercept: kiểm tra có điều kiện

**JDK dynamic proxy** chỉ expose những method thuộc proxied interface; **CGLIB proxy** có thể expose concrete class method nhưng không override được `final`/`private` methods. Cả hai đều không khiến `this.inner()` tự quay lại proxy. Với reflection, `method.invoke(receiver, args)` chỉ được Spring AOP intercept khi **receiver là proxy** và method callable phù hợp; reflection không tự đảm bảo có hoặc không có advice.

`AopUtils.isAopProxy(bean)`, `isJdkDynamicProxy` và `isCglibProxy` giúp nhận diện reference; `Advised.getAdvisors()` giúp xem chain nếu proxy triển khai `Advised`. Không lấy `equals`, tên runtime class hay sự hiện diện proxy làm bằng chứng một **method cụ thể** đã được advice. Bộ đếm/event recorder ở mục 11 mới kiểm chứng kết quả thực thi.

## 10. Chọn cách sửa theo policy và call site

| Tình huống đã chứng minh | Hướng xử lý | Điều phải kiểm thử lại |
| --- | --- | --- |
| Policy áp dụng cho **toàn operation ngoài** | Nhắm advice vào entry `outer(..)` đang đi qua proxy | Transaction, retry, exception và phạm vi policy có thể thay đổi. |
| Method inner là trách nhiệm nghiệp vụ riêng | Chuyển nó sang **Spring collaborator bean**, inject dependency rồi gọi qua proxy | Bean có được quản lý, pointcut cũ còn match class/method mới, semantics còn đúng. |
| Bất khả kháng phải gọi lại proxy của chính bean | Cân nhắc self-injection với `@Lazy` hoặc `ObjectProvider`; quản lý vòng đời và kiểu proxy | Circular dependencies, scope, và tình huống gọi quá sớm. |
| Bất khả kháng cần `AopContext.currentProxy()` | Chỉ trong proxy invocation đã bật `exposeProxy=true`, cast đúng JDK/CGLIB proxy | `IllegalStateException` khi thiếu context, đệ quy và coupling. |

Chuyển sang AspectJ weaving là thay đổi mô hình interception, cần thiết lập compiler/agent riêng; `@EnableAspectJAutoProxy` không tự tạo weaving. Hai bài riêng về collaborator, self-injection và `AopContext` cung cấp ví dụ sâu; tại đây ưu tiên **xác nhận call path trước và sau sửa**.

## 11. Kiểm tra Spring context đúng cách

### 11.1. Xác nhận bean lấy ra là proxy

```java
TaskService bean = context.getBean(TaskService.class);
System.out.println("isProxy=" + AopUtils.isAopProxy(bean));
System.out.println("isClassProxy=" + AopUtils.isCglibProxy(bean));
```

Đây là đoạn minh họa dùng `context` từ demo và import `AopUtils`. Với `AppConfig` của demo hai dòng lần lượt in `true` và `true`. Không dùng type concrete khi đã cấu hình JDK interface proxy; lúc đó lấy và inject theo interface.

**Proxy tồn tại không đủ kết luận.** Một bean có nhiều advisors, và advisor cần xét có thể không match method đang gọi. Sau bước kiểm tra proxy phải chạy một method và quan sát rõ advice event hoặc recorder.

### 11.2. Đếm invocation của advice

`TraceAspect` trong demo có `AtomicInteger` và method `invocationCount()`. Sau bốn case, `adviceCount=2` trong khi thân `TaskService.run` đã thực thi bốn lần. Đây là một phép đo trực tiếp sự khác biệt giữa **method body executions** và **advised executions**.

Nếu muốn test tự động, có thể thay console bằng một `EventRecorder` Spring bean chứa collection thread-safe, inject recorder vào aspect, gọi các case rồi assert:

- `directProxy` tạo một audit event.
- `selfInvocation` không tạo audit event riêng cho inner method.
- `otherBean` tạo thêm một event.
- `manualNew` không tạo event.
- Business outputs vẫn đúng hợp đồng.

Trong test này, **method event** mới là điều chứng minh AOP chạy, không phải chỉ `AopUtils.isAopProxy`.

### 11.3. Đặt breakpoint ở hai nơi

Đặt breakpoint ở `TraceAspect.beforeRun` và `TaskService.run`. Khi gọi `task.outer("internal")`, debugger vào `run` nhưng không vào `beforeRun` cho lần gọi đó. Khi gọi `task.run("direct")`, debugger vào advice trước target. Khi gọi `other.callTask("collaborator")`, đường đi tương tự direct proxy.

Điều này giúp chứng minh lỗi AOP không đồng nghĩa lỗi gọi method — method body vẫn chạy đúng, chỉ bỏ qua interceptor chain.

### 11.4. Kiểm tra pointcut nếu đường gọi đã qua proxy nhưng vẫn thiếu advice

Nếu một case chắc chắn đi qua Spring bean proxy mà advice không chạy, hãy kiểm tra:

1. Aspect class có `@Aspect` và đã được đăng ký thành bean qua `@Component` hoặc `@Bean` chưa?
2. Trong Spring Framework Java config có `@EnableAspectJAutoProxy` và `aspectjweaver` chưa, hoặc trong Boot AOP auto-configuration có phù hợp không?
3. Pointcut `execution(..)`, `@annotation(..)` hoặc `bean(..)` có nhắm đúng **method/type/bean runtime**?
4. Bean proxy JDK có expose method qua interface không? Class proxy có gặp `final`/`private` không?
5. Client có giữ proxy reference thật hay tự tạo `new`, giữ raw target, gọi nội bộ qua `this`?
6. Có nhiều `ApplicationContext` hoặc nhiều bean instances không? Aspect/advisor được bật ở context nào?
7. Có advice khác nuốt exception, trả sớm, thay đổi args hoặc điều phối async khiến log xuất hiện ở thời điểm khác không?

Đừng thêm `@EnableAspectJAutoProxy` trùng lặp hoặc đổi sang CGLIB khi chưa xác định nguyên nhân.

## 12. Những tình huống dễ suy luận sai

| Quan sát | Kết luận vội thường sai | Diễn giải đúng theo Spring AOP |
| --- | --- | --- |
| Hai lời gọi có cùng source code của target method | “Advice phải chạy giống nhau” | Cần xem một lời gọi qua proxy, lời kia qua `this` hay raw object. |
| `AopUtils.isAopProxy(task)==true` | “Mọi method đều có advice” | Chỉ biết proxy tồn tại; cần check method/pointcut và call path. |
| `outer()` được advice | “`this.inner()` cũng được advice” | Target self-call không quay qua proxy. |
| Thêm `public` vào inner method | “Đã sửa AOP” | Visibility chưa giải quyết self-invocation. |
| Bật `proxyTargetClass=true` | “CGLIB tự chặn internal call” | Vẫn là Spring proxy-based interception và self-call bypass. |
| Bean khác gọi method từ `@PostConstruct` | “Mọi init call đều bypass” | Nếu reference tới target khác đã proxy hoàn chỉnh, advice có thể chạy. |
| Tạo `new TaskService()` bên trong bean | “Vì caller là Spring bean, target cũng được AOP” | Object tự tạo không tự biến thành proxy của Spring. |
| Method có `@Transactional` | “Chắc chắn đang transaction” | Cần activation, proxy boundary và kiểm tra transaction thực tế. |
| Gọi qua reflection | “Reflection luôn bypass/luôn kích hoạt advice” | Phụ thuộc receiver có phải proxy và method được expose hay không. |
| Đổi sang collaborator bean rồi không thấy advice | “Spring AOP không hỗ trợ nhiều bean” | Kiểm tra collaborator thật sự được Spring quản lý và pointcut còn match. |

## 13. Quy trình phân tích một bug thực tế

### Bước 1 — Xác định method cụ thể

Ghi rõ FQCN, tên, signature, annotation, bean name và pointcut. Không dừng ở “method có annotation mà không hoạt động”.

### Bước 2 — Ghi lại đường đi caller → receiver

Vẽ các references: controller/service/coordinator/target; phân biệt `this`, DI proxy, instance `new`, bean từ context. **Receiver** ở đúng lệnh gọi tới method là ai?

### Bước 3 — Kiểm tra loại proxy và khả năng intercept

Dùng `AopUtils` trên bean do context trả về. Nếu JDK proxy, method phải nằm trên interface; nếu CGLIB, method phải override được. Không nhầm giới hạn final/private với self-invocation.

### Bước 4 — Xác nhận aspect bean và matching

Kiểm tra `getBeanNamesForType(TraceAspect.class)`, enable config/AspectJ dependency và pointcut match. Nếu advice chưa được container nhận diện, mọi đường proxy cũng không giúp được.

### Bước 5 — Thử hai call paths có kiểm soát

Từ một test Spring context thật, gọi `taskProxy.run("X")`, rồi gọi `taskProxy.outer("X")` có self-call cùng method. Dùng recorder/counter xác nhận khác biệt. Giữ input giống nhau để cô lập nguyên nhân đường đi.

### Bước 6 — Thay bằng injected collaborator nếu cần

Tách operation cần advice sang một Spring bean khác hoặc đổi boundary cho policy. Cập nhật pointcut theo method mới; tránh object tạo bằng `new` và circular dependency.

### Bước 7 — Test semantics ngoài log

Nếu concern là security, transaction, cache, async, metric, retry, hãy kiểm tra chính hành vi mong muốn, đặc biệt lỗi/rollback/side effects; đừng kết luận từ log advice duy nhất. Khi refactor làm advice bắt đầu chạy, semantics sản xuất có thể thay đổi đáng kể.

### Bước 8 — Rà soát startup và concurrency

Tách constructor/`@PostConstruct` của target ra khỏi entry call bình thường; kiểm tra bean lifecycle. Với async/đa luồng, không đặt giả định tuyệt đối về thứ tự log.

## 14. Checklist tổng kết

- [ ] Đã phân biệt **method body có chạy** với **advice có chạy**?
- [ ] Đã xác định đúng **receiver reference** tại lệnh gọi (`this`, DI proxy, `new`, raw target)?
- [ ] Nếu so hai đường gọi, đã giữ nguyên target method/pointcut/input để tránh nhiễu?
- [ ] Aspect có `@Aspect` và là Spring bean; auto-proxy support được bật?
- [ ] Spring target bean có proxy phù hợp và public/interface entry method intercept được?
- [ ] Đã kiểm tra `this.inner()` và implicit `inner()` đều là self-invocation?
- [ ] Nếu caller là bean khác, dependency có lấy từ Spring container/DI không?
- [ ] Với constructor/`@PostConstruct`, đã tính đến proxy chưa hoàn tất?
- [ ] Đã tránh giả định CGLIB, JDK proxy hoặc reflection tự giải quyết mọi call paths?
- [ ] Nếu chuyển sang collaborator, đã cập nhật pointcut và test exception/return/transaction/security semantics?
- [ ] Đã dùng integration test Spring context + recorder/counter đo đúng số advice invocations?
- [ ] Không dựa vào một thông điệp log hoặc `isAopProxy=true` để kết luận toàn bộ?

**Điểm nhớ:** Trong Spring AOP, **cùng một method đích vẫn có thể có hai hành vi interception khác nhau vì đường đi lời gọi khác nhau**. Spring proxy chỉ áp dụng advice khi lời gọi đi qua proxy thích hợp; `this.method()` và đối tượng ngoài container không có cùng ranh giới ấy. Khi debug, vẽ **caller → receiver → proxy → target**, rồi xác nhận bằng test có context thật.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Proxying Mechanisms / Understanding AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework 6.2 — Pointcut Declarations](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Bean Lifecycle / Initialization](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)
