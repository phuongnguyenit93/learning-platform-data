# Đọc annotation trên đúng phương thức khi đối tượng là proxy trong Spring AOP

## 1. Vấn đề cần giải quyết

Khi viết advice trong Spring AOP, ta thường muốn đọc annotation của **phương thức nghiệp vụ thực sự được gọi** để quyết định mức độ audit, nhãn metric, chính sách kiểm tra hoặc cách ghi log.

Ví dụ:

```java
public interface BillingOperations {
    String pay(String id);
}

public class BillingService implements BillingOperations {
    @TrackOperation("payment")
    @Override
    public String pay(String id) {
        return "paid:" + id;
    }
}
```

Trong Spring Framework, caller có thể nhận một **JDK dynamic proxy** chỉ triển khai `BillingOperations`, hoặc một **CGLIB class-based proxy** kế thừa `BillingService`. Nếu một advice viết:

```java
Method method = ((MethodSignature) joinPoint.getSignature()).getMethod();
TrackOperation annotation = method.getAnnotation(TrackOperation.class);
```

thì annotation **có thể là `null` dù annotation có thật trên `BillingService.pay()`**: `method` có thể phản ánh method được khai báo ở **interface** khi dùng JDK proxy, trong khi annotation chỉ nằm trên **implementation**.

Đây không phải lỗi của Java annotation, cũng không tự động chứng minh Spring pointcut sai. Nó là sự khác biệt giữa các **method representations** có thể thấy trong một lời gọi Spring proxy AOP.

**Cách xử lý nền tảng trong Spring:**

1. Lấy `Method` từ `MethodSignature`.
2. Xác định **target class thực tế** của Spring bean.
3. Dùng `AopUtils.getMostSpecificMethod(method, targetClass)` để tìm method cụ thể trên implementation (và giải quyết bridge method theo API Spring).
4. Dùng `AnnotatedElementUtils.findMergedAnnotation(...)` khi cần hỗ trợ **meta-annotations, composed annotations và các thuộc tính annotation được hợp nhất**.
5. Nếu annotation vẫn không tìm thấy, xem lại **annotation nằm ở interface hay implementation, nơi đặt annotation, phạm vi pointcut, proxy strategy và Spring version**.

Ví dụ:

```java
Method declared = ((MethodSignature) joinPoint.getSignature()).getMethod();
Class<?> targetType = AopUtils.getTargetClass(joinPoint.getTarget());
Method specific = AopUtils.getMostSpecificMethod(declared, targetType);
TrackOperation operation =
        AnnotatedElementUtils.findMergedAnnotation(specific, TrackOperation.class);
```

Đây là **fragment trong Spring advice**, cần `joinPoint` là `JoinPoint`/`ProceedingJoinPoint`, các imports và annotation `TrackOperation` do ứng dụng khai báo. Phần 8 sẽ có project đầy đủ.

**Giới hạn của bài:** tập trung vào cách xác định **method annotation đúng trong Spring Aspect trên Spring-managed beans được gọi qua Spring AOP proxy**. Các kiến thức AspectJ/weaving chung không phải trọng tâm.

## 2. Ba thực thể rất dễ bị đánh đồng

Khi Spring AOP thực thi advice, cần phân biệt:

| Thành phần | API / ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Proxy** | `joinPoint.getThis()` | Reference Spring AOP proxy mà caller đi qua. Có thể là JDK proxy hoặc CGLIB subclass. |
| **Target** | `joinPoint.getTarget()` | Object nghiệp vụ được proxy ủy quyền tới. |
| **Method của join point signature** | `((MethodSignature) jp.getSignature()).getMethod()` | `java.lang.reflect.Method` mô tả method được báo cho advice; có thể là **interface method**. |
| **Method cụ thể trên target class** | `AopUtils.getMostSpecificMethod(method, targetClass)` | Method triển khai thích hợp để xem annotation của implementation. |
| **Annotation trên method cụ thể** | `AnnotatedElementUtils.findMergedAnnotation(specific, TrackOperation.class)` | Metadata, có thể gồm composed/meta-annotations theo quy tắc tìm kiếm Spring. |

Điều cần nhớ:

```text
Caller
  |
  v
Spring AOP proxy                  <-- getThis()
  |
  | JoinPoint / MethodSignature
  | có thể mô tả BillingOperations.pay(...)
  v
BillingService target             <-- getTarget()
  |
  v
BillingService.pay(...)           <-- most specific method
  |
  +-- @TrackOperation("payment")  <-- annotation đặt trên implementation
```

Trong một JDK proxy, lớp runtime của `getThis()` là generated proxy class, không phải `BillingService`. Nếu dùng `getThis().getClass().getDeclaredMethod(...)` để tìm annotation nghiệp vụ, bạn thường đang **đọc nhầm lớp hạ tầng proxy**.

Trong một CGLIB proxy, `getThis().getClass()` là generated subclass. Lớp này cũng **không phải điểm neo ổn định** để đọc annotation; method annotations không mặc nhiên được sao chép nguyên vẹn lên mọi generated overrides của proxy.

## 3. Vì sao `MethodSignature.getMethod()` không luôn là implementation method?

### 3.1. JDK interface proxy

Khi Spring tạo JDK dynamic proxy cho target implement `BillingOperations`, public API của proxy là các interface mà nó expose. Lời gọi `proxy.pay("P-1")` đi qua method invocation dựa trên interface contract.

Trong advice:

```java
Method signatureMethod =
    ((MethodSignature) jp.getSignature()).getMethod();
```

