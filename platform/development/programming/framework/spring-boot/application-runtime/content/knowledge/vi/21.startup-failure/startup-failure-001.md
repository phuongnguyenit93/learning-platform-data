# Phân loại lỗi khởi động Spring Boot: trước khi có context, trong refresh và trong runner

## 1. Tại sao phải phân loại lỗi theo giai đoạn?

Khi một ứng dụng Spring Boot không khởi động thành công, dòng log cuối thường có chữ **APPLICATION FAILED TO START**, **BeanCreationException**, **IllegalStateException** hoặc một thông báo từ thư viện bên ngoài. Nếu chỉ nhìn tên exception rồi sửa theo cảm tính, rất dễ xử lý sai nguyên nhân.

Một câu hỏi chẩn đoán hữu ích hơn là: **Lúc lỗi xảy ra, SpringApplication đã tiến tới mốc lifecycle nào?**

Trong Spring Boot 3.5, có ba nhóm chính cần phân biệt:

1. **Trước khi có ApplicationContext:** Boot đang chuẩn bị Environment, ConfigData hoặc chạy những hook sớm. Chưa có context/bean factory sẵn sàng để lấy các business beans.
2. **Trong ApplicationContext.refresh():** context đã được tạo và nạp các nguồn cấu hình, nhưng container đang phân tích/đăng ký BeanDefinitions, tạo singleton beans, chạy lifecycle callbacks hoặc khởi động embedded server.
3. **Trong ApplicationRunner/CommandLineRunner:** context **đã refresh thành công** và Spring Boot đã phát **ApplicationStartedEvent**, nhưng công việc cuối của startup thất bại trước **ApplicationReadyEvent**.

**Không đồng nhất ba nhóm này.** Cùng là "startup failed", nhưng khả năng truy cập Environment, bean, DataSource, web server, failure analyzers và chiến lược sửa lỗi khác nhau.

### Ba câu hỏi nhanh

- **Context có tồn tại chưa?** Nếu chưa, không thể dùng bean listener, repository hoặc @Autowired để xử lý.
- **refresh đã hoàn tất chưa?** Nếu chưa, đừng cho rằng @Bean, @PostConstruct, post-processors và những singleton cần thiết đã sẵn sàng.
- **Runners đã hoàn tất chưa?** Nếu chưa, app có thể đã in log "Started" nhưng vẫn chưa được coi là ready.

Bài này dùng **Spring Boot 3.5.x và Java 17+**. Các tên event/API được so sánh theo tài liệu Spring Boot 3.5, không dựa vào các tên sự kiện cũ ở các phiên bản Boot 1.x.

## 2. Bản đồ các mốc sự kiện

~~~text
main(String[] args)
      |
      v
SpringApplication.run(args)
      |
      +--> ApplicationStartingEvent
      |        Chưa có Environment / ApplicationContext
      |
      +--> Chuẩn bị Environment, ConfigData, active profiles...
      |        ApplicationEnvironmentPreparedEvent
      |        Environment sẵn, context CHƯA được tạo
      |
      +--> Tạo ApplicationContext, chạy initializers
      |        ApplicationContextInitializedEvent
      |        Context đã được tạo, chưa load primary sources
      |
      +--> Load nguồn BeanDefinition ban đầu
      |        ApplicationPreparedEvent
      |        Context có, CHƯA refresh
      |
      +--> ApplicationContext.refresh()
      |        - configuration class processing
      |        - bean factory/bean post processors
      |        - @Configuration, @Bean, auto-configuration
      |        - khởi tạo singleton non-lazy, @PostConstruct
      |        - embedded web server nếu là web app
      |        ContextRefreshedEvent
      |
      +--> ApplicationStartedEvent
      |        Context đã refresh, runner CHƯA được gọi
      |        LivenessState.CORRECT
      |
      +--> ApplicationRunner / CommandLineRunner
      |        Seed, kiểm tra điều kiện, warm-up...
      |
      +--> ApplicationReadyEvent
      |        Runners đã hoàn tất bình thường
      |        ReadinessState.ACCEPTING_TRAFFIC
      |
      v
SpringApplication.run trả về
~~~

**ApplicationFailedEvent** có thể được phát khi một exception làm startup thất bại. Nó **không phải** một mốc chỉ xảy ra sau ApplicationReadyEvent: failure event có thể xuất hiện ở những giai đoạn khác nhau, tùy nơi lỗi phát sinh.

**ContextRefreshedEvent** thuộc Spring Framework, còn các event tên **Application...Event** trong sơ đồ thuộc Spring Boot. Với một web application, **WebServerInitializedEvent** cũng có thể được phát trong khoảng giữa Prepared và Started.

### Bảng phân loại cốt lõi

| Dấu hiệu | Trước context | Trong refresh | Trong runner |
| --- | --- | --- | --- |
| **Environment** | Có thể đã được chuẩn bị; chưa chắc nếu lỗi sớm hơn | Có | Có |
| **ApplicationContext** | Chưa tồn tại | Đã tồn tại nhưng refresh chưa thành công | Đã refresh thành công |
| **ApplicationPreparedEvent** | Chưa | Thường đã, nếu lỗi đúng trong refresh | Đã |
| **ContextRefreshedEvent** | Chưa | Thường chưa với refresh thất bại | Đã |
| **ApplicationStartedEvent** | Chưa | Chưa | **Đã** |
| **ApplicationReadyEvent** | Chưa | Chưa | **Không** nếu runner ném lỗi |
| **Business beans** | Chưa thể trông cậy | Có thể mới tạo một phần | Thông thường đã sẵn sau refresh |
| **Hướng xử lý chính** | ConfigData, JVM/classpath, early listeners | Bean definitions, dependency injection, init, web server | Logic runner, dependency runtime, transaction, timeout |

Từ **"thường"** rất quan trọng: exception có thể xảy ra ở **giai đoạn tạo context nhưng trước refresh**, không thuộc đúng ba ô đơn giản phía trên. Mục 7 giải thích trường hợp biên này và cách tránh kết luận sai chỉ từ một event.

## 3. Nhóm A — Lỗi trước khi có ApplicationContext

### 3.1. Context chưa được tạo nghĩa là gì?

Spring Boot phải khởi tạo nhiều thành phần **trước khi** new một ApplicationContext:

- Cấu hình SpringApplication và application arguments.
- Chuẩn bị Environment.
- Tìm và nạp **application.properties/application.yml**, các ConfigData imports và profile-specific configuration.
- Chạy các **EnvironmentPostProcessor** cùng listener của giai đoạn Environment.
- Xác định web application type và các lựa chọn startup đủ sớm.

**ApplicationEnvironmentPreparedEvent** được phát khi Environment đã chuẩn bị tới mức có thể xem/chỉnh nhưng **trước khi context được tạo**. Vì vậy một listener nhận event này không thể làm:

~~~java
context.getBean(MyService.class);
~~~

Đây là **mảnh phản ví dụ**: không có biến context và không có business bean được Spring khởi tạo tại thời điểm ấy. Nếu cần đọc cấu hình, dùng **event.getEnvironment()** thay vì ép tạo bean.

