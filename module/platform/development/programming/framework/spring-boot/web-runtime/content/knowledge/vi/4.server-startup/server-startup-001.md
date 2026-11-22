# Từ `SpringApplication.run` đến `ApplicationContext` của ứng dụng web

Trong ứng dụng Spring Boot, lời gọi `SpringApplication.run(...)` khởi động một chuỗi công việc: chuẩn bị cấu hình, chọn loại ứng dụng web, tạo `ApplicationContext`, nạp và xử lý bean definition, khởi tạo các bean cần thiết, tạo embedded web server, chạy các tác vụ sau khởi động rồi thông báo ứng dụng đã sẵn sàng. Hiểu chuỗi này giúp xác định bean được tạo ở đâu, server bắt đầu nhận request khi nào và nên đặt logic khởi tạo tại vị trí nào.

## 1. Phân biệt SpringApplication, ApplicationContext và web server

**SpringApplication** là bộ điều phối quá trình khởi động của Spring Boot. Nó nhận một hoặc nhiều primary source (thường là class có `@SpringBootApplication`), chuẩn bị Environment và ApplicationContext, gọi refresh, phát lifecycle event và chạy các runner.

**ApplicationContext** là container IoC của Spring. Nó quản lý bean definition, tạo và giữ bean instance, cung cấp Environment, resource loading, event publishing, message source và quan hệ parent-child context.

Cần phân biệt:
- **Bean definition** là metadata mô tả cách tạo bean: class, constructor, scope, dependency và các thuộc tính liên quan.
- **Bean instance** là đối tượng Java thực tế được tạo từ definition.
- **BeanFactory** là nền tảng quản lý việc tạo và phân phối bean.
- **ApplicationContext** mở rộng BeanFactory và bổ sung event, resource, Environment cùng các dịch vụ cấp ứng dụng.

**Embedded web server** tiếp nhận kết nối HTTP và chuyển request vào hạ tầng web của Spring. Với Servlet, Tomcat thường là server mặc định khi dùng `spring-boot-starter-web`; có thể thay bằng Jetty hoặc Undertow nếu cấu hình dependency tương ứng. Với WebFlux, Reactor Netty thường là lựa chọn mặc định của `spring-boot-starter-webflux`.

ApplicationContext không đồng nghĩa với web server. Context quản lý ứng dụng; web server là một thành phần runtime được tạo và quản lý trong web ApplicationContext. Khi context đóng, server cũng được dừng.

## 2. Điểm bắt đầu: class ứng dụng và SpringApplication.run

Một ứng dụng Spring Boot thường có class chính:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}
~~~

`@SpringBootApplication` kết hợp ba vai trò:
- `@SpringBootConfiguration`: đánh dấu cấu hình chính của ứng dụng.
- `@EnableAutoConfiguration`: bật cơ chế cấu hình tự động.
- `@ComponentScan`: quét component theo package của class chính và các package con theo cấu hình mặc định.

Class được truyền vào `SpringApplication.run` là primary source để Spring Boot bắt đầu nạp cấu hình. Tham số `args` là tham số dòng lệnh của tiến trình. Spring Boot phân tích chúng thành `ApplicationArguments` và đưa option dạng `--key=value` vào Environment.

Ví dụ:

~~~bash
java -jar app.jar --server.port=8081 --spring.profiles.active=local
~~~

`SpringApplication.run` trả về `ConfigurableApplicationContext`. Khi lời gọi trả về bình thường, startup tiêu chuẩn đã đi qua các runner và phát `ApplicationReadyEvent`.

## 3. Spring Boot chọn loại ApplicationContext nào?

Spring Boot xác định `WebApplicationType` dựa trên classpath và cấu hình:

| WebApplicationType | Mục đích | Context thường dùng |
|---|---|---|
| `SERVLET` | Ứng dụng Servlet, ví dụ Spring MVC | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | Ứng dụng reactive, ví dụ Spring WebFlux | `AnnotationConfigReactiveWebServerApplicationContext` |
| `NONE` | Ứng dụng không khởi tạo web server | `AnnotationConfigApplicationContext` |

