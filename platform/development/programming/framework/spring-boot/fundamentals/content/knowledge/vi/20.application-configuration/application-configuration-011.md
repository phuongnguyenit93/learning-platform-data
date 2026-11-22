# Chuyển đổi Duration, DataSize, collection và cấu hình lồng nhau

Trong ứng dụng Spring Boot, cấu hình thường được viết trong `application.yml`, `application.properties`, biến môi trường hoặc tham số dòng lệnh. Nhưng code Java không nên phải tự tách chuỗi như `"5s"`, `"32MB"` hay tự đọc từng phần tử của một danh sách cấu hình. Spring Boot có cơ chế **type-safe configuration binding** để chuyển giá trị từ những nguồn cấu hình đó thành các đối tượng có kiểu rõ ràng.

Với `@ConfigurationProperties`, bạn có thể định nghĩa một nhóm thuộc tính dưới một prefix, rồi để Spring Boot chuyển đổi:

- `Duration`: thời lượng như `500ms`, `5s`, `2m` hoặc định dạng ISO-8601 như `PT30S`.
- `DataSize`: dung lượng như `512KB`, `32MB` hoặc `1GB`.
- Collection: `List<String>`, `Set<String>`, `List<Duration>`, `Map<String, DataSize>` và các cấu trúc có kiểu khác.
- Cấu hình lồng nhau: object, record, danh sách object và map có giá trị là object.
- Giá trị mặc định và validation để ứng dụng có thể phát hiện cấu hình thiếu hoặc không hợp lệ ngay khi khởi động.

Bài học hướng tới **Spring Boot 3.3, Java 21**, tập trung vào quy tắc chuyển đổi, cách tổ chức cấu hình, các khác biệt dễ nhầm giữa collection và map, cách kiểm thử và các lỗi thường gặp.

## 1. Từ chuỗi cấu hình đến đối tượng Java

Giả sử ứng dụng có cấu hình cho một client truyền dữ liệu:

~~~yaml
app:
  transport:
    connect-timeout: 5s
    max-in-memory: 4MB
    regions:
      - apac
      - emea
    quotas:
      images: 32MB
      documents: 8MB
    retry:
      max-attempts: 4
      backoff: 750ms
~~~

Các giá trị trong YAML được nạp vào `Environment` như các thuộc tính cấu hình. Khi một class được đăng ký để binding với prefix `app.transport`, Spring Boot dùng cơ chế binder và conversion service để tạo object Java tương ứng.

~~~mermaid
flowchart TD
    A["application.yml / properties"] --> E["Environment / PropertySources"]
    B["Biến môi trường"] --> E
    C["Command-line arguments"] --> E
    D["Nguồn cấu hình bổ sung"] --> E
    E --> F["ConfigurationProperties Binder"]
    F --> G["Relaxed name matching"]
    G --> H["Convert String → Duration / DataSize"]
    H --> I["Bind List / Map / nested objects"]
    I --> J["Validate cấu hình"]
    J --> K["TransportProperties bean"]
    K --> L["Inject vào Service / Client"]
~~~

Có ba việc riêng biệt:

1. **Nạp và ưu tiên nguồn**: `Environment` xác định giá trị hiệu lực của từng property theo property-source precedence.
2. **Binding và conversion**: Binder đối chiếu tên thuộc tính, tạo object và chuyển dữ liệu sang kiểu Java khai báo.
3. **Validation và sử dụng**: các ràng buộc được kiểm tra, sau đó service nhận bean cấu hình như một dependency.

