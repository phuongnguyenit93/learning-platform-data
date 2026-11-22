# Yêu cầu khởi tạo sớm của bộ chuyển đổi và giới hạn phụ thuộc trong Spring Boot

## 1. Vì sao một `Converter` tưởng như đơn giản lại có thể làm ứng dụng không khởi động?

Trong Spring Boot, cấu hình từ `application.yaml`, biến môi trường và đối số dòng lệnh thường được bind vào các bean `@ConfigurationProperties`. Spring Boot đã biết chuyển đổi nhiều kiểu chuẩn như `String` sang `Duration`, `DataSize`, `URI`, `Enum`, số và boolean. Khi ứng dụng định nghĩa một kiểu giá trị riêng, chúng ta có thể cung cấp một `Converter`.

Ví dụ:

```yaml
routing:
  primary: "ap-southeast-1/payments"
  timeout: 2s
```

Ở Java, nhóm cấu hình mong đợi:

```java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        NodeRef primary,
        Duration timeout
) {}
```

`NodeRef` là kiểu nghiệp vụ chứa hai phần: `region` và `service`. Một custom converter có thể đọc chuỗi `"ap-southeast-1/payments"` để tạo đối tượng `NodeRef`.

Vấn đề là: **converter phục vụ binding cấu hình có thể bị Spring Boot yêu cầu rất sớm trong vòng đời khởi động**. Nếu converter hoặc `ConversionService` của nó phụ thuộc vào những bean chưa khởi tạo xong — ví dụ `DataSource`, service nghiệp vụ, HTTP client, bean `@ConfigurationProperties` khác hoặc proxy dựa trên bean post-processor — application context có thể lỗi, tạo vòng phụ thuộc hoặc phát cảnh báo khởi tạo quá sớm.

Spring Boot khuyến nghị **giới hạn dependency của các bean phục vụ chuyển đổi cấu hình**. Đặc biệt, khi khai báo converter bằng `@Bean` có `@ConfigurationPropertiesBinding`, hãy dùng **phương thức `static`** để Spring không phải khởi tạo sớm toàn bộ instance của class `@Configuration` chứa phương thức đó.

> Nguyên tắc trung tâm: **Chuyển đổi dữ liệu cấu hình nên là phép biến đổi nhỏ, thuần, xác định, không I/O và không phụ thuộc vào ứng dụng đã khởi động hoàn chỉnh.**

Bài học này thuộc nhóm **Chuyển đổi kiểu** của chủ đề **Spring Boot Externalized Configuration**.

Sau bài này, bạn có thể:

1. Giải thích vì sao binding property xảy ra khi nhiều bean ứng dụng vẫn chưa sẵn sàng.
2. Phân biệt `ConversionService` chung, converter có `@ConfigurationPropertiesBinding` và converter dùng trong logic nghiệp vụ.
3. Hiểu ý nghĩa đặc biệt của bean tên `conversionService`.
4. Viết custom converter `String -> NodeRef` theo hướng ít dependency.
5. Đăng ký converter bằng `static @Bean` và `@ConfigurationPropertiesBinding` trong Spring Boot 3.3.
6. Giải thích các vấn đề do inject `@ConfigurationProperties`, `DataSource` hoặc service khác vào converter.
7. Kiểm tra lỗi sớm khi dữ liệu không thể chuyển đổi.
8. Dùng `ApplicationConversionService` khi thực sự cần tự cung cấp bean `conversionService`.
9. Chạy và kiểm thử một project Java 21 / Gradle / Spring Boot minh họa.
10. Thiết kế một ranh giới rõ giữa **đọc và chuyển đổi cấu hình** với **logic cần tài nguyên runtime**.

**Môi trường học:** Java 21, Spring Boot 3.3.x. Các tên miền, region và service trong ví dụ chỉ là dữ liệu giả lập; không có kết nối mạng thực sự.

## 2. Đặt converter vào đúng thời điểm trong vòng đời Spring Boot

Một cái nhìn đơn giản về ứng dụng khi khởi động:

```text
SpringApplication.run(...)
        |
        v
Chuẩn bị Environment
        |
        v
Nạp Config Data và các property sources
        |
        v
Chuẩn bị ApplicationContext và bean definitions
        |
        v
Một số bean @ConfigurationProperties cần được tạo / bind
        |
        +--> Binder lấy ConversionService / converters
        |       |
        |       +--> Có thể yêu cầu chúng rất sớm
        |
        v
Các bean ứng dụng tiếp tục được khởi tạo
        |
        v
BeanPostProcessors, các callback khởi tạo, proxy...
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
Ứng dụng sẵn sàng phục vụ công việc
```

Đây là **sơ đồ khái niệm**, không phải danh sách tất cả callback nội bộ và cũng không có nghĩa mọi bean được tạo theo một thứ tự tuyệt đối. Các bean có thể được khởi tạo khi có dependency yêu cầu, theo lazy behavior, autoconfiguration và phạm vi context. Điểm quan trọng là **chuyển đổi cấu hình nằm trên đường khởi tạo của những bean cần cấu hình**, trong lúc nhiều dependency khác chưa hoàn tất vòng đời của mình.

Ví dụ:

```java
@Service
public class ApiService {
    public ApiService(RoutingProperties properties) {
        // Service chỉ có thể tạo khi RoutingProperties đã được bind.
    }
}
```

Để tạo `ApiService`, Spring cần `RoutingProperties`. Để tạo `RoutingProperties`, Binder phải chuyển chuỗi `routing.primary` thành `NodeRef`. Vì vậy, converter liên quan phải được nhận diện và khả dụng **trước khi `ApiService` có thể hoạt động**.

Nếu converter lại cần chính `ApiService`, ta có một vòng phụ thuộc về mặt thiết kế:

```text
ApiService
   -> RoutingProperties
       -> NodeRef Converter
           -> ApiService
```

Cấu trúc đó không thể giải quyết bằng cách tăng thứ tự ưu tiên của file YAML. Đây là lỗi **phụ thuộc khi khởi tạo**, không phải lỗi location hay profile của cấu hình.

### 2.1. “Rất sớm” không đồng nghĩa “trước tất cả mọi bean”

Một vài bean hạ tầng vẫn có thể tồn tại khi converter được tạo. Tuy nhiên, không nên dựa vào việc một service cụ thể tình cờ có sẵn trên máy phát triển. Spring Boot cảnh báo rằng những dependency mà bạn yêu cầu có thể chưa được khởi tạo đầy đủ.

Hệ quả: thay vì hỏi “có thể autowire service X vào converter không?”, hãy hỏi “**vì sao parsing một giá trị cấu hình lại cần service X?**”. Thông thường, phần parsing nên tự đủ thông tin từ chuỗi input và một vài hàm Java thuần.

### 2.2. Converter chạy khi bind, không nhất thiết chỉ một lần

Bạn không nên giả định phương thức `convert()` chỉ được gọi đúng một lần trong toàn bộ vòng đời ứng dụng. Binder có thể yêu cầu conversion cho nhiều property hoặc nhiều context. Không nên đặt các side effect như ghi database, gửi request hoặc tăng biến đếm nghiệp vụ trong converter.

Với cùng input, converter nên trả cùng output hoặc ném cùng loại lỗi cú pháp, bất kể trạng thái của các bean ứng dụng.

## 3. Ba lựa chọn để chuyển đổi type khi bind externalized configuration

Spring Boot hỗ trợ nhiều cơ chế. Với bài này cần phân biệt:

| Cơ chế | Phạm vi sử dụng | Khi nào nên chọn? | Điểm cần nhớ |
| --- | --- | --- | --- |
| Converter có `@ConfigurationPropertiesBinding` | Chuyển đổi phục vụ `@ConfigurationProperties` | Một số kiểu đích riêng của application | Không cần thay thế `ConversionService` toàn cục; tạo sớm, nên ít dependency |
| Bean tên **`conversionService`** | ConversionService được hạ tầng tìm theo tên | Thực sự muốn tự cung cấp conversion service cho binding hoặc mục đích rộng hơn | Có thể bị yêu cầu rất sớm; dễ gây hệ quả ngoài dự tính |
| `CustomEditorConfigurer` và property editors | Cơ chế chuyển kiểu kiểu JavaBeans/PropertyEditor | Tích hợp legacy yêu cầu editor | Cần hiểu scope và vòng đời; không phải mặc định cho type mới |

Trong thực tế, trước khi viết custom converter hãy thử dùng converter sẵn có của Spring Boot. Những kiểu như `Duration` và `DataSize` có cách diễn đạt rất thuận tiện trong cấu hình:

