# ApplicationPreparedEvent: sau khi nạp định nghĩa bean và trước refresh

## 1. ApplicationPreparedEvent là gì?

Trong Spring Boot, **ApplicationPreparedEvent** là sự kiện được phát khi **ApplicationContext đã được chuẩn bị và những BeanDefinition nguồn ban đầu đã được nạp**, nhưng **phương thức refresh() chưa được thực hiện**. Đây là một mốc của quá trình khởi chạy ứng dụng, không phải mốc ứng dụng sẵn sàng phục vụ request.

Theo Spring Boot 3.5, lớp event có tên đầy đủ **org.springframework.boot.context.event.ApplicationPreparedEvent** và kế thừa **SpringApplicationEvent**. JavaDoc nêu rằng ở thời điểm event này, **Environment đã sẵn sàng để sử dụng, context đã tồn tại nhưng chưa refresh**.

Phân biệt ba trạng thái:

1. **Context được tạo:** đối tượng container đã tồn tại. Boot có thể gắn Environment, resource loader, initializers và các thiết lập bootstrap.
2. **BeanDefinition được nạp:** một số nguồn cấu hình/metadata về bean đã được đưa vào registry. Điều này chưa có nghĩa đã tạo instance của các bean nghiệp vụ.
3. **Context refresh:** Spring hoàn tất xử lý configuration classes, post-processors và khởi tạo các singleton non-lazy; container đi vào trạng thái hoạt động.

**ApplicationPreparedEvent nằm giữa bước 2 và bước 3.** Đây là ý nghĩa cần nhớ khi đọc log startup hoặc phát triển một listener can thiệp trước refresh.

## 2. Sơ đồ các sự kiện xung quanh Prepared

~~~text
main(String[] args)
       |
       v
SpringApplication.run(args)
       |
       +--> ApplicationStartingEvent
       |       Chưa có Environment, chưa có Context
       |
       +--> Chuẩn bị ConfigurableEnvironment
       |       ApplicationEnvironmentPreparedEvent
       |       Environment có, Context chưa được tạo
       |
       +--> Tạo ApplicationContext
       |       Chạy ApplicationContextInitializer
       |       ApplicationContextInitializedEvent
       |       Context đã tạo, chưa load primary sources
       |
       +--> Load primary sources/BeanDefinition ban đầu
       |
       +--> ApplicationPreparedEvent  <--- TRỌNG TÂM
       |       Context tồn tại, Environment sẵn
       |       Source definitions đã được nạp
       |       Context CHƯA refresh
       |
       +--> ApplicationContext.refresh()
       |       ConfigurationClassPostProcessor
       |       BeanDefinitionRegistryPostProcessor
       |       BeanFactoryPostProcessor
       |       BeanPostProcessor, tạo singleton non-lazy
       |       ContextRefreshedEvent
       |
       +--> ApplicationStartedEvent
       |       LivenessState.CORRECT
       |
       +--> ApplicationRunner / CommandLineRunner
       |
       +--> ApplicationReadyEvent
       |       ReadinessState.ACCEPTING_TRAFFIC
       |
       v
run(args) trả về ConfigurableApplicationContext
~~~

Sơ đồ mô tả các mốc chính của **startup thành công**. Nó không liệt kê mọi callback nội bộ. Với web application, **WebServerInitializedEvent** có thể được phát trong quá trình refresh, trước ApplicationStartedEvent.

| Sự kiện | Đã tạo context? | Đã nạp primary source definitions? | Đã refresh? | Đã chạy runners? |
| --- | --- | --- | --- | --- |
| **ApplicationEnvironmentPreparedEvent** | Chưa | Chưa | Chưa | Chưa |
| **ApplicationContextInitializedEvent** | Có | Chưa theo luồng load sources của Boot | Chưa | Chưa |
| **ApplicationPreparedEvent** | **Có** | **Có** | **Chưa** | Chưa |
| **ContextRefreshedEvent** | Có | Có, và đã qua xử lý metadata thêm trong refresh | **Có** | Chưa chắc |
| **ApplicationStartedEvent** | Có | Có | **Có** | **Chưa** |
| **ApplicationReadyEvent** | Có | Có | Có | **Đã hoàn tất** |

