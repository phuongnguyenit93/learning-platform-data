# Ánh xạ aspect, advice và pointcut vào cơ chế của Spring AOP

## 1. Mục tiêu và phạm vi

Bài này giải thích **Spring Framework thực thi một aspect khai báo bằng `@Aspect` như thế nào**: Spring nhận diện aspect bean, chuyển biểu thức pointcut và phương thức advice thành cấu hình AOP nội bộ, chọn những Spring bean cần proxy và gọi advice khi phương thức phù hợp được gọi qua proxy. Trọng tâm là **Spring AOP dựa trên proxy**, không đi sâu vào lý thuyết AOP tổng quát hay cơ chế weaving độc lập của AspectJ.

Sau bài học, bạn có thể:
- Chỉ ra vai trò cụ thể của `@Aspect`, `@Pointcut`, các annotation advice, `Advisor`, `Pointcut` và `MethodInterceptor` trong Spring.
- Giải thích đường đi của một lời gọi phương thức từ client đến Spring proxy, advice chain và target object.
- Viết, chạy và kiểm tra một aspect dùng Spring Boot cùng `spring-boot-starter-aop`.
- Chẩn đoán những trường hợp pointcut trông đúng nhưng advice không chạy vì lời gọi không đi qua Spring proxy.

## 2. Một khai báo `@Aspect` được Spring diễn giải thành gì?

Giả sử ứng dụng có Spring bean `OrderService` và một bean `TraceAspect`. Khi lập trình, ta viết ba thành phần nhìn thấy được:

| Thành phần khai báo | Vai trò khi dùng Spring | Cơ chế Spring tương ứng |
| --- | --- | --- |
| `@Aspect` trên `TraceAspect` | Đánh dấu lớp chứa các quy tắc advice | Spring nhận diện một **aspect bean** và phân tích các advice method của nó. Chỉ đánh dấu `@Aspect` chưa tự đăng ký lớp thành bean. |
| `@Pointcut("...")` | Đặt tên cho điều kiện chọn phương thức | Biểu thức được phân tích và áp dụng bằng `AspectJExpressionPointcut`; phương thức pointcut `void` chỉ định nghĩa mẫu khớp, không chứa xử lý nghiệp vụ. |
| `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around` | Khai báo logic bổ sung ở các thời điểm khác nhau | Spring tạo các đối tượng advice tương ứng; trong lời gọi qua proxy, chúng tham gia chuỗi interceptor. |
| `Advisor` | Ghép **điều kiện khớp** với **hành vi chạy** | Proxy có thể chứa nhiều advisor; mỗi advisor quyết định có áp dụng advice của nó cho lời gọi cụ thể hay không. |
| `Pointcut` (API `org.springframework.aop.Pointcut`) | Kiểm tra lớp và phương thức mục tiêu | Gồm `ClassFilter` và `MethodMatcher`; một số điều kiện có thể cần xét thêm argument ở thời điểm gọi. |
| Spring AOP proxy | Đối tượng được Spring đưa cho bên gọi thay cho target bean trực tiếp | Chặn lời gọi phương thức, chọn interceptor phù hợp, chuyển tiếp đến target. |
| Target object | Bean thực hiện logic nghiệp vụ gốc | Chạy khi chuỗi interceptor tiếp tục đến phương thức đích. |

**Phân biệt dễ nhầm:** `@Aspect` là mô hình khai báo của lập trình viên; `Advisor` và `Advice` là những thành phần Spring sử dụng để dựng và vận hành proxy. Một aspect có nhiều advice có thể đóng góp nhiều advisor. `@Pointcut` tự nó không chạy code khi có lời gọi, và không có lời gọi nào tự sinh ra chỉ vì bạn khai báo `@Pointcut`.

Một bean khác cũng có thể nhận advice từ hạ tầng Spring thông qua advisor/interceptor mà không cần có lớp `@Aspect` do bạn tự viết. Ví dụ, hạ tầng giao dịch khai báo qua `@Transactional` có cơ chế advisor/interceptor riêng. Vì vậy, không nên đồng nhất mọi proxy trong Spring với một lớp `@Aspect` cụ thể.

## 3. Spring kích hoạt và tạo proxy như thế nào?

### 3.1. Điều kiện đăng ký

