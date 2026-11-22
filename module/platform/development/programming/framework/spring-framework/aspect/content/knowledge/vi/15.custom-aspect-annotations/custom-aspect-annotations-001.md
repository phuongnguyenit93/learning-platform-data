# Định nghĩa annotation đánh dấu dùng với Spring AOP

## 1. Annotation đánh dấu có vai trò gì trong Spring Aspect?

Trong một ứng dụng Spring, ta thường muốn áp dụng một chính sách ngang nhiều service methods — ví dụ audit những thao tác nghiệp vụ quan trọng, theo dõi latency hoặc kiểm tra một loại operation — mà không phải liệt kê cố định mọi tên phương thức trong biểu thức pointcut.

Một **custom marker annotation** có thể đóng vai trò **hợp đồng khai báo**: lập trình viên đánh dấu các method được phép/cần áp dụng chính sách; Spring AOP aspect định nghĩa một pointcut phù hợp, rồi advice chỉ chạy khi một **method execution qua Spring proxy** khớp với điều kiện.

```java
@TrackCall("payment")
public String charge(String reference) {
    return "charged:" + reference;
}
```

Đây là **method fragment**, cần định nghĩa `@TrackCall` và đặt trong một Spring service bean.

Chú ý ba việc độc lập:

1. **Định nghĩa annotation**: tạo một Java annotation type có `@Target` và `@Retention` thích hợp.
2. **Đặt annotation trên method**: biểu thị ý định nghiệp vụ, không tự thực thi code.
3. **Khai báo Spring `@Aspect`/advice**: xác định join point được chọn bằng `@annotation`, rồi xử lý logic khi lời gọi **đi qua Spring AOP proxy**.

Một annotation tự tạo **không tự bật Spring AOP**, **không tự biến class thành Spring bean**, và **không tự gây interception**. Chính hạ tầng Spring AOP cùng advice/pointcut mới làm điều đó.

Phạm vi bài này chỉ tập trung **Spring Framework Aspect** dùng annotation-style `@AspectJ` qua proxy, theo ràng buộc của chủ đề Spring Aspect. Kiến thức Java annotation chung được dùng đúng mức cần thiết để cấu hình Spring AOP, không mở rộng sang AspectJ weaving độc lập.

## 2. Định nghĩa annotation tối thiểu có thể dùng ở runtime

Annotation tối thiểu cho các method:

```java
package com.example.marker;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
}
```

Đây là **định nghĩa Java annotation hoàn chỉnh**; có thể lưu ở `TrackCall.java` trong đúng package.

Ý nghĩa:

- `public @interface TrackCall` định nghĩa một annotation type, không phải Java interface thông thường cần method implementation.
- `@Target(ElementType.METHOD)` cho phép dùng trên method declarations; tránh đặt marker sai trên class/field/parameter.
- `@Retention(RetentionPolicy.RUNTIME)` giữ annotation có thể tra cứu ở runtime, phục vụ reflection và matching/binding của Spring AOP.
- Chỉ khi method được gọi **qua Spring AOP proxy phù hợp** và có matching advisor, marker mới tác động đến thực thi.

Với một marker không có thuộc tính, cách dùng là `@TrackCall`, không cần ngoặc.

