# @Around và vai trò ProceedingJoinPoint trong Spring AOP

## 1. @Around giải quyết điều gì trong Spring Aspect?

Trong Spring AOP, một `@Aspect` có thể chạy code trước hoặc sau một method của **Spring bean được proxy**. Nếu chỉ cần ghi log trước method, `@Before` thường đủ. Nếu chỉ cần xem kết quả bình thường, có `@AfterReturning`. Nhưng khi muốn **bao cả quá trình gọi**, giữ trạng thái cục bộ trước–sau, quyết định có cho target chạy hay không, thay tham số, thay giá trị trả về hoặc xử lý exception theo chính sách rõ ràng, ta sử dụng **`@Around`**.

Ví dụ một Spring service có phương thức `find(String key)`:
- Có thể đo thời gian của toàn bộ lời gọi và in thời gian ở `finally`.
- Có thể trả trực tiếp một kết quả đã cache mà **không gọi** service target.
- Có thể chuẩn hóa tham số trước khi gọi target bằng `proceed(newArgs)`.
- Có thể để nguyên exception hoặc, khi nghiệp vụ cho phép, biến exception thành một kết quả fallback.
- Có thể dùng retry có kiểm soát, mặc dù thực tế nên đánh giá một cơ chế retry chuyên trách.

**Khác biệt cốt lõi** của `@Around` nằm ở đối tượng **`ProceedingJoinPoint`** và lời gọi **`proceed()`**. Không có `proceed()` thì Spring AOP interceptor chain ở phía trong sẽ không tự đi tiếp chỉ vì method target đã được khai báo.

Tuy nhiên, `@Around` cũng là loại advice có quyền can thiệp mạnh nhất, do đó dễ tạo bug nhất. Tài liệu Spring khuyên **chọn loại advice ít quyền nhất mà vẫn đáp ứng nhu cầu**. Bài này chỉ tập trung vào `@Around` trong **Spring Framework, Spring `@AspectJ` và cơ chế proxy**, không mở rộng sang bytecode weaving hoặc các join point ngoài method execution.

### Mục tiêu học tập

Sau bài này, bạn sẽ:
1. Giải thích vị trí `@Around` trong Spring AOP interceptor chain.
2. Viết method advice có `ProceedingJoinPoint` đứng đầu, trả `Object` và khai báo `throws Throwable`.
3. Phân biệt `proceed()`, `proceed(Object[])` và `getArgs()`.
4. Hiểu hậu quả của việc gọi `proceed()` **0 lần, 1 lần hoặc nhiều lần**.
5. Phân biệt việc target hoàn tất với kết quả cuối cùng mà client của proxy nhận được.
6. Sử dụng `try/catch/finally` chính xác khi đo thời gian, ghi log, bắt và truyền exception.
7. Chạy ví dụ Java 17 + Spring Framework để quan sát cả bình thường, thay argument, short-circuit, throw và self-invocation.
8. Tránh các lỗi quan trọng khi phối hợp `@Around` với transaction, cache, retry và các Spring advisors khác.

## 2. @Around ở vị trí nào trong Spring AOP?

Spring AOP áp dụng advice cho **method-execution join point** của Spring-managed bean bằng JDK dynamic proxy hoặc CGLIB proxy. Một đường gọi được đơn giản hóa như sau:

```text
Client
  |
  v
Spring AOP proxy
  |
  v
@Around advice
  |
  +-- code BEFORE proceed()
  |
  +-- pjp.proceed() ------------------------------+
  |                                               |
  |                                      các advisors phía trong
  |                                               |
  |                                               v
  |                                         target.method(...)
  |                                               |
  |                               return value hoặc exception
  |                                               |
  +<----------------------------------------------+
  |
  +-- code AFTER proceed() (khi return bình thường)
  +-- catch (khi exception đi qua)
  +-- finally (cả hai đường)
  |
  v
Client thấy value/exception mà advice cho đi ra ngoài
```

Hình này cho thấy hai ý nghĩa của "around":

- **Bao quanh về thời gian:** advice có thể chạy trước, rồi chạy sau invocation.
- **Bao quanh về quyền điều khiển:** advice quyết định có gọi phần bên trong của interceptor chain không, gọi với đối số nào và trả kết quả gì.

Lời gọi `proceed()` **không phải** cú pháp Java để gọi trực tiếp `target.method()`. Trong Spring, nó tiếp tục phần còn lại của **AOP interceptor chain**, có thể gồm nhiều advisors khác trước khi tới method target. Vì thế kết quả/exception của `proceed()` đôi khi đã bị một interceptor phía trong thay đổi hoặc short-circuit.

