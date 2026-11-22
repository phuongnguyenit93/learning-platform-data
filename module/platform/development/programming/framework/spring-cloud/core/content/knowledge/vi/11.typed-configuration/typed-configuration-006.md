# Constructor binding, Java record và giới hạn làm mới

Bài học thuộc chương **Cấu hình kiểu dữ liệu** của module **SPRING_CLOUD_CORE**. Spring Boot gom các property liên quan thành object có kiểu bằng `@ConfigurationProperties`. Với **constructor binding**, Binder truyền giá trị vào constructor để tạo object; các field có thể là `final` và không cần setter. Java **record** là lựa chọn tự nhiên cho cấu hình bất biến vì các component được khai báo ngay trên header record.

Tính bất biến giúp cấu hình dễ đọc, dễ kiểm thử và tránh sửa giá trị ngoài ý muốn sau khi khởi tạo. Tuy nhiên, có một giới hạn quan trọng trong Spring Cloud: **constructor-bound configuration properties, bao gồm Java record, không được Spring Cloud Context rebinding trực tiếp khi refresh**. Nếu cấu hình cần đổi trong lúc ứng dụng chạy, cần chọn một thiết kế khác hoặc có quy trình tạo lại snapshot cấu hình rõ ràng.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt JavaBean/setter binding và constructor binding.
2. Khai báo cấu hình bất biến bằng Java class hoặc Java record.
3. Đăng ký cấu hình bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
4. Dùng `@DefaultValue` cho tham số constructor, record component và object lồng nhau.
5. Kết hợp type conversion, relaxed binding và Bean Validation.
6. Hiểu yêu cầu compiler parameter names và khác biệt giữa các thế hệ Spring Boot.
7. Giải thích vì sao constructor-bound object không được rebinding bởi Spring Cloud Context.
8. Chọn giữa restart, mutable configuration properties và refresh-scoped snapshot khi cần thay đổi cấu hình.
9. Viết test xác minh binding, default, validation và giới hạn refresh.
10. Không nhầm Environment nhận giá trị mới với object bất biến đã được tạo lại.

## 2. Hai cách binding cấu hình

`@ConfigurationProperties` ánh xạ một nhóm property vào object có cấu trúc. Spring Boot hỗ trợ hai kiểu binding phổ biến.

### 2.1. JavaBean binding

JavaBean binding thường dùng constructor rỗng và setter:

~~~java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private URI baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(1);
    private int maxAttempts = 3;

    public URI getBaseUrl() { return baseUrl; }
    public void setBaseUrl(URI baseUrl) { this.baseUrl = baseUrl; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxAttempts() { return maxAttempts; }
    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

Binder tạo bean rồi gán giá trị qua setter/property access. Object có thể thay đổi sau khi tạo. Cách này thuận tiện với cấu hình cần rebinding, nhưng cần bảo vệ object khỏi thay đổi tùy tiện trong logic nghiệp vụ.

### 2.2. Constructor binding

Constructor binding truyền các giá trị đã bind vào constructor:

~~~java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final URI baseUrl;
    private final Duration connectTimeout;
    private final int maxAttempts;

    public ClientProperties(
            URI baseUrl,
            Duration connectTimeout,
            int maxAttempts) {
        this.baseUrl = baseUrl;
        this.connectTimeout = connectTimeout;
        this.maxAttempts = maxAttempts;
    }

    public URI getBaseUrl() { return baseUrl; }
    public Duration getConnectTimeout() { return connectTimeout; }
    public int getMaxAttempts() { return maxAttempts; }
}
~~~

Object được tạo với các giá trị cấu hình ngay từ đầu. Không cần setter và có thể dùng field `final`. Sau khi tạo, object không thể được cập nhật bằng cách gọi setter.

### 2.3. So sánh