Việc có property trong YAML chưa tự động tạo ra bean `@ConfigurationProperties`. Class cấu hình phải được đăng ký bằng một cơ chế phù hợp như `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

## 2. Vì sao nên dùng @ConfigurationProperties?

Có thể truy cập một giá trị bằng `Environment.getProperty(...)` hoặc `@Value`. Nhưng khi nhiều thuộc tính liên quan đến cùng một thành phần, một class cấu hình tập trung sẽ giúp code nhất quán hơn.

Ví dụ service dùng nhiều giá trị rời rạc có thể trở nên khó đọc:

~~~java
@Service
public class TransportClient {
    private final Duration connectTimeout;
    private final DataSize maxInMemory;

    public TransportClient(
            Duration connectTimeout,
            DataSize maxInMemory) {
        this.connectTimeout = connectTimeout;
        this.maxInMemory = maxInMemory;
    }
}
~~~

Các tham số trên chưa cho thấy nguồn cấu hình, tên property hay ý nghĩa mặc định. Nếu truyền chúng từ nhiều `@Bean` method, số lượng tham số có thể tiếp tục tăng.

Một giải pháp là gom các giá trị thành:

~~~java
@ConfigurationProperties(prefix = "app.transport")
public record TransportProperties(
        Duration connectTimeout,
        DataSize maxInMemory
) {
}
~~~

Sau khi bean được đăng ký và bind, consumer chỉ cần:

~~~java
@Service
public class TransportClient {
    private final TransportProperties properties;

    public TransportClient(TransportProperties properties) {
        this.properties = properties;
    }
}
~~~

Ở đây, `TransportProperties` là một cấu hình có kiểu rõ ràng. Nó khác với một map cấu hình tự do vì Java compiler, IDE và validation có thể giúp kiểm tra cách sử dụng các trường.

## 3. Duration: biểu diễn thời lượng

`Duration` là kiểu thuộc Java Time API:

~~~java
import java.time.Duration;
~~~

Nó biểu diễn một độ dài thời gian, chẳng hạn thời gian chờ kết nối, thời gian retry, thời hạn cache hoặc timeout của một thao tác.

Ví dụ Java thuần:

~~~java
Duration shortWait = Duration.ofMillis(500);
Duration connectTimeout = Duration.ofSeconds(5);
Duration retryDelay = Duration.ofMinutes(2);
Duration oneHour = Duration.ofHours(1);
~~~

Trong cấu hình Spring Boot, không cần tự gọi các factory method đó. Binder có thể chuyển giá trị văn bản sang `Duration`.

### 3.1. Các cách viết Duration

| Giá trị cấu hình | Ý nghĩa | Giá trị Java tương đương |
| --- | --- | --- |
| `500ms` | 500 mili giây | `Duration.ofMillis(500)` |
| `5s` | 5 giây | `Duration.ofSeconds(5)` |
| `2m` | 2 phút | `Duration.ofMinutes(2)` |
| `1h` | 1 giờ | `Duration.ofHours(1)` |
| `1d` | 1 ngày (24 giờ) | `Duration.ofDays(1)` |
| `PT30S` | ISO-8601: 30 giây | `Duration.ofSeconds(30)` |
| `PT1H30M` | ISO-8601: 1 giờ 30 phút | `Duration.ofMinutes(90)` |
| `10` | Mặc định 10 mili giây | `Duration.ofMillis(10)` |

Spring Boot hỗ trợ định dạng đơn giản kèm đơn vị và định dạng ISO-8601. Trong định dạng ngắn, các suffix thường gặp là `ns`, `us`, `ms`, `s`, `m`, `h` và `d`. `m` nghĩa là **minute**, còn `ms` nghĩa là millisecond.

Một con số trần không có hậu tố có thể gây hiểu lầm. Nếu cấu hình là:

~~~properties
app.transport.connect-timeout=5
~~~

và target là `Duration`, đơn vị mặc định là **mili giây**, không phải năm giây. Vì vậy nên ghi `5s` hoặc `5000ms` khi muốn thể hiện rõ ý định.

### 3.2. Ví dụ @ConfigurationProperties với Duration

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.transport")
public record TransportProperties(
        Duration connectTimeout,
        Duration readTimeout
) {
}
~~~

Cấu hình:

~~~yaml
app:
  transport:
    connect-timeout: 5s
    read-timeout: PT30S
~~~

Khi binding thành công:

~~~java
properties.connectTimeout().equals(Duration.ofSeconds(5));   // true
properties.readTimeout().equals(Duration.ofSeconds(30));      // true
~~~

Đây là phép so sánh giá trị `Duration`, không phải chuỗi ban đầu. Hai cách viết `30s` và `PT30S` có thể dẫn tới cùng một đối tượng về mặt giá trị.

### 3.3. @DurationUnit cho giá trị không có suffix

Nếu cấu hình hiện hành phải dùng số nguyên không có đơn vị nhưng ý nghĩa nghiệp vụ là giây, dùng `@DurationUnit`:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "app.legacy-client")
public record LegacyClientProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout
) {
}
~~~

Với:

~~~properties
app.legacy-client.timeout=10
~~~

giá trị được bind thành `Duration.ofSeconds(10)` thay vì `Duration.ofMillis(10)`.

Nếu property được viết rõ `10ms`, suffix tường minh vẫn cho biết ý nghĩa mili giây. Annotation chủ yếu đặt đơn vị mặc định cho giá trị không có suffix.

Dùng `@DurationUnit` khi cần hỗ trợ định dạng số cũ hoặc một contract cấu hình có chủ đích. Với cấu hình mới, cách viết `10s` thường dễ đọc hơn.

### 3.4. Dùng Duration cho timeout không có nghĩa timeout được áp dụng tự động

Binding chỉ tạo giá trị. Bạn vẫn phải đưa giá trị đó vào API thực hiện kết nối, retry hoặc cache.

~~~java
public final class RetryPolicy {
    private final Duration delay;

    public RetryPolicy(Duration delay) {
        this.delay = delay;
    }

    public Duration delay() {
        return delay;
    }
}
~~~

Nếu ứng dụng bind `delay=250ms` nhưng không dùng `delay` khi cấu hình client, không có cơ chế nào tự áp một timeout chỉ vì field có kiểu `Duration`.

### 3.5. Duration và Period là hai khái niệm khác nhau

`Duration` biểu diễn độ dài thời gian đo được theo giây/nano giây. `Period` biểu diễn lượng thời gian theo ngày, tháng và năm trên lịch.

Ví dụ:

~~~java
Duration timeout = Duration.ofHours(24);
Period retention = Period.ofMonths(1);
~~~

Một tháng lịch không luôn tương đương một số giây cố định. Với timeout, delay, deadline kỹ thuật và interval của một API thời gian, `Duration` thường phù hợp hơn. Với quy tắc lịch như “giữ dữ liệu một tháng”, cần cân nhắc `Period`.

## 4. DataSize: biểu diễn dung lượng

`DataSize` là kiểu của Spring:

~~~java
import org.springframework.util.unit.DataSize;
~~~

Nó biểu diễn số byte, thường dùng cho kích thước buffer, giới hạn upload, dung lượng cache hoặc kích thước dữ liệu tối đa.

Java có thể tạo giá trị theo đơn vị:

~~~java
DataSize oneKilobyte = DataSize.ofKilobytes(1);
DataSize fourMegabytes = DataSize.ofMegabytes(4);
DataSize oneGigabyte = DataSize.ofGigabytes(1);
~~~

Spring Boot hỗ trợ binding từ chuỗi có đơn vị.

### 4.1. Các giá trị DataSize

| Giá trị | Ý nghĩa theo DataSize | Số byte |
| --- | --- | ---: |
| `512B` | 512 byte | 512 |
| `1KB` | 1 kilobyte (1024 byte) | 1.024 |
| `256KB` | 256 × 1024 byte | 262.144 |
| `4MB` | 4 × 1024² byte | 4.194.304 |
| `1GB` | 1 × 1024³ byte | 1.073.741.824 |
| `10` | Mặc định 10 byte | 10 |

Một điểm dễ nhầm: các đơn vị `KB`, `MB`, `GB` trong `DataSize` dùng bội số **1024**, không phải 1000. Đây là quy ước của kiểu `DataSize` trong Spring, dù cách hiển thị thương mại của một số thiết bị có thể khác.

Những hậu tố thông dụng gồm `B`, `KB`, `MB`, `GB` và `TB`. Chữ `MB` biểu thị megabyte, khác hoàn toàn với suffix `m` dùng cho phút trong `Duration`.

### 4.2. Ví dụ DataSize trong application.yml

~~~java
import org.springframework.util.unit.DataSize;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        DataSize maxFileSize,
        DataSize memoryThreshold
) {
}
~~~

~~~yaml
app:
  upload:
    max-file-size: 20MB
    memory-threshold: 256KB
~~~

Khi binding:

~~~java
long maxBytes = properties.maxFileSize().toBytes();
long memoryBytes = properties.memoryThreshold().toBytes();
~~~

Trong Java, `DataSize` có các API như `toBytes()` để chuyển sang số byte. Nếu API hạ tầng yêu cầu kiểu `long` hoặc `int`, hãy chuyển đổi ở ranh giới sử dụng và kiểm tra giới hạn hợp lệ của API đó.

### 4.3. @DataSizeUnit thay đổi đơn vị mặc định

Nếu một cấu hình cũ dùng số nguyên và mặc định được hiểu theo megabyte:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(
        @DataSizeUnit(DataUnit.MEGABYTES)
        DataSize maxSize
) {
}
~~~

Với:

~~~properties
app.cache.max-size=64
~~~

giá trị được hiểu là **64 MB**, thay vì 64 byte. Nếu cấu hình ghi tường minh `64KB`, đơn vị trong giá trị vẫn có ý nghĩa theo suffix đó.

Không nên lạm dụng đơn vị ngầm. Cách dễ đọc cho người vận hành hơn là:

~~~properties
app.cache.max-size=64MB
~~~

### 4.4. DataSize không tự thực hiện giới hạn dung lượng

Nếu bạn tạo một class có field `DataSize maxFileSize`, Spring chỉ bind con số. Nó không tự chặn upload hoặc giới hạn bộ nhớ của một thư viện tùy ý. Một service hoặc auto-configuration tương ứng phải đọc field đó và áp vào API thực hiện giới hạn.

Ví dụ Spring Boot có các cấu hình multipart riêng của framework; những property tự định nghĩa dưới `app.upload` không tự thay thế các property chuẩn như `spring.servlet.multipart.max-file-size`. Hãy biết property thuộc về thành phần nào và ai tiêu thụ nó.

## 5. Chuyển đổi giá trị đơn giản thành collection

Một hệ thống thường cần nhiều giá trị cùng loại, ví dụ các vùng được phép phục vụ, thời gian chờ retry hoặc tên feature.

Class cấu hình:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        List<String> regions,
        Set<String> enabledChannels,
        List<Duration> retryDelays
) {
}
~~~

YAML:

~~~yaml
app:
  delivery:
    regions:
      - apac
      - emea
    enabled-channels:
      - email
      - sms
    retry-delays:
      - 100ms
      - 500ms
      - 2s
~~~

Binder có thể chuyển từng phần tử `retry-delays` thành `Duration`, rồi tạo `List<Duration>`. Với `Set<String>`, các phần tử trùng lặp không còn ý nghĩa như trong list.

### 5.1. List và Set có khác nhau không?

| Kiểu | Dùng khi | Lưu ý |
| --- | --- | --- |
| `List<T>` | Thứ tự phần tử có ý nghĩa | Cho phép phần tử trùng |
| `Set<T>` | Quan tâm tập giá trị duy nhất | Không dựa vào thứ tự như một hợp đồng nghiệp vụ |
| `Map<K,V>` | Cần tra cứu theo tên hoặc key | Key duy nhất; value có thể là kiểu phức tạp |
| `List<RecordType>` | Cần nhiều cấu hình có cấu trúc | Mỗi phần tử bind thành một object |

Nếu các retry delay được thực hiện lần lượt, `List<Duration>` phù hợp hơn `Set<Duration>` vì thứ tự có ý nghĩa. Nếu chỉ kiểm tra channel đã bật, một `Set<String>` có thể phản ánh yêu cầu rõ hơn.

### 5.2. Collection từ file .properties

Các phần tử list có thể được viết bằng index:

~~~properties
app.delivery.regions[0]=apac
app.delivery.regions[1]=emea

app.delivery.retry-delays[0]=100ms
app.delivery.retry-delays[1]=500ms
app.delivery.retry-delays[2]=2s
~~~

Với danh sách đơn giản, dạng phân tách bằng dấu phẩy cũng có thể được bind:

~~~properties
app.delivery.regions=apac,emea
~~~

Dạng index rõ ràng hơn khi phần tử có nhiều field hoặc khi cần xác định đúng vị trí. Với list có index, hãy dùng dãy index liên tục từ 0 để tránh phần tử trống và lỗi khó hiểu trong binding.

### 5.3. Collection có cần luôn khác null?

Nếu một property collection không được cung cấp, kết quả phụ thuộc kiểu binding và giá trị mặc định của class. Không nên giả định mọi `List` hoặc `Map` luôn là collection rỗng.

Với record immutable, có thể chuẩn hóa đầu vào trong compact constructor:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        List<String> regions,
        List<Duration> retryDelays
) {
    public DeliveryProperties {
        regions = regions == null ? List.of() : List.copyOf(regions);
        retryDelays = retryDelays == null
                ? List.of()
                : List.copyOf(retryDelays);
    }
}
~~~

Cách này giúp consumer không phải kiểm tra null liên tục. `List.copyOf` cũng tạo bản sao không thể sửa đổi, phù hợp với một object cấu hình bất biến.

Nếu tập giá trị bắt buộc phải có ít nhất một phần tử, nên dùng validation như `@NotEmpty` thay vì âm thầm chuyển thành danh sách trống.

## 6. Map: cấu hình có key và value

Khi mỗi loại dữ liệu có một giới hạn riêng, `Map<String, DataSize>` phù hợp:

~~~java
@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        Map<String, DataSize> quotas
) {
}
~~~

YAML:

~~~yaml
app:
  upload:
    quotas:
      avatars: 512KB
      images: 32MB
      videos: 1GB
~~~

Sau khi bind, service có thể truy vấn:

~~~java
DataSize imageQuota = properties.quotas().get("images");
long bytes = imageQuota.toBytes();
~~~

Giá trị trong map được chuyển đổi theo kiểu `DataSize`. Nếu một key chứa giá trị không hợp lệ như `many-megabytes`, cấu hình có thể thất bại khi bind.

### 6.1. Map<String, Duration> và kiểu khác

Spring Boot cũng có thể bind:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
        Map<String, Duration> delayByChannel,
        Map<String, Integer> maxAttemptsByChannel
) {
}
~~~

~~~yaml
app:
  retry:
    delay-by-channel:
      email: 2s
      sms: 500ms
    max-attempts-by-channel:
      email: 3
      sms: 5
~~~

Không cần tự lặp qua `Environment` để parse từng key. Binder sẽ chuyển mỗi value theo kiểu tương ứng.

### 6.2. Key chứa ký tự đặc biệt: bracket notation

Tên property có dấu chấm, dấu slash hoặc ký tự đặc biệt có thể bị binder diễn giải như đường dẫn thuộc tính lồng nhau. Nếu cần giữ nguyên key, dùng ký hiệu `[key]`.

Trong YAML, nên đặt bracket key trong dấu nháy:

~~~yaml
app:
  upload:
    quotas:
      "[/internal/images]": 4MB
      "[tenant.eu]": 8MB
~~~

Kết quả map có thể có các key nguyên văn `/internal/images` và `tenant.eu`.

Trong `application.properties`:

~~~properties
app.upload.quotas.[/internal/images]=4MB
app.upload.quotas.[tenant.eu]=8MB
~~~

Brackets đặc biệt quan trọng khi value là object lồng nhau hoặc key chứa ký tự bị loại theo quy tắc relaxed binding. Không tự giả định mọi ký tự trong key sẽ được giữ nguyên nếu bỏ brackets.

### 6.3. Dùng Enum làm key hoặc value

Nếu tập loại nghiệp vụ cố định, có thể dùng enum:

~~~java
public enum Channel {
    EMAIL,
    SMS,
    PUSH
}

@ConfigurationProperties(prefix = "app.channel")
public record ChannelProperties(
        Map<Channel, Duration> delays
) {
}
~~~

~~~yaml
app:
  channel:
    delays:
      EMAIL: 1s
      SMS: 500ms
      PUSH: 2s
~~~

Binder có thể chuyển các key sang enum tương ứng. Với kiểu enum, hãy thống nhất cách viết giá trị và bổ sung test binding để bắt lỗi cấu hình khi đổi tên hằng.

## 7. Cấu hình lồng nhau (nested properties)

Một client có thể có retry policy, authentication, endpoint list và giới hạn dung lượng. Nếu đưa tất cả thuộc tính lên một cấp với tên rất dài, cấu hình trở nên khó hiểu.

Ví dụ tự nhiên hơn:

~~~yaml
app:
  transport:
    connect-timeout: 3s
    max-in-memory: 2MB
    retry:
      max-attempts: 4
      backoff: 250ms
    endpoints:
      - name: primary
        url: https://primary.example.test
        timeout: 1s
      - name: backup
        url: https://backup.example.test
        timeout: PT2S
~~~

Trong Java, bạn có thể biểu diễn bằng nested record.

### 7.1. Nested record với constructor binding

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.transport")
public record TransportProperties(
        Duration connectTimeout,
        DataSize maxInMemory,
        Retry retry,
        List<Endpoint> endpoints
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}

    public record Endpoint(
            String name,
            String url,
            Duration timeout
    ) {}
}
~~~

Cấu trúc YAML khớp với các component:

| Property path | Vị trí trong object |
| --- | --- |
| `app.transport.connect-timeout` | `TransportProperties.connectTimeout()` |
| `app.transport.max-in-memory` | `TransportProperties.maxInMemory()` |
| `app.transport.retry.max-attempts` | `TransportProperties.retry().maxAttempts()` |
| `app.transport.retry.backoff` | `TransportProperties.retry().backoff()` |
| `app.transport.endpoints[0].name` | `TransportProperties.endpoints().get(0).name()` |
| `app.transport.endpoints[1].timeout` | `TransportProperties.endpoints().get(1).timeout()` |

Với Spring Boot 3.x, một record có constructor duy nhất được dùng cho constructor binding khi đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`; không cần gắn `@ConstructorBinding` trong trường hợp đơn giản này.