`signatureMethod.getDeclaringClass()` **có thể là `BillingOperations.class`**. Nếu `@TrackOperation` chỉ được đặt trên `BillingService.pay(String)`, thì:

```java
signatureMethod.getAnnotation(TrackOperation.class)
```

có thể trả về `null`.

**Không suy rằng implementation không có annotation chỉ vì interface `Method` không có.** Annotation trên method của implementation không tự “lan ngược” sang method cùng chữ ký trong Java interface.

### 3.2. CGLIB class proxy

Khi Spring tạo subclass proxy, method được intercept có thể phản ánh target class rõ hơn, nhưng cũng không nên gắn logic vào điều kiện “CGLIB luôn trả một loại Method cố định”. Advisor, bridge methods, generic types và proxy implementation có thể ảnh hưởng representation trong những tình huống cụ thể.

Giải pháp thống nhất cho **cả JDK và CGLIB** là chuẩn hóa về target method bằng API Spring thay vì tự phân nhánh:

```java
Method specific = AopUtils.getMostSpecificMethod(
    ((MethodSignature) jp.getSignature()).getMethod(),
    AopUtils.getTargetClass(jp.getTarget())
);
```

Nếu target không thể implement chữ ký đó hoặc có custom `TargetSource`, Spring có thể trả lại original method; phải kiểm tra nếu ứng dụng có proxy phức tạp.

### 3.3. Phân biệt tên method và đối tượng `Method`

`jp.getSignature().getName()` trả tên method như `"pay"`, nhưng **không đủ** để tìm chính xác annotation trên overload.

Ví dụ class có:

```java
String pay(String id)
String pay(String id, String channel)
```

Chỉ biết tên `"pay"` không xác định được overload nào thực thi. `MethodSignature.getMethod()` mang theo **parameter types**, và `AopUtils.getMostSpecificMethod` dùng thông tin chữ ký đó để đối chiếu method đúng trên target class.

Không nên tự dùng:

```java
target.getClass().getMethod(jp.getSignature().getName());
```

vì câu lệnh tìm method **không tham số**, dễ ném `NoSuchMethodException` hoặc chọn sai khi target có overload. API Spring giúp giảm những lỗi mà logic reflection thủ công thường mắc.

## 4. Chuẩn hóa method bằng `AopUtils.getMostSpecificMethod`

Spring Framework cung cấp API:

```java
public static Method getMostSpecificMethod(
        Method method, Class<?> targetClass);
```

Chữ ký trên là **mô tả API**, không phải chương trình độc lập. `method` có thể là method khai báo ở interface; `targetClass` là type class target thực tế.

Ví dụ:

```java
Method interfaceMethod =
        BillingOperations.class.getMethod("pay", String.class);

Method actual = AopUtils.getMostSpecificMethod(
        interfaceMethod, BillingService.class
);
```

Khi `BillingService` triển khai interface theo cách ví dụ, `actual` là đại diện cho **`BillingService.pay(String)`**.

### 4.1. Vì sao không chỉ dùng `target.getClass().getMethod(...)`?

Một đoạn reflection tự dựng cần xử lý thêm:

- Method **overloading**: phải biết chính xác parameter types.
- Class hierarchy: method có thể kế thừa từ superclass.
- Generic bridge methods: compiler có thể sinh bridge method với signature erasure.
- Annotation đặt trên method implementation/interface/supertype.
- Generated proxy class: không nên lấy `proxy.getClass()` làm nguồn domain metadata.
- Method visibility và accessibility.

`AopUtils.getMostSpecificMethod` kết hợp logic Spring để tìm implementation method tương ứng; **Javadoc Spring 6.1.14 xác nhận API này giải quyết bridge methods** nhằm đọc attributes từ original method definition.

Có thể viết:

```java
Method specific =
        AopUtils.getMostSpecificMethod(signatureMethod, targetClass);
```

thay vì tự dò bằng `getDeclaredMethods()` và so tên chuỗi.

### 4.2. Bridge methods với generics

Ví dụ generics minh họa:

```java
interface Handler<T> {
    void handle(T value);
}

class StringHandler implements Handler<String> {
    @TrackOperation("handle-string")
    public void handle(String value) {
        // ...
    }
}
```

Compiler có thể sinh **bridge method** để bảo toàn polymorphism khi Java type erasure. Nếu reflection lấy bridge method, annotation gắn với method nguồn `handle(String)` có thể không được quan sát theo cách mong muốn khi chỉ dùng `getDeclaredAnnotation` trên bridge.

Trong Spring AOP, `AopUtils.getMostSpecificMethod` là điểm bắt đầu hợp lý để chọn target method **và resolve bridge method**. Khi làm việc bên ngoài AOP có thể dùng `org.springframework.core.BridgeMethodResolver` theo nhu cầu, nhưng đừng thực hiện nhiều lớp resolution thủ công một cách vô ích.

Đừng mặc định mỗi Java compiler/version đều sinh và gắn method annotations lên bridge methods theo cùng cách. Kiểm tra bằng API Spring và integration tests.

## 5. Đọc annotation: `getAnnotation`, `findMergedAnnotation`, hay `@annotation`?

Có ít nhất ba nhu cầu khác nhau:

### 5.1. Chỉ đọc annotation gắn trực tiếp lên đúng method

```java
TrackOperation direct =
        specificMethod.getDeclaredAnnotation(TrackOperation.class);
```