```yaml
client:
  connect-timeout: 500ms
  max-buffer-size: 8MB
```

Java:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        Duration connectTimeout,
        DataSize maxBufferSize
) {}
```

Không cần tự viết một converter chỉ để xử lý `500ms` hoặc `8MB` trong một ứng dụng Spring Boot thông thường.

### 3.1. `@ConfigurationPropertiesBinding` là gì?

Annotation:

```java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
```

đánh dấu một bean là thành phần tham gia binding `@ConfigurationProperties` — thường là `Converter` hoặc `GenericConverter`. Nó là một qualifier chuyên biệt, không phải annotation biến một class bất kỳ thành configuration properties.

Ví dụ:

```java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, NodeRef> nodeRefConverter() {
    return new NodeRefConverter();
}
```

Đây là hướng lựa chọn cho bài thực hành vì chỉ cần thêm một phép chuyển đổi riêng mà không thay đổi cả conversion service mặc định.

### 3.2. Bean tên `conversionService` có ý nghĩa đặc biệt

Một bean:

```java
@Bean("conversionService")
ConversionService conversionService() {
    ...
}
```

không chỉ là một bean thông thường tình cờ có tên đẹp. Hạ tầng Spring/Spring Boot có thể yêu cầu bean với tên này cho nhu cầu chuyển đổi.

Khi bean được tìm và tạo sớm, mọi dependency phục vụ việc tạo nó cũng có thể bị kéo vào quá trình khởi tạo sớm. Nếu đó là một service dùng datasource, REST client, proxy transaction hoặc bean config khác, bạn có thể đẩy cả một nhánh ứng dụng vào thời điểm chưa thích hợp.

Nếu bạn tạo một `ConversionService` **chỉ để xử lý dữ liệu trong một service nghiệp vụ** và nó không cần cho config binding, hãy đặt **một tên khác** như `businessConversionService`. Không sử dụng tên `conversionService` một cách vô thức.

### 3.3. Tên bean và annotation quyết định đường đi

Hai ví dụ sau không tương đương:

```java
@Bean("businessConversionService")
ConversionService businessConversionService() {
    ...
}
```

và:

```java
@Bean("conversionService")
ConversionService conversionService() {
    ...
}
```

Bean đầu có thể được inject rõ ràng vào một service nghiệp vụ bằng qualifier; bean sau có thể được framework tham chiếu sớm theo convention.

Tương tự, một `Converter<String, NodeRef>` thông thường không nhất thiết tự động trở thành converter chuyên biệt cho `@ConfigurationProperties`. Khi mục đích là binding, đăng ký theo đúng cơ chế Spring Boot hỗ trợ và dùng `@ConfigurationPropertiesBinding`.

## 4. Các dependency nào gây rủi ro?

Xét converter được thiết kế không tốt:

```java
public final class BadNodeRefConverter
        implements Converter<String, NodeRef> {

    private final RoutingProperties routingProperties;
    private final ApiClient apiClient;

    public BadNodeRefConverter(
            RoutingProperties routingProperties,
            ApiClient apiClient) {
        this.routingProperties = routingProperties;
        this.apiClient = apiClient;
    }

    @Override
    public NodeRef convert(String source) {
        // Giả sử gọi apiClient để kiểm tra region tại runtime.
        ...
    }
}
```

Thiết kế này có hai vấn đề:

1. `RoutingProperties` **đang cần converter để được bind**. Converter lại đòi `RoutingProperties` trong constructor. Đó là một vòng dependency rõ rệt.
2. `ApiClient` có thể cần `RoutingProperties` để biết base URL, timeout, credential; bên trong nó có thể có proxy, interceptor hoặc tài nguyên khác chưa được hoàn tất khi converter được yêu cầu.

Các dependency dễ tạo rủi ro:

- Bean `@ConfigurationProperties` đang dùng chính converter đó.
- `DataSource`, `EntityManager`, repository hoặc transaction manager.
- Service gọi HTTP/gRPC tới hệ thống khác.
- Bean cần security context của request.
- `@Transactional`, AOP proxy, lazy initialization hoặc `BeanPostProcessor` đặc biệt.
- Bean có `@PostConstruct` thực hiện I/O nặng.
- Object phụ thuộc vào server đã mở cổng hoặc application đã nhận traffic.
- Scheduler hoặc queue consumer chỉ nên hoạt động sau startup.

Không phải mọi dependency ở danh sách đều **chắc chắn** gây lỗi. Rủi ro đến từ thứ tự, vòng phụ thuộc, side effect và việc chúng có thể chưa được khởi tạo đầy đủ. Vì vậy, chiến lược tốt hơn là **không đưa chúng vào lớp parsing cấu hình**.

### 4.1. Không kiểm tra thực thể từ xa trong converter

Một converter nhận `"ap-southeast-1/payments"` chỉ cần xác định chuỗi có hai phần đúng cú pháp. Nó không cần đăng nhập Kubernetes, hỏi database xem service tồn tại hay gọi discovery API.

Nếu nghiệp vụ thực sự yêu cầu xác minh service có tồn tại, hãy chuyển việc đó sang một **startup validator/service** chạy sau khi bean và các tài nguyên cần thiết đã sẵn sàng. Tách:

```text
Parser thuần:
"ap-southeast-1/payments" -> NodeRef("ap-southeast-1", "payments")

Nghiệp vụ:
NodeRef -> kiểm tra danh sách region / hệ thống bên ngoài
```

Hai công việc có thời điểm và quyền truy cập tài nguyên khác nhau.

### 4.2. Cẩn trọng với `Environment` làm dependency

Đọc `Environment` có thể hợp lệ ở một số thành phần hạ tầng, nhưng việc một converter vừa đọc property nguồn, vừa truy vấn thêm nhiều property khác làm tăng coupling và nguy cơ vòng tham chiếu.

Nếu cú pháp input đã chứa đầy đủ dữ liệu cần thiết, hãy để converter **nhận input như một đối số** và không tra cứu `Environment`.

## 5. Ví dụ đầy đủ: chuyển `"region/service"` thành `NodeRef`

Mục tiêu thực hành:

```properties
routing.primary=ap-southeast-1/payments
```

được bind vào:

```java
NodeRef("ap-southeast-1", "payments")
```

Custom converter sẽ chỉ dùng các thao tác Java thuần: `trim`, `split` và kiểm tra chuỗi. Nó không có constructor injection, `@Autowired`, `@Value`, `DataSource`, network call hay logger in giá trị nhạy cảm.

### 5.1. Kiểu đích `NodeRef`

Tạo `src/main/java/dev/example/earlyconversion/NodeRef.java`:

```java
package dev.example.earlyconversion;

import java.util.Objects;

public record NodeRef(String region, String service) {

    public NodeRef {
        Objects.requireNonNull(region, "region");
        Objects.requireNonNull(service, "service");

        if (region.isBlank() || service.isBlank()) {
            throw new IllegalArgumentException(
                    "region and service must not be blank");
        }
    }
}
```

Đây là một **record** biểu diễn value object, không phải Spring bean. Nó có hai component đều là `String` và một invariant đơn giản. Không có lý do để `NodeRef` biết về `ApplicationContext`.

Trong ví dụ, dấu slash `/` là ký tự phân cách do chính ứng dụng thiết kế. Nó không phải một delimiter chung của tất cả property Spring Boot.

### 5.2. `Converter<String, NodeRef>`

Tạo `src/main/java/dev/example/earlyconversion/NodeRefConverter.java`:

```java
package dev.example.earlyconversion;

import org.springframework.core.convert.converter.Converter;

public final class NodeRefConverter implements Converter<String, NodeRef> {

