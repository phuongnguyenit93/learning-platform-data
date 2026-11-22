# @Qualifier và định danh nhóm dependency

Trong Spring, một interface có thể có nhiều implementation cùng tồn tại trong một application context. Ví dụ, ứng dụng có thể gửi thông báo bằng email, SMS hoặc ghi ra console; đọc dữ liệu từ cache trong bộ nhớ hoặc cache phân tán; gọi một dịch vụ thanh toán thử nghiệm hoặc cổng thanh toán thật. Khi một service chỉ khai báo cần một bean theo kiểu interface, Spring có thể không biết phải chọn implementation nào.

**`@Qualifier` giúp thu hẹp tập bean phù hợp theo một nhãn hoặc tiêu chí có ý nghĩa.** Nó thường được dùng cùng constructor injection để chỉ ra dependency cụ thể mà một thành phần cần. Qualifier cũng có thể được dùng để nhóm nhiều bean cùng vai trò rồi inject cả nhóm vào một collection.

Trong chương **Chọn bean** của *Spring Boot Fundamentals*, cần phân biệt ba khái niệm:

- **Bean type:** kiểu class hoặc interface mà bean cung cấp.
- **Bean name:** tên định danh bean trong Spring container.
- **Qualifier:** metadata dùng để mô tả hoặc lọc ứng viên phù hợp tại điểm inject.

Ba khái niệm có thể liên quan nhưng không đồng nghĩa. Hiểu đúng chúng giúp tránh lỗi nhiều bean cùng kiểu, đồng thời tổ chức được các nhóm dependency theo chức năng, môi trường hoặc đặc tính mà ứng dụng cần.

## 1. Vì sao Spring cần qualifier?

Giả sử có hợp đồng gửi thông báo:

```java
package com.example.notification;

public interface NotificationSender {
    void send(String recipient, String message);
}
```

Ứng dụng có hai implementation:

```java
package com.example.notification;

import org.springframework.stereotype.Component;

@Component
public class EmailNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("Email to " + recipient + ": " + message);
    }
}
```

```java
package com.example.notification;

import org.springframework.stereotype.Component;

@Component
public class SmsNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS to " + recipient + ": " + message);
    }
}
```

Giả sử cả hai class nằm trong phạm vi component scan. Spring sẽ đăng ký hai bean có cùng kiểu interface `NotificationSender`. Bây giờ một service yêu cầu:

```java
@Service
public class RegistrationService {

    private final NotificationSender sender;

    public RegistrationService(NotificationSender sender) {
        this.sender = sender;
    }
}
```

Constructor có một dependency kiểu `NotificationSender`, nhưng trong context có hai ứng viên cùng phù hợp. Nếu không có metadata hoặc quy tắc lựa chọn bổ sung, Spring không thể chọn một cách duy nhất và có thể báo `NoUniqueBeanDefinitionException` trong quá trình tạo bean.

Điều này không có nghĩa Spring không hỗ trợ nhiều implementation. Nhiều implementation là hoàn toàn hợp lệ. Vấn đề chỉ xuất hiện khi **một điểm inject cần một bean duy nhất nhưng tập ứng viên còn nhiều hơn một**.

## 2. @Qualifier giúp chọn bean như thế nào?

Spring cung cấp annotation:

```java
import org.springframework.beans.factory.annotation.Qualifier;
```

Ta có thể gắn qualifier tại điểm inject:

```java
@Service
public class RegistrationService {

    private final NotificationSender sender;

    public RegistrationService(
            @Qualifier("emailNotificationSender")
            NotificationSender sender
    ) {
        this.sender = sender;
    }
}
```

Trong ví dụ component scan mặc định, tên bean thường được tạo từ tên class với chữ cái đầu viết thường: `emailNotificationSender` và `smsNotificationSender`. `@Qualifier("emailNotificationSender")` yêu cầu Spring chọn ứng viên có qualifier phù hợp với giá trị đó; tên bean có thể được dùng như một tiêu chí fallback trong quá trình tìm ứng viên.

Sau khi thêm qualifier, service nhận bean email. `RegistrationService` vẫn phụ thuộc vào interface `NotificationSender`, không cần biết class cụ thể được tạo ra bằng cách nào.

### 2.1. Có thể đặt tên bean tường minh

Thay vì dựa vào tên mặc định, có thể khai báo tên bean:

```java
@Component("emailSender")
public class EmailNotificationSender implements NotificationSender {
    // ...
}
```

Điểm inject tương ứng:

```java
public RegistrationService(
        @Qualifier("emailSender") NotificationSender sender
) {
    this.sender = sender;
}
```

Với bean tạo qua Java configuration:

```java
@Configuration
class NotificationConfiguration {

    @Bean("emailSender")
    NotificationSender emailNotificationSender() {
        return new EmailNotificationSender();
    }
}
```

