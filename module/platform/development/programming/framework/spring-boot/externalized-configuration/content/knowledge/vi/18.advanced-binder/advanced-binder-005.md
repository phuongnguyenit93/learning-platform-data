# Khởi tạo đối tượng bằng bindOrCreate và quản lý giá trị mặc định

Trong Spring Boot Externalized Configuration, `Binder` là API cho phép lấy dữ liệu từ `Environment` rồi ánh xạ vào một đối tượng Java có kiểu. Khi chỉ cần lấy một nhóm cấu hình theo yêu cầu, thay vì đăng ký mọi nhóm thành Spring bean bằng `@ConfigurationProperties`, ta có thể gọi trực tiếp:

~~~java
CacheOptions options = Binder.get(environment)
    .bindOrCreate("app.cache", CacheOptions.class);
~~~

Từ khóa quan trọng ở đây là **`bindOrCreate`**: yêu cầu Binder thử liên kết dữ liệu cấu hình với kiểu đích; nếu không có dữ liệu để bind, nó **cố tạo một instance mới** theo khả năng khởi tạo của target. Hành vi này khác với `bind`, vốn trả về `BindResult<T>` có thể ở trạng thái **không có kết quả**.

Tuy vậy, **`bindOrCreate` không có nghĩa “mọi lỗi cấu hình đều dùng giá trị mặc định”**. Nếu một key có giá trị sai kiểu, constructor không phù hợp hoặc quá trình binding thất bại, đó vẫn có thể là lỗi. Giá trị mặc định cần được thiết kế có chủ đích trong JavaBean, record, constructor hoặc logic fallback, không phải để framework tự đoán.

Bài này giải thích API, phân biệt tình huống *thiếu cả nhóm*, *thiếu một key*, *value rỗng* và *value sai*, thiết kế default cho JavaBean mutable và record bất biến, làm việc với nested objects/list/map, cách test theo tình huống, chẩn đoán exception và các nguyên tắc để không vô tình che lỗi triển khai. Ví dụ theo Spring Boot 3.x, Java 17+.

## 1. Binder giải quyết bài toán gì?

Giả sử cấu hình:

~~~yaml
# application.yml
app:
  cache:
    enabled: true
    ttl: 15m
    maximum-entries: 500
~~~

Nhóm key:

~~~text
app.cache.enabled
app.cache.ttl
app.cache.maximum-entries
~~~

có thể được Binder chuyển thành object:

~~~java
public class CacheOptions {
    private boolean enabled = true;
    private Duration ttl = Duration.ofMinutes(5);
    private int maximumEntries = 100;

    // getter/setter...
}
~~~

Khi đọc `app.cache`:

- `enabled` nhận `true`.
- `ttl` nhận `Duration.ofMinutes(15)`.
- `maximumEntries` nhận `500`.

Đây là typed binding: Binder không đơn thuần trả các chuỗi, mà ánh xạ tên thuộc tính, gọi conversion thích hợp rồi xây hoặc cập nhật object.

Một sơ đồ tổng quát:

~~~text
application.yml / application.properties
       |
profiles / config import / environment / -D / --key=value
       |
       v
Spring Environment
       |
       v
Binder.get(environment)
       |
       +-- bind("app.cache", CacheOptions.class)
       |       -> BindResult<CacheOptions>
       |       -> có thể không bound
       |
       +-- bindOrCreate("app.cache", CacheOptions.class)
               -> CacheOptions, nếu bind hoặc tạo được
               -> có thể lỗi nếu bind/khởi tạo không thành công
~~~

Cơ chế này dùng chung nguyên tắc đặt tên và conversion của Spring Boot Configuration Properties, nhưng **gọi Binder trực tiếp không tự động đăng ký object trả về thành một Spring bean**.

## 2. Ba API cần phân biệt

Một cách sử dụng phổ biến:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public final class CacheSettingsLoader {
    private final Environment environment;

    public CacheSettingsLoader(Environment environment) {
        this.environment = environment;
    }

    public CacheOptions load() {
        Binder binder = Binder.get(environment);
        return binder.bindOrCreate("app.cache", CacheOptions.class);
    }
}
~~~

So sánh các lời gọi:

~~~java
Binder binder = Binder.get(environment);

// A. Trả về một BindResult; có thể không có kết quả bind.
BindResult<CacheOptions> result =
    binder.bind("app.cache", CacheOptions.class);

// B. Cố bind, nếu không có dữ liệu thì cố tạo instance.
CacheOptions options =
    binder.bindOrCreate("app.cache", CacheOptions.class);

// C. Fallback do caller tự cấp nếu bind không có kết quả.
CacheOptions fallback =
    binder.bind("app.cache", CacheOptions.class)
          .orElse(new CacheOptions());

// D. Fallback lazy, chỉ tạo khi bind không có kết quả.
CacheOptions lazyFallback =
    binder.bind("app.cache", CacheOptions.class)
          .orElseGet(CacheOptions::new);
~~~

Để dùng ví dụ, thêm imports:

~~~java
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
~~~

**Khác nhau về hợp đồng:**

| API | Kiểu trả về | Khi không có dữ liệu bind | Khi có value không chuyển kiểu được |
| --- | --- | --- | --- |
| `bind(name, Type.class)` | `BindResult<Type>` | Kết quả không bound | Thường ném lỗi binding |
| `bindOrCreate(name, Type.class)` | `Type` | Cố tạo một instance mới | Không mặc định bỏ qua lỗi |
| `bind(...).orElse(defaultObj)` | `Type` | Trả object fallback đã cung cấp | Không mặc định bỏ qua lỗi |
| `bind(...).orElseGet(supplier)` | `Type` | Gọi supplier fallback khi cần | Không mặc định bỏ qua lỗi |

Các mẫu trên giả định target có cấu trúc và khả năng khởi tạo phù hợp với Binder. `bindOrCreate` **không hứa tạo được mọi class Java**, chẳng hạn type chỉ có constructor nhận dependency tùy ý mà Binder không biết ánh xạ.

## 3. Ví dụ JavaBean đầy đủ: giữ default khi thiếu key

Một JavaBean mutable có thể khai báo default ngay trong field initializer.

~~~java
package com.example.demo.config;

import java.time.Duration;

public class CacheOptions {
    private boolean enabled = true;
    private Duration ttl = Duration.ofMinutes(5);
    private int maximumEntries = 100;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getTtl() {
        return ttl;
    }

    public void setTtl(Duration ttl) {
        this.ttl = ttl;
    }

    public int getMaximumEntries() {
        return maximumEntries;
    }

    public void setMaximumEntries(int maximumEntries) {
        this.maximumEntries = maximumEntries;
    }
}
~~~

Class trên có constructor không tham số ngầm định, getter/setter phù hợp, nên là target điển hình cho JavaBean binding.

Cấu hình:

~~~properties
app.cache.ttl=30s
app.cache.maximum-entries=250
~~~

Sử dụng:

~~~java
CacheOptions options =
    Binder.get(environment)
          .bindOrCreate("app.cache", CacheOptions.class);
~~~

Với trường hợp minh họa này:

| Thuộc tính | Default trong Java | Value trong config | Kết quả |
| --- | --- | --- | --- |
| `enabled` | `true` | Không khai báo | Giữ `true` |
| `ttl` | 5 phút | `30s` | 30 giây |
| `maximumEntries` | `100` | `250` | 250 |

