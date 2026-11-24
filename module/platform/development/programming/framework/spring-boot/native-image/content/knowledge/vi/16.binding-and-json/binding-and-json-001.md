# @ConfigurationProperties, constructor binding và kiểu dữ liệu lồng nhau

## 1. Vì sao cần binding cấu hình có kiểu?

Ứng dụng Spring Boot thường nhận cấu hình từ `application.yml`, `application.properties`, environment variables, system properties, command-line arguments hoặc nguồn cấu hình bên ngoài. Nếu đọc từng giá trị bằng `@Value` hoặc gọi trực tiếp `Environment.getProperty()`, cấu hình dễ bị phân tán và khó kiểm tra tính hợp lệ.

**`@ConfigurationProperties`** gom các property có cùng prefix thành một object Java có kiểu. Nó hỗ trợ chuyển đổi kiểu dữ liệu, cấu trúc lồng nhau, danh sách, map và tích hợp validation. Với constructor binding, object cấu hình có thể bất biến sau khi tạo, giúp biểu diễn rõ dữ liệu đầu vào mà ứng dụng cần.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, binding còn cần được nhìn nhận trong quy trình Spring AOT. Spring AOT phân tích ApplicationContext và các bean cấu hình, sau đó sinh mã phục vụ khởi tạo. Dùng cấu hình properties được khai báo tường minh, có kiểu và được đăng ký trong context giúp cấu trúc ứng dụng dễ phân tích, kiểm thử và đóng gói native hơn.

## 2. Tạo configuration properties với prefix

Ví dụ ứng dụng xử lý đơn hàng cần các cấu hình:

```yaml
orders:
  service-name: order-api
  enabled: true
  timeout: 3s
  max-items: 100
```

Có thể ánh xạ vào class:

```java
@ConfigurationProperties(prefix = "orders")
public class OrdersProperties {

    private String serviceName;
    private boolean enabled;
    private Duration timeout;
    private int maxItems;

    // getters và setters
}
```

Spring Boot relaxed binding ánh xạ tên property như `service-name` vào thuộc tính Java `serviceName`. Các kiểu như `boolean`, `int` và `Duration` được chuyển đổi từ chuỗi cấu hình theo conversion service của Spring Boot.

Không nên dùng một class properties khổng lồ chứa cấu hình của nhiều subsystem. Tách theo prefix và trách nhiệm giúp cấu hình rõ ràng, dễ validate và dễ quản lý theo môi trường.

## 3. Đăng ký configuration properties vào ApplicationContext

Có hai cách phổ biến để Spring phát hiện class có `@ConfigurationProperties`.

### Dùng configuration properties scan

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

Scan mặc định bắt đầu từ package của application class và các package con. Nếu properties class nằm ngoài phạm vi đó, chỉ định package hoặc class cần scan theo API phù hợp.

### Dùng @EnableConfigurationProperties

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(OrdersProperties.class)
class OrdersConfiguration {
}
```

Cách này đăng ký rõ class properties cụ thể, phù hợp khi muốn kiểm soát danh sách type được đưa vào context.

Chỉ đặt `@ConfigurationProperties` trên class không có nghĩa bean chắc chắn tự được đăng ký trong mọi cấu trúc ứng dụng. Phải có cơ chế scan hoặc enable tương ứng.

## 4. Constructor binding và cấu hình bất biến

Constructor binding để Spring tạo object bằng cách truyền các giá trị cấu hình vào constructor. Với Spring Boot 3, một class có một constructor duy nhất thường được dùng cho constructor binding mà không cần thêm `@ConstructorBinding`. Với nhiều constructor, có thể cần đánh dấu constructor được chọn bằng annotation `@ConstructorBinding` thuộc package `org.springframework.boot.context.properties.bind` theo phiên bản tương ứng.

Ví dụ Java record:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        String serviceName,
        boolean enabled,
        Duration timeout,
        int maxItems) {
}
```

Record có canonical constructor và các accessor được sinh tự động. Khi dùng record, không cần viết getter/setter thủ công. Object được tạo với giá trị cấu hình và không thể thay đổi component sau khi khởi tạo.

Ưu điểm của constructor binding:

- Object cấu hình có trạng thái bất biến.
- Các giá trị cần thiết được thể hiện ngay trong constructor signature.
- Dễ viết unit test bằng cách tạo object trực tiếp.
- Tránh trạng thái cấu hình nửa khởi tạo do setter chưa được gọi đầy đủ.

Với Java class thông thường, có thể dùng constructor cùng các field final. Không kết hợp constructor binding với setter binding một cách tùy tiện; chọn mô hình binding rõ ràng theo phiên bản Spring Boot.

## 5. Kiểu dữ liệu lồng nhau

