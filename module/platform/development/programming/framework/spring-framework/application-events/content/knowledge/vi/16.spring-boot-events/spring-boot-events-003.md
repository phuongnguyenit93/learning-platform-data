# ApplicationEnvironmentPreparedEvent trong Spring Boot

## 1. Khái niệm và vị trí trong vòng đời

`ApplicationEnvironmentPreparedEvent` là một **Spring Boot application event** thuộc package `org.springframework.boot.context.event`. Spring Boot phát sự kiện này khi `Environment` dùng cho ứng dụng đã được tạo/chuẩn bị đến giai đoạn thích hợp, **trước khi `ApplicationContext` được tạo**.

Mục đích của nó là cung cấp một điểm mở rộng rất sớm để quan sát hoặc, khi có lý do rõ ràng, tùy chỉnh môi trường cấu hình trước khi container khởi tạo bean. Ví dụ: đọc cờ cấu hình cho phần bootstrap, ghi nhận profile đang kích hoạt, hoặc kiểm tra sự tồn tại của một cấu hình bắt buộc.

Event này khác với `ContextRefreshedEvent` của Spring Framework. Ở thời điểm `ApplicationEnvironmentPreparedEvent` được phát, ứng dụng **chưa có context đang vận hành**, chưa có các bean được khởi tạo để có thể tiêm dependency như trong một listener thông thường.

Đặc tính quan trọng nhất:

- **Nguồn phát:** `SpringApplication` trong chu trình khởi động Spring Boot, không phải một event nghiệp vụ do controller/service tự publish.
- **Thời điểm:** Sau `ApplicationStartingEvent` và trước `ApplicationContextInitializedEvent`.
- **Dữ liệu chính:** `event.getEnvironment()` trả về `ConfigurableEnvironment`, chứa các `PropertySource` và thông tin profile ở thời điểm event được xử lý.
- **Đăng ký listener:** Phải đăng ký **trước `SpringApplication.run(...)`**, ví dụ qua `addListeners(...)` hoặc `META-INF/spring.factories`.
- **Giới hạn:** Không inject bean bằng `@Autowired` trong listener sớm này và không coi event là tín hiệu ứng dụng đã sẵn sàng nhận request.

## 2. Trình tự các application events

Luồng khởi động thường gặp của Spring Boot:

```text
SpringApplication.run(...)
         |
         v
ApplicationStartingEvent
         |
         v
Chuẩn bị Environment / xử lý nguồn cấu hình
         |
         v
ApplicationEnvironmentPreparedEvent  <-- bài này
         |                                chưa tạo ApplicationContext
         v
Tạo ApplicationContext và chạy initializer
         |
         v
ApplicationContextInitializedEvent
         |
         v
Nạp các định nghĩa bean
         |
         v
ApplicationPreparedEvent
         |
         v
Refresh ApplicationContext
    (bao gồm ContextRefreshedEvent)
         |
         v
ApplicationStartedEvent
         |
         v
ApplicationRunner / CommandLineRunner
         |
         v
ApplicationReadyEvent
         |
         v
Ứng dụng đã qua startup thông thường
```

Với ứng dụng web còn có những sự kiện liên quan web server trong quá trình refresh. Nếu startup thất bại, Spring Boot có thể phát `ApplicationFailedEvent`. `ApplicationReadyEvent` cũng không bảo đảm các hệ thống phụ thuộc bên ngoài sẽ luôn khỏe mạnh sau startup; cần health/readiness check riêng.

**Chi tiết về thứ tự xử lý cấu hình:** Boot có các listener và `EnvironmentPostProcessor` nội bộ tham gia ngay trong quá trình xử lý event chuẩn bị environment. Một listener tùy chỉnh có thể nhìn thấy những property source khác nhau tùy thứ tự chạy (`Ordered`/`@Order`). Đừng suy đoán rằng mọi extension tùy chỉnh đều đã chạy chỉ vì event này được phát. Trong cấu hình Boot thông thường, listener không đặt priority đặc biệt sẽ thấy các cấu hình Boot đã xử lý theo chuỗi startup mặc định.

## 3. Environment có gì tại thời điểm này?

`Environment` là giao diện truy cập cấu hình của Spring. `ConfigurableEnvironment` còn cho phép lấy danh sách nguồn cấu hình và thay đổi một số thiết lập trước khi context khởi tạo. Những thao tác đọc hay gặp:

| API | Ý nghĩa | Chú ý |
| --- | --- | --- |
| `getProperty("demo.feature")` | Lấy giá trị hiệu lực theo độ ưu tiên các nguồn | Có thể trả về `null` |
| `getProperty("demo.feature", "off")` | Giá trị mặc định nếu không tìm thấy key | Mặc định ở đây không ghi thêm vào Environment |
| `getProperty("demo.enabled", Boolean.class, false)` | Đọc dưới dạng Boolean | Có thể lỗi chuyển kiểu nếu cấu hình sai |
| `getActiveProfiles()` | Danh sách profile đang active | Mảng rỗng nghĩa là không có active profile được chỉ định |
| `getDefaultProfiles()` | Profile mặc định, thường là `default` | Không đồng nghĩa với active profiles |
| `getPropertySources()` | Truy cập các `PropertySource` hiện có | Thứ tự và nguồn cụ thể phụ thuộc thời điểm, phiên bản và cấu hình |

Các nguồn thường gồm tham số dòng lệnh (ví dụ `--demo.topic=events`), system properties, biến môi trường, tệp `application.properties`/`application.yml` và tệp theo profile. Spring Boot áp dụng quy tắc độ ưu tiên giữa các nguồn; các tham số `--key=value` thông thường có thể ghi đè giá trị trong tệp cấu hình, trừ khi ứng dụng đã thay đổi chính sách nhận command-line properties.

**Không dùng listener sớm để in toàn bộ giá trị cấu hình:** `Environment` có thể chứa token, mật khẩu, URI có credential và dữ liệu nội bộ. Chỉ đọc những key cần thiết, ghi log theo allowlist hoặc che giá trị nhạy cảm.

### Environment đã tồn tại, còn bean thì chưa

Ở giai đoạn này có thể đọc:

```java
String feature = event.getEnvironment()
        .getProperty("demo.feature", "off");
```

Nhưng không thể trông đợi những thứ sau đã sẵn sàng:

- `@Autowired SomeService` trong một bean được component scan để nhận event.
- `ApplicationContext.getBean(...)` từ event (event này không cung cấp context).
- `@ConfigurationProperties` bean đã được tạo và bind xong.
- Repository, DataSource, controller, web server hoặc các bean ứng dụng.

Nếu cần một service do Spring quản lý, hãy chờ giai đoạn có context, dùng `ApplicationRunner`, `ApplicationReadyEvent` hoặc một lifecycle callback phù hợp.

## 4. Cách đăng ký listener đúng thời điểm

Vì event được phát **trước khi context tồn tại**, chỉ viết `@Component` với `@EventListener(ApplicationEnvironmentPreparedEvent.class)` hoặc khai báo `@Bean ApplicationListener<...>` bên trong context là **quá muộn cho event của chính lượt khởi động đó**.

Có ba cách đăng ký sớm phổ biến:

1. `SpringApplication.addListeners(listener)` trước `run(args)`. Phù hợp với ứng dụng kiểm soát phương thức `main`, đơn giản và có thể thấy ngay nơi listener được khai báo.
2. `SpringApplicationBuilder.listeners(listener)` khi ứng dụng bootstrap bằng builder.
3. Tệp `META-INF/spring.factories` dùng khóa `org.springframework.context.ApplicationListener` khi muốn một thư viện tự đăng ký listener trong các ứng dụng sử dụng nó.

Listener phải triển khai `ApplicationListener<ApplicationEnvironmentPreparedEvent>` hoặc một `ApplicationListener` thích hợp được đăng ký trực tiếp vào `SpringApplication`. Một instance listener khởi tạo bằng `new` lúc này **không phải bean được Spring quản lý**: không có dependency injection thông thường, `@PostConstruct`, scope của bean hay giao dịch do proxy.

### So sánh với các hook khác

| Hook | Khi nào dùng? |
| --- | --- |
| `ApplicationEnvironmentPreparedEvent` | Quan sát môi trường khởi động và thao tác nhỏ cần thực hiện trước khi tạo context |
| `EnvironmentPostProcessor` | Mở rộng hoặc chỉnh sửa `PropertySource` có hệ thống trong giai đoạn chuẩn bị environment |
| `ApplicationContextInitializer` | Tùy chỉnh `ConfigurableApplicationContext` sau khi context đã được tạo, trước quá trình refresh |
| `@PostConstruct` hoặc `InitializingBean` | Khởi tạo trạng thái của một bean sau khi được tạo và inject |
| `ApplicationRunner`/`CommandLineRunner` | Chạy công việc sau khi context đã refresh, trước khi Boot báo ready |
| `ApplicationReadyEvent` | Phản ứng khi quy trình startup của Spring Boot đạt mốc sẵn sàng |

