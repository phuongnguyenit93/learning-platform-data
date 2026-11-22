# Phân biệt đọc metadata bằng API Spring với khớp biểu thức AspectJ trong Spring AOP

## 1. Mục tiêu và phạm vi

Khi xây dựng annotation riêng cho một Spring bean, cần tách **hai việc**:

- **Đọc metadata bằng API Spring:** chủ động tra cứu xem một `Method`/`Class` mang annotation gì, giá trị thuộc tính là gì, có meta-annotation hay `@AliasFor` nào được Spring tổng hợp (merge) không.
- **Khớp biểu thức AspectJ trong Spring AOP:** khai báo pointcut để Spring chọn method execution nào sẽ chạy advice khi lời gọi **đi qua Spring proxy**. Ví dụ `@Around("@annotation(marker)")`.

**Tìm thấy annotation không đồng nghĩa advice chắc chắn chạy.** Hai cách có thể cùng xét annotation đó nhưng khác đầu vào, chính sách tìm kiếm và thời điểm kích hoạt.

Phạm vi chỉ gồm **Spring Aspect / Spring AOP dựa trên proxy** và API xử lý annotation của Spring; không trình bày lý thuyết AspectJ chung hoặc weaving của AspectJ compiler/load-time agent.

## 2. So sánh trực tiếp

| Tiêu chí | API Spring đọc metadata | Pointcut AspectJ trong Spring AOP |
|---|---|---|
| Mục tiêu | Lấy annotation hoặc giá trị cấu hình | Chọn join point mà advice áp dụng |
| Kích hoạt | Code của ứng dụng gọi API | Spring dựng advisor/proxy và intercept lời gọi phù hợp |
| Đối tượng xem xét | `AnnotatedElement`, `Method`, `Class<?>` | Method execution, target class và proxy |
| Công cụ điển hình | `AnnotatedElementUtils`, `AnnotationUtils`, `AopUtils`, `BridgeMethodResolver` | `@annotation`, `@within`, `@target`, `execution`, `bean` |
| Kết quả | Annotation, metadata hoặc `null` | Khớp/không khớp, có thể bind annotation vào advice |
| Thời điểm | Bất cứ khi nào code đọc, kể cả method chưa gọi | Khi cơ chế Spring AOP áp dụng advice cho lời gọi qua proxy |
| Annotation tổng hợp | `findMergedAnnotation` hiểu merge/meta-annotation/alias theo quy tắc Spring | Không mặc định tương đương chính sách “merged annotation” của API Spring |
| Lỗi hay nhầm | Đọc nhầm method từ interface hoặc proxy | Annotation tồn tại nhưng self-invocation, không có proxy, hoặc sai pointcut |

Ví dụ: `AnnotatedElementUtils.findMergedAnnotation(method, TraceAction.class)` có thể trả annotation trước khi `method` chạy. Trong khi đó, `@Around("@annotation(traceAction)")` chỉ chạy nếu Spring AOP thực sự intercept một method execution khớp.

## 3. Đọc metadata đúng cách với Spring

### 3.1. Reflection Java và API annotation của Spring

Với annotation đặt trực tiếp trên method, reflection thông thường có thể đọc:

```java
Method method = OrderService.class.getMethod("checkout", String.class);
TraceAction marker = method.getAnnotation(TraceAction.class);
```

Nếu ứng dụng dùng meta-annotation/composed annotation, alias thuộc tính hoặc cần tìm annotation theo hierarchy, Spring cung cấp các công cụ:

```java
TraceAction marker =
        AnnotatedElementUtils.findMergedAnnotation(method, TraceAction.class);
```

Một số API không đồng nhất về chính sách tìm:

- `AnnotatedElementUtils.getMergedAnnotation(...)`: lấy annotation đã merge từ phần tử với meta-annotation phù hợp.
- `AnnotatedElementUtils.findMergedAnnotation(...)`: tìm rộng hơn trên cấu trúc phân cấp tương ứng và tạo annotation đã merge.
- `AnnotationUtils.findAnnotation(...)`: tiện ích tra annotation theo cơ chế tìm riêng của Spring; không nên giả định nó luôn giống mọi hoạt động của `findMergedAnnotation`.
- `MergedAnnotations`: chọn `SearchStrategy` và duyệt metadata chi tiết khi quy tắc tìm kiếm cần rõ ràng.

`@AliasFor` chỉ có ý nghĩa theo cách xử lý synthesized/merged annotation của Spring. Một biểu thức `@annotation` trong AspectJ pointcut không tự động áp dụng y hệt mọi quy tắc tìm kiếm/merge của những API đó.

### 3.2. Class proxy khác class đích

Bean đã được bọc bởi Spring AOP có thể là JDK dynamic proxy hoặc subclass proxy. `bean.getClass()` không nhất thiết là lớp khai báo method nghiệp vụ.

