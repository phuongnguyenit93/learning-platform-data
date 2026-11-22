# BootstrapContextClosedEvent và chuyển giao sang ApplicationContext trong Spring Boot

## 1. Bài toán: có đối tượng cần tạo trước khi ApplicationContext sẵn sàng

Trong ứng dụng Spring Boot, không phải mọi công việc khởi tạo đều có thể chờ đến khi bean thông thường được tạo. Một số cơ chế phải hoạt động **rất sớm**, khi Boot đang chuẩn bị `Environment` hoặc nạp cấu hình ứng dụng: lấy cấu hình từ nguồn bên ngoài, chuẩn bị client để giải mã cấu hình, lưu một đối tượng đã tạo trong quá trình bootstrap, hoặc chia sẻ kết quả chuẩn bị giữa nhiều bước khởi động.

Tại thời điểm đó, `ApplicationContext` chính chưa tồn tại hoặc chưa được `refresh()`. Vì vậy ta chưa thể mặc nhiên dùng `@Autowired`, `@Bean` hoặc `applicationContext.getBean(...)`.

Spring Boot cung cấp một vùng lưu tạm chuyên cho giai đoạn sớm:

- `BootstrapRegistry`: nơi **đăng ký** cách tạo các đối tượng theo khóa `Class`.
- `BootstrapContext`: nơi **lấy** đối tượng đã đăng ký khi cần, thường theo cơ chế tạo muộn và lưu singleton.
- `ConfigurableBootstrapContext`: kết hợp giao diện đăng ký và truy cập.
- `BootstrapRegistryInitializer`: điểm mở rộng để đăng ký nội dung vào bootstrap registry trước khi ứng dụng khởi động sâu hơn.
- `BootstrapContextClosedEvent`: sự kiện tại **điểm kết thúc phạm vi bootstrap**, mang theo bootstrap context và `ApplicationContext` đã được chuẩn bị.

**Ý nghĩa cốt lõi:** khi Boot đã tạo và chuẩn bị `ApplicationContext` nhưng **chưa refresh**, nó đóng vòng đời bootstrap registry và thông báo cho những listener đã đăng ký. Listener có thể chuyển đối tượng cần giữ lại từ bootstrap sang `ApplicationContext`, để các bean thông thường sau này sử dụng cùng đối tượng đó. Sự kiện này **không phải** tín hiệu shutdown JVM, không có nghĩa ứng dụng đã chạy xong, và cũng không đồng nghĩa `ContextClosedEvent`.

Hãy hình dung một cuộc chuyển giao ca trực:

1. Nhóm **bootstrap** chuẩn bị công cụ trước khi nhà máy hoạt động.
2. Khi **nhà máy Spring** đã dựng bộ khung, nhóm bootstrap bàn giao công cụ đã chuẩn bị.
3. Nhà máy tiếp tục lắp ráp và khởi chạy các bộ phận (bean) của mình.
4. Nhóm bootstrap kết thúc vai trò. Công cụ được bàn giao có thể tiếp tục sống theo vòng đời của ứng dụng nếu được quản lý đúng.

Bài này tập trung vào **Spring Boot 3.3.x / Java 17+**, ở cấp **điểm mở rộng startup**. Không nhầm cơ chế này với một “bootstrap ApplicationContext” riêng trong một số cấu hình **Spring Cloud**.

## 2. Phân biệt các đối tượng mang chữ “context”

| Thành phần | Bản chất | Có ở giai đoạn nào? | Chứa gì? |
| --- | --- | --- | --- |
| `BootstrapRegistry` | Registry có thể cấu hình | Rất sớm, trước application context | Supplier đăng ký theo một khóa `Class<T>` |
| `BootstrapContext` | Giao diện lấy đối tượng | Trong quá trình bootstrap | Các đối tượng được tạo khi cần từ supplier |
| `ConfigurableBootstrapContext` | Kết hợp registry + context | Được Boot cung cấp cho bootstrap machinery | Khả năng `register`, `get`, `addCloseListener` |
| `DefaultBootstrapContext` | Triển khai mặc định của Boot | Từ khi `SpringApplication` bắt đầu tới mốc đóng bootstrap | Map supplier/instance và các close listener |
| `ConfigurableApplicationContext` | Spring bean container chuẩn bị được refresh | Sau khi Boot chọn và tạo context | `Environment`, `BeanFactory`, definitions, listeners, và sau refresh là bean đã khởi tạo |
| `ApplicationContext` | Giao diện sử dụng container | Trong vòng đời ứng dụng | Truy vấn bean, environment, events, resource... |

**Từ “closed” trong `BootstrapContextClosedEvent` chỉ nói về việc đóng giai đoạn bootstrap.** Nó không đóng `ApplicationContext`. Ngay khi listener nhận sự kiện, application context đã có để chuẩn bị việc bàn giao, nhưng bean ứng dụng thường **chưa** được tạo.

### 2.1. Đừng coi BootstrapContext là BeanFactory

`BootstrapContext.get(Client.class)` tìm theo kiểu đã đăng ký vào bootstrap registry. Cơ chế này **không** duyệt `@ComponentScan`, không thực hiện trọn bộ dependency injection của bean container và không tự biến đối tượng thành một Spring bean.

Ngược lại, `ApplicationContext.getBean(Client.class)` chỉ hoạt động đối với bean đã đăng ký/quản lý trong BeanFactory sau khi nó đi đến giai đoạn có thể sử dụng. Chuyển từ registry sang bean container là **một thao tác có chủ đích** trong điểm bàn giao.

### 2.2. BootstrapRegistryInitializer khác ApplicationContextInitializer

`BootstrapRegistryInitializer.initialize(BootstrapRegistry registry)` làm việc với **registry khởi động sớm**.

`ApplicationContextInitializer.initialize(ConfigurableApplicationContext context)` làm việc với **application context đã được tạo, trước refresh**.

Hai initializer cùng nằm trước `refresh()` nhưng có **đối tượng đầu vào và mục tiêu khác nhau**. Nếu muốn đăng ký client cho một bước chuẩn bị config, dùng bootstrap registry. Nếu chỉ muốn thêm listener/PropertySource khi context đã tồn tại, `ApplicationContextInitializer` có thể là lựa chọn phù hợp.