Tên bean được khai báo qua `@Component("...")` hoặc `@Bean("...")` là định danh trong container. Khi cần dùng một bean cụ thể, giá trị qualifier có thể trùng tên bean, nhưng nên hiểu rõ rằng **qualifier là tiêu chí lọc ứng viên; bean name là tên định danh**.

### 2.2. @Qualifier không tạo bean

Thêm:

```java
@Qualifier("email")
NotificationSender sender
```

không tự tạo ra một `EmailNotificationSender`. Spring vẫn cần có bean phù hợp trên context. Qualifier chỉ giúp xác định bean nào trong tập ứng viên đã được đăng ký.

Tương tự, Java import class hoặc thêm một dependency Maven/Gradle chỉ làm class có mặt trên classpath; điều đó không đồng nghĩa class đã được đăng ký thành bean và có thể inject.

## 3. Phân biệt bean name, type và qualifier

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Type | Bean cung cấp kiểu nào? | `NotificationSender` |
| Bean name | Bean được đăng ký dưới tên nào? | `emailSender` |
| Qualifier | Bean có đặc tính/nhãn nào để lọc ứng viên? | `email`, `external`, `reliable` |

Một bean có thể:

- Có một type cụ thể và nhiều type cha/interface.
- Có một tên bean trong context.
- Mang một hoặc nhiều qualifier có ý nghĩa.

Ví dụ:

```java
@Component("smtpSender")
@Qualifier("external")
public class SmtpNotificationSender implements NotificationSender {
    // ...
}
```

Bean trên có tên `smtpSender` và mang qualifier `external`. Hai thông tin này phục vụ hai mục đích khác nhau:

- `@Qualifier("external")` mô tả một đặc tính có ý nghĩa đối với cách chọn dependency.
- `@Component("smtpSender")` đặt tên định danh cụ thể cho bean.

Trong ứng dụng lớn, dùng tên bean làm qualifier cho mọi tình huống có thể khiến mã phụ thuộc vào chi tiết đặt tên. Qualifier theo ý nghĩa như `external`, `transactional`, `regional` hoặc `readOnly` thường diễn đạt mục đích tốt hơn.

### 3.1. Giá trị qualifier có thể khớp tên bean

Trong cơ chế phân giải dependency của Spring, giá trị `@Qualifier` được xét như một tiêu chí qualifier; tên bean cũng có thể được xét như fallback khi phù hợp. Vì vậy, ví dụ `@Qualifier("emailSender")` có thể chọn bean tên `emailSender` ngay cả khi class không có annotation `@Qualifier("emailSender")` riêng.

Tuy nhiên, không nên kết luận rằng qualifier chỉ là một cú pháp khác để gọi bean theo tên. Nó có thể lọc nhiều bean cùng mang một nhãn và có thể được biểu diễn bằng annotation tùy chỉnh với thuộc tính có kiểu.

## 4. @Primary và @Qualifier khác nhau thế nào?

`@Primary` đánh dấu một bean là ứng viên ưu tiên khi Spring cần chọn một bean duy nhất giữa nhiều ứng viên cùng kiểu. `@Qualifier` thu hẹp ứng viên theo metadata tại điểm inject.

Ví dụ đánh dấu email sender là lựa chọn mặc định:

```java
@Component
@Primary
public class EmailNotificationSender implements NotificationSender {
    // ...
}
```

Một service không khai báo qualifier:

```java
@Service
class DefaultRegistrationService {

    private final NotificationSender sender;

    DefaultRegistrationService(NotificationSender sender) {
        this.sender = sender;
    }
}
```

Nếu chỉ có một bean `@Primary` phù hợp trong tập ứng viên, Spring ưu tiên bean đó. Một service khác có thể chỉ định rõ SMS:

```java
@Service
class SecurityAlertService {

    private final NotificationSender sender;

    SecurityAlertService(
            @Qualifier("smsNotificationSender")
            NotificationSender sender
    ) {
        this.sender = sender;
    }
}
```

### 4.1. So sánh theo mục đích

| Tiêu chí | `@Primary` | `@Qualifier` |
| --- | --- | --- |
| Vai trò | Chọn bean mặc định được ưu tiên | Lọc ứng viên theo tiêu chí |
| Nơi khai báo thường gặp | Trên class component hoặc phương thức `@Bean` | Trên bean và/hoặc điểm inject |
| Khi nào hữu ích | Phần lớn điểm inject nên dùng một implementation mặc định | Từng điểm inject cần implementation/nhóm cụ thể |
| Có thể dùng cùng nhau? | Có | Có |
| Có tạo bean mới không? | Không | Không |

Không nên dùng `@Primary` để giải quyết mọi trường hợp có nhiều bean. Nếu service cần SMS vì đây là yêu cầu chức năng, qualifier thể hiện rõ ý định hơn việc thay đổi bean mặc định toàn ứng dụng.

### 4.2. Qualifier không nhất thiết phải chỉ một bean