Phù hợp khi policy **cố ý chỉ công nhận annotation đặt trực tiếp** lên implementation method. Nó không tự khám phá meta-annotation và không “merge” thuộc tính từ các composed annotations.

`specificMethod.getAnnotation(TrackOperation.class)` tương tự về mục tiêu trên method được chọn, nhưng dùng API `AnnotatedElement`; đừng kỳ vọng tự phát hiện annotation trên interface hoặc composed annotation.

### 5.2. Cần semantics annotation của Spring, gồm meta-annotations

```java
TrackOperation marker = AnnotatedElementUtils.findMergedAnnotation(
        specificMethod,
        TrackOperation.class
);
```

Spring `AnnotatedElementUtils.findMergedAnnotation` có thể tìm trong **annotation hierarchy** và tổng hợp metadata của composed annotations; hỗ trợ `@AliasFor` theo các quy tắc Spring.

Trường hợp ứng dụng dùng:

```java
@TrackOperation("critical")
public @interface CriticalOperation {}
```

và method được đánh dấu:

```java
@CriticalOperation
public void cancel(String id) { /* ... */ }
```

thì **direct** `getDeclaredAnnotation(TrackOperation.class)` trên method có thể trả `null`, trong khi **merged** annotation search có thể tìm `TrackOperation("critical")` thông qua meta-annotation `@CriticalOperation`. Các fragments này cần annotation type có `@Retention(RUNTIME)` và `@Target` phù hợp; ví dụ hoàn chỉnh sẽ khai báo đầy đủ.

Khi cần đọc alias/override attributes trong composed annotations, nên dùng `AnnotatedElementUtils` hoặc `MergedAnnotations` thay vì tự loop `getAnnotations()` và parse annotation tree.

### 5.3. Nếu mục tiêu đơn giản là chọn method có annotation, có thể bind trực tiếp trong pointcut

Spring `@AspectJ` hỗ trợ:

```java
@Before(
    value = "execution(public * com.example..service.*.*(..))"
          + " && @annotation(audited)",
    argNames = "audited"
)
public void audit(TrackOperation audited) {
    System.out.println(audited.value());
}
```

Đây là **fragment** theo cú pháp annotation binding của Spring. Nếu bạn chỉ cần `TrackOperation` dùng để lọc **join point đang được advice** và lấy giá trị annotation tương ứng, `@annotation(audited)` thường đơn giản hơn tự dùng reflection.

Tuy nhiên, **đừng coi `@annotation` luôn đồng nghĩa `findMergedAnnotation` cho mọi trường hợp composed annotation, interface annotation và proxy strategy**. Đây là hai cơ chế với các quy tắc matching/binding riêng. Với interface/implementation khác nhau, generic bridge, composed annotations, hãy viết test trên Spring version thật.

Nếu advice đã chạy do `execution(...)` nhưng cần **kiểm tra annotation theo một policy fallback đặc biệt**, pipeline `getMostSpecificMethod` + `findMergedAnnotation` là cách kiểm soát điều kiện đọc metadata rõ hơn.

## 6. Lấy target class đúng cách

Trong advice, hai reference quan trọng là:

```java
Object proxy = jp.getThis();
Object target = jp.getTarget();
```

Đối với Spring AOP:

- `getThis()`: Spring proxy.
- `getTarget()`: target đang được advice.

Khi đọc annotation của **implementation method**, ưu tiên target class:

```java
Class<?> targetClass = AopUtils.getTargetClass(jp.getTarget());
```

Với target object bình thường, nó nhận diện class nghiệp vụ. Nếu gọi `jp.getThis().getClass()`, bạn có thể nhận class generated của JDK/CGLIB proxy và không tìm được method annotation cần thiết.

### 6.1. Cách nhận diện proxy

```java
Object bean = context.getBean("billingOperations");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

Đây là **fragment chẩn đoán**, cần biến `context`. Kiểm tra proxy style không thay thế được tìm target method, nhưng giúp giải thích vì sao cùng advice có thể thấy method representation khác nhau giữa cấu hình.

### 6.2. Nested proxies và scoped targets

Nếu ứng dụng có scoped proxy, custom `TargetSource`, nhiều lớp proxy hoặc transaction/security advisors, `getTarget()` và `getTargetClass` có thể cần diễn giải theo **lớp target thực sự đang được advice**. Spring còn có `AopProxyUtils.ultimateTargetClass(...)` cho những tình huống nhất định, nhưng một số cách unwrap có thể kích hoạt target creation hoặc không phù hợp với scoped/non-singleton target.

**Không tự động unwrap mọi proxy đến raw object chỉ để đọc annotation.** Ưu tiên API class metadata, dùng Spring proxy utilities có hiểu biết về target source, và kiểm thử đúng ApplicationContext/scopes của hệ thống.

## 7. Method annotations nằm ở interface, implementation hoặc superclass

Một service có thể khai báo chính sách tại nhiều vị trí:

```java
public interface BillingOperations {
    @TrackOperation("interface-policy")
    String pay(String id);
}

public class BillingService implements BillingOperations {
    @Override
    public String pay(String id) {
        return "paid:" + id;
    }
}
```

Đây là **fragments minh họa**, không phải project hoàn chỉnh. Khi method annotation chỉ đặt trên interface:

- `BillingService.class.getMethod(...).getDeclaredAnnotation(...)` trên implementation method có thể trả `null`.
- `BillingOperations.class.getMethod(...).getAnnotation(...)` có thể thấy annotation.
- Spring merged annotation search với **find semantics** có khả năng tìm metadata từ method hierarchy, bao gồm các method tương ứng ở interface theo API và version.
- Nếu codebase cần **ưu tiên annotation implementation, fallback annotation interface**, phải mô tả chính sách rõ ràng và test đúng ordering.

Một mẫu fallback có chủ đích:

```java
Method signatureMethod =
        ((MethodSignature) jp.getSignature()).getMethod();

