# Nhiều aspect cùng khớp một phương thức trong Spring AOP

## 1. Bài toán và kết quả cần hiểu

Một phương thức của Spring service có thể đồng thời khớp nhiều pointcut đến từ **nhiều `@Aspect` bean**. Ví dụ, khi `OrderService.submit(..)` được caller gọi qua Spring proxy, ứng dụng có thể áp dụng logging, đo thời gian, audit, transaction hoặc custom validation thông qua những advisors khác nhau.

Với **Spring AOP theo cú pháp @AspectJ**, Spring xây một **chuỗi interceptor/advisor** cho mỗi proxy invocation phù hợp, chứ không tạo một bản sao riêng của target method cho từng aspect. Một lần gọi target có thể khiến nhiều advice thực thi theo thứ tự có quy tắc.

Những câu hỏi phải giải quyết:

1. Khi hai hoặc nhiều Spring `@Aspect` cùng match một method, **advice nào được gọi trước**?
2. Vì sao `@Order(10)` có thể chạy **trước khi vào** target nhưng **sau khi ra** target so với `@Order(20)`?
3. Với `@Around`, chuyện gì xảy ra nếu một aspect không gọi `proceed()`, tự ném lỗi, bắt lỗi, retry hoặc thay return value?
4. Nếu một aspect chỉ có `@Before` còn aspect khác dùng `@AfterReturning` hoặc `@AfterThrowing`, cần phân biệt gì về ngữ nghĩa outcome?
5. Thứ tự giữa **các aspects khác nhau** khác thế nào với thứ tự **nhiều advice cùng loại trong cùng một aspect**?
6. Làm sao kiểm chứng bằng Spring `ApplicationContext`, không suy đoán từ thứ tự method xuất hiện trong file Java?

Bài tập trung vào **Spring Aspect/Spring AOP proxy**, sự kết hợp nhiều `@Aspect`, `@Order`/`Ordered`, invocation chain và kiểm thử. Những khái niệm AOP tổng quát chỉ được nêu khi cần giải thích Spring.

## 2. Một Spring method, nhiều aspects nhưng chỉ một proxy boundary

Giả sử ba aspects đều có expression phù hợp với:

```java
public String submit(String id) {
    return "submitted:" + id;
}
```

Sơ đồ conceptual khi Spring AOP proxy nhận invocation:

```text
External caller
     |
     | service.submit("A")     (reference do Spring container trả về)
     v
Spring AOP proxy
     |
     +--> Aspect Outer / @Around / @Order(10)
     |      enter
     |         |
     |         +--> Aspect Gate / @Before / @Order(15)
     |                   |
     |                   +--> Aspect Inner / @Around / @Order(20)
     |                             enter
     |                               |
     |                               +--> target.submit("A")
     |                               |
     |                             exit
     |      exit
     v
Caller nhận kết quả hoặc exception
```

**Cần phân biệt:**

- `@Aspect` là class khai báo các advices/pointcuts; **aspect phải được đăng ký làm Spring bean** để Spring AOP sử dụng.
- Spring tạo một **proxy** (JDK dynamic proxy hoặc CGLIB class proxy) cho target bean đủ điều kiện và kết hợp các advisors áp dụng. Không nên suy mỗi aspect tạo thêm một proxy riêng trong mọi ứng dụng.
- Một target method có thể được advice bởi nhiều aspects, nhưng `@Around` có khả năng ngăn hoặc lặp lời gọi target; vì vậy **số lần target body chạy không phải lúc nào cũng bằng số lần proxy entry**.
- `@Order` điều khiển **precedence của aspect trong Spring**, không làm pointcut match nhiều hay ít hơn.
- Các advisors của Spring transaction/cache/security có thể cùng tồn tại với custom aspects, nhưng một bài học về `@Order` của custom aspects không tự quy định order của mọi infrastructure advisor.

**Mô hình đúng:** một lời gọi bên ngoài đi vào Spring proxy, nơi Spring chọn advisor chain có thể áp dụng. Nếu caller bypass proxy (`new` object, `this.inner()` trên target), việc có mười aspects match chữ ký method vẫn không tự tạo interception.

## 3. Thứ tự mặc định: không có @Order thì không dựa vào thứ tự tình cờ

Tài liệu Spring Framework nêu rõ: khi **hai pieces of advice trong hai aspects khác nhau** cùng muốn chạy ở một join point, nếu **không chỉ định precedence** thì thứ tự thực thi **không được xác định**.

Không được suy thứ tự từ:

- Tên file Java theo alphabet;
- Tên class aspect;
- Thứ tự `@Bean` factory methods;
- Thứ tự component scanning thường thấy;
- Thứ tự các methods trong một `@Aspect` class;
- Việc aspect “logging” hay “security” nghe có vẻ phải trước;
- Kết quả một lần chạy locally không có assertion/regression test.

Nếu behavior **phụ thuộc vào thứ tự**, phải dùng precedence rõ ràng rồi kiểm tra bằng test trên **Spring version, proxy mode và advisor configuration thật**.

Một số tracing/logging có thể không cần thứ tự cố định; nhưng masking secrets trước logging, authorization trước business effects, transaction boundary với audit và metrics thường đòi hỏi xem xét thứ tự kỹ.

## 4. @Order và Ordered trong Spring AOP

Trong Spring, có hai cách phổ biến để đặt precedence:

**Annotation trên aspect class:**

```java
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAspect {
    // Các advice của aspect này có precedence theo 10.
}
```

