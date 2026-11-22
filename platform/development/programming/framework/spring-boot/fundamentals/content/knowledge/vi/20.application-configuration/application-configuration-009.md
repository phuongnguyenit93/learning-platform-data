# Binding vào JavaBean, constructor hoặc record theo phiên bản

Spring Boot cho phép lấy cấu hình từ `application.yml`, `application.properties`, biến môi trường, command-line arguments và các `PropertySource` khác rồi **bind** (ánh xạ/chuyển đổi) thành các object Java có kiểu rõ ràng. Cơ chế này thường được sử dụng qua `@ConfigurationProperties`.

Có ba kiểu tổ chức class đích thường gặp:

1. **JavaBean binding:** tạo object bằng constructor không tham số rồi thiết lập các thuộc tính qua setter hoặc các mutable property phù hợp.
2. **Constructor binding:** Spring Boot đọc các giá trị cấu hình, chuyển kiểu rồi truyền chúng vào constructor, rất phù hợp cho object bất biến.
3. **Record binding:** Java record định nghĩa dữ liệu bất biến gọn hơn; Spring Boot có thể dùng canonical constructor của record để bind cấu hình.

Điểm cần chú ý nhất là **cách kích hoạt constructor binding và vị trí annotation khác nhau theo dòng Spring Boot**. Trong Boot 2.x, đặc biệt 2.2–2.7, class immutable thông thường cần `@ConstructorBinding` ở cấp class; từ Boot 3, một constructor có tham số duy nhất thường được suy luận tự động, còn `@ConstructorBinding` được chuyển sang cấp constructor khi cần chỉ rõ constructor được chọn.

## 1. Cơ chế binding phục vụ nhu cầu gì?

Giả sử ứng dụng có các cấu hình:

~~~yaml
app:
  notification:
    enabled: true
    sender-name: "Catalog Service"
    retry-count: 3
    connect-timeout: 5s
~~~

Có thể truy cập từng giá trị bằng `Environment` hoặc `@Value`, nhưng khi một nhóm cấu hình có nhiều thuộc tính, việc đọc rời rạc làm code khó quản lý:

~~~java
@Value("${app.notification.retry-count:3}")
private int retryCount;
~~~

Thay vào đó, một class cấu hình có kiểu rõ ràng:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {
    // enabled, senderName, retryCount, connectTimeout
}
~~~

Sau khi được đăng ký đúng cách, Spring Boot Binder sẽ đọc các property có prefix `app.notification` và chuyển chúng sang các field/constructor parameter tương ứng.

Ví dụ ánh xạ:

| Property trong YAML | Java property | Kiểu |
|---|---|---|
| `app.notification.enabled` | `enabled` | `boolean` |
| `app.notification.sender-name` | `senderName` | `String` |
| `app.notification.retry-count` | `retryCount` | `int` |
| `app.notification.connect-timeout` | `connectTimeout` | `Duration` |

Đây là **relaxed binding**: tên `sender-name` trong configuration có thể bind vào Java property `senderName`. Định dạng kebab-case trong file cấu hình và prefix giúp đặt tên nhất quán.

### Binding không chỉ là sao chép chuỗi

Binder còn thực hiện conversion:

- `"true"` thành `boolean`.
- `"3"` thành `int`.
- `"5s"` thành `Duration.ofSeconds(5)`.
- Các giá trị phù hợp thành enum, list, map, `DataSize` và nhiều kiểu khác.
- Có thể sử dụng converter tùy chỉnh khi kiểu dữ liệu không có cách chuyển mặc định phù hợp.

Các kiểu này giúp lỗi cấu hình được phát hiện tại giai đoạn binding/validation, thay vì chỉ xuất hiện khi một service tự parse chuỗi trong lúc xử lý request.

## 2. @ConfigurationProperties và việc đăng ký class cấu hình

`@ConfigurationProperties` thuộc:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
~~~

Annotation mô tả **prefix và hợp đồng binding**. Nó không nhất thiết làm class được đăng ký thành một Spring bean nếu không có cơ chế đăng ký phù hợp.

Các cách phổ biến:

| Cách đăng ký | Mục đích |
|---|---|
| `@ConfigurationPropertiesScan` | Tìm class `@ConfigurationProperties` trong package cần quét |
| `@EnableConfigurationProperties(MyProperties.class)` | Đăng ký tường minh một hoặc nhiều properties type |
| `@Component` cùng `@ConfigurationProperties` | JavaBean do component scanning tạo rồi được bind |
| `@Bean` cùng `@ConfigurationProperties` | Bind vào bean được tạo bởi factory method; hữu ích với đối tượng bên thứ ba có setter |

