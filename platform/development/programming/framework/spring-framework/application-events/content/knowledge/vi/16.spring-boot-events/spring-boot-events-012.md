# Khai báo `ApplicationListener` qua `META-INF/spring.factories` trong Spring Boot

## 1. Khi nào cần khai báo listener bằng `spring.factories`?

Spring Boot phát nhiều **SpringApplication events** trong suốt quá trình `SpringApplication.run(...)`. Một số sự kiện xuất hiện **trước khi `ApplicationContext` được tạo**, vì vậy các listener khai báo bằng `@Component`, `@Bean` hoặc phương thức `@EventListener` trong bean chưa thể có mặt để nhận chúng.

Ví dụ:

- `ApplicationStartingEvent` được phát rất sớm, khi `Environment` và `ApplicationContext` chưa sẵn sàng.
- `ApplicationEnvironmentPreparedEvent` được phát khi `Environment` đã được chuẩn bị, nhưng context vẫn chưa được tạo.
- `ApplicationContextInitializedEvent` được phát sau khi context được tạo và các `ApplicationContextInitializer` đã chạy, nhưng trước khi nạp bean definitions.

Muốn listener được Spring Boot **khám phá ngay khi chuẩn bị chạy ứng dụng**, kể cả các sự kiện sớm nói trên, bạn có thể đăng ký class implement `ApplicationListener` qua file:

```text
src/main/resources/META-INF/spring.factories
```

Nội dung tối thiểu:

```properties
org.springframework.context.ApplicationListener=demo.BootstrapEventsListener
```

Phần trước dấu `=` phải là **tên fully qualified của interface** `org.springframework.context.ApplicationListener`; phần sau là tên fully qualified của class listener cần tạo. Spring Boot nạp các đăng ký này từ classpath khi thiết lập `SpringApplication`, **không cần** đợi component scan hoặc dependency injection trong context.

**Điểm cần nhớ:** `spring.factories` được dùng trong bài này để đăng ký **`ApplicationListener`**. Điều đó khác với đăng ký **auto-configuration**: từ Spring Boot 3, việc khai báo auto-configuration bằng khóa `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `spring.factories` không còn được hỗ trợ; auto-configuration dùng `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Hai cơ chế có mục đích khác nhau, không nên nhầm lẫn.

## 2. Vì sao `@EventListener` hoặc `@Bean` chưa đủ cho early events?

Xét hai cách đăng ký:

```java
@Component
public class ReadyObserver {
    @EventListener
    public void ready(ApplicationReadyEvent event) {
        // Có thể nhận khi context đã có bean.
    }
}
```

Đây là mã minh họa; cần import `Component`, `EventListener` và `ApplicationReadyEvent`. Method `@EventListener` được Spring phát hiện **khi bean được tạo/đăng ký**. Nó có thể nhận các event muộn như `ApplicationReadyEvent`, nhưng không thể quay ngược thời gian để nhận `ApplicationStartingEvent` đã phát trước lúc context tồn tại.

Ngược lại:

```java
public final class StartingObserver
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        // Có thể nhận rất sớm nếu đăng ký qua spring.factories
        // hoặc SpringApplication.addListeners(...) trước run().
    }
}
```

Đây cũng là mã minh họa (cần import `ApplicationListener` và `ApplicationStartingEvent`). **Chỉ implement interface chưa đủ**: class phải được Spring Boot đăng ký bằng `spring.factories` hoặc API `addListeners`/builder tương đương. Không đặt kỳ vọng rằng `@Component` trên class này sẽ khiến nó nhận được `ApplicationStartingEvent`; bean vẫn được tạo quá muộn.

### Bảng lựa chọn