### 2.1. Điều kiện tiên quyết

Để `@Around` có hiệu lực trong một ứng dụng Spring Framework thuần:

- Lớp khai báo advice phải có `@Aspect` và được **đăng ký thành Spring bean** (qua `@Component`, `@Bean` hoặc tương đương).
- `@EnableAspectJAutoProxy` phải được áp dụng trong `ApplicationContext` tạo bean target, hoặc dùng Spring Boot AOP auto-configuration tương ứng.
- Các thư viện AspectJ cần thiết để Spring phân tích pointcut phải có trên classpath (thường cung cấp qua `spring-boot-starter-aop` hoặc `aspectjweaver`).
- Bean target phải được Spring quản lý, có method khớp pointcut và được gọi **qua AOP proxy**.
- JDK/CGLIB proxy phải có khả năng intercept method tương ứng; self-invocation, `final`/`private` methods có thể khiến advice không hoạt động như kỳ vọng.

`@Aspect` **không tự đăng ký Spring component**, và một method chỉ được gắn `@Around` mà thiếu hạ tầng Spring AOP cũng không tự chạy.

## 3. Cấu trúc chuẩn của @Around advice

Mẫu thông dụng:

```java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TimingAspect {

    @Around("execution(* com.example.service..*.*(..))")
    public Object measure(ProceedingJoinPoint pjp) throws Throwable {
        long started = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            long elapsedNanos = System.nanoTime() - started;
            System.out.println("elapsedNs=" + elapsedNanos);
        }
    }
}
```

Đây là **snippet minh họa**, không phải ứng dụng độc lập. Cần các Spring beans và cấu hình AOP phù hợp; `elapsedNs` sẽ khác ở mỗi lần chạy nên không được coi là stdout cố định.

### 3.1. Tại sao tham số đầu là ProceedingJoinPoint?

Spring yêu cầu first parameter của `@Around` advice có kiểu **`org.aspectj.lang.ProceedingJoinPoint`**. Nó mở rộng `JoinPoint` và bổ sung khả năng `proceed()`. Các advice như `@Before` có thể nhận `JoinPoint` để đọc ngữ cảnh nhưng không có quyền gọi tiếp theo cách của `ProceedingJoinPoint`.

### 3.2. Tại sao trả Object?

Tài liệu Spring khuyến nghị around advice trả `Object` vì giá trị **do advice trả** trở thành giá trị mà caller của method được proxy nhìn thấy. Ví dụ:

```java
Object result = pjp.proceed();
return result;
```

là cách giữ nguyên giá trị trả về khi không cần biến đổi.

**Không khai báo around advice trả `void` nếu method target cần giá trị trả về:** Spring lưu ý advice có kiểu trả `void` khiến caller nhận `null`, dù target đã trả giá trị. Điều này có thể gây lỗi khó hiểu khi caller mong `String`, `Integer` hoặc một object khác.

Một advice `Object` có thể bao quanh cả method target `void`; lúc đó kết quả hợp lý khi dùng `proceed()` thường được biểu diễn là `null` trong interceptor. Code nên giữ nguyên `return pjp.proceed();` và không tự suy diễn nó thành một giá trị nghiệp vụ.

### 3.3. Tại sao throws Throwable?

`proceed()` khai báo `throws Throwable`. Advice thường cũng khai báo `throws Throwable` để truyền nguyên exception ra ngoài:

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

Việc chỉ khai báo `throws Exception` không thể bao quát đầy đủ `Throwable` theo signature mà compiler cần, trừ khi bạn tự bắt/xử lý phần còn lại.

### 3.4. Method trả về hoặc ném exception gì?

Trong `@Around`, ba trường hợp cần phân biệt:

| Hành vi advice | Target hoặc interceptor chain phía trong | Caller bên ngoài proxy |
| --- | --- | --- |
| `return pjp.proceed();` | Chạy phần chain phía trong, trừ khi một advisor khác short-circuit | Nhận value/exception được truyền qua |
| `return "CACHED";` không gọi `proceed()` | Không đi vào phần chain phía trong | Nhận `"CACHED"` nếu phù hợp return contract |
| `throw ex;` trong advice | Có thể target chưa chạy hoặc đã ném ex | Caller thấy exception do advice đưa ra |
| `return transform(pjp.proceed());` | Chain có thể chạy, sau đó advice đổi kết quả | Caller nhận kết quả đã chuyển đổi |
| Catch exception rồi `return fallback` | Chain đã chạy đến nơi ném exception; advice chuyển outcome | Caller có thể thấy normal return thay vì exception |

