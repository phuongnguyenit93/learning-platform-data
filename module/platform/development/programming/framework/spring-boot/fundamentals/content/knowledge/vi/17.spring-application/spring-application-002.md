# Chuẩn bị Environment trước khi tạo ApplicationContext

Spring Boot cần biết cấu hình nào đang có hiệu lực trước khi tạo và kết nối các bean. Ứng dụng cần xác định profile nào được bật, file cấu hình nào được nạp, property nào ghi đè property khác, ứng dụng chạy kiểu web nào và những giá trị nào phải có sẵn ngay từ đầu. Spring Boot tập hợp thông tin đó vào **Environment** rồi mới tạo ApplicationContext.

Việc chuẩn bị Environment trước khi tạo ApplicationContext giúp các quyết định khởi động được đưa ra đúng thời điểm. Ví dụ, Spring Boot cần biết ứng dụng là servlet web, reactive web hay non-web để chọn loại ApplicationContext phù hợp. Nó cũng cần đọc các cấu hình như `spring.config.import`, `spring.profiles.active` hoặc logging trước khi quá trình tạo bean bắt đầu.

Bài học này giải thích vai trò của Environment, thứ tự khởi động liên quan, cách property sources và profiles được nạp, cùng các extension point để thay đổi Environment sớm. Trọng tâm là phân biệt **thay đổi Environment trước khi tạo context** với **thay đổi cấu hình sau khi context đã tồn tại**, vì hai thời điểm này không có cùng tác dụng.

## 1. Environment là gì?

`Environment` là abstraction của Spring để truy cập cấu hình và profile đang hoạt động trong ứng dụng. Nó cung cấp hai nhóm thông tin quan trọng:

- **Property:** các giá trị cấu hình như URL, timeout, port, feature flag, tên database hoặc mức logging.
- **Profile:** các nhóm cấu hình hoặc bean phù hợp với một môi trường/chế độ chạy như `dev`, `test`, `staging` hoặc `prod`.

Một thành phần có thể đọc property thông qua:

~~~java
String region = environment.getProperty("app.region");
int timeout = environment.getProperty(
        "app.http.timeout",
        Integer.class,
        5
);
~~~

`Environment` không phải một file YAML, cũng không phải một object cấu hình duy nhất. Nó là giao diện hợp nhất nhiều nguồn cấu hình và cung cấp quy tắc phân giải giá trị.

### Environment và ConfigurableEnvironment

`Environment` chủ yếu cung cấp API đọc property và kiểm tra profile. Trong quá trình bootstrap, Spring thường làm việc với `ConfigurableEnvironment`, cho phép thay đổi các nguồn property và profile.

Một số thao tác thường gặp:

~~~java
ConfigurableEnvironment environment = ...;

environment.getProperty("app.region");
environment.getActiveProfiles();
environment.getDefaultProfiles();
environment.setActiveProfiles("dev");
environment.addActiveProfile("metrics");
~~~

`ConfigurableEnvironment` còn cho phép truy cập `MutablePropertySources` để thêm, thay thế hoặc sắp xếp nguồn cấu hình.

### Environment khác ApplicationContext thế nào?

| Thành phần | Trách nhiệm chính |
|---|---|
| `Environment` | Cung cấp property và profile |
| `PropertySource` | Đại diện cho một nguồn property cụ thể |
| `ApplicationContext` | Quản lý bean, dependency injection, lifecycle, event và resource |
| `BeanFactory` | Cơ chế lõi để tạo và cung cấp bean |
| `ConfigurableApplicationContext` | ApplicationContext có thể cấu hình trước/sau refresh |

Environment là một phần của ApplicationContext sau khi context được tạo, nhưng Spring Boot có thể chuẩn bị Environment **trước khi tạo context**. Điều đó cho phép các quyết định bootstrap sử dụng cấu hình sẵn có.

## 2. Vì sao phải chuẩn bị Environment trước ApplicationContext?

Hãy xét một ứng dụng có cấu hình:

~~~yaml
spring:
  main:
    web-application-type: servlet
  profiles:
    active: prod

server:
  port: 8082
~~~

Trước khi tạo bean, Spring Boot cần biết một số thông tin:

- Profile nào đang hoạt động để các cấu hình có `@Profile("prod")` được xem xét.
- Loại ứng dụng để chọn context phù hợp.
- Các property source nào cần được nạp.
- File cấu hình nào cần import.
- Những thiết lập bootstrap nào phải có trước khi refresh context.

Nếu context được tạo trước khi các thông tin này sẵn sàng, Spring có thể chọn sai loại context hoặc phân tích cấu hình theo môi trường không mong muốn.

Luồng khái quát:

~~~text
SpringApplication.run(args)
          |
          v
Tạo BootstrapContext và RunListeners
          |
          v
Chuẩn bị Environment
  - tạo/chọn Environment
  - thêm nguồn cấu hình ban đầu
  - đọc command-line arguments
  - xử lý Config Data và profiles
  - áp dụng EnvironmentPostProcessor
          |
          v
EnvironmentPrepared
          |
          v
Tạo ApplicationContext phù hợp
          |
          v
Chạy ApplicationContextInitializer
          |
          v
Nạp configuration sources
          |
          v
Refresh ApplicationContext
  - phân tích @Configuration
  - component scan và @Import
  - đăng ký bean definitions
  - tạo bean và inject dependency
          |
          v
ApplicationStarted / ApplicationReady
~~~

Đây là mô hình khái quát. Một số listener và EnvironmentPostProcessor được gọi thông qua event trong giai đoạn chuẩn bị Environment; Config Data có quy trình riêng và có thể kích hoạt việc đọc thêm cấu hình/profile. Nhưng điểm cốt lõi không đổi: **Spring Boot hoàn tất phần chuẩn bị Environment cần thiết trước khi tạo ApplicationContext**.

### Một ví dụ dễ thấy: chọn loại ApplicationContext

Spring Boot có thể chạy theo các loại ứng dụng:

- `SERVLET`: ứng dụng web dựa trên Servlet, thường dùng Spring MVC.
- `REACTIVE`: ứng dụng reactive web, thường dùng Spring WebFlux.
- `NONE`: ứng dụng không khởi tạo web server.

Có thể chỉ định qua property:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Hoặc bằng Java:

~~~java
SpringApplication application =
        new SpringApplication(StoreApplication.class);

application.setWebApplicationType(
        WebApplicationType.REACTIVE
);
~~~

Loại ứng dụng ảnh hưởng việc Spring Boot tạo loại ApplicationContext nào và những auto-configuration nào phù hợp. Đây là một quyết định bootstrap, vì vậy cần được xác định trước khi context được tạo.

## 3. SpringApplication chuẩn bị Environment như thế nào?

Trong một ứng dụng tiêu chuẩn:

~~~java
@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

`SpringApplication.run(...)` điều phối quá trình khởi động. Có thể tóm tắt các bước liên quan Environment như sau:

1. Tạo hoặc sử dụng Environment phù hợp với loại ứng dụng.
2. Cấu hình các property source ban đầu.
3. Đưa command-line arguments vào Environment nếu được bật.
4. Chuẩn bị profiles và những thuộc tính khởi động.
5. Phát sự kiện Environment prepared để các listener và EnvironmentPostProcessor tham gia.
6. Nạp Config Data như `application.properties`, `application.yml`, file theo profile và import.
7. Sau khi Environment được chuẩn bị, tạo ApplicationContext.
8. Đưa Environment vào context và tiếp tục xử lý cấu hình/bean.

Trong triển khai Spring Boot, một số bước trên được phối hợp qua `SpringApplicationRunListeners` và `EnvironmentPostProcessorApplicationListener`. Không cần gọi thủ công từng bước trong ứng dụng thông thường; `SpringApplication` thực hiện chúng theo lifecycle.

### Có thể quan sát các mốc startup

Một số application event tiêu biểu:

| Event | Thời điểm khái quát | Mục đích |
|---|---|---|
| `ApplicationStartingEvent` | Rất sớm, trước khi Environment được chuẩn bị đầy đủ | Báo ứng dụng bắt đầu khởi động |
| `ApplicationEnvironmentPreparedEvent` | Environment đang được chuẩn bị | Cho phép xử lý cấu hình sớm |
| `ApplicationContextInitializedEvent` | Context đã được tạo và initializers đã chạy | Báo context đã được khởi tạo |
| `ApplicationPreparedEvent` | Context đã nạp nguồn cấu hình, trước refresh | Báo context chuẩn bị refresh |
| `ApplicationStartedEvent` | Sau khi context refresh thành công | Ứng dụng đã bắt đầu |
| `ApplicationReadyEvent` | Sau các bước startup runner | Ứng dụng sẵn sàng nhận công việc |
| `ApplicationFailedEvent` | Khi startup thất bại | Báo lỗi trong quá trình khởi động |

Tên event và thứ tự này phản ánh lifecycle Spring Boot hiện đại; các chi tiết có thể khác giữa những thế hệ Boot cũ. Event được phát ở một mốc không có nghĩa mọi listener tùy chỉnh đều đã hoàn tất nếu thứ tự listener được cấu hình khác nhau.

## 4. PropertySource: Environment hợp nhất nhiều nguồn cấu hình

Một `PropertySource` đại diện cho một nguồn key-value. Ví dụ:

- Giá trị mặc định do ứng dụng khai báo.
- File `application.properties` hoặc `application.yml`.
- File cấu hình riêng cho profile.
- Biến môi trường của hệ điều hành.
- JVM system properties.
- Command-line arguments.
- Nguồn cấu hình tùy chỉnh do ứng dụng hoặc thư viện thêm.

Ví dụ một nguồn map trong Java:

~~~java
Map<String, Object> values = Map.of(
        "app.region", "ap-southeast",
        "app.feature.catalog", true
);

PropertySource<?> source =
        new MapPropertySource("runtimeDefaults", values);
~~~

Nguồn này có tên `runtimeDefaults` và cung cấp các property tương ứng. Sau khi thêm vào `MutablePropertySources`, Environment có thể đọc các giá trị đó.

### PropertySource có thứ tự ưu tiên

Khi nhiều nguồn chứa cùng một key, nguồn có ưu tiên cao hơn sẽ được dùng trước. Với `MutablePropertySources`, vị trí của nguồn trong danh sách có ý nghĩa:

~~~java
environment.getPropertySources().addFirst(source);
~~~

`addFirst` đưa nguồn lên đầu danh sách, nên nguồn đó có ưu tiên cao trong quá trình tìm property.

~~~java
environment.getPropertySources().addLast(source);
~~~

`addLast` đưa nguồn xuống cuối danh sách, phù hợp với giá trị mặc định có ưu tiên thấp.

Ví dụ, nếu nhiều nguồn đều có `app.region`:

~~~text
commandLineArgs: app.region=eu-west
systemEnvironment: APP_REGION=ap-southeast
application.yml: app.region=ap-southeast
runtimeDefaults: app.region=local
~~~

Giá trị cuối cùng phụ thuộc thứ tự property source thực tế của Environment. Không nên chỉ nhìn vào một file YAML để kết luận property hiệu lực.

### Thứ tự ưu tiên trong Spring Boot

Spring Boot có quy tắc property source precedence. Nhìn ở mức thực hành:

- Default properties thường có ưu tiên thấp.
- Config Data từ file cấu hình được nạp vào Environment.
- Biến môi trường và JVM system properties có thể ghi đè file cấu hình.
- Command-line arguments thường có ưu tiên cao hơn các nguồn cấu hình file thông thường.
- Test property sources có thể được ưu tiên cao trong ngữ cảnh kiểm thử.

Thứ tự chính xác còn có các nguồn đặc biệt như JSON application properties, JNDI, servlet init parameters, test annotations và Devtools. Khi cần chẩn đoán chính xác, hãy quan sát thứ tự `PropertySource` thực tế thay vì học thuộc một danh sách rút gọn.

