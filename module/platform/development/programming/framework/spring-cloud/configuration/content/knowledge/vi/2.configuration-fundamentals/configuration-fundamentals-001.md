# Spring Environment và các lớp PropertySource

Trong một hệ thống Spring Boot, cấu hình có thể đến từ nhiều nơi: tệp `application.yml`, biến môi trường, tham số dòng lệnh, thuộc tính JVM, cấu hình theo profile hoặc một Spring Cloud Config Server ở xa. Ứng dụng cần một cách thống nhất để đọc các giá trị đó và một quy tắc rõ ràng để quyết định giá trị nào được sử dụng khi nhiều nguồn cùng khai báo một khóa.

Spring cung cấp `Environment` để giải quyết bài toán này. `Environment` đại diện cho môi trường chạy của ứng dụng, hỗ trợ đọc thuộc tính và xác định profile đang hoạt động. Các giá trị thực tế được đóng gói trong những đối tượng `PropertySource`. Hiểu mối quan hệ giữa hai thành phần này là nền tảng để thiết kế cấu hình tập trung, dự đoán được hành vi ghi đè và vận hành Spring Cloud Config Client an toàn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của `Environment`, `PropertyResolver` và `ConfigurableEnvironment`.
- Mô tả `PropertySource` và cách Spring tìm giá trị theo thứ tự ưu tiên.
- Phân biệt cấu hình của Spring Framework với cơ chế nạp cấu hình của Spring Boot.
- Đọc cấu hình bằng `Environment`, `@Value` và `@ConfigurationProperties`.
- Giải thích cách profile và Spring Cloud Config Client đưa cấu hình vào `Environment`.
- Điều tra một giá trị cấu hình bị ghi đè mà không làm lộ bí mật.

## 1. Vì sao cần Environment?

Giả sử dịch vụ `catalog-service` cần biết địa chỉ API của hệ thống tìm kiếm và thời gian chờ kết nối. Khi chạy trên máy lập trình, dịch vụ gọi API cục bộ; khi chạy ở môi trường kiểm thử, dịch vụ gọi API kiểm thử; khi chạy ở production, dịch vụ gọi API production.

Nếu mã nguồn tự đọc tệp, biến môi trường và tham số dòng lệnh ở nhiều vị trí, logic cấu hình sẽ bị phân tán. Một lớp có thể đọc biến `SEARCH_URL`, lớp khác đọc `search.url`, còn lớp thứ ba dùng một giá trị mặc định được viết cứng. Khi vận hành, rất khó biết nguồn nào đang quyết định giá trị cuối cùng.

`Environment` gom việc tra cứu thuộc tính vào một giao diện thống nhất. Mã ứng dụng hỏi `Environment` một khóa như `catalog.search.base-url`; Spring sẽ tìm khóa đó trong các nguồn cấu hình đã đăng ký và trả về giá trị có độ ưu tiên cao nhất.

```text
application.yml ───────┐
application-prod.yml ──┤
Biến môi trường ───────┤
Thuộc tính JVM ────────┼──> Environment ──> Mã ứng dụng
Tham số dòng lệnh ────┤
Spring Cloud Config ──┘
```

## 2. Environment là gì?

Trong Spring Framework, `Environment` là giao diện mô tả môi trường mà `ApplicationContext` đang chạy. Nó kết hợp hai nhóm khả năng:

1. **Tra cứu thuộc tính:** tìm giá trị theo tên, chuyển kiểu dữ liệu cơ bản và giải quyết placeholder như `${catalog.search.base-url}`.
2. **Quản lý profile:** cho biết profile nào đang hoạt động và hỗ trợ kiểm tra một cấu hình có áp dụng cho profile hiện tại hay không.

`Environment` kế thừa `PropertyResolver`, vì vậy có các phương thức tra cứu thường dùng:

| Phương thức | Công dụng |
|---|---|
| `getProperty(key)` | Lấy giá trị dưới dạng `String`; trả về `null` nếu không tìm thấy. |
| `getProperty(key, defaultValue)` | Lấy giá trị hoặc dùng giá trị mặc định. |
| `getProperty(key, TargetType.class)` | Lấy giá trị và yêu cầu chuyển sang kiểu đích. |
| `getRequiredProperty(key)` | Lấy giá trị bắt buộc; ném ngoại lệ nếu thiếu. |
| `containsProperty(key)` | Kiểm tra khóa có tồn tại hay không. |
| `resolvePlaceholders(text)` | Thay placeholder `${...}` nếu tìm thấy; placeholder chưa giải quyết có thể được giữ nguyên. |
| `resolveRequiredPlaceholders(text)` | Giải quyết placeholder và báo lỗi nếu còn khóa bắt buộc chưa được tìm thấy. |

