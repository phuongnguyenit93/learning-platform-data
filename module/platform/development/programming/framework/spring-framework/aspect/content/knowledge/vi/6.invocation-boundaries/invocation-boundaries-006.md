# Lời gọi từ constructor hoặc callback khởi tạo trước khi Spring AOP proxy sẵn sàng

## 1. Vì sao method có @Aspect advice nhưng chạy lúc khởi tạo lại không được chặn?

Trong Spring AOP, advice chỉ có cơ hội chạy khi một lời gọi method **đi qua Spring AOP proxy** có advisor phù hợp. Trong quá trình tạo một Spring bean, có một khoảng thời gian mà **target object đã tồn tại nhưng proxy cuối cùng chưa được hình thành hoặc chưa được công bố cho các bean khác sử dụng**.

Vì vậy, một lời gọi method từ constructor, `@PostConstruct`, `InitializingBean.afterPropertiesSet()` hoặc custom init method của **chính bean đang được khởi tạo** sẽ không tự đi qua proxy của bean ấy. Nếu method đó có `@Before`, `@Around`, `@Transactional` hay `@Cacheable` được áp dụng qua Spring proxy, không nên mong cơ chế ấy hoạt động chỉ vì method được gọi ngay trong lifecycle hook.

Ví dụ:

```java
public class ReportService {
    public ReportService() {
        generate(); // lời gọi trên target đang được xây dựng
    }

    public void generate() {
        // Có thể khớp pointcut của một Spring @Aspect.
        // Nhưng constructor không gọi qua Spring proxy.
    }
}
```

Đây là đoạn minh họa, không phải chương trình độc lập. Dù Spring có thể tạo proxy cho `ReportService` **sau khi khởi tạo**, điều đó không thay đổi các lời gọi đã xảy ra trước đó.

**Phạm vi bài:** Ranh giới giữa bean lifecycle và Spring AOP theo cơ chế proxy. Ta tập trung vào Spring Framework, không mở rộng sang constructor weaving/AspectJ compiler độc lập. Những vấn đề được đề cập đều gắn trực tiếp với thời điểm Spring tạo proxy, lời gọi nội bộ và việc khởi động ứng dụng.

### Sau bài học, bạn có thể

1. Mô tả thứ tự tạo Spring bean từ constructor đến proxy hoàn chỉnh.
2. Giải thích vì sao các lời gọi từ `@PostConstruct`, `afterPropertiesSet()` và `initMethod` không nhận advice trên chính bean đó.
3. Phân biệt “callback được chạy sau khi dependencies đã được tiêm” với “callback được gọi qua AOP proxy”.
4. Thiết kế bước startup cần AOP bằng một bean điều phối gọi **bean khác qua proxy** sau khi context đã sẵn sàng.
5. Kiểm chứng hành vi bằng ví dụ Java 17 và Spring Framework 6.1 với stdout xác định.
6. Nhận ra các trường hợp ngoại lệ đáng chú ý: gọi sang dependency đã proxy, khởi tạo bean quá sớm, circular reference và callback vào context chưa hoàn chỉnh.

## 2. Trình tự thông thường của một Spring bean có AOP proxy

Với một singleton bean thông thường được tạo qua `ApplicationContext`, có thể hình dung trình tự:

```text
Spring đăng ký bean definitions và BeanPostProcessors
             |
             v
[1] Instantiation: gọi constructor / @Bean factory method
             |
             v
[2] Dependency injection, *Aware callbacks và xử lý thuộc tính
             |
             v
[3] BeanPostProcessor.postProcessBeforeInitialization(...)
       + xử lý @PostConstruct khi có processor tương ứng
             |
             v
[4] InitializingBean.afterPropertiesSet()
             |
             v
[5] Custom init method: @Bean(initMethod=...), init-method...
             |
             v
[6] BeanPostProcessor.postProcessAfterInitialization(...)
       + Spring AOP auto-proxy creator có thể bọc target bằng proxy
             |
             v
[7] Container công bố bean/proxy đã khởi tạo
             |
             v
[8] Bean khác lấy bean từ Spring và gọi method qua proxy
             |
             v
       @Before / @Around / target / @After...
```

Đây là **đường đi phổ biến, giản lược để học**. Spring có nhiều BeanPostProcessor và các trường hợp đặc biệt như early proxy references, FactoryBean, scoped proxy, circular dependencies hay custom target source. Những trường hợp đó có thể bổ sung bước, nhưng không làm thay đổi nguyên tắc cốt lõi: **gọi trực tiếp trên `this` không phải gọi qua Spring AOP proxy**.

### Thời điểm xử lý các callback