### 3.2. Những lỗi thường gặp

| Hiện tượng | Nguồn lỗi có thể | Điều cần kiểm tra |
| --- | --- | --- |
| Không nạp được ConfigData import bắt buộc | File/config location hoặc nguồn config không tồn tại | spring.config.import, location, optional: và quyền đọc |
| YAML sai cấu trúc | Cú pháp YAML, thụt lề, ký tự đặc biệt | File và số dòng parser báo lỗi |
| Active profile không đúng | CLI/env/profile group hoặc config precedence | spring.profiles.active, biến môi trường và profile-specific file |
| EnvironmentPostProcessor ném exception | Logic tự viết, tài nguyên bị thiếu | Thứ tự postprocessor và stack trace root cause |
| Failure khi tạo logging/config bootstrap | Classpath, version lệch, config sớm | Dependency tree, JVM args, logging configuration |
| ClassNotFound/NoClassDefFoundError rất sớm | Dependency thiếu, incompatible bytecode | Version JVM và libraries trên runtime classpath |
| Listener sớm đọc bean | Cố truy cập @Autowired/getBean khi context chưa tồn tại | Đổi extension point và dùng Environment API |

**Không phải mọi lỗi về property đều thuộc nhóm trước context.** Ví dụ một giá trị URL định dạng sai có thể được nạp vào Environment bình thường, rồi chỉ báo lỗi khi bind sang **@ConfigurationProperties** trong refresh. Luôn căn theo **lúc lỗi thực sự được ném**, không chỉ vì tên class liên quan cấu hình.

### 3.3. Chẩn đoán khi chưa có bean

Các bước có giá trị:

1. Kiểm tra **Java runtime/version, classpath và lệnh khởi chạy thực tế**.
2. Đọc exception đầu tiên có ý nghĩa và **Caused by** sâu nhất, không chỉ dòng top-level cuối.
3. Kiểm tra nơi config được lấy: filesystem, classpath, environment variables, command-line, config import.
4. Với ConfigData errors, xác nhận **đường dẫn, quyền truy cập, active profiles** và thứ tự property sources.
5. Với EnvironmentPostProcessor, kiểm tra class đăng ký và dependencies của chính nó, không dùng DI business beans.
6. Nếu cần listener ghi dấu sớm, đăng ký từ **SpringApplication.addListeners(...)** hoặc cơ chế early registration thích hợp, không đợi @Bean trong context.

**Một giới hạn:** nếu lỗi xảy ra **trước khi SpringApplication.run() được gọi** (ví dụ main class static initializer lỗi, JVM không load được class, lệnh java sai, ClassNotFoundException trước khi vào Boot), Boot chưa có cơ hội điều phối ApplicationFailedEvent. Đó là lỗi khởi chạy **ngoài** SpringApplication, dù biểu hiện với người vận hành vẫn là "app không start".

## 4. Nhóm B — Lỗi trong ApplicationContext.refresh()

### 4.1. Refresh làm gì?

Khi SpringApplication đã tạo ApplicationContext, chạy initializers, nạp primary sources và phát **ApplicationPreparedEvent**, context bước vào **refresh()**. Trong giai đoạn này Spring:

- Chuẩn bị BeanFactory và chạy các **BeanDefinitionRegistryPostProcessor**.
- Phân tích **@Configuration**, **@ComponentScan**, **@Import**, **@Bean** và những auto-configurations thích hợp.
- Thực thi **BeanFactoryPostProcessor** để điều chỉnh metadata.
- Đăng ký **BeanPostProcessor** (ví dụ hỗ trợ annotation injection và AOP proxies).
- Khởi tạo nhiều singleton non-lazy.
- Thực hiện dependency injection, validation, initialization callbacks và **@PostConstruct**.
- Với web application, tạo/khởi động embedded web server tại các mốc liên quan của refresh.
- Khi refresh thành công, phát **ContextRefreshedEvent**.

**Một BeanDefinition được nạp không có nghĩa bean instance đã tồn tại.** Một @Bean method có thể chưa được gọi tại ApplicationPreparedEvent và chỉ bị thực thi trong refresh.

### 4.2. Các dạng lỗi phổ biến

| Exception/dấu hiệu | Khả năng nguyên nhân | Cách tiếp cận |
| --- | --- | --- |
| **BeanCreationException** | @Bean factory method, constructor hoặc init method ném lỗi | Tìm tên bean, method tạo và root cause |
| **UnsatisfiedDependencyException** | Dependency bắt buộc không có hoặc không thể tạo | Kiểm tra constructor parameters, component scan, profiles |
| **NoSuchBeanDefinitionException** | Không đăng ký bean type/name cần thiết | Kiểm tra starter, @Component/@Bean, @Conditional |
| **NoUniqueBeanDefinitionException** | Có nhiều candidates cho một điểm injection | Dùng @Qualifier/@Primary hoặc thiết kế lại |
| **BeanCurrentlyInCreationException** | Circular dependency không được giải quyết | Gỡ vòng phụ thuộc; không chỉ bật lại circular refs |
| **BeanDefinitionStoreException** | Configuration metadata bị lỗi | Kiểm tra config source/scan, class metadata |
| **BindException / validation errors** | @ConfigurationProperties không bind hợp lệ | Kiểm tra property names, types, @Validated và constraints |
| **PortInUseException** | Embedded server không bind được port | Kiểm tra process chiếm port, server.port và deployment |
| **NoSuchMethodError/LinkageError** | Libraries không tương thích | Xem dependency graph/BOM và version runtime |
| Lỗi trong **@PostConstruct** | Init callback dùng DB/API quá sớm hoặc config sai | Chuyển tác vụ dài sang runner khi phù hợp |

Các tên exception ở bảng là **những ví dụ thường gặp**, không phải một phép ánh xạ một-một giữa exception class và giai đoạn. Chẳng hạn cùng một **IllegalStateException** có thể được ném ở refresh hoặc runner tùy code. **Stack trace và sự kiện lifecycle** mới giúp phân biệt.

### 4.3. Dấu hiệu xác nhận refresh chưa thành công

- Có **ApplicationPreparedEvent** nhưng chưa thấy **ApplicationStartedEvent**.
- Stack trace dẫn vào **AbstractApplicationContext.refresh**, BeanFactory, configuration parser, constructor hoặc @Bean factory method.
- Có tên bean cụ thể trong **BeanCreationException**.
- Với web app, có log embedded server khởi tạo nhưng fail khi bind/khởi động.
- **ApplicationFailedEvent** có thể được phát với context đã được tạo; dù vậy context có thể đang bị đóng trong quá trình xử lý lỗi.

**Không suy ra rằng chỉ vì log ghi "Tomcat initialized" thì refresh đã hoàn thành.** Web server có thể khởi tạo một phần rồi lỗi. Mốc **ApplicationStartedEvent** rõ nghĩa hơn để biết SpringApplication đã vượt qua refresh thành công.

### 4.4. Lazy initialization thay đổi thời điểm lỗi

Nếu bật:

~~~properties
spring.main.lazy-initialization=true
~~~

