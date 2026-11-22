# Điều kiện chọn Spring AOP cho một yêu cầu cụ thể

## Mục tiêu và phạm vi

Bài này trả lời câu hỏi thực hành: **khi có một yêu cầu trong ứng dụng Spring, điều kiện nào khiến Spring AOP là lựa chọn phù hợp, khi nào nên dùng cơ chế có sẵn của Spring, và khi nào phải chọn cách khác?**

Spring AOP là cơ chế chặn **lời gọi phương thức trên Spring bean thông qua proxy**. Với một lời gọi phù hợp pointcut, proxy thực thi advice trước/sau/quanh phương thức đích. Đó là ranh giới kỹ thuật quyết định lựa chọn, vì Spring AOP không tự chặn mọi đoạn mã Java đang chạy. Nội dung dưới đây tập trung vào tiêu chí chọn, giới hạn và cách xác nhận trong môi trường Spring; các khái niệm AOP tổng quát không được lặp lại thành một chương riêng.

## 1. Bộ điều kiện quyết định

Đối với mỗi yêu cầu, kiểm tra lần lượt các câu hỏi sau.

| Điều kiện | Cần xác nhận trong ứng dụng Spring | Kết luận nếu không đạt |
| --- | --- | --- |
| **C1. Điểm cần xử lý là một phương thức** | Hành vi phải được kích hoạt khi một phương thức của bean chạy, ví dụ `OrderService.submit()`. | Nếu cần bắt truy cập field, constructor, mọi lời gọi nội bộ hay câu lệnh bất kỳ: Spring AOP proxy không đáp ứng. |
| **C2. Đối tượng do Spring quản lý** | Đối tượng đích do ApplicationContext tạo/quản lý và có thể được proxy. | `new OrderService()` tự tạo ngoài container không được Spring AOP tự động gắn advice. |
| **C3. Lời gọi đi qua proxy** | Caller dùng bean được inject/tra cứu từ container, thường là một bean khác hoặc lớp tích hợp Spring. | `this.method()` / gọi nội bộ trên target bỏ qua proxy; advice của phương thức bị gọi có thể không chạy. |
| **C4. Phương thức thực sự chặn được** | Kiểm tra kiểu proxy, visibility, `final` và đối tượng target; thiết kế API public rõ ràng. | `private`/`final` không phù hợp với subclass proxy; JDK proxy chỉ chặn lời gọi public qua interface được proxy. |
| **C5. Quy tắc dùng lại được, ranh giới rõ** | Yêu cầu áp dụng cùng chính sách tại nhiều service/method, không cần hiểu chi tiết luồng nghiệp vụ từng ca. | Nếu quy tắc là một bước nghiệp vụ cụ thể, gọi trực tiếp qua service/helper rõ hơn và dễ kiểm thử hơn. |
| **C6. Spring chưa có giải pháp đúng hơn** | Xem `@Transactional`, Spring Security method security, `@Cacheable`, `@Async`, validation, Micrometer/Observation, MVC interceptor/filter, `@ControllerAdvice`. | Ưu tiên tính năng chuyên dụng; không viết custom aspect mô phỏng lại cơ chế có sẵn. |
| **C7. Hệ quả của advice kiểm soát được** | Xác định thứ tự, ngoại lệ, kiểu trả về, luồng/thread, latency, dữ liệu nhạy cảm và khả năng test. | Nếu độ đúng nghiệp vụ phụ thuộc vào thứ tự khó kiểm soát, ngữ cảnh bất đồng bộ hoặc interception không chắc chắn, hãy thiết kế lại. |

**Chỉ nên chọn custom Spring AOP khi C1–C5 đạt, C6 không cung cấp cách phù hợp hơn và C7 được xác minh.** Điểm quan trọng: một yêu cầu “xuất hiện tại nhiều nơi” chưa đủ; nó còn phải đi qua ranh giới proxy được Spring hỗ trợ.

## 2. Phân loại yêu cầu thường gặp trong Spring

