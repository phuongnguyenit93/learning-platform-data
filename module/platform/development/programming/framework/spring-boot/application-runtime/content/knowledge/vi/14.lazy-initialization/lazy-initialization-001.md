# Khởi tạo lười là gì và thay đổi thời điểm tạo bean như thế nào?

## Mục tiêu học tập

Trong Spring Boot, **khởi tạo lười** (*lazy initialization*) là cơ chế trì hoãn việc **tạo và khởi tạo một bean** cho tới khi bean đó thực sự được yêu cầu, thay vì nhất thiết tạo sẵn trong lúc `ApplicationContext.refresh()`. Khái niệm này dễ bị nhầm với singleton scope, proxy, dependency injection và việc nạp class của JVM.

Bài học thuộc **Spring Boot Application Runtime → Khởi tạo lười**, minh họa bằng Java 17+ và Spring Boot 3.3.x. Sau bài này, bạn sẽ:

1. Giải thích phân biệt **eager initialization** với **lazy initialization** và biết việc chúng ảnh hưởng đến thời điểm chạy constructor, inject dependency, `@PostConstruct` và các callback khác.
2. Phân biệt **scope** (`singleton`, `prototype`, request scope...) với **chiến lược thời điểm khởi tạo**.
3. Cấu hình `@Lazy` ở `@Component`, `@Bean`, `@Configuration` và tại injection point; hiểu rõ sự khác nhau.
4. Bật lazy toàn ứng dụng bằng `spring.main.lazy-initialization=true` hoặc `SpringApplication.setLazyInitialization(true)` và chủ động giữ một số bean eager qua `@Lazy(false)`.
5. Hiểu vì sao một singleton eager phụ thuộc trực tiếp vào singleton lazy có thể khiến bean lazy **vẫn bị tạo lúc startup**.
6. Viết, chạy và quan sát một ví dụ Spring Boot có eager bean, lazy bean được yêu cầu muộn, một bean không bao giờ được dùng và callback hủy khi đóng context.
7. Đánh giá lợi/hại của lazy initialization với startup time, first-request latency, readiness, lỗi phát hiện muộn, memory và tài nguyên.

**Nguyên tắc xuyên suốt:** `@Lazy` là một lời hướng dẫn về **khi nào bean được khởi tạo**, không phải lời hứa tuyệt đối rằng bean sẽ chỉ được tạo sau `ApplicationReadyEvent`, cũng không phải một cách tự động làm code đa luồng an toàn.

## 1. Eager và lazy: khác nhau ở thời điểm, không phải tên class

Theo mặc định, Spring `ApplicationContext` thường tạo và cấu hình các bean **singleton không đánh dấu lazy** trong lúc refresh context. Đây gọi là **eager initialization** (*khởi tạo không trì hoãn*). Cách này làm startup có thêm công việc, nhưng giúp phát hiện sớm lỗi constructor, dependency và cấu hình.

**Lazy initialization** trì hoãn việc tạo bean cho đến khi một thao tác thực sự cần nó: chẳng hạn một bean khác yêu cầu dependency, `context.getBean(...)` được gọi, một proxy được sử dụng hoặc logic ứng dụng lấy bean qua `ObjectProvider`.

Ví dụ khai báo bằng Java:

~~~java
@Component
public class LocalCatalog {
    public LocalCatalog() {
        System.out.println("LocalCatalog created");
    }
}
~~~

~~~java
@Component
@Lazy
public class HeavyReportEngine {
    public HeavyReportEngine() {
        System.out.println("HeavyReportEngine created");
    }
}
~~~

Đây là **hai đoạn minh họa** (cần imports `Component`/`Lazy` và project có component scanning), không phải các file cần thêm vào ví dụ hoàn chỉnh ở mục 7.

Nếu `LocalCatalog` là singleton bình thường, container có thể tạo nó trong refresh dù không có dòng ứng dụng nào gọi trực tiếp `new LocalCatalog()`. Với `HeavyReportEngine`, container có thể để việc khởi tạo lại tới khi một bên yêu cầu bean. **Tuy nhiên**, nếu `LocalCatalog` cần `HeavyReportEngine` trong constructor, Spring vẫn có lý do khởi tạo `HeavyReportEngine` sớm để thỏa mãn dependency.

### Hình dung dòng thời gian

~~~text
Không sử dụng lazy:
SpringApplication.run()
    |
    +-- ApplicationContext.refresh()
    |      +-- tạo EagerA
    |      +-- tạo HeavyReportEngine
    |      +-- chạy @PostConstruct của cả hai
    |
    +-- runners
    +-- ApplicationReadyEvent
    +-- lần gọi nghiệp vụ đầu tiên: dùng bean đã có

Sử dụng lazy cho HeavyReportEngine, không bị bean eager nào kéo tạo sớm:
SpringApplication.run()
    |
    +-- ApplicationContext.refresh()
    |      +-- tạo EagerA
    |      +-- chưa tạo HeavyReportEngine
    |
    +-- runners
    +-- ApplicationReadyEvent
    |
    +-- lần yêu cầu HeavyReportEngine đầu tiên
           +-- tạo instance, inject, initialize
           +-- chạy @PostConstruct
           +-- thực hiện nghiệp vụ
~~~

Sơ đồ minh họa trường hợp thông thường; ở runtime thực tế, hạ tầng framework, dependency graph và cấu hình ứng dụng có thể làm thời điểm cụ thể khác nhau. Không suy diễn rằng mọi bean lazy đều chắc chắn đợi HTTP request đầu tiên.

### Bảng so sánh nhanh

| Đặc điểm | Eager singleton mặc định | Lazy singleton |
| --- | --- | --- |
| Scope | `singleton` | Vẫn là `singleton` |
| Thời điểm dự kiến tạo | Pha refresh khi pre-instantiate | Lúc có nhu cầu thực tế |
| Constructor | Thường chạy trong startup | Có thể chạy sau startup |
| Inject dependency, BeanPostProcessor, init callback | Khi eager bean được tạo | Khi lazy bean thực sự được tạo |
| Có thể bị lỗi lúc startup | Có | Có nếu bị dependency yêu cầu sớm; nếu không, lỗi có thể xuất hiện muộn |
| Có sẵn trước request đầu? | Thường có | Không bảo đảm |
| Chi phí thời gian ban đầu | Cao hơn nếu nhiều bean nặng | Có thể thấp hơn |
| Chi phí lần dùng đầu | Thường không gồm khởi tạo bean đó | Có thể gồm constructor/init/dependency |
| Số instance do Spring giữ cho một bean definition singleton | Thường một trong mỗi container | Thường một trong mỗi container |

## 2. Singleton scope không có nghĩa eager initialization

Scope `singleton` mặc định của Spring có nghĩa **một instance được quản lý cho một bean definition trong một Spring container**. Nó không có nghĩa một object duy nhất cho toàn bộ JVM, mọi classloader hoặc mọi `ApplicationContext`.

Ví dụ:

~~~java
@Bean
@Lazy
PriceCalculator priceCalculator() {
    return new PriceCalculator();
}
~~~

