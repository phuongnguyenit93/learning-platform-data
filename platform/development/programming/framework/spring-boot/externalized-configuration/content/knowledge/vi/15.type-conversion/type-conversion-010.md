# Chẩn đoán sai định dạng, sai đơn vị và giá trị vượt miền hợp lệ trong Spring Boot 3.3

## 1. Vấn đề: có property nhưng không bind được, hoặc bind đúng mà chạy sai

Spring Boot cho phép khai báo cấu hình trong `application.properties`, `application.yaml`, biến môi trường, Java system properties và command-line arguments. Khi ánh xạ các giá trị đó vào bean `@ConfigurationProperties`, bộ `Binder` phải **đọc tên property**, **chọn nguồn có hiệu lực**, **chuyển đổi kiểu** và **kiểm tra ràng buộc** nếu ứng dụng đã bật validation.

Không phải lỗi cấu hình nào cũng giống nhau. Ba nhóm cần phân biệt:

1. **Sai định dạng hoặc sai kiểu đầu vào:** chẳng hạn `app.max-retries=three` cho `int`, `app.enabled=perhaps` cho `boolean` hoặc `app.timeout=soon` cho `Duration`.
2. **Sai đơn vị:** giá trị có thể bind thành công nhưng mang nghĩa sai, chẳng hạn `app.timeout=10` được hiểu là **10 mili giây** trong khi người vận hành muốn 10 giây; `app.buffer-size=10` được hiểu là **10 byte** trong khi muốn 10 MB.
3. **Vượt miền hợp lệ:** giá trị có thể không biểu diễn được trong kiểu Java (`int` quá lớn, `Duration`/`DataSize` vượt khả năng chuyển đổi), hoặc biểu diễn được nhưng **vi phạm chính sách ứng dụng** (`retry-count=-1`, `worker-count=0` khi cần ít nhất một worker, `timeout=-5s` khi không cho phép thời lượng âm).

**Điểm mấu chốt:** *parse được* chưa chắc *đúng đơn vị*; *bind thành công* chưa chắc *hợp lệ theo nghiệp vụ*. Do đó quá trình chẩn đoán phải trả lời riêng ba câu hỏi: **giá trị thực đến từ đâu, giá trị được giải nghĩa thành kiểu gì, và giá trị có nằm trong miền cho phép không?**

Ví dụ ngắn:

```properties
app.max-retries=0
app.timeout=10
app.buffer-size=10
app.enabled=false
```

Nếu Java model khai báo `int`, `Duration`, `DataSize` và `boolean` thì các giá trị trên có thể đều bind thành công:

- `maxRetries = 0`: hợp lệ về kiểu, còn việc cho phép tắt retry hay không phụ thuộc nghiệp vụ.
- `timeout = Duration.ofMillis(10)`: **không phải 10 giây** khi không có `@DurationUnit` khác.
- `bufferSize = DataSize.ofBytes(10)`: **không phải 10 MB** khi không có `@DataSizeUnit` khác.
- `enabled = false`: giá trị được đặt rõ ràng, không phải property vắng mặt.

Câu hỏi “vì sao ứng dụng chạy sai” đôi khi không dẫn tới exception, bởi sai đơn vị vẫn có thể là cấu hình hợp lệ về mặt cú pháp.

## 2. Dòng chảy chẩn đoán từ text đến runtime

Mô hình khái quát:

```text
application.yaml / .properties / CLI / -D / OS environment
                |
                v
     Spring Environment + PropertySource order
                |
                v
     Tên property canonical/relaxed binding
                |
                v
     Giá trị có hiệu lực (có thể là text)
                |
                v
     ConversionService / Binder:
       String -> int, boolean, enum, Duration,
                 Period, DataSize, URI, ...
                |
      +---------+-----------+
      |                     |
      v                     v
 Chuyển kiểu thất bại    Chuyển kiểu thành công
      |                     |
      v                     v
 Bind/conversion error     @Validated / Bean Validation
                            |
                 +----------+---------+
                 |                    |
                 v                    v
           Constraint error     Bean cấu hình hợp lệ
                                      |
                                      v
                           Logic nghiệp vụ sử dụng giá trị
```

Các lớp lỗi có thể được phản ánh qua `BindException`, `ConversionFailedException`, `IllegalArgumentException`, `NumberFormatException`, lỗi constraint validation hoặc ngoại lệ liên quan `ConfigurationPropertiesBindException` tại startup. **Tên exception chính xác thay đổi theo đường binding, target type và chuỗi nguyên nhân.** Không nên chỉ grep một exception name duy nhất rồi kết luận toàn bộ.

### Một mẫu triệu chứng thường thấy

Khi bean cấu hình không bind được, Spring Boot có thể hiển thị failure analysis dạng:

```text
APPLICATION FAILED TO START

Description:
Failed to bind properties under 'app.max-retries' to int:

    Property: app.max-retries
    Value: "not-a-number"
    Origin: class path resource [application.properties] - ...
    Reason: failed to convert java.lang.String to int

Action:
Update your application's configuration
```

Đây là **minh họa cấu trúc thông báo**, không phải một log byte-for-byte cho mọi phiên bản. Điều có giá trị khi đọc log là các trường:

| Trường | Cần lấy thông tin gì? |
| --- | --- |
| `Property` | Tên thuộc tính cuối cùng đang bind |
| `Value` | Giá trị đầu vào gây lỗi; có thể bị ẩn/sanitize |
| `Origin` | Nguồn file/dòng/cột khi nguồn cung cấp origin |
| `Reason` | Lỗi conversion hoặc constraint cụ thể |
| `Target type` | Java type và vị trí binding thực sự |
| `Caused by` | Nguyên nhân gốc nếu wrapper exception chứa nhiều tầng |

Không phải mọi nguồn (đặc biệt env var hoặc custom PropertySource) đều có vị trí dòng/cột; thiếu `Origin` **không chứng minh property chưa tồn tại**.

## 3. Ví dụ cấu hình đầy đủ để tham chiếu

Giả sử dịch vụ có cấu hình:

```properties
# src/main/resources/application.properties
app.max-retries=3
app.worker-count=4
app.request-timeout=5s
app.idle-timeout=30s
app.cache-size=16MB
app.retention=30d
app.enabled=true
app.region=ap-southeast-1
```

JavaBean dùng `@ConfigurationProperties`:

```java
package com.example.demo.config;

import java.time.Duration;
import java.time.Period;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.boot.convert.DurationUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;
import org.springframework.validation.annotation.Validated;

import java.time.temporal.ChronoUnit;

@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    @Min(0)
    @Max(10)
    private int maxRetries = 3;

    @Min(1)
    @Max(64)
    private int workerCount = 4;

    @NotNull
    private Duration requestTimeout = Duration.ofSeconds(5);

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration idleTimeout = Duration.ofSeconds(30);

    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize cacheSize = DataSize.ofMegabytes(16);

    private Period retention = Period.ofDays(30);

    private boolean enabled = true;

    @NotBlank
    private String region = "local";

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int value) { maxRetries = value; }

    public int getWorkerCount() { return workerCount; }
    public void setWorkerCount(int value) { workerCount = value; }

    public Duration getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(Duration value) {
        requestTimeout = value;
    }

    public Duration getIdleTimeout() { return idleTimeout; }
    public void setIdleTimeout(Duration value) { idleTimeout = value; }

    public DataSize getCacheSize() { return cacheSize; }
    public void setCacheSize(DataSize value) { cacheSize = value; }

    public Period getRetention() { return retention; }
    public void setRetention(Period value) { retention = value; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean value) { enabled = value; }

    public String getRegion() { return region; }
    public void setRegion(String value) { region = value; }
}
```

