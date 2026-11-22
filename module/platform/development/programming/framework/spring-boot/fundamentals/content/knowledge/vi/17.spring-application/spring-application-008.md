# `SpringApplication` instance, setter và `SpringApplicationBuilder`

Trong ứng dụng Spring Boot đơn giản, bạn thường khởi động chương trình bằng một dòng:

```java
SpringApplication.run(DemoApplication.class, args);
```

Cách viết này thuận tiện vì Spring Boot tự tạo và cấu hình đối tượng `SpringApplication`, sau đó gọi `run()`. Nhưng khi cần kiểm soát quá trình khởi động — chẳng hạn chọn kiểu ứng dụng web, bật profile, đặt property mặc định, tắt banner, thêm initializer hoặc xây dựng nhiều application context — bạn có thể tạo **một instance `SpringApplication`**, cấu hình instance bằng các setter rồi gọi `run()`.

Khi cần cấu hình theo kiểu fluent API, hoặc tạo context theo mô hình cha-con, Spring Boot còn cung cấp **`SpringApplicationBuilder`**.

Bài học tập trung vào ba cách tiếp cận:

- Dùng static `SpringApplication.run(...)` cho ứng dụng đơn giản.
- Tạo và cấu hình một `SpringApplication` instance bằng constructor, setter và `run(...)`.
- Dùng `SpringApplicationBuilder` để nối các cấu hình theo fluent API và tổ chức context hierarchy.

## 1. `SpringApplication` đảm nhiệm điều gì?

`SpringApplication` là lớp trung tâm điều phối quá trình khởi động ứng dụng Spring Boot. Nó nhận các primary source (thường là lớp có `@SpringBootApplication`), chuẩn bị môi trường, tạo application context, áp dụng initializer và listener, tải cấu hình, refresh context, rồi gọi các startup runner phù hợp.

Có thể hình dung luồng tổng quát:

```text
SpringApplication
       |
       v
Chuẩn bị Environment và property sources
       |
       v
Tạo ApplicationContext phù hợp
       |
       v
Áp dụng ApplicationContextInitializer
       |
       v
Nạp primary sources và xử lý configuration
       |
       v
Refresh ApplicationContext
       |
       v
Khởi tạo các bean cần thiết
       |
       v
Gọi ApplicationRunner / CommandLineRunner
       |
       v
Ứng dụng sẵn sàng
```

Đây là sơ đồ khái niệm, lược bỏ nhiều sự kiện và bước nội bộ. Trình tự chi tiết phụ thuộc phiên bản Spring Boot và cấu hình ứng dụng.

### 1.1. Static `run()` là cách viết rút gọn

Ví dụ lớp khởi động:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Lời gọi static trên tạo và chạy một ứng dụng Spring Boot dựa trên source được cung cấp. Với dự án nhỏ, cách này dễ đọc và đủ dùng.

Khi cần điều chỉnh các thuộc tính trước khi khởi động, hãy tạo instance:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.run(args);
```

Hai cách đều đi tới quá trình khởi động Spring Boot. Khác biệt là cách thứ hai cho bạn một đối tượng có thể cấu hình trước khi gọi `run()`.

## 2. Tạo một `SpringApplication` instance

Constructor thường nhận một hoặc nhiều primary source:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);
```

Primary source thường là configuration class, ví dụ lớp mang `@SpringBootApplication`. Có thể truyền nhiều source nếu ứng dụng có nhiều lớp cấu hình gốc:

```java
SpringApplication application =
        new SpringApplication(
                DemoApplication.class,
                SharedConfiguration.class
        );
```

Các source sẽ được đưa vào quá trình xử lý cấu hình. Tuy nhiên, không nên thêm mọi configuration class một cách tùy tiện: hãy phân biệt primary source, component scan, `@Import` và auto-configuration.

### 2.1. Cấu hình trước khi gọi `run()`

Một ví dụ:

```java
package com.example.demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setBannerMode(Banner.Mode.OFF);
        application.setWebApplicationType(WebApplicationType.SERVLET);
        application.setAdditionalProfiles("dev");
        application.setLogStartupInfo(true);

        application.run(args);
    }
}
```

Các setter được gọi **trước** `run()`, vì chúng cấu hình cách SpringApplication chuẩn bị và khởi động context. Khi `run()` đã bắt đầu, không nên tiếp tục dùng setter như thể chúng sẽ cấu hình lại một context đang chạy.

### 2.2. `run()` trả về application context