| Vị trí | Đối tượng nhận lời gọi | Có được Spring AOP advice cho method của chính bean không? | Lý do |
| --- | --- | --- | --- |
| Constructor của target | Target đang được xây dựng | **Không** | Proxy của bean chưa sẵn sàng; Spring AOP theo proxy cũng không advice constructor execution. |
| `@PostConstruct` trên target | Raw target qua lifecycle processor | **Không** đối với lời gọi trực tiếp trên chính bean | Callback chạy ở giai đoạn before-initialization, trước khi auto-proxy hoàn tất. |
| `InitializingBean.afterPropertiesSet()` | Raw target | **Không** | Đây là init callback của target, không phải lời gọi method từ client thông qua proxy. |
| `@Bean(initMethod = "...")` | Raw target | **Không** | Spring gọi init method trong bước khởi tạo target. |
| Gọi `this.otherMethod()` bên trong một init callback | Chính target | **Không** | Self-invocation đi thẳng đến target, bypass proxy. |
| Gọi method trên **dependency bean khác** đã được Spring cấp proxy | Proxy của dependency | **Có thể có** | Nếu dependency đã được proxy và lời gọi khớp advisor, lời gọi đi qua proxy của **bean khác**. |
| Bean điều phối gọi service được inject sau khi context refresh | Proxy của service | **Có thể có** | Proxy service đã được tạo, lời gọi đi qua object Spring cấp và match pointcut. |

**Điểm cần nhớ:** Câu “init callback chạy trước khi proxy sẵn sàng” nói về **proxy của bean đang khởi tạo**. Nó không có nghĩa *mọi* dependency đều chưa được proxy. Nếu target A đã inject B (một Spring bean proxy hoàn chỉnh) thì A có thể gọi B qua proxy ngay trong `@PostConstruct` của A. Dù vậy, gọi network/database trong lúc context còn khởi tạo có thể đem tới rủi ro về startup order và trạng thái tài nguyên.

## 3. Constructor: tại sao advice không chạy?

### 3.1. Constructor không phải method join point được Spring AOP proxy chặn

Spring AOP hỗ trợ **method execution join points trên Spring-managed beans qua proxy**. Khai báo:

```java
@Aspect
public class TraceAspect {
    @Before("execution(* com.example.service..*.*(..))")
    public void beforeMethod() {
        System.out.println("advice");
    }
}
```

không biến một lời gọi constructor thành method invocation qua proxy. Spring phải **tạo target trước**, sau đó mới có target để proxy.

CGLIB tạo subclass dùng làm proxy và thường sử dụng Objenesis để tránh gọi lại constructor target khi tạo proxy. Vì vậy, không được kết luận “CGLIB proxy sẽ cho constructor chạy qua advice” hoặc “mỗi bean sẽ luôn có hai lần gọi constructor”. Spring AOP theo proxy không thực hiện constructor advice theo nghĩa AspectJ weaving.

### 3.2. Gọi method từ constructor cũng không phải gọi qua proxy

```java
public class InvoiceService {
    public InvoiceService() {
        processInvoice("startup"); // tương đương this.processInvoice(...)
    }

    public void processInvoice(String source) {
        System.out.println(source);
    }
}
```

Dù `processInvoice` là public, non-final và khớp `@Before` pointcut, lời gọi trên `this` trong constructor đang chạy trên **target chưa proxy**. Khi bean được lấy từ Spring sau đó và client gọi `proxy.processInvoice(...)` thì advice mới có cơ hội chạy.

Ngoài vấn đề AOP, việc gọi method có thể override từ constructor còn dễ lộ đối tượng chưa xây dựng hoàn chỉnh. Trong Spring, các dependency tiêm bằng `@Autowired`/`@Value` sau khi constructor chạy chưa sẵn sàng ở thời điểm đó. Constructor nên dùng để khởi tạo trạng thái nội tại, không để kích hoạt nghiệp vụ cần AOP hoặc dependency đã inject.

## 4. @PostConstruct: đã inject dependency chưa đồng nghĩa có proxy của chính mình

### 4.1. Bản chất @PostConstruct trong Spring

Trong Spring Framework 6.x, `@PostConstruct` đến từ package `jakarta.annotation`. Khi hạ tầng xử lý annotation lifecycle được đăng ký, method mang annotation chạy **sau dependency injection** nhưng **trước việc khởi tạo hoàn tất**, ở giai đoạn before-initialization.

```java
import jakarta.annotation.PostConstruct;

public class OrderService {
    @PostConstruct
    public void initialize() {
        saveOrder("from-init"); // self-invocation trên raw target
    }

    public void saveOrder(String id) {
        // Method này có thể khớp @Around/@Before của Spring AOP.
    }
}
```

