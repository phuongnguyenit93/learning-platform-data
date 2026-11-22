# Phân biệt `EnvironmentPostProcessor` với `ApplicationContextInitializer` trong Spring Boot

## 1. Vấn đề và mục tiêu

Spring Boot cho phép lấy cấu hình từ nhiều nguồn thay vì hard-code giá trị trong Java: `application.yml`, `application.properties`, biến môi trường hệ điều hành, JVM system properties, command-line arguments, config tree và những nguồn do ứng dụng hoặc thư viện bổ sung.

Đôi khi những nguồn chuẩn chưa đủ. Ví dụ, một ứng dụng cần:

- Bổ sung giá trị mặc định cho `app.region` khi deployment chưa khai báo.
- Nạp một nhóm property từ một cơ chế được kiểm soát trước khi Spring tạo bean.
- Thay đổi **một đặc tính của chính application context** trước khi nó bắt đầu refresh.
- Gắn một listener hoặc một `BeanFactoryPostProcessor` vào context trong giai đoạn khởi tạo.
- Xác định một extension point phù hợp để xử lý cấu hình thật sớm, nhưng không trộn logic infrastructure vào `@PostConstruct` hoặc service nghiệp vụ.

Hai cơ chế thường được nhắc đến là:

1. **`EnvironmentPostProcessor`** — extension point của **Spring Boot**, dành cho `Environment`.
2. **`ApplicationContextInitializer`** — extension point của **Spring Framework**, dành cho `ConfigurableApplicationContext`.

Tên gọi có vẻ tương tự vì cả hai đều chạy trước khi ứng dụng sẵn sàng, nhưng **đích thao tác, lifecycle, cơ chế đăng ký và phạm vi ảnh hưởng khác nhau**.

> Kết luận ngắn: dùng `EnvironmentPostProcessor` khi mục tiêu chính là **chuẩn bị/điều chỉnh Environment ở giai đoạn sớm**; dùng `ApplicationContextInitializer` khi cần **khởi tạo hoặc tùy biến ApplicationContext đã được tạo nhưng chưa refresh**.

Các ví dụ Java chính trong bài nhắm tới **Spring Boot 3.3–3.5, Java 17+**. Ở Spring Boot 4.x, một số package/API liên quan đã dịch chuyển; phần cuối nêu cách kiểm tra phiên bản để tránh sao chép sai import.

## 2. Hiểu hai đối tượng: `Environment` và `ApplicationContext`

### 2.1. `Environment` quản lý giá trị cấu hình hiệu lực

`org.springframework.core.env.Environment` cung cấp cách truy cập cấu hình:

~~~java
String region = environment.getProperty("app.region");
boolean enabled = environment.getProperty(
        "app.audit.enabled", Boolean.class, false);
~~~

`ConfigurableEnvironment` cho phép thao tác các `PropertySource` và profiles:

~~~java
MutablePropertySources sources = environment.getPropertySources();
sources.addLast(new MapPropertySource("fallbacks", values));
~~~

`Environment` không đồng nghĩa với một file YAML duy nhất. Nó tập hợp nhiều nguồn theo **thứ tự ưu tiên**. Thông thường, property cùng tên trong nguồn ưu tiên cao hơn có thể ghi đè giá trị ở nguồn thấp hơn.

### 2.2. `ApplicationContext` là container quản lý bean

`org.springframework.context.ApplicationContext` là ngữ cảnh chạy của Spring, giữ bean definitions, dependency injection, event publishing và nhiều infrastructure khác.

`ConfigurableApplicationContext` cho phép tùy biến lifecycle trước khi refresh:

~~~java
context.setId("catalog-local");
context.addApplicationListener(listener);
context.addBeanFactoryPostProcessor(postProcessor);
~~~

Context có `Environment` riêng:

~~~java
ConfigurableEnvironment env = context.getEnvironment();
~~~

Vì vậy, **`ApplicationContextInitializer` cũng có thể truy cập và sửa `Environment`**. Tuy nhiên, thời điểm nó được gọi đã khác so với `EnvironmentPostProcessor`, nên không thể mặc định rằng hai cơ chế tương đương trong mọi tình huống.

## 3. Timeline khởi động Spring Boot

Một sơ đồ rút gọn cho ứng dụng thông thường:

~~~text
main(String[] args)
       |
       v
SpringApplication.run(args)
       |
       v
Chuẩn bị Environment
       |
       +--> xử lý các EnvironmentPostProcessor
       |    (gồm xử lý Config Data theo thứ tự phù hợp)
       |
       +--> Environment sẵn sàng cho bước tạo context
       |
       v
Tạo ConfigurableApplicationContext
       |
       v
Gắn Environment vào context, chuẩn bị context
       |
       +--> ApplicationContextInitializer.initialize(context)
       |    (context đã tồn tại, chưa refresh)
       |
       v
Nạp bean definitions
       |
       v
Refresh ApplicationContext
       |
       +--> BeanFactoryPostProcessor
       +--> tạo/khởi tạo singleton beans
       +--> Dependency injection, @ConfigurationProperties
       +--> lifecycle và infrastructure theo loại context
       |
       v
ApplicationStartedEvent, runners, ApplicationReadyEvent...
~~~

Sơ đồ là **mô hình khái niệm**, không liệt kê mọi callback nội bộ. Spring Boot có nhiều application events và listeners; việc các post-processor được kích hoạt và nạp Config Data có thứ tự riêng. Nhưng thứ tự tương đối quan trọng là:

- **Environment có trước ApplicationContext.**
- **EnvironmentPostProcessor** làm việc trong quá trình chuẩn bị Environment.
- **ApplicationContextInitializer** nhận một context đã được tạo và chạy trước bước refresh.
- `@Bean`, `@Component` và các service nghiệp vụ thông thường chưa phải thứ có thể lấy tùy ý ở hai giai đoạn trên.

Theo chuỗi application events của Spring Boot, `ApplicationEnvironmentPreparedEvent` xuất hiện khi Environment đã được biết nhưng context chưa được tạo; `ApplicationContextInitializedEvent` xuất hiện sau khi initializers chạy và trước khi nạp các bean definitions. Điều này giúp xác định giai đoạn phù hợp để đặt logic khởi động.

## 4. Bảng đối chiếu tổng quan

