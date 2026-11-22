# Annotation tổng hợp trong Spring và giới hạn khớp pointcut cần kiểm chứng

## 1. Vấn đề thực tế trong Spring AOP

Khi xây dựng annotation tùy chỉnh cho logging, audit hoặc kiểm soát truy cập, một dự án Spring thường muốn khai báo annotation cấp cao dễ hiểu với nghiệp vụ. Ví dụ, `@BusinessTraced` được xây dựng trên `@Traced`, rồi gắn lên các phương thức dịch vụ để nhận cùng hành vi tracing.

Điểm dễ nhầm là **Spring đọc được một meta-annotation không đồng nghĩa với mọi pointcut Spring AOP tự động khớp meta-annotation ấy**. Hai cơ chế liên quan nhưng khác nhau:

1. **Mô hình annotation tổng hợp của Spring**: `MergedAnnotations` và `AnnotatedElementUtils` có thể tìm annotation trực tiếp, meta-annotation và gộp thuộc tính, bao gồm giá trị được khai báo qua `@AliasFor`.
2. **Khớp pointcut dạng `@AspectJ`**: `@annotation(com.example.Traced)` dùng quy tắc khớp annotation của ngôn ngữ pointcut AspectJ, không mặc nhiên áp dụng mọi quy tắc tìm kiếm meta-annotation của Spring.
3. **Pointcut lập trình của Spring**: `AnnotationMatchingPointcut` có lựa chọn `checkInherited=true` để kiểm tra thêm annotation ở lớp cha, interface và meta-annotation theo cơ chế matcher tương ứng.

Bài học chỉ xét **Spring Framework / Spring AOP**: thiết kế annotation trên Spring bean, giới hạn khớp của advice và cách viết test để xác nhận hành vi thật. Không mở rộng sang các kiến thức AspectJ weaving độc lập ngoài phạm vi này.

### Mục tiêu

- Khai báo annotation `@Traced` và annotation tổng hợp `@BusinessTraced` theo đúng `@Target`, `@Retention`, `@AliasFor`.
- Hiểu sự khác biệt giữa **annotation được tìm thấy** và **lời gọi thực sự bị Spring AOP proxy chặn**.
- Viết test chứng minh annotation trực tiếp, annotation tổng hợp và phương thức không đánh dấu có hành vi khác nhau.
- Biết chọn giải pháp khi muốn hỗ trợ annotation tổng hợp mà không làm pointcut bắt nhầm phương thức.
- Xác định các giới hạn khác cần kiểm chứng: JDK proxy/CGLIB, annotation trên interface, self-invocation, scope phương thức và annotation ở class.

## 2. Spring nhận diện annotation tổng hợp như thế nào?

Một meta-annotation là annotation đặt **trên khai báo của một annotation khác**. Ví dụ:

~~~java
@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface Traced {
    String label() default "default";
}

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Traced
public @interface BusinessTraced {
    @AliasFor(annotation = Traced.class, attribute = "label")
    String label() default "default";
}
~~~

Đây là **hai khai báo minh họa**, muốn đưa vào dự án phải đặt trong các tệp `Traced.java`, `BusinessTraced.java`, có import `java.lang.annotation.*` và `org.springframework.core.annotation.AliasFor`. Phần 4 cung cấp test Java đầy đủ trong một file.

Điều kiện có ý nghĩa:

- `Traced` cho phép `ElementType.ANNOTATION_TYPE` thì mới có thể dùng làm meta-annotation cho `BusinessTraced`.
- `BusinessTraced` cho phép `ElementType.METHOD` vì bài toán đánh dấu method trên Spring bean.
- `RetentionPolicy.RUNTIME` giúp các API reflection/Spring đọc metadata khi chạy.
- `@AliasFor(annotation = Traced.class, attribute = "label")` khai báo thuộc tính `label` của annotation tổng hợp ghi đè thuộc tính `label` của annotation gốc trong **mô hình merged annotations của Spring**. Nó **không** tự thay đổi ngữ nghĩa khớp `@annotation` của AspectJ.
- Kiểu của hai thuộc tính phải tương thích, giá trị mặc định tương ứng cần đồng nhất; không đặt hai giá trị xung đột rồi kỳ vọng Spring tự chọn.

Khi viết:

