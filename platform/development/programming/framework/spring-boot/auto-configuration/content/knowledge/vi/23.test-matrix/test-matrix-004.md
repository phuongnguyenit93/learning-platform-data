# Kiểm tra `@Primary` cùng trường hợp nhiều ứng viên không có ứng viên chính

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Ma trận kiểm thử  
**Mục tiêu:** Hiểu cách Spring Framework chọn bean khi một injection point có nhiều ứng viên cùng kiểu; kiểm chứng `@Primary`, trường hợp không có bean chính, nhiều bean cùng được đánh dấu chính, `@Qualifier` và collection injection bằng các test độc lập.

## 1. Vì sao một kiểu có thể có nhiều bean?

Một ứng dụng Spring thường có nhiều implementation của cùng một interface. Ví dụ ứng dụng gửi thông báo có thể hỗ trợ email và SMS:

```java
public interface MessageSender {
    void send(String message);
}
```

Cả hai implementation đều hợp lệ:

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

Nếu một service yêu cầu đúng một `MessageSender`:

```java
@Service
class NotificationService {

    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = sender;
    }
}
```

Spring phải quyết định implementation nào sẽ được inject. Khi context chỉ có một candidate phù hợp, lựa chọn rất rõ ràng. Khi có nhiều candidate, Spring cần thêm thông tin để phân giải.

Nếu không có đủ thông tin để chọn một bean duy nhất, context thường thất bại khi tạo bean tiêu thụ dependency với `NoUniqueBeanDefinitionException`. Đây là lỗi phân giải dependency, không phải lỗi tạo hai bean cùng kiểu: Spring cho phép context có nhiều bean cùng implement một interface.

## 2. `@Primary` đánh dấu ứng viên ưu tiên

`@Primary` đánh dấu một bean là lựa chọn ưu tiên khi Spring cần inject **một giá trị đơn** và có nhiều ứng viên phù hợp.

Có thể đặt annotation trên class component:

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

Trong ví dụ trên, khi một constructor yêu cầu `MessageSender`, Spring chọn `emailSender` vì đây là candidate duy nhất được đánh dấu `@Primary`.

Một số điểm cần nhớ:

- `@Primary` không xóa hoặc vô hiệu hóa các bean còn lại.
- Cả `emailSender` và `smsSender` vẫn tồn tại trong `ApplicationContext`.
- `@Primary` không đổi bean name. Với `@Bean`, tên mặc định thường là tên phương thức; với component scanning, tên mặc định được suy ra từ tên class.
- `@Primary` là metadata cho quá trình phân giải dependency; nó không phải cơ chế điều kiện đăng ký bean và không thay thế `@ConditionalOnMissingBean`.
- Nếu ứng dụng cần chính xác một implementation theo từng use case, có thể dùng `@Qualifier` thay vì chọn một default toàn cục.

### 2.1. `@Primary` phù hợp khi nào?

Dùng `@Primary` khi một implementation là mặc định hợp lý cho phần lớn injection point trong ứng dụng.

Ví dụ:

- Có nhiều `PaymentGateway`, nhưng Stripe là gateway mặc định.
- Có nhiều `Clock`, nhưng ứng dụng production dùng system clock.
- Có nhiều `MessageSender`, nhưng email là kênh mặc định.
- Có nhiều `ObjectMapper`, nhưng một mapper là mặc định cho các service không yêu cầu cấu hình riêng.

Không nên gắn `@Primary` chỉ để làm context khởi động được nếu nghiệp vụ thực tế yêu cầu mỗi service chọn implementation khác nhau. Khi đó qualifier diễn tả ý định rõ ràng hơn.

## 3. Khi không có `@Primary` và có nhiều candidate

Giả sử context có:

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

và một bean yêu cầu:

```java
@Bean
NotificationService notificationService(MessageSender sender) {
    return new NotificationService(sender);
}
```

Cả hai bean đều là ứng viên hợp lệ. Không có qualifier, không có một candidate chính và cũng không có thông tin phân giải khác đủ để chọn duy nhất. Spring không nên tự đoán email hay SMS; việc chọn sai có thể làm thay đổi hành vi nghiệp vụ.

Kết quả là lỗi dạng:

```text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'MessageSender' available:
expected single matching bean but found 2
```

Thông báo đầy đủ có thể được bọc trong `UnsatisfiedDependencyException` hoặc `BeanCreationException`, tùy injection point và thời điểm khởi tạo. Hãy tìm `NoUniqueBeanDefinitionException` trong chuỗi `Caused by`.