| Cách đăng ký | Khi nào sẵn sàng? | Nhận `ApplicationStartingEvent`? | Phù hợp |
| --- | --- | --- | --- |
| `META-INF/spring.factories` với key `ApplicationListener` | Khi Spring Boot dựng `SpringApplication`/cơ chế startup listeners | **Có**, nếu class hợp lệ và nằm trong classpath | Thư viện hoặc listener bootstrap cần hoạt động tự động |
| `SpringApplication.addListeners(...)` trước `run()` | Khi lập trình viên đăng ký trước startup | **Có** | Ứng dụng cần kiểm soát đăng ký theo từng lần chạy |
| `new SpringApplicationBuilder(...).listeners(...)` | Khi cấu hình builder trước `run()` | **Có** | Ứng dụng dùng builder hoặc context hierarchy |
| Spring bean implement `ApplicationListener<T>` | Sau khi context đủ điều kiện tạo/đăng ký bean | **Không** với event đã xảy ra trước đó | Các event muộn và application context events |
| `@EventListener` trên Spring bean | Khi Spring xử lý listener method của bean | **Không** với early events | Logic nghiệp vụ, các event sau khi context sẵn sàng |

Hãy chọn thời điểm đăng ký tương ứng với event cần quan sát. `ApplicationReadyEvent` hoặc custom event thông thường thường **không cần** `spring.factories`, vì đã có bean Spring để xử lý.

## 3. Cấu trúc và cú pháp của `spring.factories`

`spring.factories` là một file theo cú pháp **Java properties**, được đặt chính xác tại `META-INF/spring.factories` bên trong thư mục resources hoặc JAR.

Ví dụ một listener:

```properties
org.springframework.context.ApplicationListener=demo.BootstrapEventsListener
```

Ví dụ nhiều listener:

```properties
org.springframework.context.ApplicationListener=\
demo.FirstBootstrapListener,\
demo.SecondBootstrapListener
```

Dấu `\` ở cuối dòng là cú pháp nối dòng theo định dạng `.properties`. Dùng dấu phẩy để phân tách tên class. Các class được nêu phải được đóng gói vào classpath runtime, có thể được khởi tạo bởi cơ chế tải factory, và triển khai `org.springframework.context.ApplicationListener` thích hợp.

Quy tắc quan trọng:

1. **Đúng đường dẫn:** `src/main/resources/META-INF/spring.factories`, không phải `src/main/java/META-INF/...`, cũng không phải một file tên `spring-factories`.
2. **Đúng key:** `org.springframework.context.ApplicationListener`, không phải tên event (`ApplicationStartingEvent`) và không phải `org.springframework.context.event.EventListener`.
3. **Đúng tên class đầy đủ:** gồm package và class, ví dụ `demo.BootstrapEventsListener`.
4. **Class có thể tạo ở giai đoạn bootstrap:** cách đơn giản là `public class` hoặc `public final class` với public no-argument constructor. Không yêu cầu Spring tự inject bean trước khi context có mặt.
5. **Không đặt `@Component` lên chính class listener đăng ký qua factories nếu không có lý do:** tránh tạo thêm một bean listener của cùng loại và nguy cơ xử lý event trùng.
6. **Nằm trong classpath runtime:** khi đóng gói thành thư viện JAR, file phải ở `META-INF/spring.factories` trong JAR đó. Spring Boot có thể tìm các file factories từ nhiều JAR dependency trên classpath.
7. **Chú ý việc merge resource:** một công cụ tạo “fat/uber JAR” bằng cách gộp file thủ công có thể ghi đè `META-INF/spring.factories` của dependency khác. Nếu dùng shaded JAR, bảo đảm chiến lược merge resources phù hợp; Boot executable JAR dùng cơ chế đóng gói dependency riêng.

Một listener nạp từ `spring.factories` **không phải bean được tạo qua constructor injection của ApplicationContext** tại thời điểm đăng ký ban đầu. Vì vậy tránh bắt buộc `@Autowired` field, repository, service hoặc bất kỳ bean phụ thuộc context nào trong constructor cho listener khởi động sớm. Khi event đã có environment hoặc context, chỉ truy cập những API thực sự sẵn sàng ở pha đó.

## 4. Ví dụ Java 17+ chạy được với Spring Boot 3.5

Ví dụ dưới đây cho thấy:

- Listener nạp bằng `spring.factories` nhận được **`ApplicationStartingEvent`** và **`ApplicationEnvironmentPreparedEvent`**, khi Spring bean chưa tồn tại.
- Cũng listener đó vẫn có thể nhận sự kiện muộn **`ApplicationReadyEvent`**.
- Một bean `@Component` sử dụng `@EventListener` nhận `ApplicationReadyEvent`, minh họa rằng không cần factories cho event muộn.
- Kết quả được kiểm tra bằng bốn cờ boolean, tránh giả định thứ tự log console khi Boot khởi động.

Dự án dùng **Java 17**, **Spring Boot 3.5.16**, Gradle 8.4+; không cần web server hay database.

### 4.1. Cấu trúc

```text
boot-factories-listener-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── FactoriesDemoApplication.java
        │       ├── BootstrapEventsListener.java
        │       └── ReadyBeanObserver.java
        └── resources/
            └── META-INF/
                └── spring.factories
