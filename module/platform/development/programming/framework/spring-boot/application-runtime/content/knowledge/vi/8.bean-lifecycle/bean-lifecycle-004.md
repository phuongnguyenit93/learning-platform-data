# BeanPostProcessor, proxy và thời điểm tham chiếu bean hoàn chỉnh

## 1. Vì sao cùng một bean lại có thể có hai đối tượng Java khác nhau?

Khi viết Spring Boot, ta thường định nghĩa một service rồi yêu cầu Spring tiêm nó vào thành phần khác:

```java
@Service
public class OrderService {
    public String createOrder() {
        return "created";
    }
}
```

```java
@Component
public class OrderClient {
    private final OrderService orderService;

    public OrderClient(OrderService orderService) {
        this.orderService = orderService;
    }
}
```

Đọc hai đoạn trên, người mới học có thể nghĩ biến `orderService` chắc chắn tham chiếu **đúng đối tượng được tạo bằng constructor `new OrderService()`**. Điều đó không phải lúc nào cũng đúng. Spring có thể giữ một đối tượng **đích (target)** để thực hiện nghiệp vụ nhưng cung cấp cho các thành phần khác một đối tượng **đại diện (proxy)**. Proxy nhận lời gọi bên ngoài, thực hiện các xử lý bổ sung như transaction, cache, security, retry hoặc logging rồi chuyển lời gọi tới target.

Chức năng này thường được lắp vào vòng đời bean bằng hạ tầng triển khai giao diện `BeanPostProcessor`. Vì vậy cần phân biệt:

- **Định nghĩa bean (bean definition):** thông tin để Spring tạo và cấu hình bean.
- **Đối tượng đích (target instance):** instance nghiệp vụ thực tế được tạo và khởi tạo.
- **Bean tham chiếu từ container:** instance cuối cùng mà `ApplicationContext.getBean(...)` hoặc dependency injection có thể trả về, trong một số trường hợp là **proxy** bao lấy target.
- **BeanPostProcessor:** thành phần hạ tầng có cơ hội kiểm tra/chỉnh/swap instance trong quá trình bean được tạo. Không phải mọi processor đều tạo proxy.

Đề bài này trả lời ba câu hỏi: **BeanPostProcessor can thiệp ở đâu? Khi nào proxy xuất hiện? Lúc nào mới nên dựa vào tham chiếu bean hoàn chỉnh?**

## 2. Sơ đồ vòng đời đơn giản của một bean singleton

Giả sử một bean thông thường được Spring quản lý, không có tình huống vòng phụ thuộc đặc biệt:

```text
BeanDefinition của OrderService
              |
              v
       Tạo instance đích
              |
              v
       Tiêm dependency / điền property
              |
              v
 BeanPostProcessor trước khởi tạo
  postProcessBeforeInitialization(...)
              |
              |  @PostConstruct được xử lý bởi một
              |  BeanPostProcessor chuyên dụng trong pha này
              v
       afterPropertiesSet() / init-method
              |
              v
 BeanPostProcessor sau khởi tạo
  postProcessAfterInitialization(...)
              |
              |  Một processor có thể trả về PROXY
              v
     Bean được công bố qua BeanFactory
              |
              v
      getBean(...) / tiêm dependency
              |
        Tham chiếu có thể là proxy
              |
     Gọi method qua proxy -> advice -> target
```

Sơ đồ trên diễn tả **ranh giới khái niệm** của một lần tạo bean. Không có một `BeanPostProcessor` duy nhất chạy trước và một processor duy nhất chạy sau: container có thể đăng ký **nhiều processor**. Trong Spring, một số hoạt động như xử lý `@Autowired`, `@PostConstruct` hoặc tạo AOP proxy cũng dựa vào hạ tầng processor.

**Chi tiết quan trọng về `@PostConstruct`:** việc phát hiện và gọi annotation này được đảm nhiệm bởi `CommonAnnotationBeanPostProcessor`/hạ tầng khởi tạo dựa trên `BeanPostProcessor`, thường diễn ra trong vòng gọi *before initialization*. Vì vậy không nên tuyên bố rằng **mọi** custom `postProcessBeforeInitialization` chắc chắn chạy **trước `@PostConstruct`**. Thứ tự giữa các processor phụ thuộc việc đăng ký và sắp xếp thứ tự. Điều chắc chắn hơn trong tình huống chuẩn là: callback **after initialization** của một processor áp dụng cho bean được gọi sau phần callback khởi tạo của bean đó.

Khi nhiều processor cùng can thiệp, giá trị `bean` truyền vào processor sau có thể đã được một processor trước đó thay thế. Vì thế **kể cả trong một callback `postProcessAfterInitialization`, không thể tự động kết luận bạn đang thấy reference cuối cùng mà tất cả processor sẽ trả về**.

## 3. BeanPostProcessor là gì?

Giao diện cốt lõi nằm ở:

```java
org.springframework.beans.factory.config.BeanPostProcessor
```

Hai phương thức thường dùng:

```java
Object postProcessBeforeInitialization(Object bean, String beanName);

Object postProcessAfterInitialization(Object bean, String beanName);
```

Trong Spring Framework hiện đại, giao diện có các implementation mặc định; khi tự định nghĩa processor, bạn có thể override một hoặc cả hai phương thức.