Đây là đoạn minh họa. Nếu advice trông như không chạy đối với lời gọi `saveOrder` trong `initialize`, điều đó **phù hợp** với Spring proxy semantics. Không nên chỉ sửa pointcut, đổi từ JDK proxy sang CGLIB hoặc tăng `@Order` với kỳ vọng thay đổi ranh giới đó.

### 4.2. @PostConstruct trên chính method được advise thì sao?

Giả sử method vừa có annotation lifecycle vừa có annotation được pointcut nhắm đến:

```java
@PostConstruct
public void setup() {
    System.out.println("setup");
}
```

Spring gọi `setup()` thông qua lifecycle mechanism trên raw bean. Spring không phát lời gọi đó qua AOP proxy chỉ vì method public hoặc có annotation riêng.

Một lời gọi **sau này qua proxy** đến cùng method (nếu API cho phép, có advisor khớp và method proxy được) là tình huống khác; có thể nhận advice. Nhưng không nên thiết kế `@PostConstruct` như API nghiệp vụ để khách hàng gọi lại. Tách method lifecycle và method nghiệp vụ rõ ràng hơn, đồng thời giữ init idempotent nếu có thể.

### 4.3. Gọi dependency khác trong @PostConstruct là trường hợp khác

```java
public final class InitCoordinator {
    private final ReportService reportService;

    public InitCoordinator(ReportService reportService) {
        this.reportService = reportService; // Spring có thể inject proxy
    }

    @PostConstruct
    public void initialize() {
        reportService.generate(); // lời gọi trên dependency, không phải this
    }
}
```

Đây là snippet mô tả, với giả định Spring đăng ký `InitCoordinator` và `ReportService`, đồng thời dependency đã được proxy. Lời gọi `reportService.generate()` **có thể** nhận advice của `ReportService` ngay cả lúc `InitCoordinator` đang ở `@PostConstruct`. Tuy vậy, khác biệt quan trọng là **target bean của lời gọi advice không phải bean đang tự khởi tạo**.

Nếu logic đòi cả ứng dụng đã refresh, transaction infrastructure đã sẵn sàng và các service đang ở trạng thái ổn định, gọi vào dependency ngay trong `@PostConstruct` không phải lựa chọn tốt nhất. Một bước điều phối sau khi context đã khởi động thường dễ kiểm soát hơn.

## 5. InitializingBean và custom init method: cùng một nguyên tắc

Spring có thể chạy nhiều cơ chế khởi tạo cho một bean:

1. `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method cấu hình qua `@Bean(initMethod="...")` hoặc cấu hình tương đương.

Nếu một bean khai báo cả ba cơ chế với **ba method khác nhau**, thứ tự trên là thứ tự chuẩn. Tất cả đều là **initialization callbacks trên raw target**.

```java
public class CleanupService implements InitializingBean {
    @PostConstruct
    public void postConstruct() {
        process("postConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        process("afterPropertiesSet");
    }

    public void customInit() {
        process("customInit");
    }

    public void process(String phase) {
        System.out.println(phase);
    }
}
```

Đây là đoạn minh họa chưa gồm import và bean registration; ví dụ đầy đủ ở phần 7. Các lời gọi `process(...)` trên `this` đều bỏ qua proxy của `CleanupService`. Việc `InitializingBean` là một interface của Spring không làm init callback trở thành AOP invocation.

**Không nhầm callback khởi tạo với callback sau khi context refresh:** Method `afterPropertiesSet()` có nghĩa dependency properties đã được thiết lập trên bean, không có nghĩa mọi bean, advisor hoặc tài nguyên toàn ứng dụng đã ở trạng thái sẵn sàng.

## 6. Gọi method sau khi proxy sẵn sàng: ranh giới cần thiết

### 6.1. Gọi qua Spring-managed reference

```text
Trong constructor / @PostConstruct của Service:
    this.perform()
        |
        v
    target.perform()       => không có AOP proxy trong đường gọi

Sau khi context refresh, một bean khác đã inject Service:
    startupRunner -> serviceProxy.perform()
                       |
                       v
                   @Before/@Around...
                       |
                       v
                   target.perform()  => có advice nếu pointcut khớp
```

Một sự kiện context refresh có thể dùng làm **điểm điều phối** sau khi hạ tầng singleton đã được khởi tạo. Với Spring Framework thuần, có thể đăng ký một bean `ApplicationListener<ContextRefreshedEvent>` nhận proxy của service làm dependency và gọi service qua proxy. Với Spring Boot, `ApplicationRunner`/`CommandLineRunner` hoặc `ApplicationReadyEvent` thường được dùng cho tác vụ khởi động sau khi context được refresh, nhưng thời điểm cụ thể và tính thích hợp còn phụ thuộc việc cần chờ runner chạy xong hay chưa.

### 6.2. Hai lỗi có vẻ giống nhau

| Triệu chứng | Nguyên nhân | Cách xác định |
| --- | --- | --- |
| Aspect không chạy trong `@PostConstruct` của service, nhưng chạy khi controller gọi service | Lời gọi nội bộ trước proxy | Thực nghiệm cùng method trước/sau context refresh. |
| Aspect không chạy khi method A gọi `this.methodB()` **sau khi startup đã xong** | Self-invocation đi trên target, không qua proxy | Di chuyển methodB sang bean cộng tác và gọi qua dependency Spring. |

Điểm thứ hai quan trọng: **sau khi proxy được tạo, self-invocation vẫn bypass advice**. Thời điểm khởi tạo làm lỗi dễ xuất hiện hơn, nhưng bản chất proxy boundary luôn quyết định.

### 6.3. Không dùng AopContext.currentProxy() trong constructor để “lấy proxy sớm”

`AopContext.currentProxy()` chỉ có ý nghĩa khi đang thực thi một lời gọi **qua proxy được cấu hình exposeProxy**, ở luồng thực thi tương ứng. Constructor hoặc init callback thông thường của chính bean không ở trong lời gọi AOP proxy đó. Dựa vào API này có thể gây `IllegalStateException` hoặc làm mã gắn chặt vào Spring AOP.

Cũng không nên lưu `this` của target vào một static field hoặc phát tán reference này để “khởi động sớm”: client có thể giữ **raw target reference** và mãi không đi qua proxy, tạo lỗi rất khó truy vết.

## 7. Ví dụ chạy được: constructor → @PostConstruct → afterPropertiesSet → custom init → ContextRefreshedEvent

Ví dụ này dùng **Java 17, Spring Framework 6.1.14, Gradle**. Nó chứng minh bằng output rằng **cùng một method** chỉ được advice khi được gọi qua proxy sau khi bean đã hình thành.

Project Spring Framework thuần có năm lớp Java. Không cần Spring Boot, web server hay database.

### 7.1. Cấu trúc thư mục

```text
spring-aop-init-boundary/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/lifecycle/
    ├── StartupService.java
    ├── StartupAspect.java
    ├── StartupCaller.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Cấu hình build

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-init-boundary'
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
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

application {
    mainClass = 'demo.lifecycle.DemoApplication'
}
```

- `spring-context` cung cấp IoC container, `ApplicationListener`, `ContextRefreshedEvent` và Java-based configuration.
- `spring-aop` cung cấp AOP proxy infrastructure.
- `aspectjweaver` cung cấp những thành phần cần để Spring diễn giải `@Aspect` pointcut expression.
- `jakarta.annotation-api` cung cấp `@PostConstruct` trên Java 17; Spring context đăng ký hạ tầng xử lý annotation khi dependency tương ứng có mặt.

### 7.3. Target có bốn lời gọi cùng một method trong quá trình khởi tạo

`src/main/java/demo/lifecycle/StartupService.java`:

```java
package demo.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.InitializingBean;

public class StartupService implements InitializingBean {

    public StartupService() {
        System.out.println("constructor");
        perform("constructor");
    }

