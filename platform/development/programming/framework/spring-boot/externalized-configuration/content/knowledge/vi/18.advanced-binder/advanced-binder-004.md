# Xử lý BindResult và trường hợp không có dữ liệu trong Spring Boot Binder

## 1. Vì sao cần một kết quả “có dữ liệu / không có dữ liệu”?

Khi ứng dụng Spring Boot đọc cấu hình, không phải nhóm thuộc tính nào cũng bắt buộc xuất hiện. Ví dụ:

- Một chức năng xuất báo cáo có thể chỉ được cấu hình ở môi trường production.
- Một kết nối tới dịch vụ bên ngoài có thể là tùy chọn.
- Danh sách máy chủ phụ trợ có thể không được khai báo tại máy cá nhân.
- Một nhóm cấu hình có thể được cung cấp qua `application.yaml`, biến môi trường hoặc dòng lệnh; trong một số lần chạy, không nguồn nào chứa nhóm đó.

Giả sử ứng dụng có:

~~~yaml
app:
  primary:
    endpoint: https://primary.example.test
~~~

Nhưng **không có** bất kỳ khóa nào bắt đầu bằng `app.secondary`.

Nếu mã Java cố bind `app.secondary` sang một record, ta cần phân biệt:

1. Không có dữ liệu phù hợp để bind: tính năng phụ có thể được tắt, dùng mặc định, hoặc báo thiếu cấu hình theo chính sách.
2. Có dữ liệu và bind thành công: sử dụng giá trị đã chuyển kiểu.
3. Có dữ liệu nhưng sai kiểu hoặc không thể bind: đây là lỗi cấu hình, **không phải** trường hợp “không khai báo”.

Spring Boot cung cấp `Binder` và `BindResult<T>` để thực hiện việc phân biệt ấy.

Ví dụ ý tưởng:

~~~java
Binder binder = Binder.get(environment);

BindResult<SecondaryProperties> result =
        binder.bind("app.secondary", SecondaryProperties.class);

if (result.isBound()) {
    SecondaryProperties properties = result.get();
    // Dùng cấu hình thứ cấp.
} else {
    // Không có cấu hình cho nhóm thứ cấp.
}
~~~

Lưu ý: `SecondaryProperties` là kiểu Java do ứng dụng định nghĩa; ví dụ đầy đủ sẽ xuất hiện ở các phần sau.

**Mục tiêu bài học:**

- Hiểu `Binder.bind(...)` trả về `BindResult<T>` như thế nào.
- Biết dùng `isBound()`, `get()`, `orElse()`, `orElseGet()`, `orElseThrow()`, `ifBound()` và `map()`.
- Chọn chính sách phù hợp khi nguồn không có dữ liệu.
- Không nhầm “unbound” với lỗi chuyển kiểu, validation, cấu hình rỗng hoặc một object chỉ được bind một phần.
- Phân biệt `bind(...)` với `bindOrCreate(...)`.
- Biết cách bind collection có kiểu và cách kiểm thử kết quả bằng `MapConfigurationPropertySource`.
- Biết khi nào nên dùng programmatic Binder, khi nào nên để `@ConfigurationProperties` của Spring Boot quản lý.

## 2. Binder là gì và hoạt động ở tầng nào?

`org.springframework.boot.context.properties.bind.Binder` là API của Spring Boot để gắn các `ConfigurationPropertySource` vào một kiểu Java mong muốn.

Nó thực hiện các việc như:

- Tìm các khóa cấu hình theo prefix.
- Áp dụng quy tắc relaxed binding cho tên thuộc tính.
- Lấy giá trị từ các nguồn cấu hình liên quan.
- Phân giải placeholder khi có cấu hình hỗ trợ.
- Chuyển kiểu chuỗi/số sang `Duration`, `DataSize`, `URI`, `Enum`, danh sách, map hoặc object cấu trúc.
- Tạo hoặc cập nhật đối tượng mục tiêu theo cơ chế binding tương ứng.
- Trả kết quả có trạng thái thay vì bắt buộc người gọi luôn nhận một object.

Với một ứng dụng Spring Boot đã khởi động, cách truy cập quen thuộc:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

Binder binder = Binder.get(environment);
~~~

`Binder.get(Environment)` dựng binder từ một `Environment` mà Spring Boot đã chuẩn bị và gắn các `ConfigurationPropertySource` phù hợp. Đối với một `Environment` tự tạo bên ngoài luồng Boot, cần bảo đảm nguồn cấu hình đã được attach thích hợp; trong test độc lập, cách đơn giản hơn là tạo binder từ `MapConfigurationPropertySource`.

### Luồng xử lý

~~~text
application.yaml / application-prod.yaml
system environment / Java System properties
--key=value và các PropertySource khác
                   |
                   v
       Environment / nguồn cấu hình
                   |
                   v
        Binder.bind("app.secondary",
                    SecondaryProperties.class)
                   |
          +--------+---------+
          |                  |
          v                  v
   Có dữ liệu phù hợp     Không có dữ liệu
   và bind được          để bind mục tiêu
          |                  |
          v                  v
  BindResult bound     BindResult unbound
          |
          +---- nếu chuyển kiểu/binding lỗi ----> Exception
~~~

Cần tránh suy luận sai rằng `BindResult` là “hộp luôn chứa lỗi nếu quá trình thất bại”. Nó chủ yếu biểu diễn **kết quả có hoặc không có giá trị đã bind**. Một lỗi binding thông thường vẫn có thể được ném ra từ chính lời gọi `bind(...)`.

## 3. Lời gọi bind cơ bản

Một ví dụ có dữ liệu:

~~~properties
report.timeout=15s
~~~

