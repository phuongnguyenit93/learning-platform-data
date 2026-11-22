# Đọc `SpringApplication.run` như một chuỗi giai đoạn

Một ứng dụng Spring Boot có thể có điểm vào ngắn đến mức chỉ hai dòng quan trọng:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

Nhìn vào đoạn mã này, người mới học dễ tưởng `run` chỉ “tạo một đối tượng Spring rồi chạy server”. Thực tế, `SpringApplication.run(...)` **điều phối một chuỗi giai đoạn có thứ tự**, từ chuẩn bị môi trường cấu hình, dựng `ApplicationContext`, đăng ký định nghĩa bean, làm mới context, đến gọi tác vụ khởi động và phát tín hiệu ứng dụng sẵn sàng.

Đọc đúng chuỗi này giúp trả lời các câu hỏi thực tế: “Vì sao không đọc được bean ở giai đoạn chuẩn bị `Environment`?”, “`@PostConstruct` xảy ra trước hay sau `ApplicationRunner`?”, “Vì sao đã thấy log `Started` mà ứng dụng chưa sẵn sàng?” và “Nếu một runner ném exception thì `run` có trả về context hay không?”.

**Phạm vi:** bài học dùng mô hình Spring Boot **3.3.x**, chạy với Java 17 trở lên. Các lớp và sự kiện trong bài là API thật; phần mô tả các giai đoạn là mô hình đọc luồng điều khiển, không phải cam kết mọi bước nội bộ luôn có một tên phương thức duy nhất ở mọi phiên bản.

## 1. Bản đồ tổng quan: từ `main` đến ứng dụng sẵn sàng

~~~text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    |  [1] Bắt đầu, đăng ký và thông báo cho các listener sớm
    |      ApplicationStartingEvent
    |
    |  [2] Chuẩn bị Environment và nguồn cấu hình
    |      ApplicationEnvironmentPreparedEvent
    |
    |  [3] Tạo, cấu hình ApplicationContext (chưa refresh)
    |      ApplicationContextInitializedEvent
    |
    |  [4] Nạp nguồn cấu hình / BeanDefinition
    |      ApplicationPreparedEvent
    |
    |  [5] Refresh ApplicationContext
    |      Tạo các singleton cần khởi tạo sớm; áp dụng post-processors
    |      Khởi động web server nhúng nếu là ứng dụng web
    |      ContextRefreshedEvent và sự kiện web server nếu phù hợp
    |
    |  [6] Context đã refresh xong
    |      ApplicationStartedEvent
    |      LivenessState.CORRECT
    |
    |  [7] Chạy ApplicationRunner / CommandLineRunner
    |
    |  [8] Phát ApplicationReadyEvent
    |      ReadinessState.ACCEPTING_TRAFFIC
    |
    v
Trả về ConfigurableApplicationContext cho mã gọi run(...)
~~~

Nếu một lỗi khiến việc khởi động thất bại, luồng thành công không đi hết sơ đồ: Spring Boot xử lý lỗi, có thể phát `ApplicationFailedEvent`, đóng tài nguyên đã tạo và để ngoại lệ đi ra khỏi `run`. Không có bảo đảm xuất hiện `ApplicationReadyEvent` hay nhận được context trả về.

Điểm quan trọng nhất là **ba mốc khác nhau**:

- **Context đã được tạo:** mới có một đối tượng `ApplicationContext` phù hợp, chưa chắc đã chứa các bean hoàn chỉnh.
- **Context đã được refresh:** phần khởi tạo Spring container chính đã hoàn tất; `ApplicationStartedEvent` xuất hiện trước các runner.
- **Ứng dụng đã đi qua các runner:** `ApplicationReadyEvent` và tín hiệu readiness xuất hiện về cuối chuỗi khởi động.

Trong ứng dụng không có máy chủ web, toàn bộ chuỗi này vẫn diễn ra: Spring Boot vẫn tạo context, xử lý bean và runner; chỉ không có giai đoạn mở cổng HTTP.

## 2. `SpringApplication` thực hiện công việc gì?

`SpringApplication` là **bộ điều phối khởi động**; `ApplicationContext` là **container Spring** giữ thông tin và quản lý bean sau khi được tạo.

Một ví dụ điểm vào chuẩn:

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

`@SpringBootApplication` cung cấp cấu hình Spring Boot, bật cơ chế tự cấu hình và quét component theo phạm vi package phù hợp. Nó không tự thay thế quá trình khởi động; chính lời gọi `run` mới bắt đầu các giai đoạn tạo và làm mới context.

