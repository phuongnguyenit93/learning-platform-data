# Vì sao listener dạng bean không nhận được mọi sự kiện rất sớm trong Spring Boot?

## 1. Vấn đề thường gặp

Trong Spring Boot, các ứng dụng hay theo dõi sự kiện bằng `@EventListener` hoặc bằng một bean triển khai `ApplicationListener<E>`:

```java
@Component
public class MyStartupListener {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        System.out.println("Application is starting");
    }
}
```

Lập trình viên kỳ vọng thấy dòng log ngay khi ứng dụng bắt đầu, nhưng thực tế phương thức có thể **không bao giờ được gọi** trong lần khởi động đó. Điều này thường không phải do `@EventListener` bị hỏng, component scanning sai hay Spring Boot bỏ sự kiện. **Sự kiện đã được phát trước khi bean listener được tạo, phát hiện và đăng ký**.

Có hai khái niệm khác nhau:

- **Sự kiện được phát** (*event publication*): Spring Boot gửi một đối tượng event tới bộ phát tán listener đang tồn tại ở thời điểm đó.
- **Listener đã được đăng ký** (*listener registration*): bộ phát tán biết listener nào được quyền nhận event. Việc một class có `@Component` hoặc một phương thức có `@EventListener` trong source code **không đồng nghĩa** listener đã có mặt từ thời điểm đầu tiên của tiến trình.

Với sự kiện cực sớm như `ApplicationStartingEvent`, ứng dụng còn chưa có `ApplicationContext` để quét `@Component`, tạo bean hoặc xử lý `@EventListener`. Muốn nghe chúng, phải đăng ký listener **trước khi gọi `SpringApplication.run(...)`**, chẳng hạn với:

1. `SpringApplication.addListeners(...)`.
2. `SpringApplicationBuilder.listeners(...)`.
3. `META-INF/spring.factories` với key `org.springframework.context.ApplicationListener`.

Đó là vấn đề **thời điểm tồn tại của listener**, không chỉ là kiểu sự kiện hay kiểu annotation.

## 2. Ba loại đối tượng cần phân biệt

| Đối tượng | Vai trò | Khi nào sẵn sàng? |
| --- | --- | --- |
| `SpringApplication` | Điều phối tiến trình khởi chạy và giữ những listener đăng ký sớm | Tồn tại ngay khi tạo `new SpringApplication(...)` |
| `ApplicationContext` | Container quản lý bean, sự kiện, môi trường, tài nguyên và lifecycle | Được tạo sau bước chuẩn bị environment; refresh muộn hơn |
| Bean listener (`@Component`/`@Bean`/`@EventListener`) | Nhận event khi container đã phát hiện và đăng ký listener tương ứng | Thường chỉ sau quá trình tạo/refresh context thích hợp |

Khi gọi:

```java
SpringApplication.run(DemoApplication.class, args);
```

đoạn code này tạo `SpringApplication` và gọi `run` trong một lệnh ngắn. Chương trình vẫn đi qua nhiều giai đoạn; **không có bảo đảm bean listener sẽ tồn tại ngay lúc SpringApplication phát những sự kiện đầu tiên**.

Ngược lại, cách sau tạo một listener Java bình thường **trước** khi bắt đầu bootstrap:

```java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.addListeners(new EarlyBootListener());
app.run(args);
```

`EarlyBootListener` ở đây là một đối tượng được tạo bằng `new` và đăng ký vào `SpringApplication`; nó **không cần đợi Spring IoC tạo bean** để nhận sự kiện sớm. Khi context được khởi tạo, Spring Boot còn có cơ chế đưa những application listener đã đăng ký trước vào môi trường phát sự kiện của context cho các giai đoạn tiếp theo.

## 3. Dòng thời gian các sự kiện khởi động

Trong Spring Boot 3.3.x, trình tự điển hình là:

```text
main(String[] args)
    |
    | Tạo SpringApplication, đăng ký listener sớm
    v
SpringApplication.run(args)
    |
    +-- ApplicationStartingEvent
    |      Environment chưa chuẩn bị; chưa có ApplicationContext
    |
    +-- ApplicationEnvironmentPreparedEvent
    |      Environment đã được chuẩn bị; chưa tạo ApplicationContext
    |
    +-- Tạo ApplicationContext
    +-- Áp dụng ApplicationContextInitializer
    +-- ApplicationContextInitializedEvent
    |      Context đã tồn tại; sources/bean definitions chính chưa được nạp
    |
    +-- Nạp nguồn cấu hình / bean definitions
    +-- ApplicationPreparedEvent
    |      Definitions đã được nạp; chưa refresh
    |
    +-- refresh() ApplicationContext
    |      Đăng ký post-processors và bean event listeners
    |      Khởi tạo singleton cần thiết, hoàn tất refresh
    |      ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    |      Context đã refresh, runners chưa chạy
    +-- AvailabilityChangeEvent: LivenessState.CORRECT
    |
    +-- ApplicationRunner và CommandLineRunner
    |
    +-- ApplicationReadyEvent
    +-- AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC
    |
    v
run(...) trả về context

Nếu khởi động có lỗi:
    +-- ApplicationFailedEvent (tùy thời điểm, context có thể chưa tồn tại)
```

Đây là sơ đồ **những cột mốc có ý nghĩa**. Nó lược bớt các bước chuẩn bị logging, auto-configuration, startup hooks và những sự kiện context/web server khác.