    @Override
    public NodeRef convert(String source) {
        if (source == null) {
            throw new IllegalArgumentException(
                    "NodeRef source must not be null");
        }

        String[] pieces = source.trim().split("/", -1);

        if (pieces.length != 2) {
            throw new IllegalArgumentException(
                    "NodeRef must have the format region/service");
        }

        String region = pieces[0].trim();
        String service = pieces[1].trim();

        return new NodeRef(region, service);
    }
}
```

Với những input:

| Input | Kết quả |
| --- | --- |
| `ap-southeast-1/payments` | `NodeRef("ap-southeast-1","payments")` |
| ` eu-west-1 / billing ` | Hai thành phần được trim |
| `payments` | Lỗi định dạng, thiếu dấu phân cách |
| `a/b/c` | Lỗi vì có nhiều hơn hai phần |
| ` / payments` | Lỗi vì region trống |
| `ap-southeast-1/ ` | Lỗi vì service trống |

Ưu điểm của converter này:

- Cùng một input cho cùng kết quả.
- Không có side effect.
- Không tạo thread hoặc socket.
- Không kéo dependency nghiệp vụ vào startup.
- Dễ unit test bằng `new NodeRefConverter()` mà không cần Spring.
- Thông báo lỗi tập trung vào **cú pháp**, không cố xác minh dữ liệu ở hệ thống bên ngoài.

Đối với giá trị thật có thể chứa secret, không nên đưa nguyên input vào exception message hay log. Ở ví dụ chỉ mô tả shape `region/service`.

## 6. Đăng ký converter với `@ConfigurationPropertiesBinding`

Tạo `src/main/java/dev/example/earlyconversion/ConversionConfiguration.java`:

```java
package dev.example.earlyconversion;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class ConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, NodeRef> nodeRefConverter() {
        return new NodeRefConverter();
    }
}
```

Đây là phần kỹ thuật quan trọng nhất của bài.

**Vì sao `@Bean` có `static`?**

Một phương thức `static` có thể được Spring gọi để tạo bean mà **không phải tạo trước một instance của `ConversionConfiguration`**. Điều này giảm khả năng class cấu hình hoặc dependency của nó bị khởi tạo sớm chỉ để cung cấp converter.

Spring Boot khuyến nghị `@Bean` method có `@ConfigurationPropertiesBinding` nên được khai báo `static` nhằm tránh cảnh báo kiểu:

```text
Bean '...' is not eligible for getting processed
by all BeanPostProcessors
```

Cảnh báo dạng này thường liên quan một bean đã bị tạo quá sớm để đi qua toàn bộ các bean post-processors. Nó không tự chứng minh converter bị sai logic, nhưng là dấu hiệu cần xem lại **vòng đời khởi tạo** và dependency.

**`static @Bean` KHÔNG đồng nghĩa với `static field @Value`.**

- `static @Bean` method: một factory method có thể tạo **bean instance** mà không cần instance của class `@Configuration`.
- `static field @Value`: một trường thuộc class Java, không phải dependency injection chuẩn vào instance bean.

Trong bài này, Spring vẫn quản lý đối tượng `new NodeRefConverter()` như một bean bình thường. Chỉ **factory method** là static, không phải kết quả conversion nằm trong một biến toàn cục.

### 6.1. Vì sao không inject service vào `@Bean` method?

Tránh:

```java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, NodeRef> nodeRefConverter(
        ApiClient apiClient) {
    return new ClientAwareNodeRefConverter(apiClient);
}
```

Dù method là `static`, Spring vẫn phải giải quyết tham số `ApiClient` trước khi tạo converter. Như vậy, tính `static` không xóa được rủi ro phụ thuộc sớm. **Giải pháp chính là giảm dependency, không chỉ thêm một từ khóa.**

### 6.2. Có thể dùng `@Component` trên converter không?

Có thể xây một bean converter theo cơ chế component scanning và đánh dấu qualifier thích hợp trong những trường hợp được framework hỗ trợ. Nhưng khi mục đích là **property binding và khởi tạo sớm**, tài liệu Spring Boot khuyên `static @Bean` có `@ConfigurationPropertiesBinding` để giảm rủi ro khởi tạo class cấu hình quá sớm.

Không cần đăng ký **cùng một converter** hai lần bằng cả `@Component` và `@Bean`; điều đó khiến ứng dụng khó kiểm soát bean selection và có thể tạo sự nhập nhằng.

## 7. Cấu hình record được bind

Tạo `src/main/java/dev/example/earlyconversion/RoutingProperties.java`:

```java
package dev.example.earlyconversion;

import java.time.Duration;

import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotNull NodeRef primary,
        @NotNull Duration timeout,
        boolean enabled
) {}
```

Khi Spring Boot bind `routing.primary`:

```text
Externalized property: "ap-southeast-1/payments"
                         |
                         v
       @ConfigurationProperties Binder
                         |
                         v
       Converter<String, NodeRef>
                         |
                         v
       NodeRef("ap-southeast-1", "payments")
                         |
                         v
             RoutingProperties.primary()
```

`Duration` đã được Spring Boot hỗ trợ, vì vậy không cần viết thêm `Converter<String, Duration>`. `@NotNull` giúp phát hiện trường hợp `primary` hoặc `timeout` không có, khi validation đã được cấu hình.

### 7.1. Đăng ký `@ConfigurationProperties` theo đúng cơ chế

Đặt trên main class:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class EarlyConversionApplication {
    ...
}
```

`@ConfigurationPropertiesScan` cho Spring Boot đăng ký và bind `RoutingProperties`. Không cần và không nên gắn `@Component` lên một record cấu hình constructor-bound chỉ để nó được phát hiện.

Với Spring Boot 3.3, constructor binding của record thường được suy ra; không cần thêm class-level `@ConstructorBinding` từ các ví dụ cũ.

## 8. Dự án Gradle chạy được

Cấu trúc tối thiểu:

```text
early-conversion-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/earlyconversion/
    │   │   ├── EarlyConversionApplication.java
    │   │   ├── ConversionConfiguration.java
    │   │   ├── NodeRef.java
    │   │   ├── NodeRefConverter.java
    │   │   └── RoutingProperties.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-dev.yaml
    └── test/
        └── java/dev/example/earlyconversion/
            ├── NodeRefConverterTest.java
            └── RoutingBindingTest.java
```

Khởi tạo project bằng Spring Initializr với Java 21, Gradle và Spring Boot 3.3.x. Wrapper `gradlew` và `gradlew.bat` nên lấy từ project được tạo, không cần tự viết hai file này.

### 8.1. `settings.gradle`

```groovy
rootProject.name = 'early-conversion-lab'
```

### 8.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu dự án đã có version catalog hoặc convention plugins, nên tuân theo hệ thống quản lý build của dự án. Ví dụ trên dành cho một project độc lập, không có web dependency.

### 8.3. `application.yaml`

```yaml
spring:
  main:
    web-application-type: none

routing:
  primary: "ap-southeast-1/payments"
  timeout: 2s
  enabled: true
```

`routing.primary` là **scalar string**. Converter chuyển nó thành record `NodeRef`; `routing.timeout` được chuyển bằng converter có sẵn của Spring Boot thành `Duration`.

Đặt URL hay credential thật vào file để thử nghiệm converter là không cần thiết. Dùng những nhãn `region/service` không nhạy cảm giúp quan sát mà không có nguy cơ tiết lộ thông tin qua console.

### 8.4. Main class và `ApplicationRunner`

`src/main/java/dev/example/earlyconversion/EarlyConversionApplication.java`:

```java
package dev.example.earlyconversion;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class EarlyConversionApplication {

    public static void main(String[] args) {
        SpringApplication.run(EarlyConversionApplication.class, args);
    }

    @Bean
    ApplicationRunner printConfiguration(RoutingProperties properties) {
        return args -> {
            System.out.println("=== EARLY CONVERSION LAB ===");
            System.out.println("primary.region = "
                    + properties.primary().region());
            System.out.println("primary.service = "
                    + properties.primary().service());
            System.out.println("timeout = "
                    + properties.timeout());
            System.out.println("enabled = "
                    + properties.enabled());
        };
    }
}
```

Ứng dụng không mở HTTP server. Nó chỉ in các thuộc tính giả lập sau khi `RoutingProperties` đã được bind và context đã qua quá trình khởi tạo cần thiết.

### 8.5. Dòng thời gian của project

```text
SpringApplication.run
       |
       v
Spring Boot đọc routing.primary từ Environment
       |
       v
Binder cần tạo RoutingProperties
       |
       v
Converter bean được lấy để chuyển String -> NodeRef
       |
       +--> static @Bean tạo NodeRefConverter
       |         |
       |         +--> không yêu cầu ApiClient / DataSource
       |
       v
NodeRef được tạo qua convert(...)
       |
       v
RoutingProperties được tạo và kiểm tra
       |
       v
ApplicationRunner nhận bean RoutingProperties
       |
       v
In thông tin region/service và timeout
```

Điểm thiết kế là converter **đã có thể hoạt động độc lập** trước khi các service cần `RoutingProperties` được khởi tạo.

## 9. Chạy lần 1: cấu hình nền

Trên macOS/Linux:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Những dòng kết quả chính:

```text
=== EARLY CONVERSION LAB ===
primary.region = ap-southeast-1
primary.service = payments
timeout = PT2S
enabled = true
```