Có hai cách gọi tương đương về ý tưởng:

~~~java
// Dùng cách tiện lợi cho cấu hình mặc định:
SpringApplication.run(MyApplication.class, args);

// Hoặc tạo đối tượng để tùy biến trước khi chạy:
SpringApplication application = new SpringApplication(MyApplication.class);
application.run(args);
~~~

Hai đoạn trên là **hai phương án thay thế tại điểm vào**, không đặt nối tiếp trong cùng một `main`. Khi dùng cách thứ hai, ta có thể gọi `addListeners(...)`, `addInitializers(...)`, `setBannerMode(...)` hoặc thiết lập kiểu ứng dụng trước khi `run` bắt đầu.

Kết quả trên đường thành công là `ConfigurableApplicationContext`. Đây là context Spring đã hoạt động; mã gọi có thể lấy bean, đọc trạng thái, rồi đóng context khi có trách nhiệm quản lý vòng đời của nó. `run` **không trả về một đối tượng `SpringApplication` và không trả về mã trạng thái HTTP**.

## 3. Giai đoạn 1 — Bắt đầu và phát `ApplicationStartingEvent`

Khi `run` bắt đầu, Spring Boot chuẩn bị các thành phần hỗ trợ khởi động và thông báo cho các listener sớm. `ApplicationStartingEvent` được phát **trước khi `Environment` và `ApplicationContext` sẵn sàng**.

Ở thời điểm này:

- Có thể quan sát rằng Spring Boot bắt đầu chạy.
- Chưa thể giả định có bean Spring để `@Autowired`.
- Chưa thể đọc cấu hình ứng dụng qua một `Environment` của context vừa được tạo, vì context chưa tồn tại.

Để bắt những sự kiện rất sớm, đăng ký listener **trước khi gọi `run`**:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(event -> {
    // Phần xử lý sự kiện cần phù hợp với kiểu event nhận được.
});
application.run(args);
~~~

Đây là ví dụ minh họa về vị trí đăng ký; ví dụ chạy đầy đủ ở phần sau dùng biến có kiểu `ApplicationListener<ApplicationEvent>` và lọc sự kiện cụ thể.

**Không nên** tạo một bean `@Component` rồi trông chờ nó bắt được mọi sự kiện ngay từ đầu. Bean này chỉ xuất hiện sau khi quá trình nạp/khởi tạo context đã tiến đủ xa. Đây là lý do Spring Boot cung cấp khả năng đăng ký listener ngay trên `SpringApplication`.

## 4. Giai đoạn 2 — Chuẩn bị `Environment` và cấu hình

`Environment` tập hợp các nguồn thuộc tính và thông tin profile cần cho quá trình dựng ứng dụng. Trong giai đoạn chuẩn bị, Spring Boot xử lý những cơ chế liên quan đến:

- Đối số ứng dụng như `--server.port=9090`, `--spring.profiles.active=dev`.
- System properties của JVM, biến môi trường, cấu hình được khai báo trong tệp.
- Tệp `application.properties`/`application.yml` và cấu hình theo profile thông qua cơ chế xử lý cấu hình của Spring Boot.
- Việc xác định các thuộc tính điều khiển hành vi của `SpringApplication` và các điều kiện cần cho những giai đoạn sau.

`ApplicationEnvironmentPreparedEvent` báo rằng môi trường cần dùng đã được chuẩn bị **trước khi context được tạo**. Listener ở giai đoạn này có thể xem hoặc thay đổi nguồn thuộc tính theo hợp đồng API, nhưng **chưa được yêu cầu lấy bean qua context**.

Ví dụ chạy:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=dev --demo.message=hello"
~~~

Khi cấu hình mặc định cho phép xử lý đối số dòng lệnh, `demo.message` có thể được đọc về sau bằng:

~~~java
String value = environment.getProperty("demo.message", "missing");
~~~

Dòng trên là **một biểu thức trong mã có `Environment` được cung cấp**; không phải chương trình `javac` độc lập. Giá trị kỳ vọng là `hello` khi không có nguồn ưu tiên cao hơn ghi đè nó.

**Phân biệt thời điểm:** “`Environment` đã có” không đồng nghĩa với “mọi bean đã được tạo”. Các annotation như `@Value`, `@ConfigurationProperties` và điều kiện tự cấu hình có thể dùng thông tin từ `Environment` trong những giai đoạn xây dựng container tiếp theo.