Một qualifier có thể khớp với nhiều bean. Khi inject một dependency đơn, nhiều ứng viên cùng thỏa điều kiện vẫn có thể gây mơ hồ nếu không có quy tắc phân biệt tiếp. Nhưng khi inject collection, việc có nhiều bean cùng qualifier chính là điều ta mong muốn.

## 5. Dùng qualifier để định danh một nhóm dependency

Một tình huống phổ biến là service cần **tất cả các implementation thuộc cùng một nhóm**.

Ví dụ, hệ thống có nhiều loại sender, nhưng một luồng cần gọi mọi kênh được đánh dấu là có khả năng gửi ra bên ngoài. Ta có thể gắn cùng qualifier lên các bean:

```java
@Component
@Qualifier("external")
public class EmailNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Gửi email qua nhà cung cấp bên ngoài.
    }
}
```

```java
@Component
@Qualifier("external")
public class SmsNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Gửi SMS qua nhà cung cấp bên ngoài.
    }
}
```

Một sender khác chỉ ghi vào console để phục vụ phát triển:

```java
@Component
@Qualifier("local")
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("LOCAL: " + recipient + " - " + message);
    }
}
```

Bây giờ một service có thể nhận toàn bộ nhóm external:

```java
@Service
public class ExternalBroadcastService {

    private final List<NotificationSender> senders;

    public ExternalBroadcastService(
            @Qualifier("external")
            List<NotificationSender> senders
    ) {
        this.senders = senders;
    }

    public void broadcast(String recipient, String message) {
        senders.forEach(sender -> sender.send(recipient, message));
    }
}
```

Spring tìm các bean có type tương thích với `NotificationSender`, rồi dùng qualifier `external` để lọc tập ứng viên cho collection. Kết quả trong ví dụ là các sender email và SMS; sender console mang qualifier `local` không thuộc nhóm.

Đây là một ý nghĩa quan trọng của qualifier: **một nhãn có thể đại diện cho một nhóm bean**, không nhất thiết là một định danh duy nhất.

### 5.1. Inject List, Set hoặc Map

Spring có thể inject nhiều bean theo type:

```java
public NotificationCoordinator(List<NotificationSender> senders) {
    this.senders = senders;
}
```

Với qualifier:

```java
public NotificationCoordinator(
        @Qualifier("external")
        List<NotificationSender> senders
) {
    this.senders = senders;
}
```

Một số hình thức thường gặp:

| Kiểu dependency | Ý nghĩa |
| --- | --- |
| `List<NotificationSender>` | Danh sách bean phù hợp theo type |
| `Set<NotificationSender>` | Tập bean phù hợp theo type |
| `Map<String, NotificationSender>` | Map bean theo tên bean với value là instance |
| `@Qualifier("external") List<NotificationSender>` | Danh sách bean cùng type thỏa qualifier |
| `@Qualifier("external") Set<NotificationSender>` | Tập bean cùng type thỏa qualifier |

Đối với `Map<String, T>` được inject theo kiểu collection của Spring, key thường là tên bean và value là bean instance. Qualifier tại điểm inject có thể lọc tập bean trước khi đưa vào collection.

Nếu collection rỗng, cần kiểm tra có bean phù hợp nào đã được đăng ký hay chưa, qualifier trên bean và qualifier tại điểm inject có khớp không, cũng như điều kiện profile/conditional có loại các bean khỏi context không.

### 5.2. Nhóm dependency không phải một bean duy nhất

Không nên dùng `@Primary` để đại diện cho một nhóm. `@Primary` giải quyết ưu tiên cho injection đơn; qualifier trên collection thể hiện nhóm bean có cùng đặc tính.

Nếu cần thực hiện một thao tác trên tất cả bean thuộc nhóm, inject collection. Nếu chỉ cần một implementation được chọn mặc định, dùng `@Primary` hoặc qualifier đơn. Chọn cấu trúc theo hành vi mà service thực sự cần.

## 6. Tạo qualifier tùy chỉnh có ý nghĩa nghiệp vụ

Các chuỗi như `"external"` hoặc `"local"` dễ bắt đầu, nhưng khi dự án lớn, nhiều qualifier string có thể bị lặp, sai chính tả hoặc khó tìm nơi định nghĩa. Spring cho phép tạo **custom qualifier annotation** bằng cách đánh dấu annotation đó với `@Qualifier`.

Ví dụ, hệ thống gửi thông báo theo khu vực:

```java
package com.example.notification;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Region {
    String value();
}
```

`@Region` là một qualifier tùy chỉnh có thuộc tính `value`. Nó có thể được gắn lên class component, phương thức `@Bean` hoặc điểm inject phù hợp.

Hai implementation:

```java
@Component
@Region("asia")
public class AsiaEmailSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Gửi qua hạ tầng email dành cho khu vực Asia.
    }
}
```

```java
@Component
@Region("europe")
public class EuropeEmailSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Gửi qua hạ tầng email dành cho khu vực Europe.
    }
}
```

Điểm inject:

```java
@Service
public class RegionalNotificationService {

    private final NotificationSender sender;

    public RegionalNotificationService(
            @Region("asia") NotificationSender sender
    ) {
        this.sender = sender;
    }
}
```

Đọc constructor ta thấy rõ service cần một `NotificationSender` dành cho khu vực Asia. Nếu đổi tên class thành `AsiaMailAdapter` hoặc đổi bean name, qualifier theo vùng vẫn có thể giữ nguyên vì nó biểu đạt đặc tính thay vì tên class.

### 6.1. Qualifier tùy chỉnh không thay thế type

`@Region("asia")` vẫn được dùng cùng type dependency. Nếu class không thực hiện `NotificationSender` hoặc không có bean tương thích, chỉ gắn `@Region("asia")` không làm nó trở thành sender.

Có thể hiểu quá trình lọc theo hai ý:

1. Xác định các bean có type phù hợp với điểm inject.
2. Giữ lại những bean thỏa các qualifier được yêu cầu.

Vì vậy, qualifier giúp phân loại các implementation trong cùng một vai trò; nó không thay thế hệ thống type của Java.

## 7. Kết hợp nhiều qualifier để mô tả nhiều chiều

Một bean có thể được mô tả theo nhiều đặc tính. Ví dụ, ứng dụng có nhiều kênh thông báo ở nhiều khu vực:

| Implementation | Khu vực | Kênh |
| --- | --- | --- |
| `AsiaEmailSender` | Asia | Email |
| `AsiaSmsSender` | Asia | SMS |
| `EuropeEmailSender` | Europe | Email |
| `EuropeSmsSender` | Europe | SMS |

Ta có thể tạo qualifier `Channel`:

```java
package com.example.notification;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Channel {
    String value();
}
```

Gắn cả hai qualifier lên bean:

```java
@Component
@Region("asia")
@Channel("email")
public class AsiaEmailSender implements NotificationSender {
    // ...
}
```

```java
@Component
@Region("asia")
@Channel("sms")
public class AsiaSmsSender implements NotificationSender {
    // ...
}
```

```java
@Component
@Region("europe")
@Channel("email")
public class EuropeEmailSender implements NotificationSender {
    // ...
}
```

Một service yêu cầu email ở Asia:

```java
@Service
public class AsiaEmailNotificationService {

    private final NotificationSender sender;

    public AsiaEmailNotificationService(
            @Region("asia")
            @Channel("email")
            NotificationSender sender
    ) {
        this.sender = sender;
    }
}
```

Spring phải tìm bean tương thích với `NotificationSender` và thỏa cả hai metadata qualifier. Đây là cách định danh nhiều chiều: khu vực và kênh.

Nếu một bean không có qualifier bắt buộc, nó không phải ứng viên phù hợp cho điểm inject đó. Khi có nhiều qualifier, cần xem chúng như các điều kiện kết hợp; đừng gắn metadata tùy tiện lên bean rồi mong Spring tự suy ra ý nghĩa nghiệp vụ.

### 7.1. Nhóm theo một chiều

Ta cũng có thể inject tất cả sender ở Asia:

```java
public AsiaBroadcastService(
        @Region("asia")
        List<NotificationSender> senders
) {
    this.senders = senders;
}
```

Kết quả là các bean `AsiaEmailSender` và `AsiaSmsSender`. Nếu muốn tất cả sender email ở mọi khu vực, dùng `@Channel("email") List<NotificationSender>`. Nếu muốn đúng giao điểm Asia + email, kết hợp cả hai qualifier.

## 8. Qualifier dạng marker annotation

Không phải qualifier nào cũng cần giá trị. Một số đặc tính chỉ có hai nhóm rõ ràng, ví dụ implementation lưu trữ bền vững hoặc implementation chỉ dùng cho phát triển.

Có thể tạo marker qualifier:

```java
package com.example.storage;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Persistent {
}
```

Gắn lên các bean:

```java
@Component
@Persistent
public class PostgresCustomerStore implements CustomerStore {
    // ...
}
```

```java
@Component
@Persistent
public class MongoCustomerStore implements CustomerStore {
    // ...
}
```

Inject nhóm:

```java
@Service
public class CustomerBackupService {

    private final List<CustomerStore> persistentStores;

    public CustomerBackupService(
            @Persistent List<CustomerStore> persistentStores
    ) {
        this.persistentStores = persistentStores;
    }
}
```

Trong ví dụ, `@Persistent` là metadata mang ý nghĩa của ứng dụng. Các implementation cùng nhóm có thể được inject thành collection. Nếu một service chỉ cần đúng một persistent store, phải có thêm quy tắc lựa chọn hoặc qualifier cụ thể hơn.

Marker qualifier giúp tránh các chuỗi tùy ý và hỗ trợ IDE tìm nơi sử dụng. Tuy nhiên, không nên tạo một annotation mới nếu chỉ có một điểm inject và một bean duy nhất; dùng `@Qualifier("...")` đơn giản có thể đã đủ.