Trong ứng dụng thực tế, nếu muốn ghi thêm một nhãn/loại sự kiện, annotation có thể khai báo elements:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
    boolean logResult() default false;
}
```

Đây là **định nghĩa thay thế**, không đặt cùng lúc với định nghĩa phía trên trong một project. Khi có `String value()` không có default, người dùng phải cung cấp nhãn: `@TrackCall("payment")` hoặc `@TrackCall(value = "payment")`. `logResult()` có default `false` nên có thể bỏ qua.

Các attribute là **metadata cấu hình cho advice**, không phải mutable variables. Không nên lưu password, token, PII, raw SQL hay dữ liệu secret trong annotation attributes — metadata annotation thường hiện diện trong bytecode và có thể được reflection đọc.

## 3. Những meta-annotation nên và không nên dùng

### 3.1. `@Retention(RUNTIME)` — lựa chọn phù hợp cho Spring AOP

| Retention | Khi nào metadata còn tồn tại? | Phù hợp Spring `@annotation`? |
| --- | --- | --- |
| `SOURCE` | Trong source, không còn trong bytecode | **Không** để làm runtime marker |
| `CLASS` | Trong class file, nhưng không được JVM cung cấp cho runtime reflection theo cơ chế thông thường | **Không** cho thiết kế cần runtime matching |
| `RUNTIME` | Được JVM giữ để tra cứu runtime | **Có**, nên dùng |

Khi quên `@Retention`, Java mặc định dùng `RetentionPolicy.CLASS`. Đây là một lỗi dễ gặp: code đặt `@TrackCall` vẫn biên dịch nhưng Spring AOP pointcut dựa trên annotation có thể **không match như mong đợi**.

Không giải quyết bằng cách đổi tên method advice hoặc đổi `@Before` thành `@Around`; phải sửa định nghĩa annotation rồi **rebuild**.

### 3.2. `@Target(METHOD)` — chọn điểm gắn đúng hợp đồng

Nếu annotation dùng để chọn **method executions** trong Spring AOP, `ElementType.METHOD` là mục tiêu tự nhiên.

Nếu muốn tạo **composed annotations** về sau:

```java
@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
}
```

`ANNOTATION_TYPE` cho phép annotation này xuất hiện trên định nghĩa của annotation khác. Đây là **biến thể thiết kế**, không bắt buộc cho marker trực tiếp.

Cần phân biệt:

- `@annotation`: match annotation trên **method execution**.
- `@target`: match annotation gắn trên target **class/type**.
- `@within`: match các method executions thuộc type đã annotate theo semantics Spring.
- `@args`: xét annotation của **runtime argument types**.
- `args`: xét/bind runtime argument values/types, **không phải** chính annotation của method.

Không sửa `@Target` thành `TYPE` chỉ vì aspect đặt trên một service class. Chọn designator theo chỗ thực sự gắn marker.

### 3.3. `@Documented` — tùy chọn nhưng hữu ích

```java
@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
}
```

`@Documented` giúp annotation xuất hiện trong Javadoc của thành phần được annotate, nếu công cụ Javadoc tương ứng xử lý. Nó **không** quyết định Spring pointcut matching.

### 3.4. Không trông chờ `@Inherited` giải quyết method annotation inheritance

Java `@Inherited` áp dụng inheritance semantics cho **class-level annotation lookup**, không có nghĩa annotations trên interface method hoặc superclass method tự được tất cả overridden methods kế thừa theo `Method.getAnnotation()`.

Nếu policy cần tìm annotation trên interface/superclass/implementation method, xem phần 10 về `AopUtils.getMostSpecificMethod` và `AnnotatedElementUtils`; đừng nghĩ thêm `@Inherited` vào một method marker là đủ.

### 3.5. `@Repeatable` không phải cơ chế aspect mặc định đọc mọi bản

Một Java repeatable annotation có thể chứa nhiều instance của cùng annotation type. Tuy nhiên, đừng giả định một pointcut `@annotation(TrackCall)` sẽ **bind tất cả** instances theo ý bạn. Nếu cần nhiều policy records trên một method, phải định nghĩa container/repeatability và kiểm thử đúng Spring version/API; nhiều khi một annotation mang array values đơn giản hơn.

## 4. Một thiết kế marker annotation có metadata an toàn

Một ví dụ thực dụng:

```java
package com.example.marker;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
    boolean logResult() default false;
}
```

Metadata:

- `value()` biểu thị **tên hành động** ổn định như `charge`, `cancel`; tránh phụ thuộc package/class/method name nếu chúng có thể refactor.
- `logResult() default false` tạo **opt-in** rõ ràng trước khi in kết quả. Trong production, vẫn cần chính sách data classification/redaction; không phải cứ true là có quyền log PII.
- `@Documented` hữu ích cho tài liệu API.
- `METHOD` và `RUNTIME` giữ định nghĩa nhất quán với pointcut Spring.

Cách dùng:

```java
@TrackCall(value = "charge", logResult = true)
public String charge(String reference) {
    return "charged:" + reference;
}

