# Lời gọi trong quá trình khởi tạo và giới hạn của @PostConstruct trong Spring AOP

## 1. Vấn đề thực tế: cùng một method nhưng advice chỉ chạy sau khi bean sẵn sàng

Trong Spring AOP sử dụng auto-proxy, một phương thức của Spring bean có thể **không kích hoạt advice khi được gọi từ constructor hoặc callback khởi tạo `@PostConstruct`**, dù sau đó cùng phương thức ấy được advice khi gọi qua bean lấy từ `ApplicationContext`.

Cần phân biệt hai điều kiện riêng:

1. **Vòng đời:** tại thời điểm gọi, Spring đã tạo và công bố proxy hoàn chỉnh của bean đích hay chưa?
2. **Đường đi lời gọi:** code đang gọi **chính instance đích (`this`)** hay một **tham chiếu đến proxy** của Spring?

Chỉ gắn `@Aspect`, viết pointcut đúng và bật `@EnableAspectJAutoProxy` chưa bảo đảm mọi lời gọi trong thời gian khởi tạo được intercept. Tình huống này liên quan trực tiếp đến **thứ tự BeanPostProcessor và auto-proxy của Spring**.

Trong bài, `@PostConstruct` luôn là `jakarta.annotation.PostConstruct` của Spring Framework 6.x / Spring Boot 3.x trở lên. Nếu học một dự án Spring 5 / Boot 2 cũ, thường gặp `javax.annotation.PostConstruct`; không hoán đổi package theo cảm tính giữa các thế hệ.

## 2. Thứ tự lifecycle liên quan đến auto-proxy

Với một singleton bean bình thường trong Spring Framework dùng `@EnableAspectJAutoProxy`, sơ đồ khái quát:

```text
Spring ApplicationContext
        |
        v
Đăng ký BeanDefinition và BeanPostProcessor, bao gồm AOP auto-proxy creator
        |
        v
Tạo target instance (constructor / factory method)
        |
        v
Dependency injection và các Aware callbacks
        |
        v
BeanPostProcessor.postProcessBeforeInitialization(...)
  └─ xử lý @PostConstruct (khi có processor tương ứng)
        |
        v
Các init callbacks khác (InitializingBean, @Bean(initMethod), ...)
        |
        v
BeanPostProcessor.postProcessAfterInitialization(...)
  └─ AOP auto-proxy creator có thể wrap target bằng proxy
        |
        v
Đưa bean hoàn tất/proxy vào container cho client sử dụng
        |
        v
Lời gọi qua proxy -> advisor/pointcut -> advice -> target method
```

Sơ đồ cố ý trình bày **đường đi thông thường**, không phải tuyên bố mọi bean đều qua đúng một quy trình không ngoại lệ. Spring hỗ trợ các hook tạo bean sớm, `FactoryBean`, xử lý circular dependency và một số kiểu proxy đặc biệt; những trường hợp ấy có thể điều chỉnh thời điểm tạo proxy. Tuy nhiên, **không được dựa vào ngoại lệ lifecycle để bảo đảm AOP trên callback khởi tạo**.

Điều quan trọng trong Spring là:

- `CommonAnnotationBeanPostProcessor` (kế thừa cơ chế xử lý lifecycle annotations) thực hiện `@PostConstruct` **trước khi** bean hoàn tất initialization.
- `BeanPostProcessor#postProcessAfterInitialization` là điểm thông thường nơi AOP auto-proxy creator có thể trả về **proxy thay cho target gốc**.
- Theo tài liệu Spring Framework về initialization callbacks, callback khởi tạo được gọi trên **raw bean**, do đó các AOP interceptors thường **chưa áp dụng** cho invocation của init method.
- Sau khi bean hoàn tất, các **caller dùng tham chiếu proxy** mới kích hoạt advice cho method được pointcut chọn.
- `@PostConstruct` dùng để thiết lập invariant/cấu trúc nội bộ của bean; Spring 6.2 lưu ý callback chạy trong giai đoạn singleton creation lock và **không phù hợp để kích hoạt công việc nặng, truy cập thêm nhiều bean hoặc khởi động luồng nền phức tạp**.

### 2.1. Vị trí tương đối của các init callbacks

Đối với một bean có nhiều callback với các method khác nhau, Spring mô tả thứ tự thông thường:

1. Method gắn `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`, nếu bean implement interface.
3. Custom initialization method, chẳng hạn `@Bean(initMethod = "init")`.