**Hoặc implement `Ordered`:**

```java
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.Ordered;

@Aspect
public class OuterAspect implements Ordered {
    @Override
    public int getOrder() {
        return 10;
    }
}
```

Hai đoạn **là hai lựa chọn riêng**, không định nghĩa cùng tên class trong cùng project. Cần thêm Spring bean registration (`@Component` hoặc `@Bean`) và advice thực sự để ảnh hưởng runtime.

**Quy tắc Spring: số order càng nhỏ thì precedence càng cao.** Ví dụ `@Order(10)` cao hơn `@Order(20)`; `Ordered.HIGHEST_PRECEDENCE` (giá trị cực nhỏ) và `Ordered.LOWEST_PRECEDENCE` (giá trị cực lớn) là hai mốc tham khảo.

| Precedence | Thứ tự khi vào (“on the way in”) | Thứ tự khi ra (“on the way out”) |
| --- | --- | --- |
| Aspect A, `@Order(10)` | Vào **trước** aspect B | Ra **sau** aspect B |
| Aspect B, `@Order(20)` | Vào **sau** aspect A | Ra **trước** aspect A |

Suy nghĩ theo **cặp ngoặc lồng nhau**:

```text
A.enter
    B.enter
        target
    B.exit
A.exit
```

Không dùng một câu đơn giản như “order càng thấp thì aspect luôn chạy trước” để mô tả cả enter lẫn exit. Nó chỉ đúng **ở chiều vào**; chiều ra có thứ tự đảo ngược.

### 4.1. @Order ở class aspect, không phải “thứ tự của mọi method”

Trong Spring `@AspectJ`, đặt `@Order` trên **aspect type** là cách trực quan để xác định precedence giữa aspects. Nếu trong một aspect có hai `@Before` methods match cùng join point, thêm cùng `@Order` trên class **không tự quyết định method nào của hai advice chạy trước**.

Đừng dán `@Order(1)` lên mỗi advice method rồi suy Spring bảo đảm nó sẽ trở thành order toàn cục theo ý muốn. Hãy dùng **hai aspect classes riêng**, một advice duy nhất có logic thứ tự tường minh, hoặc một orchestration pointcut phù hợp.

### 4.2. Hai aspect có cùng order value

Nếu A và B cùng `@Order(10)`, không được suy Spring sẽ xử lý A trước B một cách ổn định giữa mọi môi trường. Nếu thứ tự business-critical, **đặt giá trị khác nhau có chủ đích** và regression test, không dựa vào thứ tự registration.

### 4.3. Ordered có thể đến từ bean instance

`Ordered.getOrder()` cho phép giá trị order ở instance của aspect bean. Khi nhiều Spring beans và auto-proxy behavior tham gia, cần bảo đảm Spring thực sự nhận giá trị mong muốn từ aspect bean; nếu đang dùng dynamic configuration, test runtime không chỉ đọc class annotation.

Không lạm dụng dynamic order để thay chính sách nghiệp vụ theo từng request: precedence của advisor chain là một đặc tính của hạ tầng proxy, không phải context dữ liệu per-invocation để tự thay đổi tùy tiện.

## 5. @Around quan sát chuỗi lồng nhau rõ nhất

Khi A (`@Order(10)`) và B (`@Order(20)`) đều dùng `@Around` trên cùng Spring target method:

```java
@Around("execution(* com.example.orders.OrderService.submit(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    before();
    try {
        Object value = pjp.proceed();
        afterSuccess();
        return value;
    } catch (Throwable error) {
        afterFailure(error);
        throw error;
    } finally {
        cleanup();
    }
}
```

Đoạn này **minh họa**, chưa là Java file standalone (thiếu class, imports, các helper methods). Nó cho thấy một aspect có thể chạy **cả ở chiều vào và chiều ra**.

Kết quả với hai aspects thường mô tả được bằng:

```text
A.before        (Order 10)
B.before        (Order 20)
target.submit
B.afterSuccess  (Order 20)
B.cleanup       (Order 20)
A.afterSuccess  (Order 10)
A.cleanup       (Order 10)
```

Nếu target ném exception:

```text
A.before
B.before
target.submit -> throw
B.afterFailure
B.cleanup
A.afterFailure
A.cleanup
Caller nhận exception
```

Đây là **sơ đồ logic** khi hai `@Around` luôn gọi `proceed()` đúng một lần và ném lại nguyên exception. Cách chắc chắn nhất để học/kiểm chứng là chạy demo Spring AOP thực tế ở mục 7.

### 5.1. Không có bảo đảm target luôn chạy

`@Around` có quyền **không gọi `proceed()`**, hoặc gọi nhiều lần. Nếu aspect ngoài cùng short-circuit, những advisors nằm sau nó và target **có thể không chạy**, kể cả khi pointcut của chúng hoàn toàn match method.

Ví dụ minh họa không nên dùng khi không có contract:

```java
@Around("execution(* com.example.orders.OrderService.submit(..))")
public Object unsafeSkip(ProceedingJoinPoint pjp) {
    return "ok"; // Không hề gọi target hoặc những interceptor downstream!
}
```

Một aspect có precedence cao hơn không chỉ “ghi log sớm hơn”: nó có thể quyết định liệu downstream advice có được vào chain hay không. Điều này liên quan trực tiếp tới thứ tự của security, transaction, retry và cache interceptors trong Spring.

## 6. Hai vấn đề cần tách biệt: matching và ordering

Một aspect chỉ tham gia invocation nếu:

1. Nó là **Spring-managed `@Aspect` bean** có advice được hạ tầng nhận diện;
2. Pointcut match method execution/bean trong Spring context;
3. Caller đi qua Spring proxy và method nằm trong phạm vi interception của JDK/CGLIB;
4. Những interceptors có precedence cao hơn **cho phép chain tiếp tục** tới nó;
5. Nếu advice có điều kiện động (`args`, `@annotation`, `@target`, `@within`...) thì điều kiện tương ứng đúng ở invocation đó.

**`@Order` chỉ giải quyết câu hỏi precedence sau khi các advisor đã được chọn.** Đổi `@Order(5)` thành `@Order(50)` không khiến một annotation `@AuditAction` đột nhiên xuất hiện trên target method.

### Một biểu thức match cả hai service methods

```java
@Around("execution(public * com.example.chain.TaskService.*(..))")
public Object aroundEveryPublicTaskMethod(
        ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

Nếu target có `run()` và `fail()`, cả hai có thể bị advice khi caller gọi qua Spring proxy. Thứ tự giữa aspects là một câu chuyện khác, do `@Order`/`Ordered`.

Nếu pointcut chỉ chọn `run()`, advice không chạy khi caller gọi `fail()`, bất kể `@Order` là bao nhiêu. Vì vậy, khi thiếu log, kiểm tra **matching trước** rồi mới điều tra order.

## 7. Demo Spring Framework runnable: ba aspects cùng khớp hai methods

Demo dùng Java 17+, Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**, Gradle. Đây là Spring Framework thuần, không dùng Spring Boot auto-configuration, để thứ tự `@Order` và yêu cầu `@EnableAspectJAutoProxy` được thể hiện rõ.

Gồm:

- `OuterAspect`: `@Order(10)`, `@Around`, vào đầu tiên và thoát cuối cùng.
- `GateAspect`: `@Order(15)`, `@Before`, chạy sau `OuterAspect.enter` nhưng trước `InnerAspect.enter`.
- `InnerAspect`: `@Order(20)`, `@Around`, bao sát target hơn `OuterAspect`.
- `TaskService`: một method thành công và một method ném exception để quan sát chiều ra.
- `Main`: lấy Spring proxy từ context, gọi hai methods và in stdout tất định.

### 7.1. Cây thư mục

```text
spring-multiple-aspects-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/chain/
    ├── TaskService.java
    ├── OuterAspect.java
    ├── GateAspect.java
    ├── InnerAspect.java
    ├── AppConfig.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-multiple-aspects-demo'
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
    mainClass = 'com.example.chain.Main'
}
```

Spring Framework 6.x hỗ trợ Java 17+; `spring-context` cung cấp `ApplicationContext`/`@Configuration`; `spring-aop` và `aspectjweaver` phục vụ cấu hình Spring proxy `@AspectJ`. Việc có `aspectjweaver` trên classpath để parsing pointcuts **không đồng nghĩa** đang bật AspectJ load-time weaving.

### 7.2. Spring target bean

**`TaskService.java`**

```java
package com.example.chain;

public class TaskService {
    public String run(String id) {
        System.out.println("target:run");
        return "ok:" + id;
    }

    public String fail() {
        System.out.println("target:fail");
        throw new IllegalStateException("boom");
    }
}
```

Class và methods đều public/non-final, không interface, nên class-based proxy có thể chặn chúng. Hai methods không gọi nhau để không lẫn self-invocation với thứ tự aspects.

### 7.3. Aspect order 10: wrapper ngoài cùng

**`OuterAspect.java`**

```java
package com.example.chain;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAspect {
    @Around("execution(public * com.example.chain.TaskService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String name = pjp.getSignature().getName();
        System.out.println("outer:enter:" + name);
        try {
            Object result = pjp.proceed();
            System.out.println("outer:return:" + name);
            return result;
        } catch (Throwable error) {
            System.out.println(
                    "outer:throw:" + name + ":"
                    + error.getClass().getSimpleName()
            );
            throw error;
        } finally {
            System.out.println("outer:finally:" + name);
        }
    }
}
```

Chú ý:

- `@Order(10)` có precedence cao hơn `@Order(15)` và `@Order(20)`.
- `pjp.proceed()` chuyển quyền xuống những advisors còn lại, rồi mới tới target.
- `throw error;` giữ nguyên exceptional outcome của downstream invocation.
- `finally` chạy trên cả normal return lẫn throw.
- Advice không tự tạo fallback hoặc retry. Nếu cố return fake value trong `catch`, output caller và hành vi downstream có thể thay đổi.

### 7.4. Aspect order 15: một @Before

**`GateAspect.java`**

```java
package com.example.chain;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;