```

**`settings.gradle`**

```groovy
rootProject.name = 'boot-factories-listener-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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

springBoot {
    mainClass = 'demo.FactoriesDemoApplication'
}
```

Plugin Boot và dependency-management plugin giúp dùng các version dependency Spring tương thích. Nếu bạn không có Gradle cài sẵn, có thể tạo Gradle Wrapper bằng Gradle rồi dùng `./gradlew` (Linux/macOS) hoặc `gradlew.bat` (Windows); ví dụ dưới đây dùng lệnh `gradle` vì cấu trúc trên chưa kèm wrapper.

### 4.2. Listener nạp sớm: `BootstrapEventsListener.java`

```java
package demo;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class BootstrapEventsListener
        implements ApplicationListener<SpringApplicationEvent> {

    private static volatile boolean startingSeen;
    private static volatile boolean environmentSeen;
    private static volatile boolean readySeen;

    // Constructor không tham số, không phụ thuộc Spring bean.
    public BootstrapEventsListener() {
    }

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            startingSeen = true;
        } else if (event instanceof ApplicationEnvironmentPreparedEvent) {
            environmentSeen = true;
        } else if (event instanceof ApplicationReadyEvent) {
            readySeen = true;
        }
    }

    public static boolean startingSeen() {
        return startingSeen;
    }

    public static boolean environmentSeen() {
        return environmentSeen;
    }

    public static boolean readySeen() {
        return readySeen;
    }
}
```

Ở đây `ApplicationListener<SpringApplicationEvent>` nhận các Spring Boot event kế thừa `SpringApplicationEvent`, rồi dùng `instanceof` để lọc ba loại muốn kiểm tra. Đây là cách thuận tiện cho demo. Trong ứng dụng thật, nếu chỉ cần đúng một event, nên chọn generic cụ thể hơn, chẳng hạn `ApplicationListener<ApplicationEnvironmentPreparedEvent>`.

Các cờ `static` chỉ là công cụ để demo kiểm tra sau startup. Không dùng cờ static làm bộ nhớ nghiệp vụ production, đặc biệt khi một JVM khởi chạy nhiều `SpringApplication`, test chạy lặp hoặc nhiều class loader.

### 4.3. Bean listener chỉ nhận event muộn: `ReadyBeanObserver.java`

```java
package demo;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyBeanObserver {

    private volatile boolean readySeen;

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        readySeen = true;
    }

    public boolean isReadySeen() {
        return readySeen;
    }
}
```

Bean này được component scan tạo khi context chuẩn bị; `@EventListener` đăng ký method. Nó không cố nhận `ApplicationStartingEvent` vì event ấy phát **trước** giai đoạn component scan. Nhưng `ApplicationReadyEvent` xảy ra sau refresh và sau các application runners nên bean có thể nhận được.

### 4.4. Chương trình chính: `FactoriesDemoApplication.java`

```java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class FactoriesDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(FactoriesDemoApplication.class);

        // Demo chỉ cần startup events, không chạy web server.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ReadyBeanObserver bean =
                    context.getBean(ReadyBeanObserver.class);

            System.out.println("factories starting="
                    + BootstrapEventsListener.startingSeen());
            System.out.println("factories environment="
                    + BootstrapEventsListener.environmentSeen());
            System.out.println("factories ready="
                    + BootstrapEventsListener.readySeen());
            System.out.println("bean ready=" + bean.isReadySeen());
        }
    }
}
```

Spring Boot gọi `SpringApplication.run(...)` và phát các Boot lifecycle events tương ứng. Listener từ factories đã được tạo **trước** khi event khởi động sớm phát ra; bean observer chỉ có mặt sau khi context được xử lý.

Dùng `try-with-resources` giúp đóng `ConfigurableApplicationContext` sau khi in kết quả. `WebApplicationType.NONE` không tự khởi chạy embedded web server; bài chỉ tập trung vào cơ chế event.

### 4.5. File đăng ký: `src/main/resources/META-INF/spring.factories`

```properties
org.springframework.context.ApplicationListener=demo.BootstrapEventsListener
```

Chỉ file này đăng ký early listener. **Không cần** tạo `@Bean` cho `BootstrapEventsListener`, và **không cần** import nó trong `FactoriesDemoApplication`. Nếu file không có hoặc đặt sai thư mục resources, Spring Boot vẫn có thể chạy ứng dụng, nhưng các cờ `factories ...` sẽ cho `false` vì listener không nhận được event.

### 4.6. Chạy và kết quả

Chạy khi JDK 17 và Gradle 8.4+ đã sẵn có:

```bash
gradle bootRun
```

Các dòng `System.out.println` từ `FactoriesDemoApplication`:

```text
factories starting=true
factories environment=true
factories ready=true
bean ready=true
```

Gradle và Spring Boot có thể in thêm thông tin build/log tùy môi trường; bốn dòng trên là **phần kết quả kiểm tra của ứng dụng**, không phải toàn bộ output terminal.

**Tại sao kết quả đúng?**

1. Spring Boot tìm `META-INF/spring.factories` trên classpath và đăng ký class theo key `org.springframework.context.ApplicationListener` trước khi chạy các bước startup.
2. `ApplicationStartingEvent` được gửi ngay từ đầu quá trình run, trước khi có `Environment`/context; listener factories đã tồn tại nên đặt `startingSeen=true`.
3. Khi `Environment` được tạo và chuẩn bị, Boot phát `ApplicationEnvironmentPreparedEvent`; listener đặt `environmentSeen=true`.
4. Boot tạo/refresh context, chạy application/command-line runners (nếu có), rồi phát `ApplicationReadyEvent`; cả factories listener và bean `@EventListener` đều có thể nhận sự kiện này.
5. `app.run(args)` trả về sau giai đoạn ready khi khởi động thành công, nên chương trình đọc cả bốn cờ dưới đây đều bằng `true`.

Đây là ví dụ khởi động thành công một ứng dụng không-web, không có runner đặc biệt và dùng event multicaster đồng bộ mặc định. Khi bạn thêm listener bất đồng bộ, event handling của ứng dụng có thể cần đồng bộ hóa kiểm thử riêng.

## 5. Các sự kiện Spring Boot liên quan đến listener bootstrap

Vòng đời `SpringApplication` phát các event theo thứ tự chính:

| Sự kiện | Bối cảnh tại thời điểm phát | Có thể nhận bằng listener từ factories? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Vừa bắt đầu run; chưa có `Environment` và context | Có |
| `ApplicationEnvironmentPreparedEvent` | `Environment` có sẵn; context chưa được tạo | Có |
| `ApplicationContextInitializedEvent` | Context đã tạo và chạy initializers; chưa nạp bean definitions | Có |
| `ApplicationPreparedEvent` | Bean definitions đã nạp; chưa bắt đầu refresh | Có |
| `ApplicationStartedEvent` | Context đã refresh; trước `ApplicationRunner`/`CommandLineRunner` | Có |
| `ApplicationReadyEvent` | Các runner đã chạy xong; Boot đang công bố ứng dụng sẵn sàng | Có |
| `ApplicationFailedEvent` | Quá trình khởi động thất bại | Có, nếu listener đã đăng ký và failure event được phát |

Bên cạnh đó, Boot còn phát `AvailabilityChangeEvent` với các trạng thái **liveness/readiness** ở những mốc thích hợp. `AvailabilityChangeEvent` không phải subclass của `SpringApplicationEvent` theo cách lớp listener demo khai báo; nếu muốn quan sát availability state, sử dụng một listener có event type tương thích.

Cần phân biệt:

- **`ApplicationStartedEvent` của Spring Boot**: sau refresh, trước các runners.
- **`ContextStartedEvent` của Spring Framework**: phản ánh lời gọi `ConfigurableApplicationContext.start()`, không tự đồng nghĩa Boot đã khởi động.
- **`ContextRefreshedEvent`**: context đã refresh.
- **`ApplicationReadyEvent` của Spring Boot**: thời điểm sẵn sàng sau runners.
- **`ContextClosedEvent` của Spring Framework**: context chuẩn bị/đang được đóng.

Với nhiều context cha/con, các `ApplicationEvent` từ context con có thể propagate lên context cha, khiến listener nhận nhiều lần event có cùng loại. Nếu bạn xử lý một event liên quan cụ thể đến context, cần so sánh event source/context thay vì chỉ dựa vào class.

## 6. Đăng ký bằng code: `SpringApplication.addListeners` và `SpringApplicationBuilder.listeners`

Nếu chỉ cần listener cho **một ứng dụng hoặc một lần run**, không nhất thiết sử dụng factories:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new MyStartingListener());
app.run(args);
```