Nếu cần đọc annotation trên implementation:

```java
Class<?> targetClass = AopUtils.getTargetClass(bean);
Method method = targetClass.getMethod("checkout", String.class);
TraceAction marker =
        AnnotatedElementUtils.findMergedAnnotation(method, TraceAction.class);
```

`AopUtils.getTargetClass` giúp lấy kiểu đích từ proxy Spring; từ đó đọc method triển khai thay vì nhầm method của proxy. Trong các ứng dụng có interface và overriding, vị trí đặt annotation vẫn phải được xem xét rõ.

Khi method ban đầu đến từ interface/signature, có thể tìm method cụ thể nhất và xử lý bridge do compiler sinh ra cho generic:

```java
Method interfaceMethod = /* Method đã có từ signature/interface */;
Class<?> targetType = AopUtils.getTargetClass(bean);
Method specificMethod =
        AopUtils.getMostSpecificMethod(interfaceMethod, targetType);
Method userMethod =
        BridgeMethodResolver.findBridgedMethod(specificMethod);
TraceAction marker =
        AnnotatedElementUtils.findMergedAnnotation(userMethod, TraceAction.class);
```

Đây là đoạn minh họa **nằm trong code đã có biến `bean` và `interfaceMethod`**, không phải chương trình Java độc lập. `AopUtils.getMostSpecificMethod` và `BridgeMethodResolver` xử lý hai vấn đề khác nhau: tìm method implementation và giải quyết bridge method.

### 3.3. Đọc được không có nghĩa là proxy intercept được

API metadata đọc một đối tượng phản chiếu, kể cả khi method không bao giờ được gọi. Spring AOP chỉ chạy advice khi method execution thuộc phạm vi pointcut và **lời gọi đi qua proxy**. Một đoạn startup scan đọc hết annotation trong package cũng không làm những method ấy được advice thực thi.

## 4. Khớp pointcut trong Spring Aspect

Đối với method annotation, cách rõ nhất là:

```java
@Around(value = "@annotation(traceAction)", argNames = "traceAction")
public Object trace(ProceedingJoinPoint pjp, TraceAction traceAction)
        throws Throwable {
    System.out.println("AOP: " + traceAction.value());
    return pjp.proceed();
}
```

- `@annotation(traceAction)` xác định method execution khớp annotation và **bind instance annotation** vào tham số `traceAction`.
- `argNames` giúp tên biến binding được xác định tường minh. `ProceedingJoinPoint` là tham số đặc biệt của around advice.
- `pjp.proceed()` cho method gốc tiếp tục thực thi. Bỏ lệnh đó trong `@Around` sẽ làm thay đổi hành vi method.
- Nếu chỉ lọc theo kiểu annotation, có thể dùng tên kiểu đầy đủ `@annotation(demo.TraceAction)`.

Các biểu thức Spring AOP hỗ trợ có liên quan:

| Biểu thức | Đối tượng khớp | Áp dụng |
|---|---|---|
| `@annotation(demo.TraceAction)` | Annotation gắn với method execution | Chính sách theo method marker |
| `@within(demo.AuditedType)` | Execution trong type được đánh dấu, theo quy tắc pointcut | Chính sách theo khai báo type |
| `@target(demo.AuditedType)` | Runtime target type có annotation tương ứng | Chính sách theo kiểu target |
| `execution(public * demo.service..*(..))` | Chữ ký method trong package | Giới hạn nhóm method |
| `bean(orderService)` | Spring bean có tên `orderService` | Giới hạn bean (mở rộng riêng của Spring) |

**Đặt `@TraceAction` trên class không có nghĩa nó khớp `@annotation` của method.** Nếu annotation thuộc type, hãy dùng đúng pointcut thuộc type và hiểu sự khác nhau giữa `@within`/`@target`.

Có thể phối hợp các biểu thức:

```java
@Around(value =
        "execution(public * demo.service..*(..)) && @annotation(traceAction)",
        argNames = "traceAction")
public Object trace(ProceedingJoinPoint pjp, TraceAction traceAction)
        throws Throwable {
    return pjp.proceed();
}
```

Đây là ví dụ đặt trong class `@Aspect` đã import các kiểu tương ứng. `demo.service` chỉ là package mẫu, cần đổi theo dự án thật. Kết hợp `execution` để tránh advice khớp quá rộng.

## 5. Ví dụ Java 17+ chạy được với Spring Boot

Ví dụ này dùng Spring Boot 3.3.x, Spring AOP và annotation `@TraceAction` để chứng minh hai đường xử lý độc lập. Các file đặt đúng đường dẫn; Java package chung là `demo`.

**`settings.gradle`**