## 3. Mốc chính xác của BootstrapContextClosedEvent

Trật tự khái niệm trong chuỗi `SpringApplication.run(...)` ở Spring Boot 3.3:

```text
SpringApplication.run(args)
    |
    +-- Tạo ConfigurableBootstrapContext (thường là DefaultBootstrapContext)
    +-- Chạy các BootstrapRegistryInitializer
    +-- Bắt đầu chuỗi SpringApplicationRunListener
    +-- Chuẩn bị Environment / ConfigData
    |       |
    |       +-- Các thành phần khởi động sớm có thể dùng BootstrapContext
    |
    +-- Tạo loại ConfigurableApplicationContext thích hợp
    +-- Gắn Environment, chuẩn bị context
    +-- Chạy ApplicationContextInitializer
    +-- Thông báo contextPrepared
    |       |
    |       +-- ApplicationContextInitializedEvent
    |
    +-- bootstrapContext.close(applicationContext)
    |       |
    |       +-- BootstrapContextClosedEvent
    |       +-- Các close listener nhận cả BootstrapContext và ApplicationContext
    |
    +-- Nạp primary sources và bean definitions
    +-- Thông báo contextLoaded
    |       |
    |       +-- ApplicationPreparedEvent
    |
    +-- applicationContext.refresh()
    |       |
    |       +-- BeanFactoryPostProcessor, BeanPostProcessor
    |       +-- Khởi tạo các singleton không lazy
    |       +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
```

Đây là mô tả **luồng khởi động chuẩn của Boot 3.3**, không phải hợp đồng cho thứ tự mọi callback và mọi hệ thống tích hợp tùy biến. Các application event và hoạt động của `ConfigData` có chi tiết riêng; không dựa vào biểu đồ để triển khai extension point vượt contract của API.

### 3.1. Ba ranh giới thường bị nhầm

**Ranh giới A — sau initializer của application context:** `ApplicationContextInitializedEvent` xảy ra khi `ApplicationContextInitializer` đã chạy, trước khi nạp bean definitions chính. `BootstrapContextClosedEvent` nằm trong khu vực chuẩn bị này.

**Ranh giới B — trước refresh:** `ApplicationPreparedEvent` xảy ra sau khi sources/bean definitions đã nạp nhưng trước `refresh()`. Việc đóng bootstrap đã xảy ra **trước** mốc này trong đường chạy chuẩn.

**Ranh giới C — trước ready rất lâu:** `ApplicationReadyEvent` chỉ có sau refresh và runner. Close listener của bootstrap không được kỳ vọng có thể gọi repository, controller hoặc service do Spring inject; những bean đó chưa hoàn tất khởi tạo.

### 3.2. Tại sao gọi là closed nhưng application context vẫn còn?

Bootstrap registry có **phạm vi thời gian ngắn**. Khi Spring application context đã được chuẩn bị, Boot có thể chấm dứt việc cung cấp bootstrap registry như một điểm cấu hình của startup. Nó phát sự kiện để các thành phần muốn chuyển tài nguyên còn cần thiết sang vùng quản lý mới có cơ hội làm điều đó.

Lúc này, chính `ApplicationContext` mới đang ở **đầu vòng đời**. Đóng bootstrap **không** gọi `ApplicationContext.close()` và **không** thực hiện graceful shutdown.

## 4. BootstrapContextClosedEvent mang theo những gì?

Class `org.springframework.boot.BootstrapContextClosedEvent` kế thừa `ApplicationEvent` và cung cấp hai API quan trọng:

```java
BootstrapContext getBootstrapContext();
ConfigurableApplicationContext getApplicationContext();
```

Đây là **chữ ký minh họa** hai method của sự kiện, không phải file Java độc lập.

- `getBootstrapContext()`: trả về bootstrap context đang hoàn tất vòng đời, dùng để lấy một đối tượng đã đăng ký, ví dụ `event.getBootstrapContext().get(MyClient.class)`.
- `getApplicationContext()`: trả về `ConfigurableApplicationContext` **đã được chuẩn bị**. Có thể truy cập BeanFactory hoặc Environment để đăng ký đối tượng/metadata cho phần startup tiếp theo.

Mục đích chính là **bắc cầu** giữa hai phạm vi khởi động. Nó không cung cấp request HTTP, trạng thái readiness, kết quả từ runner hay bảo đảm mọi singleton đã có mặt.

### 4.1. Listener phải được đăng ký bằng addCloseListener

`BootstrapRegistry` có phương thức:

```java
void addCloseListener(
    ApplicationListener<BootstrapContextClosedEvent> listener
);
```

Thực tế thường viết:

```java
registry.addCloseListener(event -> {
    // Lấy dữ liệu từ bootstrap context.
    // Đăng ký vào application context khi thật sự cần.
});
```

Đoạn trên là minh họa đặt **bên trong** `BootstrapRegistryInitializer.initialize(...)`.

Đây là một listener được đăng ký **trong chính cơ chế bootstrap**. Không nên thay thế bằng `@EventListener(BootstrapContextClosedEvent.class)` trên một bean ứng dụng thông thường: bean được tạo khi refresh, nghĩa là **muộn hơn** mốc bootstrap close. Cũng đừng giả định tất cả `ApplicationListener` của application context sẽ nhận được sự kiện này theo cùng đường phát sự kiện.

### 4.2. Vì sao sự kiện thuộc Spring Boot, không phải ContextClosedEvent?

| Sự kiện | Nguồn | Khi nào? | Mục đích |
| --- | --- | --- | --- |
| `BootstrapContextClosedEvent` | `BootstrapContext` của Spring Boot | Khi application context đã chuẩn bị, trước refresh | Chuyển giao đối tượng/cấu hình từ bootstrap sang container |
| `ApplicationContextInitializedEvent` | `SpringApplication` | Sau application context initializers, trước nạp bean definitions | Quan sát/tác động mốc context được chuẩn bị |
| `ApplicationPreparedEvent` | `SpringApplication` | Trước refresh, sau nạp definitions | Quan sát mốc hoàn tất chuẩn bị source |
| `ContextRefreshedEvent` | `ApplicationContext` | Sau refresh | Context đã refresh |
| `ApplicationReadyEvent` | `SpringApplication` | Sau các runner | Boot công bố ứng dụng ready |
| `ContextClosedEvent` | `ApplicationContext` | Khi application context thật sự đóng | Dừng thành phần, hủy bean, cleanup ứng dụng |