Dù bean `priceCalculator` là lazy, scope của nó mặc định vẫn là `singleton`. Lần yêu cầu đầu có thể tạo một `PriceCalculator`; những lần yêu cầu tiếp theo từ **cùng container** thường nhận chính instance đã được cache.

Điều này khác:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
PriceCalculator priceCalculator() {
    return new PriceCalculator();
}
~~~

Đoạn trên là minh họa một **prototype bean**, chưa phải file chạy độc lập; cần các import tương ứng. Với prototype scope, container tạo instance mới theo mỗi lần lookup phù hợp. Việc dùng `@Lazy` không biến singleton thành prototype; việc dùng `@Scope("prototype")` cũng không biến prototype thành singleton.

Nếu hai context khác nhau cùng có bean definition `priceCalculator`, mỗi context có thể có một singleton riêng. Với một object tự tạo qua `new PriceCalculator()` ngoài Spring, container không tự quản lý vòng đời của object đó.

### Bảng tách hai trục suy nghĩ

| Trục | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Scope** | Bean được chia sẻ/tạo bao nhiêu lần và trong phạm vi nào? | singleton, prototype, request |
| **Initialization strategy** | Bean instance thường được tạo ở giai đoạn nào? | eager hoặc lazy |
| **Dependency resolution** | Thành phần nào làm container cần bean? | constructor injection, `getBean`, provider |
| **Lifecycle** | Callback nào chạy lúc bean được tạo/hủy? | `@PostConstruct`, `@PreDestroy` |
| **Runtime execution** | Phương thức nghiệp vụ chạy khi nào? | Trong runner hoặc mỗi HTTP request |

Một singleton eager có thể được tạo sẵn nhưng **không thực thi phương thức nghiệp vụ** nếu chẳng ai gọi nó. Một singleton lazy có thể tạo muộn và được tái dùng trong hàng nghìn request tiếp theo. Khởi tạo và thực thi nghiệp vụ là hai việc khác nhau.

## 3. Spring tạo singleton mặc định ở bước nào?

Trong Spring Framework, `AbstractApplicationContext.refresh()` xử lý nhiều giai đoạn như chuẩn bị BeanFactory, gọi `BeanFactoryPostProcessor`, đăng ký `BeanPostProcessor`, chuẩn bị hệ thống sự kiện và cuối cùng tạo các singleton không lazy đủ điều kiện.

Mốc liên quan nhất:

~~~text
SpringApplication.run(...)
    |
    +-- prepare environment / create context
    |
    +-- ApplicationContext.refresh()
    |    |
    |    +-- xử lý bean definitions và post-processors
    |    |
    |    +-- finishBeanFactoryInitialization(...)
    |    |    |
    |    |    +-- preInstantiateSingletons()
    |    |         +-- bean singleton, non-lazy
    |    |         +-- những dependency cần tạo kèm
    |    |
    |    +-- finishRefresh()
    |         +-- context lifecycle hoàn tất refresh
    |         +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    +-- run(...) trả context
~~~

Sơ đồ là **các mốc chính**, không phải bản sao mọi lệnh của Spring Framework. Một số bean hạ tầng có thể khởi tạo sớm hơn trước pha pre-instantiation; các extension và bean factory đặc biệt có hợp đồng riêng.

Điểm quan trọng: khi một bean lazy được tạo **sau refresh**, constructor và những callback initialization của bean đó cũng chạy **sau refresh**. Không có chuyện Spring chạy `@PostConstruct` của bean lazy ở startup rồi để constructor lại tới lần dùng đầu.

### Chuỗi initialization của một bean

Khi container thực sự cần tạo một bean:

~~~text
Factory method / constructor
    |
Dependency resolution và injection
    |
BeanPostProcessor before initialization
    |-- xử lý @PostConstruct trong cấu hình phù hợp
    |
InitializingBean.afterPropertiesSet()
Custom init method (nếu khai báo)
BeanPostProcessor after initialization
    |
Bean sẵn sàng sử dụng
~~~

Điều này áp dụng khi bean được khởi tạo, dù việc đó diễn ra lúc startup hay muộn. Tính lazy **không xóa bỏ** lifecycle callbacks; nó chỉ có thể đẩy thời điểm chạy chúng về sau.

Với bean lazy **chưa bao giờ được tạo**, không có instance để gọi `@PreDestroy`. Nếu bean đã được tạo và được container quản lý đúng hợp đồng, callback destroy thích hợp được gọi khi context đóng.

## 4. Đánh dấu một bean là lazy bằng @Lazy

Annotation ở `org.springframework.context.annotation.Lazy` có thuộc tính mặc định `value() = true`. Thông dụng nhất là đặt trên một class `@Component` hoặc factory method `@Bean`.

### @Lazy trên @Component

~~~java
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@Component
@Lazy
public class ReportExporter {

    public ReportExporter() {
        System.out.println("ReportExporter initialized");
    }
}
~~~

Đây là một class Java đầy đủ về cú pháp nhưng cần nằm trong một ứng dụng Spring có component scan. Nếu không có ai yêu cầu `ReportExporter` trong startup, nó có thể được hoãn.

### @Lazy trên @Bean

~~~java
@Configuration
public class ReportConfiguration {

    @Bean
    @Lazy
    ReportExporter reportExporter() {
        return new ReportExporter();
    }
}
~~~

Đoạn cấu hình minh họa; thêm imports `Configuration`, `Bean`, `Lazy` và class `ReportExporter`. Gắn annotation lên `@Bean` làm thay đổi lazy flag của **bean definition được phương thức tạo ra**.

**Đừng nhầm**: chỉ viết `@Lazy` trên một class helper không được Spring đăng ký làm bean thì không khiến mọi lần gọi `new` ở Java tự được trì hoãn. Annotation có hiệu lực khi Spring xử lý bean definition/injection point phù hợp.

### @Lazy(false) để yêu cầu eager

~~~java
@Bean
@Lazy(false)
EssentialValidator essentialValidator() {
    return new EssentialValidator();
}
~~~

Nếu cấu hình khác đang yêu cầu lazy mặc định, `@Lazy(false)` là cách tường minh chỉ định bean nên được tạo eager theo hợp đồng của container. Trong Spring Boot, cấu hình global lazy cũng cho phép bảo vệ một số bean bằng `@Lazy(false)`. Lựa chọn này hữu ích cho bean bắt buộc phải fail-fast trước ready.

Đây là đoạn minh họa, cần định nghĩa type `EssentialValidator` và imports; chưa phải chương trình độc lập.

### @Lazy trên @Configuration

~~~java
@Configuration
@Lazy
public class OptionalIntegrationsConfiguration {

    @Bean
    OptionalSearchClient searchClient() {
        return new OptionalSearchClient();
    }

    @Bean
    @Lazy(false)
    RequiredHealthRule requiredHealthRule() {
        return new RequiredHealthRule();
    }
}
~~~

Khi `@Lazy` được đặt trên class `@Configuration`, các `@Bean` khai báo bên trong mặc định được đánh dấu lazy; `@Lazy(false)` trên một factory method có thể override hành vi đó. Các class `OptionalSearchClient`/`RequiredHealthRule` là type minh họa chưa được định nghĩa trong snippet.

