# Đăng ký đối tượng khởi tạo sớm qua BootstrapRegistryInitializer

## Mục tiêu học tập

Trong Spring Boot, một số thành phần phải sẵn sàng **trước khi `ApplicationContext` được tạo và refresh**: ví dụ client đọc cấu hình từ nguồn bên ngoài, bộ giải mã thông tin cấu hình, trình xác thực dùng khi nạp Config Data hoặc một tài nguyên cần chia sẻ giữa nhiều bước bootstrap. Ở giai đoạn đó, các bean thông thường do `@Component`/`@Bean` tạo ra chưa nhất thiết tồn tại.

Spring Boot cung cấp `BootstrapRegistryInitializer` và `BootstrapRegistry` để đăng ký các đối tượng phục vụ **giai đoạn khởi động sớm**. Mục tiêu bài học là hiểu đúng API, thời điểm thực thi và khả năng chuyển một đối tượng từ bootstrap context sang application context.

Sau bài này, bạn có thể:

1. Phân biệt `BootstrapRegistryInitializer`, `BootstrapRegistry`, `BootstrapContext`, `ApplicationContextInitializer` và `ApplicationContext`.
2. Đăng ký đối tượng sớm bằng `register(...)` hoặc `registerIfAbsent(...)` với `InstanceSupplier`.
3. Giải thích việc **đăng ký supplier không đồng nghĩa khởi tạo ngay đối tượng**; lần `BootstrapContext.get(...)` mới kích hoạt việc tạo khi cần.
4. Dùng `addCloseListener(...)` để nhận `BootstrapContextClosedEvent`, truy cập `getApplicationContext()` và đưa một đối tượng sớm vào Spring context theo cách được thiết kế.
5. Đăng ký initializer bằng code hoặc `META-INF/spring.factories`, chạy ví dụ Java 17+ / Spring Boot 3.3 và tránh những nhầm lẫn về lifecycle.

> **Phiên bản trong bài:** Spring Boot 3.3.x (minh họa 3.3.13), trong đó các kiểu `BootstrapRegistryInitializer`, `BootstrapRegistry`, `BootstrapContext` nằm ở package `org.springframework.boot`. Không sao chép import từ tài liệu Spring Boot 4 nếu chưa kiểm tra khác biệt package/API.

## 1. Tại sao cần điểm mở rộng này?

Một ứng dụng Spring Boot thường bắt đầu như sau:

~~~text
main()
   │
   ▼
SpringApplication.run(...)
   │
   ├─ Bootstrap registry / bootstrap context
   │    ├─ BootstrapRegistryInitializer đăng ký đối tượng sớm
   │    └─ Những bước khởi động sớm có thể lấy đối tượng khi cần
   │
   ├─ Chuẩn bị Environment, xử lý Config Data
   ├─ Tạo và chuẩn bị ApplicationContext
   │    └─ Đóng bootstrap context và gọi close listeners
   │
   ├─ Nạp bean definitions và refresh ApplicationContext
   │    ├─ Tạo singleton non-lazy, auto-configuration...
   │    └─ Hoàn tất refresh
   │
   ├─ ApplicationStartedEvent
   ├─ ApplicationRunner / CommandLineRunner
   └─ ApplicationReadyEvent
~~~

Sơ đồ nêu các **mốc quan trọng**, không liệt kê mọi phương thức nội bộ. Đặc biệt, thông điệp “bootstrap context đóng” có nghĩa là **giai đoạn chuẩn bị application context đã đến điểm kết thúc**, **không phải ứng dụng sắp shutdown**.

Ví dụ, khi nạp cấu hình từ config server, một thành phần xử lý Config Data có thể cần HTTP client tùy chỉnh **trước** khi hầu hết bean application được tạo. Nếu đặt client đó trong một `@Bean` thông thường rồi cố inject vào giai đoạn xử lý config data, thứ tự khởi tạo không phù hợp: các thành phần application chưa sẵn sàng.

`BootstrapRegistry` cung cấp một registry tạm, truy cập theo **type (`Class<?>`)**, có khả năng tạo instance lười khi được yêu cầu. Nó giúp các bước bootstrap trao đổi một đối tượng dùng chung mà không cần chờ bean factory thông thường.

**Ranh giới:** Đây là một cơ chế *early startup extension*, không phải một container DI thứ hai đầy đủ tính năng và cũng không phải cách thay thế mọi `@Configuration` trong ứng dụng.

## 2. Phân biệt các khái niệm