Method implementationMethod =
        AopUtils.getMostSpecificMethod(
                signatureMethod,
                AopUtils.getTargetClass(jp.getTarget())
        );

TrackOperation metadata = AnnotatedElementUtils.findMergedAnnotation(
        implementationMethod, TrackOperation.class
);

if (metadata == null && !implementationMethod.equals(signatureMethod)) {
    metadata = AnnotatedElementUtils.findMergedAnnotation(
            signatureMethod, TrackOperation.class
    );
}
```

Đây là **fragment đặt trong advice** và không nên sao chép nguyên xi khi có conflicting annotations trên implementation/interface mà chưa định nghĩa precedence. `findMergedAnnotation` đã thực hiện hierarchy search trong nhiều tình huống; fallback minh họa việc **không bỏ quên interface `Method` ban đầu**, chứ không phải khẳng định Spring API luôn cần hai lần tìm.

### 7.1. `@Inherited` không phải giải pháp cho method annotations

Java `@Inherited` chỉ ảnh hưởng cơ chế lookup annotation trên **class inheritance** theo contract của Java, **không làm method annotation tự kế thừa trong mọi override**. Không thêm `@Inherited` vào method-level annotation rồi kỳ vọng `Method.getAnnotation` tự hợp nhất annotation từ interface method.

Nếu cần policy kế thừa qua method hierarchy, hãy dùng API Spring phù hợp như `AnnotatedElementUtils.findMergedAnnotation`, đồng thời xác định và test precedence giữa interface, superclass và implementation.

### 7.2. Composed annotations và `@AliasFor`

Ví dụ nâng cao:

```java
@TrackOperation("default")
public @interface BusinessOperation {
    // Có thể dùng @AliasFor để override thuộc tính TrackOperation.
}
```

Đây là **fragment khái niệm**; muốn override phải khai báo đầy đủ `@AliasFor(annotation=..., attribute=...)`, retention và target. Không thể mặc định rằng mọi property tên giống nhau tự merge như mong muốn: Spring meta-annotation aliasing có quy tắc riêng và có thể báo lỗi khi cấu hình không nhất quán.

Nếu chỉ cần một label cố định cho composed annotation, `@TrackOperation("critical")` trên annotation type thứ hai đã đủ cho ví dụ runnable.

## 8. Ví dụ Java 17+ hoàn chỉnh: JDK proxy, CGLIB và annotation trên implementation

Mục tiêu của ví dụ:

1. Khai báo `BillingOperations` interface **không có method annotation**.
2. Class `BillingService` implement interface, đặt **`@TrackOperation("payment")` trực tiếp trên `pay`**.
3. Đặt **`@CriticalOperation`** (meta-annotated với `@TrackOperation("critical")`) trên `cancel`.
4. Không có annotation trên `ping`.
5. Dùng **một `@Around` Spring advice** chọn method executions của target `BillingOperations`, sau đó resolve most-specific method và merged annotation.
6. Chạy cùng project trong **hai ApplicationContexts độc lập**: JDK proxy và CGLIB proxy. Xác minh annotation trên implementation ở cả hai.
7. Đối chiếu trực tiếp `Method` lấy từ interface với most-specific implementation `Method` mà **không dựa vào generated proxy class name**.

Môi trường cố định: **Java 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1, Maven**. Đây là bộ phiên bản minh họa, **không phải tuyên bố phiên bản mới nhất**.

### 8.1. Cấu trúc project

```text
spring-aop-correct-method-annotation/
├── pom.xml
└── src/main/java/com/example/methodanno/
    ├── TrackOperation.java
    ├── CriticalOperation.java
    ├── BillingOperations.java
    ├── BillingService.java
    ├── InspectAspect.java
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
    <artifactId>spring-aop-correct-method-annotation</artifactId>
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

`spring-context` cung cấp `ApplicationContext` và các Spring AOP dependencies trong cây phụ thuộc của cấu hình ví dụ. `aspectjweaver` cung cấp thư viện để Spring phân tích `@AspectJ` pointcut expressions. **Không cấu hình compile-time/load-time AspectJ weaving**.

### 8.3. `src/main/java/com/example/methodanno/TrackOperation.java`

```java
package com.example.methodanno;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
public @interface TrackOperation {
    String value();
}
```

Hai target types có chủ đích:

- `METHOD`: cho phép đặt `@TrackOperation("payment")` trực tiếp trên method.
- `ANNOTATION_TYPE`: cho phép đặt `@TrackOperation("critical")` **trên một annotation khác** để tạo meta-annotation.

`RUNTIME` giúp Spring đọc marker tại runtime.

### 8.4. `src/main/java/com/example/methodanno/CriticalOperation.java`

```java
package com.example.methodanno;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@TrackOperation("critical")
public @interface CriticalOperation {
}
```

`@CriticalOperation` là **composed annotation** đơn giản. Một method chỉ mang `@CriticalOperation` không cần trực tiếp khai báo `@TrackOperation`; Spring `findMergedAnnotation` có thể nhận diện `TrackOperation` qua meta-annotation.

### 8.5. `src/main/java/com/example/methodanno/BillingOperations.java`

