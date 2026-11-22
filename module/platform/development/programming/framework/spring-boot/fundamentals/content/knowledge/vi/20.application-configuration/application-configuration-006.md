# @Value cho giá trị đơn và khác biệt với biểu thức SpEL

Trong Spring Boot, ứng dụng thường cần lấy các giá trị cấu hình nhỏ như tên dịch vụ, số lần thử lại, cờ bật/tắt tính năng, thời hạn chờ hoặc tên môi trường đang chạy. Một cách trực tiếp là dùng annotation `@Value` để yêu cầu Spring đưa một giá trị vào bean.

Điều dễ nhầm nhất là hai cú pháp thường xuất hiện bên trong `@Value`:

- **Property placeholder `${...}`**: tìm một thuộc tính trong Spring `Environment` rồi lấy giá trị của thuộc tính đó.
- **Spring Expression Language, viết tắt SpEL, `#{...}`**: đánh giá một biểu thức, ví dụ phép tính, biểu thức điều kiện hoặc truy cập một bean Spring.

Cả hai đều có thể được viết trong `@Value`, nhưng chúng phục vụ **hai mục đích khác nhau**. Với cấu hình đơn lẻ, property placeholder thường rõ ràng hơn. SpEL hữu ích khi cần tính một biểu thức ở thời điểm inject, song không nên biến thành nơi đặt business logic phức tạp.

## 1. @Value là gì?

`@Value` thuộc Spring Framework:

```java
import org.springframework.beans.factory.annotation.Value;
```

Annotation này có thể được đặt lên field, tham số constructor, tham số method hoặc tham số factory method `@Bean` để chỉ định giá trị cần inject.

Ví dụ ứng dụng có cấu hình:

```yaml
# application.yml
app:
  display-name: Order Service
  retry-count: 3
  notifications-enabled: true
```

Có thể lấy từng giá trị bằng:

```java
@Component
public class ApplicationInfo {

    @Value("${app.display-name}")
    private String displayName;

    @Value("${app.retry-count}")
    private int retryCount;

    @Value("${app.notifications-enabled}")
    private boolean notificationsEnabled;

    public String describe() {
        return displayName
                + " (retry=" + retryCount
                + ", notifications=" + notificationsEnabled + ")";
    }
}
```

Spring sẽ tìm các thuộc tính tương ứng, chuyển kiểu phù hợp, rồi inject vào instance của `ApplicationInfo`.

Đây là ví dụ **field injection** để thấy cú pháp dễ dàng. Trong code ứng dụng, constructor injection thường được ưu tiên vì dependency rõ ràng, dễ test và có thể lưu vào field `final`.

`@Value` **không tự tạo bean**. Class phải đã được Spring quản lý qua `@Component`, `@Service`, `@Configuration`, `@Bean` hoặc cơ chế đăng ký tương ứng. Tự gọi `new ApplicationInfo()` sẽ không khiến Spring inject giá trị.

## 2. Property placeholder: cú pháp ${property.name}

Cú pháp placeholder đầy đủ:

```java
@Value("${app.display-name}")
private String displayName;
```

Trong đó:

- `${` mở đầu một property placeholder.
- `app.display-name` là tên thuộc tính cần tìm.
- `}` kết thúc placeholder.

Nếu cấu hình có:

```properties
app.display-name=Order Service
```

thì field `displayName` nhận chuỗi `Order Service`.

Hãy hình dung quá trình:

```text
@Value("${app.display-name}")
             │
             ▼
Spring Environment
             │
             ▼
Tìm property "app.display-name"
             │
             ▼
"Order Service"
             │
             ▼
Chuyển đổi kiểu nếu cần
             │
             ▼
Inject vào bean
```

Đây là **tra cứu cấu hình**, không phải chạy biểu thức Java. Ví dụ `@Value("${2 + 3}")` có nghĩa “hãy tìm property tên `2 + 3`”, chứ không có nghĩa cộng hai số.

## 3. Giá trị mặc định với dấu hai chấm

Một placeholder có thể chứa giá trị mặc định theo cú pháp:

```java
@Value("${app.display-name:Unnamed Service}")
private String displayName;
```

Nếu `app.display-name` không tồn tại, Spring dùng `Unnamed Service`. Nếu property tồn tại, giá trị cấu hình được ưu tiên.

Một số ví dụ:

```java
@Value("${app.max-retries:3}")
private int maxRetries;

@Value("${app.feature-enabled:false}")
private boolean featureEnabled;

@Value("${app.region:local}")
private String region;
```

Bảng hành vi:

| Cấu hình | Annotation | Giá trị inject |
|---|---|---|
| `app.region=ap-southeast-1` | `@Value("${app.region:local}")` | `ap-southeast-1` |
| Không có `app.region` | `@Value("${app.region:local}")` | `local` |
| `app.max-retries=5` | `@Value("${app.max-retries:3}")` | Số nguyên `5` |
| Không có `app.max-retries` | `@Value("${app.max-retries:3}")` | Số nguyên `3` |
| `app.feature-enabled=false` | `@Value("${app.feature-enabled:true}")` | Boolean `false` |

