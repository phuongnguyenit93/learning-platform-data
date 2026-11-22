# Khi nào cần liên kết lập trình thay vì annotation trong Spring Boot

## Mục tiêu

Trong Spring Boot, cách phổ biến nhất để đọc một nhóm cấu hình là tạo một class/record có **@ConfigurationProperties**, đăng ký nó với Spring và inject bean cấu hình vào service. Cách này ngắn gọn, khai báo rõ hợp đồng, hỗ trợ cấu hình lồng nhau và có thể kết hợp validation. Tuy nhiên, có những tình huống ứng dụng cần **tự điều khiển thời điểm, tiền tố, kiểu đích hoặc cách xử lý kết quả binding**. Khi đó có thể dùng **Binder API** để liên kết thuộc tính bằng mã Java, còn gọi là *programmatic binding*.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {}
~~~

và:

~~~java
Binder binder = Binder.get(environment);
ClientProperties client = binder
        .bind("app.client", ClientProperties.class)
        .orElse(null);
~~~

đều có thể nhằm đọc nhóm **app.client**. Nhưng lựa chọn thứ hai cho phép đoạn code **quyết định trực tiếp khi nào bind**, chọn prefix bằng logic, phân biệt có/không có dữ liệu và xử lý kết quả theo nhu cầu.

**Không nên mặc định rằng Binder API tốt hơn annotation.** Đối với cấu hình ổn định, gắn với vòng đời ứng dụng, annotation thường dễ bảo trì hơn. Programmatic binding phù hợp khi có nhu cầu mà annotation không thể diễn đạt thuận tiện hoặc khi muốn một thành phần không phải bean Spring đọc cấu hình một cách có kiểm soát.

Sau bài học, người đọc có thể:

- Mô tả cơ chế **externalized configuration → PropertySource → Binder → object Java**.
- Phân biệt **@ConfigurationProperties**, **@Value**, **Environment.getProperty** và **Binder API**.
- Biết những trường hợp nên và không nên chuyển sang programmatic binding.
- Dùng **Binder.get(environment)**, **bind**, **BindResult**, **Bindable**, List và Map.
- Hiểu xử lý prefix động, cấu hình theo tenant/module, giá trị tùy chọn và fallback.
- Kiểm soát conversion, validation, BindHandler, thời điểm bind và xử lý lỗi.
- Viết ví dụ thử nghiệm với **MapConfigurationPropertySource** mà không cần khởi động cả ứng dụng.
- Tránh những hiểu lầm về refresh runtime, bảo mật, lỗi chính tả hoặc thứ tự ưu tiên cấu hình.

Các ví dụ theo phong cách **Spring Boot 3.x**, dùng Java 17+ và các API quen thuộc của **org.springframework.boot.context.properties.bind**. Với dự án dùng phiên bản khác, cần đối chiếu package, overload và các extension point tương ứng.

---

## 1. Luồng xử lý cấu hình trong Spring Boot

Dữ liệu cấu hình có thể đến từ:

- application.properties hoặc application.yml.
- Tài liệu theo profile, ví dụ application-prod.yml.
- Biến môi trường của hệ điều hành.
- JVM system properties, ví dụ **-Dapp.client.timeout=10s**.
- Tham số dòng lệnh, ví dụ **--app.client.timeout=10s**.
- Các Config Data import/location và PropertySource do ứng dụng hoặc thư viện cung cấp.

Spring Boot đưa chúng vào một hệ thống tra cứu có thứ tự ưu tiên. Binder xử lý tên property, cấu trúc nested và conversion trước khi tạo hoặc điền object Java.

~~~text
application.yml      ENV      -Dsystem.property      --argument
       \              |                |                  /
        \             |                |                 /
                 Spring Environment
                 (PropertySource precedence)
                          |
                          v
                       Binder
             (name matching, conversion,
              nested paths, collection)
                          |
             +------------+------------+
             |                         |
             v                         v
  @ConfigurationProperties     Binder API trong mã Java
  khi tạo bean cấu hình        khi được gọi tường minh
             |                         |
             v                         v
        Properties bean           Object / BindResult
~~~

Điểm quan trọng: **Binder API không tạo một hệ thống precedence mới**. Khi Binder lấy dữ liệu từ Spring Environment, kết quả vẫn chịu thứ tự ưu tiên các nguồn cấu hình đang có.

Nếu một giá trị trong application.yml bị command-line argument ghi đè, việc thay @ConfigurationProperties bằng Binder.get(environment) không làm file YAML bỗng được ưu tiên hơn.

## 2. Ba cách đọc cấu hình thường gặp

Giả sử cấu hình:

~~~yaml
app:
  client:
    base-url: "https://catalog.example.test"
    timeout: 5s
    pool:
      max-size: 20
      enabled: true
~~~

### 2.1. @Value — một số thuộc tính riêng lẻ

~~~java
@Value("\${app.client.base-url}")
private String baseUrl;

@Value("\${app.client.timeout:5s}")
private Duration timeout;
~~~

Trong các điểm tích hợp được Spring hỗ trợ, @Value phân giải placeholder và chuyển giá trị về kiểu đích. Nó phù hợp với một vài thuộc tính đơn giản, nhưng không phải lựa chọn tốt nhất cho cấu trúc lồng nhau nhiều cấp.

### 2.2. @ConfigurationProperties — mô hình cấu hình lâu dài

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Duration timeout,
        Pool pool
) {
    public record Pool(int maxSize, boolean enabled) {}
}
~~~

Đăng ký record qua **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties(ClientProperties.class)**, sau đó inject ClientProperties vào service. Đây là lựa chọn mặc định nên ưu tiên khi nhóm cấu hình đã biết rõ tại thời điểm thiết kế.

### 2.3. Binder — liên kết bằng mã Java tại một điểm gọi

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

Binder binder = Binder.get(environment);
ClientProperties properties =
        binder.bind("app.client", ClientProperties.class)
              .orElse(null);
~~~

Khác với @ConfigurationProperties, đoạn code này trực tiếp yêu cầu Binder đọc một prefix và tạo một object. Nó cho phép xử lý kết quả, chọn prefix có điều kiện và quyết định cách phản ứng nếu prefix không được bind.

### 2.4. Bảng so sánh

| Tiêu chí | @Value | @ConfigurationProperties | Binder API |
| --- | --- | --- | --- |
| Mô hình nested object | Bất tiện | Rất phù hợp | Rất phù hợp |
| Được quản lý như bean cấu hình | Qua điểm inject | Có, khi đăng ký | Không tự động |
| Prefix cố định | Thường ở placeholder | Trong annotation | Truyền qua tham số |
| Prefix chọn bằng code | Khó duy trì | Không phải mục tiêu chính | Phù hợp |
| Biết rõ có bind được không | Cần logic thêm | Thường fail/validate lúc startup | BindResult |
| Thời điểm đọc dữ liệu | Thường lúc inject | Thường lúc tạo bean | Lúc code gọi bind |
| Validation tích hợp | Tùy điểm inject | Có cơ chế chuẩn | Cần cấu hình/áp dụng chủ động |
| Độ ngắn gọn với nhóm ổn định | Vừa | Tốt nhất | Có thể nhiều mã hơn |
| Tích hợp metadata/tooling | Hạn chế | Tốt khi có processor | Không tự có hợp đồng metadata tương đương |

**Nguyên tắc chọn:** nếu nhóm cấu hình ổn định có thể trở thành một bean rõ ràng, đừng chuyển sang Binder API chỉ để tránh một annotation.

## 3. Trường hợp 1: tiền tố cấu hình được chọn động

Giả sử một ứng dụng làm việc với hai dịch vụ đối tác:

~~~yaml
integration:
  catalog:
    endpoint: "https://catalog.example.test"
    timeout: 3s
  billing:
    endpoint: "https://billing.example.test"
    timeout: 8s
~~~

Hai cấu hình có cùng cấu trúc nhưng tên prefix khác:

~~~text
integration.catalog.*
integration.billing.*
~~~

Một record dùng chung:

~~~java
import java.time.Duration;

public record PartnerSettings(
        String endpoint,
        Duration timeout
) {}
~~~