## 5. Giai đoạn 3 — Tạo và chuẩn bị `ApplicationContext`

Sau khi có `Environment`, Spring Boot chọn và tạo một kiểu context thích hợp. Một số kiểu thường gặp trong Spring Boot 3.3:

| Loại ứng dụng | Kiểu context mặc định thường dùng | Ý nghĩa |
| --- | --- | --- |
| Servlet web, ví dụ có Spring MVC | `AnnotationConfigServletWebServerApplicationContext` | Quản lý bean và vòng đời máy chủ servlet nhúng |
| Reactive web | `AnnotationConfigReactiveWebServerApplicationContext` | Quản lý bean và vòng đời máy chủ reactive |
| Không có web server | `AnnotationConfigApplicationContext` | Quản lý bean cho chương trình nền/CLI/thư viện chạy như ứng dụng |

Kiểu thực tế còn phụ thuộc classpath, `WebApplicationType` và các tùy chỉnh mà ứng dụng cung cấp. Không nên suy diễn kiểu context chỉ từ tên project.

Ở giai đoạn này Spring Boot gắn `Environment` và các thành phần cần thiết, gọi các `ApplicationContextInitializer` đã đăng ký, rồi phát `ApplicationContextInitializedEvent`. **Context đã được tạo nhưng chưa refresh và các định nghĩa bean từ nguồn ứng dụng chưa được nạp đầy đủ.**

Một `ApplicationContextInitializer<ConfigurableApplicationContext>` có thể thiết lập vài thuộc tính của context **trước khi refresh**:

~~~java
application.addInitializers(context ->
        context.getEnvironment()
                .getPropertySources()
                .addFirst(new org.springframework.core.env.MapPropertySource(
                        "startupOverride",
                        java.util.Map.of("demo.initialized", "yes"))));
~~~

Đoạn này thuộc phần tùy biến đối tượng `SpringApplication application` được tạo trong `main`; cần đặt **trước `application.run(args)`**. Đây là ví dụ kỹ thuật để nhận ra giai đoạn: chưa cần tạo bean ứng dụng vẫn có thể bổ sung một `PropertySource`. Khi sử dụng thật, cần cân nhắc thứ tự ưu tiên cấu hình và tránh thêm nguồn có độ ưu tiên cao một cách tùy tiện.

## 6. Giai đoạn 4 — Nạp định nghĩa bean và chuẩn bị refresh

Sau khi context được chuẩn bị, Spring Boot nạp các nguồn cấu hình ban đầu và chuyển chúng thành **`BeanDefinition`**: mô tả cách tạo, cấu hình và quản lý bean. Nguồn thường bắt đầu từ lớp chính gắn `@SpringBootApplication` và mở rộng thông qua component scanning, `@Configuration`, các phương thức `@Bean` và auto-configuration.

`ApplicationPreparedEvent` được phát **sau khi các định nghĩa bean ban đầu đã được nạp nhưng trước khi bắt đầu refresh**.

Đây là ranh giới quan trọng:

| Khái niệm | Diễn giải |
| --- | --- |
| `BeanDefinition` | Công thức/mô tả để Spring biết bean thuộc kiểu nào, cách tạo và các thông tin cấu hình cần thiết |
| Đối tượng bean thực tế | Instance được tạo theo bean definition, đưa qua các bước xử lý khởi tạo và quản lý vòng đời |
| `refresh()` | Giai đoạn container hoàn thiện cơ chế quản lý và khởi tạo các bean cần thiết |

Vì vậy, **có `BeanDefinition` chưa có nghĩa mọi instance đã tồn tại**. Nếu một chương trình cố gắng tìm/khởi tạo bean quá sớm trong listener, nó có thể gặp trạng thái container chưa sẵn sàng hoặc làm thay đổi quá trình khởi tạo mong muốn.

Cũng cần nhớ rằng **auto-configuration không phải một “tiến trình bí mật chạy sau khi ứng dụng ready”**: nó tham gia vào cơ chế xử lý định nghĩa bean và xây dựng container, trước khi ứng dụng đạt các sự kiện `Started`/`Ready`.

## 7. Giai đoạn 5 — `refresh()`: Spring container thực sự được khởi tạo

Khi gọi `refresh` trên `ApplicationContext`, Spring Framework tổ chức các bước của container. Một số điểm cần nhận ra về mặt ý nghĩa:

1. Chuẩn bị bean factory và các thành phần nền của context.
2. Xử lý những `BeanFactoryPostProcessor` hoặc biến thể liên quan để hoàn thiện định nghĩa bean; công đoạn này có thể ảnh hưởng mạnh đến component scanning, cấu hình và auto-configuration.
3. Đăng ký và dùng `BeanPostProcessor` cho quá trình tạo/khởi tạo bean, gồm những cơ chế liên quan đến dependency injection, proxy hoặc xử lý annotation.
4. Tạo các singleton **không thuộc diện lazy** mà container cần khởi tạo sớm, giải quyết phụ thuộc và gọi callback vòng đời như `@PostConstruct` khi phù hợp.
5. Hoàn thiện quá trình refresh, kích hoạt các thành phần vòng đời của context và phát `ContextRefreshedEvent`.

Danh sách mô tả **ý nghĩa**, không cố mô phỏng chính xác mọi lệnh gọi nội bộ của Spring Framework. Cụ thể, những bean được khai báo lazy hoặc chỉ được yêu cầu sau này có thể **chưa được tạo khi refresh hoàn tất**.

Trong ứng dụng web, việc tạo và bắt đầu máy chủ web nhúng như Tomcat hay máy chủ reactive gắn với vòng đời refresh của context web. Có thể quan sát `ServletWebServerInitializedEvent` hoặc `ReactiveWebServerInitializedEvent` khi máy chủ tương ứng đã sẵn sàng ở mức web server.

### Vì sao `@PostConstruct` thường chạy trước `ApplicationRunner`?

`@PostConstruct` là callback khởi tạo **của một bean**. Với bean singleton được tạo trong refresh, callback này diễn ra trong giai đoạn chuẩn bị instance, trước khi context báo refresh xong. `ApplicationRunner` lại được Spring Boot gọi **sau `ApplicationStartedEvent`**. Vì vậy, với bean không lazy được tạo trong refresh, thứ tự thường là:

~~~text
Tạo bean -> Inject dependencies -> @PostConstruct
    -> ContextRefreshedEvent
    -> ApplicationStartedEvent
    -> ApplicationRunner / CommandLineRunner
    -> ApplicationReadyEvent
~~~

Tuy nhiên, không nên phát biểu “mọi `@PostConstruct` đều xảy ra trước mọi runner”: bean lazy có thể chỉ được tạo khi nó được yêu cầu về sau. Đây là ngoại lệ quan trọng để đọc log chính xác.

### Vì sao “Tomcat đã mở cổng” chưa đồng nghĩa với “ứng dụng ready”?

Máy chủ web có thể đi vào trạng thái hoạt động trong lúc refresh, **trước khi runner hoàn thành**. Khi có readiness probe và bộ điều phối lưu lượng, nên dựa vào tín hiệu readiness/health phù hợp thay vì chỉ kiểm tra rằng cổng TCP đã mở.

## 8. Giai đoạn 6 — `ApplicationStartedEvent` và trạng thái sống

Sau khi làm mới context thành công, Spring Boot phát **`ApplicationStartedEvent`**. Mốc này diễn ra **trước khi gọi `ApplicationRunner` và `CommandLineRunner`**.

Ngay sau mốc started, Spring Boot phát một `AvailabilityChangeEvent` tương ứng với `LivenessState.CORRECT` trong cơ chế availability chuẩn. Ý nghĩa: container đã qua một mốc quan trọng và ứng dụng được xem là đang sống; đây **không phải bằng chứng rằng các tác vụ chạy sau context đã hoàn tất**.

Cần phân biệt bốn tín hiệu:

| Tín hiệu | Mốc xuất hiện | Có thể kết luận |
| --- | --- | --- |
| Log `Starting ...` | Giai đoạn đầu | Spring Boot đã bắt đầu khởi động |
| `ContextRefreshedEvent` | Khi refresh hoàn tất | Container đã qua quá trình refresh |
| `ApplicationStartedEvent` | Sau refresh, trước runners | Context chính đã khởi tạo thành công |
| `ApplicationReadyEvent` | Sau runners | Vòng đời `SpringApplication` đã đi qua các công việc runner |

Thông báo log `Started MyApplication in ...` thường gắn với mốc started, **không đồng nghĩa đã phát `ApplicationReadyEvent`**. Ngoài ra, log có thể bị tắt bằng `spring.main.log-startup-info=false`; sự kiện vòng đời vẫn tồn tại.