@Aspect
@Order(15)
public class GateAspect {
    @Before("execution(public * com.example.chain.TaskService.*(..))")
    public void before(JoinPoint jp) {
        System.out.println("gate:before:" + jp.getSignature().getName());
    }
}
```

`@Before` ở đây dùng để **quan sát entry**, không tự return kết quả. Nó chạy giữa `OuterAspect.enter` và `InnerAspect.enter` khi những advisors tham gia chuỗi như cấu hình.

Nếu `@Before` tự ném exception, các interceptors/target phía sau có thể không được gọi. Đừng dùng `@Before` để biến một lỗi hợp lệ thành return fallback; nếu cần authorization, hãy dùng hạ tầng Spring Security với precedence được kiểm tra phù hợp.

### 7.5. Aspect order 20: wrapper sát target

**`InnerAspect.java`**

```java
package com.example.chain;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(20)
public class InnerAspect {
    @Around("execution(public * com.example.chain.TaskService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String name = pjp.getSignature().getName();
        System.out.println("inner:enter:" + name);
        try {
            Object result = pjp.proceed();
            System.out.println("inner:return:" + name);
            return result;
        } catch (Throwable error) {
            System.out.println(
                    "inner:throw:" + name + ":"
                    + error.getClass().getSimpleName()
            );
            throw error;
        } finally {
            System.out.println("inner:finally:" + name);
        }
    }
}
```

`InnerAspect` có precedence thấp nhất trong ba aspects nhưng vẫn **bao quanh target**: `inner:enter` trước `target`, `inner:return` hoặc `inner:throw` sau target, rồi `inner:finally`. Nó hoàn thành phần chiều ra **trước** `OuterAspect`.

### 7.6. Spring Java configuration

**`AppConfig.java`**

```java
package com.example.chain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    TaskService taskService() {
        return new TaskService();
    }

    @Bean
    OuterAspect outerAspect() {
        return new OuterAspect();
    }

    @Bean
    GateAspect gateAspect() {
        return new GateAspect();
    }

    @Bean
    InnerAspect innerAspect() {
        return new InnerAspect();
    }
}
```

`@Aspect` **không tự đăng ký Spring bean**. Ở đây, ba aspect beans được khai báo bằng `@Bean`, không cần `@Component` hoặc component scanning. `@EnableAspectJAutoProxy(proxyTargetClass=true)` bật Spring @AspectJ auto-proxy và cho phép lấy `TaskService` qua concrete type trong demo.

**Không cần ba proxy objects** để chạy ba aspects. Spring có thể kết hợp các advisors phù hợp trong AOP proxy của bean `taskService`.

### 7.7. Main và lệnh chạy

**`Main.java`**

```java
package com.example.chain;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService service = context.getBean(TaskService.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("case=normal");
            System.out.println("result=" + service.run("A"));

            System.out.println("case=exception");
            try {
                service.fail();
            } catch (IllegalStateException error) {
                System.out.println("caught=" + error.getMessage());
            }
        }
    }
}
```

Ở thư mục root của project, với Java 17+ và Gradle đã cài:

```bash
gradle run --quiet
```

Nếu project có Gradle Wrapper: `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

**Stdout của các lệnh `System.out` trong project** theo đúng thứ tự (không tính logging JVM/Spring/Gradle từ môi trường):

```text
proxy=true
case=normal
outer:enter:run
gate:before:run
inner:enter:run
target:run
inner:return:run
inner:finally:run
outer:return:run
outer:finally:run
result=ok:A
case=exception
outer:enter:fail
gate:before:fail
inner:enter:fail
target:fail
inner:throw:fail:IllegalStateException
inner:finally:fail
outer:throw:fail:IllegalStateException
outer:finally:fail
caught=boom
```

### 7.8. Giải thích từng dòng có tính quyết định

**Normal case:**

1. `outer:enter:run`: aspect `@Order(10)` đứng ngoài vào trước.
2. `gate:before:run`: `@Order(15)` được gọi khi chain tiến vào.
3. `inner:enter:run`: aspect `@Order(20)` vào sau nhưng trước target.
4. `target:run`: **target body chạy đúng một lần**.
5. `inner:return:run` và `inner:finally:run`: wrapper trong cùng hoàn tất chiều ra trước.
6. `outer:return:run` và `outer:finally:run`: wrapper ngoài cùng hoàn tất sau.
7. `result=ok:A`: caller nhận nguyên value do target trả, không bị aspects thay đổi.

**Exception case:**

1. Chuỗi enter giữ thứ tự `outer → gate → inner → target`.
2. `target:fail` ném `IllegalStateException("boom")`.
3. `InnerAspect` nhận exception trước, in `inner:throw` và `inner:finally` rồi ném lại.
4. `OuterAspect` nhận cùng exceptional flow, in `outer:throw` và `outer:finally` rồi ném lại.
5. Caller catch đúng `IllegalStateException` và in `caught=boom`.

**Điểm cần phân biệt:** Mỗi `@Around` in **hai hoặc ba dòng** cho một invocation, nhưng đó **không phải nhiều target calls**. Cùng exception đi qua hai layers nên được quan sát hai lần; không có bằng chứng target đã chạy hai lần.

### 7.9. Tại sao không dùng hai @Before không có @Order?

Nếu cả hai aspect đều có `@Before` và không có `@Order`, ứng dụng có thể in hai logs trước target, nhưng **thứ tự của hai logs không phải contract**. Demo cố ý dùng **ba `@Order` khác nhau** để stdout có lý do xác định rõ.

## 8. Khi hai advice trong cùng một @Aspect cùng khớp một method

Đây là câu hỏi **khác** với thứ tự giữa nhiều aspect classes.

Ví dụ minh họa:

```java
@Aspect
public class TwoBeforeAdvices {
    @Before("execution(* com.example.chain.TaskService.run(..))")
    public void first() {
        System.out.println("first");
    }

    @Before("execution(* com.example.chain.TaskService.run(..))")
    public void second() {
        System.out.println("second");
    }
}
```

Trong một class `@Aspect`, **hai advice cùng loại (`@Before`)** mà cùng match một join point **không có thứ tự được bảo đảm** chỉ vì `first` đứng trước `second` trong Java source. Java reflection không cung cấp declaration order ổn định mà Spring có thể dựa vào như một contract.