**Constructor binding không dùng cho bean được tạo bởi cơ chế Spring thông thường** như `@Component` hoặc `@Bean` factory method. Muốn constructor binding cho class cấu hình, hãy để Boot đăng ký nó qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

### Ví dụ bật configuration properties scan

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` mặc định quét từ package của class chứa annotation xuống các package con. Có thể chỉ rõ `basePackages` hoặc `basePackageClasses` nếu properties class nằm ở nơi khác.

### Ví dụ đăng ký tường minh

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

Khi đã đăng ký qua `@EnableConfigurationProperties`, không cần đánh dấu `NotificationProperties` thêm `@Component`. Một ứng dụng cũng không cần dùng cả scan và enable cho cùng một properties class nếu chỉ muốn tạo một bean duy nhất.

## 3. JavaBean binding: tạo object rồi gọi setter

JavaBean binding là mô hình truyền thống của Spring Boot. Class có constructor không tham số và các phương thức getter/setter để Binder thao tác trên thuộc tính.

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {

    private boolean enabled;
    private String senderName;
    private int retryCount = 3;
    private Duration connectTimeout = Duration.ofSeconds(5);

    public NotificationProperties() {
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public void setSenderName(String senderName) {
        this.senderName = senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Với YAML ở phần đầu bài học, Binder thiết lập các thuộc tính bằng giá trị cấu hình tương ứng. Trường `retryCount` và `connectTimeout` có sẵn default trong Java khi property không được khai báo.

### 3.1. Trình tự JavaBean binding

~~~text
Đăng ký NotificationProperties bean definition
                  |
                  v
        Tạo object (no-args ctor)
                  |
                  v
     Binder đọc app.notification.*
                  |
                  v
     Convert giá trị sang kiểu Java
                  |
                  v
       Gọi setter / bind property
                  |
                  v
        Validation (nếu cấu hình)
                  |
                  v
      Bean được sử dụng trong service
~~~

Đây là mô tả khái quát. Binding được tích hợp với lifecycle và các processor của Spring Boot.

Ưu điểm:

- Dễ hiểu với những dự án dùng JavaBean truyền thống.
- Có thể cung cấp default bằng field initializer.
- Thuận tiện khi tích hợp object mutable của thư viện bên ngoài.
- Phù hợp với nhiều dự án Spring Boot 1.x/2.x có setter-based configuration.

Hạn chế:

- Object có thể bị sửa sau khi bind vì có setter công khai.
- Nhiều field và setter khiến class dài.
- Khi dùng ở nhiều bean, phải tránh việc code tùy tiện thay đổi cấu hình giữa lúc ứng dụng hoạt động.
- Bất biến về dữ liệu khó bảo đảm ở cấp constructor.

### 3.2. Nested properties theo JavaBean style

Ví dụ:

~~~yaml
app:
  mail:
    host: smtp.example.test
    retry:
      max-attempts: 4
      delay: 2s
~~~

JavaBean:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host;
    private Retry retry = new Retry();

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public static class Retry {
        private int maxAttempts = 3;
        private Duration delay = Duration.ofSeconds(1);

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Duration getDelay() {
            return delay;
        }

        public void setDelay(Duration delay) {
            this.delay = delay;
        }
    }
}
~~~

Nested object `Retry` được tạo sẵn nên các thuộc tính con có thể được bind vào instance đó. Với nested JavaBean không có setter/constructor/instance thích hợp, khả năng bind có thể bị giới hạn; hãy thiết kế rõ cách tạo object con.

### 3.3. Không phải mọi field đều cần một setter riêng

Một số cấu trúc mutable đã được khởi tạo, như `Map` hoặc nested object với getter, có thể được Binder cập nhật tùy kiểu và cách bind. Tuy nhiên, để tránh phụ thuộc hành vi khó đoán, với cấu hình mutable thông thường nên cung cấp setter cho những thuộc tính được cấu hình từ bên ngoài, hoặc dùng constructor binding nếu muốn bất biến.

## 4. Constructor binding: tạo object từ giá trị cấu hình

Constructor binding đưa các giá trị đã convert vào constructor. Object được tạo **sau khi** dữ liệu cấu hình phù hợp được phân giải:

~~~java
public final class NotificationProperties {
    private final boolean enabled;
    private final String senderName;
    private final int retryCount;

    public NotificationProperties(
            boolean enabled,
            String senderName,
            int retryCount) {
        this.enabled = enabled;
        this.senderName = senderName;
        this.retryCount = retryCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

Nhờ có `final` và không có setter, cấu hình không thể được thay đổi bằng các setter sau khi object được tạo.

Trong phần này, class `NotificationProperties` sẽ được minh họa riêng theo phiên bản. **Không copy nhiều phiên bản class cùng tên vào một package của cùng dự án**; các đoạn code đại diện cho các lựa chọn khác nhau.

## 5. Constructor binding trong Spring Boot 2.2–2.7

Spring Boot 2.2 bổ sung hỗ trợ constructor binding cho `@ConfigurationProperties`. Với class Java thông thường trong dòng Boot 2.x, cách sử dụng tiêu biểu là đặt `@ConstructorBinding` **trên class**:

~~~java
package com.example.catalog.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.ConstructorBinding;

@ConstructorBinding
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {

    private final boolean enabled;
    private final String senderName;
    private final int retryCount;

    public NotificationProperties(
            boolean enabled,
            String senderName,
            int retryCount) {
        this.enabled = enabled;
        this.senderName = senderName;
        this.retryCount = retryCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

Điểm chú ý:

- Import Boot 2.x: `org.springframework.boot.context.properties.ConstructorBinding`.
- Annotation được khai báo trên **class** theo API của dòng Boot 2.x.
- Properties class phải được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, không phải `@Component`.
- Constructor parameters phải có tên phù hợp với thuộc tính. Trong Java class thông thường, cần biên dịch với metadata tên tham số phù hợp, thường là flag `-parameters`.
- Nếu constructor có nhiều tham số, thứ tự tham số trong constructor không thay đổi tên property; Binder đối chiếu tên tham số với tên thuộc tính sau relaxed binding.

Ví dụ Bean registration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

Nếu sử dụng Spring Boot plugin và convention build tương ứng, flag `-parameters` thường được cấu hình phù hợp. Với cấu hình build custom, hãy kiểm tra compiler arguments khi binder không nhận được tên tham số.

### 5.1. Tránh @Component với constructor binding trên Boot 2.x

Không viết:

~~~java
@Component
@ConstructorBinding
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {
    // ...
}
~~~

Class `@Component` được tạo theo cơ chế bean constructor injection thông thường; các tham số primitive/string của constructor có thể bị Spring hiểu là dependency bean cần inject, không phải property từ Environment theo constructor binding.

Hãy dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` như các ví dụ trước. Điều này áp dụng cả khi class được đăng ký bởi `@Bean` hoặc import thông thường: constructor binding không thể thay thế cách container tạo bean bằng factory method.