Cấu hình thực tế thường có nhóm thuộc tính liên quan. Ví dụ:

```yaml
orders:
  service-name: order-api
  enabled: true
  client:
    base-url: https://inventory.internal
    connect-timeout: 2s
    read-timeout: 5s
  retry:
    max-attempts: 3
    backoff: 500ms
```

Mô hình Java có thể dùng record lồng nhau:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        String serviceName,
        boolean enabled,
        Client client,
        Retry retry) {

    public record Client(
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout) {
    }

    public record Retry(
            int maxAttempts,
            Duration backoff) {
    }
}
```

Spring Boot binder ánh xạ `orders.client.base-url` vào component `client.baseUrl`, và tương tự với `retry`. Việc chia nhóm giúp phân biệt cấu hình kết nối với cấu hình retry.

Với kiểu lồng nhau, cần xác định hành vi khi cả nhóm bị thiếu. Nếu object con bắt buộc phải có, validation hoặc default value cần được thiết kế rõ; đừng giả định mọi nested object tự có giá trị mặc định khi không có property tương ứng.

## 6. Giá trị mặc định cho nested object

Spring Boot hỗ trợ `@DefaultValue` trong constructor binding để cung cấp giá trị mặc định khi property tương ứng không được cấu hình. Ví dụ:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        String serviceName,
        @DefaultValue("true") boolean enabled,
        @DefaultValue Client client) {

    public record Client(
            @DefaultValue("2s") Duration connectTimeout,
            @DefaultValue("5s") Duration readTimeout) {
    }
}
```

`@DefaultValue` không có giá trị trên tham số nested object có thể yêu cầu binder tạo object con ngay cả khi không có property con nào. Cách này hữu ích khi muốn `client` không null với default timeout.

Nếu nested object phải được cung cấp đầy đủ, có thể không đặt default và dùng validation để từ chối cấu hình thiếu. Chọn một chính sách nhất quán: default an toàn cho môi trường phát triển, hoặc bắt buộc khai báo trong môi trường production.

## 7. Danh sách và map trong cấu hình

Configuration properties hỗ trợ collection. Ví dụ YAML:

```yaml
orders:
  allowed-regions:
    - north
    - central
    - south
  limits:
    basic: 100
    premium: 1000
```

Record:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        List<String> allowedRegions,
        Map<String, Integer> limits) {
}
```

Binder chuyển danh sách và map từ cấu trúc property sources sang kiểu Java. Có thể dùng collection lồng trong nested record để mô hình hóa routing, tenant, feature hoặc giới hạn theo nhóm.

Lưu ý thứ tự và cách merge collection giữa các property source có quy tắc riêng. Khi profile-specific config hoặc environment override danh sách, không nên giả định các giá trị luôn được nối thêm; cần kiểm tra hành vi binding của Spring Boot version và test cấu hình thực tế.

## 8. Validation cho cấu hình

Cấu hình sai nên bị phát hiện sớm lúc tạo ApplicationContext thay vì gây lỗi ở request đầu tiên. Có thể dùng Jakarta Bean Validation:

```java
@ConfigurationProperties(prefix = "orders")
@Validated
public record OrdersProperties(
        @NotBlank String serviceName,
        @Min(1) int maxItems,
        @Valid Client client) {

    public record Client(
            @NotNull URI baseUrl,
            @NotNull Duration connectTimeout) {
    }
}
```

Cần dependency validation phù hợp, thường là `spring-boot-starter-validation`, và import các annotation từ `jakarta.validation.constraints`. `@Valid` yêu cầu validation đi tiếp vào object lồng nhau; nếu thiếu, constraint trên nested object có thể không được kiểm tra như mong muốn.

Một số quy tắc hữu ích:

- `@NotBlank` cho chuỗi bắt buộc không được rỗng.
- `@Min`/`@Max` cho số nguyên trong giới hạn.
- `@NotNull` cho object/URI/Duration bắt buộc.
- `@Valid` để kiểm tra cấu trúc lồng nhau.
- Custom constraint khi quy tắc nghiệp vụ không biểu diễn được bằng annotation có sẵn.

Nếu validation thất bại, Spring Boot thường báo lỗi khi bind/khởi tạo configuration bean. Đây là thời điểm tốt để fail-fast trước khi nhận traffic.

## 9. Chuyển đổi kiểu và định dạng giá trị

Spring Boot hỗ trợ conversion cho nhiều kiểu thường dùng như `Duration`, `DataSize`, enum, URI và các kiểu số. Ví dụ:

```yaml
orders:
  timeout: 2500ms
  payload-limit: 10MB
  endpoint: https://orders.internal/api
  mode: STRICT