## 9. Đặt qualifier trên class hay phương thức @Bean?

Spring cho phép gắn qualifier lên class component hoặc bean method.

### 9.1. Class được component scan

```java
@Component
@Qualifier("fast")
public class InMemoryCache implements CacheStore {
    // ...
}
```

### 9.2. Bean được tạo qua @Bean

```java
@Configuration
class CacheConfiguration {

    @Bean
    @Qualifier("fast")
    CacheStore inMemoryCache() {
        return new InMemoryCache();
    }

    @Bean
    @Qualifier("durable")
    CacheStore redisCache() {
        return new RedisCacheStore();
    }
}
```

Trong ví dụ, `InMemoryCache` và `RedisCacheStore` là các class implementation giả định. Qualifier gắn trên phương thức `@Bean` trở thành metadata của bean được cung cấp bởi phương thức đó.

Điểm inject:

```java
public CacheCoordinator(
        @Qualifier("durable") CacheStore cacheStore
) {
    this.cacheStore = cacheStore;
}
```

Khi class bên thứ ba không thể chỉnh sửa annotation, cấu hình qua phương thức `@Bean` giúp gắn qualifier vào bean mà không cần sửa source của class đó.

### 9.3. Tránh gắn qualifier sai vị trí

Nếu một class được tạo bởi một phương thức `@Bean`, metadata bean thường được khai báo ở phương thức cấu hình. Thêm annotation lên class implementation không phải lúc nào cũng là cách rõ ràng nhất, đặc biệt khi cùng class được dùng để tạo nhiều bean với mục đích khác nhau.

Hãy đặt qualifier tại nơi thể hiện rõ bean nào đang được định nghĩa. Khi cùng một class tạo hai bean với hai cấu hình khác nhau, qualifier trên từng phương thức `@Bean` thường dễ đọc hơn qualifier cố định trên class.

## 10. @Qualifier có thể dùng với @Primary không?

Có. `@Primary` và `@Qualifier` phối hợp trong quá trình lựa chọn ứng viên.

Ví dụ:

```java
@Bean
@Primary
@Qualifier("default")
NotificationSender defaultSender() {
    return new EmailNotificationSender();
}

@Bean
@Qualifier("urgent")
NotificationSender urgentSender() {
    return new SmsNotificationSender();
}
```

Kết quả mong muốn:

- Điểm inject `NotificationSender` không có qualifier có thể nhận bean primary phù hợp.
- Điểm inject `@Qualifier("urgent") NotificationSender` yêu cầu bean có qualifier `urgent`.
- Điểm inject `@Qualifier("default") NotificationSender` có thể chọn bean được gắn qualifier `default`.

`@Primary` không làm một bean mang tất cả qualifier của các bean khác. Nó chỉ đánh dấu mức ưu tiên khi chọn một bean duy nhất trong tập ứng viên phù hợp.

Nếu nhiều bean cùng có `@Primary` hoặc nhiều bean vẫn thỏa qualifier cho injection đơn, cần làm rõ tiêu chí hơn. Không nên dựa vào thứ tự scan hoặc thứ tự file để đoán bean nào được chọn.

## 11. @Qualifier và lựa chọn bean theo thời gian chạy

Một điểm rất quan trọng: **qualifier được dùng khi Spring giải quyết dependency**, thường là lúc tạo bean hoặc lúc lấy dependency theo cơ chế container. Nó không tự chọn lại implementation cho từng request.

Giả sử một ứng dụng có cả email và SMS:

```java
@Service
class NotificationService {

    private final NotificationSender sender;

    NotificationService(@Qualifier("email") NotificationSender sender) {
        this.sender = sender;
    }
}
```

Service này được wiring với bean email. Nếu một request cần gửi SMS, qualifier cố định trên constructor không tự đổi sang SMS cho request đó.

Nếu lựa chọn phụ thuộc vào dữ liệu lúc chạy, ví dụ request chứa `channel=email` hoặc `channel=sms`, hãy inject tập implementation và chọn theo quy tắc ứng dụng:

```java
@Service
public class DynamicNotificationService {

    private final Map<String, NotificationSender> senders;

    public DynamicNotificationService(
            Map<String, NotificationSender> senders
    ) {
        this.senders = senders;
    }

    public void send(
            String channel,
            String recipient,
            String message
    ) {
        NotificationSender sender = senders.get(channel + "Sender");
        if (sender == null) {
            throw new IllegalArgumentException(
                    "Unsupported notification channel: " + channel
            );
        }
        sender.send(recipient, message);
    }
}
```

Đây là ví dụ đơn giản để minh họa lựa chọn lúc chạy; tên key phải được quản lý nhất quán với bean name và cần validation rõ ràng. Trong hệ thống lớn, có thể dùng một registry/factory có API rõ ràng thay vì ghép chuỗi tên bean trong service.

Một lựa chọn khác là inject `List<NotificationSender>` rồi xây map theo thuộc tính do từng implementation công bố. Điều này tránh buộc logic nghiệp vụ phải biết bean name Spring.