Tác dụng của default ở đây đến từ **field initializer của JavaBean**, không phải một quy tắc đặc biệt tự động áp dụng cho mọi loại Java.

Nếu bỏ toàn bộ `app.cache.*`, `bindOrCreate` cố tạo một `CacheOptions` mới. Khi tạo được, nó nhận các default của Java:

~~~text
enabled = true
ttl = PT5M
maximumEntries = 100
~~~

Đây là tình huống mà `bindOrCreate` giúp tránh việc caller phải tự viết `if (!result.isBound()) new CacheOptions()` ở nhiều nơi.

## 4. Thiếu cả prefix khác với thiếu một thuộc tính

Xem ba cấu hình.

**A. Không có bất kỳ key nào dưới prefix:**

~~~properties
spring.application.name=example
~~~

Lúc này:

~~~java
BindResult<CacheOptions> result =
    binder.bind("app.cache", CacheOptions.class);

boolean bound = result.isBound(); // Thông thường false.
~~~

Nếu target có thể khởi tạo, `bindOrCreate` có thể trả một object chứa default JavaBean.

**B. Có một key:**

~~~properties
app.cache.ttl=30s
~~~

Lúc này Binder có dữ liệu để bind. Với class mutable ở phần trên, nó điền `ttl`, còn các field không được khai báo giữ default.

**C. Có key với value sai:**

~~~properties
app.cache.maximum-entries=many
~~~

Đây không phải “thiếu cấu hình”. `many` không chuyển được thành `int`. Cả `bind` lẫn `bindOrCreate` có thể thất bại khi conversion được thực thi. **Không nên dùng `bindOrCreate` như cách tự động thay `many` bằng `100`**.

Bảng quyết định:

| Tình huống | Cách diễn giải | Hành vi nên thiết kế |
| --- | --- | --- |
| Cả prefix không được cung cấp | Cấu hình tùy chọn có thể vắng | Tạo default nếu có ý nghĩa |
| Prefix có, một key không được cung cấp | Partial override | Giữ default của field hoặc constructor |
| Key có value rỗng | Dữ liệu đã được cung cấp, nhưng rỗng | Xét kiểu target và validation |
| Key có value không convert được | Dữ liệu không hợp kiểu | Báo lỗi, sửa nguồn |
| Value đúng kiểu nhưng sai yêu cầu nghiệp vụ | Vi phạm ràng buộc | Validate/fail fast |
| Target không thể khởi tạo | Vấn đề constructor/accessor/binding | Sửa model hoặc API, không che lỗi |

## 5. bind và BindResult: khi nào cần giữ trạng thái “không có dữ liệu”?

Có những ứng dụng muốn biết **có cung cấp nhóm cấu hình đó hay không**, thay vì tạo default âm thầm.

Ví dụ:

~~~java
Binder binder = Binder.get(environment);

BindResult<CacheOptions> result =
    binder.bind("app.cache", CacheOptions.class);

if (result.isBound()) {
    CacheOptions config = result.get();
    // Cấu hình được cung cấp và bind thành công.
} else {
    // Không có kết quả bound: chọn hành vi của ứng dụng.
}
~~~

`BindResult.get()` chỉ nên gọi khi đã bound, nếu không có thể ném exception cho trường hợp không có kết quả. Một lựa chọn gọn hơn là:

~~~java
CacheOptions config =
    result.orElseGet(CacheOptions::new);
~~~

Sự khác nhau giữa `orElse` và `orElseGet` cũng quan trọng:

~~~java
CacheOptions eager =
    result.orElse(buildDefaultOptions());

CacheOptions lazy =
    result.orElseGet(() -> buildDefaultOptions());
~~~

Trong Java, biểu thức truyền cho `orElse` được tính trước khi method được gọi. Do đó `buildDefaultOptions()` có thể chạy ngay dù result đã bound. `orElseGet` nhận supplier và chỉ cần gọi nó khi thiếu kết quả.

Nếu fallback là `new CacheOptions()` rẻ và thuần, sự khác biệt có thể nhỏ. Nếu xây fallback tốn tài nguyên, cần phân biệt rõ. Dù vậy, không nên cho fallback thực hiện I/O phức tạp không cần thiết trong giai đoạn khởi động.

## 6. bindOrCreate không phải giống Optional.orElse

Hai cách sau có thể dẫn đến object với default giống nhau, nhưng không hoàn toàn là cùng một hợp đồng:

~~~java
CacheOptions a =
    binder.bindOrCreate("app.cache", CacheOptions.class);

CacheOptions b =
    binder.bind("app.cache", CacheOptions.class)
          .orElseGet(CacheOptions::new);
~~~

`bindOrCreate` yêu cầu **Binder** bind hoặc tạo target bằng cơ chế phù hợp với `Bindable` và kiểu đích. `orElseGet` yêu cầu **caller** cung cấp một fallback object khi `BindResult` không có kết quả.

Ưu điểm của `orElseGet` là bạn kiểm soát chính xác cách tạo default:

~~~java
CacheOptions config =
    binder.bind("app.cache", CacheOptions.class)
          .orElseGet(() -> CacheOptions.forDevelopment());
~~~

Ví dụ này giả định class có một factory method `forDevelopment()` do ứng dụng định nghĩa. Nếu quy tắc fallback phụ thuộc môi trường, cần thể hiện logic đó rõ, có test, không che lỗi input sai.

Ưu điểm của `bindOrCreate` là không cần lặp lại factory hoặc fallback nếu chính target type đã có khả năng tự khởi tạo an toàn và chứa default phù hợp.

### Một nguyên tắc chọn

- Cần một đối tượng mặc định cùng kiểu và Binder có thể khởi tạo? Dùng `bindOrCreate`.
- Cần giữ thông tin group có được cấp hay không? Dùng `bind` và `isBound()`.
- Cần factory fallback đặc thù hoặc lifecycle riêng? Dùng `bind(...).orElseGet(...)`.
- Cấu hình bắt buộc phải có? Dùng `bind` kèm chính sách lỗi rõ ràng hoặc `@ConfigurationProperties` và validation, đừng mặc định tạo object trống.

## 7. BindResult.orElseThrow cho cấu hình bắt buộc

Một cấu hình kết nối đến hệ thống thanh toán hoặc lưu trữ có thể là **bắt buộc**. Việc tạo default giả tạo bằng `bindOrCreate` có thể làm lỗi bị phát hiện quá muộn.

Ví dụ:

~~~java
import java.net.URI;
import org.springframework.boot.context.properties.bind.Binder;

public record PaymentOptions(
    URI endpoint,
    String merchantId
) {}

PaymentOptions payment =
    Binder.get(environment)
          .bind("app.payment", PaymentOptions.class)
          .orElseThrow(() -> new IllegalStateException(
              "Missing required app.payment configuration"
          ));
~~~

Ở đây policy của ứng dụng là: nếu không có kết quả bind cho toàn nhóm, không chạy với object tự tạo. `orElseThrow` chỉ giải quyết trạng thái **không có kết quả**; nếu value có nhưng conversion/binding thất bại, lỗi của Binder vẫn cần được xử lý theo nguyên nhân.