### Bảng đối chiếu: listener dạng bean có nhận được không?

| Sự kiện | Trạng thái tại lúc phát | Listener chỉ đăng ký bằng bean/`@EventListener` thường nhận được? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Trước `Environment` và context | **Không** — chưa có bean listener |
| `ApplicationEnvironmentPreparedEvent` | Có environment, chưa có context | **Không** |
| `ApplicationContextInitializedEvent` | Có context mới, chưa nạp bean definitions chính | **Không** |
| `ApplicationPreparedEvent` | Đã nạp definitions, chưa refresh và chưa hoàn tất đăng ký listener bean | **Không**, trong bootstrap thông thường |
| `ContextRefreshedEvent` | Refresh gần hoàn tất, event infrastructure đã sẵn sàng | Thường **có**, nếu listener bean được đăng ký đúng |
| `ApplicationStartedEvent` | Sau refresh, trước runners | Thường **có** |
| `ApplicationReadyEvent` | Sau runners | Thường **có** |
| `ApplicationFailedEvent` | Lỗi có thể xảy ra ở bất kỳ giai đoạn nào | **Không được bảo đảm**: lỗi sớm có thể xảy ra trước khi listener bean tồn tại |

Không được hiểu cột thứ ba là bảo đảm 100% trong mọi cấu hình. Một bean có điều kiện `@Profile` không phù hợp, không được quét, hoặc bị lỗi khởi tạo vẫn không thể nhận event. Ngược lại, người viết framework có thể đăng ký listener theo cơ chế thủ công sớm hơn bean. Bảng nói về **cách khai báo bean thông thường** trong `SpringApplication.run(...)` mặc định.

**Điểm dễ nhầm:** tại `ApplicationPreparedEvent`, *bean definitions có thể đã tồn tại* nhưng **instance bean listener và việc xử lý `@EventListener` vẫn chưa hoàn tất**. `BeanDefinition` là metadata “cách tạo bean”, không phải đối tượng listener đã có mặt trong event multicaster.

## 4. Vì sao @Component hoặc @Bean không giải quyết được sự kiện quá sớm?

Đăng ký bean thường đi qua quá trình:

```text
Định nghĩa lớp / cấu hình trên classpath
             |
             v
ApplicationContext được tạo
             |
             v
Component scanning / nạp bean definitions
             |
             v
refresh() và xử lý BeanFactoryPostProcessor
             |
             v
Tạo các bean cần thiết; xử lý BeanPostProcessor
             |
             v
Đăng ký listener interface và các phương thức @EventListener
             |
             v
Listener bean nhận được những sự kiện xảy ra từ đó trở đi
```

Có hai trường hợp phổ biến:

**Trường hợp A — bean implements ApplicationListener:**

```java
@Component
public class BeanStartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("bean observed starting");
    }
}
```

Kể cả triển khai đúng generic và override đúng phương thức, bean vẫn thường **không nhận `ApplicationStartingEvent`** vì event đó đã phát trước component scanning.

**Trường hợp B — phương thức @EventListener:**

```java
@Component
public class AnnotatedListener {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        System.out.println("annotation observed starting");
    }
}
```

`@EventListener` không phải công cụ “đăng ký trực tiếp ngay khi JVM nạp class”. Các phương thức có annotation được hạ tầng Spring context phát hiện và đăng ký trong lifecycle khởi tạo context. Vì vậy phương thức trên cũng quá muộn đối với `ApplicationStartingEvent`.

Cả hai đoạn này chỉ minh họa cách đăng ký; chúng cần import `@Component`, `ApplicationListener`, `ApplicationStartingEvent` hoặc `@EventListener` tương ứng và phải đặt trong dự án Spring hợp lệ. **Không phải cứ chuyển `@EventListener` sang implements interface là giải quyết được vấn đề** nếu instance vẫn do IoC container tạo.

### @Bean cũng có cùng vấn đề

```java
@Configuration
public class ListenerConfig {

    @Bean
    ApplicationListener<ApplicationStartingEvent> startingListener() {
        return event -> System.out.println("bean @Bean observed starting");
    }
}
```

Đây vẫn là **một bean** được tạo khi context xử lý configuration, quá muộn so với `ApplicationStartingEvent`. Đừng nhầm **`@Bean` tạo listener trong container** với **`new Listener()` rồi đăng ký vào `SpringApplication` trước `run`**.

## 5. Cách 1 — SpringApplication.addListeners(...) trước run

Đây là cách rõ ràng nhất khi listener chỉ phục vụ một entry point và bạn kiểm soát được phương thức `main(...)`.

Ví dụ sau dùng Java 17+, Spring Boot 3.3.x. Một listener thường có thể quan sát nhiều event thuộc họ `SpringApplicationEvent`.

**File `src/main/java/demo/early/EarlyBootListener.java`:**

```java
package demo.early;

import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyBootListener
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        System.out.println("external: "
                + event.getClass().getSimpleName());
    }
}
```

**File `src/main/java/demo/early/EarlyEventsApplication.java`:**

```java
package demo.early;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EarlyEventsApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(EarlyEventsApplication.class);

        // Đăng ký TRƯỚC run(): không cần Spring tạo bean.
        app.addListeners(new EarlyBootListener());

        app.run(args);
    }

    @Bean
    ApplicationRunner showRunner() {
        return args -> System.out.println("runner: executed");
    }
}
```

