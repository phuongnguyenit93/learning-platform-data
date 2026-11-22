# Lập bảng chọn điểm mở rộng theo thời điểm, phụ thuộc và yêu cầu hoàn tất trong Spring Boot

## 1. Đề bài thực hành: chọn đúng hook, không chỉ nhớ tên callback

Một ứng dụng Spring Boot có thể cần thêm PropertySource, thay đổi bean definitions, khởi tạo cache, kiểm tra một external service, bắt đầu consumer, phát thông báo ready hoặc đóng tài nguyên. Đây là **những yêu cầu khác nhau về thời điểm**, dù tất cả đều có thể được gọi chung là khởi tạo ứng dụng.

Trước khi chọn một extension point, cần trả lời ba câu hỏi:

1. **Thời điểm nào?** Trước Environment, trước bean definitions, khi một bean được tạo, sau khi singleton eager được tạo, sau refresh, trước readiness, sau readiness, lúc runtime hay khi shutdown?
2. **Được phụ thuộc cái gì?** Có Environment chưa? Có ApplicationContext chưa? BeanDefinitionRegistry đã sẵn sàng chưa? Có thể inject service/repository không? Có embedded server hay DataSource chưa?
3. **Phải hoàn tất đến mức nào?** Chỉ cần đăng ký một cấu hình, chạy callback đồng bộ, chờ external check thành công, fire-and-forget hoặc dừng bất đồng bộ rồi gọi callback xác nhận?

Ba câu hỏi quyết định tính đúng đắn của lifecycle logic. Ví dụ:

~~~text
Ứng dụng xử lý đơn hàng
    |
    +-- đọc và hợp nhất cấu hình
    +-- chọn những bean definitions cần đăng ký
    +-- tạo các service và connection pools
    +-- kiểm tra gateway bắt buộc trước readiness
    +-- phát trạng thái có thể nhận traffic
    +-- bắt đầu nhận messages
    |
    +-- chạy lâu dài
    |
    +-- nhận SIGTERM
          +-- ngừng nhận message và HTTP request mới
          +-- chờ công việc đang chạy có giới hạn
          +-- đóng executor, connection, cache
          +-- process kết thúc
~~~

Đưa tất cả các bước vào **@PostConstruct** có thể làm logic chạy quá sớm. Đưa tất cả vào **ApplicationReadyEvent** có thể làm bước bắt buộc chạy quá muộn. Dùng **@PreDestroy** cho một consumer cần dừng có thứ tự có thể khiến không thể báo chính xác khi nào công việc bất đồng bộ đã được drain.

**Mục tiêu:** xây một bảng lựa chọn có thể tái sử dụng, thực hành bằng Java 17+/Spring Boot 3.3.13 và chứng minh từng mốc bằng kiểm thử thực sự thay vì đoán dựa trên log hoặc Thread.sleep.

## 2. Bản đồ vòng đời cần nhớ

Sơ đồ là mô hình đọc thứ tự các mốc chính; các callback nội bộ trong cùng một phase và các context hierarchy có thể có chi tiết riêng.

~~~text
SpringApplication.run()
    |
    +-- ApplicationStartingEvent
    |
    +-- Prepare Environment
    |     +-- EnvironmentPostProcessor / Config Data
    |     +-- ApplicationEnvironmentPreparedEvent
    |
    +-- Create ApplicationContext
    |     +-- ApplicationContextInitializer
    |     +-- ApplicationContextInitializedEvent
    |
    +-- Load bean definitions
    |     +-- ApplicationPreparedEvent
    |
    +-- Refresh ApplicationContext
    |     +-- BeanDefinitionRegistryPostProcessor
    |     +-- BeanFactoryPostProcessor
    |     +-- Register BeanPostProcessors
    |     +-- Instantiate non-lazy singleton beans
    |     |     +-- Constructor/injection
    |     |     +-- @PostConstruct and init callbacks
    |     |     +-- BeanPostProcessor callbacks
    |     +-- SmartInitializingSingleton
    |     +-- SmartLifecycle auto-start
    |     +-- ContextRefreshedEvent
    |     +-- WebServerInitializedEvent when relevant
    |
    +-- ApplicationStartedEvent
    +-- LivenessState.CORRECT
    |
    +-- ApplicationRunner / CommandLineRunner
    |     +-- synchronous mandatory checks
    |
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    |
    +-- SpringApplication.run returns
    |
    +-- Runtime: requests / jobs / messages
    |
    +-- ApplicationContext.close / normal JVM shutdown
          +-- ContextClosedEvent
          +-- SmartLifecycle.stop, ordered phases
          +-- @PreDestroy, DisposableBean, destroyMethod
~~~

Có hai ràng buộc đặc biệt:

- **Environment và Config Data:** EnvironmentPostProcessors và các event listeners có ordering. Một listener chạy quá sớm ở ApplicationEnvironmentPreparedEvent có thể quan sát Environment trước khi các xử lý cấu hình khác đã thực hiện xong. Không mặc định mọi listener cùng event đều nhìn thấy một tập PropertySource như nhau.
- **Ready và availability:** Spring Boot 3.3 phát **ApplicationStartedEvent sau refresh nhưng trước runners**, rồi **ApplicationReadyEvent sau runners**. Theo luồng thành công bình thường, **ReadinessState.ACCEPTING_TRAFFIC** được công bố sau ReadyEvent. Server port có thể mở trước các mốc này; socket listening không đồng nghĩa routing ready.

## 3. Bảng chọn extension point theo ba trục

| Điểm mở rộng | Thời điểm | Có thể phụ thuộc vào | Yêu cầu hoàn tất / mục đích phù hợp |
| --- | --- | --- | --- |
| **BootstrapRegistryInitializer** | Bootstrap rất sớm | BootstrapRegistry, bootstrap helper | Đồng bộ: thiết lập hạ tầng phục vụ Config Data/khởi động |
| **ApplicationStartingEvent** | Bắt đầu run, trước Environment hoàn chỉnh | Application và startup args từ event | Quan sát/tracing cực sớm, không dùng bean |
| **EnvironmentPostProcessor** | Chuẩn bị Environment trước context | ConfigurableEnvironment, SpringApplication | Đồng bộ: thêm/sửa PropertySource và config sources |
| **ApplicationEnvironmentPreparedEvent** | Environment được công bố trước context | Environment trong event; chưa có app beans | Early listener, chú ý order với Config Data |
| **ApplicationContextInitializer** | Sau tạo context, trước nạp bean definitions | ConfigurableApplicationContext, Environment | Đồng bộ: tùy chỉnh context/PropertySources |
| **ApplicationContextInitializedEvent** | Sau initializer, trước definitions | Context, Environment | Quan sát context đã initialized |
| **ApplicationPreparedEvent** | Definitions đã được load, trước refresh | Context và metadata | Quan sát bước prepared; chưa có runtime beans |
| **BeanDefinitionRegistryPostProcessor** | Trong refresh, trước regular beans | BeanDefinitionRegistry | Thêm/đổi bean definitions |
| **BeanFactoryPostProcessor** | Trước regular bean instantiation | ConfigurableListableBeanFactory, bean metadata | Sửa/đọc metadata; tránh gọi getBean nghiệp vụ |
| **BeanPostProcessor** | Theo từng bean đang khởi tạo | Bean object, beanName | Wrap/proxy hoặc xử lý bean instance |
| **Constructor / @PostConstruct** | Khi chính bean được khởi tạo | Dependencies đã inject cho bean đó | Khởi tạo state/resource bean-local đồng bộ |
| **SmartInitializingSingleton** | Cuối pre-instantiation regular singleton | Các eager singleton thông thường | Xác minh sau eager beans; không bảo đảm lazy beans |
| **SmartLifecycle.start()** | Trong refresh/start lifecycle, theo phase | Bean và dependency được quản lý | Bắt đầu long-running component; hoàn tất start cần contract riêng |
| **ContextRefreshedEvent** | Context đã refresh | Context, regular bean graph | Quan sát refresh; chưa có bảo đảm runners đã xong |
| **WebServerInitializedEvent** | Embedded web server đã initialized | WebServer và cổng thực tế | Biết port/server, không đồng nghĩa readiness |
| **ApplicationStartedEvent** | Sau refresh, trước runners | Beans/context sau refresh | Quan sát started, chưa phải Ready |
| **ApplicationRunner / CommandLineRunner** | Sau Started, trước Ready | Services, repositories, bean dependencies | **Chạy đồng bộ và hoàn tất/throw trước readiness** |
| **ApplicationReadyEvent** | Sau runners | Bean graph và startup đã hoàn tất | Thông báo sau startup; không tự chờ tác vụ async |
| **AvailabilityChangeEvent** | Khi liveness/readiness state thay đổi | ApplicationAvailability/state | Điều phối khả năng nhận traffic |
| **ContextClosedEvent** | Bắt đầu close context | Context/managed beans đang chuyển sang shutdown | Báo bắt đầu shutdown, không chứng minh cleanup đã xong |
| **SmartLifecycle.stop(Runnable)** | Trong shutdown phase | Component và dependency còn phù hợp | Dừng có thứ tự; callback sau khi stop hoàn tất |
| **@PreDestroy / destroyMethod** | Bean destruction | Resources do bean sở hữu | Đóng tài nguyên, không block vô hạn |