**Giữ đúng hợp đồng Java method:** Nếu target method trả `int`, trả `null` từ advice có thể gây lỗi unboxing. Nếu target method trả `String`, trả object không tương thích có thể gây `ClassCastException`. Spring không tự bảo đảm fallback của bạn có kiểu nghiệp vụ hợp lệ.

## 4. ProceedingJoinPoint cung cấp những gì?

### 4.1. Các API thường dùng

| API | Ý nghĩa trong Spring AOP | Lưu ý |
| --- | --- | --- |
| `pjp.proceed()` | Tiếp tục invocation bằng các argument gốc | Gọi khi muốn phần chain phía trong chạy |
| `pjp.proceed(Object[] args)` | Tiếp tục với **bộ argument được cung cấp** | Trong Spring AOP, số lượng và vị trí phải phù hợp method execution |
| `pjp.getArgs()` | Các argument hiện có của method invocation | Không cần reflection để biết argument |
| `pjp.getSignature()` | Thông tin chữ ký method | Có thể dùng `getName()`, hoặc ép kiểu sang `MethodSignature` |
| `pjp.getThis()` | Đối tượng Spring AOP proxy | Khác `getTarget()`, nhất là JDK proxy |
| `pjp.getTarget()` | Target object phía sau proxy | Không gọi method trực tiếp trên nó nếu muốn giữ advice |
| `pjp.getStaticPart()` | Thông tin tĩnh của join point | Phù hợp khi không cần giữ object context |
| `pjp.toShortString()` / `toString()` | Mô tả join point | Phục vụ chẩn đoán, đừng phụ thuộc format log bất biến |

Trong Spring, `getThis()` là **proxy object** và `getTarget()` là **target object**. Chúng có thể khác cả identity lẫn runtime class. Ví dụ JDK proxy chỉ implement interface, còn target là instance của implementation class.

### 4.2. Đọc tên method và argument

```java
@Around("execution(* com.example.service..*.*(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    String name = pjp.getSignature().getName();
    Object[] args = pjp.getArgs();

    System.out.println("method=" + name + ", args=" + args.length);
    return pjp.proceed();
}
```

Đây là snippet cần đặt trong lớp `@Aspect` và đăng ký vào context. `getArgs()` cho phép đọc dữ liệu, nhưng **không nên log dữ liệu bí mật** như token, mật khẩu, thông tin cá nhân, thẻ thanh toán hoặc object chứa payload lớn. Với các hệ thống xử lý dữ liệu nhạy cảm, log định danh an toàn hoặc kiểu dữ liệu thay vì in toàn bộ argument values.

### 4.3. Đọc chữ ký typed

```java
import org.aspectj.lang.reflect.MethodSignature;

MethodSignature signature = (MethodSignature) pjp.getSignature();
String methodName = signature.getMethod().getName();
Class<?> returnType = signature.getReturnType();
Class<?>[] parameterTypes = signature.getParameterTypes();
```

Snippet trên nằm trong `@Around` advice; các giá trị dùng để chẩn đoán khi cần biết signature. Khi method được khai báo trên interface nhưng annotation nằm trên implementation, cần cân nhắc Spring method resolution và proxy type; đừng giả định method phản chiếu từ proxy luôn là method implementation có đầy đủ annotation như source code.

## 5. proceed(): đi tiếp một lần, không đi tiếp, hoặc đi tiếp nhiều lần

`ProceedingJoinPoint.proceed()` **tiếp tục phần interceptor chain nằm bên trong advice đang chạy**. Nó không nhất thiết gọi target ngay: một advice phía trong còn có thể trả kết quả sớm, hoặc ném ngoại lệ.

| Số lần gọi | Điều xảy ra với phần chain phía trong | Cần lưu ý |
| --- | --- | --- |
| **Một lần** | Chuyển tiếp một lượt; thường đến target nếu không bị interceptor khác chặn | Đây là cách mặc định khi chỉ muốn quan sát hoặc đo lường |
| **Không lần nào** | Không đi tiếp qua nhánh invocation này | Advice phải trả giá trị phù hợp với contract hoặc chủ động ném ngoại lệ; ví dụ cache hit/authorization gate |
| **Nhiều lần** | Có thể chạy lại các interceptor phía trong và target theo từng lượt | Chỉ phù hợp với retry/replay có giới hạn, điều kiện lỗi rõ và side effect an toàn |