@TrackCall("cancel")
public String cancel(String reference) {
    throw new IllegalStateException("already finalized");
}
```

Các method fragments này sẽ có project chạy đầy đủ tại phần 8.

Nên đặt annotation ở một **package API ổn định** và chọn tên mang ý nghĩa hành vi. Tránh dùng `@Audit` vừa để đánh dấu “được phép gọi”, vừa dùng để biểu thị “phải ghi log toàn bộ PII”, nếu các ý nghĩa ấy cần policy khác nhau. Marker chỉ là **intent/metadata**, không thay thế authorization hoặc business validation.

## 5. Spring pointcut `@annotation` là cầu nối đến marker

Spring Framework hỗ trợ `@annotation` trong AspectJ-style pointcut expressions dành cho Spring AOP. Nó chọn method executions có annotation tương ứng.

### 5.1. Match theo annotation type

```java
@Before(
    "execution(public * com.example.marker.PaymentService.*(..))"
    + " && @annotation(com.example.marker.TrackCall)"
)
public void beforeTracked() {
    // Chạy trước method được đánh dấu.
}
```

Đây là **fragment advice**, chưa có class `@Aspect` và imports. Trong biểu thức:

- `execution(public * com.example.marker.PaymentService.*(..))` giới hạn các public methods của một service cụ thể.
- `@annotation(com.example.marker.TrackCall)` chọn method có marker đúng loại.
- `&&` yêu cầu **cả hai điều kiện cùng đúng**.
- Dùng tên fully-qualified trong string pointcut giúp tránh mơ hồ khi parser không có ngữ cảnh import Java.

Marker type **không phải pointcut expression bằng chính tên method**. Ví dụ chỉ đổi tên `charge()` thành `submitCharge()` mà vẫn giữ `@TrackCall` có thể không làm thay đổi chính sách nếu phần `execution` đủ rộng.

### 5.2. Bind annotation instance vào advice

Có thể dùng named binding:

```java
@Around(
    value = "execution(public * com.example.marker.PaymentService.*(..))"
          + " && @annotation(marker)",
    argNames = "marker"
)
public Object trace(ProceedingJoinPoint pjp, TrackCall marker)
        throws Throwable {

    System.out.println("action=" + marker.value());
    return pjp.proceed();
}
```

Đây là **fragment** cho một class `@Aspect`. Với pointcut này:

- `marker` trong `@annotation(marker)` là **binding identifier**.
- `TrackCall marker` trong Java advice signature là formal parameter nhận annotation object.
- `argNames="marker"` giúp Spring map tên annotation binding rõ ràng.
- `ProceedingJoinPoint` đứng **đầu advice parameter list**, nên tên của nó có thể bỏ khỏi `argNames` theo quy tắc Spring.
- `marker.value()` và `marker.logResult()` cho phép advice lấy **metadata type-safe** mà không tự dùng reflection.
- `pjp.proceed()` thực thi phần chain phía trong; advice phải return giá trị phù hợp method contract.

**Không dùng `@annotation(TrackCall)` rồi khai báo parameter `marker` mà mong Spring bind tự động theo tên không liên quan.** Khi cần annotation object, dùng named binding thống nhất giữa expression, `argNames` và signature.

### 5.3. Pointcut riêng hoặc named pointcut tái sử dụng?

Một named pointcut có thể gom điều kiện scope:

```java
@Pointcut("execution(public * com.example.marker.PaymentService.*(..))")
public void paymentOperations() {}
```

Sau đó advice kết hợp:

```java
@Before(
    value = "paymentOperations() && @annotation(marker)",
    argNames = "marker"
)
public void before(TrackCall marker) {
    System.out.println(marker.value());
}
```

Đây là hai fragments đặt trong **cùng aspect class**. Nếu nhiều aspects sử dụng, named pointcut nên đặt trong class ổn định có accessibility thích hợp và tham chiếu theo Java package/class khi cần.

Không bắt buộc tạo named pointcut cho một ví dụ chỉ dùng một lần. Mục tiêu chính là **nội dung pointcut rõ và đủ hẹp**, không tạo thêm lớp abstraction vô ích.

## 6. Chọn loại advice nào để sử dụng marker?

| Nhu cầu | Advice thích hợp | Lưu ý |
| --- | --- | --- |
| Chỉ log trước khi method được gọi | `@Before` | Không cần điều khiển `proceed()`. |
| Quan sát return bình thường | `@AfterReturning` | Bind `returning` nếu cần; không thay reference trả về bằng gán lại parameter. |
| Quan sát exception | `@AfterThrowing` | Chỉ khi method invocation thoát bằng exception phù hợp. |
| Cleanup/tổng hợp sau mọi kết quả sync | `@After` | Có finally semantics; phải hiểu advisor ordering. |
| Đo thời gian bao quanh, có success/error trong cùng lời gọi | `@Around` | Giữ start time/actor ở **local variables**, trả đúng kết quả/exception. |
| Đổi arguments/result hoặc short-circuit | `@Around` | Chỉ khi business policy cho phép, đảm bảo type và side effects. |

Một marker `@TrackCall` **không bắt buộc gắn với `@Around`**. Chọn loại advice ít quyền nhất đủ đáp ứng yêu cầu. Ví dụ demo dùng `@Around` để quan sát **both success/failure paths** và có thể đọc `logResult`, không phải vì annotation chỉ hoạt động với `@Around`.

Nếu có nhiều advices cùng match annotated method, cần xét Spring ordering và `@Order`; **không suy thứ tự từ vị trí method trong `@Aspect` class**.

## 7. Spring thực sự cần những gì để marker có hiệu lực?

Chuỗi điều kiện:

```text
Java annotation type
    @Retention(RUNTIME), @Target(METHOD)
                |
                v