**File `src/main/java/demo/early/BeanEventsObserver.java`:**

```java
package demo.early;

import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class BeanEventsObserver {

    @EventListener
    public void tooEarlyStarting(ApplicationStartingEvent event) {
        System.out.println("bean: ApplicationStartingEvent");
    }

    @EventListener
    public void tooEarlyPrepared(ApplicationPreparedEvent event) {
        System.out.println("bean: ApplicationPreparedEvent");
    }

    @EventListener
    public void afterRefresh(ApplicationStartedEvent event) {
        System.out.println("bean: ApplicationStartedEvent");
    }

    @EventListener
    public void whenReady(ApplicationReadyEvent event) {
        System.out.println("bean: ApplicationReadyEvent");
    }
}
```

Trong ví dụ này, **cả bốn phương thức `@EventListener` đều hợp lệ về cú pháp**; hai phương thức đầu không in ra trong startup bình thường vì chúng được đăng ký sau khi event tương ứng đã phát.

**File `src/main/resources/application.properties`:**

```properties
spring.application.name=early-events-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

Thiết lập `NONE` giúp thử nghiệm không cần server HTTP. `logging.level.root=ERROR` nhằm giảm log thông thường; nó không ảnh hưởng những dòng `System.out.println(...)` của ví dụ.

### Build và chạy

Một `build.gradle` tối thiểu có thể dùng:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
```

`settings.gradle`:

```groovy
rootProject.name = 'early-events-demo'
```

Với dự án có Gradle wrapper tương thích, chạy:

```bash
./gradlew bootRun
```

Hoặc đóng gói bằng `./gradlew bootJar` và chạy `java -jar` với tên JAR được tạo. Đây là chương trình Spring Boot, **không** phải chương trình Java thuần có thể chạy bằng `javac` mà không có dependency của Spring.

### Kết quả kỳ vọng

Trong một lần chạy thành công mặc định, nhóm sự kiện do `EarlyBootListener` quan sát theo thứ tự:

```text
external: ApplicationStartingEvent
external: ApplicationEnvironmentPreparedEvent
external: ApplicationContextInitializedEvent
external: ApplicationPreparedEvent
external: ApplicationStartedEvent
external: ApplicationReadyEvent
```

Đây là **thứ tự các dòng có tiền tố `external:`**. Những dòng từ `BeanEventsObserver` và runner có thể xen giữa các dòng sau, không nên coi khối trên là toàn bộ stdout liền nhau.

Các dòng đáng chú ý khác:

```text
bean: ApplicationStartedEvent
runner: executed
bean: ApplicationReadyEvent
```

Trong đó:

- `bean: ApplicationStartedEvent` xuất hiện **trước** `runner: executed`.
- `bean: ApplicationReadyEvent` xuất hiện **sau** `runner: executed`.
- Không có `bean: ApplicationStartingEvent` và `bean: ApplicationPreparedEvent` trong đường startup chuẩn của ví dụ.
- Thứ tự giữa hai listener cùng nhận một event cụ thể có thể chịu ảnh hưởng bởi ordering/registration; không nên viết test dựa vào vị trí tùy ý của `external: ApplicationStartedEvent` so với `bean: ApplicationStartedEvent`.
- Hệ thống có thể in thêm log/các thông báo Gradle. Chỉ so sánh các dòng do demo tự in, không tuyên bố chúng là toàn bộ stdout.

Bản Spring Boot `3.3.13` là một phiên bản trong nhánh 3.3 dùng để tái hiện ví dụ; đây không phải gợi ý chọn bản đã hết thời gian hỗ trợ cho một dự án mới. Khi dùng phiên bản hiện hành của tổ chức, hãy xác nhận lại API và compatibility tương ứng.

### Vì sao listener ngoài bean lại nhận được cả event muộn?

`app.addListeners(new EarlyBootListener())` cung cấp instance trực tiếp cho `SpringApplication` **trước khi bắt đầu chạy**. Cơ chế phát event khởi động có thể thông báo listener này từ sự kiện đầu. Spring Boot cũng chuyển các listener đăng ký sớm thích hợp vào quá trình phát event của `ApplicationContext` sau khi context được nạp, nên listener có thể tiếp tục quan sát các event muộn.

Điều đó **không biến instance này thành một service bean được autowire theo cách thông thường**. Đừng kỳ vọng constructor `EarlyBootListener` được injection như một `@Component` khi bạn đã tự tạo instance bằng `new`.

## 6. Cách 2 — đăng ký sớm qua META-INF/spring.factories

Đây là lựa chọn hữu ích nếu listener thuộc một thư viện hạ tầng và bạn muốn nó được phát hiện tự động khi thư viện xuất hiện trên runtime classpath, không phụ thuộc entry point nào gọi `SpringApplication.run(...)`.

Tạo file:

```text
src/main/resources/META-INF/spring.factories
```

Nội dung:

```properties
org.springframework.context.ApplicationListener=demo.early.EarlyBootListener
```

Với file này, sửa entry point trở về dạng đơn giản:

```java
package demo.early;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EarlyEventsApplication {

    public static void main(String[] args) {
        SpringApplication.run(EarlyEventsApplication.class, args);
    }
}
```