nhiều beans được tạo muộn khi có nhu cầu. Một dependency hoặc factory method sai có thể không gây lỗi trong startup; lỗi chỉ xuất hiện ở request đầu hoặc khi một runner chủ động gọi getBean.

Vì vậy **không coi "startup thành công" là tất cả beans đều đã được kiểm chứng**. Khi debug, kiểm tra phạm vi lazy beans và thử gọi đường nghiệp vụ thật. Tuy nhiên không nên tắt lazy initialization tùy tiện trong production chỉ để cưỡng bức init mọi tài nguyên quá sớm.

## 5. Nhóm C — Lỗi trong ApplicationRunner hoặc CommandLineRunner

### 5.1. Runner chạy lúc nào?

Spring Boot gọi các **ApplicationRunner** và **CommandLineRunner** sau khi ApplicationContext refresh thành công, sau **ApplicationStartedEvent**, và trước **ApplicationReadyEvent**.

~~~text
ContextRefreshedEvent
       |
       v
ApplicationStartedEvent
       |
       v
Runner bắt đầu
       |
       +--> thành công --> Runner kế tiếp (nếu có)
       |                        |
       |                        v
       |                 ApplicationReadyEvent
       |
       +--> ném lỗi --> ApplicationFailedEvent
                        Không phát ready bình thường
~~~

Một hệ quả rất dễ bị bỏ qua:

**Log "Started ... in X seconds" hoặc ApplicationStartedEvent không có nghĩa ứng dụng đã ready.** Boot còn phải chạy runners trước khi công bố readiness.

Các tác vụ hay nằm trong runner:

- Khởi tạo dữ liệu mặc định.
- Warm-up cache.
- Kiểm tra cấu hình quan trọng hoặc kết nối tới hệ thống ngoài.
- Nạp index/mapping cần thiết trước khi phục vụ.
- Thực hiện thao tác startup ngắn có timeout và chính sách lỗi rõ ràng.

### 5.2. Lỗi thường gặp

| Lỗi | Vì sao thường chỉ xuất hiện trong runner? | Cách xử lý |
| --- | --- | --- |
| DB/API ngoài tạm thời không sẵn sàng | Runner là nơi thực hiện kết nối/validation thật | Timeout, bounded retry/backoff, policy fail vs degraded |
| Seed data gặp duplicate key | Startup/redeploy hoặc nhiều replicas chạy cùng logic | Unique constraint, insert-if-absent, idempotency |
| Runner truy cập bảng chưa migrate | Migration thứ tự sai hoặc schema drift | Đảm bảo migration trước runner |
| Cache warm-up vượt deadline | Truy vấn lớn, mạng chậm, dữ liệu không hợp lệ | Batching, bounded timeout, chính sách required/best effort |
| Exception do logic nghiệp vụ | Null/IllegalState ở code runner | Kiểm tra root cause và input |
| Runner trả về sớm khi Future vẫn đang chạy | Boot chỉ đợi lời gọi run() hoàn tất | Await task cần thiết và báo lỗi rõ ràng |
| Multi-runner ordering sai | Runner B giả định A đã chạy trước | @Order/Ordered hoặc một coordinator rõ ràng |
| Lỗi transaction | Transaction boundary hoặc retry không idempotent | Tách service @Transactional, kiểm tra commit/rollback |

### 5.3. Khi runner ném lỗi, context có phải đã refresh thành công?

**Có, trong startup bình thường của Spring Boot.** Runner được gọi **sau** ApplicationStartedEvent, nghĩa là refresh đã xong. Một exception trong runner khiến **SpringApplication.run(...) thất bại** và kích hoạt xử lý cleanup/đóng context của Boot, nên không thể tiếp tục coi instance sẵn sàng.

Một controller trong web app **có thể đã có port mở** trước thời điểm runner thất bại. Không dùng việc port đang LISTEN để kết luận service ready. Dùng readiness probe hợp lý để tránh route traffic khi runner bắt buộc chưa hoàn thành.

### 5.4. Không làm giả thành công bằng catch-all

Mẫu nguy hiểm:

~~~java
@Override
public void run(ApplicationArguments args) {
    try {
        mandatorySeed();
    } catch (Exception ignored) {
        // Sai nếu dữ liệu này là điều kiện bắt buộc.
    }
}
~~~

Đây là **mảnh code phản ví dụ**, chưa định nghĩa mandatorySeed. Nó có thể khiến Boot phát **ApplicationReadyEvent** dù seed đã thất bại.

Cách xử lý phụ thuộc chính sách:

- **Required startup task:** retry có giới hạn nếu lỗi transient, rồi ném exception và để startup fail nếu vẫn không đáp ứng.
- **Best-effort optimization:** log rõ, đo metric và cho phép fallback, nhưng không đưa dữ liệu sai vào hệ thống.
- **Asynchronous task:** chỉ return trước khi hoàn tất nếu readiness policy có cơ chế kiểm soát riêng; Boot không tự đợi tất cả CompletableFuture mà runner tạo.

**@Transactional** trong runner không bảo đảm side effect ngoài DB rollback cùng transaction. Với email, messaging hoặc API ngoài, dùng idempotency key, outbox/durable job state theo yêu cầu.

## 6. ApplicationFailedEvent là gì và giới hạn của nó?

**ApplicationFailedEvent** là sự kiện Spring Boot phát khi startup thất bại. Nó có:

- **getException()**: Throwable gây lỗi startup.
- **getApplicationContext()**: context đang được tạo/đang khởi động, **có thể null** nếu lỗi xảy ra trước khi context tồn tại.
- Các thông tin SpringApplication và raw arguments từ superclass.

Ví dụ mảnh code bên trong một listener:

~~~java
if (event instanceof ApplicationFailedEvent failed) {
    Throwable failure = failed.getException();
    boolean contextWasCreated =
            failed.getApplicationContext() != null;

    System.err.println(
            "contextPresent=" + contextWasCreated);
    System.err.println(
            "exceptionType=" + failure.getClass().getName());
}
~~~

Đây là **mảnh listener**, cần biến event và imports tương ứng. Đừng gọi **failed.getApplicationContext().getBean(...)** khi context có thể null, chưa refresh hoặc đang bị đóng.

### Đăng ký listener đủ sớm

Nếu listener chỉ tồn tại dưới dạng một **@Bean** hay **@Component**, nó có thể chưa được tạo khi lỗi trước context/refresh xảy ra. Để quan sát **ApplicationEnvironmentPreparedEvent** và lỗi rất sớm, đăng ký qua **SpringApplication.addListeners(...)** trước khi gọi run.

Đừng dùng @EventListener trong một business bean rồi kết luận event không phát chỉ vì bean chưa tồn tại. **Thời điểm listener được đăng ký** quyết định nó có cơ hội nhận event sớm hay không.

### ApplicationFailedEvent không phải cơ chế catch-all của toàn JVM

Nếu JVM không load được main class, class initializer chết trước khi SpringApplication.run bắt đầu, hoặc process bị SIGKILL, Boot có thể **không phát ApplicationFailedEvent**. Một số lỗi rất sớm trong khởi tạo SpringApplication/listeners cũng không đi qua cơ chế failure handling thông thường. Phải xem đây là tín hiệu chẩn đoán **khi Boot đã tham gia điều phối startup**, không phải nhật ký vạn năng.