Bạn có thể giữ context để truy cập bean hoặc đóng context trong một ứng dụng non-web:

```java
ConfigurableApplicationContext context =
        application.run(args);

GreetingService greetingService =
        context.getBean(GreetingService.class);

System.out.println(greetingService.greet("Lan"));
```

Trong ứng dụng web, context thường tiếp tục hoạt động cùng web server sau khi `run()` trả về. Với ứng dụng console không có server, luồng `main` có thể kết thúc sau khi thực hiện công việc. Khi cần chủ động đóng context, có thể gọi `context.close()` hoặc dùng try-with-resources với context phù hợp.

## 3. Các setter thường dùng của `SpringApplication`

`SpringApplication` cung cấp nhiều setter để điều chỉnh quá trình startup. Những setter dưới đây là các lựa chọn thường gặp; API cụ thể có thể bổ sung hoặc thay đổi theo phiên bản Spring Boot.

| Setter | Mục đích | Ví dụ |
| --- | --- | --- |
| `setBannerMode(...)` | Chọn cách hiển thị banner | `Banner.Mode.OFF` |
| `setBanner(...)` | Cung cấp banner tùy chỉnh | `application.setBanner(myBanner)` |
| `setWebApplicationType(...)` | Chọn loại application context web | `SERVLET`, `REACTIVE`, `NONE` |
| `setAdditionalProfiles(...)` | Thêm profile cho lần chạy | `"dev"` |
| `setDefaultProperties(...)` | Đặt property mặc định | `Map<String, Object>` |
| `setInitializers(...)` | Đăng ký context initializer | `ApplicationContextInitializer` |
| `addInitializers(...)` | Bổ sung initializer | `ApplicationContextInitializer` |
| `setListeners(...)` | Thiết lập application listeners | `ApplicationListener` |
| `addListeners(...)` | Bổ sung listener | `ApplicationListener` |
| `setHeadless(...)` | Thiết lập chế độ AWT headless | `true` |
| `setLogStartupInfo(...)` | Bật/tắt một số thông tin startup | `true` |
| `setRegisterShutdownHook(...)` | Đăng ký JVM shutdown hook để đóng context | `true` |
| `setLazyInitialization(...)` | Bật lazy initialization mặc định cho bean | `true` |
| `setApplicationStartup(...)` | Gắn công cụ ghi nhận startup steps | `BufferingApplicationStartup` |
| `setAddCommandLineProperties(...)` | Quyết định có thêm command-line args vào Environment hay không | `false` |

Không cần gọi tất cả setter trong mọi ứng dụng. Chỉ cấu hình những giá trị có mục đích rõ ràng.

## 4. Chọn loại ứng dụng bằng `setWebApplicationType`

Spring Boot có thể xác định kiểu ứng dụng dựa trên classpath, nhưng bạn cũng có thể chỉ định rõ:

```java
application.setWebApplicationType(WebApplicationType.SERVLET);
```

Ba giá trị thường gặp:

| Giá trị | Ý nghĩa |
| --- | --- |
| `WebApplicationType.SERVLET` | Ứng dụng web dựa trên Servlet API, thường dùng Spring MVC |
| `WebApplicationType.REACTIVE` | Ứng dụng web reactive, thường dùng Spring WebFlux |
| `WebApplicationType.NONE` | Không khởi tạo web application context |

### 4.1. Ứng dụng servlet

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setWebApplicationType(WebApplicationType.SERVLET);
application.run(args);
```

Đây là lựa chọn phổ biến cho REST API sử dụng Spring MVC với servlet container nhúng.

### 4.2. Ứng dụng reactive

```java
application.setWebApplicationType(WebApplicationType.REACTIVE);
```

Dùng khi ứng dụng được thiết kế theo reactive web stack, ví dụ Spring WebFlux. Chỉ đổi enum không tự chuyển controller blocking thành reactive; dependency và code ứng dụng vẫn phải phù hợp với WebFlux.

### 4.3. Ứng dụng non-web

```java
application.setWebApplicationType(WebApplicationType.NONE);
```

Ứng dụng non-web phù hợp với command-line task, batch job hoặc chương trình nền không cần embedded HTTP server. Nếu code vẫn yêu cầu bean web cụ thể, việc chọn `NONE` có thể khiến dependency không được cấu hình và startup thất bại.

### 4.4. Vì sao không nên đổi loại ứng dụng tùy tiện?

Kiểu application context ảnh hưởng đến những auto-configuration nào được áp dụng, loại web server nào được tạo và các bean hạ tầng có mặt. Nếu dự án dùng Spring MVC, chuyển sang `REACTIVE` mà không thay dependency và kiến trúc có thể tạo context không đúng mong đợi.

Hãy chọn loại ứng dụng dựa trên web stack thực tế của dự án. Khi không có lý do đặc biệt, để Spring Boot suy luận từ classpath là lựa chọn đơn giản.

## 5. Banner và thông tin startup

### 5.1. Tắt banner

```java
application.setBannerMode(Banner.Mode.OFF);
```

Các chế độ:

| Giá trị | Hành vi |
| --- | --- |
| `Banner.Mode.CONSOLE` | In banner ra console |
| `Banner.Mode.LOG` | Ghi banner qua logger |
| `Banner.Mode.OFF` | Không hiển thị banner |

Tắt banner thường hữu ích trong môi trường CI hoặc khi muốn log ngắn gọn.

### 5.2. Banner tùy chỉnh

Có thể cung cấp implementation `Banner`:

```java
import java.io.PrintStream;
import org.springframework.boot.Banner;
import org.springframework.core.env.Environment;