Đây là **phương án thay thế** cho entry point ở mục 5, không đặt hai khai báo public class cùng tên trong một file. Nếu muốn giữ runner của mục 5, có thể giữ bean runner đó trong một `@Configuration` class khác, hoặc giữ nguyên phương thức `@Bean` trong entry point khi thay đổi cách đăng ký listener.

**Không đồng thời đăng ký cùng một listener bằng `addListeners` và `spring.factories` một cách vô ý**. Khi hai cách tạo ra hai instance, các dòng sự kiện có thể xuất hiện hai lần, hoặc hành động phụ của listener có thể chạy lặp.

### Điều kiện để SpringFactoriesLoader tạo listener

- File phải có đúng đường dẫn `META-INF/spring.factories` trong runtime classpath.
- Key phải là **`org.springframework.context.ApplicationListener`**, không phải tên interface khác.
- Giá trị phải là tên class đầy đủ, đúng package và đúng class.
- Implementation phải tải được và có constructor phù hợp để loader tạo instance, thường là **public no-arg constructor** đối với `ApplicationListener` đơn giản như `EarlyBootListener`.
- Các dependency cần cho listener phải sẵn sàng ngay giai đoạn khởi động sớm.
- Không được giả định Spring IoC đã cung cấp `@Autowired` cho listener tạo bởi loader.

Cách đóng gói tài nguyên trong executable Spring Boot JAR thường là:

```text
BOOT-INF/classes/META-INF/spring.factories
BOOT-INF/classes/demo/early/EarlyBootListener.class
```

Kiểm tra bằng `jar tf` với JAR do build thực sự tạo. Nếu listener nằm trong JAR thư viện, file `spring.factories` sẽ nằm trong JAR phụ thuộc chứ không nhất thiết ở `BOOT-INF/classes` của ứng dụng.

**Đừng nhầm cơ chế:** Spring Boot 3 chuyển nhiều cơ chế tự cấu hình sang `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, nhưng việc đăng ký `ApplicationListener` rất sớm trong bài này vẫn có thể làm qua **`META-INF/spring.factories`** với key của `ApplicationListener`. Hai loại metadata phục vụ hai mục đích khác nhau.

### ApplicationListener khác SpringApplicationRunListener

`SpringApplicationRunListener` là interface hook các bước `starting(...)`, `environmentPrepared(...)`, `contextPrepared(...)`, `contextLoaded(...)`, `started(...)`, `ready(...)` và `failed(...)`. Nó cũng được tải rất sớm qua `SpringFactoriesLoader`, nhưng dùng **key khác**:

```properties
org.springframework.boot.SpringApplicationRunListener=demo.early.CustomRunListener
```

Đây là **dòng minh họa một cơ chế khác**, không phải cấu hình cần thêm cho ví dụ `EarlyBootListener`. `CustomRunListener` phải triển khai `SpringApplicationRunListener` và có constructor chuẩn `(SpringApplication, String[])`. Ngược lại, `EarlyBootListener` chỉ implement `ApplicationListener<SpringApplicationEvent>`, không cần constructor đặc biệt của run listener.

Nếu chỉ muốn **nhận `ApplicationStartingEvent`**, cách đơn giản nhất là `ApplicationListener<ApplicationStartingEvent>` đăng ký sớm. Không cần triển khai đầy đủ `SpringApplicationRunListener`.

## 7. Cách 3 — SpringApplicationBuilder.listeners(...)

Khi tạo ứng dụng qua `SpringApplicationBuilder`, ta có thể khai báo listener trước `run`:

```java
new SpringApplicationBuilder(EarlyEventsApplication.class)
        .listeners(new EarlyBootListener())
        .run(args);
```

Đoạn này cần import `org.springframework.boot.builder.SpringApplicationBuilder`. Đây là **lựa chọn khởi động thay thế** cho `SpringApplication.addListeners(...)`, không phải lệnh gọi thêm sau khi application đã run xong.

Về nguyên tắc, listener cần đăng ký trước khi luồng bootstrap phát event đầu tiên. Nếu thực hiện:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(EarlyEventsApplication.class, args);

// Đến lúc này đã quá muộn cho ApplicationStartingEvent.
context.addApplicationListener(new EarlyBootListener());
```

thì listener mới chỉ có thể nhận các event tương lai từ context; các event quá khứ **không được tự phát lại**. `ApplicationContext` không cung cấp hàng đợi lịch sử mặc định cho event startup.

## 8. Các giai đoạn Spring Boot đăng ký và phát event

Để hiểu sâu hơn, có thể tách luồng event thành hai giai đoạn.

### Giai đoạn A: trước khi ApplicationContext sẵn sàng

Spring Boot có một run listener nội bộ, điển hình là `EventPublishingRunListener`. Nó biết những listener đã đăng ký trước khi `run(...)` và sử dụng một cơ chế phát tán event ban đầu để gửi các thông báo sớm.

```text
new SpringApplication(...)
      |
      +-- Có những listener đăng ký sớm:
      |      addListeners / SpringFactoriesLoader
      |
      v
run()
      |
      +-- ApplicationStartingEvent
      +-- ApplicationEnvironmentPreparedEvent
      +-- ApplicationContextInitializedEvent
      +-- ApplicationPreparedEvent
      |
      v
ApplicationContext tiến tới refresh
```