**Đọc cột cuối trước khi chọn:** Nếu một kiểm tra **bắt buộc hoàn tất trước readiness**, ApplicationRunner đồng bộ thường là lựa chọn rõ nhất. Nếu một daemon consumer phải **dừng và báo hoàn tất**, SmartLifecycle.stop(callback) phù hợp. Nếu chỉ đổi blueprint của bean, chọn BeanDefinitionRegistryPostProcessor/BeanFactoryPostProcessor thay vì khởi tạo một bean thật quá sớm.

### 3.1. Bảng giới hạn: không được giả định điều gì?

| Đang ở điểm mở rộng | Chưa thể giả định |
| --- | --- |
| EnvironmentPostProcessor | Đã có @Autowired business service hoặc datasource |
| ApplicationContextInitializer | Các bean definitions và business singletons đã sẵn |
| BeanFactoryPostProcessor | Lấy được service qua getBean mà không phá lifecycle |
| BeanPostProcessor | Tất cả bean khác đã được khởi tạo và được auto-proxy |
| @PostConstruct | Tất cả singleton đã tạo, runners đã chạy |
| SmartInitializingSingleton | Lazy singletons đã được tạo hoặc external service healthy |
| SmartLifecycle.start | Startup gate ApplicationRunner đã hoàn tất |
| ContextRefreshedEvent | ApplicationReadyEvent đã xảy ra |
| ApplicationStartedEvent | Runners đã chạy xong |
| WebServerInitializedEvent | Readiness đã ACCEPTING_TRAFFIC |
| ApplicationReadyEvent | Mọi @Async/background task đã hoàn tất |
| ContextClosedEvent | SmartLifecycle.stop và @PreDestroy đã xong |
| @PreDestroy | SIGKILL/crash vẫn sẽ gọi cleanup |

Một API có tên **Ready** không bảo đảm mọi worker nền đã làm xong việc. Một API có tên **Initialized** không bảo đảm toàn bộ container hay web gateway đã sẵn sàng.

## 4. Cây quyết định thực hành

~~~text
Yêu cầu mới
    |
    +-- Cần thiết lập nguồn config trước khi có beans?
    |      +-- Bootstrap helper -> BootstrapRegistryInitializer
    |      +-- PropertySource/config loader -> EnvironmentPostProcessor
    |
    +-- Có context, chưa load bean definitions?
    |      +-- Tùy chỉnh context -> ApplicationContextInitializer
    |
    +-- Cần thay bean metadata?
    |      +-- Thêm/xóa definitions -> BeanDefinitionRegistryPostProcessor
    |      +-- Thay metadata đã đăng ký -> BeanFactoryPostProcessor
    |
    +-- Cần can thiệp mỗi bean instance?
    |      +-- Wrapping/proxy -> BeanPostProcessor
    |      +-- Bean-local init -> @PostConstruct
    |
    +-- Cần mốc sau eager singleton creation?
    |      +-- SmartInitializingSingleton
    |
    +-- Cần bắt đầu/dừng long-running component?
    |      +-- SmartLifecycle start/stop/callback
    |
    +-- Cần hoàn tất critical setup trước Ready?
    |      +-- ApplicationRunner / CommandLineRunner
    |             +-- chờ kết quả đồng bộ, bounded
    |             +-- throw nếu không đủ điều kiện
    |
    +-- Chỉ cần thông báo đã qua startup?
    |      +-- ApplicationReadyEvent
    |
    +-- Cần quản lý traffic khi dependency đổi trạng thái?
    |      +-- Readiness / ApplicationAvailability / HealthIndicator
    |
    +-- Khi shutdown?
           +-- Ngừng nhận, drain async -> SmartLifecycle.stop(callback)
           +-- Close tài nguyên bean -> @PreDestroy / destroyMethod
~~~

Đây là **quy tắc chọn mặc định**, không phải lý do để tự viết SPI khi Spring đã có một abstraction chuyên biệt tốt hơn. Ví dụ cho database schema migration, dùng Flyway/Liquibase integration thay vì tạo custom BeanPostProcessor chỉ để chạy SQL.

## 5. Thước đo completion: “được gọi” không có nghĩa “đã xong”

Một callback có thể đồng bộ nhưng chỉ submit async task rồi return.

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.execute(this::loadRequiredCache);
    // Runner đã return, nhưng cache có thể chưa hoàn tất.
}
~~~

Đây là snippet minh họa với executor/loadRequiredCache do app khai báo. Spring Boot chờ **run()** hoàn tất, **không tự chờ mọi task mà run() đã submit**.

Vì vậy không thể gọi đoạn trên là startup gate đúng khi cache bắt buộc trước readiness. Cần:

- Chạy logic hữu hạn đồng bộ ngay trong runner, **hoặc**
- Chờ completion thật bằng Future.get(timeout), CompletableFuture.get(timeout), CountDownLatch.await(timeout) có xử lý lỗi, **rồi mới return**.
- Ném exception nếu điều kiện bắt buộc không đạt; không log lỗi rồi âm thầm tiếp tục báo ready.

### 5.1. Bốn mức hoàn tất

| Mức | Điều chứng minh | Không thể suy ra |
| --- | --- | --- |
| **REGISTERED** | Callback/bean definition đã đăng ký | Bean đã tạo hoặc task đã chạy |
| **STARTED** | Task đã bước vào logic thực thi | Job đã hoàn tất |
| **COMPLETED** | Future/callback ghi nhận task kết thúc | Side effect đã commit, nếu API không bảo đảm |
| **CLEANED_UP** | Component/resource đã đóng theo contract | JVM sẽ sống sót khi SIGKILL |

Với một background consumer, **start() return** có thể chỉ chứng minh consumer đã nhận lệnh start. Nếu phải đợi broker subscription thực sự ready, component cần **một tín hiệu riêng** hoặc tích hợp readiness state thích hợp.

### 5.2. Khi nào ApplicationRunner thực sự gate Ready?

~~~text
ApplicationStartedEvent
      |