Spring Boot suy luận loại ứng dụng từ các class web có trên classpath. Nếu cả Spring MVC và WebFlux cùng xuất hiện, Spring Boot thường chọn mô hình Servlet/MVC theo mặc định. Có thể chỉ định rõ loại ứng dụng bằng thuộc tính:

~~~properties
spring.main.web-application-type=servlet
~~~

Các giá trị hợp lệ tương ứng là `servlet`, `reactive` và `none`. Cũng có thể cấu hình bằng code:

~~~java
SpringApplication app = new SpringApplication(WebRuntimeApplication.class);
app.setWebApplicationType(WebApplicationType.SERVLET);
app.run(args);
~~~

Chỉ định `SERVLET` hoặc `REACTIVE` không tự bổ sung dependency còn thiếu. Ứng dụng vẫn cần starter và thư viện runtime tương ứng.

Không phải mọi lần gọi `SpringApplication.run` đều tạo web server. Khi loại ứng dụng là `NONE`, Spring Boot vẫn tạo ApplicationContext và quản lý bean nhưng không mở cổng HTTP.

## 4. Toàn cảnh vòng đời của SpringApplication.run

Có thể chia quá trình startup thành các pha:

1. Khởi tạo SpringApplication, bootstrap context và các run listener.
2. Chuẩn bị Environment: property source, profile, cấu hình bên ngoài và tham số dòng lệnh.
3. Tạo ApplicationContext theo WebApplicationType.
4. Chuẩn bị context: gắn Environment, chạy initializer và nạp primary source.
5. Refresh context: xử lý bean definition, auto-configuration và tạo các singleton cần thiết.
6. Tạo rồi khởi động embedded web server nếu là ứng dụng web.
7. Phát ApplicationStartedEvent, chạy ApplicationRunner và CommandLineRunner.
8. Phát ApplicationReadyEvent và trả ApplicationContext về cho caller.

Đây là thứ tự khái niệm của luồng khởi động tiêu chuẩn. Một số event nội bộ và thao tác phụ trợ diễn ra xen giữa các pha; ứng dụng có thể mở rộng luồng này bằng listener, initializer hoặc customizer.

## 5. Pha chuẩn bị Environment

Environment chứa các nguồn cấu hình mà ứng dụng có thể truy cập, ví dụ:
- File cấu hình như `application.properties` hoặc `application.yml`.
- File theo profile như `application-local.yml`.
- Biến môi trường của hệ điều hành.
- Java system properties.
- Tham số dòng lệnh.
- Property source do ứng dụng hoặc thư viện bổ sung.

Spring Boot xử lý Config Data và profile trong giai đoạn chuẩn bị Environment. Giá trị cấu hình sau đó được bean, auto-configuration và điều kiện cấu hình sử dụng.

Ví dụ:

~~~yaml
server:
  port: 8081

spring:
  application:
    name: order-service
  profiles:
    active: local
~~~

Một bean có thể đọc cấu hình qua Environment hoặc `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {}
~~~

Khi dùng `@ConfigurationProperties`, cần đăng ký class theo cơ chế phù hợp, ví dụ `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

Environment được chuẩn bị trước khi context refresh. Vì vậy, profile và cấu hình ảnh hưởng đến việc nạp Config Data cần được xác định bằng nguồn cấu hình thích hợp trong pha chuẩn bị Environment, chẳng hạn biến môi trường, tham số dòng lệnh hay file cấu hình.

## 6. Tạo và chuẩn bị ApplicationContext

Sau khi Environment được chuẩn bị, SpringApplication tạo context phù hợp với loại ứng dụng.

Với ứng dụng web Servlet, context là web ApplicationContext có khả năng tích hợp `ServletWebServerFactory`. Với ứng dụng reactive, context tích hợp `ReactiveWebServerFactory`.

Trong pha chuẩn bị context, Spring Boot thực hiện các công việc chính:
- Gắn Environment đã chuẩn bị vào context.
- Thiết lập các thuộc tính và customizer dành cho context.
- Chạy các `ApplicationContextInitializer` đã đăng ký.
- Đăng ký và nạp primary source, thường là class chứa `@SpringBootApplication`.
- Thông báo cho listener rằng context đã được chuẩn bị và nạp source.

