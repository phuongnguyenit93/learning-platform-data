# Viết ApplicationListener với kiểu sự kiện cụ thể

## Mục tiêu học tập

Trong Spring Boot, `ApplicationListener<E>` là một điểm mở rộng để nhận thông báo khi **một sự kiện cụ thể** được phát. Thay vì bắt mọi sự kiện rồi viết một chuỗi `if/else instanceof`, ta có thể khai báo trực tiếp kiểu cần quan sát:

~~~java
public final class OrderPlacedListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        System.out.println("New order: " + event.getOrderId());
    }
}
~~~

Đoạn trên **chỉ là minh họa chữ ký**; bài sẽ cung cấp chương trình Spring Boot hoàn chỉnh, gồm lớp sự kiện, cách đăng ký listener và cách phát sự kiện.

Sau bài này, bạn có thể:

1. Giải thích kiểu generic `E extends ApplicationEvent` và phương thức `onApplicationEvent(E event)`.
2. Viết listener nhận đúng `ApplicationReadyEvent`, `ApplicationEnvironmentPreparedEvent` hoặc một sự kiện nghiệp vụ kế thừa `ApplicationEvent`.
3. Chọn cách đăng ký: `@Component`, `@Bean`, `SpringApplication.addListeners(...)` hoặc `META-INF/spring.factories`.
4. Hiểu vì sao **listener là bean không nhận được sự kiện khởi động quá sớm**.
5. Phát sự kiện bằng `ApplicationEventPublisher` và nhận biết mặc định đồng bộ, xử lý exception, thứ tự listener và các ràng buộc về transaction.
6. Chạy và kiểm tra ví dụ Java 17+ / Spring Boot 3.3.13 với kết quả đầu ra được giải thích.

**Ngữ cảnh:** Spring Boot Application Runtime → Listener. Bài tập trung vào **viết listener có generic type cụ thể**; những cơ chế nâng cao như asynchronous multicaster và transactional events được giới thiệu ở mức cần thiết để dùng API đúng.

## 1. ApplicationListener là gì?

Spring Framework cung cấp functional interface:

~~~java
package org.springframework.context;

// Khai báo rút gọn nhằm minh họa API, không tạo file này trong project.
@FunctionalInterface
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {

    void onApplicationEvent(E event);
}
~~~

Trong thực tế hãy **import API của Spring**, không tự định nghĩa lại interface. Ý nghĩa:

- `ApplicationListener` là hợp đồng của một thành phần **lắng nghe** sự kiện.
- `E` biểu diễn **loại sự kiện** listener quan tâm. Giới hạn `E extends ApplicationEvent` bảo đảm kiểu này là subclass của `org.springframework.context.ApplicationEvent`.
- `onApplicationEvent(E event)` được gọi khi một event tương thích được phát trong một phạm vi mà listener đã được đăng ký.
- Spring dùng metadata kiểu generic khi có thể để **lọc theo type**, không yêu cầu mỗi listener tự kiểm tra `instanceof` cho mọi sự kiện không liên quan.
- Callback nhận đối tượng event, nhưng **không có nghĩa mọi listener luôn chạy trên một thread khác** hoặc luôn có transaction.

Ví dụ:

~~~java
public final class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

Đoạn trên chưa độc lập: cần các import `ApplicationListener`, `ApplicationReadyEvent`, và một cơ chế đăng ký listener. Một `ReadyListener` được đăng ký hợp lệ sẽ nhận `ApplicationReadyEvent`, nhưng không vì vậy mà nhận `ApplicationStartingEvent`, `ContextRefreshedEvent` hay sự kiện nghiệp vụ không liên quan.

### So sánh ba dạng generic

| Khai báo listener | Phạm vi nhận dự kiến | Khi nên dùng |
| --- | --- | --- |
| `ApplicationListener<ApplicationReadyEvent>` | Ready event (và subtype tương thích nếu có) | Làm việc khi startup Boot gần hoàn tất |
| `ApplicationListener<OrderPlacedEvent>` | Sự kiện nghiệp vụ `OrderPlacedEvent` | Tách publisher khỏi logic phản ứng nghiệp vụ |
| `ApplicationListener<ApplicationEvent>` | Nhiều loại Spring `ApplicationEvent` | Diagnostics/middleware khi thực sự cần phân loại nhiều event |

**Ưu tiên type hẹp** khi đã biết sự kiện mình cần: code dễ đọc, IDE kiểm tra kiểu tốt hơn và tránh làm listener thực thi với những event không liên quan.

Nếu một listener cần nhiều loại sự kiện với cách xử lý khác nhau, có thể tạo **nhiều listener có type cụ thể** thay vì dồn tất cả vào một listener tổng quát. Trường hợp cần phân loại động theo `ResolvableType` hoặc hỗ trợ điều kiện phức tạp có thể tìm hiểu `GenericApplicationListener`/`SmartApplicationListener`, nhưng phần lớn code nghiệp vụ không cần chúng.

## 2. Sự kiện đến từ đâu?

Spring có hai nhóm ví dụ dễ gặp.