| Tiêu chí | JavaBean/setter binding | Constructor binding |
| --- | --- | --- |
| Khởi tạo | Thường dùng constructor rỗng. | Gọi constructor có tham số. |
| Gán giá trị | Setter/property access. | Truyền giá trị vào tham số constructor. |
| Mutability | Thường mutable. | Có thể immutable. |
| Default | Field initializer hoặc logic khởi tạo. | `@DefaultValue` hoặc giá trị được cung cấp. |
| Validation | Có thể validate sau khi bind. | Validate object sau khi constructor binding hoàn tất. |
| Spring Cloud refresh | Có thể được rebinding nếu thuộc loại bean được hỗ trợ. | Constructor-bound properties không được rebinding trực tiếp. |
| Phù hợp | Cấu hình cần cập nhật runtime. | Cấu hình bất biến, snapshot theo vòng đời ứng dụng. |

Không có kiểu binding tốt nhất cho mọi trường hợp. Hãy chọn theo vòng đời cấu hình: nếu giá trị chỉ đổi khi deploy, immutable configuration thường đơn giản; nếu cần thay đổi runtime, phải thiết kế riêng cho cơ chế cập nhật.

## 3. Constructor binding trong Spring Boot

### 3.1. Khi nào Spring Boot chọn constructor?

Trong các phiên bản Spring Boot hiện đại:

- Một class có một constructor tham số duy nhất thường được suy luận là constructor binding.
- Java record có canonical constructor; nếu record không khai báo constructor khác, thường không cần gắn `@ConstructorBinding`.
- Nếu class có nhiều constructor, có thể đánh dấu constructor cần dùng bằng `@ConstructorBinding`.
- Constructor binding chỉ áp dụng cho configuration-properties type được đăng ký bằng `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.
- Không dùng constructor binding cho bean tạo theo cơ chế Spring thông thường như `@Component`, method `@Bean` hoặc `@Import`.

Với Spring Boot 3.x, annotation `@ConstructorBinding` dùng khi cần chỉ định rõ constructor và nằm trong package:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
~~~

Không cần thêm annotation này vào mọi record. Khi đọc tài liệu Spring Boot 2.x hoặc nâng cấp từ phiên bản cũ, kiểm tra package và vị trí annotation theo đúng phiên bản vì API constructor binding đã thay đổi qua các thế hệ.

### 3.2. Đăng ký configuration properties

Có hai cách thường dùng.

**Quét các lớp cấu hình:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

**Đăng ký tường minh:**

~~~java
@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Chọn một cách phù hợp với cấu trúc ứng dụng. Không gắn thêm `@Component` lên class constructor-bound chỉ để Spring tìm thấy nó; việc đăng ký bằng cơ chế configuration properties là một phần của contract binding.

### 3.3. Tên tham số constructor

Binder cần biết tên tham số để ánh xạ property. Khi dùng constructor binding, project cần giữ parameter names trong bytecode bằng tùy chọn compiler `-parameters`.

Spring Boot Gradle plugin và Maven Spring Boot parent thiết lập cấu hình phù hợp trong các dự án tiêu chuẩn. Nếu dùng build tùy chỉnh, kiểm tra compiler options. Khi thiếu tên tham số, binding có thể không hoạt động như mong đợi hoặc báo lỗi lúc khởi động.

## 4. Java record cho cấu hình bất biến

### 4.1. Record cơ bản

Java record phù hợp khi một nhóm property là dữ liệu mô tả, cần khởi tạo đầy đủ và không muốn thay đổi sau khi tạo.

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {
}
~~~

Với cấu hình:

~~~yaml
app:
  client:
    base-url: https://inventory.internal
    connect-timeout: 750ms
    max-attempts: 3
~~~

Spring Boot bind `base-url` thành component `baseUrl`, `connect-timeout` thành `Duration connectTimeout` và `max-attempts` thành `int maxAttempts`. Record tự sinh accessor theo tên component, ví dụ `baseUrl()` và `connectTimeout()`.

### 4.2. Record lồng nhau

Cấu hình có thể được chia nhóm:

~~~yaml
app:
  client:
    base-url: https://inventory.internal
    connect-timeout: 750ms
    security:
      enabled: true
      username: order-reader
      roles:
        - INVENTORY_READ
        - STOCK_CHECK
~~~

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        Security security
) {
    public record Security(
            boolean enabled,
            String username,
            List<String> roles
    ) {
    }
}
~~~

Các member lồng nhau của constructor-bound class cũng được bind qua constructor của chúng. Cấu trúc Java phản ánh cấu trúc YAML và giới hạn phạm vi property.

### 4.3. Không thêm setter vào record

Record được thiết kế để biểu diễn dữ liệu bất biến. Component được lưu trong field final và chỉ có accessor. Không thể thêm setter thông thường để thay component sau khi tạo.

Nếu cấu hình phải thay đổi liên tục mà không tạo object mới, record không phải lựa chọn phù hợp cho configuration-properties bean được rebinding.

## 5. DefaultValue và giá trị mặc định

### 5.1. DefaultValue trên record component

Spring Boot cung cấp `@DefaultValue` cho constructor binding:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @DefaultValue("https://localhost:8443") URI baseUrl,
        @DefaultValue("750ms") Duration connectTimeout,
        @DefaultValue("3") int maxAttempts
) {
}
~~~

Nếu property không được cung cấp, Binder dùng giá trị mặc định trong annotation và chuyển đổi sang kiểu đích. Conversion service của Spring Boot xử lý việc chuyển `750ms` thành `Duration`.

Default trong `@DefaultValue` áp dụng khi property vắng mặt. Nếu property có mặt nhưng giá trị rỗng hoặc sai định dạng, kết quả còn phụ thuộc kiểu dữ liệu và quy tắc conversion; không xem giá trị rỗng là tương đương với property không tồn tại.

### 5.2. Khởi tạo object lồng nhau khi không có property

Nếu không có property nào thuộc nhóm `security`, component `security` có thể là `null`. Nếu muốn luôn có object con, dùng `@DefaultValue` rỗng:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        @DefaultValue Security security
) {
    public record Security(
            String username,
            @DefaultValue("USER") List<String> roles
    ) {
    }
}
~~~

`@DefaultValue` rỗng trên tham số `security` yêu cầu Binder tạo object con ngay cả khi không có property của nhóm đó. Các component chưa có giá trị vẫn cần được xử lý theo nullability/validation của ứng dụng.

### 5.3. DefaultValue không thay thế validation

Default cung cấp giá trị khi thiếu; validation từ chối giá trị không hợp lệ. Hai cơ chế phục vụ mục đích khác nhau.

~~~java
@ConfigurationProperties(prefix = "app.client")
@Validated
public record ClientProperties(
        @NotNull URI baseUrl,
        @DefaultValue("750ms") Duration connectTimeout,
        @Min(1) @DefaultValue("3") int maxAttempts
) {
}
~~~

- Nếu `baseUrl` bắt buộc nhưng không có giá trị, validation có thể làm ứng dụng fail fast.
- `connectTimeout` có default 750ms.
- `maxAttempts` có default 3 và phải lớn hơn hoặc bằng 1.

Để dùng Jakarta Bean Validation trên Spring Boot 3, cần dependency validation tương ứng, thường là `spring-boot-starter-validation`. Khi kiểm tra nested object, dùng `@Valid` ở component lồng nhau nếu cần cascade validation.

### 5.4. Tránh Optional cho configuration properties

Không nên dùng `Optional<T>` như kiểu field/constructor parameter của `@ConfigurationProperties` để biểu diễn property tùy chọn. Optional chủ yếu được thiết kế cho kiểu trả về. Với cấu hình, hãy dùng nullable type phù hợp, giá trị mặc định hoặc object con có trạng thái rõ ràng.

Nếu property là bắt buộc, dùng `@NotNull`; nếu có default, dùng `@DefaultValue`.

## 6. Type conversion và relaxed binding

### 6.1. Các kiểu dữ liệu thường gặp

| Kiểu Java | Ví dụ property | Giá trị sau binding |
| --- | --- | --- |
| `Duration` | `connect-timeout: 750ms` | Khoảng thời gian 750 mili giây. |
| `DataSize` | `max-payload: 10MB` | Kích thước dữ liệu 10 MB. |
| `URI` / `URL` | `base-url: https://api.internal` | Địa chỉ endpoint. |
| `InetAddress` | `remote-address: 10.0.0.10` | Địa chỉ IP/host. |
| `boolean` | `enabled: true` | Cờ bật/tắt. |
| `int` / `long` | `max-attempts: 3` | Số nguyên. |
| `enum` | `strategy: ROUND_ROBIN` | Hằng enum tương ứng. |
| `List<T>` | `regions: [ap-southeast, ap-northeast]` | Danh sách phần tử. |
| `Map<K,V>` | `weights.region-a: 70` | Map key/value. |