Ví dụ này là **đoạn minh họa**, trong đó `MyApplication` là class cấu hình và `MyStartingListener` implement `ApplicationListener<ApplicationStartingEvent>` với constructor phù hợp. Quan trọng là gọi `addListeners(...)` **trước** `run(...)`.

Tương tự với builder:

```java
new SpringApplicationBuilder(MyApplication.class)
        .listeners(new MyStartingListener())
        .run(args);
```

Cần import `org.springframework.boot.builder.SpringApplicationBuilder`. Hai cách trên hữu ích khi muốn kiểm soát cục bộ việc đăng ký, truyền tham số bằng constructor cho listener, hoặc chỉ bật listener trong một chế độ khởi động nhất định.

`spring.factories` phù hợp hơn khi:

- Listener nằm trong một **library** và muốn ứng dụng dùng library tự đăng ký listener lúc bootstrap.
- Listener luôn cần có mặt bất kể chỗ gọi `SpringApplication.run` ở đâu.
- Bạn muốn phân phối listener dưới dạng JAR mà không yêu cầu từng ứng dụng sửa `main()`.

Nhược điểm của auto-registration là **phạm vi toàn classpath**: nếu library nằm trong nhiều ứng dụng, mọi ứng dụng có thể tải listener ấy. Hãy tránh side effect nặng ở constructor và cung cấp cơ chế cấu hình/bật-tắt hành vi khi cần.