Cấu hình lồng nhau có thể sâu nhiều cấp. Tuy nhiên, nếu một class chứa quá nhiều nhánh, hãy xem xét tách nhóm property theo trách nhiệm của từng subsystem.

### 7.2. Danh sách object lồng nhau

`List<Endpoint>` cho phép khai báo nhiều endpoint, mỗi endpoint có name, URL và timeout.

~~~java
for (TransportProperties.Endpoint endpoint : properties.endpoints()) {
    System.out.println(
            endpoint.name() + " -> " + endpoint.url()
                    + ", timeout=" + endpoint.timeout()
    );
}
~~~

Với phần tử list là object, YAML list thường dễ đọc hơn một dãy property index dài. Nếu dùng .properties, đường dẫn tương ứng là:

~~~properties
app.transport.endpoints[0].name=primary
app.transport.endpoints[0].url=https://primary.example.test
app.transport.endpoints[0].timeout=1s

app.transport.endpoints[1].name=backup
app.transport.endpoints[1].url=https://backup.example.test
app.transport.endpoints[1].timeout=2s
~~~

Cần định nghĩa class/record `Endpoint` phù hợp và validation nếu URL hoặc tên endpoint là bắt buộc.

### 7.3. Map có value là object lồng nhau

Đôi khi cần tra cứu theo một key cố định thay vì vị trí list:

~~~java
@ConfigurationProperties(prefix = "app.routes")
public record RouteProperties(
        Map<String, Route> targets
) {
    public record Route(
            String baseUrl,
            Duration timeout,
            DataSize maxPayload
    ) {}
}
~~~

~~~yaml
app:
  routes:
    targets:
      orders:
        base-url: https://orders.example.test
        timeout: 3s
        max-payload: 1MB
      payments:
        base-url: https://payments.example.test
        timeout: 5s
        max-payload: 512KB
~~~

Ví dụ trên tạo `Map<String, Route>` với key `orders` và `payments`. Chọn `List<Route>` khi thứ tự có ý nghĩa; chọn `Map<String, Route>` khi tên route là định danh dùng để tra cứu.

## 8. Cấu hình immutable hoàn chỉnh với record và giá trị mặc định

Có thể kết hợp `Duration`, `DataSize`, collection, nested record và validation trong một cấu hình thực tế.

### 8.1. Class TransportProperties

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.transport")
@Validated
public record TransportProperties(
        @NotNull
        @DefaultValue("3s")
        Duration connectTimeout,

        @NotNull
        @DefaultValue("2MB")
        DataSize maxInMemory,

        List<String> regions,
        Map<String, DataSize> quotas,

        @Valid
        @DefaultValue
        Retry retry,

        List<@Valid Endpoint> endpoints
) {
    public TransportProperties {
        regions = regions == null ? List.of() : List.copyOf(regions);
        quotas = quotas == null ? Map.of() : Map.copyOf(quotas);
        endpoints = endpoints == null ? List.of() : List.copyOf(endpoints);
    }

    public record Retry(
            @Min(1)
            @DefaultValue("3")
            int maxAttempts,

            @NotNull
            @DefaultValue("500ms")
            Duration backoff
    ) {}

    public record Endpoint(
            @NotBlank
            String name,

            @NotBlank
            String url,

            @NotNull
            @DefaultValue("1s")
            Duration timeout
    ) {}
}
~~~

Giải thích thiết kế:

- `@ConfigurationProperties(prefix = "app.transport")` xác định nhóm property.
- `@Validated` yêu cầu validation khi cấu hình được bind.
- `@NotNull` giữ các giá trị bắt buộc không bị null sau khi áp dụng default.
- `@DefaultValue("3s")` đặt default cho constructor binding khi property không có.
- `@DefaultValue` không có tham số trên `Retry` yêu cầu binder tạo nested object từ các giá trị default của các component, kể cả khi không có key `retry` nào trong nguồn cấu hình.
- `@Min(1)` bảo đảm số lần thử lại lớn hơn hoặc bằng một.
- `@Valid` cho phép validation đi xuống nested object.
- `List<@Valid Endpoint>` giúp kiểm tra các phần tử endpoint.
- Compact constructor chuẩn hóa list và map thành collection không đổi, tránh null khi các collection không được cấu hình.

Để Bean Validation có provider trong dự án Boot 3.3, thường cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Đối với một project có sẵn validation starter thông qua dependency khác, không cần khai báo lặp chỉ vì ví dụ này. Nhưng không nên mặc định rằng annotation Jakarta Validation tự thực thi khi không có validation provider.

### 8.2. YAML cho cấu hình tổng hợp

~~~yaml
app:
  transport:
    connect-timeout: 5s
    max-in-memory: 4MB
    regions:
      - apac
      - emea
    quotas:
      images: 32MB
      documents: 8MB
    retry:
      max-attempts: 4
      backoff: 750ms
    endpoints:
      - name: primary
        url: https://primary.example.test
        timeout: 1s
      - name: backup
        url: https://backup.example.test
        timeout: PT2S
~~~

Sau binding:

~~~java
properties.connectTimeout();         // Duration.ofSeconds(5)
properties.maxInMemory();            // DataSize.ofMegabytes(4)
properties.regions();                // [apac, emea]
properties.quotas().get("images");   // DataSize.ofMegabytes(32)
properties.retry().maxAttempts();    // 4
properties.retry().backoff();        // Duration.ofMillis(750)
properties.endpoints().get(1).name();// "backup"
~~~

Các method trên được gọi trên một bean `TransportProperties` đã được Spring Boot đăng ký và bind thành công.

### 8.3. Nếu thiếu toàn bộ nhánh retry?