| Tiêu chí | `EnvironmentPostProcessor` | `ApplicationContextInitializer` |
| --- | --- | --- |
| Thuộc framework nào | Spring Boot | Spring Framework |
| Đối tượng đầu vào | `ConfigurableEnvironment` và `SpringApplication` | `ConfigurableApplicationContext` |
| Method chính | `postProcessEnvironment(...)` | `initialize(...)` |
| Khi chạy | Trong giai đoạn chuẩn bị Environment | Sau khi context đã được tạo, trước khi refresh |
| Có ApplicationContext để thao tác? | Không có đối số context | Có |
| Có thể thêm `PropertySource`? | Có, là mục đích chủ yếu | Có, thông qua `context.getEnvironment()` |
| Có thể thêm listener vào context? | Không trực tiếp qua context | Có |
| Có thể thiết lập ID context? | Không trực tiếp | Có |
| Được tìm qua component scan như `@Component`? | Không nên dựa vào component scan | Không nên dựa vào component scan |
| Đăng ký tự động trong Boot 3.x | `META-INF/spring.factories` với key `org.springframework.boot.env.EnvironmentPostProcessor` | `META-INF/spring.factories` với key `org.springframework.context.ApplicationContextInitializer` |
| Đăng ký tường minh bằng Java | Thường qua SPI; có thể thêm cơ chế lắng nghe/lifecycle tùy biến | `SpringApplication.addInitializers(...)` |
| Có điều khiển được Config Data đã nạp? | Phụ thuộc thứ tự với Config Data processor | Thông thường **quá muộn** để yêu cầu Config Data nạp lại |
| Nên phụ thuộc vào bean nghiệp vụ? | Không | Không, vì context chưa refresh |
| Mục tiêu điển hình | Nguồn config tùy biến, giá trị fallback, chuẩn bị Environment | Context ID, listeners, BeanFactoryPostProcessors và context-level setup |

Không có cơ chế nào mặc định “mạnh hơn” trong mọi trường hợp. **Chọn theo thời điểm cần giá trị và thứ bạn muốn thay đổi.**

## 5. API `EnvironmentPostProcessor` trong Spring Boot 3.x

Import thường dùng trong Spring Boot 3.3–3.5:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
~~~

Giao diện:

~~~java
public interface EnvironmentPostProcessor {
    void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application);
}
~~~

Callback nhận:

- `environment`: cho phép thêm, loại bỏ hoặc thay đổi cách tổ chức các `PropertySource` trong giới hạn API.
- `application`: instance `SpringApplication` đang khởi động.

Ví dụ tối thiểu:

~~~java
package com.example.boot;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class DemoEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> properties =
                Map.of("app.region", "vn");

        environment.getPropertySources().addLast(
                new MapPropertySource("demoFallback", properties));
    }
}
~~~

Đây là một ví dụ về **fallback property source**, không phải cập nhật cấu hình đã khai báo ở nguồn cao hơn.

`MapPropertySource` dùng map làm dữ liệu nguồn. `addLast(...)` đặt nguồn mới ở cuối chuỗi priority: nó được dùng khi không có nguồn nằm trước cung cấp cùng tên property.

### 5.1. Vì sao `addLast`?

Nếu một deployment đặt:

~~~bash
APP_REGION=apac java -jar app.jar
~~~

thì `app.region` có thể được lấy từ OS environment, thay vì `vn` trong fallback. Đây thường là hành vi mong muốn: mã cung cấp giá trị dự phòng nhưng người vận hành vẫn có thể override.

Nếu cố ý dùng:

~~~java
environment.getPropertySources().addFirst(
        new MapPropertySource("forcedRegion", properties));
~~~

thì source mới được ưu tiên rất cao và có thể ghi đè giá trị do CLI, OS environment hoặc file cung cấp. Điều này có thể gây bất ngờ và làm môi trường triển khai mất quyền kiểm soát.

**Hãy xác định mức ưu tiên của source theo hợp đồng cấu hình.** Không mặc định `addFirst` là lựa chọn tốt chỉ vì muốn chắc chắn property “có hiệu lực”.

## 6. Ví dụ đầy đủ: EnvironmentPostProcessor thêm fallback

### 6.1. Class triển khai

~~~java
package com.example.boot;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class RegionDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    private static final String SOURCE_NAME = "exampleRegionDefaults";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        if (environment.getPropertySources().contains(SOURCE_NAME)) {
            return;
        }

        Map<String, Object> defaults = new LinkedHashMap<>();
        defaults.put("app.region", "vn");
        defaults.put("app.audit.enabled", "false");

        environment.getPropertySources().addLast(
                new MapPropertySource(SOURCE_NAME, defaults));
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

Mục đích của ví dụ:

1. Có tên `PropertySource` rõ ràng để hỗ trợ chẩn đoán.
2. Tránh đăng ký trùng nguồn tên `exampleRegionDefaults` trong cùng `Environment`.
3. Dùng `addLast` để chỉ cung cấp giá trị khi nguồn có ưu tiên cao hơn chưa đặt.
4. Dùng `Ordered.LOWEST_PRECEDENCE` để bài học không phụ thuộc vào việc chạy trước Config Data processor. Điều này phù hợp với **fallback đơn giản**, không phù hợp nếu mục tiêu là thay đổi cơ chế nạp Config Data trước khi nó chạy.

### 6.2. Đăng ký bằng `META-INF/spring.factories`

Tạo file đúng đường dẫn:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.boot.RegionDefaultsEnvironmentPostProcessor
~~~