```

Record:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        Duration timeout,
        DataSize payloadLimit,
        URI endpoint,
        Mode mode) {

    enum Mode {
        STRICT, RELAXED
    }
}
```

Dùng kiểu domain phù hợp thay vì giữ mọi giá trị dưới dạng String rồi parse rải rác trong service. Khi cần định dạng đặc biệt, có thể đăng ký converter theo cơ chế Spring Boot configuration properties binding được hỗ trợ.

Cần kiểm tra đơn vị rõ ràng: `2500ms` và `2s` biểu diễn cùng khoảng thời gian, còn `10MB` là kích thước dữ liệu. Tránh số không đơn vị khi không rõ default unit.

## 10. Phân biệt binding với @Value

| Tiêu chí | `@ConfigurationProperties` | `@Value` |
|---|---|---|
| Phạm vi | Nhóm property theo prefix | Một giá trị hoặc expression |
| Nested object | Hỗ trợ trực tiếp | Phải tự kết hợp nhiều field |
| Validation | Tích hợp Bean Validation | Thường cần xử lý riêng |
| Metadata IDE | Có thể sinh configuration metadata | Hạn chế hơn |
| Constructor binding | Hỗ trợ object bất biến | Có thể inject vào constructor nhưng không tạo nhóm properties |
| SpEL | Không dùng SpEL cho property binding thông thường | Hỗ trợ SpEL |
| Phù hợp | Cấu hình có cấu trúc | Một vài giá trị riêng lẻ |

Ví dụ `@Value("${server.port}")` hợp lý cho một giá trị đơn giản trong bean. Khi có nhiều property liên quan như timeout, endpoint, retry, credentials reference và limits, `@ConfigurationProperties` dễ quản lý hơn.

Không nên thay tất cả `@Value` trong ứng dụng bằng configuration properties nếu nhóm đó chỉ có một giá trị và không cần abstraction riêng.

## 11. Binding và Spring AOT

Spring AOT phân tích ApplicationContext trong build phase. Configuration properties được đăng ký như bean trong context và có metadata kiểu rõ ràng, vì vậy Spring có thể chuẩn bị code khởi tạo tương ứng. Constructor binding cũng làm rõ các dependency đầu vào cần thiết để tạo object.

Để AOT nhận biết properties:

- Đăng ký class qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
- Giữ constructor signature và nested type cụ thể.
- Tránh tạo configuration bean bằng reflection tùy biến không có metadata.
- Đảm bảo property/profile dùng để đánh giá cấu trúc bean được cung cấp đúng cho bước AOT.
- Dùng validation để phát hiện cấu hình không hợp lệ sớm.

Spring Boot cung cấp hỗ trợ AOT cho nhiều trường hợp configuration properties phổ biến. Không nên tự thêm reflection hints cho mọi properties class nếu framework đã xử lý. Nếu một thư viện hoặc custom binder dùng reflection ngoài đường đi được Spring hỗ trợ, kiểm tra native diagnostics và bổ sung RuntimeHints/metadata cần thiết.

## 12. Metadata cho IDE và cấu hình dễ khám phá

Spring Boot configuration processor có thể sinh metadata JSON để IDE gợi ý tên property, type và description. Với Maven hoặc Gradle, thêm annotation processor phù hợp:

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Gradle:

```groovy
annotationProcessor(
    "org.springframework.boot:spring-boot-configuration-processor"
)
```

Metadata thường được sinh vào `META-INF/spring-configuration-metadata.json` trong output build. Đây là metadata hỗ trợ tooling/documentation, không phải thay thế RuntimeHints hoặc reachability metadata của GraalVM.

Có thể bổ sung description/default value trong metadata nếu cần tài liệu hóa property cho người vận hành. Không ghi secret hoặc giá trị nhạy cảm vào metadata.

## 13. Kiểm thử configuration properties

Có thể kiểm tra binding trực tiếp hoặc khởi tạo ApplicationContext. Ví dụ với Spring Boot test:

```java
@SpringBootTest(properties = {
        "orders.service-name=order-api",
        "orders.enabled=true",
        "orders.client.connect-timeout=2s"
})
class OrdersPropertiesTest {

    @Autowired
    OrdersProperties properties;

    @Test
    void bindsNestedValues() {
        assertThat(properties.serviceName()).isEqualTo("order-api");
        assertThat(properties.client().connectTimeout())
                .isEqualTo(Duration.ofSeconds(2));
    }
}
```

Ví dụ giả định `OrdersProperties` đã được đăng ký trong context, và nested client được tạo theo cấu hình đã cung cấp. Với record có nested object bắt buộc, test cần khai báo đủ property hoặc default tương ứng.

Nên có test cho:

- Giá trị mặc định khi property thiếu.
- Nested object và nested collection.
- Chuyển đổi `Duration`, `DataSize`, enum và URI.
- Validation khi thiếu hoặc sai giá trị.
- Override qua profile/environment/command line.
- Cấu hình AOT được chọn cho từng biến thể structural.

## 14. Native Image: kiểm thử binding trên executable

Một test pass trên JVM không tự chứng minh binding hoạt động đúng trên native. Sau khi cấu hình AOT và build native, cần chạy executable với cùng bộ cấu hình kiểm thử.

Quy trình:

1. Chạy JVM integration tests với profile và property đã ghi nhận.
2. Chạy Spring AOT qua Maven/Gradle plugin phù hợp.
3. Build Native Image.
4. Chạy binary với file cấu hình classpath và external config tương ứng.
5. Xác minh nested values, defaults, conversion và validation.
6. Chạy container với environment variables hoặc mounted config file.
7. Đối chiếu kết quả JVM/native.

Nếu cấu hình property chỉ cung cấp giá trị runtime như URL hoặc timeout, có thể chạy cùng binary với giá trị khác nhau nếu cấu trúc bean không thay đổi. Nếu property dùng `@ConditionalOnProperty` để bật/tắt configuration class, giá trị đó có thể ảnh hưởng cấu trúc AOT và cần được cố định phù hợp khi build.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Properties bean không được inject | Chưa scan/enable class | Thêm `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Nested object null | Không có property/default và nested binding chưa được khởi tạo | Dùng `@DefaultValue` phù hợp hoặc bắt buộc cấu hình |
| Constructor binding không hoạt động | Nhiều constructor hoặc annotation đặt sai | Xác định constructor binding theo Spring Boot version |
| Property không bind | Sai prefix, tên hoặc nguồn property | Kiểm tra relaxed binding và effective Environment |
| Duration/DataSize sai | Thiếu hoặc sai unit | Dùng đơn vị rõ ràng như `2500ms`, `10MB` |
| Validation không chạy ở nested object | Thiếu `@Valid` hoặc validation dependency | Bổ sung annotation và starter validation |
| JVM pass, native lỗi binder/custom converter | Đường reflection/type động ngoài hỗ trợ mặc định | Xem native diagnostics, bổ sung hints nếu thực sự cần |
| Native dùng cấu hình khác dự kiến | Structural property/profile khác lúc AOT | Ghi nhận và truyền đúng property vào AOT phase |

Khi debug, kiểm tra theo thứ tự: class đã được đăng ký chưa, prefix/property source đúng không, constructor/nested type có hợp lệ không, validation có chạy không, rồi mới xem xét vấn đề AOT/native metadata.

## 16. Bài thực hành: xây dựng cấu hình đơn hàng lồng nhau

**Bối cảnh:** dịch vụ order API cần endpoint inventory, timeout, retry policy và danh sách region được phép.

**Bước 1 — Tạo YAML.** Khai báo `orders.client`, `orders.retry`, `orders.allowed-regions` và các giá trị cần thiết.

**Bước 2 — Tạo record properties.** Dùng `@ConfigurationProperties(prefix = "orders")`, nested records cho client/retry và `List<String>` cho regions.

**Bước 3 — Đăng ký properties.** Dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

**Bước 4 — Thêm validation.** Kiểm tra URL không null, timeout dương, max attempts tối thiểu 1 và service name không rỗng.

**Bước 5 — Viết tests.** Test binding, default, nested values, collection, conversion và validation failure.

**Bước 6 — Chạy Spring AOT và native build.** Quan sát AOT, build executable và xác minh properties bean được tạo đúng.

**Bước 7 — Chạy trong container.** Cấp external config qua environment/mount; đổi endpoint và timeout mà không build lại khi chúng chỉ là runtime values.

Tiêu chí hoàn thành: properties được bind đúng kiểu, nested objects hoạt động, validation fail-fast, cấu hình runtime thay đổi được theo thiết kế và native executable có hành vi tương đương JVM.

## 17. Kết luận

`@ConfigurationProperties` cung cấp cách tổ chức cấu hình Spring Boot có kiểu, có prefix và hỗ trợ nested object, collection, conversion cùng validation. Constructor binding, đặc biệt với Java records, giúp tạo cấu hình bất biến và thể hiện rõ các giá trị cần có khi khởi tạo.

Trong Spring Boot Native Image, hãy đăng ký configuration properties rõ ràng trong ApplicationContext, phân biệt runtime values với property quyết định cấu trúc bean, kiểm tra validation và chạy cùng bộ test trên native executable. Cấu hình có kiểu và được kiểm thử giúp ứng dụng dễ vận hành qua nhiều môi trường mà không phụ thuộc vào các thao tác binding động khó phân tích.
