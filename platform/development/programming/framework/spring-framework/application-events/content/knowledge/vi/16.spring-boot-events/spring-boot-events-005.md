# ApplicationPreparedEvent trong vòng đời khởi động Spring Boot

## 1. ApplicationPreparedEvent là gì?

`ApplicationPreparedEvent` là một **Spring Boot application event** thuộc package `org.springframework.boot.context.event`. Sự kiện được phát trong quá trình `SpringApplication.run(...)` khi `ApplicationContext` đã được tạo, môi trường cấu hình (`Environment`) có thể sử dụng, các nguồn định nghĩa bean ban đầu đã được nạp, **nhưng context chưa chạy `refresh()`**.

Thông điệp cần nhớ: **prepared không đồng nghĩa với refreshed, started hay ready**. Đây là mốc ở giữa quá trình dựng cấu trúc ứng dụng và quá trình khởi tạo đầy đủ các bean.

Về kiểu Java, `ApplicationPreparedEvent extends SpringApplicationEvent`. Đối tượng event cung cấp:

- `getApplicationContext()`: `ConfigurableApplicationContext` chuẩn bị được refresh.
- `getSpringApplication()`: `SpringApplication` đang khởi chạy.
- `getArgs()`: mảng tham số chương trình nhận khi gọi `run(...)`.
- `getTimestamp()`: thời điểm tạo sự kiện theo cơ chế `ApplicationEvent`.

Event được Spring Boot phát tự động; ứng dụng thường **không cần tự gọi** `publishEvent(new ApplicationPreparedEvent(...))`. Nó là dấu mốc khởi động của `SpringApplication`, không phải sự kiện domain do service tự định nghĩa.

## 2. Thời điểm chính xác trong chuỗi Spring Boot events

Trong luồng startup thông thường của Spring Boot 3.5, thứ tự các sự kiện đáng chú ý là:

```text
SpringApplication.run(args)
    |
    +-- ApplicationStartingEvent
    |      Chưa có Environment hay ApplicationContext hoàn chỉnh
    |
    +-- ApplicationEnvironmentPreparedEvent
    |      Environment đã được chuẩn bị; context chưa được tạo
    |
    +-- ApplicationContextInitializedEvent
    |      Context đã tạo, initializers đã chạy;
    |      chưa nạp các nguồn bean definition của ứng dụng
    |
    +-- nạp nguồn cấu hình / bean definitions ban đầu
    |
    +-- ApplicationPreparedEvent       <== CHỦ ĐỀ BÀI NÀY
    |      Context có sẵn, Environment có sẵn;
    |      chưa refresh, chưa bảo đảm các bean đã khởi tạo
    |
    +-- refresh ApplicationContext
    |      BeanFactoryPostProcessor, cấu hình, tạo singleton...
    |      ContextRefreshedEvent và các sự kiện khởi tạo liên quan
    |
    +-- ApplicationStartedEvent
    |      Context đã refresh; runner chưa được gọi
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent
    |      Các runner đã hoàn thành; ứng dụng tới mốc ready
    |
    +-- SpringApplication.run(...) trả về context
```

Giữa các mốc có thể xuất hiện các event khác, chẳng hạn `WebServerInitializedEvent` ở ứng dụng web, và các `AvailabilityChangeEvent` đánh dấu liveness/readiness. Sơ đồ chỉ mô tả mốc liên quan; không coi đây là danh sách toàn bộ callback nội bộ.

Bảng tóm tắt:

| Event | Context đã tồn tại? | Đã refresh? | Ý nghĩa |
| --- | --- | --- | --- |
| `ApplicationEnvironmentPreparedEvent` | Chưa | Chưa | Có Environment để kiểm tra/chỉnh sửa |
| `ApplicationContextInitializedEvent` | Có | Chưa | Initializer đã chạy; nguồn bean chưa nạp |
| **`ApplicationPreparedEvent`** | **Có** | **Chưa** | Nguồn cấu hình/định nghĩa bean ban đầu đã nạp |
| `ApplicationStartedEvent` | Có | Có | Refresh xong, chưa chạy runners |
| `ApplicationReadyEvent` | Có | Có | Đã chạy runners, tới mốc ứng dụng sẵn sàng |

Một điểm rất dễ nhầm: trong giai đoạn `ApplicationPreparedEvent`, một số **bean definition** đã tồn tại, nhưng không thể suy ra rằng **tất cả singleton, bean từ các phương thức `@Bean` hoặc auto-configuration đều đã sẵn sàng**. Nhiều công đoạn xử lý `@Configuration`, `BeanFactoryPostProcessor` và khởi tạo singleton thuộc chính quá trình `refresh()` sắp diễn ra. Không lấy tên "Prepared" làm lời hứa rằng đã an toàn để lấy mọi bean ra sử dụng.