Ví dụ đọc cấu hình trong một bean:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CatalogRuntimeSettings {
    private final String searchBaseUrl;
    private final int connectTimeoutSeconds;

    public CatalogRuntimeSettings(Environment environment) {
        this.searchBaseUrl = environment.getRequiredProperty(
            "catalog.search.base-url"
        );
        this.connectTimeoutSeconds = environment.getProperty(
            "catalog.search.connect-timeout-seconds",
            Integer.class,
            3
        );
    }
}
```

Ở đây, bean không cần biết giá trị đến từ tệp YAML, biến môi trường hay Config Server. Nó chỉ phụ thuộc vào hợp đồng tra cứu của `Environment`.

### Environment và ConfigurableEnvironment

`Environment` chủ yếu cung cấp khả năng đọc thuộc tính và kiểm tra profile. Khi cần cấu hình chính đối tượng môi trường, Spring cung cấp `ConfigurableEnvironment`, một giao diện mở rộng có thêm khả năng:

- Truy cập danh sách nguồn thông qua `getPropertySources()`.
- Thêm hoặc thay đổi active profile và default profile.
- Truy cập các thuộc tính hệ thống và biến môi trường.
- Kết hợp môi trường trong một số tình huống tạo hoặc lồng `ApplicationContext`.

Trong ứng dụng Spring Boot, môi trường cụ thể được tạo trong quá trình khởi động. Loại môi trường phụ thuộc vào kiểu ứng dụng, chẳng hạn ứng dụng web servlet hoặc ứng dụng không chạy servlet. Khi viết mã nghiệp vụ, thông thường chỉ cần tiêm `Environment`; chỉ dùng `ConfigurableEnvironment` trong thành phần hạ tầng cần can thiệp vào quá trình khởi tạo.

## 3. PropertySource đóng gói một nguồn cấu hình

`PropertySource<T>` là lớp trừu tượng đại diện cho một nguồn thuộc tính. Mỗi đối tượng có:

- Một tên để nhận diện nguồn.
- Một đối tượng nguồn dữ liệu, chẳng hạn `Map`, `Properties`, thuộc tính JVM hoặc biến môi trường.
- Cách tra cứu một khóa trong nguồn dữ liệu đó.

Một `Environment` thường chứa nhiều `PropertySource`. Danh sách này được quản lý bởi `MutablePropertySources`. Các nguồn được sắp xếp theo thứ tự; khi nhiều nguồn có cùng khóa, nguồn đứng trước trong danh sách được kiểm tra trước và cung cấp giá trị được chọn.

Ví dụ, hai nguồn cùng khai báo `catalog.search.connect-timeout-seconds`:

```text
1. commandLineArgs: 8
2. systemEnvironment: 5
3. applicationConfig: [classpath:/application.yml]: 3
```

Kết quả tra cứu là `8`, vì nguồn `commandLineArgs` được ưu tiên trước hai nguồn còn lại. Spring không tự cộng hoặc hợp nhất các giá trị cùng khóa; với một khóa đơn, nguồn đầu tiên tìm thấy khóa sẽ quyết định kết quả.

### Một số loại PropertySource thường gặp

| Loại nguồn | Dữ liệu thường được bọc |
|---|---|
| `MapPropertySource` | Một `Map<String, Object>`, hữu ích cho cấu hình được tạo trong mã hoặc trong kiểm thử. |
| `PropertiesPropertySource` | Một đối tượng `java.util.Properties`. |
| `SystemEnvironmentPropertySource` | Các biến môi trường của tiến trình. |
| `StubPropertySource` | Nguồn tạm được dùng trong một số giai đoạn khởi tạo, trước khi dữ liệu thật sẵn sàng. |
| `CompositePropertySource` | Nhiều nguồn con được nhóm thành một nguồn tổng hợp. |

Ngoài ra, Spring có `EnumerablePropertySource` cho nguồn có thể liệt kê tên các khóa. Không phải nguồn nào cũng hỗ trợ liệt kê toàn bộ khóa; vì vậy, không nên giả định mọi `PropertySource` đều có thể được duyệt như một `Map`.

### Minh họa một PropertySource tự tạo

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;

Map<String, Object> overrides = Map.of(
    "catalog.search.connect-timeout-seconds", 6,
    "catalog.search.enabled", true
);

MapPropertySource source = new MapPropertySource(
    "catalogLocalOverrides",
    overrides
);
```