## 9. Giai đoạn 7 — Chạy `ApplicationRunner` và `CommandLineRunner`

Đây là nơi Spring Boot gọi các bean runner đã được đăng ký để thực hiện công việc ngay sau khi context refresh. Hai giao diện đều hỗ trợ nhiệm vụ khởi động, khác nhau ở kiểu đối số đầu vào:

~~~java
@Bean
ApplicationRunner inspectArgs() {
    return args -> {
        System.out.println(args.getOptionNames());
        System.out.println(args.getNonOptionArgs());
    };
}

@Bean
CommandLineRunner inspectRawArgs() {
    return args -> {
        System.out.println(java.util.Arrays.toString(args));
    };
}
~~~

Hai bean ở trên là **đoạn mã dùng bên trong lớp `@Configuration`/`@SpringBootApplication` với import phù hợp**. `ApplicationRunner` nhận `ApplicationArguments` đã được Spring Boot phân tích; `CommandLineRunner` nhận mảng `String[]` theo thứ tự thô.

Các runner có thể dùng bean đã được inject từ container. Nếu nhiều runner, thứ tự có thể được điều khiển bằng `@Order` hoặc `Ordered`. Nếu không định nghĩa thứ tự rõ ràng, đừng thiết kế nghiệp vụ dựa vào việc runner A luôn trước runner B.

Nếu một runner ném ngoại lệ ra ngoài, quá trình `run` được xem là khởi động thất bại: sự kiện ready sẽ **không** xuất hiện trên luồng thành công, dù context trước đó đã refresh. Đây là một nguyên nhân phổ biến của tình huống “log `Started` đã có mà chương trình vẫn báo khởi động lỗi”.

Không nên thực hiện công việc nặng và vô hạn bên trong runner nếu mục tiêu là để ứng dụng nhanh chóng nhận lưu lượng. Một runner chờ mãi sẽ trì hoãn `ApplicationReadyEvent`; cần thiết kế công việc nền và tín hiệu vận hành theo nhu cầu của hệ thống.

## 10. Giai đoạn 8 — `ApplicationReadyEvent`, readiness và giá trị trả về

Sau khi các runner hoàn thành thành công, Spring Boot phát **`ApplicationReadyEvent`**. Ngay sau đó, cơ chế availability chuẩn phát tín hiệu **`ReadinessState.ACCEPTING_TRAFFIC`**.

Trong ngữ cảnh điều phối lưu lượng, `ReadinessState.ACCEPTING_TRAFFIC` là tín hiệu mạnh hơn “cổng đã mở”, vì nó phản ánh mốc sẵn sàng mà Spring Boot quản lý. Tuy vậy, một ứng dụng thực tế vẫn có thể cần health checks riêng để đánh giá cơ sở dữ liệu, hàng đợi, dịch vụ phụ thuộc hoặc điều kiện nghiệp vụ.

Cuối đường đi thành công, `SpringApplication.run(...)` trả về một **`ConfigurableApplicationContext` đang hoạt động**. Đọc như sau:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

System.out.println(context.isActive());
~~~

Đây là mã minh họa trong `main` với import `org.springframework.context.ConfigurableApplicationContext`. Nếu không có lỗi và context vẫn hoạt động, dòng trên in:

~~~text
true
~~~

Đừng nhầm **“`run` trả về”** với **“JVM phải kết thúc”**. Ứng dụng web thường tiếp tục chạy vì máy chủ nền đang hoạt động; ứng dụng CLI không có tác vụ nền có thể tự kết thúc khi không còn luồng cần giữ chương trình sống. Với ứng dụng tự quản lý context, có thể gọi `context.close()` để giải phóng tài nguyên khi thích hợp.

## 11. Ví dụ thực hành: quan sát chuỗi sự kiện thật

Ví dụ sau dùng **Java 17 và Spring Boot 3.3.x**, chạy **không có web server** để dễ nhìn từng mốc mà không bị log Tomcat che lấp. Nó đăng ký listener **trước `run`**, lọc đúng các sự kiện Spring Boot cần theo dõi, thêm một `ApplicationRunner` và in trạng thái context sau khi `run` trả về.

### Cấu trúc dự án

~~~text
startup-stages-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runtime/StartupStagesDemo.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'startup-stages-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

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
}
~~~

