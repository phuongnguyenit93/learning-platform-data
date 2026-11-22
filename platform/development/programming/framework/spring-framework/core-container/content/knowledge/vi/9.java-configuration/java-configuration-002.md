# Đăng ký đối tượng thư viện không có @Component bằng cấu hình Java trong Spring

## 1. Tình huống và kết quả cần đạt

Trong ứng dụng Spring, rất nhiều đối tượng cần sử dụng được cung cấp bởi thư viện bên ngoài, không thuộc mã nguồn của đội phát triển: `com.fasterxml.jackson.databind.ObjectMapper` để xử lý JSON, `java.time.Clock` để kiểm soát thời gian, HTTP client, client SDK, bộ mã hóa, bộ kết nối và các adapter của bên thứ ba.

Những class này thường **không mang `@Component`**. Ta cũng thường không có quyền sửa source code hoặc thêm annotation vào class trong JAR. Vì vậy, nếu chỉ bật `@ComponentScan` và hy vọng Spring tự đăng ký mọi đối tượng thư viện, kết quả thường là thiếu bean.

Cách chuẩn trong **cấu hình Java của Spring Core Container** là khai báo một phương thức **`@Bean`** trong class cấu hình **`@Configuration`**. Phương thức ấy tạo hoặc lấy đối tượng, cấu hình các thuộc tính cần thiết rồi **trả đối tượng cho container quản lý**. Spring đăng ký bean definition của factory method và sử dụng nó để đáp ứng dependency injection.

Sau bài học, bạn có thể:

1. Giải thích vì sao một class thư viện không có `@Component` vẫn trở thành Spring bean bằng `@Bean`.
2. Viết `@Configuration` và factory method `@Bean` trả object từ thư viện ngoài; phân biệt đăng ký bean với tự gọi `new` trong mã nghiệp vụ.
3. Tiêm các dependency vào **tham số của phương thức `@Bean`**, kể cả khi object thư viện nhận dependency qua constructor.
4. Chọn đúng bean khi có nhiều instance cùng kiểu, qua `@Qualifier`, tên bean hoặc `@Primary`.
5. Quản lý scope, lazy initialization, init/destroy callback và ownership của tài nguyên.
6. Hiểu `@Configuration(proxyBeanMethods=false)`, sự khác nhau giữa dependency injection và **gọi trực tiếp phương thức `@Bean`**.
7. Chạy ví dụ Java 17+ dùng **Jackson ObjectMapper** thực tế, không có component scan.

> Ý tưởng trung tâm: **Spring quản lý object vì đã có một bean definition hợp lệ**, không phải vì class của object bắt buộc phải mang annotation Spring.

## 2. Vì sao component scanning chưa giải quyết vấn đề?

Giả sử thư viện cung cấp:

```java
// Thuộc thư viện ngoài; giả sử class không có annotation Spring.
package vendor.sdk;

public final class ExternalClient {
    public ExternalClient(String endpoint, String token) {
        // ...
    }

    public String fetch(String id) {
        // ...
        return id;
    }
}
```

Đây là class phác họa để giải thích API constructor của một SDK giả định; không phải thư viện thật có thể thêm vào Gradle. Class không chứa `@Component`, `@Service` hay meta-annotation `@Component`, và constructor cần thông tin cấu hình. `@ComponentScan` với bộ lọc stereotype mặc định sẽ không tự tạo bean `ExternalClient`.

Để đăng ký, sử dụng factory method:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExternalClientConfig {
    @Bean
    ExternalClient externalClient() {
        return new ExternalClient(
                "https://api.example.test",
                "demo-token"
        );
    }
}
```

Đoạn này tiếp tục là **ví dụ cấu trúc**, giả định có `vendor.sdk.ExternalClient` và import phù hợp; URL/token chỉ mang tính minh họa và không phải cấu hình production. Với dự án thật, endpoint/secret cần đến từ nguồn cấu hình an toàn, không hard-code vào source.

Điều quan trọng là class `ExternalClient` **không cần sửa**. Phương thức `externalClient()` là nơi mã của ứng dụng quyết định cách tạo object; Spring gọi factory method khi cần tạo bean theo scope của nó.

### Component scan và @Bean trả lời hai câu hỏi khác nhau

| Thành phần | Câu hỏi | Trường hợp phù hợp |
| --- | --- | --- |
| `@ComponentScan` | Class nào trên classpath được phát hiện theo package/filter? | Các class do ứng dụng kiểm soát, có thể đánh dấu stereotype Spring. |
| `@Component` / `@Service` | Class này có là ứng viên component trong lượt scan không? | Service, adapter, handler nằm trong mã nguồn của ứng dụng. |
| `@Bean` | Phương thức nào tạo/cấu hình một object rồi đăng ký nó thành bean? | Class thư viện, object cần builder/factory, setup phức tạp, class không mang stereotype. |
| `@Configuration` | Class nào chứa Java configuration và các bean factory methods? | Tách logic lắp ghép hạ tầng khỏi nghiệp vụ. |

Một project có thể đồng thời dùng cả hai đường đăng ký. `@ComponentScan` không bắt buộc tồn tại thì `@Bean` mới hoạt động; ngược lại, `@Bean` không loại bỏ nhu cầu quét các service của ứng dụng.

## 3. Cơ chế thực tế khi Spring xử lý @Bean

Một class cấu hình Java thường có dạng:

```java
@Configuration
public class InfraConfig {
    @Bean
    public ThirdPartyType thirdPartyType() {
        return new ThirdPartyType(/* tham số cấu hình */);
    }
}
```

`ThirdPartyType` chỉ là kiểu giả định, đoạn này chưa thể biên dịch nếu chưa có thư viện cụ thể. Đường đi logic:

```text
Ứng dụng đăng ký InfraConfig
             |
             v