Không suy ra toàn bộ class `@Configuration` không bao giờ được Spring tạo/đọc trong startup. Spring vẫn phải xử lý metadata, cấu hình và những bean infrastructure; lazy flag ở đây chủ yếu tác động đến **bean definitions được tạo bởi những `@Bean` method**.

## 5. Vì sao đánh dấu @Lazy nhưng bean vẫn tạo lúc startup?

Đây là cơ chế quan trọng nhất khi chẩn đoán.

Giả sử có một service lazy:

~~~java
@Component
@Lazy
class HeavyIndexer {
    HeavyIndexer() {
        System.out.println("HeavyIndexer created");
    }

    void index() {
        System.out.println("Indexing");
    }
}
~~~

Nhưng một singleton không lazy lại yêu cầu service đó trong constructor:

~~~java
@Component
class BootstrapCoordinator {

    private final HeavyIndexer indexer;

    BootstrapCoordinator(HeavyIndexer indexer) {
        this.indexer = indexer;
    }
}
~~~

Các class trên là minh họa (cần imports `Component` và `Lazy`). Vì `BootstrapCoordinator` được tạo eager, Spring phải giải quyết dependency `HeavyIndexer` để truyền vào constructor. Do đó `HeavyIndexer` có thể được tạo **ngay trong refresh**, dù trên class có `@Lazy`.

**Quy tắc:** `@Lazy` trên **bean definition** nói rằng “không chủ động pre-instantiate bean này nếu không cần”; nó **không** có nghĩa “mọi dependency đều được tự động hoãn và không ai được phép lấy bean này sớm”.

### Bốn trường hợp để đối chiếu

| Bean A | Bean B | Quan hệ | Điều thường xảy ra |
| --- | --- | --- | --- |
| A eager | B lazy | A không cần B | A tạo trong startup; B có thể chưa tạo |
| A eager | B lazy | A cần B qua constructor trực tiếp | Spring phải lấy B khi tạo A, nên B có thể tạo sớm |
| A lazy | B lazy | Không ai yêu cầu chúng | Cả hai có thể chưa được tạo |
| A eager | B lazy | A nhận `ObjectProvider<B>`, chưa `getObject()` | A có thể được tạo mà B vẫn chưa được tạo |

Tình huống còn có thể phức tạp hơn do BeanPostProcessor, factory beans, sự kiện, runner, startup checks, actuator và các thư viện bên ngoài yêu cầu bean. Nên đo/quan sát container thực tế thay vì kết luận từ một annotation riêng lẻ.

### @DependsOn có thể kéo dependency tạo sớm

Một bean có `@DependsOn("lazyBean")` có thể khiến bean phụ thuộc được khởi tạo sớm theo quy tắc dependency nếu bean mang annotation `@DependsOn` được tạo eager. Mục tiêu của `@DependsOn` là ràng buộc trình tự tạo/hủy, **không** phải một cách trì hoãn bean.

### Bean được lấy từ ApplicationRunner

`ApplicationRunner`/`CommandLineRunner` chạy sau context refresh nhưng trước ready. Nếu một runner gọi `getBean(LazyService.class)` hoặc `ObjectProvider.getObject()`, bean lazy được tạo **trong giai đoạn startup runner**. Do đó nó có thể được tạo **trước `ApplicationReadyEvent`**, dù không được pre-instantiate trong refresh.

### Event listener và các hook có thể kéo tạo bean

Một bean `@EventListener` có thể được Spring khởi tạo để đăng ký event handler theo vòng đời của framework; một listener hoặc callback sau đó có thể kích hoạt bean khác. Nên thận trọng nếu cố gắng biến toàn bộ listener/handler thành lazy rồi giả định chắc chắn vẫn hoạt động ở mọi sự kiện. Hãy xác định hợp đồng của từng integration cụ thể.

## 6. Lazy dependency và lazy-resolution proxy không giống nhau

`@Lazy` có **hai ngữ cảnh thường gặp**:

1. Trên `@Component`/`@Bean`: quyết định bean definition có được pre-instantiate eager hay không.
2. Trên **injection point** như constructor parameter/`@Autowired` field: yêu cầu Spring cung cấp một **lazy-resolution proxy** cho dependency tại điểm đó.

### @Lazy ngay tại injection point

~~~java
@Component
class DashboardService {

    private final ReportGenerator generator;

    DashboardService(@Lazy ReportGenerator generator) {
        this.generator = generator;
    }

    String openDashboard() {
        return generator.generate();
    }
}
~~~

Đoạn này là minh họa, cần một interface `ReportGenerator` và implementation Spring bean. Spring có thể đưa proxy vào constructor `DashboardService`, rồi proxy tìm target khi `generate()` thực sự được gọi. Nhờ vậy eager `DashboardService` có thể khởi tạo mà không lập tức tạo target *chỉ vì* constructor injection.

Nhưng **có hai lưu ý**:

- Nếu bean `ReportGenerator` vẫn là **singleton eager** độc lập, Spring có thể pre-instantiate target trong pha refresh dù Dashboard giữ proxy. Muốn trì hoãn target, cần thiết kế lazy flag ở **bean definition** hoặc cơ chế lazy global phù hợp.
- Proxy không cam kết target thật luôn có sẵn. Nếu dependency không tồn tại hoặc tạo thất bại, lỗi có thể xuất hiện khi **gọi phương thức thông qua proxy**, làm việc chẩn đoán khó hơn. Với optional dependency, proxy có thể che việc thiếu bean cho tới khi quá muộn.

Không sử dụng proxy lazy để “sửa” circular dependency một cách thiếu phân tích. Spring Boot 3.x nghiêng về thiết kế constructor injection rõ ràng, và việc che một vòng phụ thuộc có thể chuyển lỗi từ startup sang runtime.

### ObjectProvider: lựa chọn rõ ràng khi muốn lấy theo nhu cầu

~~~java
@Component
class DashboardService {

    private final ObjectProvider<ReportGenerator> generators;

    DashboardService(ObjectProvider<ReportGenerator> generators) {
        this.generators = generators;
    }

    String openDashboard() {
        ReportGenerator generator = generators.getObject();
        return generator.generate();
    }
}
~~~

Đây là ví dụ minh họa, cần import `org.springframework.beans.factory.ObjectProvider`, `Component` và type `ReportGenerator`. `ObjectProvider` tách **thời điểm inject provider** khỏi **thời điểm yêu cầu bean thật**. Nó có các API kiểm soát thiếu bean tốt hơn, ví dụ `getIfAvailable()` cho nhu cầu optional phù hợp.

Nhưng provider **không tự biến bean eager thành lazy**. Nếu target được container chủ động pre-instantiate, provider chỉ lấy lại instance đã có. Muốn hoãn việc tạo target, phải xét cả lazy flag của bean definition và các dependency khác.

