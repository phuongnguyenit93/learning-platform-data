# Kiểm tra `@Primary` cùng trường hợp nhiều ứng viên không có ứng viên chính

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Ma trận kiểm thử  
**Mục tiêu:** Kiểm chứng cách Spring chọn bean khi một injection point có nhiều candidate cùng kiểu. Bài tập trung vào một candidate, nhiều candidate có đúng một `@Primary`, nhiều candidate không có primary, nhiều primary, `@Qualifier` và collection injection.

## 1. Nhiều bean cùng kiểu là tình huống hợp lệ

Spring cho phép một `ApplicationContext` có nhiều bean cùng implement một interface. Ví dụ hệ thống thông báo hỗ trợ email và SMS:

```java
public interface MessageSender {
    void send(String message);
}
```

Hai implementation đều có thể tồn tại:

```java
@Component
class EmailSender implements MessageSender {
    @Override
    public void send(String message) {
        // Gửi email
    }
}

@Component
class SmsSender implements MessageSender {
    @Override
    public void send(String message) {
        // Gửi SMS
    }
}
```

Vấn đề chỉ xuất hiện khi một consumer yêu cầu **một giá trị duy nhất**:

```java
@Service
class NotificationService {

    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = sender;
    }
}
```

Nếu context chỉ có một `MessageSender` phù hợp, Spring inject bean đó. Nếu có nhiều bean, Spring cần thêm metadata để xác định candidate. Khi không thể chọn duy nhất, quá trình tạo consumer thất bại với `NoUniqueBeanDefinitionException` (thường được bọc trong `UnsatisfiedDependencyException` hoặc `BeanCreationException`).

Vì vậy, cần tách hai ý:

- Nhiều bean cùng kiểu: hợp lệ, có thể là chủ đích.
- Một injection point cần một bean nhưng còn nhiều candidate ngang nhau: không thể phân giải và có thể làm context khởi động thất bại.

## 2. `@Primary` đánh dấu bean ưu tiên cho injection đơn

`@Primary` đánh dấu một bean là ứng viên ưu tiên khi Spring phải inject một dependency đơn và có nhiều candidate cùng kiểu.

Có thể đặt annotation trên component:

```java
@Component
@Primary
class EmailSender implements MessageSender {
    // ...
}
```

Hoặc trên phương thức `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
class SenderConfiguration {

    @Bean
    @Primary
    MessageSender emailSender() {
        return new EmailSender();
    }

    @Bean
    MessageSender smsSender() {
        return new SmsSender();
    }
}
```

Khi một bean yêu cầu `MessageSender` mà không có qualifier khác, `emailSender` được chọn vì là candidate duy nhất có `@Primary`.

`@Primary` có các đặc điểm:

1. Nó tác động đến quá trình phân giải dependency của injection point đơn trị.
2. Nó không xóa, tắt hoặc loại bean còn lại khỏi `ApplicationContext`.
3. Nó không đổi bean name.
4. Nó không tự đăng ký bean; bean vẫn phải được tạo bởi component scanning, `@Bean` hoặc cơ chế đăng ký khác.
5. Nó không thay thế `@ConditionalOnMissingBean` trong auto-configuration.
6. Nó không lọc các candidate khi consumer yêu cầu một collection.

Nếu không có injection point nào cần một `MessageSender` đơn trị, hai bean vẫn có thể cùng tồn tại mà không gây ambiguity.

### 2.1. Khi nào nên chọn một primary?

Dùng `@Primary` khi có một implementation mặc định hợp lý cho phần lớn consumer trong ứng dụng, ví dụ:

- Một `Clock` production mặc định.
- Một `PaymentGateway` mặc định.
- Một `ObjectMapper` mặc định.
- Một kênh thông báo mặc định khi phần lớn service đều dùng cùng kênh.

Nếu mỗi consumer có yêu cầu nghiệp vụ khác nhau, một primary toàn cục có thể che giấu lựa chọn sai. Trong trường hợp đó, `@Qualifier` ở từng injection point diễn tả ý định rõ hơn.

## 3. Không có `@Primary` và có nhiều candidate

Giả sử cấu hình đăng ký:

```java
@Bean
MessageSender emailSender() {
    return new EmailSender();
}

@Bean
MessageSender smsSender() {
    return new SmsSender();
}
```