| Yêu cầu thực tế | Chọn gì trước | Có nên tự viết Spring Aspect? |
| --- | --- | --- |
| Mở/commit/rollback transaction của một service | `@Transactional` và Spring transaction management | Thường **không**; custom aspect dễ sai propagation, rollback và thứ tự advisor. |
| Kiểm tra quyền người dùng tại method | Spring Security với `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize` khi thích hợp | Thường **không**; bảo mật cần ngữ cảnh, chính sách và thứ tự kiểm soát đã chuẩn hóa. |
| Cache kết quả service | Spring Cache (`@Cacheable`, `@CacheEvict`, …) | Thường **không**; tận dụng key, eviction và cache manager chuẩn. |
| Chạy method bất đồng bộ | `@Async` cùng executor được cấu hình | Thường **không**; cần lưu ý giới hạn proxy tương tự và ngữ nghĩa trả về/exception. |
| Đo request HTTP và phân tích request/response | Servlet Filter, Spring MVC `HandlerInterceptor`, Micrometer/Observation, Actuator | Không dùng service aspect như cơ chế thay thế mặc định cho HTTP pipeline. |
| Xử lý ngoại lệ HTTP tập trung | `@ControllerAdvice` / `@RestControllerAdvice` | Không; đó là ranh giới web response. |
| Đảm bảo invariant trong domain, như kiểm tra hạn mức trước khi duyệt đơn | Domain service, policy object, validation ở đúng lớp | Thường **không**; ý nghĩa và thứ tự là logic nghiệp vụ cần được nhìn thấy rõ. |
| Gắn log/audit theo một chính sách đồng nhất cho nhiều service method đã chọn | Logging/observation hiện có; nếu cần logic tùy biến, custom Spring Aspect | **Có thể**, nếu pointcut giới hạn chính xác và xử lý đầy đủ failure/PII. |
| Đo thời gian gọi một tập method Spring bean theo annotation nội bộ | Micrometer/Observation hoặc custom advice nếu cần kết hợp riêng | **Có thể**, đặc biệt khi cần tái sử dụng một quy tắc thực sự dùng chung. |
| Bắt truy cập field, lời gọi constructor, method private hoặc object được tạo ngoài Spring | Thiết kế lại điểm mở rộng, explicit decorator, hoặc AspectJ weaving nếu thật sự cần | **Không thể chỉ dùng proxy-based Spring AOP**. |

**Chú ý về các annotation của Spring:** một số khả năng như transaction, cache, async và method security thường sử dụng proxy/interceptor bên dưới. Điều đó không có nghĩa ta cần tự triển khai aspect tương tự. Hãy dùng hợp đồng của từng tính năng Spring và kiểm tra cấu hình activation của chính tính năng đó.

## 3. Thử áp bộ điều kiện lên ba yêu cầu cụ thể

**Ca A — kiểm tra quyền trước `PaymentService.pay()`.** C1–C4 có thể đạt nếu `pay()` là method của Spring bean gọi qua proxy, nhưng **C6** khiến ta ưu tiên Spring Security method security thay cho custom `@Before`: chính sách quyền cần cơ chế xác thực, kiểm thử và bảo vệ đúng chuẩn.

**Ca B — ghi audit tùy biến trên nhóm method có `@TrackBusiness`.** Khi service được inject qua Spring, phương thức public có thể chặn và pointcut giới hạn bởi annotation, C1–C5 có thể đạt. Nếu công cụ observability hiện có chưa đáp ứng bản ghi riêng và C7 cho phép giữ nguyên exception/return value, custom advice trở thành phương án hợp lý. Ví dụ ở phần 5 triển khai chính ca này.

**Ca C — yêu cầu chặn mọi lần gọi `this.charge()` và mọi đối tượng `new CheckoutService()`.** C2/C3 không đạt với mô hình Spring AOP proxy. Đổi sang CGLIB không thay đổi đường gọi nội bộ. Cần xem lại ranh giới bean, viết gọi cộng tác tường minh, hoặc đánh giá AspectJ weaving nếu bắt buộc áp dụng ngoài container.

Như vậy các câu hỏi C1–C4 là **điều kiện kỹ thuật**, C5–C6 quyết định trách nhiệm nên nằm ở đâu, còn C7 quyết định advice có an toàn về thứ tự, lỗi, bất đồng bộ và chi phí vận hành hay không.