### 2.1. Sự kiện vòng đời ứng dụng do Spring Boot phát

Các sự kiện trong package `org.springframework.boot.context.event` gồm:

- `ApplicationStartingEvent`: rất sớm, trước khi `Environment` và `ApplicationContext` được tạo.
- `ApplicationEnvironmentPreparedEvent`: môi trường đã chuẩn bị, chưa tạo application context.
- `ApplicationContextInitializedEvent`: context đã tạo, initializers đã chạy, chưa nạp bean definitions.
- `ApplicationPreparedEvent`: bean definitions đã nạp, trước `refresh`.
- `ApplicationStartedEvent`: sau context refresh, **trước** `ApplicationRunner`/`CommandLineRunner`.
- `ApplicationReadyEvent`: sau các runner, khi lần khởi động đã tiến gần mốc sẵn sàng.
- `ApplicationFailedEvent`: nhánh thất bại khi SpringApplication khởi động không thành công.

Ngoài ra có `ContextRefreshedEvent` của Spring Framework và `AvailabilityChangeEvent` của Spring Boot. Chúng cũng có thể được quan sát qua event infrastructure phù hợp, nhưng khác type, khác ý nghĩa.

Ví dụ:

~~~java
public final class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {
    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        // Chỉ xử lý khi event này thực sự được phát và listener đã đăng ký.
    }
}
~~~

Một **HTTP request thành công** không tự phát `ApplicationReadyEvent`. Event này gắn với tiến trình khởi động ứng dụng, không phải callback “mỗi request”.

### 2.2. Sự kiện nghiệp vụ do ứng dụng tự phát

Ví dụ khi nghiệp vụ xác nhận đơn hàng, code có thể phát `OrderPlacedEvent`. Publisher không phải gọi trực tiếp từng listener; Spring event infrastructure phân phối event cho các listener đã đăng ký, phù hợp type.

~~~text
OrderService
    |
    +-- ApplicationEventPublisher.publishEvent(OrderPlacedEvent)
              |
              +-- OrderPlacedListener
              +-- AuditOrderListener (nếu được đăng ký)
              +-- Các listener type khác: không cần được gọi
~~~

Điều này giúp tách bớt trách nhiệm, nhưng event trong process **không tự biến thành message bền vững**. Nếu yêu cầu xử lý không mất dữ liệu giữa các instance/process hoặc qua crash, cần thiết kế transaction, outbox, queue/broker hoặc quy trình retry phù hợp.

## 3. Hai điều kiện để nhận event: đúng type và đăng ký đúng thời điểm

Một listener dù viết đúng generic vẫn không nhận event nếu **không được đăng ký vào nơi phát** hoặc **được đăng ký quá muộn**.

| Phương án đăng ký | Phù hợp với | Có bắt được ApplicationStartingEvent không? |
| --- | --- | --- |
| `@Component` trên class triển khai `ApplicationListener<E>` | Listener nghiệp vụ hoặc event sau khi bean factory sẵn sàng | **Không**, vì bean chưa tồn tại lúc Starting |
| `@Bean` trả `ApplicationListener<E>` | Quản lý listener bằng cấu hình Spring | **Không** với các event trước khi bean được tạo |
| `SpringApplication.addListeners(listener)` **trước `run()`** | Các sự kiện Boot rất sớm; cấu hình ngay trong `main` | **Có** nếu generic type phù hợp |
| `SpringApplicationBuilder.listeners(listener)` | Dự án dùng builder để khởi động | **Có** nếu đăng ký trước run |
| `META-INF/spring.factories` với key `ApplicationListener` | Library hoặc app muốn auto-register listener sớm | **Có** khi metadata được Boot nạp đúng |
| `@EventListener` trên method của bean | Event khi container đã quản lý bean | **Không** với event được phát trước bean initialization |

**Vấn đề rất hay gặp:** Viết:

~~~java
@Component
public class EarlyListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        System.out.println("Environment prepared");
    }
}
~~~

Mã trên **hợp lệ về Java**, nhưng nếu chỉ trông đợi `@Component` scan để đăng ký listener thì **quá muộn** cho `ApplicationEnvironmentPreparedEvent`. Lúc đó application context còn chưa được tạo để scan bean. Không giải quyết bằng cách thêm `@Order(-100)`: thứ tự giữa các listener không thể thay đổi thời điểm một bean được tạo.

**Cách đúng:** Tạo listener sớm bằng `new`, rồi `addListeners(...)` trước `run(...)`, hoặc khai báo class trong `spring.factories`.

## 4. Ví dụ hoàn chỉnh: ba ApplicationListener có kiểu cụ thể

Chúng ta sẽ tạo một ứng dụng CLI non-web để log rõ ràng:

- `EnvironmentPreparedListener`: được thêm vào `SpringApplication` trước `run`; chỉ nghe `ApplicationEnvironmentPreparedEvent`.
- `OrderPlacedListener`: một Spring bean; chỉ nghe custom `OrderPlacedEvent`.
- `ReadyListener`: một Spring bean; chỉ nghe `ApplicationReadyEvent`.
- `ApplicationRunner`: phát custom event để kiểm tra trình tự callback.