Ví dụ một advice chỉ quan sát mà không thay nghiệp vụ:

~~~java
@Around("execution(* demo.GreetingService.greet(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("enter");
    return pjp.proceed();
}
~~~

Đây là fragment cần nằm trong `@Aspect` do Spring quản lý. Nếu target ném exception, `proceed()` truyền lỗi ra caller; nó không âm thầm chuyển thành kết quả mặc định. Bài về việc tiếp tục chuỗi đi sâu vào một lượt; bài về short-circuit và nhiều lượt giải thích riêng ảnh hưởng lên advisor, target và các tác dụng phụ.

## 6. proceed(Object[]): thay argument khi gọi

Overload `pjp.proceed(Object[] replacement)` cho phép Spring AOP **chuyển tiếp invocation với argument mới**. Trong Spring AOP dựa trên proxy, mảng này tương ứng đầy đủ với các tham số của method đích, theo đúng thứ tự và kiểu tương thích; không phải mảng gồm các biến được bind trong chữ ký advice.

Ví dụ trong `@Around` advice dành riêng cho method có tham số đầu là `String`:

~~~java
Object[] oldArgs = pjp.getArgs();
Object[] nextArgs = oldArgs.clone();
nextArgs[0] = ((String) oldArgs[0]).trim();
return pjp.proceed(nextArgs);
~~~

Nếu method nhận `(String, int)`, mảng chuyển tiếp vẫn cần **hai phần tử** và phần tử thứ hai phải tương thích `int` (thường là `Integer` boxed). `clone()` chỉ sao chép mảng nông; nó không sao chép các object mutable bên trong. Quy tắc argument binding của AspectJ compiler/weaver có thể khác Spring proxy AOP, nên không mang nguyên ví dụ qua hai cơ chế mà thiếu kiểm chứng. Bài `proceed(Object[])` chuyên sâu sẽ xử lý arity, binding và các trường hợp sai kiểu.

## 7. return, throw, catch và finally trong @Around

Giá trị mà `@Around` trả về trở thành kết quả caller quan sát tại ranh giới proxy. Với mục tiêu quan sát thuần túy, **trả đúng giá trị của `proceed()` và để ngoại lệ truyền đi** là lựa chọn an toàn; đừng vô tình trả `null` cho một method `int` hoặc làm mất thông tin lỗi.

Khi cần cleanup hoặc đo latency cho cả đường thành công và thất bại, bao `proceed()` bằng `try/finally`:

~~~java
long start = System.nanoTime();
try {
    return pjp.proceed();
} finally {
    long elapsedNs = System.nanoTime() - start;
    System.out.println("elapsedNs=" + elapsedNs);
}
~~~

Đây là fragment đo thời gian; số nanosecond không cố định. `finally` chạy khi phần `try` đã được vào và `proceed()` trả hoặc ném exception, nhưng bản thân code trong `finally` cũng phải được thiết kế để không làm hỏng outcome nghiệp vụ.

`catch` chỉ nên chuyển lỗi thành fallback khi **hợp đồng method cho phép** và loại lỗi đó đã được quy định rõ. Trả fallback sẽ khiến các interceptor phía ngoài nhìn thấy normal return thay vì exception. Các bài về return contract, `try/catch/finally` và chống nuốt ngoại lệ sẽ lần lượt phân tích hệ quả với primitive, checked exception và transaction.

## 8. Ví dụ chạy độc lập: năm tình huống rõ ràng

### 8.1. Mục tiêu và môi trường

Project sau dùng **Java 17+**, **Spring Framework 6.1.14**, **AspectJ Weaver 1.9.22.1** và Gradle; không cần Spring Boot hay database. Một aspect xử lý chính xác một `GreetingService` bean với các trường hợp:

1. `greet("Bob")`: gọi `proceed()` bình thường.
2. `greet("alias")`: thay input bằng `"Alice"` khi gọi `proceed(Object[])`.
3. `greet("skip")`: trả `"SKIPPED"` mà không gọi target.
4. `fail()`: target ném `IllegalStateException`, aspect log rồi rethrow.
5. `outer()`: gọi nội bộ `this.greet("inside")` nên không phát sinh `@Around` lần hai cho lời gọi bên trong.

Log được thiết kế **deterministic**, không in duration thay đổi theo môi trường; dễ so với stdout dự kiến.