    @PostConstruct
    public void postConstruct() {
        System.out.println("postConstruct");
        perform("postConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("afterPropertiesSet");
        perform("afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("customInit");
        perform("customInit");
    }

    public void perform(String origin) {
        System.out.println("target:" + origin);
    }
}
```

Các method lifecycle gọi `perform` trực tiếp trên target. Method `perform(String)` là public và non-final, nên có thể được CGLIB advice khi client thực sự gọi qua proxy sau đó. Biến `origin` giúp ta biết lời gọi bắt nguồn ở giai đoạn nào.

### 7.4. Spring @Aspect theo dõi mọi lần gọi perform qua proxy

`src/main/java/demo/lifecycle/StartupAspect.java`:

```java
package demo.lifecycle;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class StartupAspect {

    @Before("execution(public void demo.lifecycle.StartupService.perform(String))")
    public void beforePerform(JoinPoint joinPoint) {
        String origin = (String) joinPoint.getArgs()[0];
        System.out.println("advice:" + origin);
    }
}
```

`StartupAspect` được Spring xử lý vì lớp có `@Aspect` và sẽ được đăng ký như bean trong `AppConfig`. `@Aspect` không tự động đăng ký bean nếu không có `@Component`, `@Bean` hay cơ chế tương đương.

Pointcut khớp method `StartupService.perform(String)`. Trong cả năm tình huống, method được gọi thực sự, nhưng chỉ những lần gọi **qua Spring proxy** mới kích hoạt advice.

### 7.5. Bean điều phối gọi sau khi context refresh

`src/main/java/demo/lifecycle/StartupCaller.java`:

```java
package demo.lifecycle;

import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;

public class StartupCaller
        implements ApplicationListener<ContextRefreshedEvent> {

    private final StartupService service;

    public StartupCaller(StartupService service) {
        this.service = service;
    }

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println("contextRefreshed");
        service.perform("contextRefreshed");
    }
}
```

`StartupCaller` không gọi `this.perform(...)`: nó giữ **dependency `StartupService` được Spring cấp**, tức proxy sau khi service được xử lý hoàn chỉnh. Sự kiện `ContextRefreshedEvent` được publish khi context refresh hoàn thành. Demo có một context duy nhất, nên không bị ảnh hưởng bởi trường hợp event truyền lên parent context.

Trong ứng dụng thật, `ContextRefreshedEvent` có thể được phát nhiều lần khi context refresh hoặc có nhiều context. Nếu tác vụ chỉ được phép thực thi một lần, cần idempotency/deduplication và kiểm tra event thuộc context mong muốn. Đừng gắn mọi startup work vào listener mà không cân nhắc đặc tính ấy.

### 7.6. Kích hoạt AOP và đăng ký các bean

`src/main/java/demo/lifecycle/AppConfig.java`:

```java
package demo.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean(initMethod = "customInit")
    public StartupService startupService() {
        return new StartupService();
    }

    @Bean
    public StartupAspect startupAspect() {
        return new StartupAspect();
    }

    @Bean
    public StartupCaller startupCaller(StartupService service) {
        return new StartupCaller(service);
    }
}
```

Cấu hình chủ động ép class-based proxy để ta lấy Spring bean theo kiểu `StartupService`. Không có việc tạo proxy trong constructor `new StartupService()`; Spring xử lý bean trong phần còn lại của lifecycle và áp dụng auto-proxy creator khi phù hợp.

`@Bean(initMethod = "customInit")` khiến Spring gọi `customInit` sau `afterPropertiesSet`. `StartupCaller` được tiêm service bằng container, nên nó nhận Spring-managed reference, không phải một object tự tạo bằng `new`.

### 7.7. Khởi chạy và quan sát

`src/main/java/demo/lifecycle/DemoApplication.java`:

```java
package demo.lifecycle;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            StartupService service = context.getBean(StartupService.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            service.perform("external");
        }
    }
}
```

Đặt các file đúng đường dẫn, sau đó chạy từ thư mục chứa `build.gradle`:

```bash
gradle run
```

Nếu dự án đã có Gradle Wrapper, chạy `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows).

Các dòng **do code của chương trình in ra** theo đúng thứ tự (không tính log từ Gradle hoặc môi trường):

```text
constructor
target:constructor
postConstruct
target:postConstruct
afterPropertiesSet
target:afterPropertiesSet
customInit
target:customInit
contextRefreshed
advice:contextRefreshed
target:contextRefreshed
proxy=true
advice:external
target:external
```

#### Đọc kết quả

1. Ở constructor, `@PostConstruct`, `afterPropertiesSet()` và `customInit()` đều thấy `target:...` nhưng **không có dòng `advice:...`**. Method `perform` đã chạy, nhưng đường gọi là raw target / `this`.
2. `contextRefreshed` xuất hiện sau bốn callback. Lúc này `StartupCaller` gọi `service.perform` qua Spring-managed reference, nên có `advice:contextRefreshed` trước `target:contextRefreshed`.
3. `proxy=true` xác nhận bean `StartupService` mà `getBean(...)` trả về là Spring AOP proxy.
4. Lời gọi `service.perform("external")` sau khi nhận bean từ container cũng có `advice:external`. Không cần sửa pointcut giữa startup và runtime.
5. Số lần gọi target là **sáu**: bốn lần trong lifecycle và hai lần qua proxy. Số lần advice là **hai**. Chênh lệch này minh chứng điểm chặn phụ thuộc lời gọi qua proxy.

**Lưu ý cách đọc stdout:** Ghi nhận hai dòng `advice:...` không có nghĩa Spring lúc khởi tạo “không nhận ra aspect”. Aspect đã được đăng ký; chỉ những lời gọi khởi tạo trên target không đi qua proxy. Các dòng kết quả giả định AOP được bật như `AppConfig` và các dependency đã được nạp đúng.

## 8. Nếu dùng @Transactional, @Cacheable hoặc @Async thì sao?

Các annotation sau cũng thường hoạt động qua Spring proxy:

| Cơ chế | Lời gọi trực tiếp từ init callback của cùng bean | Rủi ro khi suy luận sai |
| --- | --- | --- |
| Spring `@Aspect` advice | Không đi qua proxy của chính bean | Logging/audit/validation advice không chạy trong init call |
| `@Transactional` với proxy mode | Không đi qua transaction interceptor của chính bean | Không có transaction advice chỉ vì method có annotation |
| `@Cacheable` / `@CacheEvict` với proxy mode | Không đi qua cache interceptor của chính bean | Cache operation không diễn ra như tưởng tượng |
| `@Async` với proxy mode | Không đi qua async interceptor của chính bean | Lời gọi chạy đồng bộ trên thread khởi tạo, không chuyển vào executor |

Ví dụ sai về kỳ vọng:

```java
@PostConstruct
public void init() {
    rebuildCache(); // self-invocation; @Cacheable/@Transactional trên
                    // rebuildCache() không tự được áp dụng qua proxy
}
```

Đó chỉ là snippet minh họa, không có `CacheManager` hoặc transaction manager trong ví dụ chạy ở phần 7. Khi cần giao dịch hoặc caching thật sự trong startup work, hãy đặt nghiệp vụ vào **bean khác đã được Spring proxy** rồi gọi qua dependency tại một thời điểm thích hợp. Hạ tầng transaction/cache tương ứng phải được cấu hình đầy đủ; proxy không tự tạo `TransactionManager` hay `CacheManager`.

**Phân biệt quan trọng:** Tạo transaction bằng API lập trình trực tiếp như `TransactionTemplate` là một cơ chế khác với advice của `@Transactional`; có thể thực thi nếu dependency/hạ tầng phù hợp đã sẵn sàng, nhưng không làm self-invocation trở thành lời gọi qua proxy.

## 9. Khởi tạo quá sớm: bean không đủ điều kiện auto-proxy

Ngoài lỗi “callback của chính bean không có advice”, Spring còn có tình huống **bean được tạo trước khi các BeanPostProcessor cần thiết đăng ký đầy đủ**.

Ví dụ không nên làm:

```java
@Configuration
class EarlyProcessorConfiguration {

    @Bean
    BeanPostProcessor customProcessor(ExpensiveService service) {
        // Phụ thuộc trực tiếp vào ExpensiveService có thể khiến
        // service được khởi tạo quá sớm trong giai đoạn đăng ký BPP.
        return new CustomBeanPostProcessor(service);
    }
}
```

Đây là snippet giải thích vấn đề, **không phải file Java độc lập** vì `ExpensiveService` và `CustomBeanPostProcessor` chưa được khai báo. BeanPostProcessor cần được dựng rất sớm để có thể xử lý các bean khác. Nếu quá trình đăng ký chúng buộc tạo sớm service, service đó có thể không được mọi BeanPostProcessor (bao gồm AOP auto-proxy creator) xử lý. Spring có thể log cảnh báo dạng:

```text
Bean 'someService' ... is not eligible for getting processed
by all BeanPostProcessors (for example: not eligible for auto-proxying).
```

Đây là **dạng thông báo minh họa**; nội dung chính xác tùy phiên bản. Khác với tình huống init callback trên target, ở đây cả **lời gọi service sau startup** cũng có thể không nhận advice nếu bean đã được tạo quá sớm mà không được proxy thích hợp.

### Cách xử lý

- Tránh để BeanPostProcessor phụ thuộc trực tiếp vào những bean nghiệp vụ cần AOP.
- Khi dùng `@Bean` để khai báo BeanPostProcessor, nên để factory method là `static` và trả về kiểu BeanPostProcessor cụ thể hoặc giao diện `BeanPostProcessor` để Spring phát hiện sớm chính xác.
- Tránh gọi `getBean()` vào service tùy ý từ `BeanFactoryPostProcessor` hoặc code đăng ký hạ tầng quá sớm.
- Đọc cảnh báo `not eligible for auto-proxying`, xác định dependency nào khiến bean khởi tạo trước thời điểm phù hợp.
- Kiểm tra lại `AopUtils.isAopProxy(bean)` sau khi sửa cấu hình.

### Còn circular dependency và early proxy references?

Spring có thể cung cấp **early reference** cho một số tình huống phụ thuộc vòng, và auto-proxy creator có nhánh hỗ trợ early proxy reference trong những điều kiện thích hợp. Vì vậy, không thể phát biểu rằng “mọi early reference nhất định là raw target”, hoặc “bật cho phép circular reference chắc chắn giải quyết được advice”.