Với Binder API:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class PartnerSettingsReader {

    private final Binder binder;

    public PartnerSettingsReader(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public PartnerSettings read(String partner) {
        if (!partner.equals("catalog") && !partner.equals("billing")) {
            throw new IllegalArgumentException("Unknown partner: " + partner);
        }

        String prefix = "integration." + partner;
        return binder.bind(prefix, PartnerSettings.class)
                .orElseThrow(() ->
                        new IllegalStateException(
                                "Missing configuration: " + prefix));
    }
}
~~~

Đây là ví dụ rõ về **prefix được chọn khi gọi phương thức**. Nếu một module chọn catalog hoặc billing theo một quy tắc có kiểm soát, Binder giúp tránh viết nhiều nhánh bind thủ công từng scalar.

### 3.1. Không ghép prefix trực tiếp từ input không tin cậy

Một lời gọi HTTP nhận tùy ý **partner** không nên được dùng trực tiếp làm đường dẫn Binder nếu chưa xác minh nó nằm trong tập tên hợp lệ. Nếu không, request có thể khiến ứng dụng đọc ngoài phạm vi được thiết kế hoặc trả ra dữ liệu cấu hình không được phép.

Có thể dùng enum hoặc registry:

~~~java
public enum Partner {
    CATALOG("catalog"),
    BILLING("billing");

    private final String key;

    Partner(String key) {
        this.key = key;
    }

    public String key() {
        return key;
    }
}
~~~

Và:

~~~java
public PartnerSettings read(Partner partner) {
    String prefix = "integration." + partner.key();
    return binder.bind(prefix, PartnerSettings.class)
            .orElseThrow(() ->
                    new IllegalStateException("Missing " + prefix));
}
~~~

**Prefix động không có nghĩa tiền tố tùy tiện.** Khi dùng trong hệ thống nhiều tenant, ranh giới cấp quyền và chính sách được phép xem cấu hình phải nằm ngoài Binder.

### 3.2. Khi Map tốt hơn prefix động

Nếu toàn bộ các cấu hình đối tác đều có cùng một cấu trúc, có thể dùng:

~~~java
@ConfigurationProperties(prefix = "integration")
public record IntegrationProperties(
        Map<String, PartnerSettings> partners
) {}
~~~

Cùng YAML nhưng chuyển cấu trúc:

~~~yaml
integration:
  partners:
    catalog:
      endpoint: "https://catalog.example.test"
      timeout: 3s
    billing:
      endpoint: "https://billing.example.test"
      timeout: 8s
~~~

Khi đó service có thể dùng **properties.partners().get(partner)**. Cách này thường tốt hơn nếu danh sách đối tác được biết và mong muốn toàn bộ cấu hình được bind/validate ở startup.

Dùng prefix động khi cấu trúc nguồn khó đổi hoặc chỉ muốn bind những nhóm được chọn; dùng Map khi mô hình dữ liệu của ứng dụng thật sự là **bảng key → value** và có thể bind cả bảng như một bean.

## 4. Trường hợp 2: chỉ bind khi một chức năng được kích hoạt

Một ứng dụng có module xuất báo cáo không phải lúc nào cũng chạy:

~~~yaml
app:
  reports:
    enabled: false
    export:
      directory: "/var/reports"
      batch-size: 100
~~~

Nếu module chỉ được dùng khi enabled=true, có thể cần quyết định có bind nhóm export hay không.

Record:

~~~java
public record ExportSettings(String directory, int batchSize) {}
~~~

Ví dụ tại một điểm khởi tạo:

~~~java
boolean enabled = Boolean.TRUE.equals(
        environment.getProperty(
                "app.reports.enabled",
                Boolean.class,
                false
        )
);

if (enabled) {
    ExportSettings settings = Binder.get(environment)
            .bind("app.reports.export", ExportSettings.class)
            .orElseThrow(() ->
                    new IllegalStateException("Export config missing"));

    // Khởi tạo module export với settings.
}
~~~

Ưu điểm của programmatic binding trong tình huống này: code thể hiện **quyết định chỉ bind khi cần** và **cách xử lý khi thiếu cấu hình**.

Nhưng cần phân biệt:

- Nếu chỉ muốn **bật/tắt bean** theo property, **@ConditionalOnProperty** thường là giải pháp Spring Boot phù hợp hơn.
- Nếu muốn cấu hình được bind và validate ngay từ startup bất kể feature bật hay tắt, @ConfigurationProperties có thể rõ ràng hơn.
- Nếu chỉ muốn chọn *khi nào* thực hiện một phép bind cụ thể trong code, Binder API có ích.

Không nên dùng Binder để thay thế toàn bộ hệ thống conditional bean registration khi điều kiện khởi tạo bean vốn đã có annotation phù hợp.

## 5. Trường hợp 3: cấu hình tùy chọn thực sự có thể vắng mặt

Giả sử một ứng dụng có cấu hình **app.telemetry** nhưng một số môi trường không triển khai telemetry.

~~~yaml
app:
  telemetry:
    endpoint: "https://metrics.example.test"
    interval: 30s
~~~

Một record:

~~~java
import java.time.Duration;

public record TelemetrySettings(
        String endpoint,
        Duration interval
) {}
~~~

Có thể đọc:

~~~java
var result = Binder.get(environment)
        .bind("app.telemetry", TelemetrySettings.class);

if (result.isBound()) {
    TelemetrySettings settings = result.get();
    // Sử dụng settings.
} else {
    // Chấp nhận cấu hình telemetry không tồn tại.
}
~~~

**BindResult.isBound()** cho phép tách trường hợp có một kết quả bind khỏi trường hợp không có đối tượng. Điều này khác với việc luôn tạo một bean có field null và để code khác tự suy luận.

### 5.1. Không xem lỗi cấu hình là “không có dữ liệu”

Một lỗi nguy hiểm là:

~~~java
try {
    return binder.bind("app.telemetry", TelemetrySettings.class)
            .orElse(null);
} catch (Exception ex) {
    return null;
}
~~~

Cách này có thể nuốt cả lỗi chuyển kiểu, lỗi cấu trúc object và những sai sót triển khai thật.

Cần phân biệt:

| Tình huống | Cách xử lý nên cân nhắc |
| --- | --- |
| Prefix không được cung cấp và được phép vắng mặt | Trả Optional hoặc trạng thái disabled |
| Prefix được cung cấp nhưng giá trị sai kiểu | Báo lỗi, không âm thầm bỏ qua |
| Prefix có vài property nhưng thiếu field bắt buộc | Validation hoặc invariant rõ ràng |
| Một nguồn ưu tiên cao ghi đè giá trị | Phân tích precedence |
| Prefix không thuộc allowlist | Từ chối yêu cầu trước khi bind |

**Tùy chọn** không đồng nghĩa **bỏ qua mọi lỗi**.

### 5.2. Sử dụng orElse, get và isBound

~~~java
var bound = binder.bind("app.telemetry", TelemetrySettings.class);

TelemetrySettings withFallback = bound.orElse(
        new TelemetrySettings("disabled", Duration.ZERO)
);
~~~

**orElse(...)** là lựa chọn cho trường hợp *không có kết quả*. Nó không biến một lỗi conversion thành một giá trị mặc định hợp lệ.

Với **get()**, chỉ nên gọi khi bind có kết quả hoặc khi đã xác định thiếu kết quả cần được báo thành lỗi. Việc gọi get trên BindResult không có giá trị sẽ thất bại, không tự trả null.

## 6. Trường hợp 4: dùng kiểu đích theo quyết định runtime

Có hệ thống cần đọc các cấu hình có kiểu khác nhau tùy module:

~~~yaml
app:
  workers:
    email:
      concurrency: 4
      sender: "noreply@example.test"
    indexing:
      concurrency: 8
      index-name: products
~~~

Có thể thiết kế các record:

~~~java
public record EmailWorkerSettings(int concurrency, String sender) {}
public record IndexingWorkerSettings(int concurrency, String indexName) {}
~~~

Ở một factory quản lý loại worker:

~~~java
Binder binder = Binder.get(environment);

EmailWorkerSettings email = binder
        .bind("app.workers.email", EmailWorkerSettings.class)
        .orElseThrow();

IndexingWorkerSettings indexing = binder
        .bind("app.workers.indexing", IndexingWorkerSettings.class)
        .orElseThrow();
~~~

Hai lời gọi dùng **hai prefix và hai class đích**. Binder API phù hợp khi factory cần chọn bộ cấu hình theo loại được kích hoạt.

Không nên viết code đọc mọi property ở dạng Map<String, Object> rồi tự cast nếu đã biết kiểu Java cụ thể. Binder hỗ trợ conversion, nested values và collection một cách nhất quán hơn so với lắp ghép chuỗi thủ công.

### 6.1. Không lạm dụng runtime type selection

Nếu ứng dụng chỉ có hai worker cố định ngay từ khi thiết kế, việc tạo hai bean @ConfigurationProperties riêng và inject vào factory có thể đơn giản hơn. Programmatic binding tăng trách nhiệm tự quản lý thời điểm, lỗi và validation.

Chỉ chọn nó khi **tính động** thực sự đem lại lợi ích rõ.

## 7. API Binder: thành phần cơ bản

Những lớp và API cần nhận diện:

| Thành phần | Vai trò |
| --- | --- |
| Binder | Điểm vào để bind từ các ConfigurationPropertySource |
| Binder.get(Environment) | Tạo/lấy Binder dựa trên nguồn cấu hình của Environment |
| bind(prefix, Class<T>) | Đọc một prefix và bind thành kiểu Java cụ thể |
| bind(prefix, Bindable<T>) | Dùng mô tả kiểu đích chi tiết |
| BindResult<T> | Kết quả bind; cho biết có bound hay không |
| Bindable<T> | Mô tả kiểu hoặc instance được dùng làm đích |
| ConfigurationPropertySource | Nguồn dữ liệu ở mô hình property dành cho binder |
| MapConfigurationPropertySource | Nguồn test/programmatic có dữ liệu từ Map |
| BindHandler | Extension point can thiệp vòng đời/cách xử lý binding |
| Converter/ConversionService | Chuyển String/property value sang kiểu đích |

Một import thường gặp:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.core.env.Environment;
~~~

### 7.1. Ví dụ nền tảng: bind một record

~~~java
import java.time.Duration;

public record HttpSettings(
        Duration connectTimeout,
        Duration readTimeout,
        int maxConnections
) {}
~~~

Cấu hình:

~~~yaml
app:
  http:
    connect-timeout: 2s
    read-timeout: 8s
    max-connections: 40
~~~

Code:

~~~java
Binder binder = Binder.get(environment);

HttpSettings http = binder
        .bind("app.http", HttpSettings.class)
        .orElseThrow(() ->
                new IllegalStateException("app.http is missing"));
~~~

Với dữ liệu này, binder có thể tạo HttpSettings với Duration 2 giây, Duration 8 giây và int 40.

Spring Boot không yêu cầu record HttpSettings phải mang @ConfigurationProperties khi **code chủ động gọi Binder**. Annotation dùng cho cách tích hợp tự động với vòng đời bean cấu hình; lời gọi Binder tường minh đã xác định prefix và kiểu đích.

### 7.2. Tên field Java và tên property

~~~text
Java record component:  readTimeout
Canonical property:     app.http.read-timeout
Environment variable:   APP_HTTP_READTIMEOUT
~~~

Binder áp dụng khả năng relaxed binding thích hợp cho nguồn cấu hình, không yêu cầu đặt field Java là read-timeout.

### 7.3. Đọc một scalar cũng được, nhưng không phải lúc nào cần

~~~java
int port = binder.bind("server.port", Integer.class)
        .orElse(8080);
~~~

Đối với một scalar đơn giản, **environment.getProperty("server.port", Integer.class, 8080)** thường dễ đọc hơn. Binder API có ý nghĩa rõ nhất khi cần xử lý **object có cấu trúc**, **prefix động** hoặc **BindResult**.

## 8. Bindable<T>: khi Class<T> chưa đủ

Với kiểu đơn giản:

~~~java
binder.bind("app.http", HttpSettings.class)
~~~

đã đủ. Nhưng Java generics như **List<Server>** hoặc **Map<String, Region>** cần giữ thông tin kiểu phần tử.

Ví dụ:

~~~java
import java.util.List;

public record Server(String host, int port) {}
~~~

YAML:

~~~yaml
app:
  servers:
    - host: primary.example.test
      port: 8080
    - host: backup.example.test
      port: 8081
~~~

Binder:

~~~java
List<Server> servers = Binder.get(environment)
        .bind("app.servers", Bindable.listOf(Server.class))
        .orElse(List.of());
~~~

Ở đây **Bindable.listOf(Server.class)** mô tả List chứa Server, không phải List không biết kiểu phần tử.

### 8.1. Binding Map

~~~yaml
app:
  regions:
    asia:
      endpoint: "https://asia.example.test"
      timeout: 3s
    europe:
      endpoint: "https://eu.example.test"
      timeout: 5s
~~~

Record:

~~~java
import java.time.Duration;

public record Region(String endpoint, Duration timeout) {}
~~~

Binder:

~~~java
Map<String, Region> regions = Binder.get(environment)
        .bind(
                "app.regions",
                Bindable.mapOf(String.class, Region.class)
        )
        .orElse(Map.of());
~~~

Bindable mang thông tin cả kiểu key và kiểu value. Điều này tiện khi cần đọc một Map ở một prefix được chọn mà không tạo một @ConfigurationProperties wrapper riêng.

### 8.2. Vì sao không dùng List.class?

~~~java
binder.bind("app.servers", List.class)
~~~

không thể hiện được **Server** là kiểu phần tử. Với collection của object, việc mất generic type có thể khiến dữ liệu chỉ được bind như các structure tổng quát hoặc không đạt kiểu đích mong muốn.

**Ưu tiên Bindable.listOf(Server.class)** hoặc mô tả kiểu đầy đủ khi dùng collection, thay vì raw generic.

### 8.3. Array và Set

Spring Boot binder hỗ trợ nhiều dạng collection với quy tắc tương ứng. Nếu muốn một nhóm giá trị duy nhất không quan tâm thứ tự, Set là lựa chọn có thể cân nhắc. Với danh sách có thứ tự hoặc phần tử theo index **[0]**, **[1]**, dùng List.

Trong thiết kế public API, đừng thay đổi kiểu từ List sang Set chỉ vì muốn ít code bind hơn. Kiểu collection phải phản ánh hợp đồng dữ liệu.

## 9. Trường hợp 5: bind vào một instance đã tồn tại

Có class kiểu JavaBean được chuẩn bị trước:

~~~java
public class PoolSettings {

    private int maxSize = 10;

    public int getMaxSize() {
        return maxSize;
    }

    public void setMaxSize(int maxSize) {
        this.maxSize = maxSize;
    }
}
~~~

Programmatic binding có thể làm việc với một object hiện có qua **Bindable.ofInstance(...)** ở các overload phù hợp:

~~~java
PoolSettings target = new PoolSettings();

PoolSettings result = binder
        .bind("app.pool", Bindable.ofInstance(target))
        .orElse(target);
~~~

Cần hiểu rõ ranh giới:

- Binder có thể điền property có cấu hình vào target theo chiến lược JavaBean tương ứng.
- Giá trị mặc định được khởi tạo trong object có thể đóng vai trò khi property không được cấp.
- Nếu target hoặc nested collection bất biến, không nên suy luận mọi kiểu đều được cập nhật.
- Tác động thay đổi state phụ thuộc kiểu đích và binding strategy; phải test trên phiên bản Spring Boot thực tế.

### 9.1. Khi nào nên dùng ofInstance?

Phù hợp hơn khi có **object mutable hoặc builder-like** đã được tạo theo một quy trình, cần binder nạp thêm thông tin cấu hình vào nó.

Không nên chọn ofInstance chỉ để né constructor của một record immutable. Với record, bind trực tiếp theo class rồi nhận kết quả thường rõ ràng hơn.

### 9.2. Rủi ro khi bind lại cùng một mutable instance

Nếu gọi binder nhiều lần trên cùng instance mutable, một số field có thể giữ state cũ hoặc bị cập nhật theo cách khó dự đoán, nhất là List/Map. Nếu mục tiêu là snapshot cấu hình mới, hãy bind vào **một object mới** và thay tham chiếu ở lớp quản lý một cách rõ ràng.

## 10. Trường hợp 6: tạo đối tượng từ một nguồn cấu hình thử nghiệm

Không cần khởi động ApplicationContext để kiểm tra mọi trường hợp Binder. Spring Boot cung cấp **MapConfigurationPropertySource**, cho phép tạo một nguồn property độc lập từ Map.

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

Map<String, Object> values = Map.of(
        "app.http.connect-timeout", "2s",
        "app.http.read-timeout", "7s",
        "app.http.max-connections", "25"
);

Binder binder = new Binder(new MapConfigurationPropertySource(values));

HttpSettings http = binder
        .bind("app.http", HttpSettings.class)
        .orElseThrow();
~~~

Ví dụ này có thể được đưa vào một unit test thuần Java. Nó rất hữu ích khi:

- Muốn xác nhận cấu trúc bind của record, nested class, List hoặc Map.
- Muốn thử tên property canonical và conversion.
- Muốn kiểm tra trường hợp một khóa không có hoặc giá trị sai kiểu.
- Không muốn cấu hình toàn bộ application context cho một phép bind nhỏ.

**Giới hạn quan trọng:** Binder được tạo từ Map này chỉ nhìn thấy dữ liệu trong nguồn đã cấp, không tự đọc application.yml, biến môi trường hoặc profile của ứng dụng thật. Đây là một **môi trường test riêng**, không phải bằng chứng về thứ tự PropertySource trong runtime.

### 10.1. Trường hợp ứng dụng có nhiều nguồn

Nếu mục tiêu là tái hiện precedence, phải cung cấp những ConfigurationPropertySource theo thứ tự phù hợp hoặc dùng ApplicationContextRunner với các property values/profile tương ứng. Một test chỉ dùng Map đơn không chứng minh CLI có thắng env hay không.

## 11. Khi nào Binder.get(environment) thuận tiện?

Trong một bean Spring:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.stereotype.Component;

@Component
public class ConfigReader {

    private final Binder binder;

    public ConfigReader(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public HttpSettings readHttp() {
        return binder.bind("app.http", HttpSettings.class)
                .orElseThrow();
    }
}
~~~

Ở đây Environment do Spring inject đã chứa hệ thống PropertySource tương ứng với ứng dụng.

Ưu điểm:

- Không cần tự dựng nguồn từ file và biến môi trường.
- Tái sử dụng precedence hiện có của Spring Boot.
- Có thể bind cấu trúc nested với conversion mà không tự parse từng key.

Hạn chế:

- Vẫn phải chủ động quy định prefix, kiểu đích và xử lý trường hợp không bound.
- Cần quản lý validation nếu cấu hình quan trọng.
- Phải cân nhắc khi nào method được gọi và cách cache kết quả.
- Không tự tạo một bean @ConfigurationProperties với metadata và lifecycle tương đương.

Nếu chỉ đọc một lần tại startup và dùng mãi, có thể tạo kết quả trong constructor/factory và inject object cấu hình vào nơi cần dùng, thay vì gọi Binder cho mỗi request.

## 12. Khi nào nên tránh gọi Binder liên tục?

Giả sử Controller có:

~~~java
@GetMapping("/price")
public int price() {
    return Binder.get(environment)
            .bind("app.pricing.base-price", Integer.class)
            .orElse(100);
}
~~~

Cách này thường không cần thiết nếu base-price là cấu hình ổn định. Nó làm mỗi request phải thực hiện tra cứu và chuyển đổi lại, tăng khó khăn khi test và dễ tạo suy nghĩ rằng property tự động cập nhật nóng.

Một thiết kế đơn giản:

~~~java
@ConfigurationProperties(prefix = "app.pricing")
public record PricingProperties(int basePrice) {}
~~~

Controller inject PricingProperties rồi đọc **properties.basePrice()**.

### 12.1. Programmatic binding không đồng nghĩa dynamic refresh

Một số nguồn cấu hình trong Environment có thể được cập nhật bằng cơ chế riêng, nhưng:

- Biến môi trường của tiến trình Java thường không tự thay đổi khi shell khác set biến.
- Một object đã bind không tự được cập nhật theo nguồn.
- Việc gọi binder lần nữa chỉ cho thấy các nguồn **đang có sẵn tại thời điểm gọi**, không bảo đảm hệ thống đã refresh toàn bộ Config Data hay các bean liên quan.

Nếu cần cập nhật runtime, phải xây dựng hoặc sử dụng cơ chế refresh phù hợp, xác định khi nào nguồn được nạp lại, ai kiểm tra dữ liệu và cách thay thế snapshot một cách an toàn.

### 12.2. Bind theo yêu cầu là một quyết định vòng đời

Có thể hợp lý nếu một chức năng chỉ được nạp theo yêu cầu, nhưng cần làm rõ **mỗi lần gọi** là mong muốn hay chỉ **lần đầu rồi cache**. Với cấu hình ít thay đổi, nên hạn chế bind nhiều lần không cần thiết.

## 13. BindResult và xử lý lỗi đúng cách

Một lời gọi:

~~~java
BindResult<HttpSettings> result =
        binder.bind("app.http", HttpSettings.class);
~~~

có các tình huống:

1. **Bound thành công:** result.isBound() là true; result.get() trả HttpSettings.
2. **Không tìm được dữ liệu thích hợp để bind:** result có thể không bound; xử lý fallback theo hợp đồng.
3. **Binding thất bại:** có thể ném exception, ví dụ chuyển kiểu sai hoặc tạo object thất bại.

Không nên gộp cả tình huống 2 và 3 thành “không có cấu hình”.

Ví dụ cách xử lý:

~~~java
BindResult<HttpSettings> result =
        binder.bind("app.http", HttpSettings.class);

if (!result.isBound()) {
    throw new IllegalStateException(
            "Missing required configuration: app.http"
    );
}

HttpSettings http = result.get();
~~~

### 13.1. Không dùng fallback cho lỗi sai kiểu

Với cấu hình:

~~~yaml
app:
  http:
    max-connections: "many"
~~~

record cần int. Khi bind, chuỗi **many** không tự trở thành một giá trị vắng mặt có thể được xử lý bằng **orElse(new HttpSettings(...))**.

Nếu dữ liệu được cấp nhưng sai kiểu, nên báo lỗi để người vận hành sửa cấu hình, thay vì âm thầm chuyển sang giá trị mặc định làm thay đổi hành vi hệ thống.

### 13.2. Trả Optional ở API ứng dụng

Một lớp đọc có thể thể hiện “tùy chọn”:

~~~java
import java.util.Optional;

public Optional<TelemetrySettings> readTelemetry() {
    var result = binder.bind(
            "app.telemetry",
            TelemetrySettings.class
    );
    return result.isBound()
            ? Optional.of(result.get())
            : Optional.empty();
}
~~~

Đây là **hợp đồng của API do ứng dụng viết**, không phải Binder tự tạo Optional cho mọi lời gọi.

Nếu thiết kế yêu cầu data hợp lệ mới được trả, cần bổ sung validation trước khi đưa object ra bên ngoài.

## 14. Vì sao Binder có thể xử lý Duration và nested object?

Spring Boot Binder kết hợp nhiều bước:

~~~text
Tên prefix / đường dẫn
       |
       v
Đọc ConfigurationProperty
       |
       v
Đối chiếu tên, collection index, nested path
       |
       v
Conversion từ giá trị nguồn sang kiểu đích
       |
       v
Constructor hoặc JavaBean properties
       |
       v
Object cuối cùng
~~~

Ví dụ:

~~~yaml
app:
  storage:
    max-file-size: 25MB
    retention: 7d
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.util.unit.DataSize;

public record StorageSettings(
        DataSize maxFileSize,
        Duration retention
) {}
~~~

Binder có thể chuyển chuỗi giá trị thành DataSize và Duration theo converter của Spring Boot.

Tuy vậy, **Binder chỉ đảm bảo chuyển đổi khi giá trị có cú pháp được hỗ trợ**. Ví dụ retention="never" có thể gây lỗi conversion nếu không có converter hay cơ chế xử lý riêng.

### 14.1. Không tự đổi tất cả sang String

Một lựa chọn kém:

~~~java
Map<String, String> config = ...
int retries = Integer.parseInt(config.get("max-retries"));
Duration timeout = Duration.parse(config.get("timeout"));
~~~

Đoạn code phải tự xử lý tên, default, kiểu, đơn vị, lỗi, nested path và precedence. Binder được thiết kế để xử lý các trách nhiệm này nhất quán hơn.

Nếu cấu hình có cấu trúc, hãy bind trực tiếp sang kiểu đích thay vì lấy tất cả dạng String rồi tự parse.

## 15. Những điểm không thay đổi khi chuyển sang programmatic binding

Đổi cách gọi API **không làm thay đổi**:

- Thứ tự ưu tiên các PropertySource đã có.
- Quy tắc đặt tên canonical nên dùng.
- Ý nghĩa của dấu chấm và dấu gạch ngang trong đường dẫn property.
- Quy tắc giải quyết profile hoặc Config Data import.
- Nguyên tắc List thường bị thay thế bởi List của nguồn ưu tiên cao.
- Quy tắc Map có thể kết hợp các key khi nhiều nguồn cùng cung cấp dữ liệu.
- Việc dữ liệu sai kiểu cần được báo là lỗi.
- Các yêu cầu an toàn và bảo mật của hệ thống.

Nói cách khác, **programmatic binding đổi cách yêu cầu Binder làm việc, không thay thế các nguyên lý externalized configuration**.

## 16. Nested object với Binder

YAML:

~~~yaml
app:
  notification:
    enabled: true
    delivery:
      retry:
        max-attempts: 3
        backoff: 250ms
      batch:
        max-size: 50
~~~

Model:

~~~java
import java.time.Duration;

public record NotificationSettings(
        boolean enabled,
        Delivery delivery
) {
    public record Delivery(Retry retry, Batch batch) {}
    public record Retry(int maxAttempts, Duration backoff) {}
    public record Batch(int maxSize) {}
}
~~~

Bind:

~~~java
NotificationSettings settings = binder
        .bind("app.notification", NotificationSettings.class)
        .orElseThrow();
~~~

Đường dẫn logic:

~~~text
app.notification.enabled
app.notification.delivery.retry.max-attempts
app.notification.delivery.retry.backoff
app.notification.delivery.batch.max-size
~~~

Binder có thể tạo các record nested theo constructor binding khi kiểu đích và dữ liệu phù hợp. Không cần gọi bind riêng cho từng field.

### 16.1. Khi phải bind từng nhánh riêng

Nếu Delivery là tùy chọn và chỉ một module cần Batch, có thể bind:

~~~java
NotificationSettings.Batch batch = binder
        .bind(
            "app.notification.delivery.batch",
            NotificationSettings.Batch.class
        )
        .orElseThrow();
~~~

Đây là một cách để chỉ đọc một nhánh. Tuy nhiên, nếu dữ liệu phải được kiểm tra nhất quán theo một invariant giữa Retry và Batch, bind từng nhánh rời rạc có thể làm mất bối cảnh validation tổng thể. Trong trường hợp đó, bind cả NotificationSettings rồi validate object đầy đủ có thể tốt hơn.

## 17. List, Map và các quy tắc nguồn

Ví dụ List:

~~~yaml
app:
  servers:
    - host: alpha.example.test
      port: 8080
    - host: beta.example.test
      port: 8081
~~~

~~~java
public record Server(String host, int port) {}

List<Server> servers = binder
        .bind("app.servers", Bindable.listOf(Server.class))
        .orElse(List.of());
~~~

Ví dụ Map:

~~~yaml
app:
  labels:
    owner: platform
    region: asia
~~~

~~~java
Map<String, String> labels = binder
        .bind(
            "app.labels",
            Bindable.mapOf(String.class, String.class)
        )
        .orElse(Map.of());
~~~

Khi có nhiều nguồn:

- **List** từ nguồn ưu tiên cao thường thay thế List từ nguồn ưu tiên thấp, không tự nối các phần tử.
- **Map** có thể kết hợp key từ các nguồn khác nhau, còn key trùng chọn giá trị theo precedence.
- Nếu Map key chứa dấu chấm hoặc ký tự đặc biệt, cần chú ý bracket notation ở nguồn phù hợp.

Chọn Binder API không thay đổi quy tắc merge/replacement này.

### 17.1. Map không phải luôn thích hợp cho tenant động

Nếu Map chứa tất cả tenant và được bind ở startup, các tenant có thể được validation cùng lúc. Đây là lựa chọn phù hợp khi số lượng tenant vừa phải và cấu hình đầy đủ phải hợp lệ trước khi ứng dụng nhận request.

Nếu hệ thống có hàng nghìn tenant được kích hoạt từng đợt, hoặc một số tenant có cấu hình chỉ khi cần, binding theo prefix động có thể đem lại lợi ích. Khi đó phải bổ sung caching, validation và authorization, vì Binder không tự chịu trách nhiệm cho các cơ chế này.

## 18. Validation: khác biệt rất quan trọng với annotation

Với @ConfigurationProperties:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotBlank String baseUrl,
        @Valid Pool pool
) {
    public record Pool(@Min(1) int maxSize) {}
}
~~~

Khi bean được đăng ký qua cơ chế configuration properties và dự án có Jakarta Validation provider phù hợp, Spring Boot có cơ chế validation khi binding.

**Với một lời gọi Binder API tường minh, đừng mặc định rằng chỉ vì record có @Validated nên toàn bộ validation của bean configuration properties cũng được chạy giống hệt.** Programmatic binding cần tự quyết định cách yêu cầu kiểm tra hợp lệ.

### 18.1. Cách đơn giản: bind rồi dùng Jakarta Validator

Giả sử ứng dụng inject **jakarta.validation.Validator**:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

public final class ClientConfigReader {

    private final Binder binder;
    private final Validator validator;

    public ClientConfigReader(
            Environment environment,
            Validator validator
    ) {
        this.binder = Binder.get(environment);
        this.validator = validator;
    }

    public ClientProperties read() {
        ClientProperties settings = binder
                .bind("app.client", ClientProperties.class)
                .orElseThrow();

        Set<ConstraintViolation<ClientProperties>> violations =
                validator.validate(settings);

        if (!violations.isEmpty()) {
            throw new IllegalStateException(
                    "Invalid app.client configuration: "
                    + violations.iterator().next().getPropertyPath()
            );
        }

        return settings;
    }
}
~~~

Đoạn ví dụ chỉ đưa property path vào thông báo lỗi, tránh in giá trị cấu hình có thể chứa dữ liệu nhạy cảm.

Để code dùng được, phải có validator provider và cơ chế inject/khởi tạo Validator phù hợp. Trong Spring Boot 3.x, dependency thường dùng là **spring-boot-starter-validation**.

### 18.2. @Valid trên nested object vẫn cần thiết

Nếu ClientProperties có Pool và muốn kiểm tra constraint **@Min(1)** bên trong Pool, cần cascade phù hợp:

~~~java
public record ClientProperties(
        @NotBlank String baseUrl,
        @Valid @NotNull Pool pool
) {}
~~~

**@Valid** đi sâu vào Pool; **@NotNull** kiểm tra Pool phải tồn tại. Chỉ dùng @Valid không tự cấm null.

### 18.3. Programmatic validation là trách nhiệm của caller

Với Binder API, caller phải quyết định:

1. Cấu hình có được phép thiếu hoàn toàn không?
2. Nếu có object nhưng sai constraint, nên dừng startup hay bỏ module?
3. Có cần validate nested List/Map không?
4. Có cần kiểm tra invariant nhiều field như timeout > backoff?
5. Lỗi có được phép hiển thị dữ liệu raw không?

Nếu tất cả nhóm cấu hình của ứng dụng cần fail-fast ở startup, tự triển khai các câu trả lời trên bằng Binder ở nhiều nơi có thể phức tạp hơn dùng @ConfigurationProperties.

## 19. BindHandler — khi cần can thiệp quy trình bind

**BindHandler** là một extension point nâng cao của Spring Boot binder. Nó cho phép theo dõi hoặc điều chỉnh quá trình bind tại các hook do API quy định, chẳng hạn lúc bắt đầu bind, lúc bind thành công, khi có lỗi và khi kết thúc.

Một số nhu cầu có thể dẫn tới BindHandler:

- Muốn phát hiện property chưa được bind ở một nhóm.
- Muốn xử lý một chính sách lỗi đặc biệt, có giới hạn phạm vi.
- Muốn tích hợp validation ở quá trình bind thay vì validate object sau đó.
- Muốn quan sát có kiểm soát tên property và trạng thái bind phục vụ chẩn đoán.
- Muốn dựng một quy trình binding của framework/module dùng chung.

### 19.1. Cách dùng overload có BindHandler

Trong các phiên bản Spring Boot hỗ trợ, Binder có overload nhận một **Bindable<T>** và **BindHandler**:

~~~java
BindResult<HttpSettings> result = binder.bind(
        "app.http",
        Bindable.of(HttpSettings.class),
        handler
);
~~~

Ở đây **handler** đại diện một BindHandler được xây dựng theo chính sách cụ thể. Đây là khung minh họa API, không phải một ví dụ hoàn chỉnh tự khai báo handler.

**Không nên thêm BindHandler chỉ để đọc một record đơn giản.** Nó có thể tạo ra quy tắc lỗi hoặc lifecycle khó hiểu nếu nhiều module cùng can thiệp.

### 19.2. Không dùng ignore-errors để che cấu hình sai

Spring Boot có những BindHandler dùng cho chính sách lỗi đặc biệt, nhưng chủ động bỏ qua lỗi bind là quyết định rủi ro.

Ví dụ một maxConnections sai kiểu có thể khiến ứng dụng chạy với default mà không ai biết vì đã ignore lỗi. Đối với URL, credential, giới hạn tài nguyên hoặc thông số production quan trọng, nên để lỗi rõ ràng thay vì tự động bỏ qua.

### 19.3. Strict binding không phải một Boolean chung cho mọi thứ

Một yêu cầu như “phải báo lỗi nếu còn thuộc tính không được bind” có thể cần một handler hoặc cấu hình strict phù hợp. Nhưng cần hiểu:

- Một prefix có thể chứa thuộc tính dành cho nhiều version/module.
- Map key và List index phải được diễn giải theo kiểu Java.
- Những property từ nhiều nguồn có thể trùng logical name.
- Kiểm tra thuộc tính lạ khác với kiểm tra giá trị sai kiểu.

Khi áp dụng strict binding cho một module, hãy viết test với tên khóa đúng, khóa sai và nested properties để xác nhận phạm vi kiểm tra.

## 20. Một nguồn độc lập: MapConfigurationPropertySource

Nếu một thư viện có cấu hình dạng Map đã chuẩn hóa:

~~~java
Map<String, Object> sourceData = Map.of(
        "module.worker.concurrency", "4",
        "module.worker.enabled", "true"
);
~~~

có thể tạo:

~~~java
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

Binder binder = new Binder(
        new MapConfigurationPropertySource(sourceData)
);

WorkerSettings settings = binder
        .bind("module.worker", WorkerSettings.class)
        .orElseThrow();
~~~

Record:

~~~java
public record WorkerSettings(int concurrency, boolean enabled) {}
~~~

Đây là một lựa chọn cho **thư viện, test hoặc framework module** cần sử dụng khả năng binding nhưng chưa hoặc không muốn đưa dữ liệu vào Spring Environment chung.

### 20.1. Vì sao không cứ đưa dữ liệu vào System properties?

Tự chèn dữ liệu vào **System.setProperty** để Binder nhìn thấy có nhiều nhược điểm:

- Thay đổi trạng thái toàn cục của JVM.
- Có thể ảnh hưởng các test chạy song song.
- Trộn cấu hình của module với cấu hình khác.
- Khó phục hồi trạng thái trước khi test.
- Không quản lý nguồn và precedence rõ ràng.

Một MapConfigurationPropertySource độc lập giúp tạo phạm vi dữ liệu rõ hơn cho thử nghiệm hoặc một phép bind cô lập.

### 20.2. Không dùng nguồn test để đánh giá precedence runtime

Một Binder tạo từ đúng một Map không chứng minh được kết quả khi ứng dụng thực nhận env var, JVM system property và CLI cùng lúc. Đối với vấn đề precedence, nên test qua ApplicationContextRunner hoặc cấu hình một tập nguồn tương ứng.

## 21. Trường hợp tạo cấu hình cho plugin/module mở rộng

Một ứng dụng có thể tải các module bằng tên:

~~~yaml
plugins:
  cache:
    enabled: true
    ttl: 10m
  audit:
    enabled: false
    batch-size: 100
~~~

Mỗi plugin có kiểu cấu hình khác nhau. Plugin manager có thể đọc danh sách plugin được phép, rồi bind prefix thích hợp sang kiểu class đã biết.

Ví dụ:

~~~java
public record CachePluginSettings(boolean enabled, Duration ttl) {}
public record AuditPluginSettings(boolean enabled, int batchSize) {}
~~~

~~~java
CachePluginSettings cache = binder
        .bind("plugins.cache", CachePluginSettings.class)
        .orElseThrow();

AuditPluginSettings audit = binder
        .bind("plugins.audit", AuditPluginSettings.class)
        .orElseThrow();
~~~

Nếu plugin manager chọn module bằng một registry, có thể tạo một layer programmatic binding chung.

**Dù vậy:** không bind class tùy ý được chỉ định bằng chuỗi không tin cậy từ request hoặc nguồn người dùng. Chọn lớp đích từ registry do ứng dụng kiểm soát, không dùng reflection theo input ngoài để xác định một kiểu bất kỳ.

## 22. Khi một module cần cấu hình trước khi tạo bean nghiệp vụ

Có một số nhu cầu khởi tạo framework:

- Tạo các bean theo danh sách cấu hình có số lượng thay đổi.
- Chọn một implementation theo thuộc tính cấu hình.
- Tạo client cho nhiều endpoint theo registry.
- Cấu hình một thư viện không có tích hợp @ConfigurationProperties sẵn.
- Đọc thông tin để quyết định có đăng ký module hoặc bean nào.

Programmatic binding có thể hỗ trợ bước **đọc cấu hình để ra quyết định**, nhưng cần chú ý lifecycle.

Nếu việc chọn bean chỉ dựa trên một property boolean/string đơn giản, các annotation điều kiện như **@ConditionalOnProperty** hoặc auto-configuration của Spring Boot thường phù hợp.

Nếu cần bind một cấu trúc phức tạp để quyết định cách dựng một nhóm bean, Binder API có thể là một công cụ của cấu hình framework nâng cao.

### 22.1. Không lạm dụng khởi tạo bean quá sớm

Các thành phần thực thi ở giai đoạn bootstrap có thể hoạt động trước khi mọi nguồn cấu hình hoặc bean hỗ trợ được tạo xong, tùy extension point. Nếu gọi Binder ở giai đoạn không phù hợp, kết quả có thể thiếu nguồn hoặc không có converter mà ứng dụng mong muốn.

Khi dùng các extension point đặc biệt trong Spring Boot, phải xác định:

- Những PropertySource nào đã sẵn sàng.
- ConversionService và placeholder resolution nào đang được sử dụng.
- Có thể inject Environment/Validator ở thời điểm đó không.
- Có nên để Spring Boot auto-configuration quản lý thay vì tự làm không.

Không suy ra rằng Binder.get(environment) từ một ApplicationRunner và Binder trong một hook rất sớm luôn thấy cùng trạng thái môi trường.

## 23. Constructor binding và JavaBean binding với Binder

Giả sử record:

~~~java
public record PoolSettings(int maxSize, boolean enabled) {}
~~~

Binder có thể dùng constructor để tạo record.

Một JavaBean:

~~~java
public class PoolSettingsBean {
    private int maxSize;
    private boolean enabled;

    public int getMaxSize() { return maxSize; }
    public void setMaxSize(int maxSize) { this.maxSize = maxSize; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}
~~~

Binder có thể điền giá trị qua JavaBean properties.

Không cần đổi record thành JavaBean chỉ vì chuyển từ annotation sang programmatic binding. Kiểu đích, constructor và metadata binding mới là yếu tố quyết định cách binder tạo object.

### 23.1. Collection mutable/immutable

Với getter-only JavaBean chứa List/Map mutable đã khởi tạo, binder có những cơ chế cập nhật collection tùy trường hợp hỗ trợ. Nếu collection là **List.of** hoặc một unmodifiable wrapper và không có setter, việc bind cập nhật có thể không khả thi.

Với record, nên bind List/Map qua constructor rồi **defensive copy** nếu cần trạng thái chỉ đọc. Programmatic binding không làm collection tự trở thành immutable.

## 24. Giá trị mặc định: nên đặt ở đâu?

Một nhóm cấu hình có thể có default từ:

1. File nền **application.yml**.
2. Giá trị trong JavaBean field initializer.
3. Constructor hoặc compact constructor của record.
4. **@DefaultValue** của cơ chế constructor binding được hỗ trợ.
5. Fallback do code xử lý sau **BindResult**.

Ví dụ:

~~~java
HttpSettings http = binder
        .bind("app.http", HttpSettings.class)
        .orElse(new HttpSettings(
                Duration.ofSeconds(2),
                Duration.ofSeconds(5),
                10
        ));
~~~

Fallback này áp dụng khi toàn bộ kết quả bind không có, không phải một quy tắc mặc định riêng cho từng field thiếu bên trong HttpSettings.

### 24.1. Default cho từng field khác default cho object

Giả sử app.http chỉ có:

~~~yaml
app:
  http:
    read-timeout: 8s
~~~

Binder có thể tạo một HttpSettings với một số thành phần còn thiếu/null/giá trị nguyên thủy mặc định tùy kiểu đích và constructor. **orElse(...)** sẽ không được chọn chỉ vì một field bên trong thiếu, nếu toàn bộ object đã được bind.

Muốn default riêng cho connectTimeout, hãy dùng cấu hình nền, constructor logic hoặc một cơ chế default của binder phù hợp. Muốn phát hiện thiếu, dùng validation.

### 24.2. Default có thể che lỗi triển khai

Nếu endpoint production bắt buộc được cấp nhưng code dùng:

~~~java
.orElse(new PartnerSettings("http://localhost:8080", Duration.ofSeconds(5)))
~~~

thì production có thể chạy nhầm localhost khi cấu hình vắng mặt. Đối với URL, secret hoặc cấu hình an toàn quan trọng, nên yêu cầu property bắt buộc và báo lỗi rõ thay vì một fallback “hợp lệ” nhưng không an toàn.

## 25. Một factory dùng Binder đúng phạm vi

Ví dụ một service muốn đọc những tùy chọn của từng loại job một lần rồi giữ snapshot:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class JobSettingsFactory {

    private final Binder binder;
    private final Map<String, JobSettings> cache =
            new ConcurrentHashMap<>();

    public JobSettingsFactory(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public JobSettings get(String jobType) {
        if (!jobType.equals("mail") && !jobType.equals("index")) {
            throw new IllegalArgumentException("Unsupported job type");
        }
        return cache.computeIfAbsent(jobType, this::load);
    }

    private JobSettings load(String jobType) {
        String prefix = "app.jobs." + jobType;
        return binder.bind(prefix, JobSettings.class)
                .orElseThrow(() ->
                        new IllegalStateException("Missing " + prefix));
    }
}
~~~

Record:

~~~java
public record JobSettings(int concurrency, boolean enabled) {}
~~~

Ý nghĩa:

- Prefix nằm trong tập đã cho phép.
- Binder đọc theo yêu cầu khi lần đầu cần job type.
- Factory lưu kết quả để không bind lại trên mọi request.
- Lần sau nhận cùng object.

**Cần cân nhắc:** nếu cấu hình được refresh runtime, cache này sẽ giữ snapshot cũ cho đến khi ứng dụng chủ động vô hiệu hóa/thay thế. Cache không phải cơ chế refresh.

### 25.1. Validation phải là một phần của load

Nếu concurrency phải lớn hơn 0, phương thức load nên validate trước khi đưa object vào cache. Một bản sai được cache có thể khiến nhiều tác vụ sử dụng giá trị không hợp lệ.

Có thể đặt invariant trong record:

~~~java
public record JobSettings(int concurrency, boolean enabled) {
    public JobSettings {
        if (concurrency < 1) {
            throw new IllegalArgumentException(
                    "job concurrency must be positive"
            );
        }
    }
}
~~~

Hoặc dùng Jakarta Validation được gọi tường minh. Chọn cách phù hợp với quy mô hợp đồng cấu hình.

## 26. Khi dùng Binder để dựng nhiều client khác nhau

Một tình huống điển hình là cấu hình nhiều outbound client với tên được quyết định bởi module:

~~~yaml
clients:
  catalog:
    endpoint: "https://catalog.example.test"
    timeout: 3s
  pricing:
    endpoint: "https://pricing.example.test"
    timeout: 6s
~~~

Record:

~~~java
public record HttpClientSettings(
        String endpoint,
        Duration timeout
) {}
~~~

Factory:

~~~java
public HttpClientSettings load(String clientName) {
    if (!Set.of("catalog", "pricing").contains(clientName)) {
        throw new IllegalArgumentException("Unknown client");
    }

    return binder
            .bind("clients." + clientName, HttpClientSettings.class)
            .orElseThrow();
}
~~~

Đây là cách tái sử dụng cùng một kiểu dữ liệu cho nhiều prefix.

Nếu tất cả client đã được biết ở startup và yêu cầu startup fail khi bất kỳ client nào sai, một **@ConfigurationProperties(prefix="clients")** với **Map<String, HttpClientSettings>** kết hợp validation thường dễ duy trì hơn.

## 27. Programmatic binding cho cấu hình bên ngoài Spring Environment

Một số thư viện nhận cấu hình Map hoặc PropertySource riêng, có nhu cầu dùng chung converter/binder thay vì tự xây parser.

Ví dụ nguồn từ một file hay API đã được **đọc và xác thực bởi code của ứng dụng** rồi chuyển thành Map<String, Object>. Có thể đưa nó vào MapConfigurationPropertySource và bind theo prefix:

~~~java
Map<String, Object> values = Map.of(
        "engine.pool.size", "16",
        "engine.pool.idle-timeout", "30s"
);

Binder binder = new Binder(
        new MapConfigurationPropertySource(values)
);

EngineSettings engine = binder
        .bind("engine.pool", EngineSettings.class)
        .orElseThrow();
~~~

Record:

~~~java
public record EngineSettings(int size, Duration idleTimeout) {}
~~~

**Lợi ích:** cùng cơ chế nested binding/conversion với các cấu hình chuẩn mà không cần nhét mọi dữ liệu vào global Environment.

**Giới hạn:** không tự có profile handling, Config Data imports, CLI precedence hoặc bean lifecycle. Những thứ đó chỉ có nếu nguồn và hệ thống xung quanh được tích hợp phù hợp.

### 27.1. Binder không phải client truy vấn dịch vụ config từ xa

Nếu config nằm ở database hay HTTP API, Binder không tự kết nối và tải dữ liệu đó. Ứng dụng hoặc framework phải nạp dữ liệu và biến nó thành ConfigurationPropertySource/Environment phù hợp trước khi bind.

Không dùng Binder như một giải pháp thay thế trực tiếp cho một hệ thống quản lý secret, config server hoặc caching dữ liệu từ xa.

## 28. Rủi ro khi tự trộn nhiều nguồn cấu hình

Nếu tự tạo Binder với nhiều ConfigurationPropertySource, **thứ tự các nguồn** trở thành trách nhiệm của code. Một sai sót có thể khiến nguồn default thắng nguồn override hoặc kết quả khác Spring Environment.

Đối với nhu cầu “đọc giống hệt ứng dụng đang chạy”, thường nên:

~~~java
Binder binder = Binder.get(environment);
~~~

thay vì dựng lại danh sách nguồn bằng tay.

Đối với unit test cô lập, dùng đúng một MapConfigurationPropertySource là đủ. Đừng lấy kết quả test một Map để tuyên bố rằng toàn bộ precedence của application.yml, env và CLI đã được kiểm chứng.

## 29. Khi nào phải dùng @ConfigurationProperties dù có Binder?

Các trường hợp nên ưu tiên @ConfigurationProperties:

### 29.1. Cấu hình ổn định, biết từ lúc build

Ví dụ:

~~~yaml
app:
  email:
    sender: "noreply@example.test"
    retries: 3
~~~

Một EmailProperties bean dễ hiểu hơn một EmailConfigReader gọi Binder ở nhiều service.

### 29.2. Cần fail-fast và validation tập trung

Nếu cấu hình URL, password, timeouts, pool sizes phải hợp lệ trước khi hệ thống nhận request, @ConfigurationProperties với @Validated là đường đi chuẩn dễ giải thích.

### 29.3. Cần metadata cho IDE và tài liệu cấu hình

Cấu hình dùng @ConfigurationProperties được công cụ metadata processor hỗ trợ, tùy cách build. Điều này đem lại gợi ý property, mô tả, kiểu và khả năng phát hiện typo trong IDE.

Một Binder call được tạo từ prefix động không tự có cùng metadata. Nếu dùng Binder cho thư viện nhiều module, có thể cần xây tài liệu schema và công cụ phát hiện lỗi riêng.

### 29.4. Cần inject cùng một snapshot vào nhiều service

Một bean immutable cấu hình duy nhất, được inject vào nhiều service, dễ test và tránh lặp lại bind hơn.

### 29.5. Có quy trình quản lý và vận hành đơn giản

Programmatic binding đưa thêm logic để bảo trì: prefix, error handling, validation, caching, lifecycle. Nếu annotation giải quyết đúng bài toán, phần logic thêm có thể là gánh nặng không cần thiết.

## 30. Khi nào programmatic binding thực sự đáng giá?

| Tình huống | Lý do có thể dùng Binder |
| --- | --- |
| Prefix chọn khi runtime từ tập được phép | bind("clients." + name, Type.class) |
| Chỉ một số module được kích hoạt | Bind theo nhu cầu của module |
| Cùng một kiểu cấu hình có nhiều prefix độc lập | Tái sử dụng record/class |
| Xây framework/plugin loader | Factory kiểm soát kiểu đích, prefix và lúc bind |
| Cần xử lý prefix hoàn toàn không có | BindResult và Optional/fallback rõ |
| Cần test binder độc lập không chạy Spring context | MapConfigurationPropertySource |
| Cần bind một class do thư viện cung cấp | Không cần sửa class để thêm @ConfigurationProperties |
| Cần điều khiển BindHandler/conversion nâng cao | Dùng các overload/extension point tương ứng |
| Cần cập nhật một mutable bean được chuẩn bị sẵn | Bindable.ofInstance khi thích hợp |
| Bind cấu hình được tạo từ một nguồn đã chuẩn hóa bên ngoài Environment | Tạo ConfigurationPropertySource riêng |

**Điểm chung:** caller có một lý do thực tế để điều khiển quá trình bind. Nếu không, dùng annotation.

## 31. Programmatic binding không phải lúc nào tốt cho multi-tenant

Multi-tenant là ví dụ thường được viện dẫn nhưng cũng dễ bị lạm dụng.

Nếu thông tin của tenant đến từ **database và thay đổi liên tục**, mỗi request cần tenant-specific setting, Binder từ Environment có thể không phù hợp vì Environment không phải database truy vấn theo request.

Nếu cấu hình của một tập tenant được khai báo trong Config Data:

~~~yaml
app:
  tenants:
    alpha:
      timeout: 3s
    beta:
      timeout: 5s
~~~

có hai hướng hợp lý:

**Hướng A — bind Map lúc startup:**

~~~java
@ConfigurationProperties(prefix = "app")
public record TenantProperties(Map<String, TenantSettings> tenants) {}
~~~

**Hướng B — bind prefix khi cần:**

~~~java
binder.bind("app.tenants." + tenantName, TenantSettings.class)
~~~

Hướng B chỉ phù hợp khi tenantName đã được kiểm tra allowlist và việc đọc lười đem lại lợi ích. Nếu key tenant có dấu chấm hoặc ký tự đặc biệt, cách ghép prefix đơn giản còn có nguy cơ sai đường dẫn; thiết kế Map với bracket notation và giới hạn tên có thể thích hợp hơn.

**Binder không làm nhiệm vụ kiểm tra quyền truy cập giữa tenant.** Kết quả cấu hình cần được bảo vệ và không trả nguyên văn ra API công khai.

## 32. Cấu hình thiếu, rỗng và null

Đối với Binder:

~~~java
var result = binder.bind("app.client", ClientProperties.class);
~~~

đừng đánh đồng những trạng thái:

- Không có property dưới prefix.
- Có prefix nhưng chỉ một số field.
- Có field kiểu String với giá trị rỗng.
- Có giá trị YAML null.
- Có giá trị sai kiểu như retries="abc".

Một số tình huống có thể tạo object với field null/default; một số có thể cho không bound; một số ném lỗi conversion. Kết quả phụ thuộc kiểu đích, constructor, nguồn và chiến lược binding.

**Thiết kế rõ ràng:** dùng validation hoặc constructor invariant để từ chối object nửa đủ dữ liệu; chỉ dùng BindResult.orElse cho trường hợp được phép không tồn tại toàn bộ.

### 32.1. Không dùng BindResult để kiểm tra tất cả field

BindResult.isBound() không phải hàm **isValid()** của toàn bộ object. Nó trả lời liệu có kết quả binding không; các constraint nghiệp vụ phải được kiểm tra riêng.

Nếu một endpoint bắt buộc không rỗng:

~~~java
public record ClientProperties(String endpoint) {
    public ClientProperties {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException(
                    "app.client.endpoint must not be blank"
            );
        }
    }
}
~~~

Hoặc dùng Bean Validation sau binding.

## 33. Spring profiles và việc bind bằng code

Ví dụ:

~~~yaml
# application.yml
app:
  client:
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 10s
~~~

Nếu profile prod hoạt động, Binder từ Spring Environment có thể nhận timeout=10s, theo Config Data precedence thông thường.

~~~java
ClientProperties settings = Binder.get(environment)
        .bind("app.client", ClientProperties.class)
        .orElseThrow();
~~~

Việc caller chọn prefix bằng code **không bỏ qua profile**. Ngược lại, nếu caller tự tạo Binder từ MapConfigurationPropertySource riêng chỉ có timeout=3s, nó không tự biết profile prod.

### 33.1. Không tự nối file config theo profile

Đừng dùng Binder API như lý do để tự đọc application.yml và application-prod.yml bằng parser riêng rồi kết hợp Map theo thứ tự do mình tự nghĩ. Spring Boot Config Data đã có quy tắc về profile, location groups và import. Khi muốn cùng hành vi với Boot, nên dùng Spring Environment đã được khởi tạo.

## 34. Biến môi trường và relaxed binding

Đường dẫn canonical:

~~~text
app.client.read-timeout
~~~

Tên biến môi trường được chuyển theo quy tắc chuẩn:

~~~text
APP_CLIENT_READTIMEOUT
~~~

Ba bước:

1. Dấu chấm thành dấu gạch dưới.
2. Bỏ dấu gạch ngang.
3. Chuyển chữ thành chữ hoa.

Ví dụ:

~~~bash
APP_CLIENT_READTIMEOUT=12s java -jar demo.jar
~~~

Binder từ Spring Environment có thể liên kết giá trị này với trường **readTimeout** trong class đích.

Tên **APP_CLIENT_READ_TIMEOUT** không phải phép chuyển chuẩn của **app.client.read-timeout**, vì dấu gạch ngang bị bỏ chứ không chuyển thành gạch dưới.

Programmatic binding không làm quy tắc đặt tên khác đi. Muốn kết quả dễ dự đoán, dùng canonical prefix và document tên env chuẩn.

## 35. Điều kiện về dữ liệu nhạy cảm

Một Binder thường có thể đọc bất kỳ cấu hình nào có trong những nguồn được cấp. Vì vậy cần tránh:

- Để endpoint công khai nhận prefix rồi trả object cấu hình.
- In toàn bộ BindResult, record hoặc Map nếu chứa password/token.
- Ghép prefix từ một tenantId bất kỳ mà không có allowlist.
- Thêm log debug ghi mọi key/value của Environment.
- Sử dụng một handler tùy chỉnh đưa giá trị raw vào log.
- Truyền secret vào exception message.

Nếu cần chẩn đoán, log **tên property an toàn**, tên module, loại lỗi và một mã tương quan; không log giá trị secret.

Programmatic binding còn cần tôn trọng phân quyền giữa module/tenant. Việc một dữ liệu tồn tại trong Environment không tự cho phép mọi phần code hoặc mọi request xem nó.

## 36. Cách dùng Binder trong unit test

Một bài test thuần Java:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class HttpBinderTest {

    @Test
    void bindsNestedProperties() {
        Map<String, Object> config = Map.of(
                "app.http.connect-timeout", "2s",
                "app.http.read-timeout", "8s",
                "app.http.max-connections", "25"
        );

        Binder binder = new Binder(
                new MapConfigurationPropertySource(config)
        );

        HttpSettings result = binder
                .bind("app.http", HttpSettings.class)
                .orElseThrow();

        assertThat(result.maxConnections()).isEqualTo(25);
        assertThat(result.readTimeout())
                .isEqualTo(Duration.ofSeconds(8));
    }
}
~~~

Test này quan sát:

- Property path đúng.
- Kiểu Java phù hợp.
- Conversion Duration.
- Nested naming nếu bổ sung nested record.

Nó không quan sát:

- Spring profile thực tế của ứng dụng.
- Validation được kích hoạt qua @ConfigurationProperties.
- Thứ tự env và CLI.
- Có bean được scan/inject hay không.

Mỗi loại test có mục tiêu riêng.

## 37. Test trường hợp thiếu và sai kiểu

Ví dụ thiếu toàn bộ prefix:

~~~java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
                Map.of("unrelated.value", "x")
        )
);