`Duration.toString()` hiển thị hai giây thành `PT2S`. Nếu bạn thấy thông báo Spring Boot khác về việc khởi động, hãy tìm các dòng có nhãn `EARLY CONVERSION LAB` để đối chiếu.

**Mục tiêu quan sát:** converter hoạt động mà không cần một service nghiệp vụ nào, và Bean `RoutingProperties` đã được tạo hoàn chỉnh trước khi `ApplicationRunner` đọc dữ liệu.

### 9.1. Chạy trực tiếp JAR

```bash
./gradlew bootJar
java -jar build/libs/early-conversion-lab-0.0.1-SNAPSHOT.jar
```

PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build\libs\early-conversion-lab-0.0.1-SNAPSHOT.jar
```

Nếu repository có quy tắc đặt tên artifact riêng, thay đường dẫn bằng file JAR thực tế được tạo trong `build/libs`.

## 10. Chạy lần 2: property source ưu tiên hơn

Không cần sửa Java để thay region và service.

macOS/Linux:

```bash
./gradlew bootRun --args='--routing.primary=eu-west-1/billing'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--routing.primary=eu-west-1/billing"
```

Kỳ vọng:

```text
primary.region = eu-west-1
primary.service = billing
timeout = PT2S
enabled = true
```

Đối số CLI có thể ghi đè giá trị từ `application.yaml`, nhưng converter vẫn là cùng một đối tượng tham gia binding. Điều này minh họa separation:

```text
Nguồn nào cung cấp giá trị hiệu lực? -> Environment + precedence

Chuỗi biến thành NodeRef thế nào?    -> Converter

Bean nhận giá trị đã chuyển đổi?      -> ConfigurationProperties Binder
```

Không đưa code kiểm tra profile, đọc biến môi trường trực tiếp hoặc truy vấn file location vào `NodeRefConverter`. Binder đã chọn property theo các quy tắc external configuration.

### 10.1. Dùng biến môi trường

Bash:

```bash
ROUTING_PRIMARY=ap-northeast-1/reporting ./gradlew bootRun
```

PowerShell:

```powershell
$env:ROUTING_PRIMARY = 'ap-northeast-1/reporting'
.\gradlew.bat bootRun
Remove-Item Env:ROUTING_PRIMARY
```

Kỳ vọng `NodeRef.region()` là `ap-northeast-1` và service là `reporting`, miễn không có nguồn ưu tiên cao hơn cùng khóa.

`NodeRefConverter` không cần biết chuỗi đến từ CLI, YAML hay environment. Đó chính là đặc điểm tốt của một custom converter dùng cho type-safe configuration binding.

## 11. Chạy lần 3: cấu hình theo profile

Tạo `src/main/resources/application-dev.yaml`:

```yaml
routing:
  primary: "local/mock-service"
  timeout: 500ms
```

Chạy:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Kỳ vọng:

```text
primary.region = local
primary.service = mock-service
timeout = PT0.5S
enabled = true
```

`routing.enabled` không có trong file dev nên có thể được lấy từ file nền. Cả hai file đều được xử lý theo cơ chế Config Data của Spring Boot. Converter không tham gia việc tìm file profile — nó chỉ nhận **giá trị property hiệu lực** và chuyển sang kiểu Java cần thiết.

Khi đổi profile, đừng thêm điều kiện kiểu:

```java
if (profile.equals("dev")) { ... }
```

vào converter. Một converter chứa logic lựa chọn profile sẽ trở nên khó tái sử dụng và phụ thuộc vào nguồn cấu hình mà Binder đã chịu trách nhiệm xử lý.

## 12. Chạy lần 4: dữ liệu không hợp lệ phải lỗi sớm

Thử:

```bash
./gradlew bootRun --args='--routing.primary=invalid'
```

Lúc này `NodeRefConverter` không thể tách thành `region/service`. Nó ném `IllegalArgumentException`, được Spring Boot phản ánh trong quá trình binding và ứng dụng có thể **không khởi động**.

Đây là hành vi tốt khi cấu hình là điều kiện bắt buộc cho ứng dụng chạy đúng.

Một số input lỗi khác:

```text
routing.primary=
routing.primary=/payments
routing.primary=region/
routing.primary=region/payments/extra
```

Trong lab, ứng dụng không kết nối mạng; lỗi phải đến từ **cú pháp** hoặc **ràng buộc cấu hình**. Đừng che lỗi bằng một default giả và cho ứng dụng chạy khi giá trị bắt buộc không hợp lệ.

### 12.1. Thông điệp lỗi nên chứa những gì?

Tốt:

```text
NodeRef must have the format region/service
```

Không nên:

```text
Could not parse secret: <toàn bộ giá trị nhạy cảm>
```

Khi áp dụng converter cho token hoặc cấu trúc có bí mật, thông điệp lỗi phải tránh ghi nguyên input. Với giá trị không nhạy cảm, người vận hành có thể nhìn vào tên property và path của binding failure để tìm nguyên nhân.

### 12.2. Validation khác conversion

Một chuỗi sai cú pháp gây lỗi **conversion**. Một `NodeRef` đã chuyển đổi thành công nhưng vi phạm ràng buộc nghiệp vụ có thể cần **validation** hoặc service kiểm tra sau binding.

Trong lab:

- `region/payments` -> cú pháp có thể phân tích.
- `region/` -> lỗi converter do thiếu service.
- `region/payments` nhưng service không tồn tại trên cluster -> không phải lỗi parsing; đừng gọi cluster từ converter.

Spring Boot Binder và Jakarta Validation giải quyết các lớp vấn đề khác nhau. Lỗi cú pháp nên xảy ra trong converter; ràng buộc đối tượng cấu hình nên dùng validation; kiểm tra bên ngoài nên đưa sang service khi ứng dụng đã sẵn sàng.

## 13. Unit test Converter mà không cần Spring

Một dấu hiệu thiết kế converter tốt: có thể unit test bằng Java thuần mà không phải khởi tạo `ApplicationContext`.

Tạo `src/test/java/dev/example/earlyconversion/NodeRefConverterTest.java`:

```java
package dev.example.earlyconversion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class NodeRefConverterTest {

    private final NodeRefConverter converter = new NodeRefConverter();

    @Test
    void parsesValidValue() {
        NodeRef parsed = converter.convert("eu-west-1/billing");

        assertEquals("eu-west-1", parsed.region());
        assertEquals("billing", parsed.service());
    }

    @Test
    void trimsWhitespace() {
        NodeRef parsed = converter.convert(
                " eu-west-1 / billing ");

        assertEquals("eu-west-1", parsed.region());
        assertEquals("billing", parsed.service());
    }

    @Test
    void rejectsMissingSeparator() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("billing"));
    }

    @Test
    void rejectsEmptyComponent() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("eu-west-1/"));
    }

    @Test
    void rejectsTooManySegments() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("a/b/c"));
    }
}
```

Không có mock database, Kubernetes, network hoặc Spring container. Đó là lợi ích trực tiếp của việc giới hạn dependency trong custom converter.

Một converter nhận thêm `ApiClient` trong constructor sẽ khiến unit test phải mock client, xử lý thứ tự gọi và exception ngoài ý muốn; điều đó là một tín hiệu parser đang gánh việc không phù hợp.

## 14. Integration test: chứng minh `@ConfigurationPropertiesBinding` được sử dụng

Tạo `src/test/java/dev/example/earlyconversion/RoutingBindingTest.java`:

```java
package dev.example.earlyconversion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "routing.primary=eu-west-1/invoices",
        "routing.timeout=750ms",
        "routing.enabled=true"
})
class RoutingBindingTest {

    @Autowired
    RoutingProperties routing;

