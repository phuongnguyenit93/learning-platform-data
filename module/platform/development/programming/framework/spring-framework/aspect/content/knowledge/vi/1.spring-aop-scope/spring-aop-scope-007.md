# Spring AOP và quan hệ với IoC, Dependency Injection, vòng đời bean

## 1. Spring AOP nằm ở đâu trong Spring container?

**Spring IoC container** (`ApplicationContext` hoặc `BeanFactory`) chịu trách nhiệm tạo, cấu hình, kết nối và quản lý vòng đời của bean. **Spring AOP** tận dụng container đó để nhận diện aspect/advisor, xác định bean phù hợp và cung cấp **AOP proxy** khi cần. Ứng dụng vẫn dùng IoC/DI bình thường nếu không bật AOP.

Khi một bean cần được advice áp dụng, đối tượng mà consumer nhận qua container có thể là **proxy** bao quanh đối tượng nghiệp vụ (target), thay vì target trực tiếp. Lời gọi từ bean khác đi vào proxy sẽ qua interceptor/advice rồi đến phương thức của target. Không phải mọi bean hoặc mọi phương thức đều được proxy/advice: điều này phụ thuộc pointcut, cấu hình AOP và loại proxy.

```text
Bean definition + @Component / @Bean + @Aspect
                    |
             ApplicationContext
                    |
              tạo target bean
                    |
        giải quyết / inject dependency
                    |
        chạy lifecycle initialization
                    |
           auto-proxy creator
                    |
       xuất bản bean proxy (nếu cần)
                    |
              DI vào consumer
                    |
Consumer --> AOP proxy --> advice --> target.method()
```

Sơ đồ mô tả luồng **thông thường** cho singleton. Khi có circular dependency, scoped proxy, custom `BeanPostProcessor` hay cấu hình đặc biệt, đường đi thực tế có thể phức tạp hơn.

### Vai trò của từng thành phần

| Thành phần Spring | Trách nhiệm |
| --- | --- |
| `ApplicationContext` / `BeanFactory` | Quản lý bean, dependency và vòng đời |
| Target bean | Chứa logic nghiệp vụ cần gọi |
| Aspect bean | Chứa advice và pointcut, bản thân được Spring quản lý |
| Auto-proxy creator | Hạ tầng Spring xác định bean được advice và tạo proxy |
| AOP proxy | Đón lời gọi từ caller, áp dụng interceptor/advice, chuyển tiếp đến target |
| Dependency Injection | Cấp tham chiếu bean từ container cho đối tượng sử dụng; tham chiếu đó có thể là proxy |

**IoC không phụ thuộc AOP**, trong khi tính năng tự tạo proxy của Spring AOP thường phụ thuộc việc target và aspect được quản lý bởi Spring.

## 2. IoC container phát hiện aspect và tạo proxy thế nào?

Với cách viết theo annotation, quy trình cơ bản:

1. Có dependency Spring AOP và thư viện AspectJ hỗ trợ phân tích biểu thức pointcut.
2. Kích hoạt `@AspectJ` auto-proxy: trong Spring Framework thuần dùng `@EnableAspectJAutoProxy`; Spring Boot thường cấu hình tự động khi AOP dependency hiện diện.
3. Đăng ký aspect thành **Spring bean**: `@Aspect` kết hợp `@Component`, hoặc tạo bean aspect qua `@Bean`.
4. Spring nhận diện advice/pointcut, chọn các target bean phù hợp và tạo proxy. Khi consumer yêu cầu bean qua DI, container cấp tham chiếu đã qua xử lý.

**Chỉ có `@Aspect` là chưa đủ để component scan đăng ký bean.** `@Aspect` khai báo vai trò AOP; `@Component` hoặc `@Bean` đưa aspect vào container. Aspect cũng có thể dùng constructor injection để lấy repository/service, nhưng nên tránh circular dependency giữa aspect và các bean mục tiêu. Một bean có `@Aspect` không phải đối tượng để các aspect khác auto-advice trong Spring AOP.

Ví dụ cấu hình **Spring Framework thuần** (đoạn cấu hình, không phải ứng dụng độc lập):

```java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("demo.aop")
class AopConfig {
}
```

Trong `@AspectJ` support của Spring AOP, Spring dùng ngôn ngữ pointcut theo AspectJ và dependency `aspectjweaver`, nhưng **không cần AspectJ compiler hoặc load-time weaving** để chặn lời gọi phương thức trên Spring proxy.