ConfigurationClassPostProcessor
   phân tích @Configuration + @Bean
             |
             v
Đăng ký BeanDefinition:
   beanName = "thirdPartyType"
   factoryBean = InfraConfig
   factoryMethod = thirdPartyType
             |
             v
Spring cần tạo bean theo scope
             |
             v
Gọi factory method -> lấy object
             |
             v
BeanPostProcessor, init callback, lifecycle
             |
             v
Object có thể tiêm vào các bean khác
```

**Các mốc phải hiểu đúng:**

- `@Bean` là annotation **trên method**, không phải annotation buộc phải đặt lên class thư viện.
- Trong Spring 6.2, tên bean mặc định thông dụng là tên method: `thirdPartyType`. Có thể đặt tên cụ thể bằng `@Bean("someName")`.
- Kiểu khai báo ở return type của phương thức có ảnh hưởng đến quá trình Spring tìm bean theo type; nên khai báo kiểu đủ cụ thể cho injection point cần dùng.
- Spring không “biến source thư viện thành component”. Container quản lý **object do factory method cung cấp**.
- Việc đăng ký bean definition, tạo instance và gọi init callback là những bước khác nhau. Bean singleton không lazy thường được tạo khi refresh context; `prototype` được tạo theo mỗi lần yêu cầu.
- Spring vẫn có thể áp dụng dependency injection và lifecycle processing trên object trả về từ `@Bean` nếu annotation/hạ tầng liên quan được cấu hình.

## 4. Viết @Bean đúng cách: từ tối giản đến có dependency

### 4.1. Object không cần dependency

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfig {
    @Bean
    Clock appClock() {
        return Clock.systemUTC();
    }
}
```

`Clock` thuộc thư viện chuẩn Java; class đó không mang `@Component`. Sau khi `TimeConfig` được nạp vào Spring, bean `appClock` có thể inject vào service:

```java
import java.time.Clock;
import java.time.Instant;

public final class AuditService {
    private final Clock clock;

    public AuditService(Clock clock) {
        this.clock = clock;
    }

    public Instant now() {
        return Instant.now(clock);
    }
}
```

`AuditService` ở đây là class Java bình thường; muốn nó trở thành Spring bean thì cần đăng ký qua `@Bean` hoặc component scan phù hợp. Việc cấu hình `Clock` độc lập giúp test dùng fixed clock và production dùng system clock mà không phải gọi `Instant.now()` trực tiếp ở nhiều chỗ.

### 4.2. Factory method nhận dependency từ container