Tên “Closed” giống nhau nhưng **phạm vi bị đóng khác nhau hoàn toàn**.

## 5. Đăng ký và lấy đối tượng từ bootstrap registry

### 5.1. Dùng Class làm khóa

`BootstrapRegistry` đăng ký supplier theo loại, ví dụ:

```java
registry.registerIfAbsent(StartupClient.class,
        bootstrapContext -> new StartupClient("early-config"));
```

Với ví dụ giả định class `StartupClient` có constructor nhận `String`, đây là một **đoạn trong `initialize(BootstrapRegistry registry)`**, không phải chương trình độc lập.

- `register`: đăng ký supplier cho type; nếu có supplier đã đăng ký nhưng instance của type đó **chưa được tạo và giữ như singleton**, có thể thay thế đăng ký.
- `registerIfAbsent`: không thay thế supplier đã tồn tại cho type.
- `isRegistered`: kiểm tra type đã được đăng ký hay chưa.
- `getRegisteredInstanceSupplier`: lấy supplier được đăng ký nếu có.

Vì key là `Class`, một `BootstrapRegistry` không phải tập các named beans: không thể đăng ký năm đối tượng khác nhau cùng class dưới năm tên như `@Qualifier` của Spring BeanFactory mà không có thiết kế wrapper/key type phù hợp.

### 5.2. Tạo muộn và giữ một instance

`BootstrapContext` cung cấp `get(Class<T>)`, `getOrElse(...)`, `getOrElseSupply(...)`, `getOrElseThrow(...)`. Thông thường instance được tạo **khi `get(...)` đầu tiên xảy ra**, dựa trên `InstanceSupplier<T>` đã đăng ký; scope mặc định thường là singleton cho bootstrap context. Vì vậy **đăng ký** một supplier không có nghĩa constructor của client đã chạy.

Ví dụ:

```java
registry.registerIfAbsent(StartupClient.class, bootstrap -> {
    System.out.println("Creating StartupClient");
    return new StartupClient("early-config");
});

// Ở một bước startup khác có BootstrapContext:
StartupClient client = bootstrapContext.get(StartupClient.class);
```

Hai đoạn ở hai vị trí khác nhau. Dòng log xuất hiện **khi thực sự truy cập instance**, không phải nhất thiết ngay khi registry được tạo. `get(...)` với type chưa đăng ký ném `IllegalStateException`; dùng `getOrElseSupply(...)` nếu cần fallback do chính bạn định nghĩa.

### 5.3. Lưu ý về chi phí khởi tạo

Đăng ký supplier nhẹ và tạo muộn có lợi khi client tốn chi phí. Tuy nhiên, nếu close listener cố lấy mọi type, việc tạo muộn sẽ xảy ra ở **thời điểm bootstrap close**. Điều đó làm tăng thời gian startup và có thể phát sinh lỗi trước refresh. Hãy chỉ chuyển giao những đối tượng thật sự còn cần dùng.

Một đối tượng bootstrap có thể đã được dùng trong `EnvironmentPostProcessor` hoặc một thành phần xử lý config. Nhận lại nó qua `get(MyType.class)` trong close listener cho phép **chuyển chính instance đó** khi là singleton; không cần tạo một client thứ hai cho ứng dụng.

## 6. Chuyển giao vào ApplicationContext bằng cách nào?

Có hai nhu cầu phổ biến cần phân biệt.

### 6.1. Chuyển một giá trị cấu hình

Nếu thứ cần giữ lại chỉ là một giá trị/metadata chuẩn bị sớm, listener có thể thêm `PropertySource` vào `Environment` của application context:

```java
registry.addCloseListener(event -> {
    String resolvedMode = "safe"; // Ví dụ: kết quả chuẩn bị từ bootstrap.
    event.getApplicationContext().getEnvironment()
            .getPropertySources()
            .addLast(new MapPropertySource(
                    "bootstrapDefaults",
                    Map.of("demo.mode", resolvedMode)));
});
```

Đoạn Java minh họa; cần import `java.util.Map` và `org.springframework.core.env.MapPropertySource`. `addLast(...)` đặt nguồn này ở mức ưu tiên thấp, giúp cấu hình đã có cơ hội ghi đè. Với dữ liệu chính sách khác, xác định thứ tự nguồn theo contract của ứng dụng.

Không dùng cơ chế này để thay đổi **quyết định đã được đưa ra trước khi có context**, chẳng hạn cố đổi `WebApplicationType` sau khi Boot tạo context. Cũng không để lộ khóa bí mật trong log/exception.

### 6.2. Chuyển một instance thành bean để inject

`ConfigurableApplicationContext.getBeanFactory()` cung cấp BeanFactory đã sẵn sàng cho các thao tác đăng ký trước refresh. Một cách ngắn gọn:

```java
registry.addCloseListener(event -> {
    StartupClient client =
            event.getBootstrapContext().get(StartupClient.class);
    event.getApplicationContext().getBeanFactory()
            .registerSingleton("startupClient", client);
});
```

Đây là **đoạn mã đặt bên trong registry initializer**, giả định `StartupClient` đã được đăng ký trong `BootstrapRegistry`.

Sau này, khi `@Bean`/`@Component` của ứng dụng được tạo, BeanFactory đã biết singleton tên `startupClient` và có thể dùng nó làm dependency nếu type/naming không xung đột.

**Điểm kỹ thuật cần biết:** `registerSingleton(...)` đưa vào một **instance có sẵn**. Nó không tương đương với Spring tự tạo bean qua toàn bộ chuỗi bean definition, injection, BeanPostProcessor, init/destroy callbacks. Đặc biệt, không mặc định kỳ vọng `@PostConstruct`, `@PreDestroy` hoặc một destroy method được quản lý đầy đủ chỉ nhờ gọi `registerSingleton`. Nếu tài nguyên cần Spring sở hữu trọn lifecycle, dùng đăng ký bean definition với supplier phù hợp hoặc adapter bean quản lý đóng tài nguyên.

