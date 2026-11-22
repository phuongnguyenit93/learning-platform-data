# SpringApplicationRunListener và các callback của quá trình run

## 1. SpringApplicationRunListener là gì, và vì sao cần hiểu nó?

Một ứng dụng Spring Boot thường bắt đầu ở lệnh:

```java
SpringApplication.run(DemoApplication.class, args);
```

Lệnh này trông ngắn nhưng bên trong có nhiều giai đoạn: tạo cấu hình môi trường, chọn và tạo `ApplicationContext`, nạp bean definition, `refresh()` context, chạy `ApplicationRunner` hoặc `CommandLineRunner` và thông báo rằng ứng dụng đã sẵn sàng. Trong thực tế, đôi khi ta cần **quan sát hoặc tham gia vào những thời điểm sớm này**, trước khi các bean ứng dụng có mặt.

`org.springframework.boot.SpringApplicationRunListener` là **điểm mở rộng cho chính một lần gọi `SpringApplication.run(...)`**. Spring Boot tìm các implementation của interface này bằng `SpringFactoriesLoader`, tạo một instance cho mỗi lần chạy, rồi gọi các callback tương ứng trong quy trình khởi động.

Hãy hình dung ba lớp trách nhiệm:

1. **`SpringApplication`** điều phối một lần khởi chạy và xử lý thành công hoặc thất bại.
2. **`SpringApplicationRunListener`** nhận các mốc của chính quy trình `run`: đã bắt đầu, đã có `Environment`, đã chuẩn bị context, đã nạp nguồn bean, đã khởi động, đã hoàn thành runner hoặc đã gặp lỗi.
3. **`ApplicationContext`** quản lý bean, cấu hình, sự kiện và tài nguyên sau khi được xây dựng; nhiều callback đầu tiên diễn ra **trước khi context có thể sử dụng đầy đủ**.

Ứng dụng bình thường **không bắt buộc** phải tự viết `SpringApplicationRunListener`. Spring Boot đã có một implementation nội bộ quan trọng tên `EventPublishingRunListener` để biến các mốc khởi chạy thành những sự kiện `ApplicationStartingEvent`, `ApplicationReadyEvent`... Điểm mở rộng này hữu ích khi làm hạ tầng dùng chung, đo thời gian startup, chuẩn bị thông tin bootstrap rất sớm hoặc tích hợp cơ chế quan sát khởi động theo một hợp đồng có thứ tự rõ ràng.

**Phân biệt:** callback `ready(...)` của listener chỉ báo một mốc trong tiến trình `run`. Nó không thay thế health check, readiness probe của môi trường triển khai hoặc xác nhận rằng mọi dịch vụ bên ngoài đều sẵn sàng.

## 2. Chuỗi callback chuẩn khi khởi động thành công

Trong Spring Boot **3.3.x**, những phương thức cần nhớ là:

```text
SpringApplication.run(args)
    |
    v
starting(bootstrapContext)
    |
    v
Chuẩn bị và hoàn thiện Environment
    |
    v
environmentPrepared(bootstrapContext, environment)
    |
    v
Tạo và chuẩn bị ApplicationContext
    |
    v
contextPrepared(context)
    |
    v
Nạp các source / bean definitions vào context
    |
    v
contextLoaded(context)
    |
    v
refresh() ApplicationContext
    |  - BeanFactoryPostProcessor, BeanPostProcessor
    |  - khởi tạo singleton thích hợp
    |  - khởi động web server khi là ứng dụng web
    v
started(context, timeTaken)
    |
    v
Gọi ApplicationRunner / CommandLineRunner
    |
    v
ready(context, timeTaken)
    |
    v
SpringApplication.run trả về context
```

Nếu một giai đoạn thuộc quá trình `run` gặp exception, Spring Boot đi vào đường xử lý thất bại và có thể gọi:

```text
failed(context, exception)
```

**`failed(...)` là nhánh lỗi, không phải bước được gọi sau `ready(...)` trên đường khởi động thành công.** Với lỗi xảy ra rất sớm, `context` truyền vào `failed` có thể là `null`.

Bảng đầy đủ:

| Callback trong Spring Boot 3.3 | Thời điểm | Dữ liệu đã sẵn sàng | Việc phù hợp |
| --- | --- | --- | --- |
| `starting(ConfigurableBootstrapContext)` | Ngay đầu `run` | Bootstrap context; `Environment` ứng dụng chưa chuẩn bị hoàn tất | Đánh dấu mốc thời gian, khởi tạo bootstrap nhẹ |
| `environmentPrepared(ConfigurableBootstrapContext, ConfigurableEnvironment)` | Sau chuẩn bị environment, trước tạo application context | `Environment` và nguồn cấu hình đã được chuẩn bị cho giai đoạn này | Đọc profile/property cần thiết, quan sát cấu hình không nhạy cảm |
| `contextPrepared(ConfigurableApplicationContext)` | Context vừa được tạo, chuẩn bị xong, trước nạp sources | Có đối tượng context, environment liên kết | Quan sát loại context, thực hiện phần chuẩn bị phù hợp |
| `contextLoaded(ConfigurableApplicationContext)` | Đã nạp nguồn bean vào context, **trước `refresh`** | Bean definitions đã được nạp theo quy trình chuẩn bị | Kiểm tra metadata có kiểm soát, ghi mốc trước refresh |
| `started(ConfigurableApplicationContext, Duration)` | Context đã refresh, trước khi chạy runners | Context đã khởi tạo; có thời gian khởi động nếu đo được | Quan sát context khởi động, thống kê startup |
| `ready(ConfigurableApplicationContext, Duration)` | Sau các runners, ngay trước khi `run` kết thúc | Các `ApplicationRunner` và `CommandLineRunner` đã được gọi xong thành công | Xác nhận giai đoạn boot run hoàn thành, đo thời gian đến ready |
| `failed(ConfigurableApplicationContext, Throwable)` | Khi khởi động gặp lỗi | Throwable; context có thể `null` | Ghi chẩn đoán lỗi an toàn, phục vụ telemetry |

Những callback này được khai báo là **default methods** trong interface ở Spring Boot 3.3. Implementation chỉ cần override các mốc muốn xử lý; bảng vẫn có ích để hiểu toàn bộ vòng đời.