Nếu một client phải dùng object khác đã được đăng ký, khai báo dependency trong **tham số `@Bean`**:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfig {
    @Bean
    ClientSettings clientSettings() {
        return new ClientSettings("https://example.test");
    }

    @Bean
    VendorClient vendorClient(ClientSettings settings) {
        return new VendorClient(settings.endpoint());
    }
}
```

`ClientSettings` và `VendorClient` là kiểu minh họa, không phải class Spring dựng sẵn. Spring resolve `ClientSettings` theo dependency injection thông thường, rồi gọi `vendorClient(settings)`. Đây là cách rõ ràng để lắp ghép object, đặc biệt khi sử dụng `proxyBeanMethods=false`.

**Tránh** viết `vendorClient() { return new VendorClient(clientSettings().endpoint()); }` khi đặt `proxyBeanMethods=false`: đó là **lời gọi Java thông thường**, tạo thêm `ClientSettings` thay vì chắc chắn sử dụng singleton container quản lý. Truyền tham số phương thức là cách nhất quán.

### 4.3. Đăng ký đối tượng được tạo bằng builder/factory của thư viện

Không phải thư viện nào cũng có public constructor thích hợp. Factory method có thể gọi builder hoặc static factory:

```java
@Bean
ExternalSdkClient sdkClient(AppProperties settings) {
    return ExternalSdkClient.builder()
            .endpoint(settings.endpoint())
            .timeout(settings.timeout())
            .build();
}
```

Đây là **pseudocode Java API của SDK giả định**. Spring quan tâm object cuối cùng được trả về; cách thư viện tạo object (constructor, builder, static factory, connection pool) là quyết định của chính thư viện.

## 5. Ví dụ hoàn chỉnh: đăng ký Jackson ObjectMapper không có @Component

Ví dụ thật sau đây dùng:

- **Java 17+**.
- **Spring Framework 6.2.9** với `AnnotationConfigApplicationContext`.
- **Jackson Databind 2.18.2**: class `ObjectMapper` của thư viện ngoài **không cần `@Component`**.
- Hai bean `ObjectMapper` khác cấu hình, một bean `Clock`, một bean dịch vụ được lắp qua tham số `@Bean`.
- Hoàn toàn **không khai báo `@ComponentScan`**.

Ví dụ cố định thời gian để kết quả stdout có thể kiểm tra lại mà không phụ thuộc ngày hiện tại.

### 5.1. Cấu trúc file

```text
third-party-bean-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── ThirdPartyBeansDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'third-party-bean-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.18.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ThirdPartyBeansDemo'
}
```

Spring Context có dependency transitive cho các thành phần IoC cần thiết. Jackson Databind mang những dependency Jackson cần thiết theo cơ chế Gradle thông thường. Đây là ví dụ Spring thuần; ứng dụng Spring Boot thường dùng dependency management/BOM của Boot để đồng bộ versions.

### 5.2. Chương trình Java

**`src/main/java/demo/ThirdPartyBeansDemo.java`**

```java
package demo;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ThirdPartyBeansDemo {

    // Đây chỉ là class Java bình thường, không có @Component.
    public static final class ReportService {
        private final ObjectMapper mapper;
        private final Clock clock;

        public ReportService(ObjectMapper mapper, Clock clock) {
            this.mapper = mapper;
            this.clock = clock;
        }

        public String buildReport() throws JsonProcessingException {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("source", "jackson");
            data.put("year", LocalDate.now(clock).getYear());
            return mapper.writeValueAsString(data);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        // Jackson ObjectMapper không có @Component trong thư viện.
        @Bean("compactMapper")
        ObjectMapper compactMapper() {
            return new ObjectMapper();
        }

        @Bean("prettyMapper")
        ObjectMapper prettyMapper() {
            return new ObjectMapper()
                    .enable(SerializationFeature.INDENT_OUTPUT);
        }

        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-06-11T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }

        // Hai ObjectMapper cùng kiểu: chọn đúng tên ở injection point.
        @Bean
        ReportService reportService(
                @Qualifier("compactMapper") ObjectMapper mapper,
                Clock clock) {
            return new ReportService(mapper, clock);
        }
    }

    public static void main(String[] args) throws JsonProcessingException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("compact=" +
                    context.containsBean("compactMapper"));
            System.out.println("pretty=" +
                    context.containsBean("prettyMapper"));
            System.out.println("mapper-count=" +
                    context.getBeansOfType(ObjectMapper.class).size());

            ObjectMapper first = context.getBean(
                    "compactMapper", ObjectMapper.class);
            ObjectMapper second = context.getBean(
                    "compactMapper", ObjectMapper.class);

            System.out.println("singleton=" + (first == second));
            System.out.println("report=" +
                    context.getBean(ReportService.class).buildReport());
        }
    }
}
```

**Chạy từ thư mục dự án:**

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, trên Linux/macOS có thể dùng `./gradlew run --quiet`; trên Windows dùng `gradlew.bat run --quiet`. Gradle sử dụng cấu hình dependency và toolchain để biên dịch/chạy. Chạy `javac ThirdPartyBeansDemo.java` đơn lẻ sẽ thiếu thư viện Spring/Jackson trừ khi tự cấu hình classpath.

**Các dòng do chương trình in ra:**

```text
compact=true
pretty=true
mapper-count=2
singleton=true
report={"source":"jackson","year":2024}
```

Lý do output cố định:

1. `Config.class` được truyền trực tiếp cho `AnnotationConfigApplicationContext`; Spring xử lý `@Configuration` và bốn factory method `@Bean`. Không có `@ComponentScan`.
2. `compactMapper` và `prettyMapper` là **hai bean definition** cùng kiểu `ObjectMapper`, đều trả một object của thư viện Jackson. Cả hai tên đều tồn tại trong context.
3. `getBeansOfType(ObjectMapper.class)` tìm thấy hai bean, nên `mapper-count=2`.
4. Mặc định `@Bean` có scope singleton. Hai lần `getBean("compactMapper", ObjectMapper.class)` trong cùng context trả cùng instance.
5. Spring chọn `compactMapper` cho phương thức `reportService(...)` nhờ `@Qualifier("compactMapper")`. Nó không nhầm với `prettyMapper` dù cả hai có cùng return type.
6. `Clock.fixed(...)` luôn cung cấp cùng thời điểm ngày 11/6/2024 UTC, nên năm là 2024.
7. `LinkedHashMap` duy trì thứ tự put là `source` rồi `year`; `compactMapper` không bật pretty print, nên JSON một dòng chính xác như stdout.
8. `ReportService` cũng **không mang `@Component`**, nhưng nó vẫn trở thành bean vì method `@Bean ReportService reportService(...)` đã đăng ký.

**Đây là demo về cấu hình Java và IoC**; nó không khởi động web server, không cần Spring MVC/Boot và không truy cập network. Các log của Gradle/môi trường build, nếu có, nằm ngoài năm dòng output chủ động trên.

## 6. Chọn @Bean name, @Qualifier và @Primary

### 6.1. Một thư viện có thể cần nhiều instance cùng kiểu

Một hệ thống thực tế có thể dùng hai `ObjectMapper`:

- Một mapper xuất JSON public theo quy tắc của API.
- Một mapper cho log nội bộ với format khác.

Hoặc có hai HTTP client cùng class nhưng khác endpoint, timeout hay credentials. Khi cùng kiểu có nhiều bean, injection chỉ theo type có thể trở nên mơ hồ.

```java
@Bean("internalMapper")
ObjectMapper internalMapper() {
    return new ObjectMapper();
}

@Bean("externalMapper")
ObjectMapper externalMapper() {
    return new ObjectMapper();
}
```

Đoạn này dùng cùng dependency Jackson của demo và cần nằm trong một class cấu hình. Nếu class consumer nhận duy nhất một `ObjectMapper` mà không đủ thông tin để chọn ứng viên, Spring có thể ném `NoUniqueBeanDefinitionException`.

**Chọn rõ bằng qualifier:**

```java
@Bean
ExternalExporter externalExporter(
        @Qualifier("externalMapper") ObjectMapper mapper) {
    return new ExternalExporter(mapper);
}
```

`ExternalExporter` là class nghiệp vụ minh họa, không có sẵn trong Spring/Jackson. `@Qualifier` gắn tại injection point giúp chọn bean tương ứng.

### 6.2. Chọn một ứng viên mặc định bằng @Primary

```java
@Bean
@Primary
ObjectMapper appMapper() {
    return new ObjectMapper();
}