`ApplicationContextInitializer` cho phép tùy chỉnh context trước khi refresh. Nó phù hợp với việc đăng ký một số thiết lập cấp context hoặc điều chỉnh cấu trúc context trước khi bean được khởi tạo. Không nên dùng initializer để thực hiện công việc nghiệp vụ cần dependency injection đầy đủ, vì các singleton thông thường chưa được tạo ở thời điểm này.

Ví dụ đăng ký initializer:

~~~java
SpringApplication app = new SpringApplication(WebRuntimeApplication.class);

app.addInitializers(context ->
    context.setId("order-service-context")
);

app.run(args);
~~~

Initializer trên minh họa việc tùy chỉnh metadata của context trước refresh. Nếu cần cấu hình Environment để nạp profile hoặc Config Data, hãy đặt cấu hình trong đúng pha chuẩn bị Environment thay vì chờ đến initializer.

## 7. Refresh: nơi Spring xây dựng container

`refresh()` là bước trọng tâm. Đây là lúc context chuyển từ trạng thái được chuẩn bị sang trạng thái đã khởi tạo hạ tầng và bean cần thiết.

Các bước chính của `AbstractApplicationContext.refresh()` gồm:

1. **prepareRefresh**: đánh dấu context đang refresh, kiểm tra trạng thái và chuẩn bị cấu trúc nội bộ.
2. **obtainFreshBeanFactory**: lấy BeanFactory mới hoặc làm mới BeanFactory của context.
3. **prepareBeanFactory**: đăng ký các thành phần nền tảng và cấu hình môi trường cho BeanFactory.
4. **postProcessBeanFactory**: cho phép context chuyên biệt bổ sung xử lý cho BeanFactory.
5. **invokeBeanFactoryPostProcessors**: chạy BeanFactoryPostProcessor để xử lý hoặc thay đổi bean definition trước khi tạo bean thông thường.
6. **registerBeanPostProcessors**: đăng ký BeanPostProcessor, được dùng để can thiệp vào quá trình tạo bean instance, ví dụ xử lý annotation và proxy.
7. **initMessageSource**: khởi tạo message source cho chức năng message/i18n.
8. **initApplicationEventMulticaster**: chuẩn bị cơ chế phát event trong context.
9. **onRefresh**: cho phép context chuyên biệt khởi tạo hạ tầng bổ sung; web context tạo web server từ factory ở giai đoạn này.
10. **registerListeners**: đăng ký các listener đã biết với event multicaster.
11. **finishBeanFactoryInitialization**: khởi tạo các singleton không lazy còn lại và hoàn tất BeanFactory.
12. **finishRefresh**: khởi động lifecycle component, phát `ContextRefreshedEvent` và hoàn tất refresh.

Không phải mọi bean đều được tạo ngay khi gọi `SpringApplication.run`. Bean singleton thông thường được tạo trong quá trình hoàn tất refresh; bean có `@Lazy` có thể chỉ được tạo khi lần đầu được yêu cầu. Bean prototype được tạo theo từng lần yêu cầu từ container.

### 7.1. Configuration class và component scan

Trong quá trình xử lý BeanFactoryPostProcessor, Spring phân tích class cấu hình, component scan và import. Các annotation như `@Configuration`, `@Bean`, `@Component`, `@Service`, `@Repository` và `@Controller` đóng góp bean definition vào context.

Vị trí package của class có `@SpringBootApplication` rất quan trọng. Component scan mặc định bắt đầu từ package của class này và đi xuống các package con. Nếu class chính nằm quá sâu, quá trình quét có thể không bao phủ các package cần thiết. Nên đặt class ứng dụng ở package gốc của phần mã ứng dụng.

### 7.2. Auto-configuration

`@EnableAutoConfiguration` cho phép Spring Boot đưa vào các cấu hình dựa trên classpath, property và các bean đã có. Các cấu hình này thường sử dụng điều kiện như:
- Classpath có hoặc không có một class.
- Một property có giá trị cụ thể.
- Context đã có hoặc chưa có một bean.
- Ứng dụng đang chạy với loại web context tương ứng.

