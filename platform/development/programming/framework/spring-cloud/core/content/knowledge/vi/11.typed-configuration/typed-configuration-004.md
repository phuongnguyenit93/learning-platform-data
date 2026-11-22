# Chuyển đổi `Duration`, `DataSize` và kiểu dữ liệu riêng

Cấu hình ứng dụng thường chứa những giá trị có đơn vị: timeout tính bằng mili giây, chu kỳ dọn dẹp tính bằng giây, giới hạn bộ nhớ đệm tính bằng megabyte hoặc dung lượng tải lên tính bằng byte. Nếu tất cả đều được đọc dưới dạng chuỗi rồi tự parse ở nhiều nơi, ứng dụng dễ gặp lỗi đơn vị, chuyển đổi không nhất quán và lỗi chỉ xuất hiện khi request chạy.

Spring Boot hỗ trợ binding cấu hình sang các kiểu dữ liệu có ý nghĩa như **`java.time.Duration`** và **`org.springframework.util.unit.DataSize`**. Với kiểu nghiệp vụ riêng, ứng dụng có thể đăng ký converter để chuyển chuỗi cấu hình thành value object. Các giá trị sau khi bind có thể được kiểm tra, dùng chung và kiểm thử ngay trong giai đoạn khởi tạo.

Bài học thuộc chương **Cấu hình kiểu dữ liệu** của module **SPRING_CLOUD_CORE**. Nội dung tập trung vào chuyển đổi đơn vị, cấu hình có kiểu trong Spring Boot, converter tùy chỉnh, validation và cách các giá trị này tham gia vào cấu hình của những thành phần Spring Cloud như HTTP client, discovery và service registry.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao nên bind cấu hình sang kiểu dữ liệu thay vì giữ mọi giá trị dưới dạng `String`.
2. Chuyển đổi timeout và khoảng thời gian sang `Duration`.
3. Chuyển đổi giới hạn dung lượng sang `DataSize`.
4. Sử dụng `@DurationUnit` và `@DataSizeUnit` để xác định đơn vị mặc định cho giá trị số không có hậu tố.
5. Tạo kiểu dữ liệu riêng và đăng ký `Converter<String, T>` cho `@ConfigurationProperties`.
6. Phân biệt converter dành cho configuration binding với `ConversionService` dùng chung trong ứng dụng.
7. Kết hợp chuyển đổi, default value và validation để phát hiện cấu hình sai lúc startup.
8. Kiểm thử binding thành công, giá trị biên và lỗi chuyển đổi.

## 2. Vì sao cần cấu hình có kiểu?

Giả sử một service gọi Inventory Service và có giới hạn kích thước response:

~~~yaml
clients:
  inventory:
    read-timeout: "700"
    max-response-size: "8"
~~~

Nếu hai giá trị được đọc dưới dạng chuỗi, mã ứng dụng phải tự quyết định `"700"` là mili giây hay giây, còn `"8"` là byte, kilobyte hay megabyte. Hai nhóm có thể chọn đơn vị khác nhau mà compiler không phát hiện.

Cấu hình có kiểu biểu diễn ý nghĩa rõ hơn:

~~~yaml
clients:
  inventory:
    read-timeout: 700ms
    max-response-size: 8MB
~~~

Sau khi bind:

- `readTimeout` có kiểu `Duration`.
- `maxResponseSize` có kiểu `DataSize`.
- Mã nghiệp vụ có thể gọi `toMillis()`, `toSeconds()` hoặc `toBytes()`.
- Lỗi định dạng có thể được phát hiện khi Spring khởi tạo bean cấu hình.
- Các lớp sử dụng cấu hình không phải tự parse chuỗi ở nhiều nơi.

| Giá trị cấu hình | Kiểu phù hợp | Ví dụ sử dụng |
| --- | --- | --- |
| Timeout kết nối | `Duration` | HTTP client, database pool |
| Chu kỳ refresh hoặc cleanup | `Duration` | Scheduler, cache eviction |
| TTL | `Duration` | Cache, token expiry |
| Giới hạn upload | `DataSize` | Multipart, file validation |
| Dung lượng cache | `DataSize` | Buffer, cache capacity |
| Mã vùng, tenant, loại endpoint | Value object riêng | Discovery metadata, routing policy |

Kiểu dữ liệu không tự đảm bảo giá trị hợp lệ về nghiệp vụ. Ví dụ `Duration` có thể bằng 0 hoặc âm; `DataSize` cũng có thể không phù hợp với giới hạn vận hành. Chuyển đổi kiểu và validation là hai bước bổ sung cho nhau.