public class CompanyBanner implements Banner {

    @Override
    public void printBanner(
            Environment environment,
            Class<?> sourceClass,
            PrintStream out) {
        out.println("=== SHOP APPLICATION ===");
        out.println("Starting: " + sourceClass.getSimpleName());
    }
}
```

Đăng ký:

```java
application.setBanner(new CompanyBanner());
application.setBannerMode(Banner.Mode.CONSOLE);
```

Banner chỉ phục vụ hiển thị khi startup. Nó không phải application listener hay thành phần cấu hình bean.

### 5.3. Bật/tắt thông tin startup

```java
application.setLogStartupInfo(false);
```

Setter này điều chỉnh một số thông tin startup do Spring Boot ghi log. Nó không tắt toàn bộ logging của ứng dụng và không thay thế cấu hình logging trong `application.properties`.

## 6. Profile và property mặc định

### 6.1. Thêm profile bằng `setAdditionalProfiles`

```java
application.setAdditionalProfiles("dev");
```

Profile `dev` được bổ sung vào môi trường khi ứng dụng khởi động. Spring Boot có thể nạp thêm `application-dev.properties` hoặc `application-dev.yml` nếu file tương ứng tồn tại.

Ví dụ:

```text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
```

`application-dev.properties`:

```properties
server.port=8081
logging.level.com.example.demo=DEBUG
```

Nếu profile được bổ sung bằng setter, không cần hard-code `spring.profiles.active=dev` trong file cấu hình chung.

**Lưu ý:** `setAdditionalProfiles` thêm profile vào môi trường của lần chạy. Nó không phải API để gỡ profile đang active hoặc bảo đảm chỉ có duy nhất profile đó. Nếu ứng dụng nhận thêm profile qua biến môi trường hoặc command line, hãy kiểm tra tập profile thực tế.

### 6.2. Đặt property mặc định

```java
Map<String, Object> defaults = new HashMap<>();
defaults.put("server.port", 8081);
defaults.put("features.reports.enabled", false);

application.setDefaultProperties(defaults);
```

Default properties hữu ích để cung cấp giá trị fallback cho ứng dụng. Chúng thường có độ ưu tiên thấp hơn các property source khác như cấu hình file, biến môi trường hoặc command-line arguments. Vì vậy, giá trị mặc định có thể bị ghi đè bởi cấu hình cụ thể của môi trường.

Ví dụ, nếu default là `server.port=8081` nhưng command line truyền `--server.port=9090`, giá trị command line có độ ưu tiên cao hơn theo thứ tự property source chuẩn.

### 6.3. Phân biệt default properties và application properties

| Nguồn | Vai trò |
| --- | --- |
| `setDefaultProperties(...)` | Giá trị dự phòng do code khởi động cung cấp |
| `application.properties` | Cấu hình ứng dụng theo môi trường/profile |
| Environment variables | Cấu hình từ môi trường triển khai |
| Command-line arguments | Cấu hình truyền vào tiến trình khi chạy |

Không nên đặt password, API key hoặc secret trực tiếp trong default properties của source code. Hãy lấy bí mật từ secret manager hoặc môi trường triển khai phù hợp.

### 6.4. Ví dụ kết hợp profile và default properties

```java
Map<String, Object> defaults = Map.of(
        "server.port", 8080,
        "features.audit.enabled", false
);

SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setDefaultProperties(defaults);
application.setAdditionalProfiles("dev");
application.run(args);
```

Ứng dụng có giá trị dự phòng cho cổng và audit. Cấu hình `application-dev.properties`, biến môi trường hoặc command line có thể ghi đè giá trị mặc định theo precedence của Spring Boot.

## 7. Initializer và listener

`SpringApplication` cho phép thêm những callback ở các giai đoạn khác nhau của startup. Hai loại thường gặp là `ApplicationContextInitializer` và `ApplicationListener`.

### 7.1. `ApplicationContextInitializer`

Initializer được gọi trên application context trước khi context được refresh. Nó phù hợp để tùy chỉnh context hoặc environment ở giai đoạn chuẩn bị.

Ví dụ:

```java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class StartupContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context) {
        System.out.println("ApplicationContext is being prepared");
    }
}
```

Đăng ký:

```java
application.addInitializers(new StartupContextInitializer());
```

Initializer không nên được dùng như nơi khởi tạo service nghiệp vụ bằng tay. Nó phục vụ tùy chỉnh context trước refresh; bean vẫn nên được tạo và inject qua container.

### 7.2. `ApplicationListener`

Listener nhận các application event trong quá trình startup và runtime.

Ví dụ:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
```

Đăng ký:

```java
application.addListeners(new ReadyListener());
```

Listener nhận event tương ứng khi Spring Boot phát event đó. `ApplicationReadyEvent` được phát sau khi ứng dụng đã sẵn sàng, bao gồm giai đoạn thực thi runner theo quy trình startup của Spring Boot.

### 7.3. Một số event startup thường gặp

| Event | Thời điểm khái quát |
| --- | --- |
| `ApplicationStartingEvent` | Khi quá trình startup bắt đầu, trước khi Environment và context được chuẩn bị đầy đủ |
| `ApplicationEnvironmentPreparedEvent` | Khi Environment đã được chuẩn bị |
| `ApplicationContextInitializedEvent` | Khi context đã được tạo và initializer đã chạy |
| `ApplicationPreparedEvent` | Khi context đã được chuẩn bị, trước refresh |
| `ContextRefreshedEvent` | Khi application context được refresh |
| `ApplicationStartedEvent` | Sau khi context refresh và trước khi runner được gọi |
| `ApplicationReadyEvent` | Sau khi runner hoàn tất, ứng dụng sẵn sàng nhận traffic theo quy trình startup |
| `ApplicationFailedEvent` | Khi startup thất bại |

Tên event và chi tiết thời điểm có thể thay đổi theo thế hệ Spring Boot; hãy tham khảo API của phiên bản dự án.

### 7.4. Thêm nhiều initializer/listener

```java
application.addInitializers(
        new StartupContextInitializer(),
        new AnotherContextInitializer()
);

application.addListeners(
        new ReadyListener(),
        new StartupMetricsListener()
);
```

Nếu dùng `setInitializers(...)` hoặc `setListeners(...)`, bạn đang thiết lập danh sách theo setter đó. Nếu cần bổ sung mà vẫn giữ những phần đã cấu hình, `addInitializers(...)` và `addListeners(...)` thể hiện ý định rõ hơn.

## 8. Lazy initialization và startup tracking

### 8.1. Bật lazy initialization mặc định

```java
application.setLazyInitialization(true);
```

Lazy initialization khiến các bean được đánh dấu phù hợp trì hoãn khởi tạo cho đến khi cần. Điều này có thể rút ngắn thời gian startup, nhưng lỗi tạo bean có thể xuất hiện muộn hơn, khi bean lần đầu được sử dụng.

Ví dụ:

```java
@Service
@Lazy
public class ExpensiveReportService {
    public ExpensiveReportService() {
        System.out.println("Creating report service");
    }
}
```

Nếu một singleton non-lazy inject trực tiếp `ExpensiveReportService`, dependency vẫn cần được tạo để hoàn thành singleton đó. Lazy initialization không trì hoãn bean nếu có dependency bắt buộc khiến bean được yêu cầu sớm.

Chỉ bật lazy initialization khi hiểu tác động tới thời điểm phát hiện lỗi và cách ứng dụng sử dụng bean.

### 8.2. Theo dõi startup bằng `ApplicationStartup`

Spring Boot hỗ trợ gắn `ApplicationStartup` để ghi nhận các bước startup. Ví dụ dùng `BufferingApplicationStartup`:

```java
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setApplicationStartup(
        new BufferingApplicationStartup(2048)
);

application.run(args);
```