### 3.1. Không phải cứ nhiều bean là luôn lỗi

Spring chỉ cần một candidate cho injection point yêu cầu một giá trị đơn. Nếu ứng dụng chỉ khai báo hai bean nhưng không có bean nào yêu cầu một `MessageSender` đơn lẻ, context vẫn có thể khởi động.

Ví dụ này hợp lệ:

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

Không có consumer đơn trị nên chưa có xung đột cần phân giải. Lỗi xuất hiện khi Spring phải tạo một dependency đơn và không thể chọn candidate duy nhất.

### 3.2. Spring có thể dùng thêm thông tin nào?

`@Primary` là một cơ chế quan trọng, nhưng không phải thông tin duy nhất. Tùy injection point và context, Spring còn có thể xét:

1. **Required type:** chỉ bean tương thích với kiểu dependency mới là candidate.
2. **Qualifier:** thu hẹp candidate theo qualifier được yêu cầu.
3. **Primary:** ưu tiên candidate được đánh dấu `@Primary` trong nhóm còn phù hợp.
4. **Priority:** metadata ưu tiên như `@Priority` có thể tham gia phân giải khi phù hợp.
5. **Tên dependency/bean:** tên parameter hoặc tên field có thể giúp chọn bean cùng tên nếu metadata tên parameter được giữ và các quy tắc phân giải cho phép.

Không nên dựa vào tên parameter như một cách thay thế cho contract rõ ràng. Với Java 17, có thể bật compiler option `-parameters` để giữ tên parameter; tuy nhiên, dùng `@Qualifier` thường dễ đọc và ổn định hơn khi đổi tên biến hoặc refactor.

Nếu sau các bước phân giải vẫn còn nhiều candidate ngang nhau, Spring ném `NoUniqueBeanDefinitionException`. Đừng coi thứ tự khai báo bean hoặc thứ tự component scan là quy tắc chọn mặc định.

## 4. `@Qualifier` chọn implementation cho từng injection point

`@Qualifier` cho phép yêu cầu một candidate cụ thể theo qualifier hoặc tên bean:

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

Nếu cấu hình có hai bean tên `emailSender` và `smsSender`, injection point này yêu cầu `smsSender`.

Qualifier có thể được đặt trên bean:

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

Một qualifier không nhất thiết chỉ là bean name. Nó có thể là annotation qualifier riêng có thuộc tính, ví dụ `@Region("asia")`, để mô tả một nhóm candidate theo ngữ nghĩa ứng dụng.

### 4.1. `@Qualifier` và `@Primary` phối hợp ra sao?

Qualifier thu hẹp tập ứng viên theo yêu cầu cụ thể của injection point. `@Primary` chọn candidate ưu tiên trong tập còn phù hợp nếu vẫn có nhiều candidate.

Ví dụ:

- `emailSender` được đánh dấu `@Primary`.
- `smsSender` không phải primary.
- Consumer có `@Qualifier("smsSender")`.

Consumer nhận `smsSender`. `@Primary` không ghi đè qualifier rõ ràng thành email.

Vì vậy, có thể kết hợp một default toàn cục bằng `@Primary` với những use case đặc biệt bằng `@Qualifier`.

## 5. `@Primary` không ảnh hưởng collection injection

Một điểm rất dễ nhầm: `@Primary` giải quyết injection đơn trị; nó **không lọc bỏ** các bean khác khi consumer yêu cầu nhiều candidate.

Ví dụ:

```java
@Bean
SenderRegistry senderRegistry(List<MessageSender> senders) {
    return new SenderRegistry(senders);
}
```

Nếu context có `emailSender` và `smsSender`, list nhận cả hai, kể cả khi email là primary.

Điều tương tự áp dụng với các dạng collection injection:

```java
MessageSender[] senders;
List<MessageSender> senders;
Set<MessageSender> senders;
Map<String, MessageSender> sendersByBeanName;
```

Với `Map<String, MessageSender>`, key là bean name và value là bean tương ứng. Các candidate phù hợp đều được đưa vào map.

Nếu cần sắp xếp thứ tự các bean trong array/list, dùng `@Order` hoặc `Ordered`:

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

`@Order` điều khiển thứ tự khi Spring tạo danh sách/array candidate trong các trường hợp hỗ trợ. Nó không đồng nghĩa với `@Primary` và không phải cách giải quyết ambiguity của một injection đơn trị. Một list có thứ tự không có nghĩa phần tử đầu tiên tự động trở thành primary.