## 3. Chuyển đổi `Duration`

`Duration` của Java biểu diễn một khoảng thời gian, không phải một thời điểm trên lịch. Spring Boot có bộ chuyển đổi hỗ trợ các dạng đơn vị quen thuộc và chuỗi theo chuẩn ISO-8601.

### 3.1. Các dạng giá trị thường dùng

Ví dụ:

~~~yaml
clients:
  inventory:
    connect-timeout: 250ms
    read-timeout: 2s
    retry-delay: 1m
    long-poll-timeout: PT30S
~~~

Một số cách biểu diễn:

| Giá trị | Ý nghĩa |
| --- | --- |
| `250ms` | 250 mili giây |
| `2s` | 2 giây |
| `1m` | 1 phút |
| `5h` | 5 giờ |
| `PT30S` | 30 giây theo ISO-8601 |
| `PT1H15M` | 1 giờ 15 phút theo ISO-8601 |

Với định dạng đơn giản, Spring Boot hỗ trợ các hậu tố đơn vị thời gian phổ biến như `ns`, `us`, `ms`, `s`, `m`, `h`, `d`. ISO-8601 hữu ích khi biểu diễn khoảng thời gian phức tạp hoặc cần định dạng chuẩn giữa các hệ thống.

Nên dùng hậu tố rõ ràng như `700ms` hoặc `15s` thay vì số trần. Cách viết này làm ý định dễ đọc và tránh phụ thuộc vào đơn vị mặc định.

### 3.2. Giá trị số không có hậu tố

Nếu một thuộc tính `Duration` nhận số không kèm đơn vị, Spring Boot mặc định diễn giải giá trị số là **mili giây**.

Ví dụ:

~~~yaml
clients:
  inventory:
    read-timeout: 700
~~~

Giá trị trên tương đương `700ms`, không phải `700s`.

Có thể thay đổi đơn vị mặc định cho một thuộc tính bằng `@DurationUnit`:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.convert.DurationUnit;

public class PollingProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration interval = Duration.ofSeconds(30);

    public Duration getInterval() {
        return interval;
    }

    public void setInterval(Duration interval) {
        this.interval = interval;
    }
}
~~~

Với annotation này, số trần `15` được bind thành 15 giây. Nếu cấu hình ghi `15ms`, hậu tố tường minh vẫn xác định đơn vị mili giây.

**Khuyến nghị:** dùng hậu tố trong file cấu hình để người đọc không cần tìm annotation mới hiểu đơn vị. `@DurationUnit` hữu ích khi phải tương thích với cấu hình cũ dùng số trần hoặc khi cần quy định default unit rõ ràng cho API binding.

### 3.3. Chuyển đổi và sử dụng Duration trong Java

Sau khi bind, dùng API của `Duration`:

~~~java
Duration timeout = Duration.ofMillis(700);

long millis = timeout.toMillis();
long seconds = timeout.toSeconds();
boolean expired = timeout.isZero() || timeout.isNegative();
~~~

Một số phương thức thường dùng:

- `Duration.ofMillis(value)`, `ofSeconds(value)`, `ofMinutes(value)`.
- `toMillis()`, `toSeconds()`, `toNanos()`.
- `plus(...)`, `minus(...)`, `multipliedBy(...)`.
- `isZero()`, `isNegative()`, `compareTo(...)`.

Chú ý khi chuyển một `Duration` rất lớn sang mili giây hoặc nano giây: phép chuyển có thể vượt phạm vi `long` và ném `ArithmeticException`. Không nên giả định mọi giá trị hợp lệ về cú pháp đều an toàn cho một API đích có giới hạn số học.

## 4. Chuyển đổi `DataSize`

`DataSize` của Spring biểu diễn dung lượng dữ liệu bằng một giá trị số có kiểu. Nó hữu ích cho buffer, file upload, cache, payload và các giới hạn tài nguyên.

### 4.1. Hậu tố dung lượng

Ví dụ:

~~~yaml
storage:
  max-file-size: 64MB
  buffer-size: 256KB
  cache-size: 2GB
~~~

Các đơn vị thường dùng:

| Giá trị | Ý nghĩa |
| --- | --- |
| `512B` | 512 byte |
| `256KB` | 256 kilobyte |
| `64MB` | 64 megabyte |
| `2GB` | 2 gigabyte |
| `1TB` | 1 terabyte |

Spring `DataSize` và `DataUnit` sử dụng các bội số theo cơ số 1024 cho những đơn vị kilo, mega, giga và tera. Vì vậy `1MB` theo cách biểu diễn này là `1.048.576` byte. Khi trao đổi với hệ thống dùng quy ước SI thập phân, cần thống nhất rõ đơn vị để tránh sai lệch.