**Yêu cầu:** JDK 17+ và Gradle tương thích Spring Boot 3.3.13. Bài dùng Spring Boot **3.3.13** để đồng nhất API, không cần embedded web server hoặc database.

### 4.1. Cấu trúc thư mục

~~~text
typed-listener-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/listeners/
    ├── TypedListenerApplication.java
    ├── EnvironmentPreparedListener.java
    ├── OrderPlacedEvent.java
    ├── OrderPlacedListener.java
    └── ReadyListener.java
~~~

**Tệp `settings.gradle`:**

~~~groovy
rootProject.name = 'typed-listener-demo'
~~~

**Tệp `build.gradle`:**

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
    mainClass = 'com.example.listeners.TypedListenerApplication'
}
~~~

Plugin Spring Boot đã có phiên bản tường minh; `platform(...)` quản lý phiên bản của starter theo BOM Spring Boot 3.3.13. Không cần web starter vì ví dụ chỉ minh họa lifecycle và event trong context.

### 4.2. Listener sự kiện Environment: bắt đầu từ rất sớm

**Tệp `EnvironmentPreparedListener.java`:**

~~~java
package com.example.listeners;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class EnvironmentPreparedListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        System.out.println("EARLY: environment prepared");
    }
}
~~~

Không đặt `@Component` ở class này: chúng ta sẽ khởi tạo và thêm nó **trước** `SpringApplication.run`. Đây là cách chắc chắn cho listener cần nhận event trước khi Spring tạo application context.

Trong callback, `event.getEnvironment()` đã tồn tại. Nhưng không được gọi `event.getApplicationContext()` vì type sự kiện này không cung cấp context. Không inject repository/service của ứng dụng trong constructor listener vì bean chưa sẵn sàng.

### 4.3. Định nghĩa custom ApplicationEvent

**Tệp `OrderPlacedEvent.java`:**

~~~java
package com.example.listeners;

import java.util.Objects;
import org.springframework.context.ApplicationEvent;

public final class OrderPlacedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderPlacedEvent(Object source, String orderId) {
        super(source);
        this.orderId = Objects.requireNonNull(orderId, "orderId");
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Phân tích:

- `OrderPlacedEvent` **kế thừa** `ApplicationEvent` để có thể dùng làm kiểu `E` cho `ApplicationListener<OrderPlacedEvent>`.
- Constructor `super(source)` khai báo đối tượng nguồn của sự kiện; giá trị nguồn không được `null`. Ở ví dụ này sẽ dùng instance ứng dụng làm nguồn.
- `orderId` là dữ liệu nghiệp vụ cần truyền cho listener. `final` và không có setter giúp payload của event ổn định trong quá trình truyền; nếu chứa object mutable, cần quản lý tính bất biến riêng.
- Event này **không tự được phát** chỉ vì có class. Một thành phần phải gọi `publishEvent(...)`.

Không nên chứa toàn bộ JPA entity đang mở lazy relations trong event rồi chuyển sang thread khác mà không phân tích transaction và persistence context. Trong ví dụ, `String orderId` là dữ liệu gọn, dễ hiểu.

### 4.4. Listener nghiệp vụ được Spring quản lý

**Tệp `OrderPlacedListener.java`:**

~~~java
package com.example.listeners;

import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public final class OrderPlacedListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        System.out.println("ORDER_LISTENER: " + event.getOrderId());
    }
}
~~~

`@Component` làm Spring component scanning phát hiện class. Khi context refresh, Spring quản lý và đăng ký nó với event multicaster. Generic type `OrderPlacedEvent` là contract lọc sự kiện: listener này **không** nhận `ApplicationReadyEvent` hay `ApplicationEnvironmentPreparedEvent`.

Nếu callback yêu cầu dependency như `AuditRepository`, có thể dùng constructor injection vào listener bean. Lưu ý rằng listener này **không tồn tại sớm** như `EnvironmentPreparedListener`, nên không dùng nó để sửa quá trình nạp Config Data trước khi context được tạo.

### 4.5. Listener quan sát mốc Ready

**Tệp `ReadyListener.java`:**

~~~java
package com.example.listeners;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public final class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("READY_LISTENER: application ready");
    }
}
~~~

Ở đây `@Component` là hợp lý: `ApplicationReadyEvent` được phát **sau** khi context đã refresh và startup runners đã hoàn tất. Bean listener đã được tạo/đăng ký ở giai đoạn trước đó.

`ApplicationReadyEvent` không phải `AvailabilityChangeEvent<ReadinessState>`. Boot phát ready event rồi mới phát readiness accepting-traffic state; chúng là hai đối tượng sự kiện khác nhau, có thể dùng hai listener type riêng nếu ứng dụng thực sự cần cả hai.

### 4.6. Lớp main, publisher và ApplicationRunner

**Tệp `TypedListenerApplication.java`:**