Các bước này thuộc **khởi tạo target**, không phải lời gọi public business method từ một consumer qua proxy. Vì vậy, việc callback được Spring gọi một lần không có nghĩa nó được tính như một method invocation đã được AOP advice.

Nếu method init bị lỗi và ném exception, quá trình tạo bean/context có thể thất bại. Advice `@AfterThrowing` trên business methods không mặc nhiên bắt hoặc chuyển đổi lỗi initialization: chúng chỉ quan sát method calls đi qua proxy đúng phạm vi.

## 3. Phân biệt bốn trường hợp thường bị đánh đồng

| Trường hợp | Đối tượng/đường gọi trong Spring | Advice Spring AOP proxy |
| --- | --- | --- |
| Constructor của bean gọi `this.process()` | Chạy trực tiếp trên object đang tạo; chưa có proxy bean hoàn chỉnh cho caller | **Không** chặn được lời gọi nội bộ ấy qua Spring AOP. |
| `@PostConstruct` của **chính target** gọi `this.process()` | Callback chạy trên raw target; `process()` là self-invocation | **Không** chặn lời gọi `process()` qua proxy. |
| Spring gọi **chính method gắn `@PostConstruct`** trên target | Lifecycle callback do post-processor gọi trong khởi tạo | **Không nên kỳ vọng** advice áp dụng cho callback ấy trong vòng đời thông thường. |
| `@PostConstruct` của **bean A** gọi `targetProxy.process()` của bean B đã init xong và được inject | Invocation đi qua **proxy của bean B** | **Có thể có**, nếu B đã proxy, pointcut match và method chặn được. |
| `main`/service/controller sau context refresh gọi `targetProxy.process()` | Lời gọi vào proxy của Spring-managed target | **Có**, nếu advisor match và proxy có thể intercept method. |

Hàng thứ tư là điểm rất dễ bị hiểu sai: **không phải mọi code nằm trong `@PostConstruct` đều bỏ qua AOP**. Nếu bean A được inject một bean B đã hoàn tất initialization và B có proxy, lời gọi **A → proxy B** vẫn có thể đi qua advice. Dẫu vậy, không nên lấy điều này làm lý do chạy một workflow nặng ngay trong `@PostConstruct` của A: các bean còn lại có thể chưa khởi tạo và nguy cơ deadlock/đụng lifecycle vẫn tồn tại.

### 3.1. Self-invocation và lifecycle là hai giới hạn khác nhau

Ngay cả khi target **đã được Spring proxy hoàn chỉnh**, lời gọi nội bộ `this.process()` từ một method khác trên cùng target vẫn có thể bỏ qua proxy. Vì thế cần tránh suy luận rằng “sau khi context refresh, mọi self-call đều được advice”.

```java
// Minh họa: code trong một Spring service đã được proxy
public void outer() {
    this.inner();  // không quay lại Spring proxy
}

public void inner() {
    // chỉ được advice khi được gọi qua proxy ở ranh giới phù hợp
}
```

Đây là đoạn minh họa, không phải class Java đầy đủ. Đổi `proxyTargetClass=true` hay dùng CGLIB **không chữa được** self-invocation trong mô hình Spring AOP proxy thông thường. `private` và `final` cũng không trở thành interceptable chỉ vì đổi loại proxy.

## 4. Demo độc lập: quan sát constructor, @PostConstruct, lời gọi giữa các bean và sau refresh

Ví dụ sử dụng:

- **Java 17+**, **Spring Framework 6.2.19** và **AspectJ Weaver 1.9.25.1**.
- `jakarta.annotation-api:2.1.1` để khai báo rõ `@PostConstruct`.
- Spring Framework Java configuration thuần để thấy auto-proxy được bật bằng `@EnableAspectJAutoProxy`.
- Hai bean `WorkService` (target) và `StartupCaller` (consumer), một `TraceAspect` với pointcut giới hạn rõ đến public methods của `WorkService`.

Ví dụ **không dùng Spring Boot** để loại bỏ sự phụ thuộc vào Boot AOP auto-configuration khi lý giải vòng đời. Các dependency/framework versions cần đồng bộ theo project thật.

### 4.1. Cấu trúc thư mục và Gradle

```text
spring-aop-init-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/initdemo/
    ├── Main.java
    ├── AppConfig.java
    ├── WorkService.java
    ├── StartupCaller.java
    └── TraceAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-init-demo'
```

**`build.gradle`**

```gradle
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
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

application {
    mainClass = 'com.example.initdemo.Main'
}
```