**Giải pháp khi cần thứ tự chắc chắn:**

- Gộp logic into **một `@Before` method** có thứ tự statements rõ ràng;
- Hoặc tách thành **hai `@Aspect` classes**, áp `@Order` khác nhau và test;
- Nếu là một flow có enter/exit phức tạp, cân nhắc một `@Around` method với `try/finally` theo contract rõ ràng.

Đoạn trên là **minh họa**, không thêm vào project demo mục 7 vì sẽ làm thay stdout.

### 8.1. Các advice khác loại trong cùng aspect

Spring Framework 6.2 mô tả precedence theo **loại advice** trong cùng `@Aspect`, từ cao xuống thấp:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

Tuy vậy, `@After` có semantics kiểu **after-finally**: trên thực tế nó được gọi **sau `@AfterReturning` hoặc `@AfterThrowing`** trong cùng aspect khi join point kết thúc. Đừng biến bảng precedence theo loại thành một danh sách thứ tự logging tuyến tính đơn giản từ trái sang phải; hãy xét **chiều vào/ra của interceptor chain**.

Hai advice **cùng loại trong cùng aspect** vẫn không có source-order guarantee. Đây là một chi tiết Spring-specific quan trọng khi refactor nhiều handlers ra chung một `@Aspect`.

### 8.2. Advice của cùng @Aspect có thể khác pointcut

Một `@Aspect` chứa nhiều `@Before` không có nghĩa **mọi** advice đó đều chạy cho mọi method. Cần xét từng expression:

```java
@Before("execution(* com.example.chain.TaskService.run(..))")
public void onRun() {}

@Before("execution(* com.example.chain.TaskService.fail(..))")
public void onFail() {}
```

Nếu caller gọi `run()`, advice chỉ nhắm `fail()` không match. Đừng nhầm thiếu event với vấn đề order khi pointcut thực sự không chọn join point.

## 9. Nhiều @AfterReturning và @AfterThrowing: phân biệt normal/exception

Khi các aspects khác nhau dùng các loại advice khác nhau, chính **outcome** quyết định advice nào đủ điều kiện được gọi:

| Advice | Normal return của target execution | Exceptional exit của target execution |
| --- | --- | --- |
| `@Before` | Có thể chạy trước target | Có thể chạy trước target |
| `@Around` | Có thể chạy cả trước/sau; có thể thay outcome | Có thể bắt/propagate/transform lỗi |
| `@AfterReturning` | Chạy nếu pointcut/return binding phù hợp | Không chạy khi join point thoát bằng exception |
| `@AfterThrowing` | Không chạy khi join point normal return | Chạy nếu exception/binding phù hợp |
| `@After` | Có semantics finally khi execution thoát | Có semantics finally khi execution thoát |

**Đừng suy rằng “aspect priority cao” khiến `@AfterReturning` chạy khi target throw lỗi.** Order không thay sự kiện mà loại advice lắng nghe.

### 9.1. Chữ ký advice có returning/throwing làm tập matches khác nhau

```java
@AfterReturning(
    pointcut = "execution(* com.example.chain.TaskService.*(..))",
    returning = "text",
    argNames = "text"
)
public void afterText(String text) {
    // ...
}
```

```java
@AfterThrowing(
    pointcut = "execution(* com.example.chain.TaskService.*(..))",
    throwing = "problem",
    argNames = "problem"
)
public void afterIllegalArgument(IllegalArgumentException problem) {
    // ...
}
```

Hai đoạn minh họa này có cùng `execution` scope nhưng **ràng buộc kiểu** khác nhau. `afterText` yêu cầu normal return tương thích `String`; `afterIllegalArgument` chỉ chạy trên exception kiểu `IllegalArgumentException`/subtype và **không** chạy cho `IllegalStateException` trong demo. Không phải mọi “advice không chạy” đều liên quan `@Order`.

### 9.2. @AfterThrowing không phải catch của các advice khác

Spring docs nhấn mạnh các distinct advice types của một aspect về mặt khái niệm áp lên **join point của target**; `@AfterThrowing` không nên được hiểu là một global catch handler cho exception do một `@After`/`@AfterReturning` method **khác trong cùng aspect** ném ra.

Nếu các advisors khác nhau ném/biến đổi lỗi, quá trình propagation còn phụ thuộc vị trí interceptor trong chain. Không tự động “sửa” bằng cách catch `Throwable` ở aspect ngoài rồi return `null`, vì điều đó có thể thay transaction/security semantics và làm mất lỗi gốc.

## 10. Quan hệ với Spring transaction, security, cache, async

Spring có nhiều infrastructure interceptors ngoài custom `@Aspect`. Khi cùng tác động lên một method, cần xem **advisor chain thực tế**, không tự đồng nhất “business aspects order” với “mọi framework component sẽ luôn tuân theo ba số order ví dụ”.

### 10.1. @Transactional và thứ tự với custom aspects

Một method:

```java
@Transactional
public void save(Order order) {
    // ...
}
```

Đây là **mã minh họa**; `Order` là domain type cần định nghĩa, và transaction management cần được bật riêng. Giả sử custom `@Around` ghi “success” khi `pjp.proceed()` normal return:

- Nếu aspect **bao ngoài transaction advisor**, `proceed()` của nó có thể bao gồm cả transaction interception (commit/rollback).
- Nếu aspect **nằm bên trong transaction advisor**, nó có thể thấy target return bình thường nhưng transaction commit xảy ra sau khi nó ra.
- Propagation, rollback rules, transaction manager và thứ tự advisor có thể thay kết quả.
- **Không dùng stdout `target:return` làm bằng chứng DB đã commit.**