var result = binder.bind("app.http", HttpSettings.class);

assertThat(result.isBound()).isFalse();
~~~

Ví dụ sai kiểu:

~~~java
Map<String, Object> config = Map.of(
        "app.http.max-connections", "many"
);
~~~

Nếu record cần **int maxConnections**, phép bind có thể ném lỗi conversion. Trong test nên kiểm tra lỗi phù hợp và property gây lỗi, không cố bắt mọi Exception rồi coi đó là xử lý thành công.

### 37.1. Test validation riêng

Nếu một record có constraint Jakarta Validation, test phương thức bind rồi **validator.validate(result)**. Điều này chứng minh chương trình có đường kiểm tra dữ liệu ngay cả khi không đi qua @ConfigurationProperties auto binding.

### 37.2. Test runtime integration

Nếu chương trình dùng Binder.get(environment) và phụ thuộc profile, Config Data import hoặc command-line overrides, dùng **ApplicationContextRunner**, **@SpringBootTest** hoặc test khởi động tích hợp phù hợp. Unit test với Map độc lập là cần nhưng chưa đủ cho precedence.

## 38. Khi cần đọc một nhóm cấu hình nhưng chưa muốn tạo bean

Trong một số utility/module bootstrap, code cần một object cấu hình nhất thời mà không muốn đưa nó vào ApplicationContext như singleton bean:

~~~java
public static HttpSettings fromEnvironment(Environment environment) {
    return Binder.get(environment)
            .bind("app.http", HttpSettings.class)
            .orElseThrow();
}
~~~

Ưu điểm: phương thức rõ tên, dễ gọi, không cần tạo một bean cấu hình riêng chỉ để giữ object.

Hạn chế: caller phải quyết định lifecycle và validation. Nếu nhiều service cùng gọi phương thức này, có nguy cơ bind lặp lại và mỗi service nhận một instance khác nhau. Khi nhu cầu đã ổn định, nên cân nhắc tạo một bean cấu hình thống nhất.

## 39. Đừng quên metadata và khả năng hỗ trợ IDE

Khi dùng:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(Duration timeout, int maxConnections) {}
~~~

công cụ configuration processor có thể sinh metadata thuộc tính cho IDE, tài liệu và hỗ trợ autocomplete.

Nếu toàn bộ cấu hình được đọc qua:

~~~java
binder.bind(dynamicPrefix, DynamicSettings.class)
~~~

thì prefix/đường dẫn thực có thể không được trình phân tích tĩnh biết đến. Điều đó làm tăng nhu cầu tự ghi tài liệu:

- Các prefix hợp lệ.
- Các thuộc tính bắt buộc.
- Kiểu dữ liệu, đơn vị.
- Giá trị mặc định.
- Tên env tương ứng.
- Chính sách xử lý lỗi.
- Mối quan hệ giữa nhiều module.