```groovy
rootProject.name = 'spring-aop-metadata-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

**`src/main/java/demo/TraceAction.java`**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TraceAction {
    String value();
}
```

`RetentionPolicy.RUNTIME` là yêu cầu để đọc annotation trong runtime và để pointcut dựa trên annotation hoạt động. `@Target(METHOD)` xác định đây là marker của method.

**`src/main/java/demo/OrderService.java`**

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    @TraceAction("checkout")
    public String checkout(String orderId) {
        return "OK:" + orderId;
    }
}
```

**`src/main/java/demo/MetadataExplorer.java`**

```java
package demo;

import java.lang.reflect.Method;
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.stereotype.Component;

@Component
public class MetadataExplorer {
    private final OrderService orderService;

    public MetadataExplorer(OrderService orderService) {
        this.orderService = orderService;
    }

    public void showMetadata() throws NoSuchMethodException {
        Class<?> targetClass = AopUtils.getTargetClass(orderService);
        Method method = targetClass.getMethod("checkout", String.class);
        TraceAction marker =
                AnnotatedElementUtils.findMergedAnnotation(
                        method, TraceAction.class);
        System.out.println(
                "METADATA: " + (marker == null ? "missing" : marker.value()));
    }
}
```

`showMetadata()` chỉ đọc metadata của `checkout`; nó **không gọi `checkout`**, do đó không kích hoạt advice của method này.

**`src/main/java/demo/TrackingAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TrackingAspect {
    @Around(value = "@annotation(traceAction)", argNames = "traceAction")
    public Object trace(ProceedingJoinPoint pjp, TraceAction traceAction)
            throws Throwable {
        System.out.println("AOP: " + traceAction.value());
        return pjp.proceed();
    }
}
```

Spring tạo advisor/proxy từ `@Aspect` khi `spring-boot-starter-aop` hiện diện và cấu hình AOP của Boot được kích hoạt. Advice chỉ áp dụng cho method execution khớp `@annotation`, có bind marker để đọc `value()`.

**`src/main/java/demo/AopMetadataDemoApplication.java`**

```java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AopMetadataDemoApplication implements CommandLineRunner {
    private final MetadataExplorer explorer;
    private final OrderService orderService;

    public AopMetadataDemoApplication(
            MetadataExplorer explorer, OrderService orderService) {
        this.explorer = explorer;
        this.orderService = orderService;
    }

    public static void main(String[] args) {
        SpringApplication.run(AopMetadataDemoApplication.class, args);
    }

    @Override
    public void run(String... args) throws Exception {
        explorer.showMetadata();
        System.out.println("RESULT: " + orderService.checkout("A1"));
    }
}
```

Chạy với Gradle Wrapper tương thích đã có của dự án:

```bash
./gradlew bootRun
```

Windows: `.\gradlew.bat bootRun`. Với dự án mới chưa có wrapper, phải tạo hoặc cung cấp `gradlew`/`gradlew.bat`; chỉ viết `build.gradle` không tự sinh wrapper.

Các **dòng ứng dụng** được in theo thứ tự (Spring Boot có thể in thêm log khởi động):

```text
METADATA: checkout
AOP: checkout
RESULT: OK:A1
```

Diễn giải: `METADATA` xuất hiện trước lời gọi phương thức vì Spring API đọc được annotation; `AOP` xuất hiện khi lời gọi `orderService.checkout` đi qua proxy và khớp pointcut; `RESULT` là giá trị method sau `pjp.proceed()`.

Nếu xóa `@TraceAction` khỏi `checkout` và không thêm advisor khác, metadata in `missing` và lời gọi không chạy advice `trace`. Nếu chỉ chạy `explorer.showMetadata()` mà không gọi `checkout`, vẫn đọc được metadata nhưng không có dòng `AOP`.

## 6. Các tình huống dễ gây hiểu sai

### 6.1. Self-invocation: annotation có nhưng advice không chạy

Giả sử thêm vào `OrderService`:

```java
public String process(String id) {
    return checkout(id); // tương đương this.checkout(id)
}
```

Một bean khác gọi `orderService.process("A1")`. Lời gọi nội bộ từ `process` đến `checkout` thực hiện trực tiếp trong target, không đi qua Spring AOP proxy; advice của `checkout` không chạy vì lời gọi này. Tuy nhiên `AnnotatedElementUtils.findMergedAnnotation` vẫn tìm được `@TraceAction` trên method `checkout`.

Thiết kế rõ ràng thường là đưa method được advice vào một bean mà caller gọi thông qua Spring proxy. Đây là đặc điểm **Spring AOP proxy-based interception**, không phải dấu hiệu annotation bị mất.

### 6.2. Annotation trên interface và implementation

Với JDK dynamic proxy, signature có thể biểu diễn method ở interface; annotation thực tế có thể nằm ở implementation hoặc ngược lại. Khi dùng `MethodSignature` trong advice để tra cứu, method trả về không nhất thiết là method của target.

Mẫu tra cứu bên trong advice (biến `pjp` đã có):

```java
Method signatureMethod =
        ((org.aspectj.lang.reflect.MethodSignature)
                pjp.getSignature()).getMethod();