### FailureAnalyzer và event listener khác nhau

**FailureAnalyzer** phân tích Throwable để tạo **Description** và **Action** có ích cho vận hành. Spring Boot có nhiều built-in analyzers, chẳng hạn lỗi port đã dùng hoặc các vấn đề cấu hình phổ biến.

**ApplicationFailedEvent listener** nhận một sự kiện để quan sát/ghi log; nó không tự biến Throwable thành báo cáo có nguyên nhân và hành động. Một analyzer có thể không nhận ra lỗi custom của bạn; khi ấy log stack trace thường cần thiết.

Không khuyên dùng listener để ném exception mới khi đang xử lý failure event vì có thể làm che mất lỗi ban đầu. Khi log, không in secrets từ Environment hoặc stack trace chứa credentials.

## 7. Vùng ranh giới: context đã tạo nhưng chưa refresh

Ba nhóm của bài là **trục phân loại chính**, nhưng Spring Boot còn khoảng giữa **trước context** và **refresh**:

~~~text
ApplicationEnvironmentPreparedEvent
    |
    +--> SpringApplication tạo ApplicationContext
    |
    +--> ApplicationContextInitializer callbacks
    |
    +--> ApplicationContextInitializedEvent
    |
    +--> Load primary sources
    |
    +--> ApplicationPreparedEvent
    |
    v
refresh() bắt đầu
~~~

Nếu **ApplicationContextInitializer** ném exception, lỗi **không còn hoàn toàn thuộc "trước context"** vì context đã được tạo, nhưng cũng **chưa thuộc refresh**. Tương tự, lỗi khi load primary sources hoặc listener xử lý ApplicationPreparedEvent có thể xảy ra **trước khi refresh bắt đầu**.

Vì thế, báo cáo kỹ thuật nên dùng nhãn chính xác hơn khi cần:

- **PRE_CONTEXT**: chưa tạo ApplicationContext.
- **CONTEXT_PREPARE**: context có rồi, trước refresh.
- **REFRESH**: container đang refresh, chưa hoàn tất.
- **RUNNER**: context đã refresh, đang chạy startup runners.
- **POST_READY_RUNTIME**: startup đã xong; lỗi khi phục vụ request hoặc background task không phải failure của SpringApplication.run.

**Không dùng "ApplicationPreparedEvent đã có" để suy ra bean đã được khởi tạo.** Event này chỉ nói context và những source definitions ban đầu đã được nạp nhưng chưa refresh.

Một phép đo hữu ích là kết hợp **mốc cuối thành công**, **stack trace**, **root cause** và nếu có **ApplicationFailedEvent.getApplicationContext()**. Chỉ một tín hiệu không đủ phân loại mọi lỗi.

## 8. Ví dụ Java 17+ hoàn chỉnh: tạo lỗi ở ba mốc bằng một project

Chương trình sau có thể chạy trên **Spring Boot 3.5.x** và **Java 17+**, không cần web server. Người học truyền **--demo.fail-at=...** để chủ động gây lỗi ở một trong ba nơi:

- **before-context**: ApplicationEnvironmentPreparedEvent listener ném IllegalStateException khi chưa có ApplicationContext.
- **refresh**: method @Bean của SampleService ném IllegalStateException trong lúc Spring khởi tạo singleton.
- **runner**: ApplicationRunner ném IllegalStateException sau khi ApplicationStartedEvent đã phát.
- **none**: khởi động thành công để làm mốc so sánh.

Đây là **laboratory cố ý ném exception**. Không copy các cờ gây lỗi vào production.

### 8.1. Tạo project và POM

Dùng Maven và Java 17+, project package **com.example.demo**. Phần POM hoàn chỉnh:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>startup-failure-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích:** spring-boot-starter đủ để dùng SpringApplication, ApplicationRunner, bean factory và events. Không cần starter-web, JDBC hay Actuator vì mục tiêu là phân loại startup failure.

Nếu môi trường dùng một bản patch 3.5.x khác, có thể thay **version của parent** theo BOM tương ứng. Không kết hợp tùy tiện JAR của Spring Framework thuộc các phiên bản không phù hợp với Boot.

### 8.2. File application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
spring.application.name=startup-failure-lab
spring.main.web-application-type=none

# Không gây lỗi khi chạy không có CLI override:
demo.fail-at=none
~~~

Project chạy non-web để không bị nhiễu bởi port binding. Thuộc tính **demo.fail-at** là property riêng của bài tập, **không phải** property chuẩn của Spring Boot.

### 8.3. File Java đầy đủ

Tạo **src/main/java/com/example/demo/StartupFailureLabApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupFailureLabApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupFailureLabApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        // Đăng ký TRƯỚC run để nhận được những sự kiện rất sớm.
        application.addListeners(new TraceListener());
        application.run(args);
    }

    @Bean
    SampleService sampleService(Environment environment) {
        System.out.println("04 BEAN_FACTORY");

        if ("refresh".equals(
                environment.getProperty("demo.fail-at", "none"))) {
            System.out.println("FAIL_REFRESH");
            throw new IllegalStateException(
                    "simulated failure during context refresh");
        }

        return new SampleService();
    }

    @Bean
    ApplicationRunner startupRunner(
            Environment environment, SampleService service) {

        return args -> {
            System.out.println(
                    "07 RUNNER_BEGIN service=" + service.name());

            if ("runner".equals(
                    environment.getProperty("demo.fail-at", "none"))) {
                System.out.println("FAIL_RUNNER");
                throw new IllegalStateException(
                        "simulated failure in ApplicationRunner");
            }

            System.out.println("08 RUNNER_DONE");
        };
    }

    static final class SampleService {
        String name() {
            return "ok";
        }
    }

    static final class TraceListener
            implements ApplicationListener<ApplicationEvent> {

        @Override
        public void onApplicationEvent(ApplicationEvent event) {

            if (event instanceof ApplicationEnvironmentPreparedEvent e) {
                System.out.println("01 ENV_READY");

                String mode = e.getEnvironment().getProperty(
                        "demo.fail-at", "none");

                if ("before-context".equals(mode)) {
                    System.out.println("FAIL_BEFORE_CONTEXT");
                    throw new IllegalStateException(
                            "simulated failure before context");
                }

            } else if (event instanceof ApplicationContextInitializedEvent) {
                System.out.println("02 CONTEXT_INITIALIZED");

            } else if (event instanceof ApplicationPreparedEvent) {
                System.out.println("03 CONTEXT_PREPARED");

            } else if (event instanceof ContextRefreshedEvent) {
                System.out.println("05 CONTEXT_REFRESHED");

            } else if (event instanceof ApplicationStartedEvent) {
                System.out.println("06 APPLICATION_STARTED");

            } else if (event instanceof ApplicationReadyEvent) {
                System.out.println("09 APPLICATION_READY");

            } else if (event instanceof ApplicationFailedEvent e) {
                System.out.println("EVENT_FAILED contextPresent="
                        + (e.getApplicationContext() != null));
            }
        }
    }
}
~~~