## 3. Chữ ký chính xác của API Spring Boot 3.3

Các phương thức liên quan, viết rút gọn dưới dạng một interface để đọc:

```java
public interface SpringApplicationRunListener {

    default void starting(ConfigurableBootstrapContext bootstrapContext) { }

    default void environmentPrepared(
            ConfigurableBootstrapContext bootstrapContext,
            ConfigurableEnvironment environment) { }

    default void contextPrepared(ConfigurableApplicationContext context) { }

    default void contextLoaded(ConfigurableApplicationContext context) { }

    default void started(
            ConfigurableApplicationContext context,
            Duration timeTaken) { }

    default void ready(
            ConfigurableApplicationContext context,
            Duration timeTaken) { }

    default void failed(
            ConfigurableApplicationContext context,
            Throwable exception) { }
}
```

Đây là **bản diễn giải chữ ký**, lược bỏ import, Javadoc và các phần chi tiết của thư viện. Khi viết mã thực, import:

```java
import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
```

Đặc biệt chú ý các thay đổi theo phiên bản:

- Spring Boot 3.3 dùng `starting(ConfigurableBootstrapContext)`, **không phải** `starting()` kiểu cũ.
- `environmentPrepared(...)` nhận **hai** tham số, bao gồm `ConfigurableBootstrapContext`, **không phải** chữ ký chỉ nhận `ConfigurableEnvironment` của các phiên bản rất cũ.
- `started` và `ready` đều có thêm `Duration timeTaken`; phương thức có một tham số context không còn là chữ ký để override trong 3.3.
- Thay vì dùng callback `finished(...)` từ tài liệu Spring Boot 1.x, Spring Boot 3.3 phân biệt `ready(...)` và `failed(...)`.

Khi IDE báo “method does not override or implement”, hãy kiểm tra đúng phiên bản Spring Boot dependency và chữ ký hiện hành trước khi sửa bừa tên callback.

## 4. Điều gì có thể và chưa thể làm ở từng mốc?

### 4.1. starting: điểm sớm nhất

`starting(...)` xuất hiện ngay khi `SpringApplication.run(...)` bắt đầu. Lúc này **chưa có `ApplicationContext`** để gọi `getBean(...)`; cấu hình `application.properties` cũng chưa đi qua đầy đủ quá trình chuẩn bị `Environment`.

Nên dùng để:

- Ghi mốc khởi đầu cho phép đo thời gian.
- Khởi tạo tài nguyên bootstrap thật sự cần trước context, nếu có và đã hiểu vòng đời.
- Gắn dữ liệu bootstrap có giới hạn, thay vì cố truy cập bean nghiệp vụ.

Không nên dùng để:

- Gọi bean với `@Autowired`.
- Giả định profile cuối cùng đã được xác định.
- Thực hiện tác vụ mạng kéo dài hoặc logic nghiệp vụ.
- Giả định hệ thống logging đã sẵn sàng với toàn bộ cấu hình ở mọi môi trường.

`ConfigurableBootstrapContext` là đối tượng riêng cho hạ tầng bootstrap. Nó có thể hỗ trợ đăng ký/lấy đối tượng bootstrap được chuẩn bị trước khi context hoàn thiện. **Nó không phải `ApplicationContext` hay `BeanFactory` đầy đủ**, vì thế `bootstrapContext.get(...)` (khi dùng) không có ý nghĩa như tra cứu bean thông thường.

### 4.2. environmentPrepared: đọc cấu hình trước khi có context

`environmentPrepared(bootstrapContext, environment)` được gọi khi environment đã được Spring Boot chuẩn bị cho lần chạy và **trước khi tạo context**.

Ví dụ:

```java
@Override
public void environmentPrepared(
        ConfigurableBootstrapContext bootstrapContext,
        ConfigurableEnvironment environment) {

    String name = environment.getProperty(
            "spring.application.name", "unnamed");
    System.out.println("Application name = " + name);
}
```

Đây là **đoạn method đặt bên trong class implement `SpringApplicationRunListener`**, không phải chương trình Java độc lập. Nó có thể đọc property hoặc profile trong phạm vi thích hợp.

Một số chi tiết:

- `ConfigurableEnvironment` cho phép quan sát `PropertySources`, active profiles và property resolution.
- Cấu hình có thể đến từ file, biến môi trường, system properties, command-line arguments và các nguồn được đưa vào giai đoạn bootstrap.
- Tránh in toàn bộ `environment.getPropertySources()` hoặc environment variables. Chúng có thể chứa bí mật.
- Không nên giả định mọi cấu hình có thể được thay tùy ý ở bước này mà không ảnh hưởng tính nhất quán của những thành phần đã chạy trước đó.
- `EnvironmentPostProcessor` là điểm mở rộng chuyên trách hơn nếu mục tiêu chính là **thêm hoặc điều chỉnh PropertySource** trong quá trình chuẩn bị environment.

### 4.3. contextPrepared: context đã tồn tại, sources chưa nạp

Ở mốc `contextPrepared(context)`, `SpringApplication` đã tạo và chuẩn bị context, đồng thời áp dụng những `ApplicationContextInitializer` phù hợp theo thứ tự nội bộ. Tuy nhiên **nguồn bean chính chưa được nạp vào context theo bước tiếp theo của quy trình**.

Các thao tác hợp lý:

- Quan sát tên lớp context.
- Ghi mốc bootstrap.
- Sử dụng các khả năng cấu hình context sớm một cách thận trọng khi đây thực sự là hạ tầng framework.

Các thao tác cần tránh:

```java
// Sai kỳ vọng nếu bean chưa được đăng ký/tạo:
MyService service = context.getBean(MyService.class);
service.run();
```

Không đảm bảo bean này tồn tại lúc `contextPrepared`. Nếu cần điều chỉnh context trước refresh, `ApplicationContextInitializer` thường có ngữ nghĩa rõ ràng hơn và được thiết kế dành cho nhiệm vụ đó.

### 4.4. contextLoaded: có definitions, chưa refresh

`contextLoaded(context)` được gọi sau khi các nguồn ứng dụng đã được nạp và **trước `refresh()`**. Đây là thời điểm đặc biệt dễ nhầm “đã load” thành “đã khởi tạo”.