Ngoài việc yêu cầu prefix tồn tại, một nhóm bắt buộc cần xác thực các field như `endpoint` và `merchantId`. `bind("app.payment",...)` có kết quả không chứng minh mọi field con được cấp. Thiết kế validation và kiểm tra ràng buộc riêng khi cần.

## 8. @DefaultValue với record constructor-bound

Với Java `record`, không thể đặt field initializer tùy ý cho từng record component như JavaBean mutable. Spring Boot hỗ trợ `@DefaultValue` trong ngữ cảnh constructor binding.

Ví dụ:

~~~java
package com.example.demo.config;

import java.time.Duration;

import org.springframework.boot.context.properties.bind.DefaultValue;

public record RetryOptions(
    @DefaultValue("3") int maxAttempts,
    @DefaultValue("250ms") Duration backoff,
    @DefaultValue("false") boolean enabled
) {}
~~~

Cấu hình:

~~~properties
app.retry.enabled=true
~~~

Gọi:

~~~java
RetryOptions retry =
    Binder.get(environment)
          .bindOrCreate("app.retry", RetryOptions.class);
~~~

Nếu cơ chế constructor binding và phiên bản Spring Boot phù hợp, Binder có thể cung cấp:

~~~text
maxAttempts = 3
backoff = PT0.25S
enabled = true
~~~

**`@DefaultValue` là một phần của hợp đồng binding**, không phải một annotation Bean Validation. Nó cung cấp giá trị đầu vào khi parameter tương ứng không có cấu hình để bind; chuỗi default vẫn phải chuyển được sang kiểu parameter đích.

Dạng không có `@DefaultValue`:

~~~java
public record RetryOptions(
    int maxAttempts,
    Duration backoff,
    boolean enabled
) {}
~~~

có thể nhận giá trị mặc định nguyên thủy cho `int`/`boolean` và null cho reference type trong những tình huống thiếu value. Đó chưa chắc là policy đúng: retry bằng 0 hay backoff null có thể không phù hợp.

### Chú ý constructor và tên parameter

Record với canonical constructor phù hợp thường được Binder nhận diện tốt trong Spring Boot 3.x. Với class immutable có nhiều constructor hoặc thiếu parameter-name metadata, Binder có thể cần cấu hình/annotation constructor thích hợp. Nếu gặp lỗi, hãy kiểm tra phiên bản Boot, `-parameters` và đường đăng ký trước khi quy lỗi cho `@DefaultValue`.

## 9. Dùng @DefaultValue khi không có cả nhóm cấu hình

Nếu không có `app.retry.*`:

~~~properties
spring.application.name=demo
~~~

Gọi `bind("app.retry", RetryOptions.class)` có thể cho kết quả không bound, bởi không có property nào được tìm thấy để tạo kết quả binding cho prefix.

`bindOrCreate("app.retry", RetryOptions.class)` yêu cầu Binder **tạo object dù không có giá trị cấu hình để bind**. Với record và constructor/default binding phù hợp, object có thể nhận các `@DefaultValue` đã khai báo.

Do đó, hai chức năng kết hợp thành policy:

1. **`bindOrCreate`** xử lý trường hợp thiếu toàn bộ group bằng cách cố tạo instance.
2. **`@DefaultValue`** xử lý default ở từng constructor parameter khi target cần nhận giá trị.

Không nên nhầm rằng `@DefaultValue` trên field đơn lẻ tự làm `bind(...)` biến một prefix hoàn toàn vắng mặt thành kết quả bound trong mọi trường hợp. Nếu yêu cầu luôn có object, chọn API phù hợp và test tình huống prefix vắng.

## 10. Nested record và default cho object con

Đối tượng có cấu trúc lồng nhau thường cần default ở nhiều cấp. Ví dụ:

~~~yaml
app:
  client:
    base-url: https://api.example.test
~~~

Model:

~~~java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.bind.DefaultValue;

public record ClientOptions(
    URI baseUrl,
    @DefaultValue Retry retry
) {
    public record Retry(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("250ms") Duration backoff
    ) {}
}
~~~

Ở đây `@DefaultValue` không có chuỗi trên parameter `retry` là cách dành cho constructor binding để yêu cầu Binder cố tạo nested object khi nhóm nested không được cung cấp, trong điều kiện target có thể được khởi tạo phù hợp. Nested object sau đó nhận default của các component bên trong.

Nếu không thiết kế như vậy, `retry` có thể là null khi không có `app.client.retry.*`. Consumer gọi `options.retry().maxAttempts()` khi đó có nguy cơ lỗi.

Tệp cấu hình có thể ghi đè một phần:

~~~yaml
app:
  client:
    base-url: https://api.example.test
    retry:
      backoff: 1s
~~~

Với default đã khai báo, object có thể nhận `maxAttempts=3` và `backoff=1s`. Đây là lợi ích của việc đặt default ở đúng tầng của model.

### Khi nào không dùng default cho nested object?

Nếu `retry` chỉ được phép tồn tại khi một chế độ nhất định bật, hoặc phải được cấp trọn vẹn khi một trường khác có mặt, tạo nested object mặc định có thể làm mờ lỗi nghiệp vụ. Khi đó nên thiết kế validation/cross-field policy rõ ràng thay vì luôn tạo empty nested object.

## 11. JavaBean nested object và default

Một JavaBean mutable có thể khởi tạo nested field trước:

~~~java
package com.example.demo.config;

import java.time.Duration;

public class ClientSettings {
    private String baseUrl;
    private RetrySettings retry = new RetrySettings();

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public RetrySettings getRetry() {
        return retry;
    }

    public void setRetry(RetrySettings retry) {
        this.retry = retry;
    }

    public static class RetrySettings {
        private int maxAttempts = 3;
        private Duration backoff = Duration.ofMillis(250);

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Duration getBackoff() {
            return backoff;
        }

        public void setBackoff(Duration backoff) {
            this.backoff = backoff;
        }
    }
}
~~~

Nếu config chỉ có `app.client.retry.backoff=1s`, Binder có thể cập nhật nested object `retry` theo cơ chế JavaBean binding; các field không được cung cấp vẫn có default nếu Binder sử dụng instance initialized phù hợp.

Khi dùng JavaBean, cần có getter/setter thích hợp cho những thuộc tính mà Binder phải ghi. Nếu một nested field không thể được truy cập/bind theo cách target cho phép, kết quả có thể khác dự kiến hoặc gây lỗi; không chỉ dựa vào field initializer rồi bỏ qua cấu trúc accessor.

## 12. bindOrCreate và đối tượng đã có sẵn không giống nhau

Một ứng dụng có thể có sẵn instance:

~~~java
CacheOptions existing = new CacheOptions();
existing.setMaximumEntries(800);
~~~

Nếu muốn bind lên chính object đó theo cơ chế phù hợp, Spring Boot Binder có `Bindable.ofInstance(...)`:

~~~java
import org.springframework.boot.context.properties.bind.Bindable;

CacheOptions existing = new CacheOptions();
existing.setMaximumEntries(800);

binder.bind("app.cache", Bindable.ofInstance(existing));
~~~

Với JavaBean mutable, Binder có thể cập nhật các thuộc tính được cấp trong config trên instance có sẵn; các field không bị ghi có thể giữ giá trị ban đầu của instance, tùy binding và tính chất cấu trúc.

Ngược lại:

~~~java
CacheOptions fresh =
    binder.bindOrCreate("app.cache", CacheOptions.class);