Đăng ký class:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Phụ thuộc validation nếu project chưa có provider:

```xml
<!-- pom.xml: nếu dùng Spring Boot dependency management -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Ví dụ này tách ba phần:

- **Java type** quyết định dạng dữ liệu có thể chuyển đổi.
- **Unit annotation** quyết định cách hiểu giá trị số **không kèm hậu tố**.
- **Validation constraints** quyết định miền hợp lệ riêng của ứng dụng, ví dụ retry từ 0 đến 10.

`@NotNull` trên `Duration` giúp phát hiện giá trị null sau binding, nhưng **không tự giới hạn** thời lượng là dương hoặc nhỏ hơn một ngưỡng. Phải thêm constraint/custom validation khi đó là yêu cầu nghiệp vụ.

## 4. Sai định dạng số nguyên: cú pháp, miền của kiểu, miền của nghiệp vụ

Một property Java kiểu `int` nhận giá trị số nguyên trong phạm vi mà kiểu đó biểu diễn.

Ví dụ hợp lệ về chuyển kiểu:

```properties
app.max-retries=0
app.worker-count=8
```

Ví dụ sai định dạng:

```properties
app.max-retries=three
```

Binder không thể chuyển chuỗi `three` thành `int` bằng bộ converter thông thường, vì vậy quá trình bind có thể thất bại với nguyên nhân conversion/number format.

Ví dụ vượt miền kiểu `int`:

```properties
app.max-retries=9999999999999999999999
```

Giá trị đó không biểu diễn được bằng `int` 32-bit; đây không chỉ là lỗi policy `@Max(10)`. Quá trình chuyển kiểu đã có thể thất bại **trước khi** Bean Validation kiểm tra `@Max`.

Ví dụ nằm trong miền `int` nhưng vượt ràng buộc nghiệp vụ:

```properties
app.max-retries=100
```

Số 100 có thể parse thành `int`, nhưng vi phạm `@Max(10)` trong model ví dụ. Đây là **validation error**, khác conversion error.

Ví dụ hợp lệ tùy nghiệp vụ:

```properties
app.max-retries=0
```

Với `@Min(0)`, 0 hợp lệ và có thể mang nghĩa “không retry”. Đừng dùng `@Positive` nếu 0 là quyết định có ý nghĩa.

### Bảng phân loại cho số nguyên

| Đầu vào `app.max-retries` | Chuyển thành `int`? | Trong miền [0,10]? | Nhận định |
| --- | --- | --- | --- |
| `0` | Có | Có | Giá trị explicit hợp lệ |
| `3` | Có | Có | Hợp lệ |
| `10` | Có | Có | Giá trị biên trên |
| `-1` | Có | Không | Sai constraint `@Min(0)` |
| `11` | Có | Không | Sai constraint `@Max(10)` |
| `three` | Không | Chưa xét | Sai định dạng |
| `99999999999999999999` | Không | Chưa xét | Ngoài khả năng biểu diễn của `int` |
| `3.5` | Không theo chuyển đổi `String -> Integer` thông thường | Chưa xét | Dùng kiểu thập phân nếu cần |
| Chuỗi rỗng | Có thể cho null/lỗi tùy đường bind và kiểu đích | Không coi là zero | Không tương đương giá trị 0 |

**Phân biệt hai loại “out of range”:** vượt khả năng của kiểu đích sẽ gây lỗi trước hoặc trong conversion; còn vượt miền cho phép của nghiệp vụ chỉ được phát hiện nếu ứng dụng khai báo validation hoặc kiểm tra tương đương.

## 5. Boolean: false là hợp lệ, từ không nhận diện có thể lỗi

Một property:

```java
private boolean enabled = true;
```

có thể nhận:

```properties
app.enabled=false
```

Với `boolean`, `false` có thể ghi đè `true` khởi tạo ban đầu. **Đây không phải lỗi.**

Nhưng:

```properties
app.enabled=perhaps
```

không phải giá trị boolean được hỗ trợ thông thường, nên có thể gây conversion error. Việc converter có chấp nhận các alias boolean như `yes/no` hoặc `on/off` còn phụ thuộc nguồn/converter; muốn cấu hình nhất quán, hãy dùng rõ `true` và `false`.

Bốn trường hợp nên tách:

- **Key thiếu:** JavaBean có thể giữ giá trị khởi tạo; với primitive không khởi tạo, Java mặc định false.
- **`enabled=false`:** một lựa chọn explicit và hợp lệ.
- **`enabled=`:** một String rỗng ở nguồn, không tự động có nghĩa false.
- **`enabled=perhaps`:** không phải giá trị boolean rõ ràng; có thể gây lỗi conversion.

Khi cần phân biệt “không khai báo” và “tắt”, dùng `Boolean` wrapper cùng chính sách null/validation; đừng chỉ nhìn một primitive boolean sau binding.

## 6. Duration: dạng hợp lệ, đơn vị và sai lệch khó phát hiện

`java.time.Duration` là kiểu dành cho **khoảng thời gian có độ dài**, ví dụ 750 mili giây, 5 giây hoặc 30 phút. Spring Boot 3.3 hỗ trợ:

1. Số nguyên dài không có hậu tố: mặc định **mili giây**, trừ khi có `@DurationUnit`.
2. Chuẩn ISO-8601 của `Duration`, ví dụ `PT5S`, `PT1M`.
3. Dạng dễ đọc gồm số và đơn vị, ví dụ `750ms`, `5s`, `2m`.

### 6.1. Các hậu tố Duration được hỗ trợ

| Hậu tố | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `ns` | Nanosecond | `500ns` |
| `us` | Microsecond | `100us` |
| `ms` | Millisecond | `750ms` |
| `s` | Giây | `5s` |
| `m` | Phút | `2m` |
| `h` | Giờ | `1h` |
| `d` | Ngày | `7d` |

Các cách viết:

```properties
app.request-timeout=5s
app.request-timeout=PT5S
app.request-timeout=5000ms
```

là **ba phương án thay thế** thể hiện cùng khoảng thời gian 5 giây cho một property `Duration`. Không đặt ba dòng cùng key trong một file như ví dụ cấu hình thật.

### 6.2. Sai đơn vị nhưng vẫn parse được

```properties
app.request-timeout=5
```

Với property `Duration` không có `@DurationUnit`, giá trị 5 là **5ms**, không phải 5s. Lỗi này có thể không tạo exception vì đầu vào **hợp lệ về cú pháp**.

Thay bằng:

```properties
app.request-timeout=5s
```

hoặc:

```properties
app.request-timeout=5000ms
```

Nếu muốn số trần được hiểu là giây, khai báo:

```java
@DurationUnit(ChronoUnit.SECONDS)
private Duration requestTimeout;
```

Khi đó `app.request-timeout=5` được hiểu là 5 giây **trong target có annotation này**. Tuy nhiên, ngay cả khi dùng `@DurationUnit`, viết rõ `5s` trong file vẫn dễ hiểu hơn cho người vận hành.

### 6.3. Các lỗi thường gặp ở Duration

| Input | Tình trạng | Hướng xử lý |
| --- | --- | --- |
| `5s` | Đúng dạng thời lượng | Phù hợp nếu ứng dụng cần 5 giây |
| `5000ms` | Đúng dạng, tương đương 5 giây | Dùng khi cần nêu mili giây rõ |
| `PT5S` | Dạng ISO-8601 | Dùng khi nguồn theo chuẩn ISO |
| `5` | Đúng dạng nhưng mặc định 5ms | Thêm hậu tố hoặc `@DurationUnit` |
| `5sec` | Không thuộc danh sách hậu tố ngắn được tài liệu Boot 3.3 liệt kê | Đổi sang `5s` hoặc ISO-8601 |
| `5minutes` | Không phải dạng compact được tài liệu liệt kê | Đổi sang `5m` hoặc `PT5M` |
| `abc` | Sai định dạng | Sửa thành giá trị có thể parse |
| `-5s` | Có thể biểu diễn Duration âm | Cần validation nếu timeout phải không âm/dương |
| Giá trị rất lớn | Có nguy cơ vượt miền Java type hoặc lỗi khi downstream đổi sang ms/int | Xác định giới hạn ở từng tầng |

**Không nhầm `m` của Duration với `M` hoặc `MB` của DataSize.** `2m` là 2 phút, không phải 2 megabyte.

### 6.4. 0ms và âm có ý nghĩa nghiệp vụ đặc biệt

Một `Duration.ZERO` có thể có nghĩa “không chờ”, “vô hiệu timeout” hoặc “xử lý ngay”, tùy API sử dụng. Một duration âm cũng có thể được biểu diễn bởi Java, nhưng một API client/server cụ thể có thể từ chối nó. **Binder không có nhiệm vụ tự biết 0 hoặc âm có hợp lệ cho ứng dụng của bạn hay không.**

Khi cần ràng buộc `requestTimeout > 0` và tối đa 30 giây, hãy xác thực rõ sau binding hoặc dùng một constraint Bean Validation tùy chỉnh. `@Min(1)` không phải lựa chọn tự động cho mọi đối tượng `Duration`, vì `@Min` vốn dành cho các kiểu số được hỗ trợ.

## 7. Period: đừng nhầm “khoảng ngày/tháng/năm” với Duration

`java.time.Period` phù hợp để biểu diễn số ngày, tháng, năm theo lịch. Spring Boot 3.3 hỗ trợ:

- Số nguyên: mặc định là **ngày**, trừ khi có `@PeriodUnit`.
- Chuỗi ISO-8601 như `P3D`, `P1M`, `P1Y3D`.
- Dạng dễ đọc như `3d`, `2w`, `1m`, `1y3d`.

### Các đơn vị Period

| Hậu tố | Ý nghĩa |
| --- | --- |
| `y` | Năm |
| `m` | Tháng |
| `w` | Tuần (quy đổi thành 7 ngày) |
| `d` | Ngày |

Chú ý cùng hậu tố `m` nhưng **khác kiểu target**:

```text
Duration + "1m" -> 1 phút
Period   + "1m" -> 1 tháng
```

Ví dụ:

```properties
app.retention=30d
```

Nếu target là `Period`, giá trị tương ứng khoảng 30 ngày theo lịch. Khi target là `Duration`, `30d` là thời lượng theo giây cố định cho 30 ngày 24 giờ; hai kiểu khác biệt khi tính toán với lịch hoặc múi giờ.

### Sai đơn vị ở Period

```properties
app.retention=30
```

Với `Period` không có `@PeriodUnit` khác, 30 được hiểu là **30 ngày**. Nếu người vận hành muốn 30 tháng, giá trị phải nêu rõ, ví dụ `30m`, hoặc thiết kế model/annotation tương ứng.

### Không dùng Period như một timeout kỹ thuật

Timeout request, socket timeout, retry backoff thường là `Duration`. Thời hạn lưu trữ theo tháng/năm của chính sách nghiệp vụ có thể dùng `Period`. Việc chọn sai target type có thể gây lỗi chuyển đổi hoặc dẫn đến cách tính thời gian sai dù cùng là một con số.

## 8. DataSize: đơn vị mặc định là byte, không phải KB/MB

Spring Boot 3.3 hỗ trợ `org.springframework.util.unit.DataSize` để diễn đạt kích thước dữ liệu. Dạng được hỗ trợ:

- Số nguyên dài **không hậu tố**: mặc định là **byte**, trừ khi có `@DataSizeUnit`.
- Số + hậu tố kích thước: `256B`, `16KB`, `10MB`, `2GB`...

### 8.1. Các hậu tố được hỗ trợ

| Hậu tố | Ý nghĩa |
| --- | --- |
| `B` | Byte |
| `KB` | Kilobyte |
| `MB` | Megabyte |
| `GB` | Gigabyte |
| `TB` | Terabyte |

Ví dụ:

```properties
app.cache-size=16MB
app.upload-limit=512KB
app.buffer-size=256B
```

Nếu khai báo:

```java
private DataSize cacheSize;
```

thì `app.cache-size=16MB` được parse thành DataSize tương ứng.

### 8.2. Sai đơn vị âm thầm

```properties
app.cache-size=16
```

Nếu không có `@DataSizeUnit`, 16 là **16 byte**, không phải 16 MB. Viết:

```properties
app.cache-size=16MB
```

Hoặc trong Java:

```java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize cacheSize;
```

Với annotation này, số trần 16 có thể được hiểu là 16 MB. Tuy nhiên, để tránh phụ thuộc vào annotation khi người vận hành chỉ đọc file, **khuyến nghị luôn viết hậu tố đơn vị cho DataSize**.

### 8.3. Dùng sai hậu tố

Các chuỗi như `16MiB`, `16Megabytes` hoặc `16M` không nằm trong danh sách hậu tố DataSize `B/KB/MB/GB/TB` mà tài liệu Spring Boot 3.3 mô tả. Để cấu hình rõ ràng và tương thích, dùng `16MB` hoặc đơn vị được liệt kê.

Không dùng `16m` với ý định 16 MB; `m` trong Duration/Period lại mang nghĩa khác. Đơn vị của `DataSize` phải đi cùng kiểu đích và cú pháp hợp lệ.

### 8.4. Vượt miền biểu diễn hoặc không phù hợp môi trường thực tế

`DataSize` có thể biểu diễn kích thước lớn ở cấp API, nhưng:

- Một chuỗi cực lớn có thể không chuyển thành giá trị số/`DataSize` do vượt giới hạn dữ liệu nội bộ.
- Một kích thước convert thành công có thể vượt khả năng RAM, dung lượng đĩa hay quota của container.
- Khi convert `DataSize.toBytes()` (long) sang `int` hoặc truyền vào một API chỉ nhận số nguyên 32-bit, có nguy cơ vượt miền **ở bước downstream**.
- Giá trị âm hoặc 0 có thể được biểu diễn nhưng không hợp lệ với một buffer, upload limit hoặc cache size cụ thể.

Do đó cần **giới hạn nghiệp vụ** bằng validation phù hợp và kiểm tra an toàn trước khi thu hẹp kiểu:

```java
DataSize configured = properties.getCacheSize();
long bytes = configured.toBytes();