Điểm khác biệt quan trọng giữa **ApplicationContextInitializedEvent** và **ApplicationPreparedEvent** là **mốc nạp BeanDefinition từ các primary sources**. Cả hai đều phát trước refresh, nhưng sự kiện Prepared đến **muộn hơn**.

## 3. "Đã nạp BeanDefinition" có phải tất cả beans đã tồn tại?

**Không.** Đây là chỗ dễ hiểu sai nhất của bài.

Một **BeanDefinition** là metadata hướng dẫn Spring tạo bean: bean class, tên, scope, factory method, dependency và các thông tin lifecycle. **Bean instance** mới là Java object được tạo và quản lý. Chúng không đồng nghĩa:

~~~text
BeanDefinition           Bean instance
--------------           ---------------------------
Mô tả cách tạo bean      Đối tượng Java đã tạo thật
Tên/class/scope          Constructor đã được gọi
Có thể có trước refresh  Phụ thuộc vào giai đoạn tạo
Không cần bean chạy      Có thể đã qua init callbacks
~~~

Tại ApplicationPreparedEvent, Boot đã nạp **các nguồn cấu hình đầu vào**. Ví dụ:

~~~java
SpringApplication app =
        new SpringApplication(DemoApplication.class);
app.run(args);
~~~

**DemoApplication.class** là một primary source. SpringApplication đưa nguồn này vào context trước khi phát Prepared event.

Nhưng nếu class đó có:

~~~java
@Bean
GreetingService greetingService() {
    return new GreetingService();
}
~~~

thì **BeanDefinition của greetingService có thể chưa xuất hiện tại Prepared**. Nguyên nhân: Spring xử lý class **@Configuration**, tìm các method **@Bean**, xử lý **@Import**, **@ComponentScan** và nhiều auto-configurations trong bước **ConfigurationClassPostProcessor** khi refresh. Những định nghĩa này có thể được đăng ký **sau Prepared**.

Vì vậy, hai phát biểu sau cùng có thể đúng:

- **Đã nạp định nghĩa của primary configuration source** trước ApplicationPreparedEvent.
- **Chưa xử lý xong tất cả các @Bean method và component definitions** cho đến khi refresh chạy.

Không nên viết một phép kiểm tra "tổng số BeanDefinition bằng X" rồi coi X là hằng số của Spring Boot. Classpath, phiên bản, auto-configuration, bean conditions và thư viện đi kèm đều làm số lượng thay đổi.

## 4. ApplicationPreparedEvent có những thông tin gì?

Listener có thể truy cập những API sau:

~~~java
ConfigurableApplicationContext context =
        event.getApplicationContext();

SpringApplication application = event.getSpringApplication();
String[] args = event.getArgs();
~~~

Đây là **mảnh code minh họa bên trong callback**, cần có biến **event** và imports phù hợp. Ý nghĩa:

- **getApplicationContext():** trả về ConfigurableApplicationContext đã được chuẩn bị nhưng chưa refresh.
- **getSpringApplication():** tham chiếu SpringApplication đang thực hiện bootstrap.
- **getArgs():** các đối số raw của lần khởi chạy.
- **context.getEnvironment():** Environment đã được chuẩn bị để tra cứu giá trị và profiles.
- **context.containsBeanDefinition(name):** xem định nghĩa cụ thể đã có trong registry hay chưa, **không xác nhận instance đã được khởi tạo**.
- **context.isActive():** quan sát trạng thái hoạt động của context; trong luồng thông thường, Prepared đến trước khi context active qua refresh.

Ví dụ chỉ quan sát metadata:

~~~java
ConfigurableApplicationContext context =
        event.getApplicationContext();

System.out.println("active=" + context.isActive());
System.out.println("profiles="
        + String.join(",", context.getEnvironment().getActiveProfiles()));
System.out.println("sample definition="
        + context.containsBeanDefinition("sampleService"));
~~~

**Không gọi getBean(MyService.class) để kích hoạt nghiệp vụ tại đây.** Khi context chưa refresh, registry và các BeanPostProcessor chưa được thiết lập đầy đủ; việc cố buộc khởi tạo service có thể thất bại hoặc phá thứ tự lifecycle.

Đồng thời, Environment đã có không có nghĩa mọi **@ConfigurationProperties bean** đã được tạo và bind. Environment là nguồn dữ liệu, còn configuration-properties bean vẫn thuộc lifecycle của ApplicationContext.

## 5. Ví dụ Java 17+: in chính xác các mốc trước và sau refresh

Ví dụ dưới đây dùng **Spring Boot 3.5.x**, **Java 17+** và một ứng dụng **non-web** để tránh nhiễu từ web server. Ví dụ quan sát được:

1. Main bắt đầu cấu hình SpringApplication.
2. ApplicationPreparedEvent phát; context còn chưa refresh.
3. Singleton nghiệp vụ được tạo và chạy initialization callback trong refresh.
4. ContextRefreshedEvent đến sau refresh.
5. ApplicationStartedEvent đến trước runner.
6. ApplicationReadyEvent đến sau runner.
7. SpringApplication.run trả về main.

### 5.1. Tạo project

Tạo project Spring Initializr với **Maven**, **Java 17 trở lên**, **Spring Boot 3.5.x**, package **com.example.demo**, và dependency **Spring Boot Starter**. Giữ Maven Wrapper do Initializr sinh. Không cần dependency Spring Web vì ứng dụng chọn **WebApplicationType.NONE**.

Tạo file **src/main/java/com/example/demo/PreparedPhaseApplication.java**:

~~~java
package com.example.demo;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;

@SpringBootApplication
public class PreparedPhaseApplication {

    public static void main(String[] args) {
        System.out.println("01 | Configure application");

        SpringApplication application =
                new SpringApplication(PreparedPhaseApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.addListeners(new TimelineListener());

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println("09 | run returned; active="
                    + context.isActive());
        }

        System.out.println("10 | context closed");
    }

    @Bean
    SampleService sampleService() {
        return new SampleService();
    }

    @Bean
    ApplicationRunner startupTask(SampleService service) {
        return args -> System.out.println(
                "07 | ApplicationRunner: " + service.message());
    }

    static final class SampleService implements InitializingBean {

        SampleService() {
            System.out.println("03 | SampleService constructor");
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("04 | SampleService initialized");
        }

        String message() {
            return "hello";
        }
    }

    static final class TimelineListener
            implements ApplicationListener<ApplicationEvent> {

        @Override
        public void onApplicationEvent(ApplicationEvent event) {
            if (event instanceof ApplicationPreparedEvent prepared) {
                ConfigurableApplicationContext context =
                        prepared.getApplicationContext();

                System.out.println(
                        "02 | ApplicationPreparedEvent; active="
                        + context.isActive()
                        + "; sampleDefinition="
                        + context.containsBeanDefinition("sampleService"));
            } else if (event instanceof ContextRefreshedEvent) {
                System.out.println("05 | ContextRefreshedEvent");
            } else if (event instanceof ApplicationStartedEvent) {
                System.out.println("06 | ApplicationStartedEvent");
            } else if (event instanceof ApplicationReadyEvent) {
                System.out.println("08 | ApplicationReadyEvent");
            }
        }
    }
}
~~~

Chương trình có một **@SpringBootApplication**, một bean **SampleService**, một **ApplicationRunner** và một listener đăng ký từ sớm.

### 5.2. Giải thích điều quan sát được