| Thành phần | Mục đích | Lúc có hiệu lực |
| --- | --- | --- |
| `BootstrapRegistryInitializer` | Callback có `initialize(BootstrapRegistry registry)` để cấu hình các đăng ký sớm. | Khi SpringApplication chuẩn bị bootstrap context, trước các bước cần registry. |
| `BootstrapRegistry` | Đăng ký supplier theo type, thêm close listeners. | Trong quá trình bootstrap. |
| `BootstrapContext` | Lấy instance đã đăng ký bằng `get(Class<T>)` và các biến thể. | Trong các bước bootstrap có quyền truy cập context này. |
| `ConfigurableBootstrapContext` | Giao diện kết hợp quyền đăng ký và truy cập. | Triển khai cụ thể của bootstrap context. |
| `BootstrapContextClosedEvent` | Cho biết bootstrap context đóng và cung cấp application context đã chuẩn bị. | Ở điểm chuyển tiếp sang application context; **trước khi startup hoàn tất**. |
| `ApplicationContextInitializer` | Tùy biến `ConfigurableApplicationContext` trước refresh. | Khi application context đã được tạo nhưng chưa refresh. |
| `ApplicationContext` | Container Spring đầy đủ, quản lý bean và lifecycle của ứng dụng. | Khi startup tiến triển đến tạo/refresh context và trong runtime. |

Hai điểm mở rộng có tên gần nhau nhưng khác nhau:

~~~java
// Early bootstrap: dành cho BootstrapRegistry.
public interface BootstrapRegistryInitializer {
    void initialize(BootstrapRegistry registry);
}

// Application context preparation: dùng ConfigurableApplicationContext.
public interface ApplicationContextInitializer<C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
~~~

Hai khai báo trên dùng để **diễn giải chữ ký API**, không phải source file cần thêm vào project. Trong Spring Boot 3.3, giao diện thứ nhất thuộc `org.springframework.boot`, còn giao diện thứ hai thuộc `org.springframework.context`.

`@PostConstruct` của một bean lại muộn hơn nữa: nó chạy khi chính bean đó được Spring khởi tạo. Nếu cần can thiệp vào Config Data trước khi application beans được tạo, đăng ký bean bằng `@PostConstruct` không phải một giải pháp thay thế hợp lệ.

### Bootstrap context và Spring Cloud bootstrap context

Tên gọi có thể gây nhầm. `BootstrapRegistry`/`BootstrapContext` ở đây là **API của Spring Boot** để chia sẻ đối tượng giai đoạn startup. Nó không đồng nghĩa với **bootstrap application context** tùy chọn trong các cơ chế legacy của Spring Cloud. Khi đọc tài liệu Spring Cloud Config, hãy phân biệt hai khái niệm và chế độ nạp cấu hình thực tế.

## 3. Hợp đồng BootstrapRegistryInitializer

Spring Boot 3.3 định nghĩa một functional interface có một phương thức chính:

~~~java
package org.springframework.boot;

// Chữ ký rút gọn để học, không phải file nguồn tự tạo.
@FunctionalInterface
public interface BootstrapRegistryInitializer {
    void initialize(BootstrapRegistry registry);
}
~~~

Bạn có thể triển khai bằng class hoặc lambda:

~~~java
BootstrapRegistryInitializer initializer = registry -> {
    registry.registerIfAbsent(
            StartupClient.class,
            context -> new StartupClient("local-demo"));
};
~~~

Đây là **đoạn minh họa một phần**; `StartupClient` là type giả định và ví dụ hoàn chỉnh dùng `EarlyClient` ở mục 6.

### Các API quan trọng

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `registry.register(Type.class, supplier)` | Gắn một supplier với một class key. | Có quy tắc thay thế đăng ký hiện có; phải hiểu cạnh tranh giữa các initializer. |
| `registry.registerIfAbsent(Type.class, supplier)` | Chỉ đăng ký nếu type chưa có supplier. | Hữu ích cho giá trị mặc định có thể được ứng dụng khác cung cấp. |
| `registry.isRegistered(Type.class)` | Kiểm tra type đã đăng ký chưa. | Kiểm tra đăng ký, **không đồng nghĩa instance đã được tạo**. |
| `registry.getRegisteredInstanceSupplier(Type.class)` | Lấy supplier đã đăng ký, hoặc `null`. | Không được nhầm với `BootstrapContext.get(...)` để lấy instance. |
| `registry.addCloseListener(listener)` | Đăng ký listener nhận `BootstrapContextClosedEvent`. | Dùng để chuyển giao tài nguyên khi application context đã chuẩn bị. |
| `bootstrapContext.get(Type.class)` | Nhận instance theo type; tạo qua supplier nếu chưa có. | Throw `IllegalStateException` khi type chưa đăng ký. |
| `bootstrapContext.getOrElse(...)` | Lấy instance hoặc dùng fallback. | Không tự đăng ký fallback vào registry. |

`BootstrapRegistry.InstanceSupplier<T>` nhận một `BootstrapContext`. Nhờ vậy một supplier có thể lấy phụ thuộc **đã đăng ký ở bootstrap context**:

~~~java
registry.registerIfAbsent(
        Credentials.class,
        context -> new Credentials("local-only"));

registry.registerIfAbsent(
        StartupClient.class,
        context -> new StartupClient(
                context.get(Credentials.class)));
~~~

Đây là **minh họa API**, cần định nghĩa `Credentials` và `StartupClient` khi dùng thực tế. Mục đích là làm rõ tham số `context` trong lambda: đó là bootstrap context, không phải bean factory. Tránh dependency vòng và không giả định có sẵn bất kỳ Spring bean nào trong bootstrap context.

### “Đăng ký sớm” có phải “khởi tạo sớm” không?

**Không hoàn toàn.** Lời gọi:

~~~java
registry.registerIfAbsent(
        EarlyClient.class,
        context -> new EarlyClient("from-bootstrap"));
~~~

chỉ đưa **supplier** vào registry. Constructor của `EarlyClient` chưa nhất thiết chạy. Khi một bước bootstrap (hoặc close listener) gọi:

~~~java
EarlyClient client = bootstrapContext.get(EarlyClient.class);
~~~

instance được tạo nếu chưa có; bootstrap context hỗ trợ truy cập lazy tới singleton. Nếu muốn đối tượng thực sự tồn tại ở pha sớm, một thành phần hợp lệ phải **yêu cầu nó trước khi pha đó kết thúc**.

Đừng tạo object ngay bên ngoài supplier rồi truyền vào lambda nếu muốn tối ưu thời điểm tạo; ví dụ `EarlyClient value = new EarlyClient(...); registry.register(..., context -> value);` đã xây dựng object trước khi gọi `register`.

### Key theo Class, không phải tên bean

Bootstrap registry dùng `Class` làm key, nên tại một thời điểm chỉ có một đăng ký cho một type trong registry tương ứng. Nó không có quy tắc `@Qualifier("primary")` hay tên bean giống `BeanFactory`. Khi cần hai client cùng loại nhưng khác cấu hình, có thể tạo hai wrapper type chuyên biệt hoặc thiết kế một holder chứa các client, sau đó đăng ký holder đó theo type.

## 4. Khi nào listener đóng bootstrap được gọi?

`registry.addCloseListener(...)` nhận listener cho sự kiện `BootstrapContextClosedEvent`. Sự kiện này chứa:

- `getBootstrapContext()`: tham chiếu đến bootstrap context đang đóng, cho phép lấy đối tượng đã đăng ký.
- `getApplicationContext()`: `ConfigurableApplicationContext` đã được Spring Boot chuẩn bị.

**Đây không phải `ContextClosedEvent` của ứng dụng khi tắt JVM.** Close listener của bootstrap xảy ra trong startup, ở điểm sau khi application context đã được chuẩn bị nhưng **trước khi toàn bộ quá trình refresh/runner/ready hoàn tất**.

Các trường hợp hữu ích:

1. Một Config Data loader đã tạo client sớm, và bạn cần **dùng lại chính instance** đó khi Spring context khởi động.
2. Một đối tượng bootstrap cần được chuyển cho container để quản lý lifecycle phù hợp.
3. Bạn muốn chuyển tiếp một số thông tin khởi động sau khi bootstrap context không còn là registry đang phục vụ các bước đầu.

Lưu ý: **Đóng bootstrap context không tự đăng ký mọi object làm Spring bean**. Bạn phải viết logic chuyển giao tường minh. Ngoài ra, gọi `getApplicationContext()` không có nghĩa các bean application đã được tạo hoặc controller đã phục vụ HTTP.

## 5. Hai cách đăng ký BootstrapRegistryInitializer

### Cách A: đăng ký qua SpringApplication bằng code

~~~java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.addBootstrapRegistryInitializer(
        new DemoBootstrapRegistryInitializer());
application.run(args);
~~~

Đây là **đoạn minh họa**, giả sử đã có hai class và import. `addBootstrapRegistryInitializer(...)` của Spring Boot 3.3 nhận một initializer; hãy gọi **trước `run`**. Cách này rõ ràng, tiện khi bạn sở hữu phương thức `main`.

Có thể viết lambda nếu logic ngắn:

~~~java
application.addBootstrapRegistryInitializer(registry ->
        registry.registerIfAbsent(
                EarlyClient.class,
                ignored -> new EarlyClient("example")));
~~~

Nếu initializer cần nhiều bước (supplier và close listener), một class riêng thường dễ kiểm thử và giải thích hơn.

### Cách B: tự phát hiện qua META-INF/spring.factories

Một thư viện hoặc ứng dụng có thể khai báo class initializer trong tài nguyên:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung (đúng key cho Spring Boot 3.3):