Nếu nhiệm vụ chính là **thêm một nguồn cấu hình** hoặc can thiệp thứ tự tải config data, `EnvironmentPostProcessor` thường là hook có trách nhiệm rõ hơn. Nếu chỉ cần log một giá trị đã được nạp, listener của event này có thể đủ.

## 5. Ví dụ Java 17+ chạy được: đọc tham số khi Environment được chuẩn bị

Tạo ứng dụng Spring Boot không chạy web server. Ví dụ dùng `SpringApplication.addListeners(...)` để nhận event trước khi context tạo, sau đó quan sát `CommandLineRunner` và đoạn code sau `run(...)`.

### Cấu trúc

```text
environment-prepared-demo/
├── pom.xml
└── src/main/java/example/boot/EnvironmentPreparedDemo.java
```

### pom.xml

Maven 3.9+, Java 17 và Spring Boot 3.3.13 (chọn một phiên bản phát hành cụ thể để ví dụ có thể tái lập):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>environment-prepared-demo</artifactId>
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

### EnvironmentPreparedDemo.java

```java
package example.boot;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;

@SpringBootApplication
public class EnvironmentPreparedDemo {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EnvironmentPreparedDemo.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Bắt buộc đăng ký trước run(): context chưa tồn tại.
        application.addListeners(new EarlyEnvironmentListener());

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println(
                    "MAIN contextActive=" + context.isActive());
        }
    }

    static class EarlyEnvironmentListener implements
            ApplicationListener<ApplicationEnvironmentPreparedEvent> {

        @Override
        public void onApplicationEvent(
                ApplicationEnvironmentPreparedEvent event) {

            ConfigurableEnvironment environment =
                    event.getEnvironment();

            String topic = environment.getProperty(
                    "demo.topic", "unset");

            System.out.println("EARLY demo.topic=" + topic);
        }
    }

    @Bean
    CommandLineRunner runner() {
        return args -> System.out.println("RUNNER executed");
    }
}
```

### Biên dịch và chạy

Đứng tại thư mục chứa `pom.xml`:

```bash
mvn -q package
java -jar target/environment-prepared-demo-1.0.0.jar --demo.topic=events
```

Ba dòng do **chính chương trình** in ra theo thứ tự (các log của Maven/Spring nếu có là độc lập):

```text
EARLY demo.topic=events
RUNNER executed
MAIN contextActive=true
```

**Giải thích:**

1. `addListeners(new EarlyEnvironmentListener())` được thực hiện trên `SpringApplication` trước lúc gọi `run(args)`. Vì vậy listener có mặt đủ sớm để nhận event.
2. Trong khi Boot chuẩn bị `Environment`, command-line argument `--demo.topic=events` được đưa vào nguồn cấu hình. `event.getEnvironment().getProperty("demo.topic", "unset")` trả về `events`.
3. Sau khi môi trường được chuẩn bị, Boot mới tạo và refresh context, tạo các bean ứng dụng. `@Bean CommandLineRunner` được gọi sau giai đoạn refresh nên in `RUNNER executed`.
4. `application.run(args)` trả về context sau khi hoàn thành startup theo cơ chế thông thường; đoạn `MAIN` chứng minh context đang hoạt động. Ra khỏi `try-with-resources` sẽ đóng context.
5. Nếu chạy lại **không có** đối số `--demo.topic=events` và không có nguồn cấu hình nào khác định nghĩa `demo.topic`, dòng đầu thành `EARLY demo.topic=unset`.

Việc example in `System.out` chỉ nhằm thấy rõ thứ tự. Trong ứng dụng thực, dùng cơ chế ghi log có cấu hình phù hợp và không log secret. Listener không yêu cầu `@Component` hoặc `@Bean` vì đã đăng ký trên đối tượng `SpringApplication`.

## 6. Đăng ký tự động bằng META-INF/spring.factories

Nếu cần đóng gói listener trong một thư viện dùng chung, có thể đăng ký bằng resource:

```text
src/main/resources/META-INF/spring.factories
```

Nội dung:

```properties
org.springframework.context.ApplicationListener=\
example.boot.MyEarlyListener
```