- **SpringApplication(PreparedPhaseApplication.class)** chỉ định main class làm source. Boot nạp BeanDefinition của source này trước Prepared event.
- **application.addListeners(new TimelineListener())** đăng ký listener **trước khi run**; do đó listener nhận được event sớm. Không cần đợi component scan tạo listener bean.
- **ApplicationPreparedEvent** cho biết context đã có nhưng chưa refresh. Trong demo bình thường, **context.isActive()** là false; **sampleDefinition** là false bởi metadata của method **@Bean** chưa được ConfigurationClassPostProcessor phân tích.
- **SampleService** được tạo khi refresh khởi tạo singleton không lazy. Constructor và **InitializingBean.afterPropertiesSet()** in log.
- **ContextRefreshedEvent** xuất hiện khi refresh hoàn tất; **ApplicationStartedEvent** theo sau nhưng runner còn chưa chạy.
- **ApplicationRunner** chạy trước **ApplicationReadyEvent**.
- Sau khi **application.run(args)** trả về, khối try in trạng thái context đang active, rồi **try-with-resources** đóng context khi rời khối.

Việc đóng context ngay sau run là lựa chọn của **demo non-web**. Trong ứng dụng web server production, không dùng try-with-resources như vậy nếu cần phục vụ HTTP liên tục.

### 5.3. Chạy và stdout

Từ thư mục dự án được tạo bởi Spring Initializr:

~~~bash
# Linux / macOS
./mvnw spring-boot:run

# Windows (PowerShell hoặc cmd)
# .\mvnw.cmd spring-boot:run
~~~

Các dòng **do chính chương trình in ra** theo thứ tự trong cấu hình demo mặc định:

~~~text
01 | Configure application
02 | ApplicationPreparedEvent; active=false; sampleDefinition=false
03 | SampleService constructor
04 | SampleService initialized
05 | ContextRefreshedEvent
06 | ApplicationStartedEvent
07 | ApplicationRunner: hello
08 | ApplicationReadyEvent
09 | run returned; active=true
10 | context closed
~~~

Maven và Spring Boot có thể in thêm logging xen giữa; khối trên không đại diện cho toàn bộ stdout. Nếu project thêm các listener/initializers tự sửa BeanDefinition trước Prepared, kết quả kiểm tra definition có thể thay đổi; ví dụ giả định cấu hình ban đầu như đã mô tả.

**Tại sao dòng 02 là false nhưng tài liệu bảo đã nạp BeanDefinition?** Vì Spring đã nạp **primary source** chứ chưa nhất thiết phân tích **tất cả method @Bean** của primary source. Đó chính là ranh giới giữa nạp nguồn cấu hình và refresh.

Khi cần biên dịch project, dùng Maven/Gradle Wrapper để cung cấp Spring Boot dependencies. **javac PreparedPhaseApplication.java** riêng lẻ không chạy được nếu không chỉ định các Spring JAR trên classpath.

## 6. Đăng ký listener đúng lúc để nhận ApplicationPreparedEvent

### Cách 1 — SpringApplication.addListeners

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.addListeners(new MyListener());
application.run(args);
~~~

Đoạn trên minh họa API; **MyApplication** và **MyListener** cần được định nghĩa trong project thật. Đây là cách rõ ràng khi bạn kiểm soát main.

### Cách 2 — SpringApplicationBuilder.listeners

~~~java
new SpringApplicationBuilder(MyApplication.class)
        .listeners(new MyListener())
        .run(args);
~~~

Builder phù hợp khi muốn cấu hình startup theo fluent API. Listener được thêm trước khi **run(args)** thực hiện bootstrap.

### Cách 3 — đăng ký tự động từ một thư viện

Để một thư viện gắn listener vào mọi ứng dụng sử dụng thư viện đó, Spring Boot 3.5 hỗ trợ key **org.springframework.context.ApplicationListener** trong file **META-INF/spring.factories**.

Ví dụ **src/main/resources/META-INF/spring.factories**:

~~~properties
org.springframework.context.ApplicationListener=com.example.demo.MyListener
~~~

Đây là ví dụ cú pháp đăng ký; phải có class **com.example.demo.MyListener** được triển khai với constructor phù hợp. **Không thêm file này vào project demo ở mục 5 nếu chưa định nghĩa class**; ví dụ chạy được đã dùng cách 1.

**@Component**, **@Bean** hoặc **@EventListener** trong container có thể quá muộn để nhận Prepared event vì container chưa refresh. Đừng giả định annotation listener trong một business bean sẽ bắt được những sự kiện khởi động đã phát trước khi bean được tạo.

Cũng đừng đăng ký cùng một listener qua cả **addListeners** và **spring.factories** nếu không muốn nhận event nhiều lần do có nhiều instance.

## 7. Có thể làm gì khi ApplicationPreparedEvent được phát?

Những việc phù hợp thường nhẹ, rõ mục đích bootstrap:

- **Quan sát Environment:** kiểm tra active profiles và các thuộc tính đã được chuẩn bị, tránh log token/mật khẩu.
- **Đọc BeanDefinition metadata:** xác nhận nguồn cấu hình hay định nghĩa do một initializer đăng ký đã xuất hiện.
- **Đo và ghi dấu startup:** ghi mốc thời gian hoặc counter để phân tích trình tự chuẩn bị context.
- **Thêm metadata/định nghĩa có chủ đích:** chỉ khi hiểu rõ BeanDefinitionRegistry và có nhu cầu framework-level trước refresh.
- **Tích hợp extension của thư viện:** ví dụ một listener trong thư viện cần biết context đã có và primary sources đã load.

Ví dụ đọc số lượng definitions:

~~~java
ConfigurableApplicationContext context =
        event.getApplicationContext();

String[] names =
        context.getBeanFactory().getBeanDefinitionNames();

System.out.println("Definitions currently loaded=" + names.length);
~~~

Mảnh code trên nằm trong một listener; chưa phải file Java độc lập. Không dựa vào một con số cố định. Kết quả không chứng minh mọi bean đã khởi tạo.

### Khi thực sự muốn bổ sung một BeanDefinition

Một số context còn cho phép đăng ký programmatic definitions trước refresh thông qua **BeanDefinitionRegistry** hoặc API đăng ký tương ứng, nhưng đây là extension cấp container. Phải hiểu namespace, tên, scope và nguy cơ xung đột với những definition sẽ được tạo trong refresh.

Đừng chọn Prepared event chỉ để "lách" cấu hình bean thông thường. Nếu chỉ khai báo một service, **@Component** hoặc **@Bean** dễ hiểu và có ít rủi ro hơn. Nếu phải sửa metadata hàng loạt trong lúc Spring xử lý configuration classes, **BeanDefinitionRegistryPostProcessor** thường phù hợp hơn.

## 8. Điều gì không nên làm ở Prepared event?

### 8.1. Không tự tạo business bean bằng getBean

~~~java
DataSource ds =
        event.getApplicationContext().getBean(DataSource.class);
~~~

Đây là **mảnh phản ví dụ**, giả định đã import **javax.sql.DataSource**. Context chưa refresh; BeanFactoryPostProcessor và BeanPostProcessor có thể chưa chạy, các @Bean definitions từ @Configuration có thể chưa được sinh ra. Do đó code có thể lỗi, buộc khởi tạo bean quá sớm hoặc bỏ qua vòng đời thông thường.

**Không dùng Prepared listener để truy cập database, gửi message hay gọi business service**. Những công việc này nên thực hiện ở hook sau refresh hoặc qua một thành phần quản lý readiness đúng trách nhiệm.

### 8.2. Không tự gọi context.refresh()

**SpringApplication.run(...)** sẽ refresh context sau Prepared event. Gọi **context.refresh()** trong listener có thể làm xáo trộn lifecycle, khiến Spring cố khởi động trùng hoặc làm context không hỗ trợ refresh lặp bị lỗi.