- `bean`: **instance hiện tại**, có thể là target hoặc một wrapper được tạo trước đó.
- `beanName`: tên bean trong Spring container.
- Giá trị trả về: **reference sẽ tiếp tục đi qua chuỗi xử lý**. Thường trả lại chính `bean` nếu chỉ quan sát; nếu có lý do chính đáng, có thể trả về một proxy/thành phần thay thế tương thích.
- `postProcessBeforeInitialization`: một callback trong pha trước các initialization methods truyền thống như `InitializingBean.afterPropertiesSet()` hoặc custom init method.
- `postProcessAfterInitialization`: callback trong pha sau khởi tạo, nơi nhiều dạng proxy/wrapper được áp dụng.

Một ví dụ processor chỉ ghi nhận callback:

```java
import org.springframework.beans.factory.config.BeanPostProcessor;

public class TraceProcessor implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        if ("orderService".equals(beanName)) {
            System.out.println("BPP before: " + beanName);
        }
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        if ("orderService".equals(beanName)) {
            System.out.println("BPP after: " + beanName);
        }
        return bean;
    }
}
```

Đây là một **lớp Java hợp lệ**, nhưng chỉ có tác dụng khi được đăng ký làm bean/hạ tầng trong một `ApplicationContext`. Không gọi bằng tay `new TraceProcessor().postProcessAfterInitialization(...)` rồi coi là Spring đã dùng nó.

`BeanPostProcessor` hoạt động trên **instance của bean được container quản lý**, không phải mọi đối tượng Java tạo bằng từ khóa `new`. Nếu bạn tự tạo `new OrderService()` ngoài Spring, các `BeanPostProcessor` của context không tự động chạy cho đối tượng đó.

## 4. Phân biệt BeanPostProcessor với BeanFactoryPostProcessor

Hai tên gần giống nhưng **mức tác động khác nhau**:

| Tiêu chí | `BeanFactoryPostProcessor` | `BeanPostProcessor` |
|---|---|---|
| Đầu vào chính | Bean definition/configuration metadata | Bean instance đang được tạo |
| Thời điểm thông thường | Trước khi khởi tạo bean ứng dụng thông thường | Quanh phần khởi tạo của từng bean |
| Dùng để | Điều chỉnh metadata/property của definition, cấu hình registry | Bổ sung xử lý lên đối tượng, kiểm tra, trang trí hoặc proxy |
| Phương thức ví dụ | `postProcessBeanFactory(...)` | `postProcessBeforeInitialization(...)`, `postProcessAfterInitialization(...)` |
| Có thể thay reference bean bằng proxy? | Không phải trách nhiệm điển hình | Có, đây là cơ chế thường dùng |
| Có nên gọi service nghiệp vụ? | Không; dễ kích hoạt bean quá sớm | Cũng phải cẩn thận; đang ở giữa vòng đời bean |

Với nhu cầu **bổ sung bean definition**, một số tình huống cần `BeanDefinitionRegistryPostProcessor`, vốn hoạt động ở cấp registry và có thời điểm sớm hơn việc tạo các bean ứng dụng.

Không giải quyết lỗi proxy bằng cách gọi `beanFactory.getBean(MyService.class)` bên trong `BeanFactoryPostProcessor`: việc đó có thể buộc bean được tạo **trước khi toàn bộ post-processors đã sẵn sàng**, khiến kết quả khác với vòng đời chuẩn.

## 5. Proxy được tạo khi nào?

Trong Spring AOP theo cơ chế proxy, hạ tầng auto-proxy chọn bean cần áp dụng advice, tạo wrapper/proxy phù hợp và cung cấp proxy cho code gọi từ bên ngoài. Hạ tầng này thường triển khai các giao diện mở rộng của `BeanPostProcessor`. Với đường đi phổ biến, proxy xuất hiện trong giai đoạn `postProcessAfterInitialization(...)`.

Hãy tưởng tượng một service gọi phương thức `pay()`:

```text
Bean target: PaymentService
        |
    @PostConstruct
        |
     init done
        |
   Auto-proxy creator
        |
   +-------------------------+
   | PaymentService proxy    | <--- Bean reference bên ngoài nhận
   |  logging / transaction  |
   +------------+------------+
                |
             target.pay()
                |
             kết quả
```

Lời gọi qua proxy cho phép Spring thực hiện điều kiện bổ sung **trước/sau** khi vào target. Ví dụ một phương thức được bảo vệ bởi transaction có thể đi qua proxy để mở/đóng transaction, nếu ứng dụng đã cấu hình đầy đủ hạ tầng transaction và transaction manager.

**Không phải cứ có `@Service` thì luôn có proxy.** Khi không có advice, cơ chế AOP hoặc hạ tầng khác cần proxy, bean có thể được trả về dưới dạng target trực tiếp. Cũng không thể khẳng định mọi proxy đều được tạo **chỉ duy nhất** trong callback sau khởi tạo: Spring có những cơ chế hạ tầng chuyên biệt để xử lý tham chiếu sớm (xem phần 11).

Đặc biệt, `BeanPostProcessor` là khái niệm **rộng hơn AOP**: có processor xử lý annotation, validate hoặc wrap object mà không liên quan trực tiếp đến AOP.