@Bean
ObjectMapper legacyMapper() {
    return new ObjectMapper();
}
```

Đây là đoạn cấu hình cần import `org.springframework.context.annotation.Primary`. Khi injection theo kiểu `ObjectMapper` mà không có qualifier chi tiết, `@Primary` có thể giúp chọn `appMapper`. Tuy nhiên, đừng dùng `@Primary` để che việc có nhiều cấu hình khác nhau mà nghiệp vụ cần gọi đích xác.

**Phân biệt:** `@Primary` có tác dụng trong quá trình **lựa chọn dependency**; nó không thay tên bean, scope hay loại bỏ bean còn lại khỏi context.

### 6.3. Tên method, tên bean và alias

```java
@Bean({"jsonWriter", "publicJsonWriter"})
ObjectMapper writer() {
    return new ObjectMapper();
}
```

Đoạn này tạo **một** bean với tên `jsonWriter` và alias `publicJsonWriter`, không phải hai object độc lập. Dùng hai method `@Bean` riêng nếu thật sự cần hai cấu hình/instance. Trong bản cấu hình thông thường, `@Bean ObjectMapper objectMapper()` có tên mặc định `objectMapper`.

## 7. Lắp dependency qua tham số phương thức @Bean

Giả sử client thư viện cần `Clock`, `ObjectMapper` và configuration:

```java
@Bean
VendorClient vendorClient(
        @Qualifier("compactMapper") ObjectMapper mapper,
        Clock clock,
        ClientOptions options) {
    return new VendorClient(mapper, clock, options);
}
```

Đây là **ví dụ minh họa**; `VendorClient` và `ClientOptions` là kiểu do ứng dụng/thư viện giả định cung cấp. Spring giải quyết từng tham số method giống như dependency injection thông thường. Cách này có ba ưu điểm:

- Dependency được thấy rõ ở chữ ký factory method.
- Có thể thay object trong test bằng cấu hình khác mà không đụng đến source code thư viện.
- Không phải gọi trực tiếp các `@Bean` methods khác rồi vô tình tạo object ngoài vòng đời dự kiến.

### Nên trả về interface hay concrete type?

Nếu API công khai của bean chỉ cần interface `Client`, có thể khai báo:

```java
@Bean
Client client() {
    return new HttpClientAdapter();
}
```

`Client` và `HttpClientAdapter` là kiểu giả định. Tuy nhiên, Spring có thể dựa trên **declared return type** khi cần dự đoán type của bean **trước khi tạo instance**. Nếu nơi khác inject trực tiếp `HttpClientAdapter` nhưng factory method khai báo chỉ trả `Client`, khả năng type matching sớm có thể bị hạn chế.

Một nguyên tắc hữu ích: **khai báo return type đủ cụ thể** cho những injection point được phép sử dụng bean. Nếu muốn các lớp chỉ biết interface, giữ nhất quán kiểu interface tại injection point và API service.

### Tạo bean qua static factory method của SDK

```java
@Bean
VendorConnection connection(VendorSettings settings) {
    return VendorConnection.open(
            settings.endpoint(),
            settings.accessToken()
    );
}
```

Snippet cấu trúc, không phải API SDK có thật. Trong Spring, `@Bean` có thể gọi bất kỳ cách tạo object hợp lệ nào mà vendor công bố. Không cần Spring biết constructor nội bộ của SDK nếu factory method trả đúng object.

## 8. @Configuration(proxyBeanMethods=false) và gọi @Bean method

Đây là điểm dễ tạo bug khi tích hợp thư viện.

### 8.1. Hai cách lắp ghép bean

**Nên dùng: factory method parameters.**

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    TimeService timeService(Clock clock) {
        return new TimeService(clock);
    }
}
```

`TimeService` ở đây là kiểu ví dụ giả định có constructor nhận `Clock`. Container giải quyết tham số `Clock` theo scope và rules hiện hành.

**Cần lưu ý: direct method call.**

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    TimeService timeService() {
        return new TimeService(clock());
    }
}
```

Vì `proxyBeanMethods=false`, lệnh `clock()` trong `timeService()` là một lời gọi Java bình thường. Nó tạo một `Clock` **khác đối tượng đã đăng ký làm bean** (với cách factory ở trên), nếu method thực sự tạo object mới. Trong một số trường hợp, lỗi này gây hai connection pools/HTTP clients hoặc khác lifecycle.

Ở chế độ đầy đủ `@Configuration(proxyBeanMethods=true)`, Spring thường dùng class enhancement để những lời gọi giữa các `@Bean` methods được chuyển qua container theo scope. Nhưng code dùng **tham số injection** vẫn rõ hơn và không phụ thuộc cách proxy hóa class cấu hình.

**Quy tắc:** Với `proxyBeanMethods=false`, không dùng lời gọi chéo `@Bean` methods để giả định lấy singleton container. Chọn injection qua parameters; đây cũng là cách dễ test và ít ngạc nhiên.

### 8.2. Đừng gọi factory method từ business code

Dòng:

```java
new ExternalClientConfig().externalClient();
```

nếu cấu hình và method được truy cập hợp lệ, chỉ là **tạo một object Java**. Nó không tương đương với `applicationContext.getBean(ExternalClient.class)`. Object được tạo bằng cách gọi thủ công vào configuration mới có thể không nhận lifecycle/proxy/configuration từ container.

Muốn sử dụng bean, inject vào constructor của service, hoặc ở điểm khởi động/kiểm thử dùng `ApplicationContext.getBean(...)`. Trong domain/business code, tránh phụ thuộc trực tiếp container khi constructor injection đã đủ.

## 9. Scope và lazy initialization cho bean thư viện

### 9.1. Singleton mặc định

`@Bean` mặc định singleton (trong một container). Hợp lý với những đối tượng có khả năng dùng lại như mapper đã cấu hình, immutable config hoặc client thread-safe theo tài liệu vendor.

```java
@Bean
ObjectMapper objectMapper() {
    return new ObjectMapper();
}
```

Khi object đã được tạo và cấu hình hoàn chỉnh, các lần yêu cầu bean trong cùng context thường nhận cùng instance. Tuy nhiên, **không tự suy luận mọi object thư viện đều thread-safe** chỉ vì Spring cung cấp singleton; xem hợp đồng của từng thư viện và tránh mutate cấu hình sau khi chia sẻ.

Ví dụ `ObjectMapper` của Jackson thường có thể dùng đồng thời an toàn **khi tất cả cấu hình được hoàn tất trước các lời gọi read/write đầu tiên**. Thay đổi cấu hình chung khi nhiều thread đang sử dụng có thể gây hành vi khó đoán; nếu cần các cấu hình khác nhau, đăng ký mapper riêng hoặc dùng cấu hình reader/writer bất biến phù hợp.

### 9.2. Prototype cho object có trạng thái riêng

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
VendorRequestBuilder requestBuilder(VendorSettings options) {
    return new VendorRequestBuilder(options);
}
```