```java
package com.example.methodanno;

public interface BillingOperations {
    String pay(String id);
    String cancel(String id);
    String ping();
}
```

Interface **không có method-level annotation**. Đây là điều kiện giúp kiểm chứng lỗi “đọc nhầm method trên interface” một cách xác định.

### 8.6. `src/main/java/com/example/methodanno/BillingService.java`

```java
package com.example.methodanno;

public class BillingService implements BillingOperations {

    @Override
    @TrackOperation("payment")
    public String pay(String id) {
        System.out.println("[TARGET] pay " + id);
        return "paid:" + id;
    }

    @Override
    @CriticalOperation
    public String cancel(String id) {
        System.out.println("[TARGET] cancel " + id);
        return "cancelled:" + id;
    }

    @Override
    public String ping() {
        System.out.println("[TARGET] ping");
        return "pong";
    }
}
```

Ba methods dùng chung **target class** nhưng annotation khác nhau:

- `pay`: direct `@TrackOperation("payment")`.
- `cancel`: `@CriticalOperation`, gián tiếp mang meta-annotation `TrackOperation("critical")`.
- `ping`: không có annotation thuộc policy này.

### 8.7. `src/main/java/com/example/methodanno/InspectAspect.java`

```java
package com.example.methodanno;

import java.lang.reflect.Method;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;

@Aspect
public class InspectAspect {

    @Around(
        "target(com.example.methodanno.BillingOperations)"
        + " && execution(public * com.example.methodanno..*.*(..))"
    )
    public Object inspect(ProceedingJoinPoint pjp) throws Throwable {
        Method signatureMethod =
                ((MethodSignature) pjp.getSignature()).getMethod();

        Class<?> targetClass = AopUtils.getTargetClass(pjp.getTarget());

        Method actualMethod = AopUtils.getMostSpecificMethod(
                signatureMethod, targetClass);

        TrackOperation marker = AnnotatedElementUtils.findMergedAnnotation(
                actualMethod, TrackOperation.class);

        String label = (marker == null) ? "none" : marker.value();
        System.out.println("[ASPECT] method="
                + actualMethod.getName() + ", marker=" + label);

        return pjp.proceed();
    }
}
```

Vì advice dùng **`target(BillingOperations)` và `execution(public ...)`**, nó chỉ áp dụng cho public method executions của target phù hợp với interface và package trong demo; **không đòi target method phải có `TrackOperation`**. Đây là lựa chọn có chủ đích để `ping` không có marker vẫn bị inspect và in `marker=none`.

Nếu mục tiêu production là **chỉ chặn annotated operations**, nên cân nhắc `@annotation` trong pointcut (sau khi kiểm tra semantics của annotations/implementation/interface) hoặc sử dụng Spring `Pointcut`/advisor có predicate tương đương. **Đừng nhân rộng một advice reflection trên mọi method của cả ứng dụng** nếu chỉ cần vài annotated methods.

### 8.8. `src/main/java/com/example/methodanno/DemoApp.java`

```java
package com.example.methodanno;

import java.lang.reflect.Method;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;
import org.springframework.core.annotation.AnnotatedElementUtils;

public class DemoApp {

    @Configuration
    static class Beans {
        @Bean
        BillingOperations billingOperations() {
            return new BillingService();
        }

        @Bean
        InspectAspect inspectAspect() {
            return new InspectAspect();
        }
    }

    @Configuration
    @Import(Beans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    static class JdkProxyConfig {
    }

    @Configuration
    @Import(Beans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class CglibProxyConfig {
    }

    private static void inspectContext(String name, Class<?> config)
            throws NoSuchMethodException {

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(config)) {

            BillingOperations service = context.getBean(BillingOperations.class);

            System.out.println("[" + name + "] jdk="
                    + AopUtils.isJdkDynamicProxy(service));
            System.out.println("[" + name + "] cglib="
                    + AopUtils.isCglibProxy(service));

            Method apiMethod =
                    BillingOperations.class.getMethod("pay", String.class);

            Method implementationMethod = AopUtils.getMostSpecificMethod(
                    apiMethod, AopUtils.getTargetClass(service));

            System.out.println("[" + name + "] interfaceDirect="
                    + (apiMethod.getDeclaredAnnotation(TrackOperation.class)
                       != null));

            System.out.println("[" + name + "] implementationDirect="
                    + (implementationMethod.getDeclaredAnnotation(
                            TrackOperation.class) != null));

            System.out.println("[" + name + "] implementationMarker="
                    + AnnotatedElementUtils.findMergedAnnotation(
                            implementationMethod, TrackOperation.class).value());

            System.out.println("[" + name + "] pay="
                    + service.pay("P-1"));

            System.out.println("[" + name + "] cancel="
                    + service.cancel("C-2"));

            System.out.println("[" + name + "] ping="
                    + service.ping());
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        inspectContext("JDK", JdkProxyConfig.class);
        inspectContext("CGLIB", CglibProxyConfig.class);
    }
}
```

Hai contexts được tạo **độc lập**. Nếu dùng `@EnableAspectJAutoProxy(proxyTargetClass=false)` và `true` cùng một context, Spring có cơ chế hợp nhất hạ tầng auto-proxy; class-based setting mạnh hơn có thể chi phối và làm sai phép so sánh. Hai contexts tách biệt bảo đảm phép thử thực sự quan sát hai chiến lược.