Spring Context mang theo hạ tầng annotation configuration; `@EnableAspectJAutoProxy` kích hoạt Spring AOP auto-proxy creator. Trong `AnnotationConfigApplicationContext`, các annotation processors chuẩn được đăng ký cho vòng đời `@PostConstruct`. Không cần đặt JVM agent `-javaagent`: bài sử dụng **Spring proxy-based AOP**, không phải AspectJ load-time weaving.

### 4.2. Target bean: chủ động tạo ba loại lời gọi

**`WorkService.java`**

```java
package com.example.initdemo;

import jakarta.annotation.PostConstruct;

public class WorkService {
    public WorkService() {
        System.out.println("constructor:begin");
        process("from-constructor");
        System.out.println("constructor:end");
    }

    @PostConstruct
    public void initialize() {
        System.out.println("postConstruct:begin");
        process("from-postConstruct");
        System.out.println("postConstruct:end");
    }

    public String process(String source) {
        System.out.println("target:" + source);
        return "done:" + source;
    }
}
```

Trong constructor và `initialize()`, phương thức `process()` được gọi trực tiếp trên **chính object**, không qua Spring proxy. Mặc dù `initialize()` là public và có thể được biểu thức `execution(...)` match về mặt signature, **Spring đang gọi nó như một lifecycle callback của target**, không phải client gọi qua AOP proxy. Không gọi `initialize()` trực tiếp như business method chỉ để bắt advice.

### 4.3. Aspect chặn public method trên WorkService

**`TraceAspect.java`**

```java
package com.example.initdemo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(public * com.example.initdemo.WorkService.*(..))")
    public void beforeWork(JoinPoint point) {
        System.out.println("advice:" + point.getSignature().getName());
    }
}
```

Pointcut áp dụng cho public methods được chọn của `WorkService`. Trong demo, `process()` và `initialize()` về mặt biểu thức đều thuộc lớp này. Không có yêu cầu sử dụng `@Component` vì `TraceAspect` được đăng ký bằng `@Bean` trong cấu hình phía dưới.

**Điều cần quan sát:** việc `@PostConstruct` được container gọi **không** tự làm xuất hiện `advice:initialize`. Khi method `process()` được gọi **qua proxy từ bean khác hoặc từ main**, advice sẽ in `advice:process`.

### 4.4. Caller bean có @PostConstruct của riêng nó

**`StartupCaller.java`**

```java
package com.example.initdemo;

import jakarta.annotation.PostConstruct;

public class StartupCaller {
    private final WorkService workService;

    public StartupCaller(WorkService workService) {
        this.workService = workService;
    }

    @PostConstruct
    public void initializeCaller() {
        System.out.println("callerPostConstruct:begin");
        workService.process("from-other-bean");
        System.out.println("callerPostConstruct:end");
    }
}
```

Ở đây `workService` là dependency **được Spring inject**, không phải `new WorkService()`. Do dependency cần được tạo và init trước khi `StartupCaller` có thể gọi nó, `StartupCaller.initializeCaller()` sẽ nhận bean `WorkService` sau bước hoàn tất thường lệ và có thể gọi **qua proxy**.

**Không biến đoạn này thành quy tắc cho production:** demo cố ý sử dụng lời gọi cross-bean nhẹ để chứng minh sự khác biệt. Trong ứng dụng thật, `@PostConstruct` không phải nơi khởi động request, transaction dài, gọi remote service hoặc lập lịch task nặng khi toàn bộ context có thể chưa sẵn sàng.

### 4.5. Cấu hình Spring tạo các bean theo cách tường minh

**`AppConfig.java`**

```java
package com.example.initdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    WorkService workService() {
        return new WorkService();
    }

    @Bean
    StartupCaller startupCaller(WorkService workService) {
        return new StartupCaller(workService);
    }
}
```

Spring tạo `WorkService`, thực hiện constructor/`@PostConstruct` trên target, rồi có thể đặt AOP proxy trước khi inject vào `StartupCaller`. Class `WorkService` không có interface, và cấu hình yêu cầu class-based proxy để lấy bean theo kiểu cụ thể. Cả target và aspect đều do container quản lý nhờ các phương thức `@Bean`; không cần `@ComponentScan`.

### 4.6. Gọi qua bean sau khi context refresh

**`Main.java`**

```java
package com.example.initdemo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            WorkService workService = context.getBean(WorkService.class);
            System.out.println("isProxy=" + AopUtils.isAopProxy(workService));
            System.out.println(
                "mainResult=" + workService.process("after-refresh")
            );
        }
    }
}
```