`BufferingApplicationStartup` ghi nhận các startup step vào bộ đệm có giới hạn. Nó hữu ích khi phân tích thời gian khởi động và tìm bước tốn thời gian. Cách đọc hoặc expose dữ liệu startup phụ thuộc công cụ quan sát và cấu hình ứng dụng.

## 9. Command-line properties và cấu hình Environment

Mặc định, Spring Boot có thể thêm command-line arguments dạng `--key=value` vào Environment:

```bash
java -jar app.jar --server.port=8085 --features.audit.enabled=true
```

Nếu cần tắt việc thêm command-line arguments thành property source:

```java
application.setAddCommandLineProperties(false);
```

Điều này không có nghĩa các đối số không còn được truyền vào `main` hoặc runner. Nó chỉ thay đổi việc Spring Boot có dùng các đối số dạng property để cấu hình Environment hay không.

Thông thường nên giữ mặc định để tiện cấu hình theo môi trường. Chỉ tắt khi có lý do rõ ràng, ví dụ ứng dụng cần tự xử lý command-line arguments và không muốn chúng ghi đè property source.

## 10. `SpringApplicationBuilder` là gì?

`SpringApplicationBuilder` cung cấp fluent API để cấu hình và xây dựng `SpringApplication`. Thay vì tạo instance rồi gọi nhiều setter, bạn có thể nối các lời gọi:

```java
new SpringApplicationBuilder(DemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .web(WebApplicationType.SERVLET)
        .profiles("dev")
        .properties("server.port=8081")
        .run(args);
```

Builder thường giúp:

- Viết cấu hình startup theo chuỗi dễ đọc.
- Thiết lập profile và property.
- Chọn web application type.
- Thêm initializer và listener.
- Xây dựng application context hierarchy.

`SpringApplicationBuilder` không thay thế IoC container; nó là cách cấu hình và điều phối việc tạo/chạy `SpringApplication`.

### 10.1. Ví dụ builder cơ bản

```java
package com.example.demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplicationBuilder;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(DemoApplication.class)
                .bannerMode(Banner.Mode.OFF)
                .web(WebApplicationType.SERVLET)
                .profiles("dev")
                .properties(
                        "server.port=8081",
                        "features.audit.enabled=false"
                )
                .run(args);
    }
}
```

Builder trả về builder sau nhiều phương thức cấu hình, cho phép nối lời gọi. `run(args)` thực hiện startup và trả về application context.

### 10.2. Các phương thức builder thường gặp

| Phương thức | Công dụng |
| --- | --- |
| `sources(...)` | Thiết lập source classes cho ứng dụng |
| `profiles(...)` | Thêm profile |
| `properties(...)` | Cung cấp property cho lần chạy |
| `web(...)` | Chọn `WebApplicationType` |
| `banner(...)` / `bannerMode(...)` | Cấu hình banner |
| `initializers(...)` | Thêm application context initializer |
| `listeners(...)` | Thêm application listener |
| `headless(...)` | Thiết lập headless mode |
| `logStartupInfo(...)` | Điều chỉnh thông tin startup |
| `registerShutdownHook(...)` | Bật/tắt shutdown hook |
| `lazyInitialization(...)` | Điều chỉnh lazy initialization |
| `parent(...)` | Khai báo cấu hình cho parent context |
| `child(...)` | Tạo child context |
| `sibling(...)` | Tạo context cùng cấp với context hiện tại trong hierarchy |
| `run(...)` | Khởi động ứng dụng và trả về context |

Tên và overload cụ thể cần đối chiếu với phiên bản Spring Boot. Không phải mọi setter của `SpringApplication` đều có tên hoặc cách gọi tương ứng hoàn toàn trên builder.

## 11. Khi nào nên dùng instance setter, khi nào dùng builder?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Ứng dụng đơn giản, không cần tùy chỉnh startup | `SpringApplication.run(...)` |
| Cần một vài setter và muốn thấy từng bước rõ ràng | `new SpringApplication(...)` |
| Cần cấu hình startup theo chuỗi fluent | `SpringApplicationBuilder` |
| Cần nhiều context cha-con | `SpringApplicationBuilder` |
| Cần thao tác sâu với instance `SpringApplication` | Tạo instance trực tiếp |

Hai cách tạo instance và builder đều có thể đáp ứng nhiều nhu cầu tương tự. Hãy chọn cách làm cho cấu hình startup dễ đọc và dễ kiểm soát nhất.