Giải pháp ổn định thường là **loại bỏ vòng phụ thuộc và việc phát tán `this` trong constructor/init**. Nếu một singleton A nhận B, B nhận lại A, việc A chưa hoàn tất lifecycle khiến hành vi AOP, transaction và cấu hình BeanPostProcessor khó dự đoán và đôi khi gây lỗi khởi tạo context. Đừng dùng circular reference như một cơ chế gọi advice trong `@PostConstruct`.

## 10. Các lựa chọn chạy startup work sau khi proxy đã hoàn thiện

### 10.1. Một bean điều phối lắng nghe ContextRefreshedEvent

Đây là cách đã có trong ví dụ phần 7. Điều phối viên dùng proxy của service, không gọi tự thân service trong constructor:

```text
ContextRefreshedEvent
       |
       v
StartupCaller (ApplicationListener)
       |
       v
StartupService proxy
       |
       v
Spring AOP advice
       |
       v
StartupService target
```

Nên bảo đảm callback **idempotent**, kiểm tra context identity khi có cây context cha–con và không thực thi vô hạn mỗi lần nhận sự kiện. Nếu khởi chạy ngoài Spring Boot, cách tiếp cận này không đòi Boot-specific runner.

### 10.2. SmartInitializingSingleton

Spring có giao diện `SmartInitializingSingleton` với callback `afterSingletonsInstantiated()` khi hoàn thành việc khởi tạo các singleton không lazy thông thường trong BeanFactory. Đây là điểm có ích khi cần tương tác với các bean đã khởi tạo.

Tuy nhiên:
- Callback nằm trên object mà Spring nhận diện là `SmartInitializingSingleton`; nếu chính object đó bị proxy với JDK interface không expose callback, cần kiểm tra cơ chế phát hiện và gọi callback thực tế. Đừng tùy tiện chuyển callback vào service đã proxy.
- Không phải mọi lazy singleton, prototype, request-scoped bean đều đã được tạo.
- Lời gọi `this.advisedMethod()` **vẫn bypass proxy** dù callback xảy ra muộn hơn.

Cách rõ ràng là để một bean điều phối không cần tự advice thực hiện callback, còn service cần AOP được lấy từ Spring như dependency rồi gọi qua proxy.

### 10.3. Spring Boot: ApplicationRunner, CommandLineRunner và ApplicationReadyEvent

Nếu ứng dụng là Spring Boot:
- `ApplicationRunner` và `CommandLineRunner` chạy sau khi context được refresh và Boot gọi runners.
- `ApplicationReadyEvent` được phát gần cuối startup, sau runners theo lifecycle Boot chuẩn.
- Một runner hoặc listener riêng có thể được inject Spring-managed service proxy và gọi method có advice.

Đây là **cơ chế Boot**, không tự tồn tại trong Spring Framework thuần. Dù gọi tại thời điểm nào, **tự gọi `this.method()` trong cùng target vẫn bỏ qua Spring AOP proxy**. Khi thiết kế công việc dài hoặc blocking ở startup, cân nhắc khả năng ứng dụng chưa sẵn sàng nhận request; đừng vô tình chặn lifecycle cần thiết.

### 10.4. Event listener cũng cần đúng ranh giới bean

`@EventListener` hoặc `ApplicationListener` chỉ là cách Spring giao sự kiện, không cam kết “mọi method của listener sẽ qua AOP proxy”. Nếu method handler nằm trên bean bị JDK proxy, nó có thể cần được expose qua interface hoặc dùng cấu hình proxy phù hợp. Nếu trong handler của service gọi `this.someAdvisedMethod()` thì vẫn là self-invocation.

Để giải thích và kiểm tra dễ nhất, **tách listener/runner thành một bean điều phối** và inject service proxy riêng, như ví dụ `StartupCaller`.