## 6. Constructor binding trong Spring Boot 3.x

Từ Boot 3, với một `@ConfigurationProperties` class có **một constructor tham số phù hợp**, constructor binding thường được suy luận tự động. Không cần `@ConstructorBinding` trên class.

~~~java
package com.example.catalog.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public final class NotificationProperties {

    private final boolean enabled;
    private final String senderName;
    private final int retryCount;

    public NotificationProperties(
            boolean enabled,
            String senderName,
            int retryCount) {
        this.enabled = enabled;
        this.senderName = senderName;
        this.retryCount = retryCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

Chỉ cần đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. `enabled`, `senderName` và `retryCount` được lấy từ cùng prefix cấu hình.

### 6.1. Khi class có nhiều constructor

Nếu có nhiều constructor và cần chỉ rõ constructor mà Binder dùng, Boot 3 cung cấp annotation:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
~~~

Đặt nó trên **constructor** được chọn:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public final class NotificationProperties {

    private final String senderName;
    private final int retryCount;

    @ConstructorBinding
    public NotificationProperties(
            String senderName,
            int retryCount) {
        this.senderName = senderName;
        this.retryCount = retryCount;
    }

    public NotificationProperties() {
        this("Catalog Service", 3);
    }

    public String getSenderName() {
        return senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

Lưu ý rằng trong Boot 3, import `org.springframework.boot.context.properties.bind.ConstructorBinding` được dùng trên constructor. Việc đặt annotation đó lên type như kiểu Boot 2 có thể gây lỗi biên dịch vì target annotation đã thay đổi.

Nếu class dùng constructor `@Autowired` để inject các Spring bean thì đó là cơ chế tạo bean của Spring, không phải constructor binding configuration properties. Không nên dùng constructor binding để cố trộn dependency injection của Spring vào properties holder.

### 6.2. Java 17 và baseline phiên bản

Spring Boot 3 yêu cầu Java 17 trở lên. Vì vậy, Java record là lựa chọn tự nhiên cho những properties class bất biến trong dự án Boot 3.

Nếu ứng dụng còn ở Boot 2.x, hãy kiểm tra phiên bản Java và mức hỗ trợ record của bản Boot hiện tại trước khi áp dụng. Với Boot 2.7 trên Java 17, record binding là một trường hợp được hỗ trợ tốt để minh họa.

## 7. Record binding: immutable properties ngắn gọn

Java record giúp biểu diễn một tập dữ liệu bất biến qua các record components và canonical constructor.

Ví dụ Boot 3:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        String senderName,
        int retryCount,
        Duration connectTimeout) {
}
~~~

Khi `NotificationProperties` được đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, Binder có thể dùng canonical constructor của record để cung cấp giá trị.

Cách sử dụng ở service:

~~~java
package com.example.catalog.service;

import com.example.catalog.config.NotificationProperties;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }

    public void printConfiguration() {
        System.out.println(properties.senderName());
        System.out.println(properties.retryCount());
        System.out.println(properties.connectTimeout());
    }
}
~~~

Chú ý cú pháp accessor của record: `properties.senderName()`, không phải `properties.getSenderName()` như JavaBean. Record tự sinh constructor, accessor, `equals()`, `hashCode()` và `toString()` phù hợp với record components.

### 7.1. Record trong Spring Boot 2.7

Với Spring Boot 2.7 và một record có một canonical constructor thông thường, Boot cũng có thể tự suy luận constructor binding mà không cần đặt `@ConstructorBinding` trên record.

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        String senderName,
        int retryCount) {
}
~~~