Đoạn mã trên chỉ tạo nguồn dữ liệu. Để nguồn tham gia tra cứu, thành phần hạ tầng phải đăng ký nó vào `ConfigurableEnvironment` trước khi các bean cần cấu hình được khởi tạo. Không nên thêm các nguồn ghi đè tùy tiện từ mã nghiệp vụ vì điều đó làm thứ tự cấu hình khó quan sát và khó kiểm soát.

## 4. Thứ tự ưu tiên và quy tắc ghi đè

Thứ tự của `PropertySource` quyết định giá trị cuối cùng khi nhiều nguồn cùng khai báo một khóa. Có hai điểm cần phân biệt:

- Spring Framework cung cấp cơ chế sắp xếp và tra cứu nguồn.
- Spring Boot quyết định nhiều nguồn cấu hình nào được tạo ra trong quá trình khởi động và cách chúng được đưa vào `Environment`.

Với ứng dụng Spring Boot thông thường, có thể hình dung các nguồn phổ biến theo thứ tự từ ưu tiên thấp đến cao như sau. Đây là bản đồ định hướng; thứ tự đầy đủ còn phụ thuộc phiên bản Boot, loại ứng dụng, môi trường kiểm thử và cách nạp Config Data.

| Mức ưu tiên tương đối | Nguồn phổ biến | Ví dụ |
|---|---|---|
| Thấp | Giá trị mặc định do ứng dụng đặt | `SpringApplication.setDefaultProperties(...)` |
| | `@PropertySource` | Tệp properties được khai báo trên cấu hình Spring |
| | Config Data | `application.yml`, `application.properties` và tệp theo profile |
| | Biến môi trường của hệ điều hành | `CATALOG_SEARCH_CONNECTTIMEOUTSECONDS=5` |
| | Thuộc tính hệ thống JVM | `-Dcatalog.search.connect-timeout-seconds=7` |
| | Dữ liệu JNDI hoặc tham số servlet, nếu ứng dụng có sử dụng | Thuộc tính do container cung cấp |
| | `SPRING_APPLICATION_JSON` | JSON được truyền qua biến môi trường hoặc thuộc tính JVM |
| Cao | Tham số dòng lệnh của Spring Boot | `--catalog.search.connect-timeout-seconds=9` |
| Rất cao trong kiểm thử | Các nguồn thuộc tính dành cho test | `@DynamicPropertySource`, `@TestPropertySource` hoặc thuộc tính của `@SpringBootTest` |

Các nguồn kiểm thử có thể được sắp xếp thêm theo quy tắc riêng của Spring Test. Không dùng bảng này để suy luận thứ tự chính xác giữa mọi nguồn tùy chỉnh; khi có khác biệt, hãy kiểm tra danh sách `PropertySource` thực tế của ứng dụng đang chạy.

Ví dụ cùng một khóa được đặt ở ba nơi:

```yaml
# application.yml
catalog:
  search:
    connect-timeout-seconds: 3
```

```powershell
# Biến môi trường
$env:CATALOG_SEARCH_CONNECTTIMEOUTSECONDS = "5"
```

```bash
# Tham số dòng lệnh
java -jar catalog-service.jar --catalog.search.connect-timeout-seconds=9
```

Trong tình huống này, giá trị hiệu lực thường là `9`. Tệp YAML vẫn là cấu hình mặc định có ích, biến môi trường có thể thay đổi theo môi trường triển khai, còn tham số dòng lệnh có thể được dùng để ghi đè có chủ đích cho một lần chạy.

### Tác động của thứ tự vị trí nguồn

`MutablePropertySources` có các thao tác như:

- `addFirst(source)`: thêm nguồn lên đầu danh sách, có ưu tiên cao.
- `addLast(source)`: thêm nguồn xuống cuối danh sách, có ưu tiên thấp.
- `addBefore(name, source)` và `addAfter(name, source)`: thêm nguồn trước hoặc sau nguồn đã biết.
- `replace(name, source)` và `remove(name)`: thay thế hoặc loại bỏ nguồn theo tên.

Ví dụ sau minh họa cách thêm một nguồn ưu tiên cao:

```java
import java.util.Map;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

void addLocalOverride(ConfigurableEnvironment environment) {
    var source = new MapPropertySource(
        "localOverride",
        Map.of("catalog.search.enabled", false)
    );
    environment.getPropertySources().addFirst(source);
}
```

Đây là ví dụ về API, không phải lời khuyên để sửa `Environment` sau khi ứng dụng đã khởi động. Nếu cần nguồn cấu hình bổ sung, hãy đăng ký nó ở giai đoạn khởi tạo phù hợp và ghi rõ lý do, phạm vi cùng thứ tự ưu tiên.

## 5. Config Data, tệp cấu hình và profile trong Spring Boot

Spring Boot nạp cấu hình ngoài mã nguồn thông qua cơ chế Config Data. Các tệp phổ biến là `application.properties` và `application.yml`. Chúng có thể nằm trong classpath hoặc tại các vị trí bên ngoài ứng dụng.

Ví dụ cấu hình cơ sở:

```yaml
# application.yml
spring:
  application:
    name: catalog-service

catalog:
  search:
    base-url: http://localhost:9080
    connect-timeout-seconds: 3
```

Profile cho phép chọn nhóm cấu hình phù hợp với môi trường chạy. Ví dụ, `application-prod.yml` chỉ áp dụng khi profile `prod` được kích hoạt:

```yaml
# application-prod.yml
catalog:
  search:
    base-url: https://search.internal.example
    connect-timeout-seconds: 2
```

Có thể kích hoạt profile bằng thuộc tính `spring.profiles.active`, chẳng hạn qua biến môi trường `SPRING_PROFILES_ACTIVE=prod` hoặc tham số `--spring.profiles.active=prod`. Khi đó, cấu hình theo profile được kết hợp với cấu hình chung; các khóa trùng nhau trong cấu hình profile thường ghi đè giá trị tương ứng ở cấu hình chung. Những nguồn có độ ưu tiên cao hơn, chẳng hạn tham số dòng lệnh hoặc biến môi trường theo quy tắc Boot, vẫn có thể ghi đè cấu hình tệp.

Một số thuộc tính liên quan:

- `spring.profiles.active`: chọn profile hoạt động.
- `spring.profiles.default`: chỉ định profile mặc định khi không có profile nào được kích hoạt.
- `spring.profiles.include`: bổ sung profile vào nhóm profile hoạt động.
- `spring.profiles.group`: gom nhiều profile thành một nhóm có tên.
- `spring.config.location`: thay thế các vị trí Config Data mặc định.
- `spring.config.additional-location`: bổ sung vị trí Config Data; cấu hình ở vị trí bổ sung có thể ghi đè cấu hình đã nạp trước đó.

Profile là cơ chế chọn cấu hình, không phải ranh giới bảo mật. Không đưa mật khẩu production vào một tệp chỉ vì tệp đó mang tên `application-prod.yml`; tệp vẫn có thể bị sao chép hoặc đưa vào Git.

## 6. Spring Cloud Config Client đưa cấu hình từ xa vào Environment

Trong hệ thống có nhiều dịch vụ, lưu cấu hình riêng trong từng gói triển khai dễ dẫn đến sai lệch. Spring Cloud Config giải quyết vấn đề này bằng cách lưu cấu hình tập trung, thường trong một Git repository, và cung cấp nó qua Config Server.

Khi khởi động, Config Client yêu cầu cấu hình phù hợp với tên ứng dụng, profile và label. Các nguồn cấu hình từ xa được đưa vào `Environment` của ứng dụng. Vì vậy, mã nghiệp vụ vẫn đọc `catalog.search.base-url` qua `Environment` hoặc `@ConfigurationProperties`; nó không cần gọi Git hay HTTP đến Config Server trực tiếp.

Với cơ chế Config Data hiện đại của Spring Boot và Spring Cloud, client thường khai báo import như sau:

```yaml
# application.yml của catalog-service
spring:
  application:
    name: catalog-service
  config:
    import: "optional:configserver:http://localhost:8888"
```

Tiền tố `optional:` cho phép ứng dụng tiếp tục khởi động nếu Config Server không sẵn sàng hoặc không cung cấp được cấu hình theo điều kiện của import. Nếu cấu hình từ xa là bắt buộc để dịch vụ hoạt động đúng, hãy bỏ `optional:` và thiết kế xử lý lỗi khởi động phù hợp. URL và các thuộc tính kết nối cũng có thể được cấp qua nguồn cấu hình bên ngoài.