**Chú ý:** giá trị mặc định chủ yếu xử lý trường hợp **không tìm thấy property**. Một property tồn tại nhưng có giá trị rỗng không nhất thiết được thay bằng default. Ví dụ `app.region=` có thể inject chuỗi rỗng vào `String` dù annotation có `:local`.

Nếu ứng dụng cần coi cả null, chuỗi rỗng và chuỗi toàn khoảng trắng là không hợp lệ, hãy xác thực giá trị sau khi bind thay vì chỉ dựa vào default trong placeholder.

### 3.1. Default có thể chứa ký tự đặc biệt

Ví dụ một URL mặc định:

```java
@Value("${app.callback-url:http://localhost:8080/callback}")
private String callbackUrl;
```

Spring hiểu dấu hai chấm sau tên property là dấu phân cách cho default. Phần `http://...` vẫn là nội dung của giá trị mặc định.

Tuy nhiên, nếu default có cú pháp phức tạp hoặc cần escape ký tự placeholder, hãy cân nhắc chuyển giá trị đó vào `application.yml` hoặc bind bằng `@ConfigurationProperties`. Giữ biểu thức `@Value` đơn giản sẽ dễ đọc và ít bị lỗi khi refactor.

## 4. Property nguồn có thể đến từ đâu?

Spring Boot chuẩn bị `Environment` bằng nhiều `PropertySource`. Các nguồn phổ biến gồm:

- `application.properties` hoặc `application.yml`.
- File dành cho profile, ví dụ `application-dev.yml`.
- Biến môi trường hệ điều hành.
- Java system properties.
- Tham số dòng lệnh `--key=value`.
- Các property source do ứng dụng hoặc test thêm vào.

Ví dụ trong `application.yml`:

```yaml
app:
  payment:
    provider: mock
    max-attempts: 4
```

Code:

```java
@Value("${app.payment.provider}")
private String provider;

@Value("${app.payment.max-attempts:3}")
private int maxAttempts;
```

Khi chạy với tham số:

```bash
java -jar app.jar --app.payment.provider=remote
```

giá trị hiệu lực có thể là `remote` vì command-line properties thường có độ ưu tiên cao hơn file `application.yml` trong cấu hình Boot mặc định.

Với biến môi trường, Spring Boot hỗ trợ các quy tắc tên tương đương theo relaxed binding. Chẳng hạn, một cấu hình có tên chuẩn `app.payment.max-attempts` thường được biểu diễn trong environment variable theo dạng `APP_PAYMENT_MAXATTEMPTS`. Nên dùng **tên property canonical dạng kebab-case** trong `@Value` để Spring Boot có thể áp dụng cơ chế tra cứu tên tương ứng nhất quán.

Thứ tự ưu tiên và cách resolve cụ thể phụ thuộc vào property source thực tế được nạp. Nếu giá trị khác kỳ vọng, cần kiểm tra giá trị hiệu lực trong `Environment`, active profiles và tham số khởi chạy, không chỉ mở một file YAML.

## 5. Constructor injection với @Value

Constructor injection làm dependency và giá trị cấu hình trở thành một phần hợp đồng tạo object:

```java
package com.example.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class RetryService {

    private final int maxAttempts;
    private final boolean enabled;

    public RetryService(
            @Value("${app.retry.max-attempts:3}") int maxAttempts,
            @Value("${app.retry.enabled:true}") boolean enabled) {
        this.maxAttempts = maxAttempts;
        this.enabled = enabled;
    }

    public boolean mayRetry(int attempt) {
        return enabled && attempt < maxAttempts;
    }
}
```

Lợi ích so với field injection:

1. Hai giá trị bắt buộc được thể hiện trên constructor.
2. Fields có thể khai báo `final`.
3. Unit test có thể tạo object trực tiếp bằng `new RetryService(3, true)` mà không cần Spring context.
4. Object không tồn tại trong trạng thái thiếu những giá trị constructor cần.
5. Phù hợp với cách inject các dependency là service/repository khác.

`@Value` ở đây không quyết định nơi đặt logic retry. Nó chỉ cung cấp giá trị cấu hình; business logic vẫn nằm trong phương thức của service.

### 5.1. Kết hợp bean dependency và property value

```java
@Service
public class ReportService {

    private final ReportRepository repository;
    private final int pageSize;

    public ReportService(
            ReportRepository repository,
            @Value("${app.reports.page-size:50}") int pageSize) {
        this.repository = repository;
        this.pageSize = pageSize;
    }
}
```

Spring resolve `ReportRepository` như dependency theo type; tham số `pageSize` được resolve bằng placeholder. Hai hình thức injection có thể cùng tồn tại trong constructor.

## 6. @Value trên tham số @Bean method

Có thể dùng `@Value` khi tạo bean thông qua Java configuration.

```java
import java.time.Clock;
import java.time.ZoneId;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock applicationClock(
            @Value("${app.clock.zone:UTC}") String zoneId) {
        return Clock.system(ZoneId.of(zoneId));
    }
}
```