### 8.3. Không đặt công việc blocking dài

Listener startup thường chạy đồng bộ theo mặc định. Gọi API mạng không timeout, quét lượng lớn dữ liệu hoặc sleep có thể kéo dài thời gian startup và gây timeout orchestration. Nếu công việc bắt buộc trước application-ready, cân nhắc **ApplicationRunner** với timeout/failure policy phù hợp.

### 8.4. Không mong thay đổi config quá muộn sẽ chạy lại bootstrap

**Environment** được chuẩn bị trước Prepared. Một số thông tin như **spring.config.name**, **spring.config.location** hoặc profile liên quan đến **ConfigData** có thể đã được xử lý trước event. Thêm property tại đây **không khiến Spring Boot tự chạy lại ConfigDataEnvironmentPostProcessor hoặc nạp lại mọi file theo lựa chọn mới**.

Khi cần can thiệp cấu hình trước bước này, sử dụng **EnvironmentPostProcessor** với ordering phù hợp, cấu hình CLI/environment/system property hoặc một ConfigData extension thích hợp.

### 8.5. Không xem đây là readiness signal

**ApplicationPreparedEvent** phát trước ContextRefreshedEvent, ApplicationStartedEvent và runners. HTTP server có thể vẫn chưa được tạo. Một instance được đánh dấu ready chỉ sau những điều kiện tương ứng của Boot/readiness probes, không phải chỉ nhờ Prepared event.

## 9. So sánh với các extension point và events gần nó

| Hook/event | Thời điểm | Trạng thái context | Phù hợp để làm gì? |
| --- | --- | --- | --- |
| **EnvironmentPostProcessor** | Pha chuẩn bị Environment | Chưa cần context đã refresh | Thêm PropertySource sớm |
| **ApplicationContextInitializer** | Sau tạo context, trước Boot nạp nguồn và trước refresh | Có context, chưa refresh | Cấu hình context ban đầu |
| **ApplicationContextInitializedEvent** | Sau initializers, trước load sources | Context có, chưa nạp sources | Quan sát mốc context initialized |
| **ApplicationPreparedEvent** | **Sau load source definitions, trước refresh** | Context có, chưa active hoàn chỉnh | Quan sát/can thiệp metadata đã nạp |
| **BeanDefinitionRegistryPostProcessor** | Trong refresh, trước tạo bean nghiệp vụ | Registry đang được xử lý | Đăng ký/thay đổi definitions |
| **BeanFactoryPostProcessor** | Trong refresh | BeanFactory đang chuẩn bị | Sửa metadata về bean |
| **BeanPostProcessor** | Quanh initialization từng bean | Có instance đang được xử lý | Callback, AOP/proxy, injection support |
| **ContextRefreshedEvent** | Sau refresh | Context đã refresh | Chạy phản ứng ở mức context |
| **ApplicationStartedEvent** | Sau refresh, trước runners | Context đã refresh | Theo dõi Boot started |
| **ApplicationRunner** | Sau started, trước ready | Context hoạt động | Startup task cần hoàn tất trước ready |
| **ApplicationReadyEvent** | Sau runners | Boot báo startup đã hoàn tất | Phản ứng ở mốc ready |

Hai khác biệt đặc biệt đáng nhớ:

**Prepared khác Initialized:** tại initialized, initializers đã chạy nhưng SpringApplication chưa nạp các primary source definitions. Tại prepared, sources đã được nạp; refresh còn ở phía sau.

**Prepared khác Started:** tại started, refresh đã hoàn tất và các singleton non-lazy cần thiết thường đã được tạo. Prepared còn ở trước refresh, không bảo đảm business bean sẵn sàng.

## 10. Tình huống thực tế: kiểm tra kết nối DB đúng thời điểm