## 7. `spring.factories` và `AutoConfiguration.imports` trong Boot 3+

Đây là một nguồn gây nhầm lẫn rất phổ biến khi đọc các bài viết cũ:

| Mục đích | Spring Boot 3.5 | File/key |
| --- | --- | --- |
| Đăng ký listener để bắt early Boot application events | Được hỗ trợ | `META-INF/spring.factories` với key `org.springframework.context.ApplicationListener` |
| Đăng ký `ApplicationContextInitializer` dùng sớm | Được hỗ trợ theo cơ chế factories thích hợp | `META-INF/spring.factories` với key `org.springframework.context.ApplicationContextInitializer` |
| Đăng ký auto-configuration class | Dùng định dạng mới | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Ghi `EnableAutoConfiguration=...` trong `spring.factories` | Không còn là đường đăng ký auto-configuration trong Boot 3 | Chuyển sang `AutoConfiguration.imports` |

`AutoConfiguration.imports` thường có **mỗi tên auto-configuration trên một dòng**, không dùng key `ApplicationListener`. Ví dụ:

```text
demo.autoconfigure.ExampleAutoConfiguration
demo.autoconfigure.AnotherAutoConfiguration
```

Đây là **ví dụ về cấu trúc file auto-configuration**, không phải file thay thế cho listener factories ở bài này. Ngược lại, `spring.factories` là properties có key–value; không được đổi filename rồi giữ nguyên format.