Vì parameter `retry` có `@DefaultValue`, binder có thể tạo một `Retry` với các giá trị default của hai component bên trong, thay vì để `retry` là null.

Nếu không khai báo `@DefaultValue` trên nested component này và không có bất kỳ property nào thuộc `retry`, nested object của constructor binding có thể là null. Đó là lý do rất nhiều ví dụ record-based configuration dùng `@DefaultValue` cho nested parameter.

Không dùng default để che giấu một cấu hình thực sự bắt buộc. Nếu thiếu một endpoint phải làm startup thất bại, hãy dùng validation và thông báo lỗi rõ ràng.

## 9. Đăng ký @ConfigurationProperties trong Spring Boot 3

Class có `@ConfigurationProperties` cần được Spring đăng ký để binder tạo object và inject được vào các service.

### 9.1. @ConfigurationPropertiesScan

Trong ứng dụng đặt class main ở package gốc bao phủ `com.example.config`:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` tìm class có `@ConfigurationProperties` trong package được quét. Cách này phù hợp khi ứng dụng có nhiều cấu hình cùng kiểu.

### 9.2. @EnableConfigurationProperties

Khi muốn đăng ký tường minh một hoặc nhiều class:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(TransportProperties.class)
public class TransportConfiguration {
}
~~~

Cách này thường gặp trong Java configuration hoặc auto-configuration của thư viện.

Với record immutable constructor-bound, hãy dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Đừng gắn `@Component` lên record rồi kỳ vọng constructor của nó được Spring tự bind như configuration properties; Spring constructor injection thông thường và constructor binding của properties có cơ chế đăng ký khác nhau.

### 9.3. @ConfigurationProperties trên phương thức @Bean

Khi muốn bind một object JavaBean từ thư viện ngoài, có thể đặt annotation lên method `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
public class VendorConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "vendor.pool")
    VendorPoolSettings vendorPoolSettings() {
        return new VendorPoolSettings();
    }
}
~~~

Ví dụ giả định `VendorPoolSettings` là class có getter/setter thích hợp. Cách này hữu ích nếu không thể sửa source của class thư viện để gắn annotation.

Khác biệt: ở đây object được tạo bởi factory method rồi các property được bind vào nó. Một record immutable không có setter không nên được dùng theo kiểu factory-method JavaBean binding này nếu không có cơ chế phù hợp.

## 10. JavaBean binding: một cách khác bên cạnh record

Record thuận tiện cho cấu hình bất biến. Nhưng class mutable với constructor không tham số, getter và setter vẫn được binder hỗ trợ.

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.http")
public class HttpClientProperties {
    private Duration timeout = Duration.ofSeconds(3);
    private DataSize maxBuffer = DataSize.ofMegabytes(2);
    private final Retry retry = new Retry();

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public DataSize getMaxBuffer() {
        return maxBuffer;
    }

    public void setMaxBuffer(DataSize maxBuffer) {
        this.maxBuffer = maxBuffer;
    }

    public Retry getRetry() {
        return retry;
    }

    public static class Retry {
        private int attempts = 3;

        public int getAttempts() {
            return attempts;
        }

        public void setAttempts(int attempts) {
            this.attempts = attempts;
        }
    }
}
~~~

Với JavaBean binding, binder gọi các setter tương ứng. Nested object `Retry` đã được khởi tạo sẵn và có getter, nên binder có thể cập nhật thuộc tính bên trong mà không cần thay toàn bộ instance nested qua setter riêng.

So sánh:

| Tiêu chí | Record / constructor binding | JavaBean / setter binding |
| --- | --- | --- |
| Mô hình | Tạo instance từ constructor parameters | Tạo object rồi cập nhật properties |
| Bất biến | Dễ tạo immutable state | Thường mutable |
| Giá trị mặc định | `@DefaultValue` hoặc logic constructor | Field initializer |
| Nested object | Nested record/class qua constructor binding | Nested bean qua getter/setter |
| Thích hợp | Cấu hình ứng dụng ổn định, type-safe | Thư viện cũ, class cần setter hoặc bind trên @Bean |

Hai phương pháp có thể cùng tồn tại trong một ứng dụng, miễn mỗi class được đăng ký và bind đúng cách.

## 11. Relaxed binding của tên thuộc tính

Spring Boot cho phép những quy ước đặt tên property khác nhau cùng bind vào một Java property.

Giả sử record component là `connectTimeout`, tên canonical trong config là:

~~~yaml
app:
  transport:
    connect-timeout: 5s
~~~

Trong `application.properties`:

~~~properties
app.transport.connect-timeout=5s
~~~

Trong một số nguồn cấu hình, tên camelCase cũng có thể được binder nhận diện theo quy tắc relaxed binding. Spring Boot khuyến nghị dùng dạng **lowercase kebab-case** cho property name trong file cấu hình.

### 11.1. Biến môi trường

Tên biến môi trường thường được chuyển đổi từ canonical property name bằng cách:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch nối `-`.
3. Chuyển sang chữ hoa.

Ví dụ:

| Property canonical | Environment variable |
| --- | --- |
| `app.transport.connect-timeout` | `APP_TRANSPORT_CONNECTTIMEOUT` |
| `app.transport.max-in-memory` | `APP_TRANSPORT_MAXINMEMORY` |
| `app.transport.retry.max-attempts` | `APP_TRANSPORT_RETRY_MAXATTEMPTS` |

Đây là điểm dễ nhầm: từ `connect-timeout`, dấu gạch nối bị **bỏ** trong quy tắc này. Dạng `APP_TRANSPORT_CONNECT_TIMEOUT` không phải phép chuyển canonical chính thức của cùng một property.

Với list, index có thể được biểu diễn bằng số kẹp giữa các dấu gạch dưới:

~~~text
APP_TRANSPORT_ENDPOINTS_0_NAME
APP_TRANSPORT_ENDPOINTS_0_TIMEOUT
APP_TRANSPORT_ENDPOINTS_1_NAME
~~~

Hãy kiểm tra tên biến môi trường hiệu lực trong cách deploy cụ thể; các platform có thể giới hạn hoặc chuẩn hóa key khác nhau.

### 11.2. Relaxed binding không áp dụng tùy tiện cho mọi dữ liệu

Relaxed binding chủ yếu giúp khớp **tên property**. Nó không có nghĩa một chuỗi sai định dạng thời lượng hay dung lượng sẽ luôn được sửa tự động.

Ví dụ:

~~~properties
app.transport.connect-timeout=fast
app.transport.max-in-memory=large
~~~

Binder không thể chuyển `fast` thành `Duration` và `large` thành `DataSize` theo contract thông thường. Lỗi conversion phải được sửa tại nguồn cấu hình hoặc xử lý bằng một converter được thiết kế rõ ràng.

## 12. Collection và Map khi nhiều nguồn cấu hình cùng ghi đè

Đây là khác biệt quan trọng trong Spring Boot: **list và map thường có cách kết hợp giữa property sources khác nhau**.