Trong đó `example.boot.MyEarlyListener` là **lớp listener bạn tự định nghĩa** và phải có constructor phù hợp để Boot khởi tạo, ví dụ:

```java
package example.boot;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class MyEarlyListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {
        String mode = event.getEnvironment()
                .getProperty("demo.mode", "normal");
        System.out.println("BOOTSTRAP mode=" + mode);
    }
}
```

Lưu file class ở `src/main/java/example/boot/MyEarlyListener.java`; đây là **phương án độc lập** thay cho việc gọi `addListeners(...)`. Đừng dùng đồng thời cả đăng ký trong `spring.factories` và `addListeners(new MyEarlyListener())` cho cùng logic nếu không chủ đích muốn có hai instance và hai lần xử lý.

Nội dung trong `spring.factories` dùng tên **interface listener** làm key, không dùng tên class `ApplicationEnvironmentPreparedEvent`. Khác với cơ chế auto-configuration của Boot, đăng ký các `ApplicationListener` sớm vẫn có thể dùng cách này.

Các listener có thể hỗ trợ thứ tự bằng `Ordered` hoặc `@Order`; nên tránh đặt ưu tiên quá cao mà chưa hiểu thứ tự những listener nội bộ xử lý config data và logging của Boot.

## 7. Nếu cần thay đổi Environment, xử lý thế nào?

Có thể gọi `event.getEnvironment().getPropertySources()` để quan sát hay thay đổi `PropertySource`. Nhưng việc thay đổi cấu hình ở giữa chu trình startup có nhiều ràng buộc:

- Những key dùng để chọn **vị trí file cấu hình**, profile hoặc cơ chế bootstrap có thể đã được một số thành phần sử dụng trước khi listener tùy chỉnh chạy. Đừng giả định sửa một property tại event này sẽ khiến toàn bộ config data được đọc lại.
- `PropertySource` có thứ tự ưu tiên. `addFirst(...)` có thể ghi đè giá trị từ tham số dòng lệnh hoặc từ môi trường, trong khi `addLast(...)` thường chỉ là fallback. Chọn thứ tự phải có yêu cầu nghiệp vụ rõ.
- `@PropertySource` trên `@Configuration` thường chỉ được bổ sung khi context refresh và có thể quá muộn với các property khởi động như `logging.*` hoặc `spring.main.*`.
- Không tự thao tác các bean/repository ở đây, vì chúng chưa được khởi tạo.
- Listener sớm nên ngắn, không gọi dịch vụ HTTP dài hoặc giữ resource mà không quản lý vòng đời.

### Hook chuyên dụng: EnvironmentPostProcessor

Khi ứng dụng thực sự cần tải một nguồn property riêng trước context, Spring Boot hỗ trợ interface `EnvironmentPostProcessor`:

```java
package example.boot;

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

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "demo-fallback",
                        Map.of("demo.feature", "off")));
    }
}
```