    @Test
    void bindsScalarToCustomRecordUsingConverter() {
        assertEquals("eu-west-1", routing.primary().region());
        assertEquals("invoices", routing.primary().service());
        assertEquals(Duration.ofMillis(750), routing.timeout());
        assertTrue(routing.enabled());
    }
}
```

Chạy:

macOS/Linux:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Test này làm hai việc:

1. Kiểm tra Spring Boot bind một scalar string vào `NodeRef` nhờ converter đã đăng ký.
2. Kiểm tra các type sẵn có như `Duration` vẫn hoạt động cùng converter riêng.

Nếu unit test converter đỗ nhưng integration test binding lỗi, xem lại bean registration (`@ConfigurationPropertiesBinding`), `@ConfigurationPropertiesScan`, package scan, tên property và những bean trùng lặp.

### 14.1. Nên kiểm tra thêm những gì?

Với một custom converter quan trọng, có thể bổ sung:

- Tên property canonical khớp từ YAML, CLI và environment.
- Một giá trị sai cú pháp làm quá trình binding thất bại.
- Một giá trị thiếu gây validation error nếu cấu hình bắt buộc.
- Không phát sinh network call hoặc side effect trong `convert()`.
- Converter không có dependency vòng với bean đang được bind.
- Một ApplicationContext khác cũng tạo được converter và nhận đúng dữ liệu của context riêng.
- Không log input nhạy cảm.
- Một converter khi được tạo như bean có thể được dùng cùng những converter mặc định của Spring Boot.

Bài này không cần gọi database thật để chứng minh những điều trên.

## 15. Tại sao không nên thay `conversionService` nếu chỉ cần một converter?

Một nhóm phát triển có thể thấy type `NodeRef` chưa được Spring Boot hiểu và thử tạo:

```java
@Bean("conversionService")
ConversionService customConversionService() {
    ...
}
```

Cách đó có thể hoạt động nếu được thiết kế đúng, nhưng thường là **một thay đổi rộng hơn mức cần thiết**. Bạn đang cung cấp một service mang tên đặc biệt cho hạ tầng. Nó có thể được gọi sớm và ảnh hưởng đến những đường conversion khác phụ thuộc service đó.

Trong khi đó:

```java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, NodeRef> nodeRefConverter() {
    return new NodeRefConverter();
}
```

trực tiếp mô tả đúng nhu cầu: **chỉ bổ sung khả năng bind một kiểu cấu hình**.

### 15.1. Ví dụ bean `conversionService` chỉ dùng khi thật sự cần

Trong một ứng dụng muốn tùy chỉnh conversion service theo nghĩa rộng, có thể khai báo một bean theo tên chuẩn. **Đây là phương án thay thế, không triển khai đồng thời với cấu hình đăng ký converter ở mục 6 trong bài lab.**

```java
package dev.example.earlyconversion;

import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;

@Configuration(proxyBeanMethods = false)
public class GlobalConversionConfiguration {

    @Bean(name = "conversionService")
    public static ConversionService conversionService() {
        ApplicationConversionService service =
                new ApplicationConversionService();

        service.addConverter(new NodeRefConverter());

        return service;
    }
}
```

Giải thích:

- Tên bean chính xác là `conversionService`.
- Factory method là `static` và **không** có tham số dependency.
- `ApplicationConversionService` cung cấp tập chuyển đổi/formatting thường dùng của Spring Boot, giúp tránh việc vô tình bỏ đi nhiều converter sẵn có khi thay bằng một service chỉ chứa converter của ứng dụng.
- `NodeRefConverter` được thêm vào service đó.
- Không có `DataSource`, `RestClient`, repository hoặc bean config khác trong việc xây dựng service.
- Cách này có tác động rộng hơn; chỉ sử dụng nếu bạn cần kiểm soát conversion service thật sự.

Không chỉ sao chép ví dụ này vào một project bất kỳ đã có bean tên `conversionService` hoặc có cấu hình MVC/security/integration tùy biến mà không kiểm tra phạm vi ảnh hưởng. Khi dùng kiểu triển khai rộng này, integration test nên bao gồm cả các conversion chuẩn như `Duration`.

**Trong bài lab chính, hãy giữ cách `@ConfigurationPropertiesBinding` ở mục 6 và không thêm `GlobalConversionConfiguration`.** Hai ví dụ thể hiện hai lựa chọn kiến trúc khác nhau.

### 15.2. Vì sao không thay thế bằng `DefaultConversionService` trống?

Nếu bạn tạo một conversion service rất tối giản rồi đặt tên `conversionService`, một số conversion mặc định do Spring Boot cung cấp có thể không còn được thiết lập như mong muốn. Ví dụ `Duration` với suffix `ms`, `s` và `DataSize` với suffix `MB` là các nhu cầu thường gặp của Boot.

Khi tự cung cấp conversion service, hãy bắt đầu từ hạ tầng conversion phù hợp với Spring Boot, bổ sung converter cần thiết và kiểm thử mọi kiểu cấu hình quan trọng. Đừng thay toàn bộ chỉ vì một custom value object.

### 15.3. Đổi tên conversion service dành cho nghiệp vụ

Nếu conversion service chỉ phục vụ một service sau khi ứng dụng đã khởi động:

```java
@Bean("businessConversionService")
ConversionService businessConversionService(...) {
    ...
}
```

thì tên đó nói rõ nó **không cố trở thành bean hạ tầng mang tên đặc biệt `conversionService`**.

Trong service sử dụng, có thể inject với qualifier phù hợp. Điều này giảm rủi ro Spring Boot cố sử dụng bean conversion nghiệp vụ cho quá trình binding sớm.

Không nên coi đổi tên là giải pháp duy nhất nếu service vẫn thiết kế sai dependency; đó chỉ là cách tách đúng phạm vi trách nhiệm.

## 16. Trường hợp vòng phụ thuộc: mô hình sai và mô hình đúng

### 16.1. Mô hình sai

```text
routing.primary
       |
       v
RoutingProperties
       |
       v
Binder cần NodeRefConverter
       |
       v
NodeRefConverter cần RoutingService
       |
       v
RoutingService cần RoutingProperties
       |
       +-----------> quay lại
```

Trong trường hợp này, không có thứ tự tạo bean hợp lệ để đáp ứng đồng thời tất cả dependency. Có thể xuất hiện thông báo circular dependency hoặc lỗi bean initialization theo cấu hình thực tế.

Đừng “sửa” bằng cách dùng global static field, tự gọi `ApplicationContext.getBean()`, bật circular references hoặc khởi tạo thủ công một service không đủ dependency. Những cách đó thường che thiết kế không đúng, khó ổn định trong production và test.

### 16.2. Mô hình đúng

```text
routing.primary (String)
       |
       v
NodeRefConverter (thuần)
       |
       v
NodeRef
       |
       v
RoutingProperties
       |
       v
RoutingService
       |
       +--> có thể dùng Repository / HttpClient sau binding
```

Đây là một đồ thị một chiều dễ hiểu. Converter không biết về service; service biết về typed config.

### 16.3. Nếu cần registry để kiểm tra tên region

Có thể đưa kiểm tra vào một bean sau binding:

```java
@Service
public class RoutingService {

    private final RoutingProperties properties;
    private final RegionRegistry regionRegistry;

    public RoutingService(
            RoutingProperties properties,
            RegionRegistry regionRegistry) {
        this.properties = properties;
        this.regionRegistry = regionRegistry;
    }

    public boolean isConfiguredRegionKnown() {
        return regionRegistry.contains(
                properties.primary().region());
    }
}
```

`RegionRegistry` có thể là một component cần tài nguyên runtime; nó chỉ tham gia khi service thực hiện kiểm tra nghiệp vụ. `NodeRefConverter` tiếp tục chỉ tách chuỗi. Nếu chính sách yêu cầu fail-fast khi region không hợp lệ, đặt một startup check có chủ đích sau khi những dependency cần thiết đã sẵn sàng và đảm bảo ứng dụng không nhận traffic trước khi check thành công.

Không nên tự động gửi network request mỗi khi Spring gọi Binder.

## 17. `BeanPostProcessor` và cảnh báo “not eligible”

Spring dùng bean post-processors để thực hiện nhiều chức năng quanh việc khởi tạo bean, trong đó có các cơ chế xử lý annotation, proxy hoặc logic thư viện. Khi một bean bị tạo **trước khi tất cả processors được đăng ký**, Spring có thể cảnh báo rằng bean đó không đủ điều kiện được xử lý bởi tất cả processors.

Ví dụ thông báo có dạng:

```text
Bean 'someBean' is not eligible for getting
processed by all BeanPostProcessors
```

Một nguyên nhân có thể là factory method khai báo converter cần tạo instance của `@Configuration` class rất sớm. Nếu class cấu hình này lại có những dependency khác, việc khởi tạo sớm có thể lan sang nhiều bean hơn.

Dùng:

```java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, NodeRef> nodeRefConverter() {
    return new NodeRefConverter();
}
```

cho phép Spring tạo converter mà không phải tạo **instance cấu hình** chỉ để gọi phương thức `@Bean`. Đây là lý do hướng dẫn chính thức nhấn mạnh `static` cho factory method khi dùng `@ConfigurationPropertiesBinding`.

Nhưng lưu ý:

- Phương thức `static` **không làm mọi dependency trở nên an toàn**.
- Nếu method nhận tham số service, service vẫn cần được khởi tạo.
- Nếu `new NodeRefConverter()` mở network connection trong constructor, vẫn có side effect sớm.
- Nếu static initializer của một class khác thực hiện I/O, việc class đó được khởi tạo sớm vẫn có thể gây lỗi.
- Không cần xử lý mọi warning bằng cách thêm `@DependsOn` hoặc chỉnh bean order tùy tiện; hãy tìm **dependency nào bị kéo vào quá sớm**.

Thông điệp thực hành: `static @Bean` là một kỹ thuật giảm khởi tạo sớm **không cần thiết**, còn **converter không có dependency ứng dụng** mới là thiết kế lâu dài.

## 18. `@Value`, `Environment` và `@ConfigurationProperties` không giống nhau

Cần phân biệt đường conversion:

| Cách truy cập | Cơ chế chính | Lưu ý về custom converter |
| --- | --- | --- |
| `Environment.getProperty("routing.primary")` | Tra property theo tên | Khi trả `String`, không cần `NodeRef` converter |
| `@Value("${routing.primary}") String` | Placeholder và injection vào chuỗi | Có thể nhận scalar gốc |
| `@Value("${routing.primary}") NodeRef` | Placeholder và conversion của bean factory | Không mặc định coi converter chỉ có `@ConfigurationPropertiesBinding` áp dụng cho mọi điểm `@Value` |
| `@ConfigurationProperties(prefix="routing")` | Binder có kiểu | Đúng nơi custom converter `@ConfigurationPropertiesBinding` được thiết kế phục vụ |

Một sự nhầm lẫn phổ biến là nghĩ rằng đánh dấu `@ConfigurationPropertiesBinding` làm converter được đăng ký toàn cục cho mọi API Spring. Nó là một cơ chế **chuyên biệt cho configuration property binding**.

Nếu một service muốn dùng `NodeRef`, cách rõ ràng là:

```java
@Service
public class PaymentRouteService {