### Khi nào chọn cách nào?

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Một service tùy chọn, rất ít dùng | `@Lazy` trên bean definition |
| Một bean eager chỉ cần dependency khi gọi một method cụ thể | `ObjectProvider<T>` hoặc `@Lazy` tại injection point và cấu hình lazy target |
| Dependency có thể không tồn tại | `ObjectProvider.getIfAvailable()` và fallback có chủ đích |
| Bean thiết yếu phải phát hiện lỗi ngay khi startup | Eager hoặc `@Lazy(false)` |
| Mọi request đều cần service ngay | Eager thường đơn giản và dự đoán latency dễ hơn |
| Ứng dụng server cần tối ưu startup tổng thể | Đo lường, cân nhắc lazy global có chọn lọc |

## 7. Ví dụ chạy được: quan sát đúng thời điểm tạo bean

Dự án dưới dùng **Java 17**, **Spring Boot 3.3.13** và **Gradle**. Đây là ứng dụng CLI non-web, không cần database hay network. Nó tạo một bean eager, đăng ký hai bean lazy, **không truy cập lazy bean trong startup runner**, rồi yêu cầu một lazy bean sau khi `SpringApplication.run(...)` trả về.

Ta sẽ quan sát:

- Bean eager được tạo trong refresh.
- Một bean lazy **chưa có instance** tại thời điểm sau ready.
- Lần `getBean(...)` đầu tạo instance.
- Lần lấy thứ hai nhận đúng singleton đã được tạo.
- Một bean lazy khác không được yêu cầu sẽ **không được tạo**.
- Đóng context hủy bean lazy đã được tạo.

### 7.1. Cấu trúc

~~~text
lazy-bean-timing-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/lazy/
    └── LazyBeanTimingApplication.java
~~~

**Tệp `settings.gradle`:**

~~~groovy
rootProject.name = 'lazy-bean-timing-demo'
~~~

**Tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.lazy.LazyBeanTimingApplication'
}
~~~

Project cần Gradle tương thích với plugin Spring Boot 3.3 và JDK 17+. Có thể dùng `gradle` đã cài hoặc thêm Gradle Wrapper; snippet không tạo wrapper.

### 7.2. Toàn bộ mã Java

**Tệp `src/main/java/com/example/lazy/LazyBeanTimingApplication.java`:**

~~~java
package com.example.lazy;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class LazyBeanTimingApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LazyBeanTimingApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: run returned");

            // Chỉ hỏi SingletonBeanRegistry đã giữ instance hay chưa.
            // Không gọi getBean ở dòng này.
            System.out.println("MAIN: lazy exists before get="
                    + context.getBeanFactory().containsSingleton("lazyReport"));

            LazyReport first = context.getBean(LazyReport.class);
            System.out.println("MAIN: first result=" + first.render());

            LazyReport second = context.getBean(LazyReport.class);
            System.out.println("MAIN: same instance=" + (first == second));

            System.out.println("MAIN: lazy exists after get="
                    + context.getBeanFactory().containsSingleton("lazyReport"));

            System.out.println("MAIN: unused exists="
                    + context.getBeanFactory().containsSingleton("unusedEngine"));
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    EagerCatalog eagerCatalog() {
        return new EagerCatalog();
    }

    @Bean
    @Lazy
    LazyReport lazyReport() {
        return new LazyReport();
    }

    @Bean
    @Lazy
    UnusedEngine unusedEngine() {
        return new UnusedEngine();
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args -> System.out.println("RUNNER: executed");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("EVENT: ready");
    }

    public static final class EagerCatalog {
        public EagerCatalog() {
            System.out.println("BEAN: eager catalog created");
        }
    }

    public static final class LazyReport {
        public LazyReport() {
            System.out.println("BEAN: lazy report created");
        }

        public String render() {
            return "RPT-42";
        }

        @PreDestroy
        public void close() {
            System.out.println("BEAN: lazy report destroyed");
        }
    }

    public static final class UnusedEngine {
        public UnusedEngine() {
            System.out.println("BEAN: unused engine created");
        }
    }
}
~~~

**Vì sao ví dụ có thể chạy?** Nó định nghĩa class `@SpringBootApplication`, một `main`, ba `@Bean` với tên rõ (`eagerCatalog`, `lazyReport`, `unusedEngine`), một `ApplicationRunner` và một listener ready, cùng các lớp dữ liệu dưới dạng nested static classes. Tất cả imports và dependencies cần thiết cho chương trình đều đã được nêu.

**Vì sao không inject LazyReport vào Runner?** Nếu Runner nhận trực tiếp `LazyReport` qua constructor/factory method, chính runner có thể khiến bean lazy được tạo trong startup, làm sai mục tiêu quan sát “chưa tạo sau ready”. Demo cố ý để các bean lazy **không có dependency eager**.

### 7.3. Chạy

Trong thư mục `lazy-bean-timing-demo`:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper: dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows.

**Các dòng do chính chương trình in**, bỏ qua thông báo Gradle và log của Spring Boot, có thứ tự kỳ vọng:

~~~text
BEAN: eager catalog created
RUNNER: executed
EVENT: ready
MAIN: run returned
MAIN: lazy exists before get=false
BEAN: lazy report created
MAIN: first result=RPT-42
MAIN: same instance=true
MAIN: lazy exists after get=true
MAIN: unused exists=false
BEAN: lazy report destroyed
MAIN: context closed
~~~

Phân tích theo thời điểm:

1. `BEAN: eager catalog created` xảy ra trong pha pre-instantiate các singleton non-lazy.
2. `RUNNER: executed` xuất hiện sau context refresh nhưng trước ready.
3. `EVENT: ready` đến khi Spring Boot phát `ApplicationReadyEvent` sau startup runners.
4. `MAIN: run returned` chỉ xuất hiện khi `SpringApplication.run` đã trở về thành công.
5. `containsSingleton("lazyReport")` là phép **kiểm tra instance singleton đã được cache**, không yêu cầu tạo bean. Vì `LazyReport` chưa được yêu cầu, kết quả là `false`.
6. `getBean(LazyReport.class)` lần đầu làm Spring tạo bean và chạy constructor `LazyReport()`.
7. Lần lấy thứ hai trả lại cùng instance singleton, nên `first == second` là `true`. Không có dòng constructor thứ hai.
8. `containsSingleton("lazyReport")` sau lần lookup là `true`. Điều này chứng minh bean definition đã có từ trước nhưng instance chỉ xuất hiện ở lần yêu cầu đầu.
9. `unusedEngine` không được lookup nên chưa có singleton instance và không in dòng `BEAN: unused engine created`.
10. Khi `try-with-resources` gọi `context.close()`, bean `LazyReport` đã tạo được destroy nên `@PreDestroy` in `BEAN: lazy report destroyed`. Sau đó `MAIN: context closed` xuất hiện.

**Giới hạn của phép đo:** `containsSingleton(name)` cho biết registry hiện đã có một singleton object được đăng ký dưới tên đó; `false` **không** có nghĩa bean definition không tồn tại. Nó cũng không thay thế các công cụ startup profiling trong hệ thống thật. Với tên bean khác, scope khác hoặc proxy/factory bean, cách diễn giải phải được điều chỉnh.

### 7.4. Thay đổi từng yếu tố để thử