## 3. Context ở trạng thái nào khi nhận sự kiện?

Giả sử listener nhận event trong một lần startup bình thường:

- `event.getApplicationContext()` trả về context thật của ứng dụng, không phải `null`.
- `context.getEnvironment()` đã khả dụng để đọc cấu hình như `demo.mode`, các property sources hoặc active profiles.
- Các nguồn cấu hình/bean definition ban đầu đã được Boot nạp vào context; có thể **kiểm tra metadata** khi thực sự cần.
- `context.isActive()` với các context triển khai `AbstractApplicationContext` thông thường vẫn là `false` trước khi bước refresh được bắt đầu.
- Không thể mặc định gọi `context.getBean(MyService.class)` thành công. Bean factory có thể chưa qua post-processing, chưa khởi tạo bean hậu xử lý, chưa tạo singleton.
- Web server, application runners, các tác vụ khởi tạo sau refresh, hệ thống nhận traffic và readiness **chưa được coi là sẵn sàng**.

So sánh ba khái niệm:

**Bean definition đã được nạp:** Spring biết về một số định nghĩa nguồn của bean hoặc lớp cấu hình sẽ sử dụng.

**Bean đã khởi tạo:** Spring đã thực sự tạo object, giải quyết dependency và thực hiện các callback khởi tạo thích hợp.

**Ứng dụng sẵn sàng:** Context đã refresh và những bước khởi động liên quan, kể cả runners, đã chạy xong. Trạng thái này gần với `ApplicationReadyEvent`, không phải `ApplicationPreparedEvent`.

Vì vậy `ApplicationPreparedEvent` rất hữu ích để **quan sát trạng thái bootstrap**, không phải một tín hiệu cho phép gọi toàn bộ nghiệp vụ của ứng dụng.

## 4. Đăng ký listener đủ sớm

### Cách khuyến nghị: SpringApplication.addListeners trước run()

Thay vì chỉ dựa vào `@EventListener` trên Spring bean, hãy đăng ký listener trước khi Boot bắt đầu khởi động:

```java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(
        (ApplicationListener<ApplicationPreparedEvent>) event -> {
            var context = event.getApplicationContext();
            System.out.println(context.getEnvironment().getProperty("app.mode"));
        });
application.run(args);
```

Đây là **trích đoạn**, chưa phải chương trình đầy đủ; ví dụ chạy được ở mục 5. Nguyên tắc là `addListeners(...)` phải được gọi **trước** `run(...)`. Nếu gọi sau khi ứng dụng đã chạy xong, bạn sẽ bỏ lỡ sự kiện prepared của lượt startup đó.

Nếu dùng builder, có thể đăng ký bằng `SpringApplicationBuilder.listeners(...)` trước khi gọi `run(...)`.

### Đăng ký dùng META-INF/spring.factories

Khi xây một thư viện cần tự động nhận sự kiện ở nhiều ứng dụng, Spring Boot hỗ trợ khai báo listener theo khóa `org.springframework.context.ApplicationListener` trong file `src/main/resources/META-INF/spring.factories`:

```properties
org.springframework.context.ApplicationListener=com.example.boot.PreparedAuditListener
```

Class `com.example.boot.PreparedAuditListener` phải được đóng gói ở classpath, có constructor thích hợp để Spring có thể khởi tạo và triển khai `ApplicationListener<ApplicationPreparedEvent>`. Đây chỉ là cấu hình minh họa: tên class phải được thay bằng class thật của dự án.

### Có nên dùng @Bean hoặc @EventListener không?

`@Bean` và `@EventListener` là mô hình tốt cho sự kiện xảy ra **sau khi bean factory đã được refresh**. Nhưng `ApplicationPreparedEvent` xuất hiện **trước refresh**, nên một listener chỉ tồn tại như một bean thông thường có thể **chưa được phát hiện hoặc khởi tạo kịp**. Để nhận sự kiện này một cách đáng tin, ưu tiên listener đăng ký trực tiếp với `SpringApplication` hoặc `spring.factories`.

Đặc biệt, không cố gọi `getBean()` trong listener prepared chỉ để kích hoạt một listener khác: có thể làm các bean được tạo quá sớm, bỏ qua những hậu xử lý mà Spring phải thực hiện trong `refresh()`.

## 5. Ví dụ Maven + Java 17 chạy được