**Các điểm cần kiểm tra trong code:**

- Public class, package và file name khớp; không dùng Java API mới hơn Java 17.
- **ApplicationListener<ApplicationEvent>** có thể nhận các subclass event; **instanceof pattern matching** hợp lệ từ Java 16+.
- Listener được tạo bằng **new TraceListener()** và đăng ký **trước run**; không phụ thuộc component scan.
- **ApplicationEnvironmentPreparedEvent.getEnvironment()** truy cập thuộc tính CLI **--demo.fail-at** trước khi context tồn tại.
- **@Bean SampleService** là singleton non-lazy mặc định, được gọi trong refresh; exception ở đây thường được Spring bọc trong **BeanCreationException**.
- **ApplicationRunner** được tạo như bean khi refresh, nhưng **phương thức run** của nó được gọi **sau ApplicationStartedEvent**.
- **SampleService** inject vào runner chứng minh bean đã sẵn; không cần repository hoặc web server.
- **ApplicationFailedEvent.getApplicationContext()** được kiểm tra null trước khi dùng; không cố lấy bean từ context có thể thất bại/đang đóng.
- Log của chương trình có các marker cố định; exception stack trace và dòng log Spring Boot còn phụ thuộc môi trường.

### 8.4. Build

Từ thư mục gốc dự án:

~~~bash
java -version
mvn -version
mvn clean package
~~~

Nếu tạo project với Maven Wrapper từ Initializr, có thể chạy **./mvnw clean package** (Linux/macOS) hoặc **.\mvnw.cmd clean package** (Windows PowerShell/cmd). Với POM trên, executable JAR là:

~~~text
target/startup-failure-lab-0.0.1-SNAPSHOT.jar
~~~

Khi sửa artifactId/version, phải đổi đúng tên JAR thực tế.

### 8.5. Chạy thử từng giai đoạn

**Không gây lỗi:**

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar --demo.fail-at=none
~~~

Các marker của ứng dụng trong một startup thành công:

~~~text
01 ENV_READY
02 CONTEXT_INITIALIZED
03 CONTEXT_PREPARED
04 BEAN_FACTORY
05 CONTEXT_REFRESHED
06 APPLICATION_STARTED
07 RUNNER_BEGIN service=ok
08 RUNNER_DONE
09 APPLICATION_READY
~~~

Đây là **các dòng marker do ví dụ tự in**, không phải toàn bộ stdout (Spring Boot cũng có log INFO). Với project non-web này, sau successful run JVM có thể kết thúc vì không có web server giữ tiến trình sống; điều đó không phải startup failure.

**Nhóm A — lỗi trước context:**

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar --demo.fail-at=before-context
~~~

Các marker phản ánh nơi ném lỗi:

~~~text
01 ENV_READY
FAIL_BEFORE_CONTEXT
EVENT_FAILED contextPresent=false
~~~

Điểm học: Environment đã có, context chưa được tạo nên **contextPresent=false**; không có CONTEXT_INITIALIZED, PREPARED hay RUNNER_BEGIN. Nếu một lỗi xảy ra trước cả SpringApplication.run, thậm chí EVENT_FAILED có thể không xuất hiện.

**Nhóm B — lỗi trong refresh:**

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar --demo.fail-at=refresh
~~~

Các marker mong đợi:

~~~text
01 ENV_READY
02 CONTEXT_INITIALIZED
03 CONTEXT_PREPARED
04 BEAN_FACTORY
FAIL_REFRESH
EVENT_FAILED contextPresent=true
~~~

Điểm học: Context đã tạo, Prepared đã được phát. Bean factory method ném exception khi tạo singleton, nên **ContextRefreshedEvent** và **ApplicationStartedEvent** chưa xảy ra. Exception top-level có thể là BeanCreationException, còn root cause là IllegalStateException do demo tạo ra.

**Nhóm C — lỗi trong runner:**

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar --demo.fail-at=runner
~~~

Các marker mong đợi:

~~~text
01 ENV_READY
02 CONTEXT_INITIALIZED
03 CONTEXT_PREPARED
04 BEAN_FACTORY
05 CONTEXT_REFRESHED
06 APPLICATION_STARTED
07 RUNNER_BEGIN service=ok
FAIL_RUNNER
EVENT_FAILED contextPresent=true
~~~

Điểm học: Refresh và ApplicationStartedEvent đã hoàn tất, nhưng **ApplicationReadyEvent không phát** vì runner thất bại.

Các khối output trên chỉ tập trung vào **System.out markers của code ví dụ**; log lỗi, stack trace, ANSI colors và thứ tự xen kẽ stdout/stderr có thể khác. Khi nhiều threads hoặc logger ghi đồng thời, không dùng thứ tự giữa stdout và stderr làm chứng cứ duy nhất. Trên các đường lỗi bình thường do ví dụ tạo, java process kết thúc không thành công; mã exit chính xác nên quan sát theo shell/runtime.

### 8.6. Chạy cả bốn lần với script

Ví dụ Bash (Linux/macOS hoặc WSL), nếu muốn nhanh chóng so sánh:

~~~bash
for mode in none before-context refresh runner; do
  echo "==================== $mode"
  java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar \
    --demo.fail-at="$mode" || echo "Startup failed for $mode"
done
~~~

Đây là lệnh **có chủ đích gây exception** ở ba lượt. Đừng dùng trong service production, benchmark tải hoặc pipeline không biết rằng exit code sẽ thất bại.

### 8.7. Chỉnh sửa bài thử để nhận diện lỗi thực tế

Sau khi nắm rõ ba markers, có thể thay lời ném IllegalStateException bằng một lỗi được kiểm soát:

- Trước context: cấu hình **spring.config.import** trỏ tới resource không tồn tại mà không dùng optional.
- Trong refresh: tạo bean yêu cầu một dependency bắt buộc chưa đăng ký.
- Trong runner: gọi service seed có lỗi hoặc timeout được mô phỏng.

**Không** cố tạo lỗi bằng cách xóa dữ liệu production, tắt database dùng chung hoặc làm hỏng secrets thật. Sử dụng local test profile, H2/testcontainers hoặc mock services phù hợp.

## 9. Bảng quyết định chẩn đoán nhanh theo mốc cuối cùng