## 12. Context hierarchy với `SpringApplicationBuilder`

Một tính năng nổi bật của builder là tạo **parent-child application contexts**. Đây là mô hình hữu ích khi ứng dụng có một phần cấu hình chung và nhiều phần web hoặc module riêng.

Ví dụ:

```text
Parent ApplicationContext
    ├── Shared services
    ├── Common configuration
    └── Shared infrastructure
           |
           +---------------------+
           |                     |
           v                     v
     Child context A        Child context B
     (Web/API A)            (Web/API B)
```

Quy tắc cơ bản:

- Child context có thể tra cứu bean từ parent context.
- Parent context không nhìn thấy bean chỉ tồn tại trong child.
- Hai context có registry riêng; cùng tên bean ở child có thể che bean cùng tên ở parent khi tra cứu từ child.
- Mỗi context có lifecycle riêng và cần được đóng phù hợp.

### 12.1. Tạo parent và child

Ví dụ:

```java
import org.springframework.boot.SpringApplicationBuilder;
import org.springframework.boot.WebApplicationType;

new SpringApplicationBuilder()
        .parent(SharedConfiguration.class)
        .web(WebApplicationType.NONE)
        .child(ApiApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
```

Trong ví dụ, parent context chứa cấu hình chung, còn child context chứa ứng dụng API. Cách tổ chức cụ thể cần được thiết kế cẩn thận để component scan không vô tình đăng ký cùng một component ở nhiều context.

### 12.2. Parent cung cấp bean dùng chung

```java
@Configuration
public class SharedConfiguration {

    @Bean
    public Clock sharedClock() {
        return Clock.systemUTC();
    }
}
```

Child có thể inject bean `Clock` từ parent:

```java
@RestController
public class TimeController {
    private final Clock clock;

    public TimeController(Clock clock) {
        this.clock = clock;
    }
}
```

Nếu child context không có bean `Clock` riêng phù hợp, nó có thể tìm thấy bean từ parent context. Đây là một cách chia sẻ hạ tầng chung.

### 12.3. Child có thể định nghĩa bean riêng cùng tên

Giả sử parent có bean `clock` và child cũng đăng ký bean `clock`. Child context có thể dùng bean của chính nó khi lookup trong child; bean ở parent vẫn tồn tại trong context cha.

Đây là quan hệ che khuất khi tra cứu giữa các context, không phải bean definition overriding trong cùng một registry.

### 12.4. Không nên tạo hierarchy khi không có nhu cầu

Context hierarchy làm tăng độ phức tạp:

- Phải hiểu bean visibility giữa parent và child.
- Cần kiểm soát component scan và auto-configuration trong từng context.
- Cần quản lý lifecycle của từng context.
- Có thể xuất hiện bean trùng tên hoặc cấu hình bị áp dụng nhiều lần.
- Việc debug dependency injection trở nên khó hơn.

Ứng dụng Spring Boot thông thường chỉ cần một application context. Dùng hierarchy khi thực sự có ranh giới module hoặc nhiều ứng dụng con cần chia sẻ hạ tầng.

## 13. Sibling context và nhiều ứng dụng con

`SpringApplicationBuilder` còn có thể tạo các context cùng cấp (sibling) có chung parent.

Mô hình:

```text
              Parent context
             /              \
            /                \
           v                  v
      Sibling A           Sibling B
      API module          Admin module
```

Ví dụ khái niệm:

```java
new SpringApplicationBuilder()
        .parent(SharedConfiguration.class)
        .web(WebApplicationType.NONE)
        .child(ApiApplication.class)
        .web(WebApplicationType.SERVLET)
        .sibling(AdminApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
```

`sibling(...)` tạo context cùng cấp với context con hiện tại theo cấu trúc builder. Hãy xem tài liệu phiên bản đang dùng để xác định cách builder mang theo cấu hình chung và cách quản lý các context được tạo.

Không nên giả định các sibling nhìn thấy bean của nhau. Chúng chia sẻ parent, còn bean được định nghĩa riêng trong một sibling không tự động trở thành bean của sibling khác.

## 14. Quản lý shutdown và lifecycle

### 14.1. Shutdown hook

Spring Boot thường đăng ký shutdown hook để đóng application context khi JVM kết thúc theo cách phù hợp.

Có thể cấu hình:

```java
application.setRegisterShutdownHook(true);
```

Hoặc với builder:

```java
new SpringApplicationBuilder(DemoApplication.class)
        .registerShutdownHook(true)
        .run(args);
```