Config Server thường kết hợp cấu hình chung như `application.yml` với cấu hình dành riêng cho ứng dụng và profile, ví dụ `catalog-service-prod.yml`. Label có thể trỏ đến nhánh, tag hoặc phiên bản cấu hình mà máy chủ hỗ trợ. Config Client nhận các property source từ phản hồi của máy chủ rồi tham gia vào cơ chế tra cứu chung của `Environment`.

Thứ tự chính xác giữa nguồn từ xa và nguồn cục bộ chịu ảnh hưởng của phiên bản Spring Cloud, cách dùng Config Data import hay cơ chế bootstrap cũ, cùng các tùy chọn cho phép ghi đè. Do đó, không nên mặc định rằng mọi giá trị từ Config Server luôn thắng mọi giá trị cục bộ. Khi thiết kế quy tắc ghi đè, hãy kiểm tra tài liệu của release train đang dùng và kiểm tra danh sách nguồn thực tế.

Ở các hệ thống cũ, Spring Cloud Config Client có thể dùng `bootstrap.yml` và bootstrap context để nạp cấu hình từ xa trước context chính. Với các phiên bản hiện đại dựa trên Config Data, `spring.config.import` là cách tích hợp phổ biến. Không trộn hướng dẫn của hai cơ chế nếu chưa xác định phiên bản Spring Boot và Spring Cloud của dự án.

### Cấu hình lúc khởi động và cập nhật khi ứng dụng đang chạy

Việc lấy cấu hình từ Config Server lúc khởi động không đồng nghĩa ứng dụng sẽ tự nhận mọi thay đổi về sau. Muốn cập nhật cấu hình đang chạy, hệ thống cần một cơ chế refresh phù hợp, chẳng hạn endpoint refresh được bảo vệ hoặc Spring Cloud Bus để phát thông báo đến nhiều instance. Những bean giữ giá trị cấu hình có thể cần `@RefreshScope` để được tạo lại sau refresh. Đây là vòng đời riêng của refresh; `Environment` chỉ là nơi tra cứu các giá trị đã được nạp vào ứng dụng.

## 7. Đọc cấu hình trong mã ứng dụng

Spring cung cấp nhiều cách đọc thuộc tính. Hãy chọn cách phù hợp với số lượng khóa và mức độ cấu trúc của cấu hình.

### Dùng Environment cho tra cứu linh hoạt

Phù hợp khi một thành phần cần tra cứu một vài khóa theo điều kiện lúc chạy:

```java
@Component
public class FeatureDecider {
    private final Environment environment;

    public FeatureDecider(Environment environment) {
        this.environment = environment;
    }

    public boolean isNewSearchEnabled() {
        return environment.getProperty(
            "catalog.search.new-engine.enabled",
            Boolean.class,
            false
        );
    }
}
```

### Dùng @Value cho một thuộc tính đơn lẻ

```java
@Component
public class SearchEndpoint {
    private final String baseUrl;

    public SearchEndpoint(
        @Value("${catalog.search.base-url}") String baseUrl
    ) {
        this.baseUrl = baseUrl;
    }
}
```

Có thể khai báo giá trị mặc định bằng cú pháp `${property.name:default-value}`:

```java
@Value("${catalog.search.connect-timeout-seconds:3}")
private int connectTimeoutSeconds;
```

Nếu thiếu một thuộc tính quan trọng, nên để ứng dụng báo lỗi rõ ràng khi khởi động thay vì âm thầm dùng một giá trị mặc định có thể gây lỗi vận hành.

### Dùng @ConfigurationProperties cho nhóm cấu hình

Với nhóm thuộc tính có cấu trúc, `@ConfigurationProperties` thường dễ kiểm tra và bảo trì hơn nhiều trường `@Value` rời rạc.

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog.search")
public record SearchProperties(
    @NotBlank String baseUrl,
    @Min(1) int connectTimeoutSeconds,
    boolean newEngineEnabled
) {}
```

Đăng ký lớp cấu hình bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(SearchProperties.class)` trong một lớp cấu hình. Khi đó, Spring Boot bind các khóa có tiền tố `catalog.search` vào đối tượng `SearchProperties`; cơ chế chuyển đổi kiểu và kiểm tra hợp lệ giúp phát hiện cấu hình sai sớm.

Ví dụ YAML tương ứng:

```yaml
catalog:
  search:
    base-url: https://search.internal.example
    connect-timeout-seconds: 2
    new-engine-enabled: true
```

Spring Boot hỗ trợ relaxed binding, vì vậy các dạng tên tương ứng có thể được ánh xạ giữa YAML, properties và biến môi trường. Khi đặt biến môi trường, hãy tuân theo quy tắc chuyển đổi tên của Spring Boot: viết hoa, thay dấu chấm bằng dấu gạch dưới và bỏ dấu gạch ngang. Ví dụ, `catalog.search.connect-timeout-seconds` thường được biểu diễn thành `CATALOG_SEARCH_CONNECTTIMEOUTSECONDS`.

## 8. Placeholder và chuyển đổi kiểu

Một thuộc tính có thể tham chiếu thuộc tính khác bằng placeholder:

```yaml
catalog:
  search:
    host: search.internal.example
    base-url: "https://${catalog.search.host}"
```

Khi được xử lý bởi cơ chế cấu hình của Spring, placeholder `${catalog.search.host}` được thay bằng giá trị tương ứng. Placeholder có thể có giá trị dự phòng, ví dụ `${catalog.search.port:443}`. Nếu cần bắt buộc một khóa phải tồn tại, hãy dùng API hoặc cơ chế bind có thể báo lỗi khi thiếu.

Spring cũng hỗ trợ chuyển đổi giá trị sang kiểu đích. Ví dụ, chuỗi `5` có thể được chuyển thành `Integer`, `true` thành `Boolean`, và các kiểu phổ biến như thời lượng hoặc kích thước dữ liệu có thể được bind qua cơ chế chuyển đổi của Spring Boot. Nên dùng kiểu dữ liệu thể hiện đúng ý nghĩa cấu hình, chẳng hạn `Duration` cho timeout, thay vì tự xử lý chuỗi ở nhiều nơi.

## 9. Quan sát và chẩn đoán nguồn cấu hình

Khi ứng dụng nhận giá trị khác mong đợi, hãy điều tra theo trình tự:

1. Xác định chính xác khóa mà mã đang đọc, bao gồm tiền tố và cách viết tên.
2. Xác nhận profile đang hoạt động bằng `Environment.getActiveProfiles()` và kiểm tra default profile nếu không có profile hoạt động.
3. Xác định các tệp Config Data đã được nạp, gồm cấu hình chung, cấu hình theo profile và các vị trí bên ngoài.
4. Kiểm tra biến môi trường, thuộc tính JVM, tham số dòng lệnh và nguồn cấu hình từ xa có thể ghi đè khóa đó.
5. Kiểm tra thứ tự các `PropertySource` trong `ConfigurableEnvironment` để xác định nguồn đầu tiên có khóa.
6. Nếu dùng Config Server, xác nhận application name, profile, label, URL máy chủ và trạng thái kết nối.
7. Kiểm tra thời điểm nạp cấu hình. Một số thuộc tính điều khiển quá trình khởi động phải có mặt trước khi context được tạo.

Có thể liệt kê tên nguồn mà không in giá trị cấu hình:

```java
import org.slf4j.Logger;
import org.springframework.core.env.ConfigurableEnvironment;

void logPropertySourceNames(
    ConfigurableEnvironment environment,
    Logger logger
) {
    environment.getPropertySources().forEach(source ->
        logger.debug("Property source: {}", source.getName())
    );
}
```

Không ghi toàn bộ giá trị của các `PropertySource` vào log. Nguồn có thể chứa mật khẩu, token, khóa mã hóa hoặc thông tin kết nối. Các endpoint quản trị như Actuator `env` cũng cần được giới hạn quyền truy cập và cấu hình che giấu giá trị nhạy cảm đúng cách.

Một khác biệt thường gây nhầm lẫn là `@PropertySource` được đăng ký trong quá trình tạo context, vì vậy nó có thể đến quá muộn đối với một số thuộc tính mà Spring Boot cần đọc rất sớm, chẳng hạn cấu hình logging hoặc một phần cấu hình `spring.main`. Với các thuộc tính điều khiển bootstrap, hãy ưu tiên nguồn và cơ chế nạp được Spring Boot hỗ trợ ở giai đoạn Config Data hoặc trước đó.

## 10. Bảo vệ bí mật và quản trị thay đổi