### 4.7. Chạy và đối chiếu stdout

Tại thư mục project, với Java 17+ và Gradle đã cài:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows).

Các dòng do mã ứng dụng in, theo thứ tự đối với project và cấu hình nêu trên:

```text
constructor:begin
target:from-constructor
constructor:end
postConstruct:begin
target:from-postConstruct
postConstruct:end
callerPostConstruct:begin
advice:process
target:from-other-bean
callerPostConstruct:end
isProxy=true
advice:process
target:after-refresh
mainResult=done:after-refresh
```

Đoạn stdout chỉ gồm các lệnh `System.out.println` đã mô tả; thông báo khởi động/cảnh báo riêng của JVM hoặc build tool có thể xuất hiện ngoài các dòng này.

**Phân tích bằng chứng:**

1. Sau `constructor:begin` là `target:from-constructor`, **không có `advice:process`**. Đây là lời gọi từ object đang được tạo.
2. Sau `postConstruct:begin` là `target:from-postConstruct`, **không có `advice:initialize` hay `advice:process`**. Callback chạy trên raw target; lời gọi `process` trong callback là self-invocation.
3. Sau `callerPostConstruct:begin` **có** `advice:process` trước `target:from-other-bean`. `StartupCaller` đã được inject tham chiếu proxy của `WorkService`. Điều này bác bỏ kết luận quá rộng rằng mọi method được gọi trong một `@PostConstruct` đều không thể AOP.
4. `isProxy=true` xác nhận `WorkService` sau context refresh đã là Spring AOP proxy.
5. Gọi `workService.process("after-refresh")` từ `Main` cũng in `advice:process` vì đi qua proxy đã hoàn tất.

Không có dòng `advice:initialize` vì callback `@PostConstruct` của target được gọi trực tiếp trong lifecycle. Nếu một developer cố gọi thủ công `workService.initialize()` sau refresh thì đó là **lời gọi khác**, có thể bị advice vì đi qua proxy; nhưng sẽ **khởi tạo lại** target theo cách không đúng contract. Không dùng thủ thuật này để “kiểm chứng” callback ban đầu.

## 5. Vì sao @PostConstruct không phải nơi khởi động workflow cần advice?

`@PostConstruct` phù hợp với bước local: kiểm tra cấu hình được inject, thiết lập cấu trúc dữ liệu nội bộ, xác nhận invariant đơn giản. Nó **không phải sự kiện toàn bộ ApplicationContext đã sẵn sàng**.

Những lý do cụ thể trong Spring:

- **Target có thể còn raw:** callback chạy trước lúc proxy cuối cùng được công bố; advice của chính target không đáng tin ở thời điểm này.
- **Self-invocation:** constructor/init gọi `this.method()` không đi qua Spring proxy dù method public và pointcut match.
- **Các singleton khác có thể chưa tạo:** truy cập tùy tiện bean khác từ `@PostConstruct` có thể làm Spring tạo sớm cả chuỗi dependency.
- **Creation lock:** Spring 6.2 nhấn mạnh callback init chạy trong giai đoạn singleton creation lock; gọi chuỗi bean phức tạp, chờ thread hoặc tác vụ DB/network dài có nguy cơ deadlock.
- **Transaction/cache/security proxy semantics:** nếu logic init cần `@Transactional`, `@Cacheable`, `@Async` hoặc method security thì gọi nội bộ ở phase này có thể bỏ qua interception tương ứng. Không suy rằng chỉ thêm annotation nghiệp vụ là transaction/async đã vận hành.
- **Khả năng test/giám sát:** lỗi xảy ra trong startup có thể khiến context không tạo xong; hook post-refresh thường có contract rõ hơn cho việc “khởi động công việc”.

**Ví dụ sai giả định:**

```java
@Service
public class ImportService {
    @PostConstruct
    public void onCreate() {
        importBatch(); // self-invocation trong init callback
    }

    @Transactional
    public void importBatch() {
        // Ghi nhiều bảng với kỳ vọng transaction bao quanh
    }
}
```

Đây là **đoạn minh họa** không phải ứng dụng đầy đủ. Kể cả khi `@EnableTransactionManagement` được bật, lời gọi `importBatch()` trực tiếp trên target từ `onCreate()` không bảo đảm đi qua transaction interceptor; cần tránh tin rằng annotation đã bao transaction trong trường hợp này. Transaction management còn đòi hỏi manager thích hợp và đúng ranh giới dữ liệu.