ApplicationRunner
      |-- verify configuration
      |-- verify critical external service (bounded timeout)
      |-- Future.get(timeout) nếu có async task bắt buộc
      |-- return success hoặc throw
      |
ApplicationReadyEvent
      |
ReadinessState.ACCEPTING_TRAFFIC
~~~

Phần kết quả phải được quan sát trong chính runner trước khi return. Với remote check, đặt timeout/connect timeout, retry có giới hạn và phân biệt backend critical/optional. Một remote check thành công lúc startup không bảo đảm nó không lỗi sau đó; runtime vẫn cần circuit breaker/retry/fallback.

### 5.3. SmartLifecycle.stop callback phải phản ánh dừng thật

~~~java
@Override
public void stop(Runnable callback) {
    CompletableFuture.runAsync(this::drainAndClose)
            .whenComplete((unused, error) -> {
                if (error != null) {
                    recordStopError(error);
                }
                callback.run();
            });
}
~~~

Đây là snippet khái niệm; drainAndClose và recordStopError là methods do ứng dụng triển khai. Nếu drainAndClose gửi một task rồi return ngay, callback vẫn quá sớm. **SmartLifecycle.stop(Runnable)** phải gọi callback sau khi component đã dừng theo hợp đồng. Nếu callback không được gọi, LifecycleProcessor có thể chờ tới timeout của shutdown phase.

Cần bounded drain, error reporting và không block vô hạn. Khi stop thất bại, không báo hoàn tất sai; định nghĩa rõ trạng thái failed-stop và cleanup cuối.

### 5.4. Event listener không nhất thiết là barrier

Mặc định các Spring application events thường được dispatch đồng bộ, nhưng behavior có thể thay đổi khi cấu hình asynchronous multicaster, @Async listener hoặc error handler.

**Không chọn một listener @Async của ApplicationReadyEvent làm bước bắt buộc trước readiness.** Sự kiện đã publish có thể kết thúc trong khi tác vụ nền chưa xong. Dùng runner hoặc một gate explicit.

## 6. Trước context: BootstrapRegistryInitializer và EnvironmentPostProcessor

### 6.1. BootstrapRegistryInitializer

Một integration có thể cần credentials provider, bootstrap connection hoặc helper dùng để **nạp chính Config Data**. Nó không thể đợi một service bean vì container chưa tạo bean.

Trong trường hợp đó, **BootstrapRegistryInitializer** là một điểm mở rộng được thiết kế cho bootstrap infrastructure. Đây thường là trách nhiệm thư viện/hạ tầng, không phải phương tiện mặc định để chạy mọi logic nghiệp vụ.

Một phương thức interface minh họa:

~~~java
@Override
public void initialize(BootstrapRegistry registry) {
    registry.registerIfAbsent(
            BootstrapHelper.class,
            context -> new BootstrapHelper());
}
~~~

Snippet cần class BootstrapHelper và imports tương ứng. Việc đăng ký initializer phải theo cơ chế của integration Spring Boot; đừng coi @Component scan là cơ chế bootstrap sớm.

### 6.2. EnvironmentPostProcessor: cấu hình trước bean graph

Một EnvironmentPostProcessor có thể thêm PropertySource với precedence phù hợp. Ví dụ lớp Java 17+ độc lập:

~~~java
package com.example.extension;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class FallbackEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "extensionDefaults",
                        Map.of("demo.region", "local")));
    }
}
~~~

Đăng ký qua **META-INF/spring.factories** nếu muốn Boot discover:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.extension.FallbackEnvironmentPostProcessor
~~~

- **addLast** dùng cho fallback, tránh ghi đè cấu hình người sử dụng có precedence cao hơn.
- **Ordered** kiểm soát thứ tự so với các EnvironmentPostProcessors khác. Config Data cũng tham gia chuẩn bị Environment, nên không giả định mọi source đã được tải trước callback có order bất kỳ.
- Đây không phải nơi @Autowired repository/service; bean graph chưa sẵn sàng.

### 6.3. ApplicationEnvironmentPreparedEvent không bắt bằng @Component theo cách thông thường

Event này xảy ra trước khi application beans được tạo. Muốn nhận, đăng ký sớm:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(
        (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                event -> System.out.println("Environment available"));
app.run(args);
~~~

Đây là snippet cần MyApplication, imports và args. Một listener đánh dấu @Component/@EventListener không thể được trông đợi nhận lại early event đã phát trước lúc bean tồn tại.

### 6.4. ApplicationContextInitializer: có context, chưa có service bean

Initializer thích hợp để chỉnh Environment, context ID/property sources trước khi bean definitions được load.

~~~java
application.addInitializers(context -> {
    context.getEnvironment().getPropertySources().addLast(
            new MapPropertySource(
                    "demoDefaults",
                    Map.of("demo.name", "fallback")));
});
~~~

Đây là snippet; trong dự án thực tế cần SpringApplication, imports và source map. **Có context object không đồng nghĩa context.getBean(OrderService.class) đã hợp lệ.**

Nếu muốn thay đổi logging properties từ nguồn tùy biến, cần đặc biệt chú ý timing: @PropertySource được nạp lúc refresh có thể **quá muộn** đối với một số logging.* hoặc spring.main.* đã tiêu thụ sớm. Không thể dùng ReadyEvent để “áp dụng ngược” một thiết lập đã được đọc trước đó.

## 7. Khi container xử lý metadata và bean instances

### 7.1. BeanDefinitionRegistryPostProcessor

Muốn đăng ký thêm BeanDefinition trước khi Spring khởi tạo beans, dùng BeanDefinitionRegistryPostProcessor hoặc một registrar/import SPI thích hợp.

~~~java
@Override
public void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry) {

    if (!registry.containsBeanDefinition("featureMarker")) {
        registry.registerBeanDefinition(
                "featureMarker",
                new RootBeanDefinition(FeatureMarker.class));
    }
}
~~~

Đoạn code này là method minh họa, không phải class độc lập: cần class triển khai BeanDefinitionRegistryPostProcessor, method postProcessBeanFactory, imports và class FeatureMarker. Nó **đăng ký metadata**, không gọi new một service rồi bỏ qua lifecycle.

### 7.2. BeanFactoryPostProcessor

BeanFactoryPostProcessor hoạt động trên cấu hình metadata, thường để sửa property values, scopes hoặc definitions trước khi regular bean creation.

~~~java
@Bean
static BeanFactoryPostProcessor metadataCount() {
    return factory -> System.out.println(
            "BFPP | definitions=" + factory.getBeanDefinitionCount());
}
~~~

Đây là snippet cho một @Configuration. **static @Bean** giúp tránh tạo configuration instance sớm. Tránh gọi beanFactory.getBean("businessService") từ BFPP: có thể gây premature instantiation và bỏ qua một phần AOP/BeanPostProcessor.

### 7.3. BeanPostProcessor

BeanPostProcessor nhận từng instance trước/sau initialization. Nó dùng cho wrapping/proxy hoặc instrumentation framework; **không phải callback sau toàn bộ app startup**.

~~~java
@Bean
static BeanPostProcessor traceBeans() {
    return new BeanPostProcessor() {

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {

            if (bean instanceof MyTrackedType) {
                System.out.println("BPP | " + beanName);
            }
            return bean;
        }
    };
}
~~~

Đây là snippet cần một MyTrackedType và imports. BeanPostProcessors và những dependencies được tạo rất sớm có thể **không được auto-proxy đầy đủ**. Nếu viết BPP trong @Bean method, nên dùng static và ít dependencies khi có thể.

### 7.4. @PostConstruct: initialization cục bộ của một bean

Khi @PostConstruct chạy, injection cho chính bean đó đã được thực hiện, nhưng:

- Không có bảo đảm mọi bean khác đã được tạo.
- Không có bảo đảm ApplicationRunner đã chạy.
- Không nên thực hiện bước external I/O nặng chỉ vì method được gọi ở init.
- Lời gọi this.someAsyncMethod() hoặc this.transactionalMethod() có thể không đi qua Spring proxy, nhất là self-invocation.

Chọn @PostConstruct cho state/resource **thuộc bean**; cung cấp @PreDestroy/destroyMethod phù hợp.

### 7.5. SmartInitializingSingleton

SmartInitializingSingleton.afterSingletonsInstantiated chạy ở cuối giai đoạn tạo trước các regular singleton **không lazy**. Phù hợp nếu một bean cần kiểm tra/tổng hợp sau khi tập singleton eager thông thường đã được tạo.

Nó **không chứng minh các lazy singletons đã tạo**, không thay thế ApplicationRunner và không quản lý stop phase. Nếu đối tượng thực sự là long-running worker, chọn SmartLifecycle.

## 8. Sau refresh: started, runners, ready và readiness

### 8.1. ContextRefreshedEvent

ContextRefreshedEvent là mốc framework sau context refresh. Một ứng dụng nhiều contexts có thể thấy event propagation từ child sang parent. Listener chỉ làm việc cho một context cụ thể nên so sánh context gắn với event khi cần.

Không đồng nhất ContextRefreshedEvent với runners đã hoàn tất, vì các runners nằm sau refresh.

### 8.2. WebServerInitializedEvent

Khi dùng server.port=0, WebServerInitializedEvent giúp quan sát cổng thực tế của embedded server. Đây không phải dấu hiệu chắc chắn instance được load balancer cho nhận traffic, bởi runners/ready/availability có thể còn ở phía sau.

### 8.3. ApplicationStartedEvent

ApplicationStartedEvent đến sau refresh và trước ApplicationRunner/CommandLineRunner. Nó có thể dùng để quan sát container đã started, nhưng không được dùng để thông báo critical startup checks đã thành công.

### 8.4. ApplicationRunner và CommandLineRunner

Hai interface đều chạy trước Ready; khác nhau chủ yếu ở kiểu input arguments:

- ApplicationRunner dùng ApplicationArguments.
- CommandLineRunner nhận String... args.

Nếu có nhiều runners, Ordered/@Order có thể sắp thứ tự theo contract của Boot. Nhưng **@Order chỉ sắp thứ tự gọi run**, không chờ Future tự phát sinh bên trong runner.

### 8.5. ApplicationReadyEvent và ApplicationAvailability

ApplicationReadyEvent được gửi sau runners trong luồng thành công. ReadinessState.ACCEPTING_TRAFFIC được phát sau đó. Nếu listener Ready gửi một notification optional rồi fail, policy của việc đó nên tách riêng, không làm cả cluster restart chỉ vì một side task.

Với critical dependency động, health/readiness cần phản ánh khả năng phục vụ và runtime error handling; một startup probe thành công không bảo đảm remote online vĩnh viễn.

## 9. Dừng ứng dụng: completion ở shutdown

### 9.1. ContextClosedEvent là điểm bắt đầu

ContextClosedEvent được phát khi context bắt đầu đóng. Nó có thể cập nhật metrics, ngừng phát sinh công việc mới, nhưng **không chứng minh tất cả components và resources đã dừng**.

### 9.2. SmartLifecycle.start / stop và phase

SmartLifecycle tự khởi động theo isAutoStartup và lifecycle processor. Start phases đi từ **giá trị thấp lên cao**, stop phases đi **ngược lại**. Nếu có depends-on relationship, dependency graph có thể được ưu tiên hơn phase order.

**SmartLifecycle.stop(Runnable callback)** phải gọi callback **sau khi component đã dừng thực sự**. Không gọi ngay lúc mới submit lệnh drain, và không bỏ quên callback khiến shutdown chờ hết timeout phase.

Nếu component cần nhận việc sau một startup gate trong ApplicationRunner, lưu ý SmartLifecycle auto-start trong refresh có thể chạy **trước runner**. Khi đó phải dùng isAutoStartup=false hoặc một cơ chế gate rõ để không cho consumer nhận việc quá sớm.

### 9.3. @PreDestroy và destroyMethod

Chúng dùng để đóng file, socket, cache, executor, connection pool hoặc unregister callback do bean quản lý. Nếu một task đang chạy, shutdown() không luôn đồng nghĩa task đã hoàn tất; cần bounded awaitTermination/interrupt tùy chính sách.

Không chờ vô hạn trong @PreDestroy. Không dựa vào Java cleanup khi SIGKILL/crash. Một resource có thể được dọn hai lần qua nhiều cơ chế; close phải có tính idempotent hoặc ownership rõ.

### 9.4. Web graceful shutdown khác background worker drain

Với Spring Boot 3.3:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

giúp embedded web server drain HTTP in-flight khi context đóng. Tuy nhiên nó không tự đợi tất cả @Async/@Scheduled tasks, message consumers hoặc WebSocket streams lâu dài. Những component nền cần lifecycle riêng, và thời gian các phase phải phù hợp với termination grace của container.

## 10. Demo Maven/Java 17+ chọn đúng một hook cho từng việc

Bài thực hành gồm:

| Nhu cầu | API được dùng |
| --- | --- |
| Early notification | ApplicationEnvironmentPreparedEvent listener đăng ký trước run |
| Thêm fallback config | ApplicationContextInitializer + MapPropertySource.addLast |
| Quan sát metadata | Static @Bean BeanFactoryPostProcessor |
| Quan sát một bean instance | Static @Bean BeanPostProcessor |
| Khởi tạo state cục bộ | @PostConstruct |
| Sau eager singletons | SmartInitializingSingleton |
| Managed long-running lifecycle | SmartLifecycle |
| Gate công việc bắt buộc | ApplicationRunner đồng bộ |
| Quan sát started/ready | @EventListener ApplicationStartedEvent và ApplicationReadyEvent |
| Đóng context và resource | ContextClosedEvent, SmartLifecycle.stop, @PreDestroy |

Ứng dụng là **non-web CLI** để log rõ mốc. Khi SpringApplication.run hoàn thành, main chủ động đóng context bằng try-with-resources.

### 10.1. Cấu trúc

~~~text
lifecycle-choice-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/choice/LifecycleChoiceApplication.java
  src/test/java/com/example/choice/LifecycleChoiceApplicationTest.java
~~~

### 10.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>lifecycle-choice-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 10.3. application.properties

~~~properties
demo.name=from-file
demo.fail-on-startup=false
spring.main.web-application-type=none
~~~

Không có server HTTP. Các lệnh CLI có thể override cấu hình file bằng **--demo.name=from-cli** theo property precedence mặc định.

### 10.4. Java application hoàn chỉnh

Tạo **src/main/java/com/example/choice/LifecycleChoiceApplication.java**:

~~~java
package com.example.choice;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import jakarta.validation.constraints.NotBlank;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.MapPropertySource;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@SpringBootApplication(proxyBeanMethods = false)
@EnableConfigurationProperties(
        LifecycleChoiceApplication.DemoOptions.class)
public class LifecycleChoiceApplication {