Khi context đóng, Spring gọi các callback hủy phù hợp như `@PreDestroy`, `DisposableBean` hoặc destroy method đã khai báo cho bean singleton.

Nếu ứng dụng được quản lý bởi môi trường đặc biệt, container khác hoặc một lifecycle coordinator riêng, cần quyết định ai chịu trách nhiệm đóng context để tránh đóng hai lần hoặc không đóng.

### 14.2. Đóng context thủ công

```java
ConfigurableApplicationContext context =
        new SpringApplication(DemoApplication.class).run(args);

try {
    // Thực hiện công việc của ứng dụng console
} finally {
    context.close();
}
```

Trong ứng dụng web dài hạn, không đóng context ngay sau `run()` nếu muốn web server tiếp tục phục vụ request. Ví dụ trên phù hợp với chương trình console hoặc một workflow có thời điểm kết thúc rõ ràng.

### 14.3. Parent-child lifecycle

Khi dùng builder tạo hierarchy, hãy quản lý context gốc và các context con. Đóng context cha có thể ảnh hưởng các context con theo quan hệ lifecycle; cách đóng và thứ tự đóng nên theo API/context hierarchy thực tế của ứng dụng. Không giữ context sống vô thời hạn nếu ứng dụng đã kết thúc.

## 15. Những lỗi thường gặp

### 15.1. Cấu hình setter sau khi đã gọi `run()`

Ví dụ không đúng mục đích:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.run(args);
application.setAdditionalProfiles("dev");
```

Setter được gọi sau khi startup đã diễn ra không thể được kỳ vọng thay đổi profile của context đã tạo. Hãy cấu hình trước `run()`.

### 15.2. Nhầm `setDefaultProperties` với property bắt buộc

Default properties có độ ưu tiên thấp. Nếu muốn cấu hình môi trường cụ thể, hãy đặt property ở nguồn thích hợp và kiểm tra precedence. Đừng dùng default properties như cách ép một giá trị không thể bị ghi đè.

### 15.3. Chọn sai web application type

Nếu ứng dụng dùng Spring MVC nhưng đặt `WebApplicationType.NONE`, web server không được tạo theo kiểu servlet. Nếu ứng dụng dùng WebFlux nhưng ép servlet, cấu hình runtime có thể không như mong đợi.

Chỉ chọn thủ công khi bạn hiểu dependency và loại application context cần dùng.

### 15.4. Dùng `@Order` để điều khiển khởi tạo bean

`@Order` phục vụ sắp xếp tại những extension point có hỗ trợ, chẳng hạn list injection hoặc startup runner. Nó không đảm bảo thứ tự constructor hoặc `@PostConstruct` của mọi singleton.

Nếu bean B cần bean A, hãy dùng constructor injection. Nếu chỉ cần A được khởi tạo trước vì side effect, cân nhắc `@DependsOn`.

### 15.5. Dùng hierarchy khiến component được đăng ký lặp

Nếu parent và child cùng component scan một package, một số component có thể được đăng ký trong cả hai context. Điều này làm xuất hiện hai instance hoặc hai bean cùng tên ở hai cấp.

Hãy phân chia package/configuration rõ ràng:

- Parent chứa shared configuration và bean dùng chung.
- Child chỉ scan module của nó.
- Không để cả parent và child cùng quét toàn bộ package ứng dụng nếu không có chủ đích.

### 15.6. Gọi `getBean()` quá sớm trong initializer

`ApplicationContextInitializer` chạy trước khi context được refresh hoàn chỉnh. Không nên giả định tất cả bean nghiệp vụ đã sẵn sàng trong initializer. Dùng initializer để tùy chỉnh environment/context; dùng bean lifecycle, event hoặc runner cho công việc phù hợp giai đoạn sau.

## 16. So sánh ba cách khởi động

| Tiêu chí | Static `run()` | `SpringApplication` instance | `SpringApplicationBuilder` |
| --- | --- | --- | --- |
| Cú pháp | Ngắn nhất | Tạo object rồi gọi setter | Fluent chain |
| Tùy chỉnh startup | Hạn chế trước khi gọi | Nhiều setter trực tiếp | Các phương thức builder tương ứng |
| Dễ debug cấu hình | Phù hợp khi ít tùy chỉnh | Rõ từng bước | Dễ đọc khi cấu hình chuỗi |
| Context hierarchy | Không phải mục đích chính | Có thể xây dựng thủ công phức tạp hơn | Hỗ trợ parent/child/sibling |
| Dùng khi | Ứng dụng thông thường | Cần điều khiển instance | Cần cấu hình linh hoạt hoặc nhiều context |

Ví dụ:

**Cách ngắn:**

```java
SpringApplication.run(DemoApplication.class, args);
```

**Cách instance:**

```java
SpringApplication app =
        new SpringApplication(DemoApplication.class);