Trong giai đoạn trước refresh:

- Có thể đã có các bean definition được đăng ký.
- Không đảm bảo các singleton đã được khởi tạo.
- `BeanFactoryPostProcessor` và `BeanPostProcessor` chưa hoàn tất toàn bộ công việc refresh.
- Những bean dùng `@ConfigurationProperties`, proxy, auto-configuration hoặc lifecycle callback chưa nên được coi là sẵn sàng để sử dụng như runtime.

Vì vậy đừng gọi nghiệp vụ hoặc `getBean(...)` bừa bãi trong `contextLoaded`. Việc tạo bean quá sớm có thể làm mất các bước xử lý framework mà bean cần trải qua.

### 4.5. started: refresh xong, runner chưa chạy

`started(context, timeTaken)` báo context đã được refresh, ứng dụng đã hoàn tất giai đoạn khởi tạo chính, **nhưng `ApplicationRunner` và `CommandLineRunner` chưa được gọi**.

Đây là mốc có thể dùng để đánh dấu thời gian sau refresh hoặc quan sát cấu hình đã tạo. Tuy nhiên một tác vụ trong runner có thể còn cần tạo bảng, kiểm tra dữ liệu hoặc chuẩn bị một phần trạng thái; không thể dùng `started` như bằng chứng rằng mọi công việc startup đã hoàn tất.

`Duration timeTaken` có thể là `null` nếu không có dữ liệu thời gian. Không gọi ngay `timeTaken.toMillis()` mà bỏ qua khả năng này.

### 4.6. ready: sau runner, ngay trước khi run trả về

`ready(context, timeTaken)` được gọi sau khi Spring Boot chạy xong các runner trong lượt startup thành công, ngay trước khi `SpringApplication.run(...)` hoàn thành.

Nên hiểu mốc này là: **quy trình `run` đã đi tới đoạn cuối thành công**. Nó không khẳng định mọi kết nối bên ngoài luôn khỏe, queue đã được xử lý hết hay load balancer đã định tuyến traffic về instance.

Nếu muốn quan sát readiness ở môi trường triển khai, dùng các tín hiệu health/readiness phù hợp. Một `ApplicationReadyEvent` cũng được phát gần thời điểm tương ứng qua cơ chế listener sự kiện Spring Boot.

### 4.7. failed: nhận lỗi ở mọi thời điểm có thể

`failed(context, exception)` có thể được gọi khi exception xảy ra ở nhiều giai đoạn: chuẩn bị environment, tạo context, refresh, chạy runner...

- `exception` là lỗi Spring Boot đang xử lý.
- `context` **có thể bằng `null`** nếu thất bại trước khi tạo context.
- `ready` sẽ không đạt được trên đường chạy thất bại đó.
- Dùng chính lỗi này để bổ sung thông tin chẩn đoán; không tự động “nuốt” exception hoặc cố chạy tiếp ứng dụng nửa khởi tạo.

Nếu xử lý thất bại trong callback này lại ném thêm lỗi, thông tin ban đầu có thể bị che lấp hoặc làm quá trình xử lý phức tạp. Nên giữ phần xử lý nhẹ, không phát sinh lỗi mới, không làm lộ credentials.

## 5. Đăng ký SpringApplicationRunListener bằng spring.factories

Điểm khác biệt kỹ thuật quan trọng là **SpringApplicationRunListener được tải bởi `SpringFactoriesLoader` từ classpath, rất sớm trong startup**. Việc chỉ thêm `@Component` vào class không đủ để Boot chọn nó làm run listener.

Cấu trúc một ứng dụng ví dụ:

```text
src/
  main/
    java/
      demo/startup/
        DemoApplication.java
        TraceRunListener.java
    resources/
      META-INF/
        spring.factories
      application.properties
```

Nội dung `src/main/resources/META-INF/spring.factories`:

```properties
org.springframework.boot.SpringApplicationRunListener=demo.startup.TraceRunListener
```

Chìa khóa của file là **tên đầy đủ interface** `org.springframework.boot.SpringApplicationRunListener`. Giá trị là **tên class đầy đủ** của implementation.

Spring Boot dùng `SpringFactoriesLoader` để tìm và tạo những listener được đăng ký. Mỗi lần gọi `run(...)` sẽ có một instance mới của `SpringApplicationRunListener` tương ứng với lượt khởi chạy đó.

**Constructor bắt buộc:** implementation cần có một **public constructor** nhận chính xác `SpringApplication` và `String[]` (theo thứ tự đó). Điều này rất khác với một bean được tạo qua injection thông thường.

```java
public TraceRunListener(SpringApplication application, String[] args) {
    // Lưu thông tin phù hợp hoặc khởi tạo hạ tầng nhẹ.
}
```

Không dùng constructor chỉ có zero arguments hay constructor chỉ có `ApplicationContext` rồi mong `SpringFactoriesLoader` tự inject như Spring IoC. Khi chưa tới giai đoạn tạo context, Spring IoC cũng chưa sẵn sàng để thực hiện việc đó.

**Phân biệt với cách đăng ký `ApplicationListener`**: để đăng ký một `ApplicationListener` thông qua `spring.factories`, key là `org.springframework.context.ApplicationListener`. Hai key phục vụ hai interface khác nhau. Một class implement `SpringApplicationRunListener` không tự động là `ApplicationListener<ApplicationEvent>` và ngược lại.

Nếu xây một thư viện dùng chung, file `META-INF/spring.factories` nên được đóng trong JAR thư viện. Khi thư viện đó nằm trên classpath, loader có thể tìm thấy đăng ký của nó. Điều này khiến hook khởi động ảnh hưởng nhiều ứng dụng, nên phải làm rõ phiên bản tương thích và tránh tác dụng phụ không cần thiết.

## 6. Ví dụ chạy được với Spring Boot 3.3 và Java 17+

Ví dụ này sử dụng **Spring Boot 3.3**, Java 17 trở lên, và dependency `spring-boot-starter`. Chọn ứng dụng không có web server để tập trung quan sát startup; cùng loại listener vẫn dùng được khi ứng dụng là `SERVLET` hoặc `REACTIVE`.

### 6.1. Lớp SpringApplicationRunListener

Tạo file `src/main/java/demo/startup/TraceRunListener.java`:

```java
package demo.startup;

import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;

public final class TraceRunListener implements SpringApplicationRunListener {

    private final int argumentCount;

    public TraceRunListener(SpringApplication application, String[] args) {
        this.argumentCount = args.length;
    }

    @Override
    public void starting(ConfigurableBootstrapContext bootstrapContext) {
        System.out.println("RUN LISTENER: starting, args=" + argumentCount);
    }

    @Override
    public void environmentPrepared(
            ConfigurableBootstrapContext bootstrapContext,
            ConfigurableEnvironment environment) {
        String name = environment.getProperty(
                "spring.application.name", "unnamed");
        System.out.println("RUN LISTENER: environmentPrepared, app=" + name);
    }

    @Override
    public void contextPrepared(ConfigurableApplicationContext context) {
        System.out.println("RUN LISTENER: contextPrepared, type="
                + context.getClass().getSimpleName());
    }

    @Override
    public void contextLoaded(ConfigurableApplicationContext context) {
        System.out.println("RUN LISTENER: contextLoaded");
    }

    @Override
    public void started(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("RUN LISTENER: started, elapsed="
                + formatDuration(timeTaken));
    }

    @Override
    public void ready(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("RUN LISTENER: ready, elapsed="
                + formatDuration(timeTaken));
    }

    @Override
    public void failed(
            ConfigurableApplicationContext context, Throwable exception) {
        System.out.println("RUN LISTENER: failed, cause="
                + exception.getClass().getSimpleName()
                + ", contextPresent=" + (context != null));
    }

    private static String formatDuration(Duration duration) {
        return duration == null ? "unknown" : duration.toMillis() + "ms";
    }
}
```

Giải thích thiết kế:

- Class và constructor đều `public` để loader có thể tạo instance.
- Constructor nhận đúng `SpringApplication` và `String[]`. Ví dụ chỉ lưu **số lượng** tham số, không in giá trị tham số vì chúng có thể chứa thông tin nhạy cảm.
- Các callback đầu không gọi bean vì context chưa sẵn sàng.
- `contextPrepared(...)` chỉ đọc **tên lớp** context; không gọi `getBean`.
- `started` và `ready` xử lý được `Duration == null`.
- `failed` kiểm tra context có null hay không.
- `System.out.println` dùng để minh họa trình tự. Trong hệ thống thực cần chọn logging/telemetry theo yêu cầu vận hành, đặc biệt ở giai đoạn logging chưa được cấu hình hoàn toàn.

Đối tượng `SpringApplication application` trong constructor không cần sử dụng cho ví dụ; vẫn phải giữ tham số đó đúng chữ ký.

### 6.2. Entry point và runner

Tạo file `src/main/java/demo/startup/DemoApplication.java`:

```java
package demo.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demoRunner() {
        return args -> {
            System.out.println("APPLICATION RUNNER: called");

            if (args.containsOption("demo.fail")) {
                throw new IllegalStateException("demonstration failure");
            }
        };
    }
}
```

`ApplicationRunner` được gọi **sau `started` và trước `ready`**. Đoạn kiểm tra option `--demo.fail` cho phép chủ động tạo lỗi trong runner để quan sát callback `failed`.

Cấu hình `src/main/resources/application.properties`:

```properties
spring.application.name=run-listener-demo
spring.main.web-application-type=none
```

Với `NONE`, ứng dụng không tự mở HTTP port; điều này không thay đổi chuỗi callback cơ bản của `SpringApplicationRunListener`.

Trong `src/main/resources/META-INF/spring.factories`, đăng ký:

```properties
org.springframework.boot.SpringApplicationRunListener=demo.startup.TraceRunListener
```

Ví dụ dependency trong `build.gradle` của **dự án đã áp dụng Spring Boot Gradle plugin**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Để chạy với Gradle wrapper của dự án:

```bash
./gradlew bootRun
```

Hoặc khi đã tạo executable JAR:

```bash
./gradlew bootJar
java -jar build/libs/<ten-jar-thuc-te>.jar
```

Dòng thứ hai là **cú pháp minh họa**: thay `<ten-jar-thuc-te>` bằng tên file thực tế do `bootJar` sinh ra, không giữ dấu ngoặc nhọn. Với Maven, dùng cách build/run tương ứng.

### 6.3. Kết quả đường thành công

Khi chạy không truyền `--demo.fail`, các dòng do mã ví dụ in ra có thứ tự tương đối:

```text
RUN LISTENER: starting, args=0
RUN LISTENER: environmentPrepared, app=run-listener-demo
RUN LISTENER: contextPrepared, type=AnnotationConfigApplicationContext
RUN LISTENER: contextLoaded
RUN LISTENER: started, elapsed=<thoi-gian-ms>
APPLICATION RUNNER: called
RUN LISTENER: ready, elapsed=<thoi-gian-ms>
```

Các phần `<thoi-gian-ms>` là vị trí minh họa vì thời gian thực tế thay đổi theo máy; mã in số mili giây hoặc `unknown` nếu thời gian không được cung cấp. Spring Boot có thể in thêm banner, log và các dòng khác xen vào. Không nên dùng ví dụ để khẳng định stdout đầy đủ chỉ gồm bảy dòng trên.

Với cấu hình `spring.main.web-application-type=none` và không có classpath web phù hợp, tên context mặc định thường là `AnnotationConfigApplicationContext`. Nếu dự án chủ động cung cấp `ApplicationContextFactory` khác thì tên có thể khác.

Ý nghĩa quan trọng của thứ tự:

- Hai callback đầu xảy ra khi chưa có context.
- `contextPrepared` rồi `contextLoaded` xảy ra trước refresh.
- `started` chứng minh refresh đã đi tới cuối, nhưng runner vẫn chưa chạy.
- `ready` xuất hiện khi runner đã chạy thành công.

### 6.4. Kết quả nhánh lỗi trong runner

Để tạo lỗi có kiểm soát:

```bash
./gradlew bootRun --args='--demo.fail'
```

Nếu dùng shell không hỗ trợ dấu nháy đơn theo cách trên, đổi cú pháp trích dẫn cho đúng môi trường. Có thể truyền `--demo.fail=true` và vẫn được `ApplicationArguments.containsOption("demo.fail")` nhận diện.