Không nên suy luận rằng “mọi bản Boot 2.x đều bind record hệt Boot 3”. Record là tính năng Java mới hơn các dòng Boot 2 đầu tiên; khi hỗ trợ một phiên bản cũ cụ thể, hãy dựa vào tài liệu/API của đúng phiên bản đó.

### 7.2. Record không có setter

Không thể sử dụng JavaBean setter binding cho một record vì record components là final và không có setter. Cũng không thể kỳ vọng thay đổi field sau khi tạo record.

Nếu muốn một cấu hình có thể thay đổi trực tiếp qua setter do Spring quản lý, JavaBean là lựa chọn tự nhiên hơn. Tuy nhiên, việc cấu hình động ở runtime là một bài toán riêng: dùng record hay JavaBean không làm Spring Boot tự động rebind mọi bean khi file YAML thay đổi.

### 7.3. Cẩn thận với toString() của record

Record tự sinh `toString()` hiển thị giá trị các component. Nếu một record chứa mật khẩu, token hoặc khóa bí mật, **đừng log nguyên object** chỉ vì tiện quan sát cấu hình.

~~~java
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        String endpoint,
        String apiToken) {
}
~~~

Lệnh `System.out.println(properties)` có nguy cơ làm lộ `apiToken` vào log. Hãy loại bỏ hoặc che giá trị nhạy cảm khi log và cân nhắc thiết kế riêng kiểu dữ liệu chứa secret.

## 8. Bảng so sánh theo các dòng phiên bản

| Dòng Spring Boot | JavaBean + setters | Constructor binding class thường | Record |
|---|---|---|---|
| Boot 1.x / 2.0–2.1 | Cách phổ biến | Chưa có cơ chế `@ConstructorBinding` như Boot 2.2+ | Không phải lựa chọn chính cho các dòng này |
| Boot 2.2–2.6 | Hỗ trợ | Dùng `@ConstructorBinding` theo API Boot 2, đặt trên type | Phụ thuộc Java và khả năng hỗ trợ của phiên bản cụ thể |
| Boot 2.7 | Hỗ trợ | `@ConstructorBinding` đặt trên class | Record một canonical constructor có thể được suy luận |
| Boot 3.x | Hỗ trợ | Constructor đơn thường được suy luận; nhiều constructor có thể chỉ rõ bằng annotation cấp constructor | Lựa chọn phù hợp, thường không cần annotation với canonical constructor đơn |

Các mốc quan trọng:

- **Boot 2.2:** giới thiệu constructor binding cho `@ConfigurationProperties`.
- **Boot 2.7:** hỗ trợ tốt mô hình constructor/record binding trong nhánh Boot 2.
- **Boot 3:** chuyển namespace/target của `@ConstructorBinding` và suy luận constructor binding cho trường hợp một constructor tham số.
- **Java record:** yêu cầu phiên bản Java hỗ trợ record; Boot 3 có baseline Java 17.