Một ứng dụng cần kiểm tra DataSource trước khi phục vụ request. Cách sai là lấy DataSource trong Prepared listener, vì có thể chưa khởi tạo.

Nếu project cần kết thúc startup khi cấu hình bắt buộc không hợp lệ, có thể dùng một runner như ví dụ sau, đặt trong một class **@Configuration**:

~~~java
@Bean
ApplicationRunner verifyDatasourceConfiguration(
        Environment environment) {
    return args -> {
        String url =
                environment.getProperty("spring.datasource.url");

        if (url == null || url.isBlank()) {
            throw new IllegalStateException(
                    "Missing spring.datasource.url");
        }
    };
}
~~~

Đây là **mảnh cấu hình**, không phải file độc lập. Cần imports **ApplicationRunner**, **Bean**, **Environment** và project có chính sách datasource tương ứng. Mục đích là chỉ ra **runner chạy sau refresh** và có thể chặn ready nếu ném exception. Nó chỉ kiểm tra **config URL tồn tại**, chưa chứng minh DB kết nối thành công.

Nếu cần xác minh kết nối trước readiness, kiểm tra thực sự với timeout, retry/failure policy và health/readiness riêng phù hợp. Không đưa network check không giới hạn vào Prepared listener.

## 11. Khi có parent/child context hoặc chạy test

Trong hierarchy tạo bởi **SpringApplicationBuilder.parent(...).child(...)**, mỗi context có lifecycle riêng. Sự kiện context con có thể được publish lên các context tổ tiên. Một listener gắn ở parent có thể nhận nhiều event cùng loại. Khi phân tích, kiểm tra **event.getApplicationContext()** thay vì chỉ đếm sự kiện.

Trong **@SpringBootTest**, Spring Test có thể cache/reuse ApplicationContext. Không được giả định Prepared event sẽ phát lại **mỗi test method**. Khi cần test thứ tự startup, có thể tạo riêng một SpringApplication do test quản lý và gắn listener trước run, hoặc dùng **ApplicationContextRunner** cho những bài test cấu hình/auto-configuration thích hợp (nó không nhất thiết phát trọn cùng một dãy SpringApplication events).

Nếu listener/initializer do ứng dụng đăng ký có side effect, hãy thiết kế theo hướng idempotent khi có thể và không phụ thuộc vào thứ tự không được cam kết giữa các listener cùng priority.

## 12. Lỗi thường gặp và cách xử lý

| Dấu hiệu / nhầm lẫn | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không nhận ApplicationPreparedEvent trong bean listener | Bean được tạo sau event | Đăng ký từ main bằng addListeners hoặc factories |
| Đã có BeanDefinition mà getBean lỗi | Context chưa refresh/bean chưa sẵn sàng | Chờ hook sau refresh, tránh lấy bean trong Prepared |
| containsBeanDefinition cho @Bean method trả false | ConfigurationClassPostProcessor chưa phân tích @Bean | Quan sát sau refresh, phân biệt source definition |
| Nghĩ Prepared nghĩa là ứng dụng ready | Event phát trước refresh và runners | Dùng ApplicationReadyEvent/readiness phù hợp |
| Thấy context.isActive=false và kết luận lỗi | Context đang ở pha trước refresh | Đây có thể là hành vi đúng |
| Có Environment nhưng @ConfigurationProperties chưa bind | Bean config vẫn thuộc lifecycle sau đó | Đọc Environment khi cần, đừng ép bean tạo sớm |
| Thêm spring.config.location tại Prepared nhưng config không đổi | ConfigData đã được nạp sớm | Chỉ định config từ nguồn đủ sớm |
| Gọi context.refresh trong listener gây lỗi | SpringApplication tự quản lý refresh | Không gọi refresh thủ công |
| Listener bị gọi nhiều lần | Đăng ký lặp hoặc nhiều context | Kiểm tra nguồn đăng ký/context |
| Startup bị treo ở listener | Listener làm I/O chậm hoặc blocking | Giảm công việc, thêm timeout, chuyển hook |
| Bean chưa thấy dù classpath có | Điều kiện auto-configuration/chưa xử lý @Configuration | Đọc Condition Evaluation Report và thứ tự lifecycle |
| Mở cổng HTTP khi Prepared chưa xong | Không nên kỳ vọng server đã ready tại mốc này | Quan sát WebServerInitializedEvent/ready/probes |