Giữ bản gốc để biết output kỳ vọng, sau đó thử **mỗi lần một thay đổi**:

1. **Bỏ `@Lazy` ở factory method `lazyReport`:** Bean `LazyReport` trở thành eager mặc định; dòng constructor chuyển lên trước Runner và ready, `MAIN: lazy exists before get` trở thành `true`.
2. **Giữ `@Lazy` nhưng gọi `context.getBean(LazyReport.class)` trong `ApplicationRunner`:** Bean được tạo trong runner, **trước** ready, vì chính runner đã yêu cầu nó.
3. **Giữ bean lazy, thêm một eager bean có constructor dependency vào `LazyReport`:** Bean lazy bị tạo để thỏa mãn dependency của eager bean, thường trong refresh.
4. **Gọi `context.getBean(UnusedEngine.class)` sau lần kiểm tra đầu:** Constructor `UnusedEngine` sẽ in khi nó được lấy lần đầu; `containsSingleton("unusedEngine")` sau đó thành `true`.
5. **Đổi `@Lazy` thành `@Lazy(false)` trên `lazyReport`:** Bean được yêu cầu eager như không dùng annotation.
6. **Cho constructor `LazyReport` ném exception:** Vì chỉ được yêu cầu trong `main` sau `run`, lỗi có thể xuất hiện **sau `ApplicationReadyEvent`**; điều này thể hiện rủi ro phát hiện lỗi muộn.
7. **Dùng `@Lazy(false)` trên `eagerCatalog` rồi bật global lazy:** Bean quan trọng này được yêu cầu eager ngay cả khi phần lớn bean khác được cấu hình lazy.

## 8. Bật lazy initialization cho toàn ứng dụng Spring Boot

Ngoài gắn `@Lazy` từng bean, Spring Boot hỗ trợ chế độ lazy trên diện rộng.

### application.properties

**`src/main/resources/application.properties`:**

~~~properties
spring.main.lazy-initialization=true
~~~

### application.yml

~~~yaml
spring:
  main:
    lazy-initialization: true
~~~

Hai cách biểu diễn cùng một property; chỉ cần dùng **một** cách trong ứng dụng thực tế hoặc xác định rõ nguồn cấu hình nào được ưu tiên.

### Cấu hình programmatically

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setLazyInitialization(true);
app.run(args);
~~~

Đây là **mã minh họa**; thay `MyApplication` bằng application class thật. Quan trọng là gọi `setLazyInitialization(true)` **trước** `run`. Với `SpringApplicationBuilder` cũng có method `lazyInitialization(true)`.

Khi global lazy được bật, nhiều bean có thể được tạo theo nhu cầu thay vì trong startup. Điều này giúp giảm startup cost ở một số ứng dụng, đặc biệt khi có nhiều web-related beans hoặc feature ít dùng. Nhưng **không cam kết mọi bean đều hoãn**: hạ tầng Spring, dependencies cần trong quá trình bootstrap, listener, runner và một số bean được đánh dấu eager vẫn có thể tạo sớm.

### Giữ bean thiết yếu eager khi global lazy

~~~java
@Bean
@Lazy(false)
StartupPolicyValidator startupPolicyValidator() {
    return new StartupPolicyValidator();
}
~~~

Đây là snippet minh họa, cần class `StartupPolicyValidator` và imports `Bean`/`Lazy`. Nếu policy validator phải phát hiện thiếu cấu hình nghiêm trọng **trước ready**, nên để nó eager hoặc kiểm tra tường minh tại mốc startup thích hợp.

### Cẩn trọng khi bật global lazy trong demo ở mục 7

Nếu chạy project với:

~~~bash
gradle bootRun --args="--spring.main.lazy-initialization=true"
~~~

số bean eager và thứ tự in log có thể **khác** so với output mục 7. Vì hạ tầng, runner và observer vẫn cần hoạt động, không kết luận đơn giản rằng mọi bean không có `@Lazy(false)` đều chắc chắn chưa tạo lúc ready. Quan sát bằng log, tránh dùng output cũ làm test cho một cấu hình có mục đích khác.

**Giá trị mặc định Spring Boot 3.3 là `false`** cho `spring.main.lazy-initialization`. Hãy bật khi đã đo được lợi ích và chấp nhận trade-off; không mặc định bật chỉ vì muốn thấy startup nhanh hơn.

## 9. @Lazy và @PostConstruct, @PreDestroy, event, runner

Lazy initialization thay đổi **khi nào** callback lifecycle được gọi.

| Callback hoặc mốc | Eager bean mặc định | Lazy bean chưa được yêu cầu |
| --- | --- | --- |
| Constructor / `@Bean` method | Trong startup khi bean được tạo | Chưa chạy |
| Dependency injection | Khi bean tạo | Chưa thực hiện với instance chưa tồn tại |
| `@PostConstruct` | Trong initialization | Chưa chạy |
| `InitializingBean.afterPropertiesSet()` | Trong initialization | Chưa chạy |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Có thể chạy cho các bean đủ điều kiện sau pha pre-instantiate | Không coi callback được tự gọi nếu bean chưa từng được pre-instantiate |
| `ApplicationStartedEvent` | Event Boot phát theo mốc ứng dụng | Không tự biến mọi lazy bean thành eager |
| `ApplicationRunner`/`CommandLineRunner` | Chạy ở pha startup, có thể lookup bean | Có thể làm lazy bean được tạo khi runner dùng |
| `ApplicationReadyEvent` | Event Boot báo mốc ready | Không bắt buộc mọi lazy bean đã được tạo |
| `@PreDestroy` | Khi singleton đã được tạo và context đóng bình thường | Không có instance để destroy nếu chưa từng tạo |

Một lỗi thường gặp là trông đợi `@PostConstruct` của bean lazy chạy trước mọi startup runner. Không: nếu bean chưa được tạo, callback của chính bean đó chưa chạy. Nếu runner cần bean được xác thực, nó phải yêu cầu bean hoặc thiết kế bean thiết yếu thành eager.

Tương tự, `ContextRefreshedEvent` có nghĩa context đã refresh, không có nghĩa từng lazy singleton đều đã khởi tạo. `ApplicationReadyEvent` có nghĩa quá trình startup Boot đã đạt mốc ready sau runners thành công, không đồng nghĩa mọi tính năng tùy chọn sẽ không phải khởi tạo ở request đầu tiên.

## 10. Trade-off vận hành: startup nhanh hơn có thể làm request đầu chậm hơn

Lazy initialization **dịch chuyển chi phí**. Thay vì trả chi phí ở startup, ứng dụng có thể trả chi phí khi chức năng được gọi lần đầu.

### Lợi ích có thể có

- Giảm thời gian tạo bean ở startup khi có nhiều tính năng ít được sử dụng.
- Giảm một phần memory sử dụng ngay sau startup khi những object lớn chưa được dựng.
- Trì hoãn tài nguyên không thiết yếu như cache chuyên dụng, một số parser/formatter hoặc client tùy chọn.
- Hữu ích cho ứng dụng CLI có nhiều feature nhưng mỗi lần chỉ dùng một lệnh cụ thể.
- Có thể cải thiện cold-start path nếu tập bean thật sự cần cho request đầu nhỏ hơn toàn bộ bean definitions.

