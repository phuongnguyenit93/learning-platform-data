# Spring AOP `@Around`: giữ đúng giá trị trả về và kiểu dữ liệu của phương thức đích

## 1. Vấn đề: method chạy đúng nhưng caller nhận sai kết quả

Trong **Spring AOP dựa trên proxy**, `@Around` là advice có khả năng đứng bao quanh lời gọi một method của Spring-managed bean. Advice quyết định có gọi `ProceedingJoinPoint.proceed()` hay không, và **giá trị mà advice trả về chính là giá trị cuối cùng caller nhìn thấy**, miễn giá trị đó tương thích với method contract.

Một lỗi dễ mắc:

```java
@Around("execution(* demo.returns.PricingService.label(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    System.out.println("result = " + result);
    return null; // SAI: làm mất giá trị mà method đích vừa trả về.
}
```

Target có thể đã trả `"LABEL-A1"`, nhưng caller lại nhận `null`. Chỉ một chữ `return null` trong advice đủ đổi ý nghĩa API, dù code của target không thay đổi.

Cách mặc định an toàn khi chỉ cần đo thời gian, logging hoặc telemetry:

```java
@Around("execution(* demo.returns.PricingService.label(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    System.out.println("result = " + result);
    return result; // Giữ nguyên kết quả method đích.
}
```

Hai đoạn trên là **fragment** để minh họa, không phải file chạy độc lập. Trong ví dụ thực tế cần có `@Aspect`, aspect là Spring bean, hạ tầng AOP và bean target được quản lý bởi Spring.

**Quy tắc quan trọng nhất:** với một `@Around` chỉ quan sát, hãy `return pjp.proceed()` hoặc giữ kết quả trong biến rồi `return result`. Đừng cố ý sửa kết quả nếu bài toán không đòi hỏi thay đổi contract.

Bài chỉ tập trung vào **Spring Aspect/Spring AOP proxy** và những ranh giới khi giữ đúng kiểu/kết quả method. Đây không phải phần giới thiệu AOP nói chung hay AspectJ bytecode weaving.

## 2. Giá trị trả về đi theo đường nào?

```text
Caller
  |
  | PricingOperations.priceInCents(3)
  v
Spring AOP proxy (JDK hoặc CGLIB)
  |
  | pointcut match
  v
@Around advice
  |
  | Object value = pjp.proceed()
  v
Các interceptor còn lại / target.priceInCents(3)
  |
  | int 450
  v
proceed() trả Integer(450) do boxing trong API Object
  |
  | advice return chính giá trị đó
  v
Spring AOP proxy kiểm tra/trao lại kiểu theo method contract
  |
  v
Caller thấy int 450
```

Một số điểm cần hiểu chính xác:

1. `ProceedingJoinPoint.proceed()` có kiểu trả về Java là `Object` để hỗ trợ nhiều loại target methods.
2. Kiểu trả về **ở chữ ký method đích** vẫn là contract mà caller sử dụng, ví dụ `String`, `int`, `void`, `Optional<String>` hoặc `List<String>`.
3. Nếu target trả primitive như `int`, giá trị được biểu diễn dưới dạng wrapper `Integer` trong kết quả `Object`. Proxy cần đưa giá trị tương thích trở lại caller.
4. Với `void`, `proceed()` thông thường trả `null`; caller không sử dụng return value. Nhưng điều đó **không** có nghĩa nên trả `null` cho **mọi** method.
5. Trả một object không đúng kiểu có thể lỗi ở runtime; phương thức target chạy xong không bảo đảm caller nhận được giá trị đúng.
6. Nếu target ném exception, `proceed()` ném exception ấy và không trả value. Advice phải truyền tiếp hoặc xử lý exception có chủ đích; không được vô tình nuốt lỗi bằng một `finally return`.

### Tại sao Spring khuyến nghị advice method trả `Object`?

Tài liệu Spring Framework về `@Around` ghi rõ phương thức advice nên trả `Object` và tham số đầu tiên phải là `ProceedingJoinPoint`. Nếu **khai báo chính method advice có return type `void`**, Spring sẽ đưa **`null`** về caller, bỏ qua kết quả thực của `proceed()`. Do đó `void` cho advice là cái bẫy nghiêm trọng khi pointcut áp dụng cho các method không-void.