Đây là ví dụ với `VendorRequestBuilder`/`VendorSettings` giả định; cần import `Scope` và `ConfigurableBeanFactory`. Prototype phù hợp khi đối tượng giữ state của từng yêu cầu và vendor không cho tái sử dụng an toàn.

Nếu singleton consumer cần một instance mỗi lần xử lý, có thể inject `ObjectProvider<VendorRequestBuilder>` và gọi `getObject()` khi bắt đầu công việc. Đừng inject một prototype trực tiếp vào singleton rồi cho rằng Spring tự đổi object cho mọi method call.

### 9.3. @Lazy chỉ thay thời điểm tạo, không thay scope

```java
@Bean
@Lazy
ObjectMapper expensiveMapper() {
    return new ObjectMapper();
}
```

Cần import `org.springframework.context.annotation.Lazy`. Với bean singleton, `@Lazy` thường trì hoãn tạo bean tới khi thực sự được yêu cầu. Nhưng nếu một singleton eager khác cần mapper trong constructor/factory method, dependency ấy có thể buộc Spring tạo mapper sớm. `@Lazy` không biến singleton thành prototype.

### 9.4. Vòng đời tài nguyên thư viện

Một SDK client có `close()`/`shutdown()` có thể nắm socket, executor hoặc thread riêng. Với `@Bean`, Spring hỗ trợ:

- `initMethod`: gọi method init do tên khai báo nếu thích hợp.
- `destroyMethod`: gọi method hủy theo tên; với cách cấu hình mặc định, Spring có khả năng suy luận `close`/`shutdown` công khai cho bean thích hợp.
- `@PreDestroy` hoặc `DisposableBean` khi bản thân class/adapter hỗ trợ và processor phù hợp.
- `AutoCloseable`/lifecycle API tùy quy tắc của framework và class.

Ví dụ **cấu trúc** khi SDK có method `start()` và `stop()`:

```java
@Bean(initMethod = "start", destroyMethod = "stop")
VendorConnection managedConnection(VendorSettings options) {
    return new VendorConnection(options);
}
```

Đừng giả định mọi SDK có các method này. Nếu vendor trả một singleton toàn cục, client mượn từ container khác, object quản lý bởi app server hoặc lifecycle thuộc tổ chức khác, **Spring không nên đóng tài nguyên ngoài quyền sở hữu**. Khi đó có thể dùng `@Bean(destroyMethod = "")` để tắt suy luận destroy method.

**Lưu ý:** Container thường không tự quản lý đầy đủ callback hủy cho bean prototype sau khi cấp instance; code sử dụng cần đóng tài nguyên đúng thời điểm.

## 10. Lấy cấu hình từ bên ngoài, không hard-code secrets

Class thư viện thường cần host, credential, timeout. Phương thức `@Bean` là điểm lắp ghép tốt, nhưng secret không nên xuất hiện như chuỗi cứng trong Git.

Một ví dụ dùng Spring Environment:

```java
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ClientConfiguration {
    @Bean
    VendorClient vendorClient(Environment environment) {
        String endpoint = environment.getRequiredProperty("vendor.endpoint");
        String apiKey = environment.getRequiredProperty("vendor.api-key");

        return new VendorClient(endpoint, apiKey);
    }
}
```

`VendorClient` là kiểu minh họa. `Environment` là bean/đối tượng hạ tầng mà Spring có thể cung cấp khi thực thi factory method. `getRequiredProperty` giúp lỗi cấu hình thiếu xuất hiện sớm. Nguồn property có thể đến từ cấu hình ứng dụng, environment variables, secret store hoặc các `PropertySource` phù hợp.

Trong Spring Boot, `@ConfigurationProperties` thường hợp lý hơn cho nhiều field cấu hình, validation và test; đó là tính năng hạ tầng Boot bổ sung. Dù cách đọc cấu hình khác nhau, nguyên tắc `@Bean` vẫn là tạo/configure object SDK từ thông tin đã resolve.

**Đừng log credential** khi debug lỗi bean creation. Ghi context đủ để chẩn đoán endpoint/chế độ, nhưng che token và các giá trị nhạy cảm.

## 11. Import và tổ chức nhiều configuration class

Tách cấu hình theo nhóm là hữu ích:

```java
@Configuration(proxyBeanMethods = false)
class JsonLibraryConfig {
    @Bean
    ObjectMapper apiMapper() {
        return new ObjectMapper();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(JsonLibraryConfig.class)
class ApplicationConfig {
    @Bean
    ReportService reportService(ObjectMapper apiMapper) {
        return new ReportService(apiMapper);
    }
}
```