**Sự linh hoạt của runtime có giá về mặt tooling.** Đây là yếu tố quan trọng khi chọn giữa annotation và programmatic binding.

## 40. Kiến trúc kết hợp: annotation cho phần ổn định, Binder cho phần động

Không cần chọn “100% annotation” hay “100% programmatic”.

Ví dụ một ứng dụng có:

~~~yaml
app:
  service:
    name: orders
    enabled: true
  integrations:
    catalog:
      timeout: 3s
    billing:
      timeout: 8s
~~~

Có thể dùng @ConfigurationProperties cho cấu hình service:

~~~java
@ConfigurationProperties(prefix = "app.service")
public record ServiceProperties(String name, boolean enabled) {}
~~~

và dùng Binder chỉ trong integration factory có nhu cầu chọn prefix:

~~~java
public IntegrationSettings readIntegration(String name) {
    String prefix = switch (name) {
        case "catalog" -> "app.integrations.catalog";
        case "billing" -> "app.integrations.billing";
        default -> throw new IllegalArgumentException(
                "Unknown integration"
        );
    };

    return binder
            .bind(prefix, IntegrationSettings.class)
            .orElseThrow();
}
~~~

Mô hình hỗn hợp này giữ **đường dữ liệu ổn định ở dạng bean có validation/metadata**, còn Binder được dùng chính xác ở nơi tính động thực sự cần.