Với Spring Boot có thư viện AspectJ cần thiết trên classpath (thường nhờ `spring-boot-starter-aop`), Boot tự cấu hình hỗ trợ proxy cho `@Aspect`; ví dụ Boot bên dưới **không cần** thêm `@EnableAspectJAutoProxy`. Với ứng dụng Spring Framework thuần, có thể chủ động bật bằng `@EnableAspectJAutoProxy` trên lớp cấu hình và đăng ký aspect dưới dạng Spring bean (thí dụ `@Component` hoặc `@Bean`).

`@Aspect` **không phải** stereotype tự quét bean: lớp aspect cần được đăng ký trong `ApplicationContext`. Dependency chứa annotation mà thiếu cơ chế auto proxy cũng không đủ để advice chạy.

### 3.2. Từ bean definition đến lời gọi thực tế

```text
ApplicationContext tạo hạ tầng AOP
    |
    +-- nhận diện các aspect bean và các advisor hiện có
    |       |
    |       +-- phân tích @Pointcut / biểu thức match
    |       +-- chuyển phương thức @Before/@Around/... thành advice
    |
    +-- trong quá trình tạo bean, auto-proxy creator xem xét advisor phù hợp
            |
            +-- không cần advice --> dùng bean thông thường
            |
            +-- có advisor phù hợp --> tạo Spring proxy cho bean
                                        |
Client lấy bean từ container --> gọi phương thức qua proxy
                                        |
                              chọn các interceptor khớp
                                        |
                               chạy advice theo chain
                                        |
                               gọi phương thức target
                                        |
                            trả kết quả hoặc ném exception
```

Spring sử dụng cơ chế `BeanPostProcessor`, điển hình là hạ tầng auto-proxy creator như `AnnotationAwareAspectJAutoProxyCreator`, để xét bean và áp dụng các advisor phù hợp. Khi gọi một phương thức qua proxy, Spring chọn interceptor chain cho phương thức đó; chuỗi chạy qua advice rồi tới target theo semantics của từng advice. Việc tạo proxy **không đồng nghĩa** mọi phương thức trong bean đều được advice: pointcut và giới hạn proxy vẫn quyết định lời gọi được chặn hay không.

### 3.3. Hai dạng proxy cần nhận biết

- **JDK dynamic proxy** triển khai các interface được proxy. Lời gọi của client đi qua giao diện công khai do proxy cung cấp; nếu tiêm bean theo lớp triển khai thay vì interface, có thể không phù hợp với kiểu proxy này.
- **Proxy dựa trên lớp (CGLIB)** tạo lớp con để chặn các lời gọi có thể override. Nó không thể override phương thức `final`; lớp `final` cũng không thể được subclass để proxy theo cách này. Phương thức `private` không thể được advise bằng dạng proxy này.

Với **Spring Boot 3.3**, auto-configuration mặc định ưu tiên proxy theo lớp; đặt `spring.aop.proxy-target-class=false` để dùng JDK proxy khi bean có interface phù hợp. Với cấu hình Spring Framework trực tiếp, thuộc tính `proxyTargetClass` trong `@EnableAspectJAutoProxy` quyết định ưu tiên tương ứng. Đừng suy ra loại proxy chỉ từ việc có `@Aspect`: hãy kiểm tra proxy thực tế.

## 4. Điểm khớp trong Spring AOP: từ pointcut expression đến method execution

Spring AOP theo cơ chế proxy hỗ trợ **method-execution join point trên Spring bean**. Ví dụ:

```java
@Pointcut("execution(public * com.example.app.service..*.*(..))")
public void publicServiceMethod() { }
```

- `execution(...)`: lọc lời gọi thực thi phương thức; ở đây là phương thức `public`, mọi kiểu trả về, trong package `com.example.app.service` và package con.
- `publicServiceMethod()`: tên pointcut có thể tái sử dụng trong các advice cùng aspect; method Java khai báo là `void` và thân rỗng.
- Biểu thức chỉ mô tả **điều kiện chọn**. Không có lệnh trong method `publicServiceMethod()` được chạy khi một service method khớp.

Các designator hữu ích trong Spring:

| Biểu thức | Ý nghĩa trong Spring AOP |
| --- | --- |
| `execution(* com.example.app.service..*.*(..))` | Phương thức thuộc phạm vi chữ ký/lớp đã chỉ ra. |
| `within(com.example.app.service..*)` | Giới hạn target method thuộc kiểu trong package/phân cấp package đó. |
| `@annotation(com.example.app.TrackAction)` | Phương thức thực thi có annotation được chỉ ra. |
| `bean(*Service)` | Chọn bean theo **tên bean Spring** khớp mẫu; đây là mở rộng riêng của Spring AOP. |
| `this(com.example.app.OrderApi)` | Kiểm tra **Spring proxy** có kiểu được chỉ ra. |
| `target(com.example.app.OrderService)` | Kiểm tra **target object** phía sau proxy có kiểu được chỉ ra. |
| `args(java.lang.String, ..)` | Xét kiểu đối số thực tế khi gọi phương thức. |

Kết hợp điều kiện bằng `&&`, `||` và `!`. Ví dụ, chỉ áp dụng cho phương thức có annotation và nằm trong service layer:

```java
@Pointcut("within(com.example.app.service..*)"
        + " && @annotation(com.example.app.TrackAction)")
public void annotatedServiceOperation() { }
```

Có thể trỏ advice đến tên pointcut: `@Around("annotatedServiceOperation()")`. Nếu dùng pointcut khai báo ở lớp khác, dùng tên đầy đủ đến pointcut method theo quy tắc Spring.

**Giới hạn quan trọng:** biểu thức `call(...)`, `get(...)`, `set(...)` và nhiều loại join point khác của AspectJ không được Spring AOP theo proxy hỗ trợ. Nhìn thấy cú pháp AspectJ trong annotation không có nghĩa Spring đã bật AspectJ compiler hoặc weaving. Trong Spring, `this` là proxy, còn `target` là đối tượng đích nên hai giá trị có thể khác nhau.

## 5. Advice khớp vào chuỗi gọi ra sao?

| Advice annotation | Khi nào logic chạy khi lời gọi được proxy chặn | Khả năng/giới hạn thực tế |
| --- | --- | --- |
| `@Before` | Trước phương thức đích | Thường để kiểm tra/log; không trực tiếp thay kết quả trả về; ném exception sẽ ngăn lời gọi tiếp tục. |
| `@AfterReturning` | Khi phương thức hoàn tất bình thường | Có thể lấy kết quả qua `returning`, nhưng không thay thế kết quả chỉ bằng cách gán lại biến tham số advice. |
| `@AfterThrowing` | Khi phương thức thoát bằng exception | Có thể lấy exception qua `throwing`; nên giới hạn kiểu exception phù hợp để bắt đúng trường hợp. |
| `@After` | Sau khi phương thức kết thúc, dù bình thường hay exception | Gần với hành vi `finally`, không đồng nghĩa luôn thành công. |
| `@Around` | Bao quanh phần còn lại của invocation chain và target | Nhận `ProceedingJoinPoint`; gọi `proceed()` để tiếp tục, có thể đo thời gian, trả kết quả hoặc xử lý lỗi có chủ đích. |

Ví dụ về chữ ký nhận thông tin Spring cung cấp (đoạn minh họa độc lập, không ghép vào ví dụ chạy ở mục sau):

```java
@Before("execution(* com.example.app.service..*.*(..))")
public void beforeCall(org.aspectj.lang.JoinPoint joinPoint) {
    System.out.println(joinPoint.getSignature().getName());
}

@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    returning = "result"
)
public void afterSuccess(Object result) {
    System.out.println("result=" + result);
}

@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error"
)
public void afterFailure(Throwable error) {
    System.out.println("error=" + error.getClass().getSimpleName());
}
```

Trong `@Around`, lời gọi `proceed()` là ranh giới đi vào phần còn lại của chuỗi và cuối cùng là target; tránh quên gọi khi cần nghiệp vụ chạy. `@Around` có thể quyết định không gọi `proceed()`, gọi nhiều lần, hoặc đổi giá trị trả về, nhưng chỉ nên làm vậy khi đó là chủ đích và bảo toàn hợp đồng method. Nếu advice chỉ cần quan sát trước/sau thì chọn loại advice đơn giản hơn.