### 11.1. Khi nào dùng qualifier, khi nào dùng strategy/factory?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Service luôn dùng email sender | Constructor injection với `@Qualifier("email")` |
| Service cần mọi sender bên ngoài | `@Qualifier("external") List<NotificationSender>` |
| Request quyết định email hay SMS | Inject tập sender và chọn qua factory/strategy |
| Hệ thống có một sender mặc định | `@Primary` |
| Một module tùy chọn chỉ được bật ở môi trường dev | Cấu hình profile/condition, có thể kết hợp qualifier nếu có nhiều ứng viên |

Không nên dùng qualifier như một bộ định tuyến nghiệp vụ động. Nó giải quyết wiring, còn quyết định theo request hoặc dữ liệu khách hàng nên được biểu diễn trong application logic.

## 12. @Qualifier khác @Profile và @Conditional như thế nào?

Ba cơ chế này thường xuất hiện gần nhau trong cấu hình bean, nhưng trả lời các câu hỏi khác nhau:

| Cơ chế | Câu hỏi |
| --- | --- |
| `@Qualifier` | Trong các bean đã đăng ký và phù hợp về type, bean nào/nhóm nào phù hợp với điểm inject? |
| `@Profile` | Cấu hình hoặc bean có được đăng ký trong profile hiện tại không? |
| `@Conditional...` | Cấu hình hoặc bean có được đăng ký khi điều kiện cụ thể thỏa không? |

Ví dụ:

```java
@Configuration
@Profile("dev")
class DevNotificationConfiguration {

    @Bean
    @Qualifier("local")
    NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }
}
```

Bean trên chỉ được cung cấp khi profile `dev` phù hợp. Nếu nó đã được đăng ký, qualifier `local` có thể được dùng để chọn bean tại điểm inject. Qualifier không kích hoạt profile, và profile không tự thay thế việc phân biệt nhiều bean cùng kiểu.

Nếu một service yêu cầu `@Qualifier("local")` nhưng ứng dụng chạy profile `prod` khiến bean local không được tạo, Spring có thể không tìm được ứng viên phù hợp. Đây là lỗi khác với trường hợp có nhiều bean cùng qualifier.

## 13. Thứ tự của nhóm dependency

Khi inject `List<T>` hoặc mảng bean, đôi khi thứ tự xử lý có ý nghĩa. Ví dụ một chuỗi validator hoặc bộ xử lý cần chạy theo thứ tự xác định.

Spring hỗ trợ `@Order` hoặc interface `Ordered` trong những tình huống collection injection phù hợp:

```java
@Component
@Order(10)
class FirstNotificationProcessor implements NotificationProcessor {
    // ...
}

@Component
@Order(20)
class SecondNotificationProcessor implements NotificationProcessor {
    // ...
}
```

Khi inject:

```java
public NotificationPipeline(List<NotificationProcessor> processors) {
    this.processors = processors;
}
```

`@Order` giúp xác định thứ tự ưu tiên trong những collection được Spring sắp xếp theo order metadata. Số nhỏ hơn thường có độ ưu tiên trước số lớn hơn.

Cần phân biệt:

- `@Qualifier` chọn tập ứng viên theo đặc tính.
- `@Order` sắp xếp các ứng viên trong những tình huống hỗ trợ ordering.
- `@Primary` ưu tiên một ứng viên cho dependency đơn.

`@Order` không thay thế qualifier và cũng không phải lệnh bảo đảm thứ tự khởi tạo bean. Nếu thứ tự xử lý ảnh hưởng tới nghiệp vụ, hãy thể hiện và kiểm thử rõ ràng.

## 14. Các lỗi thường gặp khi sử dụng qualifier

### 14.1. Không có bean nào thỏa qualifier

Ví dụ:

```java
public PaymentService(
        @Qualifier("card") PaymentGateway gateway
) {
    this.gateway = gateway;
}
```

Nếu context không có bean kiểu `PaymentGateway` mang qualifier phù hợp hoặc tên bean fallback tương ứng, Spring không thể giải quyết dependency. Nguyên nhân có thể là:

- Chưa đăng ký implementation.
- Bean nằm ngoài component scan và chưa được import/cấu hình.
- Giá trị qualifier sai chính tả hoặc khác metadata.
- Bean bị loại bởi `@Profile` hoặc điều kiện.
- Implementation nằm trong module không có trên classpath.

### 14.2. Nhiều bean cùng thỏa qualifier tại điểm inject đơn

Nếu cả email và SMS sender đều mang qualifier `external`, điểm inject:

```java
@Qualifier("external") NotificationSender sender
```

vẫn có thể mơ hồ vì có hai ứng viên cùng thỏa. Nếu muốn cả hai, hãy inject `List<NotificationSender>`. Nếu muốn một bean, cần tiêu chí cụ thể hơn như `@Channel("email")`, hoặc một lựa chọn mặc định phù hợp.