### 12.1. List thường bị thay thế toàn bộ

Giả sử `application.yml` có:

~~~yaml
app:
  delivery:
    regions:
      - apac
      - emea
~~~

Và một cấu hình có độ ưu tiên cao hơn đặt:

~~~yaml
app:
  delivery:
    regions:
      - americas
~~~

Khi bind `List<String>`, list từ nguồn ưu tiên cao hơn được dùng; không tự nối thành `[apac, emea, americas]`.

Nếu muốn các vùng được hợp nhất có quy tắc, hãy định nghĩa một bước tổng hợp trong code hoặc cấu trúc cấu hình khác. Đừng dựa vào việc binder tự gộp nhiều list từ nhiều nguồn.

### 12.2. Map có thể kết hợp các key

Giả sử nguồn cơ sở:

~~~yaml
app:
  upload:
    quotas:
      images: 16MB
      documents: 8MB
~~~

Nguồn ưu tiên cao hơn:

~~~yaml
app:
  upload:
    quotas:
      images: 32MB
~~~

Một map có thể giữ key `documents` từ nguồn cơ sở, trong khi key `images` nhận giá trị 32MB từ nguồn ưu tiên cao hơn.

Với map có value là object phức tạp, cách hợp nhất từng nhánh/property có thêm chi tiết; hãy kiểm thử kịch bản thực tế trước khi xem nó là hợp đồng triển khai.

### 12.3. Profile-specific configuration

Cùng quy tắc về source precedence xuất hiện khi sử dụng profile-specific files hoặc các YAML documents được kích hoạt theo profile.

Ví dụ cấu hình trong `application-prod.yml` có thể override list ở `application.yml`. Khi deploy, kiểm tra profile active và nguồn property có độ ưu tiên cao hơn để biết collection cuối cùng là gì.

Một lỗi thường gặp là nghĩ rằng thêm một phần tử ở file profile sẽ bổ sung vào danh sách ban đầu. Với list binding, điều đó thường thay thế list.

## 13. Validation cho Duration, DataSize, collection và nested object

Type conversion kiểm tra giá trị có thể được chuyển sang kiểu đích hay không. Nhưng chuyển đổi thành công chưa chắc cấu hình hợp lệ về nghiệp vụ.

Ví dụ:

- `-5s` có thể là một `Duration` hợp lệ về mặt kiểu nhưng không hợp lệ cho connect timeout.
- `0B` là một `DataSize` có thể biểu diễn được nhưng không phù hợp với một giới hạn buffer bắt buộc dương.
- `max-attempts=0` chuyển được thành `int` nhưng không hợp lệ nếu hệ thống cần ít nhất một lần thử.
- Một endpoint thiếu `name` hoặc `url` có thể gây lỗi khi runtime nếu không được kiểm tra sớm.

### 13.1. Jakarta Bean Validation

Kết hợp `@Validated` với annotation constraints:

~~~java
@ConfigurationProperties(prefix = "app.retry")
@Validated
public record RetryProperties(
        @Min(1) int maxAttempts,
        @NotNull Duration backoff,
        @NotNull DataSize maxPayload
) {
}
~~~

Nếu `max-attempts=0` hoặc giá trị bắt buộc bị thiếu, validation có thể khiến quá trình khởi động thất bại với thông báo liên quan tới property lỗi.

Khi nested type cần validation, thêm `@Valid` tại vị trí thích hợp:

~~~java
@ConfigurationProperties(prefix = "app.worker")
@Validated
public record WorkerProperties(
        @Valid
        @NotNull
        Retry retry
) {
    public record Retry(
            @Min(1) int attempts
    ) {}
}
~~~

`@Valid` cho phép kiểm tra constraint bên trong nested object. Nếu thiếu toàn bộ nhánh và không có default, nested object có thể null; vì vậy `@NotNull` trên nested component là một yêu cầu riêng.

### 13.2. Kiểm tra Duration không âm bằng domain validation

Nếu cần đảm bảo timeout dương, có thể áp dụng kiểm tra trong compact constructor:

~~~java
@ConfigurationProperties(prefix = "app.deadline")
public record DeadlineProperties(
        @DefaultValue("5s") Duration timeout
) {
    public DeadlineProperties {
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }
}
~~~

Đây là kiểm tra trong constructor của record, xảy ra khi binder tạo object. Nó phù hợp cho invariant đơn giản. Nếu dùng Bean Validation trong toàn bộ ứng dụng, có thể tạo custom constraint để có thông báo và metadata nhất quán hơn.

Tương tự với `DataSize`:

~~~java
if (maxBuffer == null || maxBuffer.toBytes() <= 0) {
    throw new IllegalArgumentException("maxBuffer must be positive");
}
~~~

Không nên cố gắng dùng `@Min(1)` trực tiếp lên `Duration` hoặc `DataSize` nếu validator đang dùng không hỗ trợ constraint đó cho kiểu đích. `@Min` chủ yếu dành cho kiểu số theo contract của Jakarta Validation.

### 13.3. Kiểm tra collection

Dùng `@NotEmpty` nếu danh sách hoặc map bắt buộc có phần tử:

~~~java
@ConfigurationProperties(prefix = "app.routes")
@Validated
public record RouteProperties(
        @NotEmpty
        List<@Valid Route> routes
) {
    public record Route(
            @NotBlank String name,
            @NotBlank String url
    ) {}
}
~~~

Khi cấu hình không có `routes` hoặc list rỗng, validation có thể từ chối cấu hình. Điều này rõ ràng hơn để ứng dụng khởi động rồi mới lỗi vì không có route.

## 14. Khi binding lỗi, Spring Boot báo gì?

Các lỗi thuộc nhiều nhóm khác nhau:

| Tình huống | Ví dụ | Nguyên nhân |
| --- | --- | --- |
| Sai định dạng Duration | `timeout=soon` | Không chuyển được chuỗi sang Duration |
| Sai định dạng DataSize | `max-buffer=very-large` | Không chuyển được chuỗi sang DataSize |
| Số nằm ngoài giới hạn kiểu | `max-attempts=abc` | Không chuyển được sang int |
| Thiếu property bắt buộc | `base-url` không có | Binding/validation không thỏa constraint |
| Collection sai cấu trúc | List object thiếu index hoặc field bắt buộc | Nguồn cấu hình không đúng cấu trúc binder kỳ vọng |
| Nested object thiếu | Không có nhánh `retry` | Nested component có thể null nếu không có default |
| Giá trị chuyển đổi được nhưng sai nghiệp vụ | `max-attempts=0` | Lỗi validation hoặc invariant |

Một lỗi binding thường kèm đường dẫn property, giá trị gây lỗi, kiểu đích và nguồn cấu hình nếu có thông tin origin. Hãy đọc phần nguyên nhân sâu hơn thay vì chỉ nhìn exception bao ngoài từ việc tạo bean.

### 14.1. Cách chẩn đoán từng bước