~~~java
package com.example.listeners;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TypedListenerApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(TypedListenerApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Thêm trước run: listener nhận được event EnvironmentPrepared.
        application.addListeners(new EnvironmentPreparedListener());

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner publishOrder(ApplicationEventPublisher publisher) {
        return args -> {
            System.out.println("RUNNER: before publish");

            publisher.publishEvent(
                    new OrderPlacedEvent(this, "ORD-001"));

            System.out.println("RUNNER: after publish");
        };
    }
}
~~~

Giải thích từng trách nhiệm:

1. `SpringApplication` tạo context non-web nhờ `WebApplicationType.NONE`. `Banner.Mode.OFF` và `setLogStartupInfo(false)` giảm những dòng startup do Boot ghi, nhưng không vô hiệu hóa toàn bộ logging.
2. `application.addListeners(new EnvironmentPreparedListener())` diễn ra trước `run`; listener có thể thấy event sớm đúng kiểu.
3. `@SpringBootApplication` và component scanning phát hiện `OrderPlacedListener` cùng `ReadyListener` trong package `com.example.listeners`.
4. Spring inject `ApplicationEventPublisher` vào factory method `@Bean` để Runner có thể phát một `OrderPlacedEvent`. `ApplicationEventPublisher` không phải HTTP message broker; nó là API của cơ chế event trong context.
5. `ApplicationRunner` chạy **sau** `ApplicationStartedEvent` và **trước** `ApplicationReadyEvent`.
6. Theo mặc định, Spring event multicaster đồng bộ: listener `OrderPlacedListener` chạy khi `publishEvent(...)` được gọi, rồi điều khiển trở về runner. Nếu cấu hình multicaster bất đồng bộ, thứ tự hoàn tất có thể khác.
7. `try-with-resources` đóng `ConfigurableApplicationContext` sau thí nghiệm. Chỉ dùng mẫu này cho ứng dụng CLI ngắn hạn; ứng dụng server chạy dài không nên đóng context ngay khi `run` trở về.

### 4.7. Chạy và kiểm tra stdout

Trong thư mục `typed-listener-demo`, với Gradle đã cài:

~~~bash
gradle bootRun
~~~