Ở đây:

- `@Bean` khai báo một factory method tạo `Clock`.
- `@Value` đưa giá trị cấu hình vào tham số `zoneId`.
- Factory method tự chuyển tên timezone thành `ZoneId`.
- Spring quản lý đối tượng `Clock` được trả về.

Cách này đặc biệt hữu ích khi cần khởi tạo class từ JDK hoặc thư viện bên ngoài không mang annotation Spring.

Nếu `app.clock.zone` là chuỗi không hợp lệ, `ZoneId.of(...)` sẽ ném exception và bean không khởi tạo được. `@Value` không tự xác thực tính hợp lệ của mọi giá trị domain.

## 7. Chuyển kiểu từ String sang giá trị Java

`Environment` cung cấp giá trị property và Spring dùng hạ tầng chuyển đổi kiểu khi inject. Với các kiểu scalar thông dụng, bạn thường không cần parse thủ công.

Ví dụ:

```java
@Value("${app.name:Demo}")
private String name;

@Value("${app.worker-count:4}")
private int workerCount;

@Value("${app.audit-enabled:false}")
private boolean auditEnabled;

@Value("${app.failure-rate:0.05}")
private double failureRate;
```

Nếu cấu hình:

```properties
app.worker-count=8
app.audit-enabled=true
app.failure-rate=0.12
```

Spring cố gắng chuyển các chuỗi tương ứng thành `int`, `boolean` và `double`.

**Khi chuyển kiểu thất bại:** ví dụ `app.worker-count=many` nhưng field là `int`, ứng dụng có thể lỗi lúc tạo bean vì giá trị không hợp lệ. Default `:4` không giải quyết trường hợp property đã tồn tại nhưng chứa nội dung sai kiểu.

Không nên sử dụng giá trị cấu hình không tin cậy mà không có giới hạn. Ví dụ `workerCount` có thể parse thành số rất lớn hoặc âm; cả hai đều hợp lệ về kiểu `int` nhưng không hợp lệ với nghiệp vụ. Nếu cần validation như min/max, nên cân nhắc `@ConfigurationProperties` cùng Bean Validation.

### 7.1. Duration, DataSize và các kiểu phức tạp

Spring Boot có hỗ trợ nhiều cách bind giá trị có đơn vị thời gian/kích thước, đặc biệt qua `@ConfigurationProperties`. Đối với `@Value`, kết quả chuyển đổi còn phụ thuộc loại field, conversion service và các annotation/hạ tầng hỗ trợ phiên bản.

Ví dụ, thay vì mặc định một chuỗi `10s` luôn tự chuyển thành mọi kiểu thời gian bạn muốn, có thể inject String và parse rõ:

```java
@Bean
public ClientSettings clientSettings(
        @Value("${app.client.timeout:PT10S}") String timeout) {
    return new ClientSettings(
            java.time.Duration.parse(timeout)
    );
}
```

Ví dụ này quy ước thời hạn theo định dạng ISO-8601 như `PT10S`. Nếu muốn syntax thân thiện như `10s` cùng validation/metadata, `@ConfigurationProperties` thường phù hợp hơn.

## 8. Thiếu property: điều gì xảy ra?

Giả sử bạn khai báo:

```java
@Value("${payment.api-endpoint}")
private String apiEndpoint;
```

nhưng không có property `payment.api-endpoint` ở các nguồn Environment. Trong ứng dụng Spring Boot thông thường có cơ chế placeholder resolution, quá trình tạo bean sẽ thất bại với thông báo kiểu:

```text
Could not resolve placeholder 'payment.api-endpoint'
```

Đây là một **lỗi cấu hình tại startup**, thường tốt hơn việc phát hiện thiếu endpoint khi đang xử lý request.

Có ba cách xử lý, tùy ý định:

1. **Property bắt buộc:** giữ placeholder không có default, để startup fail nếu thiếu.
2. **Property tùy chọn có default hợp lệ:** dùng `${payment.api-endpoint:http://localhost:8080}`.
3. **Nhóm cấu hình có ràng buộc:** dùng `@ConfigurationProperties` và validation để diễn đạt các trường bắt buộc và quan hệ giữa chúng.

Không nên đặt default giả cho mọi secret hoặc endpoint chỉ để ứng dụng khởi động. Một default không đúng có thể gây request đến sai hệ thống và khó phát hiện hơn lỗi fail-fast.

### 8.1. Giá trị rỗng khác property không tồn tại

Ví dụ:

```properties
app.label=
```

và:

```java
@Value("${app.label:My Application}")
private String label;
```

Property có thể được resolve thành chuỗi rỗng thay vì dùng default. Nếu chuỗi rỗng không được chấp nhận, cần validation sau injection hoặc bind theo cơ chế có thể validate.

## 9. Giá trị literal trong @Value

`@Value` không nhất thiết chứa placeholder hoặc SpEL. Bạn có thể inject literal:

```java
@Value("Local Mode")
private String label;

@Value("5")
private int retryCount;
```