Dự án cần có Gradle tương thích Spring Boot 3.3 và truy cập kho phụ thuộc để tải lần đầu. Nếu dự án hiện tại đã dùng Spring Boot plugin, hãy dùng phiên bản phù hợp với dự án thay vì tự thêm cấu hình plugin trùng lặp. Với dự án có Gradle Wrapper, ưu tiên chạy bằng wrapper của chính dự án; nếu chưa tạo wrapper, có thể dùng Gradle đã cài để chạy `gradle bootRun`.

Tệp `src/main/java/com/example/runtime/StartupStagesDemo.java`:

~~~java
package com.example.runtime;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupStagesDemo {

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(StartupStagesDemo.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        ApplicationListener<ApplicationEvent> trace = event -> {
            boolean milestone =
                    event instanceof ApplicationStartingEvent
                    || event instanceof ApplicationEnvironmentPreparedEvent
                    || event instanceof ApplicationContextInitializedEvent
                    || event instanceof ApplicationPreparedEvent
                    || event instanceof ApplicationStartedEvent
                    || event instanceof ApplicationReadyEvent;

            if (milestone) {
                System.out.println("EVENT " + event.getClass().getSimpleName());
            }
        };

        application.addListeners(trace);

        ConfigurableApplicationContext context = application.run(args);
        System.out.println("RETURN contextActive=" + context.isActive());
        context.close();
    }

    @Bean
    ApplicationRunner printRunner() {
        return args -> System.out.println("RUNNER ApplicationRunner");
    }
}
~~~

**Vì sao ví dụ chỉ bắt sáu event?** `ApplicationEvent` là kiểu cha rộng. Trong refresh, Spring Framework còn phát các sự kiện như `ContextRefreshedEvent` và Spring Boot có thêm `AvailabilityChangeEvent`. Để kết quả dễ học và có thứ tự ổn định, ví dụ chỉ in các mốc được chọn; những sự kiện khác vẫn được framework xử lý bình thường.

### Chạy và đọc đầu ra

Ở thư mục dự án, nếu đã có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Hoặc chạy bằng Gradle đã được cài nếu chưa có wrapper:

~~~bash
gradle bootRun
~~~

Các dòng **do mã ví dụ in ra**, theo thứ tự mong đợi khi chạy thành công, là:

~~~text
EVENT ApplicationStartingEvent
EVENT ApplicationEnvironmentPreparedEvent
EVENT ApplicationContextInitializedEvent
EVENT ApplicationPreparedEvent
EVENT ApplicationStartedEvent
RUNNER ApplicationRunner
EVENT ApplicationReadyEvent
RETURN contextActive=true
~~~

Đây là **phần đầu ra do ứng dụng in**, không bao gồm thông báo tác vụ Gradle, thông báo logging khác hoặc thời gian chạy. Không có log web server vì đã đặt `WebApplicationType.NONE`.

Hãy đối chiếu:
1. `ApplicationStartingEvent` đứng đầu vì quá trình khởi động vừa được thông báo.
2. `ApplicationEnvironmentPreparedEvent` đứng trước `ApplicationContextInitializedEvent` vì cần chuẩn bị cấu hình trước khi dựng context.
3. `ApplicationPreparedEvent` đứng trước `ApplicationStartedEvent` vì còn bước refresh context.
4. `ApplicationStartedEvent` xuất hiện **trước** dòng runner.
5. `ApplicationReadyEvent` xuất hiện **sau** runner, còn dòng `RETURN` chỉ xuất hiện khi `run` hoàn thành.

### Thử biến thể để thấy ranh giới

- Bỏ `application.setLogStartupInfo(false)`: bạn có thể thấy thêm log startup ở mức INFO, nhưng **thứ tự dòng `EVENT`/`RUNNER`/`RETURN` không đổi**.
- Thay `application.setWebApplicationType(WebApplicationType.NONE)` bằng kiểu web phù hợp **khi project có dependency web cần thiết**: chuỗi lớn vẫn giữ ý nghĩa nhưng sẽ có thêm khởi tạo web server trong refresh.
- Thêm `throw new IllegalStateException("runner failed");` vào thân lambda `ApplicationRunner` **chỉ để thử trong môi trường học**: chương trình không còn in `ApplicationReadyEvent`/`RETURN` theo luồng thành công, và Spring Boot báo lỗi khởi động. Xóa dòng ném lỗi sau khi quan sát.
- Thử đăng ký sự kiện `ApplicationStartingEvent` bằng một bean `@EventListener` được tạo trong context: nó không thể quan sát được sự kiện sớm này trong lần khởi động thông thường, vì chính bean listener chưa tồn tại khi event được phát.