Nếu project đã có Gradle Wrapper, có thể chạy `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows. Project mẫu không tự sinh wrapper; cần có Gradle bên ngoài hoặc thêm wrapper riêng.

**Các dòng do mã Java của ví dụ tự in**, bỏ qua log framework/Gradle và giả sử không thêm listener khác có side effect, xuất hiện theo thứ tự:

~~~text
EARLY: environment prepared
RUNNER: before publish
ORDER_LISTENER: ORD-001
RUNNER: after publish
READY_LISTENER: application ready
MAIN: run returned
MAIN: context closed
~~~

Bảng đọc kết quả:

| Dòng log | Được in ở đâu? | Tại sao xuất hiện lúc đó? |
| --- | --- | --- |
| `EARLY: environment prepared` | `EnvironmentPreparedListener` | Environment đã được chuẩn bị, trước khi context được tạo. |
| `RUNNER: before publish` | `ApplicationRunner` | Context đã refresh; runner bắt đầu tác vụ. |
| `ORDER_LISTENER: ORD-001` | `OrderPlacedListener` | Publisher phát đúng `OrderPlacedEvent`; listener được chọn theo type. |
| `RUNNER: after publish` | `ApplicationRunner` | Với mặc định đồng bộ, callback listener đã trả về. |
| `READY_LISTENER: application ready` | `ReadyListener` | Boot phát `ApplicationReadyEvent` sau runners. |
| `MAIN: run returned` | `main` | Lời gọi `application.run(args)` hoàn tất. |
| `MAIN: context closed` | `main` | `try-with-resources` đóng context sau khi dùng. |

**Kiểm tra quan trọng:** Không có `ORDER_LISTENER` khi Boot phát `ApplicationReadyEvent`; không có `READY_LISTENER` khi runner phát `OrderPlacedEvent`. Generic type giúp Spring định tuyến đến listener quan tâm.

## 5. Cách dùng @Bean thay vì @Component

Không phải lúc nào cũng cần class listener mang `@Component`. Nếu sở hữu class config, bạn có thể tạo bean:

~~~java
@Configuration
class ListenerConfiguration {

    @Bean
    ApplicationListener<OrderPlacedEvent> extraOrderListener() {
        return event ->
                System.out.println("EXTRA_ORDER: " + event.getOrderId());
    }
}
~~~

Đây là **đoạn minh họa bổ sung**, không phải một tệp cần thiết cho project mục 4. Cần import `@Configuration`, `@Bean` và `ApplicationListener`. Khi bean được tạo và đăng ký, nó nghe `OrderPlacedEvent`. Generic return type trên phương thức `@Bean` cho phép Spring khai thác thông tin kiểu; nếu làm mờ thành một type/raw bean không đủ metadata, việc xác định type sự kiện có thể kém rõ ràng.

Nếu thêm bean này vào project mẫu, sẽ có **thêm một listener** nhận event, nên stdout mẫu ở mục 4.7 thay đổi. Không sử dụng hai listener có side effect không idempotent mà không chủ ý.

Một điểm khác biệt quan trọng: một `@Bean ApplicationListener<ApplicationEnvironmentPreparedEvent>` vẫn quá muộn cho event environment-prepared đầu tiên. `@Bean` và `@Component` đều phụ thuộc vào application context. Khả năng viết lambda không làm listener xuất hiện sớm hơn lifecycle của container.

## 6. Đăng ký listener sớm qua spring.factories

Khi tạo starter/library cần tự đăng ký listener trước context creation, có thể dùng:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.context.ApplicationListener=com.example.listeners.EnvironmentPreparedListener
~~~

Với cách này, Boot nạp class `EnvironmentPreparedListener` theo cơ chế factories. Class mẫu có constructor không đối số nên phù hợp. **Để thử riêng đường spring.factories**, bỏ dòng:

~~~java
application.addListeners(new EnvironmentPreparedListener());
~~~

ở `main`. Nếu đồng thời giữ cả hai đường đăng ký, dễ có **hai instance listener** và log/side effect bị lặp; không nên dựa vào việc Boot tự loại trừ mọi kiểu đăng ký trùng.

Không nhầm key trên với:

~~~properties
org.springframework.boot.BootstrapRegistryInitializer=...
~~~

Đây là một điểm mở rộng khác, nhận `BootstrapRegistry` ở pha rất sớm. Cũng không đặt `ApplicationListener` vào `AutoConfiguration.imports` — file đó là cơ chế dành cho auto-configuration.

### Nếu chỉ quan sát ApplicationStartingEvent?

Một listener kiểu:

~~~java
public final class StartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Starting now");
    }
}
~~~

là minh họa; cần import `ApplicationStartingEvent` và `ApplicationListener`, rồi đăng ký bằng `addListeners` **trước run** hoặc `spring.factories`. Tại thời điểm này **chưa có Environment lẫn ApplicationContext**, nên không inject bean và không gọi các API yêu cầu context đang sống. Đây là ví dụ cho việc **cả generic type lẫn thời điểm đăng ký** phải đúng.

## 7. ApplicationListener so với @EventListener

Hai cách nhận event cùng dùng cơ chế của Spring nhưng khác cú pháp:

**Kiểu interface:**

~~~java
@Component
class InventoryListener implements ApplicationListener<OrderPlacedEvent> {
    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        // Xử lý event type cụ thể.
    }
}
~~~

**Kiểu annotation:**

~~~java
@Component
class InventoryObserver {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        // Kiểu event được suy luận từ tham số method.
    }
}
~~~

Hai đoạn trên chỉ minh họa, không thêm chúng vào ví dụ mục 4 khi muốn giữ đúng stdout. Cần các import tương ứng; và cả hai đều trở thành **listener bean sau khi context quản lý chúng**.

| Tiêu chí | `ApplicationListener<E>` | `@EventListener` |
| --- | --- | --- |
| Khai báo type | Generic `E` trên interface | Tham số method hoặc thuộc tính annotation |
| Callback | `onApplicationEvent(E event)` | Method do ứng dụng định nghĩa |
| Đăng ký sớm trước context | Có, bằng instance + `addListeners`/`spring.factories` | Không theo cách bean method thông thường |
| Nhiều event type | Thường dùng nhiều class/interface hoặc kiểu rộng và lọc | Có hỗ trợ điều kiện và nhiều method |
| Phụ thuộc Spring API ở class | Có | Annotation Spring trên method |
| Mức dễ kiểm thử | Có thể gọi `onApplicationEvent` trực tiếp | Có thể gọi method xử lý hoặc test qua context |

Chọn `ApplicationListener<E>` khi muốn **hợp đồng listener tường minh**, class có một trách nhiệm rõ ràng hoặc cần đăng ký trước context. Chọn `@EventListener` khi đã có bean và muốn method ngắn, hoặc cần điều kiện annotation (như `condition`) mà không phải tạo class riêng.

Đừng dùng `@EventListener` như giải pháp cho một `ApplicationEnvironmentPreparedEvent` vốn đã xảy ra trước khi bean tồn tại.

## 8. Sự kiện tự định nghĩa: type-safe và phạm vi

### Lớp sự kiện cần kế thừa ApplicationEvent

Giới hạn generic của `ApplicationListener<E>` yêu cầu `E extends ApplicationEvent`. Ví dụ:

~~~java
record OrderPlaced(String orderId) {}
~~~

đây là một Java record **không** kế thừa `ApplicationEvent`, nên **không thể** trực tiếp khai báo:

~~~java
// KHÔNG HỢP LỆ về giới hạn kiểu E:
ApplicationListener<OrderPlaced> listener = event -> {};
~~~

Đoạn thứ hai cố ý minh họa **lỗi biên dịch**, không đưa vào source chạy. Nếu muốn xuất bản record như payload object, Spring Framework hỗ trợ `ApplicationEventPublisher.publishEvent(Object)` và có thể bọc nó thành `PayloadApplicationEvent<T>`. Khi đó có thể dùng:

~~~java
ApplicationListener<PayloadApplicationEvent<OrderPlaced>>
        listener = event ->
                System.out.println(event.getPayload().orderId());
~~~

Đoạn là **minh họa API**, cần import `ApplicationListener`, `PayloadApplicationEvent` và định nghĩa record `OrderPlaced`. Bạn cũng có thể dùng `@EventListener` với tham số là record payload. Trong bài thực hành chính, ta chủ động khai báo `OrderPlacedEvent extends ApplicationEvent` để type parameter là rõ ràng và không phụ thuộc wrapper.

### Publisher không gắn với một listener cụ thể

~~~java
publisher.publishEvent(new OrderPlacedEvent(this, "ORD-001"));
~~~

Publisher không cần gọi `orderPlacedListener.onApplicationEvent(event)`. Việc định tuyến dựa vào event infrastructure và các listener được đăng ký. Nhờ đó có thể thêm audit/notification listener mà không sửa trực tiếp publisher.

Tuy nhiên **event không phải RPC**. Đừng dựa vào return value của listener để trả kết quả cho nghiệp vụ phát event; `onApplicationEvent` trả `void`. Nếu phía phát cần một kết quả đồng bộ có cam kết, có thể phù hợp hơn khi gọi service interface trực tiếp.

## 9. Đồng bộ, thứ tự listener và ngoại lệ

### Mặc định đồng bộ

Với cấu hình mặc định của `SimpleApplicationEventMulticaster`, phần lớn listener được thực thi **đồng bộ** trên thread phát event. Trong ví dụ, vì runner gọi `publisher.publishEvent(...)`, dòng `ORDER_LISTENER` xuất hiện trước `RUNNER: after publish`.

Điều này có hệ quả:

1. Listener chạy lâu khiến lời gọi `publishEvent` trả về muộn.
2. Listener ném unchecked exception có thể làm exception đi ngược lên publisher.
3. Nếu publisher đang nằm trong `ApplicationRunner`, exception không xử lý có thể khiến **Spring Boot startup thất bại** và không đạt `ApplicationReadyEvent`.
4. Nếu publisher đang xử lý HTTP request, một listener đồng bộ bị lỗi có thể ảnh hưởng response/request đó, tùy chính sách exception handling.

**Không nên xem event listener như “fire-and-forget” bất đồng bộ** nếu chưa tự cấu hình một executor/multicaster phù hợp.

### Điều chỉnh thứ tự

Nếu có hai listener cho cùng event và thật sự cần thứ tự, có thể dùng `@Order` hoặc triển khai `Ordered` khi được hỗ trợ bởi cơ chế đăng ký/sắp xếp listener:

~~~java
@Component
@Order(10)
class FirstOrderListener implements ApplicationListener<OrderPlacedEvent> {
    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        // Ưu tiên xử lý theo thứ tự listener.
    }
}
~~~

Đây là **minh họa một phần**, cần import `Component`, `Order` và `ApplicationListener`. Giá trị order nhỏ hơn thường có mức ưu tiên cao hơn. Không nên dùng thứ tự listener thay cho quan hệ nghiệp vụ bắt buộc; nếu B phải chỉ chạy sau khi A commit dữ liệu thành công, hãy thiết kế transaction/coordination phù hợp.

Khi event delivery được chuyển sang bất đồng bộ, **thứ tự gọi hoặc lập lịch không bảo đảm thứ tự hoàn tất công việc**. Một listener có order thấp hơn vẫn có thể kết thúc sau listener khác.

### Listener lỗi có thể làm hỏng đường khởi động

Ví dụ **cố ý gây lỗi**:

~~~java
@Override
public void onApplicationEvent(OrderPlacedEvent event) {
    throw new IllegalStateException("Order listener failed");
}
~~~

Đây chỉ là thân callback minh họa, không phải chỉnh sửa cần thêm vào code chạy. Nếu nó được gọi đồng bộ từ runner và không có xử lý exception, `SpringApplication.run(...)` có thể thất bại trước ready. Vì vậy listener cần chọn chính sách lỗi rõ: lỗi phải làm nghiệp vụ thất bại, hay lỗi có thể retry/ghi lại riêng?

Không nên “nuốt” mọi exception chỉ để ứng dụng tiếp tục, đặc biệt khi listener đảm nhận side effect quan trọng như ghi audit bắt buộc hoặc thay đổi số dư.

## 10. Transaction và độ tin cậy

Một event được phát từ trong transaction **không tự chờ commit**. Với listener đồng bộ thông thường, callback có thể chạy trước khi transaction được commit. Nếu listener gửi email hoặc gọi hệ thống ngoài, sau đó transaction DB rollback, hệ thống có thể đã gửi thông báo cho giao dịch chưa được xác nhận.

Ví dụ tư duy:

~~~text
@Transactional orderService.placeOrder(...)
    |
    +-- lưu Order (chưa commit)
    +-- publishEvent(OrderPlacedEvent)
    |      └-- listener gửi email ngay (nếu đồng bộ)
    |
    +-- transaction rollback
           └-- Email đã gửi không tự được thu hồi
~~~

Khi cần callback gắn với transaction, Spring có `@TransactionalEventListener` (thường dùng `AFTER_COMMIT`) trong ngữ cảnh quản lý transaction phù hợp. Nó **không** có nghĩa event được lưu bền vững và tự phân phối lại sau crash. Với outbox, ứng dụng ghi bản ghi sự kiện trong cùng transaction rồi có worker/broker xử lý và retry. Mỗi giải pháp phục vụ một mức bảo đảm khác nhau.

Ứng dụng nhiều replica cũng vậy: `ApplicationEventPublisher` chỉ phát trong **một application context/process**, không tự chuyển event đến các pod khác. Muốn liên lạc liên tiến trình, cần message broker, HTTP/gRPC hoặc một hạ tầng phù hợp.

## 11. Một số điểm nâng cao khi dùng generic event

### Listener rộng và listener hẹp

~~~java
ApplicationListener<ApplicationEvent> broad = event -> {
    // Lắng nghe nhiều subtype.
};
~~~

Với listener rộng, code thường phải phân biệt từng event qua `instanceof`. Nếu nhu cầu chỉ là xử lý `OrderPlacedEvent`, listener hẹp rõ nghĩa và ít bị kích hoạt ngoài ý muốn hơn.

### Listener generic và Spring's ResolvableType

Khi class trực tiếp khai báo `implements ApplicationListener<OrderPlacedEvent>`, thông tin generic thường đủ rõ để Spring xác định loại event cần gửi. Nhưng các tình huống sử dụng **raw type**, proxy tùy biến, nhiều lớp generic base class hoặc lambda thiếu metadata kiểu có thể phức tạp hơn.

Ví dụ nên tránh:

~~~java
@SuppressWarnings("rawtypes")
ApplicationListener listener = event -> {
    // Không còn type parameter cụ thể ở declaration.
};
~~~

Đoạn trên là **minh họa code xấu**. Raw type bỏ mất bảo đảm type-safe của Java, dễ dẫn đến cảnh báo và khó suy luận định tuyến. Trong code thực tế, khai báo `ApplicationListener<MyEvent>` hoặc class cụ thể có type rõ ràng.

### Context cha/con có thể phát trùng theo hướng lan truyền

Spring event publication trong một `ApplicationContext` có thể chuyển sự kiện từ **child context lên parent context**. Nếu có nhiều context hoặc nhiều lần SpringApplication run, một listener ở parent có thể thấy nhiều event cùng type phát từ các context khác nhau. Vì vậy:

- Không tự coi mọi event phải xuất hiện đúng một lần trong cả JVM.
- Với event có context (`ContextRefreshedEvent`, một số Spring Boot event), kiểm tra nguồn context khi cần.
- Nếu chỉ xử lý event trong đúng context hiện tại, có thể so sánh context của event với context được inject vào bean listener.
- Đừng dùng `@Order` để chữa vấn đề listener bị đăng ký hai lần hoặc event bubbling.

### Cleanup không đồng nghĩa với request lifecycle

Một listener bean được hủy cùng application context theo quy tắc bean lifecycle, **không** được tạo và hủy cho từng event. Nếu listener giữ state mutable, hãy bảo đảm concurrency, tránh lưu thông tin request ở field của singleton và dọn resource đúng nơi.

## 12. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Chỉ @Component cho early listener.** Sự kiện sớm phát trước bean scanning; chuyển sang `SpringApplication.addListeners(...)` trước `run` hoặc `spring.factories`.

**Lỗi 2 — Viết ApplicationListener<ApplicationEvent> rồi đoán mọi event sẽ có context.** Một số Boot event rất sớm chưa có context. Chọn type cụ thể hoặc kiểm tra sự kiện/nguồn phù hợp.

**Lỗi 3 — Nhầm EventListener với ApplicationListener.** `@EventListener` là annotation trên method của bean; `ApplicationListener<E>` là interface có callback `onApplicationEvent`. Có thể chọn một trong hai, nhưng không giả định annotation giúp tạo bean trước context.

**Lỗi 4 — Không bao giờ gọi publishEvent.** Định nghĩa `OrderPlacedEvent` và listener không tự phát event; cần một publisher gọi `ApplicationEventPublisher.publishEvent(...)` trong luồng nghiệp vụ.

**Lỗi 5 — Dùng generic type không kế thừa ApplicationEvent.** `ApplicationListener<OrderPlaced>` không compile nếu `OrderPlaced` là record thường. Dùng event class mở rộng `ApplicationEvent` hoặc `PayloadApplicationEvent<T>`/`@EventListener` cho payload object.

**Lỗi 6 — Tin rằng event luôn async.** Mặc định listener thường đồng bộ, có thể làm chậm hoặc làm lỗi publisher. Nếu cần bất đồng bộ, thiết kế executor, backpressure, error handling và thứ tự công việc.

**Lỗi 7 — Cho rằng @Order bảo đảm transaction commit.** Order của listener không thay thế transaction boundary. Kiểm tra `@TransactionalEventListener` hoặc outbox nếu cần after-commit/durable delivery.

**Lỗi 8 — Gửi event rồi nghĩ tất cả replica đều nhận.** Spring application event là nội bộ process/context, không phải distributed message bus.

**Lỗi 9 — Chạy tác vụ vô hạn trong ApplicationReadyEvent listener.** Callback chạy vào mốc startup/ready; công việc chặn lâu có thể ảnh hưởng readiness. Dùng background service/executor có lifecycle phù hợp.

**Lỗi 10 — Truy cập bean khi ApplicationStartingEvent/EnvironmentPreparedEvent.** Lúc này context chưa được tạo; không autowire service ứng dụng vào early listener rồi kỳ vọng sẵn sàng.

**Lỗi 11 — Đăng ký cùng một listener bằng cả addListeners và spring.factories.** Có thể có nhiều instance/side effect lặp; chọn một cách hoặc tự thiết kế idempotency.

**Lỗi 12 — Nuốt exception để “event không ảnh hưởng publisher”.** Nếu side effect quan trọng, việc không xử lý lỗi rõ ràng có thể làm sai nghiệp vụ. Phân biệt tác vụ bắt buộc và tác vụ best-effort, gắn retry/monitoring tương ứng.

## 13. Bài thực hành

1. Chạy ví dụ mục 4. Vì sao `EARLY` xuất hiện trước `RUNNER`, còn `READY_LISTENER` xuất hiện sau runner?
2. Đổi `OrderPlacedListener` thành `ApplicationListener<ApplicationReadyEvent>` nhưng giữ logic muốn đọc `getOrderId()`. Trình biên dịch sẽ báo vấn đề gì? Generic type bảo vệ code như thế nào?
3. Bỏ `application.addListeners(new EnvironmentPreparedListener())`. Liệu log `EARLY` còn xuất hiện không? Vì sao các listener bean vẫn hoạt động?
4. Đăng ký `EnvironmentPreparedListener` qua `spring.factories`, đồng thời bỏ `addListeners`. Xác nhận nó vẫn nhận event sớm.
5. Tạo thêm `AuditOrderListener implements ApplicationListener<OrderPlacedEvent>`. Khi một event được publish, có bao nhiêu listener nghiệp vụ nhận? Khi thay kiểu sang `ApplicationReadyEvent`, điều gì thay đổi?
6. Trong callback `OrderPlacedListener`, thử in tên thread bằng `Thread.currentThread().getName()` và so với runner. Với mặc định đồng bộ, bạn mong đợi điều gì? Có nên hard-code tên thread trong test không?
7. Tạm thời ném exception trong `OrderPlacedListener`. Quan sát `RUNNER: after publish` và `READY_LISTENER`. Điều này cho biết event listener có thể ảnh hưởng startup như thế nào?
8. Thay `OrderPlacedEvent` bằng record thuần và thử `ApplicationListener<OrderPlaced>`. Vì sao generic constraint không cho compile? Hãy nghiên cứu `PayloadApplicationEvent<OrderPlaced>`.
9. Một listener cần gửi email **chỉ sau khi** DB commit thành công. Vì sao `ApplicationListener<OrderPlacedEvent>` chạy ngay không luôn phù hợp? Hãy giải thích vai trò của after-commit và outbox.
10. Một hệ thống có hai application context cha/con. Vì sao parent listener có thể thấy event phát ở child, và bạn sẽ xác định nguồn như thế nào?
11. Thêm một `@EventListener` method trên bean khác để nghe `OrderPlacedEvent`. So sánh cách viết và thời điểm đăng ký với interface listener.
12. Khi ứng dụng nhận hàng nghìn sự kiện/s, bạn cần đo những gì trước khi cấu hình multicaster bất đồng bộ (thời gian callback, queue, retry, memory, ordering, tracing)?
13. Vì sao `ApplicationReadyEvent` không tương đương một sự kiện HTTP request thành công? Hãy chọn listener thích hợp cho hai nhu cầu khác nhau.

## Ghi nhớ

- `ApplicationListener<E extends ApplicationEvent>` cho phép **nhận đúng loại sự kiện** qua `onApplicationEvent(E event)`.
- **Đúng type chưa đủ**: listener phải được đăng ký **trước khi** event xảy ra, và ở nơi sự kiện được phát.
- Với event sau refresh/runner, bean `@Component`/`@Bean` hoặc method `@EventListener` thường phù hợp.
- Với event khởi động rất sớm, dùng `SpringApplication.addListeners(...)` trước `run` hoặc `META-INF/spring.factories`.
- Sự kiện nghiệp vụ do `ApplicationEventPublisher.publishEvent(...)` phát; Spring định tuyến theo event type.
- Mặc định listener thường **đồng bộ**, exception có thể ảnh hưởng publisher; event nội bộ Spring không phải message queue bền vững.
- Khi cần transaction-after-commit, async delivery, nhiều replica hoặc retry, phải chọn cơ chế thiết kế riêng chứ không chỉ thay generic type.

### Tài liệu tham khảo

- Spring Framework 6.1 — `ApplicationListener<E>` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationListener.html
- Spring Framework 6.1 — `ApplicationEventPublisher` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework — Standard and Custom Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events
- Spring Framework — Annotation-based Event Listeners: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Boot 3.3 — SpringApplication Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — `ApplicationEnvironmentPreparedEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
- Spring Boot 3.3 — `ApplicationReadyEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