if (bytes <= 0 || bytes > 100L * 1024 * 1024) {
    throw new IllegalArgumentException(
            "app.cache-size must be > 0 and <= 100MB");
}

int safeBytes = Math.toIntExact(bytes);
```

`Math.toIntExact` sẽ báo lỗi nếu `long` không nằm trong miền `int`, thay vì âm thầm cắt dữ liệu qua cast `(int)`. Thêm kiểm tra tài nguyên thực tế khi cần; validator không thể thay thế capacity planning.

## 9. Bảng đối chiếu đơn vị: cùng một con số có thể khác hoàn toàn

Giả sử cấu hình chỉ có text `"10"`:

| Target Java | Chú giải | Ý nghĩa khi không có annotation đổi đơn vị |
| --- | --- | --- |
| `int` | Giá trị số nguyên | 10 |
| `long` | Giá trị số nguyên dài | 10 |
| `Duration` | Thời lượng | 10 **ms** |
| `Period` | Chu kỳ lịch | 10 **ngày** |
| `DataSize` | Kích thước dữ liệu | 10 **byte** |
| `String` | Text | Chuỗi `"10"` |

Nếu muốn ý định rõ ràng trong file:

```properties
app.retry-count=10
app.request-timeout=10s
app.retention=10d
app.buffer-size=10MB
```

**Đừng đoán đơn vị chỉ bằng tên property** như `timeout` hoặc `size`. Hãy xác định target type và annotation `@DurationUnit`/`@PeriodUnit`/`@DataSizeUnit` thực tế trong Java code.

## 10. Sai miền hợp lệ: conversion khác validation

Một giá trị như:

```properties
app.worker-count=0
```

được chuyển thành `int 0` hoàn toàn hợp lệ. Nhưng trong ví dụ `AppProperties`, `workerCount` có `@Min(1)`, do đó đây là **vi phạm policy**, không phải lỗi parser.

Tương tự:

```properties
app.worker-count=128
```

parse được, nhưng vượt `@Max(64)`.

Các nhóm constraint thường dùng:

| Kiểu/nhu cầu | Constraint phù hợp | Lưu ý |
| --- | --- | --- |
| Số nguyên phải ≥ 0 | `@Min(0)` | Cho phép 0 |
| Số nguyên phải ≥ 1 | `@Min(1)` hoặc `@Positive` | Loại 0 và số âm |
| Số nguyên không vượt ngưỡng | `@Max(n)` | Không kiểm tra syntax nếu conversion đã lỗi |
| Decimal trong khoảng | `@DecimalMin`, `@DecimalMax` | Cẩn trọng biên inclusive/exclusive |
| String bắt buộc có nội dung | `@NotBlank` | Khác `@NotNull` |
| String đúng mẫu | `@Pattern` | Dùng Regex gắn với hợp đồng dữ liệu |
| Nested object | `@Valid` | Cho phép validate property con |
| Enum đã biết | Enum target Java | Conversion kiểm tra tên giá trị hợp lệ |
| `Duration`/`DataSize` trong miền đặc biệt | Custom constraint/validator | Không mặc định dùng `@Min` trên mọi object |

### 10.1. Ví dụ decimal

```java
import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;