Mã:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public final class ReportConfigReader {

    private final Binder binder;

    public ReportConfigReader(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public Duration timeout() {
        BindResult<Duration> result =
                binder.bind("report.timeout", Duration.class);

        return result.orElse(Duration.ofSeconds(5));
    }
}
~~~

Khi `report.timeout=15s` có hiệu lực:

~~~text
result.isBound() = true
result.get() = PT15S
timeout() = PT15S
~~~

Nếu `report.timeout` không tồn tại trong các nguồn phù hợp:

~~~text
result.isBound() = false
timeout() = PT5S
~~~

Giá trị 5 giây đến từ `orElse(Duration.ofSeconds(5))`, **không phải một giá trị do Spring Boot tự đoán**.

### Ba tham số khái niệm

~~~java
binder.bind("report.timeout", Duration.class)
            |               |
            |               +-- kiểu đích
            +------------------ tên cấu hình cần bind
~~~

- Tên thuộc tính nên viết ở dạng canonical lowercase kebab-case, có dấu chấm phân cấp.
- Kiểu đích quyết định quy tắc chuyển đổi.
- Kết quả là `BindResult<Duration>`, không phải `Duration` trực tiếp.

Nếu chỉ cần một khóa và không cần trạng thái bound/unbound, `Environment.getProperty(...)` có thể đủ. Nhưng khi muốn xử lý một object hay collection có cấu trúc và kiểm soát chính sách vắng mặt, `BindResult` diễn đạt rõ ràng hơn.

## 4. BindResult<T> không phải Optional<T>

`BindResult<T>` là một lớp riêng của Spring Boot:

~~~java
org.springframework.boot.context.properties.bind.BindResult<T>
~~~

Nó giống `Optional<T>` ở một số thao tác, nhưng **không phải `java.util.Optional<T>`** và không thể gán trực tiếp:

~~~java
// Sai kiểu:
Optional<Duration> result =
        binder.bind("report.timeout", Duration.class);
~~~

Dạng đúng:

~~~java
BindResult<Duration> result =
        binder.bind("report.timeout", Duration.class);
~~~

Bảng API chính trong Spring Boot 3.x:

| Phương thức | Ý nghĩa khi bound | Ý nghĩa khi unbound |
| --- | --- | --- |
| `isBound()` | Trả `true`. | Trả `false`. |
| `get()` | Trả đối tượng đã bind. | Ném `NoSuchElementException`. |
| `orElse(other)` | Trả đối tượng đã bind. | Trả `other`. |
| `orElseGet(supplier)` | Trả đối tượng đã bind, không gọi supplier. | Gọi supplier và trả kết quả. |
| `orElseThrow(supplier)` | Trả đối tượng đã bind. | Ném exception do supplier tạo. |
| `ifBound(consumer)` | Chạy consumer với giá trị. | Không làm gì. |
| `map(function)` | Áp dụng function lên giá trị và trả một `BindResult` mới. | Giữ trạng thái không bound, không gọi function. |

Cách xử lý cần dựa vào **ý nghĩa nghiệp vụ** của việc thiếu cấu hình: có thể chấp nhận, có mặc định, hay phải từ chối khởi động.

## 5. isBound(): kiểm tra trước khi lấy giá trị

Ví dụ:

~~~java
BindResult<String> result =
        binder.bind("app.region", String.class);

if (result.isBound()) {
    String region = result.get();
    System.out.println("Vùng được cấu hình: " + region);
} else {
    System.out.println("Chưa khai báo app.region");
}
~~~

Ở đây `isBound()` giúp tránh gọi `get()` trên kết quả trống.

Nếu YAML có:

~~~yaml
app:
  region: apac
~~~

thì `isBound()` là true và `get()` trả `apac`.

Nếu YAML không có `app.region`, và không nguồn nào khác cung cấp nó, kết quả unbound.

### Không nhầm với kiểm tra Boolean

Giả sử:

~~~properties
feature.export.enabled=false
~~~

Và:

~~~java
BindResult<Boolean> result =
        binder.bind("feature.export.enabled", Boolean.class);
~~~

Khi giá trị `false` được bind thành công:

~~~text
result.isBound() = true
result.get() = false
~~~

**Giá trị Boolean false là dữ liệu có mặt, không phải trạng thái không bind được.**

Tương tự:

~~~properties
app.retry-count=0
~~~

khi bind thành công sang `Integer`, kết quả là **bound với giá trị 0**, không phải unbound.

Đừng viết:

~~~java
if (Boolean.TRUE.equals(result.orElse(false))) {
    // ...
}
~~~

rồi cho rằng nhánh false cho biết thuộc tính vắng mặt. Nó gộp hai tình huống khác nhau: không có cấu hình và người vận hành đã chủ động tắt tính năng.

## 6. get(): chỉ dùng khi có bằng chứng giá trị tồn tại

`BindResult.get()` trả về đối tượng đã bind, nhưng **ném `NoSuchElementException` nếu không có giá trị**.

Ví dụ không an toàn:

~~~java
Duration timeout =
        binder.bind("remote.timeout", Duration.class)
                .get();
~~~

Nếu `remote.timeout` không tồn tại, code ném exception. Đây có thể là lựa chọn có chủ đích nếu bạn muốn ứng dụng thất bại, nhưng thông báo của exception mặc định thường không diễn đạt đầy đủ yêu cầu nghiệp vụ.

Khi điều kiện thiếu cấu hình là lỗi có ý nghĩa riêng, dùng:

~~~java
Duration timeout =
        binder.bind("remote.timeout", Duration.class)
                .orElseThrow(() -> new IllegalStateException(
                        "Thiếu cấu hình bắt buộc remote.timeout"));
~~~

Khi muốn kiểm tra rồi xử lý nhiều nhánh:

~~~java
BindResult<Duration> result =
        binder.bind("remote.timeout", Duration.class);

if (!result.isBound()) {
    throw new IllegalStateException(
            "Chưa cấu hình remote.timeout");
}

Duration timeout = result.get();
~~~

Cách thứ nhất ngắn hơn; cách thứ hai phù hợp khi cần thêm thông tin log, đặt trạng thái hoặc xử lý nhiều trường hợp.

**Không bắt `NoSuchElementException` của `get()` làm một cơ chế điều khiển luồng mặc định** khi đã có `isBound()` và `orElseThrow()` với thông điệp rõ ràng.

## 7. orElse(): giá trị dự phòng đơn giản

Trường hợp phổ biến nhất: cấu hình tùy chọn có một mặc định rõ ràng.

~~~java
Duration retryDelay =
        binder.bind("jobs.retry-delay", Duration.class)
                .orElse(Duration.ofMillis(250));
~~~

Với:

~~~properties
jobs.retry-delay=2s
~~~

kết quả là `Duration.ofSeconds(2)`.

Không có `jobs.retry-delay` thì dùng `Duration.ofMillis(250)`.

### Chú ý: orElse chỉ áp dụng khi BindResult không bound

Giả sử:

~~~properties
jobs.retry-delay=0ms
~~~

Binder có thể tạo `Duration.ZERO` hợp lệ. Vì đã bind, `orElse(Duration.ofMillis(250))` **không thay giá trị 0 bằng mặc định**.

Nếu 0 không được phép theo nghiệp vụ, cần validation riêng:

~~~java
Duration delay =
        binder.bind("jobs.retry-delay", Duration.class)
                .orElse(Duration.ofMillis(250));

if (delay.isZero() || delay.isNegative()) {
    throw new IllegalArgumentException(
            "jobs.retry-delay phải lớn hơn 0");
}
~~~

Tách hai câu hỏi:

- Không khai báo khóa → có thể dùng default.
- Có khai báo nhưng giá trị ngoài phạm vi → báo lỗi validation.

### Giá trị dự phòng được tính trước

Trong Java:

~~~java
ServiceOptions value = result.orElse(createDefaultOptions());
~~~

`createDefaultOptions()` được gọi **trước** khi `orElse(...)` nhận tham số, kể cả khi `result` đã bound.

Điều này không gây vấn đề với `Duration.ofSeconds(5)` đơn giản, nhưng nếu việc tạo default tốn chi phí, gọi file/network hoặc có side effect, hãy dùng `orElseGet(...)`.

## 8. orElseGet(): chỉ tạo giá trị dự phòng khi thật sự cần

~~~java
ServiceOptions options =
        binder.bind("service.backup", ServiceOptions.class)
                .orElseGet(() -> loadLocalDefaultOptions());
~~~

`loadLocalDefaultOptions()` chỉ được gọi nếu bind không có giá trị.

Ví dụ một record:

~~~java
import java.time.Duration;

public record ServiceOptions(
        String endpoint,
        Duration timeout) {
}
~~~

Giá trị mặc định:

~~~java
private ServiceOptions defaultOptions() {
    return new ServiceOptions(
            "http://localhost:8089",
            Duration.ofSeconds(3));
}
~~~

Sử dụng:

~~~java
ServiceOptions options =
        binder.bind("service.backup", ServiceOptions.class)
                .orElseGet(this::defaultOptions);
~~~

So sánh:

| Cách viết | Khi bound | Khi unbound |
| --- | --- | --- |
| `orElse(defaultOptions())` | Vẫn gọi `defaultOptions()` rồi bỏ kết quả. | Gọi và dùng default. |
| `orElseGet(this::defaultOptions)` | Không gọi `defaultOptions()`. | Gọi và dùng default. |

Nên ưu tiên `orElseGet` nếu default có chi phí hoặc đòi hỏi logic khởi tạo. Tuy nhiên, **không nên thực hiện network call trong supplier fallback của cấu hình** trừ khi bạn có một yêu cầu và cơ chế xử lý lỗi thật rõ ràng; các mặc định cấu hình thường nên xác định và không phụ thuộc kết nối bên ngoài.

## 9. orElseThrow(): cấu hình bắt buộc

Có những tham số không nên có default tùy tiện. Ví dụ địa chỉ một dịch vụ thanh toán:

~~~java
URI paymentEndpoint =
        binder.bind("payment.endpoint", URI.class)
                .orElseThrow(() -> new IllegalStateException(
                        "payment.endpoint là cấu hình bắt buộc"));
~~~

Khi không có dữ liệu bind, ứng dụng báo lỗi có ý nghĩa nghiệp vụ.

Khi có dữ liệu hợp lệ:

~~~properties
payment.endpoint=https://payment.example.test
~~~

Binder chuyển thành `URI` và trả qua `orElseThrow(...)` mà không gọi supplier exception.

### Điều quan trọng về lỗi chuyển kiểu

Nếu cấu hình là:

~~~properties
jobs.max-attempts=abc
~~~

mà code thực hiện:

~~~java
int attempts =
        binder.bind("jobs.max-attempts", Integer.class)
                .orElseThrow(() -> new IllegalStateException(
                        "Thiếu jobs.max-attempts"));
~~~

Lỗi **không phải** “thiếu jobs.max-attempts”: khóa có mặt nhưng `abc` không thể chuyển thành `Integer`. Binder thường ném một lỗi binding, ví dụ `BindException`, **trước khi** bạn nhận được `BindResult` để gọi `orElseThrow(...)`.

Do đó, đừng hiểu `orElseThrow` là nơi xử lý tất cả lỗi dữ liệu. Nó xử lý **kết quả unbound**, không thay cơ chế thông báo lỗi conversion/validation.

## 10. ifBound(): thực hiện hành động chỉ khi có cấu hình

~~~java
binder.bind("diagnostics.label", String.class)
        .ifBound(label -> System.out.println(
                "Label: " + label));
~~~

Nếu không khai báo `diagnostics.label`, consumer không chạy.

Cách này hữu ích khi:

- Có một nhãn hiển thị tùy chọn.
- Một giá trị cấu hình sẽ kích hoạt bước thiết lập phụ.
- Muốn bổ sung hành vi khi thuộc tính hiện diện, không cần một nhánh `else`.

Ví dụ trong một `ApplicationRunner`:

~~~java
@Override
public void run(ApplicationArguments args) {
    Binder binder = Binder.get(environment);

    binder.bind("app.startup-note", String.class)
            .ifBound(note ->
                    System.out.println("Startup note: " + note));
}
~~~

Không nên dùng `ifBound` như một cách che giấu việc thiếu cấu hình bắt buộc. Nếu `app.startup-note` thực sự là bắt buộc, `orElseThrow` làm yêu cầu đó rõ ràng hơn.

### ifBound không bắt đầu một quá trình “theo dõi”

`ifBound` chỉ thực hiện consumer **tại thời điểm lời gọi**. Nó không đăng ký subscription theo dõi tệp YAML, không chạy lại khi biến môi trường thay đổi, và không tự reload config trong lúc ứng dụng đang chạy.

## 11. map(): biến đổi giá trị khi bind thành công

`BindResult.map(...)` có thể chuyển một `BindResult<T>` sang `BindResult<U>`.

Ví dụ:

~~~java
BindResult<Integer> retryLimit =
        binder.bind("jobs.retry-limit", Integer.class);

BindResult<String> description =
        retryLimit.map(value -> "Giới hạn: " + value);
~~~

Nếu `jobs.retry-limit=5`:

~~~text
retryLimit.isBound() = true
description.isBound() = true
description.get() = "Giới hạn: 5"
~~~

Nếu không có cấu hình:

~~~text
retryLimit.isBound() = false
description.isBound() = false
~~~

Function không được gọi trong trường hợp unbound.

Một mẫu gọn:

~~~java
String description =
        binder.bind("jobs.retry-limit", Integer.class)
                .map(value -> "Giới hạn: " + value)
                .orElse("Dùng chính sách mặc định");
~~~

`map` hữu ích khi muốn làm giàu một giá trị đã bind rồi mới quyết định fallback.

**Lưu ý:** `map` không phải một trình xử lý lỗi chuyển kiểu từ Binder. Nếu `retry-limit=abc` và quá trình bind số nguyên thất bại, function không có cơ hội “sửa” dữ liệu đó qua `map`.

## 12. Tổng hợp các cách xử lý một khóa

Giả sử:

~~~java
BindResult<Duration> result =
        binder.bind("client.timeout", Duration.class);
~~~

| Yêu cầu nghiệp vụ | Cách viết phù hợp |
| --- | --- |
| Chỉ muốn biết có dữ liệu hay không | `result.isBound()` |
| Đã biết chắc có dữ liệu | `result.get()` |
| Có default đơn giản | `result.orElse(Duration.ofSeconds(5))` |
| Cần tạo default khi thiếu | `result.orElseGet(this::defaultTimeout)` |
| Bắt buộc cấu hình | `result.orElseThrow(() -> new IllegalStateException("..."))` |
| Chỉ chạy hành động nếu có | `result.ifBound(this::useTimeout)` |
| Chuyển sang kiểu mô tả rồi dùng default | `result.map(Duration::toString).orElse("unspecified")` |

Đừng viết một chuỗi `if/else` dài chỉ vì chưa biết `BindResult` đã có API phù hợp. Ngược lại, không nên ép mọi chính sách nghiệp vụ vào một dòng chain quá dài khiến thông báo lỗi và logic validation trở nên khó đọc.

## 13. Bốn trạng thái khác nhau: thiếu, rỗng, giá trị đặc biệt, dữ liệu sai

Đây là phần quan trọng nhất khi xử lý “không có dữ liệu”.

### Trạng thái A — không tồn tại thuộc tính

~~~properties
# Không có jobs.enabled ở bất kỳ nguồn nào
~~~

~~~java
BindResult<Boolean> result =
        binder.bind("jobs.enabled", Boolean.class);
~~~

Trong trường hợp không có khóa tương ứng, kết quả thường là unbound.

### Trạng thái B — có Boolean false hoặc số 0

~~~properties
jobs.enabled=false
jobs.retry-count=0
~~~

Đây là dữ liệu có giá trị. Binder có thể chuyển chúng thành `Boolean.FALSE` và `Integer.valueOf(0)`.

~~~text
isBound() = true
get() = false hoặc 0
~~~

Đừng dùng điều kiện như `if (result.orElse(false))` để suy luận xem **người vận hành có cung cấp khóa không**.

### Trạng thái C — chuỗi rỗng

~~~properties
jobs.label=
~~~

Nếu bind tới `String`, chuỗi rỗng có thể là một giá trị được bind. Nếu bind tới một kiểu khác, chuỗi rỗng có thể có cách chuyển đổi khác hoặc gây vấn đề tùy converter.

Vì vậy, **“có khóa nhưng chuỗi rỗng” không nên bị coi mặc nhiên là “không có nguồn dữ liệu”**. Khi chuỗi bắt buộc có nội dung:

~~~java
String label = binder.bind("jobs.label", String.class)
        .orElseThrow(() -> new IllegalStateException(
                "Thiếu jobs.label"));

if (label.isBlank()) {
    throw new IllegalStateException(
            "jobs.label không được rỗng");
}
~~~

### Trạng thái D — có dữ liệu nhưng không chuyển kiểu được

~~~properties
jobs.retry-count=abc
~~~

~~~java
binder.bind("jobs.retry-count", Integer.class);
~~~

Trường hợp này là lỗi binding/conversion. `orElse(3)` **không có nghĩa** “nếu người vận hành nhập sai kiểu thì âm thầm dùng 3”.

### Bảng suy luận

| Nguồn | Kiểu đích | Hướng xử lý |
| --- | --- | --- |
| Không có `jobs.enabled` | `Boolean` | Unbound; tự chọn default hoặc báo thiếu. |
| `jobs.enabled=false` | `Boolean` | Bound với false. |
| `jobs.retry-count=0` | `Integer` | Bound với 0. |
| `jobs.label=` | `String` | Kiểm tra rỗng theo chính sách nghiệp vụ. |
| `jobs.retry-count=abc` | `Integer` | Lỗi conversion/binding, không phải fallback do vắng mặt. |
| `jobs.timeout=5s` | `Duration` | Bound nếu converter hỗ trợ, là 5 giây. |

Kết luận: `BindResult.isBound()` trả lời câu hỏi **“có bind được một kết quả không?”**, không phải câu hỏi **“giá trị đó có hợp lý cho ứng dụng không?”**.

## 14. Khi toàn bộ prefix vắng mặt

Hãy xét record:

~~~java
package com.example.demo.config;

import java.time.Duration;

public record ExportOptions(
        boolean enabled,
        String outputDirectory,
        Duration timeout) {
}
~~~

Mã:

~~~java
BindResult<ExportOptions> result =
        binder.bind("feature.export", ExportOptions.class);
~~~

Nguồn hiện tại chỉ có:

~~~yaml
feature:
  notifications:
    enabled: true
~~~

Không có khóa nào thuộc `feature.export.*`.

Trong cách bind thông thường, `result` là unbound. Cách xử lý tùy nghiệp vụ:

**Chức năng xuất tùy chọn:**

~~~java
ExportOptions options = result.orElseGet(() ->
        new ExportOptions(
                false,
                "./out",
                Duration.ofSeconds(10)));
~~~

**Chức năng xuất bắt buộc:**

~~~java
ExportOptions options = result.orElseThrow(
        () -> new IllegalStateException(
                "Thiếu nhóm cấu hình feature.export"));
~~~

**Chỉ khởi tạo một thành phần nếu được cấu hình:**

~~~java
result.ifBound(options ->
        System.out.println("Export config: " + options));
~~~

### Cẩn thận với tên prefix

`feature.export` là một namespace. Có `feature.enabled` hoặc `feature.notifications.enabled` **không có nghĩa** nhóm `feature.export` đã được cung cấp.

Đối với object lồng nhau, Binder xét những đường dẫn thuộc nhóm mục tiêu. Đừng dựa vào sự tồn tại của một khóa gần giống để khẳng định nhóm đã bound.

## 15. Khi có một phần dữ liệu: bound không đồng nghĩa mọi field đầy đủ

Giả sử nguồn chỉ có:

~~~yaml
feature:
  export:
    enabled: true
~~~

Nhưng kiểu đích là:

~~~java
public record ExportOptions(
        boolean enabled,
        String outputDirectory,
        Duration timeout) {
}
~~~

Binder có thể tạo một object `ExportOptions` khi tìm được dữ liệu cho phần `enabled`. Vì `output-directory` và `timeout` chưa có giá trị, các thành viên tham chiếu có thể nhận `null` theo cách constructor binding đang dùng.

Do đó:

~~~java
BindResult<ExportOptions> result =
        binder.bind("feature.export", ExportOptions.class);
~~~

có thể trả **bound** dù object **chưa đủ dữ liệu cho nghiệp vụ xuất báo cáo**.

Và:

~~~java
ExportOptions options = result.orElseGet(() ->
        new ExportOptions(
                false, "./out", Duration.ofSeconds(10)));
~~~

sẽ **không** dùng default nếu `result` đã bound do `enabled=true`. Nó không tự lấy default để điền cho từng field còn thiếu trong object đã tạo.

Đây là nhầm lẫn lớn nhất cần tránh khi áp dụng fallback cho **cả nhóm cấu hình**.

### Hai mức thiếu dữ liệu

1. **Thiếu toàn bộ nhóm:** không bind được target → `BindResult` unbound.
2. **Nhóm có một vài thuộc tính:** có thể bind được object → `BindResult` bound, nhưng một số member vẫn thiếu/default.

Phải xử lý hai mức này riêng biệt.

### Khi cần từng field có default

Có thể dùng `@DefaultValue` trong constructor binding:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.bind.DefaultValue;

public record ExportOptions(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("./out") String outputDirectory,
        @DefaultValue("10s") Duration timeout) {
}
~~~

Với đăng ký và binder hỗ trợ constructor binding phù hợp, `@DefaultValue` cung cấp default cho những thành viên bị thiếu trong quá trình tạo object.

Điểm phân biệt:

- `@DefaultValue` trên **thành viên constructor/record**: mặc định ở cấp field/parameter khi binder tạo object.
- `BindResult.orElse(...)`: mặc định cho **toàn bộ kết quả**, chỉ khi không bind được giá trị mục tiêu.

Ngay cả khi đã dùng `@DefaultValue` cho các thành viên, vẫn nên xác định chính sách khi **toàn bộ prefix không có dữ liệu**; không nên giả định những default cấp field luôn buộc Binder phải tạo một object nếu toàn nhóm vắng mặt.

## 16. Mặc định của JavaBean và cơ chế binding

Với một class mutable:

~~~java
import java.time.Duration;

public class ExportOptions {

    private boolean enabled = false;
    private String outputDirectory = "./out";
    private Duration timeout = Duration.ofSeconds(10);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getOutputDirectory() {
        return outputDirectory;
    }

    public void setOutputDirectory(String outputDirectory) {
        this.outputDirectory = outputDirectory;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Nếu Binder tạo và gắn dữ liệu vào instance mutable theo JavaBean binding, các giá trị field ban đầu có thể được giữ lại cho những thuộc tính không xuất hiện. Đây là một cách đặt default ở mức object.

Nhưng cần tách:

- JavaBean field initializer: default **bên trong object khi nó được tạo**.
- `orElseGet(() -> new ExportOptions())`: default **khi kết quả bind hoàn toàn unbound**.
- `bindOrCreate(...)`: API trực tiếp yêu cầu trả một instance được bind hoặc tạo nếu không có kết quả.

Một mô hình tốt cần nói rõ khi nào cho phép vắng cấu hình và trường nào là bắt buộc.

## 17. bindOrCreate(): bind nếu được, tạo mới nếu không

`Binder` còn có:

~~~java
<T> T bindOrCreate(String name, Class<T> target);
~~~

Ví dụ với một JavaBean có constructor không tham số như `ExportOptions` ở phần trước:

~~~java
ExportOptions options =
        binder.bindOrCreate("feature.export", ExportOptions.class);
~~~

Nếu nguồn cung cấp các khóa phù hợp, Binder cố bind như thông thường. Nếu kết quả bind là `null`, phương thức sẽ cố tạo một instance mới của kiểu đích.

So sánh:

~~~java
BindResult<ExportOptions> result =
        binder.bind("feature.export", ExportOptions.class);
~~~

và:

~~~java
ExportOptions options =
        binder.bindOrCreate("feature.export", ExportOptions.class);
~~~

| Cách gọi | Kiểu trả về | Khi không có dữ liệu |
| --- | --- | --- |
| `bind(name, type)` | `BindResult<T>` | Unbound; người gọi chọn chính sách. |
| `bindOrCreate(name, type)` | `T` | Cố tạo instance mới của type. |

### Khi nào bindOrCreate hợp lý?

Khi một kiểu có thể tạo an toàn với các mặc định của chính nó, ví dụ JavaBean có constructor mặc định:

~~~java
public class OptionalCacheSettings {
    private boolean enabled = false;
    private int capacity = 100;

    public OptionalCacheSettings() {
    }

    // getters / setters
}
~~~

`bindOrCreate("cache.optional", OptionalCacheSettings.class)` là một cách yêu cầu luôn có đối tượng cài đặt nếu việc tạo instance thành công.

### Những giới hạn quan trọng

- Không phải mọi kiểu đều có thể tạo khi thiếu cấu hình. Một class bất biến có constructor bắt buộc, interface hay kiểu trừu tượng có thể không có cách khởi tạo phù hợp; thao tác có thể báo lỗi.
- `bindOrCreate` không đảm bảo một object thỏa mọi constraint nghiệp vụ. Nó chủ yếu giải quyết việc có hay không có instance.
- Nó không biến giá trị cấu hình **sai kiểu** thành một object mặc định; lỗi bind vẫn cần được xử lý như lỗi.
- Nếu yêu cầu phải phân biệt “không khai báo” với “có khai báo”, `bind(...)` và `BindResult.isBound()` minh bạch hơn.

Không nên thay toàn bộ `bind(...)` bằng `bindOrCreate(...)` chỉ để tránh các nhánh xử lý thiếu dữ liệu. Việc luôn tạo object có thể làm ứng dụng bỏ qua một nhóm cấu hình đáng lẽ bắt buộc.

## 18. Chiến lược xử lý thiếu dữ liệu theo tính chất chức năng

Giả sử có một cấu hình cho dịch vụ giám sát bên ngoài:

~~~text
monitoring.remote.*
~~~

Có ba chiến lược chính.

### 18.1. Tính năng tùy chọn: bỏ qua khi không cấu hình

~~~java
BindResult<RemoteMonitorProperties> result =
        binder.bind("monitoring.remote",
                RemoteMonitorProperties.class);

if (!result.isBound()) {
    System.out.println(
            "Remote monitoring chưa được cấu hình");
    return;
}

RemoteMonitorProperties config = result.get();
startRemoteMonitor(config);
~~~

Ứng dụng không cần khởi động kết nối remote nếu hoàn toàn không có cấu hình.

### 18.2. Tính năng có mặc định an toàn: dùng fallback

~~~java
RemoteMonitorProperties config =
        binder.bind("monitoring.remote",
                RemoteMonitorProperties.class)
                .orElseGet(this::localMonitorDefaults);
~~~

Đây là trường hợp có thiết kế mặc định hợp lệ như giám sát local hoặc chế độ disable.

### 18.3. Tính năng bắt buộc: thất bại sớm

~~~java
RemoteMonitorProperties config =
        binder.bind("monitoring.remote",
                RemoteMonitorProperties.class)
                .orElseThrow(() -> new IllegalStateException(
                        "monitoring.remote là cấu hình bắt buộc"));
~~~

Khi cấu hình cần thiết để hệ thống hoạt động chính xác, thất bại sớm thường an toàn hơn tự ý thay bằng một URL giả.

### Câu hỏi thiết kế

Trước khi chọn phương thức, hãy trả lời:

1. Nếu không có nhóm này, ứng dụng có chạy đúng về mặt nghiệp vụ không?
2. Một default có làm giảm bảo mật hoặc khiến hệ thống gửi dữ liệu nhầm nơi không?
3. Nếu có một vài field nhưng thiếu field quan trọng, ứng dụng nên xử lý thế nào?
4. Nếu một field đã được cấu hình sai kiểu, có cần báo lỗi thay vì fallback không?
5. Default có cần dựa vào môi trường/profiles không, hay là một hằng số ổn định?

`BindResult` cho phép triển khai quyết định này, nhưng không quyết định thay ứng dụng.

## 19. Một ví dụ programmatic Binder hoàn chỉnh

Giả sử module export chỉ hoạt động khi được cấu hình. Đối tượng:

~~~java
package com.example.demo.export;

import java.time.Duration;

public record ExportProperties(
        boolean enabled,
        String outputDirectory,
        Duration timeout) {
}
~~~

Một `ApplicationRunner` đọc từ `Environment`:

~~~java
package com.example.demo.export;

import java.time.Duration;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ExportStartupReporter implements ApplicationRunner {

    private final Environment environment;

    public ExportStartupReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        Binder binder = Binder.get(environment);

        BindResult<ExportProperties> result =
                binder.bind("feature.export",
                        ExportProperties.class);

        if (!result.isBound()) {
            System.out.println(
                    "Export module: chưa cấu hình, giữ trạng thái tắt");
            return;
        }

        ExportProperties properties = result.get();

        if (!properties.enabled()) {
            System.out.println(
                    "Export module: đã cấu hình nhưng bị tắt");
            return;
        }

        if (properties.outputDirectory() == null
                || properties.outputDirectory().isBlank()) {
            throw new IllegalStateException(
                    "Thiếu feature.export.output-directory");
        }

        if (properties.timeout() == null
                || properties.timeout().isZero()
                || properties.timeout().isNegative()) {
            throw new IllegalStateException(
                    "feature.export.timeout phải là Duration dương");
        }

        System.out.println(
                "Export module: bật, thư mục="
                        + properties.outputDirectory()
                        + ", timeout=" + properties.timeout());

        // Ví dụ chỉ minh họa phân loại và validation.
        // Chưa đọc/ghi bất kỳ tệp đầu ra nào.
    }
}
~~~

Các trường hợp:

**Không có `feature.export.*`:**

~~~text
Export module: chưa cấu hình, giữ trạng thái tắt
~~~

**Chỉ có:**

~~~properties
feature.export.enabled=false
~~~

thì một object có thể được bind với `enabled=false`; ứng dụng nhận diện được rằng người vận hành **có khai báo cấu hình nhưng chủ động tắt**.

**Có:**

~~~yaml
feature:
  export:
    enabled: true
    output-directory: ./reports
    timeout: 30s
~~~

thì một object hợp lệ có thể được bind và được sử dụng.

**Có:**

~~~yaml
feature:
  export:
    enabled: true
~~~

thì kết quả có thể bound nhưng thiếu hai field tham chiếu. Runner tự kiểm tra và báo lỗi cụ thể thay vì giả định `result.isBound()` đã bảo đảm toàn bộ cấu hình hợp lệ.

### Tại sao ví dụ không dùng fallback cả record?

Vì yêu cầu xuất báo cáo chỉ an toàn khi các field cần thiết có giá trị. Nếu tạo default cho cả record khi có bất kỳ thiếu sót nào, ứng dụng có thể gửi dữ liệu vào một thư mục không mong đợi hoặc che mất một lỗi triển khai.

## 20. Đưa default xuống cấp từng field với @DefaultValue

Nếu cấu hình cho phép một số field vắng mặt, có thể thiết kế record dùng `@DefaultValue` cho tham số constructor:

~~~java
package com.example.demo.export;

import java.time.Duration;

import org.springframework.boot.context.properties.bind.DefaultValue;

public record ExportProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("./reports") String outputDirectory,
        @DefaultValue("30s") Duration timeout) {
}
~~~

Giả sử nguồn có:

~~~yaml
feature:
  export:
    enabled: true
~~~

Nếu Binder xây dựng record theo constructor binding, các thành viên còn thiếu có thể được nhận giá trị default đã khai báo.

Điểm cần làm rõ:

- Khi nhóm đã đủ dữ liệu để bind và object được tạo, `@DefaultValue` giải quyết giá trị của **từng tham số** thiếu.
- Nếu hoàn toàn không có dữ liệu cho prefix, không nên mặc định rằng một bản ghi với toàn default sẽ được tạo bởi `bind(...)`. Nếu muốn fallback chắc chắn, xử lý `BindResult` hoặc dùng `bindOrCreate` theo kiểu phù hợp.
- `@DefaultValue("30s")` đưa ra **giá trị mặc định**, không phải là cùng một khái niệm với `@DurationUnit`, vốn chỉ đổi **đơn vị mặc định của số trần**.

Nếu một field thực sự bắt buộc khi `enabled=true`, có thể không nên đặt default cho nó. Thay vì che giấu yêu cầu bằng một giá trị giả, hãy dùng validation khi tính năng được bật.

## 21. Collection: dùng Bindable để giữ kiểu phần tử

Đối với một List:

~~~properties
app.backends[0]=alpha.example.test
app.backends[1]=beta.example.test
~~~

Bạn muốn `List<String>`, không phải một `List` raw type.

Sử dụng:

~~~java
import java.util.List;

import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;

BindResult<List<String>> result =
        binder.bind(
                "app.backends",
                Bindable.listOf(String.class));
~~~

Khi có các phần tử, Binder có thể tạo danh sách tương ứng.

Khi không có dữ liệu:

~~~java
List<String> backends =
        binder.bind("app.backends", Bindable.listOf(String.class))
                .orElseGet(List::of);
~~~

Trong trường hợp không có cấu hình, bạn có danh sách rỗng do ứng dụng lựa chọn. Đây là fallback được tính ở **cấp kết quả**.

### Tại sao không dùng bind("app.backends", List.class)?

Vì `List.class` không mô tả đầy đủ kiểu phần tử cần chuyển đổi. `Bindable.listOf(String.class)` giúp Binder biết `String` là kiểu mỗi phần tử.

Có API tương tự cho các tập khác:

~~~java
Bindable.setOf(String.class);
Bindable.mapOf(String.class, Integer.class);
~~~

Với map:

~~~properties
app.quotas.alpha=5
app.quotas.beta=10
~~~

~~~java
import java.util.Map;

Map<String, Integer> quotas =
        binder.bind(
                "app.quotas",
                Bindable.mapOf(String.class, Integer.class))
                .orElseGet(Map::of);
~~~

### Không có List khác List rỗng

- **Không có nguồn cho `app.backends`:** có thể unbound, ứng dụng dùng `List.of()` theo chính sách.
- **Có nguồn biểu diễn một danh sách rỗng:** hành vi cụ thể phụ thuộc dạng nguồn và quy tắc conversion/binding; không nên suy đoán mọi cách biểu diễn trống đều giống thiếu prefix.
- **Có một danh sách nhưng phần tử chuyển kiểu sai:** đó là lỗi binding, không phải mặc định danh sách rỗng.

Ngoài ra, khi nhiều `PropertySource` cùng định nghĩa một list, Spring Boot có quy tắc ưu tiên/thay thế riêng. Không dùng `orElseGet(List::of)` để hiểu là “trộn danh sách từ các nguồn” — đó là hai vấn đề khác nhau.

## 22. Bindable.ofInstance(): bind vào đối tượng đã có

Một khả năng khác của Binder là làm việc với `Bindable` bọc một instance:

~~~java
MutableOptions current = new MutableOptions();

BindResult<MutableOptions> result =
        binder.bind(
                "feature.export",
                Bindable.ofInstance(current));
~~~

Giả sử `MutableOptions` có getter/setter phù hợp. Đây là cách cung cấp **đối tượng hiện có** làm target cho quá trình binding, thay vì luôn yêu cầu Binder tự tạo record mới.

Cách này hữu ích khi cần kiểm soát object được cập nhật, nhưng cần cẩn trọng:

- Mutable object có thể bị thay đổi trong quá trình bind.
- Giá trị mặc định có sẵn trong object và dữ liệu được ghi đè cần có hợp đồng rõ ràng.
- Việc không có dữ liệu cho nhóm vẫn nên được xử lý bằng trạng thái `BindResult` hoặc chính sách riêng, không suy luận rằng target đã tạo sẽ luôn thành bound.
- Không sử dụng lại một instance mutable chung một cách tùy tiện giữa nhiều luồng hoặc lần binding.

Đối với cấu hình ứng dụng thông thường, một `@ConfigurationProperties` bean hoặc record bất biến thường dễ quản lý hơn việc tự cập nhật một đối tượng chia sẻ.

## 23. Lỗi conversion không tương đương unbound

Ví dụ:

~~~properties
server.client.timeout=not-a-duration
~~~

Mã:

~~~java
Duration timeout =
        binder.bind(
                "server.client.timeout",
                Duration.class)
                .orElse(Duration.ofSeconds(5));
~~~

Bạn có thể muốn “nếu không bind được thì dùng 5 giây”. Nhưng ở đây **dữ liệu thực sự tồn tại và sai cú pháp**, nên Binder thường ném `BindException` hoặc một lỗi binding liên quan.

`orElse` không đảm bảo được chạy trong trường hợp exception ấy.

Đây là hành vi nên giữ cho một cấu hình quan trọng. Nếu tự ý bỏ qua giá trị nhập sai, hệ thống có thể chạy với timeout khác hoàn toàn mong đợi.

### Xử lý lỗi tường minh khi thực sự cần

~~~java
try {
    return binder.bind(
            "server.client.timeout",
            Duration.class)
            .orElse(Duration.ofSeconds(5));
} catch (org.springframework.boot.context.properties.bind.BindException ex) {
    throw new IllegalStateException(
            "Cấu hình server.client.timeout không hợp lệ", ex);
}
~~~

Khi thực hiện catch, nên bảo toàn exception gốc trong chuỗi nguyên nhân để có thông tin về khóa và conversion.

### Không nên biến lỗi thành “không có dữ liệu”

Mẫu sau thường không nên dùng:

~~~java
try {
    return binder.bind("server.client.timeout", Duration.class)
            .orElse(Duration.ofSeconds(5));
} catch (Exception ignored) {
    return Duration.ofSeconds(5);
}
~~~

Nó che cả lỗi lập trình, lỗi conversion, lỗi validation hoặc những lỗi hệ thống khác. Nếu có một yêu cầu fallback sau lỗi cụ thể, hãy giới hạn loại lỗi, ghi dấu chẩn đoán an toàn và nói rõ chính sách nghiệp vụ.

## 24. BindHandler và kiểm soát cách binder xử lý lỗi

Ở mức nâng cao, `Binder.bind(...)` có overload nhận `BindHandler`:

~~~java
binder.bind(
        "app.settings",
        Bindable.of(Settings.class),
        handler);
~~~

`BindHandler` cho phép can thiệp vào một số bước xử lý binding. Spring Boot có các implementation phục vụ kiểm tra, validation hoặc chính sách lỗi trong những ngữ cảnh nhất định.

Nhưng `BindHandler` **không phải** là một giá trị trả về khác của `BindResult`. Vai trò của nó là thay đổi hoặc quan sát quá trình bind trước khi kết quả xuất hiện.

Đối với câu hỏi “nếu khóa không có dữ liệu thì làm gì?”, hầu hết trường hợp nên bắt đầu từ:

~~~java
bind(...).orElse(...)
bind(...).orElseGet(...)
bind(...).orElseThrow(...)
~~~

thay vì viết một `BindHandler` phức tạp.

Đặc biệt, các handler bỏ qua lỗi (nếu dùng) có thể khiến dữ liệu cấu hình sai bị che khuất. Chỉ sử dụng khi bạn thật sự cần và có kiểm thử chứng minh trạng thái cuối đúng.

## 25. Validation là bước khác với trạng thái BindResult

Giả sử object:

~~~java
public record ConnectionOptions(
        String host,
        int port) {
}
~~~

và nguồn chỉ có:

~~~properties
connection.port=0
~~~

Một object có thể được bind với `host=null` và `port=0`. `BindResult.isBound()` có thể true, nhưng cấu hình đó không an toàn để kết nối.

Với `@ConfigurationProperties`, có thể dùng Bean Validation:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "connection")
public record ConnectionProperties(
        @NotBlank String host,
        @Min(1) int port) {
}
~~~