`Environment` làm cho nhiều nguồn cấu hình có cùng giao diện tra cứu, nhưng không tự biến dữ liệu thành an toàn. Hãy áp dụng các nguyên tắc sau:

- Không commit mật khẩu, token, private key hoặc thông tin xác thực vào Git repository cấu hình.
- Dùng hệ thống quản lý bí mật phù hợp, chẳng hạn Vault hoặc secret store của nền tảng triển khai; cấp quyền đọc theo từng ứng dụng và môi trường.
- Nếu dùng cơ chế mã hóa của Spring Cloud Config, quản lý khóa mã hóa bên ngoài repository và kiểm soát chặt quyền giải mã.
- Không ghi giá trị nhạy cảm vào log, exception, endpoint chẩn đoán hoặc báo cáo hỗ trợ.
- Quản lý thay đổi cấu hình bằng review, lịch sử phiên bản và quy trình rollback; thay đổi cấu hình production cần có người chịu trách nhiệm.
- Dùng profile để chọn hành vi theo môi trường, không dùng profile để thay thế phân quyền truy cập bí mật.

Một thay đổi cấu hình có thể tác động đến tất cả instance cùng đọc một nguồn. Vì vậy, hãy kiểm thử thay đổi trước khi phát hành, triển khai theo phạm vi phù hợp và có cách khôi phục phiên bản cấu hình trước đó.

## 11. Ví dụ tổng hợp

Giả sử `catalog-service` lấy cấu hình từ Config Server và hỗ trợ cấu hình riêng cho production. Tệp cục bộ khai báo tên ứng dụng và địa chỉ Config Server:

```yaml
# application.yml
spring:
  application:
    name: catalog-service
  config:
    import: "configserver:http://config-server:8888"
```

Trong Git repository cấu hình, Config Server có thể cung cấp cấu hình dùng chung:

```yaml
# application.yml trong repository cấu hình
catalog:
  search:
    base-url: https://search.default.internal
    connect-timeout-seconds: 3
```

Và cấu hình riêng cho production:

```yaml
# catalog-service-prod.yml trong repository cấu hình
catalog:
  search:
    base-url: https://search.prod.internal
    connect-timeout-seconds: 2
```

Khởi động ứng dụng với profile `prod`, chẳng hạn bằng `--spring.profiles.active=prod`. Config Client yêu cầu cấu hình cho `catalog-service` và profile đó. Các property source nhận được được thêm vào `Environment`. Lớp cấu hình ứng dụng bind nhóm khóa `catalog.search` vào `SearchProperties`, sau đó các thành phần sử dụng đối tượng đã bind để tạo client tìm kiếm.

Nếu một instance cần kiểm tra tạm thời với timeout khác, có thể truyền thuộc tính qua cơ chế triển khai, chẳng hạn biến môi trường hoặc tham số dòng lệnh. Giá trị cuối cùng phụ thuộc thứ tự ưu tiên thực tế của các nguồn trong phiên bản Spring Boot và Spring Cloud đang dùng. Vì thế, thay đổi này cần được quan sát và ghi nhận để tránh tạo ra khác biệt không chủ ý giữa các instance.

## 12. Những điểm cần ghi nhớ

- `Environment` là giao diện tra cứu thuộc tính và profile của ứng dụng Spring.
- `PropertySource` đóng gói một nguồn dữ liệu; nhiều nguồn được sắp xếp trong `MutablePropertySources`.
- Khi một khóa xuất hiện ở nhiều nguồn, thứ tự nguồn quyết định giá trị được trả về.
- Spring Boot nạp Config Data, profile và các nguồn bên ngoài vào `Environment` trong quá trình khởi động.
- Spring Cloud Config Client bổ sung cấu hình từ xa vào cùng mô hình tra cứu, vì vậy mã ứng dụng không cần biết cấu hình đến từ Git hay HTTP.
- Dùng `@ConfigurationProperties` cho nhóm cấu hình có cấu trúc, xác thực dữ liệu và giữ bí mật ngoài repository.
- Luôn kiểm tra profile, danh sách nguồn và quy tắc ghi đè khi giá trị hiệu lực khác mong đợi.

Khi hiểu rõ `Environment` và `PropertySource`, bạn có thể lần theo đường đi của một giá trị từ nguồn khai báo đến bean sử dụng nó. Đây là cơ sở để tiếp tục học cách thiết kế repository cấu hình, tích hợp Config Server, refresh cấu hình và quản trị thay đổi trên nhiều dịch vụ.