**Thiết kế rõ hơn:** `ImportService.importBatch()` là method của Spring bean B, còn bean điều phối khởi động A gọi **qua reference proxy B** sau thời điểm startup phù hợp, ví dụ sau context refresh. Nếu bắt buộc import sớm, vẫn phải đánh giá transaction manager, idempotency, thứ tự startup, lỗi/retry và môi trường nhiều replica.

## 6. Cơ chế nên dùng thay thế khi công việc phải chạy sau initialization

Chọn callback theo **mốc readiness** thật sự cần, rồi để bean điều phối **inject target bean qua Spring**.

| Nhu cầu | Cơ chế Spring phù hợp | Bảo đảm/giới hạn cần hiểu |
| --- | --- | --- |
| Thiết lập thuộc tính, validate dependency của **chính bean** | `@PostConstruct` | Chỉ local initialization. Không yêu cầu advice trên chính callback hay self-call. |
| Chờ các **non-lazy singleton** được container tạo xong | `SmartInitializingSingleton.afterSingletonsInstantiated()` | Chạy cuối giai đoạn tạo các non-lazy singleton; không nói rằng mọi lazy bean hoặc toàn bộ context events đã hoàn tất. |
| Chạy một bước sau **ApplicationContext refresh** | `@EventListener(ContextRefreshedEvent.class)` / `ApplicationListener<ContextRefreshedEvent>` | Context đã refresh; event có thể phát lại khi refresh, và có thể phát ở parent/child contexts. Thiết kế idempotent. |
| Khởi động/đóng tài nguyên cần phối hợp lifecycle | `SmartLifecycle` | Có start/stop và phase ordering, thường phù hợp component nền. |
| Spring Boot: chạy một công việc khi context đã khởi động và runners được gọi | `ApplicationRunner` hoặc `CommandLineRunner` | Hook của Boot; code gọi service được inject qua proxy. Có thể chặn startup nếu công việc lâu/lỗi. |
| Spring Boot: phản ứng sau khi startup hoàn tất | `@EventListener(ApplicationReadyEvent.class)` | Event từ Boot sau runners; **không chứng minh** downstream external dependency khỏe hoặc mọi task async đã hoàn tất. |

### 6.1. Ví dụ Spring Framework: điều phối sau ContextRefreshedEvent

Đoạn sau là **biến thể minh họa riêng**, không thêm vào project demo trên nếu muốn giữ nguyên stdout đã kiểm chứng.

```java
package com.example.initdemo;

import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

public class AfterRefreshCoordinator {
    private final WorkService workService;

    public AfterRefreshCoordinator(WorkService workService) {
        this.workService = workService;
    }

    @EventListener(ContextRefreshedEvent.class)
    public void onRefreshed() {
        workService.process("after-context-refreshed");
    }
}
```

Đăng ký từ config:

```java
@Bean
AfterRefreshCoordinator afterRefreshCoordinator(WorkService workService) {
    return new AfterRefreshCoordinator(workService);
}
```

Khi Spring phát `ContextRefreshedEvent`, `AfterRefreshCoordinator` gọi `WorkService.process` qua reference được inject từ container, nên method có thể đi qua advice nếu pointcut match. Trong ứng dụng có parent/child contexts, nhiều refresh hoặc nhiều node, cần lọc context/đảm bảo idempotency; đừng giả định sự kiện chỉ xảy ra đúng một lần trong suốt đời hệ thống.

**Điểm then chốt:** Mốc “sau refresh” giúp điều phối công việc ở phase phù hợp, nhưng **nếu event handler đặt ngay trong `WorkService` rồi gọi `this.process()`, self-invocation vẫn bypass advice**. Giữ bean điều phối tách khỏi bean nghiệp vụ khi cần gọi qua proxy.

### 6.2. Ví dụ Spring Boot: ApplicationRunner gọi qua bean khác

Với Spring Boot, một `ApplicationRunner` nhận dependency `WorkService` là lựa chọn sáng sủa cho startup task:

```java
package com.example.initdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupRunner implements ApplicationRunner {
    private final WorkService workService;

    public StartupRunner(WorkService workService) {
        this.workService = workService;
    }

    @Override
    public void run(ApplicationArguments args) {
        workService.process("boot-runner");
    }
}
```