### 14.3. Qualifier trên bean và điểm inject không khớp

Ví dụ bean có `@Qualifier("external")` nhưng constructor yêu cầu `@Qualifier("remote")`. Nếu không có metadata khác thỏa điều kiện, bean sẽ không được chọn. Đừng nhầm giá trị qualifier với tên mô tả tự do; nó là tiêu chí cần nhất quán ở hai phía.

### 14.4. Dùng bean name thay cho ý nghĩa qualifier ở mọi nơi

Nếu service dùng `@Qualifier("smtpNotificationSender")`, việc đổi tên class/bean có thể kéo theo thay đổi nhiều nơi. Nếu điều service cần là “kênh email”, dùng một qualifier mang ý nghĩa `email` có thể ổn định hơn tên implementation.

### 14.5. Dùng qualifier để che một thiết kế thiếu hợp đồng

Nếu có nhiều class cùng type nhưng mỗi class có API khác nhau, việc gắn qualifier không làm chúng trở thành các implementation thay thế được. Hãy thiết kế interface phù hợp trước, rồi dùng qualifier để phân loại các bean thực sự cùng vai trò.

### 14.6. Trộn nhiều cơ chế chọn mà không hiểu ưu tiên

`@Primary`, qualifier, tên bean và các metadata khác có thể cùng tham gia giải quyết dependency. Nếu có nhiều quy tắc chồng chéo, code sẽ khó dự đoán. Nên dùng tiêu chí trực tiếp tại điểm inject và giữ cấu hình nhất quán, tránh dựa vào hành vi fallback nếu không cần thiết.

## 15. Cách điều tra lỗi chọn bean trong Spring Boot

Khi ứng dụng không khởi động vì dependency có nhiều hoặc không có ứng viên, hãy đọc thông báo lỗi theo thứ tự:

1. **Bean nào đang được tạo?** Xác định service, controller hoặc configuration thất bại.
2. **Dependency nào đang được yêu cầu?** Đọc type ở constructor/field/method parameter.
3. **Có qualifier tại điểm inject không?** Ghi lại tất cả qualifier và giá trị của chúng.
4. **Những bean nào cùng type đã được đăng ký?** Tìm component, phương thức `@Bean`, cấu hình được import và auto-configuration liên quan.
5. **Metadata của bean có khớp không?** Kiểm tra qualifier ở class hoặc phương thức bean.
6. **Có profile/condition nào loại bean không?** Kiểm tra môi trường và điều kiện cấu hình.
7. **Có nhiều bean cùng thỏa không?** Chọn qualifier cụ thể, collection hoặc primary theo nhu cầu thực tế.

Các dạng lỗi thường gặp:

| Triệu chứng | Ý nghĩa có thể có | Hướng điều tra |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Không tìm thấy bean phù hợp | Kiểm tra type, scan, import, qualifier, profile |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp cho một dependency đơn | Kiểm tra `@Primary`, qualifier và tên bean |
| `UnsatisfiedDependencyException` | Spring không thể cung cấp dependency cho bean đang tạo | Đọc nguyên nhân lồng bên trong để tìm lỗi gốc |
| Collection rỗng | Không có bean nào thỏa type/qualifier trong context | Kiểm tra đăng ký bean và metadata nhóm |
| Dùng nhầm implementation | Một ứng viên khác đã được chọn theo metadata/ưu tiên | Kiểm tra qualifier, primary, bean name và cấu hình |

Không nên chỉ thêm `@Primary` để làm ứng dụng khởi động mà chưa xác nhận implementation đó đúng với yêu cầu. Một ứng dụng khởi động thành công nhưng dùng nhầm cổng thanh toán hoặc nhầm hệ thống gửi thông báo vẫn là lỗi chức năng.

## 16. Thiết kế qualifier sao cho dễ duy trì

### 16.1. Dùng nhãn mô tả vai trò hoặc đặc tính

Tên như `external`, `persistent`, `readOnly` hoặc `regional` thường diễn đạt ý nghĩa ổn định hơn tên class. Qualifier nên giúp người đọc hiểu **vì sao service cần bean đó**.

### 16.2. Tránh tạo quá nhiều qualifier trùng ý nghĩa

Nếu ứng dụng có `remote`, `external`, `thirdParty` nhưng không có định nghĩa khác nhau rõ ràng, người phát triển sẽ không biết nên dùng nhãn nào. Nên thống nhất từ vựng trong module và giải thích khi qualifier đại diện một chính sách cụ thể.

### 16.3. Chọn custom annotation khi metadata được dùng lặp lại

Nếu qualifier có nhiều chiều, được dùng ở nhiều module hoặc có ý nghĩa domain rõ, custom annotation có thuộc tính giúp IDE hỗ trợ refactor và giảm lỗi chuỗi.

### 16.4. Không biến qualifier thành cấu hình nghiệp vụ động