**Đúng:**

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object preserveResult(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

**Sai khi áp dụng cho non-void target:**

```java
@Around("execution(* demo.returns..*Service.*(..))")
public void discardResult(ProceedingJoinPoint pjp) throws Throwable {
    pjp.proceed(); // Method target chạy nhưng kết quả không được chuyển về caller.
}
```

Một `@Around` trên method có return type `String`, `int`, `List`... mà advice tự khai báo `void` có thể khiến caller nhận `null` hoặc phát sinh lỗi tương thích kiểu. Hãy khai báo `Object` và trả về kết quả theo contract.

## 3. Ma trận các kiểu trả về quan trọng

| Chữ ký target | `proceed()` trả qua `Object` | Giá trị advice nên trả khi không biến đổi | Nếu advice trả sai |
| --- | --- | --- | --- |
| `String label()` | `String` hoặc `null` | Đúng `String` gốc | Trả `Integer`: sai kiểu; `null` có thể vi phạm nghiệp vụ |
| `int total()` | `Integer` boxed | Chính `Integer` từ proceed | `null` không thể unbox thành `int`; `"42"` không là `int` |
| `long amount()` | `Long` boxed | `Long` | `Integer` không tự thành `Long` chỉ vì số tương đương |
| `boolean allowed()` | `Boolean` boxed | `Boolean` | `null` hoặc `"true"` không phù hợp |
| `void notifyUser()` | Thông thường `null` | `null` từ `proceed()` | Không dựa vào một return value của void method |
| `Optional<String> find()` | `Optional<String>` | Cùng `Optional` | `null` khác `Optional.empty()`; `String` không đúng contract |
| `List<String> list()` | `List<String>` ở mức object | Cùng `List` | Trả `Set` sai API; list có phần tử sai generic gây lỗi về sau |
| `CompletableFuture<String> loadAsync()` | `CompletableFuture<String>` | Chính future | Trả `String` trực tiếp sai method contract |
| `Mono<String> stream()` nếu dùng Reactor | Publisher `Mono<String>` | Chính publisher | Trả payload `String` thay publisher không hợp lệ |

Trong bảng, tên hàm chỉ để diễn giải; các API asynchronous/reactive chỉ có khi dependencies tương ứng được dùng. Không phải mọi loại lỗi đều ném cùng một exception trong mọi proxy implementation: **ClassCastException**, exception unboxing hoặc **Spring `AopInvocationException`** có thể xuất hiện theo vị trí/type mismatch. Điều quan trọng là **kiểu trả về cuối cùng phải tương thích**.

### 3.1. Reference type và nullability

`String`, domain DTO và các reference types có thể trả `null` về mặt ngôn ngữ Java, nhưng API nghiệp vụ có thể cấm null. Trả `null` vì advice quên `return result` là **phá contract** ngay cả khi không ném exception tức thì.

Trường hợp target trả `Optional.empty()` thì advice cần giữ một **Optional rỗng**, không thay bằng `null`. Caller hợp lý có thể gọi `result.isPresent()` mà không kiểm tra null, vì contract `Optional` kỳ vọng object Optional.

### 3.2. Primitive và boxed types

```java
public int calculate() {
    return 450;
}
```

Bên trong advice:

```java
Object result = pjp.proceed(); // Thường là Integer(450).
return result;                  // Spring trả int 450 đến caller.
```

Đây là các fragment. Nếu đổi thành `return null;`, `int` không có giá trị null. Spring AOP có thể phát sinh exception do null return trên primitive method. Nếu đổi thành `return "450";`, chuỗi không phải Integer tương thích với primitive int; Java không tự parse chuỗi.

Tránh hardcode trả `0` thay giá trị target chỉ vì để caller không lỗi: nó có thể làm dữ liệu đúng bị thay bằng kết quả sai mà không phát tín hiệu.

### 3.3. `void` có đặc điểm riêng

```java
public void announce(String id) {
    System.out.println("announce " + id);
}
```

Advice vẫn nên viết một cách thống nhất:

```java
@Around("execution(* demo.returns.PricingService.announce(..))")
public Object preserveVoid(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed(); // Đối với void: kết quả là null.
    return result;                 // Hợp lệ cho void method.
}
```

Một advice dạng `Object` có thể áp dụng cho cả method `void` lẫn non-void. **Không** viết `return "DONE"` chỉ vì muốn báo log thành công cho caller: void method không có giá trị trả về theo Java interface. Kết quả công việc cần phản ánh bằng side effect hoặc domain API được thiết kế rõ ràng.

## 4. Ví dụ lỗi phổ biến của `@Around`

### 4.1. Quên `return result`

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object broken(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    logResult(result);
    return null; // Sai với mọi non-void method cần giá trị.
}
```

Đây là fragment có `logResult` giả định. Lỗi không nhất thiết nằm ở target; phải xem stack trace và aspect chain để phát hiện advice đã **ghi đè** return.

### 4.2. Dùng `finally` để `return`

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object veryDangerous(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        return null; // Sai: thay cả return đúng lẫn exception của target.
    }
}
```

Trong Java, `return` ở `finally` có thể **đè** return của try, đồng thời **nuốt exception**. Đây là lỗi đặc biệt nguy hiểm với transaction và security checks.

Dùng finally chỉ để cleanup/logging:

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object safeCleanup(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        clearTemporaryContext();
    }
}
```

Ở đây `clearTemporaryContext()` là fragment giả định; nếu chính cleanup ném exception, nó vẫn có thể che lỗi/return trước đó. Code cleanup nên được thiết kế để không vô tình thay đổi kết quả nghiệp vụ.

### 4.3. Dùng sai phương thức advice

```java
@AfterReturning(
    pointcut = "execution(* demo.returns.PricingService.label(..))",
    returning = "value"
)
public String tryReplace(String value) {
    return "NEW-" + value;
}
```

Đây là fragment minh họa một ý tưởng **sai về semantics**: Spring `@AfterReturning` có thể bind value để quan sát, nhưng không dùng method return của advice này để thay hoàn toàn reference mà caller nhận. Nếu mục tiêu cần thay return, dùng `@Around` theo contract phù hợp. Trong thực hành, `@AfterReturning` nên là `void` nếu chỉ log/metric.

### 4.4. Ép kiểu một giá trị mà `proceed()` không bảo đảm

```java
Object result = pjp.proceed();
String text = (String) result; // Sai nếu pointcut cũng match int/List/void.
return text;
```

Với pointcut rộng, target có thể có return type khác String. Không cast cứng trừ khi expression và method signature bảo đảm. Mặc định tốt nhất là **return trực tiếp kết quả `proceed()`**.

### 4.5. Gọi `proceed()` hai lần ngoài ý muốn

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object duplicateCall(ProceedingJoinPoint pjp) throws Throwable {
    Object first = pjp.proceed();
    pjp.proceed(); // Gọi target lần hai nếu chain cho phép.
    return first;
}
```