Tại thời điểm đó, không thể truy xuất bean listener từ một context chưa có/ chưa refresh. Vì vậy những event này được gửi tới **tập listener sớm**, không chờ bean container dựng xong mới phát.

### Giai đoạn B: context đã refresh

Khi Spring tiến hành refresh, các cơ chế phát hiện và đăng ký listener dựa trên bean/annotation được thiết lập. Những event sau đó có thể được phát qua hạ tầng event của `ApplicationContext`.

```text
ApplicationContext.refresh()
      |
      +-- Chuẩn bị ApplicationEventMulticaster
      +-- Đăng ký ApplicationListener beans
      +-- Phát hiện @EventListener methods
      +-- Hoàn tất singleton và refresh
      |
      v
ContextRefreshedEvent
ApplicationStartedEvent
ApplicationReadyEvent
...
```

Đây là sơ đồ giải thích hai giai đoạn; trong source framework, việc đăng ký listener, tạo singleton và khởi tạo multicaster có thứ tự chi tiết hơn.

**Kết luận quan trọng:** trước refresh, event không thể chờ một bean `@Component` chưa được tạo. Sau refresh, chính bean đó có thể nhận những event **được phát kể từ lúc nó đã được đăng ký**. Việc đăng ký listener không làm sự kiện `ApplicationStartingEvent` được gửi lại từ đầu.

## 9. Tại sao ApplicationPreparedEvent cũng thường không đến được bean?

Một câu hỏi khó là: `ApplicationPreparedEvent` được phát **sau khi bean definitions đã được load**, vậy tại sao bean listener vẫn không thấy?

Phải phân biệt:

- **Bean definition tồn tại:** container biết metadata để có thể tạo bean.
- **Bean instance được tạo:** Spring đã chạy constructor/factory method và các bước injection thích hợp.
- **Listener được đăng ký với event infrastructure:** multicaster biết cần gửi event tới instance hoặc phương thức nào.

`ApplicationPreparedEvent` xảy ra **trước refresh**. Với cách đăng ký thông thường bằng `@Component` và `@EventListener`, hạ tầng hoàn tất việc tạo bean/đăng ký listener còn chưa đến thời điểm phù hợp.

```text
Đã load bean definition
       !=
Đã tạo listener bean
       !=
Đã đăng ký listener để nhận sự kiện
```

Vì vậy sự kiện `ApplicationPreparedEvent` có thể xuất hiện trong log của `EarlyBootListener` từ `addListeners(...)`, nhưng không có log tương ứng từ `BeanEventsObserver.tooEarlyPrepared(...)`.

Nếu cần xử lý một nhiệm vụ **trước refresh**, hãy cân nhắc:

- Một `ApplicationListener<ApplicationPreparedEvent>` **đăng ký trước run** để chỉ quan sát mốc đó.
- `ApplicationContextInitializer` nếu cần tùy chỉnh context đã được tạo, trước bước refresh và trước lúc nạp các source chính.
- `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor` khi cần điều chỉnh bean definitions bằng điểm mở rộng đúng mục đích.

Không nên cưỡng ép một bean nghiệp vụ khởi tạo sớm chỉ để nghe `ApplicationPreparedEvent`, vì điều đó có thể bỏ qua post-processors và những giả định vòng đời còn lại của Spring.

## 10. Cách xử lý đúng theo nhu cầu

| Nhu cầu | Cách nên chọn | Tránh |
| --- | --- | --- |
| Quan sát lúc Boot vừa bắt đầu chạy | Listener đăng ký qua `addListeners` hoặc `spring.factories` cho `ApplicationStartingEvent` | `@EventListener` bean kỳ vọng được tạo ngay |
| Đọc cấu hình đã được chuẩn bị nhưng trước context | Listener sớm nhận `ApplicationEnvironmentPreparedEvent` | `@Autowired Environment` từ bean chưa tồn tại |
| Thêm `PropertySource`, điều chỉnh environment rất sớm | `EnvironmentPostProcessor` phù hợp | Lạm dụng controller/service bean |
| Điều chỉnh context trước refresh | `ApplicationContextInitializer` phù hợp | Gọi `getBean` sớm trên context chưa refresh |
| Quan sát mốc trước refresh | Listener sớm nhận `ApplicationPreparedEvent` | Dựa vào `@Component` đã có definition |
| Chạy công việc cần repository/service bean sau refresh | `ApplicationRunner` / `CommandLineRunner` | Xử lý nghiệp vụ trong `ApplicationStartingEvent` |
| Ghi log startup sau refresh | `@EventListener(ApplicationStartedEvent)` | Viết hook quá sớm nếu không cần |
| Chạy logic sau khi runner hoàn tất | `@EventListener(ApplicationReadyEvent)` | Coi `ApplicationStartedEvent` là đã ready |
| Quan sát lỗi có thể xuất hiện trước context | Listener sớm nhận `ApplicationFailedEvent` | Chỉ dựa vào listener bean tạo muộn |
| Theo dõi sức khỏe lâu dài sau startup | Actuator health/readiness probes | Coi event startup một lần là giám sát liên tục |

Một ứng dụng nhỏ thường không cần hook rất sớm. Lựa chọn quá mạnh có thể tăng độ phức tạp startup, khiến lỗi khó truy vết và làm chương trình phụ thuộc chặt vào chi tiết bootstrap của Spring Boot.