~~~java
@BusinessTraced(label = "checkout")
public void checkout() {
    // business logic
}
~~~

Reflection Java theo cách tra **trực tiếp** `checkoutMethod.getAnnotation(Traced.class)` không thấy `@Traced` trên chính method đó. Spring có thể lấy `Traced` theo nhánh meta-annotation:

~~~java
Method method = CheckoutService.class.getMethod("checkout");

Traced direct = method.getAnnotation(Traced.class);
Traced merged = AnnotatedElementUtils.findMergedAnnotation(method, Traced.class);

System.out.println(direct == null);
System.out.println(merged.label());
~~~

Ở đây `CheckoutService` là class có method `checkout` trong ví dụ ngay trước, cần import `java.lang.reflect.Method` và `org.springframework.core.annotation.AnnotatedElementUtils`. Nếu hai annotation được khai báo đúng, hai dòng in ra lần lượt là:

~~~text
true
checkout
~~~

Đó là bằng chứng Spring **đọc được metadata**. Nó chưa chứng minh một `@Before`, `@Around` hay `@AfterReturning` được chạy.

### Các trường hợp sử dụng cơ chế này trong Spring

Spring có nhiều cơ chế riêng biết xử lý annotation tổng hợp, ví dụ các stereotype dựa trên `@Component`, mapping trong Spring MVC, hoặc một số cơ chế annotation-driven transaction/cache. **Không suy từ hành vi của chúng sang mọi pointcut tùy chỉnh**: mỗi subsystem có matcher và chiến lược tìm annotation của mình.

## 3. Phân biệt điểm khớp của Spring AOP

Trong chế độ proxy-based AOP, Spring chặn **method execution trên bean qua proxy**. Các dạng pointcut liên quan:

| Cú pháp | Đối tượng được đối chiếu | Điều không nên suy ra |
| --- | --- | --- |
| `@annotation(demo.Traced)` | Annotation trên method tại join point | Không tự đồng nghĩa với truy vấn `MergedAnnotations` theo meta-annotation |
| `@within(demo.ServiceTag)` | Annotation ở type chứa method được khớp | Không phải `@annotation` trên từng method |
| `@target(demo.ServiceTag)` | Annotation trên class của target runtime | Không dùng thay thế cho mọi trường hợp annotation ở interface |
| `execution(public * demo.CatalogueService.*(..))` | Chữ ký và phạm vi của method execution | Khớp phương thức dù có hay không có `@Traced` |

Dưới đây là ví dụ với **method annotation**:

~~~java
@Aspect
public class DirectTraceAspect {
    @Before("@annotation(demo.Traced)")
    public void record(JoinPoint joinPoint) {
        System.out.println(joinPoint.getSignature().getName());
    }
}
~~~

Aspect trên yêu cầu `demo.Traced` theo cú pháp `@annotation` của AspectJ. **Không được mặc nhiên giả định** rằng method chỉ gắn `@BusinessTraced` sẽ vào advice, dù Spring `findMergedAnnotation` nhận ra `Traced` ở method ấy. Với nhiều loại composed annotation, kết quả thực tế trong Spring AOP là method trực tiếp được intercept, còn composed method bị bỏ qua. Hãy chứng minh bằng test trên **đúng phiên bản Spring và cấu hình proxy của dự án**.

> Lưu ý: `@AliasFor` giải quyết cách Spring tổng hợp giá trị thuộc tính. Nó không thêm một biểu thức pointcut thay thế vào advice.

## 4. Test JUnit 5: metadata đúng nhưng pointcut có thể bỏ qua

Ví dụ này kiểm tra ba câu hỏi độc lập:

1. `MergedAnnotations` có nhìn thấy annotation gốc qua `@BusinessTraced` và đọc giá trị `label` đã override không?
2. Advice `@Before("@annotation(demo.Traced)")` có thực sự được gọi cho method đánh dấu trực tiếp, method đánh dấu bằng composed annotation và method thường không?
3. Một `AnnotationMatchingPointcut` với `checkInherited=true` có cho phép đánh dấu cả annotation trực tiếp và annotation tổng hợp không?

### Dependency