### Giá trị mặc định không nên ghi đè cấu hình triển khai

Nếu một thư viện thêm default property, thường nên dùng `addLast` để người vận hành có thể ghi đè bằng file, biến môi trường hoặc command line.

Ví dụ:

~~~java
Map<String, Object> defaults = Map.of(
        "app.retry.max-attempts", 3,
        "app.retry.backoff", "500ms"
);

environment.getPropertySources().addLast(
        new MapPropertySource("retryDefaults", defaults)
);
~~~

Đây là cách cung cấp giá trị fallback. Nếu dùng `addFirst` cho default, có thể vô tình khiến cấu hình do người dùng triển khai không có hiệu lực.

## 5. Config Data: nạp application.properties và application.yml

Từ Spring Boot 2.4, cơ chế Config Data là cách chuẩn để nạp cấu hình từ file và import nguồn cấu hình. Những file phổ biến:

- `application.properties`
- `application.yml`
- `application-{profile}.properties`
- `application-{profile}.yml`

Ví dụ cấu trúc:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

File mặc định:

~~~yaml
app:
  name: store-service
  feature:
    catalog: true
~~~

File dev:

~~~yaml
app:
  endpoint:
    payment: http://localhost:8085
~~~

File prod:

~~~yaml
app:
  endpoint:
    payment: https://payments.example.internal
~~~

Khi profile `dev` hoạt động, Spring Boot nạp cấu hình phù hợp cho profile đó. Các property source được kết hợp theo precedence; file profile-specific có thể ghi đè giá trị chung theo quy tắc Config Data.

### Chỉ định file cấu hình

Một số property bootstrap quan trọng:

| Property | Mục đích |
|---|---|
| `spring.config.name` | Thay đổi tên cơ sở của file cấu hình được tìm |
| `spring.config.location` | Chỉ định location cấu hình; có thể thay thế các location mặc định |
| `spring.config.additional-location` | Bổ sung location bên cạnh các location mặc định |
| `spring.config.import` | Import thêm nguồn cấu hình |
| `spring.config.on-not-found` | Điều khiển cách xử lý một số location không tìm thấy theo cơ chế Config Data |

Ví dụ thêm một location:

~~~bash
java -jar store.jar --spring.config.additional-location=optional:file:./config/
~~~

`additional-location` giúp bổ sung thư mục cấu hình bên ngoài. Tiền tố `optional:` cho phép ứng dụng tiếp tục nếu location tùy chọn không tồn tại, tùy cú pháp và loại location.

Nếu dùng `spring.config.location`, cần nhớ rằng nó có thể thay thế danh sách location mặc định. Nếu mục tiêu chỉ là thêm cấu hình bên ngoài mà vẫn giữ các vị trí mặc định, `spring.config.additional-location` thường đúng ý hơn.

### Import file cấu hình

Ví dụ trong `application.yml`:

~~~yaml
spring:
  config:
    import: optional:file:./config/partner.yml
~~~

Spring Boot sẽ nhập nguồn cấu hình bổ sung theo cơ chế Config Data. Cấu hình import có thể là file, location hoặc loại nguồn được hỗ trợ như config tree.

### Config tree cho cấu hình được mount từ môi trường triển khai

Một số nền tảng triển khai mount secret/config dưới dạng file. Có thể dùng config tree:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Mỗi file trong thư mục có thể được ánh xạ thành một property. Đây là cách hữu ích khi môi trường triển khai cung cấp secret qua file. Cần bảo vệ quyền truy cập thư mục và tránh ghi secret vào log hoặc endpoint quản trị.

### Config Data được nạp sớm

Config Data là một phần quan trọng của việc chuẩn bị Environment. Những property như `spring.config.import` hoặc profile activation phải được xử lý đủ sớm để Spring biết cần nạp những nguồn cấu hình nào trước khi tạo ApplicationContext và phân tích bean.

## 6. Profiles: chọn cấu hình theo môi trường

Profile là nhãn để kích hoạt một nhóm cấu hình hoặc bean. Ví dụ:

~~~java
@Configuration
@Profile("dev")
public class DevelopmentConfiguration {
    // Bean chỉ dành cho môi trường dev.
}
~~~

~~~java
@Configuration
@Profile("prod")
public class ProductionConfiguration {
    // Bean chỉ dành cho môi trường production.
}
~~~

Spring đánh giá `@Profile` trong quá trình xử lý cấu hình dựa trên Environment đã được chuẩn bị.

### Kích hoạt profile bằng property

Trong `application.yml`:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Hoặc khi chạy:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

Có thể bật nhiều profile:

~~~bash
java -jar store.jar --spring.profiles.active=prod,metrics
~~~

Khi nhiều profile cùng active, cấu hình của chúng có thể cùng được áp dụng; nếu nhiều bean cùng kiểu được đăng ký, cần có quy tắc lựa chọn rõ ràng.

### Default profile

Nếu không có active profile nào, Spring sử dụng default profile (mặc định thường là `default`). Có thể thay đổi:

~~~yaml
spring:
  profiles:
    default: local
~~~

Default profile chỉ được dùng khi không có active profile phù hợp. Nếu đã bật profile cụ thể, default profile không nhất thiết được thêm vào danh sách active.

### Include thêm profile

Có thể đưa thêm profile vào danh sách:

~~~yaml
spring:
  profiles:
    include:
      - common
      - observability
~~~

`spring.profiles.include` cho phép thêm profile ngoài profile active ban đầu. Quy tắc xử lý include có liên quan đến Config Data và vị trí khai báo; không nên đặt property này tùy tiện trong một document chỉ được kích hoạt bởi profile khác.

### Profile group

Profile group giúp một profile đại diện cho một nhóm profile:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-security
        - observability
~~~

Khi kích hoạt `production`, các profile thành viên được đưa vào theo quy tắc group. Điều này giúp lệnh chạy ngắn hơn và tránh phải liệt kê nhiều profile mỗi lần triển khai.

### Profile activation trong Config Data

Có thể gắn một document cấu hình với profile:

~~~yaml
spring:
  config:
    activate:
      on-profile: dev