Auto-configuration không tạo mọi bean có thể có. Mỗi cấu hình chỉ áp dụng khi các điều kiện phù hợp. Nhiều cấu hình còn có cơ chế back-off: nếu ứng dụng đã tự cung cấp bean phù hợp, cấu hình mặc định có thể không tạo bean thay thế.

Ví dụ, khi có Spring MVC và embedded server dependency, Boot có thể cấu hình DispatcherServlet và web server factory. Nếu ứng dụng tự khai báo một số bean hạ tầng, kết quả auto-configuration có thể thay đổi theo điều kiện.

## 8. Web ApplicationContext tạo và khởi động server

Với ứng dụng Servlet, `ServletWebServerApplicationContext` tích hợp `ServletWebServerFactory`. Với ứng dụng reactive, `ReactiveWebServerApplicationContext` tích hợp `ReactiveWebServerFactory`.

Cần phân biệt hai việc:
- Trong hook `onRefresh()` của web context, Spring Boot tạo web server từ factory và cấu hình servlet/filter/initializer cần thiết.
- Trong `finishRefresh()`, sau khi phần refresh cơ sở hoàn tất, web context khởi động web server và phát event thông báo server đã khởi tạo.

Với Servlet, event cụ thể là `ServletWebServerInitializedEvent`; với reactive, event tương ứng là `ReactiveWebServerInitializedEvent`. Event chứa web server và context liên quan. Đây là thời điểm có thể đọc port thực tế, đặc biệt khi cấu hình `server.port=0` để hệ điều hành cấp cổng ngẫu nhiên.

Việc server được tạo và bắt đầu nhận request là một phần của refresh web context. `SpringApplication.run` chỉ tiếp tục đến các bước sau khi refresh hoàn tất. Vì vậy, với startup thành công, server đã được khởi động trước khi `ApplicationStartedEvent` được phát.

Dependency `spring-boot-starter-web` thường đưa Tomcat embedded vào ứng dụng Servlet. Nếu thay embedded server, factory tương ứng sẽ được auto-configure dựa trên dependency và cấu hình. Với WebFlux, server factory thuộc reactive stack.

## 9. Các lifecycle event quan trọng

Spring Boot phát event để listener có thể quan sát tiến trình startup:

| Event | Thời điểm | Có thể dùng để |
|---|---|---|
| `ApplicationStartingEvent` | Rất sớm, trước khi Environment và ApplicationContext sẵn sàng | Theo dõi tiến trình bắt đầu; đăng ký listener trước khi run |
| `ApplicationEnvironmentPreparedEvent` | Environment đã được chuẩn bị | Quan sát cấu hình và profile đã nạp |
| `ApplicationContextInitializedEvent` | Context đã được tạo và initializer đã chạy, trước khi nạp source | Theo dõi context ở pha chuẩn bị |
| `ApplicationPreparedEvent` | Context đã được chuẩn bị và nạp source, trước refresh | Quan sát context trước khi refresh |
| `ContextRefreshedEvent` | Context hoàn tất refresh cơ sở | Biết context đã refresh |
| `ServletWebServerInitializedEvent` hoặc `ReactiveWebServerInitializedEvent` | Embedded web server đã được khởi động | Lấy port và thông tin web server |
| `ApplicationStartedEvent` | Sau refresh, trước các runner | Xử lý tại mốc application started |
| `ApplicationReadyEvent` | Sau khi các runner hoàn tất | Bắt đầu công việc cần ứng dụng đã sẵn sàng |
| `ApplicationFailedEvent` | Startup thất bại | Ghi nhận lỗi khởi động |

`ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent` diễn ra trước khi ApplicationContext thông thường có thể quản lý bean listener. Muốn nhận event sớm, cần đăng ký listener với `SpringApplication` trước khi gọi `run` hoặc dùng cơ chế đăng ký listener toàn cục phù hợp. Một bean có `@EventListener` trong context không thể nhận ngược event đã phát trước khi bean đó tồn tại.

Không nên nhầm `ContextRefreshedEvent` với `ApplicationReadyEvent`. Context đã refresh không có nghĩa mọi tác vụ startup đã hoàn thành. `ApplicationRunner` và `CommandLineRunner` còn chạy sau `ApplicationStartedEvent`, trước `ApplicationReadyEvent`.