Trong Spring AOP, `proceed()` có thể được gọi nhiều lần; nhưng với một method ghi dữ liệu, gửi email, thanh toán, lần thứ hai có thể tạo **side effect kép**. Một advice chỉ đo/log kết quả phải gọi `proceed()` **một lần**, không vô tình nhân đôi operation.

### 4.6. Dùng `return null` để “bỏ qua” execution

`@Around` có thể chủ động **không gọi `proceed()`**, ví dụ cache hit. Nhưng nếu lời gọi target được bỏ qua, advice phải trả **một giá trị tương thích với method**:

```java
@Around("execution(* demo.returns.PricingService.label(..))")
public Object cacheHit(ProceedingJoinPoint pjp) throws Throwable {
    String cached = lookupCache(pjp.getArgs()[0]); // Fragment, helper giả định.
    if (cached != null) {
        return cached; // Đúng kiểu String; cần đảm bảo đúng ngữ nghĩa.
    }
    return pjp.proceed();
}
```

Bỏ qua target không nhất thiết an toàn với `@Transactional`, logging, authorization hoặc side effects bên trong method. Cache chỉ phù hợp với operation có contract cho phép tái sử dụng kết quả; policy phải đảm bảo cache key, invalidation và dữ liệu nhạy cảm.

## 5. Chỉ thay đổi return khi có yêu cầu rõ ràng

Một `@Around` có quyền bọc hoặc thay thế return value. Nhưng đây là hành vi **có chủ đích**, không phải hiệu ứng phụ của tracing advice.

### 5.1. Thay string thành string