### Chi phí và rủi ro

- **First-use latency:** Request hoặc job đầu tiên đợi constructor, injection, `@PostConstruct` và các dependency; p95/p99 latency có thể tăng nếu cold path bị kích hoạt đột ngột.
- **Lỗi phát hiện muộn:** Bean thiếu property, thiếu class, lỗi kết nối hoặc exception trong init có thể chỉ lộ ra khi ứng dụng đã báo ready.
- **Đột biến memory:** Ứng dụng có thể chạy với heap thấp sau startup nhưng tăng mạnh khi nhiều tính năng lần đầu cùng được gọi; cần sizing heap cho workload đầy đủ.
- **Khó quan sát hơn:** Log startup bình thường không cho thấy một số phần chỉ lỗi ở request đầu.
- **Có thể chỉ là cải thiện giả:** Nếu các endpoint quan trọng đều cần cùng tập service, chúng vẫn phải tạo ở lần sử dụng đầu, chỉ chuyển chi phí sang người dùng.
- **Phức tạp callback:** Mã kỳ vọng toàn bộ singleton tồn tại ở refresh có thể phải xét lại khi bật global lazy.

### Tư duy “thời gian khởi động” và “thời gian sẵn sàng phục vụ”

Nếu tính chi phí:

~~~text
Eager:
startup = build context + create essential beans + create optional beans
first request ≈ business work (bean đã có)

Lazy:
startup = build context + create beans thực sự cần trong bootstrap
first request = create lazy dependencies + business work
~~~

Đây là mô hình **định tính**, không phải công thức thời gian thực cho mọi ứng dụng. Lazy có thể thay đổi các tuyến phụ thuộc, thứ tự I/O, class loading và mức dùng bộ nhớ; chỉ benchmark đúng deployment mới cho kết luận có lợi hay không.

### Readiness không tự xác thực toàn bộ lazy beans

Một container orchestration có thể xem instance ready vì Spring Boot đã qua startup runners. Nhưng một endpoint ít dùng có dependency lazy hỏng có thể trả lỗi khi được gọi lần đầu.

Nếu một bean hoặc downstream service là **điều kiện bắt buộc để nhận traffic**, hãy chọn một trong các chiến lược rõ ràng:

1. Giữ bean eager bằng `@Lazy(false)`.
2. Xác thực/khởi tạo bean thiết yếu trong một startup runner có timeout, failure policy rõ ràng.
3. Dùng readiness/health indicators phản ánh điều kiện quan trọng và không tạo tác dụng phụ nguy hiểm.
4. Có bước pre-warm ở deployment trước khi chuyển lưu lượng, nếu việc pre-warm có ích và an toàn.

**Không dùng liveness probe để phụ thuộc vào một downstream bên ngoài theo cách khiến mọi pod tự restart cùng lúc khi hệ thống bên ngoài gặp sự cố.** Liveness và readiness phục vụ mục đích khác nhau.

## 11. Lazy singleton và truy cập đồng thời

Một ứng dụng web có thể nhận hai request cùng sử dụng singleton lazy lần đầu. Spring container phải phối hợp việc tạo singleton thông thường để không tùy tiện tạo nhiều instance cho cùng bean definition, nhưng điều đó **không làm cho business state của bean thread-safe**.

Ví dụ rủi ro:

~~~java
@Component
@Lazy
class VisitCounter {

    private int visits;

    int next() {
        return ++visits;
    }
}
~~~

Mã trên là minh họa thread-safety **không tốt**, không thuộc project mẫu. Hai request cùng gọi `next()` có thể bị race condition trên phép `++`. `@Lazy` chỉ ảnh hưởng thời điểm tạo bean; nó không làm phép tăng trở thành atomic.

Nếu phải giữ counter dùng chung, cân nhắc `AtomicInteger`, đồng bộ hóa phù hợp hoặc thiết kế stateless. Tương tự, `@Lazy` không giải quyết deadlock, blocking I/O hoặc vấn đề visibility của state do code ứng dụng tự quản lý.

### Một lần tạo có thể vẫn tốn nhiều thời gian

Nếu constructor của lazy bean thực hiện kết nối ngoài không có timeout, request đầu có thể bị chặn rất lâu. Hãy:

- Hạn chế I/O trong constructor khi có thể.
- Cấu hình timeouts rõ ràng cho network clients.
- Đưa init bắt buộc vào cơ chế startup/health có kiểm soát.
- Đo thời gian khởi tạo và số lần thực sự dùng bean.
- Tránh giữ lock ứng dụng quá rộng quanh thao tác cần tạo lazy bean.

## 12. Các tình huống thiết kế và lựa chọn phù hợp

### Trường hợp A: chức năng tùy chọn ít dùng

Một công cụ xuất báo cáo chuyên dụng được gọi vài lần mỗi tuần. `@Lazy` có thể hợp lý để trì hoãn engine nặng cho tới khi thật sự dùng. Dùng một endpoint/job riêng để trigger.

Điều cần kiểm tra: thời gian chờ hợp lý của lượt gọi đầu, chi phí tạo engine, mức memory cao nhất và khả năng retry nếu init lỗi.

### Trường hợp B: authentication/security hoặc policy bắt buộc

Nếu việc xác thực policy cần hoàn tất trước khi server nhận traffic, để bean lazy mà không kiểm tra ở startup có thể làm tăng rủi ro. Đảm bảo cấu hình authentication bean và các kiểm tra thiết yếu có chiến lược eager/fail-fast phù hợp; không trì hoãn lỗi bảo mật chỉ để giảm thời gian startup.

### Trường hợp C: CLI nhiều subcommand

Một JAR dùng để `import` hoặc `export`, mỗi lệnh có dependency riêng. Lazy bean definitions hoặc conditional configuration giúp tránh khởi tạo những công cụ không cần cho subcommand đang chạy.

Đặc biệt, nếu một `ApplicationRunner` điều phối subcommand gọi đúng provider cho từng tính năng, bean tương ứng được tạo khi runner yêu cầu. Đây là thiết kế khác với web app cần đáp ứng nhiều chức năng đồng thời.

### Trường hợp D: web application phải có latency đầu tiên ổn định

Nếu mọi request quan trọng đều dùng cùng một service nặng, lazy có thể khiến request đầu chậm và gây timeout. Có thể ưu tiên eager hoặc pre-warm. Cần đo startup + first-request latency + p95/p99, không chỉ nhìn log “Started” của Spring Boot.

### Trường hợp E: external service đôi khi không có mặt

Tạo bean lazy có thể khiến ứng dụng vẫn startup dù external dependency đang lỗi, nhưng **không nên dùng lazy như cơ chế thay thế circuit breaker/retry**. Cần chính sách rõ ràng: tính năng đó có được degrade không, trạng thái health thế nào, lần gọi đầu thất bại xử lý ra sao, và người dùng có được thông báo phù hợp không?

## 13. Chẩn đoán: làm sao biết bean được tạo khi nào?