## 6. Ví dụ Spring Boot 3.3.x + Java 17+: quan sát bean đích và proxy

Ví dụ có đầy đủ mã và Gradle. Nó cho thấy `@PostConstruct` chạy trên target, một custom processor nhìn thấy callback khởi tạo, còn `ApplicationRunner` nhận một bean đã đi qua quá trình xử lý của context.

Project sử dụng `spring-boot-starter-aop` để có AspectJ annotations và hạ tầng Spring AOP. Không cần HTTP server nên dùng `spring-boot-starter` và `WebApplicationType.NONE`.

### 6.1. Cấu trúc thư mục

```text
bean-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/beanproxy/
    ├── BeanProxyApplication.java
    ├── GreetingService.java
    ├── GreetingAspect.java
    └── TraceBeanPostProcessor.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'bean-proxy-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Phiên bản này chỉ phục vụ bài thực hành; với repository thật, hãy dùng phiên bản Gradle/Spring Boot/JDK mà dự án đang quản lý. Để chạy lệnh Wrapper bên dưới, dự án cần các tệp `gradlew`/`gradlew.bat` cùng `gradle/wrapper`; tạo dự án qua Spring Initializr hoặc sinh Wrapper bằng bản Gradle phù hợp nếu chúng chưa có.

### 6.2. Service có @PostConstruct và lời gọi nội bộ

**`src/main/java/com/example/beanproxy/GreetingService.java`:**

```java
package com.example.beanproxy;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    @PostConstruct
    public void initialize() {
        System.out.println("Service: @PostConstruct");
        System.out.println("Service: self call = " + greet("noi-bo"));
    }

    public String greet(String person) {
        return "Xin chao " + person;
    }
}
```

`GreetingService` là lớp thường, không có `final` ở class hoặc phương thức `greet`. Ta muốn Spring tạo subclass proxy nên phải cho phép override. Lời gọi `greet("noi-bo")` bên trong `initialize` sử dụng trực tiếp `this` của target; ví dụ sẽ dùng nó để phân biệt **self invocation** với lời gọi qua proxy.

### 6.3. Aspect theo dõi một lời gọi greet từ bên ngoài

**`src/main/java/com/example/beanproxy/GreetingAspect.java`:**

```java
package com.example.beanproxy;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class GreetingAspect {

    @Around("execution(* com.example.beanproxy.GreetingService.greet(..))")
    public Object aroundGreeting(ProceedingJoinPoint joinPoint)
            throws Throwable {
        System.out.println("Advice: before greet");
        Object result = joinPoint.proceed();
        System.out.println("Advice: after greet");
        return result;
    }
}
```

`@Around` tạo một advice bao quanh lời gọi method được pointcut lựa chọn. Ví dụ không mở transaction hay dùng database; nó chỉ in hai dòng để minh chứng lời gọi có đi qua proxy hay không. `joinPoint.proceed()` thực sự chuyển tiếp lời gọi tới target; nếu bỏ nó, hành vi của method có thể bị thay đổi hoặc không thực thi.

### 6.4. BeanPostProcessor để quan sát callback

**`src/main/java/com/example/beanproxy/TraceBeanPostProcessor.java`:**

```java
package com.example.beanproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanPostProcessor;

public class TraceBeanPostProcessor implements BeanPostProcessor {