@DecimalMin("0.0")
@DecimalMax("1.0")
private BigDecimal sampleRate = new BigDecimal("0.5");
```

Các giá trị:

```properties
app.sample-rate=0.0
app.sample-rate=1.0
```

là những phương án hợp lệ tại hai biên theo constraint ví dụ. `app.sample-rate=1.25` có thể parse thành `BigDecimal` nhưng **không vượt qua validation**. `app.sample-rate=abc` có thể thất bại ngay khi chuyển kiểu.

Không dùng `double` cho mọi giá trị decimal cần chính xác; `BigDecimal` có thể phù hợp khi yêu cầu biểu diễn thập phân chính xác.

### 10.2. Missing, empty và zero là ba chuyện khác nhau

Giả sử JavaBean có:

```java
@Min(1)
private int workerCount = 4;
```

- **Thiếu `app.worker-count`:** có thể giữ giá trị mặc định 4.
- **`app.worker-count=0`:** có value 0, chuyển kiểu thành công nhưng không đạt `@Min(1)`.
- **`app.worker-count=`:** chuỗi rỗng, cần xem conversion sang primitive/nullable type; đừng tự xem là 0 hoặc missing.
- **`app.worker-count=abc`:** sai định dạng số.

Nếu cấu hình bắt buộc được khai báo thay vì cho phép field initializer, cần dùng wrapper/constraint hoặc kiểm tra sự tồn tại trong `Environment` theo cách thích hợp; primitive có giá trị mặc định của Java không chứng minh property đã được cung cấp.

## 11. `@Validated` và Jakarta Bean Validation trong @ConfigurationProperties

Spring Boot 3.3 hỗ trợ validate `@ConfigurationProperties` nếu bean cấu hình có `@Validated` và có Bean Validation provider tương thích trên classpath.

Ví dụ class:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public class WorkerProperties {

    @Min(1)
    @Max(64)
    private int threads = 4;

    @NotBlank
    private String region = "local";

    @Valid
    private final Pool pool = new Pool();

    public int getThreads() { return threads; }
    public void setThreads(int threads) { this.threads = threads; }

    public String getRegion() { return region; }
    public void setRegion(String region) { this.region = region; }

    public Pool getPool() { return pool; }

    public static class Pool {

        @Min(1)
        @Max(100)
        private int maxConnections = 20;

        public int getMaxConnections() { return maxConnections; }
        public void setMaxConnections(int value) {
            maxConnections = value;
        }
    }
}
```

Cấu hình:

```properties
worker.threads=0
worker.pool.max-connections=200
```

Cả hai giá trị là số nguyên đúng định dạng. Nếu validation chạy, chúng có thể bị từ chối vì nằm ngoài các constraint đã khai báo. `@Valid` giúp validate object con `pool` ngay cả khi nó đã được khởi tạo sẵn.

**Đừng nhầm:** nếu không có Bean Validation provider hoặc cấu hình validation thích hợp, không thể giả định mọi annotation constraint sẽ được thực thi. Dự án Spring Boot thường dùng `spring-boot-starter-validation`.

### `@NotBlank` và `@NotNull`

`@NotNull` không bắt chuỗi rỗng. Ví dụ:

```properties
worker.region=
```

`worker.region` có thể bind thành chuỗi rỗng. Nếu yêu cầu tên vùng có ký tự không phải khoảng trắng, `@NotBlank` phù hợp hơn `@NotNull`.

### Không giấu lỗi bằng `ignoreInvalidFields`

`@ConfigurationProperties` có tham số `ignoreInvalidFields` nhưng việc bật nó để “ứng dụng khởi động bằng mọi giá” có thể làm giữ giá trị cũ/mặc định và che mất cấu hình vận hành sai. Thông thường **không nên bật** chỉ để bỏ lỗi conversion; sửa giá trị nguồn hoặc cung cấp cơ chế fallback có chủ đích và được kiểm thử.

`ignoreUnknownFields` là một vấn đề khác: nó liên quan các key không ánh xạ vào model, không phải chính sách tổng quát để hợp thức hóa mọi value sai định dạng.

## 12. Một example validator riêng cho Duration/DataSize

Bean Validation không tự hiểu rằng mọi `Duration` đều phải dương hoặc mọi `DataSize` phải nằm trong một dung lượng cho phép của dịch vụ. Có thể viết kiểm tra rõ ở tầng validation hoặc sau binding.

Ví dụ một Bean Validation constraint ở mức getter:

```java
import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;

public class TimeoutProperties {

    private Duration requestTimeout = Duration.ofSeconds(5);

    public Duration getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(Duration value) {
        requestTimeout = value;
    }

    @AssertTrue(message =
            "request-timeout must be between 1ms and 30s")
    public boolean isRequestTimeoutInRange() {
        return requestTimeout != null
                && requestTimeout.compareTo(Duration.ofMillis(1)) >= 0
                && requestTimeout.compareTo(Duration.ofSeconds(30)) <= 0;
    }
}
```

Đây là ví dụ một quy tắc tự định nghĩa thông qua `@AssertTrue`; chỉ hoạt động khi đối tượng chứa constraint **được validate**. Nếu `TimeoutProperties` là nested class bên trong `@ConfigurationProperties`, cần `@Valid` ở parent hoặc cơ chế validate tương đương.

Với DataSize cũng có thể kiểm tra `toBytes()`, giới hạn và tính hợp lệ nghiệp vụ trong custom validator. Nếu cần thông báo lỗi gắn trực tiếp vào field `cacheSize`, một **custom constraint annotation + ConstraintValidator** sẽ rõ hơn `@AssertTrue` phụ trợ.