Trong ví dụ thứ hai, literal `"5"` được chuyển đổi thành số nguyên phù hợp với field.

Tuy nhiên, literal không phải external configuration. Nếu giá trị luôn cố định trong code, hằng số Java hoặc constructor argument thông thường có thể rõ ràng hơn:

```java
private static final int DEFAULT_PAGE_SIZE = 50;
```

Dùng `@Value` đặc biệt có ý nghĩa khi giá trị cần đến từ `Environment` hoặc một expression do Spring đánh giá.

## 10. SpEL là gì?

**Spring Expression Language (SpEL)** là ngôn ngữ biểu thức của Spring Framework. Trong `@Value`, biểu thức SpEL có dạng:

```java
@Value("#{2 + 3}")
private int result;
```

Thay vì tìm property `2 + 3`, Spring đánh giá biểu thức số học và inject `5`.

Các ví dụ thường gặp:

```java
@Value("#{10 * 4}")
private int capacity;

@Value("#{'spring'.toUpperCase()}")
private String platform;

@Value("#{T(java.lang.Math).max(3, 8)}")
private int maxValue;

@Value("#{true ? 'enabled' : 'disabled'}")
private String status;
```

SpEL hỗ trợ nhiều tính năng như toán tử logic/số học, truy cập property/method, tham chiếu bean, toán tử điều kiện và gọi các static method được phép bởi expression evaluation context.

Điều quan trọng: **SpEL không phải cú pháp Java đầy đủ**. Nó có grammar và evaluation context riêng. Không nên giả định bất kỳ đoạn mã Java nào viết vào `#{...}` cũng có thể chạy.

## 11. Khác biệt cốt lõi giữa ${...} và #{...}

| Tiêu chí | Property placeholder `${...}` | SpEL `#{...}` |
|---|---|---|
| Mục đích | Tra cứu property | Đánh giá biểu thức |
| Dữ liệu nguồn | Spring `Environment` và property sources | Expression evaluation context, literals, bean references, objects |
| Ví dụ | `${app.max-retries:3}` | `#{2 * 3}` |
| Default | Dùng `:default` bên trong placeholder | Dùng logic của SpEL như ternary hoặc Elvis |
| Chuyển kiểu | Chuyển property text sang kiểu đích | Kết quả biểu thức có kiểu, có thể tiếp tục convert |
| Độ phức tạp phù hợp | Cấu hình scalar | Tính toán nhỏ hoặc tham chiếu expression |
| Rủi ro chính | Thiếu property, sai kiểu, nguồn override | Biểu thức khó đọc, lỗi evaluation, nguy cơ khi cho dữ liệu không tin cậy tham gia biểu thức |

Hai ví dụ rất khác nhau:

```java
@Value("${app.max-retries:3}")
private int maxRetries;
```

Spring tìm property `app.max-retries`; nếu không có thì dùng `3`.

```java
@Value("#{3 * 2}")
private int maxRetries;
```

Spring tính `3 * 2`, không liên quan đến property name nào.

Cú pháp sau không làm phép cộng:

```java
@Value("${3 + 2}")
private int number;
```

Spring cố tìm property có tên `3 + 2`. Nếu không tồn tại và không có default, quá trình placeholder resolution thường thất bại.

## 12. SpEL tham chiếu system properties

SpEL có thể truy cập các đối tượng được expression context cung cấp. Một ví dụ thường gặp là `systemProperties`:

```java
@Value("#{systemProperties['user.home']}")
private String userHome;
```

Đây là SpEL lấy giá trị Java system property `user.home`, không phải property placeholder từ `application.yml`.

Có thể cung cấp fallback bằng toán tử Elvis:

```java
@Value("#{systemProperties['app.region'] ?: 'local'}")
private String region;
```

Nếu expression bên trái là null hoặc giá trị được xem là rỗng theo semantics SpEL tương ứng, expression trả về `local`.

Dù ví dụ này hữu ích để học SpEL, với property cấu hình của Spring Boot, cú pháp:

```java
@Value("${app.region:local}")
private String region;
```

thường đúng ý định hơn vì nó tận dụng Environment và các nguồn cấu hình Spring Boot quản lý.

## 13. SpEL tham chiếu bean và gọi method

SpEL có thể tham chiếu bean Spring bằng cú pháp `@beanName`.

Giả sử:

```java
@Component
public class TaxRules {

    public double defaultRate() {
        return 0.08;
    }
}
```

Một bean khác có thể khai báo:

```java
@Component
public class InvoiceSettings {

    @Value("#{@taxRules.defaultRate()}")
    private double taxRate;

    public double getTaxRate() {
        return taxRate;
    }
}
```

Trong expression `#{@taxRules.defaultRate()}`:

- `@taxRules` là tham chiếu bean tên `taxRules`.
- `defaultRate()` là method được gọi khi expression được evaluate.
- Kết quả `0.08` được inject vào field.

Đây là một ví dụ minh họa khả năng của SpEL. Trong ứng dụng thật, **inject trực tiếp `TaxRules` bằng constructor rồi gọi method khi cần** thường dễ test và ít phụ thuộc vào string expression hơn:

```java
@Service
public class InvoiceService {

    private final TaxRules taxRules;

    public InvoiceService(TaxRules taxRules) {
        this.taxRules = taxRules;
    }

    public double calculateTax(double subtotal) {
        return subtotal * taxRules.defaultRate();
    }
}
```

Nếu biểu thức SpEL gọi method trên bean trong giai đoạn tạo dependency, nó cũng có thể kích hoạt khởi tạo bean sớm hoặc làm lộ vòng phụ thuộc. Dùng SpEL khi có lý do rõ ràng, không thay thế toàn bộ dependency injection.

## 14. Kết hợp placeholder và SpEL

Spring có thể resolve property placeholder trước rồi đánh giá một biểu thức SpEL chứa kết quả đã thay thế.

Ví dụ:

```java
@Value("#{${app.base-limit:10} * 2}")
private int effectiveLimit;
```

Nếu:

```properties
app.base-limit=15
```

thì có thể hình dung:

```text
#{${app.base-limit:10} * 2}
          │
          ▼
Resolve app.base-limit = 15
          │
          ▼
#{15 * 2}
          │
          ▼
Evaluate SpEL
          │
          ▼
30
```

Không có property thì default `10` được thay vào, và expression `10 * 2` trả `20`.

Đây là ví dụ thích hợp khi giá trị nguồn được quy ước là số nguyên đáng tin cậy. Nếu người vận hành nhập `app.base-limit=large` thì biểu thức không hợp lệ và bean có thể không khởi tạo được.

**Cảnh báo:** không nên nhúng trực tiếp chuỗi không tin cậy vào SpEL. SpEL có khả năng đánh giá expression và gọi method; đưa dữ liệu bên ngoài vào vị trí cú pháp expression có thể làm thay đổi ý nghĩa của đoạn được đánh giá. Hãy coi expression là code cấu hình đáng tin cậy, còn dữ liệu người dùng là data cần validate và xử lý tách biệt.

### 14.1. Một cách dùng SpEL cho null

Trong một số trường hợp có thể viết:

```java
@Value("${app.optional-label:#{null}}")
private String optionalLabel;
```

Nếu property không tồn tại, placeholder default là SpEL `#{null}` và có thể cho ra null. Tuy nhiên, cách này làm code phức tạp hơn placeholder thông thường và không phù hợp với primitive như `int` khi null không thể được inject.

Với cấu hình có nhiều trường tùy chọn và các ràng buộc, một class `@ConfigurationProperties` thường là lựa chọn dễ hiểu hơn.

## 15. Thời điểm @Value được xử lý

`@Value` thường được resolve khi Spring tạo và inject bean. Điều đó có nghĩa:

1. Spring đã chuẩn bị các nguồn property cần thiết cho application context.
2. Dependency injection xử lý annotation và resolve placeholder/expression.
3. Giá trị được chuyển đổi sang type mà injection point yêu cầu.
4. Bean sử dụng giá trị đã inject trong vòng đời tiếp theo.

Nếu bạn sửa file `application.yml` sau khi ứng dụng đã khởi động, field được inject bằng `@Value` **không tự thay đổi**. `@Value` không phải cơ chế reactive subscription hoặc hot reload cấu hình.

Nếu cần cập nhật cấu hình runtime, hãy dùng một thiết kế dynamic configuration hoặc refresh mechanism được hỗ trợ trong hệ thống đang dùng; cần cân nhắc tính nhất quán, lifecycle và thread safety. Không nên mong `@Value` tự quan sát file và cập nhật.

## 16. @Value và @ConfigurationProperties khác nhau thế nào?

`@Value` phù hợp khi bean cần **một vài giá trị đơn lẻ**. Khi cấu hình lớn, có cấu trúc hoặc cần validation, `@ConfigurationProperties` thường tốt hơn.

Giả sử cấu hình:

```yaml
mail:
  host: smtp.example.test
  port: 587
  security:
    start-tls: true
  retry:
    max-attempts: 3
    delay: 5s
```

Cách dùng nhiều `@Value`:

```java
@Value("${mail.host}")
private String host;

@Value("${mail.port:587}")
private int port;

@Value("${mail.security.start-tls:true}")
private boolean startTls;

@Value("${mail.retry.max-attempts:3}")
private int maxAttempts;
```

Với một vài field, cách này vẫn dùng được. Nhưng khi cấu hình mở rộng, tên property rải khắp nhiều class, thiếu metadata nhóm và khó validate thống nhất.

Một hướng khác là property class:

```java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        String host,
        int port,
        Security security,
        Retry retry) {

    public record Security(boolean startTls) {}

    public record Retry(int maxAttempts, Duration delay) {}
}
```