Phần dòng liên quan có dạng:

```text
RUN LISTENER: starting, args=1
RUN LISTENER: environmentPrepared, app=run-listener-demo
RUN LISTENER: contextPrepared, type=AnnotationConfigApplicationContext
RUN LISTENER: contextLoaded
RUN LISTENER: started, elapsed=<thoi-gian-ms>
APPLICATION RUNNER: called
RUN LISTENER: failed, cause=IllegalStateException, contextPresent=true
```

`ready` **không được gọi** trên đường thất bại này. Exception do runner ném khiến `SpringApplication.run` thất bại; Gradle có thể báo tác vụ chạy thất bại hoặc JVM kết thúc với mã lỗi. Đây là kết quả được mong đợi của thí nghiệm lỗi, không phải ứng dụng đã sẵn sàng.

Dạng exception mà `failed` nhìn thấy có thể khác khi lỗi phát sinh ở bước khác hoặc được framework bao bọc; không nên dựa vào tên `IllegalStateException` cho mọi sự cố.

## 7. EventPublishingRunListener và mối liên hệ với SpringApplicationEvent

Spring Boot dùng một implementation nội bộ tên:

```text
org.springframework.boot.context.event.EventPublishingRunListener
```

Nó là cầu nối giữa các callback `SpringApplicationRunListener` và hệ thống **Spring application events**. Khi một callback chạy, listener nội bộ phát sự kiện tương ứng để những `ApplicationListener<?>` thích hợp có thể nhận thông báo.

| Callback | Sự kiện Boot tương ứng thường được phát |
| --- | --- |
| `starting` | `ApplicationStartingEvent` |
| `environmentPrepared` | `ApplicationEnvironmentPreparedEvent` |
| `contextPrepared` | `ApplicationContextInitializedEvent` |
| `contextLoaded` | `ApplicationPreparedEvent` |
| `started` | `ApplicationStartedEvent` |
| `ready` | `ApplicationReadyEvent` |
| `failed` | `ApplicationFailedEvent` |

Đây là các **event do Boot phát để quan sát tiến trình**, khác với việc gọi trực tiếp phương thức run listener của bạn. Nếu một ứng dụng có cả `TraceRunListener` tùy chỉnh và listener phát event nội bộ, cả hai cùng tham gia vào các mốc; không cần tự phát lại các event kể trên.

Ngoài chuỗi này còn có các sự kiện của Spring Framework như `ContextRefreshedEvent` và sự kiện web server như `ServletWebServerInitializedEvent` hoặc `ReactiveWebServerInitializedEvent`. Chúng có thể xuất hiện trong giai đoạn refresh, **không phải tất cả đều là callback riêng của `SpringApplicationRunListener`**.

**Vì sao phân biệt quan trọng?** `ApplicationStartingEvent` được phát trước khi `ApplicationContext` tồn tại. Một bean ứng dụng kiểu:

```java
@Component
class LateEventListener {

    @EventListener
    void onStarting(ApplicationStartingEvent event) {
        // Không dựa vào bean @Component để nhận event cực sớm này.
    }
}
```

không thể được coi là cách đáng tin để nhận sự kiện cực sớm, vì bean chưa được khởi tạo tại thời điểm phát. Đoạn trên là ví dụ minh họa vấn đề, cần import tương ứng và không nên dùng làm cơ chế triển khai.

Để nhận sự kiện sớm, bạn có thể đăng ký một `ApplicationListener` **trước `run(...)`** hoặc dùng cấu hình `spring.factories` đúng key cho `ApplicationListener`.

## 8. Phân biệt SpringApplicationRunListener với những điểm mở rộng khác

Các API này đều liên quan startup nhưng không thay thế hoàn toàn cho nhau:

| Công cụ | Khi nào hoạt động? | Vai trò chính |
| --- | --- | --- |
| `SpringApplicationRunListener` | Nhiều mốc xuyên suốt `SpringApplication.run`, cả trước context và khi lỗi | Theo dõi/điều phối ở mức run |
| `ApplicationListener<ApplicationEvent>` | Khi một event được phát và listener đã được đăng ký | Phản ứng sự kiện được phát |
| `@EventListener` trên bean | Sau khi cơ chế xử lý listener và bean đã sẵn sàng; tùy event | Phản ứng sự kiện từ bean ứng dụng |
| `ApplicationContextInitializer` | Khi context đã được tạo nhưng trước refresh và trước các source chính được load | Cấu hình context sớm |
| `EnvironmentPostProcessor` | Trong giai đoạn chuẩn bị environment | Tùy chỉnh nguồn property, profile hoặc environment |
| `BeanFactoryPostProcessor` | Trong refresh, trước khởi tạo phần lớn bean thông thường | Điều chỉnh bean definitions |
| `BeanPostProcessor` | Trong lifecycle khởi tạo từng bean | Thực hiện xử lý, proxy hoặc điều chỉnh bean |
| `ApplicationRunner` / `CommandLineRunner` | Sau refresh và trước ready | Chạy công việc khởi tạo dựa trên bean |
| `ApplicationReadyEvent` listener | Ở cuối startup thành công | Phản ứng khi Spring Boot đã hoàn tất quy trình chạy |
| `ApplicationStartup` / Actuator startup | Thu thập thông tin bước khởi động khi được cấu hình | Phân tích chi phí startup, không phải hook thay thế mọi callback |

Ví dụ, nếu nhu cầu là **nạp một PropertySource mới**, `EnvironmentPostProcessor` thường rõ mục đích hơn `SpringApplicationRunListener`. Nếu nhu cầu là **chạy truy vấn kiểm tra dữ liệu sau khi bean đã được dựng**, `ApplicationRunner` thường đúng thời điểm hơn. Nếu cần **phát hiện một exception trong quá trình `run` ngay cả khi context chưa hình thành**, `failed(...)` của run listener có lợi thế.

### 8.1. Không nhầm addListeners với run listener

API:

```java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.addListeners(new SomeApplicationListener());
application.run(args);
```

là dành cho `org.springframework.context.ApplicationListener`. Nó không phải cơ chế đăng ký `SpringApplicationRunListener` bất kỳ qua một overload tương ứng. Với run listener tùy chỉnh, hãy dùng `META-INF/spring.factories` theo hợp đồng `SpringFactoriesLoader`.