Với Boot 3.3, đăng ký file `src/main/resources/META-INF/spring.factories` như sau:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
example.boot.DemoEnvironmentPostProcessor
```

Đây là **ví dụ riêng về extension cấu hình**, không cần thêm vào demo chạy ở mục 5. Nó chỉ tạo một nguồn fallback; key `demo.feature` từ các nguồn có ưu tiên cao hơn vẫn thắng. Không dùng để thay đổi property nhạy cảm hoặc ghi đè cấu hình triển khai mà không có chủ đích.

## 8. Hiểu nhầm thường gặp khi dùng @EventListener

Cách viết sau **không đáp ứng yêu cầu nhận sớm** của event trong cùng lượt khởi động:

```java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class TooLateListener {

    @EventListener
    public void observe(ApplicationEnvironmentPreparedEvent event) {
        System.out.println("Never called during this startup");
    }
}
```

Đoạn này là **minh họa anti-pattern**, không phải file của demo ở mục 5. Một `@Component` được tìm và tạo khi context xây dựng bean, trong khi sự kiện đã được phát trước thời điểm đó. Việc dùng `@EventListener` không tự đăng ký listener lên `SpringApplication` từ trước.

Phân biệt với các event muộn hơn: `ApplicationStartedEvent` và `ApplicationReadyEvent` xảy ra sau khi context refresh, nên listener đã đăng ký trong container có thể được gọi theo cơ chế thông thường.

Không kết luận rằng sự kiện hoàn toàn "không thể" tới listener dạng bean trong mọi trường hợp nhân tạo. Một ứng dụng có thể tự publish lại event hoặc tạo nhiều context. Nhưng **đối với event sớm của chính `SpringApplication.run(...)`**, đăng ký bằng bean trong context được tạo sau đó không kịp thời điểm.

## 9. Sử dụng thực tế và các điều kiện an toàn

### Trường hợp phù hợp

- Quan sát giá trị cấu hình cần thiết trong giai đoạn bootstrap để ghi log có kiểm soát.
- Phát hiện thiếu property quan trọng trước khi context tạo; nếu chọn fail-fast, lỗi cần rõ ràng và không rò rỉ thông tin nhạy cảm.
- Thiết lập/kiểm tra một tùy chọn nhỏ liên quan giai đoạn bootstrap trong thư viện khởi động.
- Đo thời điểm một mốc startup đã đến hoặc gắn correlation ID cho log của giai đoạn sớm, miễn không phụ thuộc bean.

### Trường hợp nên chọn hook khác

- **Cần tiêm service** để thực thi nghiệp vụ: chờ khi context đã tạo.
- **Cần đọc DB hoặc gọi API** để tạo dữ liệu nền: chọn lifecycle phù hợp và thiết kế timeout/retry; đừng mặc định nó nên nằm trước context.
- **Cần thêm property source có cơ chế riêng:** dùng `EnvironmentPostProcessor`.
- **Cần biết app sẵn sàng nhận request:** dùng `ApplicationReadyEvent`/readiness.
- **Cần phản ứng với một thay đổi cấu hình trong runtime:** event này không phải event hot-reload tự động.

### Không ghi nhầm trạng thái hoặc lỗi

Một listener ném exception trong giai đoạn sớm có thể khiến startup thất bại trước khi context được tạo. Vì vậy chỉ chủ động fail-fast với cấu hình thật sự bắt buộc. Không catch rồi bỏ qua mọi lỗi cấu hình; nhưng cũng không biến nhiệm vụ log thông thường thành điểm lỗi làm ứng dụng không khởi động.

Trong hệ thống có nhiều SpringApplication/context hoặc test gọi khởi động nhiều lần, listener có thể được thực thi nhiều lần. Nếu tác dụng phụ phải duy nhất toàn hệ thống, cần lưu vết bền vững và idempotency riêng; biến `boolean` trong listener không đủ.

## 10. Kiểm thử ApplicationEnvironmentPreparedEvent

Kiểm thử nên chứng minh ba điều độc lập: **listener được đăng ký đủ sớm**, **đọc được property cần thiết**, **không vô tình phụ thuộc context/bean**.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| `addListeners(...)` trước `run(...)`, truyền `--demo.topic=events` | Listener được gọi và đọc `events` |
| Không truyền arg và không có nguồn khác cho key | Giá trị fallback `unset` |
| Chỉ khai báo `@Component @EventListener` trong context được tạo sau | Không nhận event chuẩn bị environment của chính lần bootstrap đó |
| Thay đổi key bằng command-line arg so với `application.properties` | Thông thường command-line arg có ưu tiên cao hơn |
| Listener cố dùng Spring bean qua dependency injection | Không hợp lệ ở giai đoạn bootstrap này |
| Listener phát sinh exception | Có thể làm việc khởi động thất bại, tùy đường xử lý lỗi |
| Cùng chương trình khởi động hai lần | Mỗi chu trình bootstrap có thể phát event riêng; cần tránh tác dụng phụ trùng |

Khi viết integration test, nên tạo `SpringApplication` với `WebApplicationType.NONE` để không mở web server, đăng ký listener thu kết quả vào `AtomicReference`/counter, chạy với một key kiểm thử, rồi đóng context. Không kiểm tra thứ tự chính xác của **mọi listener nội bộ Boot** vì thứ tự đó còn phụ thuộc các extension đã đăng ký và phiên bản.

Ví dụ phần thân của một test **minh họa, không phải chương trình độc lập**:

```java
AtomicReference<String> seen = new AtomicReference<>();