app:
  endpoint:
    payment: http://localhost:8085
~~~

Document này chỉ được áp dụng khi profile phù hợp. `spring.config.activate.on-profile` là cơ chế kích hoạt document; nó khác với việc khai báo `spring.profiles.active` để chọn profile.

Một số thuộc tính profile như `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` và `spring.profiles.group` có quy tắc vị trí riêng trong Config Data; không thể đặt tùy tiện trong document đã được profile kích hoạt. Khi cấu hình profile phức tạp, hãy tách document rõ ràng và kiểm tra quy tắc của phiên bản Spring Boot.

## 7. Command-line arguments và SpringApplication

Spring Boot tạo `ApplicationArguments` từ các tham số dòng lệnh. Với dạng option:

~~~bash
java -jar store.jar --app.region=ap-southeast --spring.profiles.active=prod
~~~

các giá trị option có thể được thêm vào Environment như command-line property source, nếu tính năng này được bật.

Có thể đọc arguments trong runner:

~~~java
@Component
public class StartupReporter implements ApplicationRunner {

    private final Environment environment;

    public StartupReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: "
                        + String.join(",", environment.getActiveProfiles())
        );
    }
}
~~~

`ApplicationRunner` chạy sau khi context đã refresh; đây là ví dụ quan sát Environment ở runtime, không phải extension point để thay đổi bootstrap property trước khi context được tạo.

### Tùy chỉnh SpringApplication bằng Java

Có thể tạo đối tượng `SpringApplication` rồi cấu hình trước khi gọi `run`:

~~~java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(StoreApplication.class);

    application.setDefaultProperties(Map.of(
            "app.region", "local",
            "app.retry.max-attempts", "3"
    ));

    application.setAdditionalProfiles("metrics");

    application.run(args);
}
~~~

`setDefaultProperties` thêm giá trị mặc định có ưu tiên thấp. `setAdditionalProfiles` bổ sung profile. Các giá trị từ file, environment hoặc command line vẫn có thể ghi đè default theo precedence.

Một số API khác:

~~~java
application.setAddCommandLineProperties(false);
application.setWebApplicationType(WebApplicationType.SERVLET);
application.addInitializers(new StoreContextInitializer());
application.addListeners(new StartupListener());
~~~

- `setAddCommandLineProperties(false)` tắt việc đưa option arguments thành property source.
- `setWebApplicationType(...)` chỉ định loại ứng dụng.
- `addInitializers(...)` đăng ký ApplicationContextInitializer.
- `addListeners(...)` đăng ký listener.

Chỉ tắt command-line properties nếu ứng dụng có lý do rõ ràng; nếu không, người vận hành sẽ mất một cơ chế cấu hình hữu ích.

### Dùng SpringApplicationBuilder

Với cấu hình fluent:

~~~java
new SpringApplicationBuilder(StoreApplication.class)
        .profiles("dev")
        .properties(
                "app.region=local",
                "app.feature.catalog=true"
        )
        .run(args);
~~~

`SpringApplicationBuilder` có thể hữu ích khi ứng dụng cần cấu hình nhiều context hoặc cấu hình khởi động bằng code. Với một ứng dụng đơn giản, `SpringApplication.run(...)` vẫn là lựa chọn gọn.

## 8. EnvironmentPostProcessor: thay đổi Environment trước khi tạo context

`EnvironmentPostProcessor` là extension point của Spring Boot để tùy chỉnh Environment trong giai đoạn bootstrap. Nó được gọi khi Environment đang được chuẩn bị, trước khi ApplicationContext được tạo.

Interface:

~~~java
public interface EnvironmentPostProcessor {
    void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    );
}
~~~

Một implementation có thể thêm property source, thay đổi active profile hoặc chuẩn bị giá trị cấu hình dựa trên thông tin có sẵn.

### Ví dụ thêm default property source

~~~java
package com.example.store.bootstrap;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class StoreEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        Map<String, Object> defaults = Map.of(
                "app.region", "local",
                "app.retry.max-attempts", 3
        );

        environment.getPropertySources().addLast(
                new MapPropertySource("storeBootstrapDefaults", defaults)
        );
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

Nguồn `storeBootstrapDefaults` được thêm cuối danh sách, nên đóng vai trò fallback. Nếu người vận hành cung cấp `app.region` trong application config, environment variable hoặc command line, nguồn có ưu tiên cao hơn có thể được dùng.

Nếu customizer cần ưu tiên cao hơn, có thể chọn vị trí khác, nhưng cần cân nhắc việc ghi đè cấu hình triển khai. Đừng dùng `addFirst` cho default một cách vô ý.

### Đăng ký EnvironmentPostProcessor

Trong các thế hệ Spring Boot hỗ trợ cơ chế này, đăng ký implementation qua file:

`META-INF/spring.factories`:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.store.bootstrap.StoreEnvironmentPostProcessor
~~~

Đây là cơ chế đăng ký extension point của Boot. Nó khác với việc đánh dấu class bằng `@Component`: EnvironmentPostProcessor cần được phát hiện trong giai đoạn bootstrap, trước khi component scan của ApplicationContext diễn ra.

### Khi nào nên dùng EnvironmentPostProcessor?

Phù hợp khi cần:

- Thêm property source trước khi context được tạo.
- Chuẩn bị property từ một nguồn bootstrap được hỗ trợ.
- Tính toán cấu hình sớm dựa trên environment có sẵn.
- Tích hợp cấu hình bên ngoài vào quá trình khởi động.
- Cung cấp default hoặc metadata cho các bước cấu hình sau.

Không nên dùng nó để tạo service nghiệp vụ, query database, gọi API bên ngoài hoặc thực hiện công việc cần bean dependency. EnvironmentPostProcessor chạy trước khi ApplicationContext sẵn sàng; nó không phải một Spring service bình thường.

### Thứ tự EnvironmentPostProcessor

Có thể implement `Ordered` hoặc dùng annotation ordering phù hợp để xác định thứ tự tương đối. Điều này quan trọng khi một processor cần đọc property do processor khác cung cấp, hoặc muốn chạy trước/sau Config Data.