Với ứng dụng Spring Boot 3.x sử dụng Gradle Groovy DSL và đã có plugin Spring Boot cùng BOM/dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đối với dự án Spring Framework thuần, cần `spring-aop`, `spring-context` khi tích hợp bean, `aspectjweaver` cho expression pointcut và JUnit Jupiter cho test; các phiên bản phải tương thích và được quản lý tường minh. `AspectJProxyFactory` và `ProxyFactory` trong ví dụ dưới đây là Spring AOP thật, dù test không chạy HTTP server.

### File test hoàn chỉnh

Tạo file `src/test/java/demo/ComposedAnnotationPointcutTest.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import org.aopalliance.intercept.MethodInterceptor;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.core.annotation.AliasFor;
import org.springframework.core.annotation.AnnotatedElementUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@interface Traced {
    String label() default "default";
}

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Traced
@interface BusinessTraced {
    @AliasFor(annotation = Traced.class, attribute = "label")
    String label() default "default";
}

class CatalogueService {
    @Traced(label = "direct")
    public String direct() {
        return "direct";
    }

    @BusinessTraced(label = "business")
    public String composed() {
        return "composed";
    }

    public String plain() {
        return "plain";
    }
}

@Aspect
class DirectAnnotationAspect {
    final List<String> invoked = new ArrayList<>();

    @Before("@annotation(demo.Traced)")
    public void before(JoinPoint joinPoint) {
        invoked.add(joinPoint.getSignature().getName());
    }
}

public class ComposedAnnotationPointcutTest {

    @Test
    void springCanReadAComposedAnnotation() throws Exception {
        Method method = CatalogueService.class.getMethod("composed");

        // Java reflection trực tiếp không thấy @Traced trên method.
        assertNull(method.getAnnotation(Traced.class));

        // Spring đi qua @BusinessTraced -> @Traced và gộp @AliasFor.
        Traced merged =
                AnnotatedElementUtils.findMergedAnnotation(method, Traced.class);
        assertNotNull(merged);
        assertEquals("business", merged.label());
    }

    @Test
    void aspectJStyleAnnotationPointcutOnlyRecordsDirectAnnotation() {
        DirectAnnotationAspect aspect = new DirectAnnotationAspect();
        AspectJProxyFactory factory = new AspectJProxyFactory(new CatalogueService());
        factory.addAspect(aspect);
        CatalogueService service = factory.getProxy();

        assertEquals("direct", service.direct());
        assertEquals("composed", service.composed());
        assertEquals("plain", service.plain());

        // Điểm quan trọng: test đo advice thực sự chạy qua Spring proxy.
        assertEquals(List.of("direct"), aspect.invoked);
    }

    @Test
    void springAnnotationPointcutCanInspectMetaAnnotations() {
        List<String> intercepted = new ArrayList<>();
        ProxyFactory factory = new ProxyFactory(new CatalogueService());

        AnnotationMatchingPointcut pointcut =
                new AnnotationMatchingPointcut(null, Traced.class, true);

        factory.addAdvisor(new DefaultPointcutAdvisor(
                pointcut,
                (MethodInterceptor) invocation -> {
                    intercepted.add(invocation.getMethod().getName());
                    return invocation.proceed();
                }));

        CatalogueService service = (CatalogueService) factory.getProxy();
        assertEquals("direct", service.direct());
        assertEquals("composed", service.composed());
        assertEquals("plain", service.plain());

        assertEquals(List.of("direct", "composed"), intercepted);
    }
}
~~~

Chạy riêng test:

~~~bash
./gradlew test --tests demo.ComposedAnnotationPointcutTest
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests demo.ComposedAnnotationPointcutTest
~~~

**Kỳ vọng test:**

| Phép thử | Kết luận được kiểm tra |
| --- | --- |
| `springCanReadAComposedAnnotation` | Reflection trực tiếp không thấy `Traced`; Spring tìm được meta-annotation và nhãn `business` |
| `aspectJStyleAnnotationPointcutOnlyRecordsDirectAnnotation` | Với Spring AOP/AspectJ-style pointcut mô tả, advice chỉ ghi lại `direct` |
| `springAnnotationPointcutCanInspectMetaAnnotations` | Với `checkInherited=true`, advisor bắt `direct` và `composed`, bỏ qua `plain` |

Không in stdout trong bộ test này; khi thành công Gradle báo task test thành công theo định dạng riêng của môi trường. Nếu assertion về matching không đúng với stack Spring đang dùng, hãy điều tra phiên bản và proxy đã tạo; **không sửa assertion chỉ để biến test thành xanh**. Ví dụ này dùng class-based proxy cho class không khai báo interface, các method đều public và không final, giúp tập trung kiểm tra semantics của annotation.

**Đây là test về hành vi Spring AOP**, không phải test đơn thuần về reflection. Cần đảm bảo `AspectJProxyFactory` thật sự tạo được proxy và aspect đã được áp dụng. Với ứng dụng thực, nên có thêm test `ApplicationContext` để xác nhận auto-proxying và bean wiring tương ứng.

## 5. Khi muốn annotation tổng hợp được intercept, chọn cách nào?

### 5.1. Giải pháp đơn giản: khai báo các annotation tường minh trong pointcut

Nếu số lượng annotation tổng hợp ít và được kiểm soát:

~~~java
@Before("@annotation(demo.Traced) || @annotation(demo.BusinessTraced)")
public void before(JoinPoint joinPoint) {
    // Theo dõi lời gọi được đánh dấu bằng một trong hai annotation.
}
~~~

Ưu điểm: tường minh, dễ hiểu và đơn giản trong một số dự án. Hạn chế: mỗi loại annotation tổng hợp mới cần được bổ sung vào biểu thức và được test; không phải cơ chế tìm mọi meta-annotation theo chiều sâu bất kỳ.

### 5.2. Dùng Spring programmatic advisor hỗ trợ tìm meta-annotation

Ở test mục 4, `AnnotationMatchingPointcut(null, Traced.class, true)` kiểm tra metadata cả mức method, đồng thời bật hỗ trợ annotation kế thừa/meta theo API của Spring. Kết hợp `DefaultPointcutAdvisor` với `MethodInterceptor` có thể tổ chức advice mà không cần viết `@Before("@annotation(...)")` cho từng annotation con.

Trong ứng dụng Spring-managed, có thể đăng ký một `Advisor` bean vào context thay cho việc tự tạo `ProxyFactory` cho từng đối tượng. Ví dụ **khung cấu hình**:

~~~java
@Configuration
class TraceAdvisorConfig {
    @Bean
    Advisor traceAdvisor(TraceInterceptor traceInterceptor) {
        return new DefaultPointcutAdvisor(
                new AnnotationMatchingPointcut(null, Traced.class, true),
                traceInterceptor);
    }
}
~~~

Ở đoạn này, `TraceInterceptor` là một lớp ứng dụng implement `MethodInterceptor`; `Advisor`, `@Configuration`, `@Bean` và các type liên quan phải được import. Đây là **khung tích hợp**, chưa phải file chạy độc lập. Khi áp dụng, đo xem `BeanFactory` có thực sự gắn advisor vào bean cần xử lý và lưu ý thứ tự advisor khi có transaction, security, caching.

### 5.3. Dùng pointcut đủ hẹp và đọc merged annotation bên trong advice

Nếu cần một advice `@Aspect` hiện hữu và danh sách composed annotations thường xuyên thay đổi, có thể dùng biểu thức `execution(...)` để khớp **phạm vi dịch vụ đã chọn**, rồi tra merged annotation trong advice:

~~~java
@Around("execution(public * demo.CatalogueService.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    Method signatureMethod = ((MethodSignature) pjp.getSignature()).getMethod();
    Method targetMethod = AopUtils.getMostSpecificMethod(
            signatureMethod, pjp.getTarget().getClass());

    Traced traced = AnnotatedElementUtils.findMergedAnnotation(
            targetMethod, Traced.class);
    if (traced == null) {
        return pjp.proceed();
    }

    recordTrace(traced.label()); // tích hợp tracing của ứng dụng
    return pjp.proceed();
}
~~~

Đây là **đoạn code minh họa** bên trong `@Aspect`, cần các import:
`org.aspectj.lang.ProceedingJoinPoint`, `org.aspectj.lang.annotation.Around`,
`org.aspectj.lang.reflect.MethodSignature`, `java.lang.reflect.Method`,
`org.springframework.aop.support.AopUtils` và
`org.springframework.core.annotation.AnnotatedElementUtils`.

Ưu điểm: quyền quyết định dựa trực tiếp vào mô hình merged annotations; có thể lấy thuộc tính `label` ngay. Hạn chế: proxy/pointcut có thể intercept nhiều method hơn số method cần tracing, tăng overhead. Nên giới hạn `execution` theo package, type hoặc method signature cụ thể, xử lý interface annotation theo chính sách dự án, và test cả trường hợp null. Cách này cũng không tự khắc phục self-invocation.

### Tiêu chí lựa chọn

| Nhu cầu | Phương án phù hợp |
| --- | --- |
| Ít annotation, tên ổn định | Pointcut ghép `@annotation(A) || @annotation(B)` và test cả hai |
| Muốn Spring tự tìm meta-annotation ở mức pointcut | `AnnotationMatchingPointcut` với `checkInherited` được cấu hình rõ |
| Cần giá trị tổng hợp `@AliasFor` và logic chọn động | Khớp phạm vi hẹp, dùng `AnnotatedElementUtils` trong advice |
| Cần hỗ trợ bean ngoài Spring hay method gọi nội bộ | Thiết kế khác ngoài giới hạn Spring proxy AOP; không thể chỉ chỉnh `@annotation` |

## 6. Các ranh giới cần kiểm chứng trên dự án thật

**1. Annotation đặt trên method hay class?** `@annotation` chỉ nói tới annotation của method. Nếu muốn đánh dấu cả class, hãy thiết kế annotation với `@Target(TYPE)` phù hợp và dùng đúng pointcut (`@within`/`@target`) hoặc class annotation matcher; đừng đưa method annotation tới class rồi mong nó match tự động.

**2. Annotation ở interface, method override và implementation:** JDK proxy nhìn qua interface; class-based proxy làm việc với class thực. Annotation có thể đặt ở interface method mà không khai báo lại ở implementation. Thứ tự lấy method và chiến lược tìm metadata có thể tạo kết quả khác nhau. Test phải đối chiếu **actual proxy, implementation method và interface method**. `@Inherited` của Java áp dụng cho type inheritance theo quy tắc riêng; không có nghĩa method annotation được tự động kế thừa theo mọi trường hợp.

**3. Proxy phải thật sự được gọi:** self-invocation (một method trong target gọi trực tiếp method khác của cùng target), tạo đối tượng bằng `new` ngoài Spring, final/private method hoặc cấu hình proxy sai có thể khiến advice không chạy. Bài test nào chỉ gọi `new CatalogueService().composed()` sẽ không chứng minh Spring AOP hoạt động.

**4. Thứ tự và điều kiện advisor:** khi service có transaction, caching hoặc authorization, thứ tự advice có thể làm thay đổi thời điểm logging. Một `@Transactional` composite annotation được Spring transaction infrastructure nhận diện không chứng minh `@Around("@annotation(Transactional)")` cũng bắt đúng như vậy.

**5. Annotation và giá trị thuộc tính:** `@AliasFor` chỉ được Spring áp dụng khi annotation được đọc qua API hỗ trợ gộp. Java reflection thuần không tự thực thi quy tắc alias. Hãy kiểm tra value thực sự nhận được, trường hợp default và cấu hình alias sai/xung đột.

**6. Với ứng dụng reactive:** Spring AOP chặn lời gọi method trả về `Mono`/`Flux`; advice chạy khi method trả publisher, khác thời điểm publisher phát tín hiệu. Nếu viết tracing cho Reactor, cần kiểm thử trên subscription/signal/context đúng cơ chế. Đây là ranh giới của Spring Aspect, không phải bằng chứng rằng một pointcut annotation tự động xử lý toàn bộ chuỗi reactive.

## 7. Ma trận kiểm thử khuyến nghị

| Case | Cấu hình đầu vào | Điều cần assert |
| --- | --- | --- |
| Method gắn `@Traced` trực tiếp | Proxy gọi `direct()` | Advice chạy đúng một lần |
| Method gắn `@BusinessTraced` | Proxy gọi `composed()` | Xác nhận matching theo **phương án đã chọn**; `MergedAnnotations` trả nhãn đã override |
| Method không annotation | Proxy gọi `plain()` | Không có side effect tracing |
| Annotation trên interface method | JDK proxy và class-based proxy | Không phụ thuộc giả định mơ hồ về vị trí annotation |
| Annotation trên class | Dùng annotation `TYPE`, chọn `@within`/`@target` hoặc class matcher | Xác nhận mức type khác method |
| Method tự gọi lẫn nhau | `outer()` gọi `inner()` trong cùng target | Chỉ tính advice tại những lời gọi thực sự đi qua proxy |
| Annotation ở composed nhiều cấp | `@Feature` -> `@BusinessTraced` -> `@Traced` | API merged nhận đúng giá trị; pointcut test riêng, không suy đoán |
| Alias sai hoặc xung đột | Cấu hình annotation không hợp lệ | Test chứng minh cấu hình được phát hiện, không âm thầm dùng sai nhãn |

Có thể tổ chức test `@SpringBootTest` riêng trên bean thật: gọi qua bean được inject, xác nhận `AopUtils.isAopProxy(bean)`, quan sát một recorder độc lập để biết advice đã chạy. Khi dùng cùng một test matrix cho JDK proxy/CGLIB, khai báo interface nếu cần và điều chỉnh `proxyTargetClass` một cách tường minh.

## 8. Lỗi thường gặp và cách chẩn đoán

- **Tìm thấy annotation bằng `findMergedAnnotation` nhưng advice không chạy:** kiểm tra biểu thức pointcut `@annotation`, proxy, vị trí annotation và liệu meta-annotation đã được liệt kê hay matcher có `checkInherited` chưa.
- **Advice chạy nhưng giá trị label vẫn là mặc định:** kiểm tra `@AliasFor`, `@Retention(RUNTIME)`, cách đọc annotation bằng reflection/merged API và mâu thuẫn giá trị mặc định.
- **`@annotation` trên class không match:** nó nhắm method; phân biệt với `@within` và `@target`.
- **Annotation trên interface hoạt động ở test này nhưng hỏng ở test khác:** xác định loại proxy và method thực sự được resolve; đừng giả định implementation luôn mang annotation của interface.
- **Test pass dù advice bị bỏ qua:** chỉ assert kết quả business mà không ghi nhận invocation của advice; thêm counter/recorder để test thất bại khi pointcut không match.
- **Tăng phạm vi `execution(* *(..))` để chữa lỗi:** có thể khiến quá nhiều bean/method bị proxy và nhiều lời gọi vào advice; cần chọn đúng scope và có test hiệu năng hoặc tích hợp khi mở rộng.
- **Dùng `@AliasFor` như công cụ mở rộng pointcut:** alias chỉ giải quyết metadata tổng hợp, không tự viết lại biểu thức AspectJ.

## 9. Checklist áp dụng

1. Ghi rõ annotation gốc và annotation tổng hợp được đặt ở **method** hay **type**, có `RUNTIME` retention hay không.
2. Quyết định rõ **bộ máy khớp pointcut**: AspectJ-style `@annotation` hay Spring `AnnotationMatchingPointcut`/custom advisor.
3. Tạo ít nhất ba method mẫu: đánh dấu trực tiếp, đánh dấu composite, không đánh dấu; assert **advice invocation** cho từng method.
4. Kiểm tra `MergedAnnotations`/`AnnotatedElementUtils` độc lập với kiểm tra proxy để biết vấn đề nằm ở metadata hay matching.
5. Test interface/class proxy, override và self-invocation khi cấu trúc ứng dụng có các trường hợp đó.
6. Kiểm tra nhãn/thuộc tính từ `@AliasFor`, cả giá trị tùy chỉnh và mặc định.
7. Đặt phạm vi pointcut đủ hẹp, tránh intercept toàn ứng dụng chỉ để tự lọc metadata sau đó.

**Tiêu chí hoàn thành:** Team có test cho thấy rõ phương thức nào bị Spring AOP advice intercept, phương thức nào chỉ được Spring annotation API nhận diện, và việc hỗ trợ composed annotation là quyết định thiết kế được xác minh bằng test.

## Tài liệu tham khảo

- Spring Framework — Declaring a Pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework — `AliasFor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/annotation/AliasFor.html
- Spring Framework — `AnnotationMatchingPointcut` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/aop/support/annotation/AnnotationMatchingPointcut.html
- Spring Framework — `MergedAnnotations` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/annotation/MergedAnnotations.html