## 11. ApplicationFailedEvent: trường hợp cần đặc biệt cẩn thận

`ApplicationFailedEvent` xuất hiện khi `SpringApplication.run(...)` gặp lỗi. Nhưng **thời điểm lỗi không cố định**:

- Cấu hình hoặc environment thất bại trước khi context được tạo.
- Tạo context hoặc nạp bean definitions thất bại.
- Bean không thể khởi tạo trong `refresh()`.
- Một runner ném exception sau khi context đã refresh.

Nếu listener chỉ là bean, ở các trường hợp đầu **không có gì bảo đảm listener đã được dựng và đăng ký**. Thậm chí khi context tồn tại nhưng không active hoặc quá trình refresh thất bại, không nên giả định mọi `@EventListener` đã hoàn tất đăng ký.

Một listener sớm có thể xử lý lỗi nhẹ:

```java
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable cause = event.getException();
        String type = cause.getClass().getSimpleName();

        System.err.println("Startup failure: " + type);
    }
}
```

Đây là đoạn source cho class `EarlyFailureListener.java`, cần khai báo package phù hợp và đăng ký **trước run** bằng `app.addListeners(new EarlyFailureListener())` hoặc `spring.factories`. Nó không cần truy xuất `ApplicationContext`, phù hợp khi lỗi xảy ra rất sớm.

Cần giữ callback lỗi thật đơn giản:

- Không gọi repository, bean chưa có hoặc API network chỉ để gửi log trong lúc ứng dụng đã lỗi.
- Không in password, token, đường dẫn nhạy cảm hoặc toàn bộ command-line arguments.
- Không throw thêm exception từ listener để che mất lỗi gốc.
- Không giả định `event.getApplicationContext()` luôn trả về context; event có thể phát khi context chưa được tạo.
- Cân nhắc ghi nhận exception type và log stack trace bằng hệ thống logging/diagnostics khi nó đã sẵn sàng.

**Không có cơ chế event replay mặc định.** Một bean listener được tạo sau khi lỗi khởi động đã xảy ra không thể được dùng để “nhận bù” `ApplicationFailedEvent` đó.

## 12. Thời điểm ApplicationStartedEvent và ApplicationReadyEvent

Sự khác biệt giữa hai event muộn này cũng thường bị bỏ qua:

**`ApplicationStartedEvent`:** phát khi context đã refresh xong, **trước** khi Spring Boot gọi `ApplicationRunner` và `CommandLineRunner`.

**`ApplicationReadyEvent`:** phát **sau** khi các runner hoàn tất thành công, sát thời điểm `run(...)` trả về.

Ví dụ một runner in log:

```java
@Bean
ApplicationRunner initializeCache() {
    return args -> {
        System.out.println("runner: loading cache");
        // Mã tạo dữ liệu thực tế nếu cần.
    };
}
```

Một bean nhận `ApplicationStartedEvent` sẽ được gọi **trước** dòng `runner: loading cache`. Bean nhận `ApplicationReadyEvent` sẽ được gọi **sau** dòng đó nếu runner thành công.

Vậy nếu một listener dạng bean nhận được `ApplicationReadyEvent` nhưng không nhận `ApplicationStartingEvent`, đó là **hành vi đúng theo thời điểm đăng ký**, không phải mâu thuẫn hay hành vi ngẫu nhiên.

Một chi tiết nữa: Spring Boot phát `AvailabilityChangeEvent` để phản ánh `LivenessState` và `ReadinessState` trong các mốc liên quan. Không đồng nhất chúng với những sự kiện “trước context”. Listener bean có thể theo dõi các thay đổi availability sau khi context đã sẵn sàng.

## 13. Một ApplicationListener đăng ký sớm có cần là bean không?

**Không.** `SpringApplication.addListeners(new X())` đã cung cấp một instance Java cho cơ chế sự kiện của Boot. Không cần annotate `X` bằng `@Component` để nó hoạt động.

Nếu gắn cả `@Component` lên class `X` và lại tự `new X()` khi đăng ký sớm, chương trình có nguy cơ có **hai instance riêng biệt**. Hậu quả có thể gồm:

- Listener nhận event hai lần khi cả hai instance cùng được đăng ký về sau.
- Tập dữ liệu lưu ở một instance khác với instance còn lại.
- Những field autowired chỉ có ở bean, không có trong instance tạo thủ công.
- Cleanup và lifecycle của hai instance khác nhau.

Với listener được đăng ký bằng `spring.factories`, hạ tầng loader cũng tạo instance theo cơ chế riêng, không tự động dùng lại bean singleton trong IoC container.

**Cách an toàn:** nếu listener thuần quan sát các sự kiện bootstrap, làm nó không trạng thái hoặc chỉ giữ state nhỏ và tự quản lý. Nếu mục tiêu cần beans nghiệp vụ, chọn listener bean cho sự kiện muộn hoặc kết hợp cơ chế trung gian có thiết kế rõ ràng thay vì trộn hai kiểu đăng ký.

## 14. Ordering và thread: những lưu ý ảnh hưởng độ tin cậy

### Thứ tự giữa nhiều listeners

Spring có hỗ trợ thứ tự thông qua `Ordered` và `@Order` trong các trường hợp phù hợp. Nhưng **đừng dựa vào thứ tự ngẫu nhiên của classpath hoặc thứ tự khai báo `@Component`** để quyết định logic nghiệp vụ.