Ví dụ minh họa cấu trúc record; cần đăng ký class `@ConfigurationProperties` qua `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc cơ chế phù hợp, đồng thời có các import cần thiết. Với binding thực tế, cần bảo đảm tên property, constructor, default và validation tương ứng với phiên bản Boot.

So sánh:

| Nhu cầu | @Value | @ConfigurationProperties |
|---|---|---|
| Một chuỗi hoặc boolean đơn lẻ | Rất phù hợp | Có thể hơi nhiều cấu trúc |
| Nhiều property cùng prefix | Dễ phân tán | Nhóm được trong một object |
| Validation `@NotBlank`, `@Min`, ... | Cần giải pháp khác | Tích hợp tốt với Bean Validation |
| Binding nested objects | Không thuận tiện | Phù hợp |
| List/Map phức tạp | Khó duy trì | Phù hợp hơn |
| Default/cấu hình tài liệu hóa | Default tại từng injection point | Có thể quản lý tập trung |
| Biểu thức SpEL | Có thể dùng | Binding properties không có mục tiêu đánh giá SpEL tùy ý |

Nguyên tắc thực hành: **một đến vài giá trị scalar dùng `@Value`; một nhóm cấu hình có nghĩa nghiệp vụ dùng `@ConfigurationProperties`**.

## 17. Property placeholder không phải binding collection đầy đủ

`@Value` có thể inject một chuỗi chứa dấu phẩy:

```properties
app.allowed-regions=vn,sg,jp
```

và lấy nguyên văn:

```java
@Value("${app.allowed-regions:vn}")
private String allowedRegions;
```

Sau đó ứng dụng có thể parse theo quy ước riêng nếu danh sách rất nhỏ. Trong một số context, Spring conversion service có thể chuyển String sang collection, nhưng không nên coi `@Value` là cơ chế binding list/map với mọi quy tắc của `@ConfigurationProperties`.

Với YAML list:

```yaml
app:
  allowed-regions:
    - vn
    - sg
    - jp
```

nên ưu tiên `@ConfigurationProperties` để bind thành `List<String>`, đặc biệt khi cần validation từng phần tử hoặc cấu trúc nested.

Không nên sử dụng SpEL để tự ráp các list/map phức tạp khi dữ liệu thực chất là cấu hình có cấu trúc.

## 18. @Value trên static field và object tự tạo

`@Value` được Spring xử lý trong vòng đời của bean instance, không phải cơ chế Java compiler tự gán giá trị.

Ví dụ không nên làm:

```java
@Component
public class BadSettings {

    @Value("${app.mode:local}")
    private static String mode;
}
```

Static field không được inject như instance field theo cơ chế thông thường của `@Value`. Kết quả có thể là null hoặc không đúng kỳ vọng.

Tương tự:

```java
public class Client {
    @Value("${app.endpoint}")
    private String endpoint;
}

Client client = new Client();
```

Object `client` được tạo bằng `new` ở ngoài Spring container nên annotation không tự có tác dụng.

Thay vì static field, inject giá trị vào constructor của một bean và để các consumer khác nhận bean đó bằng DI. Nếu code tĩnh thực sự cần cấu hình, thường nên thiết kế lại ranh giới để tránh global mutable state.

## 19. @Value không thay thế @ConditionalOnProperty

Hai annotation đều liên quan `Environment`, nhưng mục đích khác nhau.

```java
@Value("${feature.export.enabled:false}")
private boolean exportEnabled;
```

Bean vẫn được tạo, và field chỉ nhận giá trị bật/tắt.

Trong khi đó:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "feature.export",
        name = "enabled",
        havingValue = "true")
public class ExportConfiguration {

    @Bean
    ExportClient exportClient() {
        return new ExportClient();
    }
}
```

Cấu hình `ExportConfiguration` chỉ được áp dụng khi property thỏa condition. Nếu không match, Spring không đăng ký `exportClient` qua factory method này.

Dùng `@Value` khi bean luôn tồn tại nhưng behavior phụ thuộc vào value. Dùng `@ConditionalOnProperty` khi bạn muốn **việc đăng ký bean** phụ thuộc vào cấu hình.

Đừng mặc định chọn conditional configuration cho mọi boolean: nếu cả hai nhánh đều cần cùng một service, việc đọc một boolean trong service có thể đơn giản hơn.

## 20. @Value và những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Could not resolve placeholder` | Property không tồn tại và không có default | Kiểm tra key, profile và property sources; dùng default khi thật sự tùy chọn |
| Bean không tạo được vì `int` sai | Property có nội dung như `abc`, không thể convert sang kiểu đích | Sửa dữ liệu cấu hình, thêm validation phù hợp |
| Giá trị khác trong `application.yml` | Có property source ưu tiên cao hơn, chẳng hạn command line/environment | Kiểm tra Environment và profile |
| Default không được dùng khi property rỗng | Property có mặt nhưng chứa chuỗi rỗng | Validate hoặc chuẩn hóa giá trị |
| Field vẫn là null | Object tự tạo bằng `new`, class chưa là bean hoặc dùng static field | Đăng ký bean, dùng constructor injection |
| `@Value("${1 + 2}")` không cộng số | `${...}` tìm property, không đánh giá phép tính | Dùng `#{1 + 2}` |
| SpEL parse/evaluation exception | Biểu thức `#{...}` sai cú pháp hoặc gọi method không phù hợp | Giữ expression đơn giản, kiểm tra bean/method name |
| Cấu hình không tự cập nhật | `@Value` được resolve khi bean khởi tạo | Dùng refresh/dynamic configuration phù hợp nếu cần |
| List/map bị bind sai | Dùng placeholder scalar cho cấu hình nested/collection | Dùng `@ConfigurationProperties` |
| Inject nhầm khi có nhiều bean | Expression tham chiếu bean name sai hoặc bean không tồn tại | Ưu tiên DI theo type/qualifier thay cho string SpEL |
| Giá trị bí mật bị lộ trong log | In trực tiếp toàn bộ cấu hình hoặc exception chứa secrets | Không log secret, dùng secret management phù hợp |