    private final RoutingProperties properties;

    public PaymentRouteService(RoutingProperties properties) {
        this.properties = properties;
    }

    public NodeRef primaryRoute() {
        return properties.primary();
    }
}
```

Service không cần dùng `@Value` rồi tự cố gắng conversion lại. Tránh tạo ra hai đường parsing khác nhau chỉ vì một vài chỗ code quen dùng annotation khác.

### 18.1. Có nhất thiết cung cấp converter cho mọi record không?

Không. Một nested record được bind từ các property phân cấp như:

```yaml
routing:
  primary:
    region: ap-southeast-1
    service: payments
```

có thể dùng constructor binding theo cấu trúc record mà **không cần custom converter `"region/service"`**, miễn root và nested types được đăng ký/bind phù hợp.

Custom converter chỉ cần thiết khi bạn cố ý định nghĩa **một scalar format đặc thù**:

```yaml
routing:
  primary: "ap-southeast-1/payments"
```

Trước khi viết converter, hãy cân nhắc liệu schema cấu hình có thể biểu diễn rõ ràng hơn bằng YAML nested object hay không. Với một hoặc hai trường, scalar format ngắn; với object nhiều trường, cấu trúc nested dễ quản lý và validation hơn.

## 19. Tách parsing thuần khỏi validation và side effect

Một thiết kế cân bằng thường có ba lớp:

```text
Lớp 1: Parser / Converter
  Chuỗi nguồn -> kiểu Java
  Không I/O, không state ứng dụng

Lớp 2: Configuration properties
  NodeRef + Duration + flags
  Bean Validation / invariant tại thời điểm binding

Lớp 3: Service khởi động / nghiệp vụ
  Kiểm tra service tồn tại, mở connection,
  tương tác với registry, lưu cache, phục vụ request