### 40.1. Đừng để nhiều thành phần cùng “sở hữu” một prefix

Nếu ServiceProperties và IntegrationFactory đồng thời tự xử lý cùng một prefix với default/validation khác nhau, có thể xuất hiện hai cách hiểu khác nhau trong một ứng dụng.

Hãy phân định prefix nào thuộc bean cấu hình chuẩn, prefix nào được factory động sở hữu, và document việc này trong module tương ứng.

## 41. Bảng chọn nhanh

| Câu hỏi | Nếu “Có” | Hướng nên cân nhắc |
| --- | --- | --- |
| Prefix và schema cố định? | Có | @ConfigurationProperties |
| Cần bean dùng chung trong nhiều service? | Có | @ConfigurationProperties |
| Cần validation/fail-fast tự động ở startup? | Có | @ConfigurationProperties + @Validated |
| Cần chọn prefix từ tập tên ở runtime? | Có | Binder |
| Chỉ muốn bind khi module được sử dụng? | Có | Binder với lifecycle rõ |
| Cần đọc cấu hình của plugin có kiểu đích khác nhau? | Có | Binder trong plugin factory |
| Cần bind một Map thử nghiệm cô lập? | Có | MapConfigurationPropertySource + Binder |
| Chỉ cần một scalar String/int? | Có | Environment hoặc @Value |
| Cần một List/Map typed ở một prefix? | Có | Binder + Bindable hoặc @ConfigurationProperties |
| Cần bảo vệ secret/tenant isolation? | Có | Authorization/secret policy ngoài Binder |
| Cấu hình thay đổi nóng liên tục? | Có | Xem cơ chế refresh/state riêng; Binder không đủ |
| Cần autocomplete property đầy đủ? | Có | Ưu tiên @ConfigurationProperties metadata |
| Có lý do rõ để xử lý bind events/errors? | Có | BindHandler theo phạm vi kiểm soát |