| Mốc cuối cùng thấy | Có thể suy ra | Không được suy ra | Hành động |
| --- | --- | --- | --- |
| Không có Boot event nào | Có thể lỗi rất sớm hoặc logging không có | Chắc chắn Spring chưa được gọi | Kiểm tra java command, JVM, classpath và stderr |
| ENV_READY, contextPresent=false | Lỗi trước khi tạo context trong ví dụ | Mọi lỗi property đều là pre-context | Kiểm tra ConfigData, early hooks, source config |
| CONTEXT_INITIALIZED nhưng chưa PREPARED | Đang trong chuẩn bị context/load sources | Đã refresh | Xem initializer, registry/load source, listener |
| CONTEXT_PREPARED nhưng chưa REFRESHED | Đang sát/ở refresh, có thể lỗi listener tại Prepared | Đã tạo đủ beans | Xem phase thực trong stack trace |
| BEAN_FACTORY + FAIL_REFRESH | Lỗi ngay khi @Bean method tạo singleton | Lỗi tại runner | Xem bean factory, @PostConstruct, root cause |
| CONTEXT_REFRESHED, APPLICATION_STARTED | Refresh đã thành công | Ứng dụng đã ready | Kiểm tra runner/runner ordering |
| RUNNER_BEGIN rồi EVENT_FAILED | Runner lỗi (trong demo) | Cần sửa auto-configuration | Xem business startup task, network, transaction |
| APPLICATION_READY | Boot đã hoàn tất runners theo luồng bình thường | Mọi dependency khỏe mãi hoặc request không bao giờ fail | Xem readiness probes và lỗi runtime nếu có |

**Đừng dùng số thứ tự marker để kết luận với một project có custom listeners/asynchronous event multicaster khác.** Demo tạo một listener đơn giản, dùng behavior event synchronous mặc định để dễ học. Với hệ thống nhiều contexts, các event có thể lặp ở parent/child contexts và listener phải xác nhận context liên quan.

## 10. Bóc tách stack trace đúng chỗ

Một failure trong refresh có thể hiện dạng:

~~~text
BeanCreationException: Error creating bean with name 'sampleService'
    ...
Caused by: IllegalStateException:
    simulated failure during context refresh
~~~

Đây là **trích đoạn minh họa**, không phải stack trace đầy đủ; class names, package, method frames và cách logger trình bày thay đổi theo runtime. Trong trường hợp này, **BeanCreationException là vỏ container**, còn IllegalStateException do method tạo bean ném mới là nguyên nhân trực tiếp.

Một runner failure có thể được Spring Boot bọc bằng thông điệp về việc thực thi ApplicationRunner:

~~~text
... Failed to execute ApplicationRunner
Caused by: IllegalStateException:
    simulated failure in ApplicationRunner
~~~

Không cần khớp từng ký tự message wrapper giữa các patch versions. Điều quan trọng là **có ApplicationStartedEvent trước lỗi** và stack trace đi vào **startupRunner.run(...)**.

### Quy tắc đọc nguyên nhân

1. Tìm exception gần đầu log để biết framework báo lỗi ở đâu.
2. Xác định **bean name, runner class, property name, config location** hoặc port liên quan.
3. Đi theo **Caused by** tới lỗi có khả năng hành động nhất, tránh chỉ dừng ở một BeanCreationException tổng quát.
4. Đối chiếu với mốc lifecycle cuối đã xảy ra.
5. Chỉ sau đó mới quyết định sửa Spring configuration, dependency, classpath, database hay business logic.

**Không tự động chọn cause sâu nhất trong mọi lỗi** nếu framework đã cung cấp FailureAnalysis chỉ ra vấn đề chính xác hơn. Kết hợp thông điệp có ngữ cảnh của Spring và nguyên nhân kỹ thuật trong stack trace.

## 11. FailureAnalyzer, --debug và Condition Evaluation Report

Spring Boot có cơ chế **FailureAnalyzer** để chuyển một số startup exceptions thành phần **Description** và **Action** có tính hướng dẫn. Ví dụ khi một port đã được sử dụng, Boot có thể đưa ra báo cáo:

~~~text
APPLICATION FAILED TO START

Description:
Embedded web server cannot bind the configured port.

Action:
Stop the process using that port or choose another port.
~~~

Đây là **minh họa dạng thông tin**, không phải nguyên văn message được cam kết bởi mọi patch version hoặc mọi embedded server.

### Khi nào thêm --debug?

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar \
  --demo.fail-at=refresh --debug
~~~

**--debug** làm Boot phát thông tin condition evaluation hữu ích cho auto-configuration, tùy thời điểm fail và context đã có hay chưa.

- Nếu một bean không được tạo vì **@ConditionalOnClass**, **@ConditionalOnBean** hoặc **@ConditionalOnProperty**, report có thể cho biết condition matched/negative.
- Nếu lỗi xảy ra **trước khi context tồn tại**, không nên mong có một Condition Evaluation Report đầy đủ.
- Nếu lỗi nằm trong code runner hoặc remote API, report auto-configuration có thể không phải nơi mang nguyên nhân chính.
- Bật debug có thể tạo log rất lớn và lộ thông tin môi trường trong các hệ thống thực; chọn phạm vi logging an toàn.

Có thể cấu hình logging chuyên biệt:

~~~properties
logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

Property này có thể giúp xem auto-configuration decisions, nhưng không phải phép chữa lỗi. Với ứng dụng đang lỗi trước khi logging được khởi tạo, hãy dựa vào stderr/JVM startup diagnostics và các cơ chế early logging phù hợp.

### PortInUseException thuộc giai đoạn nào?

Với Spring MVC embedded Tomcat, việc bind port thường xảy ra trong quá trình context refresh/web server initialization. Do đó lỗi port trùng thường xếp vào nhóm **REFRESH**, không phải RUNNER. Nhưng phải kiểm tra **stack trace và web server factory** thực tế; đừng xếp mọi lỗi network chung vào runner.

## 12. Startup failure, liveness và readiness

Spring Boot 3.5 mô tả:

~~~text
Sau ApplicationStartedEvent:
    LivenessState.CORRECT

Sau ApplicationReadyEvent:
    ReadinessState.ACCEPTING_TRAFFIC
~~~

Với lỗi **pre-context** hoặc **refresh**, app chưa đạt mốc Started. Với lỗi **runner**, context đã refresh và liveness state có thể đã CORRECT, nhưng startup **chưa đạt Ready** và Boot bước vào xử lý failure.

Điều này giải thích vì sao:

- "Container process có PID" không nghĩa là app đã ready.
- "Cổng HTTP đã LISTEN" không nghĩa là runners xong.
- "Log có Started..." không nghĩa là ApplicationReadyEvent đã phát.
- Readiness probe phù hợp cần phản ánh điều kiện mà ứng dụng có thể nhận traffic thật.
- Khi startup thất bại, Kubernetes có thể restart container do process exit; readiness probe không phải cơ chế sửa lỗi startup.

**Không ép AvailabilityChangeEvent công bố ACCEPTING_TRAFFIC để che một runner bắt buộc đang lỗi.** Nó không làm database/schema trở lại bình thường và có thể đưa traffic vào một service chưa đủ điều kiện.

Nếu công việc runner chỉ mang tính tối ưu hiệu năng, có thể tách thành background best-effort với fallback và metric, nhưng cần thiết kế rõ **ready nghĩa là gì** để không lừa hệ thống điều phối.

## 13. Chọn hook đúng để tránh đưa lỗi vào sai giai đoạn