Với duration và data size, dùng hậu tố có đơn vị rõ ràng để tránh hiểu sai. Nếu cần đơn vị mặc định khác, có thể sử dụng annotation liên quan hoặc cấu hình conversion theo yêu cầu.

### 6.2. Relaxed binding

Tên property trong YAML thường dùng kebab-case:

~~~yaml
app:
  client:
    connect-timeout: 750ms
    max-attempts: 3
~~~

Tên component Java dùng camelCase:

~~~java
Duration connectTimeout;
int maxAttempts;
~~~

Binder hỗ trợ relaxed binding để ánh xạ các dạng tên phù hợp. Khi tham chiếu property bằng `@Value`, nên dùng tên canonical dạng chữ thường và dấu gạch ngang để tránh khác biệt giữa các nguồn.

### 6.3. Enum và giá trị sai

~~~java
public enum RoutingStrategy {
    ROUND_ROBIN,
    RANDOM,
    WEIGHTED
}
~~~

~~~yaml
app:
  routing:
    strategy: WEIGHTED
~~~

Nếu cấu hình là `WEIGHT` thay vì giá trị enum hợp lệ, Binder báo lỗi conversion/binding. Đây là hành vi tốt với cấu hình quan trọng vì ứng dụng fail fast thay vì chạy với chiến lược không xác định.

## 7. Validation và fail-fast khi khởi động

### 7.1. Vì sao cần validation?

Cấu hình là đầu vào của ứng dụng. Nếu giá trị sai, lỗi có thể xuất hiện muộn khi request thật được xử lý. Validation ngay khi bind giúp phát hiện sai cấu hình ở thời điểm khởi động.

~~~java
@ConfigurationProperties(prefix = "app.routing")
@Validated
public record RoutingProperties(
        @NotNull RoutingStrategy strategy,
        @Min(1) @Max(100) int maxConcurrentRequests,
        @NotNull Duration requestTimeout
) {
}
~~~

~~~yaml
app:
  routing:
    strategy: ROUND_ROBIN
    max-concurrent-requests: 50
    request-timeout: 800ms
~~~

Nếu `max-concurrent-requests` là 0 hoặc vượt quá 100, validation thất bại và ứng dụng không khởi động thành công.

### 7.2. Nested validation

~~~java
@ConfigurationProperties(prefix = "app.client")
@Validated
public record ClientProperties(
        @NotNull URI baseUrl,
        @Valid Security security
) {
    public record Security(
            @NotBlank String username,
            @NotBlank String credential
    ) {
    }
}
~~~

`@Valid` yêu cầu validation đi sâu vào object con. Nếu security là tùy chọn, hãy quyết định rõ trường hợp null có hợp lệ không; nếu không, dùng `@NotNull` cùng `@Valid`.

Không ghi credential vào log khi validation thất bại. Error message nên chỉ ra tên property và loại constraint, tránh in toàn bộ giá trị bí mật.

### 7.3. Validation khác conversion

- **Conversion:** chuyển chuỗi cấu hình thành kiểu Java, ví dụ `750ms` thành Duration.
- **Validation:** kiểm tra giá trị đã bind có thỏa quy tắc hay không, ví dụ timeout phải dương.
- **Business validation:** kiểm tra quan hệ giữa nhiều giá trị hoặc điều kiện phụ thuộc trạng thái hệ thống.