Một bean khác yêu cầu:

```java
@Bean
NotificationService notificationService(MessageSender sender) {
    return new NotificationService(sender);
}
```

Nếu không có qualifier và cũng không có metadata khác đủ để chọn duy nhất, Spring không tự đoán email hay SMS. Kết quả là `NoUniqueBeanDefinitionException`.

Thông báo có thể có dạng:

```text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'MessageSender' available:
expected single matching bean but found 2
```

Exception đầy đủ phụ thuộc injection point và phiên bản Spring. Khi chẩn đoán, hãy tìm `NoUniqueBeanDefinitionException` trong chuỗi `Caused by`, sau đó xác định consumer nào đang yêu cầu một bean duy nhất và danh sách candidate mà Spring tìm thấy.

### 3.1. Không phải cứ có nhiều bean là context lỗi

Ví dụ này vẫn có thể khởi động bình thường:

```java
@Configuration(proxyBeanMethods = false)
class SenderConfiguration {

    @Bean
    MessageSender emailSender() {
        return new EmailSender();
    }

    @Bean
    MessageSender smsSender() {
        return new SmsSender();
    }
}
```

Nếu không có bean nào yêu cầu một `MessageSender` đơn lẻ, Spring không cần chọn một candidate duy nhất. Có thể lấy từng bean theo tên hoặc inject cả hai dưới dạng collection.

Đây là điểm cần kiểm tra trong test: muốn chứng minh ambiguity, phải tạo một injection point thực sự yêu cầu một bean đơn trị. Chỉ assert rằng context có hai bean cùng kiểu chưa đủ để chứng minh lỗi.

### 3.2. Những thông tin khác có thể giúp phân giải

`@Primary` không phải tín hiệu duy nhất. Tùy injection point, Spring còn có thể xét qualifier, metadata ưu tiên và tên dependency/bean nếu có thông tin phù hợp.

Tuy nhiên, không nên dựa vào thứ tự khai báo method `@Bean`, thứ tự component scan hoặc tên biến tình cờ để chọn implementation. Khi yêu cầu nghiệp vụ cụ thể, dùng `@Qualifier` để thể hiện lựa chọn tường minh. Điều đó giúp refactor tên biến hoặc sắp xếp lại configuration không làm thay đổi hành vi ngoài ý muốn.

## 4. `@Qualifier` chọn candidate tại từng injection point

`@Qualifier` thu hẹp tập candidate cho một consumer cụ thể:

```java
@Service
class NotificationService {

    private final MessageSender sender;

    NotificationService(
            @Qualifier("smsSender") MessageSender sender) {
        this.sender = sender;
    }
}
```

Nếu có bean tên `emailSender` và `smsSender`, injection point này yêu cầu `smsSender`.

Qualifier cũng có thể được đặt trên bean:

```java
@Bean
@Qualifier("urgent")
MessageSender smsSender() {
    return new SmsSender();
}
```

và được yêu cầu ở consumer:

```java
@Bean
NotificationService notificationService(
        @Qualifier("urgent") MessageSender sender) {
    return new NotificationService(sender);
}
```

Qualifier không nhất thiết chỉ là bean name. Có thể định nghĩa annotation qualifier riêng có thuộc tính, ví dụ `@Region("asia")`, để nhóm candidate theo ngữ nghĩa nghiệp vụ.

### 4.1. `@Qualifier` phối hợp với `@Primary`

Giả sử `emailSender` là primary nhưng consumer có `@Qualifier("smsSender")`. Consumer vẫn nhận SMS sender vì qualifier yêu cầu một candidate cụ thể.

Có thể dùng một default toàn cục bằng `@Primary`, sau đó dùng qualifier ở những service có yêu cầu riêng. Hãy giữ qualifier ổn định và có ý nghĩa; tránh rải tên implementation cụ thể khắp ứng dụng nếu một qualifier theo nghiệp vụ sẽ rõ ràng hơn.

## 5. `@Primary` không lọc collection injection

Đây là khác biệt quan trọng nhất giữa injection đơn và injection nhiều candidate.

Khi consumer yêu cầu:

```java
@Bean
SenderRegistry senderRegistry(List<MessageSender> senders) {
    return new SenderRegistry(senders);
}
```