Khi có **nhiều aspect**, thứ tự advice chịu ảnh hưởng của advisor ordering, loại advice và `@Order`/`Ordered`. Không nên viết ví dụ phụ thuộc một thứ tự không được cấu hình; nếu có thứ tự bắt buộc, chỉ định và kiểm thử nó.

## 6. Ví dụ chạy được: `@Aspect` + `@Pointcut` + `@Around` trên Spring Boot

Ví dụ dùng **Java 21, Spring Boot 3.3.x và Gradle**. Ý đồ là theo dõi các method có `@TrackAction` trong Spring bean. Tất cả lớp Java nằm trong package `com.example.demo` để được component scan phát hiện.

### 6.1. Cấu hình Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'spring-aop-mapping'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

`spring-boot-starter-aop` cung cấp hạ tầng Spring AOP và thư viện AspectJ cần để Spring diễn giải các annotation và pointcut expression. Mã nguồn ví dụ sau sử dụng Spring proxy, không cấu hình AspectJ compile-time weaving/load-time weaving.

Tệp `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=OFF
```

### 6.2. Annotation đánh dấu phương thức muốn theo dõi

Tệp `src/main/java/com/example/demo/TrackAction.java`:

```java
package com.example.demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackAction {
}
```

### 6.3. Target Spring bean có phương thức được chọn

Tệp `src/main/java/com/example/demo/OrderService.java`:

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    @TrackAction
    public String place(String productId) {
        return "stored:" + productId;
    }

    public String status() {
        return "ok";
    }
}
```

`place(...)` có `@TrackAction`; `status()` không có annotation nên không khớp pointcut trong ví dụ. Cả hai đều là method của cùng một Spring bean.

### 6.4. Aspect khai báo pointcut và advice

Tệp `src/main/java/com/example/demo/TraceAspect.java`:

```java
package com.example.demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    @Pointcut("@annotation(com.example.demo.TrackAction)")
    public void trackedAction() {
    }

    @Around("trackedAction()")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        String method = joinPoint.getSignature().getName();
        System.out.println("enter " + method);
        try {
            Object result = joinPoint.proceed();
            System.out.println("exit " + method);
            return result;
        } catch (Throwable error) {
            System.out.println("failed " + method);
            throw error;
        }
    }
}
```

Ánh xạ từ code sang Spring:
1. `@Component` đăng ký `TraceAspect` thành bean; `@Aspect` nói với hạ tầng AOP đây là lớp chứa advice.
2. `@Pointcut` đặt tên `trackedAction` cho mẫu các method có `@TrackAction`.
3. `@Around("trackedAction()")` gắn phương thức `trace` với pointcut đó. Spring cung cấp `ProceedingJoinPoint` của lời gọi được chặn.
4. Auto-proxy creator xét `OrderService` và có thể tạo proxy áp dụng advisor tương ứng; gọi `place(...)` **qua proxy** kích hoạt `trace`.
5. `joinPoint.proceed()` thực thi phần còn lại của chain/target; `trace` trả nguyên kết quả hoặc ném lại exception.

### 6.5. Chạy và quan sát proxy

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {
            OrderService service = context.getBean(OrderService.class);
            System.out.println(service.place("P-100"));
            System.out.println("isProxy=" + AopUtils.isAopProxy(service));
            System.out.println(service.status());
        }
    }
}
```

Tại thư mục dự án có Gradle đã cài hoặc Gradle Wrapper, chạy tương ứng `gradle bootRun` hoặc `./gradlew bootRun`. Với cấu hình logging bên trên, các dòng do chương trình in ra là:

```text
enter place
exit place
stored:P-100
isProxy=true
ok
```

`enter place` / `exit place` xuất hiện quanh lời gọi được đánh dấu. `status()` vẫn chạy, nhưng **không** sinh hai dòng advice vì không khớp `@annotation(TrackAction)`. `isProxy=true` chứng tỏ bean nhận từ container là Spring AOP proxy. Đoạn mã không phụ thuộc tên lớp proxy vốn có thể khác nhau giữa các cấu hình và phiên bản.

**Một lỗi dễ mắc:** gọi `new OrderService().place("P-100")` sẽ không chạy advice, vì đối tượng được tạo bằng `new` không phải proxy do Spring cấp. Điểm chặn là lời gọi **đi qua Spring proxy**, không phải bản thân annotation tự thực thi logic.