## 10. ApplicationRunner và CommandLineRunner

Spring Boot chạy các bean triển khai `ApplicationRunner` hoặc `CommandLineRunner` sau khi ApplicationContext refresh thành công và trước `ApplicationReadyEvent`.

Khác biệt chính:
- `ApplicationRunner` nhận `ApplicationArguments`, có API để truy cập option và non-option arguments.
- `CommandLineRunner` nhận trực tiếp mảng `String... args`.

Ví dụ:

~~~java
@Component
class StartupTasks implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Application arguments: "
            + args.getOptionNames());
    }
}
~~~

Có thể khai báo runner bằng `@Bean`:

~~~java
@Configuration
class StartupConfiguration {

    @Bean
    ApplicationRunner verifyStartupConfiguration() {
        return args -> {
            // Kiểm tra cấu hình bắt buộc hoặc nạp dữ liệu khởi tạo nhỏ.
        };
    }
}
~~~

Nếu có nhiều runner, dùng `Ordered` hoặc `@Order` để xác định thứ tự chạy. Exception không được xử lý trong runner có thể làm startup thất bại; runner nên có phạm vi rõ ràng, thời gian thực thi hợp lý và xử lý lỗi có chủ đích.

Không nên đưa mọi công việc khởi tạo dài vào runner. Gọi dịch vụ ngoài, đồng bộ dữ liệu lớn hoặc chờ tác vụ lâu có thể trì hoãn `ApplicationReadyEvent`. Hãy cân nhắc timeout, retry, tính idempotent và khả năng phục hồi khi công việc thất bại.

## 11. Ví dụ quan sát vòng đời ứng dụng Servlet

Ví dụ sau dùng Spring Boot 3.x và Java 17+ (cũng phù hợp Java 21). Đặt các class trong cùng package hoặc package con của class ứng dụng. Project cần dependency `spring-boot-starter-web`.

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebRuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}

@Component
class StartupObserver implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ApplicationRunner executed");
    }

    @EventListener
    public void onWebServerInitialized(
            ServletWebServerInitializedEvent event) {
        System.out.println("Web server port: "
            + event.getWebServer().getPort());
    }

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("Application is ready: "
            + event.getApplicationContext().getId());
    }
}

@RestController
class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
~~~

Chạy ứng dụng trong project Spring Boot:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Gọi endpoint:

~~~bash
curl -i http://localhost:8080/hello
~~~

Response body là:

~~~text
Hello from Spring Boot
~~~

Thông tin port trong log phụ thuộc cấu hình server. Nếu cấu hình `server.port=0`, hãy dùng port được in từ `ServletWebServerInitializedEvent` để gửi request. Thứ tự log có thể xen với log nội bộ của Spring Boot và embedded server; không nên dùng thứ tự dòng log tùy ý làm hợp đồng lifecycle.

## 12. Tùy chỉnh SpringApplication trước khi run

Có thể tạo instance `SpringApplication` thay vì dùng static method để tùy chỉnh startup:

~~~java
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

public class CustomBootstrap {

    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(WebRuntimeApplication.class);

        app.setWebApplicationType(WebApplicationType.SERVLET);
        app.setBannerMode(Banner.Mode.OFF);
        app.setApplicationStartup(
            new BufferingApplicationStartup(2048)
        );

        app.run(args);
    }
}
~~~

Một số điểm có thể tùy chỉnh:
- `setWebApplicationType`: chọn Servlet, Reactive hoặc None.
- `setDefaultProperties`: cung cấp cấu hình mặc định; nguồn cấu hình có độ ưu tiên cao hơn có thể ghi đè.
- `addInitializers`: đăng ký ApplicationContextInitializer.
- `addListeners`: đăng ký ApplicationListener.
- `setBannerMode`: bật/tắt banner.
- `setApplicationStartup`: thu thập thông tin startup step để phân tích thời gian khởi động.

Chỉ tùy chỉnh khi có yêu cầu rõ. Ép WebApplicationType có thể làm ứng dụng khởi động sai nếu dependency của stack tương ứng không có mặt.