app.setBannerMode(Banner.Mode.OFF);
app.setAdditionalProfiles("dev");
app.run(args);
```

**Cách builder:**

```java
new SpringApplicationBuilder(DemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .profiles("dev")
        .run(args);
```

## 17. Bài thực hành

### Bài 1 — Chuyển từ static run sang instance

Tạo một ứng dụng Spring Boot đơn giản đang dùng:

```java
SpringApplication.run(DemoApplication.class, args);
```

Chuyển sang:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);
application.run(args);
```

Quan sát log startup và endpoint. Giải thích vì sao hai cách khởi động có cùng hành vi cơ bản.

### Bài 2 — Tắt banner và thay web type

Tạo `SpringApplication` instance, tắt banner và chỉ định `WebApplicationType.SERVLET`. Khởi động ứng dụng web và xác nhận server vẫn hoạt động. Sau đó thử `NONE` trong một ứng dụng không cần HTTP.

### Bài 3 — Thêm profile bằng setter

Tạo `application-dev.properties` với `server.port=8081`. Gọi `setAdditionalProfiles("dev")`, khởi động và xác nhận cổng. Thử thêm profile qua biến môi trường để quan sát tập profile active.

### Bài 4 — Default properties và precedence

Dùng `setDefaultProperties` để đặt `server.port=8080`. Sau đó truyền `--server.port=8082` khi chạy.

**Câu hỏi:** giá trị nào được dùng và vì sao?

### Bài 5 — Thêm initializer và listener

Viết một `ApplicationContextInitializer` in log khi context được chuẩn bị và một `ApplicationListener<ApplicationReadyEvent>` in log khi ứng dụng sẵn sàng.

So sánh thời điểm hai callback được gọi. Giải thích vì sao không nên lấy initializer làm nơi gọi service nghiệp vụ.

### Bài 6 — Sử dụng `SpringApplicationBuilder`

Viết lại ví dụ Bài 1 bằng builder:

```java
new SpringApplicationBuilder(DemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .profiles("dev")
        .run(args);
```

So sánh khả năng đọc cấu hình với cách setter.

### Bài 7 — Thử parent-child context

Tạo `SharedConfiguration` trong parent, cung cấp một bean `Clock`. Tạo child context chứa controller hoặc service inject `Clock`. Xác nhận child có thể sử dụng bean của parent.

Sau đó khai báo một bean cùng kiểu trong child và quan sát lookup. Giải thích vì sao parent không nhìn thấy bean chỉ được đăng ký ở child.

### Bài 8 — Theo dõi startup

Gắn `BufferingApplicationStartup` cho `SpringApplication`. Khởi động ứng dụng và quan sát các startup steps qua công cụ hỗ trợ. Xác định bước nào tiêu tốn thời gian và giải thích vì sao dữ liệu startup hữu ích khi tối ưu ứng dụng.

## 18. Ghi nhớ

`SpringApplication` là đối tượng điều phối quá trình khởi động Spring Boot. Static `run()` phù hợp với ứng dụng đơn giản; tạo instance giúp cấu hình bằng setter trước startup; còn `SpringApplicationBuilder` cung cấp fluent API và hỗ trợ tổ chức context hierarchy.

Hãy chọn setter theo đúng mục tiêu: `setWebApplicationType` chọn loại context, `setAdditionalProfiles` bổ sung profile, `setDefaultProperties` cung cấp giá trị dự phòng, initializer và listener can thiệp ở các giai đoạn startup, còn shutdown hook giúp đóng context theo lifecycle của JVM.

`SpringApplicationBuilder` đặc biệt hữu ích khi cần nối nhiều cấu hình hoặc xây dựng parent-child-sibling contexts. Tuy nhiên, ứng dụng thông thường chỉ cần một context; hãy dùng hierarchy khi có nhu cầu chia sẻ bean và ranh giới module rõ ràng. Quan trọng nhất, mọi cấu hình startup cần được thực hiện trước `run()` và phải được kiểm chứng bằng property, log, bean trong context và hành vi thực tế của ứng dụng.