### 8.2. Cấu trúc project

```text
spring-around-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/around/
    ├── GreetingService.java
    ├── AroundAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 8.3. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'spring-around-demo'
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
    mainClass = 'demo.around.DemoApplication'
}
```

`spring-context` cung cấp IoC, `AnnotationConfigApplicationContext`, `@Bean` và `@Configuration`; `spring-aop` chứa proxying infrastructure; `aspectjweaver` là thư viện cần để Spring phân tích `@AspectJ` pointcut.

### 8.4. Service target

Tệp `src/main/java/demo/around/GreetingService.java`:

```java
package demo.around;

public class GreetingService {

    public String greet(String name) {
        System.out.println("target:greet:" + name);
        return "Hello " + name;
    }

    public void fail() {
        System.out.println("target:fail");
        throw new IllegalStateException("boom");
    }

    public void outer() {
        System.out.println("target:outer");
        greet("inside");
    }
}
```

`greet`, `fail` và `outer` đều public và non-final, có thể được class-based proxy advise nếu đi qua proxy. Dòng `greet("inside")` trong `outer` là **self-invocation** của target; nó không quay lại proxy.

### 8.5. @Around aspect và ProceedingJoinPoint

Tệp `src/main/java/demo/around/AroundAspect.java`:

```java
package demo.around;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class AroundAspect {

    @Around("execution(public * demo.around.GreetingService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("around:before:" + method);

        try {
            if ("greet".equals(method)
                    && "skip".equals(pjp.getArgs()[0])) {
                System.out.println("around:short-circuit:greet");
                return "SKIPPED";
            }

            Object result;
            if ("greet".equals(method)
                    && "alias".equals(pjp.getArgs()[0])) {

                Object[] newArgs = pjp.getArgs().clone();
                newArgs[0] = "Alice";
                result = pjp.proceed(newArgs);
            } else {
                result = pjp.proceed();
            }

            System.out.println("around:after:" + method);
            return result;
        } catch (Throwable ex) {
            System.out.println("around:throw:" + method
                    + ":" + ex.getClass().getSimpleName());
            throw ex;
        } finally {
            System.out.println("around:finally:" + method);
        }
    }
}
```

**Vì sao đoạn code an toàn trong phạm vi demo:**
- `method.equals("greet")` được biểu diễn bằng `"greet".equals(method)` và điều kiện `&&` short-circuit, nên code chỉ truy cập `pjp.getArgs()[0]` cho `greet`, method có một parameter. `fail`/`outer` không truy cập index không tồn tại.
- `"skip"` trả trực tiếp trước `proceed`; `finally` vẫn chạy bởi Java semantics.
- `"alias"` tạo một bản sao mảng argument rồi gọi `proceed(newArgs)`; target nhận `"Alice"` dù caller truyền `"alias"`.
- Case thông thường gọi `proceed()` đúng một lần và giữ nguyên result.
- Case target throw được catch để log, sau đó rethrow; advice không nuốt exception.
- `finally` in một dòng cho mọi đường return/throw mà advice thực sự đã tham gia.
- Pointcut chỉ áp dụng cho `GreetingService`, không tự advise `AroundAspect` hoặc Spring infrastructure.

Trong production, đừng rẽ nhánh theo string method name kiểu demo để thực hiện chính sách khác nhau; hãy dùng **named pointcuts, method annotation hoặc advisor riêng**. Demo cố tình gom các nhánh vào một advice để người học nhìn thấy từng khả năng của `ProceedingJoinPoint`.

### 8.6. Đăng ký Spring beans và bật AOP

Tệp `src/main/java/demo/around/AppConfig.java`:

```java
package demo.around;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }

    @Bean
    public AroundAspect aroundAspect() {
        return new AroundAspect();
    }
}
```

`@Bean aroundAspect()` đăng ký aspect thành Spring bean; `@Aspect` nói với Spring cách đọc advice. `@EnableAspectJAutoProxy(proxyTargetClass=true)` bật auto-proxy creator và ưu tiên proxy theo lớp, nhờ đó ta lấy service theo `GreetingService.class`. Đây là Spring Framework thuần, nên không phụ thuộc mặc định của Spring Boot.

### 8.7. Main chạy các nhánh

Tệp `src/main/java/demo/around/DemoApplication.java`:

```java
package demo.around;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            GreetingService service =
                    context.getBean(GreetingService.class);

            System.out.println(
                    "proxy=" + AopUtils.isAopProxy(service));

            System.out.println("result=" + service.greet("Bob"));
            System.out.println("result=" + service.greet("alias"));
            System.out.println("result=" + service.greet("skip"));

            try {
                service.fail();
            } catch (IllegalStateException ex) {
                System.out.println(
                    "caller:fail:" + ex.getMessage());
            }

            service.outer();
        }
    }
}
```

### 8.8. Lệnh chạy và stdout chính xác

Từ thư mục chứa `build.gradle`:

```bash
gradle run
```

Nếu đã có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

Các dòng bên dưới là **output do chương trình Java tự in**, không tính Gradle hoặc logging hệ thống:

```text
proxy=true
around:before:greet
target:greet:Bob
around:after:greet
around:finally:greet
result=Hello Bob
around:before:greet
target:greet:Alice
around:after:greet
around:finally:greet
result=Hello Alice
around:before:greet
around:short-circuit:greet
around:finally:greet
result=SKIPPED
around:before:fail
target:fail
around:throw:fail:IllegalStateException
around:finally:fail
caller:fail:boom
around:before:outer
target:outer
target:greet:inside
around:after:outer
around:finally:outer
```

### 8.9. Đối chiếu từng lời gọi với proceed

| Caller gọi | Advice thực hiện | Target có chạy? | Caller nhìn thấy |
| --- | --- | --- | --- |
| `greet("Bob")` | `proceed()` với args gốc | Có: `target:greet:Bob` | `Hello Bob` |
| `greet("alias")` | `proceed(new Object[]{"Alice"})` | Có: `target:greet:Alice` | `Hello Alice` |
| `greet("skip")` | Return sớm, không `proceed` | **Không** | `SKIPPED` |
| `fail()` | `proceed()` rồi log/rethrow | Có, target throw | `IllegalStateException("boom")` |
| `outer()` | `proceed()`, target gọi `this.greet` | `outer` và `greet` đều chạy trong target | Không có around advice lồng cho `greet("inside")` |

**Chú ý đường `outer()`:** Spring AOP proxy advice khớp method `outer` được caller gọi. Nhưng lời gọi `greet("inside")` phát sinh **trong target** nên không có một dòng `around:before:greet` thứ hai. Không phải `@Around` không biết đến `greet`; đường gọi nội bộ đã bypass proxy.

**Chú ý đường `skip`:** Dù method `greet` là một Spring bean method và có pointcut phù hợp, Spring không tự ép target chạy. Advice đã trả kết quả từ trước `proceed()`, chứng minh quyền điều khiển của `@Around`.

## 9. @Around khác gì @Before, @AfterReturning, @AfterThrowing và @After?

| Nhu cầu | Loại advice nên xem trước | Vì sao |
| --- | --- | --- |
| Chỉ log trước khi method chạy | `@Before` | Không cần tự quản lý `proceed()` |
| Chỉ nhận normal return value | `@AfterReturning` | Có `returning` binding, không cần bao quanh invocation |
| Chỉ log exception thoát ra | `@AfterThrowing` | Có `throwing` binding, nêu rõ failure outcome |
| Cleanup khi method hoàn tất bình thường/exception | `@After` | Semantics after-finally, không cần đổi flow |
| Đo thời gian của đúng một invocation trong một scope | `@Around` | Biến `started` local đi qua trước–sau, dùng `finally` |
| Thay input trước khi target chạy | `@Around` | `proceed(newArgs)` |
| Trả cache/fallback thay target | `@Around` | Có thể short-circuit |
| Retry có kiểm soát | `@Around` hoặc retry interceptor chuyên trách | Có thể gọi `proceed()` nhiều lần |

Nguyên tắc Spring: **dùng advice ít quyền nhất đáp ứng nhu cầu**. Không có lý do dùng `@Around` chỉ để `System.out.println("before")` nếu `@Before` đã đủ.

## 10. Phối hợp @Around với Spring transaction, cache và retry

Một Spring bean có thể đồng thời chịu ảnh hưởng của `@Around` do ứng dụng khai báo và các interceptor do transaction, caching hoặc retry infrastructure cung cấp. **Vị trí trong chain quyết định điều gì được đo và điều gì được chạy lại.**