Muốn side effect sau commit, dùng Spring transaction synchronization hoặc `@TransactionalEventListener(phase=AFTER_COMMIT)` theo cấu hình đúng. Không thay `@Order` một cách tùy hứng để “bảo đảm commit” khi chưa xác định transaction advisor order thực tế.

### 10.2. Method security và aspect có short-circuit

Nếu custom `@Around` precedence cao và **không gọi `proceed()`**, một method security interceptor **downstream** có thể không chạy. Điều này có thể vô tình bỏ qua `@PreAuthorize` hay policy khác, tùy thứ tự. Security-sensitive paths cần end-to-end tests cho access denied, bao gồm những nhánh cache/fallback/short-circuit.

Đừng gán một con số `@Order` bất kỳ cho custom security aspect rồi tự kết luận nó bảo vệ toàn bộ ứng dụng. Spring Security có cấu hình và advisors riêng; cần kiểm tra actual method security activation và proxy semantics.

### 10.3. Cache advisors

`@Cacheable` có thể trả giá trị từ cache mà không gọi target method. Nếu custom metrics aspect ở bên ngoài cache advisor, nó có thể thấy **proxy invocation** dù target không chạy; nếu ở bên trong, nó có thể không được gọi khi cache hit short-circuit. Đây là lý do số log entries của aspects có thể khác số target body executions **một cách hợp lệ**.

Nếu custom `@Around` tự cache/fallback, cẩn thận không cache một giá trị giả “success” từ lỗi backend nếu contract không cho phép.

### 10.4. @Async và Future/Publisher

`@Async`, `CompletableFuture` và reactive `Mono`/`Flux` làm thời điểm và thread execution phức tạp hơn. Thứ tự quan sát của logs giữa threads có thể xen kẽ, ngay cả khi precedence của các advisors trên **một invocation chain** rõ ràng. `@Around` có thể thấy **future/publisher wrapper return** trước khi computation/subscription kết thúc.

Không dùng một ví dụ đồng bộ như `TaskService.run()` để tuyên bố thứ tự logs toàn cục giữa nhiều threads hoặc success cuối cùng của các asynchronous tasks.

## 11. Self-invocation và các giới hạn Spring proxy

`@Order` chỉ có ý nghĩa khi Spring AOP thực sự intercept invocation.

### 11.1. Self-invocation vẫn bypass

```java
public class TaskService {
    public String outer() {
        return this.run("A"); // call nội bộ trên target
    }

    public String run(String id) {
        return "ok:" + id;
    }
}
```

Nếu target đã nhận call `outer()` thông qua proxy, lời gọi `this.run()` ở bên trong target **không quay lại proxy**. Do đó các advices nhắm `run(..)` không tự chạy thêm, dù mỗi aspect có `@Order` rõ ràng. Muốn advice trên `run`, gọi qua Spring proxy từ bean khác hoặc refactor phần cần interception sang collaborator bean.

### 11.2. JDK proxy và CGLIB

- Với **JDK dynamic proxy**, caller dùng interface method được proxy expose; implementation class có thể final nếu chọn interface proxy phù hợp.
- Với **CGLIB**, class phải subclass được và method cần advice phải override được; `final` class/method tạo giới hạn.
- `@EnableAspectJAutoProxy(proxyTargetClass=true)` chọn class proxy cho demo; nó **không sửa self-invocation**.
- `private` method không phải entry interceptable thông thường của Spring AOP proxy.
- Constructor, field read/write và AspectJ compiler weaving join points không được tự động hỗ trợ bởi Spring proxy AOP.
- Spring `@AspectJ` uses AspectJ annotation syntax nhưng runtime interception vẫn là Spring proxy.

### 11.3. Không dùng new target khi test

```java
TaskService service = new TaskService();
service.run("A");
```

Đây là Java object thuần, không phải Spring AOP proxy; không có advices chạy. Khi test thứ tự Spring aspects, luôn nhận target bean từ `ApplicationContext`/dependency injection và gọi qua proxy.

## 12. Những lỗi chẩn đoán dễ gặp

| Dấu hiệu | Kết luận dễ sai | Cách giải thích trong Spring |
| --- | --- | --- |
| Hai aspects đều có `@Before` | “Theo thứ tự khai báo source” | Không có guarantee khi không đặt precedence. |
| `@Order(10)` in log cuối | “Order bị đảo nên cấu hình sai” | Trong **chiều ra**, aspect precedence cao chạy **sau** aspect thấp hơn. |
| Có ba log entry nhưng một target log | “Target chạy ba lần” | Một target execution có thể đi qua nhiều advice; logs không phải target call count. |
| Aspect A không in gì | “Spring bỏ qua @Order” | Có thể pointcut không match, aspect chưa là bean, caller bypass proxy hoặc A outer short-circuit. |
| `@AfterReturning` không chạy khi exception | “Order của advice quá thấp” | Không có normal return; dùng `@AfterThrowing` cho exceptional exit. |
| Hai `@Before` trong cùng aspect đổi thứ tự ngẫu nhiên | “Cần đổi tên Java methods” | Cùng advice type không có source-order guarantee; tách aspects hoặc gộp logic. |
| Cache hit không có target log | “Target/Aspect bị Spring lỗi” | Cache interceptor có thể short-circuit; xem advisor precedence. |
| Outer `@Around` return null khi lỗi | “Logging vẫn thành công” | Có thể đã nuốt exception, thay contract và behavior transaction/security. |
| Aspect in success trước DB commit | “DB transaction chắc chắn thành công” | Thời điểm phụ thuộc vị trí transaction advisor; success log không bảo đảm commit. |
| Request có nhiều log lines | “Có nhiều HTTP requests” | Một invocation qua nhiều aspects tạo nhiều events. |
| Bean là proxy nhưng method không advice | “AOP proxy hỏng” | Pointcut, final/private, interface visibility và self-call cần kiểm tra. |
| Aspects có cùng order nhưng local chạy ổn | “Thứ tự được đảm bảo” | Equal precedence không phải contract trong mọi Spring setups. |