~~~

yêu cầu Binder làm việc từ target type, không có ý định giữ state của một `existing` object bạn đã tạo thủ công.

**Lựa chọn theo ý định:**

- Muốn object mới với default trong model: `bindOrCreate(name, Type.class)`.
- Muốn cập nhật một mutable object đã có: `bind(name, Bindable.ofInstance(existing))`.
- Muốn immutable record: dùng constructor binding, không cố mutate instance record.

Nếu object đã có chứa giá trị do user nhập hoặc runtime state, đừng dùng Binder như một công cụ “merge mọi thứ” mà không có policy rõ: binding có thể thay đổi các field đúng tên, và collections có quy tắc riêng.

## 13. Các overload dành cho target phức tạp

`Binder` có thể nhận một `Class<T>` hoặc một `Bindable<T>`. Dạng class tiện cho target cụ thể:

~~~java
CacheOptions options =
    binder.bindOrCreate("app.cache", CacheOptions.class);
~~~

Với kiểu generic, cần giữ thông tin generic type. Ví dụ bind danh sách chuỗi từ một path:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.bind.Bindable;

List<String> regions = binder
    .bind("app.allowed-regions", Bindable.listOf(String.class))
    .orElseGet(List::of);
~~~

`Bindable.listOf(String.class)` giữ rõ item type. Việc dùng `List.class` thuần có thể khiến generic element type không được biểu đạt đầy đủ.

Đối với một nhóm root type có field `List<Server>` hoặc `Map<String,Target>`, thường dễ bảo trì hơn khi tạo một class/record root và bind qua prefix thay vì bind từng collection rời rạc.

Các overload hỗ trợ `BindHandler` tồn tại cho những tình huống cần can thiệp vào vòng đời bind; tuy nhiên bài học này tập trung vào **tạo instance và default**, không cần tự viết handler để sửa mọi trường hợp vắng key.

## 14. Default của collection: đừng giả định list tự cộng phần tử

Giả sử JavaBean có default list:

~~~java
public class WorkerOptions {
    private List<String> servers =
        new ArrayList<>(List.of("localhost:8080"));

    public List<String> getServers() {
        return servers;
    }

    public void setServers(List<String> servers) {
        this.servers = servers;
    }
}
~~~

Và config:

~~~yaml
app:
  worker:
    servers:
      - node-a.example.test:8080
      - node-b.example.test:8080
~~~

Khi Binder bind một list được cung cấp, không nên mặc định kết quả là **default `localhost:8080` cộng thêm hai server**. Trong configuration properties, list có quy tắc binding/thay thế riêng, đặc biệt khi cùng list xuất hiện ở các PropertySource có thứ tự ưu tiên khác nhau.

Trong tình huống muốn danh sách mặc định chỉ khi key thiếu, hãy diễn đạt policy rõ. Nếu config có một list thực tế, coi cấu hình đó là tập hợp cần dùng, đừng tự ghép với default trừ khi nghiệp vụ yêu cầu.

Nếu cần override từng phần tử theo tên, `Map<String, ServerOptions>` có thể là cấu trúc phù hợp hơn `List<ServerOptions>`. Map cũng có quy tắc merge/override riêng; không mặc định rằng mọi object nested đều được deep-merge tùy ý.

## 15. bindOrCreate không thay thế validation

Ví dụ model:

~~~java
import java.time.Duration;

public record WorkerOptions(
    @DefaultValue("4") int concurrency,
    @DefaultValue("2s") Duration pollInterval
) {}
~~~

Tạo instance bằng `bindOrCreate` có thể cho giá trị hợp kiểu. Nhưng nó không tự biết rằng `concurrency` phải từ 1 đến 32 hoặc `pollInterval` phải dương.

Một object có thể nhận:

~~~properties
app.worker.concurrency=-10
app.worker.poll-interval=0s
~~~

Những value này có thể convert thành `int` và `Duration`. Nếu nghiệp vụ cấm, cần validation.

Khi đăng ký `@ConfigurationProperties` thành Spring bean:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
    @Min(1) @Max(32) int concurrency,
    @NotNull Duration pollInterval
) {}
~~~

Spring Boot có thể chạy Bean Validation trong quy trình tạo configuration properties bean khi đã bật dependency/provider thích hợp.

**Khác biệt cần nhớ:** khi dùng **Binder API thủ công**, đừng tự động giả định rằng mọi annotation `@Validated` hay Bean Validation constraint trên target sẽ được thực thi y hệt lifecycle của `@ConfigurationProperties` bean được Boot quản lý. Nếu yêu cầu validate object tạo thủ công, cần cấu hình/call Validator hoặc một `BindHandler` thích hợp, hoặc dùng Spring-managed configuration properties bean.

### Test riêng ràng buộc nghiệp vụ

~~~java
if (options.getMaximumEntries() < 1) {
    throw new IllegalArgumentException(
        "app.cache.maximum-entries must be positive");
}
~~~

Đây là một cách rõ ràng nếu policy cực nhỏ và object được tạo bằng Binder thủ công. Với nhóm lớn, dùng Jakarta Bean Validation và đăng ký/hành vi validate nhất quán sẽ dễ bảo trì hơn.

## 16. Conversion failure không được fallback âm thầm

Cấu hình:

~~~properties
app.cache.maximum-entries=many
~~~

Target:

~~~java
private int maximumEntries = 100;
~~~

Nếu gọi:

~~~java
CacheOptions options =
    binder.bindOrCreate("app.cache", CacheOptions.class);
~~~

Binder không nên được hiểu là sẽ bỏ qua giá trị `many` rồi dùng `100`. Conversion không thành công thường làm binding báo lỗi. `bindOrCreate` **không phải `try/catch` tự động**.

Tương tự:

~~~java
CacheOptions options =
    binder.bind("app.cache", CacheOptions.class)
          .orElseGet(CacheOptions::new);
~~~

`orElseGet` chỉ xử lý **không có BindResult**, không phải mặc nhiên bắt exception từ `bind(...)`. Nếu `bind` ném exception, code không đến nhánh fallback bình thường.

Đây là khác biệt mang tính an toàn: thiếu group tùy chọn có thể được cho phép; **một giá trị đã được deploy nhưng sai kiểu thường cần báo lỗi**. Đừng che lỗi cấu hình production bằng việc bao toàn bộ Binder trong `catch (Exception ignored)` rồi chạy với default.

## 17. Dấu hiệu của ba trường hợp không khởi tạo được

### Trường hợp A — target không có constructor Binder sử dụng được

~~~java
public class UnsupportedOptions {
    private final ExternalClient client;

    public UnsupportedOptions(ExternalClient client) {
        this.client = client;
    }
}
~~~

`ExternalClient` trong ví dụ là dependency nghiệp vụ, không phải property scalar của nhóm cấu hình. Một lời gọi `bindOrCreate("app.unsupported", UnsupportedOptions.class)` không tự biến Binder thành Spring dependency-injection container để tìm bean `ExternalClient`.

**Sửa thiết kế:** tạo typed settings từ key/value, rồi inject/khởi tạo `ExternalClient` ở tầng bean nghiệp vụ.

### Trường hợp B — một field có giá trị sai định dạng

~~~properties
app.retry.backoff=tomorrow
~~~