**Tách biệt:** custom validator là code ứng dụng; không phải bộ chuyển đổi đơn vị của Binder. Validator nên báo lỗi chính sách, còn converter đảm nhiệm việc parse dữ liệu.

## 13. Xác định giá trị thực sự có hiệu lực trước khi sửa file

Lỗi có thể không nằm trong file bạn đang chỉnh. Spring Boot tổng hợp cấu hình từ nhiều PropertySource; một command-line argument hay environment variable có thể ghi đè file trong JAR.

Giả sử file:

```properties
app.request-timeout=5s
```

Nhưng môi trường triển khai có:

```bash
APP_REQUESTTIMEOUT=5
```

Binder nhận tên biến môi trường tương ứng và có thể lấy giá trị có ưu tiên cao hơn từ OS environment. Kết quả Duration có thể là **5ms**, dù file trong JAR đã ghi `5s` đúng ý định.

Hoặc:

```bash
java -jar myapp.jar --app.worker-count=0
```

Nếu `@Min(1)` yêu cầu workerCount ≥ 1, lỗi có thể do **CLI** chứ không phải `application.yaml`.

Một số nguồn và mức ưu tiên phổ biến trong Boot 3.3 (không phải toàn bộ danh sách):

```text
Default properties
       < Config Data (application.*)
       < OS environment
       < Java system properties (-D)
       < Command-line arguments (--...)
```

Có những nguồn riêng như `SPRING_APPLICATION_JSON`, test properties, Devtools, Servlet config… với mức khác. Hãy đọc **thứ tự thực tế của ứng dụng** thay vì dùng bảng tóm tắt này như danh sách tuyệt đối.

### Relaxed binding khi đọc environment variables

Công thức tên biến môi trường từ canonical property:

1. Thay dấu chấm `.` bằng `_`.
2. Bỏ dấu gạch nối `-`.
3. Chuyển chữ hoa.

Ví dụ:

```text
app.max-retries     -> APP_MAXRETRIES
app.worker-count    -> APP_WORKERCOUNT
app.request-timeout -> APP_REQUESTTIMEOUT
app.cache-size      -> APP_CACHESIZE
```

Không tự đặt `APP_REQUEST_TIMEOUT` rồi mặc định chắc chắn nó tương đương `app.request-timeout`. Dấu gạch dưới có ý nghĩa phân cấp; dấu gạch nối trong canonical property **được bỏ**, không thay bằng một underscore nữa.

## 14. Đọc lỗi có `Origin` và lần tới đúng tệp cấu hình

Một nguồn Config Data đọc từ file thường có origin giúp chỉ ra nơi property được khai báo. Khi startup báo lỗi dạng:

```text
Property: app.cache-size
Value: "ten-gigabytes"
Origin: class path resource [application.yaml] - 12:15
Reason: Failed to convert property value ...
```

hãy lần theo:

1. **Key:** `app.cache-size` là property cần sửa.
2. **Value:** `ten-gigabytes` có đúng cú pháp mà `DataSize` hỗ trợ không? Không.
3. **Origin:** file và vị trí nguồn, nếu báo được. Trong YAML, kiểm tra thụt lề/tài liệu đang active.
4. **Target type:** `DataSize`, chứ không phải `String`.
5. **Đơn vị mặc định:** byte nếu thiếu hậu tố và không có annotation.
6. **Nguồn ưu tiên cao hơn:** origin có thể chỉ sang Config Data hoặc một nguồn khác.
7. **Nếu parser thành công:** tiếp tục kiểm tra validation và policy.

**Lưu ý bảo mật:** Spring Boot có thể che giá trị nhạy cảm trong một số công cụ chẩn đoán. Không cần bật hiển thị secret để phân tích lỗi cấu hình thông thường.

### Profile và Config Data có thể đổi giá trị hiệu lực

```yaml
# application.yaml
app:
  request-timeout: 5s
```

```yaml
# application-prod.yaml
app:
  request-timeout: 5
```

Khi `prod` active, file theo profile có thể ghi đè giá trị bằng 5ms. Nếu chỉ đọc file chung, khó hiểu vì sao timeout quá ngắn.

Kiểm tra active profiles, `spring.config.import`, `spring.config.additional-location`, profile-specific file và override từ CLI/environment khi tìm nguồn gốc.

## 15. Trình tự chẩn đoán 10 bước

Khi một giá trị cấu hình sai hoặc làm ứng dụng không khởi động, thực hiện:

1. **Xác định property canonical** (ví dụ `app.request-timeout`), prefix `@ConfigurationProperties` và Java property đích.
2. **Đọc target type**: `int`, `Integer`, `Boolean`, `Duration`, `Period`, `DataSize`, enum, `URI`, List/Map hay custom type.
3. **Xác định nguồn hiệu lực**: Config Data, profile, OS env, JVM `-D`, CLI, import hoặc test PropertySource.
4. **Giữ nguyên raw value để phân tích**, nhưng không log bí mật; phân biệt missing, empty String, `0`, `false` và một chuỗi có nội dung.
5. **Kiểm tra syntax** của loại dữ liệu: số nguyên, boolean, ISO duration, hậu tố đơn vị, cú pháp YAML.
6. **Kiểm tra đơn vị**: bare `10` được hiểu thế nào khi target là Duration/Period/DataSize và có hay không `@*Unit`?
7. **Kiểm tra miền type**: giá trị có vượt khả năng biểu diễn của `int`/`long` hoặc thư viện xử lý tiếp theo không?
8. **Kiểm tra Bean Validation**: `@Min`/`@Max`/`@NotBlank`/`@Valid`/custom constraint có được áp dụng không?
9. **Xác định tác động nghiệp vụ**: 0, âm, cực lớn hoặc rất nhỏ có hợp lệ với service/resource thực tế không?
10. **Sửa đúng nguồn có ưu tiên**, rồi khởi chạy/test lại ở môi trường phù hợp. Không che lỗi conversion bằng `ignoreInvalidFields` như một biện pháp mặc định.

Sơ đồ quyết định:

```text
Có giá trị hiệu lực không?
  ├─ Không -> dùng default có chủ đích / bắt buộc khai báo -> validation?
  └─ Có
      |
      v
  Có đúng cú pháp target type không?
      ├─ Không -> sửa text/format/quote/enum/number
      └─ Có
          |
          v
      Đơn vị có đúng ý định không?
          ├─ Không -> thêm hậu tố / sửa @*Unit
          └─ Có
              |
              v
          Có nằm trong miền của kiểu đích không?
              ├─ Không -> giảm giá trị / chọn kiểu phù hợp
              └─ Có
                  |
                  v
              Có qua validation nghiệp vụ không?
                  ├─ Không -> sửa cấu hình hoặc constraint
                  └─ Có -> kiểm tra code downstream và source precedence
```

Không dừng chẩn đoán ngay sau khi thấy Binder không ném exception: **sai đơn vị** thường đi qua parse thành công.

## 16. Bảng triệu chứng → nguyên nhân → hướng xử lý