| Nhu cầu | Hook hợp lý | Lưu ý |
| --- | --- | --- |
| Bổ sung một PropertySource sớm | EnvironmentPostProcessor | Không inject business beans; cân nhắc ConfigData ordering |
| Cấu hình context trước khi refresh | ApplicationContextInitializer | Context có nhưng beans chưa sẵn |
| Đăng ký/biến đổi BeanDefinition | BeanDefinitionRegistryPostProcessor | Chạy trong refresh, cần hiểu registry lifecycle |
| Thay đổi bean metadata | BeanFactoryPostProcessor | Tránh tạo bean sớm ngoài contract |
| Khởi tạo một bean nhẹ | Constructor/@PostConstruct | Không gọi API mạng chậm nếu không cần |
| Chạy tác vụ startup cần Spring services | ApplicationRunner/CommandLineRunner | Sau refresh, trước ready, cần idempotency |
| Nhận ApplicationEnvironmentPreparedEvent | addListeners hoặc đăng ký early listener | Không dùng @Bean listener được tạo quá muộn |
| Phản ứng sau app ready | ApplicationReadyEvent listener | Không sửa sự thật rằng startup runners đã xong |
| Đo lỗi startup | ApplicationFailedEvent listener hoặc FailureAnalyzer | Đăng ký đúng thời điểm, kiểm tra context null |
| Background work không bắt buộc | Managed executor/scheduler với failure policy | Không mặc định Boot chờ async task hoàn thành |

Chọn sai hook có thể gây lỗi khó tìm: lấy DataSource trong EnvironmentPreparedEvent, gọi repository ở @PostConstruct khi dependency chưa đủ, hoặc chạy một công việc bắt buộc trong Future rồi trả về từ runner trước khi nó hoàn thành.

## 14. Khi lỗi xảy ra trong runner: retry, rollback và idempotency

Một tình huống thực tế: runner seed danh mục, đã ghi được 3/5 records rồi lỗi kết nối. Kubernetes restart Pod và runner chạy lại. Nếu không có ràng buộc unique hay trạng thái bền vững, có thể tạo record trùng.

Thiết kế đúng:

- Mỗi seed operation có **business key ổn định** và unique constraint tại database.
- Dùng insert-if-absent hoặc upsert theo semantics được định nghĩa, không ghi đè vô điều kiện dữ liệu hợp lệ.
- Nếu seed nhiều bảng liên quan, chọn transaction boundary đúng và đảm bảo bước retry idempotent.
- Nếu gọi external API, dùng idempotency key hoặc durable job/outbox nếu phía đích hỗ trợ.
- Retry chỉ transient errors với bounded attempts, deadline, backoff và jitter.
- Với lỗi cấu hình cố định như thiếu bảng do migration, **fail fast** và sửa deployment, không retry vô hạn.
- Log stage, elapsed time, attempt và root cause, không log secrets.

**ApplicationRunner ném exception khiến startup thất bại, nhưng điều đó không tự rollback những side effects đã commit trước đó.** SpringApplication failure handling có thể đóng context, song không thể tự undo một email đã gửi hoặc một DB transaction đã commit.

Với **@Transactional**, phải đảm bảo lời gọi đi qua Spring proxy hoặc dùng TransactionTemplate khi cần; self-invocation có thể không tạo transaction như dự định.

## 15. Vì sao không nên chỉ xóa bean hoặc tắt tính năng để làm app start?

Một số cách "sửa nhanh" có nguy cơ:

- Xóa @Bean gây lỗi mà không hiểu service khác cần nó.
- Bật spring.main.lazy-initialization=true chỉ để dời lỗi sang request đầu tiên.
- Bắt và bỏ qua toàn bộ Exception trong runner bắt buộc.
- Vô hiệu hóa readiness check để Pod hiện READY trong khi DB/schema vẫn sai.
- Tăng timeout lên vô hạn để che deadlock hoặc kết nối mạng không có retry policy.
- Đổi nhiều thư viện version một lúc khiến khó xác định binary incompatibility.
- Đọc một dòng "Error creating bean" rồi lập tức thay component scan, trong khi root cause là secret hoặc database credential sai.

Cách làm tốt hơn là **khóa phạm vi lỗi theo lifecycle**, tái hiện bằng một cấu hình nhỏ, xác định root cause và sửa ở extension point phù hợp. Giữ lại test regression cho trường hợp đã gây lỗi.

## 16. Kịch bản production: ba sự cố, ba cách điều tra

### Tình huống 1 — Config server hoặc ConfigData không có

Ứng dụng không vượt qua phase Environment. Chưa có context, nên repository và business listener không thể cứu startup. Xem **spring.config.import**, optional imports, credentials đọc config và logs từ environment processing. Nếu config là bắt buộc, fail sớm là hợp lý. Nếu optional, khai báo optional có chủ đích và xác định default.

### Tình huống 2 — Bean DataSource hoặc web server lỗi trong refresh

Đã có context, nhưng refresh chưa thành công. Với DataSource, kiểm tra driver, JDBC URL, credentials, bean construction và database reachable; với port bind, kiểm tra server.port và process chiếm cổng. Bật debug để xem auto-config condition report **nếu report có ích**, rồi tìm BeanCreationException và root cause.

### Tình huống 3 — Warm-up cache ném lỗi trong runner

Context đã refresh và SpringApplication đã started. Runner query database bị timeout. Quyết định cache là **required** hay **best effort**:

- Required: runner chờ có deadline, xử lý retry hợp lý, rồi fail startup nếu chưa đủ điều kiện.
- Best effort: ghi metric, cho cache-aside/fallback và sẵn sàng chấp nhận request.
- Không để một Future đang fail ở background nhưng vẫn cho Boot báo ready nếu nó là điều kiện bắt buộc.

Mỗi tình huống có cùng biểu hiện bên ngoài "process startup failed", nhưng nguyên nhân kỹ thuật và cách khôi phục khác nhau.

## 17. Kiểm thử và quan sát lỗi theo môi trường

### Với test đơn vị và integration tests

- Test **EnvironmentPostProcessor** ở môi trường cấu hình tối thiểu, không dùng toàn bộ ApplicationContext nếu không cần.
- Dùng **ApplicationContextRunner** cho các bài test auto-configuration/bean conditions; nó không nhất thiết phát đủ chuỗi SpringApplication events của một ứng dụng thật.
- Dùng **SpringApplication** có listener đăng ký sớm như demo để test event ordering.
- Dùng **@SpringBootTest** khi cần toàn bộ context; nhớ rằng context caching có thể làm hành vi startup không xảy ra ở mỗi test method.
- Test runner logic bằng service riêng và fake dependencies, rồi integration test xem exception có thực sự khiến startup fail.

### Với container/Kubernetes

- Xem **container exit reason/exit code**, logs và previous logs khi container restart liên tục.
- Phân biệt lỗi process không lên, lỗi startupProbe, livenessProbe restart và readinessProbe chưa healthy.
- Xem timestamp giữa event markers và error stack.
- Kiểm tra config từ ConfigMap, Secret, environment variables, command-line arguments thực tế.
- Với startup chậm, cấu hình startupProbe hợp lý; không biến lỗi schema vĩnh viễn thành một vòng chờ vô hạn.
- Khi số replicas lớn, việc tất cả pods cùng seed/warm-up có thể làm downstream quá tải. Cần idempotency, limits và coordination.