Nếu hai listener cùng nhận `ApplicationReadyEvent` và cùng cập nhật một resource, việc một listener được gọi trước không nên là dependency ẩn. Thay vào đó, tổ chức một service điều phối với thứ tự rõ ràng hoặc dùng hạ tầng lifecycle/runner thích hợp.

### Event có đồng bộ không?

Theo cơ chế thông thường, listener Spring được gọi **đồng bộ trên thread phát event**. Với sự kiện bootstrap rất sớm, một listener chặn lâu có thể khiến toàn bộ quá trình khởi động chậm hoặc gặp lỗi.

`@Async` không thể được xem là giải pháp mặc định cho mọi event sớm: trước context refresh, các bean executor và proxy phục vụ async có thể chưa tồn tại. Đặc biệt, listener được tạo trực tiếp qua `new` không tự nhận các khả năng proxy bean.

**Thiết kế tốt:** callback sớm nên nhanh, ít phụ thuộc, không I/O mạng không giới hạn và không làm công việc nghiệp vụ dài. Các tác vụ cần bean hoặc transaction nên được chuyển tới runner, lifecycle service hoặc kiến trúc riêng.

### Context cha/con có thể phát nhiều event

Trong cấu trúc nhiều `ApplicationContext`, event xuất phát từ context con có thể được truyền lên context cha. Một listener có thể quan sát nhiều event cùng loại ở các context khác nhau. Khi cần lọc, xem context của event và context mà listener chịu trách nhiệm, không chỉ dựa vào `getClass().getSimpleName()`.

Vấn đề này khác với việc không nghe được sự kiện sớm nhưng cũng là lý do quan trọng khiến test đếm event cần định nghĩa phạm vi.

## 15. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `@EventListener(ApplicationStartingEvent)` không chạy | Bean chưa tồn tại khi event được phát | Đăng ký listener trước `run` |
| `@Bean ApplicationListener<ApplicationEnvironmentPreparedEvent>` không chạy | Bean factory chưa được tạo/refresh | Dùng `addListeners` hoặc `spring.factories` |
| `ApplicationPreparedEvent` không tới bean mặc dù đã có definitions | Bean definition chưa phải listener instance đã đăng ký | Dùng listener sớm hoặc điểm mở rộng before-refresh |
| `ApplicationStartedEvent` nhận được, `ApplicationStartingEvent` không | Hai sự kiện ở hai mốc khác nhau | Đây là hành vi bình thường, không cần đổi annotation |
| Listener từ `spring.factories` không chạy | Sai key, path, class name hoặc constructor/đóng gói | Kiểm tra `META-INF/spring.factories` trong runtime classpath |
| Listener chạy hai lần | Đăng ký lặp giữa `addListeners`, `spring.factories` và bean | Chọn một cơ chế, kiểm tra instance |
| Listener cần `@Autowired` nhưng bị `null` | Listener do `new`/loader tạo, không phải bean IoC | Không dùng injection bean ở sự kiện rất sớm |
| Listener gây lỗi startup | Exception hoặc blocking operation trong listener | Giữ callback sớm đơn giản; xử lý lỗi thích hợp |
| Listener lỗi startup không nhận được `ApplicationFailedEvent` | Lỗi xảy ra trước khi listener bean được khởi tạo | Đăng ký listener lỗi từ trước `run` |
| `@EventListener(ApplicationReadyEvent)` không chạy | Runner thất bại hoặc startup không hoàn tất | Xem exception/`ApplicationFailedEvent` trước |
| Test đếm nhiều event hơn mong đợi | Test nhiều context hoặc hierarchy | Chỉ định context/run mục tiêu trong test |
| Đăng ký listener sau `run` không nhận Starting | Event quá khứ không được lưu để replay | Đăng ký trước lần run tiếp theo, không đợi replay |
| Đang đọc properties ở `ApplicationStartingEvent` nhưng thiếu | `Environment` chưa được chuẩn bị | Chọn `ApplicationEnvironmentPreparedEvent` hoặc `EnvironmentPostProcessor` |
| Đổi thành `SpringApplicationRunListener` nhưng listener không được tạo | Sai constructor/key của run listener | So Javadoc: run listener có hợp đồng khởi tạo khác |

Quy trình chẩn đoán cụ thể:

1. Xác định **event type** và **mốc thời gian được phát**.
2. Xác định listener được tạo bằng `new`, `spring.factories` hay IoC container.
3. Kiểm tra listener đã đăng ký **trước khi event được publish** chưa.
4. Nếu là bean, xác nhận bean được quét/đăng ký, profile/condition phù hợp và startup refresh thành công.
5. Với `@EventListener`, xác nhận method có signature được Spring hỗ trợ và hạ tầng xử lý annotation đang hoạt động.
6. Với `spring.factories`, kiểm tra file thật sự nằm trên **runtime** classpath, không phải chỉ ở source.
7. Nếu event muộn cũng không thấy, xem ứng dụng có khởi động hoàn tất không và có exception giữa đường không.
8. Kiểm tra có đăng ký trùng, context hierarchy hoặc custom event multicaster gây khác biệt về số lượng/thứ tự không.
9. Viết test đơn giản thu thập event để phân biệt “Spring không phát” với “listener chưa được đăng ký”.