| Triệu chứng | Nhóm vấn đề | Cách xử lý chính |
| --- | --- | --- |
| Không bind được `worker-count=abc` | Sai cú pháp | Cấp một số nguyên đúng kiểu |
| Không bind được `worker-count=9999999999999` vào `int` | Vượt miền type | Dùng số nhỏ hơn hoặc kiểu đích phù hợp |
| `worker-count=0` và constraint `@Min(1)` báo lỗi | Vượt miền nghiệp vụ | Chọn ≥ 1 nếu policy yêu cầu |
| Request timeout 5ms dù file tưởng là 5 giây | Sai đơn vị | `5s` hoặc `5000ms` |
| Buffer được set 16B dù muốn 16MB | Sai đơn vị | `16MB` |
| `cache-size=16MiB` không parse như mong muốn | Hậu tố không thuộc dạng được mô tả | Dùng `16MB` |
| `retention=1m` ra 1 tháng, không phải 1 phút | Sai kiểu/đơn vị | `Period` dùng tháng; `Duration` dùng phút |
| `enabled=maybe` lỗi | Sai định dạng boolean | Dùng `true` hoặc `false` |
| `enabled=false` không lỗi nhưng tính năng tắt | Giá trị explicit hợp lệ | Kiểm tra ý định chứ không ép thành true |
| `region=` vẫn qua `@NotNull` | Constraint chưa đúng | Dùng `@NotBlank` |
| Timeout âm qua Binder nhưng thư viện từ chối | Policy downstream | Validate Duration trước khi dùng |
| DataSize quá lớn làm downstream ép kiểu sai | Tràn miền downstream | Kiểm tra giới hạn trước `toIntExact` |
| File `application.properties` đúng nhưng runtime vẫn sai | Nguồn khác override | Xem profile, OS env, CLI và origin |
| Một key typo không báo exception | Unknown fields | Dùng metadata/test và chính sách strict khi cần |
| Bật `ignoreInvalidFields` rồi ứng dụng chạy với default | Lỗi bị che | Tắt bỏ qua lỗi, sửa giá trị nguồn |
| Nested bean có constraint nhưng không báo | Chưa cascade validation | `@Valid` và Bean Validation provider phù hợp |
| Config sai chỉ trên production | Profile/env khác local | Tái hiện bằng profile và override thực tế |

## 17. Kiểm tra bằng Environment và bean đã bind

Đôi khi property đang bind thành giá trị **hợp lệ về kiểu nhưng sai đơn vị**, nên bean vẫn được tạo. Có thể kiểm tra cả raw và typed value đối với các key **không nhạy cảm**:

```java
package com.example.demo.config;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ConfigDiagnostics {

    @Bean
    ApplicationRunner printEffectiveTimeout(
            Environment env, AppProperties props) {
        return args -> {
            String key = "app.request-timeout";

            String raw = env.getProperty(key);
            System.out.println("Raw effective value: "
                    + (raw == null ? "<missing>" : "[" + raw + "]"));

            System.out.println("Typed timeout: "
                    + props.getRequestTimeout());

            System.out.println("Timeout in milliseconds: "
                    + props.getRequestTimeout().toMillis());
        };
    }
}
```

Ví dụ nếu `app.request-timeout=5`:

```text
Raw effective value: [5]
Typed timeout: PT0.005S
Timeout in milliseconds: 5
```

Nếu `app.request-timeout=5s`:

```text
Raw effective value: [5s]
Typed timeout: PT5S
Timeout in milliseconds: 5000
```

Đoạn này giả định `AppProperties` đã được bind thành công, không có `@DurationUnit` đổi đơn vị cho `requestTimeout` và không có override khác. Nó **không chạy** trong trường hợp startup thất bại trước lúc tạo `ApplicationRunner`, nên khi bind lỗi phải đọc failure analysis/log ở giai đoạn startup.

### Nhìn xem property có mặt hay không

```java
boolean present = env.containsProperty("app.request-timeout");
String raw = env.getProperty("app.request-timeout");
```

`containsProperty` thường cho biết Environment giải quyết được một giá trị không null. Nó không trả lời “key này có xuất hiện trong file nào” ở mức source raw, đặc biệt khi có nhiều PropertySource hoặc một source biểu diễn null.

**Không in toàn bộ Environment** chỉ để tìm một lỗi; trong đó có thể có credential và token.

## 18. Actuator, logging và nguồn dữ liệu

Nếu sử dụng Spring Boot Actuator, một số endpoint hữu ích cho chẩn đoán là:

- `/actuator/env`: xem property hiệu lực hoặc các PropertySource, tùy cấu hình exposure/sanitization.
- `/actuator/configprops`: quan sát `@ConfigurationProperties` beans và các giá trị đã bind, tùy cơ chế bảo vệ và masking.

**Không mở công khai hai endpoint này.** Chỉ bật khi có biện pháp authentication/authorization, exposure phù hợp và không làm lộ secret.

Để tăng mức log khi tìm lỗi Config Data/Binding, có thể thử:

```properties
logging.level.org.springframework.boot.context.config=DEBUG
logging.level.org.springframework.boot.context.properties=DEBUG
```

Tùy phiên bản, loại nguồn và thời điểm logging được khởi tạo, không phải mọi bước conversion đều xuất hiện ở DEBUG. Có thể tăng TRACE cho package cụ thể trong môi trường kiểm soát, nhưng phải lưu ý log có thể chứa cấu hình nhạy cảm và tăng dung lượng đáng kể.

`--debug` khi chạy Spring Boot có ích để xem báo cáo điều kiện auto-configuration ở những trường hợp thích hợp; nó **không tự sửa lỗi bind**, và không nên xem báo cáo condition là thay thế cho origin/Reason của lỗi converter.

## 19. Kiểm thử lỗi conversion và validation bằng ApplicationContextRunner

Thay vì chỉ test trường hợp hợp lệ, nên tạo test cho đầu vào sai và ngưỡng biên. `ApplicationContextRunner` từ `spring-boot-test` giúp dựng một context nhỏ với property values được xác định rõ.

Class cấu hình test:

```java
package com.example.demo;

import com.example.demo.config.AppProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AppProperties.class)
class BindingTestConfig {
}
```

Test:

```java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AppPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingTestConfig.class);

    @Test
    void validUnitsAreBound() {
        runner
            .withPropertyValues(
                "app.request-timeout=5s",
                "app.cache-size=16MB",
                "app.worker-count=4")
            .run(context -> {
                assertThat(context).hasNotFailed();
                var props = context.getBean(
                        com.example.demo.config.AppProperties.class);
                assertThat(props.getRequestTimeout().toMillis())
                        .isEqualTo(5000);
                assertThat(props.getCacheSize().toBytes())
                        .isGreaterThan(0);
                assertThat(props.getWorkerCount())
                        .isEqualTo(4);
            });
    }

    @Test
    void badIntegerFormatFailsStartup() {
        runner
            .withPropertyValues("app.worker-count=not-an-int")
            .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void businessRangeIsValidated() {
        runner
            .withPropertyValues("app.worker-count=0")
            .run(context -> assertThat(context).hasFailed());
    }
}
```

Ví dụ này yêu cầu Spring Boot Test, AssertJ/JUnit và một Bean Validation provider nếu test validation phải thực thi. `hasFailed()` xác nhận context không khởi tạo thành công, không phải khẳng định chính xác exception class ở mọi bản patch.

Test nên bổ sung cho `0`, `-1`, `@Max`, bare numeric Duration/DataSize và profile overrides. Một test chỉ kiểm tra “đã tạo bean” không phát hiện giá trị 5ms thay vì 5s; hãy assert **typed result và đơn vị**.

### Tạo kiểm thử phân biệt lỗi parse và lỗi range

Một ma trận test có ý nghĩa:

| Property | Input | Kỳ vọng |
| --- | --- | --- |
| `app.worker-count` | `4` | Context chạy; bind 4 |
| `app.worker-count` | `0` | Conversion thành công nhưng constraint `@Min(1)` không đạt |
| `app.worker-count` | `abc` | Conversion thất bại |
| `app.worker-count` | Số > 2^31 − 1 | Lỗi do miền kiểu `int` |
| `app.request-timeout` | `5s` | 5 giây |
| `app.request-timeout` | `5` | 5 mili giây nếu không có `@DurationUnit` |
| `app.cache-size` | `16MB` | 16 MB |
| `app.cache-size` | `16` | 16 byte nếu không có `@DataSizeUnit` |
| `app.enabled` | `false` | False hợp lệ |
| `app.region` | Chuỗi rỗng | `@NotBlank` không đạt |

## 20. Chẩn đoán custom Converter

Có trường hợp ứng dụng bind một type đặc thù, ví dụ `ServerAddress`, `Percentage` hoặc enum tự định nghĩa, và cần một `Converter<String,T>`.

Spring Boot 3.3 hỗ trợ đăng ký converter chuyên dùng cho configuration properties bằng `@ConfigurationPropertiesBinding`.

Ví dụ type:

```java
package com.example.demo.config;

public record Percentage(int value) {
    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "percentage must be between 0 and 100");
        }
    }
}
```

Converter:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class StringToPercentageConverter
        implements Converter<String, Percentage> {

    @Override
    public Percentage convert(String source) {
        String trimmed = source.trim();
        if (!trimmed.matches("\\d+")) {
            throw new IllegalArgumentException(
                    "percentage must be an integer");
        }
        return new Percentage(Integer.parseInt(trimmed));
    }
}
```

Model:

```java
@ConfigurationProperties(prefix = "app")
public class PercentageProperties {
    private Percentage sampleRate;

    public Percentage getSampleRate() { return sampleRate; }
    public void setSampleRate(Percentage sampleRate) {
        this.sampleRate = sampleRate;
    }
}
```

Config:

```properties
app.sample-rate=80
```

Nếu giá trị là `120`, parser số có thể thành công nhưng constructor `Percentage` cố ý từ chối vì vượt miền. Đó là **domain validation đặt trong value object**, khác với lỗi không parse được số.

**Cảnh báo lifecycle:** các bean dùng cho conversion của configuration properties có thể được yêu cầu **rất sớm** khi ứng dụng khởi động; converter nên có dependency đơn giản và tránh kéo các bean khởi tạo muộn. Khi cần custom `ConversionService`, chú ý tên bean `conversionService` và thứ tự khởi tạo.

Không viết converter tùy chỉnh chỉ để đọc `Duration`/`DataSize` thông thường; Spring Boot đã cung cấp các converter và annotation về đơn vị tương ứng.

## 21. Java type nhỏ hơn giá trị: int, long, byte và narrowing

Một value có thể hợp lệ đối với `long` nhưng không hợp lệ cho `int`. Ví dụ:

```properties
app.max-events=3000000000
```

Nếu Java target là `int`, số này vượt giới hạn 2.147.483.647. Thay target thành `long` khi miền nghiệp vụ thực sự cần hơn 32-bit:

```java
private long maxEvents;
```

**Nhưng đừng tăng kiểu để che lỗi policy.** Nếu hệ thống chỉ nên cho phép tối đa 100.000 sự kiện, hãy dùng constraint `@Max(100000)` hoặc custom validation dù Java type có thể chứa giá trị lớn hơn.

Với số âm/byte:

```text
byte  → -128 đến 127
short → -32768 đến 32767
int   → -2147483648 đến 2147483647
long  → miền 64-bit có dấu
```

Trong Java, chuyển kiểu thu hẹp bằng cast không kiểm tra tự động:

```java
long raw = 3_000_000_000L;
int unsafe = (int) raw;           // có thể mất giá trị
int checked = Math.toIntExact(raw); // ném ArithmeticException
```

Đây là lỗi có thể xuất hiện **sau khi Binder bind thành công long**, khi code khác thu hẹp nó. Chẩn đoán phải theo đến nơi giá trị được sử dụng, không chỉ kiểm tra bean đã tạo thành công.

## 22. Chuỗi rỗng, placeholder default và @DefaultValue

Một property **vắng mặt** khác với property có chuỗi rỗng.

```properties
# app.name không có
app.region=
```

Ở dạng String qua Environment:

```text
app.name   -> null (khi không có nguồn nào cung cấp)
app.region -> ""
```

Với placeholder:

```java
@Value("${app.name:Guest}")
private String name;
```

Khi `app.name` vắng mặt, default `Guest` được dùng. Khi `app.name=`, property có mặt với chuỗi rỗng nên placeholder default thường **không thay thế** bằng `Guest`.

`@DefaultValue` trên constructor-bound `@ConfigurationProperties` cũng có nguyên tắc: default được dùng khi Binder **không tìm thấy property**; property có mặt với chuỗi rỗng không tự kích hoạt `@DefaultValue`.

Nếu target là primitive `int` hoặc `boolean`, một chuỗi rỗng có thể tạo vấn đề conversion/binding khác với key missing. Không tự ép empty thành `0`/`false` trừ khi ứng dụng xây dựng chính sách đó rõ ràng.

### Vì sao cần chẩn đoán empty trước khi parse?

Người vận hành có thể đặt:

```bash
APP_WORKERCOUNT=""
```

và cho rằng bỏ trống sẽ làm ứng dụng lấy default 4. Nhưng đó là một **biến môi trường có mặt** với value rỗng, khác với việc không khai báo biến. Nếu lỗi chỉ xảy ra trong container, hãy kiểm tra file Compose/Kubernetes/CI đang tạo biến rỗng ngoài ý muốn.

Đối với String bắt buộc, `@NotBlank` giúp phân biệt “value có nội dung” với rỗng/trắng; đối với typed numbers, nên dùng đúng giá trị hoặc bỏ hẳn key để default hợp lệ được áp dụng.

## 23. YAML có thể làm đổi cách parse giá trị

YAML là ngôn ngữ dữ liệu có cú pháp riêng. Những lưu ý:

- Thụt lề sai có thể khiến property path bị thay đổi, ví dụ `app.retry-count` vô tình nằm dưới một object khác.
- Những chuỗi có ký tự đặc biệt đôi khi nên đặt trong dấu nháy để bảo toàn chính xác.
- `true` và `false` có thể là boolean scalar, trong khi `"true"` và `"false"` là text; Binder có thể chuyển các dạng phù hợp sang target type.
- `null`/một key không có giá trị không đồng nhất với String rỗng `""`.
- Giá trị có hậu tố đơn vị như `5s`, `16MB` nên được viết rõ ràng; có thể quote để tăng tính minh bạch.
- Một file cấu hình có nhiều document YAML phân cách bằng `---` có thể chứa các giá trị khác nhau theo `spring.config.activate.on-profile`; cần biết document nào được kích hoạt.

Ví dụ YAML rõ ràng:

```yaml
app:
  worker-count: 4
  max-retries: 0
  request-timeout: "5s"
  cache-size: "16MB"
  enabled: false
  region: "ap-southeast-1"