Ký tự `\` cuối dòng đầu là cách xuống dòng/tiếp diễn trong Java Properties. Hoặc viết một dòng để tránh nhầm cú pháp:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.boot.RegionDefaultsEnvironmentPostProcessor
~~~

**Đây là tên fully qualified của interface trong Spring Boot 3.x.** Spring Boot tìm các implementer theo key này trong `spring.factories` khi tạo `SpringApplication`. Đặt `@Component` lên class không phải cách thay thế đáng tin cậy, vì thời điểm environment processing diễn ra **trước** quá trình quét và tạo component beans.

Nếu đóng gói thành JAR thư viện dùng chung, file `META-INF/spring.factories` phải có trong chính JAR xuất bản. Đừng chỉ tạo nó trong `src/test/resources` nếu muốn chức năng có hiệu lực khi chạy production.

### 6.3. Ứng dụng demo

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`src/main/resources/application.yml`:

~~~yaml
app:
  audit:
    enabled: true
~~~

Khi khởi động mà không có `APP_REGION` hoặc nguồn khác cho `app.region`, kết quả thông thường là:

~~~text
app.region = vn
app.audit.enabled = true
~~~

`app.region` đến từ `exampleRegionDefaults`. Trong khi đó `app.audit.enabled=true` trong YAML được ưu tiên hơn `false` từ fallback.

Nếu thêm:

~~~bash
APP_REGION=apac java -jar demo.jar
~~~

thì `app.region=apac` có thể thắng fallback.

### 6.4. Đọc giá trị sau startup

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class DemoDiagnostics {

    @Bean
    ApplicationRunner printEffectiveProperties(Environment environment) {
        return args -> {
            System.out.println("region="
                    + environment.getProperty("app.region"));
            System.out.println("audit="
                    + environment.getProperty("app.audit.enabled"));
        };
    }
}
~~~

Đây là ví dụ quan sát property không nhạy cảm. Với secret thật, **không log toàn bộ Environment hoặc object cấu hình**, vì chúng có thể chứa password, token hoặc thông tin hạ tầng nội bộ.

## 7. API `ApplicationContextInitializer`

Import chính:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
~~~

Giao diện:

~~~java
public interface ApplicationContextInitializer<
        C extends ConfigurableApplicationContext> {

    void initialize(C applicationContext);
}
~~~

Bạn nhận được một `ConfigurableApplicationContext` **đã tồn tại** nhưng chưa refresh. Có thể:

- Đọc `context.getEnvironment()`.
- Thay đổi ID context bằng `context.setId(...)`.
- Thêm application listener.
- Thêm `BeanFactoryPostProcessor` để xử lý trong refresh.
- Chuẩn bị một số thiết lập context-level khác mà implementation thực sự hỗ trợ.

Không nên nghĩ đây là thời điểm các service, repository và bean do `@ComponentScan` tạo ra đã hoàn tất và có thể lấy qua `getBean(...)`. Việc tải bean definitions và khởi tạo bean diễn ra **sau** callback initializer trong luồng Boot thông thường.

## 8. Ví dụ đầy đủ: ApplicationContextInitializer đặt Context ID

Giả sử nhóm vận hành cần mỗi application context có ID khác nhau theo instance chạy. Giá trị được đọc từ config data sau khi Environment đã được chuẩn bị.

Class:

~~~java
package com.example.boot;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public final class InstanceIdContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        String instance = context.getEnvironment()
                .getProperty("app.instance-id", "local");

        context.setId("catalog-" + instance);
    }
}
~~~

`application.yml`:

~~~yaml
app:
  instance-id: zone-a-01
~~~

Khi initializer chạy, context đã có `Environment`. Nó đọc `app.instance-id` và đặt:

~~~text
context.getId() = catalog-zone-a-01
~~~

Đây là một **tùy biến context**, không chỉ là thêm giá trị property. Nó minh họa lý do dùng `ApplicationContextInitializer` thay cho `EnvironmentPostProcessor`.

### 8.1. Đăng ký qua `SpringApplication.addInitializers`

~~~java
package com.example;

import com.example.boot.InstanceIdContextInitializer;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addInitializers(new InstanceIdContextInitializer());
        application.run(args);
    }
}
~~~

`addInitializers(...)` hữu ích khi bạn kiểm soát trực tiếp entrypoint và muốn chỉ định initializers bằng Java, không cần sửa `spring.factories`.

Chú ý gọi trước `run(args)`. Đăng ký initializer vào một instance `SpringApplication` khác sau khi ứng dụng đã chạy không làm thay đổi lần chạy hiện tại.

### 8.2. Đăng ký qua `spring.factories`

Khi đóng gói một thư viện hoặc muốn tự động phát hiện initializer qua classpath, Spring Boot cũng hỗ trợ key:

~~~properties
org.springframework.context.ApplicationContextInitializer=com.example.boot.InstanceIdContextInitializer
~~~

Đặt trong:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Key này thuộc **Spring Framework interface**; nó **khác** key của EnvironmentPostProcessor. Không ghi cả hai class dưới một key rồi kỳ vọng framework tự phân biệt method.

Nếu một application đã đăng ký cùng initializer tường minh bằng `addInitializers(...)` và qua `spring.factories`, cần kiểm soát khả năng logic bị chạy trùng hoặc cùng chức năng được áp dụng nhiều lần. Tốt nhất dùng **một cách đăng ký rõ ràng** cho mỗi initializer.

## 9. Dùng initializer để bổ sung một listener

`ApplicationContextInitializer` cũng có thể dùng để đăng ký application listener vào một context sắp được refresh.

Ví dụ:

~~~java
package com.example.boot;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;

public final class StartupListenerInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.addApplicationListener(
                (ApplicationListener<ContextRefreshedEvent>) event -> {
                    // Chỉ dùng metadata không nhạy cảm trong ví dụ.
                    String id = event.getApplicationContext().getId();
                    System.out.println("Context refreshed: " + id);
                });
    }
}
~~~

Initializer **đăng ký** listener trước refresh; listener thực sự nhận `ContextRefreshedEvent` **khi sự kiện đó được phát đi**, không phải tại chính thời điểm `initialize(...)`.

Nếu mục tiêu chỉ là lắng nghe một application event, đăng ký listener trực tiếp có thể đơn giản hơn viết initializer. Nhưng ví dụ trên cho thấy initializer có quyền **tùy biến chính context**.

Cũng có thể gọi:

~~~java
context.addBeanFactoryPostProcessor(postProcessor);
~~~

để thêm một processor phục vụ bước refresh. Processor đó cần được triển khai theo lifecycle của Spring, không nên dùng nó để gọi các bean nghiệp vụ chưa được tạo.

## 10. ApplicationContextInitializer có sửa Environment được không?

**Có.** Ví dụ:

~~~java
package com.example.boot;

import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public final class ContextFlagInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "contextFlags",
                        Map.of("app.diagnostics.label", "initialized")));
    }
}
~~~

Một bean được tạo **sau đó** có thể truy cập:

~~~java
String label = environment.getProperty("app.diagnostics.label");
~~~

Và `@ConfigurationProperties` được bind sau callback có thể nhìn thấy giá trị phù hợp.

Tuy nhiên, câu hỏi quan trọng là **ai cần đọc property và vào thời điểm nào**.

- Nếu property chỉ dùng bởi bean, `@Value` hoặc `@ConfigurationProperties` trong quá trình context refresh, bổ sung ở initializer **có thể đủ sớm**.
- Nếu property điều khiển việc tìm file như `spring.config.location`, hoặc ảnh hưởng một quá trình **đã chạy trước initializer**, thêm ở initializer **quá muộn**.
- Nếu logging đã được cấu hình dựa trên Environment từ trước, thay `logging.level.root` ở initializer chưa chắc làm logging khởi tạo lại theo giá trị mới.

Vì vậy, `ApplicationContextInitializer` không thay thế `EnvironmentPostProcessor` cho mọi nhu cầu cấu hình sớm, dù cùng có thể gọi `getPropertySources().addLast(...)`.

## 11. Ví dụ song song: cùng bài toán, chọn extension point nào?

Giả sử có hai yêu cầu độc lập:

**Yêu cầu A:** cấp fallback `app.region=vn` để các cơ chế dùng Environment sớm có thể đọc.

**Yêu cầu B:** đổi ID context thành `catalog-zone-a-01` dựa trên `app.instance-id` đã nạp.

Cách chọn:

~~~text
app.region fallback
       |
       v
RegionDefaultsEnvironmentPostProcessor
       |
       v
Environment có thêm PropertySource


app.instance-id từ Environment
       |
       v
InstanceIdContextInitializer
       |
       v
ApplicationContext.setId(...)
~~~

Nếu hai class được đăng ký theo cách đã hướng dẫn, chúng không cạnh tranh làm cùng một việc. Chúng xử lý ở **hai giai đoạn khác nhau**.

Bảng tình huống:

| Nhiệm vụ | Cơ chế ưu tiên | Lý do |
| --- | --- | --- |
| Bổ sung một nguồn property trước khi context được tạo | `EnvironmentPostProcessor` | Được gọi ở giai đoạn chuẩn bị Environment |
| Thêm fallback cho property nghiệp vụ | `EnvironmentPostProcessor` hoặc default properties | Chọn cơ chế đơn giản nhất; đôi khi không cần SPI |
| Đặt Context ID theo property đã có | `ApplicationContextInitializer` | Phải có context để gọi `setId` |
| Đăng ký listener vào context trước refresh | `ApplicationContextInitializer` hoặc listener registration | Có đối tượng context |
| Thêm `BeanFactoryPostProcessor` để chạy trong refresh | `ApplicationContextInitializer` | Có API trên context |
| Đưa property vào Environment để bean sau đó bind | Cả hai có thể làm được | Phụ thuộc thời điểm property được tiêu thụ |
| Cung cấp `spring.config.location` từ mã khởi động | Cần đặt **trước** Config Data processing | Initializer thường quá muộn; EnvironmentPostProcessor cũng phải có order phù hợp |
| Nạp config từ một protocol/remote store tùy biến | Cân nhắc Config Data SPI | `ConfigDataLocationResolver`/`ConfigDataLoader` có contract riêng |
| Lấy một service bean để gọi HTTP sau startup | Không cơ chế nào là lựa chọn phù hợp | Dùng lifecycle sau refresh hoặc readiness/runner thích hợp |

## 12. Thứ tự `EnvironmentPostProcessor` so với Config Data rất quan trọng

Một điểm dễ gây hiểu nhầm: vì `EnvironmentPostProcessor` chạy “sớm”, có phải mọi processor đều chạy **trước** khi Spring Boot nạp `application.yml`?

**Không.** Bản thân việc nạp Config Data của Spring Boot 2.4+ do một processor riêng thực hiện:

~~~java
org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor
~~~

Processor này cũng có thứ tự thực thi. Vì vậy, các `EnvironmentPostProcessor` khác có thể chạy **trước hoặc sau** nó, tùy `Ordered` hoặc `@Order`.

### 12.1. Khi muốn xem Config Data đã nạp

Nếu processor của bạn cần đọc `app.region` từ `application.yml` rồi bổ sung một số giá trị khác, nó cần chạy ở giai đoạn dữ liệu đó đã khả dụng. Một ví dụ order mang tính kỹ thuật:

~~~java
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.core.Ordered;

@Override
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER + 1;
}
~~~

Mục tiêu là chạy **sau** Config Data processor trong Boot 3.x. `Ordered.LOWEST_PRECEDENCE` cũng là một lựa chọn chạy muộn nếu bạn chỉ thêm fallback mà không cần kiểm soát vị trí tương đối rất cụ thể.

Lưu ý thứ tự có thể chịu ảnh hưởng các processor khác; không nên đoán từ tên class hoặc thứ tự ghi trong `spring.factories`. Nếu có yêu cầu lifecycle nhạy cảm, sử dụng `Ordered` một cách có chủ đích và test thực tế.

### 12.2. Khi muốn ảnh hưởng tới việc tìm/nạp Config Data

Những property như:

~~~properties
spring.config.name
spring.config.location
spring.config.additional-location
spring.profiles.active
~~~

có thể tham gia vào quyết định nạp file, profile và cấu trúc Config Data. Thêm chúng **sau khi** Config Data đã được xử lý thì không thể mặc định Spring Boot sẽ quay lại đọc toàn bộ nguồn.

Nếu thật sự cần tùy biến dữ liệu đầu vào của Config Data, hãy chọn hook chạy trước bước tương ứng hoặc dùng API Config Data chuyên dụng. Với cấu hình triển khai thông thường, cung cấp các giá trị này từ **OS environment, JVM system properties hoặc command-line arguments** ngay khi khởi động sẽ dễ hiểu hơn.

Ví dụ:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/catalog/ \
  java -jar app.jar
~~~

Hoặc:

~~~bash
java -Dspring.config.additional-location=optional:file:/etc/catalog/ -jar app.jar
~~~

Hai cách trên cung cấp giá trị từ nguồn sớm hơn một `ApplicationContextInitializer` thông thường.

### 12.3. Khi nào dùng Config Data SPI thay vì EnvironmentPostProcessor?

Nếu yêu cầu là hỗ trợ một dạng URI custom:

~~~properties
spring.config.import=customstore:team/catalog
~~~

thì mô hình Config Data của Spring Boot cung cấp các extension point như:

~~~java
ConfigDataLocationResolver
ConfigDataLoader
~~~

Chúng phù hợp với contract tìm location, load dữ liệu, profile và import được Spring Boot quản lý. Một `EnvironmentPostProcessor` tự đọc và tự thêm nguồn config cũng làm được một số việc, nhưng không tự tham gia đầy đủ vào mọi quy tắc Config Data imports.

**Chọn extension point phù hợp với bài toán** thay vì đưa mọi logic liên quan tới cấu hình vào một processor khởi động tổng hợp.

## 13. `PropertySource` precedence: lỗi dễ gặp ở cả hai extension point

Khi thêm `MapPropertySource`, hai API quan trọng:

~~~java
environment.getPropertySources().addFirst(source);
environment.getPropertySources().addLast(source);
~~~

Ngữ nghĩa tổng quát:

- `addFirst`: nguồn được ưu tiên cao hơn các nguồn hiện có.
- `addLast`: nguồn được ưu tiên thấp hơn các nguồn hiện có.

Ví dụ:

~~~yaml
# application.yml
app:
  mode: development
~~~

Processor thêm:

~~~java
MapPropertySource custom = new MapPropertySource(
        "customMode",
        Map.of("app.mode", "production"));
~~~

Nếu gọi `addFirst(custom)` sau khi nguồn YAML đã có, `app.mode` có thể thành `production`. Nếu gọi `addLast(custom)`, `development` trong YAML thường được giữ.

Không nên đưa một source chỉ có mục đích fallback lên đầu khiến CLI và deployment environment bị ghi đè. Tương tự, không nên đặt một source cần ưu tiên cao vào cuối rồi kết luận processor “không chạy” chỉ vì giá trị bị che bởi nguồn khác.

Có thể chọn vị trí tương đối:

~~~java
sources.addBefore("someSource", custom);
sources.addAfter("someSource", custom);
~~~

nhưng tên nguồn tham chiếu phải **thực sự tồn tại** ở thời điểm gọi. Đừng tự giả định tên hay thứ tự tất cả `PropertySource` ở mọi phiên bản Spring Boot.

## 14. Đăng ký: vì sao `@Component` không đủ?

`@ComponentScan` và `@Bean` hoạt động trong giai đoạn xử lý application context và bean definitions. Một `EnvironmentPostProcessor` cần được gọi **trước** khi quá trình tạo bean thông thường diễn ra.

Do đó:

~~~java
@Component
public class MyEnvironmentPostProcessor
        implements EnvironmentPostProcessor {
    // ...
}
~~~

không phải mẫu đăng ký đúng cho SPI này. Class có thể được nhận như bean về sau, nhưng **không có nghĩa** nó đã được Spring Boot gọi ở giai đoạn Environment preparation.

Tương tự, một `ApplicationContextInitializer` tự đăng ký thành `@Component` thông thường cũng không bảo đảm nó được áp dụng như initializer trong bước trước refresh; lúc component được tạo đã qua thời điểm này.

Hãy đăng ký đúng:

- `EnvironmentPostProcessor`: `META-INF/spring.factories` với key của Boot.
- `ApplicationContextInitializer`: `SpringApplication.addInitializers(...)` hoặc `spring.factories` với key của Framework.

Đối với cùng một `spring.factories` có nhiều loại SPI:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.boot.RegionDefaultsEnvironmentPostProcessor
org.springframework.context.ApplicationContextInitializer=com.example.boot.InstanceIdContextInitializer
~~~

Đây là hai mục độc lập, không phải một danh sách class chung.

## 15. Thứ tự giữa các initializers

`ApplicationContextInitializer` có thể được sắp thứ tự bằng Spring `Ordered` hoặc `@Order` khi có nhiều initializer cùng tác động tới context.

Ví dụ:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.Ordered;

public final class ContextIdInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.setId("catalog-" + context.getEnvironment()
                .getProperty("app.instance-id", "local"));
    }
}
~~~

Một initializer khác chạy sau có thể đọc `context.getId()`. Tuy nhiên, nếu cả hai cùng thay context ID, kết quả phụ thuộc thứ tự và logic thực hiện. Đừng thiết kế hệ thống có nhiều initializer âm thầm ghi đè cùng một trạng thái quan trọng.

**Quan trọng:** order của `ApplicationContextInitializer` chỉ quyết định thứ tự **giữa các initializers** trong chính giai đoạn của chúng. Nó không cho phép initializer “nhảy ngược” lên trước quá trình Environment preparation chỉ bằng `Ordered.HIGHEST_PRECEDENCE`.

Tương tự, `Ordered` trên `EnvironmentPostProcessor` xác định thứ tự **các processors trong giai đoạn Environment**, không làm cho nó có quyền truy cập context chưa tồn tại.

## 16. Liên hệ với `@PropertySource` và `@Value`

Một lập trình viên có thể hỏi: “Tôi chỉ cần thêm một file properties, sao không dùng `@PropertySource`?”

Ví dụ:

~~~java
@Configuration
@PropertySource("classpath:extra.properties")
public class ExtraPropertiesConfiguration {
}
~~~

`@PropertySource` được xử lý cùng cấu hình class trong giai đoạn context processing. Trong Spring Boot, điều đó có thể **quá muộn** đối với các property dùng ngay từ đầu, như một số thiết lập logging hoặc `spring.main.*`.

Ngược lại, `EnvironmentPostProcessor` tạo nguồn property trong giai đoạn chuẩn bị Environment. Nếu một nguồn tùy biến cần được nhìn thấy rất sớm, đây là khác biệt thực tế.

Với bean ứng dụng:

~~~java
@Component
public class RegionReporter {

    public RegionReporter(
            @Value("${app.region:unknown}") String region) {
        System.out.println(region);
    }
}
~~~

giá trị `app.region` có thể đến từ `@PropertySource`, `application.yml`, environment variables hoặc nguồn mà processor thêm, miễn là nó có hiệu lực vào lúc placeholder được resolve.

Nhưng `@Value` thành công **không chứng minh** property đã có mặt sớm tới mức ảnh hưởng Config Data. Hãy chọn giải pháp dựa trên **consumer sớm nhất** cần đọc key đó.

## 17. Không nên inject service vào extension point khởi động sớm

### 17.1. Trong `EnvironmentPostProcessor`

Không nên viết processor dựa vào một `@Service` như:

~~~java
public MyProcessor(RemoteConfigService remoteConfigService) {
    this.remoteConfigService = remoteConfigService;
}
~~~

và kỳ vọng Spring Boot inject nó như một bean thông thường. Processor do SPI khởi tạo ở giai đoạn ứng dụng chưa có context sẵn sàng cho dependency injection.

Trong Spring Boot 3.x, nếu thực sự cần khả năng hỗ trợ đặc biệt của startup, các constructor tham số như `DeferredLogFactory` hoặc `ConfigurableBootstrapContext` được hỗ trợ trong phạm vi API tương ứng. Đây **không phải** quyền inject tùy ý mọi service bean.

### 17.2. Trong `ApplicationContextInitializer`

Initializer có context reference, nhưng context **chưa refresh**, nên cũng không nên lấy service qua:

~~~java
// Không nên làm trong initialize(...):
context.getBean(RemoteConfigService.class);
~~~

Bean definitions có thể chưa được tải, bean có thể chưa tồn tại, hoặc việc tạo sớm gây ra lifecycle behavior không mong muốn.

Nếu cần gọi service sau khi ứng dụng khởi động, cân nhắc `ApplicationRunner`, `CommandLineRunner`, một event listener giai đoạn sau hoặc một bean lifecycle phù hợp.

### 17.3. Security và IO

Cả hai extension point đều chạy trong quá trình startup và có thể làm ứng dụng không khởi động được nếu xảy ra lỗi.

- Tránh gọi network không có timeout.
- Tránh đọc secret rồi in ra log.
- Tránh thay đổi môi trường toàn tiến trình như `System.setProperty(...)` nếu không cần.
- Tránh tạo file hoặc mutate shared infrastructure không có cơ chế kiểm soát.
- Khi nguồn config bắt buộc bị lỗi, chọn policy fail-fast rõ ràng; khi nguồn là optional, thiết kế fallback có chủ đích.

Nếu bắt buộc tích hợp remote secret store, cân nhắc cơ chế tích hợp chuyên dụng với Config Data hoặc secret manager được framework hỗ trợ, thay vì tự triển khai một processor mạng đơn giản nhưng thiếu retry/security contract.

## 18. Logging trong giai đoạn rất sớm

Một processor có thể muốn ghi log để debug thứ tự khởi động:

~~~java
@Override
public void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application) {
    // Có thể chạy trước khi logging system hoàn tất.
}
~~~

Nhưng logging cũng có thể được cấu hình **từ Environment**. Nếu dùng logger thông thường quá sớm, format hoặc level không nhất thiết phản ánh cấu hình cuối cùng.

Spring Boot 3.x hỗ trợ cơ chế như `DeferredLogFactory` cho một số environment processors để hoãn việc phát log tới khi environment/logger đã sẵn sàng:

~~~java
import org.springframework.boot.logging.DeferredLogFactory;
import org.apache.commons.logging.Log;

public final class LoggingAwareProcessor
        implements EnvironmentPostProcessor {

    private final Log log;

    public LoggingAwareProcessor(DeferredLogFactory factory) {
        this.log = factory.getLog(LoggingAwareProcessor.class);
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {
        log.info("Environment extension is active");
    }
}
~~~

Đây là **constructor injection đặc biệt do Boot cung cấp cho SPI**, không phải bean DI thông thường. API/import có thể khác theo phiên bản Boot; hãy đọc Javadoc chính xác của version đang sử dụng.

Trong `ApplicationContextInitializer`, logging thường đã đi xa hơn trong startup lifecycle, nhưng không nên mặc định mọi thay đổi `logging.*` tại thời điểm này sẽ được logging system áp dụng lại.

## 19. Kiểm thử đơn vị `EnvironmentPostProcessor`

Đối với xử lý `PropertySource` thuần, có thể test trực tiếp class mà không khởi động toàn ứng dụng:

~~~java
package com.example.boot;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class RegionDefaultsEnvironmentPostProcessorTest {

    private final RegionDefaultsEnvironmentPostProcessor processor =
            new RegionDefaultsEnvironmentPostProcessor();

    @Test
    void addsFallbackWhenNoRegionIsProvided() {
        StandardEnvironment environment = new StandardEnvironment();

        processor.postProcessEnvironment(
                environment, new SpringApplication(Object.class));

        assertThat(environment.getProperty("app.region"))
                .isEqualTo("vn");
    }

    @Test
    void preservesHigherPriorityOverride() {
        StandardEnvironment environment = new StandardEnvironment();

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "deployment",
                        Map.of("app.region", "apac")));

        processor.postProcessEnvironment(
                environment, new SpringApplication(Object.class));

        assertThat(environment.getProperty("app.region"))
                .isEqualTo("apac");
    }
}
~~~

Những test này chứng minh **logic class** và precedence trong một environment được chuẩn bị rõ ràng. Chúng **chưa chứng minh** rằng ứng dụng thật có `spring.factories` đúng path/key hoặc processor được gọi đúng order bởi SpringApplication.

Để kiểm chứng SPI registration, cần thêm một integration test khởi động thực tế với `SpringApplication` hoặc đóng gói chạy JAR.

## 20. Kiểm thử đơn vị `ApplicationContextInitializer`

Vì callback nhận một context chưa refresh, có thể tạo context rồi gọi initializer trong unit test:

~~~java
package com.example.boot;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class InstanceIdContextInitializerTest {

    @Test
    void setsContextIdFromEnvironment() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try {
            context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("test", Map.of(
                        "app.instance-id", "zone-b-02")));

            new InstanceIdContextInitializer().initialize(context);

            assertThat(context.getId())
                    .isEqualTo("catalog-zone-b-02");
        }
        finally {
            context.close();
        }
    }
}
~~~

Test trên không cần khởi tạo tất cả singleton beans. Nó cho thấy initializer làm việc trên một context object và có thể dùng Environment đã được gắn vào context.

Giống như processor test, unit test này **không tự kiểm chứng** `SpringApplication.addInitializers(...)` hoặc `spring.factories` đã được gắn đúng trong ứng dụng thật.

### 20.1. Integration test theo toàn bộ lifecycle

Khi cần kiểm tra hai extension point phối hợp, có thể chạy một `SpringApplication` tối giản:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);
application.addInitializers(new InstanceIdContextInitializer());

try (ConfigurableApplicationContext context = application.run(
        "--app.instance-id=test-01")) {

    String region = context.getEnvironment()
            .getProperty("app.region");

    String id = context.getId();

    // Assert region và ID theo thiết kế.
}
~~~

Ví dụ cần import:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
~~~

Nếu `RegionDefaultsEnvironmentPostProcessor` đã đăng ký đúng `spring.factories` trên test runtime classpath, lúc này Spring Boot có thể kích hoạt processor trong bước chuẩn bị Environment. Initializer được đăng ký tường minh sẽ chạy khi context được tạo.

**Chú ý:** `ApplicationContextRunner` rất hữu ích khi test các bean, nhưng nó không mặc nhiên đi qua toàn bộ lifecycle `SpringApplication` như khởi động Boot thật. Nếu bài kiểm thử nhằm xác nhận `spring.factories` của EnvironmentPostProcessor được kích hoạt tự động, dùng một con đường khởi động `SpringApplication` thực tế sẽ đáng tin hơn.

## 21. Chẩn đoán khi extension point không chạy

Một số lỗi rất thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `EnvironmentPostProcessor` không được gọi | Không có file `META-INF/spring.factories` hoặc key sai | Kiểm tra classpath/JAR resource và fully qualified interface name |
| Thêm `@Component` nhưng không chạy sớm | Component scan xảy ra muộn hơn | Đăng ký processor qua SPI `spring.factories` |
| Bị `ClassNotFoundException` khi startup | Sai package/class name trong factories | Đối chiếu class compiled và resource |
| Processor chạy nhưng property không thắng | Dùng `addLast` dưới một source có giá trị trùng | Xem precedence và chọn vị trí nguồn đúng mục đích |
| Processor chạy hai lần và thêm source trùng | Logic không idempotent hoặc có nhiều cách đăng ký | Kiểm tra tên source trước khi thêm |
| Giá trị trong `application.yml` chưa đọc được | Processor chạy trước Config Data processor | Xác định order hoặc chọn hook phù hợp |
| `spring.config.location` đặt từ initializer không hiệu lực | Config Data đã được xử lý | Cung cấp property từ nguồn sớm hoặc thiết kế Config Data SPI |
| Initializer không chạy | Chưa gọi `addInitializers` hoặc factories key sai | Đăng ký đúng trước `run` |
| Initializer gọi `getBean` bị lỗi | Bean definitions/chương trình chưa refresh | Chuyển logic sang giai đoạn tạo bean hoặc sau refresh |
| Thêm listener nhưng không thấy event | Lắng nghe sai loại sự kiện hoặc context | Kiểm tra loại event và ngữ cảnh phát event |
| Cấu hình logging không phản ánh processor | Logger chưa cấu hình ở thời điểm sớm | Xem `DeferredLogFactory` và timing |
| Chạy trong IDE được, JAR không chạy | `spring.factories` không được đóng gói vào artifact | Kiểm tra resources trong build output/JAR |
| Dùng import Boot 3.x trong Boot 4.x lỗi | Package/API đã thay đổi | Kiểm tra Javadoc của version chính xác |
| Context ID bất ngờ | Nhiều initializers cùng sửa ID hoặc config override | Kiểm tra initializer ordering và nguồn config hiệu lực |

Khi debug, có thể quan sát những tên `PropertySource` không nhạy cảm:

~~~java
for (PropertySource<?> source
        : environment.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

Không nên tự in mọi `source.getProperty(...)` vì có thể làm lộ secrets. Nếu dùng Actuator, `/actuator/env` hoặc `/actuator/configprops` cần được bảo vệ và có cơ chế che dữ liệu nhạy cảm.

## 22. `EnvironmentPostProcessor`, `ApplicationListener` và `ApplicationRunner`

Ba loại hook này không nên bị dùng thay cho nhau tùy tiện:

| Hook | Khi phù hợp | Điều không nên kỳ vọng |
| --- | --- | --- |
| `EnvironmentPostProcessor` | Bổ sung/tùy biến Environment trước khi tạo context | Inject bean nghiệp vụ |
| `ApplicationContextInitializer` | Tùy biến context trước refresh | Lấy service đã khởi tạo như sau refresh |
| `ApplicationListener<ApplicationEnvironmentPreparedEvent>` | Quan sát/xử lý sự kiện Environment prepared | Tự động có context đã tạo |
| `BeanFactoryPostProcessor` | Điều chỉnh bean definitions trong refresh | Trực tiếp thay thế Config Data initialization |
| `ApplicationRunner` | Thực hiện tác vụ sau khi context refresh | Ảnh hưởng lựa chọn config files đã nạp |

Nếu chỉ muốn **chạy một công việc sau khi bean sẵn sàng**, `ApplicationRunner` hoặc listener sau refresh đơn giản hơn. Nếu muốn **thay đổi config trước khi bean tạo**, chọn extension point sớm.

`ApplicationListener<ApplicationEnvironmentPreparedEvent>` có thể truy cập Environment ở một thời điểm sớm, nhưng `EnvironmentPostProcessor` là contract chuyên dụng cho việc xử lý Environment và có cách ordering theo processor mà Spring Boot thiết kế.

## 23. Lưu ý tương thích Spring Boot 3.x và 4.x

Ví dụ trong phần chính nhắm đến **Spring Boot 3.3–3.5** với:

~~~java
org.springframework.boot.env.EnvironmentPostProcessor
~~~

và `spring.factories` key:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.boot.RegionDefaultsEnvironmentPostProcessor
~~~

Trong **Spring Boot 4.x**, API này được chuyển dần sang namespace khác, với interface `org.springframework.boot.EnvironmentPostProcessor` ở phiên bản mới. Một số package cũ có thể còn tồn tại ở dạng deprecated trong giai đoạn chuyển tiếp.

Do đó, nếu dự án dùng Boot 4.x, hãy kiểm tra **Javadoc và migration guide của chính phiên bản đang chạy** rồi cập nhật import và key `spring.factories` cho phù hợp. Không nên dùng nguyên một ví dụ Boot 3.x với Boot 4.x chỉ vì tên interface ngắn giống nhau.

Ngược lại, `ApplicationContextInitializer` thuộc Spring Framework:

~~~java
org.springframework.context.ApplicationContextInitializer
~~~

Nó không phải cùng interface với EnvironmentPostProcessor, ngay cả ở những phiên bản Boot mới.

Các ý tưởng lifecycle trong bài vẫn hữu ích: một extension point xử lý Environment sớm; một extension point khởi tạo Context trước refresh. Nhưng **tên class/package và cách đăng ký SPI phải theo phiên bản**.

## 24. Bài tập thực hành

### Bài 1: chọn extension point

Hệ thống cần thêm `app.region=vn` như một **fallback**, nhưng cho phép deployment dùng `APP_REGION=apac` ghi đè.

**Đáp án:** `EnvironmentPostProcessor` với `MapPropertySource` được thêm bằng `addLast`, hoặc một cấu hình mặc định khác nếu không cần processor. Không dùng `addFirst` cho fallback.

### Bài 2: phân biệt property source với context state

Hệ thống muốn đặt context ID thành `catalog-zone-c-03` dựa trên property `app.instance-id=zone-c-03`.

**Đáp án:** `ApplicationContextInitializer` nhận `ConfigurableApplicationContext`, đọc `context.getEnvironment()` rồi gọi `context.setId(...)`.

### Bài 3: xác định giai đoạn quá muộn

Một initializer thêm:

~~~java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource("late", Map.of(
                "spring.config.location",
                "file:/etc/catalog/")));
~~~

Có nên kỳ vọng Spring Boot nạp lại toàn bộ `application.yml` theo location mới?

**Đáp án:** Không. Initializer chạy **sau** giai đoạn chuẩn bị Environment và Config Data thông thường. Việc thêm property sau đó không mặc nhiên kích hoạt xử lý lại các config locations.

### Bài 4: kiểm tra thứ tự

Một `EnvironmentPostProcessor` được đặt order thấp để đọc `app.name` từ YAML, nhưng chạy trước Config Data processor.

**Đáp án:** Không chỉ dựa vào một số order tùy ý. Xem `ConfigDataEnvironmentPostProcessor.ORDER` và thiết lập thứ tự phù hợp, hoặc chuyển nhu cầu sang extension point phù hợp hơn. Khi cần giá trị từ YAML, phải chạy sau lúc YAML đã được nạp.

### Bài 5: đăng ký SPI

Đoạn `spring.factories`:

~~~properties
org.springframework.context.ApplicationContextInitializer=com.example.boot.RegionDefaultsEnvironmentPostProcessor
~~~

Có đúng không?

**Đáp án:** Sai vì key thuộc `ApplicationContextInitializer` nhưng class triển khai `EnvironmentPostProcessor`. Trong Boot 3.x, key đúng là `org.springframework.boot.env.EnvironmentPostProcessor`.

### Bài 6: thao tác trên bean quá sớm

Trong `initialize(context)`:

~~~java
PaymentService service = context.getBean(PaymentService.class);
service.warmUp();
~~~

Tại sao nguy hiểm?

**Đáp án:** Context chưa refresh và bean definitions có thể chưa được nạp. Lấy bean lúc này có thể lỗi hoặc tạo lifecycle bất thường. Đưa thao tác warm-up sang giai đoạn sau khi bean sẵn sàng, với timeout và chính sách failure rõ ràng.

### Bài 7: phối hợp hai extension point

Cho file:

~~~yaml
app:
  instance-id: node-07
  audit:
    enabled: true
~~~

Processor thêm fallback:

~~~properties
app.region=vn
app.audit.enabled=false
~~~

Initializer đặt:

~~~java
context.setId("catalog-" + context.getEnvironment()
        .getProperty("app.instance-id", "local"));
~~~

Nếu không có nguồn ưu tiên cao khác, kết quả dự kiến:

~~~text
app.region        = vn
app.audit.enabled = true
context ID        = catalog-node-07
~~~

Lý do: source fallback `addLast` không ghi đè `app.audit.enabled=true` trong YAML; initializer đọc `app.instance-id` rồi sửa state của context.

## 25. Checklist triển khai

Trước khi đưa một extension point vào ứng dụng thật:

1. **Xác định consumer sớm nhất** cần property hoặc context state. Consumer đó chạy trước hay sau Config Data processing?
2. **Chọn đúng interface:** EnvironmentPostProcessor cho Environment, ApplicationContextInitializer cho context.
3. **Đăng ký đúng cơ chế:** `spring.factories` cho processor; `addInitializers` hoặc `spring.factories` cho initializer.
4. **Kiểm tra version Spring Boot:** package Boot 3.x và Boot 4.x có thể khác nhau.
5. **Đặt priority có chủ đích:** `addLast` cho fallback; `addFirst` chỉ khi cần override thực sự.
6. **Thiết kế idempotent:** kiểm tra tên PropertySource trước khi thêm, không tạo side effects lặp vô ý.
7. **Không phụ thuộc bean được tạo muộn:** không truy cập repository/service trong hai giai đoạn sớm.
8. **Không coi Initializer như một Config Data resolver:** việc thêm `spring.config.*` muộn không nạp lại file.
9. **Không log secrets:** chỉ ghi metadata hoặc trạng thái không nhạy cảm.
10. **Test hai lớp:** unit test logic và integration test xác minh SPI registration/lifecycle.
11. **Giữ thao tác startup nhanh và xác định:** tránh network/blocking lâu hoặc thay đổi shared state không kiểm soát.
12. **Tài liệu hóa contract:** nói rõ processor thêm nguồn nào, thứ tự ưu tiên, giá trị mặc định và cách override trong deployment.

## 26. Ghi nhớ

- **`EnvironmentPostProcessor`** (Spring Boot) chỉnh `ConfigurableEnvironment` trong bước chuẩn bị cấu hình, trước khi tạo `ApplicationContext`.
- **`ApplicationContextInitializer`** (Spring Framework) chỉnh `ConfigurableApplicationContext` đã được tạo nhưng **chưa refresh**.
- Cả hai **có thể thêm `PropertySource`**, nhưng điểm khác nhau là **thời điểm** và **đối tượng đích**. Những property dùng cho Config Data hoặc logging sớm không nên được bổ sung muộn trong initializer.
- Trong **Boot 3.x**, `EnvironmentPostProcessor` được đăng ký qua `META-INF/spring.factories` với key `org.springframework.boot.env.EnvironmentPostProcessor`.
- `ApplicationContextInitializer` có thể đăng ký qua `SpringApplication.addInitializers(...)` hoặc `spring.factories` với key `org.springframework.context.ApplicationContextInitializer`.
- Không dùng `@Component` như một cách thay thế cho registration SPI sớm.
- Dùng `Ordered` hoặc `@Order` cho thứ tự **trong từng giai đoạn**; đừng nhầm order với việc thay đổi bản chất lifecycle.
- Dùng `addLast` cho fallback và hiểu rõ precedence khi thêm nguồn tùy biến.
- Không lấy bean nghiệp vụ trong các extension point khởi động sớm.
- Nếu nạp cấu hình từ location custom, cân nhắc **Config Data SPI** thay vì giải quyết mọi việc qua một processor thủ công.

### Tài liệu tham khảo

- Spring Boot 3.5 — Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 — SpringApplication lifecycle/events: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 API — EnvironmentPostProcessor: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.5 API — ConfigDataEnvironmentPostProcessor: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
- Spring Boot 3.5 API — SpringApplication: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework API — ApplicationContextInitializer: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextInitializer.html
- Spring Boot 4.x API — EnvironmentPostProcessor: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/EnvironmentPostProcessor.html