## 42. Các lỗi thường gặp

### 42.1. Dùng Binder chỉ để tránh viết annotation

Một class có prefix cố định, được inject ở năm service, nhưng mỗi service đều tự gọi Binder. Kết quả là lặp code, khó thống nhất default và validation.

**Cách xử lý:** tạo một @ConfigurationProperties bean rồi inject.

### 42.2. Bỏ qua lỗi conversion

~~~java
try {
    return binder.bind("app.pool", PoolSettings.class).orElse(null);
} catch (Exception ex) {
    return null;
}
~~~

Một giá trị sai có thể bị biến thành “không có cấu hình”. **Cách xử lý:** chỉ coi no-bind là tùy chọn khi thiết kế cho phép; với dữ liệu sai, báo lỗi.

### 42.3. Prefix ghép từ request không được kiểm soát

~~~java
binder.bind("app.tenants." + request.getParameter("tenant"), Type.class)
~~~

Đây không phải kiến trúc multi-tenant an toàn tự động. **Cách xử lý:** xác thực tenant, áp dụng allowlist/quyền truy cập, xác định key canonical, tránh trả dữ liệu nhạy cảm.

### 42.4. Coi @Validated trên record là validation tự động của mọi Binder call

Programmatic binding có thể bỏ qua lớp tích hợp validation mà @ConfigurationProperties sử dụng. **Cách xử lý:** gọi validator sau bind hoặc thiết lập validation handler theo API phù hợp.