Không nên chọn order bằng cách đoán. Hãy kiểm tra order của processor liên quan trong phiên bản Spring Boot đang sử dụng và xác nhận property source cuối cùng. Nếu processor cần đọc application config đã được nạp, nó phải được sắp xếp ở thời điểm phù hợp sau bước Config Data; nếu chạy trước, file config có thể chưa xuất hiện.

Một processor chỉ thêm fallback defaults thường có thể dùng nguồn có ưu tiên thấp và order phù hợp. Processor thực hiện tích hợp đặc biệt cần tài liệu hóa thứ tự mong muốn.

## 9. ApplicationContextInitializer: thay đổi context sau khi tạo nhưng trước refresh

`ApplicationContextInitializer<C>` là extension point khác:

~~~java
public interface ApplicationContextInitializer<C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
~~~

Initializer được gọi sau khi ApplicationContext đã được tạo, nhưng trước khi context refresh và trước khi các bean thông thường được khởi tạo.

Ví dụ:

~~~java
package com.example.store.bootstrap;

import java.util.Map;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public class StoreContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context
    ) {
        Map<String, Object> values = Map.of(
                "app.context-label", "store-web"
        );

        context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource("storeContextDefaults", values)
        );
    }
}
~~~

Đăng ký từ main:

~~~java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(StoreApplication.class);

    application.addInitializers(new StoreContextInitializer());
    application.run(args);
}
~~~

Initializer có thể truy cập context, Environment và một số metadata cấu hình. Nó phù hợp khi cần chuẩn bị context trước refresh, chẳng hạn thêm property source, đăng ký một số cấu hình hoặc tùy chỉnh context.

### EnvironmentPostProcessor khác ApplicationContextInitializer thế nào?

| Tiêu chí | EnvironmentPostProcessor | ApplicationContextInitializer |
|---|---|---|
| Thời điểm | Trong giai đoạn chuẩn bị Environment, trước ApplicationContext | Sau khi context được tạo, trước refresh |
| Có ApplicationContext chưa? | Chưa | Có |
| Nhận đối tượng | Environment và SpringApplication | ConfigurableApplicationContext |
| Phù hợp với | Bootstrap property, Config Data integration, profile sớm | Tùy chỉnh context/Environment trước khi nạp bean |
| Đăng ký thường gặp | `spring.factories` với key EnvironmentPostProcessor | `SpringApplication.addInitializers` hoặc cơ chế đăng ký initializer |
| Có thể dùng bean nghiệp vụ đã khởi tạo không? | Không | Chưa có các bean thông thường đã khởi tạo |

Nếu một giá trị phải ảnh hưởng tới việc chọn loại ApplicationContext hoặc nạp Config Data, EnvironmentPostProcessor thường là thời điểm phù hợp hơn. Nếu cần thao tác với context đã tạo nhưng chưa refresh, dùng initializer.

### Initializer không phải nơi thay đổi mọi bootstrap property

Đến lúc initializer chạy, Spring Boot đã chuẩn bị Environment và đã chọn/tạo ApplicationContext. Thay đổi property trong initializer có thể ảnh hưởng các bean và configuration được xử lý khi refresh, nhưng không thể quay ngược thời gian để thay đổi những quyết định đã hoàn tất như loại context hoặc các bước Config Data đã chạy.

## 10. ApplicationListener và ApplicationEnvironmentPreparedEvent

Có thể lắng nghe event của Spring Boot. Ví dụ:

~~~java
public class EnvironmentPreparedListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event
    ) {
        ConfigurableEnvironment environment = event.getEnvironment();

        String region = environment.getProperty("app.region");
        // Quan sát giá trị trong giai đoạn Environment prepared.
    }
}
~~~

Listener có thể được thêm vào SpringApplication:

~~~java
SpringApplication application =
        new SpringApplication(StoreApplication.class);

application.addListeners(new EnvironmentPreparedListener());
application.run(args);
~~~

Tuy nhiên, listener quan sát event và EnvironmentPostProcessor có vai trò khác nhau. Nếu mục tiêu là bổ sung property source bằng một extension point chuyên biệt, EnvironmentPostProcessor thường thể hiện ý định rõ hơn.

### Cẩn thận với thứ tự listener

Nhiều listener có thể phản ứng với cùng một event. Thứ tự của chúng ảnh hưởng việc một listener nhìn thấy property source do listener khác thêm hay chưa. Nếu phải thay đổi Environment, hãy dùng extension point và ordering được thiết kế cho bootstrap thay vì dựa vào thứ tự ngầm của listener.

Không nên tạo bean hoặc lấy bean từ ApplicationContext trong `ApplicationEnvironmentPreparedEvent` vì context lúc này chưa được tạo. Listener có thể quan sát Environment và thực hiện công việc bootstrap phù hợp, nhưng không nên giả định dependency injection của context đã sẵn sàng.

## 11. @PropertySource: vì sao có thể quá muộn cho cấu hình bootstrap?

Một cấu hình Spring có thể thêm property source bằng:

~~~java
@Configuration
@PropertySource("classpath:custom.properties")
public class CustomPropertiesConfiguration {
}
~~~

Cơ chế này được xử lý khi Spring phân tích configuration class, tức là sau khi ApplicationContext đã được tạo và quá trình refresh bắt đầu.

Vì vậy, `@PropertySource` có thể cung cấp property cho các bean/configuration được xử lý sau đó, nhưng **không phù hợp để cấu hình một số thuộc tính cần biết trước khi context được tạo hoặc trước khi Config Data được nạp**.

Ví dụ các nhóm property bootstrap:

- `spring.config.name`
- `spring.config.location`
- `spring.config.additional-location`
- `spring.config.import`
- Một số thuộc tính `spring.main.*`
- Cấu hình logging sớm

Nếu muốn chọn file cấu hình, import config tree hoặc xác định profile từ sớm, hãy dùng nguồn cấu hình bootstrap được Spring Boot hỗ trợ như command line, environment variables, system properties, Config Data hoặc EnvironmentPostProcessor.