Qualifier được giải quyết khi wiring. Nếu yêu cầu lựa chọn phụ thuộc dữ liệu mỗi request, hãy xây factory, strategy resolver hoặc registry được inject. Đừng tạo nhiều bean qualifier rồi mong Spring tự đổi bean cho một service singleton theo từng request.

### 16.5. Chỉ dùng qualifier khi type chưa đủ phân biệt

Nếu một type chỉ có một bean duy nhất, thêm qualifier không mang lại nhiều giá trị. Qualifier hữu ích khi có nhiều implementation, nhiều nhóm hoặc cần lựa chọn tường minh.

## 17. Bài tập thực hành

### Bài tập 1 – Chọn đúng implementation

Cho hai bean `EmailNotificationSender` và `SmsNotificationSender` cùng thực hiện `NotificationSender`. Hãy:

1. Gắn qualifier `email` và `sms` lên hai bean.
2. Tạo `RegistrationService` nhận bean email qua constructor.
3. Tạo `SecurityAlertService` nhận bean SMS qua constructor.
4. Giải thích vì sao cả hai service có thể dùng cùng interface nhưng nhận implementation khác nhau.

**Gợi ý:** type vẫn là `NotificationSender`; qualifier tại từng constructor thu hẹp ứng viên theo mục đích.

### Bài tập 2 – Inject cả nhóm

Tạo ba bean `NotificationSender`:

- Email sender mang qualifier `external`.
- SMS sender mang qualifier `external`.
- Console sender mang qualifier `local`.

Viết `ExternalBroadcastService` nhận `@Qualifier("external") List<NotificationSender>` và gọi tất cả sender trong danh sách. Giải thích vì sao cùng qualifier không gây lỗi mơ hồ trong trường hợp collection như injection một bean đơn.

### Bài tập 3 – Tạo qualifier tùy chỉnh

Tạo hai annotation `@Region` và `@Channel`, mỗi annotation có thuộc tính `String value()` và được meta-annotated bằng `@Qualifier`. Đăng ký các bean Asia/Europe cho Email/SMS rồi inject đúng bean Asia Email.

Thử inject `@Region("asia") List<NotificationSender>` và `@Channel("email") List<NotificationSender>` để quan sát cách qualifier lọc nhóm.

### Bài tập 4 – Phân biệt @Primary và @Qualifier

Đánh dấu email sender là `@Primary`. Sau đó:

- Inject `NotificationSender` không có qualifier.
- Inject `@Qualifier("sms") NotificationSender`.
- Inject `@Qualifier("external") List<NotificationSender>`.

Giải thích vì sao ba điểm inject có thể nhận các tập bean khác nhau.

### Bài tập 5 – Lựa chọn theo request

Một REST request có trường `channel` nhận giá trị `email` hoặc `sms`. Hãy thiết kế một service có thể chọn sender lúc chạy bằng `Map<String, NotificationSender>` hoặc registry. So sánh thiết kế đó với việc gắn `@Qualifier("email")` cố định ở constructor.

**Gợi ý:** qualifier cố định là lựa chọn ở thời điểm wiring; map/registry cho phép logic ứng dụng lựa chọn dựa trên dữ liệu lúc chạy.

## 18. Những điều cần nhớ về @Qualifier

`@Qualifier` là công cụ của Spring để **mô tả và lọc ứng viên bean khi giải quyết dependency**. Nó đặc biệt hữu ích khi nhiều bean cùng type nhưng có vai trò, kênh, vùng, môi trường hoặc đặc tính khác nhau.

Các nguyên tắc chính:

- Spring xét type trước, rồi dùng qualifier và các quy tắc lựa chọn bean để xác định ứng viên phù hợp.
- Bean name là định danh trong container; qualifier là metadata lọc ứng viên. Giá trị qualifier có thể khớp tên bean như một fallback, nhưng không nên đồng nhất hai khái niệm.
- `@Primary` chỉ định ứng viên mặc định được ưu tiên; `@Qualifier` thể hiện tiêu chí cụ thể tại điểm inject.
- Cùng một qualifier có thể gắn lên nhiều bean để tạo thành nhóm; inject `List<T>` hoặc `Set<T>` khi cần cả nhóm.
- Custom qualifier annotation giúp diễn đạt metadata nhiều chiều và tránh phụ thuộc vào chuỗi rời rạc.
- Qualifier không đăng ký bean, không thêm dependency vào classpath và không thay thế profile/condition.
- Qualifier giải quyết wiring; lựa chọn implementation dựa trên dữ liệu runtime cần factory, strategy hoặc registry phù hợp.

Khi gặp nhiều bean cùng kiểu, hãy hỏi **service cần một bean mặc định, một implementation cụ thể hay cả một nhóm bean?** Câu trả lời sẽ giúp chọn giữa `@Primary`, `@Qualifier` đơn, custom qualifier hoặc collection injection. Đây là cách tổ chức dependency rõ ràng, giúp Spring context dễ hiểu và ứng dụng Spring Boot dễ mở rộng hơn.