Không phải mọi quy tắc nghiệp vụ đều nên đặt trong annotation validation. Các kiểm tra cần truy cập database, registry hoặc dịch vụ từ xa nên được đặt ở bước phù hợp trong lifecycle ứng dụng.

## 8. Constructor binding và giới hạn refresh của Spring Cloud

### 8.1. Vì sao record không tự cập nhật?

~~~java
@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(
        String strategy,
        int maxAttempts
) {
}
~~~

Khi Binder tạo object, nó gọi constructor với các giá trị hiện hành. Các component được lưu trong field final. Nếu Environment sau đó nhận giá trị mới, object record đã tồn tại vẫn giữ các giá trị cũ.

Không có setter để rebinding từng field. Spring Cloud Context không thể cập nhật trực tiếp constructor-bound configuration properties theo cơ chế rebind thông thường.

### 8.2. Spring Cloud Context rebind bean mutable thế nào?

Với JavaBean mutable được đăng ký là `@ConfigurationProperties`, Spring Cloud Context có thể xử lý `EnvironmentChangeEvent` và rebinding bean sau khi Environment thay đổi.

Về bản chất, rebinding cập nhật các thuộc tính trên bean đang tồn tại. Nó không nhất thiết tạo object mới. Điều này có nghĩa:

- Các field có thể được cập nhật trong cùng instance.
- Code đang đọc object đồng thời có thể quan sát trạng thái trung gian khi nhiều field được cập nhật.
- Collection có thể có khoảng thời gian ngắn bị làm rỗng trong quá trình rebind trước khi phần tử mới được thêm vào, tùy loại collection và Binder.
- Rebind không tự cập nhật mọi bean singleton khác đã snapshot giá trị từ configuration bean.

Nếu cần một cấu hình nhất quán như một snapshot, Spring Cloud khuyến nghị cân nhắc `@RefreshScope` cho bean phù hợp thay vì để nhiều thread đọc một mutable configuration object trong lúc nó đang được cập nhật.

### 8.3. Constructor-bound configuration properties không được refresh

Spring Cloud Context hiện hành xác định rõ: **object dùng constructor binding, bao gồm Java record được đánh dấu `@ConfigurationProperties`, không thể được refresh/rebind trực tiếp**.

Điều này không có nghĩa record không thể được dùng trong ứng dụng Spring Cloud. Nó vẫn phù hợp với cấu hình bất biến được đọc khi khởi động. Giới hạn chỉ xuất hiện khi mong muốn cập nhật chính bean constructor-bound sau khi Environment thay đổi.

### 8.4. Bảng so sánh

| Loại bean | Khi Environment đổi và refresh | Kết quả |
| --- | --- | --- |
| Singleton thông thường có `@Value` | Không tự inject lại. | Field thường giữ snapshot cũ. |
| Mutable `@ConfigurationProperties` | Có thể được rebinding qua EnvironmentChangeEvent. | Các field được cập nhật trên bean hiện tại. |
| Constructor-bound class | Không được rebinding trực tiếp. | Object đã tạo giữ giá trị cũ. |
| Java record `@ConfigurationProperties` | Không được rebinding trực tiếp. | Record vẫn là snapshot bất biến. |
| Bean phù hợp có `@RefreshScope` | Target cache được invalidate; lần gọi sau tạo target mới. | Target mới có thể nhận cấu hình hiện hành nếu dependency/source được thiết kế đúng. |

## 9. Chọn chiến lược khi cấu hình cần thay đổi runtime

Có ba hướng chính. Chọn theo yêu cầu nhất quán, vòng đời và mức độ ảnh hưởng của thay đổi.

### 9.1. Chiến lược A: restart hoặc rollout instance

Nếu cấu hình chỉ thay đổi khi deploy, dùng immutable record và khởi động lại instance khi cần áp dụng giá trị mới.

Ưu điểm:
- Object bất biến và đơn giản.
- Không có trạng thái nửa cũ nửa mới do rebinding.
- Dễ kiểm thử cấu hình ở thời điểm startup.
- Dễ tái tạo từ cùng artifact và config revision.

Đây thường là lựa chọn dễ dự đoán cho port, listener, endpoint nền tảng hoặc cấu hình tạo resource trong startup.