### Khi nào @PropertySource vẫn phù hợp?

Nó có thể phù hợp khi ứng dụng có một file properties bổ sung và các giá trị chỉ cần được sử dụng trong giai đoạn tạo bean/configuration sau khi context bắt đầu refresh.

Ví dụ:

~~~properties
app.invoice.prefix=INV
app.invoice.max-lines=100
~~~

~~~java
@Configuration
@PropertySource("classpath:invoice.properties")
public class InvoiceConfiguration {

    @Bean
    public InvoiceFormatter invoiceFormatter(
            Environment environment
    ) {
        String prefix = environment.getProperty(
                "app.invoice.prefix",
                "DOC"
        );

        return new InvoiceFormatter(prefix);
    }
}
~~~

Nếu các property này không cần quyết định bootstrap, `@PropertySource` có thể là lựa chọn hợp lệ. Nếu dự án đã dùng Config Data, thường có thể đặt chúng trong `application.yml` hoặc import file cấu hình để thống nhất cơ chế nạp.

## 12. Những property cần có sớm và property có thể đọc muộn

Không phải mọi property đều cần được biết trước khi tạo ApplicationContext.

| Nhóm cấu hình | Ví dụ | Thời điểm cần |
|---|---|---|
| Chọn loại ứng dụng | `spring.main.web-application-type` | Trước khi tạo context |
| Chọn file/config location | `spring.config.name`, `spring.config.location` | Trong bootstrap Config Data |
| Kích hoạt profile | `spring.profiles.active` | Trước khi xử lý các cấu hình có `@Profile` |
| Logging bootstrap | `logging.config`, một số `logging.*` | Rất sớm trong startup |
| Cấu hình bean | `app.payment.timeout` | Trước khi bean tương ứng được bind/tạo |
| Port server | `server.port` | Khi cấu hình embedded server, sau khi Environment có giá trị |
| Business feature flag | `app.feature.catalog-enabled` | Trước khi conditional bean hoặc logic tương ứng cần đọc |
| Dữ liệu request | `customerId`, `orderId` | Runtime qua tham số, không phải bootstrap Environment |

Một nguyên tắc: property ảnh hưởng đến **việc chọn nguồn cấu hình hoặc loại context** phải được cung cấp từ nguồn sớm. Property chỉ được sử dụng khi tạo một bean có thể được đọc trong giai đoạn sau, miễn là nó có mặt trước thời điểm bean đó được khởi tạo/bind.

### ConfigurationProperties và Environment