### 4.2. Giá trị số không có hậu tố

Giá trị số trần của `DataSize` mặc định được hiểu là **byte**:

~~~yaml
storage:
  max-file-size: 1048576
~~~

Giá trị này là 1.048.576 byte, tương đương 1 MiB theo bội số 1024; không phải 1 megabyte theo ý nghĩa số 1.

Có thể đổi đơn vị mặc định bằng `@DataSizeUnit`:

~~~java
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

public class StorageProperties {

    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize maxFileSize = DataSize.ofMegabytes(64);

    public DataSize getMaxFileSize() {
        return maxFileSize;
    }

    public void setMaxFileSize(DataSize maxFileSize) {
        this.maxFileSize = maxFileSize;
    }
}
~~~

Với thuộc tính này, số trần `128` được hiểu là 128 megabyte. Nếu ghi `128KB`, hậu tố tường minh vẫn có hiệu lực.

### 4.3. Sử dụng DataSize

Ví dụ:

~~~java
DataSize limit = DataSize.ofMegabytes(64);

long bytes = limit.toBytes();
long kilobytes = limit.toKilobytes();
long megabytes = limit.toMegabytes();
~~~

Một số API hữu ích:

- `DataSize.ofBytes(value)`.
- `DataSize.ofKilobytes(value)`.
- `DataSize.ofMegabytes(value)`.
- `DataSize.ofGigabytes(value)`.
- `toBytes()`, `toKilobytes()`, `toMegabytes()`.
- `compareTo(...)`, `plus(...)`, `minus(...)`.

Khi truyền `DataSize` cho API chỉ nhận `int`, cần kiểm tra giới hạn `Integer.MAX_VALUE` trước khi ép kiểu. Không nên ép kiểu trực tiếp từ `long` xuống `int` vì có thể làm tràn số.

## 5. Kết hợp Duration và DataSize trong ConfigurationProperties

Một nhóm cấu hình thường chứa nhiều giá trị có đơn vị. Dùng `@ConfigurationProperties` giúp bind chúng vào một object duy nhất.

### 5.1. File application.yml

~~~yaml
clients:
  inventory:
    base-url: https://inventory.internal.example
    connect-timeout: 250ms
    read-timeout: 2s
    max-response-size: 8MB
    polling-interval: 15
~~~

Trong ví dụ này:

- `connect-timeout` là 250 mili giây.
- `read-timeout` là 2 giây.
- `max-response-size` là 8 megabyte.
- `polling-interval` là 15 giây nếu thuộc tính Java được đánh dấu `@DurationUnit(ChronoUnit.SECONDS)`.

### 5.2. Định nghĩa lớp cấu hình

~~~java
import java.net.URI;
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "clients.inventory")
public class InventoryClientProperties {

    private URI baseUrl;

    private Duration connectTimeout = Duration.ofMillis(250);

    private Duration readTimeout = Duration.ofSeconds(2);

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration pollingInterval = Duration.ofSeconds(15);

    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize maxResponseSize = DataSize.ofMegabytes(8);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }

    public Duration getPollingInterval() {
        return pollingInterval;
    }

    public void setPollingInterval(Duration pollingInterval) {
        this.pollingInterval = pollingInterval;
    }

    public DataSize getMaxResponseSize() {
        return maxResponseSize;
    }

    public void setMaxResponseSize(DataSize maxResponseSize) {
        this.maxResponseSize = maxResponseSize;
    }
}
~~~

Đăng ký lớp cấu hình bằng scan:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Hoặc đăng ký cụ thể:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryConfiguration {
}
~~~

Chọn một cách đăng ký phù hợp với cấu trúc ứng dụng. Không cần vừa scan vừa khai báo cùng một lớp ở nhiều nơi nếu điều đó tạo đăng ký trùng lặp.

### 5.3. Default value và giá trị cấu hình

Các giá trị khởi tạo trong field là default của object. Nếu property không xuất hiện, binder giữ giá trị khởi tạo đó. Nếu property có mặt, binder chuyển đổi giá trị cấu hình rồi gán vào field.

Có thể chọn cách khác:

- Dùng `@DefaultValue` trong constructor binding/record để khai báo default ngay tại tham số.
- Dùng giá trị mặc định trong file cấu hình.
- Dùng default ở field hoặc constructor của lớp Java.

Không nên đặt cùng một default ở quá nhiều tầng vì người bảo trì khó xác định giá trị nào thực sự có hiệu lực. Với giá trị quan trọng, hãy kiểm thử trường hợp không khai báo key và trường hợp có override.