Ví dụ dùng Spring Boot **3.5.6**, JDK 17+, và chạy **không có web server** để tập trung vào startup events. Một listener được đăng ký trước `run()` và quan sát ba mốc: Prepared, Started và Ready. Một `ApplicationRunner` in một dòng ở giữa Started và Ready.

### Cấu trúc

```text
application-prepared-demo/
├── pom.xml
└── src/main/java/demo/PreparedEventDemo.java
```

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>application-prepared-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
```

Tệp `src/main/java/demo/PreparedEventDemo.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PreparedEventDemo {

    @Bean
    ApplicationRunner sampleRunner() {
        return args -> System.out.println("runner: completed");
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(PreparedEventDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of(
                "demo.mode", "training",
                "logging.level.root", "OFF"));

        // Listener phải được đăng ký trước application.run().
        application.addListeners(
                (ApplicationListener<ApplicationPreparedEvent>) event -> {
                    var context = event.getApplicationContext();
                    System.out.println("prepared: active=" + context.isActive());
                    System.out.println("prepared: mode=" +
                            context.getEnvironment().getProperty("demo.mode"));
                });

        application.addListeners(
                (ApplicationListener<ApplicationStartedEvent>) event -> {
                    System.out.println("started: active=" +
                            event.getApplicationContext().isActive());
                });

        application.addListeners(
                (ApplicationListener<ApplicationReadyEvent>) event -> {
                    System.out.println("ready: active=" +
                            event.getApplicationContext().isActive());
                });

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("main: active=" + context.isActive());
        }
    }
}
```

Chạy trong thư mục dự án:

```bash
mvn -q spring-boot:run
```

Với Spring Boot 3.5.6 và không truyền argument ghi đè cấu hình, những dòng do chương trình tự in là:

```text
prepared: active=false
prepared: mode=training
started: active=true
runner: completed
ready: active=true
main: active=true
```

Đầu ra trên bỏ qua thông tin phụ do Maven hoặc môi trường khởi chạy. Ví dụ đã tắt banner và giảm logging Spring Boot để dễ nhìn dấu mốc sự kiện.

**Giải thích từng dòng:**

1. Khi `ApplicationPreparedEvent` được gửi, context đã tồn tại nhưng chưa refresh, nên `active=false`. `Environment` đã có property mặc định `demo.mode=training`.
2. Sau khi refresh hoàn thành, Boot phát `ApplicationStartedEvent`. Context đã active, vì vậy nhận `started: active=true`.
3. Boot gọi `ApplicationRunner` đã được tạo trong quá trình refresh. Nó in `runner: completed`.
4. Sau khi các runner hoàn thành, Boot phát `ApplicationReadyEvent`. Listener in `ready: active=true`.
5. `SpringApplication.run(...)` trả về context, rồi mã trong `main` in `main: active=true`. Cuối khối `try`, context được đóng.

Chú ý: Tệp main dùng `@SpringBootApplication` để Spring Boot tìm cấu hình và `@Bean ApplicationRunner`. Listener prepared **không** được khai báo là `@Bean`; nó được gắn vào `SpringApplication` trước khi chạy, vì vậy chắc chắn có mặt khi event xuất hiện.

Nếu chạy với một tham số như `--demo.mode=production`, giá trị property có thể bị ghi đè và dòng `prepared: mode=...` sẽ khác. Đây là hành vi đúng của hệ thống cấu hình, không phải lỗi thứ tự event.

## 6. Đọc các thuộc tính của ApplicationPreparedEvent

Giả sử đã nhận được `ApplicationPreparedEvent event`, các accessor hữu ích là:

| API | Kiểu trả về / ý nghĩa | Dùng khi nào |
| --- | --- | --- |
| `event.getApplicationContext()` | `ConfigurableApplicationContext` | Kiểm tra context và môi trường |
| `event.getSpringApplication()` | `SpringApplication` | Xác định ứng dụng đang khởi chạy, khi có nhiều SpringApplication |
| `event.getArgs()` | `String[]` | Biết tham số startup đã truyền |
| `event.getTimestamp()` | `long` | Ghi nhận thời gian event được tạo |

Ví dụ snippet nhỏ, **không phải chương trình độc lập**:

```java
ApplicationPreparedEvent event = /* event đã nhận bởi listener */;
ConfigurableApplicationContext context = event.getApplicationContext();
String mode = context.getEnvironment().getProperty("app.mode", "default");
int startupArgumentCount = event.getArgs().length;
```

Trong mã thực tế, không viết dòng placeholder để tạo event: dùng tham số `event` của `ApplicationListener` như ví dụ ở mục 5. Lưu ý `getArgs()` thể hiện arguments truyền cho `SpringApplication.run`, không phải danh sách mọi property cuối cùng sau khi hợp nhất tất cả nguồn cấu hình.

## 7. Phân biệt ApplicationPreparedEvent với các hook khác

| Mục đích | Cơ chế phù hợp hơn | Vì sao |
| --- | --- | --- |
| Đọc trạng thái Environment và context **ngay trước refresh** | **`ApplicationPreparedEvent`** | Đúng mốc trong bài |
| Sửa Environment rất sớm, trước khi context được dựng | `EnvironmentPostProcessor` / cấu hình Environment phù hợp | Làm việc trước quá trình tải nguồn bean |
| Tùy biến context ngay sau khi tạo, trước khi tải nguồn bean | `ApplicationContextInitializer` | Có hook rõ ràng cho giai đoạn này |
| Đăng ký/chỉnh sửa bean definitions trong chuỗi refresh chính thức | `BeanDefinitionRegistryPostProcessor` hoặc `BeanFactoryPostProcessor` | Được Spring quản lý theo vòng đời post-processing |
| Dùng bean đã được khởi tạo đầy đủ khi context refresh xong | `ContextRefreshedEvent`, `ApplicationStartedEvent` | Bean factory đã refresh |
| Chạy công việc startup cần injection/service beans | `ApplicationRunner` hoặc `CommandLineRunner` | Được gọi sau refresh |
| Biết mốc ứng dụng chuẩn bị nhận traffic | `ApplicationReadyEvent` / readiness state | Đúng ngữ nghĩa ready |
| Bắt lỗi xảy ra khi Spring Boot đang khởi động | `ApplicationFailedEvent` | Có thể chứa exception gây thất bại |

**Không nên dùng prepared event để gọi service nghiệp vụ, mở kết nối cần bean đã cấu hình đầy đủ, đọc dữ liệu qua repository hoặc thực thi một job dài.** Những thành phần đó có thể chưa được tạo; nếu listener gây lỗi, startup có thể thất bại.

### ApplicationPreparedEvent không phải ContextRefreshedEvent

`ApplicationPreparedEvent` thuộc Spring Boot và phát **trước** refresh. `ContextRefreshedEvent` thuộc Spring Framework, xuất hiện khi việc refresh đã hoàn tất. Spring Boot có thể phát `ApplicationPreparedEvent` ngay cả khi quá trình refresh sau đó thất bại và ứng dụng **không bao giờ** đạt `ApplicationStartedEvent` hoặc `ApplicationReadyEvent`.

### Không phải ApplicationContextInitializedEvent

`ApplicationContextInitializedEvent` xuất hiện sau khi context và các `ApplicationContextInitializer` đã chuẩn bị xong nhưng **trước khi** nguồn bean definition của ứng dụng được nạp. `ApplicationPreparedEvent` xuất hiện **sau khi** chúng được nạp (nhưng vẫn trước refresh). Hai event bao quanh bước nạp nguồn cấu hình.

## 8. Lỗi phổ biến và giới hạn cần chú ý

### 8.1. Đăng ký listener quá trễ

Nếu dùng một `@EventListener` trong bean chỉ được tạo khi refresh, có thể không nhận được `ApplicationPreparedEvent` vì mốc này đã qua. Tương tự, gọi `addListeners(...)` sau `SpringApplication.run(...)` đã trả về là quá muộn cho lượt startup vừa hoàn thành.

**Giải pháp:** đăng ký thông qua `SpringApplication.addListeners(...)` trước `run(...)`, `SpringApplicationBuilder.listeners(...)`, hoặc `META-INF/spring.factories`.

### 8.2. Suy luận rằng tất cả bean đã hoạt động

"Bean definitions đã nạp" **không đồng nghĩa** "đã tạo bean". `@Bean` methods, component scanning bổ sung, auto-configuration và singleton creation phần lớn được xử lý trong refresh. Việc cưỡng ép `getBean(...)` tại mốc prepared có thể khởi tạo đối tượng sai thời điểm hoặc tạo lỗi khó chẩn đoán.

**Giải pháp:** nếu cần dependency injection để chạy nghiệp vụ, chuyển sang `ApplicationRunner` hoặc event sau refresh.

### 8.3. Xử lý quá lâu hoặc ném exception

Các listener startup được gửi đồng bộ trong đường đi thông thường của `SpringApplication`, nên I/O mạng chậm trong listener prepared sẽ tăng thời gian khởi động. Nếu listener ném exception không xử lý, `SpringApplication.run(...)` có thể thất bại và Boot phát `ApplicationFailedEvent` trong quá trình xử lý lỗi.

**Giải pháp:** giữ listener nhẹ, logging/metering vừa đủ; không làm nhiệm vụ business kéo dài. Nếu cần bắt lỗi, phân biệt rõ lỗi cần hủy startup với lỗi có thể log và tiếp tục.

### 8.4. Dùng prepared để báo readiness

`ApplicationPreparedEvent` không có nghĩa web server đã mở cổng, tất cả runner đã chạy, hay ứng dụng nhận traffic an toàn. Một hệ thống giám sát đánh dấu ready ngay tại event này sẽ báo sai thời điểm.

**Giải pháp:** theo dõi `ApplicationReadyEvent` hoặc readiness probes theo chính sách triển khai.

### 8.5. Nhiều ApplicationContext / SpringApplication

Khi dùng phân cấp parent-child context hoặc nhiều `SpringApplication`, một listener có thể quan sát sự kiện từ hơn một context; sự kiện cũng có thể được chuyển tới ancestor context theo cơ chế publish của Spring. Đừng giả định chỉ có duy nhất một instance event trong toàn tiến trình.

**Giải pháp:** khi cần, nhận diện nguồn bằng `event.getApplicationContext()` hoặc `event.getSpringApplication()`, gắn một correlation ID của mỗi lượt startup và lọc theo mục tiêu của listener.

### 8.6. Nhầm với @TransactionalEventListener

Prepared event diễn ra trước khi ứng dụng sẵn sàng, thường không gắn với transaction nghiệp vụ đang hoạt động. Không dùng `@TransactionalEventListener` để đợi một transaction commit của quá trình startup mà không tồn tại. Đây là hai khái niệm event khác nhau.

## 9. Quy tắc vận dụng

Có thể dùng `ApplicationPreparedEvent` khi cần:

1. Ghi dấu mốc quan sát bootstrap, đo thời gian từ environment-prepared đến trước refresh.
2. Kiểm tra một số property/profile đã sẵn sàng tại thời điểm chuẩn bị context.
3. Phát hiện ứng dụng hoặc context nào đang bước vào giai đoạn refresh trong môi trường có nhiều context.
4. Thực hiện kiểm tra metadata rất nhẹ, không yêu cầu bean đã khởi tạo và không can thiệp quá sâu vào container.

Không dùng khi cần:

1. Chạy SQL qua repository đã được inject.
2. Gửi email, đăng ký consumer, chạy job nghiệp vụ hoặc kết nối tới các hệ thống phụ thuộc vào bean hoàn chỉnh.
3. Khẳng định service đã sẵn sàng để nhận traffic.
4. Thay đổi bean definitions một cách tùy tiện, bỏ qua lifecycle post-processors.

## 10. Câu hỏi tự kiểm tra

1. **ApplicationPreparedEvent chạy trước hay sau refresh?** — Trước refresh, sau khi nạp các nguồn định nghĩa bean ban đầu.
2. **Có ApplicationContext trong event không?** — Có; `getApplicationContext()` trả về `ConfigurableApplicationContext`.
3. **Environment có dùng được chưa?** — Có, để đọc trạng thái cấu hình.
4. **Có nên lấy mọi Spring bean bằng context.getBean() ở thời điểm này không?** — Không. Context chưa refresh và nhiều bean chưa được tạo.
5. **Vì sao @Bean/@EventListener có thể bỏ lỡ event prepared?** — Listener bean có thể được khởi tạo sau khi event đã phát.
6. **Nên đăng ký listener ở đâu?** — `SpringApplication.addListeners(...)` trước `run(...)` hoặc `spring.factories` thích hợp.
7. **Khác ApplicationStartedEvent thế nào?** — `ApplicationStartedEvent` xảy ra sau refresh nhưng trước runners.
8. **Khác ApplicationReadyEvent thế nào?** — `ApplicationReadyEvent` sau khi runners đã chạy và ứng dụng đạt mốc ready.
9. **Nếu refresh thất bại sau prepared, ready có chắc chắn xuất hiện?** — Không; startup có thể thất bại và `ApplicationFailedEvent` được phát.
10. **Vì sao không dùng prepared event làm health-ready signal?** — Vì server và ứng dụng chưa hoàn tất startup.

## Tài liệu tham khảo

- [Spring Boot 3.5 — SpringApplication / Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot 3.5 — ApplicationPreparedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html)
- [Spring Boot 3.5 — Customizing the Environment or ApplicationContext](https://docs.spring.io/spring-boot/3.5/how-to/application.html)
- [Spring Boot 3.5 — ApplicationStartedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
- [Spring Boot 3.5 — ApplicationReadyEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