1. Xác định bean `@ConfigurationProperties` nào không tạo được.
2. Đọc property path đang lỗi, ví dụ `app.transport.connect-timeout`.
3. Kiểm tra kiểu Java đích: `Duration`, `DataSize`, `List<Endpoint>` hay kiểu khác.
4. Kiểm tra giá trị thực tế ở property source có độ ưu tiên cao nhất.
5. Xác nhận định dạng, đơn vị và cách đánh index/map key.
6. Kiểm tra giá trị default, nested binding và validation.
7. Nếu còn nghi ngờ, viết một test context nhỏ với đúng property values.

Với lỗi đơn vị, ưu tiên chỉnh cấu hình để có hậu tố tường minh. Tránh sửa class Java thành `String` chỉ để bỏ qua lỗi conversion; việc đó chuyển lỗi sang runtime và mất lợi ích của type-safe binding.

### 14.2. Cẩn thận với property không được bind

Nếu YAML có một key gõ sai mà không trùng với field trong class, key đó có thể bị bỏ qua tùy cấu hình binder. `@ConfigurationProperties` có các thuộc tính như `ignoreUnknownFields`, nhưng không nên bật chế độ strict một cách bừa bãi khi prefix chứa những key của thành phần khác.

Nếu yêu cầu cấu hình nghiêm ngặt, hãy kiểm thử các key quan trọng, dùng validation cho field bắt buộc và thiết kế prefix đủ riêng để tránh đụng cấu hình của module khác.

## 15. Kiểm thử type-safe binding bằng ApplicationContextRunner

Bạn không cần khởi động cả web server để kiểm tra một bean `@ConfigurationProperties`. Spring Boot test support cung cấp `ApplicationContextRunner` để tạo context nhỏ và truyền property values.

Giả sử dùng class `TransportProperties` tổng hợp ở mục 8.

### 15.1. Test binding của Duration, DataSize và nested record

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.unit.DataSize;

class TransportPropertiesBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(TransportProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsDurationsDataSizesCollectionsAndNestedProperties() {
        runner.withPropertyValues(
                "app.transport.connect-timeout=5s",
                "app.transport.max-in-memory=4MB",
                "app.transport.regions[0]=apac",
                "app.transport.regions[1]=emea",
                "app.transport.quotas.images=32MB",
                "app.transport.retry.max-attempts=4",
                "app.transport.retry.backoff=750ms",
                "app.transport.endpoints[0].name=primary",
                "app.transport.endpoints[0].url=https://primary.example.test",
                "app.transport.endpoints[0].timeout=1s"
        ).run(context -> {
            assertThat(context).hasSingleBean(TransportProperties.class);

            TransportProperties properties =
                    context.getBean(TransportProperties.class);

            assertThat(properties.connectTimeout())
                    .isEqualTo(Duration.ofSeconds(5));
            assertThat(properties.maxInMemory().toBytes())
                    .isEqualTo(DataSize.ofMegabytes(4).toBytes());
            assertThat(properties.regions())
                    .containsExactly("apac", "emea");
            assertThat(properties.quotas().get("images"))
                    .isEqualTo(DataSize.ofMegabytes(32));
            assertThat(properties.retry().maxAttempts()).isEqualTo(4);
            assertThat(properties.retry().backoff())
                    .isEqualTo(Duration.ofMillis(750));
            assertThat(properties.endpoints().get(0).name())
                    .isEqualTo("primary");
        });
    }
}
~~~

Ví dụ dùng các dependency test từ Spring Boot test starter và Bean Validation provider vì class ở mục 8 dùng `@Validated`. Không cần thêm một full `@SpringBootTest` chỉ để test binder.

### 15.2. Test giá trị mặc định

~~~java
@Test
void usesDefaultsWhenOptionalPropertiesAreMissing() {
    runner.run(context -> {
        TransportProperties properties =
                context.getBean(TransportProperties.class);

        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(3));
        assertThat(properties.maxInMemory())
                .isEqualTo(DataSize.ofMegabytes(2));
        assertThat(properties.retry().maxAttempts()).isEqualTo(3);
        assertThat(properties.retry().backoff())
                .isEqualTo(Duration.ofMillis(500));
        assertThat(properties.regions()).isEmpty();
        assertThat(properties.quotas()).isEmpty();
    });
}
~~~

Điểm đáng chú ý là nested `Retry` vẫn được tạo dù không có property `retry` nào, nhờ `@DefaultValue` ở vị trí nested parameter.

### 15.3. Test lỗi validation

