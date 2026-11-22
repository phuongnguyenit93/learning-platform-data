# Giới hạn của Binder khi dùng trực tiếp ngoài vòng đời bean trong Spring Boot 3.3

## 1. Mục tiêu

Spring Boot 3.3 cung cấp API `org.springframework.boot.context.properties.bind.Binder` để liên kết dữ liệu cấu hình bên ngoài vào một kiểu Java. Trong trường hợp phổ biến, lập trình viên khai báo `@ConfigurationProperties`, đăng ký bean bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, rồi để Spring Boot quản lý việc tạo bean, binding và validation theo vòng đời ứng dụng.

Tuy nhiên, đôi khi cần gọi Binder **trực tiếp**:

- Đọc một nhóm cấu hình tạm thời ở một điểm trong chương trình.
- Chuyển các giá trị từ một `Environment` đã có thành một record hoặc POJO.
- Parse một `MapPropertySource` trong unit test hay công cụ chạy độc lập.
- Bind một `Map<String, Integer>` hoặc `List<String>` mà không cần tạo một bean Spring.
- Tạo một snapshot cấu hình cho một thao tác ngắn.

Các thao tác này được hỗ trợ, nhưng cần phân biệt **khả năng của Binder** với **toàn bộ vòng đời `@ConfigurationProperties` bean**.

**Nguyên tắc trung tâm:**

> `Binder.bind(...)` là một thao tác đọc, chuyển đổi và liên kết giá trị từ `ConfigurationPropertySources` vào một đối tượng. Nó không tự động đăng ký đối tượng đó thành Spring bean, không gọi toàn bộ bean lifecycle và không mặc nhiên áp dụng mọi tiện ích mà Spring Boot thiết lập cho `@ConfigurationProperties` bean trong `ApplicationContext`.

Bài viết giải thích các giới hạn này ở Spring Boot **3.3**, từ chuẩn bị `Environment`, Config Data, placeholder, conversion và validation đến vòng đời bean, thay đổi cấu hình, concurrency và cách test.

## 2. Hai đường đi khác nhau đến cùng một đối tượng cấu hình

### 2.1. Đường đi do Spring Boot quản lý

```text
SpringApplication.run(...)
  |
  +-- Chuẩn bị Environment và Config Data
  |      application.properties / YAML / import / profiles...
  |
  +-- Khởi tạo ApplicationContext và bean definitions
  |
  +-- Tạo @ConfigurationProperties bean
  |
  +-- Binder liên kết dữ liệu cho bean
  |
  +-- BindHandler / conversion / validation được cấu hình
  |
  +-- BeanPostProcessors và các bước khởi tạo của Spring
  |
  +-- Bean sẵn sàng để inject vào các component khác
```