### 6.3. Lựa chọn BeanDefinition khi cần lifecycle của Spring

Trong ứng dụng Boot dùng `DefaultListableBeanFactory`, có thể đăng ký bean definition với supplier trả về cùng instance bootstrap:

```java
registry.addCloseListener(event -> {
    StartupClient client =
            event.getBootstrapContext().get(StartupClient.class);

    ConfigurableListableBeanFactory beanFactory =
            event.getApplicationContext().getBeanFactory();

    if (!(beanFactory instanceof BeanDefinitionRegistry definitions)) {
        throw new IllegalStateException(
                "BeanFactory does not support BeanDefinitionRegistry");
    }

    RootBeanDefinition beanDefinition =
            new RootBeanDefinition(StartupClient.class);
    beanDefinition.setInstanceSupplier(() -> client);
    definitions.registerBeanDefinition("startupClient", beanDefinition);
});
```

Đây là **snippet cấp nâng cao**, cần import `ConfigurableListableBeanFactory`, `BeanDefinitionRegistry`, `RootBeanDefinition`; `StartupClient` là type bạn tự định nghĩa. Bean definition với instance supplier cho Spring quản lý bean khi nó được tạo qua BeanFactory, hỗ trợ quá trình hậu xử lý và callback theo contract tương ứng. Kiểm tra kỹ chính sách singleton, bean name, phụ thuộc vòng và ownership tài nguyên.

Hai snippet `registerSingleton` và `registerBeanDefinition` là **hai phương án thay thế**, không dùng đồng thời cùng bean name. Với đối tượng immutable đơn giản như ví dụ chính ở phần sau, `registerSingleton` đủ dễ hiểu.

## 7. Ví dụ Java 17+ hoàn chỉnh: chuyển cùng instance từ bootstrap sang BeanFactory

Ví dụ có **một file Java đầy đủ**, không cần HTTP server hay database. Chúng ta sẽ tạo một đối tượng `BootstrapValue` thông qua registry sớm, chuyển instance đó sang application BeanFactory ở close event và inject nó vào `ApplicationRunner` để chứng minh chuỗi hoạt động.

**Điều kiện:** Spring Boot 3.3.x, Java 17+, project Gradle đã có Spring Boot plugin và `spring-boot-starter`.

**File:** `src/main/java/com/example/bootstrap/BootstrapTransferApplication.java`

```java
package com.example.bootstrap;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootstrapTransferApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(BootstrapTransferApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        app.addBootstrapRegistryInitializer(registry -> {
            registry.registerIfAbsent(BootstrapValue.class, bootstrap -> {
                System.out.println("02 SUPPLIER: tao gia tri bootstrap");
                return new BootstrapValue("from-early-bootstrap");
            });
            System.out.println("01 REGISTRY: supplier da dang ky");

            registry.addCloseListener(event -> {
                BootstrapValue value = event.getBootstrapContext()
                        .get(BootstrapValue.class);

                event.getApplicationContext().getBeanFactory()
                        .registerSingleton("bootstrapValue", value);

                System.out.println("03 HANDOFF: applicationContext active="
                        + event.getApplicationContext().isActive());
            });
        });

        try (ConfigurableApplicationContext context = app.run(args)) {
            BootstrapValue transferred =
                    context.getBean(BootstrapValue.class);
            System.out.println("05 AFTER_RUN: same bean="
                    + (transferred == context.getBean("bootstrapValue")));
        }
    }

    @Bean
    ApplicationRunner showTransferredValue(BootstrapValue value) {
        return args -> System.out.println(
                "04 RUNNER: value=" + value.value());
    }

    public record BootstrapValue(String value) {
    }
}
```

**Ý nghĩa từng điểm:**

1. `addBootstrapRegistryInitializer(...)` đăng ký callback khởi động sớm. Trong callback, `registerIfAbsent` chỉ đăng ký supplier chứ chưa khởi tạo `BootstrapValue`.
2. `addCloseListener(...)` gắn listener chuyên biệt vào bootstrap registry.
3. Khi Boot đóng bootstrap context, listener gọi `event.getBootstrapContext().get(BootstrapValue.class)`; supplier tạo instance nếu chưa được lấy ở nơi khác.
4. Listener đăng ký **cùng instance** vào BeanFactory của application context bằng tên `bootstrapValue`, ở thời điểm BeanFactory chưa xử lý toàn bộ bean ứng dụng.
5. Sau `refresh()`, Spring tạo bean `ApplicationRunner`; dependency `BootstrapValue` được giải quyết từ singleton vừa chuyển giao.
6. `SpringApplication.run(...)` trả về `ConfigurableApplicationContext` sau giai đoạn startup; phần `try` đối chiếu identity, rồi `close()` theo contract `AutoCloseable`.

### 7.1. Dependency Gradle

Trong một project Spring Boot 3.3.x đã được cấu hình plugin/build phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Không yêu cầu Spring Web hoặc Spring WebFlux vì ví dụ cố tình dùng `NONE`.

### 7.2. Lệnh chạy

Từ thư mục dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD dùng `gradlew.bat bootRun`; PowerShell dùng `.\gradlew.bat bootRun`. Nếu tên main class trong dự án không được Boot phát hiện đúng, cấu hình `springBoot { mainClass = 'com.example.bootstrap.BootstrapTransferApplication' }` trong Gradle build. Một project chứa nhiều main class có thể cần chỉ định main class rõ ràng.

### 7.3. Các dòng xuất ra do ví dụ tự in

Bỏ qua banner và log framework. Với lần startup thành công và không có custom initializer thay đổi logic, các dòng ví dụ được in theo thứ tự:

```text
01 REGISTRY: supplier da dang ky
02 SUPPLIER: tao gia tri bootstrap
03 HANDOFF: applicationContext active=false
04 RUNNER: value=from-early-bootstrap
05 AFTER_RUN: same bean=true
```