Đây là snippet cấu trúc khác với demo chạy ở trên: `ReportService` ở đây là kiểu giả định có constructor chỉ nhận `ObjectMapper`; cần import `Bean`, `Configuration`, `Import`, `ObjectMapper`. `@Import` giúp nạp class cấu hình chứa bean definitions. Không cần đặt `@Component` trên `ObjectMapper`.

Với ứng dụng nhiều module, mỗi nhóm thư viện có thể có configuration riêng: JSON, HTTP client, database adapter, cache hoặc message producer. Cấu hình nào được import/scan sẽ quyết định bean có xuất hiện trong context đó hay không.

**Không nhập nhằng:** `@Import(SomeConfig.class)` và `@ComponentScan` khác nhau. `@Import` khai báo trực tiếp nguồn cấu hình/type liên quan, trong khi scan tìm class theo package/filter.

## 12. Đăng ký một thư viện mà không có @Bean cũng có thể, nhưng khi nào?

Có những API đăng ký bean bằng chương trình:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.registerBean(
        "appClock",
        Clock.class,
        Clock::systemUTC
);
context.refresh();
try {
    Clock clock = context.getBean("appClock", Clock.class);
    // Dùng clock.
} finally {
    context.close();
}
```

Đây là code Java hợp lệ khi có import `java.time.Clock` và `org.springframework.context.annotation.AnnotationConfigApplicationContext` cùng Spring dependencies. `registerBean(...)` đăng ký bean definition với supplier; cũng không đòi `@Component` trên `Clock`.

Tuy nhiên, **`@Bean` thường dễ đọc và bảo trì hơn** khi dự án đã theo Java configuration. Đăng ký bằng chương trình phù hợp với bootstrap động, plugin registrar, framework integration hoặc code cần dựng context theo metadata runtime.

Có thể đăng ký instance sẵn có qua API bean factory, nhưng **vòng đời, khởi tạo và việc đóng object** cần hiểu chính xác theo API được chọn; không coi việc gán một instance vào registry như hoàn toàn tương đương với factory method `@Bean`.

## 13. Những lỗi phổ biến và hướng sửa

### 13.1. Quét đúng package của ứng dụng nhưng không thấy class từ JAR

**Triệu chứng:** inject `ObjectMapper` hoặc client SDK gây `NoSuchBeanDefinitionException`/`UnsatisfiedDependencyException`.

**Nguyên nhân:** class thư viện không mang stereotype phù hợp và không có bean definition do `@Bean`/autoconfiguration cung cấp.

**Sửa:** khai báo một method `@Bean` trả đúng type và nạp class `@Configuration` vào context. Đừng mặc định rằng mở rộng `@ComponentScan` tới package vendor sẽ giải quyết được.

### 13.2. Có @Bean nhưng class @Configuration không được nạp

Một file cấu hình chỉ nằm trong source code mà **không được register, import, scan hoặc autoconfigure** thì không tự chạy. Kiểm tra `AnnotationConfigApplicationContext(Config.class)`, `@Import`, vị trí package của Spring Boot application và condition/profile liên quan.

### 13.3. Hai instance cùng kiểu gây lỗi ambiguous dependency

Nếu có hai `ObjectMapper` và một injection point chỉ biết `ObjectMapper`, Spring có thể báo `NoUniqueBeanDefinitionException`.

**Sửa:** `@Qualifier` chọn đúng bean, hoặc `@Primary` khi thật sự có default. Nếu use case cần tất cả instance, inject `Map<String, ObjectMapper>` hoặc collection phù hợp để chủ động lựa chọn.

### 13.4. Gọi @Bean method trực tiếp với proxyBeanMethods=false

Ví dụ `new Client(mapper())` tạo thêm object `ObjectMapper` bên ngoài instance đã đăng ký khi `mapper()` dùng `new ObjectMapper()`. Điều này có thể làm cấu hình, identity hoặc lifecycle bị lệch. **Sửa:** truyền `ObjectMapper mapper` trong tham số của factory method khác.

### 13.5. Tạo client bằng new trong mỗi request

Nếu client hoặc connection pool có chi phí khởi tạo cao, tạo trực tiếp trong request handler có thể tốn tài nguyên và khó shutdown.

**Sửa:** đăng ký bean singleton **nếu class thread-safe và lifecycle phù hợp**, inject client vào service. Không tự chuyển mọi thư viện sang singleton; phải kiểm tra vendor documentation.

### 13.6. Spring đóng object do nơi khác sở hữu

Một object có `close()` công khai có thể bị Spring suy luận destroy callback, trong khi tài nguyên đó do application server hoặc bên khác quản lý. Hệ quả là đóng sớm một connection dùng chung.

**Sửa:** xác định ownership; nếu không thuộc quyền Spring, dùng `@Bean(destroyMethod = "")` hoặc cơ chế đăng ký/lifecycle phù hợp và kiểm thử shutdown.

### 13.7. Quên đóng object do Spring sở hữu

Nếu bean giữ thread/socket và cần `shutdown()` nhưng không được cấu hình destroy callback, shutdown context có thể không giải phóng tài nguyên.

**Sửa:** xác nhận API lifecycle của thư viện, cấu hình `destroyMethod` khi thích hợp, đóng context đúng cách và kiểm thử nguồn lực sau shutdown.

### 13.8. Factory method trả interface quá tổng quát

Spring có thể không dự đoán được concrete type tại các điểm injection xảy ra trước khi singleton được tạo. **Sửa:** khai báo return type đủ cụ thể hoặc thống nhất dependency injection bằng service interface.

### 13.9. Custom mapper được Spring quản lý nhưng bị thay đổi sau khi dùng

Một `ObjectMapper` dùng chung được reconfigure khi nhiều thread đang serialize. Thao tác này có thể gây lỗi khó tái hiện.

**Sửa:** cấu hình hoàn tất trước khi bean được publish cho callers; dùng instance riêng cho mỗi policy, hoặc reader/writer được tạo theo API Jackson thích hợp.

### 13.10. @Bean có rồi nhưng cho rằng @ComponentScan sẽ không tạo bean trùng

Nếu cùng class vừa được scan qua một stereotype, vừa có factory method tạo bean khác cùng type, context có thể có **hai instance khác tên** hoặc xung đột bean names.

**Sửa:** kiểm tra từng đường đăng ký, tránh đăng ký đúp, dùng tên/qualifier rõ ràng. Không dựa vào việc bean definition overriding luôn được bật vì hành vi cấu hình có thể khác theo môi trường.

### 13.11. Dùng @Bean để sửa source của thư viện

`@Bean` không gắn annotation vào class vendor, không biến mọi lời gọi `new VendorType()` trong toàn chương trình thành managed bean, và không tự thay đổi hành vi đối tượng được tạo ngoài container.

**Sửa:** mọi code cần object được cấu hình hãy **inject bean từ Spring**; hạn chế khởi tạo thủ công ở đường nghiệp vụ.

### 13.12. Dùng @ConditionalOnMissingBean trong Spring Framework thuần

`@ConditionalOnMissingBean` là annotation thuộc **Spring Boot autoconfigure**, không phải annotation lõi có sẵn trong project chỉ dependency `spring-context`.

**Sửa:** với Spring thuần, quản lý cấu hình explicit hoặc dùng `@Conditional` và một `Condition` tương ứng nếu có nhu cầu; với Boot, dùng conditional auto-configuration đúng ngữ cảnh để cung cấp default bean mà ứng dụng vẫn có thể override theo policy.

## 14. Kiểm thử và quan sát bean đăng ký

### 14.1. Kiểm tra bean names, identity và type

Ví dụ hoàn chỉnh ở mục 5 đã dùng:

```java
context.containsBean("compactMapper");
context.getBeansOfType(ObjectMapper.class).size();
context.getBean("compactMapper", ObjectMapper.class);
```

Ba phép quan sát kiểm tra sự tồn tại, số lượng và instance. Khi thêm bean cùng kiểu, nên kiểm tra cả tên và cách resolve injection point, vì `getBean(ObjectMapper.class)` có thể mơ hồ dù `containsBean("compactMapper")` trả true.

### 14.2. Kiểm tra bean definition đến từ đâu

```java
var beanFactory = context.getBeanFactory();
var definition = beanFactory.getBeanDefinition("compactMapper");