## 4. Quy trình chọn cho một yêu cầu cụ thể

Giả sử đề bài: “Mỗi khi một số thao tác quan trọng của service hoàn tất hoặc phát sinh lỗi, hệ thống cần ghi dấu theo chính sách đồng nhất.”

**Bước 1 — xác định nơi quan sát.** Muốn theo dõi kết quả xử lý của service method, không phải toàn bộ request HTTP hay truy cập repository. Mỗi service là Spring bean và được gọi từ bean khác qua DI: đáp ứng C1–C3.

**Bước 2 — kiểm tra các lựa chọn sẵn có.** Nếu chỉ cần trace/span/metric chuẩn, ưu tiên Micrometer/Observation và hạ tầng logging. Nếu là security/transaction, dùng module chuyên biệt tương ứng. Nếu thật sự cần một bản ghi tùy chỉnh với domain event fields sau mỗi use case được phép, cân nhắc một aspect riêng.

**Bước 3 — xác định phạm vi chính xác.** Dùng annotation tường minh `@TrackBusiness` cho method nghiệp vụ được chọn, thay vì pattern quá rộng như `execution(* com.example..*(..))` vốn có thể match controller, infrastructure hoặc method ngoài ý muốn.

**Bước 4 — quyết định thời điểm.** Nếu chỉ cần tín hiệu *trước* lời gọi, `@Before` là đủ. Khi chỉ ghi nhận hoàn tất thành công, dùng `@AfterReturning`; ghi thất bại, `@AfterThrowing`; ghi cleanup bất kể kết quả, `@After`. Chỉ dùng `@Around` khi phải bao quanh lời gọi, đo thời gian, chuyển đổi kết quả hoặc kiểm soát việc gọi tiếp; `@Around` phải xử lý `proceed()` chính xác.

**Bước 5 — kiểm tra hệ quả.** Không log payload nhạy cảm; giữ nguyên kết quả/ngoại lệ nghiệp vụ; xem lại tương tác với `@Transactional`, `@Async` và advisor order. “Phương thức trả về” không nhất thiết đồng nghĩa transaction đã commit, hoặc tác vụ bất đồng bộ đã hoàn tất.

**Bước 6 — xác nhận bằng integration test.** Kiểm thử lời gọi qua bean thật, trường hợp annotation có/không, thất bại, self-invocation, và proxy mode đang cấu hình. Nếu một tiêu chí không bảo đảm được, dừng chọn Spring AOP cho yêu cầu đó.

## 5. Ví dụ chạy được: chỉ đánh dấu những service method cần audit

Trong ứng dụng Spring Boot hỗ trợ Java 17+, ví dụ này in thông báo trước một method có annotation. Nó minh họa cách lựa chọn Spring AOP khi yêu cầu là chính sách tùy biến, được áp dụng ở ranh giới Spring service.

Dự án cần Spring Boot và dependency AOP phù hợp **đúng major version**:

- Spring Boot **3.x**: `org.springframework.boot:spring-boot-starter-aop`.
- Spring Boot **4.x**: starter đã đổi tên thành `org.springframework.boot:spring-boot-starter-aspectj`. Tên có chữ “aspectj” là dependency hỗ trợ khai báo pointcut/advice dạng `@Aspect`; ví dụ dưới đây vẫn sử dụng **Spring AOP proxy**, không thực hiện AspectJ bytecode weaving.

Ví dụ Gradle cho dự án **Spring Boot 4.x đã cấu hình plugin và dependency management**:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

Với dự án Boot 3.x, thay dòng dependency thành `spring-boot-starter-aop`. Không thêm `@EnableAspectJAutoProxy` chỉ để chạy ví dụ khi Boot đã auto-configure AOP và không vô hiệu hóa `spring.aop.auto`; với ứng dụng Spring Framework tự cấu hình, phải chủ động bật `@EnableAspectJAutoProxy` và cung cấp những dependency cần thiết.

Các tệp Java sau nằm trong `src/main/java/com/example/demo/`.

**Tệp `TrackBusiness.java` — khai báo phương thức được theo dõi:**