### Ghi log ở constructor hoặc factory method

Trong demo, constructor in `BEAN: lazy report created`. Khi log xuất hiện là lúc constructor chạy. Đây là cách học trực quan, nhưng production không nên ghi thông tin nhạy cảm và không nên thêm logging quá mức vào mọi bean.

### Dùng BeanFactory.containsSingleton để kiểm tra instance

~~~java
boolean instantiated =
        context.getBeanFactory().containsSingleton("lazyReport");
~~~

Giá trị `false` nghĩa là singleton registry **chưa chứa instance dưới key đó**, không có nghĩa bean definition thiếu. Cách này phù hợp với ví dụ `@Bean` singleton có tên đã biết. Nếu có `FactoryBean`, custom scope, proxy hoặc nhiều context, trạng thái có thể cần giải thích sâu hơn.

### Dùng startup diagnostics phù hợp

Spring Boot có `ApplicationStartup`/`BufferingApplicationStartup` để thu thông tin về các bước khởi động, và có thể tích hợp Actuator startup endpoint khi cấu hình phù hợp. Java Flight Recorder và profiling/metrics có thể giúp thấy bean initialization hoặc class loading thật sự chiếm bao nhiêu thời gian. Hãy xét **cả giai đoạn startup** và **lần dùng đầu** sau ready.

### Không dùng getBean để “kiểm tra bean đã tồn tại chưa”

~~~java
context.getBean(LazyReport.class);
~~~

Nếu `LazyReport` chưa được tạo, chính lệnh trên **kích hoạt khởi tạo**. Vì vậy nó không phải một phép thăm dò thụ động. Dùng `containsBeanDefinition(...)` để hỏi về định nghĩa, `containsSingleton(...)` để hỏi về instance theo nghĩa registry, hoặc công cụ metrics khi cần quan sát không gây side effect.

### Kiểm tra dependency graph

Nếu `@Lazy` không có tác dụng như kỳ vọng, hãy trả lời lần lượt:

1. Có một eager bean nào constructor-inject trực tiếp bean này không?
2. Có `@DependsOn`, `@Bean` factory method hoặc BeanPostProcessor nào đòi nó sớm không?
3. Có runner/startup event listener nào gọi `getBean`/provider trước ready không?
4. Có cấu hình `@Lazy(false)` hoặc BeanFactoryPostProcessor thay đổi lazy flag không?
5. Có thư viện AutoConfiguration nào bắt buộc khởi tạo bean cùng type không?
6. Có context khác hoặc một bean trùng type khiến bạn quan sát nhầm không?
7. Bạn đang đo constructor, proxy creation, bean method hay business method? Bốn thứ đó không nhất thiết đồng thời.

## 14. Kiểm thử đúng lazy initialization

### Unit test ý tưởng bằng một context

Một bài test tốt nên chứng minh:

- Bean definition tồn tại ngay sau refresh.
- Bean singleton chưa được tạo khi không có ai yêu cầu.
- Lần lookup đầu tạo instance.
- Lần lookup thứ hai trong cùng context trả instance cũ.
- Đóng context chạy destroy callback nếu instance đã được tạo.

Demo mục 7 chính là một kiểu kiểm thử bằng quan sát logs. Trong automated tests, thay `System.out.println` bằng counter/test spy được thiết kế cẩn thận, tránh phụ thuộc thứ tự log của toàn bộ framework.

### Test với ApplicationContextRunner

Spring Boot Test có `ApplicationContextRunner` để tạo context nhỏ trong test. Một bài test có thể xây dựng configuration gồm một eager bean và một lazy bean, rồi kiểm tra trạng thái bean registry trước/sau `getBean` trong callback. Đây là công cụ phù hợp khi bạn muốn test behavior của bean definitions mà không boot toàn bộ web server.

Đoạn **minh họa** cho một test khi đã khai báo `DemoConfig` và `MyLazyService`:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(DemoConfig.class)
        .run(context -> {
            assertFalse(context.getBeanFactory()
                    .containsSingleton("myLazyService"));

            MyLazyService service =
                    context.getBean(MyLazyService.class);

            assertNotNull(service);
            assertTrue(context.getBeanFactory()
                    .containsSingleton("myLazyService"));
        });
~~~

Đây **không phải** code test độc lập. Cần dependency `spring-boot-starter-test`, các imports cho `ApplicationContextRunner`/JUnit assertions, tên bean chính xác và class `DemoConfig` trả một `@Bean @Lazy MyLazyService`. Hãy dùng test runner/JUnit đúng phiên bản; đừng xem snippet này là một file hoàn chỉnh có thể `javac` đơn lẻ.

### Nên test đường lỗi

Đánh dấu một bean là `@Lazy` và cố ý làm factory method ném exception trong test; xác minh:

- Context có thể refresh khi chưa ai yêu cầu bean đó.
- `context.getBean(...)` làm xuất hiện lỗi tạo bean.
- Khi bean bắt buộc được đổi thành eager, startup không nên lặng lẽ vượt qua lỗi đó.
- Test production cần phân loại lỗi thật thay vì chỉ assert “exception bất kỳ”.

Việc startup thành công **không chứng minh** mọi lazy bean đều hợp lệ.

## 15. Lỗi phổ biến và cách sửa

**1. “Singleton là eager theo định nghĩa.”** Sai. Singleton nói về phạm vi instance, lazy/eager nói về thời điểm tạo. `@Bean @Lazy` vẫn mặc định singleton.

**2. “@Lazy luôn giúp bean chỉ tạo ở HTTP request đầu tiên.”** Sai. Bean có thể được yêu cầu bởi eager dependency, runner, listener hoặc code khác trước request.

**3. “Chỉ @Lazy trên dependency đã chắc chắn hoãn target.”** Không hẳn. `@Lazy` ở **injection point** thường tạo proxy; nếu bean target tự nó eager và bị pre-instantiate, target vẫn có thể tồn tại từ startup.

**4. “@Lazy làm mất @PostConstruct.”** Sai. `@PostConstruct` vẫn chạy khi bean thực sự được tạo/initialized, dù muộn hơn.

**5. “@PreDestroy chắc chắn chạy cho bean lazy chưa ai dùng.”** Không. Nếu chưa có instance được Spring tạo thì không có instance để destroy.

**6. “ApplicationReadyEvent nghĩa là mọi bean lazy đã sẵn sàng.”** Sai. Ready là mốc startup của Boot sau runners, không phải vòng lặp buộc tạo toàn bộ lazy bean definitions.

**7. “Bật global lazy thì mọi bean đều chắc chắn không tạo ở startup.”** Sai. Một số bean infrastructure và dependency cần thiết có thể được yêu cầu sớm; `@Lazy(false)` cũng cho phép chỉ định eager.

**8. “Dùng getBean để kiểm tra có tạo chưa.”** Sai. `getBean` có thể **chính là trigger** làm bean khởi tạo. Nếu cần kiểm tra thụ động cho singleton registry, `containsSingleton` giúp quan sát trong phạm vi phù hợp.