    private boolean interested(String beanName) {
        return "greetingService".equals(beanName);
    }

    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        if (interested(beanName)) {
            System.out.println("BPP: before initialization");
        }
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        if (interested(beanName)) {
            System.out.println(
                    "BPP: after initialization; proxy at callback = "
                    + AopUtils.isAopProxy(bean));
        }
        return bean;
    }
}
```

Processor này **không tự tạo proxy**; nó chỉ in trạng thái thấy được tại callback và trả lại `bean`. Vì nhiều post-processors có thể chạy ở thứ tự khác nhau, giá trị `AopUtils.isAopProxy(bean)` trong **callback của riêng processor này** có thể là `true` hoặc `false`. Không coi giá trị đó là kết luận cuối cùng.

### 6.5. Lớp khởi động và runner kiểm tra reference cuối

**`src/main/java/com/example/beanproxy/BeanProxyApplication.java`:**

```java
package com.example.beanproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@SpringBootApplication
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class BeanProxyApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BeanProxyApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // Đóng context sau khi runner đã in bằng chứng.
        }
    }

    @Bean
    public static BeanPostProcessor traceBeanPostProcessor() {
        return new TraceBeanPostProcessor();
    }

    @Bean
    ApplicationRunner verifyProxy(GreetingService service) {
        return args -> {
            System.out.println(
                    "Runner: AOP proxy = " + AopUtils.isAopProxy(service));
            System.out.println(
                    "Runner: CGLIB proxy = " + AopUtils.isCglibProxy(service));

            String result = service.greet("Lan");
            System.out.println("Runner: result = " + result);
        };
    }
}
```

Những lựa chọn quan trọng trong mã:

- `@EnableAspectJAutoProxy(proxyTargetClass = true)` chọn kiểu proxy theo subclass để ví dụ nhận `GreetingService` bằng **lớp cụ thể**. Spring Boot có cơ chế cấu hình AOP tự động, nhưng bài thực hành đặt rõ lựa chọn để tránh phụ thuộc mặc định của project.
- `@Bean public static BeanPostProcessor ...` làm rõ kiểu trả về là `BeanPostProcessor` và dùng **static** để Spring tạo processor sớm mà không buộc phải khởi tạo instance của lớp cấu hình trước thời điểm cần thiết.
- `ApplicationRunner` được gọi **sau khi context refresh thành công**; trong kịch bản không có vòng phụ thuộc, nó nhận reference do container cung cấp khi bean đã qua chuỗi post-processing.
- `AopUtils.isAopProxy(service)` xác nhận việc proxy theo AOP, còn `AopUtils.isCglibProxy(service)` xác nhận loại proxy trong bài thực hành.
- `try-with-resources` chỉ nhằm đóng context sau khi chương trình non-web demo hoàn thành; ứng dụng Web thật không nên tự đóng context ngay khi mới khởi động.

### 6.6. Chạy và quan sát

Nếu đã có Gradle Wrapper, trong thư mục project:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Trong các log chương trình, những dòng quan trọng có nội dung sau:

```text
Service: @PostConstruct
Service: self call = Xin chao noi-bo
BPP: after initialization; proxy at callback = <true-hoac-false>
Runner: AOP proxy = true
Runner: CGLIB proxy = true
Advice: before greet
Advice: after greet
Runner: result = Xin chao Lan
```

Đây là **phần log minh họa**, không phải toàn bộ stdout. `BPP: before initialization` cũng sẽ được in, nhưng **vị trí tương đối với `Service: @PostConstruct` không phải hợp đồng cố định**, bởi `@PostConstruct` bản thân được xử lý trong một BeanPostProcessor khác ở pha before. Log Spring Boot/Gradle có thể xuất hiện xen giữa các dòng.

Các quan hệ cần kiểm chứng là:

1. `@PostConstruct` của `GreetingService` đã hoàn thành trước khi callback after-initialization tương ứng được chạy.
2. `Runner: AOP proxy = true` và `Runner: CGLIB proxy = true` khi aspect được đăng ký thành công, vì runner nhận reference đã được container xử lý.
3. Lời gọi `greet("noi-bo")` **trong chính target** không in hai dòng `Advice`.
4. Lời gọi `service.greet("Lan")` **từ runner qua proxy** in `Advice: before greet` rồi `Advice: after greet`, sau đó trả về `Xin chao Lan`.

Không lấy vị trí của riêng dòng `BPP: before initialization` để khẳng định một thứ tự tuyệt đối với mọi `@PostConstruct` trong mọi project. Đó chính là rủi ro khi nhầm tên một callback với trạng thái toàn cục.

## 7. Vì sao @PostConstruct chưa phải thời điểm tham chiếu bean hoàn chỉnh?

Trong ví dụ, `@PostConstruct` chạy trong quá trình bean đích được khởi tạo. Với proxy AOP thông thường, wrapper cung cấp cho các caller bên ngoài xuất hiện **sau** các callback khởi tạo của target. Vì vậy:

```text
Đang tạo GreetingService (target)
        |
        v
@PostConstruct gọi trên target
        |      |
        |      +--> this.greet(...)   (gọi trực tiếp)
        |
        v
BeanPostProcessor sau khởi tạo
        |
        v
Có thể tạo wrapper/proxy
        |
        v
Caller lấy GreetingService từ context
        |
        +--> proxy.greet(...)         (được advice)
```

**Không nên** gọi một phương thức `@Transactional`, `@Async` hay `@Cacheable` từ `@PostConstruct` trên chính bean và mặc nhiên kỳ vọng advice sẽ có hiệu lực. Trong proxy-based AOP, lời gọi `this.method()` bỏ qua proxy. Ngoài ra, các annotation này chỉ hoạt động nếu ứng dụng có hạ tầng tương ứng: `@EnableAsync` cho xử lý bất đồng bộ bằng proxy, caching đã được bật với cache manager, hoặc transaction management đã cấu hình với transaction manager.

Khi cần chạy nghiệp vụ phụ thuộc advice **sau khi bean đã được công bố**, một cách đơn giản là chuyển phần việc vào **bean khác** nhận dependency qua constructor, rồi gọi method của service từ `ApplicationRunner` hoặc một entry point phù hợp. Không cần sử dụng `AopContext.currentProxy()` trong mã nghiệp vụ chỉ để né vòng đời.

### Ví dụ minh họa: tách lời gọi sang một bean khác

```java
@Service
public class PaymentService {
    @Transactional
    public void pay() {
        // Logic cần transaction (trong dự án đã cấu hình transaction).
    }
}

@Component
public class StartupPayment {
    private final PaymentService paymentService;