~~~properties
org.springframework.boot.BootstrapRegistryInitializer=com.example.early.DemoBootstrapRegistryInitializer
~~~

Lớp được nêu phải có tên package chính xác, implementation có thể được tạo qua cơ chế Spring factories; ví dụ này sử dụng constructor không đối số. Khi chọn **cách B**, bỏ lời gọi `addBootstrapRegistryInitializer(new DemoBootstrapRegistryInitializer())` trong `main` để không cố ý đăng ký cùng initializer hai lần.

**Không đặt class initializer vào `AutoConfiguration.imports`:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` dành cho auto-configuration, không thay cho key `BootstrapRegistryInitializer` trong `spring.factories`. Cũng không trông đợi `@Component` scan là đủ, vì bean scanning diễn ra muộn hơn thời điểm cần initializer.

Khi nhiều JAR đóng góp `spring.factories`, Spring Boot có thể tải nhiều initializer. Không thiết kế logic dựa trên thứ tự ngẫu nhiên; dùng `registerIfAbsent` khi cung cấp mặc định và xác định rõ chính sách khi nhiều thư viện muốn cùng một type.

## 6. Ví dụ chạy được: chuyển một đối tượng từ bootstrap sang Spring context

Ta xây một ứng dụng **console** dùng Java 17+ và Spring Boot 3.3.13. Ví dụ không gọi mạng hoặc kết nối DB, nên có thể quan sát vòng đời một cách rõ ràng.

Điểm chính:

- `DemoBootstrapRegistryInitializer` đăng ký supplier của `EarlyClient`.
- Listener yêu cầu `EarlyClient` từ bootstrap context khi context chính đã được chuẩn bị.
- Listener đưa một **bean definition với supplier trả lại cùng instance** vào `GenericApplicationContext` chuẩn của ví dụ.
- `ApplicationRunner` nhận `EarlyClient` bằng dependency injection như bean thông thường.
- `@PreDestroy` của `EarlyClient` chạy khi context chính đóng bình thường.

### 6.1. Cấu trúc project

~~~text
bootstrap-registry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/early/
    ├── BootstrapRegistryDemoApplication.java
    ├── DemoBootstrapRegistryInitializer.java
    └── EarlyClient.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'bootstrap-registry-demo'
~~~

**`build.gradle`:**

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
    mainClass = 'com.example.early.BootstrapRegistryDemoApplication'
}
~~~

Chỉ dùng `spring-boot-starter`, vì ví dụ này không cần HTTP server. Các tệp nằm trong cùng package `com.example.early`.

### 6.2. Đối tượng cần chia sẻ: EarlyClient

**`src/main/java/com/example/early/EarlyClient.java`:**

~~~java
package com.example.early;

import jakarta.annotation.PreDestroy;

public final class EarlyClient {

    private final String identity;

    public EarlyClient(String identity) {
        this.identity = identity;
        System.out.println("EARLY_CLIENT: constructed");
    }

    public String greet() {
        return "hello:" + identity;
    }

    @PreDestroy
    public void destroy() {
        System.out.println("EARLY_CLIENT: destroyed");
    }
}
~~~

`EarlyClient` là POJO không có `@Component`. Bootstrap registry sẽ đăng ký supplier của nó; một listener sau đó đăng ký bean definition trong context chính. Điều này cho phép giải thích vì sao instance không tự trở thành bean chỉ nhờ `registry.registerIfAbsent`.

Ví dụ sử dụng chuỗi `identity` không nhạy cảm. Với client thực tế có secret hoặc token, tránh in thông tin bí mật ra log.

### 6.3. Initializer và close listener

**`src/main/java/com/example/early/DemoBootstrapRegistryInitializer.java`:**

~~~java
package com.example.early;

import org.springframework.boot.BootstrapRegistry;
import org.springframework.boot.BootstrapRegistryInitializer;
import org.springframework.context.support.GenericApplicationContext;

public final class DemoBootstrapRegistryInitializer
        implements BootstrapRegistryInitializer {

    @Override
    public void initialize(BootstrapRegistry registry) {

        System.out.println("BOOTSTRAP: initializer registered");

        // Đăng ký supplier. Chưa tạo EarlyClient ở dòng này.
        registry.registerIfAbsent(
                EarlyClient.class,
                ignored -> new EarlyClient("config-client-demo"));

        // Chuyển một instance bootstrap sang bean definition của Spring.
        registry.addCloseListener(event -> {
            EarlyClient client =
                    event.getBootstrapContext().get(EarlyClient.class);

            if (!(event.getApplicationContext()
                    instanceof GenericApplicationContext context)) {
                throw new IllegalStateException(
                        "Expected GenericApplicationContext in this demo");
            }

            context.registerBean(
                    "earlyClient",
                    EarlyClient.class,
                    () -> client);

            System.out.println("BOOTSTRAP: bean definition registered");
        });
    }
}
~~~

Giải thích các dòng quan trọng:

1. `initialize(...)` chạy sớm và có một `BootstrapRegistry`, **chưa** nhận đối tượng `ApplicationContext` chính.
2. `registerIfAbsent(EarlyClient.class, ignored -> ...)` chỉ đăng ký factory cho type; constructor chưa chạy.
3. `addCloseListener(...)` lên lịch callback tại điểm bootstrap context đóng. Khi callback gọi `get(EarlyClient.class)`, supplier tạo instance nếu chưa tồn tại.
4. `event.getApplicationContext()` cung cấp context đã chuẩn bị. Vì demo non-web mặc định dùng context dựa trên `GenericApplicationContext`, ta có thể dùng `registerBean(...)` để đăng ký **bean definition** với supplier trả lại instance bootstrap.
5. Đến pha refresh, Spring tạo/initialize bean qua definition đó. Với đối tượng được quản lý và lifecycle processing phù hợp, `@PreDestroy` được xử lý khi context chính đóng bình thường.

**Giới hạn quan trọng:** Đoạn chuyển giao này dựa vào khả năng `registerBean(...)` của `GenericApplicationContext`. Nếu ứng dụng sử dụng một implementation context khác, hãy dùng API đăng ký tương thích với implementation đó hoặc thiết kế integration tương ứng; đừng ép cast không kiểm tra.

Không thay `registerBean(...)` bằng `getBeanFactory().registerSingleton(...)` một cách máy móc. `registerSingleton(...)` đưa một object có sẵn vào singleton registry nhưng **không thực hiện toàn bộ các bước initialization và destruction bean definition thông thường**. Nó có thể hữu ích ở điểm mở rộng nhất định nhưng nếu mong chờ `@PostConstruct`, `@PreDestroy` hay mọi BeanPostProcessor tự chạy, cần chọn hợp đồng phù hợp.

### 6.4. Lớp ứng dụng và ApplicationRunner

**`src/main/java/com/example/early/BootstrapRegistryDemoApplication.java`:**

~~~java
package com.example.early;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootstrapRegistryDemoApplication {

    public static void main(String[] args) {

        SpringApplication application =
                new SpringApplication(BootstrapRegistryDemoApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        // Phải thêm initializer trước run.
        application.addBootstrapRegistryInitializer(
                new DemoBootstrapRegistryInitializer());

        try (ConfigurableApplicationContext context =
                     application.run(args)) {

            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner printFromBean(EarlyClient client) {
        return args ->
                System.out.println("RUNNER: " + client.greet());
    }
}
~~~

`ApplicationRunner` được Spring Boot gọi **sau khi refresh context thành công**. Nếu listener không đăng ký bean definition, việc inject `EarlyClient` vào runner sẽ thất bại vì class không được đánh dấu `@Component` và không có `@Bean` khác.

Đối tượng `SpringApplication` đăng ký initializer qua code. Vì vậy **không cần** tạo `spring.factories` cho phiên bản chạy của mục này. `WebApplicationType.NONE` giúp chương trình không chạy HTTP server và chủ động đóng context sau khi runner hoàn tất.

### 6.5. Lệnh chạy

Từ thư mục `bootstrap-registry-demo`, chạy với Gradle tương thích:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows. Dự án mẫu không tự chứa wrapper; cần có Gradle đã cài hoặc tự tạo wrapper.

Bỏ qua các dòng log/framework/build có thể khác nhau, **những dòng do mã ứng dụng tự in** được mong đợi theo thứ tự:

~~~text
BOOTSTRAP: initializer registered
EARLY_CLIENT: constructed
BOOTSTRAP: bean definition registered
RUNNER: hello:config-client-demo
MAIN: run returned
EARLY_CLIENT: destroyed
MAIN: context closed
~~~

Vì sao thứ tự này có ý nghĩa?

- `BOOTSTRAP: initializer registered` xuất hiện khi registry được cấu hình.
- `EARLY_CLIENT: constructed` xuất hiện **sau** đăng ký supplier, khi close listener lấy client.
- `BOOTSTRAP: bean definition registered` có nghĩa context chính đã nhận một cách tạo bean dùng cùng instance.
- `RUNNER` chỉ chạy sau khi application context được refresh.
- `MAIN: run returned` chứng minh `SpringApplication.run` đã đi qua startup runners.
- `EARLY_CLIENT: destroyed` và `MAIN: context closed` thuộc **lúc ứng dụng đóng**, muộn hơn sự kiện đóng bootstrap context.

Một instance được tạo trong bootstrap và tiếp tục dùng trong runtime là hợp lý **chỉ khi** tài nguyên đó được thiết kế cho cả hai giai đoạn. Không chuyển bừa những object chỉ dùng ngắn hạn hoặc chứa trạng thái bootstrap không còn hợp lệ sang bean runtime.

### 6.6. Thử chế độ spring.factories

Để thử **cách B**, thêm:

~~~text
src/main/resources/META-INF/spring.factories
~~~

với nội dung:

~~~properties
org.springframework.boot.BootstrapRegistryInitializer=com.example.early.DemoBootstrapRegistryInitializer
~~~

Sau đó sửa `main` để bỏ đúng hai dòng đăng ký programmatic:

~~~java
application.addBootstrapRegistryInitializer(
        new DemoBootstrapRegistryInitializer());
~~~

Đây là **phần mã cần xóa khi chuyển sang spring.factories**, không phải file thứ tư phải chạy. Chạy lại `gradle bootRun` và kiểm tra initializer vẫn được gọi nhờ metadata. Hãy giữ đúng **một đường đăng ký** cho demo để output có thể dự đoán.

## 7. Đọc thực tế trong pha Config Data

Trong ví dụ demo, close listener là nơi gọi `get(EarlyClient.class)` để quan sát lazy creation. Một use case thực tế thường là **Config Data loader** yêu cầu client ở pha sớm, trước khi application context được refresh.

Luồng khái niệm:

~~~text
BootstrapRegistryInitializer
    └─ registerIfAbsent(HttpClientType.class, supplier)
             │
             ▼
Config Data infrastructure
    └─ BootstrapContext.get(HttpClientType.class)
             └─ Supplier tạo client lần đầu nếu cần
             │
             ▼
Environment có thêm cấu hình được nạp
             │
             ▼
BootstrapContextClosedEvent
    └─ Có thể chuyển tài nguyên phù hợp sang application context
             │
             ▼
ApplicationContext.refresh() → beans → runners → ready
~~~

Spring Cloud Config là một ví dụ ứng dụng của ý tưởng này: tùy biến HTTP client để tải Config Data rất sớm. Tuy nhiên, tên class, integration hooks và cấu hình cụ thể phụ thuộc phiên bản Spring Cloud; không đưa các class Spring Cloud vào project chỉ có Spring Boot starter nếu chưa thêm dependencies tương ứng.

**Không giả định initializer đã có mọi property từ `application.yml`.** Config Data có thể đang được nạp sau khi bootstrap registry đã được dựng. Nếu supplier cần property, phải xác định nguồn nào đã có ở thời điểm thực thi và cơ chế API mà bên gọi cung cấp. Tránh truy cập một `Environment` toàn cục chưa sẵn sàng.

## 8. Quản lý lifecycle và cleanup

Cần phân biệt ba thời điểm dễ nhầm:

| Sự kiện | Ý nghĩa | Có tương đương shutdown ứng dụng? |
| --- | --- | --- |
| `BootstrapContextClosedEvent` | Bootstrap context tạm kết thúc; application context đã chuẩn bị. | **Không** |
| `ContextRefreshedEvent` | Application context đã hoàn tất refresh. | **Không** |
| `ContextClosedEvent` / destroy callbacks | Application context đang đóng và dọn bean. | **Có**, trong đường đóng bình thường |

Nếu bạn tạo một HTTP client, kết nối hoặc nguồn tài nguyên sớm:

1. Xác định **ai sở hữu** vòng đời client: bootstrap code hay Spring bean sau khi chuyển giao?
2. Nếu tài nguyên **chỉ dùng trong bootstrap**, hãy thiết kế cách giải phóng phù hợp khi bootstrap hoàn tất. Đừng kỳ vọng bootstrap context là Spring BeanFactory tự chạy hết `@PreDestroy` cho mọi đối tượng.
3. Nếu tài nguyên được **chuyển sang runtime**, tránh đóng nó trong bootstrap close listener khi application bean còn dùng. Cần đảm bảo lifecycle/callback của bean runtime được đăng ký thích hợp.
4. Nếu startup **thất bại giữa chừng**, không giả định mọi callback “thành công” đều chắc chắn được gọi. Tài nguyên tự mở phải có cơ chế cleanup/idempotency cho đường lỗi.
5. Với client thực tế, cấu hình timeout, giới hạn retry, bảo vệ secret và tránh thao tác network vô hạn trong initializer. Khởi động sớm là đoạn rất nhạy cảm với deadlock và độ trễ toàn ứng dụng.

Ví dụ học tập chuyển `EarlyClient` thành bean definition nên `@PreDestroy` được gọi khi context đóng thành công. Việc dùng một object do code tự tạo với supplier trong bean definition cần được kiểm tra tương thích với BeanPostProcessor của hệ thống thực tế, đặc biệt khi bean cần proxy/AOP hoặc lifecycle phức tạp.

## 9. Register, registerIfAbsent và cách xử lý xung đột

### registerIfAbsent: cung cấp mặc định

~~~java
registry.registerIfAbsent(
        EarlyClient.class,
        ignored -> new EarlyClient("default"));
~~~

Nếu đã có supplier cho `EarlyClient.class`, lời gọi này giữ đăng ký cũ. Phù hợp khi thư viện muốn cung cấp **fallback** cho ứng dụng.

### register: đăng ký tường minh

~~~java
registry.register(
        EarlyClient.class,
        ignored -> new EarlyClient("explicit"));
~~~

Theo Javadoc của Spring Boot 3.3, đăng ký có sẵn có thể bị thay thế khi instance tương ứng **chưa được lấy như một singleton**. Không xây dựng thiết kế phụ thuộc việc “thay thế chắc chắn luôn thắng”; sau khi instance đã tạo, quy tắc khác đi, và trình tự nhiều initializer có thể ảnh hưởng kết quả.

### Kiểm tra trước khi get

~~~java
if (bootstrapContext.isRegistered(EarlyClient.class)) {
    EarlyClient client = bootstrapContext.get(EarlyClient.class);
    // Sử dụng instance trong bước bootstrap hiện tại.
}
~~~

Đây là **đoạn minh họa một phần**, giả định bạn đang ở callback thực sự nhận `BootstrapContext`. Không gọi `get` cho type không được đăng ký rồi xem đó là cách kiểm tra tồn tại, vì API sẽ báo lỗi.

Với nhiều module hoặc thư viện chia sẻ registry, nên quy định type owner và ý nghĩa của instance, tránh hai thành phần độc lập cùng chiếm một key `Class` nhưng mong cấu hình khác nhau.

## 10. Các lỗi thường gặp

**Lỗi 1 — Đặt initializer thành @Component và chờ auto-scan chạy sớm**

~~~java
@Component
public class DemoBootstrapRegistryInitializer
        implements BootstrapRegistryInitializer {
    // ...
}
~~~

Đoạn trên chỉ mô tả một **lỗi thiết kế**, không phải phương án được khuyến nghị. Component scanning diễn ra trong startup application context, trong khi bootstrap initializer cần được biết **trước đó**. Hãy đăng ký bằng `addBootstrapRegistryInitializer` hoặc `META-INF/spring.factories`.

**Lỗi 2 — Nhầm SpringApplication.addInitializers với addBootstrapRegistryInitializer**

~~~java
application.addInitializers(context -> {
    // context là ConfigurableApplicationContext, không phải BootstrapRegistry.
});
~~~

`ApplicationContextInitializer` không nhận `BootstrapRegistry` và không tự thay thế chức năng của `BootstrapRegistryInitializer`. Chọn API đúng theo thời điểm và tham số callback.

**Lỗi 3 — Cho rằng register tạo đối tượng ngay**

~~~java
registry.registerIfAbsent(
        EarlyClient.class,
        context -> new EarlyClient("demo"));
~~~

Chỉ thêm supplier; muốn instance tồn tại sớm, một thành phần phải gọi `BootstrapContext.get(EarlyClient.class)` khi phù hợp. Bọc tạo client trong supplier giúp tránh chi phí khi không ai cần.

**Lỗi 4 — Lấy @Autowired bean từ bootstrap registry**

`BootstrapRegistry` không phải `ApplicationContext` và không thực hiện component scanning, bean injection, `@Qualifier`, bean post-processing như Spring BeanFactory. Nếu muốn truy cập một type, nó phải được đăng ký theo API bootstrap; không giả định bean application có mặt.

**Lỗi 5 — Truy cập application context như thể đã refresh trong close listener**

Sự kiện bootstrap close cung cấp **prepared application context**, nhưng không bảo đảm `@Bean` của ứng dụng đã được khởi tạo. Trong ví dụ, listener đăng ký bean definition để context xử lý ở refresh, không gọi controller/service thông qua `getBean(...)` khi chưa đúng mốc.

**Lỗi 6 — Nhầm bootstrap close với shutdown**

Không đóng client cần dùng trong runtime tại `BootstrapContextClosedEvent`. Đóng sai thời điểm có thể khiến bean nhận tài nguyên đã bị dispose.

**Lỗi 7 — Dùng registerSingleton và nghĩ @PreDestroy chắc chắn chạy**

`registerSingleton` không thay thế việc tạo/initialize bean qua definition có BeanPostProcessor. Nếu cần vòng đời thông thường, cân nhắc `GenericApplicationContext.registerBean` hoặc một cơ chế đăng ký bean definition được hỗ trợ. Luôn kiểm tra thực tế việc đóng tài nguyên.

**Lỗi 8 — Ghi đè type key không kiểm soát**

Registry key là `Class`, không có qualifier. `register(...)` khác `registerIfAbsent(...)`, và xung đột có thể khiến kết quả phụ thuộc thứ tự đăng ký. Tạo hợp đồng rõ ràng khi nhiều thư viện tích hợp.

**Lỗi 9 — Đọc bí mật rồi in log ở bootstrap**

Cấu hình sớm có thể chứa thông tin nhạy cảm. Đừng log token, password, URL có query secret, cấu hình xác thực hoặc exception chứa header. Dùng logging/diagnostics tối thiểu và bảo vệ dữ liệu ở mọi giai đoạn startup.

**Lỗi 10 — Nghĩ spring.factories đã bị AutoConfiguration.imports thay thế cho mọi loại extension**

Migration của auto-configuration không đồng nghĩa Spring Boot 3.3 bỏ cơ chế `spring.factories` cho `BootstrapRegistryInitializer`. Dùng đúng key của hook theo tài liệu phiên bản, không hoán đổi hai cơ chế.

## 11. Bài thực hành

1. Chạy project mục 6 và kiểm tra thứ tự `BOOTSTRAP`, `EARLY_CLIENT`, `RUNNER`, `MAIN`. Tại sao constructor chạy sau lời gọi `registerIfAbsent`?
2. Di chuyển lệnh `event.getBootstrapContext().get(EarlyClient.class)` ra khỏi listener và chỉ giữ đăng ký supplier. Một instance `EarlyClient` có tự được tạo để Runner inject không? Hãy xác định bước chuyển giao nào bị thiếu.
3. Thay programmatic registration bằng `spring.factories` đúng hướng dẫn. Xác minh initializer chạy một lần và output tương đương.
4. Thử `registry.registerIfAbsent` hai lần cho cùng `EarlyClient.class` với hai giá trị khác nhau; giải thích supplier nào được giữ khi chưa ai lấy instance.
5. Thêm một type `BootstrapOptions` và đăng ký supplier của `EarlyClient` dùng `context.get(BootstrapOptions.class)`. Cách này giống và khác dependency injection của application bean ở đâu?
6. Thử bỏ logic `registerBean(...)` trong close listener. Vì sao `ApplicationRunner` yêu cầu `EarlyClient` nhưng context không thể autowire type đó?
7. Nếu một bootstrap client phải dùng tiếp sau startup, bạn sẽ bảo đảm shutdown/cleanup, timeout và ownership như thế nào?
8. Vì sao gọi `application.addBootstrapRegistryInitializer(...)` **sau** `run(args)` không thể phục hồi các bước bootstrap đã qua?
9. Giải thích vì sao không thể dùng `@PostConstruct` trên một application bean để tùy biến quá trình nạp Config Data trước khi context tồn tại.
10. Hệ thống có hai thư viện cùng muốn đăng ký HTTP client theo một class key. Bạn sẽ xử lý type ownership hoặc fallback như thế nào để tránh ngẫu nhiên?

## Ghi nhớ

- `BootstrapRegistryInitializer` là callback **rất sớm**, nhận `BootstrapRegistry` trước khi các application bean thông thường sẵn sàng.
- `register` và `registerIfAbsent` nhận **supplier theo Class key**; việc đăng ký không nhất thiết tạo object ngay, còn `BootstrapContext.get` tạo/lấy singleton khi cần.
- `BootstrapContextClosedEvent` xảy ra **trong quá trình startup**, lúc application context đã được chuẩn bị; nó **khác** `ContextClosedEvent` khi ứng dụng tắt.
- Object bootstrap **không tự trở thành Spring bean**. Cần bridge tường minh, kèm ownership và lifecycle phù hợp.
- Có hai đường đăng ký initializer phổ biến ở Spring Boot 3.3: `SpringApplication.addBootstrapRegistryInitializer(...)` và `META-INF/spring.factories` với key `org.springframework.boot.BootstrapRegistryInitializer`.
- Chỉ sử dụng điểm mở rộng này khi thực sự có nhu cầu ở pha sớm. Đối với logic nghiệp vụ chạy sau startup, `@Bean`, `ApplicationRunner`, `ApplicationReadyEvent` hoặc hook bean lifecycle thường phù hợp hơn.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — BootstrapRegistryInitializer: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistryInitializer.html
- Spring Boot 3.3.13 — BootstrapRegistry: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistry.html
- Spring Boot 3.3.13 — BootstrapContext: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContext.html
- Spring Boot 3.3.13 — BootstrapContextClosedEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContextClosedEvent.html
- Spring Boot 3.3.13 — SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Cloud Config — Customizing a BootstrapRegistryInitializer for Config Data: https://docs.spring.io/spring-cloud-config/reference/client.html