Spring đưa vào list tất cả bean phù hợp với kiểu `MessageSender`, kể cả bean không được đánh dấu primary.

Collection injection thường hỗ trợ:

```java
MessageSender[] senders;
List<MessageSender> senders;
Set<MessageSender> senders;
Map<String, MessageSender> sendersByBeanName;
```

Với `Map<String, MessageSender>`, key là bean name và value là bean tương ứng. `@Primary` không loại các bean khác khỏi list, set, array hoặc map.

Nếu cần thứ tự trong list/array, dùng `@Order` hoặc `Ordered`:

```java
@Bean
@Order(1)
MessageSender emailSender() {
    return new EmailSender();
}

@Bean
@Order(2)
MessageSender smsSender() {
    return new SmsSender();
}
```

`@Order` có thể sắp xếp thứ tự candidate trong collection injection. Nó không biến bean thành primary và không giải quyết ambiguity của injection đơn. Phần tử đầu tiên của list không mặc nhiên trở thành bean được inject vào một tham số đơn.

## 6. Hai bean cùng được đánh dấu `@Primary`

Với một injection point không có qualifier, nếu nhiều candidate còn phù hợp đều được đánh dấu `@Primary`, Spring vẫn không có một primary duy nhất để lựa chọn. Trường hợp này tiếp tục có thể gây `NoUniqueBeanDefinitionException`.

Ví dụ cấu hình không nên dùng:

```java
@Bean
@Primary
MessageSender emailSender() {
    return new EmailSender();
}

@Bean
@Primary
MessageSender smsSender() {
    return new SmsSender();
}
```

Cách xử lý:

- Chỉ đánh dấu một implementation làm default.
- Dùng qualifier ở các injection point cần lựa chọn cụ thể.
- Tách interface nếu hai implementation thực sự có vai trò khác nhau.
- Dùng strategy/factory nếu quyết định phụ thuộc dữ liệu runtime thay vì một default cố định.

Không dùng `@Order` để giải quyết nhiều primary. Hai annotation phục vụ hai mục đích khác nhau.

## 7. Phân biệt `@Primary` với `@ConditionalOnMissingBean`

Trong Spring Boot auto-configuration, hai annotation này thường xuất hiện gần nhau nhưng giải quyết hai giai đoạn khác nhau:

| Annotation | Giai đoạn | Vai trò |
| --- | --- | --- |
| `@ConditionalOnMissingBean` | Đăng ký bean definition của auto-configuration | Chỉ tạo fallback nếu chưa có bean phù hợp |
| `@Primary` | Phân giải dependency khi inject | Chọn candidate ưu tiên cho dependency đơn |
| `@Qualifier` | Phân giải dependency tại injection point | Thu hẹp candidate theo yêu cầu cụ thể |
| `@Order` | Sắp xếp ordered components/collection | Điều khiển thứ tự, không chọn primary |

Ví dụ:

```java
@AutoConfiguration
class SenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    @Primary
    MessageSender defaultMessageSender() {
        return new EmailSender();
    }
}
```

`@ConditionalOnMissingBean` quyết định có tạo fallback hay không. Nếu ứng dụng đã cung cấp một `MessageSender` mà condition nhận diện, fallback không được đăng ký. `@Primary` chỉ có ý nghĩa sau khi bean được đăng ký và Spring cần chọn candidate.

Nếu auto-configuration vô tình tạo thêm một bean cùng kiểu mà không có điều kiện back-off, việc đánh dấu bean đó `@Primary` chỉ ảnh hưởng lựa chọn injection; nó không ngăn bean của ứng dụng tồn tại hoặc tự động xóa bean kia.

## 8. Ma trận kiểm thử cần có

| Tình huống | Bean candidates | Injection point | Kết quả |
| --- | --- | --- | --- |
| Một candidate | Một sender | `MessageSender` | Inject sender duy nhất |
| Nhiều candidate, một primary | Email primary, SMS thường | `MessageSender` | Inject email |
| Nhiều candidate, không primary | Email, SMS | `MessageSender` | Ambiguous nếu không có tín hiệu khác |
| Nhiều candidate, qualifier | Email primary, SMS thường | `@Qualifier("smsSender") MessageSender` | Inject SMS |
| Hai primary | Email primary, SMS primary | `MessageSender` không qualifier | Ambiguous |
| Collection với primary | Email primary, SMS thường | `List<MessageSender>` | Nhận cả hai |
| Nhiều bean, không có consumer đơn | Email, SMS | Không có injection đơn | Context vẫn có thể chạy |