Đừng nâng cấp bằng cách chỉ thay dependency mà giữ nguyên import `@ConstructorBinding` của Boot 2. Code có thể cần xóa annotation ở cấp class hoặc chuyển nó sang đúng constructor trong Boot 3.

## 9. Nested immutable properties với record

Record có thể chứa nested record để biểu diễn cấu hình có phân cấp:

~~~yaml
app:
  client:
    base-url: https://api.example.test
    retry:
      max-attempts: 5
      backoff: 250ms
~~~

Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Retry retry) {

    public record Retry(
            int maxAttempts,
            Duration backoff) {
    }
}
~~~

Cách dùng:

~~~java
String url = properties.baseUrl();
int attempts = properties.retry().maxAttempts();
Duration backoff = properties.retry().backoff();
~~~

Nếu toàn bộ nhóm `retry` không có trong cấu hình, giá trị nested object có thể là `null` theo semantics binding/defaults của constructor. Tránh mặc định rằng tất cả nested records đều được tạo tự động với giá trị rỗng.

Có thể yêu cầu một nested object mặc định hoặc đặt default tường minh bằng `@DefaultValue` trong những phiên bản hỗ trợ:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("1s") Duration backoff) {
    }
}
~~~

`@DefaultValue` không có value trên tham số nested có thể hướng Binder tạo nested object dù không có các property con, nếu kiểu nested có cấu trúc bind phù hợp. Các giá trị mặc định bên trong `Retry` được dùng khi thông tin tương ứng không được cung cấp. Với thiết kế bắt buộc phải có `baseUrl`, nên bổ sung validation.

## 10. Giá trị mặc định: JavaBean và constructor/record khác nhau

### 10.1. JavaBean: field initializer

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private int retryCount = 3;

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

Nếu `app.mail.retry-count` không có, giá trị khởi tạo `3` vẫn được giữ lại trong trường hợp binder không ghi đè.

### 10.2. Record: @DefaultValue

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        @DefaultValue("3") int retryCount,
        @DefaultValue("5s") Duration timeout) {
}
~~~

Đây là cách khai báo default rõ ràng ở vị trí constructor parameter/record component.

Nếu không có default:

- Primitive như `int` sẽ nhận giá trị mặc định kiểu primitive nếu property vắng mặt.
- Reference type như `String` hoặc `Duration` có thể là `null`.
- Nếu thiếu một giá trị bắt buộc, nên dùng validation thay vì cho rằng Binder luôn coi missing property là lỗi.

`@DefaultValue` của Binder không phải là `@Value` của Spring injection. Hai annotation có vai trò khác nhau.

### 10.3. Constructor tự quyết định giá trị mặc định

Một class immutable cũng có thể xử lý default trong constructor:

~~~java
@ConfigurationProperties(prefix = "app.report")
public final class ReportProperties {

    private final String outputFolder;

    public ReportProperties(String outputFolder) {
        this.outputFolder = (outputFolder == null || outputFolder.isBlank())
                ? "reports"
                : outputFolder;
    }

    public String getOutputFolder() {
        return outputFolder;
    }
}
~~~

Cách này hữu ích khi default cần tính toán hoặc chuẩn hóa dữ liệu. Nhưng logic trong properties constructor nên đơn giản, không thực hiện I/O hoặc gọi Spring beans.

## 11. Validation với @Validated

Binding chuyển dữ liệu sang object; **validation** kiểm tra dữ liệu có hợp lệ theo quy tắc ứng dụng hay không.

Ví dụ Boot 3 với record:

~~~java
package com.example.catalog.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @NotBlank String senderName,
        @Min(1) int retryCount) {
}
~~~

Khi bean được bind và validation phù hợp được kích hoạt, giá trị thiếu hoặc không thỏa constraint có thể làm context khởi động thất bại với thông báo lỗi cấu hình.

Thông thường dự án cần dependency validation, ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Với Boot 3, annotation constraint dùng namespace `jakarta.validation.*`. Với Boot 2.x dựa trên Spring Framework 5 và Bean Validation cũ, thường là `javax.validation.*`.

### 11.1. Nested validation

Với cấu hình lồng nhau:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotBlank String baseUrl,
        @Valid Retry retry) {

    public record Retry(
            @Min(1) int maxAttempts) {
    }
}
~~~

`@Valid` giúp áp dụng validation vào object con khi object đó được tạo và có validator tương ứng. Nếu thuộc tính nested bắt buộc phải có, kết hợp `@NotNull` hoặc default phù hợp; `@Valid` một mình không mặc nhiên bắt buộc một reference khác `null`.