### 20.1. Chú ý về lỗi cấu hình

Không nên “giải quyết” mọi lỗi bằng cách thêm default tùy tiện. Một giá trị quan trọng như URL hệ thống thanh toán, credential hoặc đường dẫn output bắt buộc thiếu nên dẫn đến lỗi rõ ràng khi startup, thay vì silently fallback sang một endpoint có thể sai.

Với dữ liệu cấu hình yêu cầu nhiều validation liên quan nhau, tạo một configuration properties object là cách thể hiện hợp đồng chặt chẽ hơn.

## 21. Kiểm thử giá trị được inject

Một cách đơn giản là dùng `@SpringBootTest` với properties chuyên cho test.

Ví dụ bean:

```java
@Component
public class GreetingSettings {

    private final String prefix;
    private final int times;

    public GreetingSettings(
            @Value("${greeting.prefix:Hello}") String prefix,
            @Value("${greeting.times:1}") int times) {
        this.prefix = prefix;
        this.times = times;
    }

    public String prefix() {
        return prefix;
    }

    public int times() {
        return times;
    }
}
```

Integration test:

```java
@SpringBootTest(properties = {
        "greeting.prefix=Chao",
        "greeting.times=3"
})
class GreetingSettingsTest {

    @Autowired
    private GreetingSettings settings;

    @Test
    void injectsConfiguredValues() {
        assertEquals("Chao", settings.prefix());
        assertEquals(3, settings.times());
    }
}
```

Đoạn test giả định có Spring Boot Test, JUnit Jupiter và các import tương ứng. Mục tiêu là chứng minh property test override giá trị và Spring convert `"3"` thành `int`.

Có thể viết test thứ hai không truyền `greeting.times` để kiểm tra default `1`, hoặc truyền giá trị không hợp lệ để quan sát lỗi tạo context.

### 21.1. Unit test mà không cần Spring context

Vì `GreetingSettings` dùng constructor injection, có thể kiểm tra logic thông thường bằng:

```java
@Test
void createsSettingsWithoutSpring() {
    GreetingSettings settings = new GreetingSettings("Hi", 2);
    assertEquals("Hi", settings.prefix());
    assertEquals(2, settings.times());
}
```

Đây là một lợi ích thiết thực của constructor injection: unit test không phụ thuộc vào annotation processor hoặc Spring application context chỉ để tạo object.

## 22. Ví dụ kết hợp: một giá trị cấu hình và một biểu thức

Giả sử ứng dụng cho phép cấu hình số lượng bản ghi cơ sở, nhưng cần một giới hạn lớn gấp hai lần cho tác vụ quản trị.

Cấu hình:

```properties
reports.base-limit=100
```

Cách 1 — inject giá trị đơn, tính toán trong Java:

```java
@Service
public class ReportLimits {

    private final int baseLimit;

    public ReportLimits(
            @Value("${reports.base-limit:100}") int baseLimit) {
        this.baseLimit = baseLimit;
    }

    public int adminLimit() {
        return baseLimit * 2;
    }
}
```

Cách 2 — dùng SpEL để tính ngay lúc inject:

```java
@Service
public class ReportLimits {

    private final int adminLimit;

    public ReportLimits(
            @Value("#{${reports.base-limit:100} * 2}")
            int adminLimit) {
        this.adminLimit = adminLimit;
    }

    public int adminLimit() {
        return adminLimit;
    }
}
```

Hai cách đều minh họa mối quan hệ giữa property và giá trị tính được. Với logic nghiệp vụ cần thay đổi, có test riêng hoặc cần xử lý overflow/giới hạn, cách 1 thường dễ đọc và dễ kiểm soát hơn. SpEL nên dành cho biểu thức đơn giản có mục đích rõ.

Không đăng ký cả hai class `ReportLimits` trong cùng package dưới cùng bean name ở một ứng dụng thật; đây là hai phiên bản thay thế để so sánh.

## 23. Lựa chọn giữa placeholder, SpEL và config object

Dùng bảng sau khi thiết kế:

| Nhu cầu | Cơ chế nên ưu tiên | Lý do |
|---|---|---|
| Đọc tên ứng dụng | `@Value("${app.name}")` | Một scalar từ Environment |
| Boolean có default | `@Value("${feature.enabled:false}")` | Rõ default và kiểu |
| Tính biểu thức đơn giản chỉ lúc inject | SpEL `@Value("#{2 * 5}")` | Tính giá trị từ expression |
| Giá trị dẫn xuất từ property | Đọc property rồi tính bằng Java; SpEL khi thật sự cần | Tách logic thường dễ test hơn |
| Nhiều property liên quan | `@ConfigurationProperties` | Typed object và nhóm cấu hình |
| Nested list/map | `@ConfigurationProperties` | Binding cấu trúc tốt hơn |
| Chỉ đăng ký bean khi bật cờ | `@ConditionalOnProperty` | Điều kiện tạo bean |
| Thay đổi giá trị runtime | Dynamic configuration mechanism | `@Value` không tự refresh |
| Truy cập một Spring service | Constructor injection | Không cần SpEL `@beanName` |
| Thiếu cấu hình bắt buộc phải báo lỗi | Placeholder không default hoặc validated properties | Fail-fast, tránh giá trị giả |

## 24. Bài tập thực hành

### Bài tập A — Đọc scalar values

Tạo các property `app.title`, `app.max-connections` và `app.debug-enabled` trong `application.yml`. Inject bằng constructor `@Value` vào một bean. In kết quả qua `CommandLineRunner` hoặc endpoint thử nghiệm.

### Bài tập B — Kiểm tra default

Xóa `app.max-connections`, giữ annotation `@Value("${app.max-connections:10}")`. Quan sát số 10. Sau đó đặt `app.max-connections=20` và kiểm tra giá trị được override.

### Bài tập C — Phân biệt chuỗi rỗng và missing

Đặt `app.title=` rồi thử `@Value("${app.title:Untitled}")`. So sánh khi key tồn tại nhưng rỗng và khi key bị xóa hoàn toàn. Đề xuất validation nếu không chấp nhận tiêu đề rỗng.

### Bài tập D — SpEL số học

Tạo field nhận `@Value("#{4 * 5}")`. So sánh với `@Value("${4 * 5}")` và giải thích vì sao một biểu thức được tính toán còn biểu thức kia tìm property.

### Bài tập E — Kết hợp placeholder và SpEL

Thử `@Value("#{${app.base-limit:10} * 2}")` với base-limit bằng 5, 20 và không tồn tại. Sau đó thử giá trị không phải số để quan sát lỗi.

### Bài tập F — Constructor injection và test

Viết một service nhận `@Value("${app.retry-count:3}")` qua constructor. Tạo unit test bằng constructor trực tiếp, rồi tạo integration test với `@SpringBootTest(properties = ...)`.

### Bài tập G — Chuyển sang @ConfigurationProperties

Bắt đầu với bốn field `@Value` cùng prefix `mail`. Chuyển chúng thành một properties object có nested object và validation. So sánh khả năng tổ chức, test và quản lý default.

### Bài tập H — Tránh expression với dữ liệu không tin cậy

Xác định vì sao không nên ghép input từ HTTP request vào một biểu thức SpEL để đánh giá. Viết lại để nhận input là dữ liệu, kiểm tra kiểu và xử lý bằng method Java thông thường.

## 25. Nguyên tắc sử dụng

1. **`@Value` inject một giá trị vào bean Spring**, không tự tạo bean và không có tác dụng trên object tự tạo bằng `new`.
2. **`${...}` là property placeholder**: lấy giá trị từ Spring Environment.
3. **`${key:default}`** đưa ra default khi không tìm thấy key; không thay thế validation.
4. **`#{...}` là SpEL**: đánh giá biểu thức, không đơn thuần tra cứu property.
5. Có thể kết hợp hai cú pháp, ví dụ `#{${app.limit:10} * 2}`, nhưng phải hiểu thứ tự resolve và đảm bảo dữ liệu đưa vào expression là đáng tin cậy.
6. Với scalar types như String, int và boolean, Spring thường chuyển kiểu tự động.
7. **Constructor injection** thường tốt hơn field injection vì dependency tường minh, field có thể final và dễ unit test.
8. `@Value` không phải cơ chế tự cập nhật cấu hình sau startup.
9. **`@ConfigurationProperties`** phù hợp hơn với nhiều giá trị có cùng prefix, nested objects, list/map và validation.
10. **`@ConditionalOnProperty`** quyết định có đăng ký bean hay không; `@Value` chỉ inject giá trị cho bean.
11. Không dùng SpEL làm nơi thực thi business logic phức tạp hoặc đánh giá expression được ghép từ input không tin cậy.
12. Với cấu hình bắt buộc và nhạy cảm, ưu tiên fail-fast, validate và quản lý secret đúng cách.

Khi cần lấy một giá trị cấu hình, hãy đặt câu hỏi: **“Mình đang cần đọc một property, tính một biểu thức, hay bind cả một nhóm cấu hình?”** Câu trả lời lần lượt dẫn tới property placeholder `${...}`, SpEL `#{...}` hoặc một typed configuration object.