Record cần `Duration backoff`. Nếu converter không thể parse `tomorrow`, lỗi nằm ở type conversion. Tạo default instance không phải policy đúng cho input sai.

### Trường hợp C — giá trị hợp kiểu nhưng không hợp lệ nghiệp vụ

~~~properties
app.retry.max-attempts=-3
~~~

`-3` thành `int` được; nhưng nếu retry count không được âm, ứng dụng phải có validation rule hoặc constructor/domain validation phù hợp. Binder không tự suy ra constraint nghiệp vụ.

Bảng nhanh:

| Hiện tượng | Nguyên nhân cần kiểm đầu tiên |
| --- | --- |
| Không tạo được target khi prefix thiếu | Constructor/instantiation strategy của target |
| Có prefix nhưng một key không map đúng | Tên key, nested shape, setter hoặc constructor binding |
| Có key đúng nhưng kiểu sai | ConversionService, format value, target type |
| Bind xong nhưng field null/0 | Thiếu key/default chưa được thiết kế |
| Bean đã tạo nhưng bị từ chối | Validation hoặc domain invariant |
| Dữ liệu từ file không thắng | Profile/PropertySource precedence |

## 18. Các giá trị mặc định nên đặt ở đâu?

Có ba cấp policy mặc định phổ biến:

**Cấp kiểu dữ liệu** — default thuộc về chính model và áp dụng mọi nơi:

~~~java
public class WorkerSettings {
    private int concurrency = 4;
    // ...
}
~~~

**Cấp parameter của constructor binding** — default được Binder cung cấp khi constructor parameter không có value:

~~~java
public record WorkerSettings(
    @DefaultValue("4") int concurrency
) {}
~~~

**Cấp caller** — default phụ thuộc ngữ cảnh sử dụng, chỉ áp dụng tại một điểm:

~~~java
WorkerSettings settings =
    binder.bind("app.worker", WorkerSettings.class)
          .orElseGet(WorkerSettings::new);
~~~

Chọn nơi đặt default dựa trên **ai sở hữu chính sách**. Nếu mọi instance của type đều mặc định 4 workers, model phù hợp. Nếu một component development muốn 1 worker còn production bắt buộc khai báo, policy caller hoặc cấu hình theo profile thích hợp hơn.

Không đặt nhiều default khác nhau ở field initializer, annotation và fallback caller mà không có tài liệu precedence. Những mức default ấy dễ gây nhầm khi đổi phương pháp binding.

## 19. Default trong file, trong Java và trong môi trường chạy

Giả sử JavaBean có:

~~~java
private Duration ttl = Duration.ofMinutes(5);
~~~

File:

~~~properties
app.cache.ttl=10m
~~~

Và khi chạy:

~~~bash
java -jar app.jar --app.cache.ttl=30s
~~~

Trong cấu hình Spring Boot thông thường, `--app.cache.ttl=30s` là property source có ưu tiên cao hơn file, nên Binder đọc giá trị hiệu lực `30s`. Default 5 phút trong Java chỉ có tác dụng khi không có value nào cần áp dụng cho field đó.

Có thể hình dung:

~~~text
Java default                = 5m
application.properties      = 10m
command-line value         = 30s
                              |
                              v
                  Binder dùng value hiệu lực
                              |
                              v
                            30s
~~~

Java default **không phải một PropertySource** tham gia tranh thứ tự ưu tiên giống file/env/CLI. Nó nằm trong logic tạo/bind target object. Đây là lý do không nên diễn giải “field initializer có precedence thấp nhất” như một dòng trong danh sách PropertySource của Spring Boot; nó không cùng tầng khái niệm.

## 20. Missing value, empty value, zero và false

Các trường hợp này dễ bị trộn lẫn:

~~~properties
# Không có app.worker.enabled
# Không có app.worker.concurrency
~~~

~~~properties
app.worker.enabled=false
app.worker.concurrency=0
~~~

Hai case không đồng nghĩa. `false` và `0` là giá trị hợp lệ của `boolean` và `int`, không thể dựa vào chúng để chứng minh “key bị thiếu”.

Nếu một property bắt buộc phải hiện diện, cân nhắc:

~~~java
public record WorkerOptions(
    Boolean enabled,
    Integer concurrency
) {}
~~~

Sau đó kiểm tra null hoặc Bean Validation. Wrapper type giúp phân biệt vắng value với những giá trị nguyên thủy theo model; tuy nhiên cách xử lý còn phụ thuộc default/binding thực tế.

Tương tự, một value rỗng:

~~~properties
app.worker.name=
~~~

khác với thiếu key về mặt dữ liệu nguồn, nhưng Binder có thể xử lý chuỗi rỗng khác nhau tùy kiểu target, placeholder và converter. Không coi mọi value rỗng là tín hiệu “dùng @DefaultValue”, đặc biệt với `Duration`, `URI` và số.

### Một quy tắc thiết kế

- **Thiếu key**: quyết định default hoặc bắt buộc.
- **Có `false` hoặc `0`**: coi là dữ liệu hợp lệ về kiểu; validation riêng nếu domain cấm.
- **Có chuỗi rỗng**: xác định có chấp nhận không, thường dùng `@NotBlank` cho String bắt buộc.
- **Sai định dạng**: nêu lỗi conversion.
- **Sai ràng buộc**: nêu lỗi validation.

## 21. Kiểm thử bằng ApplicationContextRunner: không có prefix

`ApplicationContextRunner` giúp tạo một Spring context nhỏ với `Environment` để thử Binder mà không khởi chạy toàn bộ web app.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class CacheDefaultsTest {
    private final ApplicationContextRunner runner =
        new ApplicationContextRunner();

    @Test
    void createsDefaultsWhenPrefixIsAbsent() {
        runner.run(context -> {
            CacheOptions options =
                Binder.get(context.getEnvironment())
                    .bindOrCreate("app.cache", CacheOptions.class);

            assertThat(options.isEnabled()).isTrue();
            assertThat(options.getTtl())
                .isEqualTo(Duration.ofMinutes(5));
            assertThat(options.getMaximumEntries())
                .isEqualTo(100);
        });
    }
}
~~~

Test này kiểm nhánh *không có prefix* và target JavaBean có thể được khởi tạo. Nó không chứng minh tất cả typed settings của ứng dụng đã được scan thành Spring bean, vì object đang được tạo bằng API thủ công.

Khi chạy test, cần dependency Spring Boot Test/JUnit/AssertJ thích hợp, thường được cung cấp qua `spring-boot-starter-test`.

## 22. Kiểm thử: chỉ một key được ghi đè

~~~java
@Test
void partialBindingKeepsJavaBeanDefaults() {
    new ApplicationContextRunner()
        .withPropertyValues("app.cache.ttl=30s")
        .run(context -> {
            CacheOptions options =
                Binder.get(context.getEnvironment())
                    .bindOrCreate("app.cache", CacheOptions.class);

            assertThat(options.getTtl())
                .isEqualTo(Duration.ofSeconds(30));
            assertThat(options.getMaximumEntries())
                .isEqualTo(100);
            assertThat(options.isEnabled()).isTrue();
        });
}
~~~

Ở đây `ttl` lấy từ cấu hình; hai field còn lại giữ default từ JavaBean. Kiểm thử với một key rất hữu ích vì nó phát hiện sự khác nhau giữa **partial binding** và **thiếu toàn nhóm**.