## 6. Nhiều bean cùng được đánh dấu `@Primary`

Thông thường, một nhóm candidate phù hợp cho một injection đơn nên có tối đa một primary candidate.

Ví dụ không nên làm:

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

Nếu consumer yêu cầu một `MessageSender`, cả hai đều được đánh dấu ưu tiên. Spring vẫn không có cơ sở để chọn một bean duy nhất. Kết quả có thể tiếp tục là `NoUniqueBeanDefinitionException`.

Nếu có hai implementation cùng được đánh dấu primary, hãy sửa thiết kế theo một trong các cách:

- Chỉ giữ một default bằng `@Primary`.
- Dùng `@Qualifier` ở các injection point cần lựa chọn cụ thể.
- Chia interface theo vai trò rõ hơn nếu hai implementation phục vụ hai hợp đồng khác nhau.
- Dùng một factory/strategy bean có logic chọn implementation theo nghiệp vụ nếu quyết định phụ thuộc runtime input.

Không dùng `@Order` để giải quyết hai primary cùng kiểu; `@Order` không biến một bean thành primary duy nhất.

## 7. `@Primary` khác `@ConditionalOnMissingBean`

Hai annotation thường xuất hiện trong Spring Boot nhưng có nhiệm vụ khác nhau.

| Annotation | Mục đích | Kết quả |
| --- | --- | --- |
| `@Primary` | Chọn candidate ưu tiên khi inject một dependency đơn | Nhiều bean vẫn được đăng ký |
| `@Qualifier` | Thu hẹp candidate tại một injection point | Consumer nhận bean phù hợp qualifier |
| `@ConditionalOnMissingBean` | Chỉ đăng ký bean mặc định nếu chưa có bean phù hợp | Bean fallback có thể không được tạo |
| `@Order` | Sắp xếp một số collection/array hoặc ordered components | Không chọn default cho injection đơn |

Ví dụ auto-configuration:

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

Ở đây `@ConditionalOnMissingBean` quyết định có tạo default bean hay không. `@Primary` chỉ có ý nghĩa nếu default bean được tạo và sau đó có nhiều candidate phù hợp.

Nếu ứng dụng đã tự đăng ký một `MessageSender`, auto-configuration nhường chỗ; annotation `@Primary` trên bean fallback không ép Spring tạo thêm bean. Đây là back-off của auto-configuration, khác với việc chọn bean trong một context đã có nhiều candidate.

## 8. Ví dụ chạy được: kiểm thử candidate resolution bằng Java 17 và Spring Boot 3.3.13

Ta dùng `ApplicationContextRunner` để dựng các context nhỏ, mỗi test có một cấu hình riêng. Nhờ vậy có thể kiểm tra chính xác hành vi khi:

1. Có một candidate duy nhất.
2. Có hai candidate và đúng một `@Primary`.
3. Có hai candidate nhưng không có `@Primary`.
4. Có `@Qualifier` chọn candidate cụ thể.
5. Có hai primary candidate cùng lúc.
6. Inject collection để chứng minh cả hai bean vẫn được giữ lại.

### 8.1. Cấu trúc dự án

```text
primary-candidate-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── PrimaryCandidateResolutionTest.java
```

### 8.2. `pom.xml`

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