## 6. Kiểu dữ liệu riêng và Converter

`Duration` và `DataSize` đã có converter hỗ trợ. Nhưng một ứng dụng thường có kiểu riêng biểu diễn khái niệm nghiệp vụ, ví dụ:

- `RegionCode`: mã vùng triển khai.
- `TenantId`: định danh tenant.
- `ServiceAlias`: tên logic của một downstream service.
- `RetryWindow`: chính sách retry có cấu trúc.
- `StorageTier`: cấp lưu trữ có quy tắc riêng.

Nếu file cấu hình chứa chuỗi cho một kiểu riêng, có thể đăng ký `Converter<String, T>` để Spring Boot binding chuyển chuỗi thành object.

### 6.1. Định nghĩa value object

Ví dụ `RegionCode` chuẩn hóa mã vùng theo dạng `vn-hcm`:

~~~java
import java.util.Locale;

public record RegionCode(String value) {

    public RegionCode {
        if (value == null) {
            throw new IllegalArgumentException("Region code is required");
        }

        String normalized = value.trim().toLowerCase(Locale.ROOT);

        if (!normalized.matches("[a-z]{2}-[a-z0-9-]{2,20}")) {
            throw new IllegalArgumentException(
                    "Region code must match language-region format"
            );
        }

        value = normalized;
    }
}
~~~

Value object chịu trách nhiệm duy trì invariant của chính nó. Mã không hợp lệ không được phép tạo ra một `RegionCode` hợp lệ giả.

### 6.2. Đăng ký Converter cho configuration binding

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
class RegionCodeConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionCode> regionCodeConverter() {
        return source -> new RegionCode(source);
    }
}
~~~

`@ConfigurationPropertiesBinding` đánh dấu converter dành cho quá trình binding `@ConfigurationProperties`. Khai báo bean method là `static` giúp tránh khởi tạo sớm lớp cấu hình trong lúc hạ tầng binding đang được thiết lập.

Converter nhận chuỗi và tạo `RegionCode`. Nếu constructor ném `IllegalArgumentException`, quá trình binding sẽ báo lỗi và ứng dụng không nên tiếp tục với mã vùng không hợp lệ.

Không nên thêm `@Component` hoặc đăng ký converter toàn cục một cách tùy tiện nếu mục tiêu chỉ là chuyển đổi trong configuration binding. `@ConfigurationPropertiesBinding` giúp giới hạn mục đích của converter và tránh làm thay đổi hành vi chuyển đổi ở những phần khác của ứng dụng.

### 6.3. Dùng kiểu riêng trong cấu hình

Khai báo property:

~~~yaml
clients:
  inventory:
    region: VN-HCM
~~~

Thêm field vào `InventoryClientProperties`:

~~~java
private RegionCode region;

public RegionCode getRegion() {
    return region;
}

public void setRegion(RegionCode region) {
    this.region = region;
}
~~~

Sau binding, giá trị `VN-HCM` trở thành `RegionCode("vn-hcm")`. Các service có thể nhận `InventoryClientProperties` và dùng `region()` hoặc `getRegion()` mà không phải lặp lại logic trim, lowercase và validate.

### 6.4. Khi nào cần Converter, ConverterFactory hoặc GenericConverter?

| API | Khi phù hợp |
| --- | --- |
| `Converter<S, T>` | Một cặp kiểu nguồn-đích rõ ràng, ví dụ `String` sang `RegionCode` |
| `ConverterFactory<S, R>` | Một kiểu nguồn chuyển sang nhiều kiểu đích cùng họ, ví dụ một hệ thống enum tùy biến |
| `GenericConverter` | Cần hỗ trợ nhiều cặp kiểu hoặc điều kiện chuyển đổi phức tạp |
| `Formatter<T>` | Chuyển đổi/định dạng gắn với biểu diễn text, thường trong web/data binding |

Đối với một value object đọc từ YAML, `Converter<String, T>` thường là lựa chọn đơn giản và dễ kiểm thử nhất.

## 7. Phân biệt converter của ConfigurationProperties và ConversionService chung

Spring có cơ chế `ConversionService` để chuyển đổi giữa các kiểu. Spring Boot dùng các converter phù hợp trong quá trình binding cấu hình. Tuy nhiên, converter đăng ký với qualifier `@ConfigurationPropertiesBinding` có mục đích dành cho configuration properties binding.

Điều này giúp tránh tình huống một converter được thêm vào chỉ để đọc YAML lại vô tình ảnh hưởng đến:

- Request parameter trong Spring MVC.
- Form binding.
- Data binding của các bean khác.
- Chuyển đổi ở những thành phần dùng `ConversionService` chung.

Nếu ứng dụng thực sự muốn một kiểu chuyển đổi được dùng rộng rãi, hãy thiết kế và đăng ký `ConversionService` phù hợp với phạm vi cần dùng. Đừng mặc định converter cấu hình sẽ có mặt trong mọi nơi gọi `conversionService.convert(...)`.

### 7.1. Không tự tạo ConversionService riêng cho mọi property

Spring Boot đã cung cấp cơ chế chuyển đổi cho các kiểu phổ biến. Với `Duration`, `DataSize`, `URI`, số và boolean, thường không cần tự viết converter.

Chỉ thêm converter khi kiểu đích có ý nghĩa nghiệp vụ hoặc format riêng. Nếu tự tạo conversion service, cần bảo đảm vẫn có các converter tiêu chuẩn mà binding cần; thay thế service mặc định không đúng cách có thể làm mất khả năng chuyển đổi có sẵn.

## 8. Validation sau khi chuyển đổi

Chuyển đổi thành công không có nghĩa giá trị phù hợp nghiệp vụ. Ví dụ:

- `Duration.ofMillis(-1)` vẫn là một Duration hợp lệ về kiểu.
- `Duration.ZERO` có thể không phù hợp với timeout hoặc polling interval.
- `DataSize.ofBytes(0)` có thể không phù hợp với giới hạn upload.
- `DataSize` lớn hơn mức ứng dụng cho phép có thể gây áp lực bộ nhớ hoặc tài nguyên.

### 8.1. Dùng Jakarta Bean Validation

Có thể bật validation trên lớp `@ConfigurationProperties`:

~~~java
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "clients.inventory")
@Validated
public class InventoryClientProperties {

    @NotNull
    private URI baseUrl;

    @NotNull
    private Duration readTimeout = Duration.ofSeconds(2);

    @NotNull
    private DataSize maxResponseSize = DataSize.ofMegabytes(8);

    @NotNull
    private RegionCode region;

    // getters/setters
}
~~~

Để dùng Jakarta Bean Validation trong Spring Boot, cần có implementation validation phù hợp, thường được đưa vào qua `spring-boot-starter-validation`. Chỉ thêm annotation mà không có provider không bảo đảm validation được thực thi.

Các constraint như `@NotNull`, `@NotBlank`, `@Min`, `@Max` phù hợp với kiểu được hỗ trợ. Không nên gắn trực tiếp constraint dành cho số nguyên lên `Duration` hoặc `DataSize` rồi kỳ vọng nó so sánh đơn vị. Với điều kiện như “timeout phải lớn hơn 0” hoặc “file size không vượt 100MB”, có thể dùng custom constraint/validator hoặc kiểm tra trong constructor/factory theo thiết kế.

### 8.2. Kiểm tra điều kiện nghiệp vụ

Ví dụ một phương thức kiểm tra rõ ràng:

~~~java
public void validateOperationalLimits() {
    if (readTimeout == null || readTimeout.isZero()
            || readTimeout.isNegative()) {
        throw new IllegalArgumentException(
                "read-timeout must be greater than zero"
        );
    }

    if (maxResponseSize == null || maxResponseSize.toBytes() <= 0) {
        throw new IllegalArgumentException(
                "max-response-size must be greater than zero"
        );
    }
}
~~~

Trong ứng dụng thật, nên thực hiện kiểm tra bằng Bean Validation hoặc một cơ chế validation tập trung để lỗi được trình bày nhất quán. Đoạn mã trên chỉ minh họa invariant.

## 9. Tích hợp Duration và DataSize với client Spring Cloud

Một nhóm cấu hình có kiểu giúp tạo client với timeout và giới hạn tài nguyên rõ ràng.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryClientConfiguration {

    @Bean
    InventoryGateway inventoryGateway(InventoryClientProperties properties) {
        return new InventoryGateway(
                properties.getBaseUrl(),
                properties.getConnectTimeout(),
                properties.getReadTimeout(),
                properties.getMaxResponseSize(),
                properties.getRegion()
        );
    }
}
~~~

`InventoryGateway` là lớp ví dụ của ứng dụng. Constructor của nó có thể nhận các kiểu:

~~~java
public InventoryGateway(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        DataSize maxResponseSize,
        RegionCode region
) {
    // Khởi tạo transport và chính sách gọi dịch vụ.
}
~~~

Ở đây các kiểu dữ liệu có thể tham gia vào nhiều quyết định:

- `connectTimeout` giới hạn thời gian thiết lập kết nối.
- `readTimeout` giới hạn thời gian chờ phản hồi theo khả năng của HTTP client.
- `maxResponseSize` được dùng để giới hạn payload hoặc buffer theo API transport.
- `region` có thể tham gia lựa chọn endpoint, metadata hoặc routing policy.

Lưu ý rằng việc bind `Duration` không tự áp dụng timeout cho HTTP client. Bean cấu hình phải chuyển giá trị sang API của transport đang dùng. Tương tự, `DataSize` không tự giới hạn response body; cần cấu hình HTTP client hoặc kiểm tra payload theo API tương ứng.

### 9.1. Timeout có thể cần nhiều cấp

Một client có thể có:

- Connection timeout.
- Response/read timeout.
- Timeout lấy connection từ pool.
- Deadline tổng của một thao tác nghiệp vụ.
- Timeout cho từng attempt khi retry.

Không gộp tất cả thành một thuộc tính `timeout` nếu chúng có ý nghĩa khác nhau. `Duration` chỉ biểu diễn khoảng thời gian; chính sách áp dụng phụ thuộc transport, client và tầng điều phối.

### 9.2. Dung lượng cũng cần xác định phạm vi

`max-response-size` có thể là giới hạn cho response body đã đọc vào bộ nhớ, nhưng không nhất thiết tương đương giới hạn file tải lên, kích thước message broker hay dung lượng cache. Hãy đặt tên property theo phạm vi rõ ràng, ví dụ:

~~~yaml
clients:
  inventory:
    max-response-size: 8MB

uploads:
  max-file-size: 32MB

cache:
  max-memory: 256MB
~~~

Mỗi thành phần sẽ bind vào property tương ứng và áp dụng theo API riêng.

## 10. Kiểm thử chuyển đổi và binding

Kiểm thử cấu hình nên bao gồm cả giá trị có hậu tố, số trần có annotation, custom converter và trường hợp không hợp lệ.

### 10.1. Kiểm tra Duration và DataSize

Ví dụ với `ApplicationContextRunner`:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.util.unit.DataSize;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            InventoryConfiguration.class,
                            RegionCodeConversionConfiguration.class
                    );

    @Test
    void bindsUnitsAndCustomType() {
        runner.withPropertyValues(
                "clients.inventory.base-url=https://inventory.example",
                "clients.inventory.connect-timeout=250ms",
                "clients.inventory.read-timeout=2s",
                "clients.inventory.polling-interval=15",
                "clients.inventory.max-response-size=8MB",
                "clients.inventory.region=VN-HCM"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            InventoryClientProperties properties =
                    context.getBean(InventoryClientProperties.class);

            assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofMillis(250));

            assertThat(properties.getReadTimeout())
                    .isEqualTo(Duration.ofSeconds(2));

            assertThat(properties.getPollingInterval())
                    .isEqualTo(Duration.ofSeconds(15));

            assertThat(properties.getMaxResponseSize())
                    .isEqualTo(DataSize.ofMegabytes(8));

            assertThat(properties.getRegion())
                    .isEqualTo(new RegionCode("vn-hcm"));
        });
    }
}
~~~

Test này giả định `InventoryConfiguration` bật `@EnableConfigurationProperties(InventoryClientProperties.class)` và converter được đăng ký trong test context. Nó kiểm tra cả suffix tường minh lẫn số trần được diễn giải theo `@DurationUnit`.

### 10.2. Kiểm tra số trần và đơn vị mặc định

Tạo test riêng để xác nhận:

| Property | Giá trị | Kết quả mong đợi |
| --- | --- | --- |
| `read-timeout` kiểu Duration, không có annotation | `700` | 700 mili giây |
| `polling-interval` có `@DurationUnit(SECONDS)` | `15` | 15 giây |
| `max-response-size` kiểu DataSize, không có annotation | `1024` | 1024 byte |
| `max-file-size` có `@DataSizeUnit(MEGABYTES)` | `64` | 64 megabyte theo DataUnit |

Các test này bảo vệ ứng dụng khi đổi tên field, di chuyển lớp cấu hình hoặc thay đổi cách binding.

### 10.3. Kiểm tra giá trị không hợp lệ

Các tình huống nên thử:

- `read-timeout=fast`: không phải duration hợp lệ.
- `max-response-size=large`: không phải data size hợp lệ.
- `region=invalid!`: không thỏa quy tắc `RegionCode`.
- `read-timeout=0ms`: có thể chuyển đổi thành công nhưng phải bị validation nghiệp vụ từ chối nếu timeout bằng 0 không hợp lệ.
- `max-response-size=0B`: chuyển đổi được nhưng không đạt giới hạn tối thiểu nếu ứng dụng yêu cầu kích thước dương.