Nếu sau này refactor từ JavaBean sang record, hãy đảm bảo những default trên được chuyển sang `@DefaultValue` hoặc một cơ chế phù hợp; nếu không, các test này có thể thất bại hoặc bean nhận null/0 ngoài dự kiến.

## 23. Kiểm thử: bind khác bindOrCreate khi prefix vắng

~~~java
@Test
void bindCanRemainUnbound() {
    new ApplicationContextRunner()
        .run(context -> {
            Binder binder = Binder.get(context.getEnvironment());

            var result =
                binder.bind("app.cache", CacheOptions.class);

            assertThat(result.isBound()).isFalse();

            CacheOptions options =
                binder.bindOrCreate("app.cache", CacheOptions.class);

            assertThat(options).isNotNull();
            assertThat(options.getMaximumEntries()).isEqualTo(100);
        });
}
~~~

Với target JavaBean minh họa, test cho thấy sự khác nhau về hợp đồng API:

- `bind` có thể cho biết không có cấu hình dưới prefix.
- `bindOrCreate` cố tạo một instance có default của type.

Nếu target không thể được Binder khởi tạo, `bindOrCreate` không thể bảo đảm test thứ hai thành công; đây chính là lý do phải chọn kiểu đích phù hợp.

## 24. Kiểm thử: value sai không được biến thành default

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void invalidIntegerDoesNotSilentlyUseDefault() {
    new ApplicationContextRunner()
        .withPropertyValues("app.cache.maximum-entries=many")
        .run(context -> {
            Binder binder = Binder.get(context.getEnvironment());

            assertThatThrownBy(() ->
                binder.bindOrCreate(
                    "app.cache", CacheOptions.class
                )
            ).isInstanceOf(RuntimeException.class);
        });
}
~~~

Đây là test minh họa ý định: **input không hợp lệ phải được phát hiện**. Trong test thật, có thể kiểm nguyên nhân `BindException`/conversion exception hoặc đường dẫn property theo phiên bản Spring Boot đang dùng thay vì assert một loại chung quá rộng.

Nếu test bất ngờ không lỗi, kiểm class model, setter, khả năng target field được bind, nguồn cấu hình đang thắng và option xử lý invalid field. Không bật `ignoreInvalidFields` để biến một trường hợp sai dữ liệu thành test pass.

## 25. Kiểm thử: record có @DefaultValue

Model:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.bind.DefaultValue;

public record RetryOptions(
    @DefaultValue("3") int maxAttempts,
    @DefaultValue("250ms") Duration backoff
) {}
~~~

Test:

~~~java
@Test
void recordUsesConstructorDefaults() {
    new ApplicationContextRunner()
        .withPropertyValues("app.retry.max-attempts=5")
        .run(context -> {
            RetryOptions options =
                Binder.get(context.getEnvironment())
                    .bindOrCreate("app.retry", RetryOptions.class);

            assertThat(options.maxAttempts()).isEqualTo(5);
            assertThat(options.backoff())
                .isEqualTo(Duration.ofMillis(250));
        });
}
~~~

Trường hợp này khác test JavaBean: default `backoff` đến từ annotation trên record component được xử lý trong constructor binding, không phải field initializer.

Nếu có nhiều constructor không phù hợp hoặc phiên bản Spring Boot thay đổi cách nhận diện constructor, cần kiểm hướng dẫn API tương ứng với phiên bản dự án. Không giải quyết bằng cách thêm `@Component` lên record; component construction và Binder constructor binding là hai cơ chế khác nhau.

## 26. Khi nào dùng @ConfigurationProperties thay Binder thủ công?

Không phải mọi component đều nên gọi `Binder.get(environment)` mỗi lần cần đọc config. Nếu group được dùng xuyên suốt ứng dụng và có ý nghĩa nghiệp vụ rõ, Spring-managed typed configuration bean có thể là thiết kế tốt hơn:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(
    @DefaultValue("true") boolean enabled,
    @DefaultValue("5m") Duration ttl,
    @DefaultValue("100") int maximumEntries
) {}
~~~

Đăng ký:

~~~java
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
~~~

Consumer inject qua constructor:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CacheManager {
    private final CacheProperties config;

    public CacheManager(CacheProperties config) {
        this.config = config;
    }

    public Duration ttl() {
        return config.ttl();
    }
}
~~~

**Khi nên dùng Binder API thủ công:**

- Đang viết infrastructure hoặc auto-configuration cần bind một nhóm vào thời điểm phù hợp.
- Muốn quyết định có tạo một optional config object hay không.
- Cần bind vào một object mutable đã có.
- Cần tạo nhiều đối tượng cấu hình theo prefix được chọn bằng logic hạ tầng.

**Khi nên dùng Spring-managed `@ConfigurationProperties`:**

- Group được nhiều bean nghiệp vụ sử dụng.
- Muốn typed dependency rõ ràng.
- Cần lifecycle validation gắn với Spring context.
- Muốn giảm việc gọi Binder rải rác trong service.

Cả hai dùng nguyên tắc cấu hình ngoài và type conversion tương tự; khác đường đăng ký/lifecycle và mức kiểm soát mà caller có.

## 27. Ví dụ service tạo cấu hình theo tên tenant

Một lý do hợp lý để gọi Binder thủ công là prefix thay đổi theo một định danh được kiểm soát.

File:

~~~properties
app.tenants.alpha.timeout=2s
app.tenants.alpha.max-retries=3

app.tenants.beta.timeout=5s
app.tenants.beta.max-retries=1
~~~

JavaBean:

~~~java
import java.time.Duration;