## 12. Tìm đúng vị trí can thiệp trong chuỗi khởi động

Bắt đúng mốc giúp xử lý đúng việc, giảm code phụ thuộc vào thứ tự ngầm.

| Nhu cầu | Điểm mở rộng thường thích hợp | Lý do |
| --- | --- | --- |
| Quan sát lúc Spring Boot vừa bắt đầu | `ApplicationListener<ApplicationStartingEvent>` đăng ký sớm | Chưa có `Environment` và context |
| Thêm/chỉnh nguồn thuộc tính trước khi container dựng | Listener `ApplicationEnvironmentPreparedEvent` hoặc cơ chế cấu hình được hỗ trợ | `Environment` đã xuất hiện, bean chưa được tạo |
| Tùy biến đối tượng context trước refresh | `ApplicationContextInitializer` | Tác động khi context vừa được tạo |
| Thêm các định nghĩa bean theo cách framework hỗ trợ | `@Configuration`, `@Bean`, auto-configuration, `BeanDefinitionRegistryPostProcessor` khi thật cần | Đúng giai đoạn quản lý định nghĩa bean |
| Khởi tạo riêng cho từng bean | Constructor, dependency injection, `@PostConstruct` | Gắn với vòng đời tạo bean |
| Chạy việc một lần sau khi container refresh | `ApplicationRunner` hoặc `CommandLineRunner` | Bean được cung cấp, kiểm soát thứ tự bằng `@Order` |
| Phản ứng khi ứng dụng hoàn tất runners | `ApplicationReadyEvent` | Quan sát mốc sẵn sàng của Spring Boot |
| Quan sát lỗi khởi động | `ApplicationFailedEvent`, báo cáo nguyên nhân lỗi | Luồng thất bại không có event ready |

Nên tránh viết xử lý dài bên trong listener vì nhiều listener được gọi đồng bộ trong cùng luồng mặc định. Việc xử lý chặn có thể kéo dài thời gian đến mốc ready hoặc làm khởi động thất bại khi ném lỗi ra ngoài.

## 13. Khi `run` thất bại: tìm giai đoạn bị dừng

Không phải mọi ngoại lệ khởi động đều đến từ cùng vị trí. Khi xử lý lỗi, đọc log theo giai đoạn đã hoàn tất cuối cùng:

| Dấu hiệu quan sát | Giai đoạn nên kiểm tra trước | Ví dụ |
| --- | --- | --- |
| Không có `ApplicationEnvironmentPreparedEvent` | Đầu luồng, listener sớm hoặc chuẩn bị môi trường | Lỗi thiết lập cực sớm, listener ném exception |
| Có `EnvironmentPrepared` nhưng chưa `Prepared` | Chuẩn bị/tạo context, nạp nguồn cấu hình | Lỗi nguồn cấu hình hoặc cấu trúc context |
| Có `Prepared` nhưng chưa `Started` | `refresh`, bean factory, tạo bean, web server | Thiếu dependency, bean không tạo được, cổng server đang dùng |
| Có `Started` nhưng chưa `Ready` | Runner, listener gần cuối, các tác vụ sau refresh | `ApplicationRunner`/`CommandLineRunner` ném exception |
| Có `Ready` rồi phát sinh lỗi nghiệp vụ | Sau khi startup đã qua | Lỗi request, tác vụ nền, kết nối bị gián đoạn sau thời điểm ready |

Bảng là **gợi ý khoanh vùng**, không phải bộ suy đoán nguyên nhân đầy đủ. Listener có thể tự ném exception, logging có thể bị tắt, và một số lỗi có thể xảy ra sau mốc sự kiện cuối cùng đã thấy.

Với thất bại khi khởi động, Spring Boot thường dùng `ApplicationFailedEvent` và cơ chế phân tích lỗi (failure analysis) để thông báo. Khi chạy qua Gradle, hãy tách lỗi Gradle build/configuration khỏi lỗi trong JVM ứng dụng; dùng stack trace và nguyên nhân gốc để chẩn đoán, không chỉ dựa vào mốc event.

Quan trọng: nếu runner thất bại, **context đã refresh xong trước đó không đồng nghĩa cả lời gọi `run` đã thành công**. Trên nhánh lỗi, Spring Boot có thể thực hiện dọn dẹp và ném ngoại lệ; mã sau `SpringApplication.run(...)` trong `main` không được thực thi như luồng bình thường.