Kiểm tra lỗi chuyển đổi khác với lỗi validation. Lỗi chuyển đổi xảy ra khi chuỗi không thể trở thành kiểu đích; lỗi validation xảy ra khi đã có object nhưng giá trị không thỏa điều kiện.

## 11. Chẩn đoán lỗi chuyển đổi khi startup

Khi `@ConfigurationProperties` không bind được, Spring Boot thường báo lỗi bind có chứa tên property và kiểu đích. Hãy đọc nguyên nhân gốc thay vì chỉ nhìn exception ngoài cùng.

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Failed to bind properties` cho Duration | Sai hậu tố hoặc format | Dùng `250ms`, `2s`, hoặc ISO-8601 |
| Duration lớn/nhỏ hơn mong đợi | Số trần dùng đơn vị mặc định khác kỳ vọng | Thêm suffix hoặc `@DurationUnit` |
| DataSize lớn/nhỏ hơn mong đợi | Số trần mặc định là byte | Dùng suffix hoặc `@DataSizeUnit` |
| `ConverterNotFoundException` | Chưa đăng ký converter cho kiểu riêng | Kiểm tra bean `@ConfigurationPropertiesBinding` |
| Value object không hợp lệ | Converter hoặc constructor từ chối dữ liệu | Kiểm tra format và thông báo lỗi |
| Bean cấu hình không được tạo | Chưa đăng ký `@ConfigurationProperties` hoặc sai prefix | Kiểm tra scan/enable và tên key |
| Validation không chạy | Thiếu validation provider hoặc chưa bật `@Validated` | Thêm starter validation và kiểm tra bean |
| Giá trị bind đúng nhưng client vẫn dùng giá trị cũ | Client đã được tạo từ cấu hình trước đó | Kiểm tra lifecycle, refresh/recreate và cách truyền property |

### 11.1. Đọc đúng property path

Nếu lỗi báo:

~~~text
Failed to bind properties under 'clients.inventory.read-timeout'
to java.time.Duration
~~~

Hãy kiểm tra đúng key và kiểu đích. Đừng chỉ sửa tên property ở file vì nguyên nhân có thể là giá trị `700seconds` không thuộc định dạng được hỗ trợ hoặc nguồn ưu tiên cao hơn đã ghi đè bằng chuỗi khác.

### 11.2. Kiểm tra property source thắng

Một giá trị hợp lệ trong `application.yml` vẫn có thể bị biến môi trường, command line hoặc Config Server ghi đè. Dùng `Environment` hoặc Actuator `env` trong môi trường được bảo vệ để kiểm tra giá trị cuối cùng và nguồn cung cấp.

### 11.3. Không bắt lỗi chuyển đổi rồi dùng default im lặng

Nếu cấu hình timeout sai format, tự bắt exception rồi thay bằng `Duration.ZERO` hoặc một giá trị tùy ý có thể che lỗi triển khai. Với cấu hình bắt buộc, nên fail startup với thông báo có property path. Với cấu hình tùy chọn, dùng default tường minh và ghi nhận việc fallback theo chính sách.

## 12. Những lưu ý về phiên bản và tương thích

Các API `Duration`, `DataSize`, `@DurationUnit`, `@DataSizeUnit`, `@ConfigurationPropertiesBinding` thuộc hệ sinh thái Spring Boot và Spring Framework. Khi nâng cấp, cần kiểm tra:

- Spring Boot release tương thích với Spring Cloud release train của dự án.
- Package import và API của annotation theo phiên bản.
- Cách đăng ký converter và thời điểm binder tạo conversion service.
- Validation API (Jakarta Validation ở các thế hệ Boot hiện đại; dự án cũ có thể dùng hệ namespace khác).
- Cách cấu hình được nạp từ Config Data hoặc bootstrap legacy.
- Các transport client có nhận `Duration` hay chỉ nhận số nguyên theo đơn vị cụ thể.

Không nên lấy version riêng mới nhất của `spring-boot` hoặc `spring-cloud-commons` để thay vào dự án mà bỏ qua BOM. Hãy dùng Spring Cloud BOM tương thích và xem dependency tree sau khi thay đổi.

## 13. Quy ước thiết kế cấu hình có kiểu

Đối với ứng dụng Spring Cloud, nên áp dụng:

1. Dùng `Duration` cho mọi thuộc tính biểu diễn khoảng thời gian; tránh đặt tên kiểu `timeoutMs` nếu có thể dùng `timeout` với suffix rõ ràng.
2. Dùng `DataSize` cho dung lượng; không lưu số byte trần ở nhiều lớp.
3. Viết hậu tố tường minh trong YAML/Properties, ví dụ `250ms`, `15s`, `8MB`.
4. Dùng `@DurationUnit` và `@DataSizeUnit` khi phải tương thích với cấu hình số trần hoặc cần quy định default unit.
5. Dùng `@ConfigurationProperties` cho nhóm cấu hình liên quan thay vì parse chuỗi ở từng service.
6. Dùng converter riêng cho value object có invariant nghiệp vụ; không tạo converter cho kiểu Spring Boot đã hỗ trợ.
7. Đăng ký converter qua `@ConfigurationPropertiesBinding` khi nó chỉ phục vụ binding.
8. Validate giá trị sau khi chuyển đổi, đặc biệt timeout, retry delay, file size và giới hạn tài nguyên.
9. Kiểm thử cả suffix, số trần, default, override từ nguồn ngoài và dữ liệu sai.
10. Xác minh client thật sự áp dụng giá trị đã bind; kiểu dữ liệu đúng chưa đủ để đảm bảo transport đã được cấu hình đúng.

## 14. Bài tập vận dụng

**Bài tập 1 — Duration.** Khai báo `connect-timeout` là `250ms`, `read-timeout` là `2s` và `polling-interval` là số `15` có `@DurationUnit(ChronoUnit.SECONDS)`. Viết test xác nhận ba giá trị sau binding.

**Bài tập 2 — DataSize.** Khai báo `max-file-size` là `32MB` và `cache-size` là số `256` có `@DataSizeUnit(DataUnit.MEGABYTES)`. Chuyển cả hai sang byte và giải thích vì sao số trần không mặc định là megabyte.

**Bài tập 3 — Custom Converter.** Tạo value object `RegionCode` hoặc `TenantId`, viết `Converter<String, T>` và đăng ký với `@ConfigurationPropertiesBinding`. Kiểm thử giá trị hợp lệ, khoảng trắng, chữ hoa và format không hợp lệ.

**Bài tập 4 — Validation.** Quy định timeout phải lớn hơn 0 và response size phải nằm trong một giới hạn được chọn. Tách test lỗi conversion khỏi test validation.

**Bài tập 5 — Nguồn cấu hình.** Đặt `read-timeout` trong file YAML, biến môi trường và tham số command line. Xác định giá trị thắng rồi kiểm tra bean `@ConfigurationProperties` nhận đúng `Duration`.

**Bài tập 6 — Tích hợp client.** Truyền `Duration` vào cấu hình HTTP client và `DataSize` vào giới hạn response. Viết test hoặc integration test chứng minh transport áp dụng các giới hạn này, không chỉ chứng minh binder chuyển đổi thành công.

## 15. Ghi nhớ và nguồn tra cứu

- `Duration` biểu diễn khoảng thời gian; giá trị số trần mặc định được hiểu là mili giây.
- `DataSize` biểu diễn dung lượng; giá trị số trần mặc định được hiểu là byte.
- `@DurationUnit` và `@DataSizeUnit` thay đổi đơn vị mặc định cho số trần; suffix tường minh vẫn thể hiện đơn vị trực tiếp.
- Spring Boot có sẵn chuyển đổi cho các kiểu phổ biến; không cần tự parse `Duration` hoặc `DataSize`.
- Với kiểu nghiệp vụ riêng, dùng `Converter<String, T>` và đăng ký qua `@ConfigurationPropertiesBinding` khi converter dành cho configuration binding.
- Chuyển đổi kiểu không thay thế validation. Timeout bằng 0 hoặc file size âm có thể cần bị từ chối theo quy tắc ứng dụng.
- `@ConfigurationProperties` chỉ bind giá trị; client/transport phải thực sự sử dụng giá trị đó.
- Khi cấu hình đến từ Spring Cloud Config hoặc nguồn ngoài, kiểm tra property source thắng và kiểm thử giá trị runtime.

Nguồn chính thức để tra cứu theo phiên bản Spring Boot/Spring Cloud của dự án:

1. [Spring Boot Reference – Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
2. [Spring Boot Reference – Duration Conversion](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion)
3. [Spring Boot Reference – DataSize Conversion](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion)
4. [Spring Boot API – `DurationUnit`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/convert/DurationUnit.html)
5. [Spring Boot API – `DataSizeUnit`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/convert/DataSizeUnit.html)
6. [Spring Boot API – `ConfigurationPropertiesBinding`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBinding.html)
7. [Spring Framework Reference – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
8. [Spring Cloud – release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