## 16. Kiểm thử sự kiện cực sớm đúng cách

Có thể kiểm chứng listener độc lập với ứng dụng lớn bằng một lớp nhỏ tự đăng ký trước `run`:

```java
package demo.early;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class RecordingApplication {

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        ApplicationListener<SpringApplicationEvent> listener =
                event -> events.add(event.getClass().getSimpleName());

        SpringApplication app = new SpringApplication(RecordingApplication.class);
        app.setWebApplicationType(org.springframework.boot.WebApplicationType.NONE);
        app.addListeners(listener);

        try (var context = app.run(args)) {
            // Không cần web server; quan sát sau khi run() hoàn thành.
        }

        System.out.println(events.contains("ApplicationStartingEvent"));
        System.out.println(events.contains("ApplicationReadyEvent"));
    }
}
```

Với ứng dụng khởi động thành công và cấu hình listener như trên, hai dòng do phần kiểm tra ở cuối in ra là:

```text
true
true
```

Thực tế còn có banner/log Spring Boot. `ArrayList` ở ví dụ phù hợp với cơ chế đồng bộ mặc định và luồng demo; nếu dùng multicaster async tùy chỉnh, phải xem xét khả năng truy cập đồng thời và thời điểm assert.

**Vì sao không chỉ dựa vào `@SpringBootTest`?** Test framework có thể tạo, cache hoặc tái sử dụng context theo cách khác với chạy trực tiếp `main()`. Khi cần kiểm chứng sự kiện trước context, test có thể xây `SpringApplication` với listener đã đăng ký sớm và chủ động khởi chạy/đóng context; cần tránh test tự mở nhiều server hoặc làm rò rỉ tài nguyên.

Các mốc đáng kiểm tra trong test:

- Sau khi listener được thêm, **trước `run`**: danh sách chưa có event.
- Trong `run`: `ApplicationStartingEvent` được ghi nhận trước những event sau.
- Sau `run` thành công: có `ApplicationReadyEvent`.
- Nếu runner ném lỗi: không có `ApplicationReadyEvent` của lượt chạy thất bại; listener sớm có thể nhận `ApplicationFailedEvent`.
- Khi listener chỉ là bean, không kỳ vọng nó quan sát bốn event sớm trong bảng mục 3.

Không nên khẳng định một listener bean “không nhận bất kỳ application event nào”. Nó vẫn có thể nhận `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent` và các event nghiệp vụ sau refresh.

## 17. Bài tập tự kiểm tra

1. Một class `@Component` implements `ApplicationListener<ApplicationStartingEvent>` nhưng không có log. Điều này có chứng minh class không được component-scan không? Cần kiểm tra gì trước?
2. Tại sao `ApplicationPreparedEvent` có thể không đến `@EventListener` bean dù bean definition đã được load?
3. `ApplicationStartedEvent` và `ApplicationReadyEvent` khác nhau ở đâu so với các runner?
4. Nếu đăng ký `new EarlyBootListener()` qua `addListeners`, Spring có tự inject repository vào constructor listener không?
5. Key của `spring.factories` để nhận event qua `ApplicationListener` là gì? Nó khác key của `SpringApplicationRunListener` ra sao?
6. Có thể nhận lại `ApplicationEnvironmentPreparedEvent` bằng cách đăng ký listener sau `SpringApplication.run` không? Vì sao?
7. Vì sao listener nhận `ApplicationFailedEvent` từ một lỗi rất sớm cần tránh truy cập context như một đối tượng chắc chắn đã tồn tại?
8. Tại sao không nên thực hiện một truy vấn database chậm trong `ApplicationStartingEvent`?
9. Nếu listener được đăng ký bằng cả `spring.factories` và `addListeners`, điều gì có thể xảy ra với số lần gọi callback?
10. Khi nào `EnvironmentPostProcessor` phù hợp hơn một application event listener?

### Kết luận

**Spring Boot phát sự kiện rất sớm trước khi IoC container có thể tạo bean listener.** Vì thế `@Component`, `@Bean` và `@EventListener` không tự bảo đảm nhận `ApplicationStartingEvent`, `ApplicationEnvironmentPreparedEvent`, `ApplicationContextInitializedEvent` hoặc `ApplicationPreparedEvent` trong luồng khởi động chuẩn.

Nếu cần nghe các event ấy, **tạo và đăng ký `ApplicationListener` trước `SpringApplication.run`**, qua `addListeners(...)`, `SpringApplicationBuilder.listeners(...)` hoặc `META-INF/spring.factories`. Nếu chỉ cần phản ứng sau khi bean đã sẵn sàng, listener dạng bean là thiết kế đơn giản và phù hợp hơn. Hãy chọn điểm mở rộng theo **thời điểm và dependency thật sự cần**, thay vì dùng một loại listener cho toàn bộ lifecycle.

### Tài liệu chính thức

- [Spring Boot 3.3 — SpringApplication, Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): trình tự các event và cách đăng ký listener sớm.
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): `addListeners(...)` và luồng bootstrap.
- [Spring Boot 3.3 — SpringApplicationRunListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html): hook cấp run, không đồng nhất với `ApplicationListener`.
- [Spring Framework — Annotation-based Event Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation): cơ chế `@EventListener` khi bean context đã tồn tại.