    public static void main(String[] args) {
        SpringApplication app = newApplication();

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println(
                    "MAIN | run returned, now closing context");
        }
    }

    static SpringApplication newApplication() {
        SpringApplication app =
                new SpringApplication(LifecycleChoiceApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        app.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                        event -> System.out.println(
                                "EARLY | environment prepared"));

        app.addInitializers(
                (ApplicationContextInitializer<ConfigurableApplicationContext>)
                        context -> {
                            context.getEnvironment()
                                    .getPropertySources()
                                    .addLast(new MapPropertySource(
                                            "demoFallback",
                                            Map.of("demo.name", "fallback")));

                            System.out.println(
                                    "INITIALIZER | fallback registered");
                        });

        return app;
    }

    @Bean
    static BeanFactoryPostProcessor inspectMetadata() {
        return beanFactory -> System.out.println(
                "BFPP | definitions=" +
                beanFactory.getBeanDefinitionCount());
    }

    @Bean
    static BeanPostProcessor observeResource() {
        return new BeanPostProcessor() {

            @Override
            public Object postProcessAfterInitialization(
                    Object bean, String beanName) {

                if (bean instanceof DemoResource) {
                    System.out.println("BPP | resource initialized");
                }
                return bean;
            }
        };
    }

    @Bean
    ApplicationRunner mandatoryGate(
            DemoOptions options,
            DemoResource resource) {

        return args -> {
            System.out.println("RUNNER | required check started");

            if (options.failOnStartup()) {
                throw new IllegalStateException(
                        "Required startup check failed");
            }

            resource.markGatePassed();
            System.out.println("RUNNER | required check completed");
        };
    }

    @Validated
    @ConfigurationProperties(prefix = "demo")
    public record DemoOptions(
            @NotBlank String name,
            boolean failOnStartup) {
    }
}

@Component
class DemoResource implements SmartInitializingSingleton {

    private final LifecycleChoiceApplication.DemoOptions options;
    private final AtomicBoolean gatePassed = new AtomicBoolean();

    DemoResource(
            LifecycleChoiceApplication.DemoOptions options) {
        this.options = options;
    }

    @PostConstruct
    void initialize() {
        System.out.println(
                "BEAN | name=" + options.name());
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("SINGLETONS | eager beans ready");
    }

    void markGatePassed() {
        gatePassed.set(true);
    }

    boolean isGatePassed() {
        return gatePassed.get();
    }

    @EventListener
    void onStarted(ApplicationStartedEvent event) {
        System.out.println("STARTED | before runners");
    }

    @EventListener
    void onReady(ApplicationReadyEvent event) {
        System.out.println(
                "READY | gatePassed=" + gatePassed.get());
    }

    @EventListener
    void onClosing(ContextClosedEvent event) {
        System.out.println("CLOSING | context closing");
    }

    @PreDestroy
    void destroy() {
        System.out.println("DESTROY | DemoResource");
    }
}

@Component
class DemoLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        System.out.println("LIFECYCLE | started");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running = false;
            System.out.println("LIFECYCLE | stopped");
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

### 10.5. Giải thích và giới hạn của demo

- **@EnableConfigurationProperties** đăng ký nested record DemoOptions; @NotBlank được thực thi nhờ validation starter.
- **newApplication()** gắn early listener/initializer trước run. Không có @Component nào được trông đợi nhận lại early event.
- **MapPropertySource.addLast** cung cấp fallback, không ghi đè application.properties.
- **static @Bean BFPP và BPP** tránh làm @Configuration class tạo quá sớm.
- BFPP chỉ quan sát definition count; BPP chỉ quan sát DemoResource sau initialization, trả lại cùng object.
- **@PostConstruct** chỉ dùng giá trị đã inject; **SmartInitializingSingleton** quan sát mốc eager singleton.
- **SmartLifecycle** auto-start trong refresh, stop khi context.close() chạy. Callback được gọi trong finally sau khi ví dụ đặt running=false; ứng dụng thật cần kết thúc resource thực sự rồi mới báo callback.
- **ApplicationRunner** là gate đồng bộ: nếu failOnStartup=true thì throw, nếu false thì đánh dấu gate passed.
- **@EventListener(ApplicationReadyEvent)** nhìn thấy gatePassed=true sau runner thành công.
- **Try-with-resources** gọi close sau run để minh họa shutdown, không phù hợp đặt ngay sau run của một web service chạy lâu dài.
- Program không tạo background thread dài hạn, vì vậy việc main kết thúc và dừng context có chủ ý.

### 10.6. Build và chạy

~~~bash
java -version
mvn -q -DskipTests package
java -jar target/lifecycle-choice-demo-1.0.0.jar
~~~

**Cần Java 17+ và Maven tương thích.** Spring Boot có thể in log riêng, nên chỉ xét các marker của ví dụ. Theo contract lifecycle, các marker quan trọng xuất hiện theo thứ tự khái quát:

~~~text
EARLY | environment prepared
INITIALIZER | fallback registered
BFPP | definitions=...
BEAN | name=from-file
BPP | resource initialized
SINGLETONS | eager beans ready
LIFECYCLE | started
STARTED | before runners
RUNNER | required check started
RUNNER | required check completed
READY | gatePassed=true
MAIN | run returned, now closing context
CLOSING | context closing
LIFECYCLE | stopped
DESTROY | DemoResource
~~~

Dấu ba chấm ở definition count không phải output số cố định; số lượng phụ thuộc Spring Boot auto-configuration. **Không assert nguyên văn stdout** vì logs framework có thể xen kẽ.

Hai marker quan trọng để chứng minh runner gate là:

~~~text
RUNNER | required check completed
READY | gatePassed=true
~~~

Đầu tiên phải có completion của bước bắt buộc; sau đó mới tới ReadyEvent.

### 10.7. CLI override và failure path

Override tên:

~~~bash
java -jar target/lifecycle-choice-demo-1.0.0.jar \
  --demo.name=from-cli
~~~

Dòng bean init có giá trị:

~~~text
BEAN | name=from-cli
~~~

Làm runner fail:

~~~bash
java -jar target/lifecycle-choice-demo-1.0.0.jar \
  --demo.fail-on-startup=true
~~~

Dòng runner có thể tới:

~~~text
RUNNER | required check started
~~~

sau đó ném IllegalStateException với message **Required startup check failed**. Đường startup thành công **không phát READY | gatePassed=true**. Các callback cleanup có thể được gọi khi Spring xử lý thất bại; không gán một stack trace/log ordering cuối tuyệt đối cho mọi failure path.

## 11. JUnit 5: kiểm chứng thứ tự thật, không sleep

Tạo **src/test/java/com/example/choice/LifecycleChoiceApplicationTest.java**:

~~~java
package com.example.choice;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LifecycleChoiceApplicationTest {

    @Test
    void startedThenReadyAfterRequiredRunner() {
        List<String> events = new CopyOnWriteArrayList<>();

        SpringApplication app =
                LifecycleChoiceApplication.newApplication();

        app.addListeners(
                (ApplicationListener<ApplicationStartedEvent>)
                        event -> events.add("STARTED"));

        app.addListeners(
                (ApplicationListener<ApplicationReadyEvent>)
                        event -> events.add("READY"));

        try (ConfigurableApplicationContext context =
                     app.run(
                             "--demo.name=test",
                             "--demo.fail-on-startup=false")) {

            assertEquals(List.of("STARTED", "READY"), events);
            assertTrue(
                    context.getBean(DemoResource.class)
                            .isGatePassed());
        }
    }

    @Test
    void failedRunnerNeverPublishesSuccessfulReady() {
        AtomicBoolean ready = new AtomicBoolean();
        AtomicBoolean failed = new AtomicBoolean();

        SpringApplication app =
                LifecycleChoiceApplication.newApplication();

        app.addListeners(
                (ApplicationListener<ApplicationReadyEvent>)
                        event -> ready.set(true));

        app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>)
                        event -> failed.set(true));

        assertThrows(RuntimeException.class,
                () -> app.run(
                        "--demo.name=test",
                        "--demo.fail-on-startup=true"));

        assertFalse(ready.get());
        assertTrue(failed.get());
    }

    @Test
    void configDataOverridesInitializerFallback() {
        SpringApplication app =
                LifecycleChoiceApplication.newApplication();

        try (ConfigurableApplicationContext context =
                     app.run("--demo.fail-on-startup=false")) {

            assertEquals(
                    "from-file",
                    context.getEnvironment()
                            .getProperty("demo.name"));
        }
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Những điều test xác minh:**

1. **Started đến trước Ready**, và lúc Ready, startup runner đã hoàn thành bước gate.
2. Runner thất bại không tạo **successful ApplicationReadyEvent**, Spring phát ApplicationFailedEvent trong đường lỗi startup.
3. Property **demo.name=from-file** thắng fallback của initializer, vì fallback được thêm với precedence thấp.

Các test dùng SpringApplication thật, không phải ApplicationContextRunner giả lập tất cả lifecycle events. **SpringApplication.run là lời gọi đồng bộ**, nên listener đã ghi sự kiện xong khi run return thành công; không cần chờ một số mili-giây tùy ý.

**Giới hạn:** Đây chưa phải kiểm thử một remote API thật, shutdown SIGTERM/container hay load balancer readiness. Các lớp đó cần integration/process-level test riêng.

## 12. Bảng tình huống thực tế: chọn API và completion đúng

| Bài toán | Điểm mở rộng nên chọn | Lý do và điều kiện |
| --- | --- | --- |
| Nạp mặc định cấu hình thấp ưu tiên | EnvironmentPostProcessor / ContextInitializer | Cần Environment, không cần bean; dùng addLast |
| Cấu hình nguồn secret phục vụ Config Data | BootstrapRegistryInitializer hoặc SPI config integration | Cần chạy trước runtime bean graph |
| Thêm bean definition từ feature registry | BeanDefinitionRegistryPostProcessor | Can thiệp blueprint trước instantiation |
| Sửa metadata property values của beans | BeanFactoryPostProcessor | Không tạo business service sớm |
| Wrap một nhóm beans để đo metrics | BeanPostProcessor hoặc AOP | Per-instance instrumentation |
| Kiểm tra tham số của chính bean | @PostConstruct / initMethod | Bean-local invariant; có @PreDestroy nếu giữ resource |
| Tổng hợp trạng thái sau eager singleton phase | SmartInitializingSingleton | Không làm lazy beans eager ngoài ý muốn |
| Ghi log context đã refresh | ContextRefreshedEvent | Không nhận định runners đã xong |
| Biết port nhúng ngẫu nhiên | WebServerInitializedEvent | ServerInitialized khác Readiness |
| Kiểm tra schema bắt buộc trước traffic | Flyway/Liquibase hoặc custom Runner đồng bộ | Gate rõ; dependency DB đã inject |
| Check remote critical trước ready | ApplicationRunner có timeout, fail-fast policy | Chờ completion thật; phối hợp readiness |
| Bắt đầu Kafka consumer cần stop có thứ tự | SmartLifecycle | Phased start/stop/callback |
| Gửi optional notification đã ready | ApplicationReadyEvent | Không biến async notification thành startup gate |
| Đánh dấu unready khi remote lỗi runtime | ApplicationAvailability / HealthIndicator | Trạng thái động, không chỉ startup event |
| Ngừng HTTP mới và drain request cũ | Graceful web shutdown | Kết hợp load balancer/readiness, không chỉ @PreDestroy |
| Dừng job nền và đợi ack có hạn | SmartLifecycle.stop(Runnable) | Callback sau stop thật, deadline rõ |
| Đóng unmanaged socket/file/executor | @PreDestroy / destroyMethod | Ownership và cleanup idempotent |
| Trả process exit code cho batch | ExitCodeGenerator / SpringApplication.exit | CLI process semantics, không phải web readiness |

### 12.1. Database startup task

Nếu migration schema thực sự là yêu cầu, ưu tiên framework integration như Flyway/Liquibase. Nếu phải custom kiểm tra một invariant sau khi repository/DB đã ready, ApplicationRunner đồng bộ có thể phù hợp.

Không chạy repository trong EnvironmentPostProcessor hoặc BFPP. Không submit một migration task trong @Async rồi return runner, vì ReadyEvent có thể được phát trước commit.

### 12.2. Cache warm-up

- **Cache của một bean, nhỏ và nội bộ:** @PostConstruct có thể đúng.
- **Cache từ nhiều service, bắt buộc trước traffic:** Runner đồng bộ hoặc đợi Future trong Runner.
- **Cache optional làm nóng dần:** ApplicationReadyEvent hoặc managed background component, có fallback.
- **Cache cần refresh liên tục:** SmartLifecycle/@Scheduled hay hạ tầng chuyên biệt, với shutdown policy rõ.

Không chọn hook chỉ từ danh từ “cache”; cần biết thời điểm sử dụng và tính bắt buộc.

### 12.3. Consumer phải bắt đầu sau gate

SmartLifecycle auto-start thường chạy trong refresh **trước runners**. Nếu consumer không được lấy message trước khi runner kiểm tra remote xong, không thể chỉ giả định phase cao sẽ khiến nó start sau ApplicationRunner.

Có thể đặt **isAutoStartup=false** và start có kiểm soát sau gate, hoặc dùng một readiness/gate state trong component, tùy nghiệp vụ. Đừng để consumer phục vụ message trước khi hệ thống đã bảo đảm các invariant bắt buộc.

### 12.4. Logging property từ nguồn tùy biến

Một @PropertySource chỉ được thêm khi context refresh có thể quá muộn để cấu hình một số logging.* hoặc spring.main.* đã được đọc ở giai đoạn sớm hơn. Cần EnvironmentPostProcessor hoặc Boot-supported configuration path đúng ordering.

Đừng “sửa” bằng ReadyEvent hoặc @PostConstruct vì không thể đảm bảo áp dụng ngược các quyết định đã thực hiện.

### 12.5. Cleanup nhiều lớp

Một web app có thể cần:

- Readiness chuyển sang từ chối traffic.
- Embedded server graceful drain HTTP requests.
- Consumer dừng nhận message mới.
- Consumer hoàn tất in-flight jobs.
- Executor/datasource đóng sau khi không còn bị dùng.
- @PreDestroy giải phóng resource cuối.

Sử dụng phase/dependency ordering phù hợp; không tạo một @PreDestroy duy nhất với Thread.sleep vô hạn để trì hoãn toàn bộ tiến trình.

## 13. Ordering và dependency: ba cơ chế khác nhau

| Cơ chế | Điều nó sắp thứ tự | Điều nó không bảo đảm |
| --- | --- | --- |
| **Ordered / @Order** | Runners, listeners, processors trong phạm vi framework áp dụng | Async task bên trong đã complete |
| **@DependsOn** | Bean creation/destruction dependency | HTTP call hoặc job đã hoàn tất |
| **SmartLifecycle.getPhase()** | Start phase thấp tới cao, stop ngược | Có ReadyEvent hay external readiness |
| **Event dispatch mặc định đồng bộ** | Listener được gọi theo publisher | Nếu @Async/multicaster đổi mode thì không còn completion barrier |
| **Future/CompletionStage** | Completion của một task cụ thể | Thay thế bean definitions/ordering |

Nếu một runner có @Order ưu tiên cao nhưng chỉ submit task rồi return, một runner tiếp theo vẫn có thể sử dụng dữ liệu chưa sẵn sàng. **Order không biến async thành sync.**

Nếu một bean B depends on bean A, B được khởi tạo sau A, nhưng A.@PostConstruct có thể mới submit một job; không có guarantee công việc đó đã complete. Phải có completion contract riêng.

## 14. Chính sách thất bại: fail-fast hay degrade?

| Mốc phát hiện lỗi | Hệ quả thường thấy khi exception không được xử lý | Lựa chọn hợp lý |
| --- | --- | --- |
| Environment/config processing | Startup thất bại sớm | Fail-fast khi nguồn cấu hình bắt buộc sai |
| ContextInitializer | Không tiếp tục tạo context bình thường | Fail-fast cho context invariant |
| BFPP/BDRPP | Context refresh thất bại | Phát hiện metadata sai; tránh network side effects |
| BPP / @PostConstruct | Bean creation/refresh thất bại | Bean invariant/initialization |
| SmartInitializingSingleton | Refresh thất bại | Eager singleton invariant |
| SmartLifecycle.start | Refresh/startup có thể thất bại | Kiểm soát partial start và cleanup |
| ApplicationRunner | Startup thất bại sau refresh, trước Ready | Critical startup gate |
| ApplicationReadyEvent listener | Có thể ảnh hưởng run nếu synchronous listener ném lỗi | Không chọn làm gate; async work cần error policy riêng |
| SmartLifecycle.stop | Lỗi hoặc timeout khi shutdown | Báo lỗi, callback theo contract, bounded cleanup |
| @PreDestroy | Lỗi trong destruction | Không tự đảm bảo hoàn tất mọi task/background resources |

Fail-fast hợp lý khi thiếu config hoặc remote critical sẽ khiến mọi request cốt lõi không chạy. Với remote optional, degraded mode có monitoring có thể tốt hơn fail toàn hệ thống. Dù đã check trước ready, runtime vẫn phải xử lý remote outages.

**Một lưu ý bảo mật:** callback sớm có thể đọc secrets/credentials. Không log toàn bộ Environment hoặc expose /env, /configprops không bảo vệ để debug.

## 15. Kiểm thử theo đúng tầng của extension point

### 15.1. Unit test

Nếu logic chỉ là chọn config value, kiểm tra URI syntax hoặc tính toán phase, unit test Java thuần thường đủ. Không cần khởi động full SpringApplication.

### 15.2. ApplicationContextRunner

Khi kiểm tra @ConfigurationProperties binding, auto-configuration conditions hoặc BFPP/BPP đơn giản, ApplicationContextRunner tạo context nhỏ và dễ kiểm tra dependency graph.

Nhưng **ApplicationContextRunner không mặc nhiên phát toàn bộ chuỗi sự kiện SpringApplication**, nên không dùng nó để kết luận ReadyEvent diễn ra đúng mốc.

### 15.3. SpringApplication integration test

Khi kiểm chứng Started → Runner → Ready và failure path, dùng SpringApplication.run thực, register listeners trước run, như mục 11. Không đăng ký @Component listener sau thời điểm early event đã qua.

### 15.4. Async lifecycle test

Với SmartLifecycle.stop(Runnable), cần phân biệt ba tín hiệu:

~~~text
stopRequested
       |
       +-- đang drain
       |
stopCallbackCompleted
       |
ApplicationContext.close() returned
~~~

Dùng CountDownLatch.await(timeout) hoặc Future.get(timeout) để chờ mốc, không dùng Thread.sleep cố định. Test phải release gate trong finally và cleanup executor/threads nếu assertion thất bại.

### 15.5. Process-level test

Một test đóng context chứng minh Spring lifecycle callbacks. Nó **không tự chứng minh**:

- SIGTERM được chuyển đúng qua container entrypoint.
- Kubernetes ngừng định tuyến đúng thời gian.
- WebServer graceful drain request HTTP trên network thật.
- SIGKILL vẫn chạy @PreDestroy (không bảo đảm).

Những yêu cầu này cần integration/process/container test ở môi trường tương ứng và deadline tổng rõ.

## 16. Bài tập lựa chọn kèm đáp án

**Bài 1.** Một thư viện cần thêm fallback property nhưng không ghi đè application.properties.

**Đáp án:** EnvironmentPostProcessor đăng ký đúng cách, sử dụng property source ưu tiên thấp (addLast), hoặc ContextInitializer cho trường hợp một application cụ thể.

**Bài 2.** Đăng ký một bean type động từ feature metadata, trước dependency injection.

**Đáp án:** BeanDefinitionRegistryPostProcessor hoặc registrar/import SPI chuyên biệt.

**Bài 3.** Wrap các bean implement một interface để instrumentation.

**Đáp án:** BeanPostProcessor hoặc Spring AOP SPI thích hợp; BFPP không sửa runtime instance.

**Bài 4.** Kiểm tra gateway thanh toán bắt buộc online trước readiness.

**Đáp án:** Runner đồng bộ có bounded timeout; throw nếu fail theo policy. Runtime vẫn cần timeout/retry và readiness khi dependency lỗi sau startup.

**Bài 5.** Dừng consumer, chờ ack và gọi callback sau khi drain.

**Đáp án:** SmartLifecycle.stop(Runnable), phase/depends-on đúng, bounded stop.

**Bài 6.** Thông báo telemetry optional sau khi app khởi động xong.

**Đáp án:** ApplicationReadyEvent listener hoặc observability integration; không coi async listener như startup gate.

**Bài 7.** Biết cổng server nhúng khi dùng server.port=0.

**Đáp án:** WebServerInitializedEvent hoặc test API phù hợp. ApplicationStartingEvent quá sớm.

**Bài 8.** Xác nhận tập non-lazy singleton đã pre-instantiated.

**Đáp án:** SmartInitializingSingleton; không tự coi lazy singleton đã có.

**Bài 9.** Đóng một custom executor do bean tự tạo.

**Đáp án:** @PreDestroy/destroyMethod có bounded shutdown; nếu cần phối hợp phase và callback, SmartLifecycle.

**Bài 10.** Chạy migration bắt buộc bên trong controller @PostConstruct được không?

**Đáp án:** Không nên. Ưu tiên Flyway/Liquibase; nếu custom, startup gate đồng bộ sau dependencies, không phụ thuộc controller init.

**Bài 11.** Một consumer SmartLifecycle có được chắc chắn bắt đầu sau runner không?

**Đáp án:** Không. Auto-start thường ở refresh, trước runners. Cần isAutoStartup=false hoặc gate theo policy.

**Bài 12.** Đặt @Order cho runner gọi executor rồi cho rằng cache sẵn sàng?

**Đáp án:** Không. Order sắp xếp invocation, không chờ async completion.

**Bài 13.** Dùng ContextClosedEvent để assert @PreDestroy đã chạy xong?

**Đáp án:** Không. Event chỉ đánh dấu context đang đóng; destruction diễn ra sau đó trong đường bình thường.

**Bài 14.** Dùng @Component @EventListener để nghe ApplicationEnvironmentPreparedEvent?

**Đáp án:** Không đáng tin, vì bean chưa tồn tại. Register early listener trước run hoặc qua spring.factories.

## 17. Các lỗi lựa chọn phổ biến

### 17.1. Dùng ApplicationReadyEvent để chỉnh Environment cần trước bean binding

Quá muộn; properties có thể đã được tiêu thụ. Chọn điểm xử lý Environment sớm hơn.

### 17.2. Dùng BeanFactoryPostProcessor để gọi repository

Không có bean graph ổn định, có nguy cơ premature bean creation và bỏ qua post-processing.

### 17.3. Dùng BeanPostProcessor như một hook “sau khi mọi bean xong”

Nó chạy cho từng instance. SmartInitializingSingleton, runner hoặc lifecycle event mới có semantics mốc phù hợp.

### 17.4. Dùng @PostConstruct làm custom global startup task

Bean-local initialization khác ứng dụng đã sẵn sàng. Với critical work cần tất cả services, runner thường rõ hơn.

### 17.5. Dùng ApplicationStartedEvent để công bố startup gate hoàn tất

Started trước runners. Không suy ra bước cần thiết trong runner đã xong.

### 17.6. Dùng @Async Ready listener cho công việc bắt buộc

Async listener có thể chưa hoàn tất khi readiness đã được công bố. Dùng completion gate đúng.

### 17.7. Gọi SmartLifecycle.stop callback ngay sau khi submit drain

Context có thể đóng dependencies khi component vẫn đang dùng chúng. Callback chỉ phát sau stop thật.

### 17.8. Không gọi callback và để lifecycle processor chờ timeout

Shutdown bị kéo dài, thậm chí trông như treo. Thiết kế bounded stop và callback semantics rõ.

### 17.9. Tin @PreDestroy luôn chạy sau SIGKILL

Không. Hard kill không cho Java callbacks hoàn tất. Công việc quan trọng cần persistence/recovery.

### 17.10. Dùng static global state không có ownership

Context hierarchy/DevTools restart có thể tạo nhiều context trong một JVM. Global state dễ giữ classloader cũ và duplicate callbacks.

### 17.11. Dùng Thread.sleep để sửa race giữa runner và background worker

Chỉ dự đoán scheduling; dùng Future/latch/completion signal với timeout.

### 17.12. Dùng cùng một default cho mọi remote dependency

Critical và optional có chính sách fail-fast/degrade khác nhau. Không làm cả cluster restart vô ích khi một service phụ tạm lỗi.

## 18. Checklist trước khi chọn điểm mở rộng

- [ ] Đã viết rõ thời điểm cần chạy và điều kiện phải hoàn tất.
- [ ] Đã liệt kê dependency thực sự có tại thời điểm đó.
- [ ] Phân biệt metadata với runtime bean instance.
- [ ] Early listener được đăng ký trước SpringApplication.run.
- [ ] PropertySource có precedence/order được chủ động lựa chọn.
- [ ] Không lấy business bean trong EnvironmentPostProcessor/Initializer/BFPP.
- [ ] BFPP/BPP @Bean methods dùng static khi thích hợp để hạn chế eager references.
- [ ] @PostConstruct chỉ quản lý bean-local initialization.
- [ ] SmartInitializingSingleton không đồng nghĩa lazy beans hay ready.
- [ ] SmartLifecycle có start/stop policy và phase rõ.
- [ ] Runner phải thật sự chờ critical task trước khi return.
- [ ] Async task có timeout, cancellation/error handling nếu quan trọng.
- [ ] ReadyEvent chỉ được coi là quan sát sau runners, không là async gate.
- [ ] Readiness và web server socket được phân biệt.
- [ ] ContextClosedEvent không được coi là cleanup hoàn tất.
- [ ] @PreDestroy/destroyMethod có owner và bounded cleanup.
- [ ] Đã hiểu khác biệt @Order, @DependsOn và getPhase.
- [ ] Tests dùng events/completion signal thay vì sleep cố định.
- [ ] Có integration test cho startup failure path và shutdown.
- [ ] Container shutdown budget phù hợp từng lifecycle phase.
- [ ] Secrets được che khỏi logs/diagnostics.
- [ ] Ưu tiên SPI chuyên biệt của framework thay vì global custom hook nếu có.

## 19. Câu hỏi tự kiểm tra

**1.** EnvironmentPostProcessor có inject được JPA repository không?

**Đáp án:** Không nên; application beans chưa tồn tại ở giai đoạn đó.

**2.** Khi initializer chạy, bean definitions ứng dụng đã được load hết chưa?

**Đáp án:** Chưa theo vòng đời chuẩn, initializer chạy trước definitions.

**3.** BeanFactoryPostProcessor nên làm việc với metadata hay instance?

**Đáp án:** Metadata. BeanPostProcessor xử lý instances.

**4.** @PostConstruct của một bean có chứng minh mọi singleton đã tạo xong?

**Đáp án:** Không. SmartInitializingSingleton là mốc sau regular eager singleton pre-instantiation.

**5.** ApplicationStartedEvent xảy ra trước hay sau runners?

**Đáp án:** Trước.

**6.** ApplicationReadyEvent xảy ra trước hay sau runners?

**Đáp án:** Sau trong luồng startup thành công thông thường.

**7.** ReadyEvent đã phát có nghĩa mọi background task do runner submit đã xong?

**Đáp án:** Không, trừ khi runner thực sự chờ chúng trước khi return.

**8.** getPhase của SmartLifecycle điều khiển thứ tự nào?

**Đáp án:** Start thấp đến cao và stop ngược; dependency tường minh có thể được ưu tiên.

**9.** Có thể dùng WebServerInitializedEvent làm bằng chứng readiness nhận traffic?

**Đáp án:** Không. Server có thể mở socket trước runners/ReadinessState.

**10.** ContextClosedEvent có bảo đảm destroy callback đã hoàn tất?

**Đáp án:** Không; event đánh dấu bắt đầu close.

**11.** SmartLifecycle.stop(Runnable) nên gọi callback lúc nào?

**Đáp án:** Sau khi component đã hoàn thành stop theo hợp đồng; không phải ngay khi chỉ mới submit một task.

**12.** @Order giúp một Future từ runner thứ nhất complete trước runner thứ hai?

**Đáp án:** Không, trừ khi runner đầu chủ động chờ completion.

**13.** Dùng @PreDestroy có đủ cho một task không được phép mất khi SIGKILL không?

**Đáp án:** Không. Cần durable queue/checkpoint/transaction và recovery.

**14.** Khi remote chỉ phục vụ tính năng phụ, có luôn nên fail startup không?

**Đáp án:** Không. Cân nhắc degraded startup và runtime resilience theo nghiệp vụ.

## 20. Tổng kết

Lập bảng chọn extension point tốt phải kết hợp **ba trục**: khi nào được gọi, dependency nào đã sẵn sàng và mức completion Spring hoặc ứng dụng phải bảo đảm.

- **Trước beans:** BootstrapRegistryInitializer, EnvironmentPostProcessor, ApplicationContextInitializer.
- **Trong container refresh:** BeanDefinitionRegistryPostProcessor, BeanFactoryPostProcessor, BeanPostProcessor, @PostConstruct, SmartInitializingSingleton.
- **Sau refresh nhưng trước Ready:** ApplicationStartedEvent để quan sát; ApplicationRunner/CommandLineRunner cho **mandatory startup work đồng bộ**.
- **Sau runners:** ApplicationReadyEvent và trạng thái availability.
- **Long-running component:** SmartLifecycle với phase và stop callback.
- **Shutdown/destroy:** ContextClosedEvent để biết bắt đầu; SmartLifecycle.stop để drain và @PreDestroy/destroyMethod để giải phóng cuối.

Một thiết kế đúng phải trả lời được: **callback đến khi nào, có những dependency gì, có đợi hoàn tất không, fail sẽ ảnh hưởng startup/readiness như thế nào và dừng ra sao**. Dùng ma trận này trước khi thêm bất kỳ hook mới nào vào ứng dụng.

## 21. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — SpringApplication Events, Runners và Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Customize Environment/ApplicationContext Before It Starts: https://docs.spring.io/spring-boot/3.3/how-to/application.html
- Spring Boot 3.3 — EnvironmentPostProcessor API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.3 — ApplicationContextInitializedEvent API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html
- Spring Framework 6.1 — BeanFactoryPostProcessor và BeanPostProcessor: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework 6.1 — SmartInitializingSingleton: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework 6.1 — SmartLifecycle và callback: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework — Bean Lifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html