Một test tốt cần xác nhận cả hai mặt: bean nào được inject vào consumer đơn và những bean nào vẫn tồn tại trong context/collection.

## 9. Ví dụ chạy được: Java 17, Spring Boot 3.3.13 và `ApplicationContextRunner`

Dự án Maven nhỏ sau kiểm thử năm tình huống: một candidate, primary, không có primary, qualifier và hai primary. Test primary còn xác nhận collection injection vẫn nhận đủ hai implementation.

### 9.1. Cấu trúc dự án

```text
primary-candidate-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── PrimaryCandidateResolutionTest.java
```

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>primary-candidate-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 9.3. `PrimaryCandidateResolutionTest.java`

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;

class PrimaryCandidateResolutionTest {

    interface MessageSender {
        String channel();
    }

    static class EmailSender implements MessageSender {
        @Override
        public String channel() {
            return "email";
        }
    }

    static class SmsSender implements MessageSender {
        @Override
        public String channel() {
            return "sms";
        }
    }

    record NotificationService(MessageSender sender) {
    }

    record SenderRegistry(List<MessageSender> senders) {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void aSingleCandidateIsInjectedWithoutPrimary() {
        this.runner
                .withUserConfiguration(SingleCandidateConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(MessageSender.class);
                    assertThat(context.getBean(NotificationService.class)
                            .sender().channel()).isEqualTo("email");
                });
    }