Spring Boot hỗ trợ **--debug** để xem Condition Evaluation Report trong các trường hợp cần tìm hiểu auto-configuration, nhưng không nên coi report là bằng chứng bean đã được tạo tại Prepared.

## 13. Bài tập và câu trả lời gợi ý

**Bài 1.** Sắp xếp: ApplicationContextInitializedEvent, ContextRefreshedEvent, ApplicationPreparedEvent, ApplicationStartedEvent, ApplicationReadyEvent.

**Bài 2.** Tại Prepared event, **containsBeanDefinition("sampleService")=false** dù Spring đã nạp nguồn **DemoApplication.class**. Có mâu thuẫn không?

**Bài 3.** Một listener có **@Component** nhưng không thấy ApplicationPreparedEvent. Vì sao và nên đăng ký thế nào?

**Bài 4.** Có thể gọi repository trong Prepared listener để kiểm tra DB không? Nêu rủi ro.

**Bài 5.** Khi muốn bổ sung một PropertySource ảnh hưởng đến việc nạp ConfigData, có nên đợi tới Prepared event không?

**Bài 6.** Sau Prepared event, một bean @Bean được tạo, rồi ApplicationRunner ném exception. Những event nào đã xảy ra, và event nào không xảy ra trong startup thất bại này?

**Đáp án ngắn:**

1. Initialized → Prepared → ContextRefreshed → Started → Ready (trong startup thành công).
2. Không. Primary source có thể đã nạp, còn @Bean method được parser xử lý trong refresh.
3. Bean listener được tạo quá muộn; đăng ký bằng **SpringApplication.addListeners**, builder listeners hoặc **META-INF/spring.factories**.
4. Không nên; context chưa refresh và dependency/BeanPostProcessor chưa hoàn chỉnh.
5. Thường không; phải can thiệp trước ConfigData hoặc dùng extension phù hợp.
6. Prepared, ContextRefreshed, Started có thể đã xảy ra; runner lỗi làm startup fail nên **ApplicationReadyEvent không phát**.

## 14. Ghi nhớ và tài liệu chính thức

**ApplicationPreparedEvent xuất hiện sau khi SpringApplication nạp các nguồn BeanDefinition ban đầu nhưng trước khi refresh ApplicationContext.** Đã có context và Environment; **chưa thể xem mọi bean đã được khởi tạo hoặc ứng dụng đã ready**.

Dãy mốc cần thuộc:

~~~text
ApplicationContextInitializedEvent
     -> load primary BeanDefinitions
     -> ApplicationPreparedEvent
     -> refresh() / ContextRefreshedEvent
     -> ApplicationStartedEvent
     -> ApplicationRunner / CommandLineRunner
     -> ApplicationReadyEvent
~~~

Tài liệu chính thức tương ứng với phiên bản dự án:

1. Spring Boot 3.5 — SpringApplication, mục Application Events and Listeners: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot 3.5 JavaDoc — ApplicationPreparedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html
3. Spring Boot 3.5 JavaDoc — ApplicationContextInitializedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html
4. Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
5. Spring Framework — Java Configuration và @Bean: https://docs.spring.io/spring-framework/reference/core/beans/java/basic-concepts.html

Ví dụ sử dụng **Java 17+ / Spring Boot 3.5.x**. Với các phiên bản Spring Boot khác, nên đối chiếu JavaDoc của phiên bản tương ứng, đặc biệt về sự kiện bootstrap, lựa chọn ApplicationContext và cách đăng ký listener.