## 13. Khi startup thất bại

Startup có thể dừng ở nhiều pha khác nhau:

| Triệu chứng | Pha thường liên quan | Hướng kiểm tra |
|---|---|---|
| Không đọc được cấu hình hoặc profile | Chuẩn bị Environment | Tên file, profile, biến môi trường, tham số dòng lệnh và thứ tự ưu tiên property source |
| Không tìm thấy bean | Xử lý configuration/component scan hoặc tạo bean | Package scan, điều kiện auto-configuration, qualifier và dependency |
| Bean khởi tạo ném exception | Refresh, tạo singleton | Constructor, `@PostConstruct`, kết nối hạ tầng và cấu hình bean |
| Không tạo được web server | Web context onRefresh | WebApplicationType, starter, server factory và dependency xung đột |
| Port đã được sử dụng | Khởi động embedded server | Giá trị server.port, tiến trình đang chiếm port và quyền bind |
| Runner thất bại | Sau ApplicationStartedEvent | Logic runner, dữ liệu bên ngoài, timeout và exception |
| Không nhận được request dù context đã tạo | Web server hoặc mapping | Server đã start chưa, port, context path, controller mapping và network |

Khi startup thất bại, Spring Boot phát `ApplicationFailedEvent` khi có thể, ghi nhận exception và đóng context đã tạo để giải phóng tài nguyên. Nếu server đã được khởi động trước khi runner lỗi, việc đóng context sẽ dừng server.

### 13.1. Xem auto-configuration đã áp dụng

Chạy ứng dụng với option `--debug` để xem condition evaluation report:

~~~bash
./gradlew bootRun --args="--debug"
~~~

Báo cáo giúp xác định auto-configuration nào được áp dụng, cấu hình nào bị loại và điều kiện nào không thỏa. Kết hợp với log của package liên quan để tìm nguyên nhân thiếu bean hoặc bean được tạo ngoài dự kiến.

### 13.2. Đo thời gian startup

Có thể dùng `BufferingApplicationStartup` để thu thập startup step. Với ứng dụng có Spring Boot Actuator, có thể cấu hình endpoint startup phù hợp để xem các bước được ghi nhận. Cần cấu hình và bảo vệ endpoint quản trị theo chính sách của ứng dụng.

Không nên kết luận startup chậm chỉ từ một dòng log tổng thời gian. Hãy phân tích từng startup step, đặc biệt các bước tạo bean, đọc cấu hình, khởi tạo connection pool, gọi dịch vụ ngoài và khởi động web server.

## 14. Đóng ApplicationContext và dừng web server

Khi ứng dụng kết thúc, context phải được đóng để giải phóng tài nguyên. `ConfigurableApplicationContext.close()` kích hoạt quy trình shutdown:
- Phát event đóng context.
- Dừng các bean tham gia lifecycle.
- Dừng embedded web server.
- Gọi destruction callback của bean, ví dụ `@PreDestroy` hoặc `DisposableBean`.
- Giải phóng tài nguyên được context quản lý.

Spring Boot đăng ký shutdown hook theo cấu hình mặc định để đóng context khi JVM kết thúc bình thường. Trong môi trường triển khai, cần để tiến trình nhận tín hiệu dừng và có đủ thời gian shutdown.

Có thể bật graceful shutdown:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Graceful shutdown cho phép server ngừng nhận request mới và chờ request đang xử lý hoàn tất trong thời gian được cấu hình, trước khi lifecycle component bị dừng. Thời gian thực tế còn phụ thuộc server, request và cấu hình triển khai.

## 15. Những hiểu nhầm thường gặp