### 8.2. Không nhầm contextPrepared với contextLoaded

Hai callback rất gần nhau nhưng **khác giai đoạn**:

```text
Tạo context
  -> áp dụng các initializer phù hợp
  -> contextPrepared
  -> nạp sources/bean definitions
  -> contextLoaded
  -> refresh
```

Nếu công việc của bạn cần bean đã khởi tạo, **cả hai mốc đều còn quá sớm**. Chọn runner, event phù hợp hoặc bean lifecycle thay vì ép `getBean(...)` chạy ở đây.

### 8.3. Không nhầm started với ready

`started(...)` đến **trước** runner, `ready(...)` đến **sau** runner. Nếu runner thất bại:

```text
started -> runner -> exception -> failed
                    |
                    +-- không có ready
```

Vì vậy một dashboard quan sát startup không nên đếm `started` là “application ready” khi hệ thống cần toàn bộ runner hoàn tất. Ngược lại, `ready` là mốc cuối của Spring Boot `run`, chưa phải sự thay thế cho health/readiness probe dài hạn.

## 9. Thời gian khởi động: dùng Duration đúng nghĩa

Hai callback cuối đường thành công có `Duration timeTaken`:

```java
@Override
public void started(
        ConfigurableApplicationContext context, Duration timeTaken) {
    if (timeTaken != null) {
        System.out.println("Startup ms=" + timeTaken.toMillis());
    }
}

@Override
public void ready(
        ConfigurableApplicationContext context, Duration timeTaken) {
    if (timeTaken != null) {
        System.out.println("Ready ms=" + timeTaken.toMillis());
    }
}
```

Đây là các phương thức **thay thế/cài đặt bên trong listener**, có import như mục 3.

Giải thích:

- `started` cho biết mốc sau khi context refresh thành công, trước các runner.
- `ready` là mốc sau các runner và sát lúc `run` hoàn tất.
- Khoảng chênh giữa hai phép đo có thể phản ánh công việc runners và các bước khác giữa hai mốc, nhưng không nên coi là phép đo chuẩn cho riêng một runner nếu có nhiều hook/công việc xen vào.
- `Duration` là thời gian trôi qua, không phải đồng hồ ngày giờ. Dùng `Instant` hoặc đồng hồ phù hợp nếu cần timestamp riêng.
- Nếu cần phân tích chi tiết hàng trăm bước khởi tạo bean, sử dụng hạ tầng `ApplicationStartup`, `BufferingApplicationStartup` hoặc Actuator startup endpoint khi được cấu hình. Một run listener chỉ cho các mốc lớn.

Nếu thu thập metric trong môi trường production, tránh block luồng bootstrap để gửi qua mạng ở callback. Tốt hơn là ghi nhận dữ liệu nhẹ rồi chuyển cho cơ chế telemetry phù hợp khi nó đã hoạt động.

## 10. BootstrapContext: tại sao chưa có BeanFactory vẫn có ngữ cảnh?

Trong hai callback đầu, thay vì `ApplicationContext`, interface trao cho người dùng `ConfigurableBootstrapContext`. Đối tượng này hỗ trợ chuẩn bị **dữ liệu hoặc tài nguyên cần từ giai đoạn rất sớm** và truyền chúng qua các bước bootstrap theo cơ chế mà Boot hỗ trợ.

Hãy phân biệt:

| `ConfigurableBootstrapContext` | `ApplicationContext` |
| --- | --- |
| Có sẵn rất sớm trong quá trình startup | Chỉ được tạo sau khi `Environment` đã chuẩn bị |
| Dành cho thành phần bootstrap có vòng đời riêng | Dành cho container bean và ứng dụng |
| Không dùng như `getBean(...)` của Spring IoC | Có `getBean(...)`, injection và lifecycle |
| Có cơ chế đăng ký/tra cứu bootstrap instance | Có BeanFactory, bean definitions và scope |
| Có thể được đóng/hoàn tất theo quy trình bootstrap | Sống theo vòng đời application context |

Khi một resource thực sự cần chia sẻ giữa giai đoạn chuẩn bị environment và bước dựng context, có thể xem các API bootstrap registry/context như `register(...)` hoặc `addCloseListener(...)` theo Javadoc chính thức của phiên bản đang dùng. Tuy nhiên việc dùng chúng đòi hỏi hiểu thứ tự tạo/đóng và sở hữu tài nguyên. **Không biến bootstrap context thành nơi cất mọi singleton nghiệp vụ**.

Nếu chỉ cần đọc vài cấu hình ở `environmentPrepared` thì dùng `ConfigurableEnvironment` là đủ. Đừng tạo hạ tầng bootstrap phức tạp khi không có nhu cầu.

## 11. Cách kiểm tra SpringFactoriesLoader đã tìm thấy listener

Nếu mã `TraceRunListener` đúng nhưng không có dòng `RUN LISTENER` nào, hãy kiểm tra từ gốc:

1. File phải ở đúng đường dẫn `src/main/resources/META-INF/spring.factories`, với tên chính xác, chữ hoa/thường phù hợp.
2. Key phải là `org.springframework.boot.SpringApplicationRunListener`. Đừng ghi nhầm key `org.springframework.context.ApplicationListener`.
3. Giá trị phải là **tên class đầy đủ** (`demo.startup.TraceRunListener`), đúng package đã khai báo.
4. Class phải là `public`, có **public constructor `(SpringApplication, String[])`**, không chỉ có constructor mặc định.
5. Class phải có trên **runtime classpath** của ứng dụng thực tế.
6. Kiểm tra có đang chạy JAR cũ chưa được đóng gói lại không.
7. Nếu đang tích hợp từ thư viện, xác nhận file `META-INF/spring.factories` của thư viện vẫn được bảo toàn trong artifact hoặc classpath, tránh bị bỏ khi đóng gói lại.
8. Nếu load thất bại, đọc exception từ `SpringFactoriesLoader` và stack trace gốc; không “chữa” bằng cách gắn `@Component`.

Kiểm tra tài nguyên trong executable JAR bằng lệnh minh họa:

```bash
jar tf build/libs/app.jar
```

Tìm trong output:

```text
BOOT-INF/classes/META-INF/spring.factories
BOOT-INF/classes/demo/startup/TraceRunListener.class
```

Đối với tên file JAR thực tế, thay `app.jar` bằng đúng artifact build. Hai entry trên là **ví dụ kỳ vọng** khi listener nằm trực tiếp trong source của ứng dụng; nếu listener được cung cấp từ dependency JAR, nó sẽ nằm trong dependency đó dưới `BOOT-INF/lib/...` của executable Boot JAR.

Nếu chỉ dùng Gradle `bootRun`, tài nguyên sẽ được tìm từ các thư mục/classes runtime classpath thay vì nhất thiết phải có `BOOT-INF/classes`.

## 12. Lỗi trong callback và khả năng gây hỏng startup

`SpringApplicationRunListener` chạy ngay trên luồng khởi động do Boot điều phối. Đây là quyền can thiệp mạnh, nên các lỗi trong callback có thể làm hỏng startup.

**Ví dụ không nên làm:**

```java
@Override
public void starting(ConfigurableBootstrapContext bootstrapContext) {
    // Truy cập DB hoặc HTTP đồng bộ kéo dài khi Environment
    // và ApplicationContext còn chưa được chuẩn bị đầy đủ.
    callRemoteService();
}
```

Đây là **minh họa phản ví dụ**, không phải đoạn biên dịch độc lập: `callRemoteService()` cố ý là một phương thức chưa định nghĩa. Điều cần học là tránh phụ thuộc mạng/bean trong hook quá sớm.

Khi mở rộng hạ tầng:

- Đảm bảo callback **nhanh và có thể dự đoán được**. Không chặn khởi động vì một dịch vụ quan sát bên ngoài tạm thời không truy cập được.
- Không giữ tham chiếu `ApplicationContext` vào biến static tồn tại lâu, dễ gây rò rỉ class loader và tài nguyên trong test hoặc môi trường reload.
- Không giả định chỉ có một lần `run` trong toàn JVM: ứng dụng test, context hierarchy hoặc các mô hình bootstrap khác có thể có nhiều instance.
- Không lưu trạng thái chia sẻ mutable không được đồng bộ hóa giữa nhiều instance hoặc nhiều context.
- Không in password, API token, URL chứa credential hoặc toàn bộ command-line arguments ra log.
- `failed(...)` cần an toàn khi context bằng `null`. Không cố gọi `context.getBean(...)` để ghi lỗi.
- Nếu callback ném exception, việc xử lý lỗi của Boot có thể còn gọi thêm callback thất bại; không nên phát sinh lỗi mới trong `failed(...)`.
- Khi bổ sung nhiều run listener, có thể cần kiểm soát thứ tự qua cơ chế ordering phù hợp của Spring Boot; **không phụ thuộc vào thứ tự liệt kê class tình cờ trong classpath**.

Đặc biệt, tránh dùng listener để “vá” các vấn đề có API riêng. Việc cấu hình bean thường phù hợp `@Configuration`; nạp property phù hợp `EnvironmentPostProcessor`; logic sau khi sẵn sàng phù hợp `ApplicationRunner` hoặc event.

## 13. So sánh ba thời điểm thường cần trong ứng dụng

Giả sử một ứng dụng cần ba nhiệm vụ: đọc nhãn môi trường để đặt tên log, đăng ký bean và khởi tạo dữ liệu.

| Nhu cầu | Thời điểm gợi ý | Lý do |
| --- | --- | --- |
| Đọc thông tin profile/config để thêm nhãn chẩn đoán khởi động | `environmentPrepared` hoặc điểm mở rộng chuyên dụng | Environment đã tồn tại; bean chưa cần tạo |
| Thêm/sửa bean definition trước khi singleton được khởi tạo | `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor` | Chính là API hạ tầng dành cho bean definitions |
| Chạy khởi tạo dữ liệu bằng repository bean | `ApplicationRunner` hoặc `CommandLineRunner` | Context đã refresh, bean thường đã sẵn sàng |
| Đo tổng thời gian tới ready | `ready` cùng `Duration` | Sau runners và ở cuối luồng startup |
| Quan sát exception dù context chưa tạo xong | `failed` | Có exception và cho phép context null |
| Kiểm tra tình trạng dịch vụ trong thời gian vận hành | Health/readiness indicator | Dữ liệu runtime, không chỉ trạng thái startup một lần |

Từ bảng này, không nên dùng `started` để chạy một migration dài: nếu nó có lỗi, luồng startup bị kéo dài hoặc thất bại ở một hook ít phù hợp; sử dụng công cụ quản lý schema/migration chuyên biệt sẽ rõ ràng hơn. Tương tự, không nên đưa xử lý nghiệp vụ vào `ready` chỉ vì đó là callback cuối cùng.

## 14. Kiểm chứng với sự kiện và runner: phương pháp thực hành

### Thực hành A: dự đoán thứ tự callback

Chạy ví dụ ở mục 6 và trả lời **trước khi xem output**:

- Listener nào xuất hiện trước: `contextLoaded` hay `started`?
- `ApplicationRunner` chạy trước hay sau `ready`?
- Nếu callback `contextPrepared` đã chạy, có chắc bean repository đã được tạo không?
- Vì sao `starting` không thể đọc `spring.application.name` chắc chắn từ environment đã nạp?
- Khi chạy với `--demo.fail`, các callback nào còn xuất hiện và callback nào biến mất?

Sau đó so sánh output của các dòng do `TraceRunListener` và `ApplicationRunner` in ra. Cần phân biệt log/banners của Spring Boot với các dòng do mã ví dụ tạo.

### Thực hành B: đổi kiểu ứng dụng

Nếu thay `spring.main.web-application-type=none` bằng web app hợp lệ có đủ starter web và server factory, quan sát `contextPrepared` in tên context khác, nhưng **thứ tự callback vẫn có cùng ý nghĩa**. Với Servlet web app mặc định của Spring Boot 3.3, tên có thể là `AnnotationConfigServletWebServerApplicationContext`. Với reactive web app phù hợp, có thể là `AnnotationConfigReactiveWebServerApplicationContext`.