~~~java
@Test
void rejectsInvalidRetryCount() {
    runner.withPropertyValues(
            "app.transport.retry.max-attempts=0"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

Test xác nhận cấu hình không thể khởi tạo khi vi phạm invariant. Với một ứng dụng thật, có thể kiểm tra thêm failure message và property path để bảo đảm lỗi dễ chẩn đoán, nhưng tránh gắn test vào toàn bộ chuỗi exception có thể thay đổi giữa phiên bản framework.

### 15.4. Test ghi đè list bằng property source

Một test nâng cao có thể tạo property source cơ sở với `regions[0]=apac`, `regions[1]=emea`, rồi bổ sung nguồn có độ ưu tiên cao hơn đặt `regions[0]=americas`. Kiểm tra list cuối cùng theo quy tắc Spring Boot trong môi trường thực tế.

Đừng chỉ đặt tất cả property trong cùng một `withPropertyValues` và xem đó là phép thử precedence giữa nhiều nguồn. Cần tổ chức các property source riêng nếu muốn kiểm tra đúng cơ chế override.

## 16. Khi nào cần custom converter?

Các kiểu như `Duration`, `DataSize`, enum, kiểu số thông dụng và nhiều collection thường được Spring Boot chuyển đổi sẵn.

Nếu domain có một kiểu cấu hình đặc biệt, ví dụ `ShardId` với cú pháp `shard-12`, bạn có thể định nghĩa converter riêng:

~~~java
public record ShardId(int value) {
    public ShardId {
        if (value < 0) {
            throw new IllegalArgumentException("Shard ID must be non-negative");
        }
    }
}
~~~

Converter:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class ShardIdConverter implements Converter<String, ShardId> {
    @Override
    public ShardId convert(String source) {
        if (!source.startsWith("shard-")) {
            throw new IllegalArgumentException("Expected shard-N");
        }

        int number = Integer.parseInt(source.substring("shard-".length()));
        return new ShardId(number);
    }
}
~~~

Sau đó một property:

~~~properties
app.storage.shard=shard-12
~~~

có thể được bind vào field `ShardId` nếu converter được đăng ký đúng cách.

`@ConfigurationPropertiesBinding` dùng để đánh dấu converter phục vụ configuration-properties binding. Những converter này có thể được tạo rất sớm trong application lifecycle; tránh cho chúng phụ thuộc vào nhiều service nghiệp vụ hoặc một bean graph phức tạp.

Không tạo custom converter cho `Duration` hoặc `DataSize` khi chỉ cần format chuẩn của Spring Boot. Hãy ưu tiên built-in converter để giảm code và giảm khác biệt giữa các module.

## 17. Các lỗi thiết kế thường gặp

### 17.1. Dùng số trần không có đơn vị

~~~yaml
app:
  transport:
    connect-timeout: 10
    max-in-memory: 10
~~~

Với conversion mặc định, `10` có thể được hiểu là **10 mili giây** cho `Duration` và **10 byte** cho `DataSize`. Đây có thể không phải ý định của người cấu hình.

Nên viết:

~~~yaml
app:
  transport:
    connect-timeout: 10s
    max-in-memory: 10MB
~~~

### 17.2. Dùng String thay vì kiểu chuyên dụng

Nếu class có:

~~~java
public record UploadProperties(String maxSize) {}
~~~

mọi consumer phải tự hiểu cú pháp, parse số và đơn vị, xử lý lỗi và chuyển đổi. Dùng `DataSize` giúp logic conversion tập trung trong binder.

### 17.3. Dùng Map<String, Object> cho toàn bộ cấu hình

Một map không kiểu rõ ràng có thể khiến service phải cast, kiểm tra key và phát hiện lỗi muộn. Hãy dùng record/class có các field rõ ràng khi schema cấu hình đã biết.

`Map<String, X>` vẫn hợp lý khi tập key thực sự động, nhưng value nên có kiểu cụ thể thay vì tràn lan `Object`.

### 17.4. Lầm tưởng list sẽ gộp từ mọi profile

Nhánh list thường được thay thế theo property-source precedence. Nếu một profile chỉ cung cấp phần tử đầu tiên, phần tử còn lại từ nguồn khác không tự được nối vào.

### 17.5. Quên validate nested object

`@Validated` trên class gốc không có nghĩa mọi constraint trong nested type luôn được kiểm tra theo cách bạn mong muốn. Cần `@Valid` cho nested bean/collection element và validation provider phù hợp.

### 17.6. Sử dụng cấu hình như mutable runtime state

`@ConfigurationProperties` biểu diễn cấu hình ứng dụng. Nếu cần cập nhật trạng thái theo từng request, tenant, job hoặc user, hãy dùng context/domain object hoặc storage phù hợp. Không dùng setter lên singleton properties bean như một cách lưu state nghiệp vụ tùy tiện.

### 17.7. Nhầm giá trị cấu hình với hiệu ứng runtime

Một field `DataSize maxPayload` không tự chặn payload lớn. Một field `Duration timeout` không tự cấu hình client HTTP. Bean tiêu thụ cần đọc và áp dụng chúng theo API của thư viện sử dụng.

### 17.8. Binding xong nhưng quên đăng ký properties bean

Class gắn `@ConfigurationProperties` chưa đủ nếu không được scan hoặc enable. Nếu injection thất bại, kiểm tra `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, package scan và source configuration.

## 18. Bài tập thực hành

### Bài tập 1 — Duration với các cách viết khác nhau

Tạo `@ConfigurationProperties` có ba field `Duration`: `connectTimeout`, `retryDelay` và `cacheTtl`. Bind lần lượt `5s`, `250ms` và `PT10M`. Viết test kiểm tra chúng bằng `Duration.ofSeconds`, `Duration.ofMillis` và `Duration.ofMinutes`.

### Bài tập 2 — @DurationUnit và @DataSizeUnit

Tạo hai property có kiểu `Duration` và `DataSize`, gắn `@DurationUnit(ChronoUnit.SECONDS)` và `@DataSizeUnit(DataUnit.MEGABYTES)`. Cấp giá trị số không suffix, rồi so sánh với các giá trị có suffix tường minh.

### Bài tập 3 — Collection có thứ tự

Tạo `List<Duration> retryDelays` được cấu hình bằng YAML gồm `100ms`, `500ms` và `2s`. Viết logic thử lại giả lập theo thứ tự và giải thích vì sao `Set<Duration>` không phù hợp.

### Bài tập 4 — Map dung lượng theo loại file

Bind `Map<String, DataSize> quotas` với các key `images`, `documents` và `videos`. Viết method nhận file type và trả về giới hạn byte tương ứng. Thêm case không tồn tại key để luyện xử lý fallback.

### Bài tập 5 — Nested record

Tạo `ClientProperties` chứa nested `Retry` và `List<Endpoint>`. Viết YAML có hai endpoint với timeout khác nhau. Kiểm tra hai phần tử được bind đúng thứ tự và nested retry có dữ liệu.

### Bài tập 6 — Validation fail fast

Thêm `@Validated`, `@Min(1)` và `@NotBlank` vào cấu hình. Cố ý cung cấp `max-attempts=0` và endpoint thiếu name. Xác nhận context test thất bại trước khi service xử lý request.

### Bài tập 7 — Precedence giữa list và map

Tạo hai property sources có độ ưu tiên khác nhau. Nguồn cơ sở chứa hai list elements và hai map entries; nguồn ưu tiên cao hơn chỉ khai báo một list và ghi đè một map key. Xác nhận sự khác biệt giữa list replacement và map merging.

### Bài tập 8 — Cấu hình từ environment variables

Bind `app.transport.connect-timeout`, `app.transport.retry.max-attempts` và `app.transport.endpoints[0].name` qua tên biến môi trường theo quy tắc relaxed binding. Ghi lại tên biến chính xác và kiểm tra giá trị sau khi application khởi động.

## 19. Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration và Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — Conversion of Durations, Periods and Data Sizes](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion)
- [Spring Framework — DataSize API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/util/unit/DataSize.html)

## 20. Ghi nhớ

Spring Boot có thể chuyển trực tiếp property values thành `Duration`, `DataSize`, collection và nested object qua `@ConfigurationProperties`. `Duration` giúp cấu hình timeout/delay bằng giá trị như `5s` hoặc `PT30S`, còn `DataSize` giúp cấu hình dung lượng bằng `512KB` hoặc `32MB`. Một số không có suffix mặc định là mili giây cho `Duration` và byte cho `DataSize`; `@DurationUnit` và `@DataSizeUnit` cho phép thay đơn vị mặc định khi cần.

Collection giúp biểu diễn nhiều giá trị cùng loại; `List` phù hợp khi thứ tự quan trọng, `Set` cho tập giá trị duy nhất và `Map` cho dữ liệu tra cứu theo key. List thường bị thay thế từ property source có độ ưu tiên cao hơn, còn map có thể gộp key giữa các nguồn. Nested record/class mô hình hóa các nhóm cấu hình như retry, endpoint và quota mà không phải parse thủ công.

Với Spring Boot 3.x, record đơn constructor hỗ trợ constructor binding, `@DefaultValue` cung cấp giá trị mặc định và `@Validated` cùng Jakarta Validation giúp phát hiện cấu hình không hợp lệ lúc khởi động. Hãy đăng ký bean bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, kiểm thử với `ApplicationContextRunner` và luôn nhớ: binding tạo ra dữ liệu có kiểu; thành phần sử dụng vẫn chịu trách nhiệm áp dụng timeout hoặc giới hạn dung lượng trong runtime.