1. **Cho rằng `SpringApplication.run` chỉ tạo ApplicationContext.** Thực tế nó điều phối Environment, context, refresh, web server, runner và lifecycle event.
2. **Cho rằng context đã tồn tại nghĩa là mọi bean đã được tạo.** Bean definition có thể đã được nạp nhưng bean instance chỉ được tạo ở pha phù hợp; lazy và prototype có quy tắc riêng.
3. **Cho rằng ApplicationContext chính là Tomcat hoặc Netty.** Context quản lý server và các bean; server là thành phần runtime thuộc web context.
4. **Cho rằng `ContextRefreshedEvent` đồng nghĩa ứng dụng sẵn sàng nhận traffic.** Runner còn chạy sau event này; mốc hoàn tất startup thông thường là `ApplicationReadyEvent`.
5. **Đưa logic nghiệp vụ vào constructor hoặc initializer.** Các pha này có thể diễn ra trước khi toàn bộ dependency và hạ tầng sẵn sàng. Chọn runner hoặc event phù hợp với nhu cầu.
6. **Cho rằng auto-configuration luôn tạo bean mặc định.** Điều kiện classpath, property và bean hiện có có thể khiến cấu hình không áp dụng hoặc back-off.
7. **Ép WebApplicationType mà không kiểm tra dependency.** Loại ứng dụng cần tương thích với starter và runtime stack thực tế.
8. **Dùng runner cho tác vụ không có giới hạn thời gian.** Runner hoàn tất trước ApplicationReadyEvent, nên tác vụ treo có thể giữ ứng dụng ở trạng thái chưa sẵn sàng.
9. **Cho rằng server start thành công có nghĩa endpoint đúng.** Server có thể lắng nghe port nhưng controller mapping, security filter, database hoặc dependency ngoài vẫn lỗi.

## 16. Quy trình lần theo startup khi debug

Khi cần xác định ứng dụng dừng ở đâu trong quá trình khởi động, đi theo trình tự sau:

1. Xác nhận primary source và class có `@SpringBootApplication`.
2. Xác nhận dependency web và WebApplicationType thực tế.
3. Kiểm tra Environment, profile và property ảnh hưởng server.
4. Xác nhận context được tạo đúng loại.
5. Kiểm tra component scan, bean definition và condition evaluation report.
6. Tìm exception đầu tiên trong quá trình refresh; các lỗi sau có thể chỉ là hậu quả.
7. Kiểm tra việc tạo web server factory và bind port.
8. Xác nhận ApplicationStartedEvent, sau đó kiểm tra runner.
9. Xác nhận ApplicationReadyEvent và thực hiện HTTP request tới endpoint kiểm thử.
10. Kiểm tra shutdown hook và graceful shutdown khi cần xử lý vòng đời kết thúc.

Trong kiểm thử tích hợp, `@SpringBootTest` có thể khởi tạo ApplicationContext theo cấu hình kiểm thử. Thuộc tính `webEnvironment` cho phép chọn mock web, random port, defined port hoặc không tạo web environment. Kiểm thử với random port hữu ích để xác nhận server thực sự khởi động và endpoint nhận HTTP request; kiểm thử context mock phù hợp với trường hợp chỉ cần xác nhận cấu hình và bean.

## 17. Ghi nhớ

- `SpringApplication` điều phối startup; `ApplicationContext` là container quản lý bean và hạ tầng; embedded web server tiếp nhận HTTP.
- Environment được chuẩn bị trước khi context refresh, vì vậy profile và cấu hình ảnh hưởng Config Data phải được cung cấp đúng pha.
- `WebApplicationType` quyết định context Servlet, Reactive hay None.
- `refresh()` xử lý bean definition, auto-configuration, BeanFactoryPostProcessor, BeanPostProcessor và khởi tạo singleton.
- Web context tạo server trong quá trình refresh và khởi động server khi hoàn tất refresh.
- `ApplicationStartedEvent` được phát sau refresh và trước runner; `ApplicationReadyEvent` được phát sau khi runner hoàn tất.
- Runner phù hợp với tác vụ startup có giới hạn và có xử lý lỗi; event listener phù hợp khi cần phản ứng tại một mốc lifecycle cụ thể.
- Đóng ApplicationContext sẽ dừng lifecycle component, web server và gọi callback giải phóng tài nguyên.

Nắm được ranh giới giữa chuẩn bị Environment, tạo context, refresh, khởi động web server và hoàn tất runner giúp đọc log startup có hệ thống, đặt mã khởi tạo đúng thời điểm và xử lý lỗi mà không phụ thuộc vào phỏng đoán.