### Tại sao `BeanPostProcessor` lại quan trọng?

`BeanPostProcessor` nhận callback trước/sau giai đoạn initialization của bean. Một số thành phần hạ tầng AOP (auto-proxy creator) sử dụng cơ chế này để bọc bean thành proxy. Vì vậy instance của `PaymentService` được tạo ra và instance được inject cho một consumer có thể là hai đối tượng Java khác nhau: target và proxy. Đừng dựa vào `bean.getClass() == PaymentService.class` hoặc ép kiểu nội bộ theo suy đoán để kết luận về AOP.

Hạ tầng AOP/auto-proxy và các post-processor có quy tắc khởi tạo riêng, nên một số bean cơ sở hình thành rất sớm có thể không được áp dụng advice giống các bean nghiệp vụ thông thường.

## 3. Dependency Injection quyết định đường đi của lời gọi

Một consumer do Spring quản lý có thể khai báo constructor injection:

```java
@Service
public class CheckoutService {
    private final PaymentService paymentService;

    public CheckoutService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout(String orderId) {
        paymentService.pay(orderId);
    }
}
```

Đây là ví dụ minh họa; `PaymentService` được định nghĩa trong ví dụ hoàn chỉnh phía dưới. Nếu container đã bọc `PaymentService` thành AOP proxy, dependency truyền vào constructor có thể chính là proxy. Consumer gọi qua dependency này sẽ được advice áp dụng khi pointcut khớp.

Ngược lại, khi viết `new PaymentService()` và gọi trực tiếp phương thức trên object tự tạo, Spring không tự quản lý object đó và không tự gắn AOP proxy. Điều tương tự xảy ra khi bên trong consumer tự `new` một dependency thay vì nhận qua DI.

### Kiểu proxy và kiểu dependency

- **JDK dynamic proxy** triển khai các interface của target. Nếu dùng kiểu này, điểm inject nên khai báo theo interface; inject class implementation có thể thất bại do kiểu thực tế không tương thích.
- **Class-based proxy (CGLIB)** là lớp con của target, thường hỗ trợ DI theo concrete class. Spring Boot mặc định dùng class-based proxy khi auto-configure AOP; có thể đặt `spring.aop.proxy-target-class=false` để chọn JDK proxy trong trường hợp thích hợp.
- Với CGLIB, class `final` không thể được subclass để proxy; phương thức `final` hoặc `private` không thể bị override để advice theo cách đó.
- Spring Framework thuần và Spring Boot có thể chọn mặc định khác nhau; luôn xét cấu hình thực tế của ứng dụng.

Các hàm chẩn đoán hữu ích: `AopUtils.isAopProxy(bean)`, `AopUtils.isJdkDynamicProxy(bean)`, `AopUtils.isCglibProxy(bean)`. Chúng giúp xác định proxy hiện tại nhưng không thay thế việc kiểm tra pointcut và đường gọi.

## 4. Vòng đời bean: lúc nào advice được kích hoạt?

Với bean singleton thông thường:

1. **Instantiation:** Spring tạo target bằng constructor hoặc factory method.
2. **Dependency population:** container cấu hình target và inject các dependency cần thiết.
3. **Initialization:** các `BeanPostProcessor` trước initialization hoạt động; lifecycle callbacks như `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, custom init method được thực hiện theo quy tắc Spring.
4. **Post-initialization:** auto-proxy creator có thể bọc target và trả về proxy.
5. **Use:** consumer nhận bean qua DI và gọi phương thức đi qua proxy; advice hoạt động nếu pointcut khớp.
6. **Destruction:** context đóng thì Spring điều phối các callback hủy cho singleton thích hợp (chẳng hạn `@PreDestroy` hoặc `DisposableBean.destroy()`).

Từ trình tự trên, có ba hệ quả thực tế:

**`@PostConstruct` chạy trong lifecycle của target.** Các lời gọi ở bước này thường diễn ra trước khi proxy cuối cùng được cấp cho consumer. Vì vậy không nên đặt logic trông chờ `@Transactional`, logging advice hay security advice trong `@PostConstruct` hoặc gọi nội bộ từ phương thức init rồi cho rằng advice chắc chắn chạy.

**`@PreDestroy` là callback do container thực thi.** Không nên trông chờ AOP intercept theo cách của một business method thông thường để giải phóng tài nguyên. Đặt cleanup trực tiếp trong callback; callback cũng không được bảo đảm nếu JVM bị dừng cưỡng bức.

**Bean scope có ảnh hưởng tới lifecycle.** Spring gọi initialization cho prototype mà nó tạo nhưng không tự quản lý toàn bộ destruction của prototype như singleton. Inject trực tiếp một prototype vào singleton cũng không khiến nó tự được tạo lại trên mỗi method call. Scoped proxy là cơ chế riêng, có thể cùng xuất hiện với AOP proxy.

## 5. Ví dụ chạy: Spring Boot, DI, advice, init/destroy và self-invocation

Tạo một dự án **Spring Boot 3.x, Java 17+** bằng Spring Initializr, build bằng Maven, thêm dependency **Spring AOP** (`spring-boot-starter-aop`). Dự án Boot thông thường đã có starter cơ bản. Đặt các tệp sau vào package `demo.aop`. Boot sẽ auto-configure AOP, nên ví dụ không cần khai báo `@EnableAspectJAutoProxy`.

**Tệp `src/main/java/demo/aop/AopApplication.java`**

```java
package demo.aop;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AopApplication {
    public static void main(String[] args) {
        SpringApplication.run(AopApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(PaymentService service) {
        return args -> {
            System.out.println("[di] proxy=" + AopUtils.isAopProxy(service));
            service.pay("A01");
            service.placeOrder();
        };
    }
}
```

**Tệp `src/main/java/demo/aop/PaymentService.java`**

```java
package demo.aop;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    @PostConstruct
    void initialize() {
        System.out.println("[lifecycle] init target");
    }

    public void pay(String orderId) {
        System.out.println("[business] pay " + orderId);
    }

    public void placeOrder() {
        System.out.println("[business] placeOrder");
        this.pay("B02"); // Gọi nội bộ, không đi qua proxy
    }

    @PreDestroy
    void cleanup() {
        System.out.println("[lifecycle] destroy target");
    }
}
```

**Tệp `src/main/java/demo/aop/TracingAspect.java`**

```java
package demo.aop;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TracingAspect {
    @Around("execution(public void demo.aop.PaymentService.pay(java.lang.String))")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        System.out.println("[aop] before");
        try {
            return joinPoint.proceed();
        } finally {
            System.out.println("[aop] after");
        }
    }
}
```

Chạy tại thư mục gốc của dự án Maven:

```bash
mvn spring-boot:run
```

Những dòng `System.out` cần chú ý, theo thứ tự tương ứng (ngoài các log của Spring Boot):

```text
[lifecycle] init target
[di] proxy=true
[aop] before
[business] pay A01
[aop] after
[business] placeOrder
[business] pay B02
[lifecycle] destroy target
```

Giải thích kết quả:

- `[lifecycle] init target` xuất hiện trước khi runner gọi service. Không có advice cho `initialize()`.
- Spring inject bean `PaymentService` vào tham số của `CommandLineRunner`. Aspect áp dụng lên phương thức `pay` nên kết quả `AopUtils.isAopProxy(service)` là `true`.
- `service.pay("A01")` đi qua proxy: trước `pay` có `[aop] before`, sau đó là `[aop] after`.
- `service.placeOrder()` có lời gọi từ bên ngoài, nhưng advice chỉ chọn `pay`. Bên trong target, `this.pay("B02")` không đi qua proxy nên không xuất hiện hai dòng advice quanh `B02`.
- Khi ứng dụng kết thúc và context đóng bình thường, Spring gọi `@PreDestroy`; dòng `destroy target` phản ánh lifecycle callback, không phản ánh business advice.

**Giới hạn self-invocation là tính chất cốt lõi của Spring AOP dạng proxy.** Khi cần advice cho `pay` trong luồng từ `placeOrder`, cách đơn giản là đưa phần gọi cần intercept vào một Spring bean khác, sau đó constructor-inject bean đó và gọi qua tham chiếu Spring. Có thể dùng proxy tự tham chiếu theo cấu hình đặc biệt, nhưng cách đó làm code phụ thuộc vào hạ tầng AOP và dễ tạo vấn đề vòng đời/circular dependency.

## 6. Những nhầm lẫn liên quan trực tiếp vòng đời bean

| Trường hợp | Điểm cần kiểm tra |
| --- | --- |
| `@PostConstruct` gọi method có advice | Callback initialization thường chạy trên target trước khi proxy cuối cùng được công bố; chuyển công việc cần interception sang một lời gọi qua bean sau khởi tạo. |
| `@PreDestroy` mong chạy qua advice | Cleanup là lifecycle callback do container điều phối; viết cleanup ở callback thay vì phụ thuộc business interceptor. |
| Prototype bean được inject trực tiếp vào singleton | Injection diễn ra theo lifecycle của singleton; prototype không tự được cấp mới ở mỗi lời gọi method. Nếu cần mỗi lần lấy mới, cân nhắc provider hoặc lookup phù hợp. |
| Scoped proxy bị nhầm với AOP proxy | Scoped proxy giải quyết cách tham chiếu bean theo scope; không đồng nghĩa có advisor ứng dụng. Một bean có thể chịu nhiều tầng proxy. |
| Aspect inject đúng target mà nó advice | Có nguy cơ tạo circular dependency, dẫn tới proxy sớm hoặc lỗi khởi tạo. Tách dependency quan sát ra bean độc lập và kiểm tra đồ thị phụ thuộc. |

Những trường hợp này là vấn đề **thời điểm và nguồn tham chiếu bean**; kiểm tra `AopUtils` chỉ giúp biết tham chiếu hiện tại có proxy hay không, còn lifecycle đòi hiểu khi nào container tạo, inject, khởi tạo và hủy bean.

### Một lưu ý về thiết kế DI

Constructor injection thể hiện dependency rõ ràng và cho Spring cơ hội cung cấp proxy phù hợp. Nó **không tự giải quyết** circular dependency. Nếu phải self-inject chỉ để AOP advice một phương thức, nên xem lại ranh giới trách nhiệm của các service thay vì lách vòng đời bean.

`@Lazy` và scoped proxy cũng tạo tham chiếu gián tiếp, nhưng không đồng nghĩa với AOP advice. Một ứng dụng có thể có nhiều lớp proxy; hãy xác định nguồn của proxy bằng cấu hình và công cụ chẩn đoán thay vì chỉ xem tên class runtime.

## 7. Checklist phân tích khi lời gọi không được aspect chặn

1. Target và aspect có thuộc đúng `ApplicationContext`? Có `@ComponentScan`, `@Bean` và dependency AOP đầy đủ?
2. Aspect có `@Aspect` **và** đã được đăng ký thành bean? Spring Framework thuần đã bật `@EnableAspectJAutoProxy` hoặc cấu hình tương đương?
3. `AopUtils.isAopProxy(targetInjected)` có trả `true`? Proxy là JDK hay CGLIB, phù hợp với kiểu dependency?
4. Pointcut có thực sự khớp phương thức **được gọi**? Phương thức có thuộc trường hợp `private`/`final` không thể intercept bằng class proxy?
5. Caller gọi qua Spring-injected reference hay là `new`, `this.method()`, hoặc gọi trong initialization callback?
6. Nếu logic phụ thuộc transaction/cache/async, hãy kiểm tra cách annotation đó tạo và dùng proxy trong cấu hình hiện tại.
7. Nếu liên quan lifecycle, phân biệt rõ `@PostConstruct`, lời gọi sau khi context sẵn sàng và `@PreDestroy`.

## 8. Câu hỏi ôn tập

**1. IoC/DI có cần Spring AOP để hoạt động?** Không. IoC và DI là cơ sở quản lý bean; Spring AOP có thể dùng chúng để tự động cung cấp proxy.

**2. Tại sao DI vào service lại nhận proxy?** Auto-proxy creator có thể thay tham chiếu bean được container công bố bằng proxy chứa interceptor/advice.

**3. Vì sao `@Around` không chạy quanh `this.pay()`?** Vì lời gọi đi trực tiếp trên target, không đi qua tham chiếu proxy của Spring.

**4. Có thể tin rằng `@Transactional` chạy trong `@PostConstruct` không?** Không nên. Initialization callback thường diễn ra trên target trước khi có luồng gọi business qua proxy.

**5. Tại sao DI theo interface chạy nhưng DI theo implementation đôi khi lỗi?** JDK proxy chỉ triển khai interface của target, trong khi class-based proxy dùng subclass của target.

## Tài liệu tham khảo chính thức

- [Spring Framework: @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework: Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework: BeanPostProcessor / Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework: @PostConstruct và @PreDestroy](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Spring Boot: Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html)