**9. “@Lazy nghĩa là prototype.”** Sai. Tính lazy không thay đổi scope. Singleton vẫn chỉ có một instance theo bean definition trong container sau khi được tạo.

**10. “Thời gian startup giảm đồng nghĩa trải nghiệm người dùng tốt hơn.”** Không luôn. Lazy có thể chuyển chi phí sang first request, làm tăng tail latency và phát hiện lỗi muộn.

**11. “Không cần cấu hình timeout vì Bean được tạo theo nhu cầu.”** Sai. Network I/O trong constructor/init của bean lazy có thể làm treo request đầu hoặc runner, gây quá thời gian chờ.

**12. “@Lazy làm bean thread-safe.”** Sai. Spring quản lý singleton creation, nhưng field mutable và business methods cần chính sách concurrency riêng.

**13. “@Lazy có thể sửa lỗi circular dependency mà không đổi thiết kế.”** Không nên. Proxy/late resolution có thể trì hoãn triệu chứng; nên phân tách trách nhiệm và graph dependency rõ ràng.

**14. “@Lazy(false) không có tác dụng khi bật global lazy.”** Không đúng với Spring Boot 3.3: annotation có thể dùng để chỉ định bean cần được tạo eager trong khi phần còn lại lazy.

**15. “@Lazy trên class không được Spring quản lý vẫn có tác dụng.”** Sai. Annotation không biến các object tạo bằng `new` ngoài container thành lazy Spring bean.

**16. “Không cần test lazy beans vì startup đã PASS.”** Sai. Các nhánh ít dùng có thể chứa lỗi config, classpath hoặc dependency chưa phát hiện.

**17. “Một singleton lazy tạo rồi là tự đóng ngay sau lần dùng đầu.”** Sai. Singleton được giữ trong container; lifecycle kết thúc khi context đóng hoặc khi có cơ chế hủy khác phù hợp.

**18. “Tất cả bean khác đều có thể truy cập trong @PostConstruct của bean lazy.”** Không nên suy ra điều đó từ một callback; phải xét thời điểm khởi tạo, dependency graph, trạng thái context và contract của bean liên quan.

## 16. Bài thực hành

1. Chạy project mục 7. Vì sao dòng `BEAN: eager catalog created` xuất hiện trước `EVENT: ready`?
2. Vì sao `MAIN: lazy exists before get=false` vẫn đúng dù Spring đã nạp `@Bean` definition của `lazyReport`?
3. Sau `context.getBean(LazyReport.class)` lần đầu, tại sao constructor chỉ in đúng một lần dù gọi `getBean` lần thứ hai?
4. `UnusedEngine` không được yêu cầu trong chương trình. Vì sao không thấy log constructor của nó?
5. Bỏ `@Lazy` ở `lazyReport`, chạy lại và ghi phần output thay đổi. Tính singleton có thay đổi không?
6. Thêm một eager bean có constructor nhận `LazyReport`. Điều gì xảy ra với thời điểm tạo `LazyReport`?
7. Cho runner nhận `ObjectProvider<LazyReport>` và gọi `getObject()` trong `run`. Bean được tạo trước hay sau `ApplicationReadyEvent`?
8. Giữ provider nhưng **không** gọi `getObject()` trong runner. Kết quả có khác không?
9. Bật `spring.main.lazy-initialization=true`, so sánh số bean được tạo trong startup với cấu hình mặc định. Có thể kết luận tất cả bean đều lazy không?
10. Gắn `@Lazy(false)` lên `eagerCatalog` khi đang bật global lazy. Quan sát kết quả và giải thích mục đích fail-fast.
11. Thêm `@PostConstruct` vào `LazyReport`. Nó xuất hiện trước hay sau `MAIN: lazy exists before get=false`?
12. Giữ `@PreDestroy` trong `LazyReport` nhưng xóa toàn bộ lệnh yêu cầu `LazyReport`. Lúc context đóng có callback của `LazyReport` không?
13. Thêm một `LazyReport` có factory method cố ý ném exception. Nếu chưa có ai yêu cầu bean, startup có thể đạt ready không? Điều gì xảy ra khi lookup?
14. Trong ứng dụng web, hãy đo first-request latency khi bật/tắt lazy. Vì sao chỉ dùng thời gian in “Started” không đủ đánh giá?
15. Một controller eager inject target qua `@Lazy` injection point. Vì sao proxy có thể có từ startup nhưng target vẫn chưa được tạo? Trường hợp nào target vẫn bị tạo sớm?
16. Hệ thống có một client kết nối DB bắt buộc trước nhận traffic. Bạn có giữ client lazy không, hay dùng startup validation/`@Lazy(false)`? Nêu lý do.
17. Vì sao singleton lazy với field `int count` vẫn có data race khi nhiều request đồng thời tăng count?
18. Viết test sử dụng `ApplicationContextRunner`/`containsSingleton` để khẳng định bean definition lazy và lần lookup đầu tiên. Kiểm tra tên bean và scope nào quan trọng?
19. So sánh `@Lazy` trên `@Bean` và `@Lazy` trên constructor parameter: khác nhau ở bean definition và dependency reference ra sao?
20. Nếu một tính năng rất ít dùng nhưng constructor mất nhiều giây, bạn sẽ thiết kế pre-warm, timeout, health và thông báo người dùng như thế nào?

## Ghi nhớ

- **Khởi tạo lười** hoãn việc tạo và initialization một bean **đến lúc có nhu cầu**, nhưng dependency có thể làm bean vẫn được tạo sớm.
- `@Lazy` trên `@Bean`/`@Component` ảnh hưởng **bean definition**; `@Lazy` ở injection point có thể tạo **lazy-resolution proxy**.
- **Singleton scope** không thay đổi: một singleton lazy sau lần tạo đầu vẫn được giữ và tái sử dụng trong cùng context.
- Spring Boot mặc định không bật lazy toàn cục. Có thể bật bằng `spring.main.lazy-initialization=true` hoặc `SpringApplication.setLazyInitialization(true)`; dùng `@Lazy(false)` cho bean quan trọng cần eager.
- Constructor, injection, `@PostConstruct` và các init callbacks chạy **khi bean thực sự được tạo**, không chạy ở startup cho instance chưa tồn tại.
- `ApplicationReadyEvent` và readiness không bảo đảm tất cả lazy beans đã tồn tại hoặc hợp lệ.
- Lazy có thể giúp giảm startup time nhưng **chuyển chi phí và lỗi** sang lần dùng đầu; luôn đo first-use latency, memory, lỗi phát hiện muộn và tác động vận hành.
- `ObjectProvider`, dependency injection, lifecycle callbacks và runtime readiness cần được hiểu cùng nhau; chỉ dán `@Lazy` không phải giải pháp cho mọi vấn đề hiệu năng.

### Tài liệu tham khảo

- Spring Boot 3.3 — Lazy Initialization, SpringApplication: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.lazy-initialization
- Spring Boot 3.3 — SpringApplication Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.1 — `@Lazy` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Lazy.html
- Spring Framework — Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Framework — Bean Scope: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — Bean lifecycle callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — `ObjectProvider` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/ObjectProvider.html