Thông điệp chính khi nâng cấp từ Boot 2.x: Spring Boot 3 chuyển cách tìm **auto-configurations**, **không đồng nghĩa bỏ toàn bộ `spring.factories`**. Khóa `ApplicationListener` phục vụ bootstrap listeners vẫn có tác dụng.

## 8. Khi nào dùng `ApplicationListener`, khi nào dùng `EnvironmentPostProcessor`?

Một listener nhận `ApplicationEnvironmentPreparedEvent` có thể **đọc hoặc thay đổi** `ConfigurableEnvironment` khi Boot đang chuẩn bị startup, nhưng không nên mặc định dùng một listener cho mọi loại chỉnh sửa môi trường.

Ví dụ một listener early chỉ đọc property:

```java
public class ProfileObserver
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        String[] profiles = event.getEnvironment().getActiveProfiles();
        // Có thể kiểm tra metadata profile/environment ở pha này.
        // Không truy cập @Autowired service vì context chưa sẵn sàng.
    }
}
```

Đây là đoạn minh họa, cần import `ApplicationListener` và `ApplicationEnvironmentPreparedEvent`. Class phải được đăng ký sớm. Cần cân nhắc rằng thời điểm load một số config data, order của listeners và property sources ảnh hưởng những giá trị đã được cấu hình tại pha đó.

Nếu mục tiêu là **bổ sung/chỉnh sửa property sources có hệ thống**, Spring Boot có cơ chế `EnvironmentPostProcessor` phù hợp hơn với mục đích xử lý environment. Nó cũng có đường đăng ký bootstrap riêng. Không nên biến listener factories thành nơi chứa toàn bộ cấu hình phức tạp chỉ vì nó chạy sớm.

Nguyên tắc chọn:

- **Quan sát startup hoặc thất bại sớm:** `ApplicationListener<...>` qua `spring.factories`/`addListeners`.
- **Can thiệp cấu hình environment trước context:** cân nhắc `EnvironmentPostProcessor`.
- **Khởi tạo bean hoặc logic nghiệp vụ sau context:** `@Bean`, `@Component`, `@EventListener` hoặc `ApplicationRunner`.
- **Tác vụ khi ứng dụng thực sự sẵn sàng:** `ApplicationReadyEvent` hoặc runner theo ý nghĩa nghiệp vụ.
- **Dừng/start resource nền:** cân nhắc `SmartLifecycle` và shutdown callbacks, không ép mọi thao tác vào bootstrap event listener.

## 9. Thứ tự listener, lỗi startup và các giới hạn

### 9.1. Thứ tự

Một class loader có thể tìm thấy nhiều file `spring.factories` ở nhiều JAR. Không nên dựa vào thứ tự class được liệt kê trong files để điều phối các thao tác phụ thuộc nhau. Spring có cơ chế ordering cho listener, ví dụ `Ordered` hoặc `@Order` khi thích hợp.

```java
public final class OrderedStartingListener
        implements ApplicationListener<ApplicationStartingEvent>, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        // Quan sát startup trong thứ tự được Spring sắp xếp phù hợp.
    }
}
```

Đây là code minh họa, cần import `ApplicationListener`, `ApplicationStartingEvent` và `Ordered`. Giá trị order chỉ ảnh hưởng việc Spring sắp xếp các listener trong cơ chế dispatch tương ứng; nó **không biến các listener thành giao dịch nguyên tử** hay bảo đảm thứ tự hoàn tất nếu xử lý trên nhiều thread.

### 9.2. Sự kiện trước context không thể dựa vào dependency injection

Ở `ApplicationStartingEvent`, Spring chưa chuẩn bị `Environment` hay context. Tránh:

- Yêu cầu constructor injection một `@Service`/repository.
- Gọi `ApplicationContext.getBean(...)` khi chưa có context.
- Giả định một `@ConfigurationProperties` bean đã bind.
- Truy vấn cơ sở dữ liệu hoặc gọi API mạng tốn thời gian ở thread startup.

Ở `ApplicationEnvironmentPreparedEvent`, bạn có môi trường cấu hình để đọc nhưng **không có đảm bảo bean nghiệp vụ đã tồn tại**. Với `ApplicationContextInitializedEvent`, context đã được tạo nhưng **bean definitions chưa được load đầy đủ**. Với `ApplicationPreparedEvent`, context chưa refresh nên phần lớn bean không nên bị truy cập như thể ứng dụng đã sẵn sàng.

### 9.3. `ApplicationFailedEvent`

Nếu Boot không khởi động được, listener nhận `ApplicationFailedEvent` có thể hữu ích cho logging/telemetry. Nhưng không được mặc định `ApplicationContext` hay mọi bean luôn tồn tại:

```java
public final class FailureObserver
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        // Dùng thông tin lỗi có sẵn; context có thể chưa được tạo.
    }
}
```

Đây là đoạn minh họa cần import `ApplicationListener` và `ApplicationFailedEvent`. Listener phải được đăng ký sớm như các listener khác nếu muốn bao phủ các lỗi trước khi context có mặt.

Không nên để lỗi trong chính listener kiểm soát/giám sát làm phức tạp thêm quá trình fail fast. Ghi log an toàn, không phụ thuộc hạ tầng chưa khởi tạo, và giữ xử lý ngắn.

## 10. Kiểm thử `spring.factories` đúng cách

### 10.1. Kiểm thử có khởi chạy `SpringApplication`

Vì trọng tâm là early application events **trước khi context có bean**, một test chỉ dùng `ApplicationContextRunner` hoặc tự tạo `AnnotationConfigApplicationContext` không thay thế đầy đủ kiểm thử đường `SpringApplication.run(...)`. Bạn nên có một integration test chạy một ứng dụng Boot nhỏ với classpath chứa `META-INF/spring.factories`.

Các assert hữu ích:

1. Sau `run()` thành công, early listener đã nhận `ApplicationStartingEvent`.
2. `ApplicationEnvironmentPreparedEvent` được nhận trước giai đoạn tạo bean.
3. Listener chỉ khai báo như Spring bean không bị giả định đã nhận early events.
4. `ApplicationReadyEvent` được nhận sau khi runners hoàn tất, nếu startup thành công.
5. Nếu cố tình tạo lỗi startup, listener factories có thể quan sát `ApplicationFailedEvent`, kể cả khi context chưa refresh.
6. Nếu nhiều JAR có đăng ký listener, kiểm tra không bị xử lý lặp và thứ tự chỉ dựa vào quy tắc công khai.

Mẫu demo ở mục 4 đã có assert quan sát bằng boolean sau khi `app.run(args)`. Khi viết JUnit, có thể thay các dòng print bằng `assertTrue(...)` và **reset state static giữa các test** nếu giữ cách lưu trạng thái demo, hoặc thiết kế một observer có thể kiểm tra độc lập theo mỗi lần run.

### 10.2. Kiểm tra đúng vị trí trong build

Nếu listener không được tải:

```bash
gradle clean processResources
```

Sau đó kiểm tra resource đã được copy vào thư mục build tương ứng, ví dụ:

```text
build/resources/main/META-INF/spring.factories
```

Nếu build `bootJar`, hãy kiểm tra JAR có chứa resource và class listener đúng đường dẫn. Nếu dùng nhiều plugin đóng gói/relocation, kiểm tra resources không bị ghi đè. Không nên sửa `spring.factories` nằm trong dependency bên thứ ba để thử nghiệm; hãy cung cấp file trong module ứng dụng hoặc module library do bạn quản lý.