Spring service method mang marker
                |
          Caller dùng bean
                |
                v
          Spring AOP proxy
                |
       pointcut @annotation match
                |
                v
         Spring @Aspect advice
                |
         target method execution
```

Các bước thiết lập bắt buộc:

1. Service là Spring-managed bean (ví dụ `@Bean` hoặc `@Service` được component scan).
2. Aspect class có `@Aspect` và **được đăng ký làm Spring bean** (ví dụ `@Bean` hoặc `@Component`). `@Aspect` đơn lẻ không phải annotation stereotype đăng ký bean.
3. Bật hạ tầng Spring AOP bằng `@EnableAspectJAutoProxy` hoặc Spring Boot auto-configuration phù hợp. Không cần thêm cả hai một cách máy móc.
4. Có dependency AspectJ hỗ trợ Spring pointcut parsing, thông thường `org.aspectj:aspectjweaver`.
5. Pointcut thực sự match method và annotation placement, không bị điều kiện scope loại bỏ.
6. Caller gọi qua reference **Spring proxy**, không tự `new` target hoặc chỉ gọi `this.annotatedMethod()` nội bộ.

`@EnableAspectJAutoProxy` sử dụng **Spring proxy-based AOP**, không tự kích hoạt full AspectJ compile-time/load-time weaving.

## 8. Project Maven Java 17+ chạy được, có success, failure và method không đánh dấu

Mục đích demo:

- Định nghĩa annotation `@TrackCall` có `value` và `logResult`.
- Spring chỉ advise hai methods mang annotation.
- Advice bind annotation instance và lấy metadata.
- Method success có thể in return result khi opt-in.
- Method fail được audit rồi **throw exception gốc**.
- Method không annotate chỉ chạy target, không in dòng audit.
- Cuối cùng assert số advised calls để kiểm tra **pointcut đúng phạm vi**.

Môi trường cố định: **Java 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1, Maven**. Đây là phiên bản minh họa, không tuyên bố là mới nhất.

### 8.1. Cấu trúc project

```text
spring-aop-marker/
├── pom.xml
└── src/main/java/com/example/marker/
    ├── TrackCall.java
    ├── PaymentService.java
    ├── TrackCallAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-marker</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp `ApplicationContext` và các Spring AOP dependencies phù hợp qua dependency tree; `aspectjweaver` hỗ trợ phân tích `@AspectJ` pointcut expressions. Demo không dùng full weaving agent.

### 8.3. `TrackCall.java`

```java
package com.example.marker;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
    boolean logResult() default false;
}
```

Đây là annotation **không tự chứa advice logic**. Hai method annotation elements được đọc khi Spring bind `TrackCall marker` trong aspect.

### 8.4. `PaymentService.java`

```java
package com.example.marker;

public class PaymentService {

    @TrackCall(value = "charge", logResult = true)
    public String charge(String reference) {
        System.out.println("[TARGET] charge " + reference);
        return "charged:" + reference;
    }

    @TrackCall("cancel")
    public String cancel(String reference) {
        System.out.println("[TARGET] cancel " + reference);
        throw new IllegalStateException("already finalized");
    }

    public String status() {
        System.out.println("[TARGET] status");
        return "UP";
    }
}
```

Chỉ `charge` và `cancel` được đánh dấu. `status()` không mang `@TrackCall`. Mỗi method là public, non-final và Spring quản lý target instance qua `@Bean` ở phần tiếp theo.

Trong production, đừng đánh dấu operation chỉ để log **toàn bộ payment parameters**. Demo cố ý chỉ in một test reference và một kết quả chuỗi không nhạy cảm.

### 8.5. `TrackCallAspect.java`