```

### 19.1. Converter nên làm gì?

- Trim, normalize theo contract đã công bố.
- Tách một chuỗi thành các thành phần xác định.
- Kiểm tra format bắt buộc.
- Convert scalar sang value object.
- Ném exception rõ nếu input không hợp lệ.
- Sử dụng các class Java cơ bản, không cần Spring container để test.

### 19.2. Converter không nên làm gì?

- Gọi database để hỏi ID tồn tại.
- Gửi HTTP request để xác thực endpoint.
- Đọc secret từ kho ngoài chỉ để parse một giá trị.
- Khởi tạo cache hoặc mở thread.
- Lấy một bean đang được bind từ `ApplicationContext`.
- Tạo scheduler hoặc đăng ký consumer.
- Ghi dữ liệu hoặc kích hoạt sự kiện nghiệp vụ.
- Phụ thuộc vào request context hoặc user session.
- Ghi raw input nhạy cảm vào logger.
- Giả định các bean proxy đã hoàn chỉnh.

Một phép chuyển đổi cần network để chạy không còn chỉ là chuyển đổi kiểu cấu hình. Hãy chuyển nghiệp vụ đó sang thành phần có lifecycle phù hợp.

### 19.3. Startup check có hợp đồng rõ

Nếu ứng dụng buộc phải kiểm tra một endpoint trước khi sẵn sàng nhận traffic, có thể chạy check sau khi Spring đã tạo các dependency cần thiết. Chọn mốc lifecycle phù hợp với framework và loại ứng dụng: một runner, một initializer ở tầng service, hoặc health/readiness mechanism có kiểm soát.

Mốc nào là đúng phụ thuộc yêu cầu: fail-fast, retry, backoff, readiness, shutdown, startup probe. Nhưng đây là bài toán **quản lý khởi động dịch vụ**, không phải parsing scalar property. Không nhét toàn bộ quy tắc ấy vào `Converter`.

## 20. Khi nào cần `CustomEditorConfigurer`?

Spring Framework có cơ chế `PropertyEditor` và `CustomEditorConfigurer` cho một số nhu cầu chuyển kiểu, đặc biệt với mã legacy hoặc framework component dùng JavaBeans property editors.

Về nguyên tắc, bạn có thể thêm custom editor vào hệ thống bean factory. Tuy nhiên, cần phân biệt rằng:

- Converter Spring `Converter<S,T>` có giao diện dễ test và thân thiện với mô hình conversion service.
- Property editor thường liên quan tới API JavaBeans, state của editor instance và phạm vi đăng ký.
- Boot's `@ConfigurationProperties` Binder đã có cơ chế converter chuyên biệt.
- Khi sửa legacy, phải biết chính xác component nào đang dùng editor và cơ chế lifecycle nào yêu cầu nó.

Với một type mới trong Spring Boot application thông thường, một custom `Converter<String, T>` có `@ConfigurationPropertiesBinding` thường là lựa chọn dễ bảo trì hơn việc mở rộng trực tiếp JavaBeans editor infrastructure.

Đừng kết luận rằng ba phương án trong tài liệu Spring Boot là **ba bước buộc phải làm cùng lúc**. Chúng là các lựa chọn tùy mục đích.

## 21. Những lỗi thường gặp và cách chẩn đoán

### 21.1. Lỗi vì custom `conversionService` phụ thuộc vào bean config

**Triệu chứng:** startup báo circular dependency hoặc bean đang được tạo mà lại được yêu cầu lần nữa.

**Nguyên nhân có thể có:** `conversionService` hoặc converter nhận một bean `@ConfigurationProperties` mà binder đang cần chính conversion service đó để tạo.

**Cách sửa:** bỏ dependency ngược; viết converter nhận raw input và trả value object. Đưa logic nghiệp vụ sử dụng config sang service sau binding.

### 21.2. Cảnh báo bean không đi qua toàn bộ processors

**Triệu chứng:** log có `not eligible for getting processed by all BeanPostProcessors`.

**Nguyên nhân có thể có:** phương thức `@Bean` cung cấp converter không static, dẫn đến việc class `@Configuration` hoặc các bean phụ bị khởi tạo sớm.

**Cách sửa:** dùng `static @Bean` cho `@ConfigurationPropertiesBinding` theo hướng dẫn của Boot. Đồng thời kiểm tra constructor, tham số factory method và side effect.

### 21.3. Converter chạy unit test nhưng binding không áp dụng

**Triệu chứng:** `new NodeRefConverter().convert(...)` đúng, nhưng `RoutingProperties.primary` không bind.

**Nguyên nhân cần kiểm tra:**

- Converter có thực sự được đăng ký thành bean?
- Có `@ConfigurationPropertiesBinding` đúng ở factory method?
- `ConversionConfiguration` nằm trong package scan của ứng dụng?
- `RoutingProperties` đã được đăng ký bằng `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`?
- YAML có `routing.primary` chứ không phải tên khác?
- Target type có đúng `NodeRef` và nguồn có dạng scalar string?
- Có converter khác cùng cặp source/target gây nhập nhằng không?

### 21.4. Thêm converter rồi mất conversion cho `Duration`

**Triệu chứng:** trước đây `client.timeout=2s` bind được, sau khi thêm bean `conversionService` tự chế thì conversion khác đi hoặc lỗi.

**Nguyên nhân có thể có:** một conversion service tự cung cấp đã thay đường chuyển đổi mặc định và không giữ đầy đủ converter của Boot.

**Cách sửa:** nếu chỉ cần một kiểu riêng, dùng `@ConfigurationPropertiesBinding`. Nếu thực sự cần service toàn cục, cân nhắc `ApplicationConversionService` và kiểm thử lại toàn bộ kiểu cấu hình quan trọng.

### 21.5. Thêm `@Lazy` vào converter để tránh tạo sớm

**Triệu chứng:** converter có `@Lazy` nhưng lúc bind vẫn bị tạo trước những service khác.

**Giải thích:** khi Binder cần converter để tạo config bean, converter phải có mặt. `@Lazy` không xóa dependency thực sự. Nếu cần giá trị ngay khi bind, không thể trì hoãn converter vô thời hạn.

**Cách sửa:** giảm dependency và tách parsing khỏi side effect.

### 21.6. `@Value` không nhận custom type dù `@ConfigurationProperties` nhận được

**Giải thích:** converter có `@ConfigurationPropertiesBinding` phục vụ Binder; đường conversion của `@Value` không nhất thiết giống hệt. Không mặc định qualifier này đăng ký converter cho mọi conversion service.

**Cách sửa:** inject bean `RoutingProperties` vào service hoặc đăng ký converter vào conversion service đúng với nhu cầu khác và kiểm tra tác động toàn ứng dụng.

### 21.7. `DataSource` hoặc HTTP client không được khởi tạo khi converter yêu cầu

**Giải thích:** converter đang kéo một dependency runtime vào giai đoạn binding sớm. Dù một vài lần startup có thể tình cờ hoạt động, lifecycle không phải hợp đồng ổn định cho kiểu thiết kế này.

**Cách sửa:** converter chỉ parse; phần xác minh từ database/network chạy sau khi config bean và service tương ứng sẵn sàng.

### 21.8. Converter ghi log raw value

**Triệu chứng:** log có token, user info hoặc URL chứa credential.

**Cách sửa:** không log input nhạy cảm; mô tả yêu cầu cú pháp trong lỗi. Đối với cấu hình production, quản lý secret bằng cơ chế phù hợp, quyền truy cập và phân loại các key có thể hiển thị.

### 21.9. Có nhiều `ApplicationContext` trong test

**Triệu chứng:** converter hoặc một static holder dùng lại state từ test trước.

**Cách sửa:** converter nên stateless; không giữ cache mutable toàn cục chứa thông tin config đã bind. Dùng dependency instance thuộc context, hoặc service quản lý cache rõ ràng ở tầng ứng dụng sau binding.

### 21.10. Sửa YAML rồi converter không chạy lại

**Giải thích:** Config Data thông thường được nạp và bean config được bind khi ứng dụng khởi động. Sửa file ngoài tiến trình không mặc nhiên kích hoạt binding/refresh.

**Cách sửa:** khởi động lại trong bài lab. Nếu cần refresh động, thiết kế riêng vòng đời cập nhật, tính thread safety và cách thay thế các object cấu hình cũ; không giả định converter tự giám sát file.

## 22. Ma trận lựa chọn nhanh

| Nhu cầu thực sự | Cách tiếp cận | Lý do |
| --- | --- | --- |
| Chuyển `500ms` thành `Duration` | Dùng conversion có sẵn | Boot đã hỗ trợ các định dạng thời gian phổ biến |
| Chuyển `"region/service"` thành value object | `Converter<String, NodeRef>` + `@ConfigurationPropertiesBinding` | Hạn chế phạm vi thay đổi, ít dependency |
| Tùy chỉnh service chung được Binder tìm theo tên | Bean `conversionService` có thiết kế cẩn thận | Có tác động sớm/rộng, cần kiểm thử |
| Chuyển dữ liệu trong một service nghiệp vụ | Converter/service nghiệp vụ tên riêng | Không cần chen vào binding hạ tầng |
| Kiểm tra ID trong database | Service sau binding | Cần tài nguyên runtime, không phải parsing |
| Xác thực route qua API | Startup check hoặc readiness policy | Có side effect, cần retry/timeouts |
| Chuyển scalar format legacy | Converter thuần hoặc editor nếu hệ thống legacy bắt buộc | Chọn theo API đang tiêu thụ dữ liệu |
| Binding nested object từ YAML | `@ConfigurationProperties` có nested record | Nhiều khi không cần custom converter |
| Ánh xạ `String` -> enum chuẩn | Binder/conversion tích hợp | Tránh code dư thừa |
| Cấp default cho property thiếu | `@DefaultValue` hoặc file nền | Không nên viết converter để tự đi tìm default từ nguồn khác |

### 22.1. Một quy tắc thiết kế hữu ích

Nếu chữ ký constructor của converter như sau:

```java
public ConverterImpl(Repository repository,
                     ApiClient client,
                     UserService userService) {
    ...
}
```

hãy xem lại thiết kế. Một converter cấu hình hiếm khi cần các dependency đó.

Một chữ ký hợp lý hơn có thể là:

```java
public NodeRefConverter() {
}
```

hoặc constructor chỉ nhận những **quy tắc thuần, bất biến** không phụ thuộc vào context. Kể cả khi có tham số, chúng phải an toàn để được tạo trong giai đoạn binding sớm.

## 23. Checklist triển khai custom converter an toàn

Trước khi đưa custom converter vào một Spring Boot service:

1. **Xác nhận thực sự cần converter.** Thử type conversion có sẵn và nested `@ConfigurationProperties` trước.
2. **Định nghĩa chính xác source/target type.** Ví dụ `String -> NodeRef`, không dùng parser chung không rõ kiểu.
3. **Giữ `convert()` thuần.** Không đọc database, gọi network hoặc phát sự kiện.
4. **Không inject bean cấu hình đang được bind** vào converter.
5. **Không inject service phụ thuộc vào bean cấu hình đó** qua đường gián tiếp.
6. **Dùng `@ConfigurationPropertiesBinding`** khi converter chỉ phục vụ Binder.
7. **Khai báo `static @Bean`** cho converter này để giảm khởi tạo sớm class cấu hình.
8. **Tránh tên `conversionService`** nếu bạn không có chủ đích cung cấp service hạ tầng chung.
9. **Nếu phải thay conversion service chung**, sử dụng nền tảng conversion phù hợp của Boot và kiểm thử lại các conversion chuẩn.
10. **Không dựa vào `@Lazy`** để che vòng dependency của converter bắt buộc.
11. **Viết unit test không cần Spring** cho mọi dạng input hợp lệ/sai cú pháp.
12. **Viết integration test binding** trên một config record thật.
13. **Tách validation nghiệp vụ và external verification** sang lớp thích hợp.
14. **Không log giá trị nhạy cảm** trong converter hoặc exception.
15. **Kiểm tra vòng đời trên profile, CI và container** vì những nguồn runtime có thể khác local.
16. **Giữ converter stateless và thread-safe** nếu nó có thể được dùng ở nhiều lần binding.
17. **Dùng message lỗi có ngữ nghĩa**, nhưng không phụ thuộc vào đúng wording exception nội bộ của framework.
18. **Không bắt converter tự refresh dữ liệu** khi nguồn cấu hình thay đổi; refresh là một hệ thống khác.

## 24. Bài tập luyện tập

### Bài A — Phân loại dependency

Cho ba converter:

```java
// A
public class RegionConverter implements Converter<String, Region> {
    public Region convert(String source) {
        return Region.valueOf(source.toUpperCase(Locale.ROOT));
    }
}

// B
public class RegionConverter implements Converter<String, Region> {
    private final RegionRepository repository;
    public Region convert(String source) {
        return repository.findByCode(source).orElseThrow();
    }
}

// C
public class RegionConverter implements Converter<String, Region> {
    private final RoutingProperties properties;
    public Region convert(String source) {
        return parseWithRule(source, properties.defaultRegion());
    }
}
```

Converter nào phù hợp hơn cho `@ConfigurationPropertiesBinding` trong giai đoạn binding sớm? Giải thích rủi ro của hai converter còn lại.

### Bài B — Sửa factory method

Đầu vào:

```java
@Configuration
public class MyConverters {

    private final RoutingService routingService;