SpringApplication app =
        new SpringApplication(EnvironmentPreparedDemo.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.addListeners(
        (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event ->
                seen.set(event.getEnvironment()
                        .getProperty("demo.topic")));

try (ConfigurableApplicationContext context =
             app.run("--demo.topic=verified")) {
    assertEquals("verified", seen.get());
}
```

Đoạn này giả định đã import `AtomicReference`, `ApplicationListener`, `ApplicationEnvironmentPreparedEvent`, `ConfigurableApplicationContext`, `SpringApplication`, `WebApplicationType` và `assertEquals` từ JUnit; cần phụ thuộc test của Spring Boot/JUnit phù hợp. Kiểm thử này kiểm tra **giá trị property mà listener nhận**, không giả định thứ tự các dòng log của mọi thư viện.

## 11. Những lỗi phổ biến và cách khắc phục

**Lỗi 1 — Đăng ký bằng @Component rồi chờ event đến.** Bean được tạo quá muộn. Hãy đăng ký listener trực tiếp với `SpringApplication.addListeners(...)` trước `run(...)` hoặc qua `spring.factories`.

**Lỗi 2 — Truy cập ApplicationContext hoặc @Autowired service trong listener.** `ApplicationEnvironmentPreparedEvent` không chứa context; bean container chưa sẵn sàng. Chỉ dùng những dependency có thể tạo độc lập hoặc chọn event muộn hơn.

**Lỗi 3 — Cho rằng Environment bất biến hoặc đã qua mọi extension.** Thứ tự `ApplicationListener` và `EnvironmentPostProcessor` ảnh hưởng giá trị có thể đọc tại từng thời điểm. Chỉ đặt priority đặc biệt khi biết rõ vòng đời Boot.

**Lỗi 4 — Sửa profile hoặc config location quá muộn.** Một số thiết lập đã được dùng trong quá trình tải config data. Đặt chúng từ CLI/system env hoặc sử dụng extension chuyên dụng theo đúng thứ tự.

**Lỗi 5 — In toàn bộ Environment để debug.** Có thể lộ secret. Chỉ log key không nhạy cảm và che thông tin định danh khi cần.

**Lỗi 6 — Làm I/O/blocking dài ở listener sớm.** Mặc định listener chạy trong luồng khởi động, làm tăng thời gian startup hoặc khiến startup treo. Dời công việc nặng sang hook sau khi app sẵn sàng.

**Lỗi 7 — Gọi event này là ContextRefreshedEvent hoặc ApplicationReadyEvent.** Ba event ở các mốc khác nhau. Early environment ≠ đã tạo bean ≠ đã sẵn sàng xử lý request.

**Lỗi 8 — Đăng ký cùng listener cả trong spring.factories và addListeners.** Có thể tạo nhiều instance được gọi và tác dụng phụ lặp. Chọn một cơ chế đăng ký theo phạm vi cần dùng.

## 12. Checklist khi áp dụng vào ứng dụng

1. Có thật sự cần xử lý **trước khi tạo ApplicationContext**, hay hook muộn hơn sẽ dễ triển khai hơn?
2. Listener đã được đăng ký trước `run(...)` bằng cơ chế phù hợp chưa?
3. Toàn bộ logic có chỉ phụ thuộc `Environment`/tham số khởi động, không phụ thuộc bean chưa tạo không?
4. Nếu đọc cấu hình, giá trị và ưu tiên `PropertySource` đã được kiểm chứng ở đúng thời điểm chưa?
5. Có tránh log secret và tránh tác vụ blocking tại thời điểm startup không?
6. Có cần `EnvironmentPostProcessor` nếu đang chỉnh sửa nguồn cấu hình không?
7. Khi khởi động lại hoặc chạy nhiều context, logic có an toàn khi lặp không?
8. Đã kiểm thử input có/không có property và trường hợp cấu hình sai chưa?

**Ghi nhớ:** `ApplicationEnvironmentPreparedEvent` cho phép xử lý **Environment rất sớm** trong startup của Spring Boot. Hãy đăng ký listener **trước khi chạy SpringApplication**, dùng nó cho trách nhiệm bootstrap ngắn gọn và chờ event muộn hơn khi cần bean, context hoặc trạng thái ready.

## Tài liệu tham khảo

- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners): danh sách event và hướng dẫn đăng ký listener trước khi tạo context.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn property, độ ưu tiên và cấu hình qua command line.
- [Spring Boot — Customize the Environment or ApplicationContext](https://docs.spring.io/spring-boot/how-to/application.html): cách đăng ký `ApplicationListener`, `ApplicationContextInitializer` và `EnvironmentPostProcessor`.
- [Spring Boot API — ApplicationEnvironmentPreparedEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html): kiểu event và thông tin được cung cấp.