### 9.2. Chiến lược B: mutable @ConfigurationProperties

Nếu giá trị runtime cần cập nhật và không đòi hỏi thay toàn bộ object atomically, dùng JavaBean configuration properties:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public class RoutingProperties {
    private String strategy = "ROUND_ROBIN";
    private int maxAttempts = 3;

    public String getStrategy() { return strategy; }
    public void setStrategy(String strategy) { this.strategy = strategy; }

    public int getMaxAttempts() { return maxAttempts; }
    public void setMaxAttempts(int maxAttempts) { this.maxAttempts = maxAttempts; }
}
~~~

Bean này có thể được rebinding khi quy trình Spring Cloud Context phát event phù hợp. Hãy kiểm soát concurrency nếu request đọc nhiều thuộc tính có quan hệ với nhau.

### 9.3. Chiến lược C: refresh-scoped snapshot

Nếu cần object cấu hình bất biến nhưng muốn tạo lại toàn bộ object khi refresh, có thể thiết kế một **bean factory/holder thuộc refresh scope** để tạo snapshot mới từ Environment hiện tại. Không coi record constructor-bound được đăng ký trực tiếp bằng `@ConfigurationProperties` là refreshable.

~~~mermaid
flowchart TD
    ENV["Environment sau khi cập nhật"] --> FACTORY["Refresh-scoped snapshot factory"]
    FACTORY --> TARGET["Immutable configuration snapshot"]
    CALLER["Service caller"] --> PROXY["Refresh-scoped proxy"]
    PROXY --> TARGET
    REFRESH["Refresh event"] --> INVALIDATE["Invalidate target cache"]
    INVALIDATE --> PROXY
    PROXY --> NEW["Lần gọi tiếp theo tạo snapshot mới"]
~~~

Cách này phù hợp khi cấu hình có nhiều field phải được thay đồng bộ, bean cần giữ tính bất biến sau khi tạo và ứng dụng có thể kiểm soát cách tạo lại object.

## 10. Ví dụ factory tạo immutable snapshot

Ví dụ sau minh họa ý tưởng: một bean thuộc refresh scope tạo record từ Environment mỗi khi target được khởi tạo. Đây là object do ứng dụng quản lý, **không đăng ký record này như một constructor-bound @ConfigurationProperties bean**.

Record:

~~~java
public record RoutingSnapshot(
        RoutingStrategy strategy,
        int maxAttempts,
        Duration requestTimeout
) {
}
~~~

Factory bean:

~~~java
@Component
@RefreshScope
public class RoutingSnapshotProvider {

    private final RoutingSnapshot snapshot;

    public RoutingSnapshotProvider(Environment environment) {
        Binder binder = Binder.get(environment);

        this.snapshot = binder.bind(
            "app.routing",
            Bindable.of(RoutingSnapshot.class)
        ).orElseThrow(() ->
            new IllegalStateException("Missing app.routing configuration")
        );
    }

    public RoutingSnapshot current() {
        return snapshot;
    }
}
~~~

Caller:

~~~java
@Service
public class RoutingService {

    private final RoutingSnapshotProvider snapshotProvider;

    public RoutingService(RoutingSnapshotProvider snapshotProvider) {
        this.snapshotProvider = snapshotProvider;
    }

    public RoutingDecision decide() {
        RoutingSnapshot config = snapshotProvider.current();
        return calculate(config);
    }
}
~~~

Trong ví dụ:
- `RoutingSnapshotProvider` là refresh-scoped bean/proxy.
- Khi refresh scope invalidate target, lần gọi `current()` tiếp theo tạo provider mới.
- Constructor provider dùng Binder đọc Environment hiện hành và tạo record mới.
- `RoutingService` giữ proxy provider, không giữ trực tiếp snapshot cũ.
- Mỗi lần xử lý nên lấy snapshot một lần rồi dùng xuyên suốt thao tác để tránh đọc nhiều revision trong cùng request.