Một class cấu hình typed:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {
    private Duration timeout = Duration.ofSeconds(3);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Có thể đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Spring bind các property từ Environment vào object khi cấu hình bean tương ứng được xử lý.

Ví dụ YAML:

~~~yaml
app:
  payment:
    timeout: 5s
~~~

Typed properties phù hợp với cấu hình có nhiều field, validation và metadata. Nó không thay thế Environment; nó là cách bind một nhóm property từ Environment vào object có kiểu.

## 13. Custom Environment và thay đổi property source bằng code

Trong một số ứng dụng đặc biệt, có thể tạo Environment riêng và đưa vào SpringApplication:

~~~java
ConfigurableEnvironment environment =
        new StandardEnvironment();

Map<String, Object> values = Map.of(
        "app.region", "local"
);

environment.getPropertySources().addFirst(
        new MapPropertySource("bootstrapOverrides", values)
);

SpringApplication application =
        new SpringApplication(StoreApplication.class);

application.setEnvironment(environment);
application.run(args);
~~~

Cách này cho phép kiểm soát Environment trước khi khởi động. Tuy nhiên, phải chọn Environment tương thích với loại ứng dụng và hiểu cách Spring Boot tiếp tục cấu hình, chuyển đổi hoặc bổ sung property source. Tự thay Environment có thể làm mất một số hành vi mặc định nếu chọn sai loại.

Với ứng dụng web, Spring có các Environment chuyên biệt cho servlet/reactive context. Trong hầu hết trường hợp, nên để Spring Boot tạo Environment phù hợp rồi bổ sung property bằng default properties hoặc EnvironmentPostProcessor.

### Thêm property source ở đâu?

Một số lựa chọn:

~~~java
environment.getPropertySources().addFirst(source);
environment.getPropertySources().addLast(source);
environment.getPropertySources().addBefore("systemEnvironment", source);
environment.getPropertySources().addAfter("systemEnvironment", source);
~~~

`addBefore` và `addAfter` yêu cầu tên property source mốc tồn tại. Nếu tên không có, thao tác có thể thất bại. Hãy kiểm tra danh sách hiện tại trước khi sắp xếp tương đối.

### Đừng thay đổi Environment sau khi các bean đã bind mà mong chúng tự cập nhật

Một số bean đọc property trong constructor hoặc được bind vào `@ConfigurationProperties` khi context khởi tạo. Nếu thay đổi property source sau đó, các object đã tạo không tự động được bind lại.

Environment có thể phản ánh giá trị mới khi truy vấn trực tiếp, nhưng bean đang giữ một giá trị đã được copy vào field có thể vẫn giữ giá trị cũ. Nếu cần refresh cấu hình runtime, phải dùng cơ chế refresh/rebind được thiết kế rõ ràng, không chỉ thêm property source rồi giả định mọi bean cập nhật.

## 14. Thứ tự property source và ví dụ ghi đè thực tế

Giả sử ứng dụng có:

`application.yml`:

~~~yaml
app:
  payment:
    timeout: 3s
    endpoint: https://sandbox-payments.example
~~~

Biến môi trường:

~~~bash
APP_PAYMENT_TIMEOUT=8s
~~~

Command line:

~~~bash
java -jar store.jar --app.payment.endpoint=https://payments.example
~~~

Giá trị hiệu lực có thể là:

- Timeout: 8 giây từ biến môi trường, nếu nguồn này có ưu tiên cao hơn file config.
- Endpoint: URL từ command line, thường ưu tiên cao hơn file config.
- Những property khác không bị ghi đè vẫn lấy từ YAML.

Đây là lý do một file cấu hình không luôn thể hiện đầy đủ cấu hình runtime. Trong production, property có thể đến từ environment, secret store, command line hoặc config server.

### Đặt default trong code có thể bị ghi đè

Nếu EnvironmentPostProcessor thêm:

~~~java
environment.getPropertySources().addLast(
        new MapPropertySource(
                "appDefaults",
                Map.of("app.payment.timeout", "2s")
        )
);
~~~

thì giá trị `2s` là fallback. File cấu hình hoặc biến môi trường có ưu tiên cao hơn có thể ghi đè. Cách này phù hợp khi thư viện muốn cung cấp default mà vẫn tôn trọng cấu hình triển khai.

### Không ghi secret thành default hoặc log

Không đưa API key, password hoặc token vào default property source trong code. Secret nên được cấp từ secret manager, environment hoặc config tree có kiểm soát. Khi log Environment, không in toàn bộ property values vì có thể lộ thông tin xác thực.

## 15. Phân biệt các extension point bootstrap

Những extension point sau thường bị nhầm:

| Extension point | Thời điểm | Việc nên làm |
|---|---|---|
| `EnvironmentPostProcessor` | Khi chuẩn bị Environment, trước ApplicationContext | Thêm/sắp xếp property source, xử lý bootstrap config |
| `ApplicationEnvironmentPreparedEvent` listener | Khi Environment prepared event được phát | Quan sát hoặc xử lý event bootstrap |
| `ApplicationContextInitializer` | Sau khi context được tạo, trước refresh | Tùy chỉnh context/Environment trước khi nạp bean |
| `BeanFactoryPostProcessor` | Sau khi bean definitions được đăng ký, trước khởi tạo bean thông thường | Chỉnh metadata bean definitions |
| `BeanDefinitionRegistryPostProcessor` | Trong giai đoạn xử lý registry | Đăng ký/chỉnh bean definitions |
| `BeanPostProcessor` | Trong quá trình tạo từng bean | Chỉnh instance/proxy trước hoặc sau initialization |
| `ApplicationRunner` / `CommandLineRunner` | Sau khi context refresh | Thực hiện công việc sau startup |

Nếu mục tiêu là thay đổi property dùng để nạp file cấu hình, dùng EnvironmentPostProcessor hoặc nguồn bootstrap. Nếu muốn thay đổi bean definition, dùng registry post-processor hoặc registrar phù hợp. Nếu muốn xử lý bean instance, dùng BeanPostProcessor. Nếu muốn chạy công việc sau khi ứng dụng đã sẵn sàng, dùng runner.

Đặt logic vào sai extension point có thể khiến property xuất hiện quá muộn hoặc bean chưa tồn tại.

## 16. Lỗi thường gặp khi chuẩn bị Environment

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Profile không được kích hoạt | Giá trị active profile bị ghi đè hoặc khai báo sai nguồn | Kiểm tra `spring.profiles.active`, command line, environment variables |
| File cấu hình ngoài không được nạp | Dùng sai `spring.config.location` hoặc import syntax | Kiểm tra Config Data location và log startup |
| `@Profile` không match | Profile chưa active ở thời điểm configuration parsing | Kiểm tra Environment trước refresh |
| Property trong `@PropertySource` không ảnh hưởng logging | Property được nạp quá muộn | Chuyển sang Config Data hoặc nguồn bootstrap |
| Custom Environment làm mất cấu hình web | Dùng loại Environment không phù hợp hoặc thay thế hành vi Boot | Để Boot tạo Environment, bổ sung property source |
| EnvironmentPostProcessor không chạy | Chưa đăng ký đúng `spring.factories` hoặc class không có trên classpath | Kiểm tra file metadata và runtime artifact |
| EnvironmentPostProcessor không thấy property file | Processor chạy trước Config Data processor | Kiểm tra order của processor |
| Custom property bị ghi đè | Property source nằm ở vị trí ưu tiên thấp | Quan sát thứ tự `PropertySources` |
| Bean vẫn giữ giá trị cũ sau khi Environment đổi | Bean đã bind/copy property khi khởi tạo | Dùng cơ chế refresh/rebind có chủ đích |
| Ứng dụng chọn sai ApplicationContext | Web application type được xác định trước khi property tùy chỉnh được nạp | Cung cấp property từ nguồn bootstrap sớm |

### Kiểm tra active profiles

Có thể quan sát:

~~~java
log.info("Active profiles: {}",
        Arrays.toString(environment.getActiveProfiles()));
~~~

Chỉ log tên profile, tránh log toàn bộ cấu hình nếu có secret.

### Kiểm tra property source names

Có thể duyệt các nguồn:

~~~java
for (PropertySource<?> source :
        environment.getPropertySources()) {
    log.info("Property source: {}", source.getName());
}
~~~

Tên source giúp hiểu property đến từ đâu. Không nên in toàn bộ map vì có thể chứa thông tin nhạy cảm.

### Dùng Actuator một cách có kiểm soát

Nếu đã tích hợp Spring Boot Actuator, endpoint `env` có thể hỗ trợ quan sát property sources và giá trị đã được lọc. Endpoint này có thể tiết lộ cấu hình nhạy cảm, nên chỉ expose qua mạng quản trị được bảo vệ, giới hạn quyền truy cập và giữ cơ chế sanitization phù hợp.

## 17. Kiểm thử Environment và bootstrap configuration

Không phải mọi test đều cần khởi động toàn bộ ứng dụng. Có thể kiểm tra property hoặc profile theo nhiều mức.

### Test với property của Spring Boot

~~~java
@SpringBootTest(properties = {
        "app.region=test",
        "app.feature.catalog=false"
})
class StoreConfigurationTest {
    // Test bean/configuration sử dụng các property trên.
}
~~~

Các property test được thêm vào Environment của test context với precedence phù hợp cho kiểm thử.

### Test profile

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentConfigurationTest {
    // Kiểm tra bean thuộc profile test.
}
~~~

`@ActiveProfiles` chọn profile cho test context. Nó giúp kiểm tra cấu hình theo môi trường mà không cần thay file cấu hình chính.

### Test property source

~~~java
@SpringBootTest
@TestPropertySource(properties = {
        "app.payment.timeout=2s"
})
class PaymentPropertiesTest {
    // ...
}
~~~

`@TestPropertySource` bổ sung property cho test. Với Spring Boot hiện đại, có thể cân nhắc `@DynamicPropertySource` khi giá trị đến từ tài nguyên test động như container database.

### Test EnvironmentPostProcessor

EnvironmentPostProcessor là bootstrap extension point, vì vậy test nên xác nhận cả việc processor được đăng ký và property source xuất hiện đúng thời điểm. Có thể tạo một `SpringApplication` nhỏ hoặc kiểm tra qua context integration test dùng đúng metadata đăng ký.

Nếu chỉ gọi trực tiếp `postProcessEnvironment` trong unit test, ta kiểm tra logic processor nhưng chưa kiểm tra đăng ký bằng `spring.factories` hay thứ tự chạy cùng Config Data.

### Test cấu hình theo nhiều nguồn

Một test hữu ích có thể đặt cùng một key ở default properties, file config và command line, sau đó xác nhận giá trị có precedence mong muốn. Điều này tránh lỗi triển khai do giả định sai nguồn nào thắng.

## 18. Một ví dụ end-to-end: chọn profile và property trước context

Giả sử ứng dụng thanh toán có hai cấu hình:

~~~java
@Configuration
@Profile("dev")
public class DevPaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new DemoPaymentGateway();
    }
}
~~~