Đây là **đoạn minh họa chỉ dành cho Spring Boot**, không biên dịch trong project Spring Framework thuần vì chưa khai báo dependency Boot. Boot có thể tự cấu hình AOP khi có starter phù hợp và không tắt auto-configuration; dù dùng Boot hay Framework, advice vẫn phụ thuộc pointcut và lời gọi qua proxy.

`ApplicationRunner` chạy khi khởi động ứng dụng Boot, trước khi Boot phát `ApplicationReadyEvent`. Nếu runner làm việc lâu, startup cũng chậm; các task nên có thiết kế timeout, lỗi và idempotency. Nếu cần quan hệ start/stop của một background component, xem `SmartLifecycle`.

### 6.3. SmartInitializingSingleton có giúp tránh self-invocation không?

Không. `afterSingletonsInstantiated()` chạy tại mốc muộn hơn `@PostConstruct`, nhưng **callback tự gọi method khác trên chính object** vẫn không tự động biến thành lời gọi qua AOP proxy. Nếu cần advice, dùng một **coordinator bean riêng** nhận proxy của service tương ứng.

Thứ tự startup callback giải quyết **khi nào công việc bắt đầu**; Spring AOP proxy quyết định **lời gọi đi qua đâu**. Phải thỏa cả hai điều kiện.

## 7. Khi constructor hoặc @PostConstruct buộc phải gọi code chung

Không phải mọi method được gọi từ constructor/init đều cần Spring AOP. Với logic thuần túy như validate input, xây bộ nhớ đệm local hoặc chuẩn hóa cấu hình, giữ thành **private helper** gọi trực tiếp là hợp lý:

```java
@PostConstruct
public void initialize() {
    validateConfiguration();
    createLocalIndex();
}

private void validateConfiguration() {
    // Chỉ kiểm tra dữ liệu đã được inject; không cần proxy.
}

private void createLocalIndex() {
    // Tạo cấu trúc dữ liệu local và bất biến sau khởi tạo.
}
```

Đoạn trên minh họa, không phải tệp runnable độc lập. Những private helper ấy **cố ý không cần AOP**, và `private` không được Spring subclass proxy override/intercept. Tách đúng mục tiêu:

- **Initialization local:** trực tiếp, không phụ thuộc proxy.
- **Use case nghiệp vụ cần transaction/security/audit/metric:** nằm trên method chặn được ở một Spring bean; caller có reference proxy.
- **Startup orchestration:** bean riêng chạy sau mốc phù hợp và gọi qua bean service đã sẵn sàng.

Đối với công việc cần giữ trạng thái hoặc tài nguyên ngoài, xây dựng cơ chế start/stop/retry riêng; đừng đặt nó trong constructor vì constructor có thể chạy trước khi dependency injection hoàn tất.

## 8. Các trường hợp nâng cao và giới hạn của phép suy luận

### 8.1. Không dùng ObjectProvider hoặc ApplicationContext.getBean trong constructor để “lấy proxy của chính mình”

Có thể tìm thấy cách cố lấy bean từ context, dùng `ObjectProvider`, self-injection hoặc `AopContext.currentProxy()` để gọi method của chính mình. Trong lúc constructor/`@PostConstruct` chạy, **proxy có thể chưa sẵn sàng**, hoặc bạn tạo ra phụ thuộc vòng gây khởi tạo sớm. `AopContext.currentProxy()` chỉ có khi `exposeProxy=true` và đang ở trong một lời gọi qua Spring AOP proxy; nó không biến constructor/init callback trở thành lời gọi được proxy.

Trong trường hợp method thật sự phải được intercept, ưu tiên **tách bean** và chọn mốc startup muộn hơn.

### 8.2. Early singleton references và circular dependencies

Spring có các bước xử lý early bean references trong những tình huống dependency vòng, và auto-proxy creator có thể tham gia qua các hook như `getEarlyBeanReference`. Không vì thế mà có thể kết luận “proxy đã tồn tại trong mọi `@PostConstruct`”. Thực tế việc khởi tạo sớm làm rủi ro nhận raw target/bean chưa được xử lý đầy đủ cao hơn. Cách ổn định nhất là **phá vòng dependency**, giữ constructor/init local và gọi nghiệp vụ sau khi dependency graph hoàn tất.

### 8.3. BeanPostProcessor và chính các bean được tạo sớm