Các import cần thiết gồm Spring Environment, Binder, Bindable, Spring Cloud `@RefreshScope` và các kiểu domain. API Binder có thể thay đổi chi tiết theo Spring Boot version; hãy xác nhận cách tạo Binder được hỗ trợ trong phiên bản dự án. Cũng cần thêm validation/kiểm tra dữ liệu trước khi snapshot được dùng và xử lý lỗi nếu target mới không thể khởi tạo.

## 11. Kiểm thử constructor binding và record

### 11.1. Test Binder độc lập

Có thể dùng `Binder` và `MapConfigurationPropertySource` để kiểm tra binding mà không cần khởi động toàn bộ application:

~~~java
@Test
void bindsRecordFromConfigurationProperties() {
    MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of(
            "app.client.base-url", "https://inventory.internal",
            "app.client.connect-timeout", "750ms",
            "app.client.max-attempts", "4"
        ));

    ClientProperties properties = new Binder(source)
        .bind("app.client", Bindable.of(ClientProperties.class))
        .orElseThrow();

    assertEquals(
        URI.create("https://inventory.internal"),
        properties.baseUrl()
    );
    assertEquals(Duration.ofMillis(750), properties.connectTimeout());
    assertEquals(4, properties.maxAttempts());
}
~~~

Test này kiểm tra Binder chuyển property thành record. Nó không kiểm tra component scan, validation trong ApplicationContext, refresh hoặc Config Server.

### 11.2. Test default values

~~~java
@Test
void usesDefaultsWhenPropertiesAreMissing() {
    MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of(
            "app.client.base-url", "https://inventory.internal"
        ));

    ClientProperties properties = new Binder(source)
        .bind("app.client", Bindable.of(ClientProperties.class))
        .orElseThrow();

    assertEquals(Duration.ofMillis(750), properties.connectTimeout());
    assertEquals(3, properties.maxAttempts());
}
~~~

Đảm bảo class record đang test khai báo `@DefaultValue` tương ứng. Nếu không có default và property không bắt buộc, giá trị có thể là null/primitive default theo kiểu; test cần phản ánh contract thật.

### 11.3. Test validation qua ApplicationContext

Để xác minh `@Validated`, tạo test context đăng ký configuration properties và cung cấp dependency validation. Thử cả cấu hình hợp lệ và cấu hình vi phạm constraint. Với cấu hình bắt buộc, kỳ vọng context không khởi động và exception chỉ rõ property/constraint gây lỗi.

### 11.4. Test giới hạn refresh

Thiết kế integration test riêng cho các trường hợp:

1. Khởi động context với property A và tạo record constructor-bound.
2. Cập nhật nguồn cấu hình thành B.
3. Thực hiện quy trình refresh của Spring Cloud Context.
4. Xác minh Environment có giá trị B.
5. Xác minh record constructor-bound hiện tại vẫn giữ A.
6. Nếu có mutable configuration bean, xác minh bean đó được rebinding theo cơ chế hỗ trợ.
7. Nếu có refresh-scoped snapshot provider, xác minh target mới đọc được B sau khi cache bị invalidate.
8. Xác minh singleton không giữ trực tiếp snapshot cũ nếu kỳ vọng nó sử dụng snapshot mới.