- **Cache:** nếu cache interceptor ở phía trong trả cache hit mà không gọi tiếp, `@Around` nằm ngoài cache vẫn chạy, nhưng target không chạy. Nếu cache nằm ngoài và short-circuit, advice ở trong có thể không được gọi.
- **Transaction:** khi retry nằm ngoài transaction advice, mỗi attempt *có thể* bước qua transaction interceptor riêng theo propagation/transaction configuration; transaction nằm ngoài retry lại có thể bao nhiều attempts trong một transaction. Không suy ra mỗi attempt luôn có transaction mới.
- **Retry:** gọi `proceed()` nhiều lần có thể lặp việc ghi DB, gửi message hoặc gọi dịch vụ thanh toán. Ngoại lệ xảy ra sau side effect không chứng minh thao tác trước đó chưa thành công.
- **Thứ tự:** `@Order`/advisor order có ảnh hưởng đến ai vào trước và quan sát kết quả nào. Thứ tự annotation trong source không phải chứng cứ về runtime order.

Khi kiểm tra một aspect, đo riêng **số lần caller gọi proxy**, **số lần advice vào**, và **số lần target hoặc side effect thực thi**. Những bài về multiple-`proceed()`, retry side effects và bảo toàn hợp đồng nghiệp vụ mở rộng các tình huống này bằng phép thử cụ thể.

## 11. Những lỗi Spring @Around thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Target method không chạy nhưng caller nhận giá trị | Advice trả kết quả mà không gọi `proceed()` | Kiểm tra nhánh return sớm; chỉ short-circuit khi chủ đích |
| Caller nhận `null` dù target trả `String` | Around advice khai báo `void` hoặc bỏ return kết quả | Dùng `Object`, `return pjp.proceed()` |
| Exception bị biến mất | `catch` và return fallback vô tình | Rethrow exception trừ khi policy fallback hợp lệ |
| Log sau `proceed()` không xuất hiện khi target throw | Code sau proceed chỉ chạy ở normal return | Đưa cleanup/metric tổng thời gian vào `finally` |
| Lỗi `ArrayIndexOutOfBoundsException` trong advice | Dùng `pjp.getArgs()[0]` cho method không có params | Giới hạn pointcut/arity hoặc kiểm tra args trước |
| `IllegalArgumentException` khi `proceed(newArgs)` | Sai số args hoặc kiểu không tương thích | Cung cấp đủ argument đúng thứ tự và kiểu |
| `ClassCastException` ở caller | Advice return object không tương thích target return type | Bảo toàn return contract |
| Hai lần side effect | Gọi `proceed()` nhiều lần | Cân nhắc idempotency, retry boundary |
| Aspect không chạy khi `this.method()` | Self-invocation bypass Spring proxy | Tách bean cộng tác, gọi qua proxy |
| Aspect không chạy trên bean tạo bằng `new` | Không có Spring AOP post-processing | Inject bean từ context |
| `final`/`private` method không được CGLIB advice | Không override được | Chọn thiết kế method/proxy phù hợp |
| Đo thời gian đột nhiên bao cả retry/cache | Advisor order thay đổi phạm vi đo | Định nghĩa metric boundary và test ordering |
| `@Around` method không khởi tạo | Aspect không phải Spring bean hoặc chưa bật AOP | Kiểm tra `@Bean`/`@Component` và `@EnableAspectJAutoProxy` |
| Pointcut quá rộng | `execution(* *(..))` không giới hạn type/package | Kết hợp `within`/service pattern |
| AspectJ weaving chạy khác khi thay `proceed(Object[])` | Spring proxy và AspectJ compiled advice có quy tắc args khác | Tham khảo tài liệu về binding đúng thứ tự nếu cần portability |

### Không log mọi argument không kiểm soát

`pjp.getArgs()` trả object thực tế; nhiều service arguments có thể chứa password, bearer token, nội dung cá nhân hoặc cấu trúc lớn. Đừng tự động `Arrays.toString(pjp.getArgs())` trên toàn tầng service trong production. Sử dụng allowlist, masking và metadata tối thiểu, đồng thời quan tâm overhead serialization/toString.

## 12. Checklist debug @Around có vẻ không hoạt động