```java
@Around("execution(String demo.returns.PricingService.label(..))")
public Object uppercaseLabel(ProceedingJoinPoint pjp) throws Throwable {
    String result = (String) pjp.proceed();
    return result.toUpperCase(java.util.Locale.ROOT);
}
```

Đây là fragment mà pointcut giới hạn return type `String`. Nếu business contract cho phép đổi chuỗi, caller vẫn nhận `String` hợp lệ. Tuy nhiên, giữ **đúng kiểu** chưa chắc giữ **đúng giá trị/ngữ nghĩa**; viết test xác nhận đó là kết quả mong muốn.

### 5.2. Fallback phải đúng kiểu khi catch exception

```java
@Around("execution(* demo.returns.PricingService.maybeLookup(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return java.util.Optional.empty();
    }
}
```

Nếu target có contract `Optional<String>`, fallback `Optional.empty()` hợp lệ. Trả `null` hoặc chuỗi `"NOT_FOUND"` phá API. Với method `int calculate()`, fallback hợp lệ về mặt type có thể là một `Integer` tương ứng với `int`, nhưng **chọn số fallback** phải có ý nghĩa nghiệp vụ; không lặng lẽ trả 0 nếu đó là kết quả sai.

### 5.3. Không làm mất cùng reference khi chỉ muốn quan sát

Nếu một service trả domain object mutable, advice `return result` giữ **cùng reference**. Trả một DTO được tạo lại hoặc một copy có thể gây khác biệt về identity, lazy relations, proxy entities hoặc state mà caller trông đợi, kể cả khi field values có vẻ tương đương.

Một logging advice **không nên** map result sang String hoặc JSON rồi vô tình trả String thay object nghiệp vụ. Muốn serialize để log thì serialize thành biến khác, vẫn `return result`.

### 5.4. Generic return types

Giả sử method trả `List<String>`. Ở runtime, Java generics có type erasure; một raw `List<Integer>` cũng có thể đi qua một số cast đối với `List`, rồi gây lỗi khi caller đọc phần tử dưới dạng String. Vì vậy, check chỉ `result instanceof List` chưa bảo đảm giữ **generic contract**. Lựa chọn an toàn cho cross-cutting advice là chuyển nguyên object từ `proceed()`, không thay collection contents.

Với `Optional<User>`, `ResponseEntity<DTO>`, `Page<T>` hoặc các wrapper có metadata, giữ wrapper và nội dung trừ khi policy cụ thể đòi hỏi transformation đúng type.

## 6. Ví dụ hoàn chỉnh: một `@Around` bảo toàn nhiều kiểu trả về

Dự án sau dùng **Java 17, Spring Framework 6.2.x, Maven** không cần Spring Boot. Một advice duy nhất match nhiều method khác kiểu và gọi `proceed()` đúng một lần, sau đó trả nguyên object. Ví dụ nhằm kiểm chứng:

- `String` không bị thành null.
- `int` vẫn là `int` đối với caller dù `proceed()` trả boxed `Integer`.
- Method `void` vẫn chạy side effect; `proceed()` cho kết quả null.
- `Optional.empty()` là object Optional, không bị thay bằng null.
- `List<String>` không bị map sang loại object khác.
- Proxy vẫn phải bảo đảm Spring quản lý target và aspect; consumer lấy bean qua context.

### 6.1. Cấu trúc dự án

```text
spring-around-return-values/
├── pom.xml
└── src/main/java/demo/returns/
    ├── AppConfig.java
    ├── PricingOperations.java
    ├── PricingService.java
    ├── ReturnTraceAspect.java
    └── Main.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-around-return-values</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. `AppConfig.java`

```java
package demo.returns;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` tìm `@Service` và `@Aspect @Component` trong package. `@EnableAspectJAutoProxy` bật proxying. Target có interface và `proxyTargetClass=false` nên Spring Framework thuần dùng JDK interface proxy trong ví dụ.

### 6.4. `PricingOperations.java`

```java
package demo.returns;

import java.util.List;
import java.util.Optional;

public interface PricingOperations {
    String label(String id);
    int priceInCents(int quantity);
    void announce(String id);
    Optional<String> maybeLookup(String id);
    List<String> codes();
}
```

Các methods được công bố qua interface để caller giữ JDK proxy có thể gọi. Mỗi method trả một kiểu khác, đúng trọng tâm bảo toàn result của `@Around`.

### 6.5. `PricingService.java`

```java
package demo.returns;