~~~java
@Configuration
@Profile("prod")
public class ProdPaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway(
            PaymentProperties properties
    ) {
        return new LivePaymentGateway(properties.getEndpoint());
    }
}
~~~

`PaymentProperties`:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {
    private String endpoint;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

File `application.yml`:

~~~yaml
spring:
  profiles:
    active: dev

app:
  payment:
    endpoint: https://sandbox-payments.example
~~~

Khi chạy production, người vận hành có thể cung cấp:

~~~bash
java -jar store.jar --spring.profiles.active=prod --app.payment.endpoint=https://payments.example
~~~

Trình tự:

1. Spring Boot chuẩn bị Environment.
2. Command-line property source được thêm theo cấu hình.
3. Profile active được xác định là `prod`.
4. Config Data nạp các file chung và profile-specific phù hợp.
5. ApplicationContext được tạo.
6. Spring phân tích cấu hình, `@Profile("prod")` match và cấu hình dev không được áp dụng.
7. `PaymentProperties` được bind từ Environment.
8. `PaymentGateway` production được tạo và inject vào service.

Service không cần tự đọc profile hay tìm bean. Environment quyết định cấu hình nào được đăng ký; container kết nối dependency sau đó.

## 19. Các nguyên tắc thiết kế bootstrap dễ dự đoán

1. **Cung cấp property bootstrap từ nguồn sớm.** Dùng command line, environment variables, system properties, Config Data hoặc EnvironmentPostProcessor cho cấu hình cần trước context.
2. **Để Spring Boot tạo Environment phù hợp trong ứng dụng thông thường.** Bổ sung property source thay vì thay toàn bộ Environment nếu không có nhu cầu đặc biệt.
3. **Hiểu precedence của PropertySource.** Default nên có ưu tiên thấp; cấu hình triển khai phải có khả năng ghi đè.
4. **Chọn profile trước khi refresh context.** `@Profile` được đánh giá khi Spring xử lý configuration/bean definitions.
5. **Dùng Config Data cho file cấu hình ứng dụng.** `spring.config.import`, additional-location và config tree giúp nạp nguồn ngoài theo cơ chế chuẩn.
6. **Dùng EnvironmentPostProcessor cho bootstrap logic.** Không dùng nó làm service nghiệp vụ hoặc nơi gọi database/API.
7. **Dùng ApplicationContextInitializer cho context đã tạo nhưng chưa refresh.** Đừng kỳ vọng initializer thay đổi các quyết định bootstrap đã hoàn tất.
8. **Không dùng @PropertySource cho thuộc tính cần sớm.** Nó được xử lý trong quá trình configuration class parsing.
9. **Không kỳ vọng bean đã bind tự cập nhật khi Environment đổi.** Runtime refresh cần cơ chế riêng.
10. **Không log secret từ Environment.** Quan sát tên property source và profile là đủ cho nhiều tình huống.
11. **Kiểm thử cả precedence lẫn profile.** Một file YAML riêng lẻ không đại diện toàn bộ Environment runtime.
12. **Chọn extension point theo giai đoạn cần can thiệp.** Environment, context, bean definition và bean instance là những mốc khác nhau.

## Kết luận

Spring Boot chuẩn bị Environment trước khi tạo ApplicationContext để có thể xác định property sources, profiles, Config Data và những quyết định bootstrap cần thiết. Environment hợp nhất nhiều nguồn cấu hình theo thứ tự ưu tiên; profile quyết định những cấu hình nào phù hợp; Config Data nạp file và nguồn import trước khi Spring bắt đầu tạo object graph.

`EnvironmentPostProcessor` can thiệp trong giai đoạn chuẩn bị Environment, còn `ApplicationContextInitializer` chạy sau khi context được tạo nhưng trước refresh. `@PropertySource` được xử lý muộn hơn trong quá trình phân tích configuration class, nên không phù hợp với một số thuộc tính cần biết từ sớm như cấu hình Config Data hoặc logging bootstrap.

Khi property hay profile có kết quả khác dự đoán, hãy kiểm tra nguồn cấu hình thực tế, thứ tự PropertySource, thời điểm processor chạy và giai đoạn mà bean/configuration sử dụng giá trị đó. Hiểu đúng ranh giới giữa Environment và ApplicationContext giúp startup Spring Boot có thể dự đoán, cấu hình theo môi trường rõ ràng và tránh những lỗi chỉ xuất hiện khi triển khai.