Ví dụ:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public class ClientProperties {
    private String host = "localhost";
    private int port = 8080;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
```

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Khi được đăng ký đúng cách, `ClientProperties` là một **Spring bean**. Các component khác có thể nhận nó qua constructor injection. Spring Boot quản lý binding cùng những bước cần thiết của lifecycle.

### 2.2. Đường đi gọi Binder trực tiếp

```java
Binder binder = Binder.get(environment);
ClientProperties settings = binder
        .bind("client", ClientProperties.class)
        .orElseGet(ClientProperties::new);
```

Ở đây:

1. `Binder.get(environment)` dùng những `ConfigurationPropertySources` đã gắn vào `Environment`.
2. `bind("client", ClientProperties.class)` đọc và liên kết dữ liệu theo prefix `client`.
3. Kết quả là một đối tượng Java do lời gọi này tạo ra, **không tự biến thành bean trong Spring container**.
4. Nếu không có giá trị nào được bind, `BindResult` có thể không chứa kết quả; `orElseGet(...)` trong ví dụ là phương án fallback của code gọi.
5. Việc tạo instance thủ công không đồng nghĩa Spring sẽ xử lý `@Autowired`, `@PostConstruct`, `BeanPostProcessor`, proxy AOP hay dependency injection trên instance đó.

**Điều không bị mất:** Binder vẫn có thể thực hiện relaxed binding, binding đối tượng lồng nhau, collection, map, chuyển đổi kiểu và constructor binding khi nguồn dữ liệu, target type và các thành phần hỗ trợ được cấu hình phù hợp.

**Điều không tự xuất hiện:** một Spring bean được đăng ký, các bước lifecycle container, cơ chế validation gắn với bean binding và hành vi refresh ứng dụng.

## 3. Bảng so sánh nhanh

| Năng lực | `@ConfigurationProperties` do Boot quản lý | `Binder` gọi trực tiếp |
| --- | --- | --- |
| Đọc property theo prefix | Có | Có |
| Relaxed binding | Có | Có với `ConfigurationPropertySources` thích hợp |
| Nested object/List/Map | Có | Có, tùy target type và nguồn |
| Chuyển đổi `Duration`/`DataSize`/enum | Có | Có với conversion service thích hợp |
| Đọc `application.yaml`/profile/import | Có sau khi Boot chuẩn bị Env | Chỉ đọc được nếu những nguồn đó **đã có** trong Env/nguồn được truyền |
| Tự tạo và đăng ký Spring bean | Qua cơ chế đăng ký config props | **Không** |
| Inject dependency vào object | Do container nếu object là bean | **Không tự động** |
| `@PostConstruct`/`InitializingBean` | Thuộc lifecycle của bean | **Không tự động** |
| BeanPostProcessor/proxy AOP | Có thể áp dụng cho Spring bean | **Không áp dụng tự động cho object thủ công** |
| `@Validated`/Bean Validation trên config bean | Có khi hạ tầng được cấu hình | **Không mặc nhiên**; cần handler/validator hoặc validation riêng |
| Custom converter từ ApplicationContext | Có thể được Boot tích hợp cho bean binding | Không nên giả định có cùng tập converter khi dùng Binder độc lập |
| Bean name, scope, disposal callback | Do container quản lý | **Không có** nếu object chưa được đăng ký |
| Cập nhật khi config nguồn thay đổi | Không mặc nhiên live-update trong mọi ứng dụng | Cũng **không tự refresh** đối tượng đã bind |
| Có thể dùng ngoài Spring context | Không theo cách bean lifecycle thông thường | Có, nếu tự cấp nguồn và hạ tầng cần thiết |
| Kiểm soát BindHandler | Thông qua cấu hình/hạ tầng Boot | Có thể truyền trực tiếp vào `bind(...)` |

Bảng này không có nghĩa mọi `@ConfigurationProperties` bean tự hot-reload. Trong ứng dụng Boot thông thường, cấu hình được bind trong quá trình startup và không tự cập nhật khi file đổi. Nếu cần refresh, phải dùng một cơ chế riêng được thiết kế cho việc đó.

## 4. API cơ bản của Binder trong Spring Boot 3.3

Những API đáng biết trong `org.springframework.boot.context.properties.bind.Binder`:

```java
Binder.get(Environment environment)

binder.bind(String name, Class<T> target)

binder.bind(String name, Bindable<T> target)

binder.bind(String name, Bindable<T> target, BindHandler handler)

binder.bindOrCreate(String name, Class<T> target)

binder.bindOrCreate(String name, Bindable<T> target)
```

Các kiểu đi cùng:

- `BindResult<T>`: mô tả kết quả đã bind hoặc trạng thái không có kết quả.
- `Bindable<T>`: mô tả target type, generic type, đối tượng đã có và những thông tin binding khác.
- `BindHandler`: cho phép tùy biến quá trình binding, ví dụ validation hoặc hành vi khi gặp property không bind được.
- `ConfigurationPropertySource`: nguồn dữ liệu phù hợp với mô hình tên property của Spring Boot.
- `ConfigurationPropertySources`: adapter/registry nối Spring `PropertySource` với nguồn dữ liệu mà Binder đọc.

### 4.1. Đọc một scalar

```java
Integer retryCount = Binder.get(environment)
        .bind("app.retry-count", Integer.class)
        .orElse(3);
```

Nếu Binder không tìm thấy giá trị cần thiết cho `app.retry-count`, `orElse(3)` trả về 3. Nếu property có `0`, kết quả có thể là `0`; default 3 không được dùng chỉ vì giá trị bằng zero.

### 4.2. Đọc một POJO

```java
ClientProperties properties = Binder.get(environment)
        .bind("client", ClientProperties.class)
        .orElseGet(ClientProperties::new);
```

Binder có thể gọi constructor không tham số rồi các setters theo JavaBean binding. Code này không gọi `@ConfigurationPropertiesScan` và cũng không cần class nhất thiết có annotation `@ConfigurationProperties` để mô tả prefix: prefix đã được truyền vào `bind(...)`.

### 4.3. Đọc Map có generic type

```java
import java.util.Map;
import org.springframework.boot.context.properties.bind.Bindable;

Map<String, Integer> limits = Binder.get(environment)
        .bind(
            "app.retry-limits",
            Bindable.mapOf(String.class, Integer.class))
        .orElseGet(Map::of);
```

Khi có:

```properties
app.retry-limits.billing=3
app.retry-limits.search=0
```

Binder có thể tạo `Map<String,Integer>` với `billing → 3`, `search → 0`. Dùng `Bindable.mapOf(...)` để giữ thông tin generic; truyền `Map.class` đơn thuần không truyền đạt đầy đủ kiểu key/value cần convert.

### 4.4. Đọc List có element type

```java
import java.util.List;

List<String> regions = Binder.get(environment)
        .bind("app.regions", Bindable.listOf(String.class))
        .orElseGet(List::of);
```

Với:

```properties
app.regions[0]=vn
app.regions[1]=sg
```

kết quả có thể là `["vn", "sg"]`. Dù API gọi Binder thủ công, quy tắc binding collection từ những nguồn có precedence khác nhau vẫn liên quan: List thường được lấy từ một nguồn có ưu tiên thích hợp thay vì tự nối các List.

## 5. Giới hạn thứ nhất: Environment phải được chuẩn bị

Phương thức `Binder.get(environment)` trong Spring Boot 3.3 yêu cầu `Environment` đã được gắn các `ConfigurationPropertySources` thích hợp. Đây là điều kiện được nêu trong Javadoc của chính `Binder.get(Environment)`.

### 5.1. Trong SpringApplication thông thường

Khi một bean sau startup nhận `Environment` qua constructor injection hoặc method parameter, Spring Boot đã chuẩn bị hạ tầng configuration properties như một phần quá trình khởi động.

Ví dụ `ApplicationRunner`:

```java
package com.example.demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class StartupDiagnostics {

    @Bean
    ApplicationRunner showRetryCount(Environment environment) {
        return args -> {
            int retries = Binder.get(environment)
                    .bind("app.retry-count", Integer.class)
                    .orElse(3);

            System.out.println("Effective retry count: " + retries);
        };
    }
}
```

Ở thời điểm `ApplicationRunner` chạy, `Environment` của Boot đã qua giai đoạn Config Data thông thường. Kết quả dùng các property sources đang có, theo precedence của chúng. Mục đích ở đây là **đọc một giá trị để chẩn đoán**, không phải tạo một cấu hình bean thứ hai để thay thế bean đã được quản lý.

### 5.2. Với StandardEnvironment được tạo thủ công

Nếu tạo một `StandardEnvironment` độc lập, đừng giả định chỉ cần gọi `Binder.get(env)` là mọi adapter đã tồn tại.

Ví dụ tự chuẩn bị môi trường:

```java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

public class StandaloneBinderExample {

    public static void main(String[] args) {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
            new MapPropertySource("manual-config", Map.of(
                "app.retry-count", "4",
                "app.enabled", "false"
            ))
        );

        ConfigurationPropertySources.attach(env);

        int count = Binder.get(env)
                .bind("app.retry-count", Integer.class)
                .orElse(3);

        boolean enabled = Binder.get(env)
                .bind("app.enabled", Boolean.class)
                .orElse(true);

        System.out.println(count);   // 4
        System.out.println(enabled); // false
    }
}
```

**Ý nghĩa `attach(env)`:** kết nối Spring `Environment` với `ConfigurationPropertySources` để Binder có thể truy cập theo tên configuration property. Nó **không khởi động một Spring Boot application**, không tải `application.yaml`, không tìm `spring.config.import` và không tự thực thi `ConfigDataEnvironmentPostProcessor`.

`StandardEnvironment` còn có các property sources mặc định như system properties và OS environment; trong ví dụ, `manual-config` được đặt lên đầu để ưu tiên dữ liệu đang minh họa. Nếu muốn unit test cô lập tuyệt đối, sử dụng dữ liệu và môi trường được kiểm soát rõ, tránh để giá trị từ máy developer ảnh hưởng test.

### 5.3. Nếu muốn tránh attach vào Environment dùng chung

Có thể tạo Binder từ những `ConfigurationPropertySource` đã biết hoặc adapter cho Spring `PropertySource`:

```java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.StandardEnvironment;

StandardEnvironment env = new StandardEnvironment();

Binder binder = new Binder(
        ConfigurationPropertySources.from(env.getPropertySources()));
```

Đây là một hướng tạo Binder thủ công từ các nguồn. **Nhưng** khi tự xây dựng Binder bằng constructor tối giản, phải hiểu những thành phần khác như **placeholder resolver** và **custom conversion services** có thể chưa được cấu hình như trong `Binder.get(environment)`.

Nếu dữ liệu có placeholder `${...}`, hãy dùng `Binder.get(env)` trên Environment đã attach hoặc tự cung cấp `PlaceholdersResolver` phù hợp. Không coi hai cách khởi tạo Binder là tương đương tuyệt đối khi project có placeholder/custom converters phức tạp.

## 6. Giới hạn thứ hai: Binder không tự tải Config Data

Một giả định sai thường gặp:

```java
Environment env = new StandardEnvironment();
Binder binder = Binder.get(env);
```

Ngay cả khi đã attach `ConfigurationPropertySources`, Environment tự tạo **không mặc nhiên** đọc các file:

```text
src/main/resources/application.properties
src/main/resources/application.yaml
config/application-prod.yaml
```

Các file trên thuộc quy trình **Config Data** của Spring Boot; chúng được xử lý trong quá trình khởi động bởi những thành phần chuyên dụng.

Các tính năng như:

- `spring.config.import`.
- `spring.config.location`, `spring.config.additional-location`.
- `application-{profile}.properties`, `application-{profile}.yaml`.
- Multi-document YAML phân tách bằng `---`.
- Multi-document .properties phân tách bằng `#---`.
- `spring.config.activate.on-profile`.
- `spring.config.activate.on-cloud-platform`.