public class TenantSettings {
    private Duration timeout = Duration.ofSeconds(3);
    private int maxRetries = 2;

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Loader:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class TenantSettingsLoader {
    private final Binder binder;

    public TenantSettingsLoader(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public TenantSettings load(String tenant) {
        if (!tenant.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException(
                "Invalid tenant identifier");
        }

        return binder.bindOrCreate(
            "app.tenants." + tenant, TenantSettings.class);
    }
}
~~~

Trong ví dụ, `tenant` phải được validate trước khi dùng làm một phần của property path. Điều này giúp tránh tra cứu một key tùy ý nằm ngoài không gian cấu hình dự định.

Nếu tenant không có cấu hình, method sẽ cố tạo `TenantSettings` với timeout 3 giây và maxRetries 2. Đó là một policy có thể hợp lý cho sandbox; với production hoặc tenant phải được provision, có thể nên dùng `bind(...).orElseThrow(...)` để không vô tình chấp nhận tenant chưa cấu hình.

## 28. Không dùng bindOrCreate làm “lối thoát” khi source lỗi

Giả sử deployment cần endpoint quan trọng:

~~~properties
app.payment.endpoint=https://pay.example.test
app.payment.timeout=2s
~~~

Nếu người vận hành viết nhầm:

~~~properties
app.payment.endpoint=not a valid URI
app.payment.timeout=two seconds?
~~~

thì policy an toàn không phải là “lỗi thì dùng object mặc định”:

~~~java
// Thiết kế có rủi ro: che mọi lỗi cấu hình.
try {
    return binder.bindOrCreate(
        "app.payment", PaymentOptions.class);
} catch (Exception ignored) {
    return PaymentOptions.forDevelopment();
}
~~~

Đoạn trên minh họa **anti-pattern**: nó có thể che lỗi conversion, lỗi binding, lỗi constructor hoặc vấn đề triển khai thực tế.

Một hướng tốt hơn:

~~~java
return binder.bind(
        "app.payment", PaymentOptions.class)
    .orElseThrow(() -> new IllegalStateException(
        "Missing app.payment configuration"
    ));
~~~

Nếu value không hợp kiểu, vẫn cần để nguyên lỗi conversion/binding có ngữ cảnh; với value hợp kiểu nhưng không hợp lệ domain, thêm validation cần thiết. Default chỉ nên dùng cho group **thực sự tùy chọn**.

## 29. Quan hệ với active profiles và Config Data import

Binder đọc các value từ `Environment` sau khi Spring Boot đã xác định Config Data và những PropertySource liên quan trong ứng dụng.

Ví dụ:

~~~properties
# application.properties
app.cache.ttl=5m
~~~

~~~properties
# application-dev.properties
app.cache.ttl=30s
~~~

Khi profile `dev` active, `Binder.get(environment).bindOrCreate("app.cache", CacheOptions.class)` đọc **giá trị hiệu lực** theo thứ tự nguồn, nên trong tình huống thông thường `ttl` là 30 giây.

Nếu có:

~~~bash
java -jar app.jar --spring.profiles.active=dev --app.cache.ttl=10s
~~~

command-line có thể ghi đè file profile, cho ra 10 giây. Default 5 phút của JavaBean chỉ có ý nghĩa khi không có value đến từ các nguồn thắng.

Tương tự với:

~~~properties
spring.config.import=optional:file:./config/extra-cache.properties
~~~

Nếu file import có key `app.cache.ttl`, nó tham gia Environment theo quy tắc Config Data. Binder không cần biết file nào được import, nhưng **người vận hành cần biết nguồn giá trị hiệu lực** khi debug.

## 30. Nested list và map khi đặt default

Đối với cấu hình phức tạp:

~~~yaml
app:
  destinations:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 5s
~~~

Một model:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;

public record DestinationOptions(
    List<Destination> destinations
) {
    public record Destination(
        String name,
        URI url,
        Duration timeout
    ) {}
}
~~~

Có thể bind:

~~~java
DestinationOptions options =
    binder.bindOrCreate("app", DestinationOptions.class);
~~~

Nhưng **thiếu `app.destinations`** có thể làm thành phần list không được cấp theo cách ứng dụng mong đợi. `bindOrCreate("app",...)` không tự tạo ra một destination mặc định có URL và timeout nếu model không có policy tạo chúng.

Đối với list, cần quyết định:

- Thiếu list nghĩa là **rỗng** hay **lỗi**?
- Nếu có một phần tử, URL/timeout có bắt buộc không?
- Có chấp nhận duplicate `name` không?
- Khi file theo profile thay toàn bộ list, kết quả cuối cần gồm những phần tử nào?

Nếu muốn default list, có thể thiết kế fallback ở caller hoặc một JavaBean initializer phù hợp và kiểm thử chính xác. Với record bất biến, cần mô tả default/constructor logic và kiểm tra behavior Binder cụ thể; không giả định object thiếu list trở thành `List.of()` trong mọi tình huống.

## 31. bindOrCreate không tự reload config file

Một điểm dễ nhầm: gọi Binder lại nhiều lần không tự động khiến Spring Boot **đọc lại một file YAML vừa sửa trên ổ đĩa**.

~~~java
public CacheOptions current() {
    return Binder.get(environment)
        .bindOrCreate("app.cache", CacheOptions.class);
}
~~~

Method `current()` chạy Binder tại thời điểm gọi. Tuy nhiên, dữ liệu nó đọc đến từ các `PropertySource` hiện có. Trong ứng dụng Spring Boot thông thường, Config Data từ file được nạp ở startup, không tự theo dõi thay đổi file liên tục.

Do đó:

1. **Gọi Binder lại** có thể tái bind từ môi trường hiện tại.
2. **Môi trường hiện tại có thay đổi hay không** phụ thuộc vào PropertySource/cơ chế refresh.
3. **Bean đã được tạo/bind trước đó** không tự được cập nhật vì có một method nơi khác gọi Binder.

Nếu cần dynamic reload, phải thiết kế rõ nguồn dữ liệu thay đổi, vòng đời object, thread-safety và policy refresh. `bindOrCreate` không phải cơ chế file watcher.

## 32. Chi phí và vị trí nên gọi Binder

Việc gọi `Binder.get(environment).bindOrCreate(...)` ở mỗi request chỉ để đọc một nhóm cấu hình ổn định thường là thiết kế không cần thiết:

~~~java
public Response handleRequest() {
    CacheOptions options =
        Binder.get(environment)
              .bindOrCreate("app.cache", CacheOptions.class);
    // ...
}
~~~

Với một nhóm config ổn định, có thể bind một lần ở startup và inject bean typed cho service. Điều này làm các dependency dễ test và tránh parsing/conversion lặp lại.

**Binder thủ công** hợp với việc khởi tạo infrastructure, xây một registry đối tượng theo prefix hoặc một luồng chuyên biệt. Nếu phải bind lại thường xuyên, hãy xác định nguồn config có thay đổi hợp lệ không và có cách cache/snapshot an toàn nào không.

Không dùng cơ chế Binder thay cho quản lý dữ liệu nghiệp vụ động như trạng thái session, số dư, danh mục cập nhật liên tục hoặc cờ thay đổi theo từng request mà không có thiết kế refresh rõ.

## 33. Một ví dụ kết hợp: bindOrCreate trong @Bean factory

Một cách hợp lý để dùng Binder thủ công là xây một bean nghiệp vụ trong configuration class:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class CacheConfiguration {

    @Bean
    CacheClient cacheClient(Environment environment) {
        CacheOptions settings =
            Binder.get(environment)
                .bindOrCreate("app.cache", CacheOptions.class);

        return new CacheClient(
            settings.isEnabled(),
            settings.getTtl(),
            settings.getMaximumEntries()
        );
    }
}
~~~

`CacheClient` là type minh họa của ứng dụng, giả định có constructor tương ứng. Factory method chỉ dựng client từ typed options.

Lựa chọn khác thường gọn hơn nếu settings là một contract dùng ở nhiều nơi:

~~~java
@Bean
CacheClient cacheClient(CacheProperties properties) {
    return new CacheClient(
        properties.enabled(),
        properties.ttl(),
        properties.maximumEntries()
    );
}
~~~

Ở mẫu thứ hai, `CacheProperties` đã được Spring Boot đăng ký/bind như một configuration properties bean. Không cần gọi Binder thêm lần nữa.

Không nhất thiết biến mọi thứ thành bean cấu hình. Nhưng nên chọn **một** cách rõ ràng, tránh vừa có bean typed settings vừa có nhiều service tự bind lại một prefix, dẫn tới logic default không thống nhất.

## 34. Đọc lỗi khi bindOrCreate không khởi tạo được

Một số lỗi có thể gặp:

| Tình huống | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Value sai kiểu | `Failed to bind` / conversion exception | Sửa value hoặc converter |
| Prefix sai | Kết quả bind không bound, object default không có data | Kiểm tên prefix/key |
| Không tạo được target | Lỗi constructor/instantiation | Chọn JavaBean/record phù hợp với Binder |
| Record thiếu parameter metadata khi cần | Constructor binding không xác định parameter | Kiểm Java compiler/Boot version |
| Nested object bị null | Default nested chưa được thiết kế | Dùng `@DefaultValue`/model phù hợp hoặc validation |
| List từ profile bị thay | Mất phần tử ở nguồn thấp hơn | Xét list replacement/precedence |
| Bean thiếu trong DI | Object bind thủ công chưa được đăng ký bean | Đăng ký @Bean hoặc dùng @ConfigurationProperties |
| Validation không chạy như dự kiến | Manual Binder không được cấu hình validation tương ứng | Bật validator/handler hoặc dùng managed bean |
| Value chỉ sai trên production | Một env/CLI/profile override | Xem effective value/Origin |
| Chỉnh file nhưng object không đổi | Config Data không refresh | Thiết kế refresh/restart |

Đọc exception theo tầng:

~~~text
Source loading
  -> Property name / shape
  -> Conversion
  -> Constructor / setter binding
  -> Validation
  -> Consumer nghiệp vụ
~~~

Tên `BindException` trong Spring Boot có thể là lớp bọc ngoài của vấn đề conversion hoặc instantiation. Muốn sửa đúng, cần đọc root cause và property path.

## 35. Checklist lựa chọn API

| Nhu cầu | API/cách làm |
| --- | --- |
| Muốn biết group có được bind hay không | `binder.bind(prefix, Type.class)` rồi `isBound()` |
| Muốn một instance ngay cả khi prefix không có | `binder.bindOrCreate(prefix, Type.class)` |
| Muốn fallback do caller tự xây | `bind(...).orElseGet(factory)` |
| Muốn yêu cầu group bắt buộc | `bind(...).orElseThrow(...)` |
| Muốn bind vào mutable object sẵn có | `bind(prefix, Bindable.ofInstance(existing))` |
| Muốn bind list có generic type | `bind(prefix, Bindable.listOf(Element.class))` |
| Muốn default cho JavaBean | Field initializer / constructor hợp lệ |
| Muốn default cho record constructor binding | `@DefaultValue` trên parameter/component |
| Muốn default nested record | `@DefaultValue` trên nested parameter nếu phù hợp |
| Muốn kiểm ràng buộc của config bean | `@Validated` + Jakarta Validation, đúng registration |
| Muốn kiểm validation object bind thủ công | Tích hợp Validator hoặc BindHandler có chủ đích |
| Muốn phát hiện value sai | Không nuốt exception; kiểm converter/type |
| Muốn cùng group inject nhiều bean | `@ConfigurationProperties` + scan/enable |
| Muốn config thay đổi ở runtime | Thiết kế refresh/snapshot, không dựa vào bindOrCreate |

## 36. Bài tập tự luyện

### Bài 1: prefix hoàn toàn không có

JavaBean `CacheOptions` có default `ttl=5m`, `maximumEntries=100`. Không có bất kỳ `app.cache.*` nào. Dùng:

~~~java
binder.bindOrCreate("app.cache", CacheOptions.class)
~~~

**Kết luận:** nếu Binder tạo được JavaBean, object mới giữ các default của Java. `bind(...)` trong cùng tình huống có thể trả `BindResult` không bound.

### Bài 2: chỉ có một key

~~~properties
app.cache.ttl=30s
~~~

JavaBean vẫn có default maximumEntries 100. **Kết luận:** `ttl` được bind thành 30 giây; `maximumEntries` thường giữ default 100 theo JavaBean binding.

### Bài 3: key sai kiểu

~~~properties
app.cache.maximum-entries=hundreds
~~~

Target cần `int`. **Kết luận:** conversion failure; `bindOrCreate` không mặc định quay về 100.

### Bài 4: record không có annotation default

~~~java
public record RetryOptions(int maxAttempts, Duration backoff) {}
~~~

Không có prefix config. **Kết luận:** không nên giả định maxAttempts=3 hoặc backoff=250ms. Nếu cần những default đó, phải khai báo policy ở Binder/constructor/caller một cách phù hợp.

### Bài 5: default từ @DefaultValue

~~~java
public record RetryOptions(
    @DefaultValue("3") int maxAttempts,
    @DefaultValue("250ms") Duration backoff
) {}
~~~

Chỉ cấu hình `app.retry.max-attempts=5`. **Kết luận:** maxAttempts là 5, backoff là 250ms khi Binder áp dụng constructor binding thành công.

### Bài 6: bắt buộc phải có group

Payment config không được phép thiếu. **Kết luận:** `bind(...).orElseThrow(...)` có thể diễn đạt policy vắng cả group; bổ sung validation cho các field bắt buộc, không dùng `bindOrCreate` để tạo dữ liệu mặc định thiếu ý nghĩa.

### Bài 7: factory fallback

~~~java
result.orElse(buildDefault());
result.orElseGet(() -> buildDefault());
~~~

**Kết luận:** `orElse` đánh giá biểu thức argument trước lời gọi; `orElseGet` trì hoãn đến khi fallback cần thiết.

### Bài 8: muốn giữ object mutable có sẵn

Đã tạo `CacheOptions existing` và đặt maximumEntries=800. Muốn bind thêm cấu hình bên ngoài lên instance này. **Kết luận:** cân nhắc `Bindable.ofInstance(existing)` với `bind(...)` thay vì tạo object mới với `bindOrCreate`. Khi triển khai Java, dùng tên class ASCII chính xác `Bindable`.

### Bài 9: thay file YAML khi ứng dụng đang chạy

Sau khi sửa file, gọi `bindOrCreate` lại. **Kết luận:** không tự bảo đảm đọc lại file trên đĩa; còn phụ thuộc PropertySource đã refresh chưa.

### Bài 10: list default

JavaBean có default một server, file cung cấp hai server. **Kết luận:** không tự giả định kết quả ba server. Xem list binding/replacement, và đặt default list chỉ cho trường hợp không được cấu hình nếu đó là policy mong muốn.

## 37. Kết luận và công thức ghi nhớ

Ba phương thức giải quyết ba câu hỏi riêng:

~~~text
bind:
  "Có dữ liệu để liên kết thành một kết quả không?"

bindOrCreate:
  "Liên kết nếu có; nếu không, hãy cố tạo một instance."

bind(...).orElseGet(factory):
  "Nếu không có kết quả bound, tôi tự cấp fallback."
~~~

Default cũng có ba dạng:

~~~text
JavaBean field initializer   -> default trên instance mutable
@DefaultValue               -> default cho constructor parameter
orElse / orElseGet          -> fallback tại call site khi không bound
~~~

Hãy phân biệt **không có cấu hình** với **cấu hình sai**. Khi group thực sự tùy chọn và type có default hợp lý, `bindOrCreate` giúp code gọn và rõ. Khi group là bắt buộc, dùng chính sách fail fast và validation. Khi chỉ thiếu một field trong record, đặt `@DefaultValue` đúng chỗ; với JavaBean, dùng initializer hoặc constructor hợp lệ. Khi value hiện diện nhưng sai kiểu hoặc sai ràng buộc, **đừng dùng fallback để che lỗi**. Cách quản lý như vậy giữ cho cấu hình vừa linh hoạt giữa các môi trường, vừa có hành vi khởi động dễ dự đoán và dễ chẩn đoán.