## 11. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân Spring AOP thường gặp | Cách sửa/kiểm tra |
| --- | --- | --- |
| Method public có `@Before` nhưng gọi từ constructor không in advice | Target còn đang xây dựng, chưa có đường gọi qua proxy | Đưa nghiệp vụ sang bước sau startup thông qua service proxy |
| `@PostConstruct` gọi method `@Transactional` nhưng không thấy transaction interceptor | Lời gọi `this.method()` trên raw target | Tách transaction method sang bean cộng tác và inject/call qua Spring proxy |
| `afterPropertiesSet()` gọi method `@Cacheable` mà lần sau vẫn phải tính lại | Init call bypass cache proxy | Di chuyển thao tác có cache qua bean proxy, kiểm tra cache manager |
| `@Async` method chạy trên main/startup thread khi gọi trong init | Không đi qua async proxy | Dùng runner/listener gọi bean khác sau khi hạ tầng sẵn sàng |
| Advice chạy sau startup nhưng không chạy ngay trong init | Hành vi proxy lifecycle chuẩn | So sánh stdout và `isAopProxy`; không coi đây là pointcut lỗi |
| Advice không chạy cả sau startup; log `not eligible for auto-proxying` | Bean bị khởi tạo quá sớm trong pha BeanPostProcessor | Sửa dependencies của post-processor, tránh tạo sớm bean nghiệp vụ |
| Gọi từ `@PostConstruct` của bean A sang bean B lại có advice | A đang inject **proxy B** đã hoàn tất | Bình thường; phân biệt owner của callback với bean target được gọi |
| Dùng `AopContext.currentProxy()` trong constructor bị lỗi | Không có active exposed proxy ở thời điểm đó | Không dùng như giải pháp khởi tạo; thiết kế bean điều phối |
| Có proxy CGLIB mà `this.method()` vẫn không có advice | Self-invocation là giới hạn của proxy mechanism | Gọi qua một Spring bean dependency/proxy thực sự |
| Listener chạy lặp sau refresh | Nhiều lần refresh, nhiều context hoặc event propagation | Filter đúng context, dùng trạng thái idempotent |
| Method annotated `@PostConstruct` không chạy | Chưa có Jakarta annotation API hoặc lifecycle processor phù hợp; method/config không hợp lệ | Kiểm tra Jakarta package, dependency, registration và lifecycle setup |

## 12. Quy trình chẩn đoán khi advice biến mất trong startup

Thay vì sửa cấu hình ngẫu nhiên, kiểm tra theo thứ tự:

1. **Lời gọi xảy ra ở đâu?** Constructor, `@PostConstruct`, `afterPropertiesSet`, custom init, event listener hay REST/service invocation sau startup?
2. **Bean nào thực sự được gọi?** Nếu là `this` trên target đang khởi tạo, đó không phải Spring AOP proxy. Nếu gọi dependency khác, kiểm tra dependency ấy có proxy chưa.
3. **Bean có được Spring quản lý không?** Dùng `new` tự tạo ngoài context không qua AOP post-processing.
4. **AOP đã được bật và aspect đã là Spring bean chưa?** Với Spring Framework, đăng ký `@EnableAspectJAutoProxy` trong context thích hợp; với Boot, xem AOP auto-configuration và dependency.
5. **Proxy có thật sự được tạo không?** Lấy bean sau startup từ context và kiểm tra `AopUtils.isAopProxy`; kiểm tra thêm JDK/CGLIB khi cần.
6. **Pointcut và method có khớp không?** Kiểm tra package, annotation, method visibility và giới hạn `final`/`private`. Nếu cùng method được advice khi gọi từ ngoài, vấn đề nằm ở call boundary.
7. **Bean có bị tạo quá sớm không?** Xem log BeanPostProcessor và bean definitions, đặc biệt `@Bean` method khai báo custom processors.
8. **Có circular dependency hoặc early reference không?** Tránh dùng early reference làm cách bảo đảm advice; sửa dependency graph.
9. **Nếu đã chuyển sang event/runner, kiểm tra thời điểm và idempotency.** Sự kiện có chạy nhiều lần? Service có thật sự được inject bằng proxy? Runner có chạy trong đúng context không?

## 13. Kết luận cần nhớ

Trong Spring AOP theo proxy, có hai ranh giới độc lập:

- **Ranh giới lifecycle:** Target được tạo và nhận init callback **trước** khi proxy cho bean đó hoàn tất.
- **Ranh giới lời gọi:** Chỉ method invocation **qua Spring AOP proxy** mới có thể được advice; self-invocation trên `this` bỏ qua advice, kể cả sau khi startup xong.

Constructor, `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và custom init method của bean là những nơi tốt để thiết lập **trạng thái nội bộ của bean**, nhưng không phải nơi thích hợp để kỳ vọng AOP advice trên chính bean đó. Với startup work cần logging, transaction, caching hoặc async advice, hãy dùng **bean điều phối** gọi **Spring-managed service proxy** tại thời điểm lifecycle đáp ứng nhu cầu và có cơ chế kiểm soát chạy lặp.

### Tài liệu Spring chính thức

- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): initialization callbacks thực thi trên raw bean, thứ tự `@PostConstruct` → `afterPropertiesSet` → custom init.
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): `BeanPostProcessor` trước/sau initialization, auto-proxying và bean khởi tạo quá sớm.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): Spring AOP proxy, self-invocation, JDK/CGLIB và Objenesis.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký `@Aspect` và bật `@EnableAspectJAutoProxy`.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ContextRefreshedEvent` và `ApplicationListener`.
- [Spring Framework — SmartInitializingSingleton Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): callback sau khởi tạo singleton thông thường.