### 42.5. Gọi Binder trong mỗi request mà không cần

Config ổn định nhưng liên tục được chuyển đổi, làm code chậm và khó test hơn. **Cách xử lý:** tạo bean/snapshot hoặc cache rõ.

### 42.6. Dùng Binder với một nguồn Map riêng nhưng mong nó đọc application.yml

MapConfigurationPropertySource chỉ chứa những key đã cung cấp. **Cách xử lý:** dùng Binder.get(environment) nếu muốn đọc hệ thống nguồn Spring Boot thực tế.

### 42.7. Mong BindResult.orElse xử lý tất cả field thiếu

Một object có thể bind được dù một số field còn null/0. **Cách xử lý:** default theo field hoặc validation; không dùng orElse của toàn object như validation.

### 42.8. Không hiểu List replacement

Nếu file nền có hai server, file prod có một server, binder có thể lấy danh sách từ file prod. Đây là precedence, không phải Binder API “đọc thiếu”. **Cách xử lý:** khai báo đầy đủ List ở nguồn override.

### 42.9. Log toàn bộ object cấu hình có secret

Record toString có thể chứa password/token. **Cách xử lý:** log key/path không nhạy cảm, dùng masking và không expose BindResult ra API.

### 42.10. Kỳ vọng Binder tự refresh bean đã tạo

Một object bind trước đó vẫn là object Java cũ. **Cách xử lý:** có cơ chế reload và thay snapshot được định nghĩa, hoặc restart ứng dụng khi thay cấu hình.

## 43. Bài thực hành 1: chọn công cụ phù hợp

Xét bốn yêu cầu:

**A.** App có các thuộc tính app.mail.sender, app.mail.retries cố định, dùng trong nhiều service và cần fail-fast.

**B.** Một plugin manager chọn prefix **plugins.email** hoặc **plugins.audit** lúc khởi tạo plugin.

**C.** Controller chỉ cần đọc **server.port**.

**D.** Một unit test muốn chuyển một Map có các key app.pool.max-size và app.pool.enabled thành PoolSettings mà không mở Spring context.

Gợi ý:

- A → **@ConfigurationProperties**, thêm validation.
- B → **Binder API** trong plugin manager.
- C → **Environment.getProperty(...)** hoặc @Value.
- D → **new Binder(new MapConfigurationPropertySource(map))**.

Lý do chọn gắn với nhu cầu, không phải một API “hiện đại hơn” API khác.

## 44. Bài thực hành 2: prefix động

YAML:

~~~yaml
gateways:
  bank-a:
    endpoint: "https://bank-a.example.test"
    timeout: 3s
  bank-b:
    endpoint: "https://bank-b.example.test"
    timeout: 6s
~~~

Record:

~~~java
public record GatewaySettings(String endpoint, Duration timeout) {}
~~~

Hãy viết một phương thức **readGateway(String name)** chỉ nhận **bank-a** và **bank-b**, rồi dùng Binder bind prefix tương ứng.

Đáp án gợi ý:

~~~java
public GatewaySettings readGateway(String name) {
    if (!Set.of("bank-a", "bank-b").contains(name)) {
        throw new IllegalArgumentException("Unknown gateway");
    }

    return binder
            .bind("gateways." + name, GatewaySettings.class)
            .orElseThrow();
}
~~~

**Bài mở rộng:** nếu gateway name là key Map động, cân nhắc mô hình Map thay vì tự ghép prefix.

## 45. Bài thực hành 3: bind List có kiểu

YAML:

~~~yaml
jobs:
  scheduled:
    - name: cleanup
      interval: 1h
    - name: backup
      interval: 12h
~~~

Record:

~~~java
public record ScheduledJob(String name, Duration interval) {}
~~~

Code:

~~~java
List<ScheduledJob> jobs = Binder.get(environment)
        .bind(
                "jobs.scheduled",
                Bindable.listOf(ScheduledJob.class)
        )
        .orElse(List.of());
~~~

Hãy giải thích vì sao Bindable.listOf(ScheduledJob.class) có lợi hơn bind với List.class: nó cung cấp **kiểu phần tử**, cho phép binder chuyển từng mục thành ScheduledJob.

## 46. Bài thực hành 4: phân biệt không có cấu hình và cấu hình sai

Nguồn A:

~~~properties
# Không có khóa app.pool.*
~~~

Nguồn B:

~~~properties
app.pool.max-size=many
~~~

Record:

~~~java
public record PoolSettings(int maxSize) {}
~~~

Lời gọi:

~~~java
var result = binder.bind("app.pool", PoolSettings.class);
~~~

**Nguồn A** có thể cho không bound; caller được phép fallback nếu hợp đồng cho phép.

**Nguồn B** có thể gây lỗi chuyển kiểu sang int; không nên âm thầm đổi thành không bound. Nếu max-size bắt buộc hợp lệ, ứng dụng cần phát hiện và báo lỗi cụ thể.

## 47. Bài thực hành 5: validation

Record:

~~~java
public record HttpSettings(
        @jakarta.validation.constraints.Min(1) int maxConnections
) {}
~~~

Cấu hình:

~~~properties
app.http.max-connections=0
~~~

Binder có thể bind giá trị int 0, vì đây là số hợp lệ về mặt chuyển kiểu. Nhưng cấu hình có thể **vi phạm @Min(1)**.

Hỏi: làm sao bảo đảm object do programmatic binding tạo ra bị kiểm tra?

Gợi ý: gọi một **Jakarta Validator** với object sau bind hoặc tích hợp một validation handler phù hợp. Đừng chỉ gắn @Validated ở record rồi mặc định Binder gọi thông thường sẽ có đúng cơ chế validation của bean cấu hình.

## 48. Bài thực hành 6: sửa kiến trúc lặp binding

Code ban đầu:

~~~java
@Service
class CheckoutService {
    private final Environment environment;

    CheckoutService(Environment environment) {
        this.environment = environment;
    }

    int retries() {
        return Binder.get(environment)
                .bind("app.checkout.retries", Integer.class)
                .orElse(3);
    }
}
~~~

Nếu retries cố định trong suốt vòng đời ứng dụng và được dùng ở nhiều service, refactor:

~~~java
@ConfigurationProperties(prefix = "app.checkout")
public record CheckoutProperties(int retries) {}
~~~

Rồi inject CheckoutProperties. Dùng một bean cấu hình giúp test và quản lý default/validation tập trung, tránh Binder được gọi đi gọi lại không cần thiết.

## 49. Checklist triển khai

Khi quyết định dùng programmatic binding, hãy kiểm tra:

1. **Có lý do thực sự** để không dùng @ConfigurationProperties không?
2. **Nguồn** là Spring Environment hiện tại hay một ConfigurationPropertySource riêng?
3. **Prefix** cố định hay động? Nếu động, tập prefix được phép ở đâu?
4. **Kiểu đích** là scalar, record, JavaBean, List hay Map?
5. **Generic types** có được bảo toàn bằng Bindable không?
6. **Khi không có dữ liệu**, caller nên trả Optional, fallback hay ném lỗi?
7. **Khi có dữ liệu sai kiểu**, lỗi có được báo rõ và không bị nuốt không?
8. **Validation** được thực thi ở đâu, bao gồm nested List/Map?
9. **Thời điểm bind** là startup, lần dùng đầu hay mỗi request?
10. **Kết quả có cache không**, và chiến lược refresh nếu nguồn thay đổi?
11. **PropertySource precedence** có được bảo toàn theo yêu cầu?
12. **Tên canonical và env var** có được document đúng?
13. **Có rò rỉ secret/tenant config** qua log, exception hoặc API không?
14. **Test** đã bao gồm bound, unbound, invalid và nguồn override chưa?
15. **Công cụ IDE/metadata** có cần thêm tài liệu khi không dùng annotation không?

Nếu không trả lời rõ các câu hỏi này, một bean @ConfigurationProperties có thể là thiết kế dễ bảo trì hơn.

## 50. Ghi nhớ

- **@ConfigurationProperties** nên là lựa chọn mặc định cho một nhóm cấu hình ổn định, dùng lại qua dependency injection, với validation và metadata theo vòng đời ứng dụng.
- **Binder API** phù hợp khi code phải điều khiển **prefix, kiểu đích, thời điểm bind, nguồn dữ liệu hoặc cách xử lý kết quả**.
- **Binder.get(environment)** dùng những PropertySource hiện có trong Spring Environment, cùng hệ thống precedence mà ứng dụng đang dùng.
- **bind(prefix, Class<T>)** phù hợp với một kiểu đích cụ thể; **Bindable** giúp mô tả List, Map và những loại đích cần thông tin kiểu chi tiết.
- **BindResult.isBound()** phân biệt có/không có kết quả; nó **không phải kiểm tra hợp lệ** và không biến lỗi chuyển kiểu thành giá trị mặc định.
- **@Validated trong mô hình annotation không đồng nghĩa programmatic binding sẽ tự validate như một @ConfigurationProperties bean**. Khi cần, chủ động dùng Validator hoặc BindHandler tích hợp validation.
- **MapConfigurationPropertySource** hữu ích để test hoặc bind dữ liệu cô lập; nó không tự đọc mọi cấu hình đã có trong ứng dụng.
- **Programmatic binding không giải quyết refresh runtime, authorization, secret management hoặc caching**. Đây vẫn là trách nhiệm kiến trúc của hệ thống.
- **List/Map, relaxed names, profile và precedence** tiếp tục chịu quy tắc binder/externalized configuration; đổi API không đổi nghĩa của cấu hình.
- Một thiết kế cân bằng có thể dùng **annotation cho phần cố định** và **Binder API ở đúng nơi có tính động**.

Câu hỏi quyết định tốt nhất không phải “dùng annotation hay Binder thì ít code hơn?”, mà là: **“Ai cần kiểm soát thời điểm và phạm vi binding?”**. Nếu Spring Boot có thể tạo một bean cấu hình chuẩn ngay từ startup, dùng @ConfigurationProperties. Nếu một module phải lựa chọn prefix/kiểu nguồn khi chạy và xử lý kết quả theo hợp đồng riêng, programmatic binding là công cụ phù hợp — miễn là lỗi, validation, bảo mật và vòng đời được thiết kế rõ ràng.