Auto-proxy creator của Spring là một loại `BeanPostProcessor`. Một `BeanPostProcessor` khác và các bean nó trực tiếp phụ thuộc có thể bị tạo từ rất sớm, trước khi toàn bộ BeanPostProcessors được đăng ký. Tài liệu Spring cảnh báo một số bean thuộc giai đoạn này **không đủ điều kiện để được auto-proxy đầy đủ**, thường có log đại ý “not eligible for getting processed by all BeanPostProcessors”.

Không nhét nghiệp vụ cần AOP vào BeanPostProcessor hoặc dependency được tạo trong phase hạ tầng. Để hạ tầng BPP hoạt động đúng, các `@Bean` định nghĩa BeanPostProcessor thường được khuyến nghị khai báo `static` với ít dependency; đây là vấn đề cấu hình hạ tầng Spring, khác hẳn `@PostConstruct` của một service thông thường.

### 8.4. Cấu hình proxy và phương thức không chặn được

Không phải proxy nào cũng cho phép chặn mọi method:

- JDK dynamic proxy chặn các lời gọi thông qua interface của proxy.
- Class-based proxy (CGLIB) không override được `private`/`final` methods hoặc subclass một class `final`.
- Self-invocation trên target bỏ qua proxy trong cả hai cơ chế.
- Constructor **không phải Spring AOP method execution join point**; Spring proxy không cung cấp cách intercept các câu lệnh constructor tùy ý.

Nếu yêu cầu bắt constructor/field/đường gọi bên trong ở mức bytecode, cần xem phương án thiết kế khác hoặc AspectJ weaving riêng; `@EnableAspectJAutoProxy` không tự bật weaving.

## 9. Chẩn đoán khi advice không xuất hiện trong lúc startup

| Hiện tượng | Cách giải thích trong Spring | Kiểm chứng và xử lý |
| --- | --- | --- |
| Method gọi trong constructor không có advice | Target đang xây dựng; lời gọi là `this.method()` | Không dựa vào proxy trong constructor; chỉ làm initialization local. |
| Method được gọi từ `@PostConstruct` của chính target không có advice | Callback chạy trước proxy hoàn chỉnh; lời gọi nội bộ bỏ qua proxy | Chuyển use case cần AOP ra một service boundary; gọi từ coordinator sau startup. |
| `@PostConstruct` tự nó không có advice dù pointcut khớp | Lifecycle gọi trên raw bean trong chu kỳ initialization | Không dùng advice để điều khiển init callback; dùng hook lifecycle đúng nhiệm vụ. |
| `@PostConstruct` của bean A gọi method bean B và có advice | B đã init/proxy, A giữ reference của proxy | Hành vi có thể đúng; nhưng tránh lạm dụng post-construct cho công việc nặng. |
| Spring context tạo xong nhưng method vẫn không có advice | Aspect chưa là bean, thiếu auto-proxy support, pointcut không match hoặc caller dùng raw reference | Kiểm tra `@Aspect`+`@Component`/`@Bean`, `@EnableAspectJAutoProxy`, runtime proxy và actual invocation. |
| Self-call vẫn không có advice sau startup | `this` không quay lại proxy | Tách method sang bean khác, gọi qua injected proxy. |
| Tự tiêm bean của chính mình dẫn đến lỗi vòng dependency | Bean bị tham chiếu khi đang khởi tạo | Bỏ self-injection, phá vòng và thay bằng coordinator bean. |
| Có log “not eligible for auto-proxying” | Bean được tạo quá sớm trong quá trình bootstrap BeanPostProcessor | Kiểm tra BPP dependencies, `@Bean` static và thời điểm tạo bean. |
| Startup treo khi `@PostConstruct` truy cập nhiều bean hoặc chờ thread | Gọi hoạt động phức tạp trong singleton creation lock | Chuyển sang `SmartInitializingSingleton`/`ContextRefreshedEvent`/Boot runner tùy readiness. |
| `@Transactional`/`@Async` không tác dụng trong init | Proxy boundary hoặc cơ chế kích hoạt riêng của annotation chưa đáp ứng | Chẩn đoán proxy/service boundary và chọn hook sau initialization. |

### Một phép đo tối thiểu đáng tin

```java
WorkService bean = context.getBean(WorkService.class);
System.out.println(AopUtils.isAopProxy(bean));
bean.process("probe");
```

Đây là đoạn minh họa đặt **sau context refresh**, có import `AopUtils` và context/bean tồn tại. Nó kiểm tra hai việc:

1. `AopUtils.isAopProxy(bean)` xác nhận **reference hiện tại** có phải Spring AOP proxy.
2. Output/advice của lời gọi `process("probe")` chứng minh method cụ thể thực sự được advisor xử lý.