đều gắn với bước nạp Config Data phù hợp. Một Binder được tạo độc lập **không phải Config Data loader** và không tự kích hoạt lại quá trình tìm file hay xử lý profile.

### 6.1. Ví dụ dễ nhầm

```properties
# application.properties
spring.config.import=classpath:/config/remote.properties
app.client.timeout=5s
```

Nếu một `StandardEnvironment` thủ công chỉ chứa các PropertySource mặc định, `Binder` không tự đi tìm `application.properties` rồi import `remote.properties`. Việc đưa text `spring.config.import=...` vào một `MapPropertySource` cũng không khiến Binder thực thi import.

Muốn dùng dữ liệu do Boot tải, hãy gọi Binder **sau khi** Environment đã được Spring Boot chuẩn bị. Muốn dùng dữ liệu từ file ngoài Boot, hãy cung cấp chính nguồn đã được đọc/chuyển thành `ConfigurationPropertySource` phù hợp, hoặc dùng một cơ chế Config Data thích hợp ở tầng startup.

### 6.2. Thời điểm gọi Binder quyết định tập nguồn có sẵn

Nếu code đọc trong một `EnvironmentPostProcessor` rất sớm, một số property sources hoặc profile-specific data có thể **chưa được thêm** tùy ordering. Đừng suy luận rằng giá trị đọc được từ một Binder sớm bằng giá trị sau khi Boot khởi động hoàn tất.

Với những thuộc tính khởi động quan trọng như `spring.config.name`, `spring.config.location` hoặc `spring.main.*`, cần xác định chính xác giai đoạn sử dụng. Binder gọi ở giai đoạn muộn không thể quay ngược lại để thay đổi quyết định nạp file đã xảy ra.

## 7. Giới hạn thứ ba: đối tượng bind được không tự thành bean

Ví dụ:

```java
ClientProperties raw = Binder.get(environment)
        .bindOrCreate("client", ClientProperties.class);
```

`raw` là một object Java. Bản thân lời gọi trên **không thực hiện**:

- Đăng ký `BeanDefinition` trong `ApplicationContext`.
- Gán bean name hoặc scope.
- Dependency injection vào các field có `@Autowired`.
- Gọi `BeanPostProcessor` / `BeanFactoryPostProcessor` cho object đó.
- Kích hoạt `@PostConstruct`/`InitializingBean.afterPropertiesSet()` theo bean lifecycle.
- Tạo AOP proxy chỉ vì class hoặc method có annotation thích hợp.
- Quản lý `@PreDestroy` hoặc `DisposableBean` khi context đóng.
- Đăng ký object để có thể `@Autowired` vào một service khác.

### 7.1. Ví dụ @PostConstruct không được gọi

```java
package com.example.demo.config;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public class ClientProperties {

    private String host = "localhost";
    private boolean initialized;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public boolean isInitialized() { return initialized; }

    @PostConstruct
    public void init() {
        initialized = true;
    }
}
```

Sau lời gọi trực tiếp:

```java
ClientProperties p = Binder.get(environment)
        .bindOrCreate("client", ClientProperties.class);
```

chỉ có thể chắc rằng Binder đã thử liên kết các property. `p.isInitialized()` có thể vẫn là `false` vì `@PostConstruct` không được Binder tự gọi. Nếu class được container tạo và xử lý như một Spring bean, các lifecycle callbacks mới có cơ hội được gọi theo cơ chế tương ứng.

**Thiết kế tốt hơn:** property object nên chủ yếu chứa dữ liệu. Nếu cần một hành vi khởi tạo resource có side effect, hãy thực hiện nó trong Spring-managed service dùng `ClientProperties`, không đặt trách nhiệm tạo connection/thread hoặc đăng ký callback trong getter/setter của properties.

### 7.2. Annotation @ConfigurationProperties không tạo ra magic

Một class có:

```java
@ConfigurationProperties(prefix = "client")
public class ClientProperties { /* ... */ }
```

chưa chắc là bean nếu không đăng ký. Tương tự, truyền class đó vào `Binder.bind("client", ClientProperties.class)` không đăng ký nó vào context.

`@ConfigurationPropertiesScan` và `@EnableConfigurationProperties` là các cơ chế **đăng ký bean**. `Binder` là cơ chế **liên kết dữ liệu**. Hai việc có thể phối hợp nhưng không phải cùng một thao tác.

### 7.3. Trường hợp có chủ đích đưa kết quả vào @Bean

Nếu object được tạo trong một `@Bean` method:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    ClientProperties clientProperties(Environment environment) {
        return Binder.get(environment)
                .bindOrCreate("client", ClientProperties.class);
    }
}
```

thì **kết quả trả về của `@Bean` method** được container quản lý sau khi method chạy, và Spring có thể áp dụng các bước bean lifecycle phù hợp cho bean đó. Điều này khác với việc tạo object ở một utility method ngoài container.

Tuy nhiên, cách này không phải lúc nào cũng cần thiết; với `@ConfigurationProperties` chuẩn, thường đơn giản hơn:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientConfiguration {
}
```

Không vừa manual-bind vừa đặt thêm cơ chế binding `@ConfigurationProperties` trên cùng bean một cách thiếu chủ đích, vì có thể gây binding trùng/khó xác định điểm lỗi.

## 8. Giới hạn thứ tư: validation không tự động giống bean binding

Giả sử một class cấu hình có:

```java
package com.example.demo.config;

import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public class WorkerProperties {

    @Min(1)
    private int threads = 4;

    public int getThreads() { return threads; }
    public void setThreads(int threads) {
        this.threads = threads;
    }
}
```

Và nguồn:

```properties
worker.threads=0
```

Binding number `0` sang `int` là thành công về **conversion**, nhưng vi phạm `@Min(1)`.

Khi `WorkerProperties` được Spring Boot đăng ký như `@ConfigurationProperties` bean và Bean Validation provider phù hợp có mặt, validation có thể làm startup thất bại. Nhưng:

```java
WorkerProperties value = Binder.get(environment)
        .bindOrCreate("worker", WorkerProperties.class);
```

không nên được xem là bảo đảm chạy **chính cơ chế validation** của bean-managed `@ConfigurationProperties`. `@Validated` là metadata phục vụ validation infrastructure; nó không tự biến mọi lời gọi Binder thuần túy thành validation.

### 8.1. Kiểm tra thủ công bằng BindHandler

Spring Boot có `ValidationBindHandler` trong package:

```java
org.springframework.boot.context.properties.bind.validation
```

Ví dụ trong một component đã có Spring `Validator` phù hợp:

```java
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.validation.ValidationBindHandler;
import org.springframework.core.env.Environment;
import org.springframework.validation.Validator;

public final class ManualValidatedBinding {

    private final Environment environment;
    private final Validator validator;

    public ManualValidatedBinding(Environment environment,
                                  Validator validator) {
        this.environment = environment;
        this.validator = validator;
    }

    public WorkerProperties load() {
        return Binder.get(environment)
                .bind(
                    "worker",
                    Bindable.of(WorkerProperties.class),
                    new ValidationBindHandler(validator))
                .orElseGet(WorkerProperties::new);
    }
}
```

**Điểm phải hiểu:**

- Cần một `Validator` thực sự hỗ trợ kiểu đối tượng `WorkerProperties` và có hạ tầng validation phù hợp.
- `ValidationBindHandler` được gọi trong lần `bind(...)` đã chỉ định; không vì tồn tại một lần mà mọi `Binder.bind(...)` ở nơi khác đều có validation.
- Trong ví dụ, nếu không có property nào được bind, nhánh `orElseGet(WorkerProperties::new)` tạo object **ngoài lần bind**; object fallback này cần được validate riêng nếu policy yêu cầu validation ngay cả khi nguồn vắng mặt.
- Nếu muốn fail-fast cho property bắt buộc, hãy xác định rõ hành vi khi `BindResult` rỗng và khi object vi phạm constraint.

Ngoài `ValidationBindHandler`, có thể gọi Bean Validation trên kết quả đã bind thông qua service hạ tầng được inject. Đó là lựa chọn dễ kiểm soát khi ứng dụng cần nhiều quy tắc nghiệp vụ hoặc policy độc lập.

### 8.2. Conversion error vẫn khác validation error

```properties
worker.threads=abc
```

Ở đây lỗi phát sinh khi chuyển `"abc"` sang `int`, trước khi `@Min(1)` có thể đánh giá. `ValidationBindHandler` không phải bộ sửa conversion lỗi; nó chỉ giúp validate kết quả bind được.

Cần phân biệt lỗi `BindException`/`ConversionFailedException` với vi phạm Bean Validation để báo thông điệp đúng cho người vận hành.

### 8.3. Custom BindHandler phải được truyền có chủ đích

Nếu quy trình bean-managed có các `BindHandler` được Boot cài đặt thông qua configuration-properties infrastructure/advisor, một Binder tạo độc lập **không mặc nhiên** nhận toàn bộ chuỗi handler tương tự. Nếu cần:

- Từ chối unbound properties.
- Ghi metric hoặc theo dõi binding.
- Validate theo một tập constraint.
- Xử lý lỗi bằng logic riêng.

hãy cấu hình `BindHandler` được hỗ trợ **ngay cho lời gọi Binder** hoặc dùng managed bean binding khi đó mới là mục tiêu.

## 9. Giới hạn thứ năm: converter và placeholder có thể khác

### 9.1. Default conversion của Binder

Binder có hỗ trợ các kiểu quen thuộc thông qua conversion service, ví dụ:

- `String` → `int`, `Integer`, `boolean`, `Boolean`.
- Chuỗi thời lượng → `java.time.Duration`.
- Chuỗi kích thước → `DataSize`.
- Tên enum → enum được khai báo.
- Cấu hình nested → JavaBean/constructor-bound target.
- List/Map với element/key/value type có thể xác định.

Vì thế dùng Binder trực tiếp không có nghĩa phải tự parse mọi số hoặc Duration.

### 9.2. Custom converter từ Spring context

Giả sử ứng dụng định nghĩa:

```java
@Component
@ConfigurationPropertiesBinding
public class StringToRegionConverter
        implements Converter<String, Region> {

    @Override
    public Region convert(String source) {
        return Region.parse(source);
    }
}
```

Trong bean-managed configuration-properties binding, Spring Boot có thể tích hợp converter được đăng ký đúng cách. Nhưng với một `Binder` độc lập, đặc biệt tạo bằng `new Binder(...)` bên ngoài `ApplicationContext`, **không nên mặc định converter này đã có mặt**.

Nếu cần conversion đặc thù, một số lựa chọn là:

1. Dùng `@ConfigurationProperties` bean-managed để Boot quản lý hạ tầng.
2. Cấu hình `ConversionService` thích hợp và truyền vào constructor Binder tương ứng.
3. Đọc giá trị bằng kiểu trung gian được Binder hỗ trợ, rồi chuyển bằng service riêng với xử lý lỗi rõ ràng.

Không giải quyết bằng cách thêm converter bean rồi cho rằng mọi lời gọi `new Binder(...)` trong unit test/CLI tool tự phát hiện nó.

### 9.3. Placeholder trong giá trị

Ví dụ:

```properties
app.base-url=https://api.example.test
app.client-url=${app.base-url}/v1
```

Trong Environment đã chuẩn bị, `Binder.get(environment)` có thể sử dụng resolver phù hợp để giải các placeholder tham chiếu property. Nhưng nếu tự khởi tạo:

```java
Binder binder = new Binder(
        ConfigurationPropertySources.from(env.getPropertySources()));
```

thì không nên giả định Binder cấu hình tối giản nhận cùng `PlaceholdersResolver` và context như Binder tạo từ Environment.

Nếu ứng dụng cần placeholder, dùng `Binder.get(environment)` sau khi `ConfigurationPropertySources.attach(env)`, hoặc tự cấp `PlaceholdersResolver` phù hợp trong constructor Binder. Đừng để một giá trị literal `${app.base-url}` đi vào Java field rồi chỉ phát hiện khi HTTP client sử dụng URL.

## 10. Giới hạn thứ sáu: không tự được dependency injection hoặc AOP

Một cấu hình object có:

```java
public class Settings {
    @Autowired
    private SomeService service;
}
```

khi được tạo bởi `Binder.bindOrCreate(...)` không được bảo đảm Spring tiêm `SomeService`. Điều này có thể dẫn đến `null` khi code sử dụng field, nếu không qua bean lifecycle.

Tương tự, các annotation như `@Transactional`, `@Async` hoặc `@Cacheable` thường dựa vào proxy/infrastructure của Spring. Một object được Binder trả về không tự nhận proxy chỉ do phương thức mang annotation.

**Khuyến nghị:** không thiết kế `@ConfigurationProperties` như một service có injected dependencies. Tách thành:

```text
Configuration object (chỉ dữ liệu và validation)
        |
        v
Spring-managed service (dependency injection, lifecycle, logic)
```

Ví dụ:

```java
@Service
public class ClientService {

    private final ClientProperties settings;
    private final HttpClient httpClient;

    public ClientService(ClientProperties settings,
                         HttpClient httpClient) {
        this.settings = settings;
        this.httpClient = httpClient;
    }
}
```

Trong ví dụ, `ClientProperties` được đăng ký là bean, `ClientService` cũng là bean, và việc inject được thực hiện qua constructor. Nếu dùng Binder thủ công để lấy một snapshot cấu hình tạm thời, hãy truyền snapshot đó như một **dữ liệu** vào service thay vì xem nó là Spring-managed component.

## 11. Giới hạn thứ bảy: không tự refresh sau khi nguồn thay đổi

Giả sử lúc startup:

```properties
app.retry-count=3
```

Rồi code gọi:

```java
var snapshot = Binder.get(environment)
        .bind("app.retry-count", Integer.class)
        .orElse(0);
```

Giá trị `snapshot` là `3` tại lúc gọi. Sau đó, nếu một hệ thống khác thay đổi property source hoặc file cấu hình ngoài tiến trình thành `app.retry-count=5`, biến `snapshot` **không tự chuyển thành 5**.

Những điều cần tách:

- **Đổi file trên đĩa:** Spring Boot thông thường không tự load lại Config Data chỉ vì file đổi.
- **Thay đổi một MutablePropertySource trong cùng Environment:** lần đọc/bind mới có thể quan sát giá trị mới nếu nguồn đã cập nhật phù hợp, nhưng object đã được bind trước đó vẫn không tự cập nhật.
- **Binder giữ tham chiếu đến nguồn:** đây không phải một cơ chế watch file/reload/callback cho bean cũ.
- **Spring Cloud refresh hoặc giải pháp tự xây dựng:** là hạ tầng riêng, không phải một tính năng tự động của `Binder.bind`.

### 11.1. Snapshot bất biến giúp tránh nhầm

Với record:

```java
public record RetryPolicy(
        int maxRetries,
        java.time.Duration backoff) {
}
```

Khi thực hiện:

```java
RetryPolicy policy = Binder.get(environment)
        .bind("app.retry", RetryPolicy.class)
        .orElse(new RetryPolicy(3, java.time.Duration.ofSeconds(1)));
```

`policy` là một cấu trúc dữ liệu tại thời điểm binding. Dùng nó như **snapshot**. Nếu cấu hình thay đổi và ứng dụng yêu cầu thay chính sách, phải thiết kế lại quy trình lấy snapshot mới và việc chuyển giao an toàn cho các thread/requests.

### 11.2. Cẩn trọng khi bind lại vào cùng mutable object

```java
ClientProperties existing = new ClientProperties();

Binder.get(environment).bind(
        "client",
        Bindable.ofInstance(existing));
```

`Bindable.ofInstance(existing)` cho phép Binder sử dụng instance hiện tại làm target. Việc bind có thể sửa trạng thái object **tại chỗ**, nên không nên làm điều đó song song với các thread đang đọc object nếu không có cơ chế đồng bộ và quy tắc snapshot rõ.

Không nên mặc định `Binder` hoặc object JavaBean được tạo có tính thread-safe/hot-reload chỉ vì chúng thuộc thư viện Spring Boot. Một chiến lược đáng tin cậy là bind sang instance mới, validate, rồi thay toàn bộ tham chiếu bất biến/được bảo vệ nếu ứng dụng thực sự cần cập nhật cấu hình động.

## 12. BindResult: không có kết quả không đồng nghĩa đã có default đúng

`Binder.bind(...)` trả về `BindResult<T>`. Đây không phải lúc nào cũng chứa một object.

Ví dụ:

```java
BindResult<ClientProperties> result = Binder.get(environment)
        .bind("client", ClientProperties.class);
```

Nếu không có property nào phù hợp với prefix `client`, kết quả có thể là **unbound**. Các cách xử lý:

```java
ClientProperties a = result.orElseGet(ClientProperties::new);
```

Hoặc:

```java
if (result.isBound()) {
    ClientProperties b = result.get();
}
```

Không dùng `result.get()` khi chưa biết nó bound; API có thể ném exception khi không có giá trị. `bindOrCreate(...)` là lựa chọn khác khi cần tạo target dù bind không tìm thấy dữ liệu, nhưng object tạo mới vẫn cần đủ constructor/default để có trạng thái hợp lệ.

### 12.1. Thiếu toàn bộ prefix và thiếu một property con khác nhau

Giả sử JavaBean:

```java
public class RetryProperties {
    private int maxRetries = 3;
    private boolean enabled = true;

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int x) { maxRetries = x; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean x) { enabled = x; }
}
```

Nếu:

```properties
app.retry.enabled=false
```

thì Binder có thể tạo object với:

```text
maxRetries=3
enabled=false
```

Nếu **không có key `app.retry.*`**, một lời gọi `bind("app.retry", RetryProperties.class)` có thể không có kết quả, và code cần lựa chọn fallback. Chọn `orElseGet(RetryProperties::new)` nếu muốn giữ những field initializer; chọn fail-fast nếu prefix bắt buộc.

### 12.2. Không nhầm 0/false/empty với missing

```properties
app.retry.max-retries=0
app.retry.enabled=false
```

`0` và `false` là giá trị explicit. Binder không dùng default 3/true chỉ vì chúng “falsy”. Chuỗi rỗng lại có semantics riêng tùy target type và conversion, không được coi tự động là “không có nguồn”.

## 13. Constructor binding, record và @DefaultValue khi gọi trực tiếp

Bộ Binder có thể bind một type được thiết kế cho constructor binding, không chỉ JavaBean có setter.

Ví dụ:

```java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.bind.DefaultValue;

public record RetryOptions(
        @DefaultValue("3") int maxRetries,
        @DefaultValue("1s") Duration backoff,
        @DefaultValue("false") boolean enabled) {
}
```

Sử dụng:

```java
RetryOptions options = Binder.get(environment)
        .bind("app.retry", RetryOptions.class)
        .orElse(new RetryOptions(3, Duration.ofSeconds(1), false));
```

Nếu có:

```properties
app.retry.max-retries=0
app.retry.backoff=500ms
app.retry.enabled=false
```

Binder có thể tạo record với `maxRetries=0`, `backoff=500ms` và `enabled=false`. `@DefaultValue` của Spring Boot có ý nghĩa khi **property thành phần không được tìm thấy** trong quá trình bind; nó không ghi đè giá trị explicit `0` hoặc `false`.

**Lưu ý quan trọng:** `@DefaultValue` trên thành phần record không làm lời gọi `bind(...)` thành một yêu cầu phải tạo object cho **prefix hoàn toàn vắng mặt**. Chính code gọi nên xử lý `BindResult` rỗng hoặc dùng một API phù hợp nếu muốn luôn có object. Đừng nhầm constructor-binding default với Spring bean registration.

### 13.1. Constructor binding không phải @Autowired constructor

Một constructor dùng để nhận cấu hình:

```java
public RetryOptions(int maxRetries, Duration backoff, boolean enabled)
```

không phải constructor cần Spring inject những bean có kiểu `int`/`Duration`. Binder gán giá trị từ property sources theo tên parameter/record component. Đừng đưa `DataSource` hoặc service vào record configuration rồi kỳ vọng Binder biết tự lấy bean từ context.

## 14. BindHandler: kiểm soát hành vi từng lời gọi

`BindHandler` trong Spring Boot 3.3 cung cấp các hook trong quá trình binding, như:

- `onStart`: bắt đầu bind một property.
- `onSuccess`: bind thành công.
- `onFailure`: bind thất bại.
- `onFinish`: hoàn tất xử lý.

Một số handler do Spring Boot cung cấp có thể dùng cho các trường hợp như validation, bỏ qua lỗi nhất định hoặc báo property chưa được bind.