import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class PricingService implements PricingOperations {
    @Override
    public String label(String id) {
        System.out.println("[target] label " + id);
        return "LABEL-" + id;
    }

    @Override
    public int priceInCents(int quantity) {
        System.out.println("[target] priceInCents " + quantity);
        return quantity * 150;
    }

    @Override
    public void announce(String id) {
        System.out.println("[target] announce " + id);
    }

    @Override
    public Optional<String> maybeLookup(String id) {
        System.out.println("[target] maybeLookup " + id);
        return "NONE".equals(id)
                ? Optional.empty()
                : Optional.of("SKU-" + id);
    }

    @Override
    public List<String> codes() {
        System.out.println("[target] codes");
        return List.of("A", "B");
    }
}
```

Service không chứa advice logic và không tự tạo proxy. Spring đăng ký bean nhờ `@Service` và component scan.

### 6.6. `ReturnTraceAspect.java`

```java
package demo.returns;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ReturnTraceAspect {
    @Around("execution(* demo.returns.PricingService.*(..))")
    public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
        String name = pjp.getSignature().getName();
        System.out.println("[around] enter " + name);

        Object result = pjp.proceed();

        String display = result == null ? "<null>" : result.toString();
        System.out.println("[around] exit " + name + " -> " + display);

        return result; // Chủ đích bảo toàn return value lẫn object identity.
    }
}
```

Khai báo `@Aspect` mô tả aspect, `@Component` đăng ký aspect thành Spring bean, `@Around` match các method trên `PricingService`. Advice dùng `Object` để không buộc result phải là String. Nó **không return `display`**, chỉ dùng `display` để in log. Với result null của void method, log `<null>` nhưng `return result` là hợp lệ.

Đây là demo quan sát kiểu, không phải logging recipe production: `result.toString()` trên object nhạy cảm/lazy-loaded/chi phí lớn có thể gây side effect hoặc rò dữ liệu. Với sản phẩm thật, log method name và metadata an toàn thay cho toàn bộ giá trị.

### 6.7. `Main.java`

```java
package demo.returns;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            PricingOperations port = context.getBean(PricingOperations.class);

            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(port));
            System.out.println("[caller] label=" + port.label("A1"));
            System.out.println("[caller] price=" + port.priceInCents(3));
            port.announce("B1");
            System.out.println("[caller] lookup=" + port.maybeLookup("NONE"));
            System.out.println("[caller] codes=" + port.codes());
        }
    }
}
```

Từ thư mục có `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.returns.Main
```

**Stdout xác định từ các lệnh `System.out` của ví dụ** (không kể Maven/Spring logs nếu có):

```text
jdkProxy=true
[around] enter label
[target] label A1
[around] exit label -> LABEL-A1
[caller] label=LABEL-A1
[around] enter priceInCents
[target] priceInCents 3
[around] exit priceInCents -> 450
[caller] price=450
[around] enter announce
[target] announce B1
[around] exit announce -> <null>
[around] enter maybeLookup
[target] maybeLookup NONE
[around] exit maybeLookup -> Optional.empty
[caller] lookup=Optional.empty
[around] enter codes
[target] codes
[around] exit codes -> [A, B]
[caller] codes=[A, B]
```

### 6.8. Vì sao output theo đúng thứ tự này?

1. Context lấy `PricingOperations` do Spring quản lý, aspect match service, JDK proxy phù hợp interface nên `jdkProxy=true`.
2. `port.label("A1")` đi qua advice: in `enter`, target trả `"LABEL-A1"`, advice in `exit` rồi **trả nguyên String**, caller in đúng giá trị.
3. `port.priceInCents(3)`: target trả primitive `int 450`; qua `Object` của `proceed()` được boxing thành `Integer(450)`, advice trả lại; caller có `int 450`.
4. `port.announce("B1")`: target là `void` nên `proceed()` có kết quả null; advice log `<null>` và caller không nhận business return.
5. `port.maybeLookup("NONE")`: target trả `Optional.empty()`; advice giữ nguyên Optional thay vì null.
6. `port.codes()`: target trả `List.of("A","B")`, advice giữ nguyên List; `toString()` của List tạo biểu diễn `[A, B]`.
7. Advice không gọi `proceed()` nhiều lần, không biến đổi giá trị, không tạo một error recovery trái với contract.

## 7. Kiểm tra return type khi cố ý transform dữ liệu

Nếu yêu cầu nghiệp vụ **cho phép** một `@Around` thay đổi value, hãy dựa trên return type thực tế của method đích. Từ `ProceedingJoinPoint.getSignature()` có thể lấy thông tin phương thức; Spring có helper để resolve method/target method trong trường hợp JDK proxy và bridge methods.

Một cách kiểm tra cơ bản dành cho method execution:

```java
MethodSignature signature = (MethodSignature) pjp.getSignature();
Class<?> returnType = signature.getReturnType();
System.out.println("Declared return type: " + returnType.getName());
```

Đây là fragment trong `@Around` và cần import `org.aspectj.lang.reflect.MethodSignature`. Nó giúp đọc kiểu return **được khai báo**, nhưng không phải validation đầy đủ của generics, nullability, custom serialization, transaction state hoặc object identity.

### 7.1. Tình huống method trả primitive

```java
if (returnType == int.class && result == null) {
    throw new IllegalStateException("Null result for primitive int");
}
```

Fragment này giúp bắt trường hợp rõ ràng, nhưng một framework proxy vẫn có quyền ném exception riêng khi advice trả null cho primitive. **Đừng** gán fallback `0` chỉ để biến lỗi thành success.

### 7.2. Tình huống method trả Optional

```java
Object result = pjp.proceed();
if (result instanceof java.util.Optional<?> optional) {
    System.out.println("present=" + optional.isPresent());
}
return result;
```

Không tự unwrap Optional rồi return thành String: caller đang mong `Optional<String>`. Nếu cần một fallback, trả `Optional.empty()` hoặc Optional hợp lệ theo contract, không return null.

### 7.3. Tình huống thay arguments

Spring cho phép `pjp.proceed(Object[] args)`. Mảng mới cần **đúng số phần tử, vị trí và kiểu tương thích với các parameters của method đích** trong ngữ cảnh Spring AOP:

```java
Object[] original = pjp.getArgs();
Object[] replacement = original.clone();
replacement[0] = "NORMALIZED";
return pjp.proceed(replacement);
```

Đây là fragment chỉ phù hợp với method có argument đầu tiên kiểu String. Đổi input không được làm biến đổi return contract; method vẫn có quyền trả/throw theo chữ ký. Không dùng `proceed(new Object[0])` cho method cần parameters, và không tưởng rằng việc thay args tự động tạo return type hợp lệ.

### 7.4. Tình huống future/reactive return type

Nếu method trả `CompletableFuture<String>`, `proceed()` có thể trả một future **chưa hoàn thành**. Một `@Around` chạy đồng bộ không có sẵn payload String của future; return `"ready"` để thay future là sai kiểu.

Khi cần transform kết quả asynchronous, có thể dùng:

```java
Object result = pjp.proceed();
if (result instanceof java.util.concurrent.CompletableFuture<?> future) {
    return future.thenApply(value -> value); // Giữ wrapper Future.
}
return result;
```

Đây là fragment minh họa, không phải một giải pháp tổng quát cho tất cả futures/generics; với `CompletableFuture<T>`, transformation phải giữ đúng `T` và error/completion semantics. Với Reactor `Mono<T>`/`Flux<T>` cần sử dụng operators và types tương ứng, không return payload trực tiếp thay publisher.

## 8. Exceptions và return value: không thể bảo toàn một cách máy móc

Advice có thể vừa giữ giá trị trả về bình thường vừa bảo đảm exception **không bị nuốt**:

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object preserveOutcome(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        System.out.println("elapsed ns=" + elapsed);
    }
}
```