1. **Aspect đã được Spring đăng ký?** Lớp có `@Aspect` và được tạo bằng `@Component`/`@Bean`? `@Aspect` một mình không đăng ký bean.
2. **AOP đã bật ở context sở hữu target?** Có `@EnableAspectJAutoProxy` hoặc Boot AOP auto-configuration đúng không?
3. **Proxy có thật không?** Kiểm tra `AopUtils.isAopProxy(bean)` và nếu cần `isJdkDynamicProxy`/`isCglibProxy`.
4. **Pointcut có match method?** `execution(...)`, package/type/visibility/overload có đúng?
5. **Call path qua proxy?** Client gọi Spring-managed bean hay tự `new`? Target có dùng `this.otherMethod()` không?
6. **Method được proxy hóa hợp lệ?** `final` class, `private`/`final` method hoặc interface không expose method có gây giới hạn không?
7. **Advice đã gọi `proceed()`?** Có nhánh `return` trước đó hoặc exception từ code before không?
8. **Kiểu và số args của `proceed(newArgs)` đúng?** Đặc biệt khi method có nhiều parameters hoặc varargs.
9. **Advice trả đúng result/throw đúng exception?** Tránh `void` around hoặc swallow exception vô chủ đích.
10. **Advisor order/caching/transaction có thay kết quả?** Có một interceptor bên ngoài short-circuit khiến around không được gọi?
11. **Có multiple proceed hoặc retry?** Kiểm tra số lần target chạy và side effects.
12. **Integration test có dùng Spring context thật?** Unit test gọi trực tiếp target bằng `new` không chứng minh AOP có hay không.

Ví dụ snippet chẩn đoán (giả sử đã có `ApplicationContext context` và bean tên `greetingService`):

```java
Object bean = context.getBean("greetingService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Cần import `org.springframework.aop.support.AopUtils`. Có proxy chưa đủ để khẳng định **mọi method** hoặc **mọi lời gọi** đều đi qua advice; vẫn phải kiểm tra pointcut và đường gọi.

## 13. Quy tắc thiết kế @Around an toàn

- **Giữ đơn giản:** nếu chỉ cần pre/post event, cân nhắc `@Before`, `@AfterReturning`, `@AfterThrowing` hoặc `@After`.
- **Mặc định proceed đúng một lần:** chỉ đổi sang 0/n lần với mục tiêu và tests rõ ràng.
- **Bảo toàn result và exception:** `return pjp.proceed()` trong đường thông thường; `throw ex` sau khi log nếu không chủ đích fallback.
- **Dùng `finally` cho cleanup:** đảm bảo advice không bỏ phần đo thời gian khi method throw.
- **Đúng API:** first parameter `ProceedingJoinPoint`, return `Object`, `throws Throwable`.
- **Thay argument có kiểm soát:** clone array, đúng arity/type và test tác động cache/transaction/advisors.
- **Tránh state không thread-safe:** dùng biến local trong mỗi invocation; nếu aspect singleton có mutable field, quản lý concurrency.
- **Bảo vệ dữ liệu:** không log payload nhạy cảm từ `getArgs()` hoặc result/exception không giới hạn.
- **Xác định điểm quan sát:** timing bên ngoài cache/retry khác timing target attempt.
- **Test cả đường bình thường và lỗi:** return value, null, exception, short-circuit, replacement và self-invocation.
- **Không tự tạo object target bằng `new`:** để Spring bean proxy quản lý cross-cutting behavior.

## 14. Kết luận

Trong Spring Aspect, **`@Around` là advice bao quanh method invocation và `ProceedingJoinPoint` là công cụ điều khiển phần chain phía trong**. Ba thao tác quyết định semantics là:

- `proceed()`: tiếp tục với original arguments;
- `proceed(Object[])`: tiếp tục với arguments được thay thế hợp lệ;
- **không gọi `proceed()`**: có thể chủ động bỏ qua target và trả kết quả/exception do advice tạo.

Advice có thể quan sát cả return và throw, dùng `finally` để dọn dẹp, nhưng cũng có thể gây lỗi khó phát hiện nếu vô tình nuốt exception, trả sai kiểu, thay tham số ngoài dự kiến hoặc lặp target có side effect.

Với Spring AOP, hãy luôn đặt câu hỏi **“lời gọi có đi qua Spring-managed proxy không?”** rồi mới xét `@Around`. `ProceedingJoinPoint` không thay thế proxy boundary, không sửa self-invocation và không biến constructor/private/final methods thành join points được Spring AOP intercept.

### Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice: Around Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): kiểu method `@Around`, `ProceedingJoinPoint`, `proceed()`/`proceed(Object[])`, return values, semantics zero/one/many proceed, advice ordering.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): các loại advice và vai trò quyền điều khiển của around advice.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): kích hoạt proxy và đăng ký Spring `@Aspect`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxy, self-invocation và các giới hạn.
- [Spring Framework — Advice API](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): `MethodInterceptor` và cách `proceed` đi tiếp trong interceptor chain.