Khi bean được đăng ký theo cơ chế phù hợp và có validation provider, Spring Boot có thể phát hiện cấu hình vi phạm ngay khi khởi động.

Khi tự gọi Binder ở ngoài cơ chế bean cấu hình, **không nên giả định các annotation validation luôn được tự thực thi theo đúng đường đi `@ConfigurationProperties`**. Nếu cần validation, hãy cung cấp handler/validator thích hợp hoặc kiểm tra kết quả bằng logic rõ ràng.

### Hai câu hỏi khác nhau

- `result.isBound()`: có object từ binding hay không?
- Object có hợp lệ?: host có rỗng không, port có trong phạm vi không, retry có dương không?

Một hệ thống nghiêm túc có thể cần cả hai.

## 26. So sánh Binder thủ công với @ConfigurationProperties

Khi toàn bộ ứng dụng cần một nhóm cấu hình ổn định, thường dùng:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String host,
        Duration timeout) {
}
~~~

Sau đó đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` và inject bean:

~~~java
@Service
public class ClientService {
    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }
}
~~~

Phù hợp khi:

- Nhóm cấu hình là một phần của thiết kế module.
- Cần validation lúc khởi động.
- Nhiều service dùng chung bean.
- Cần metadata cấu hình cho IDE.
- Muốn Spring Boot quản lý lifecycle và DI.

Ngược lại, programmatic Binder:

~~~java
BindResult<ClientProperties> result =
        Binder.get(environment)
                .bind("app.client", ClientProperties.class);
~~~

phù hợp khi:

- Cần đọc một nhóm cấu hình tùy chọn trong một luồng xử lý cụ thể.
- Muốn kiểm tra **có hay không có namespace** trước khi quyết định hành vi.
- Cần bind động một kiểu đích hoặc collection không thuận tiện tạo bean cố định.
- Đang xây một module hạ tầng xử lý nhiều nhóm cấu hình có cấu trúc khác nhau.
- Cần lựa chọn fallback riêng ở đúng thời điểm đọc.

**Không dùng Binder thủ công chỉ vì @ConfigurationProperties không hoạt động**, khi nguyên nhân thực sự là quên đăng ký bean hoặc đặt sai prefix. Đó là vấn đề wiring, không phải giới hạn của `@ConfigurationProperties`.

## 27. Environment.getProperty và Binder.bind khác nhau ra sao?

Có thể đọc một khóa đơn:

~~~java
String host = environment.getProperty("app.client.host");
~~~

hoặc:

~~~java
BindResult<String> result =
        Binder.get(environment)
                .bind("app.client.host", String.class);
~~~

Nhưng hai API có trọng tâm khác:

| Cơ chế | Mục đích chính |
| --- | --- |
| `Environment.getProperty(key)` | Lấy một thuộc tính từ nguồn cấu hình theo quy tắc property resolution. |
| `Environment.getProperty(key, type)` | Lấy một thuộc tính và chuyển kiểu bằng conversion service phù hợp. |
| `Binder.bind(prefix, target)` | Bind theo cấu trúc, relaxed binding, target có kiểu, trả `BindResult`. |
| `@ConfigurationProperties` | Khai báo một nhóm cấu hình thành bean ứng dụng, hỗ trợ binding, validation và DI. |

Với một record có nhiều field, `Binder.bind("app.client", ClientProperties.class)` thường hữu ích hơn việc tự gọi `Environment.getProperty(...)` cho từng khóa rồi tự xây object.

Nếu chỉ cần một giá trị String, `Environment.getProperty(...)` có thể là công cụ đơn giản nhất.

### BindResult không chỉ là một phép kiểm tra khóa “có tồn tại”

Với object và collection, Binder còn phải thực hiện binding trên cấu trúc mục tiêu. Do đó, không nên suy luận hoàn toàn từ `environment.containsProperty("prefix")`.

Ví dụ namespace:

~~~properties
app.client.host=api.example.test
app.client.timeout=5s
~~~

Không nhất thiết có một **khóa literal** tên `app.client`. Binder vẫn có thể bind object `ClientProperties` từ các khóa con. Kiểm tra trực tiếp `containsProperty("app.client")` không phải một phép thay thế tương đương cho `binder.bind("app.client", target).isBound()`.

## 28. Thứ tự PropertySource và trường hợp không có dữ liệu

Spring Boot hợp nhất các nguồn cấu hình theo độ ưu tiên. Một nguồn không chứa khóa không có nghĩa khóa vắng mặt trong toàn bộ môi trường.

Ví dụ:

~~~yaml
# application.yaml
feature:
  export:
    enabled: false
~~~

Nhưng khi chạy:

~~~bash
java -jar app.jar --feature.export.enabled=true
~~~

Binder có thể lấy giá trị `true` từ CLI vì nguồn dòng lệnh thường có ưu tiên cao hơn Config Data.

Nếu bỏ khóa `feature.export.enabled` khỏi một file YAML, một biến môi trường hoặc system property vẫn có thể cung cấp nó. Vì vậy, khi `BindResult.isBound()` là true dù tệp hiện tại không có khóa, hãy kiểm tra:

- Tệp config theo profile.
- Config Data ở ngoài JAR.
- Biến môi trường của tiến trình.
- Java System properties.
- Command-line properties.
- Nguồn do ứng dụng hoặc test thêm vào.

Tương tự, một khóa trong YAML có thể bị nguồn ưu tiên cao hơn ghi đè bằng giá trị khác, kể cả giá trị rỗng; quy tắc chuyển đổi phụ thuộc kiểu đích.

**Không nên chẩn đoán “unbound” chỉ bằng cách mở một tệp và tìm không thấy prefix.** Binder làm việc với tập nguồn cấu hình có hiệu lực, không phải một file đơn lẻ.

## 29. Gắn Binder với một tập nguồn có kiểm soát trong unit test

Để kiểm thử mà không cần khởi động toàn bộ Spring Boot, có thể tạo Binder trực tiếp từ `MapConfigurationPropertySource`.

### 29.1. Có dữ liệu

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of(
                "client.timeout", "12s"));

Binder binder = new Binder(source);

BindResult<Duration> result =
        binder.bind("client.timeout", Duration.class);

System.out.println(result.isBound()); // true
System.out.println(result.get());     // PT12S
~~~

Ở đây `MapConfigurationPropertySource` cung cấp một tập thuộc tính được kiểm soát, không phụ thuộc vào biến môi trường của máy chạy test.

### 29.2. Không có dữ liệu

~~~java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of());

Binder binder = new Binder(source);

BindResult<Duration> result =
        binder.bind("client.timeout", Duration.class);

System.out.println(result.isBound()); // false
~~~

Có thể lấy fallback:

~~~java
Duration timeout =
        result.orElse(Duration.ofSeconds(3));
~~~

Kết quả là 3 giây.

### 29.3. Dữ liệu có nhưng sai kiểu

~~~java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of(
                "client.timeout", "invalid-duration"));

Binder binder = new Binder(source);

binder.bind("client.timeout", Duration.class);
~~~

Lời gọi có thể ném `BindException` vì không thể chuyển dữ liệu sang `Duration`. Đây là test quan trọng để xác nhận ứng dụng không lẫn lỗi cấu hình với trường hợp không khai báo.

## 30. Kiểm thử JUnit: phân biệt kết quả và ngoại lệ

Một lớp test mẫu:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.Map;
import java.util.NoSuchElementException;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class BinderResultTest {

    @Test
    void absentPropertyIsUnbound() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(Map.of()));

        BindResult<Duration> result =
                binder.bind("client.timeout", Duration.class);

        assertFalse(result.isBound());
        assertEquals(Duration.ofSeconds(5),
                result.orElse(Duration.ofSeconds(5)));

        assertThrows(NoSuchElementException.class, result::get);
    }

    @Test
    void validPropertyIsBound() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of("client.timeout", "12s")));

        BindResult<Duration> result =
                binder.bind("client.timeout", Duration.class);

        assertTrue(result.isBound());
        assertEquals(Duration.ofSeconds(12), result.get());
    }

    @Test
    void invalidPropertyDoesNotUseFallback() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of("client.timeout", "not-a-duration")));

        assertThrows(BindException.class, () ->
                binder.bind("client.timeout", Duration.class)
                        .orElse(Duration.ofSeconds(5)));
    }
}
~~~

Ba test xác nhận ba nhánh độc lập:

- Thiếu khóa → unbound.
- Giá trị hợp lệ → bound.
- Giá trị sai kiểu → lỗi bind.

Nếu test cuối dùng một loại exception bọc khác trong ngữ cảnh cụ thể, hãy kiểm tra cause tương ứng với `BindException`; phần quan trọng là phải phân biệt lỗi với fallback.

### Test false không phải unbound

~~~java
@Test
void falseIsStillBound() {
    Binder binder = new Binder(
            new MapConfigurationPropertySource(
                    Map.of("feature.enabled", "false")));

    BindResult<Boolean> result =
            binder.bind("feature.enabled", Boolean.class);

    assertTrue(result.isBound());
    assertFalse(result.get());
}
~~~

### Test supplier chỉ chạy khi cần

~~~java
@Test
void fallbackSupplierIsLazy() {
    Binder binder = new Binder(
            new MapConfigurationPropertySource(
                    Map.of("client.timeout", "12s")));

    Duration timeout = binder
            .bind("client.timeout", Duration.class)
            .orElseGet(() -> {
                throw new AssertionError(
                        "Không được gọi supplier khi bound");
            });

    assertEquals(Duration.ofSeconds(12), timeout);
}
~~~

Test này minh họa trực tiếp đặc tính lazy của `orElseGet`.

## 31. Kiểm tra object đã bind một phần

Một test về prefix:

~~~java
public record ClientOptions(
        String host,
        Integer port) {
}
~~~

Nguồn:

~~~properties
client.host=api.example.test
~~~

Mã:

~~~java
Binder binder = new Binder(
        new MapConfigurationPropertySource(Map.of(
                "client.host", "api.example.test")));

BindResult<ClientOptions> result =
        binder.bind("client", ClientOptions.class);
~~~

Khi Binder tạo được object từ dữ liệu có mặt, `result.isBound()` có thể là true nhưng `result.get().port()` chưa có giá trị.

Do đó, test nên xác minh cả:

~~~java
assertTrue(result.isBound());
assertEquals("api.example.test", result.get().host());
~~~

và chính sách với thành viên còn thiếu:

~~~java
if (result.get().port() == null) {
    // Thiếu cấu hình cổng: báo lỗi hoặc dùng default theo thiết kế.
}
~~~

Không thể kiểm tra sự đầy đủ của object chỉ bằng `isBound()`.

### Dùng wrapper thay primitive khi cần phân biệt thiếu

Nếu kiểu record là:

~~~java
public record ClientOptions(String host, int port) {
}
~~~

một thành viên `int` thiếu có thể được gắn giá trị mặc định 0 theo cách tạo object. Điều này khiến bạn khó phân biệt “người vận hành cố ý đặt 0” với “không cung cấp port”.

Nếu sự phân biệt ấy quan trọng, dùng `Integer`, `@NotNull` hoặc validation rõ ràng. Đừng dựa vào giá trị mặc định primitive như một dấu hiệu tồn tại của khóa.

## 32. BindResult và Optional trong cấu hình: chọn cách nào?

Có thể nghĩ đến:

~~~java
Optional<String> endpoint;
~~~

trong một class `@ConfigurationProperties` để diễn tả giá trị tùy chọn.

Tuy nhiên, tài liệu Spring Boot khuyến nghị **không sử dụng `Optional` làm field của `@ConfigurationProperties`**. Với dữ liệu thiếu, cách binder xử lý có thể không giống trực giác “luôn tạo `Optional.empty()`”.

Với một class cấu hình, có thể dùng:

- `String` hoặc kiểu wrapper nullable có validation tùy yêu cầu.
- `@DefaultValue` ở constructor binding khi có giá trị mặc định hợp lệ.
- `@NotNull` cho thuộc tính bắt buộc.
- `@Valid` để kiểm tra object lồng nhau.

Với một lời gọi Binder **thủ công**, `BindResult<T>` chính là abstraction phù hợp để biết có kết quả hay không.

Nếu một API bên ngoài thật sự yêu cầu `Optional<T>`, bạn có thể chuyển rõ ràng:

~~~java
BindResult<String> result =
        binder.bind("app.label", String.class);

Optional<String> label =
        result.isBound()
                ? Optional.of(result.get())
                : Optional.empty();
~~~

Ở đoạn này cần import `java.util.Optional`. Đây là phép chuyển trạng thái của **một lời gọi Binder**, không phải khuyến nghị gắn `Optional` trực tiếp làm thành viên `@ConfigurationProperties`.

## 33. An toàn khi chọn giá trị mặc định

Một default không phải lúc nào cũng là lựa chọn an toàn.

**Nên dùng fallback** cho:

- Số lượng retry thử nghiệm với mức nhỏ hợp lý.
- Tên hiển thị tùy chọn.
- Tắt một tính năng phụ khi chưa được cấu hình.
- Thư mục local minh họa không ảnh hưởng hệ thống production.
- Timeout có giá trị đã được phê duyệt như một chính sách.

**Cẩn thận với fallback** cho:

- Endpoint thanh toán hoặc dịch vụ production.
- Mật khẩu, token, khóa ký.
- Cấu hình TLS hoặc kiểm tra chứng chỉ.
- Đích lưu trữ dữ liệu nhạy cảm.
- Mã vùng/đối tác quyết định nơi dữ liệu được chuyển đến.

Ví dụ nguy hiểm:

~~~java
URI endpoint = binder.bind(
        "payments.endpoint", URI.class)
        .orElse(URI.create("http://localhost:8080"));
~~~

Nếu production quên cấu hình, ứng dụng có thể gọi nhầm địa chỉ local. Với cấu hình bắt buộc, `orElseThrow` kèm thông báo rõ ràng thường phù hợp hơn.

### Không để fallback che lỗi vận hành

`orElse(default)` là quyết định chỉ áp dụng cho unbound. Nếu cấu hình sai định dạng, hãy giữ lỗi hoặc chuyển thành một exception giàu ngữ cảnh, thay vì bắt mọi exception và thay bằng default.

Một policy tốt nên được ghi trong tài liệu vận hành: khóa nào optional, khóa nào required, default là gì, và việc thiếu dữ liệu có ý nghĩa gì.

## 34. Bài tập thực hành

### Bài 1 — dự đoán trạng thái

Nguồn:

~~~properties
app.name=demo
~~~

Mã:

~~~java
BindResult<String> a =
        binder.bind("app.name", String.class);

BindResult<String> b =
        binder.bind("app.region", String.class);
~~~

**Đáp án:** `a.isBound()` là true, `b.isBound()` thường là false nếu không có nguồn khác cung cấp `app.region`.

### Bài 2 — false là dữ liệu có mặt

~~~properties
feature.enabled=false
~~~

Mã:

~~~java
BindResult<Boolean> result =
        binder.bind("feature.enabled", Boolean.class);
~~~

**Đáp án:** `isBound()` là true, `get()` là false.

### Bài 3 — fallback đơn giản

Không có `app.timeout`:

~~~java
Duration value =
        binder.bind("app.timeout", Duration.class)
                .orElse(Duration.ofSeconds(10));
~~~

**Đáp án:** 10 giây.

### Bài 4 — fallback không áp dụng khi bound

~~~properties
app.timeout=0ms
~~~

Mã:

~~~java
Duration value =
        binder.bind("app.timeout", Duration.class)
                .orElse(Duration.ofSeconds(10));
~~~

**Đáp án:** `Duration.ZERO`, không phải 10 giây. Nếu 0 không hợp lệ, phải validation riêng.

### Bài 5 — fallback không cứu sai kiểu

~~~properties
app.timeout=bad-duration
~~~

Mã dùng `bind(..., Duration.class).orElse(Duration.ofSeconds(10))`.

**Đáp án:** Binder có thể ném lỗi chuyển kiểu, không phải tự dùng 10 giây.

### Bài 6 — orElse và orElseGet

Hai đoạn:

~~~java
result.orElse(makeDefaults());
result.orElseGet(this::makeDefaults);
~~~

Nếu result bound, cái nào vẫn gọi `makeDefaults()`?

**Đáp án:** `orElse(makeDefaults())` vì đối số Java được tính trước. `orElseGet(...)` không gọi supplier khi bound.

### Bài 7 — cấu hình nhóm thiếu hoàn toàn

Không có thuộc tính `feature.export.*`. Muốn tắt tính năng một cách an toàn, nên dùng `result.isBound()` để quyết định bỏ qua hoặc `orElseGet(...)` tạo object có `enabled=false` theo chính sách.

### Bài 8 — bind một phần

Nguồn:

~~~properties
feature.export.enabled=true
~~~

Kiểu:

~~~java
public record ExportOptions(
        boolean enabled,
        String outputDirectory,
        Duration timeout) {
}
~~~

**Câu hỏi:** Nếu result bound, liệu `orElseGet(...)` có tự điền `outputDirectory` và `timeout`?

**Đáp án:** Không. `orElseGet` chỉ dùng fallback khi kết quả toàn bộ unbound. Giá trị thiếu bên trong object cần xử lý qua `@DefaultValue`, field initializer hoặc validation theo thiết kế.

### Bài 9 — get() khi unbound

Không có `app.name`:

~~~java
binder.bind("app.name", String.class).get();
~~~

**Đáp án:** Có thể ném `NoSuchElementException`. Dùng `orElseThrow` nếu muốn thông báo lỗi phù hợp.

### Bài 10 — bind collection có kiểu

Để bind `List<String>` ở `app.backends`, chọn:

~~~java
binder.bind("app.backends", Bindable.listOf(String.class));
~~~

Không nên chỉ dùng `List.class` nếu muốn bảo toàn kiểu phần tử.

### Bài 11 — kiểm tra namespace

Nguồn:

~~~properties
app.client.host=api.example.test
app.client.timeout=5s
~~~

Không có khóa literal `app.client`. Hỏi có thể bind class `ClientProperties` bằng prefix `app.client` không?

**Đáp án:** Có thể, vì Binder tìm các member dưới namespace. `environment.containsProperty("app.client")` không phải phép kiểm tra tương đương.

### Bài 12 — ba trạng thái của input

Hãy thiết kế một test cho:

1. Không có `app.max-attempts`.
2. Có `app.max-attempts=0`.
3. Có `app.max-attempts=abc`.

**Đáp án mong đợi:** thứ nhất unbound; thứ hai bound với 0 nếu kiểu là `Integer`; thứ ba lỗi conversion. Ba nhánh cần được xử lý riêng.

### Bài 13 — chính sách required

Với `payment.endpoint` bắt buộc và không có mặc định an toàn:

~~~java
binder.bind("payment.endpoint", URI.class)
        .orElseThrow(() ->
                new IllegalStateException(
                        "Thiếu payment.endpoint"));
~~~

Dùng `orElseThrow` thay vì một URL mặc định tùy tiện.

### Bài 14 — dùng map()

~~~properties
jobs.retry-limit=5
~~~

~~~java
String label =
        binder.bind("jobs.retry-limit", Integer.class)
                .map(x -> "Retry: " + x)
                .orElse("Không có cấu hình");
~~~

**Đáp án:** `Retry: 5`.

### Bài 15 — đặt một handler có hợp lý không?

Một nhóm cấu hình không có dữ liệu và bạn chỉ muốn default 10 giây.

**Đáp án:** Không cần tự viết `BindHandler`. Dùng `binder.bind(...).orElse(Duration.ofSeconds(10))` là đủ và rõ ràng.

## 35. Quy trình kiểm tra khi BindResult không như mong đợi

Khi `isBound()` là false dù bạn nghĩ đã cấu hình, hãy đi theo thứ tự:

1. **Tên khóa/prefix**: có đúng dạng canonical và đúng đường dẫn member không?
2. **Nguồn dữ liệu**: giá trị ở `application.yaml`, file theo profile, biến môi trường hay CLI?
3. **Profile hoạt động**: tài liệu cấu hình chứa khóa có thật sự được nạp không?
4. **Tên biến môi trường**: đã tuân theo quy tắc relaxed binding của Spring Boot chưa?
5. **Mục tiêu bind**: kiểu đích có thể chuyển từ nguồn không? Object có member khớp không?
6. **Trạng thái toàn nhóm**: hoàn toàn không có thuộc tính, hay chỉ thiếu vài member?
7. **Binding exception**: có lỗi trước khi trả kết quả không?
8. **Fallback**: dùng `orElse`, `orElseGet` hay `orElseThrow` có đúng chính sách không?
9. **Validation**: nếu object bound, nó có đủ trường và đúng phạm vi nghiệp vụ không?
10. **Thời điểm đọc**: `Environment` và binder có được tạo trong đúng vòng đời của Spring Boot không?

Một số lỗi phổ biến và cách xử lý:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `isBound=false`, không có prefix | Cấu hình tùy chọn thật sự vắng | Default/bỏ qua/báo thiếu. |
| `get()` ném `NoSuchElementException` | Gọi get khi unbound | Kiểm tra hoặc dùng `orElseThrow`. |
| Có một field nhưng field khác null | Object bind một phần | Default cấp member/validation. |
| Boolean false nhưng bị coi là “không cấu hình” | Nhầm giá trị với trạng thái | Dùng `isBound()`. |
| `orElse` không cứu dữ liệu sai kiểu | Binder ném lỗi trước khi có `BindResult` | Sửa dữ liệu hoặc xử lý `BindException`. |
| `orElseGet` không được gọi | Kết quả đã bound | Đây là hành vi đúng; kiểm tra object. |
| `bindOrCreate` lỗi tạo instance | Kiểu không thể khởi tạo theo cách được hỗ trợ | Chọn kiểu/factory/fallback phù hợp. |
| Có YAML nhưng giá trị bị CLI ghi đè | Thứ tự `PropertySource` | Kiểm tra nguồn ưu tiên. |
| List rỗng khác mong đợi | Nguồn list và quy tắc binding | Kiểm tra dữ liệu thực và thứ tự nguồn. |

## 36. Bảng quyết định nhanh

| Mục tiêu | API khuyến nghị |
| --- | --- |
| Đọc một scalar có thể không có | `binder.bind(name, Type.class)` + `BindResult`. |
| Kiểm tra trạng thái vắng mặt | `isBound()`. |
| Yêu cầu có giá trị, nếu không báo lỗi | `orElseThrow(...)`. |
| Có default đơn giản | `orElse(defaultValue)`. |
| Có default tính toán khi cần | `orElseGet(supplier)`. |
| Thực hiện một hành động khi đã bind | `ifBound(consumer)`. |
| Biến đổi kết quả mà giữ logic unbound | `map(function)`. |
| Muốn luôn cố có instance từ một kiểu có thể tạo | `bindOrCreate(...)`. |
| Bind list/map có generic element types | `Bindable.listOf(...)` / `Bindable.mapOf(...)`. |
| Cấu hình cố định, nhiều service dùng chung | `@ConfigurationProperties` + đăng ký bean. |
| Cần kiểm tra object đủ trường và đúng chính sách | Validation riêng, không chỉ `isBound()`. |
| Dữ liệu sai kiểu | Điều tra/báo lỗi binding, không âm thầm fallback. |

## 37. Ghi nhớ cuối bài

`BindResult<T>` giúp lập trình viên xử lý rõ ràng **trường hợp bind có kết quả** và **trường hợp không có dữ liệu để bind**. Những phương thức `isBound`, `get`, `orElse`, `orElseGet`, `orElseThrow`, `ifBound` và `map` tương ứng với các chính sách đọc, dùng default, yêu cầu bắt buộc hoặc chỉ hành động khi có cấu hình.

Tuy nhiên, cần luôn phân biệt **ba trục**:

1. **Có nguồn dữ liệu hay không?** → `BindResult` biểu diễn bound/unbound.
2. **Dữ liệu có thể chuyển thành kiểu đích không?** → Binder và conversion xử lý; lỗi có thể ném exception.
3. **Object đã bind có đầy đủ và hợp lệ cho nghiệp vụ không?** → default cấp member, validation và logic nghiệp vụ xử lý.

Một object chỉ cần một vài member có thể đã được coi là bound; vì vậy `orElseGet(...)` không tự điền những field còn thiếu. Một giá trị `false` hoặc `0` vẫn có thể là dữ liệu bound. Một chuỗi sai kiểu không tự chuyển thành “không có dữ liệu” chỉ vì bạn đặt fallback.

Khi cần cấu hình không bắt buộc, lựa chọn `orElse` hoặc `orElseGet` với mặc định an toàn. Khi cấu hình là bắt buộc, dùng `orElseThrow` với thông báo cụ thể. Khi muốn một object được tạo kể cả không có dữ liệu, cân nhắc `bindOrCreate` nhưng phải bảo đảm kiểu có thể tạo và mặc định của nó hợp lệ.

Đó là cách dùng `Binder` ở mức nâng cao mà vẫn giữ hệ thống dễ chẩn đoán, không che mất lỗi triển khai và không tạo hành vi bất ngờ giữa các môi trường.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Binder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html).
- [Spring Boot 3.x — BindResult API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindResult.html).
- [Spring Boot 3.3 — Bindable API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Bindable.html).
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 — MapConfigurationPropertySource API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/source/MapConfigurationPropertySource.html).