    public MyConverters(RoutingService routingService) {
        this.routingService = routingService;
    }

    @Bean
    @ConfigurationPropertiesBinding
    Converter<String, NodeRef> converter() {
        return new ClientAwareConverter(routingService);
    }
}
```

Hãy chuyển thành một factory method `static @Bean` không nhận dependency runtime và một converter thuần. Nêu rõ vì sao chỉ thêm `static` mà vẫn giữ dependency tham số không đủ.

### Bài C — Chọn giữa nested object và scalar format

So sánh:

```yaml
routing:
  primary: "ap-southeast-1/payments"
```

với:

```yaml
routing:
  primary:
    region: ap-southeast-1
    service: payments
```

Hãy thiết kế record Java cho từng cách. Cách nào cần custom scalar converter? Cách nào có thể dùng nested binding trực tiếp?

### Bài D — Global conversion service

Một dự án có bean tên `conversionService` chỉ dùng để chuyển các định dạng UI trong một service nghiệp vụ. Theo hướng dẫn bài này, bạn sẽ cân nhắc điều chỉnh tên bean ra sao và vì sao?

### Bài E — Thêm type mới

Định nghĩa một `FeatureCode` gồm `group` và `name`, với scalar `"group:name"`. Viết converter thuần `String -> FeatureCode`, đăng ký bằng `static @Bean @ConfigurationPropertiesBinding`, và bind:

```yaml
features:
  primary: "billing:new-flow"
```

Đưa ra ít nhất ba input sai cú pháp cần được converter từ chối.

### Bài F — Unit test và integration test

Viết một test thuần Java chứng minh parser xử lý input `"ap-southeast-1/payments"`. Sau đó viết một `@SpringBootTest` dùng:

```properties
routing.primary=eu-west-1/invoices
```

để xác minh `RoutingProperties.primary()` có hai thành phần đúng.

Giải thích vì sao hai loại test kiểm tra hai trách nhiệm khác nhau.

### Bài G — Vòng phụ thuộc

Vẽ đường phụ thuộc nếu `RoutingProperties` dùng `NodeRefConverter`, `NodeRefConverter` inject `ApiClient`, và `ApiClient` inject `RoutingProperties`. Có tồn tại một thứ tự khởi tạo bean hợp lý không? Bạn sẽ di chuyển dependency nào sang tầng service?

### Bài H — Không làm lộ secret

Giả sử format là `"provider/key-id"` nhưng `key-id` là dữ liệu nhạy cảm. Sửa error message và logging để converter không in nguyên input khi parsing thất bại.

## 25. Câu hỏi tự kiểm tra

**1.** Vì sao converter phục vụ `@ConfigurationProperties` có thể bị tạo trước một số service ứng dụng?

**2.** Bean tên `conversionService` có gì khác một `ConversionService` được đặt tên riêng cho nghiệp vụ?

**3.** Vì sao phương thức `@Bean` có `@ConfigurationPropertiesBinding` được khuyên khai báo `static`?

**4.** Thêm `static` có giải quyết được vấn đề nếu factory method vẫn inject `DataSource` hoặc `ApiClient` không?

**5.** Vì sao một converter cần chính `RoutingProperties` mà nó đang giúp bind là một thiết kế sai?

**6.** Đối với `Duration` và `DataSize` phổ biến, có phải luôn viết converter mới không?

**7.** `@ConfigurationPropertiesBinding` có bảo đảm converter dùng được trực tiếp cho mọi `@Value` không?

**8.** Nếu input `"region/service"` hợp lệ nhưng service đó không tồn tại trên Kubernetes, parser nên gọi Kubernetes API luôn không?

**9.** Khi một converter thất bại vì format, ứng dụng có nên âm thầm dùng giá trị tùy ý để khởi động không?

**10.** Nếu một `ConversionService` chỉ dùng để xử lý business data, có lý do nào để tránh đặt tên `conversionService` không?

**11.** Vì sao unit test không cần Spring là một dấu hiệu tốt cho converter cấu hình?

**12.** Nếu Spring log `not eligible for getting processed by all BeanPostProcessors`, nên kiểm tra điều gì?

**13.** Dùng `@Lazy` có làm biến mất dependency khi Binder nhất thiết cần converter không?

**14.** Trong ứng dụng nhiều `ApplicationContext`, vì sao không nên lưu trạng thái cấu hình trong static mutable field của converter?

**15.** Khi sửa YAML ngoài tiến trình, converter có mặc định được gọi lại không?

### Gợi ý đối chiếu

1. Vì binding diễn ra trong khi tạo các bean config, trước khi toàn bộ service khác hoàn tất startup.
2. Bean tên đặc biệt có thể được hạ tầng yêu cầu sớm; bean nghiệp vụ tên riêng không tự nhận vai trò đó.
3. Để tạo converter mà không cần tạo instance class `@Configuration`, giảm khởi tạo sớm không cần thiết và cảnh báo liên quan.
4. Không; dependency thực tế vẫn cần được resolve.
5. Vì tạo vòng phụ thuộc giữa binder, converter và bean được bind.
6. Không; Spring Boot có converter chuẩn.
7. Không; đó là qualifier cho binding cấu hình, không phải đăng ký toàn cục cho mọi đường conversion.
8. Không; xác minh ngoại vi là trách nhiệm của service ở lifecycle phù hợp.
9. Không đối với cấu hình bắt buộc; nên phát hiện sớm dữ liệu sai.
10. Có; tránh kích hoạt convention hạ tầng trong khi bean chỉ phục vụ business.
11. Vì converter ít dependency và parsing có thể xác định bằng input/output.
12. Xem việc một bean hoặc class cấu hình bị tạo sớm, factory method có static không, và có kéo thêm dependency không.
13. Không; Binder vẫn phải tạo converter khi cần.
14. Vì static state thuộc class/JVM, có thể rò dữ liệu giữa context/test và gây concurrency issues.
15. Không mặc định; Config Data/bean binding thường xử lý lúc startup, refresh cần cơ chế riêng.

## 26. Hướng áp dụng trong dự án thực

Với một ứng dụng nhiều môi trường triển khai, kiến trúc nên giữ đường dữ liệu như sau:

```text
application.yaml / environment / CLI
                 |
                 v
        Config Data / Environment
                 |
                 v
             Binder
                 |
      +----------+----------+
      |                     |
  Conversion chuẩn    Converter custom thuần
      |                     |
      +----------+----------+
                 |
                 v
       @ConfigurationProperties
                 |
                 v
       Bean configuration đã có kiểu
                 |
                 v
    Services / Repositories / Clients
                 |
                 v
    Khởi động và hoạt động nghiệp vụ
```

Không nên đảo mũi tên để converter phụ thuộc vào chính service cần config đã bind. Các converter phải ở **rìa đầu vào của cấu hình**, có thể chạy khi application context còn đang hình thành.

Trong code review, hãy hỏi:

```text
Converter này có thể chạy với `new` trong unit test không?
Nó có thực sự chỉ parse/convert hay đang gọi nghiệp vụ?
Có một bean cấu hình nào phụ thuộc ngược vào converter không?
Ta có bắt buộc phải cung cấp bean tên conversionService không?
Nếu có @ConfigurationPropertiesBinding, @Bean method đã static chưa?
Các conversion mặc định của Spring Boot có còn hoạt động không?
Lỗi dữ liệu sai có được phát hiện và báo rõ mà không lộ secrets không?
```

Nếu những câu hỏi này được giải quyết ngay khi thiết kế, bạn sẽ tránh được một loại lỗi startup rất khó tìm: YAML đúng, tên property đúng, nhưng converter kéo những dependency chưa sẵn sàng vào quá trình khởi tạo.

## 27. Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): mục *Properties Conversion*, yêu cầu khởi tạo sớm, `conversionService`, `@ConfigurationPropertiesBinding`, khuyến nghị `static @Bean`.
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binder, constructor binding, validation và conversion chuẩn.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `Converter`, `ConverterFactory`, `GenericConverter` và `ConversionService`.
- [Spring Boot 3.3 API — `ConfigurationPropertiesBinding`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBinding.html): qualifier cho converter phục vụ binding cấu hình.

**Kết luận ngắn:** Converter dùng cho externalized configuration phải sẵn sàng khi Binder cần nó, thường là rất sớm. Hãy để converter chỉ chuyển dữ liệu, đăng ký scoped converter với `@ConfigurationPropertiesBinding` và `static @Bean`, giới hạn dependency, tránh thay `conversionService` toàn cục khi không thật sự cần, và chuyển kiểm tra nghiệp vụ sang service sau binding.