```java
package com.example.marker;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TrackCallAspect {

    private final AtomicInteger advisedCalls = new AtomicInteger();

    @Around(
        value = "execution(public * com.example.marker.PaymentService.*(..))"
              + " && @annotation(marker)",
        argNames = "marker"
    )
    public Object around(ProceedingJoinPoint pjp, TrackCall marker)
            throws Throwable {

        advisedCalls.incrementAndGet();
        String action = marker.value();
        System.out.println("[AUDIT] enter action=" + action);

        try {
            Object result = pjp.proceed();

            if (marker.logResult()) {
                System.out.println("[AUDIT] success action=" + action
                        + " result=" + result);
            } else {
                System.out.println("[AUDIT] success action=" + action);
            }
            return result;
        } catch (Throwable error) {
            System.out.println("[AUDIT] failure action=" + action
                    + " type=" + error.getClass().getSimpleName());
            throw error;
        }
    }

    public int advisedCalls() {
        return advisedCalls.get();
    }
}
```

Các điểm cần kiểm chứng:

- `@annotation(marker)` bind **annotation instance** có trên method đang được intercept.
- `argNames="marker"` cung cấp tên parameter tường minh; `pjp` là leading `ProceedingJoinPoint` không cần liệt kê.
- `pjp.proceed()` được gọi một lần cho mỗi matching invocation trong demo.
- Success branch trả **đúng kết quả** target; failure branch ném lại **đúng exception**.
- `advisedCalls` là shared aggregate counter nên dùng `AtomicInteger`; không có mutable field lưu user hoặc join point của lời gọi gần nhất.
- `logResult` chỉ dùng để minh họa attribute; trong production cần data classification/redaction, tránh ghi toàn bộ result object hoặc `toString()` có side effects.

### 8.6. `AppConfig.java`

```java
package com.example.marker;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }

    @Bean
    public TrackCallAspect trackCallAspect() {
        return new TrackCallAspect();
    }
}
```

`@EnableAspectJAutoProxy(proxyTargetClass=true)` bật Spring AOP và dùng CGLIB class-based proxy cho `PaymentService` (không implement business interface). Aspect được đăng ký là một Spring bean qua `@Bean`. Chỉ có annotation type `@TrackCall` trên classpath không tạo proxy nếu không có advisor.

### 8.7. `DemoApp.java`

```java
package com.example.marker;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            PaymentService payment =
                    context.getBean(PaymentService.class);
            TrackCallAspect aspect =
                    context.getBean(TrackCallAspect.class);

            System.out.println("isProxy=" + AopUtils.isAopProxy(payment));

            System.out.println("[CALLER] charge");
            String charged = payment.charge("P-1");
            System.out.println("[CALLER] result=" + charged);

            System.out.println("[CALLER] cancel");
            try {
                payment.cancel("P-2");
            } catch (IllegalStateException error) {
                System.out.println("[CALLER] caught=" + error.getMessage());
            }

            System.out.println("[CALLER] status");
            System.out.println("[CALLER] health=" + payment.status());
            System.out.println("advisedCalls=" + aspect.advisedCalls());

            if (aspect.advisedCalls() != 2) {
                throw new AssertionError("Expected exactly two advised calls");
            }
        }
    }
}
```

Caller dùng **bean từ Spring context**, không tự khởi tạo `new PaymentService()` bên ngoài container. Phép đếm cuối giúp phát hiện pointcut match quá rộng hoặc không match.

### 8.8. Lệnh chạy và stdout dự kiến

Từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.marker.DemoApp
```

Các dòng do chương trình in ra (không tính log khác của Maven/Spring nếu môi trường có):

```text
isProxy=true
[CALLER] charge
[AUDIT] enter action=charge
[TARGET] charge P-1
[AUDIT] success action=charge result=charged:P-1
[CALLER] result=charged:P-1
[CALLER] cancel
[AUDIT] enter action=cancel
[TARGET] cancel P-2
[AUDIT] failure action=cancel type=IllegalStateException
[CALLER] caught=already finalized
[CALLER] status
[TARGET] status
[CALLER] health=UP
advisedCalls=2
```

Giải thích thứ tự:

1. Spring tạo proxy: `isProxy=true`.
2. `charge` mang `@TrackCall` nên aspect chạy trước body: `[AUDIT] enter...`, rồi target in `[TARGET]`.
3. Target trả chuỗi, attribute `logResult=true` khiến aspect in success kèm result; caller nhận cùng chuỗi.
4. `cancel` cũng mang marker, aspect chạy rồi target ném `IllegalStateException`. Advice bắt/ghi event và throw lại, caller bắt cùng exception. `logResult` không liên quan nhánh lỗi.
5. `status` không mang annotation, nên **chỉ target** in log; không có `[AUDIT]` cho method này.
6. `advisedCalls=2` cho thấy marker giới hạn đúng hai invocations.

Đây là **stdout dự kiến từ code đã rà soát tĩnh**, không khẳng định Maven đã được chạy trên môi trường cụ thể. Nếu sửa Spring version, cấu hình proxy, JDK, annotation placement hoặc bổ sung advisors, nên chạy lại integration test.

## 9. Spring proxy boundary: marker đúng vẫn có thể không có advice

### 9.1. Self-invocation

```java
public class PaymentService {
    public String perform() {
        return charge("internal");
    }