## 7. Kiểm tra ánh xạ `@Aspect` → advisor → proxy

Khi advice không chạy, nên tìm **mắt xích ánh xạ còn thiếu** trước khi sửa biểu thức pointcut. Kiểm tra theo thứ tự: lớp `@Aspect` đã được đăng ký thành bean chưa; hỗ trợ auto-proxy đã bật chưa; biểu thức có tạo được advisor cho kiểu/method đó không; và Spring đã cung cấp proxy cho caller chưa.

Ví dụ, `@Pointcut("@annotation(com.example.demo.TrackAction)")` chỉ chọn những method có annotation phù hợp; nó không thực thi xử lý. `@Around("trackedAction()")` mới cung cấp hành vi, được Spring chuyển thành advice trong interceptor chain. Nếu bỏ `@Component` khỏi `TraceAspect`, không có bean aspect để hạ tầng khám phá; nếu bỏ annotation khỏi `place()`, pointcut không chọn method dù service vẫn có trong container.

Việc thấy `AopUtils.isAopProxy(service) == true` chỉ xác nhận tham chiếu là proxy; vẫn phải xác minh **advisor có khớp lời gọi cụ thể**. Gọi `this.place()` từ trong target hoặc tự tạo service bằng `new` có thể bỏ qua đường đi proxy. Nếu dùng JDK proxy, caller phải truy cập phương thức được công bố qua interface; với subclass proxy phải xét khả năng override.

Phép thử hữu ích: gọi một method có annotation và một method không có annotation qua cùng proxy, ghi lại dấu vết advice và target rồi so với pointcut đã khai báo. Kết quả giúp phân biệt **không tạo proxy**, **không khớp advisor** và **không đi qua proxy**.

## 8. Kiểm chứng có hệ thống và áp dụng thực tế

Khi cần debug, thực hiện theo thứ tự:

1. **Bean:** xác nhận cả aspect và service có trong `ApplicationContext`; Spring Boot đã nhận dependency AOP.
2. **Proxy:** kiểm tra `AopUtils.isAopProxy(service)`, khi cần kiểm tra thêm `AopUtils.isJdkDynamicProxy(service)` / `AopUtils.isCglibProxy(service)`.
3. **Pointcut:** so đúng package/method annotation và điều kiện `this`, `target`, `bean`; biểu thức càng hẹp càng dễ dự đoán.
4. **Đường gọi:** bảo đảm client lấy bean từ Spring và gọi từ ngoài qua proxy; phân biệt gọi method khác với self-invocation.
5. **Advice semantics:** xác minh method trả về bình thường hay throw; với `@Around` phải kiểm tra `proceed()` và quy tắc trả về/ném exception.

Ví dụ áp dụng phù hợp: đo thời gian xử lý một nhóm Spring service methods, log thao tác có annotation riêng, theo dõi exception của boundary dịch vụ, hoặc kiểm tra quy ước nội bộ. Cần giới hạn logging dữ liệu nhạy cảm trong advice; chọn pointcut rõ ràng để tránh áp dụng tràn lan lên nhiều bean và tăng chi phí không cần thiết. Với nhu cầu giao dịch, bảo mật hay cache, ưu tiên các cơ chế khai báo chuyên biệt của Spring khi chúng đã đáp ứng yêu cầu.

## 9. Tóm tắt cơ chế cần ghi nhớ

`@Aspect` và các advice annotation là **đầu vào khai báo**. Spring phân tích pointcut/advice, ghép điều kiện với xử lý thành các advisor, chọn bean cần proxy và dùng interceptor chain để chạy advice khi lời gọi phương thức đi qua proxy. `@Pointcut` định nghĩa nơi advice áp dụng; `@Around` và các advice khác định nghĩa hành vi ở thời điểm tương ứng. Hiểu được ranh giới **Spring-managed bean → proxy → advice chain → target** là chìa khóa để giải thích vì sao aspect chạy, chạy sai lúc hoặc không chạy.

Tài liệu Spring chính thức để đối chiếu:
- Spring Framework — [AOP trong Spring](https://docs.spring.io/spring-framework/reference/core/aop.html).
- Spring Framework — [Khai báo pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html).
- Spring Framework — [Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html).
- Spring Boot 3.3 — [AOP auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/aop.html).