`apiMethod` trong `DemoApp` được lấy **tường minh từ interface** để chứng minh direct annotation absent; không cần đặt giả định output vào cách `MethodSignature.getMethod()` thể hiện chi tiết trên CGLIB runtime. Đây là cách dựng phép thử đáng tin hơn việc assert string tên generated proxy class.

### 8.9. Chạy chương trình và stdout kỳ vọng

Yêu cầu JDK 17+, Maven và quyền tải dependencies. Từ thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.methodanno.DemoApp
```

Các dòng do chương trình in ra (bỏ qua log Spring/Maven/SLF4J nếu môi trường có):

```text
[JDK] jdk=true
[JDK] cglib=false
[JDK] interfaceDirect=false
[JDK] implementationDirect=true
[JDK] implementationMarker=payment
[ASPECT] method=pay, marker=payment
[TARGET] pay P-1
[JDK] pay=paid:P-1
[ASPECT] method=cancel, marker=critical
[TARGET] cancel C-2
[JDK] cancel=cancelled:C-2
[ASPECT] method=ping, marker=none
[TARGET] ping
[JDK] ping=pong
[CGLIB] jdk=false
[CGLIB] cglib=true
[CGLIB] interfaceDirect=false
[CGLIB] implementationDirect=true
[CGLIB] implementationMarker=payment
[ASPECT] method=pay, marker=payment
[TARGET] pay P-1
[CGLIB] pay=paid:P-1
[ASPECT] method=cancel, marker=critical
[TARGET] cancel C-2
[CGLIB] cancel=cancelled:C-2
[ASPECT] method=ping, marker=none
[TARGET] ping
[CGLIB] ping=pong
```

**Giải thích:**

1. JDK context có interface-based proxy; CGLIB context ép class proxy, trong khi **target implementation và aspect code không đổi**.
2. `interfaceDirect=false` vì chúng ta cố ý không đặt `@TrackOperation` lên `BillingOperations.pay`.
3. `implementationDirect=true` vì annotation trực tiếp nằm trên `BillingService.pay`.
4. `implementationMarker=payment` là giá trị được tìm trên implementation method qua Spring API.
5. Advice đọc `pay` có marker `payment`, dù JDK proxy cho caller làm việc qua interface.
6. Advice đọc `cancel` có marker `critical` nhờ `@CriticalOperation` là meta-annotated.
7. Advice đọc `ping` có marker `none` nhưng vẫn cho phép target method chạy; **không đọc được annotation** không đồng nghĩa **method không được gọi**.
8. Hai contexts cho thấy **một cách normalize target method dùng được cho cả JDK và CGLIB**. Không có nhu cầu tạo một nhánh reflection riêng chỉ vì loại proxy khác nhau.

Lệnh và stdout là kết quả **dự kiến theo code**. Khi tích hợp vào codebase thực, hãy chạy bằng đúng Spring/JDK/proxy configuration của dự án; ví dụ chưa phải một kiểm chứng tự động cho mọi loại `TargetSource`, nested proxy, bridge methods hoặc annotation hierarchy.

## 9. Khi annotation nằm trên interface mà không nằm trên implementation

Bài demo đặt marker ở implementation. Nhưng một codebase khác có thể muốn annotation làm **hợp đồng API của interface**:

```java
public interface BillingOperations {
    @TrackOperation("api-payment")
    String pay(String id);
}
```

và implementation:

```java
@Override
public String pay(String id) {
    return "paid:" + id;
}
```

Hai fragments mô tả một **cấu hình thay thế**, không sửa project runnable ở phần 8.

Trong mô hình này:

- Direct lookup trên interface method có thể thấy marker.
- Direct lookup trên concrete method không nhất thiết thấy marker.
- `AnnotatedElementUtils.findMergedAnnotation(concreteMethod, TrackOperation.class)` có **find semantics** và có khả năng khám phá method hierarchy (bao gồm các interfaces) theo API Spring.
- Việc một **pointcut `@annotation` có match** annotation chỉ ở interface hay không cần test riêng; không đồng nhất annotation hierarchy resolution với AspectJ pointcut matching.
- Nếu interface và implementation mang **hai marker xung đột**, application phải định nghĩa cách ưu tiên, không để chi tiết proxy style quyết định policy ngẫu nhiên.

**Khuyến nghị thực hành:** Chọn một source of truth nhất quán. Chẳng hạn: “annotation policy luôn đặt trên concrete service method”, hoặc “interface API là nguồn khai báo chính và implementation không ghi đè tùy tiện”. Document và kiểm thử quy tắc để tránh silent drift.

## 10. Xử lý annotation hợp nhất và `@AliasFor`

Trong ứng dụng Spring, composed annotations cho phép thiết kế meta-policy:

```java
@TrackOperation("critical")
public @interface CriticalOperation {}
```

Dạng đầy đủ phải thêm `@Target`, `@Retention` đúng như project runnable. Khi `@CriticalOperation` nằm trên method, `getDeclaredAnnotation(TrackOperation.class)` thường không tìm thấy vì method không gắn trực tiếp `TrackOperation`; `findMergedAnnotation` có thể tìm thấy nó.

Nếu muốn composed annotation có attribute để **override** `value` của `TrackOperation`:

```java
@TrackOperation("default")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface ClassifiedOperation {

    @org.springframework.core.annotation.AliasFor(
        annotation = TrackOperation.class,
        attribute = "value"
    )
    String value() default "default";
}
```

Đây là **fragment annotation definition**; cần import `java.lang.annotation.*` hoặc import từng type, và `TrackOperation` cho phép `ANNOTATION_TYPE`. Với `@ClassifiedOperation("vip")`, `findMergedAnnotation(method, TrackOperation.class)` có thể tạo synthesized annotation `value="vip"`.

Các lưu ý:

- Chỉ những alias hợp lệ theo Spring `@AliasFor` semantics mới hoạt động; giá trị mặc định và cấu trúc meta-annotation phải nhất quán.
- `getAnnotation` hoặc `getDeclaredAnnotation` thông thường **không tự áp dụng** meta-annotation attribute override của Spring.
- Nếu code cần merged annotation trên class hierarchy, nên kiểm tra rõ `findMergedAnnotation` vs `getMergedAnnotation`: **find semantics** tra cứu rộng hơn theo cấu trúc phù hợp.
- Đừng xây dựng policy audit/security bằng cách đọc `toString()` của annotation hoặc dùng tên runtime proxy class; lấy metadata type-safe theo annotation type.

## 11. Những lỗi phổ biến khi dùng reflection trong Spring advice

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `method.getAnnotation(...)=null` nhưng implementation có annotation | `MethodSignature.getMethod()` là interface method trên JDK proxy. | Lấy target class, gọi `AopUtils.getMostSpecificMethod` rồi tìm annotation. |
| Nhìn vào `getThis().getClass()` thấy `jdk.proxy...` | Đang nhìn generated proxy class, không phải target. | Dùng `getTarget()`, `AopUtils.getTargetClass`. |
| Reflection gọi `getMethod(name)` ném lỗi | Method thật có tham số; overloads/parameter types bị bỏ qua. | Dùng `MethodSignature.getMethod()` rồi resolve target method. |
| Annotation trực tiếp không có nhưng meta-annotation có | Dùng `getDeclaredAnnotation` thay vì Spring merged search. | Dùng `AnnotatedElementUtils.findMergedAnnotation` khi cần composed metadata. |
| Generic method có bridge method và metadata không đúng | Đang đọc compiler-generated bridge method. | Dùng `AopUtils.getMostSpecificMethod` / `BridgeMethodResolver` theo API Spring. |
| Annotation chỉ nằm ở interface, tìm trực tiếp trên implementation trả null | Method-level annotation không tự kế thừa như class annotation. | Dùng find semantics hoặc chính sách fallback interface method rõ ràng. |
| Advice chạy trên method không annotate | Pointcut `execution` rộng; reflection trong advice không phải pointcut predicate. | Đặt điều kiện annotation trong pointcut khi phù hợp hoặc tự skip logic trong advice. |
| `@annotation(marker)` không bind như mong đợi | Tên advice parameter/`argNames` không khớp, hoặc annotation placement/proxy style khác giả định. | Kiểm tra naming, type và annotated method; test implementation/interface. |
| Spring bean không bị advice | Aspect chưa thành Spring bean, chưa bật AOP, pointcut không match hoặc caller bypass proxy. | Kiểm tra bean registration, `@EnableAspectJAutoProxy`, `AopUtils`, invocation path. |
| CGLIB proxy không intercept method `final` | CGLIB không override được method đó. | Điều chỉnh public method contract hoặc proxy strategy phù hợp. |
| Có cùng tên method ở nhiều overloads, đọc nhầm annotation | Sử dụng method name string thay vì complete method signature. | Giữ `Method` và parameter types trong resolution. |
| Class bị move/rename và expression cũ không match | String pointcut hardcode old package/class. | Dùng stable named pointcut/annotation contract + behavior tests. |
| `@Inherited` trên annotation method không giúp | Java `@Inherited` không áp dụng phương thức theo cách giả định. | Dùng hierarchy-aware Spring annotation utility, thiết kế quy ước placement. |
| Đọc annotation bằng `proxy.getClass().getDeclaredMethods()` | Generated proxy overrides không phải source of truth. | Resolve target class/method trước. |

## 12. Chẩn đoán theo trình tự để tìm “đúng method”

Một quy trình có thể áp dụng khi Spring advice đã chạy nhưng annotation trả `null`:

1. **Xác nhận proxy thực:** Bean được Spring tạo/cung cấp, `AopUtils.isAopProxy(bean)` ra sao?
2. **Xác định method trong advice:** `((MethodSignature) jp.getSignature()).getMethod()`, class khai báo và parameter types của method.
3. **Xác định target thực:** `jp.getTarget()`, `AopUtils.getTargetClass(...)`; không lấy class generated từ `jp.getThis()` làm business class.
4. **Tìm most-specific method:** `AopUtils.getMostSpecificMethod(signatureMethod,targetClass)`.
5. **Kiểm tra placement:** annotation đặt trên concrete method, interface method, parent method hay meta-annotation?
6. **Chọn lookup semantics:** `getDeclaredAnnotation` nếu cần direct-only; `findMergedAnnotation` nếu cần hierarchy/composition.
7. **Xử lý generic bridge methods:** API Spring giúp giải quyết nhiều trường hợp; test các generic interfaces/overrides quan trọng.
8. **Xem lại pointcut:** `@annotation` dùng matcher của pointcut, không nhất thiết giống hoàn toàn custom reflection policy.
9. **Kiểm tra method call boundary:** self-invocation hoặc target object tự `new` không đi qua Spring proxy, nên advice không chạy để đọc metadata.
10. **Đưa các trường hợp vào integration test** thay vì chỉ debug bằng class names từ stdout.

Chỉ cần có `isAopProxy=true` **chưa đủ**: bean có thể được proxy vì transaction, cache hoặc advisor khác, trong khi pointcut audit của bạn không match method cần quan sát.

## 13. Checklist cho integration tests

Một bộ test đủ tin cậy nên có các cases:

| Case | Kết quả mong muốn |
| --- | --- |
| Annotation trực tiếp trên implementation, JDK proxy | Đọc ra metadata implementation thông qua most-specific method. |
| Annotation trực tiếp trên implementation, CGLIB proxy | Đọc ra metadata nhất quán với JDK. |
| Annotation chỉ trên interface method | Đọc ra metadata theo policy hierarchy/fallback đã document. |
| Annotation ở superclass method hoặc override | Đọc đúng precedence được ứng dụng quy định. |
| Method có composed annotation | `findMergedAnnotation` đọc ra annotation hợp nhất và attributes mong đợi. |
| Generic override có bridge method | Metadata đúng trên original method, không đọc nhầm compiler-generated method. |
| Method không annotate | Trả null hoặc “none” đúng ý đồ, không gây lỗi. |
| Hai overloads cùng tên, khác annotations | Không nhầm method/parameter types. |
| Caller bypass proxy bằng `this` hoặc `new` | Spring advice không chạy theo proxy AOP thông thường. |
| Đổi proxy style khi refactor | Annotation lookup vẫn đọc đúng với target type thật. |

Một test tốt không chỉ assert `method.getName()`, mà phải assert **marker.value()** trên method cụ thể, kèm đúng số lần advice/target chạy. Nếu annotation điều khiển security/audit/transaction policy, hãy test cả **trường hợp không đủ điều kiện** và exception paths.

## 14. Nên dùng reflection trong advice hay binding trực tiếp `@annotation`?

**Dùng `@annotation` binding khi:**

- Policy phụ thuộc đúng annotation trên method mà Spring pointcut engine match.
- Không cần fallback tùy chỉnh từ implementation sang interface hoặc meta-annotation resolution khác.
- Muốn code advice ngắn, type-safe, rõ ý định.
- Có integration test bao phủ JDK/CGLIB và annotation placement thật.

**Dùng method resolution + Spring annotation utilities khi:**

- Advice được chọn rộng bằng `execution/target`, nhưng phải đọc marker để phân loại hành vi.
- MethodSignature có thể là interface method còn marker ở concrete implementation.
- Code cần đọc **composed/meta-annotations** với `@AliasFor`.
- Cần chính sách rõ về method hierarchy, overrides hoặc generic bridge methods.
- Muốn nhất quán khi thay đổi proxy style mà không dùng generated proxy classes.

**Không nên lạm dụng reflection** trong mỗi invocation nếu policy có thể chọn trực tiếp bằng một pointcut tĩnh/annotation có ý nghĩa. Nếu thực sự cần đọc method metadata thường xuyên, có thể cache theo **method/target class hoặc resolved method** với chiến lược thread-safe phù hợp. Chỉ cache immutable metadata, không cache `JoinPoint`/request-specific state trong singleton aspect; cân nhắc classloader và lifecycle khi ứng dụng hot-reload nhiều contexts.

## 15. Những ranh giới vẫn giữ nguyên của Spring AOP

Dù resolve đúng annotation, Spring proxy AOP vẫn có các giới hạn cơ bản:

- **Spring quản lý bean và có advisor áp dụng:** đối tượng `new` ngoài container không tự được Spring AOP xử lý.
- **Caller đi qua proxy:** lời gọi `this.method()` nội bộ trên target không quay lại proxy.
- **JDK proxy:** lời gọi đi qua contract của proxied interfaces; không thể cast JDK proxy về mọi concrete implementation.
- **CGLIB proxy:** class `final` không subclass được; method `final/private` không được advice bằng override theo mô hình thông thường.
- **Thời điểm khởi tạo:** constructor/init callback trên raw target không giống lời gọi nghiệp vụ bình thường sau khi proxy được trao cho caller.
- **Context/scope:** creator hoạt động trong context; scoped proxies/custom target sources có lớp indirection cần kiểm thử riêng.
- **Annotation placement:** Java reflection `@Inherited` không tự giải quyết method hierarchy; Spring annotation search có semantics và giới hạn riêng.

Đọc đúng metadata **không thay thế thiết kế call boundary và pointcut**. Một annotation rất đúng trên implementation vẫn không tạo advice cho self-invocation mà proxy không nhìn thấy.

### Tài liệu Spring Framework chính thức

- **AopUtils.getMostSpecificMethod — Spring Framework 6.1.14 Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/aop/support/AopUtils.html
- **AnnotatedElementUtils — Spring annotation hierarchy, composed annotations:** https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/annotation/AnnotatedElementUtils.html
- **BridgeMethodResolver — Spring Framework Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/BridgeMethodResolver.html
- **Declaring Advice — annotation binding with `@annotation`:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- **Declaring a Pointcut — `@annotation`, `this`, `target`:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- **Proxying Mechanisms — JDK/CGLIB and self-invocation:** https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Kết luận:** Khi một object là Spring AOP proxy, `MethodSignature.getMethod()` không nhất thiết là **phương thức triển khai mang annotation nghiệp vụ**. Để đọc đúng trong Spring Aspect, hãy xác định **target class**, chuẩn hóa sang **most-specific method** bằng `AopUtils.getMostSpecificMethod`, rồi dùng **Spring merged annotation utilities** nếu cần meta-annotation hoặc hierarchy search. Kiểm thử trên cả JDK và CGLIB proxy giúp tránh những lỗi “annotation có trên source nhưng advice đọc ra null”.