Advice này không tự trả một fallback khi target ném exception. `throws Throwable` cho phép đưa exception từ `proceed()` đi tiếp. Lưu ý `System.nanoTime()` chỉ dùng đo khoảng thời gian tương đối, không dùng làm wall-clock.

Nếu muốn recovery:

```java
@Around("execution(* demo.returns.PricingService.maybeLookup(..))")
public Object recoverOptional(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return java.util.Optional.empty();
    }
}
```

Đây là một decision **thay đổi outcome có chủ đích**, chỉ phù hợp khi API nghiệp vụ cho phép chuyển lỗi cụ thể thành trạng thái không tìm thấy. Không catch `Throwable` rồi return null trên pointcut rộng: nó có thể che lỗi nghiêm trọng, đổi exception thành result sai và phá giao dịch.

### 8.1. Return đúng kiểu nhưng không đúng transaction state

Spring `@Transactional` thường dùng một advisor/interceptor khác. Một `@Around` đứng ngoài transaction interceptor có thể catch exception sau khi transaction đã bị đánh dấu rollback. Trả một DTO “success” từ outer advice không làm rollback-only tự biến mất. Vì vậy, **đúng return type chưa đủ** để bảo đảm transaction commit thành công.

### 8.2. Retry có thể tạo return cuối khác return ban đầu