System.out.println(definition.getFactoryMethodName());
```

Đây là snippet để đặt trong `try` của demo; kết quả từ bean definition `@Bean("compactMapper") ObjectMapper compactMapper()` thông thường là `compactMapper`. Có thể xem `getResourceDescription()` để truy dấu configuration, nhưng chuỗi cụ thể thay đổi theo môi trường.

### 14.3. Kiểm tra đường injection thay vì chỉ getBean()

Một test tốt nên xác nhận `ReportService.buildReport()` thực sự xuất JSON compact. Nếu vô tình tiêm `prettyMapper`, output sẽ có indent/xuống dòng và khác kết quả mong đợi. Đây là tín hiệu trực tiếp rằng `@Qualifier` hoặc assembly đã sai.

### 14.4. Test scope và lifecycle

- Với singleton, hai lời gọi `getBean("compactMapper")` trong cùng context trả cùng instance.
- Với prototype được cấu hình trên method `@Bean`, hai lookup thông thường tạo instance khác; không nên gán trạng thái cho cả hai rồi nghĩ sẽ tự chia sẻ.
- Với client có `close`/`shutdown`, test đóng context và quan sát callback/tài nguyên được giải phóng.
- Với tài nguyên externally owned, test rằng đóng context **không** đóng đối tượng ấy nếu đã tắt destroy callback.

### 14.5. Test thiếu dependency và cấu hình sai

Nếu factory method cần `Environment.getRequiredProperty(...)` mà property không tồn tại, lỗi khi bean được tạo là kỳ vọng hợp lý cho dependency bắt buộc. Nếu secret sai hoặc vendor client không kết nối được, đừng sửa bằng cách catch rộng rồi trả `null` từ `@Bean`; hãy phân loại lỗi cấu hình, lỗi mạng và chính sách retry theo từng thư viện.

## 15. Mẫu thiết kế cho các loại thư viện khác nhau

### 15.1. JSON serializer

`@Bean ObjectMapper` là đối tượng chia sẻ nếu cấu hình được hoàn tất trước khi sử dụng. Có thể đăng ký nhiều mapper cho các policy độc lập và tiêm bằng qualifier, như ví dụ chạy được.

### 15.2. HTTP client

Một HTTP client thường nên dùng lại connection/thread resources khi thư viện khuyến nghị. Tạo bằng builder từ timeout, TLS và endpoint configuration rồi đăng ký `@Bean`; lựa chọn scope và shutdown method theo tài liệu vendor. Không giả định mọi HTTP client đều giống nhau về thread safety và lifecycle.

### 15.3. DataSource/connection pool

Một `DataSource` có thể được tạo bằng factory/builder của thư viện pool và đăng ký qua `@Bean`. Cần cung cấp driver, URL, authentication và xác định rõ ai sở hữu pool. Trong Spring Boot, thường đã có auto-configuration cho `DataSource`; đừng đăng ký thủ công trùng với bean có sẵn nếu không có chủ ý.

### 15.4. SDK client bên thứ ba

Đăng ký qua `@Bean` cho phép tập trung endpoint, timeout, token provider và retry policy tại một chỗ. Nếu SDK có nhiều tài khoản/region, đặt tên từng bean và chọn bằng `@Qualifier`. Đừng nhét token vào constructor trong source; lấy qua secure configuration.

### 15.5. Test doubles

Có thể thay `@Bean` factory method để cấp fake/stub ở test context mà không chỉnh sửa code thư viện:

```java
@Configuration(proxyBeanMethods = false)
class TestClockConfig {
    @Bean
    Clock clock() {
        return Clock.fixed(
            Instant.parse("2030-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Đoạn này là một class cấu hình hợp lệ khi thêm import `Bean`, `Configuration`, `Clock`, `Instant`, `ZoneOffset`. Hãy nạp **một** cấu hình clock phù hợp cho test context thay vì vô tình tạo hai `Clock` cùng type và gây mơ hồ injection. Với các object không dễ fake, hãy thiết kế adapter/interface do ứng dụng sở hữu rồi đăng ký adapter dùng SDK qua `@Bean`.

## 16. Tự luyện và đáp án

**Câu 1.** Vì sao chỉ thêm `@ComponentScan(basePackages="com.fasterxml.jackson")` không phải cách thông thường để tạo `ObjectMapper`?

**Đáp:** Default component scanning tìm các class mang stereotype hoặc marker phù hợp; `ObjectMapper` không cần và không được thiết kế như Spring component. Khai báo `@Bean ObjectMapper ...` cho phép ứng dụng chủ động cấu hình instance.

**Câu 2.** Dự án không có `@ComponentScan` nhưng đã đăng ký `@Configuration` với factory method `@Bean`. Object có được Spring quản lý không?

**Đáp:** Có, nếu configuration được nạp/xử lý và bean được tạo thành công. Component scanning chỉ là một trong các đường đăng ký bean.

**Câu 3.** Trong demo có hai `ObjectMapper`. Vì sao factory method `reportService(@Qualifier("compactMapper") ObjectMapper mapper, ...)` không bị mơ hồ?

**Đáp:** Qualifier thu hẹp candidate theo bean có tên tương ứng; Spring đưa đúng mapper compact cho service.

**Câu 4.** Nếu bỏ `@Qualifier` trong demo, điều gì có thể xảy ra?

**Đáp:** Có hai mapper cùng type mà không có một ứng viên mặc định được phân định rõ, nên dependency injection có thể báo `NoUniqueBeanDefinitionException`. Không dựa vào tên biến để làm quy tắc cấu hình bắt buộc; dùng qualifier rõ ràng.

**Câu 5.** Hai lần `context.getBean("compactMapper")` có tạo hai mapper không?

**Đáp:** Không ở scope singleton mặc định; cùng tên bean trong cùng context trả cùng instance. Đổi scope sang prototype mới làm hai lookup thông thường tạo hai instance.

**Câu 6.** Vì sao `@Configuration(proxyBeanMethods=false)` nên đi cùng parameter injection trên `@Bean` methods?

**Đáp:** Vì gọi trực tiếp method `@Bean` khác là lời gọi Java thông thường, có thể tạo thêm instance ngoài bean đã đăng ký. Tham số method được container resolve theo tên/type/qualifier và scope.

**Câu 7.** Object thư viện có method `close()`. Có thể mặc định Spring được phép đóng nó khi context shutdown không?

**Đáp:** Cần xác định ownership. Spring có cơ chế suy luận destroy callback cho phương thức close/shutdown thích hợp, nhưng với object do môi trường khác quản lý có thể phải tắt qua `destroyMethod=""`. Không coi việc có `close()` là bằng chứng Spring sở hữu tài nguyên.

**Câu 8.** Vì sao một factory method khai báo return type là interface có thể làm một injection point theo concrete class khó resolve sớm?

**Đáp:** Spring dự đoán type từ metadata của factory method trước khi instance được tạo; nếu declared return type quá tổng quát, concrete type có thể chưa biết. Khai báo return type đủ cụ thể hoặc inject nhất quán theo interface.

**Câu 9.** Nếu muốn cấu hình một singleton vendor client khác trong test, có bắt buộc sửa source thư viện không?

**Đáp:** Không. Dùng Java configuration riêng của test để trả fake/đối tượng cấu hình khác, hoặc cấp bean phù hợp theo chính sách test context và tránh đăng ký trùng ngoài ý muốn.

**Câu 10.** `@Bean` có tự khiến method của client thư viện chạy trong transaction hay được cache không?

**Đáp:** Không. `@Bean` chỉ đăng ký/cấu hình object trong IoC Container. Transaction, caching và hành vi proxy cần hạ tầng, annotation, invocation path và dependency thích hợp riêng.

## 17. Nguồn tham khảo

- [Spring Framework 6.2 — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html): tổng quan cách cấu hình bean bằng Java.
- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): ý nghĩa bean factory methods và full/lite configuration.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): tham số factory method, bean name, scope, lifecycle, init/destroy callbacks.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): dependency giữa các bean, method interception và `proxyBeanMethods=false`.
- [Spring Framework 6.2 — Container Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies.html): cách container resolve dependency.
- [Jackson Databind — ObjectMapper API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.18.2/com/fasterxml/jackson/databind/ObjectMapper.html): API mapper dùng trong bài.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definition, metadata và cách Spring quản lý instance.

**Tóm tắt kiến thức cốt lõi:** Khi thư viện không có `@Component`, ta tạo bean definition bằng **`@Bean`** trên một configuration được Spring nạp. Factory method tạo/cấu hình object; IoC Container quản lý dependency, scope và lifecycle theo cấu hình. Component scanning dành cho việc tìm các class ứng viên có marker phù hợp, còn `@Bean` là công cụ lắp ghép chủ động các đối tượng thư viện mà ta không sửa source được.