Class<?> targetType =
        org.springframework.aop.support.AopUtils.getTargetClass(pjp.getTarget());
Method specific =
        org.springframework.aop.support.AopUtils.getMostSpecificMethod(
                signatureMethod, targetType);
Method bridged =
        org.springframework.core.BridgeMethodResolver.findBridgedMethod(specific);
TraceAction marker =
        org.springframework.core.annotation.AnnotatedElementUtils
                .findMergedAnnotation(bridged, TraceAction.class);
```

Đây là **đoạn minh họa trong advice**, không phải file Java độc lập. Với annotation chỉ đặt trên interface/hierarchy, phải test pointcut trên đúng kiểu proxy và vị trí khai báo. `findMergedAnnotation` có thể thấy annotation theo quy tắc tìm kiếm Spring, nhưng điều đó không tự đảm bảo `@annotation` khớp y hệt.

### 6.3. Composed annotation / meta-annotation

Nếu định nghĩa một composed annotation được Spring hợp nhất bằng `@AliasFor`, `findMergedAnnotation` có thể trả annotation tổng hợp mà reflection đơn giản không trả. Không vì thế mà giả định biểu thức `@annotation(demo.TraceAction)` cũng thừa hưởng toàn bộ ngữ nghĩa merged của Spring.

Có hai hướng thiết kế: (1) dùng annotation trực tiếp mà pointcut nhắm tới; (2) dùng pointcut `execution` phù hợp rồi lọc metadata trong advice bằng `AnnotatedElementUtils`. Hướng (2) có phạm vi intercept rộng hơn và cần cân nhắc hiệu năng. Chỉ chọn cách này khi thực sự cần ngữ nghĩa tìm/merge của Spring.

### 6.4. Giới hạn interception của Spring AOP

- Chỉ những bean do Spring quản lý mới được Spring AOP tạo proxy/advisor; `new OrderService()` không nhận advice của container.
- Spring AOP hỗ trợ method execution, không chặn field access, constructor execution hoặc join point khác như weaving AspectJ.
- Private method không thể được tư vấn qua cơ chế proxy; final method không thể override trong subclass proxy. Với interface-based proxy, các method được bộc lộ qua interface.
- Khớp annotation cần retention runtime; `@Retention(SOURCE)` hoặc `CLASS` không phù hợp để kiểm tra annotation theo runtime trong ví dụ.
- Annotation như `@Transactional` có hệ thống attribute lookup/advisor của Spring Transaction, không nên mô phỏng tùy tiện bằng một `@annotation(Transactional)` đơn giản rồi cho rằng kết quả giống hệt.

### 6.5. Có cần reflection trong mỗi lời gọi advice?

Nếu đã bind `@annotation(traceAction)`, dùng trực tiếp `traceAction.value()`. Chỉ truy ngược `Method` khi cần đọc thêm metadata của target class, alias/composed annotation, method generic hoặc các annotation khác. Với advice tần suất cao, tránh lặp reflection không cần thiết; cache theo method/target khi có đo lường và đảm bảo khóa cache đúng.

## 7. Checklist khi metadata có nhưng Spring Aspect không chạy

1. Lời gọi đến bean có đi **qua Spring proxy** không, hay gọi `new` / `this.method()`?
2. Pointcut dùng `@annotation` cho method hay `@within`/`@target` cho type? Annotation thực tế đặt ở đâu?
3. Annotation có `@Retention(RUNTIME)` và target element phù hợp chưa?
4. Có đang nhầm method trên interface/proxy với implementation method không? Đã kiểm tra `getMostSpecificMethod` và bridge method chưa?
5. Method có thuộc phạm vi Spring AOP hỗ trợ, có đủ khả năng được intercept theo proxy strategy không?
6. Nếu dùng meta-annotation hoặc `@AliasFor`, đã **kiểm thử pointcut** độc lập với kết quả `findMergedAnnotation` chưa?
7. `@Aspect` có là Spring bean và dependency/cấu hình Spring AOP đã kích hoạt chưa?
8. Có đang nhầm “đọc thấy annotation tại startup” với “method thực sự được gọi qua proxy” không?

**Điểm cần nắm:** API Spring trả lời “metadata có gì trên class/method tôi đang kiểm tra?”; pointcut AspectJ trong Spring AOP trả lời “lời gọi method nào qua Spring proxy khớp để chạy advice?”. Cùng annotation nhưng hai câu hỏi, hai cơ chế và những giới hạn khác nhau.