```java
package com.example.demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackBusiness {
}
```

**Tệp `CheckoutService.java` — Spring bean làm nghiệp vụ:**

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    @TrackBusiness
    public String placeOrder(String id) {
        return "created:" + id;
    }

    public String status() {
        return "ok";
    }
}
```

**Tệp `BusinessAuditAspect.java` — advice chỉ match annotation đã chọn:**

```java
package com.example.demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class BusinessAuditAspect {
    @Before("@annotation(com.example.demo.TrackBusiness)")
    public void beforeTrackedCall(JoinPoint joinPoint) {
        System.out.println("AOP:" + joinPoint.getSignature().getName());
    }
}
```

**Tệp `DemoApplication.java` — lấy `CheckoutService` qua Spring DI:**

```java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CheckoutService checkoutService) {
        return args -> {
            System.out.println(checkoutService.placeOrder("ORD-1"));
            System.out.println(checkoutService.status());
        };
    }
}
```

**Chạy:** với Gradle wrapper và plugin Spring Boot đã cấu hình trong project, sử dụng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Trên Maven/Spring Boot Maven Plugin, dùng `mvn spring-boot:run`. Với Spring Boot 3/4, tuân thủ phiên bản JDK và Gradle/Maven tương thích của bản Boot được chọn.

Trong log của ứng dụng, ba dòng do demo in ra theo thứ tự là:

```text
AOP:placeOrder
created:ORD-1
ok
```

Những dòng khởi động khác của Spring Boot được bỏ qua ở đoạn kết quả này. `placeOrder()` được advice vì có `@TrackBusiness` và được gọi qua injected proxy. `status()` không có annotation nên không xuất hiện `AOP:status`. Nếu tạo `new CheckoutService()` và gọi `placeOrder()` trực tiếp, object đó không được container áp proxy, nên không có dòng `AOP:placeOrder`.

**Từ nhu cầu đến quyết định:** đối với chính sách audit tùy biến trên một nhóm service method, đây là trường hợp có thể chọn Spring AOP. Nếu yêu cầu chuyển thành “mọi request HTTP phải có access log”, giải pháp phù hợp cần đánh giá lại ở Servlet Filter/MVC/Micrometer, không mở rộng bừa pointcut toàn ứng dụng.

## 6. Khi phải dùng `@Around`: điều kiện an toàn bổ sung

Chỉ chọn `@Around` nếu yêu cầu thật sự cần đo quanh method hoặc chủ động can thiệp tiến trình. Đây là đoạn minh họa **không phải file độc lập**, thay cho method advice của ví dụ trên khi muốn đo thời gian:

```java
@Around("@annotation(com.example.demo.TrackBusiness)")
public Object measure(ProceedingJoinPoint point) throws Throwable {
    long started = System.nanoTime();
    try {
        return point.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - started;
        System.out.println("elapsed-ns=" + elapsedNanos);
    }
}
```

Đoạn trên cần import `org.aspectj.lang.ProceedingJoinPoint` và `org.aspectj.lang.annotation.Around` trong class `@Aspect`; giá trị `elapsed-ns` thay đổi theo từng lần chạy nên không có stdout số cố định. `finally` bảo đảm có phép đo cả khi method ném exception, còn `return point.proceed()` giữ nguyên giá trị trả về và ngoại lệ gốc. Không nuốt exception, không quên `proceed()` và không gọi `proceed()` nhiều lần trừ khi yêu cầu nghiệp vụ thực sự cho phép thực thi lại.

Nếu phương thức trả về `CompletableFuture`/`Mono`/`Flux` hoặc khởi chạy xử lý nền, phép đo quanh lời gọi có thể chỉ đo **thời gian tạo/trả đối tượng bất đồng bộ**, không phải thời gian xử lý kết thúc. Để đo completion thật, phải sử dụng cơ chế gắn với lifecycle của loại trả về hoặc observability phù hợp. Với transaction, vị trí advisor quyết định phép đo bao quanh hay nằm bên trong vùng transaction; đừng mặc định thời điểm advice chạy là thời điểm commit thành công.

## 7. Checklist kiểm chứng trước khi phê duyệt Spring AOP

- **Ranh giới:** đã liệt kê method phải chặn, caller và Spring bean sở hữu method chưa? Có lời gọi bằng `this`/`new` làm mất interception không?
- **Loại proxy:** đã xác nhận JDK hoặc class-based proxy và kiểm tra `final`, `private`, method visibility, interface method chưa?
- **Pointcut:** đã dùng `@annotation`, `within`, `execution` hoặc `bean(...)` đúng phạm vi Spring bean chưa? Có nguy cơ trúng method không mong muốn không?
- **Thứ tự:** nếu kết hợp với transaction/security/cache/async, đã kiểm chứng advisor order và vị trí logic chạy chưa?
- **Ngữ nghĩa:** advice giữ nguyên giá trị/exception? Có phân biệt success/failure, rollback, completion bất đồng bộ? Có dữ liệu cá nhân/token cần loại khỏi log không?
- **Vận hành:** có đánh giá chi phí proxy/pointcut/logging, tránh vòng lặp do advice tự gọi bean bị advice match, và bảo đảm quan sát được qua test không?
- **Giải pháp thay thế:** Spring Security, `@Transactional`, caching, `@Async`, Micrometer/Observation, Filter/Interceptor hoặc explicit code có phù hợp hơn không?

Tối thiểu nên có kiểm thử integration với ApplicationContext thật cho (a) method được chọn gọi từ bean khác có advice, (b) method không được chọn không có advice, (c) exception vẫn được truyền, (d) lời gọi nội bộ và object tạo ngoài Spring có hành vi đúng theo giới hạn proxy. Dùng `org.springframework.aop.support.AopUtils.isAopProxy(bean)` để hỗ trợ chẩn đoán khi cần, nhưng **proxy tồn tại không chứng minh mọi method đều match pointcut**: hãy xác nhận hiệu ứng của từng lời gọi.

## 8. Các nhầm lẫn dễ khiến chọn sai

1. **“Có `@Aspect` là mọi method đều được chặn.”** Sai: class aspect phải là Spring bean, hạ tầng AOP phải được bật, pointcut match và lời gọi phải qua proxy.
2. **“Dùng CGLIB là xử lý được `this.method()`/private.”** Sai: self-invocation vẫn đi trên target; private không override được.
3. **“Cross-cutting thì luôn viết custom aspect.”** Sai: nhiều chức năng Spring đã có module chuyên biệt, ngữ nghĩa đầy đủ và công cụ vận hành tốt hơn.
4. **“`@Around` và `@Before` thay thế nhau tùy ý.”** Sai: `@Around` quyết định có gọi target hay không, có thể thay kết quả/exception; chọn advice ít quyền nhất đủ đáp ứng yêu cầu.
5. **“AOP có thể đo thời gian hoàn tất mọi tác vụ async.”** Sai: cần phân biệt thời gian invocation và completion của future/reactive stream.
6. **“Advice chạy sau khi method trả về nghĩa là transaction đã commit.”** Chưa chắc: thứ tự proxy/advisor và transaction boundary phải được xét riêng.
7. **“Bật `@EnableAspectJAutoProxy` nghĩa là có AspectJ weaving.”** Sai: cơ chế proxy của Spring AOP vẫn là nền tảng; weaving là chế độ triển khai khác.

**Quy tắc chốt:** chọn Spring AOP khi cần một hành vi dùng chung tại **ranh giới method của Spring-managed beans**, lời gọi **thực sự qua proxy**, các giới hạn visibility/proxy/advisor **chấp nhận được**, và không có thành phần Spring chuyên dụng phù hợp hơn. Khi bất kỳ điều kiện nền tảng nào không đạt, điều chỉnh ranh giới thiết kế hoặc dùng cơ chế khác trước khi viết aspect.

## Tài liệu tham khảo chính thức

- [Spring Framework — Spring AOP capabilities](https://docs.spring.io/spring-framework/reference/core/aop/introduction-spring-defn.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Declaring Pointcuts](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Boot — AOP auto-configuration](https://docs.spring.io/spring-boot/reference/features/aop.html)
- [Spring Boot 4.0 Migration Guide — AOP starter rename](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