## 13. Debug một Spring AOP chain khi thứ tự khác kỳ vọng

### 13.1. Xác nhận proxy loại nào

```java
TaskService bean = context.getBean(TaskService.class);
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Đoạn minh họa dùng context của demo và import `org.springframework.aop.support.AopUtils`. Trong demo, cả hai là `true` do `proxyTargetClass=true` và method pointcut match.

**Proxy tồn tại không chứng minh một advice cụ thể match.** Dùng event recorder hoặc log có tên aspect/method để xác nhận mỗi advice thực thi.

### 13.2. Kiểm tra order value runtime

Có thể log hoặc inspect `@Order` trên các aspect classes hoặc `Ordered.getOrder()` khi aspects implement interface. Khi hạ tầng có nhiều advisors, muốn xem advisor list thường có thể inspect Spring `Advised` proxy:

```java
import org.springframework.aop.framework.Advised;

Object bean = context.getBean("taskService");
if (bean instanceof Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

Đây là **đoạn chẩn đoán minh họa**, không thêm vào `Main` nếu muốn giữ stdout ở mục 7.7. Advisor list giúp điều tra chuỗi proxy và hạ tầng, nhưng không tự chứng minh toàn bộ dynamic pointcut conditions match trên một invocation. Một advisor có thể match method theo static filter và cần runtime checks để advice chạy. Không nên mutate advisor list trong production chỉ để thử order.

### 13.3. Dùng event recorder thay vì log lẫn nhiều threads

Một recorder cho demo đồng bộ:

```java
public final class EventRecorder {
    private final java.util.List<String> events =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public java.util.List<String> snapshot() {
        return java.util.List.copyOf(events);
    }
}
```

Đây là **một Java class minh họa độc lập**, nếu gắn vào project demo cần đăng ký recorder làm Spring bean và inject vào aspects. Sử dụng một recorder giúp test thứ tự chính xác hơn so với đọc console có nhiều sources.

Trong async/multithread environment, mỗi invocation nên có **correlation ID** riêng; `CopyOnWriteArrayList` thread-safe cho writes nhưng không biến event order giữa concurrent invocations thành một thứ tự tổng quát bảo đảm.

### 13.4. Kiểm tra pointcut matching

Xem các biểu thức `execution(...)`, `within(...)`, `@annotation(...)`, `bean(...)`; lưu ý `bean(...)` là extension Spring AOP, không hỗ trợ toàn bộ AspectJ language. Với pointcut phụ thuộc annotation/args, method được gọi phải thực sự mang metadata/arguments tương ứng.

Nếu aspect chưa được Spring register, thêm `@Aspect` không đủ: dùng `@Component` + component scan đúng package hoặc `@Bean` trong config. Với Spring Framework Java config, bật `@EnableAspectJAutoProxy` đúng context và có `aspectjweaver`.

## 14. Quy trình kiểm thử integration cho nhiều aspects

### 14.1. Các assertion cần có

Một integration test tốt nên chứng minh:

1. Spring trả về **proxy** cho target.
2. Cả ba aspects được Spring đăng ký và pointcuts thực sự match.
3. Đường normal return có thứ tự `outer enter → gate before → inner enter → target → inner return/finally → outer return/finally`.
4. Đường exceptional exit có thứ tự `outer enter → gate before → inner enter → target throw → inner catch/finally → outer catch/finally`.
5. Caller thấy result/exception gốc khi advices không được quyền thay outcome.
6. Khi đổi `@Order` có chủ đích, thứ tự kỳ vọng thay đổi theo contract.
7. Caller không qua proxy hoặc self-invocation không tạo thêm interception.
8. Aspects khác pointcut không được chạy ngoài ý muốn.
9. Test được trên Spring Framework/Boot version và proxy mode giống production.

### 14.2. Đối chiếu một output mẫu

Trong code demo, `Main` in stdout chi tiết. Một test có thể thay `System.out` trong advices bằng recorder để assert danh sách events. **Không dựa vào một substring “outer” hay số dòng log tổng**, vì hai `@Around` đều có multiple exit events.

Ví dụ expectation cho normal call:

```java
List<String> expected = List.of(
    "outer:enter:run",
    "gate:before:run",
    "inner:enter:run",
    "target:run",
    "inner:return:run",
    "inner:finally:run",
    "outer:return:run",
    "outer:finally:run"
);
```

Đoạn này **minh họa assertion data**, cần import `java.util.List`, recorder và một target method dùng recorder thay `System.out`. Không tự copy vào `Main` đang chạy nếu không có biến `expected` được sử dụng và binding tới events thực tế.

### 14.3. Test exception identity khi contract yêu cầu

Với `OuterAspect` và `InnerAspect` đều thực hiện `throw error;`, exception từ target có thể giữ identity xuyên chain khi không interceptor khác wrap. Một fixture Spring test riêng có thể cho target ném một `IllegalStateException` đã tạo sẵn và assert caller catch đúng object ấy (`==`), đồng thời assert order events.

Nhưng nhớ: trong production, JDK interface proxies, transactions hoặc library interceptors khác có thể wrap/mapping exceptions theo contract; test phải xét thực tế thay vì khẳng định mọi Spring AOP scenario đều giữ object identity bất kể chain.

### 14.4. Test với transaction hoặc method security

Nếu method có `@Transactional` hay `@PreAuthorize`, hãy thêm integration tests với các cấu hình activation thực, không chỉ load `@EnableAspectJAutoProxy`. Thử cả success/failure, rollback/commit, unauthorized caller, cache hit và short-circuit. Quan sát advisor ordering thực tế thay vì suy từ 10, 15, 20 của ví dụ thuần AOP.

## 15. Spring Boot và việc phối hợp nhiều aspects

Trong Spring Boot, khi AOP starter/auto-configuration phù hợp, thường không cần tự khai báo `@EnableAspectJAutoProxy`. Nhưng:

- Mỗi class `@Aspect` có advice phải là **Spring bean** (thường thêm `@Component` hoặc dùng `@Bean`).
- Dùng `@Order` trên aspect classes khi cần precedence giữa nhiều aspects.
- Đặt pointcut đủ hẹp để không proxy nhầm bean hạ tầng và không tăng overhead toàn hệ thống.
- Cấu hình `spring.aop.proxy-target-class` có thể ảnh hưởng JDK vs CGLIB proxy, đặc biệt với final methods hoặc interface injection.
- Transaction, caching, async và method security có infrastructures/activation và advisor precedence riêng; không bảo đảm custom aspect luôn “bọc” hay “bên trong” chúng chỉ bằng cách đặt một order value tùy ý.
- Khi có request concurrency, thứ tự events giữa **các invocation khác nhau** không được suy từ thứ tự advisors trong **một invocation**.

Dependency Gradle lựa chọn theo Boot major và dependency management (hai dòng là phương án riêng):

```gradle
// Spring Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Spring Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

Không thêm đồng thời cả hai nếu không có thiết kế dependency cụ thể. Khi Boot cung cấp BOM, để Boot chọn version Spring modules phù hợp, không cố trộn `6.2.19` với các version không tương thích.

### Khi dùng @Order và @Priority

Với Spring AOP aspects, tài liệu Spring mô tả `@Order` hoặc `Ordered` cho precedence. Đừng nhầm nó với `@Priority` của Java/Jakarta mà không kiểm tra cách Spring infrastructure cụ thể đọc annotation. Khi test, cách dễ chứng minh nhất vẫn là **quan sát actual advisor chain và event order**.

## 16. Checklist review trước khi đưa vào production

- [ ] Có thật sự **nhiều Spring `@Aspect` beans** có advice match cùng một target method?
- [ ] Target method được gọi **qua Spring proxy**, không phải `new`/self-invocation?
- [ ] Mỗi aspect được đăng ký bean bằng `@Component`/`@Bean` và Spring AOP @AspectJ support bật đúng context?
- [ ] Các pointcut expressions nhắm đúng target package/type/method và không match quá rộng?
- [ ] Nếu order quan trọng, aspects có `@Order` khác nhau hoặc `Ordered` rõ ràng?
- [ ] Hiểu **số nhỏ precedence cao**; vào trước nhưng ra sau khi dùng wrapper `@Around`?
- [ ] Không dựa vào source declaration order, bean registration order hoặc tên class để suy thứ tự?
- [ ] Không suy hai advice cùng loại trong cùng một aspect có thứ tự cố định?
- [ ] `@Around` downstream call `proceed()` đúng số lần theo contract, không short-circuit/retry ngoài dự tính?
- [ ] `@AfterReturning` chỉ quan sát normal return, `@AfterThrowing` chỉ exceptional exit đúng kiểu?
- [ ] Khi advice tự ném lỗi hoặc chuyển return, đã test semantics với transaction/security/cache advisors?
- [ ] Đã xem precedence của infrastructure interceptors thực tế thay vì áp quy tắc 10/15/20 máy móc?
- [ ] Với JDK/CGLIB proxy, method entry có expose/override được, class final/visibility phù hợp?
- [ ] Từng invocation có event correlation để tránh nhầm thứ tự concurrency với precedence?
- [ ] Integration tests bao gồm cả return lẫn exception, thứ tự events và contract return/throw?
- [ ] Không coi số lần advice chạy đồng nghĩa số lần target business logic được thực thi?

**Ghi nhớ:** Trong **Spring AOP**, nhiều aspects cùng match một method được Spring đưa vào **một invocation chain của proxy**. Khi cần kiểm soát thứ tự giữa các aspects, **`@Order` số nhỏ có precedence cao**: chạy trước khi đi vào target và **sau trên đường ra**. Thứ tự đó không làm pointcut match thêm, không ép `@Around` phải `proceed()`, không giải quyết self-invocation và không thay semantics của normal/exception outcomes. Mọi giả định về order phải được xác nhận trên **Spring proxy và advisors thực tế**.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Declaring Advice: Advice Ordering và nhiều advice cùng join point](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Declaring Pointcuts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Proxying Mechanisms, JDK/CGLIB và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Schema-based AOP Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html)
- [Spring Framework 6.2 — Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