**Tại sao `active=false` ở dòng handoff?** `BootstrapContextClosedEvent` xảy ra trước `refresh()`; cờ active của `AbstractApplicationContext` thông thường chỉ được bật trong quá trình refresh. Đó là hành vi dự kiến, không phải lỗi khởi động.

**Tại sao `same bean=true`?** Chúng ta đăng ký **đúng instance** vào BeanFactory, không tạo một bản sao. `ApplicationRunner` và `getBean(...)` đều có thể tham chiếu instance đó. Ví dụ record không giữ connection hoặc thread nên không có công việc dọn dẹp đặc biệt. Đừng suy rộng hợp đồng này sang tài nguyên I/O có yêu cầu lifecycle phức tạp nếu bạn dùng raw `registerSingleton`.

**Điểm cần thận trọng khi tự sửa ví dụ:** không thêm `@Component` hoặc `@Bean` khác cùng type/name `BootstrapValue` mà không xử lý rõ conflict. Đoạn này đã cố tình để record chỉ là type dữ liệu; phần đăng ký bean duy nhất ở close listener.

## 8. Đăng ký BootstrapRegistryInitializer bằng những cách nào?

### 8.1. Trực tiếp trên SpringApplication

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addBootstrapRegistryInitializer(new MyBootstrapInitializer());
app.run(args);
```

Đoạn này nằm trong method `main`, giả định `MyBootstrapInitializer` implements `BootstrapRegistryInitializer`. Cách này rõ ràng khi bạn kiểm soát main class và muốn khai báo extension point trực tiếp.

### 8.2. Cài đặt interface riêng trong thư viện

```java
package com.example.bootstrap;

import org.springframework.boot.BootstrapRegistry;
import org.springframework.boot.BootstrapRegistryInitializer;

public final class MyBootstrapInitializer
        implements BootstrapRegistryInitializer {

    @Override
    public void initialize(BootstrapRegistry registry) {
        registry.registerIfAbsent(BootstrapValue.class,
                bootstrap -> new BootstrapValue("library-default"));

        registry.addCloseListener(event -> {
            BootstrapValue value = event.getBootstrapContext()
                    .get(BootstrapValue.class);
            event.getApplicationContext().getBeanFactory()
                    .registerSingleton("bootstrapValue", value);
        });
    }
}
```

Đây là **class triển khai hoàn chỉnh** nhưng cần có type `BootstrapValue` được định nghĩa cùng package hoặc import. Nếu sử dụng chung với ví dụ ở phần 7, tránh đăng ký hai lần một bean cùng tên. Class này nên dùng như một biến thể **thay thế** cho lambda đã đặt trong main.

### 8.3. Tự phát hiện qua META-INF/spring.factories

Khi cần phát hành starter/library mà nhiều ứng dụng dùng chung, Spring Boot có thể tìm `BootstrapRegistryInitializer` qua `SpringFactoriesLoader`. Thêm tệp:

**`src/main/resources/META-INF/spring.factories`**

```properties
org.springframework.boot.BootstrapRegistryInitializer=\
com.example.bootstrap.MyBootstrapInitializer
```

Để cơ chế này hoạt động, class phải nằm trên runtime classpath của ứng dụng và có thể được Spring Boot tạo bằng cơ chế factory loading. Không nhầm dòng này với key cũ đăng ký **auto-configuration classes**: Spring Boot 3.x có cơ chế `AutoConfiguration.imports` riêng cho auto-configuration, còn `spring.factories` vẫn có vai trò đối với một số factory như bootstrap initializer.

Nếu đã dùng cơ chế tự phát hiện, không đăng ký trùng cùng initializer trong main trừ khi có lý do rõ ràng và đảm bảo idempotence. Đăng ký hai listener chuyển cùng bean name có thể gây conflict.

## 9. Bootstrap client và EnvironmentPostProcessor: trường hợp thực tế

Một tình huống mang tính hạ tầng: ứng dụng tải cấu hình từ một nguồn bên ngoài trước khi Spring tạo bean. Phần tải cấu hình nằm trong một `EnvironmentPostProcessor` hoặc cơ chế ConfigData tương ứng; nó không thể tự `@Autowired` client từ BeanFactory vì container chưa sẵn sàng.

Luồng thiết kế phù hợp:

```text
BootstrapRegistryInitializer
    |
    +-- registerIfAbsent(ConfigClient.class, supplier)
    +-- addCloseListener(listener)
    |
EnvironmentPostProcessor / ConfigData component
    |
    +-- nhận BootstrapContext từ cơ chế Boot hỗ trợ
    +-- ConfigClient client = bootstrapContext.get(ConfigClient.class)
    +-- dùng client tải/cấu hình PropertySource
    |
BootstrapContextClosedEvent
    |
    +-- Lấy lại ConfigClient cùng type/instance
    +-- Đăng ký thành Spring bean nếu còn dùng khi runtime
    |
ApplicationContext.refresh()
    |
    +-- Bean runtime có thể inject ConfigClient