    @TrackCall("charge")
    public String charge(String reference) {
        return "charged:" + reference;
    }
}
```

Đây là **fragment cấu hình thay thế**, không copy lên cạnh `PaymentService.java` demo mà không đổi class tương ứng. Khi caller gọi `proxy.perform()` nhưng target tự gọi `this.charge()`, lời gọi nội bộ thường **không đi qua proxy**. Aspect nhắm `charge` có thể **không chạy**, dù annotation được đặt đúng.

Tương tự, `new PaymentService().charge(...)` bên ngoài Spring container không được auto-proxy chỉ vì method có marker.

### 9.2. JDK dynamic proxy và CGLIB

- **JDK proxy** expose interfaces; cần gọi qua proxied interface methods.
- **CGLIB proxy** là subclass proxy, không intercept `final`/`private` method theo cách override thông thường; final class không thể được CGLIB subclass.
- Với annotation nằm trên concrete implementation còn interface không có, cơ chế resolution/matching cần được kiểm thử khi đổi proxy strategy.
- Nếu method chỉ có package visibility hoặc protected, behavior/khả năng gọi qua proxy khác public API; nên thiết kế marker cho **public business operations** khi không có lý do đặc biệt.

Spring Boot và Spring Framework core có thể chọn proxy strategy mặc định khác nhau theo cấu hình. Không gắn lời hứa “luôn JDK” hoặc “luôn CGLIB” vào Java annotation type.

### 9.3. Aspect bean không được đăng ký

Sai:

```java
@Aspect
public class TrackCallAspect {
    @Before("@annotation(com.example.marker.TrackCall)")
    public void before() {}
}
```

Nếu không có `@Component` được scan hoặc `@Bean` registration, Spring có thể **không có instance aspect** để tạo advisor. Annotation trên target method vẫn có, nhưng không có advice.

Giải pháp: bật `@EnableAspectJAutoProxy`/Boot AOP auto-configuration phù hợp; đăng ký aspect dưới Spring bean lifecycle, xác minh đúng `ApplicationContext`.

### 9.4. Kiểm chứng bean/proxy trước khi debug expression

```java
System.out.println(AopUtils.isAopProxy(payment));
System.out.println(AopUtils.isJdkDynamicProxy(payment));
System.out.println(AopUtils.isCglibProxy(payment));
```

Đây là fragment, `payment` là bean reference do Spring trả về. `isAopProxy=true` cho biết proxy tồn tại, **không chứng minh mọi advice mong muốn đều match**: bean có thể đã được proxy bởi transaction hoặc advisor khác. Luôn assert event count của đúng aspect trên đúng method.

## 10. Annotation ở interface, implementation và class

Một marker gắn trực tiếp lên implementation method là trường hợp dễ kiểm chứng nhất với Spring AOP. Khi đặt marker lên interface method, method override hoặc trên class, cần phân biệt:

- Java reflection không tự kế thừa annotation trên interface method sang implementation method; `@Inherited` không giải quyết method annotation.
- `@annotation` nhắm tới method execution; `@within` và `@target` xét type theo semantics tương ứng.
- Với JDK proxy, `MethodSignature.getMethod()` có thể chỉ ra interface method. Nếu phải đọc implementation metadata, dùng `AopUtils.getMostSpecificMethod(...)` và Spring annotation utilities.

Nếu nhiều nơi cùng khai báo marker nhưng khác giá trị, quy định nơi nào có ưu tiên và test với cả JDK/CGLIB. Nếu pointcut không match từ đầu, lookup đặt bên trong advice cũng không thể làm advice chạy.

## 11. Composed annotations và `@AliasFor`

Khi một annotation khác được meta-annotated bằng `@TrackCall`, type gốc phải có `@Target` cho phép `ANNOTATION_TYPE` và cả hai loại annotation phải giữ `RUNTIME`. Spring có thể đọc metadata qua `AnnotatedElementUtils.findMergedAnnotation(...)`; `@AliasFor` diễn đạt cách ghi đè thuộc tính trong mô hình merged annotations.

Tuy nhiên, **Spring merged annotation lookup và AspectJ-style `@annotation` pointcut không phải cùng một thuật toán**. Đừng mở rộng lời hứa của marker sang composed annotations nếu chưa có integration test đo được số lần advice. Khi bắt buộc hỗ trợ nhiều lớp composition, cân nhắc matcher/advisor dựa trên API Spring hoặc một pointcut `execution` đủ hẹp rồi phân giải metadata.

## 12. Giữ phạm vi pointcut có chủ đích

`@annotation(marker)` có thể khớp nhiều bean hơn nhóm nghiệp vụ cần xử lý. Một phạm vi kiểu `execution(public * com.example.payment..*Service.*(..)) && @annotation(marker)` làm ranh giới rõ hơn; nhưng khi đổi package hoặc tên class, integration test phải phát hiện pointcut không còn khớp.

Chọn scope dựa trên contract và phương thức gọi thực tế. Spring AOP chỉ can thiệp method executions đi qua Spring proxy; nó không chặn field access hay constructor chỉ vì annotation có `@Target` tương ứng.

## 13. Marker không phải sự bảo đảm an ninh hoặc nghiệp vụ

`@TrackCall("transfer")` chỉ mô tả ý định áp dụng tracking, không xác thực quyền truy cập, không bảo đảm transaction đã commit và không tự làm thao tác có thể retry an toàn. Nếu advice quyết định short-circuit hoặc gọi `proceed()` nhiều lần, đó là một thay đổi business contract cần kiểm thử tường minh. Không dùng annotation audit làm hàng rào bảo mật duy nhất khi self-invocation hoặc object ngoài Spring có thể bỏ qua proxy.

## 14. Thiết kế attribute nhỏ và có nghĩa

Các element của annotation chỉ có thể là primitive, `String`, `Class`, enum, annotation hoặc mảng các kiểu được phép. Chẳng hạn `String value()` nên là tên sự kiện ổn định, còn `boolean logResult() default false` chỉ bật ghi kết quả theo chính sách dữ liệu đã kiểm soát. Tránh password, token và trạng thái request trong metadata; nếu giá trị là loại thao tác hữu hạn, `enum` thường rõ hơn chuỗi tùy ý.

Thêm một element bắt buộc hoặc đổi default của element cũ là thay đổi API/hành vi đối với các method đã được annotate. Cần quản lý compatibility khi các module dùng chung annotation.

## 15. Kiểm thử hai lớp hành vi

Kiểm thử **metadata** để xác nhận `@Target`, `@Retention(RUNTIME)`, element bắt buộc/default và placement. Sau đó kiểm thử **Spring context** bằng lời gọi qua bean proxy thật, bao gồm:

1. Method có marker nhận advice đúng một lần và đúng giá trị annotation; method không có marker không bị advice.
2. Return value và exception của nghiệp vụ được `@Around` giữ nguyên, kể cả nhánh lỗi.
3. Hai method có giá trị marker khác nhau không dùng nhầm metadata; aspect singleton không lưu request/JoinPoint vào field mutable.
4. Self-invocation và `new Target()` bên ngoài container không được tính là những lần intercept bởi Spring AOP.
5. Nếu hỗ trợ interface, overload, composed annotations hoặc nhiều advisors, có positive/negative tests cho từng trường hợp và từng proxy strategy thực sự dùng.

Thử đúng nơi Spring thực thi chính sách sẽ tránh nhầm kết quả reflection hoặc sự tồn tại của proxy với việc advice cụ thể đã chạy.

## 16. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| Marker đặt trên method nhưng advice không chạy | Quên `@Retention(RUNTIME)`, mặc định `CLASS` | Thêm retention đúng, rebuild. |
| Annotation đặt trên class nhưng dùng `@annotation` | `@annotation` xét method join point, không phải marker trên type | Đặt marker lên method hoặc đổi PCD như `@target`/`@within` khi phù hợp. |
| `@Target` không cho đặt trên method | Annotation chỉ cho `TYPE`/`FIELD` | Thêm `ElementType.METHOD` đúng nhu cầu. |
| Có `@TrackCall` nhưng không có AOP proxy | Chưa bật AOP, chưa đăng ký aspect bean, caller dùng `new` | Kiểm tra `@EnableAspectJAutoProxy`/Boot config và Spring bean. |
| Self-invocation không được advice | `this.method()` bypass proxy | Refactor bean boundary/call qua Spring proxy phù hợp. |
| JDK proxy không intercept concrete-only method | Method không nằm trên proxied interface | Gọi qua interface contract phù hợp hoặc chọn class proxy khi cần. |
| CGLIB không intercept method `final` | CGLIB không override được | Đổi method/class contract hoặc chọn chiến lược khác. |
| `@annotation(marker)` không bind | Sai `argNames`/parameter type hoặc expression | Đồng bộ identifier và advice signature. |
| Method không annotate vẫn bị advice | Pointcut quá rộng, thiếu `&& @annotation(...)` | Giới hạn expression, thêm negative test. |
| Interface annotate nhưng implementation lookup direct trả null | Method-level annotation không tự được kế thừa như class annotation | Quy định placement và dùng Spring annotation utilities khi cần. |
| Composed marker không hoạt động như mong đợi | Nhầm direct `@annotation` matching với merged annotation lookup | Test riêng; dùng `findMergedAnnotation`/matcher thích hợp. |
| Gán result mới vào parameter `@AfterReturning` nhưng caller không thấy | Advice parameter là local reference | Dùng `@Around` nếu phải return replacement. |
| Mỗi caller chỉ gọi một lần nhưng audit lặp | Multiple proxies/advisors hoặc `proceed()` nhiều lần | Chẩn đoán chain, ordering và retry. |
| Log chứa token/PII | `logResult=true` mà không có policy redaction | Thiết kế default-safe, audit allowlist. |
| Aspect shared field bị lẫn user | Singleton aspect giữ per-invocation state | Dùng local variables và thread-safe event sink. |
| Annotation bị xem như authorization | Marker không tự bảo vệ đường gọi | Dùng framework security và test proxy bypass/edge cases. |

## 17. Checklist review trước khi đưa custom marker vào module

- [ ] Tên annotation diễn đạt **ý nghĩa nhất quán**, không ôm quá nhiều trách nhiệm.
- [ ] Có `@Retention(RUNTIME)`.
- [ ] Có `@Target(METHOD)` hoặc target set cụ thể phù hợp policy.
- [ ] Có `@Documented` nếu hữu ích cho API docs.
- [ ] Các elements như `value()`/`logResult()` có defaults an toàn và API rõ.
- [ ] Annotation không lưu credentials hoặc runtime mutable state.
- [ ] Aspect có `@Aspect` **và** được quản lý bởi Spring.
- [ ] Spring AOP auto-proxy đã được bật và `aspectjweaver` có trên classpath.
- [ ] Pointcut `@annotation` được bind đúng type/name, có scope hợp lý.
- [ ] Caller sử dụng Spring proxy, không dựa vào self-invocation.
- [ ] Có positive/negative integration tests cho methods có/không có marker.
- [ ] Đã kiểm tra exception path và return contract của advice.
- [ ] Có quy ước rõ annotation đặt ở interface hay implementation.
- [ ] Nếu dùng composed annotations, đã test `@AliasFor`/merged semantics và pointcut matching riêng.
- [ ] Nếu nhiều aspects cùng match, đã kiểm soát Spring ordering.
- [ ] Không suy marker đủ thay thế business validation, authorization, transaction hoặc idempotency.

### Tài liệu Spring chính thức

- Spring Framework — Declaring a Pointcut (`@annotation` và các PCD): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework — Declaring Advice (binding annotation instance, `argNames`, `ProceedingJoinPoint`): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — Enabling `@AspectJ` Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Proxying Mechanisms (JDK/CGLIB, self-invocation): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — `AopUtils` và target method resolution: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework — `AnnotatedElementUtils`, merged annotations: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/annotation/AnnotatedElementUtils.html

**Kết luận:** Để có một annotation đánh dấu thực sự dùng được với Spring AOP, hãy tạo annotation type có **`@Target(METHOD)` và `@Retention(RUNTIME)`**, gắn lên Spring-managed service methods, rồi khai báo một **Spring `@Aspect` bean** với pointcut `@annotation` (và binding khi cần đọc metadata). Annotation **chỉ đánh dấu ý định**; interception phụ thuộc Spring AOP proxy, phạm vi pointcut, advisor configuration và đường gọi thực tế.