Không dùng một test chỉ kiểm tra Environment rồi kết luận toàn bộ bean đã được cập nhật.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Record không được tạo thành bean. | Chưa đăng ký bằng configuration properties scan/enable. | Dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. |
| Constructor binding không tìm được tham số. | Compiler không giữ parameter names. | Bật `-parameters` và kiểm tra Maven/Gradle plugin. |
| Binder dùng constructor không mong muốn. | Class có nhiều constructor nhưng không chỉ rõ constructor binding. | Dùng `@ConstructorBinding` đúng package/target của phiên bản. |
| `@ConstructorBinding` báo lỗi khi gắn lên component. | Annotation đặt sai vị trí hoặc đang dùng API version khác. | Kiểm tra tài liệu Boot version; record một canonical constructor thường không cần annotation. |
| @ConfigurationProperties không bind property lồng nhau. | Sai prefix, tên property hoặc cấu trúc nested object. | Kiểm tra YAML, record component và Binder diagnostics. |
| Giá trị mặc định không xuất hiện. | Thiếu `@DefaultValue` hoặc property được cung cấp với giá trị không hợp lệ. | Kiểm tra property source và semantics missing vs blank. |
| Validation không chạy. | Thiếu validation starter, `@Validated` hoặc cascade `@Valid`. | Kiểm tra dependency và annotation trên nested properties. |
| Record vẫn giữ giá trị cũ sau refresh. | Constructor-bound properties không được Spring Cloud rebind. | Dùng restart, mutable bean hoặc refresh-scoped snapshot factory. |
| Mutable config có trạng thái trung gian. | Rebind thay đổi object tại chỗ trong khi thread khác đọc. | Dùng snapshot bất biến hoặc refresh scope phù hợp. |
| Refresh-scoped provider vẫn trả cấu hình cũ. | Factory inject lại một singleton record đã cũ hoặc caller giữ snapshot. | Đọc Environment/Binder khi target mới được tạo và chỉ giữ proxy ở caller. |
| App chạy được nhưng cấu hình sai. | Không có validation hoặc default che giấu property thiếu. | Thêm constraint và test fail-fast. |

## 13. Nguyên tắc chọn mô hình cấu hình

| Nhu cầu | Lựa chọn đề xuất | Lý do |
| --- | --- | --- |
| Cấu hình chỉ đổi khi deploy | Constructor binding / Java record | Immutable, dễ kiểm thử và tái tạo. |
| Cấu hình cần rebind từng thuộc tính | Mutable `@ConfigurationProperties` | Hỗ trợ cập nhật bean theo cơ chế Spring Cloud Context. |
| Cần thay một nhóm giá trị như một snapshot | Refresh-scoped snapshot/provider | Tạo lại target và dùng một object nhất quán. |
| Cấu hình tạo tài nguyên hạ tầng | Đánh giá restart/rollout hoặc refresh lifecycle riêng | Cần đóng/mở resource an toàn. |
| Cấu hình bí mật | Secret manager và typed binding có kiểm soát | Hạn chế lộ giá trị và quản lý rotation. |

Đừng chọn record chỉ vì cú pháp ngắn. Hãy xác định ai sở hữu vòng đời cấu hình, khi nào nó được thay đổi, bean nào cần nhận giá trị mới và cách xác minh mọi instance đã áp dụng cùng revision.

## 14. Checklist hoàn thành

- [ ] Phân biệt được JavaBean binding và constructor binding.
- [ ] Tạo được configuration class có constructor và field final.
- [ ] Dùng Java record với `@ConfigurationProperties`.
- [ ] Đăng ký record bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
- [ ] Biết khi nào cần `@ConstructorBinding` và package annotation theo Boot version.
- [ ] Đảm bảo compiler giữ constructor parameter names.
- [ ] Dùng `@DefaultValue` cho scalar và nested object.
- [ ] Dùng type conversion cho Duration, DataSize, URI, enum và collection.
- [ ] Kết hợp `@Validated`, constraint và `@Valid`.
- [ ] Hiểu vì sao constructor-bound/record configuration không được Spring Cloud Context rebinding.
- [ ] Phân biệt Environment update với việc tạo lại configuration object.
- [ ] Chọn restart, mutable properties hoặc refresh-scoped snapshot theo yêu cầu.
- [ ] Có test binding, default, validation và refresh limitation.
- [ ] Có chính sách xử lý secret, revision và cấu hình giữa nhiều instance.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): hỗ trợ ConfigurationProperties, constructor binding, Java records, DefaultValue, validation và parameter names.
- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Environment changes, rebinding, refresh scope và giới hạn của constructor-bound objects.
- [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): tích hợp Bean Validation và fail-fast khi bind cấu hình.

Constructor binding, package của annotation và refresh behavior có thể khác giữa các thế hệ Spring Boot/Spring Cloud. Hãy kiểm tra compatibility matrix và tài liệu đúng release train trước khi dùng ví dụ trong production.