```

Chẩn đoán syntax YAML diễn ra trước hoặc trong lúc dữ liệu được nạp vào Config Data; không nhầm lỗi YAML parser với lỗi Binder không chuyển `String -> Duration`.

## 24. Cấu hình có chủ đích: mặc định, đơn vị và giới hạn

Một hợp đồng cấu hình tốt nên có ba lớp:

**Lớp 1 — Tên và kiểu:**

```text
app.worker-count     Integer
app.request-timeout  Duration
app.cache-size       DataSize
app.region           String
```

**Lớp 2 — Đơn vị và giá trị mặc định:**

```text
app.worker-count     mặc định 4
app.request-timeout  mặc định 5s
app.cache-size       mặc định 16MB
app.region           mặc định local
```

**Lớp 3 — Miền hợp lệ:**

```text
app.worker-count     1..64
app.request-timeout  > 0ms và <= 30s
app.cache-size       > 0B và <= 100MB
app.region           chuỗi không rỗng, theo danh sách vùng được phép
```

Thể hiện trong code:

- Field initializer/`@DefaultValue`: default có chủ đích.
- `@DurationUnit`/`@DataSizeUnit`: cách hiểu giá trị số trần.
- Bean Validation hoặc custom validator: giới hạn.
- README/metadata cấu hình: tài liệu cho người vận hành.
- Tests: đảm bảo cả ví dụ hợp lệ, sai cú pháp, sai đơn vị và giá trị ở biên được xử lý như mong đợi.

Nếu muốn tránh hoàn toàn sự mơ hồ của bare numeric, hướng dẫn người vận hành **luôn viết hậu tố** cho `Duration`/`DataSize` trong file, ngay cả khi đã có unit annotation.

## 25. Phân biệt lỗi lúc startup và lỗi lúc vận hành

| Giai đoạn | Ví dụ | Nguyên nhân |
| --- | --- | --- |
| Config Data parse | YAML sai indentation hoặc syntax | File không đọc được thành dữ liệu cấu hình |
| Binding conversion | `app.worker-count=foo` | Không chuyển String sang int |
| Binding conversion | Số quá lớn cho `int` | Ngoài miền biểu diễn |
| Validation | `worker-count=0` khi `@Min(1)` | Dữ liệu đúng kiểu nhưng sai policy |
| Runtime sử dụng giá trị | `Duration=5ms` trong khi muốn 5s | Bind đúng nhưng sai đơn vị/ngữ nghĩa |
| Runtime sử dụng giá trị | `DataSize=16MB` nhưng quota memory nhỏ hơn | Giá trị hợp lệ trong model nhưng không phù hợp tài nguyên |
| Runtime downstream conversion | `long` bị cast thành `int` | Mất dữ liệu sau binding |

Nơi phát hiện quyết định cách sửa:

- Lỗi parse: sửa cú pháp file.
- Lỗi conversion: sửa value theo kiểu target hoặc converter hợp lệ.
- Lỗi validation: sửa value theo miền được hỗ trợ hoặc xem lại rule nghiệp vụ.
- Lỗi ngữ nghĩa/đơn vị: sửa hậu tố, annotation hoặc chọn đúng Java type.
- Lỗi downstream: thêm kiểm tra miền, unit conversion hoặc capacity constraints nơi tiêu thụ.

Không tự động coi mọi `IllegalArgumentException` ở startup là lỗi cấu hình; cần đọc stack trace và property/origin để tìm gốc.

## 26. Checklist triển khai và vận hành

- [ ] Tên property trong tài liệu dùng **lowercase kebab-case**.
- [ ] Prefix `@ConfigurationProperties` và Java target type khớp nhau.
- [ ] Có default rõ ràng cho optional property.
- [ ] Các property `Duration` trong file nêu rõ `ms/s/m/h/d` khi cần.
- [ ] Các property `DataSize` nêu rõ `B/KB/MB/GB/TB`.
- [ ] Các property `Period` dùng `d/w/m/y` khi là thời gian theo lịch, không nhầm với Duration.
- [ ] Khi dùng bare numeric, kiểm tra `@DurationUnit`, `@DataSizeUnit` và `@PeriodUnit`.
- [ ] Số nguyên lớn được khai báo bằng type đủ rộng, không cast hẹp thiếu kiểm tra.
- [ ] Cấu hình quan trọng có `@Min`/`@Max`/`@NotBlank`/`@Valid` hoặc custom validation.
- [ ] Đã có Jakarta Bean Validation provider nếu muốn constraint hoạt động.
- [ ] Đã xác định 0 và số âm có hợp lệ cho từng property hay không.
- [ ] Không xem `false` hoặc `0` là property missing.
- [ ] Không xem String rỗng là fallback tự động.
- [ ] Không bật `ignoreInvalidFields` chỉ để che lỗi vận hành.
- [ ] Truy nguyên `Property`, `Value`, `Origin` và `Reason` trong failure analysis.
- [ ] Kiểm tra profile, Config Data import, OS env, `-D` và CLI để biết source có ưu tiên.
- [ ] Khi có thể, assert giá trị **sau chuyển đổi** và đơn vị bằng tests, không chỉ assert context chạy.
- [ ] Actuator `env/configprops` và debug logging được bảo vệ, không lộ secret.
- [ ] Các giá trị upper/lower bounds được test ở cả hai phía.
- [ ] Cập nhật README cấu hình khi thay kiểu Java, mặc định hoặc đơn vị.

## 27. Bảng ghi nhớ nhanh

| Nếu thấy... | Hãy hỏi... | Thao tác điển hình |
| --- | --- | --- |
| `Failed to bind... to int` | Value có phải số nguyên trong miền `int`? | Sửa text hoặc target type |
| `ConversionFailedException` | Source và target type là gì? | Xem root cause |
| `BindValidationException` | Constraint nào bị vi phạm? | Kiểm tra `@Min`/`@Max`/... |
| `timeout=10` | Đơn vị mặc định là gì? | Viết `10s` nếu muốn giây |
| `cache-size=10` | 10 byte hay 10 MB? | Viết `10MB` khi muốn MB |
| `retention=1m` | Target là Period hay Duration? | Chọn đúng kiểu/đơn vị |
| `0` | 0 có phải lựa chọn hợp lệ? | Không tự loại bỏ |
| `false` | Đây có phải chủ ý tắt tính năng? | Giữ value explicit |
| `value=""` | Khóa có mặt hay không? | Không mặc định dùng fallback |
| Giá trị đúng trong file nhưng runtime sai | Có nguồn cao hơn override? | Xem PropertySource/Origin |
| Lỗi chỉ ở môi trường prod | Active profiles/env khác local? | Tái hiện source và profile |
| Startup thành công nhưng hành vi sai | Bind đúng nhưng sai ý định hoặc downstream? | Kiểm tra typed value, đơn vị và policy |

## 28. Tài liệu tham khảo

- **Spring Boot 3.3 Reference — Externalized Configuration**, các mục *Properties Conversion*, *Converting Durations*, *Converting Periods*, *Converting Data Sizes*, *@ConfigurationProperties Validation*, *PropertySource Order* và *Binding*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 API — `@ConfigurationProperties`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- **Spring Boot 3.3 API — `Binder`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- **Spring Boot 3.3 API — `@DurationUnit`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/DurationUnit.html
- **Spring Boot 3.3 API — `@DataSizeUnit`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/DataSizeUnit.html
- **Spring Boot 3.3 API — `@PeriodUnit`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/PeriodUnit.html
- **Spring Framework — Environment Abstraction**: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- **Jakarta Bean Validation — Constraints** (`@Min`, `@Max`, `@NotBlank`, `@Valid`, `@AssertTrue`): https://jakarta.ee/specifications/bean-validation/

**Kết luận:** chẩn đoán cấu hình Spring Boot 3.3 phải phân biệt rõ **sai định dạng**, **sai đơn vị** và **vượt miền hợp lệ**. Dùng `Environment`/origin để tìm raw value có hiệu lực, xem **Java target type + unit annotation** để hiểu giá trị sau conversion, và dùng **Bean Validation hoặc domain checks** để từ chối những giá trị đúng cú pháp nhưng không an toàn cho ứng dụng. Bare numeric cho `Duration`/`DataSize` đặc biệt dễ gây lỗi âm thầm; hãy đặt hậu tố đơn vị rõ ràng trong cấu hình.