Không ép `SERVLET` khi thiếu hạ tầng Servlet server rồi xem lỗi thiếu bean là hành vi “sai” của run listener. Listener vẫn phản ánh quá trình Boot, còn việc tạo web context phải có dependency thích hợp.

### Thực hành C: lỗi sớm so với lỗi trong runner

Trong môi trường thử nghiệm, so sánh hai lỗi:

1. Lỗi từ runner với `--demo.fail`: context đã được refresh; `started` xuất hiện; `failed` xuất hiện; `ready` không xuất hiện.
2. Lỗi khởi tạo trước khi context hoàn thành: tùy điểm lỗi, `contextPrepared` hoặc `contextLoaded` có thể chưa xuất hiện; `failed` phải xử lý được cả trường hợp context `null`.

Không cố tạo lỗi bằng cách phá dependency hay cấu hình production; chỉ cần thử trong ứng dụng demo biệt lập.

### Thực hành D: so sánh ApplicationListener

Tạo một `ApplicationListener<ApplicationReadyEvent>` đăng ký trước `run` hoặc qua `spring.factories` bằng đúng key `org.springframework.context.ApplicationListener`. So sánh thời điểm nhận `ApplicationReadyEvent` với callback `ready` của `SpringApplicationRunListener`.

Hãy trả lời: cái nào là callback trực tiếp trong giao diện run listener, cái nào là event được `EventPublishingRunListener` phát? Vì sao không cần tự định nghĩa cả hai nếu mục tiêu chỉ là ghi log “ready”?

## 15. Bảng lỗi và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra / xử lý |
| --- | --- | --- |
| Không callback nào chạy | `spring.factories` không được đóng gói, sai key hoặc sai tên class | Kiểm tra runtime classpath, entry trong JAR và key đầy đủ |
| Startup báo không tạo được listener | Thiếu constructor `public (SpringApplication, String[])` hoặc class không public | Sửa chữ ký constructor đúng với Boot 3.3 |
| IDE báo `@Override` sai | Dùng signature từ Spring Boot 1.x/2.x khác với 3.3 | So Javadoc 3.3 của `SpringApplicationRunListener` |
| `getBean(...)` thất bại trong `contextLoaded` | Context chưa refresh, bean chưa được tạo | Chuyển logic phụ thuộc bean sang runner hoặc lifecycle thích hợp |
| `getProperty(...)` trả giá trị không như dự kiến ở `starting` | Chưa có environment được chuẩn bị đầy đủ | Đọc trong `environmentPrepared` hoặc điểm mở rộng phù hợp |
| `started` có mà `ready` không có | Runner hoặc bước cuối startup gặp lỗi | Kiểm tra exception và `failed`; không báo READY |
| `failed` tự ném `NullPointerException` | Context chưa được tạo nhưng code vẫn dereference | Kiểm tra `context != null` trước khi sử dụng |
| Có hai nơi cùng thông báo startup | Vừa tự log trong run listener, vừa có `ApplicationListener`/Boot log | Chọn một nguồn metric/log chủ đạo, tránh ghi trùng |
| Callback chậm làm startup lâu | Gọi HTTP/DB đồng bộ trong hook | Chuyển sang cơ chế phù hợp, đo chi phí và giới hạn blocking |
| Test bị ghi log startup nhiều lần | Nhiều context hoặc nhiều lượt `run` | Hiểu scope instance theo từng run; kiểm tra test lifecycle |
| Nhận event quá sớm bằng bean `@EventListener` không thành công | Bean chưa tồn tại tại thời điểm event đầu | Đăng ký listener sớm bằng API hoặc `spring.factories` |
| Thấy `ready` nhưng endpoint vẫn không phản hồi | Sự cố runtime, routing, network, health downstream | Kiểm tra readiness/health và cổng mạng độc lập |

Một quy trình xử lý sự cố thực tế:

1. Kiểm tra dependency Spring Boot và **Javadoc cùng phiên bản** để xác nhận chữ ký.
2. Kiểm tra file `META-INF/spring.factories` hiện diện trên runtime classpath.
3. Kiểm tra class và public constructor; đọc exception gốc nếu loader thất bại.
4. Ghi một mốc ở `starting` và `environmentPrepared` bằng cách an toàn, không in bí mật.
5. Quan sát callback cuối cùng đã chạy; kết hợp với stack trace để xác định giai đoạn lỗi.
6. Nếu thất bại sau `started`, xem runners và các hook gần cuối run trước khi kết luận lỗi thuộc refresh.
7. Không chuyển lỗi startup thành “cảnh báo nhẹ” khi ứng dụng thực sự không đáp ứng điều kiện vận hành.

## 16. Những nguyên tắc cần ghi nhớ

1. **`SpringApplicationRunListener` là hook của một lần `SpringApplication.run`**, được tải qua `SpringFactoriesLoader` từ `META-INF/spring.factories`.
2. **Constructor bắt buộc là `public (SpringApplication, String[])`**; đừng kỳ vọng component scanning hoặc injection của BeanFactory tạo listener này.
3. **Chuỗi thành công:** `starting → environmentPrepared → contextPrepared → contextLoaded → started → runners → ready`; khi lỗi, đi vào `failed`.
4. **`started` khác `ready`**: started trước runner, ready sau runner.
5. **`contextPrepared` và `contextLoaded` đều trước refresh**; không gọi bean nghiệp vụ ở đó.
6. **`failed` phải chịu được context null** nếu lỗi xảy ra rất sớm.
7. **`EventPublishingRunListener` là cầu nối tới các `Application*Event`**; `ApplicationListener` là API khác.
8. Dùng listener cho việc hạ tầng cần mốc startup. Với cấu hình environment, bean definitions và công việc sau refresh, ưu tiên các điểm mở rộng chuyên trách tương ứng.
9. Khi phân tích startup, đối chiếu callback, event, runner và health/readiness. Mỗi thứ cho biết **một loại thông tin khác nhau** về trạng thái ứng dụng.

### Tài liệu chính thức

- [Spring Boot 3.3 — SpringApplicationRunListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html): chữ ký, thời điểm gọi và yêu cầu constructor.
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): vòng đời `run`, cấu hình listener và initializer.
- [Spring Boot 3.3 — EventPublishingRunListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/EventPublishingRunListener.html): cầu nối callback và application events.
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): chuỗi sự kiện trong startup.