### Gợi ý thông tin cần ghi log

Một log startup chuẩn có thể chứa:

~~~text
stage=ENVIRONMENT_PREPARED
stage=CONTEXT_PREPARED
stage=REFRESH_COMPLETED
stage=RUNNER_STARTED task=seed-defaults
stage=RUNNER_FAILED task=seed-defaults error=database-timeout
stage=APPLICATION_FAILED
~~~

Đây là **mẫu log thiết kế** chứ không phải output mặc định của Spring Boot hoặc demo. Log có thêm **app version, environment, instance ID, elapsed time, trace/correlation ID** nếu phù hợp. Tránh in mật khẩu, access token, JDBC URL chứa secrets, hoặc nội dung file config nhạy cảm.

## 18. Bài tập tự kiểm tra

**Câu 1.** ApplicationEnvironmentPreparedEvent được phát trước hay sau khi có ApplicationContext? Có thể gọi business repository ngay trong listener không?

**Câu 2.** Một ứng dụng có ApplicationPreparedEvent nhưng chưa có ContextRefreshedEvent. Bạn có thể kết luận điều gì, và điều gì vẫn chưa chắc?

**Câu 3.** Boot đã phát ApplicationStartedEvent rồi runner ném IllegalStateException. Có ApplicationReadyEvent không? App đã refresh chưa?

**Câu 4.** Cùng tên IllegalStateException có thể xuất hiện trong cả ba nhóm không? Vì sao exception type đơn lẻ không đủ?

**Câu 5.** Một @Bean factory method gọi API ngoài rồi ném lỗi. Lỗi thuộc phase nào nếu singleton được tạo trong refresh?

**Câu 6.** Một ApplicationContextInitializer ném exception sau khi context được tạo. Nó có thuộc hoàn toàn nhóm "trước khi có context" hay "trong refresh" không?

**Câu 7.** Vì sao listener dưới dạng @Component có thể không nhận được lỗi ở giai đoạn Environment?

**Câu 8.** App có log Started và port 8080 đang mở, nhưng readiness chưa UP. Có thể do runner đang chạy không?

**Câu 9.** Vì sao --debug/Condition Evaluation Report hữu ích cho @ConditionalOnBean nhưng ít hữu ích hơn với lỗi mạng trong runner?

**Câu 10.** Runner seed dữ liệu một phần rồi thất bại; có thể tin rằng SpringApplication tự rollback mọi ghi nhận trước đó không?

**Câu 11.** Lỗi xảy ra trước SpringApplication.run vì main class không load được. Có nên chờ ApplicationFailedEvent không?

**Câu 12.** Bật lazy initialization có loại bỏ bean creation error không, hay có thể chỉ chuyển nó sang thời điểm khác?

### Đáp án gợi ý

1. Trước; không có context/beans để dùng repository.
2. Context đã chuẩn bị, refresh chưa được xác nhận hoàn tất; có thể lỗi trước hoặc trong refresh.
3. Không có Ready theo luồng startup thất bại; refresh đã hoàn thành.
4. Có; throw site và lifecycle mới quyết định phase.
5. Thường là REFRESH, dù lỗi sâu bên dưới do remote API.
6. Là khoảng CONTEXT_PREPARE, đã có context nhưng chưa refresh.
7. Vì bean listener được tạo sau early event; dùng addListeners trước run.
8. Có; ApplicationStartedEvent và port mở chưa đồng nghĩa Ready.
9. Conditions report mô tả auto-configuration, không giải thích mọi remote runtime timeout.
10. Không; cần transaction, unique key, idempotency và recovery.
11. Không; lỗi nằm ngoài SpringApplication startup handling.
12. Có thể dời lỗi sang lần sử dụng bean, không tự làm cấu hình đúng.

## 19. Checklist chẩn đoán trước khi sửa

- [ ] Đã biết startup thực tế chạy bản **Spring Boot/JDK** nào?
- [ ] Đã xác nhận command-line, profiles, ConfigData và env vars của instance lỗi?
- [ ] Có ghi nhận **mốc lifecycle cuối cùng thành công**?
- [ ] Có phân biệt PRE_CONTEXT, CONTEXT_PREPARE, REFRESH, RUNNER và runtime sau Ready?
- [ ] Có đọc **Caused by** và thông điệp lỗi có tính hành động nhất?
- [ ] Khi chưa có context, không cố dùng @Autowired/getBean?
- [ ] Với refresh error, đã kiểm tra BeanCreation/DI/validation/port bind?
- [ ] Với runner error, đã kiểm tra transaction, retries, seed idempotency và external services?
- [ ] Không hiểu sai ApplicationStartedEvent thành ApplicationReadyEvent?
- [ ] Không tự coi port mở là ứng dụng sẵn sàng phục vụ?
- [ ] Có tránh bắt Exception rồi bỏ qua trong tác vụ startup bắt buộc?
- [ ] --debug/Condition Evaluation Report chỉ được dùng khi phù hợp?
- [ ] Có kiểm thử failure/restart và bảo vệ dữ liệu khỏi duplicate side effects?
- [ ] Có giới hạn timeout và log đủ thông tin, không lộ secrets?
- [ ] Đã kiểm tra context failure event có thể có null context và không sửa nhầm context đã đóng?

## 20. Tổng kết và nguồn chính thức

**Cách phân loại đáng tin nhất là kết hợp mốc sự kiện, trạng thái context và stack trace:**

~~~text
BEFORE CONTEXT:
  Environment/config/early hook lỗi
  -> chưa có context, không dùng bean

DURING REFRESH:
  @Configuration / BeanDefinition / singleton / web server lỗi
  -> context có, nhưng chưa ApplicationStartedEvent

IN RUNNER:
  Context đã refresh, ApplicationStartedEvent đã xảy ra
  -> runner lỗi, không tới ApplicationReadyEvent

Ngoài ba nhóm:
  Lỗi trong context preparation trước refresh
  và lỗi xảy ra ngoài SpringApplication.run / sau ready
~~~

**ApplicationFailedEvent** có thể giúp quan sát lỗi startup nhưng không thay thế root cause analysis; **FailureAnalyzer** có thể cung cấp Description/Action cho các lỗi được hỗ trợ. Với những công việc bắt buộc trước ready, dùng runner có timeout, retry và idempotency đúng, không dùng catch-all để làm hệ thống báo healthy giả.

Nguồn tài liệu theo Spring Boot 3.5:

1. Spring Boot 3.5 Reference — SpringApplication, Application Events and Listeners, Startup Failure, runners: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot 3.5 API — ApplicationFailedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html
3. Spring Boot 3.5 API — ApplicationEnvironmentPreparedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
4. Spring Boot 3.5 API — ApplicationPreparedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html
5. Spring Boot 3.5 API — FailureAnalyzer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html
6. Spring Framework Reference — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html

Ví dụ được thiết kế cho **Spring Boot 3.5.x, Java 17+ và Maven**. Trong các phiên bản khác, hãy đối chiếu JavaDoc của đúng bản đang triển khai trước khi xây dựng runbook dựa trên thứ tự events, diagnostics và auto-configuration.