```

**Chi tiết quan trọng:** `EnvironmentPostProcessor` thông thường có phương thức `postProcessEnvironment(ConfigurableEnvironment, SpringApplication)`; nếu cần nhận bootstrap context, phải dùng **đường tích hợp mà phiên bản Boot hỗ trợ**, chẳng hạn constructor injection theo cơ chế loader dành cho component tương ứng hoặc API context của resolver/loader. Đừng tạo biến `bootstrapContext` không có nguồn, hay giả định mọi class implement `EnvironmentPostProcessor` tự được inject như bean thông thường.

### 9.1. Chỉ tái sử dụng client khi cần

Nếu client chỉ dùng một lần để tải cấu hình, không nhất thiết chuyển nó sang application context; có thể giữ quá trình khởi động gọn và cho resource được đóng theo chính sách thư viện. Nếu runtime còn cần client để thực hiện thao tác quản trị/cập nhật cấu hình, close listener là điểm bàn giao có chủ đích.

### 9.2. Thứ tự xử lý property

Để một property mới ảnh hưởng đến parsing/config loading, nó thường phải có mặt **trong giai đoạn chuẩn bị Environment**, trước khi Boot xử lý xong ConfigData. Việc thêm `PropertySource` **lúc bootstrap close** vẫn hữu ích cho các bean chưa khởi tạo, nhưng có thể quá muộn để thay đổi quyết định ConfigData đã thực hiện.

Vì vậy, đừng dùng close listener để sửa các tùy chọn mà Boot đã áp dụng từ trước, ví dụ chọn `WebApplicationType` hoặc một số chính sách load config ban đầu. Hãy đặt config tại extension point đủ sớm.

## 10. Chuyển giao ownership và quản lý tài nguyên

Một đối tượng được tạo trong bootstrap có thể là value object bất biến (rất đơn giản), nhưng cũng có thể giữ socket, connection pool, thread, file handle hoặc bộ giải mã.

Nếu bạn chuyển một resource như vậy sang application context, cần trả lời rõ:

1. **Ai sở hữu instance sau handoff?** Bootstrap registry và BeanFactory đang giữ tham chiếu tới cùng object hay tạo object khác?
2. **Ai chịu trách nhiệm gọi `close()` / `dispose()`?** Nếu Boot chỉ thấy nó qua raw `registerSingleton`, đừng tự giả định destroy callback được kết nối.
3. **Ai xử lý khi startup fail trước hoặc sau handoff?** Có resource chưa được chuyển giao nhưng đã tạo?
4. **Ai bảo đảm chỉ giải phóng một lần?** Hai bên cùng close một client có thể gây lỗi nếu client không idempotent.
5. **Trong nhiều ApplicationContext hoặc nhiều lần chạy SpringApplication**, instance được tạo dùng chung hay độc lập? Đừng vô tình dùng singleton static cho toàn JVM khi chỉ muốn singleton mỗi lần startup.
6. **Tài nguyên có thread-safety và phạm vi sử dụng phù hợp không?** Một client tạo rất sớm có thể có cấu hình khác khi runtime hoàn chỉnh.

### 10.1. Tránh nhầm raw singleton với Spring-managed lifecycle

`beanFactory.registerSingleton("name", instance)` đăng ký instance tồn tại sẵn. Nó bỏ qua các bước Spring **tạo** bean theo definition. Với đối tượng `AutoCloseable` thực sự, hãy cân nhắc `BeanDefinition` với supplier và destroy method được cấu hình đúng, hoặc tạo một bean adapter được quản lý:

```java
@Bean(destroyMethod = "close")
RuntimeClientOwner clientOwner(ConfigClientClient client) {
    return new RuntimeClientOwner(client);
}
```

Đoạn này chỉ là **hình thức minh họa**, giả định `RuntimeClientOwner` có method `close()` và tham số type `ConfigClientClient` đã là bean. Không phải code tự biên dịch nếu chưa định nghĩa hai class. Mục tiêu là phân biệt instance bootstrap với cơ chế Spring quản lý cleanup.

Một resource không idempotent cần hợp đồng cụ thể để tránh hai nơi cùng close. Việc đóng bootstrap context **không tự bảo đảm** những tài nguyên được đăng ký trong đó đã được chuyển sang BeanFactory hoặc đã được destroy an toàn.

### 10.2. Không giữ registry như một service runtime

Trong thiết kế thông thường, bootstrap registry chỉ tồn tại để phục vụ giai đoạn trước application context. Đừng inject chính registry vào mọi service và tiếp tục gọi `registry.register(...)` tùy tiện trong request runtime. Nếu cần dynamic registry cho nghiệp vụ, hãy viết bean/service runtime có lifecycle và concurrency control riêng.

## 11. Xử lý lỗi trong giai đoạn handoff

### 11.1. Type chưa đăng ký

`event.getBootstrapContext().get(MyClient.class)` ném lỗi nếu type chưa được đăng ký. Trước khi lấy, có thể dùng:

```java
if (event.getBootstrapContext().isRegistered(MyClient.class)) {
    MyClient client =
            event.getBootstrapContext().get(MyClient.class);
    // Đăng ký vào application context khi thật sự cần.
}
```

Đoạn nằm trong close listener, type `MyClient` do ứng dụng định nghĩa. Nếu đây là dependency bắt buộc, thường nên **fail fast** với lỗi cụ thể hơn là lặng lẽ bỏ qua.

### 11.2. Trùng bean name hoặc type

Nếu handoff dùng tên `startupClient` nhưng module khác cũng khai báo bean cùng tên, startup có thể xung đột hoặc tạo tình trạng khó dự đoán. `registerIfAbsent` chỉ kiểm tra **bootstrap registry**, không bảo đảm trong Spring BeanFactory chưa có bean cùng tên/type từ các nguồn cấu hình khác được nạp sau đó.

Cách giảm rủi ro: dùng bean name riêng đủ rõ, kiểm soát thứ tự load, tránh cấu hình trùng class, và có integration test chạy cùng các starter/auto-configuration thực tế.

### 11.3. Listener ném exception

Close listener chạy trên đường startup chuẩn, **trước refresh**. Lỗi trong supplier hoặc listener có thể làm `SpringApplication.run` thất bại và ứng dụng không đạt ready. Vì vậy nên:

- Báo lỗi mô tả type, phase và nguyên nhân gốc, không in secret.
- Đặt timeout cho I/O nếu supplier mở kết nối bên ngoài.
- Không nuốt lỗi bắt buộc rồi để bean runtime chạy thiếu tài nguyên.
- Dọn dẹp tài nguyên đã mở nếu cần và phù hợp với ownership.
- Tránh retry vô hạn trong listener; một startup bị chặn có thể khiến health probe mãi không sẵn sàng.

### 11.4. Có nên tự gọi bootstrapContext.close(...)?

Thông thường **không**. `SpringApplication` điều phối thời điểm đóng để application context đúng pha, truyền context đã chuẩn bị cho listeners. Gọi close thủ công có thể phát sự kiện quá sớm, nhiều lần hoặc với context sai. `DefaultBootstrapContext.close(ConfigurableApplicationContext)` là API của implementation dành cho chuỗi bootstrap, không phải một “nút shutdown” dùng trong business service.

## 12. So sánh BootstrapContextClosedEvent với các extension point khác

| Cần làm gì? | Điểm mở rộng phù hợp | Tại sao? |
| --- | --- | --- |
| Đăng ký client dùng cho config-loading rất sớm | `BootstrapRegistryInitializer` | Registry có mặt trước application context. |
| Dùng sớm đối tượng đã đăng ký | API `BootstrapContext` qua tích hợp phù hợp | Lấy một instance với class key; tạo muộn nếu cần. |
| Giữ lại đối tượng sớm để inject ở runtime | `BootstrapRegistry.addCloseListener` + handoff | Có cả bootstrap instance và BeanFactory đã chuẩn bị. |
| Thêm property cho quá trình tải ConfigData | `EnvironmentPostProcessor`/ConfigData API | Có thể cần chạy trước khi application context được tạo. |
| Sửa context trước khi nạp bean definitions | `ApplicationContextInitializer` | Nhận `ConfigurableApplicationContext` trước refresh. |
| Tùy biến bean definitions | `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor` | Làm việc trong quá trình refresh. |
| Thực hiện I/O nghiệp vụ cần service/repository | `ApplicationRunner` hoặc lifecycle bean phù hợp | Bean đã được khởi tạo. |
| Phục vụ endpoint | Spring MVC/WebFlux handler | Chỉ sau khi web runtime đã được dựng. |
| Dọn dẹp bean khi ứng dụng dừng | Destroy callback, `SmartLifecycle`, `ContextClosedEvent` tùy nhu cầu | Đây là shutdown của application context, khác bootstrap close. |

Không nhất thiết ứng dụng nào cũng cần bootstrap registry. Với phần lớn service chỉ đọc property từ `application.yml` và inject bean bình thường, cấu hình + bean container đủ đáp ứng.

## 13. Tại sao không bắt sự kiện này bằng @EventListener?

Ví dụ sau **không nên dùng như cơ chế chính để nhận sự kiện bootstrap close**:

```java
@Component
class IncorrectListener {
    @EventListener
    void onBootstrapClose(BootstrapContextClosedEvent event) {
        // Bean này thường chỉ được tạo khi refresh,
        // sau khi bootstrap context đã đóng.
    }
}
```

Đây là ví dụ **minh họa sai thời điểm**, giả định import `@Component`, `@EventListener` và `BootstrapContextClosedEvent`. Lý do: Spring chưa dựng bean khi bootstrap close listener cần chạy, và BootstrapContextClosedEvent được phát bởi cơ chế bootstrap listener, không được bảo đảm đi qua `ApplicationEventMulticaster` đã khởi tạo của application context.

Cách đúng là đăng ký sớm:

```java
registry.addCloseListener(event -> {
    // Handoff tại thời điểm bootstrap close.
});
```

Nếu muốn thư viện tự động đăng ký, dùng `BootstrapRegistryInitializer` qua `spring.factories` như phần 8.

## 14. Phân biệt với Spring Cloud bootstrap context

Trong một số hệ thống Spring Cloud, thuật ngữ *bootstrap context* còn được dùng để chỉ **một Spring `ApplicationContext` riêng** ở giai đoạn trước ứng dụng chính (ví dụ một số cơ chế Spring Cloud Config/legacy bootstrap).

Cơ chế `BootstrapRegistry` của **Spring Boot core** trong bài này là **một registry nhẹ**, không mặc nhiên tạo một context cha chứa đầy đủ Spring bean. Đừng suy luận:

- Có `BootstrapContextClosedEvent` nghĩa là một “Spring Cloud bootstrap ApplicationContext” đã đóng.
- Lấy bean từ `BootstrapContext` cũng giống `@Autowired` từ Spring Cloud parent context.
- Mọi cơ chế `bootstrap.yml` của Spring Cloud đều tuân cùng một thứ tự sự kiện mà không cần xét phiên bản/cấu hình Cloud.

Nếu dùng Spring Cloud, xác minh phiên bản tương thích với Boot và đường config-loading cụ thể. Bài này cố ý chỉ trình bày API Spring Boot 3.3 để tránh trộn hai hệ thống với nhau.

## 15. Cách kiểm thử và xác minh hành vi chuyển giao

Khi triển khai một `BootstrapRegistryInitializer` thực tế, các phép kiểm chứng có giá trị:

1. **Đăng ký sớm:** xác nhận initializer chạy trước việc dùng client từ bước config-loading.
2. **Lazy singleton:** supplier chỉ tạo instance khi `get(...)` thực sự xảy ra và với scope singleton không tạo lại cùng type.
3. **Đúng thời điểm event:** handoff chạy sau lúc application context chuẩn bị, nhưng trước refresh/runner.
4. **Đúng identity:** instance ứng dụng nhận là cùng object (hoặc bản sao có chủ đích) với dữ liệu bootstrap.
5. **Không bean trùng:** tên/type đăng ký không xung đột với component scan hoặc starter khác.
6. **Cleanup:** resource I/O được đóng đúng một lần khi ứng dụng kết thúc hoặc startup fail.
7. **Failure case:** type chưa đăng ký, supplier ném exception, listener ném exception phải có log/exit rõ ràng.
8. **Không rò bí mật:** không in endpoint nội bộ nhạy cảm, token hoặc toàn bộ cấu hình trong startup log.
9. **Đúng môi trường:** test với các profile và dependency thực tế; cơ chế khởi động test có thể khác khi dùng cấu hình test tùy biến.
10. **Độc lập nhiều lần chạy:** nếu tạo nhiều `SpringApplication`/contexts trong một JVM test, không để một static registry giữ nhầm instance giữa các lần chạy.

Với ví dụ mục 7, chỉ cần chạy `./gradlew bootRun` và quan sát dòng `01` đến `05` theo thứ tự đã nêu. Nó minh họa việc tạo muộn, bàn giao và inject. **Không cần** mở HTTP server để thử vì đây là lifecycle của Spring Boot startup, không phải tính năng request routing.

## 16. Lỗi hiểu nhầm thường gặp và cách sửa

| Hiểu nhầm hoặc triệu chứng | Thực chất | Cách xử lý |
| --- | --- | --- |
| “BootstrapContextClosedEvent nghĩa ứng dụng đang shutdown.” | Chỉ đóng phạm vi bootstrap rất sớm. | Phân biệt với `ContextClosedEvent`. |
| “Event xuất hiện sau ApplicationReadyEvent.” | Đóng bootstrap trước refresh và runners. | Kiểm tra thứ tự startup sự kiện. |
| “Có @Bean thì bootstrap context tự lấy được.” | Registry không phải BeanFactory. | Dùng `BootstrapRegistryInitializer.register(...)`. |
| “Chỉ register supplier là đã tạo client.” | Thường tạo muộn khi gọi `get`. | Đặt log constructor và kiểm tra lần truy cập đầu. |
| “@EventListener trong @Component bắt được bootstrap close.” | Bean/listener này thường chỉ tồn tại sau refresh. | Dùng `registry.addCloseListener`. |
| “Bean của app đã sẵn sàng trong close listener.” | Context được chuẩn bị, chưa refresh. | Không `getBean` nghiệp vụ; chỉ thao tác đăng ký hợp lệ. |
| “Đóng bootstrap tự đăng ký mọi đối tượng thành Spring bean.” | Không có bàn giao tự động tổng quát. | Handoff type/instance cần thiết có chủ đích. |
| “registerSingleton chạy đủ @PostConstruct và @PreDestroy.” | Raw singleton bỏ qua nhiều bước lifecycle. | Dùng BeanDefinition/managed owner khi cần. |
| “Đã chuyển instance thì có thể dùng registry suốt runtime.” | Bootstrap registry là vùng tạm của startup. | Truy cập qua Spring bean đã chuyển giao. |
| “registerIfAbsent tránh mọi xung đột Spring bean.” | Nó chỉ kiểm tra key trong bootstrap registry. | Kiểm tra thêm BeanFactory name/type. |
| “Close listener phù hợp để chạy batch nặng.” | Nó nằm trên critical path startup. | Giới hạn công việc; đưa nghiệp vụ sau refresh sang runner. |
| “Thêm PropertySource lúc close sẽ sửa mọi quyết định khởi động trước đó.” | Một số lựa chọn đã được Boot áp dụng. | Đặt config/processor ở giai đoạn sớm hơn. |
| “Spring Cloud bootstrap và Boot BootstrapRegistry là cùng loại context.” | Có thiết kế, lifecycle và API khác nhau. | Xác minh module/version và ý nghĩa của từng thuật ngữ. |
| “Cứ gọi DefaultBootstrapContext.close() để reset startup.” | Boot sở hữu chuỗi đóng bootstrap. | Để `SpringApplication` tự điều phối. |

## 17. Bài tập áp dụng

**Bài tập A — Quan sát tạo muộn:** trong ví dụ mục 7, thêm một log vào supplier. Chạy chương trình và so sánh vị trí log này với `REGISTRY`, `HANDOFF`. Giải thích tại sao việc đăng ký supplier chưa tạo đối tượng.

**Bài tập B — Chứng minh handoff:** bỏ dòng `registerSingleton(...)` nhưng vẫn giữ `@Bean ApplicationRunner` yêu cầu `BootstrapValue`. Dự đoán startup fail tại giai đoạn nào, sau đó khôi phục dòng đăng ký và giải thích sự khác nhau giữa hai container.

**Bài tập C — So sánh event:** vẽ đường đi `ApplicationContextInitializedEvent → BootstrapContextClosedEvent → ApplicationPreparedEvent → refresh → ApplicationStartedEvent → ApplicationReadyEvent`. Đánh dấu ở mốc nào có thể dùng BeanFactory để đăng ký và ở mốc nào bean nghiệp vụ đã được khởi tạo.

**Bài tập D — Ownership:** giả sử `BootstrapValue` là một client giữ socket thay vì record. Thiết kế ai là owner sau handoff, khi nào đóng socket, cách tránh close hai lần, xử lý nếu startup fail trước khi handoff.

**Bài tập E — Phân biệt hai bootstrap context:** mô tả tại sao registry của Boot core không tương đương một Spring Cloud parent `ApplicationContext`. Chỉ ra một API của mỗi bên và vòng đời đặc trưng.

## 18. Checklist ghi nhớ

- `BootstrapRegistryInitializer` là điểm đăng ký **rất sớm**, trước khi bean container chính hoàn chỉnh.
- Registry khóa theo `Class<T>`; `get(Class<T>)` lấy instance đã đăng ký và có thể tạo muộn.
- `BootstrapContextClosedEvent` cung cấp **cả `BootstrapContext` và `ConfigurableApplicationContext`**.
- Event phát khi application context đã **prepared**, còn **chưa refresh** trong chuỗi `SpringApplication` thông thường.
- `BootstrapRegistry.addCloseListener(...)` là cách đăng ký listener đúng pha; một `@EventListener` trên bean runtime sẽ đến quá muộn.
- Chuyển object sang BeanFactory bằng `registerSingleton` hoặc bean definition khi thật sự cần, hiểu rõ khác biệt về lifecycle.
- Đóng bootstrap **không phải** đóng application context/JVM; cũng không đánh dấu readiness.
- Bootstrap registry dùng cho startup; runtime nên dùng bean/abstraction đã được bàn giao.
- Đối tượng có socket/thread cần owner, cleanup, lỗi và timeout rõ ràng.
- Không trộn `BootstrapRegistry` của Spring Boot core với Spring Cloud bootstrap context.

## Tài liệu chính thức để đối chiếu

- [Spring Boot 3.3 — BootstrapRegistry API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistry.html)
- [Spring Boot 3.3 — BootstrapContext API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContext.html)
- [Spring Boot 3.3 — ConfigurableBootstrapContext API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ConfigurableBootstrapContext.html)
- [Spring Boot 3.3 — DefaultBootstrapContext API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultBootstrapContext.html)
- [Spring Boot 3.3 — BootstrapContextClosedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContextClosedEvent.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — SpringApplication events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework — Programmatically registering beans](https://docs.spring.io/spring-framework/reference/core/beans/java/programmatic-bean-registration.html)