Không dùng validation thay cho conversion. Ví dụ một chuỗi không thể chuyển thành `Duration` có thể gây lỗi binding ngay trước khi validation constraint chạy.

## 12. Bind vào bean của thư viện bên thứ ba

Có những class bên thứ ba không có `@ConfigurationProperties` và bạn không thể sửa source. Nếu chúng có cách khởi tạo phù hợp và setter để nhận property, có thể đăng ký qua `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.legacy-client")
    LegacyClientSettings legacyClientSettings() {
        return new LegacyClientSettings();
    }
}
~~~

Giả sử `LegacyClientSettings` có các setter tương ứng như `setHost`, `setPort`. Boot sẽ bind giá trị vào object được tạo bởi factory method.

Đây là **JavaBean/property binding**, không phải constructor binding; vì factory method đã tự tạo object.

Tránh cố sử dụng constructor binding trên một class nhận từ `@Bean`:

~~~java
// Không dùng @ConstructorBinding để yêu cầu Binder tạo lại object
// đã được một @Bean factory method khởi tạo sẵn.
@Bean
@ConfigurationProperties(prefix = "app.legacy-client")
LegacyClientSettings legacyClientSettings() {
    return new LegacyClientSettings();
}
~~~

Nếu đối tượng thứ ba là immutable và không có setter, hãy bind vào một record/class properties do bạn kiểm soát, sau đó dùng các giá trị đó để xây object bất biến trong phương thức `@Bean`.

~~~java
@ConfigurationProperties(prefix = "app.legacy-client")
public record LegacyClientProperties(String host, int port) {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(LegacyClientProperties.class)
class ClientConfiguration {

    @Bean
    LegacyClient legacyClient(LegacyClientProperties properties) {
        return new LegacyClient(properties.host(), properties.port());
    }
}
~~~

Cách này tách rõ quá trình **bind dữ liệu cấu hình** và quá trình **tạo instance thư viện**.

## 13. Relaxed binding và nguồn cấu hình

`@ConfigurationProperties` hỗ trợ cách viết tên property đa dạng. Ví dụ Java property `connectTimeout` có thể nhận cấu hình từ:

~~~properties
app.client.connect-timeout=5s
~~~

Hoặc YAML:

~~~yaml
app:
  client:
    connect-timeout: 5s
~~~

Với environment variables, nên theo quy tắc chuyển tên canonical của Spring Boot sang uppercase và underscore, chẳng hạn:

~~~text
APP_CLIENT_CONNECTTIMEOUT=5s
~~~

Trong môi trường thực tế, cách chuyển property sang biến môi trường có quy tắc riêng về dấu chấm, dấu gạch ngang và index của list; tránh tự suy đoán tên từ một biểu thức camelCase nếu đang gặp vấn đề bind.

### 13.1. Property source precedence

Nếu cùng một property tồn tại ở nhiều nguồn (ví dụ `application.yml`, environment variable và command-line argument), Spring Boot chọn giá trị theo thứ tự ưu tiên `PropertySource` phù hợp với phiên bản và cách khởi động.

Có thể xem cấu hình hiệu lực qua `Environment` hoặc các công cụ chẩn đoán phù hợp. Không nên hard-code một thứ tự ưu tiên do trí nhớ khi ứng dụng có config import, profile files hoặc property source tùy chỉnh.

### 13.2. Đừng dùng @Value thay cho cả một nhóm properties

`@Value` phù hợp với một vài biểu thức đơn lẻ, nhưng không có cùng mô hình relaxed binding cho cả một nhóm typed/nested properties như `@ConfigurationProperties`. Với nhiều property liên quan, class cấu hình thường dễ kiểm thử, validate và tài liệu hóa hơn.

### 13.3. Annotation processor hỗ trợ metadata

Dự án có thể thêm `spring-boot-configuration-processor` để tạo metadata gợi ý configuration properties cho IDE:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Processor giúp tạo completion/metadata cho property names và mô tả. Nó **không phải yêu cầu để runtime binding hoạt động**. Nếu thiếu metadata, ứng dụng vẫn có thể bind bình thường nhưng IDE có thể ít gợi ý hơn.

## 14. Lỗi thường gặp khi chuyển từ Boot 2 sang Boot 3

### 14.1. @ConstructorBinding sai import hoặc vị trí

Boot 2.x:

~~~java
import org.springframework.boot.context.properties.ConstructorBinding;

@ConstructorBinding
@ConfigurationProperties(prefix = "app.report")
public class ReportProperties {
    // Một constructor nhận các property.
}
~~~

Boot 3.x:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.report")
public class ReportProperties {

    @ConstructorBinding
    public ReportProperties(String format) {
        // ...
    }
}
~~~

Trong Boot 3, nếu class chỉ có một constructor có tham số và không có ambiguity, thông thường **bỏ hẳn annotation** cũng được. Ví dụ Boot 3 ở trên chỉ minh họa vị trí mới của annotation; không phải mọi class đều phải dùng nó.

### 14.2. Quên đăng ký properties bean

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(String format) {
}
~~~

Chỉ có annotation trên record không bảo đảm bean này đã được đăng ký. Hãy thêm `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(ReportProperties.class)` trong cấu hình được Spring xử lý.

### 14.3. Dùng @Component cho immutable constructor binding

~~~java
@Component
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(String format) {
}
~~~

Cách trên làm class đi qua cơ chế component tạo bean thông thường, không phải kiểu đăng ký constructor binding được Boot thiết kế. Hãy bỏ `@Component` và đăng ký record qua configuration-properties scan/enable.

### 14.4. Không có tên tham số constructor

Trong class Java thông thường, Binder cần biết tham số constructor tương ứng property nào. Khi lỗi binding xảy ra ở class immutable, kiểm tra `-parameters` và compiler/plugin thay vì chỉ đổi tên field.

Record có metadata canonical components rõ ràng hơn, nhưng vẫn cần sử dụng phiên bản framework hỗ trợ record binding phù hợp.

### 14.5. Thiếu validation dependency

Có `@Validated` và constraint annotation không bảo đảm validation sẽ hoạt động nếu không có validator implementation tương ứng trên classpath. Kiểm tra starter validation, namespace Javax/Jakarta và xem lỗi gốc khi context khởi động.

### 14.6. Nhầm cấu hình runtime với mutable object

Có setter không đồng nghĩa bean tự cập nhật khi file property thay đổi. Spring Boot thường bind cấu hình trong lúc tạo bean và không tự theo dõi rồi cập nhật mọi properties bean. Nếu ứng dụng cần refresh runtime, phải thiết kế cơ chế refresh/configuration cụ thể, xử lý concurrency và tính nhất quán trạng thái.

## 15. Kiểm thử JavaBean, constructor và record binding

Có thể sử dụng `ApplicationContextRunner` để kiểm thử properties class trong một context nhỏ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class NotificationPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotificationProperties.class)
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsPropertiesFromEnvironment() {
        runner
                .withPropertyValues(
                        "app.notification.enabled=true",
                        "app.notification.sender-name=Catalog Service",
                        "app.notification.retry-count=4",
                        "app.notification.connect-timeout=2s"
                )
                .run(context -> {
                    NotificationProperties properties =
                            context.getBean(NotificationProperties.class);

                    assertThat(properties.enabled()).isTrue();
                    assertThat(properties.senderName())
                            .isEqualTo("Catalog Service");
                    assertThat(properties.retryCount()).isEqualTo(4);
                    assertThat(properties.connectTimeout())
                            .isEqualTo(java.time.Duration.ofSeconds(2));
                });
    }
}
~~~

Đoạn test giả định `NotificationProperties` là **record Boot 3** như phần 7, vì nó dùng accessor `enabled()`, `senderName()`. Nếu thử JavaBean, thay bằng các getter `isEnabled()`, `getSenderName()` tương ứng.

Có thể bổ sung các test:

1. Property đầy đủ: tất cả field/record components được bind đúng.
2. Property thiếu: default có được áp dụng đúng không.
3. Dữ liệu sai kiểu: binding có báo lỗi rõ không.
4. Giá trị vi phạm validation: context có từ chối khởi tạo không.
5. Nested object: có được bind đúng hay trở thành `null` khi thiếu.
6. Bean được tạo qua `@Bean`: setter binding có hoạt động với class của thư viện bên ngoài không.
7. Nâng cấp Boot: cùng file YAML có bind ra cấu trúc dữ liệu tương đương sau khi đổi annotation/namespace không.

Không chỉ kiểm tra constructor có chạy; hãy kiểm tra giá trị từ `Environment` thực sự đã được chuyển và lưu vào properties object.

## 16. Phân biệt bind properties và dependency injection

Giả sử có hai constructor:

~~~java
public NotificationService(NotificationProperties properties) {
    this.properties = properties;
}
~~~

và:

~~~java
public NotificationProperties(boolean enabled, int retryCount) {
    this.enabled = enabled;
    this.retryCount = retryCount;
}
~~~

Constructor thứ nhất là **constructor injection của Spring**: container tìm bean `NotificationProperties` rồi inject vào service.

Constructor thứ hai, khi properties class được đăng ký bằng cơ chế constructor binding tương ứng, là **constructor binding của Spring Boot Binder**: Binder đọc giá trị cấu hình như `app.notification.enabled` và `app.notification.retry-count` rồi truyền vào constructor.

Hai cơ chế có thể kết hợp trong cùng ứng dụng nhưng phục vụ mục đích khác nhau. Constructor binding không phải cách inject `DataSource`, `RestClient` hay service bean vào properties class. Class `@ConfigurationProperties` nên giữ vai trò là cấu trúc dữ liệu cấu hình; các dependency nghiệp vụ hãy inject vào service hoặc configuration class sử dụng nó.

~~~text
application.yml / ENV / command-line
                 |
                 v
          Spring Boot Binder
                 |
                 v
        NotificationProperties
                 |
            (Spring bean)
                 |
                 v
     constructor injection vào
        NotificationService
                 |
                 v
          Nghiệp vụ sử dụng
~~~

## 17. Khi nào chọn cách nào?

| Tình huống | Lựa chọn nên cân nhắc |
|---|---|
| Dự án legacy Boot 2.x, nhiều class mutable sẵn có | JavaBean binding |
| Bind cấu hình vào object của thư viện có setter | `@Bean` + `@ConfigurationProperties` |
| Cần cấu hình bất biến trong Boot 2.2–2.7 | Constructor binding theo API Boot 2 |
| Cần immutable class trong Boot 3 | Một constructor tham số; thường không cần annotation |
| Dự án Java 17+, muốn properties class ngắn gọn | Record + configuration-properties scan/enable |
| Nested immutable configuration | Nested records/classes dùng constructor binding |
| Cần default rõ ràng ở constructor/record component | `@DefaultValue` hoặc logic constructor đơn giản |
| Cần phát hiện thiếu/sai cấu hình lúc startup | `@Validated` + Bean Validation |
| Cấu hình cần nhiều bean dependency hoặc logic mở kết nối | Bind properties riêng rồi tạo bean chức năng trong `@Configuration` |

**Quy tắc thiết kế:** Chọn kiểu dữ liệu dựa trên nhu cầu về bất biến, khả năng tương thích phiên bản và cách đăng ký bean. Không chọn một kiểu chỉ vì ít code hơn nếu nó làm phương thức binding hoặc lifecycle khó hiểu.

## 18. Các nguyên tắc cần ghi nhớ

- `@ConfigurationProperties` nhóm nhiều property thành một object Java có kiểu rõ ràng.
- JavaBean binding thường dùng object mutable và setter; constructor binding tạo immutable object từ constructor parameters.
- Record phù hợp với immutable configuration và sử dụng canonical constructor.
- Dòng Boot 2.2–2.7 dùng `@ConstructorBinding` cấp class với package `org.springframework.boot.context.properties` cho class Java truyền thống.
- Dòng Boot 3 thường tự suy luận constructor duy nhất; annotation khi cần là `org.springframework.boot.context.properties.bind.ConstructorBinding` **trên constructor**.
- Constructor-bound properties cần đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`; không dùng `@Component` hoặc `@Bean` làm đường tạo bean rồi kỳ vọng Binder gọi constructor lại.
- Setter binding vẫn hữu ích cho mutable JavaBean và đối tượng bên thứ ba.
- Cần chú ý default, nested nullability, validation, compiler metadata và version baseline của Java.
- Với Boot 3, validation annotations thuộc `jakarta.validation`; với Boot 2.x thường thuộc `javax.validation`.
- Property object là dữ liệu cấu hình, không phải service locator hay nơi thực thi nghiệp vụ.

Khi hiểu đúng **ai tạo object** (Spring BeanFactory hay Boot Binder), **object được tạo bằng setter hay constructor** và **dòng phiên bản nào đang dùng**, việc binding cấu hình sẽ dễ dự đoán, kiểm thử và bảo trì hơn. Các ứng dụng mới trên Spring Boot 3 thường ưu tiên record hoặc class immutable cho cấu hình không cần thay đổi; các ứng dụng đang nâng cấp từ Boot 2 nên xử lý chính xác thay đổi của `@ConstructorBinding`, đăng ký bean và namespace validation để tránh lỗi khi khởi động.