## 14. Những nhầm lẫn thường gặp

**Nhầm 1: “`run` chỉ khởi động Tomcat.”** Đây là bộ điều phối mọi loại Spring Boot application, kể cả CLI không có Tomcat.

**Nhầm 2: “`ApplicationContextInitializedEvent` có nghĩa toàn bộ bean đã sẵn sàng.”** Lúc này context mới được cấu hình và các initializer đã chạy; việc nạp bean definitions và refresh còn ở phía sau.

**Nhầm 3: “Đã nạp BeanDefinition tức là bean đã được tạo.”** Bean definition là mô tả. Instance được tạo theo các điều kiện và thời điểm của container; bean lazy có thể tạo muộn.

**Nhầm 4: “`ApplicationStartedEvent` là sự kiện bắt đầu chạy `main`.”** Tên dễ gây hiểu sai. Trong Spring Boot 3.3, sự kiện sớm là `ApplicationStartingEvent`; `ApplicationStartedEvent` xuất hiện **sau refresh**, trước runners.

**Nhầm 5: “`ApplicationReadyEvent` xuất hiện ngay khi cổng HTTP mở.”** Cổng có thể mở từ giai đoạn refresh; ready đến sau các runner.

**Nhầm 6: “Bean `@EventListener` bắt được mọi startup event.”** Những sự kiện xảy ra trước khi context tạo bean cần listener được đăng ký sớm, ví dụ qua `SpringApplication.addListeners`.

**Nhầm 7: “`@PostConstruct` là chỗ phù hợp để truy cập mọi hệ thống từ bên ngoài.”** Callback này thuộc vòng đời bean và có thể ảnh hưởng quá trình refresh. Với tác vụ khởi tạo sau khi container sẵn sàng, cân nhắc runner; với công việc nền lâu dài, dùng cơ chế quản lý vòng đời/tác vụ rõ ràng.

**Nhầm 8: “Chỉ cần thấy `Started ...` là có thể nhận traffic.”** Log started là tín hiệu của một mốc; sẵn sàng nhận traffic còn phụ thuộc runners và readiness/health của hệ thống.

**Nhầm 9: “`run` luôn trả về context, kể cả khi startup fail.”** Nếu ngoại lệ thoát khỏi quá trình khởi động, lời gọi không trả về bình thường. Phải xử lý lỗi, không giả định context luôn có thể lấy.

## 15. Tự kiểm tra kiến thức

1. Đề bài: `ApplicationEnvironmentPreparedEvent` đã phát nhưng `ApplicationContextInitializedEvent` chưa phát. **Có thể lấy bean bằng `context.getBean(...)` chưa?** Chưa: context chưa được tạo ở thời điểm sự kiện environment.
2. Đề bài: `ApplicationPreparedEvent` đã phát. **Có thể khẳng định mọi singleton đã khởi tạo xong chưa?** Chưa: `refresh` chưa hoàn tất.
3. Đề bài: `ApplicationStartedEvent` đã phát, runner sắp chạy. **`ApplicationReadyEvent` đã phát chưa?** Chưa.
4. Đề bài: một runner chờ tác vụ ngoài trong thời gian dài. **Mốc nào bị trì hoãn?** `ApplicationReadyEvent` và trạng thái readiness nhận lưu lượng.
5. Đề bài: chỉ cần ghi log tên profile từ giai đoạn sớm. **Chọn điểm mở rộng nào?** Listener cho `ApplicationEnvironmentPreparedEvent` vì lúc đó `Environment` tồn tại.
6. Đề bài: một ứng dụng CLI đã chạy xong mọi runner. **Tại sao chương trình có thể kết thúc ngay?** Không có web server hoặc các luồng khác để giữ JVM chạy; hoàn tất chuỗi startup không tự buộc tiến trình phải tồn tại mãi.
7. Đề bài: `@PostConstruct` của một bean lazy chạy sau khi `ApplicationReadyEvent` đã phát. **Có mâu thuẫn không?** Không: bean lazy có thể được tạo lần đầu sau ready.

Khi tự giải thích được vì sao ba mốc **`Environment prepared` → `Context refreshed/Started` → `Runners completed/Ready`** khác nhau, bạn đã có bản đồ đáng tin để đọc source, đặt log, chọn extension point và khoanh vùng lỗi khởi động Spring Boot.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — `SpringApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — `SpringApplication`, Application Events and Listeners, Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework — `ApplicationContext` và vòng đời bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