Gọi `proceed()` hai hoặc nhiều lần để retry là một nghiệp vụ khác, không phải logging. Kết quả từ lần thực thi nào được trả cho caller, side effects có lặp không, exception cuối được ném thế nào đều phải được quy định rõ. Với method idempotent mới nên cân nhắc retry; transaction boundaries, timeout và logging cần được kiểm thử.

### 8.3. Advice khác có thể biến đổi return trước bạn

Trong interceptor chain có thể có caching, security, transactions, async proxy hoặc nhiều `@Around` advices. `pjp.proceed()` trả kết quả của **phần còn lại của chain**, không luôn là “return trực tiếp từ code target chưa qua biến đổi”. Nếu một interceptor bên trong chủ động trả cached value thì outer advice cũng sẽ nhận cached value. Vì vậy cần xác định ordering/chain thực tế khi behavior không giống target method độc lập.

## 9. JDK proxy, CGLIB và giới hạn lời gọi

Giữ return value trong `@Around` chỉ có ý nghĩa khi advice thực sự được gọi.

- **JDK dynamic proxy:** caller dùng public methods thuộc interface mà proxy thực hiện. Nếu implementation có method khác không ở interface, JDK proxy không tự expose method đó.
- **CGLIB class-based proxy:** có thể intercept method mà proxy subclass override được; không override được `final` hay `private`; không subclass được `final class`.
- **Self-invocation:** `this.someMethod()` bên trong target bypass proxy, kể cả method public; một advice match method ấy không được chạy trên lời gọi nội bộ.
- **Object tạo bằng `new` ngoài container:** không nhận Spring AOP proxy; advice không tự xuất hiện.
- **Pointcut không khớp:** method vẫn chạy bình thường, nhưng `@Around` không được áp dụng.
- **Aspect không đăng ký bean:** `@Aspect` một mình không làm Spring component scan tự đăng ký; cần `@Component` hoặc `@Bean` tương ứng.

Không đổi `proxyTargetClass=true` chỉ để sửa lỗi `return null` trong advice; loại proxy không thay thế nghĩa vụ trả đúng value của `@Around`.

## 10. Checklist chẩn đoán khi giá trị sau aspect sai

| Hiện tượng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Target in kết quả đúng, caller nhận null | Around advice quên `return result` hoặc khai báo `void` | Advice `Object` + `return pjp.proceed()` hoặc `return result` |
| Method `int` báo lỗi sau khi advice trả null | Primitive không thể có null | Trả đúng boxed value từ `proceed()` |
| Return `String` bị lỗi kiểu | Advice trả một kiểu khác, ví dụ `Integer` | Hạn chế pointcut hoặc giữ nguyên value |
| Caller của `Optional<String>` bị NPE | Advice thay `Optional.empty()` bằng null | Giữ `Optional` object |
| Generic List gây ClassCastException khi đọc phần tử | Advice thay List contents sai generic | Tránh thay đổi collection không được contract cho phép |
| `void` method không in return value | Đây là Java `void` bình thường | Log side effect trong advice; không đòi return |
| Target chạy hai lần | Advice gọi `proceed()` hai lần | Mặc định gọi đúng một lần |
| Exception biến mất | `catch` quá rộng hoặc `return` trong `finally` | Truyền exception đi tiếp; không return trong finally |
| Caching advice return sai DTO | Cache chứa object không đúng method contract | Thiết kế cache key/type và kiểm tra trước return |
| Trả `String` thay `CompletableFuture<String>` | Nhầm payload với wrapper | Giữ future/publisher và transform bằng API tương ứng |
| Trả đúng kiểu mà caller thấy state sai | Copy/mutate object trong logging advice | Giữ nguyên reference/immutable policy |
| Lỗi chỉ sau khi thêm logging | `result.toString()` có side effect hoặc ném exception | Log metadata an toàn; không để logging phá flow |
| @Around không chạy trên method nội bộ | Self-invocation bypass Spring proxy | Gọi qua Spring bean khác được DI |
| Advice chạy sai thứ tự với transaction/cache | Advisor ordering và nested chain | Test chain và thiết kế precedence |
| Target ném exception nhưng advice vẫn return "success" | Advice catch và nuốt lỗi | Chỉ dùng fallback nếu nghiệp vụ xác nhận |
| Một số method không có advice | Pointcut, proxy type, aspect bean registration | Kiểm tra Spring context, method visibility, loại proxy |