Chỉ xem `isAopProxy=true` là chưa đủ: proxy có thể dùng advisor khác và pointcut của aspect cần kiểm tra không match method `process`.

Để test lifecycle, đặt một recorder thread-safe ghi các mốc constructor/init/advice/target rồi assert thứ tự, thay vì dựa vào log framework trộn lẫn log ứng dụng. Nếu chạy bất đồng bộ, thứ tự giữa các thread không còn tất định; tránh ghi một bảng stdout cố định cho trường hợp ấy.

## 10. Quy tắc chọn nơi đặt khởi tạo

Hãy trả lời từng câu theo thứ tự:

1. **Hành động chỉ thay đổi trạng thái nội bộ của chính bean?** Nếu có, `@PostConstruct` phù hợp. Không ép nó đi qua Spring AOP.
2. **Hành động là một use case cần advice hoặc Spring interceptor?** Đặt nó ở một method service được proxy, rồi gọi từ một bean khác qua DI.
3. **Hành động cần chắc mọi singleton bình thường đã tạo?** Xem `SmartInitializingSingleton`, nhưng vẫn giữ đường gọi qua proxy.
4. **Hành động phải chạy sau ApplicationContext refresh?** Xem `ContextRefreshedEvent`, chú ý khả năng có nhiều contexts và re-publish.
5. **Đang ở Spring Boot và cần runner/ready event?** Sử dụng `ApplicationRunner` hoặc `ApplicationReadyEvent` theo thời điểm mong muốn.
6. **Công việc cần vận hành dài hạn, stop/restart?** Xem `SmartLifecycle`.
7. **Công việc cần gọi remote/DB hoặc async?** Xác định timeout, transaction, retry, idempotency, lỗi startup và khả năng chạy nhiều replicas.

Không nên coi **`@PostConstruct` + self-call đến method có annotation AOP** là mô hình gọi nghiệp vụ đáng tin, dù project đôi lúc cho thấy một vài advice vẫn được in ra trong các cấu hình đặc biệt.

## 11. Checklist QA thực hành

- [ ] Đã xác định rõ callback `@PostConstruct` thuộc **target nào** và method cần advice thuộc **target nào**.
- [ ] Với cùng target, constructor/`@PostConstruct` có gọi `this.method()` không? Nếu có, không kỳ vọng proxy AOP intercept.
- [ ] Aspect đã được đăng ký thành Spring bean, AOP auto-proxy được bật, pointcut match method?
- [ ] Với Spring Framework 6.x đã dùng `jakarta.annotation.PostConstruct` và dependency tương ứng?
- [ ] Đã phân biệt bean đang initialization với bean đã hoàn tất và proxy được inject vào một bean khác?
- [ ] Dùng `AopUtils.isAopProxy` **sau context refresh** để kiểm tra reference; gọi method qua chính reference ấy.
- [ ] Không dùng `AopContext.currentProxy()` hoặc self-injection trong constructor/init để né lifecycle.
- [ ] Không đặt remote call, transaction dài, scheduler nặng hay thao tác chờ các bean khác trong init callback?
- [ ] Khi công việc cần startup, đã chọn `SmartInitializingSingleton`, event, lifecycle hook hoặc Boot runner/ready event đúng mốc?
- [ ] Đã test đường gọi qua proxy và đường gọi nội bộ riêng biệt, so kết quả advice với kỳ vọng?
- [ ] Đã tính đến context hierarchy, circular dependency, lỗi startup và khả năng sự kiện được phát lại?

**Điểm nhớ:** Với Spring AOP proxy, `@PostConstruct` chạy trong vòng đời của **raw target** và không phải một lời gọi nghiệp vụ qua proxy; gọi `this.method()` từ đó sẽ bỏ qua advice. Nhưng `@PostConstruct` của một **bean khác** vẫn có thể gọi qua proxy của bean đã được tạo xong. Nếu yêu cầu thực sự cần transaction/security/audit/async advice, hãy **chọn đúng ranh giới bean và mốc startup**, đừng dựa vào interception trong lúc bean còn được khởi tạo.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Customizing the Nature of a Bean (lifecycle, raw bean, creation lock)](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)
- [Spring Framework 6.2 — Container Extension Points (BeanPostProcessor và auto-proxy)](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html)
- [Spring Framework 6.2 — Using @PostConstruct and @PreDestroy](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Spring Framework 6.2 — Proxying Mechanisms (self-invocation)](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