**Không nên** tự viết handler chỉ để “làm Binder hoạt động”, vì đối với một bean cấu hình tiêu chuẩn Boot đã quản lý hạ tầng cần thiết. Hãy dùng handler khi có yêu cầu rõ ràng về validation, strictness hoặc quan sát việc bind thủ công.

### 14.1. NoUnboundElementsBindHandler

Spring Boot cung cấp:

```java
org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler
```

Handler này có thể giúp phát hiện các property trong phạm vi binding đã xuất hiện nhưng không được bind vào target, khi được cấu hình đúng. Trong manual binding, không có bảo đảm mọi unknown key sẽ bị từ chối nếu bạn **không gắn handler** hoặc không có cơ chế strictness tương đương.

Tuy nhiên, việc phát hiện unknown/unbound cũng phụ thuộc cách source có thể enumerate key và cấu trúc tên property. Đừng dùng handler này như một cơ chế kiểm tra schema tuyệt đối cho mọi loại PropertySource tùy chỉnh.

### 14.2. Không che lỗi conversion bằng handler bỏ qua

Một số BindHandler cho phép tiếp tục khi gặp lỗi bind hoặc trả về giá trị fallback. Nhưng nếu `app.retry-count=abc` mà ứng dụng cần số nguyên, âm thầm bỏ qua lỗi có thể dẫn tới chạy với một giá trị cũ/không mong đợi. Với cấu hình vận hành quan trọng, ưu tiên fail-fast và thông báo lỗi có nguồn.

## 15. Khi dùng Binder trong unit test không có Spring context

Một unit test có thể tạo `Environment` nhỏ, thêm Map source, attach và bind. Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

class ManualBinderTest {

    @Test
    void bindsFromManualMap() {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
            new MapPropertySource(
                "test-values",
                Map.of(
                    "client.host", "api.example.test",
                    "client.port", "9090"
                )
            )
        );

        ConfigurationPropertySources.attach(env);

        ClientProperties result = Binder.get(env)
                .bindOrCreate("client", ClientProperties.class);

        assertEquals("api.example.test", result.getHost());
        assertEquals(9090, result.getPort());
    }
}
```

Ví dụ này kiểm thử **Binder và model** với nguồn rõ ràng. Nó không chứng minh:

- File Config Data được Spring Boot tìm/nạp đúng location.
- Profile-specific file được chọn theo `spring.profiles.active`.
- `@ConfigurationPropertiesScan` tạo bean đúng.
- `@Validated` fail-fast trong `ApplicationContext` thực tế.
- Custom Spring bean converter được Boot tích hợp đúng.
- `@PostConstruct` và các BeanPostProcessor chạy đúng.
- Các test properties hoặc OS environment overrides có precedence giống production.

Để kiểm tra những điều đó, cần test với Spring context, ví dụ `ApplicationContextRunner` hay `@SpringBootTest` tùy mục tiêu.

## 16. Khi cần test hành vi của bean-managed @ConfigurationProperties

`ApplicationContextRunner` từ `spring-boot-test` giúp tạo ApplicationContext nhẹ và kiểm tra chính hành vi đăng ký/bind một bean cấu hình.

Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientConfigContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(Config.class);

    @Test
    void bindsManagedBean() {
        runner.withPropertyValues(
                "client.host=api.example.test",
                "client.port=9090")
            .run(context -> {
                assertThat(context).hasNotFailed();
                ClientProperties props =
                        context.getBean(ClientProperties.class);
                assertThat(props.getHost())
                        .isEqualTo("api.example.test");
                assertThat(props.getPort()).isEqualTo(9090);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class Config {
    }
}
```

Với context runner, property values được cung cấp trực tiếp và cấu hình bean được Spring quản lý. Nếu muốn kiểm tra cả **giai đoạn Config Data/file profile thực tế**, cần một bài integration test khởi động theo workflow tương ứng; một `ApplicationContextRunner` không mặc nhiên tái hiện mọi bước của `SpringApplication`.

### 16.1. Test Bean Validation

Khi property có `@Validated`/constraint và có Bean Validation provider:

```properties
worker.threads=0
```

Test context có thể xác nhận startup thất bại do `@Min(1)`. Test Binder thuần nên kiểm tra riêng handler/validator mà chính lời gọi direct bind sử dụng.

Đừng so sánh hai test chỉ bằng `int threads` sau binding, vì một Binder trực tiếp không validate có thể trả về 0, còn managed bean binding có thể từ chối context. Đó là khác biệt lifecycle/infrastructure, không phải sai relaxed binding.

## 17. Nếu cần kết hợp Binder với logic khởi tạo bean: chọn điểm thích hợp

Có các lựa chọn thiết kế:

### Lựa chọn A — Để Boot tự quản lý cấu hình

```java
@ConfigurationProperties(prefix = "client")
public class ClientProperties {
    // JavaBean accessors hoặc constructor-bound model
}
```

```java
@SpringBootApplication
@ConfigurationPropertiesScan
class DemoApplication {
}
```

Dùng cách này nếu cấu hình là thành phần lâu dài của ứng dụng, cần injection, validation, metadata và nguồn Config Data theo startup thông thường.

### Lựa chọn B — @Bean method trả về một object đã được tạo

```java
@Configuration(proxyBeanMethods = false)
class ClientConfig {

    @Bean
    Client client(ClientProperties properties) {
        return new Client(
                properties.getHost(),
                properties.getPort());
    }
}
```

`Client` là class nghiệp vụ minh họa. Khi service/client cần kết nối thật, hãy tạo nó từ managed configuration bean ở `@Bean` method. Không nhất thiết phải dùng Binder thủ công trong method này.

### Lựa chọn C — Binder trực tiếp cho một snapshot cục bộ

```java
public record QueryOptions(int limit, boolean includeArchived) {
}
```

```java
QueryOptions options = Binder.get(environment)
        .bind("report.query", QueryOptions.class)
        .orElse(new QueryOptions(100, false));
```

Phù hợp khi cần nhóm giá trị cho một thao tác ngắn và không cần Spring quản lý object kết quả. Hãy kiểm tra giới hạn và nhất quán của snapshot trước khi sử dụng.

### Lựa chọn D — Binder trong công cụ chạy độc lập

Một CLI tool không khởi động Spring Boot có thể:

1. Tạo `Environment` hoặc `ConfigurationPropertySources` phù hợp.
2. Nạp dữ liệu vào nguồn đã chọn.
3. Cấu hình placeholder/convert/validation theo nhu cầu.
4. Bind sang target type.
5. Xử lý missing/invalid values.
6. Đóng resource tự tạo theo quy trình riêng.

Với cách này, **không kỳ vọng** Spring Boot tự tìm Config Data, tạo beans hoặc chạy các callback của `ApplicationContext`.

## 18. Không tự động có configuration metadata hoặc Actuator bean information

`spring-boot-configuration-processor` chạy ở compile time và phát hiện các kiểu `@ConfigurationProperties` trong mã nguồn phù hợp; nó không được kích hoạt bởi mỗi lời gọi `Binder.bind` ở runtime.

Nếu chỉ có một utility:

```java
SomeOptions opts = Binder.get(environment)
        .bind("custom", SomeOptions.class)
        .orElse(null);
```

thì lời gọi đó không tự tạo:

- `META-INF/spring-configuration-metadata.json`.
- Một mục `@ConfigurationProperties` bean trong Actuator `/actuator/configprops`.
- IDE autocomplete cho prefix `custom`.
- Một property description/schema runtime.

Nếu muốn hỗ trợ IDE cho các property được đọc thủ công, có thể tạo `META-INF/additional-spring-configuration-metadata.json` và để annotation processor hợp nhất theo quy trình build. Đây là **metadata tooling**, không phải side effect của Binder.

Nếu object không phải Spring bean, đừng kỳ vọng Actuator liệt kê nó như bean configuration properties được container theo dõi.

## 19. Đọc giá trị đơn giản: Environment hay Binder?

Khi cần một scalar và không có nested structure:

```java
String url = environment.getProperty(
        "client.base-url", "http://localhost:8080");
```

có thể là đủ. Binder hữu ích khi muốn typed conversion theo mô hình Boot:

```java
java.time.Duration timeout = Binder.get(environment)
        .bind("client.connect-timeout",
              java.time.Duration.class)
        .orElse(java.time.Duration.ofSeconds(3));
```

Với nhiều field liên quan:

```java
ClientProperties config = Binder.get(environment)
        .bindOrCreate("client", ClientProperties.class);
```

nhưng nếu object đó là cấu hình ứng dụng ổn định, bean-managed `@ConfigurationProperties` thường rõ ràng hơn.

**Tiêu chí quyết định:**

| Tình huống | Cách ưu tiên |
| --- | --- |
| Đọc một String để chẩn đoán | `Environment.getProperty(...)` |
| Đọc một scalar có type conversion | `Environment.getProperty(key, Type.class)` hoặc Binder khi cần semantics Boot |
| Bind record/Map/List cục bộ | Binder trực tiếp + xử lý kết quả |
| Cấu hình shared bởi nhiều service | Managed `@ConfigurationProperties` |
| Cần validation trong startup | Managed `@ConfigurationProperties` với validation |
| Cần thứ tự Config Data, import và profiles | SpringApplication chuẩn bị Env trước |
| Cần hot reload | Cơ chế refresh riêng, không dựa vào Binder một lần |
| Cần class có Spring dependencies | Spring-managed service/bean, không phải DTO Binder tạo độc lập |

Không lạm dụng Binder cho từng getter hoặc mỗi HTTP request nếu cấu hình thực chất là một tập giá trị tĩnh trong suốt vòng đời ứng dụng.

## 20. Các lỗi phổ biến khi gọi trực tiếp

### Lỗi 1 — `Binder.get(new StandardEnvironment())` không chạy như mong đợi

**Nguyên nhân:** `ConfigurationPropertySources` có thể chưa được attach.

**Khắc phục:** với `ConfigurableEnvironment` độc lập, gọi `ConfigurationPropertySources.attach(env)` trước; với Spring Boot environment bình thường, dùng env do container đã chuẩn bị.

### Lỗi 2 — Đọc application.yaml nhưng kết quả missing

**Nguyên nhân:** tự tạo StandardEnvironment không thực hiện Config Data loader.

**Khắc phục:** bind trên Environment do `SpringApplication` chuẩn bị hoặc nạp nguồn cụ thể bằng cơ chế phù hợp.

### Lỗi 3 — Đối tượng có @PostConstruct nhưng chưa initialized

**Nguyên nhân:** Binder tạo Java object, không gọi bean lifecycle.

**Khắc phục:** đưa bean/service vào container nếu cần lifecycle, hoặc bỏ side effect khỏi cấu hình object.

### Lỗi 4 — @Autowired field bị null

**Nguyên nhân:** object trả về không phải managed bean.

**Khắc phục:** không đưa dependencies vào configuration DTO; dùng constructor injection ở managed service.

### Lỗi 5 — @Validated không báo lỗi khi trực tiếp bind `threads=0`

**Nguyên nhân:** direct Binder không mặc nhiên có cùng validation handler.

**Khắc phục:** truyền `ValidationBindHandler` với validator phù hợp hoặc validate kết quả thủ công; nếu cần fail-fast tại startup, dùng managed properties.

### Lỗi 6 — Custom converter hoạt động ở bean nhưng không chạy ở CLI tool

**Nguyên nhân:** Binder độc lập không tự lấy mọi converter được Spring context đăng ký.

**Khắc phục:** truyền conversion service phù hợp hoặc chuyển việc bind về hạ tầng quản lý.

### Lỗi 7 — Giá trị `${...}` không được resolve

**Nguyên nhân:** tạo Binder tối giản từ sources mà không cấu hình placeholder resolver tương ứng.

**Khắc phục:** dùng `Binder.get(environment)` trên Env đã attach hoặc cấp resolver phù hợp.

### Lỗi 8 — Thay application.properties nhưng object không đổi

**Nguyên nhân:** Binder một lần trả snapshot; không có live reload.

**Khắc phục:** giải quyết nhu cầu refresh riêng và truyền lại snapshot an toàn.

### Lỗi 9 — `BindResult.get()` gây exception

**Nguyên nhân:** prefix không có property được bind.

**Khắc phục:** kiểm tra `isBound()` hoặc dùng `orElse(...)`/`orElseGet(...)`/`bindOrCreate(...)` theo hợp đồng.

### Lỗi 10 — Bind Map.class nhưng key/value không đúng type

**Nguyên nhân:** thiếu generic type metadata.

**Khắc phục:** `Bindable.mapOf(String.class, Integer.class)` hoặc `Bindable.of(ResolvableType)`.

### Lỗi 11 — Bind vào object đang dùng bởi nhiều thread

**Nguyên nhân:** mutable instance bị cập nhật giữa chừng.

**Khắc phục:** bind sang object mới, validate, rồi đổi snapshot an toàn thay vì mutate shared object mà không kiểm soát.

### Lỗi 12 — Cài đặt property typo nhưng Binder không báo

**Nguyên nhân:** default binding không phải schema validator toàn năng; unknown key có thể không được bind mà không gây exception.

**Khắc phục:** dùng strict handler/validation/test khi cần, và kiểm tra metadata/nguồn cấu hình rõ ràng.

### Lỗi 13 — Chỉ nhìn lỗi Binder mà không xét source precedence

**Nguyên nhân:** CLI/env/profile có thể ghi đè value trong file bạn đang đọc.

**Khắc phục:** xác định giá trị hiệu lực và origin; ghi log không nhạy cảm hoặc dùng công cụ chẩn đoán được bảo vệ.

## 21. Chẩn đoán trực tiếp lỗi Binder

Ví dụ helper phân loại binding:

```java
package com.example.demo;

import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public class ConfigReader {

    private final Environment environment;

    public ConfigReader(Environment environment) {
        this.environment = environment;
    }

    public int retryCount() {
        try {
            BindResult<Integer> result = Binder.get(environment)
                    .bind("app.retry-count", Integer.class);

            if (!result.isBound()) {
                return 3;
            }

            return result.get();
        } catch (BindException ex) {
            throw new IllegalStateException(
                "Invalid configuration: app.retry-count", ex);
        }
    }
}
```