**Quy trình rà soát có hệ thống:**

1. Xác nhận target/aspect là Spring beans và hạ tầng Spring AOP đã bật.
2. Trên reference thực được DI hoặc lấy từ context, dùng `AopUtils.isAopProxy(bean)` và xác định JDK/CGLIB proxy.
3. Xác nhận pointcut chọn đúng method và caller đi qua proxy.
4. Xem chữ ký target: return type, primitive/reference, nullability, wrapper/generic, exceptions.
5. Xem advice khai báo `Object`, gọi `proceed()` bao nhiêu lần và có `return result` đúng ở mọi nhánh hay không.
6. Kiểm tra các nhánh `catch`/`finally`; tránh return trong finally và tránh nuốt exception ngoài policy.
7. Nếu biến đổi result, test đầy đủ success/failure/empty/null/async với type contract.
8. Kiểm tra các advisors khác như cache/transaction/security để xác định kết quả trong chain.

## 11. Câu hỏi ôn tập

**1. Vì sao `@Around` nên khai báo return type `Object`?** Vì `proceed()` trả `Object` và target methods có nhiều kiểu khác nhau. Lấy và trả chính kết quả ấy giúp proxy giữ contract caller.

**2. Nếu method trả `int 42` nhưng advice trả `null` thì sao?** Primitive không chứa null; proxy/unboxing có thể lỗi runtime. Không dùng null cho primitive.

**3. Method trả `Optional.empty()` thì advice có được đổi thành `null` không?** Về business contract thường là không. Caller kỳ vọng một Optional object; giữ nguyên Optional hoặc biến đổi theo policy xác định.

**4. Có phải cứ `pjp.proceed()` chạy xong là caller nhận target result?** Không. Giá trị cuối là **return của advice**. Nếu advice không trả result hoặc return khác, caller nhận value khác.

**5. Với target `void`, `proceed()` trả gì?** Thông thường `null` qua API `Object`; advice có thể trả chính null đó và caller vẫn thấy một void invocation hợp lệ.

**6. Vì sao `return result` tốt hơn `return result.toString()`?** Giá trị mới là String, có thể khác kiểu declared return; kể cả khi đúng String cũng có thể đổi semantics hoặc ném lỗi từ `toString()`.

**7. Có được gọi `proceed()` nhiều lần không?** Spring AOP cho phép về kỹ thuật, nhưng mỗi lần có thể thực thi lại operation. Nếu không chủ ý retry, chỉ gọi một lần.

**8. `@AfterReturning` có thể thay thế một reference hoàn toàn mới làm kết quả của target không?** Không theo contract thông thường; `@Around` mới có thể chủ động chọn return value khác.

**9. Khi method trả `CompletableFuture<T>`, advice nên trả `T` hay Future?** Phải trả type tương thích với method, tức future tương ứng, không phải payload trực tiếp.

**10. Return đúng kiểu có bảo đảm transaction commit không?** Không. Transaction interceptor có thể đã rollback/đánh dấu rollback-only trước khi outer advice catch exception; phải xét ordering và transaction boundary.

## Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice: Around Advice, proceeds and return value](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — Spring AOP Advice API / MethodInterceptor](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html)
- [Spring Framework — AOP Concepts và role của Around Advice](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html)
- [Spring Framework — Proxying Mechanisms: JDK/CGLIB/self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