    @Test
    void primaryWinsForSingleInjectionButOtherBeanRemainsInCollection() {
        this.runner
                .withUserConfiguration(PrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(NotificationService.class);

                    NotificationService service =
                            context.getBean(NotificationService.class);

                    assertThat(service.sender().channel()).isEqualTo("email");
                    assertThat(context.getBeansOfType(MessageSender.class))
                            .hasSize(2);

                    SenderRegistry registry =
                            context.getBean(SenderRegistry.class);

                    assertThat(registry.senders().stream()
                            .map(MessageSender::channel)
                            .toList())
                            .containsExactly("email", "sms");
                });
    }

    @Test
    void multipleCandidatesWithoutPrimaryFailSingleInjection() {
        this.runner
                .withUserConfiguration(AmbiguousConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }

    @Test
    void qualifierSelectsSmsEvenWhenEmailIsPrimary() {
        this.runner
                .withUserConfiguration(QualifiedConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBean(NotificationService.class)
                            .sender().channel()).isEqualTo("sms");
                });
    }

    @Test
    void twoPrimaryCandidatesAreStillAmbiguous() {
        this.runner
                .withUserConfiguration(TwoPrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class SingleCandidateConfiguration {

        @Bean
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        NotificationService notificationService(MessageSender sender) {
            return new NotificationService(sender);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryConfiguration {

        @Bean
        @Primary
        @Order(1)
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        @Order(2)
        MessageSender smsSender() {
            return new SmsSender();
        }

        @Bean
        NotificationService notificationService(MessageSender sender) {
            return new NotificationService(sender);
        }

        @Bean
        SenderRegistry senderRegistry(List<MessageSender> senders) {
            return new SenderRegistry(senders);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousConfiguration {

        @Bean
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        MessageSender smsSender() {
            return new SmsSender();
        }

        @Bean
        NotificationService notificationService(MessageSender sender) {
            return new NotificationService(sender);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class QualifiedConfiguration {

        @Bean
        @Primary
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        MessageSender smsSender() {
            return new SmsSender();
        }

        @Bean
        NotificationService notificationService(
                @Qualifier("smsSender") MessageSender sender) {
            return new NotificationService(sender);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoPrimaryConfiguration {

        @Bean
        @Primary
        MessageSender emailSender() {
            return new EmailSender();
        }

        @Bean
        @Primary
        MessageSender smsSender() {
            return new SmsSender();
        }

        @Bean
        NotificationService notificationService(MessageSender sender) {
            return new NotificationService(sender);
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

Maven Surefire có thể hiển thị thêm thời gian và tên test theo phiên bản plugin. Các test không ghi stdout tùy biến.

### 9.4. Ý nghĩa của năm test

| Test | Điều được chứng minh |
| --- | --- |
| `aSingleCandidateIsInjectedWithoutPrimary` | Một candidate không cần `@Primary` |
| `primaryWinsForSingleInjectionButOtherBeanRemainsInCollection` | Primary được inject đơn; collection vẫn nhận cả hai bean theo `@Order` |
| `multipleCandidatesWithoutPrimaryFailSingleInjection` | Hai candidate không có tín hiệu phân giải làm injection đơn thất bại |
| `qualifierSelectsSmsEvenWhenEmailIsPrimary` | Qualifier có thể yêu cầu candidate khác primary |
| `twoPrimaryCandidatesAreStillAmbiguous` | Nhiều primary phù hợp không tạo ra một lựa chọn duy nhất |

Test collection là bằng chứng trực tiếp rằng `@Primary` không phải bộ lọc bean. Test ambiguity cũng cho thấy hai bean cùng kiểu có thể tồn tại; lỗi chỉ xuất hiện khi consumer yêu cầu một bean duy nhất.

## 10. Cách chẩn đoán `NoUniqueBeanDefinitionException`

Khi context khởi động thất bại do nhiều candidate:

1. Xác định bean consumer đang được tạo.
2. Tìm constructor parameter, field hoặc method parameter đang yêu cầu một kiểu đơn trị.
3. Đọc kiểu dependency và danh sách candidate trong exception.
4. Kiểm tra qualifier có thiếu, sai giá trị hoặc không khớp bean không.
5. Kiểm tra candidate có một primary duy nhất hay không.
6. Nếu có nhiều primary, giữ một default hoặc dùng qualifier để thu hẹp.
7. Nếu quyết định phụ thuộc use case, thiết kế qualifier/strategy thay vì chọn default toàn cục.
8. Nếu consumer cần tất cả implementation, đổi dependency thành collection phù hợp.

Ví dụ lỗi có thể được bọc như sau:

```text
UnsatisfiedDependencyException
  caused by NoUniqueBeanDefinitionException:
  expected single matching bean but found 2:
  emailSender, smsSender
```

Format và tên bean cụ thể phụ thuộc cấu hình. Hãy dựa vào root cause và injection point, không dựa vào số dòng hoặc thông điệp chính xác.

Không nên sửa bằng cách thêm `@Primary` một cách máy móc. Nếu service gửi OTP bắt buộc dùng SMS, qualifier `smsSender` là hợp đồng chính xác hơn việc hy vọng SMS trở thành primary trong mọi context.

## 11. Những hiểu lầm thường gặp

**Hiểu lầm 1: Có hai bean cùng interface là lỗi.**  
Không đúng. Spring cho phép nhiều implementation cùng tồn tại. Lỗi phát sinh khi một dependency đơn không thể chọn duy nhất.

**Hiểu lầm 2: `@Primary` xóa bean còn lại.**  
Không đúng. Bean còn lại vẫn có trong context và có thể được lấy theo tên, qualifier hoặc collection.

**Hiểu lầm 3: `@Primary` làm list chỉ còn một phần tử.**  
Không đúng. Collection nhận tất cả candidate phù hợp; primary chỉ ảnh hưởng lựa chọn đơn trị.

**Hiểu lầm 4: `@Order(1)` tương đương `@Primary`.**  
Không đúng. Order sắp xếp collection/ordered processing; primary chọn candidate ưu tiên cho dependency đơn.

**Hiểu lầm 5: Hai bean primary thì Spring chọn bean khai báo trước.**  
Không nên dựa vào thứ tự khai báo. Nếu nhiều primary vẫn phù hợp với injection đơn, cần thêm qualifier hoặc thiết kế lại.

**Hiểu lầm 6: `@ConditionalOnMissingBean` và `@Primary` giống nhau.**  
Không đúng. Condition quyết định bean fallback có được đăng ký; primary chỉ tham gia chọn bean sau khi các bean đã tồn tại.

**Hiểu lầm 7: Context khởi động được chứng minh lựa chọn bean đúng nghiệp vụ.**  
Không đúng. Một primary có thể khiến context khởi động nhưng service vẫn dùng sai implementation. Test phải assert bean thực tế được inject.

## 12. Checklist thiết kế và kiểm thử

- [ ] Xác định consumer cần một implementation hay cần tất cả implementations.
- [ ] Nếu cần một default, chỉ đánh dấu một candidate phù hợp là `@Primary`.
- [ ] Nếu lựa chọn phụ thuộc từng consumer, dùng `@Qualifier`.
- [ ] Nếu cần tất cả candidate, dùng `List`, `Set`, array hoặc `Map<String, T>`.
- [ ] Nếu thứ tự collection quan trọng, dùng `@Order`/`Ordered`.
- [ ] Test trường hợp một candidate.
- [ ] Test nhiều candidate có một primary.
- [ ] Test nhiều candidate không primary và xác nhận root cause.
- [ ] Test qualifier chọn bean khác primary.
- [ ] Test nhiều primary còn phù hợp.
- [ ] Test collection vẫn chứa tất cả bean cần thiết.
- [ ] Với auto-configuration, kiểm tra thêm `@ConditionalOnMissingBean` để bean do ứng dụng cung cấp khiến fallback back off.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Context có hai bean `MessageSender`, một bean được đánh dấu `@Primary`. Constructor yêu cầu `MessageSender` nhận bean nào?  
**Đáp án:** Bean primary duy nhất trong các candidate phù hợp.

**Câu 2.** Có hai bean cùng kiểu, không có primary hoặc qualifier, và một constructor yêu cầu một bean. Điều gì xảy ra?  
**Đáp án:** Spring không thể chọn duy nhất và context thất bại với `NoUniqueBeanDefinitionException` (thường được bọc trong exception tạo bean).

**Câu 3.** Có một primary và một bean thường. `List<MessageSender>` nhận bao nhiêu bean?  
**Đáp án:** Cả hai candidate phù hợp; `@Primary` không lọc collection.

**Câu 4.** Email là primary nhưng injection point có `@Qualifier("smsSender")`. Bean nào được inject?  
**Đáp án:** SMS sender, vì qualifier yêu cầu candidate cụ thể.

**Câu 5.** Hai bean cùng kiểu đều được đánh dấu `@Primary`. Có thể dựa vào thứ tự khai báo để chọn một không?  
**Đáp án:** Không. Nếu cả hai vẫn phù hợp và không có tín hiệu phân giải khác, injection đơn tiếp tục ambiguous.

**Câu 6.** `@Order(1)` có làm bean trở thành primary không?  
**Đáp án:** Không. `@Order` điều khiển thứ tự; `@Primary` điều khiển lựa chọn candidate đơn.

**Câu 7.** `@ConditionalOnMissingBean` khác `@Primary` ở đâu?  
**Đáp án:** Condition quyết định có đăng ký fallback hay không; primary đánh dấu bean đã đăng ký là ứng viên ưu tiên khi inject đơn.

## 14. Nguyên tắc cần nhớ

- Nhiều bean cùng kiểu là hợp lệ; ambiguity chỉ xuất hiện khi injection point cần một bean duy nhất mà Spring không thể phân giải.
- `@Primary` chọn candidate ưu tiên cho injection đơn, không xóa bean khác.
- Nhiều candidate không có primary có thể gây `NoUniqueBeanDefinitionException` nếu qualifier hoặc metadata khác không giải quyết được.
- `@Qualifier` thể hiện lựa chọn tại từng injection point và có thể yêu cầu bean khác primary.
- `List`, `Set`, array và `Map<String, T>` nhận tất cả candidate phù hợp; `@Primary` không lọc collection.
- `@Order` sắp xếp collection trong những trường hợp Spring hỗ trợ, không thay thế `@Primary`.
- Nhiều primary còn phù hợp không tạo ra một lựa chọn duy nhất.
- Dùng `@ConditionalOnMissingBean` cho back-off của auto-configuration; dùng `@Primary` cho candidate resolution.

### Tài liệu tham khảo chính thức

- [Spring Framework — Using `@Primary` to Fine-tune Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Autowired Collections and Ordering](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Framework API — `NoUniqueBeanDefinitionException`](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/NoUniqueBeanDefinitionException.html)