### 8.3. `PrimaryCandidateResolutionTest.java`

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
    void primaryWinsForSingleValuedInjectionButOtherBeanStillExists() {
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
                    assertThat(context).hasBean("emailSender");
                    assertThat(context).hasBean("smsSender");

                    SenderRegistry registry =
                            context.getBean(SenderRegistry.class);

                    assertThat(registry.senders())
                            .extracting(MessageSender::channel)
                            .containsExactly("email", "sms");
                });
    }

    @Test
    void multipleCandidatesWithoutPrimaryFailSingleValuedInjection() {
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

Maven Surefire có thể hiển thị thêm thông tin thời gian hoặc tên test theo phiên bản plugin. Các test không ghi stdout tùy biến.

### 8.4. Test đang chứng minh điều gì?

| Test | Cấu hình | Kết quả mong đợi |
| --- | --- | --- |
| `aSingleCandidateIsInjectedWithoutPrimary` | Chỉ có email sender | Context khởi động, inject email |
| `primaryWinsForSingleValuedInjectionButOtherBeanStillExists` | Email primary, SMS thường | Consumer đơn nhận email; registry vẫn có cả hai theo `@Order` |
| `multipleCandidatesWithoutPrimaryFailSingleValuedInjection` | Email và SMS, không primary/qualifier | Context fail với `NoUniqueBeanDefinitionException` |
| `qualifierSelectsSmsEvenWhenEmailIsPrimary` | Email primary, injection có qualifier SMS | Consumer nhận SMS |
| `twoPrimaryCandidatesAreStillAmbiguous` | Cả email và SMS đều primary | Context fail vì không có primary duy nhất |

Test thứ hai quan trọng nhất để hiểu đúng `@Primary`: bean email được chọn cho injection đơn, nhưng SMS vẫn có mặt trong `ApplicationContext` và trong `List<MessageSender>`. `@Primary` không phải một bộ lọc candidate cho collection.

Test thứ ba cho thấy lỗi chỉ xảy ra khi có một injection point yêu cầu một bean duy nhất. Nếu bỏ `NotificationService` khỏi cấu hình ambiguous, hai bean sender vẫn có thể cùng tồn tại mà không gây lỗi phân giải.

## 9. Đọc lỗi `NoUniqueBeanDefinitionException`

Khi ứng dụng khởi động thất bại do nhiều candidate, đọc thông tin exception theo thứ tự:

1. Xác định bean consumer đang được tạo, ví dụ `notificationService`.
2. Xác định injection point yêu cầu kiểu gì, ví dụ `MessageSender`.
3. Đọc danh sách candidate trong message exception.
4. Kiểm tra có qualifier nào bị thiếu hoặc sai tên không.
5. Kiểm tra có một primary candidate duy nhất không.
6. Nếu nhiều primary, loại bỏ sự mơ hồ bằng một default duy nhất hoặc qualifier.
7. Nếu quyết định phụ thuộc use case, dùng qualifier/strategy thay vì cố tạo một primary toàn cục.

Ví dụ lỗi thường có dạng:

```text
Parameter 0 of method notificationService in
demo.PrimaryCandidateResolutionTest$AmbiguousConfiguration
required a single bean, but 2 were found:
    - emailSender
    - smsSender
```

Tên class/method và cách trình bày thực tế phụ thuộc injection point và Spring version. Hãy dựa vào candidate type/name được báo, không dựa vào số dòng hoặc format exception cố định.

Có thể bật debug logging khi cần theo dõi quá trình tạo context:

```properties
debug=true
logging.level.org.springframework.beans.factory.support=DEBUG
```

Không nên bật logging quá chi tiết trong production lâu dài nếu log có thể quá lớn hoặc lộ thông tin cấu trúc nội bộ.

## 10. Những khác biệt cần nhớ

### 10.1. `@Primary` không phải `@Order`

- `@Primary`: chọn candidate cho dependency đơn khi có nhiều ứng viên.
- `@Order`: điều khiển thứ tự trong những collection/ordered processing được Spring hỗ trợ.
- `@Qualifier`: chọn candidate theo yêu cầu của injection point.

Không dùng `@Order(1)` với kỳ vọng nó sẽ làm bean đó thắng một injection đơn giống `@Primary`.

### 10.2. `@Primary` không phải `@ConditionalOnMissingBean`

- `@ConditionalOnMissingBean` quyết định có đăng ký bean fallback hay không.
- `@Primary` chỉ đánh dấu một bean đã được đăng ký là ưu tiên trong candidate resolution.
- Một bean có thể vừa là fallback có điều kiện vừa là primary, nhưng hai annotation giải quyết hai giai đoạn khác nhau.

### 10.3. `@Primary` không thay thế qualifier theo nghiệp vụ

Nếu một service luôn phải gửi SMS cho OTP, dùng `@Qualifier("smsSender")` để code thể hiện rõ yêu cầu. Đừng phụ thuộc vào việc SMS vô tình là primary ở một configuration khác.

### 10.4. Không phụ thuộc thứ tự khai báo

Thứ tự method `@Bean`, thứ tự file cấu hình hoặc thứ tự component scan không phải chính sách chọn bean mặc định. Khi cần quyết định rõ ràng, khai báo primary hoặc qualifier.

### 10.5. `@Primary` không thay đổi danh sách bean

Các bean không được chọn vẫn có thể được inject ở collection, được truy cập theo tên và được dùng tại injection point có qualifier riêng. Nếu muốn một bean không bao giờ là autowire candidate, đó là vấn đề cấu hình candidate khác; `@Primary` không làm việc đó.

## 11. Quy trình quyết định khi thiết kế nhiều implementation

Trước khi thêm `@Primary`, hãy trả lời:

1. Có thực sự cần một implementation mặc định cho toàn ứng dụng không?
2. Các consumer có cùng ý nghĩa khi nhận default đó không?
3. Những consumer đặc biệt có thể mô tả lựa chọn bằng qualifier không?
4. Có use case nào cần tất cả implementation dưới dạng collection không?
5. Thứ tự collection có quan trọng không? Nếu có, dùng `@Order`.
6. Auto-configuration có cần back off khi ứng dụng tự cung cấp bean không?
7. Có test cho một candidate, nhiều candidate, no-primary, qualifier và collection chưa?

Một thiết kế tốt thường dùng một primary default có chủ đích, qualifier cho các trường hợp chuyên biệt và collection injection khi cần fan-out. Nếu không có default đúng về mặt nghiệp vụ, hãy để ambiguity xuất hiện trong test thay vì âm thầm chọn một implementation tùy tiện.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Context có hai bean `MessageSender`, một bean được đánh dấu `@Primary`. Constructor yêu cầu `MessageSender` nhận bean nào?  
**Đáp án:** Bean duy nhất được đánh dấu primary, nếu cả hai vẫn là candidate phù hợp cho injection point.

**Câu 2.** Có hai bean cùng kiểu và không có `@Primary`, qualifier hay thông tin phân giải nào khác. Điều gì xảy ra khi một constructor yêu cầu đúng một bean?  
**Đáp án:** Spring không thể chọn duy nhất và context thất bại với `NoUniqueBeanDefinitionException` (thường được bọc trong exception tạo bean).

**Câu 3.** Có một primary và một bean thường. `List<MessageSender>` nhận bao nhiêu bean?  
**Đáp án:** Cả hai candidate phù hợp. `@Primary` không loại bean thường khỏi collection.

**Câu 4.** Email là primary nhưng injection point có `@Qualifier("smsSender")`. Bean nào được inject?  
**Đáp án:** SMS sender, vì qualifier yêu cầu candidate cụ thể cho injection point đó.

**Câu 5.** Hai bean cùng kiểu đều được đánh dấu `@Primary`. Có thể dựa vào thứ tự khai báo để chọn một không?  
**Đáp án:** Không. Nếu không có thông tin phân giải khác, vẫn ambiguous và có thể ném `NoUniqueBeanDefinitionException`.

**Câu 6.** `@Order(1)` có làm bean trở thành primary không?  
**Đáp án:** Không. `@Order` liên quan đến thứ tự; `@Primary` liên quan đến lựa chọn một candidate.

**Câu 7.** `@ConditionalOnMissingBean` và `@Primary` khác nhau ở đâu?  
**Đáp án:** Condition quyết định có đăng ký fallback hay không; primary đánh dấu bean đã đăng ký là ứng viên ưu tiên khi inject đơn.

## 13. Nguyên tắc cần nhớ

- Nhiều bean cùng kiểu là hợp lệ; lỗi chỉ xuất hiện khi một injection point cần một bean duy nhất nhưng không thể phân giải candidate.
- `@Primary` chọn một ứng viên ưu tiên cho injection đơn; nó không xóa bean còn lại.
- Nhiều candidate không có primary có thể gây `NoUniqueBeanDefinitionException` nếu qualifier, tên hoặc metadata ưu tiên khác không giải quyết được.
- `@Qualifier` thể hiện lựa chọn theo từng injection point và có thể thắng default primary khi qualifier chọn một candidate khác.
- `List`, `Set`, array và `Map<String, T>` nhận các candidate phù hợp; `@Primary` không lọc collection.
- `@Order` sắp xếp collection trong các trường hợp hỗ trợ, không thay thế `@Primary`.
- Hai primary cùng phù hợp không tạo ra một lựa chọn duy nhất.
- Dùng `@ConditionalOnMissingBean` cho back-off của auto-configuration; dùng `@Primary` cho candidate resolution.

### Tài liệu tham khảo chính thức

- [Spring Framework — Using `@Primary` to Fine-tune Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Using `@Order` with Component Scanning](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Framework API — `NoUniqueBeanDefinitionException`](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/NoUniqueBeanDefinitionException.html)