Code này cố ý tách:

- **Không có kết quả binding** → default 3 theo chính sách ứng dụng.
- **Có giá trị hợp lệ** → trả về số nguyên đã convert.
- **Lỗi bind/convert** → báo lỗi với ngữ cảnh key rồi giữ nguyên exception gốc.

Một lời gọi Binder trực tiếp không nhất thiết được bọc theo chuỗi exception y hệt quá trình đăng ký `@ConfigurationProperties` bean lúc startup. Để điều tra sự cố, xem `ex.getCause()`, target type, source name/origin khi có, cùng giá trị raw không nhạy cảm.

Không log password, token hoặc secret trong thông báo exception tự tạo.

## 22. Test các ranh giới một cách minh bạch

Các bài test nên phân thành hai nhóm, thay vì kỳ vọng một unit test Binder chứng minh mọi phần của Spring Boot startup:

| Test | Khả năng xác nhận | Không tự xác nhận |
| --- | --- | --- |
| Binder + MapPropertySource + attach | Relaxed names, conversion, class binding, BindResult | Config Data/profiles/bean lifecycle |
| Binder với ValidationBindHandler | Validation của lời gọi đã cấu hình | Validation tự động của mọi lời gọi khác |
| Binder với custom ConversionService | Converter cụ thể được truyền hoạt động | Spring Boot tự tìm mọi bean converter |
| ApplicationContextRunner + EnableConfigurationProperties | Managed binding/injection/validation theo context đã cấu hình | Mọi Config Data startup behavior |
| SpringBootTest với profiles/files | Tích hợp bootstrap đầy đủ hơn, tùy test setup | Hot reload trong production |
| Manual rebind với MutablePropertySource | Lời gọi mới quan sát dữ liệu nguồn phù hợp | Tự cập nhật object cũ |
| Chạy trong production-like container | OS env và precedence thực tế | Tính bất biến qua mọi phiên triển khai |

Nếu thay đổi cách gọi Binder ở code chạy sớm, cần một bài integration test mô phỏng đúng **thời điểm** nguồn cấu hình được chuẩn bị, không chỉ một unit test đọc `Map` đơn giản.

## 23. Checklist khi quyết định dùng Binder ngoài bean lifecycle

- [ ] Tôi có thật sự cần Binder thủ công, hay một bean `@ConfigurationProperties` sẽ đơn giản hơn?
- [ ] `Environment` đã được chuẩn bị và có `ConfigurationPropertySources` phù hợp chưa?
- [ ] Nếu tạo `StandardEnvironment` độc lập, tôi đã attach đúng chưa?
- [ ] Dữ liệu cần đọc là PropertySource sẵn có hay còn phụ thuộc Config Data loader, import, profiles?
- [ ] Thời điểm gọi có chắc diễn ra sau giai đoạn nạp nguồn cần thiết?
- [ ] Tên prefix và tên property sử dụng lowercase kebab-case nhất quán chưa?
- [ ] Tôi đã xử lý `BindResult` rỗng thay vì gọi `get()` mù quáng chưa?
- [ ] Có generic type cho List/Map qua `Bindable` chưa?
- [ ] Placeholder có được resolver của Binder hiện tại xử lý không?
- [ ] Kiểu dữ liệu có cần custom converter mà Binder này chưa được cấp?
- [ ] Có cần validation? Nếu có, đã truyền `ValidationBindHandler` hoặc validate kết quả chưa?
- [ ] Những property unknown hoặc sai định dạng có được xử lý theo chính sách fail-fast đúng chưa?
- [ ] Tôi có tránh nhầm object đã bind là một Spring bean với DI/lifecycle/AOP không?
- [ ] Nếu object cần được inject, tôi đã đăng ký managed bean đúng cách chưa?
- [ ] Tôi có tránh tạo lại Binder và bind lại config tĩnh trong mọi request không?
- [ ] Nếu thay đổi cấu hình động, tôi đã thiết kế rebind/refresh và thread-safety chưa?
- [ ] Log chẩn đoán không chứa secrets và vẫn giữ nguyên exception cause?
- [ ] Unit test manual Binder và integration test managed bean được phân biệt rõ?
- [ ] Cấu hình runtime, default, validation và metadata cho IDE có được quản lý ở các tầng đúng trách nhiệm?

## 24. Kết luận và cách nhớ

`Binder` dùng trực tiếp **không hề “yếu” về khả năng type-safe binding**: nó vẫn nhận dạng tên property, chuyển đổi giá trị và có thể tạo đối tượng từ dữ liệu cấu hình. Nhưng **một lời gọi binding không bằng toàn bộ ApplicationContext lifecycle**.

Hãy nhớ sáu ranh giới:

1. **Nguồn:** Binder chỉ thấy những `ConfigurationPropertySources` đã cấp/attach; không tự tìm Config Data.
2. **Thời điểm:** Gọi trước khi Boot nạp nguồn cần thiết có thể trả về giá trị thiếu hoặc khác sau startup.
3. **Bean:** Object được Binder trả về không tự đăng ký, inject, chạy `@PostConstruct`, AOP hay shutdown callbacks.
4. **Validation:** `@Validated`/custom handlers không mặc nhiên có trong mọi direct bind; cấu hình explicit khi cần.
5. **Conversion/placeholder:** Binder độc lập không tự nhận toàn bộ hạ tầng conversion/placeholder của container.
6. **Thay đổi cấu hình:** Binding là thao tác tạo/cập nhật dữ liệu ở thời điểm gọi, không phải dịch vụ hot reload/thread-safe snapshot tự động.

Khi cấu hình là phần nền tảng của một ứng dụng Spring Boot, ưu tiên **`@ConfigurationProperties` bean-managed**. Khi cần một snapshot cục bộ, test cô lập hoặc công cụ CLI, dùng **direct Binder**, nhưng chủ động cung cấp nguồn, converter, validator, fallback và quy trình quản lý object.

## 25. Tài liệu tham khảo

- Spring Boot **3.3 API — Binder**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- Spring Boot **3.3 API — Bindable**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Bindable.html
- Spring Boot **3.3 API — BindResult**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindResult.html
- Spring Boot **3.3 API — ConfigurationPropertySources**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/source/ConfigurationPropertySources.html
- Spring Boot **3.3 API — ValidationBindHandler**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/ValidationBindHandler.html
- Spring Boot **3.3 Reference — Externalized Configuration / Type-safe Configuration Properties**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3 API — @ConfigurationProperties**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Framework — **Container Extension Points / BeanPostProcessor / Bean Lifecycle**: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html

**Thông điệp cuối:** Hãy coi `Binder.bind` là **hàm biến dữ liệu cấu hình thành đối tượng**, còn `ApplicationContext` là **hệ thống quản lý bean và lifecycle**. Chỉ khi triển khai rõ ranh giới giữa hai phần, ứng dụng mới tránh các lỗi khó nhận ra liên quan đến nguồn nạp sớm, validation thiếu, converter khác, object không được inject và cấu hình không tự làm mới.