    public StartupPayment(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void afterReady() {
        paymentService.pay(); // Lời gọi đi qua reference tiêm từ container.
    }
}
```

Đây là đoạn **minh họa tích hợp**, chưa phải project hoàn chỉnh: cần import Spring và transaction API, cấu hình `PlatformTransactionManager` và dependency phù hợp. Ví dụ cho thấy **ranh giới bean** làm cho cuộc gọi có cơ hội đi qua proxy. `ApplicationReadyEvent` phù hợp nếu đây là việc sau khi các runner hoàn tất; nếu việc cần hoàn thành **trước khi Ready**, dùng `ApplicationRunner` thay cho listener này.

## 8. Hai kiểu proxy thường gặp: JDK và CGLIB

Trong Spring AOP dùng proxy, lựa chọn tùy vào cấu hình và khả năng của target:

| Đặc điểm | JDK dynamic proxy | CGLIB/class-based proxy |
|---|---|---|
| Cơ chế | Proxy triển khai interface | Proxy là lớp con runtime của target |
| Có thể tiêm theo interface? | Có | Có nếu target triển khai interface |
| Có thể tiêm trực tiếp theo lớp cụ thể? | Thường không: JDK proxy không là subclass của lớp target | Thường có, nếu lớp có thể được proxy |
| Hạn chế đáng chú ý | Chỉ những method được phơi ra qua proxy interface | Không thể subclass lớp `final`; không override method `final`/`private` |
| Kiểm tra runtime | `AopUtils.isJdkDynamicProxy(bean)` | `AopUtils.isCglibProxy(bean)` |

Có interface **không đồng nghĩa chắc chắn** là JDK proxy trong Spring Boot: cài đặt Spring Boot có thể chọn class-based proxy theo cấu hình mặc định hoặc theo `@EnableAspectJAutoProxy(proxyTargetClass = true)`. Nếu cần biết chính xác, kiểm tra **runtime reference** thay vì suy từ `getClass().getSimpleName()`.

Ở ví dụ phần 6, `proxyTargetClass = true` cố ý chọn class-based proxy, và `GreetingService` không `final`. Đó là lý do runner có thể dùng kiểu tham số `GreetingService` và kiểm chứng `isCglibProxy(...)`.

### Tránh so sánh lớp proxy với lớp đích bằng ==

```java
System.out.println(service.getClass() == GreetingService.class);
```

Ở class-based proxy, biểu thức này có thể là `false` vì lớp runtime là subclass được sinh. Điều đó **không có nghĩa bean sai kiểu**. Có thể kiểm tra:

```java
System.out.println(AopUtils.isAopProxy(service));
System.out.println(AopUtils.getTargetClass(service));
```

`getTargetClass` cho biết lớp target được nhận diện theo hạ tầng AOP khi áp dụng; còn `service.getClass()` là lớp của reference hiện tại (có thể là proxy). Không coi mọi bean đều có proxy hoặc mọi proxy đều thuộc Spring AOP; cần chọn API kiểm tra tương ứng.

## 9. Lời gọi nội bộ: vì sao self-invocation đi vòng qua proxy?

Giả sử trong cùng bean:

```java
public void outer() {
    inner();
}

@Transactional
public void inner() {
    // Logic nghiệp vụ
}
```

Nếu một caller bên ngoài gọi `proxy.outer()`, AOP có thể áp dụng advice cho `outer` nếu có rule phù hợp. Tuy nhiên, bên trong target, lời gọi `inner()` tương đương `this.inner()`; nó được gọi **trực tiếp trên target**, bỏ qua việc quay trở lại proxy. Vì vậy transaction advice chỉ đặt trên `inner` thường **không** chạy với self-invocation này.

Phân biệt:

```text
Gọi từ bean khác:
Client -> Proxy -> Advice(inner) -> Target.inner()      [đi qua proxy]

Gọi trong cùng target:
Client -> Proxy -> Target.outer() -> this.inner()        [bỏ qua advice(inner)]
```

Cách xử lý tốt về thiết kế là **tách method cần advice sang một bean khác**, để caller thật sự nhận reference từ container rồi gọi qua proxy. Có cách dùng self-injection hoặc `AopContext.currentProxy()`, nhưng chúng làm phụ thuộc vòng đời/phụ thuộc Spring AOP phức tạp hơn và không nên là lựa chọn mặc định.

Cũng cần phân biệt **Spring AOP proxy-based** với **AspectJ weaving trực tiếp trong bytecode**: cơ chế weaving không mang hạn chế self-invocation theo cùng cách. Đề bài này nói về vòng đời proxy trong Spring Boot thông thường, không tự giả định ứng dụng đang dùng bytecode weaving.

## 10. BeanPostProcessor được đăng ký khi nào và áp dụng cho những bean nào?

Trong một `ApplicationContext` tiêu chuẩn, Spring **phát hiện, tạo và đăng ký BeanPostProcessor đủ sớm** trước khi tạo các bean ứng dụng thông thường. Chỉ những bean được tạo **sau khi các processors thích hợp đã đăng ký** mới có cơ hội đi qua chuỗi đầy đủ.

Vì vậy một số bean hạ tầng được khởi tạo sớm có thể **không đủ điều kiện** nhận toàn bộ post-processing hoặc AOP auto-proxy. Bạn có thể gặp log:

```text
Bean 'someBean' of type [...] is not eligible for getting processed
by all BeanPostProcessors (for example: not eligible for auto-proxying)
```

Thông điệp này không có nghĩa chắc chắn mọi bean trong context đều sai. Nó báo một bean được tạo quá sớm để được mọi processor xử lý. Cần xác định bean nào, tại sao được tạo sớm và nó có thực sự cần được proxy hay không.

### Quy tắc khai báo một processor tự viết

Trong lớp `@Configuration`, nên viết:

```java
@Bean
public static BeanPostProcessor myProcessor() {
    return new MyProcessor();
}
```

Ở đây `MyProcessor` phải là một implementation thật của `BeanPostProcessor`. Khai báo **static** giúp Spring tạo processor mà không nhất thiết phải khởi tạo toàn bộ instance của lớp cấu hình trước thời điểm phù hợp. Đồng thời kiểu trả về phương thức phải thể hiện rõ BeanPostProcessor (bản thân implementation hoặc interface).

Không khai báo processor với kiểu trả về quá chung như `Object` rồi kỳ vọng container luôn phát hiện nó đúng thời điểm. Cũng nên hạn chế việc processor cần tiêm quá nhiều bean nghiệp vụ vào constructor, bởi điều đó có thể **kích hoạt tạo các bean khác quá sớm**, khiến chúng không được áp dụng AOP.

### Thứ tự processor

Khi nhiều processor tham gia, có thể dùng `Ordered`, `PriorityOrdered` hoặc cơ chế sắp xếp phù hợp do Spring hỗ trợ. Tuy nhiên:

- Thứ tự cụ thể tùy cách processor được đăng ký (tự động hay programmatic).
- Processor đăng ký programmatic qua `BeanFactory.addBeanPostProcessor(...)` có quy tắc thứ tự khác với tự động phát hiện từ bean.
- Thứ tự của các callback **before** không nhất thiết phản chiếu một cách đơn giản thứ tự của một thao tác nghiệp vụ khác.
- Thay thứ tự processor có thể làm thay đổi thời điểm wrapper/proxy được thấy bởi processor khác.

Nếu cần kiểm tra một xử lý, hãy quan sát **tham chiếu do container trả về sau khi bean khởi tạo hoàn chỉnh**, và không chỉ dựa trên một log trung gian của custom processor.

## 11. Tham chiếu sớm (early reference) và vòng phụ thuộc

Trong trường hợp một số bean singleton phụ thuộc vòng tròn, Spring có cơ chế nội bộ có thể cung cấp **tham chiếu sớm** cho bean đang được tạo. Các triển khai chuyên biệt của `SmartInstantiationAwareBeanPostProcessor` có khả năng tham gia xử lý qua `getEarlyBeanReference(...)`, nhằm hỗ trợ những trường hợp cần giữ sự nhất quán giữa reference sớm và proxy cuối.

Đây là một **ngoại lệ hạ tầng quan trọng** đối với sơ đồ đơn giản “chỉ sau init mới thấy proxy”. Không nên từ ngoại lệ này suy ra rằng mọi bean, mọi loại proxy hoặc mọi vòng phụ thuộc đều được Spring hỗ trợ an toàn.

Spring Boot 3.3 mặc định **không cho phép vòng tham chiếu bean** (`spring.main.allow-circular-references=false`). Ví dụ vòng constructor injection thường sẽ thất bại, thay vì có một reference sớm để sử dụng:

```text
ServiceA constructor cần ServiceB
ServiceB constructor cần ServiceA
              |
         Circular dependency
              |
    Không thể xây đủ hai đối tượng
```

Đừng bật `spring.main.allow-circular-references=true` chỉ để né việc thiết kế phụ thuộc sai. Cách phù hợp là sửa quan hệ trách nhiệm hoặc tách phần cộng tác dùng chung, để đường phụ thuộc rõ ràng và không vòng.

Nếu dùng cơ chế reference sớm để điều tra một lỗi hiện có, cần phân biệt:

- **Raw target:** instance chưa hoàn tất các bước khởi tạo.
- **Early reference:** đối tượng được cung cấp trước khi tạo bean xong, có thể đã được wrap tùy processor.
- **Final exposed reference:** reference của container sau khi chuỗi khởi tạo/post-processing hoàn tất.

Không lưu raw target từ callback trung gian vào một registry toàn cục rồi đưa cho caller khác, vì bạn có thể làm hai caller cùng nhìn thấy các đối tượng khác nhau của cùng bean.

## 12. Kiểm tra bean hoàn chỉnh tại thời điểm phù hợp

Với ứng dụng bình thường, muốn xác minh rằng service đã được tạo và proxy đang hoạt động, những điểm quan sát thường dễ hiểu hơn là:

- **Constructor của một bean khách hàng**: nó nhận dependency do container giải quyết; với dependency không vòng, reference thông thường đã qua xử lý của bean được tiêm, nhưng **constructor của chính bean đang khởi tạo** không có nghĩa toàn hệ thống đã sẵn sàng.
- **ApplicationRunner/CommandLineRunner**: được gọi sau khi context được refresh, phù hợp để gọi service và đo hành vi trước mốc Ready.
- **ApplicationStartedEvent**: sau refresh, trước runner; phù hợp cho quan sát sau khi context sẵn sàng mà không gắn vào initialization của một bean cụ thể.
- **ApplicationReadyEvent**: sau runner; phù hợp cho việc quan sát/truyền thông tin ứng dụng đã hoàn tất chuỗi startup, không nên dùng để sửa bean definition đã được xử lý.
- **ApplicationContext.getBean(...)**: lấy reference được Spring quản lý khi context đã chạy; nếu bean có AOP proxy, đây thông thường là proxy đã công bố.

Điểm quan trọng là **“bean hoàn chỉnh” và “toàn ứng dụng ready” không cùng một mốc**. Bean đơn lẻ có thể được tạo hoàn tất rất sớm, còn application phải tiếp tục khởi tạo các bean khác, khởi chạy server và hoàn tất runner. Trái lại, một `@Lazy` bean có thể chưa được tạo dù ứng dụng đã Ready; khi có yêu cầu, nó mới đi qua vòng đời khởi tạo.

Đừng dùng `Thread.sleep(...)` trong `@PostConstruct` để “chờ proxy xuất hiện”. Nó không khiến lời gọi `this.method()` đi qua proxy, lại làm chậm startup và dễ che giấu vấn đề thứ tự.

## 13. Phân biệt với proxy @Transactional, @Async và @Cacheable

Những tính năng hay dựa vào proxy có cùng quy tắc về **đường đi của lời gọi**, nhưng cơ chế cần kích hoạt là khác nhau:

| Trường hợp | Hạ tầng cần có | Vì sao dễ hiểu sai |
|---|---|---|
| `@Transactional` | Transaction management và transaction manager phù hợp | Tự gọi một method `@Transactional` trên cùng target không đi qua proxy transaction. |
| `@Async` | Bật async processing, ví dụ `@EnableAsync`, cùng executor phù hợp | Self-invocation có thể chạy đồng bộ vì bỏ qua advice. |
| `@Cacheable` | `@EnableCaching` và cache manager phù hợp | Self-invocation có thể không truy cập bộ nhớ đệm do bypass proxy. |
| `@Aspect` và `@Around` | Hạ tầng Spring AOP/AspectJ annotations như trong ví dụ | Lời gọi qua proxy được advice; gọi trực tiếp trên target không được cùng xử lý. |

Một method có annotation **chưa đủ** để bảo đảm có proxy. Nếu dependency/hạ tầng không có, điều kiện không hợp lệ hoặc method không thể bị intercept, hiệu ứng có thể không xuất hiện. Với class-based proxy, `final` class và `final/private` method là những giới hạn quan trọng.

Ví dụ `@Transactional` không tự tạo một database hay transaction manager. Nếu muốn chứng minh transaction thật đang mở, phải dùng một project đã cấu hình transaction management hợp lệ và kiểm tra trạng thái transaction/rollback, không chỉ nhìn thấy annotation.

## 14. Những lỗi chẩn đoán thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và sửa |
|---|---|---|
| BPP thấy `proxy=false` nhưng runner thấy `proxy=true` | Một auto-proxy creator chạy sau custom BPP trong chuỗi after-init | Kiểm tra reference trong runner/context sau khi toàn bộ chuỗi processor hoàn tất. |
| `@PostConstruct` gọi method `@Transactional` nhưng không thấy transaction | Self invocation trên target xảy ra trước khi caller có proxy | Chuyển lời gọi sang bean khác qua dependency đã tiêm và chọn hook sau khởi tạo phù hợp. |
| Tự tạo `new Service()` nên `@Autowired`/AOP không hoạt động | Đối tượng không do Spring quản lý | Để container tạo bean, tiêm dependency bằng constructor hoặc `getBean` từ context khi phù hợp. |
| `ClassCastException` khi ép proxy sang lớp cụ thể | JDK proxy chỉ triển khai interface, không phải subclass của target | Tiêm theo interface hoặc cấu hình class-based proxy nếu thiết kế yêu cầu. |
| `final` class/method không được advice theo CGLIB | Proxy subclass không thể override | Sửa thiết kế cho phép proxy, ưu tiên public method phù hợp, hoặc cơ chế khác khi thật sự cần. |
| Không thấy advice khi gọi từ cùng bean | `this.method()` bỏ qua proxy | Tách call sang bean cộng tác; không dùng self-call làm phép thử proxy. |
| Có log “not eligible for getting processed by all BeanPostProcessors” | Bean khởi tạo quá sớm do processor/hạ tầng | Giảm dependency sớm; dùng `@Bean static` cho processor; kiểm tra bean bị nêu trong log. |
| BPP gây vòng phụ thuộc khi inject service | Processor được khởi tạo trước service và vô tình buộc service tạo sớm | Giữ processor nhẹ, tránh phụ thuộc trực tiếp vào bean nghiệp vụ. |
| BPP thay instance nhưng trả `null` | Vi phạm ý định chuỗi xử lý; `null` có ý nghĩa đặc biệt và có thể dừng chuỗi | Khi chỉ quan sát, luôn trả `bean`; khi wrap, trả đúng object mới tương thích. |
| Muốn sửa bean definition trong BPP | BPP đang xử lý instance, có thể quá muộn để sửa metadata tạo bean | Sử dụng `BeanFactoryPostProcessor`/registry post-processor trước instantiation. |
| Dựa vào thứ tự mọi log before-init/@PostConstruct | `@PostConstruct` cũng do processor chạy trong pha before | Đừng giả định thứ tự giữa các processor khi chưa cấu hình và kiểm chứng rõ. |
| Gọi service từ listener bootstrap quá sớm | Context/bean có thể chưa tồn tại | Chọn runner hoặc sự kiện sau refresh nếu cần dependency hoàn chỉnh. |

### Quy trình điều tra có căn cứ

1. Xác định **bean nào** và **method nào** cần advice; biết chính xác annotation/pointcut và hạ tầng tương ứng.
2. Xác định **reference được gọi từ đâu**: từ một bean khác, từ `this`, từ `new` hay từ `ApplicationContext.getBean`.
3. Ở một mốc muộn phù hợp, kiểm tra `AopUtils.isAopProxy(reference)`, `isJdkDynamicProxy`/`isCglibProxy` và target class; đừng kết luận chỉ từ class name.
4. Kiểm tra log bean khởi tạo sớm và kiểu đăng ký `BeanPostProcessor`; tìm nguyên nhân nếu cần proxy mà bean bị loại khỏi xử lý.
5. Kiểm tra phương thức có thể được intercept không: visibility, `final`, interface/proxy type, pointcut và điều kiện feature.
6. Tạo một lời gọi **từ bean khác** đến method đó, quan sát behavior của advice; không dùng lời gọi từ `@PostConstruct` trên cùng target làm bằng chứng duy nhất.

## 15. Bài thực hành có thể kiểm chứng

Dùng project `bean-proxy-demo` ở phần 6. Thực hiện từng thay đổi, quay về trạng thái trước thử nghiệm khi xong:

**Thử nghiệm A — đối tượng trước và sau:** chạy nguyên mẫu, quan sát `BPP: after initialization; proxy at callback = ...` có thể thay đổi theo thứ tự BPP, nhưng `Runner: AOP proxy = true` với cấu hình ví dụ. Giải thích vì sao **một mốc trung gian** không bằng reference cuối cùng.

**Thử nghiệm B — self invocation:** giữ `GreetingService.initialize()` gọi `greet("noi-bo")`. Không có log `Advice` cho lời gọi đó. So với `service.greet("Lan")` trong runner, nơi log advice xuất hiện.

**Thử nghiệm C — không có advice:** tạm bỏ `@Component` khỏi `GreetingAspect` hoặc bỏ aspect bean khỏi project, chạy lại. `GreetingService` vẫn là một bean Spring, nhưng có thể không còn AOP proxy vì không có advice áp dụng. Kiểm tra `AopUtils.isAopProxy` thực tế.

**Thử nghiệm D — class proxy:** thêm `final` vào `GreetingService` (sau đó khôi phục) rồi thử chạy khi vẫn yêu cầu subclass proxy. Quan sát lỗi hoặc việc không thể proxy theo cấu hình, từ đó hiểu vì sao CGLIB bị hạn chế với `final` class.

**Thử nghiệm E — processor trả lại bean:** giữ nguyên `return bean` ở cả hai callbacks của `TraceBeanPostProcessor`. Thay đổi log để chỉ ghi `beanName` hoặc class hiện tại; không tự thay instance nếu chỉ đo. Thử quan sát một bean khác bằng cách điều chỉnh điều kiện `interested` và giải thích vì sao processor có thể chạy trên nhiều bean trong context.

**Thử nghiệm F — thời điểm callback:** thêm log từ `@PostConstruct`, BPP và `ApplicationRunner`. Đánh dấu các quan hệ **chắc chắn** (after-init trước runner) và các quan hệ **phụ thuộc thứ tự BPP** (custom before-init so với `@PostConstruct`). Không biến một thứ tự log của một lần chạy thành hợp đồng của mọi ứng dụng.

Câu hỏi tự đánh giá: **(1)** Tại sao `@PostConstruct` trên target không phải bằng chứng đã nhận proxy hoàn chỉnh? **(2)** Tại sao `BeanFactoryPostProcessor` khác `BeanPostProcessor`? **(3)** Vì sao service do Spring tiêm có thể là proxy dù code chỉ khai báo một lớp `@Service`? **(4)** Tại sao `this.method()` tránh được advice? **(5)** Khi nào `ApplicationRunner` phù hợp để kiểm chứng proxy? Trả lời được năm câu này là đã nắm mối quan hệ giữa khởi tạo bean, hậu xử lý và tham chiếu mà caller sử dụng.

## Tài liệu chính thức

- Spring Framework 6.1, Container Extension Points (`BeanPostProcessor` / `BeanFactoryPostProcessor`): https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-extension.html
- Spring Framework 6.1, `BeanPostProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html
- Spring Framework, `@PostConstruct` / `@PreDestroy`: https://docs.spring.io/spring-framework/reference/6.1/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework 6.1, Spring AOP Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/6.1/core/aop/proxying.html
- Spring Boot 3.3, Spring Application Events and Runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Điều cần nhớ:** `BeanPostProcessor` là điểm mở rộng làm việc trên **instance**, có thể tạo proxy hoặc trả một reference khác sau khởi tạo. `@PostConstruct` chạy trong quá trình khởi tạo của target và **không bảo đảm các lời gọi nội bộ đi qua proxy**. Khi cần quan sát bean đã được Spring công bố, dùng tham chiếu do context/constructor injection cung cấp tại giai đoạn phù hợp và kiểm tra đúng behavior của advice, đồng thời hiểu các ngoại lệ liên quan đến bean tạo sớm và phụ thuộc vòng.