### 10.3. Các lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Listener không nhận `ApplicationStartingEvent` | Chỉ dùng `@Component`/`@Bean`; đăng ký quá muộn | Dùng `spring.factories` hoặc `addListeners` trước `run()` |
| Listener factories không chạy | Sai đường dẫn `META-INF/spring.factories`, sai key hoặc resource không trong classpath | Kiểm tra tên file, key đầy đủ, `processResources` và JAR |
| `IllegalArgumentException`/lỗi tạo factory listener | Sai tên class, class không implement `ApplicationListener`, constructor không phù hợp | Đảm bảo class public, có no-arg constructor dùng được và đúng interface |
| Chưa có `Environment` | Đang xử lý `ApplicationStartingEvent` | Chờ `ApplicationEnvironmentPreparedEvent` cho nhu cầu đọc environment |
| `@Autowired` service null/không sẵn sàng | Listener được tạo trước ApplicationContext | Tránh phụ thuộc bean trong bootstrap listener |
| `ApplicationStartedEvent` bị nhầm với `ContextStartedEvent` | Import sai package hoặc lẫn Spring Boot với Spring Framework | Kiểm tra tên class và thời điểm phát thực tế |
| Listener xử lý cùng event hai lần | Vừa đăng ký factories vừa bean, nhiều context hoặc nhiều đăng ký | Dùng một đường đăng ký và kiểm tra context/event source |
| Sau nâng cấp Boot 3, auto-configuration không được nạp | Vẫn khai báo `EnableAutoConfiguration` trong `spring.factories` | Chuyển auto-config sang `AutoConfiguration.imports`; giữ key ApplicationListener riêng |
| Test chỉ tạo ApplicationContext không nhận early event | Không chạy `SpringApplication` lifecycle | Viết integration test khởi chạy `SpringApplication.run` |
| Startup rất chậm hoặc bị ngắt bởi listener | Xử lý I/O/blocking hoặc exception ở bootstrap | Giữ listener ngắn, an toàn; đưa tác vụ dài sang giai đoạn phù hợp |

## 11. Checklist áp dụng trong dự án

Trước khi đưa listener từ `spring.factories` vào dự án hoặc thư viện, xác nhận:

- **Event muốn nhận là event nào?** Nếu xảy ra trước context, cần đăng ký sớm; nếu chỉ nhận event muộn, hãy cân nhắc bean `@EventListener` đơn giản hơn.
- **Đúng resource path và key `ApplicationListener` chưa?** Kiểm tra cả artifact đóng gói, không chỉ file trong source.
- **Class có thể được tạo ngoài Spring context không?** Tránh phụ thuộc DI trong constructor và logic khởi tạo nặng.
- **Có tránh đăng ký trùng không?** Đừng vô tình vừa khai báo factories vừa dùng `@Component` cho cùng listener.
- **Listener có an toàn ở giai đoạn đó không?** `ApplicationStartingEvent` chưa có environment; `ApplicationFailedEvent` có thể chưa có context.
- **Thứ tự và lỗi có được thiết kế rõ không?** Không làm chậm startup bằng công việc không bắt buộc; không dùng ordering ngầm.
- **Phiên bản Boot nào?** Phân biệt `ApplicationListener` trong `spring.factories` với auto-configuration trong `AutoConfiguration.imports` ở Boot 3+.
- **Có test startup thật không?** Một test qua `SpringApplication.run` giúp phát hiện lỗi path, packaging, class loading và listener registration.

**Tóm tắt:** Để lắng nghe các sự kiện Spring Boot xuất hiện trước khi `ApplicationContext` sẵn sàng, khai báo class implement `ApplicationListener` trong `META-INF/spring.factories` bằng key `org.springframework.context.ApplicationListener`. Với các sự kiện muộn, bean `@EventListener` thường đủ. Trong Spring Boot 3+, không nhầm cơ chế listener này với đăng ký auto-configuration qua `AutoConfiguration.imports`.

## Tài liệu chính thức

- [Spring Boot 3.5 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Boot 3.5 — SpringApplication and listener bootstrap customization](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot — Customize Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html)
- [Spring Boot 3.5 — Spring Boot application event classes](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/package-summary.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html)
- [Spring Boot 3 Migration Guide — Auto-configuration files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
