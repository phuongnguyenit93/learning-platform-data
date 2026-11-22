# Kiểm thử auto-configuration có back-off khi người dùng cung cấp bean

Spring Boot nổi bật nhờ **auto-configuration**: framework có thể tự đăng ký các bean thường dùng dựa trên dependency và cấu hình hiện có. Tuy nhiên, tự động không đồng nghĩa áp đặt. Nếu ứng dụng chủ động cung cấp một bean đáp ứng vai trò mà auto-configuration định tạo, cấu hình mặc định thường phải **back off** — rút lui, không tạo thêm bean cạnh tranh.

Đây là một hợp đồng quan trọng khi phát triển thư viện, starter, hoặc kiểm thử các module tích hợp Spring Boot:

- **Không có bean do ứng dụng cung cấp:** auto-configuration tạo bean mặc định, để ứng dụng sử dụng được ngay.
- **Có bean tùy chỉnh phù hợp:** auto-configuration nhường quyền điều khiển cho ứng dụng.
- **Có điều kiện khác không đạt:** bean mặc định cũng có thể không được tạo, nhưng nguyên nhân không nhất thiết là back-off vì bean người dùng.

Một test tốt phải chứng minh cả **hai nhánh chính** và phân biệt chúng với tình huống không đăng ký bean vì lý do khác. Bài học xây ví dụ hoàn chỉnh với **@ConditionalOnMissingBean**, **@AutoConfiguration**, **ApplicationContextRunner**, **AutoConfigurations.of**, cách kiểm tra bean registry và các lỗi thường gặp về type, tên bean, thứ tự xử lý và parent context.

## 1. Back-off trong auto-configuration nghĩa là gì?

Giả sử một thư viện cung cấp khả năng gửi thông báo. Mặc định, thư viện muốn đăng ký một bean MessageSender:

~~~text
Ứng dụng Spring Boot
        │
        ▼
Auto-configuration được chọn
        │
        ▼
Đã có MessageSender bean thích hợp?
        │
    ┌───┴────┐
    │        │
   Chưa      Có
    │        │
    ▼        ▼
Tạo bean    Back off:
mặc định    không tạo bean mặc định
    │        │
    └───┬────┘
        ▼
Ứng dụng sử dụng MessageSender
~~~

Back-off không phải việc Spring Boot tạo bean rồi xóa đi. Thông thường, **điều kiện đăng ký bean được đánh giá trước**, và nếu điều kiện không đạt, bean definition mặc định không được đăng ký theo nhánh đó.

Ví dụ:

~~~java
@Bean
@ConditionalOnMissingBean(MessageSender.class)
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

Điều kiện nói: **chỉ đăng ký defaultMessageSender nếu trong phạm vi tìm kiếm phù hợp chưa có bean tương ứng với MessageSender**.

Nếu ứng dụng tự khai báo:

~~~java
@Bean
MessageSender myMessageSender() {
    return new CustomMessageSender();
}
~~~

thì bean mặc định phải nhường chỗ trong một auto-configuration được tổ chức đúng.

### 1.1. Back-off không phải @Primary

Giả sử auto-configuration luôn tạo DefaultMessageSender rồi ứng dụng tạo CustomMessageSender và đánh dấu custom bằng @Primary.

Khi đó cả hai bean vẫn có thể tồn tại:

~~~text
MessageSender beans:
- defaultMessageSender
- myMessageSender (@Primary)
~~~

@Primary chỉ hỗ trợ **chọn một bean** khi inject một dependency đơn; nó **không làm bean mặc định biến mất**. Code inject List<MessageSender> vẫn có thể nhận cả hai, và các bean phụ thuộc vào tên hoặc qualifier khác vẫn thấy default.

Vì thế back-off là hành vi **đăng ký bean có điều kiện**, còn @Primary là cơ chế **chọn ứng viên khi injection**.

### 1.2. Back-off không phải bean overriding

Bean overriding là tình huống một bean definition có cùng tên được định nghĩa lại theo cơ chế container. Spring Boot hiện đại thông thường không bật tùy tiện việc override bean definition theo tên.

Trong thiết kế back-off đúng:

- Không cần bật **spring.main.allow-bean-definition-overriding=true**.
- Không cần tạo hai bean trùng tên rồi để bean tùy chỉnh ghi đè.
- Không cần bắt exception do trùng definition sau khi khởi động.

Thay vào đó, auto-configuration **không đăng ký default** nếu điều kiện thiếu bean không đạt.

## 2. Vai trò của @ConditionalOnMissingBean

Annotation chính:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean
~~~

Nó có thể được đặt trên một @Bean method hoặc một configuration class khi cần điều kiện hóa đăng ký.

Ví dụ:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
@Bean
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

Điều kiện này được đánh giá trên thông tin bean definitions mà Spring biết ở thời điểm xử lý. Nó **không kiểm tra một database bên ngoài**, không gọi method send(), và không so sánh nội dung business logic.

### 2.1. Kiểm tra theo kiểu, theo tên hoặc tiêu chí khác

Những trường hợp hay gặp:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

Kiểm tra sự vắng mặt của bean thuộc kiểu MessageSender theo cơ chế matching của điều kiện.

~~~java
@ConditionalOnMissingBean(name = "messageSender")
~~~

Kiểm tra sự vắng mặt của bean có tên tương ứng.

~~~java
@ConditionalOnMissingBean(annotation = MyMarker.class)
~~~

Kiểm tra sự vắng mặt của bean có annotation thích hợp theo quy tắc của condition.

Khi kết hợp các tiêu chí, phải hiểu chúng tạo ra một hợp đồng khác nhau. **Tên bean không đồng nghĩa kiểu bean** và một ứng dụng có thể cung cấp cùng kiểu với tên tùy ý.

Ví dụ bean người dùng tên **myMessageSender** vẫn có type MessageSender. Kiểm tra bằng name="messageSender" có thể không xem nó là sự thay thế, trong khi kiểm tra bằng type MessageSender.class có thể back off như mong muốn.

### 2.2. Khi không ghi rõ type trên @Bean method

Với một @Bean method:

~~~java
@Bean
@ConditionalOnMissingBean
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

Spring Boot có thể suy ra kiểu cần kiểm tra từ **return type của @Bean method**.

Tuy vậy, ghi rõ:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

thường giúp người đọc hiểu chính xác hợp đồng back-off, nhất là trong một starter cung cấp interface mà người dùng được khuyến khích tùy biến.

### 2.3. Vì sao return type trong @Bean quan trọng?

Giả sử ứng dụng tự khai báo:

~~~java
@Bean
Object customBean() {
    return new CustomMessageSender();
}
~~~

Mặc dù object thực tế là CustomMessageSender, bean definition có thể chỉ công bố return type **Object** trong quá trình đánh giá condition. Framework có thể chưa biết nó là MessageSender khi quyết định có đăng ký bean mặc định hay không.

Đó là lý do nên khai báo type cụ thể và chính xác:

~~~java
@Bean
MessageSender customMessageSender() {
    return new CustomMessageSender();
}
~~~

Khi phát triển auto-configuration, **metadata của bean definition tại lúc đánh giá điều kiện** thường quan trọng hơn runtime object mà ta nghĩ sẽ được tạo sau đó.

## 3. Vì sao annotation này phù hợp đặc biệt với auto-configuration?

Tài liệu và cách sử dụng của Spring Boot nhấn mạnh rằng các điều kiện kiểu **@ConditionalOnBean** và **@ConditionalOnMissingBean** phụ thuộc vào những bean definitions **đã được xử lý đến thời điểm đánh giá**.

Nếu đặt chúng trong một @Configuration class thông thường không có thứ tự thích hợp, kết quả có thể phụ thuộc vào việc class nào được xử lý trước.

Ví dụ một cấu hình mặc định nằm trong app:

~~~java
@Configuration(proxyBeanMethods = false)
class DefaultSenderConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

Nếu cấu hình này được xử lý **trước** một user configuration có MessageSender, điều kiện có thể không nhìn thấy user bean definition như mong đợi.

### 3.1. Boot tổ chức auto-configuration sau user configuration

Auto-configuration được Spring Boot xử lý thông qua cơ chế import và có những quy tắc ordering để thường **nhường ưu tiên cho user bean definitions**.

Đây là ý nghĩa thiết kế của @AutoConfiguration và điều kiện missing-bean:

~~~text
User configuration / component scanning
                │
                ▼
Spring biết những bean definitions ứng dụng cung cấp
                │
                ▼
Auto-configuration được xử lý
                │
                ▼
@ConditionalOnMissingBean có đủ thông tin để back off
~~~

Sơ đồ là mô hình khái niệm; quá trình startup của Spring có nhiều mốc đăng ký definitions và xử lý conditions. Điểm cần nhớ là không nên tùy ý dùng missing-bean condition trong một configuration class được import sớm rồi trông chờ nó luôn back off.

### 3.2. Auto-configuration ordering cũng quan trọng

Hai auto-configurations có thể cùng tham gia tạo các beans liên quan. Spring Boot hỗ trợ các cơ chế ordering như:

~~~java
@AutoConfiguration(after = SomeOtherAutoConfiguration.class)
~~~

hoặc before/after name khi thích hợp.

Ordering giúp condition nhìn thấy những bean definitions dự định do auto-configuration trước đăng ký. Nó **không thay thế** dependency injection hoặc quyết định runtime initialization order của tất cả bean instances.

Khi kiểm thử back-off, cần mô phỏng đúng cách Spring Boot import auto-configuration, thay vì chỉ tự tạo new instance hoặc gọi @Bean method bằng tay.

## 4. Ví dụ xuyên suốt: một starter gửi thông báo

Ta xây module minh họa có public interface MessageSender và default implementation do thư viện cung cấp.

Cấu trúc logic:

~~~text
com.example.messaging/
├── MessageSender.java
├── DefaultMessageSender.java
└── autoconfigure/
    └── MessageSenderAutoConfiguration.java

com.example.demo/
├── DemoApplication.java
└── CustomMessageSenderConfiguration.java
~~~

Vì đây là tài liệu học, các package có thể được đặt trong một project để thử nghiệm. Trong một starter thật, API, auto-configuration và consumer application thường là những module hoặc artifact khác nhau.

### 4.1. Interface mà ứng dụng sử dụng

~~~java
package com.example.messaging;

public interface MessageSender {
    String send(String recipient, String message);
}
~~~

Ví dụ dùng String làm kết quả để dễ kiểm thử mà không cần mạng hoặc dịch vụ bên ngoài.

### 4.2. Implementation mặc định

~~~java
package com.example.messaging;

public final class DefaultMessageSender
        implements MessageSender {

    @Override
    public String send(String recipient, String message) {
        return "default:" + recipient + ":" + message;
    }
}
~~~

Class này không tự có @Component. Nó sẽ được tạo bởi auto-configuration, nhờ vậy việc đăng ký default do một nơi rõ ràng kiểm soát.

### 4.3. Auto-configuration có điều kiện back-off

~~~java
package com.example.messaging.autoconfigure;

import com.example.messaging.DefaultMessageSender;
import com.example.messaging.MessageSender;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class MessageSenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

Giải thích:

- **@AutoConfiguration** đánh dấu đây là configuration phục vụ auto-configuration.
- **@Bean** khai báo factory method tạo MessageSender.
- **@ConditionalOnMissingBean(MessageSender.class)** yêu cầu chưa có bean type MessageSender phù hợp.
- **DefaultMessageSender** chỉ là implementation được chọn khi cần fallback.

Trong một Spring Boot starter thực tế, auto-configuration cần được đăng ký cho Boot phát hiện, chẳng hạn qua file imports dành cho auto-configuration của Boot 3:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung ví dụ:

~~~text
com.example.messaging.autoconfigure.MessageSenderAutoConfiguration
~~~

Khi thư viện có trên classpath của một ứng dụng Spring Boot và được đăng ký đúng, Boot có thể import auto-configuration này.

Trong các unit-style tests ở phần sau, ta dùng **AutoConfigurations.of** để thêm class auto-configuration trực tiếp vào context thử nghiệm, **không cần** đóng gói starter hoặc tạo file imports chỉ để kiểm tra điều kiện.

### 4.4. Implementation do ứng dụng cung cấp

~~~java
package com.example.demo;

import com.example.messaging.MessageSender;

public final class CustomMessageSender
        implements MessageSender {

    @Override
    public String send(String recipient, String message) {
        return "custom:" + recipient + ":" + message;
    }
}
~~~

Và user configuration:

~~~java
package com.example.demo;

import com.example.messaging.MessageSender;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomMessageSenderConfiguration {

    @Bean
    MessageSender customMessageSender() {
        return new CustomMessageSender();
    }
}
~~~

Ở đây tên bean **customMessageSender** khác tên **defaultMessageSender**. Ta cố ý dùng tên khác để chứng minh condition **back off theo type**, không phải vì hai definitions trùng bean name.

### 4.5. Ứng dụng sử dụng interface

~~~java
package com.example.demo;

import com.example.messaging.MessageSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final MessageSender sender;

    public NotificationService(MessageSender sender) {
        this.sender = sender;
    }

    public String notifyRecipient(String recipient) {
        return sender.send(recipient, "Hello");
    }
}
~~~

NotificationService không cần biết default hay custom implementation. Contract của auto-configuration là cố gắng để có một MessageSender thích hợp **nếu ứng dụng chưa tự cung cấp**.

## 5. ApplicationContextRunner là gì?

**ApplicationContextRunner** là công cụ kiểm thử do Spring Boot cung cấp để khởi tạo một ApplicationContext nhỏ, có thể tùy chỉnh bằng configuration classes, auto-configuration imports, property values và beans.

Import:

~~~java
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
~~~

Nó phù hợp để kiểm thử auto-configuration vì:

- Không cần chạy một web server.
- Không cần khởi động toàn bộ ứng dụng bằng @SpringBootTest.
- Mỗi lần **run** tạo một context có phạm vi rõ ràng và được đóng khi callback hoàn tất.
- Test dễ dựng các tình huống **có hoặc không có user-defined bean**.
- Có thể quan sát cả successful startup lẫn startup failure.
- Có thể phối hợp với **AutoConfigurations.of(...)** để import những auto-configurations cần kiểm tra.

Sơ đồ một test:

~~~text
ApplicationContextRunner
     │
     ├── withConfiguration(AutoConfigurations.of(...))
     ├── withUserConfiguration(...) [nếu test custom bean]
     ├── withPropertyValues(...)    [nếu cần]
     └── run(context -> assertions)
                            │
                            ▼
                 Tạo context thử nghiệm
                            │
                            ▼
                 Đánh giá conditional beans
                            │
                            ▼
                 Assert bean được/không được tạo
                            │
                            ▼
                   Đóng test context
~~~

### 5.1. Dependency cho kiểm thử

Trong một ứng dụng Spring Boot dùng Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter test thường cung cấp JUnit Jupiter, AssertJ và spring-boot-test. Ví dụ trong bài giả định dự án đã quản lý phiên bản dependencies tương thích với Spring Boot đang dùng.

Nếu module auto-configuration được tách riêng và không có spring-boot-starter-test, hãy thêm những test dependencies phù hợp, bao gồm **spring-boot-test**, JUnit Jupiter và AssertJ.

### 5.2. AutoConfigurations.of khác gì withUserConfiguration?

Ví dụ:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                MessageSenderAutoConfiguration.class))
        .withUserConfiguration(
                CustomMessageSenderConfiguration.class);
~~~

Hai phương thức biểu thị hai vai trò:

- **withConfiguration(AutoConfigurations.of(...))**: đưa auto-configuration vào context theo cơ chế hỗ trợ test của Spring Boot.
- **withUserConfiguration(...)**: đưa configuration do ứng dụng cung cấp vào context.

Sự phân biệt này giúp test mô phỏng đúng thiết kế: user bean có quyền thay thế default của starter.

Trong môi trường thực tế, auto-configurations thường được phát hiện qua danh sách imports của thư viện. Trong context runner, chúng được khai báo trực tiếp để test tập trung và nhanh.

## 6. Test nhánh A: không có custom bean thì default được tạo

Đây là test cơ bản đầu tiên.

~~~java
package com.example.messaging.autoconfigure;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.messaging.DefaultMessageSender;
import com.example.messaging.MessageSender;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class MessageSenderAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    MessageSenderAutoConfiguration.class));

    @Test
    void createsDefaultSenderWhenNoUserBeanExists() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(MessageSender.class);
            assertThat(context).hasBean("defaultMessageSender");

            MessageSender sender =
                    context.getBean(MessageSender.class);

            assertThat(sender)
                    .isInstanceOf(DefaultMessageSender.class);

            assertThat(sender.send("customer-1", "hello"))
                    .isEqualTo("default:customer-1:hello");
        });
    }
}
~~~

Test này chứng minh những điều gì?

1. Context khởi động thành công.
2. Có **đúng một** bean MessageSender mà test quan sát được.
3. Bean mặc định tên **defaultMessageSender** tồn tại.
4. Bean được inject theo type là DefaultMessageSender.
5. Behavior đơn giản của implementation hoạt động như mong đợi.

Điểm (1)–(4) mới là trọng tâm của kiểm thử auto-configuration. Điểm (5) là một sanity check bổ sung; hành vi gửi thông báo phức tạp có thể được kiểm thử riêng ở unit tests của implementation.

### 6.1. Vì sao assert hasSingleBean quan trọng?

Chỉ viết:

~~~java
assertThat(context).hasBean("defaultMessageSender");
~~~

chứng minh bean có tên đó tồn tại, nhưng chưa nói có một MessageSender khác bị đăng ký ngoài ý định hay không.

Với hợp đồng fallback một candidate:

~~~java
assertThat(context).hasSingleBean(MessageSender.class);
~~~

giúp phát hiện trường hợp có quá nhiều beans cùng type trong một test context.

### 6.2. Đừng chỉ kiểm tra ApplicationContext không lỗi

Một context không lỗi vẫn có thể **không có MessageSender** nếu auto-configuration bị condition khác loại bỏ.

~~~java
assertThat(context).hasNotFailed();
~~~

là điều kiện cần, chưa đủ. Kiểm tra sự hiện diện và type của default bean mới xác nhận đúng mục tiêu.

## 7. Test nhánh B: có custom bean thì default back off

Đây là test **quan trọng nhất** của bài học.

Từ runner ở phần trước, thêm user configuration:

~~~java
@Test
void backsOffWhenUserProvidesMessageSender() {
    contextRunner
            .withUserConfiguration(
                    CustomMessageSenderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .hasSingleBean(MessageSender.class);

                assertThat(context)
                        .hasBean("customMessageSender");
                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");

                MessageSender sender =
                        context.getBean(MessageSender.class);

                assertThat(sender)
                        .isInstanceOf(CustomMessageSender.class);

                assertThat(sender.send("customer-1", "hello"))
                        .isEqualTo("custom:customer-1:hello");
            });
}
~~~

Nhớ import hai class demo vào test:

~~~java
import com.example.demo.CustomMessageSender;
import com.example.demo.CustomMessageSenderConfiguration;
~~~

Kết quả mà test mong đợi:

~~~text
Context:
  customMessageSender   -> CustomMessageSender

Không tồn tại:
  defaultMessageSender  -> DefaultMessageSender

MessageSender beans count = 1
~~~

### 7.1. Ba assertion cốt lõi

Trong nhánh back-off, tối thiểu nên chứng minh:

~~~java
assertThat(context).hasSingleBean(MessageSender.class);
assertThat(context).hasBean("customMessageSender");
assertThat(context).doesNotHaveBean("defaultMessageSender");
~~~

Vì sao cần cả ba?

- Bean custom tồn tại → user configuration thực sự được đưa vào test.
- Bean default không tồn tại → auto-configuration đã back off.
- Có đúng một MessageSender → không tạo hai candidates gây ambiguity.

Nếu chỉ kiểm tra CustomMessageSender có thể inject được, test vẫn có thể pass trong một context chứa **cả custom và default** khi @Primary hoặc @Qualifier che mất sự trùng lặp.

### 7.2. Chứng minh back-off theo type chứ không theo name

Trong ví dụ, tên bean custom là **customMessageSender**, khác hẳn **defaultMessageSender**. Vì vậy:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

phải back off dựa vào kiểu MessageSender. Không thể giải thích kết quả thành việc custom bean ghi đè cùng tên default.

Đây là đặc tính quan trọng khi thiết kế starter: ứng dụng không bị buộc phải sử dụng tên bean mà thư viện lựa chọn.

### 7.3. Không tạo custom bean bằng new ở ngoài Spring

Ví dụ:

~~~java
MessageSender sender = new CustomMessageSender();
~~~

chỉ tạo một object Java ở local variable. Nó **không trở thành bean trong ApplicationContext** và do đó không thể khiến @ConditionalOnMissingBean back off.

Một test đúng phải đăng ký bean thông qua Spring, ví dụ:

- @Bean trong một user configuration.
- withBean(...) của ApplicationContextRunner.
- Component scan được thiết lập rõ ràng.
- Một cơ chế bean registration tương đương.

## 8. Một cách test ngắn gọn: withBean

Khi không cần tạo một @Configuration class riêng, ApplicationContextRunner có thể đăng ký bean trực tiếp:

~~~java
@Test
void backsOffForProgrammaticallyRegisteredUserBean() {
    contextRunner
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(
                        MessageSender.class);

                assertThat(context.getBean(
                        MessageSender.class))
                        .isInstanceOf(
                                CustomMessageSender.class);

                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");
            });
}
~~~

**withBean** giúp tạo đúng một user-defined bean với type/instance supplier do test kiểm soát.

Ưu điểm:

- Ít boilerplate.
- Tập trung vào điều kiện có hoặc không có bean.
- Không cần định nghĩa test configuration riêng cho mỗi biến thể.

Tuy nhiên, **withUserConfiguration** vẫn cần thiết nếu muốn kiểm tra cách ứng dụng thực sự khai báo @Bean, qualifiers, bean names, scopes hoặc điều kiện trên configuration class.

### 8.1. Nên chọn withBean hay withUserConfiguration?

| Nhu cầu kiểm thử | Cách thường phù hợp |
|---|---|
| Chỉ cần một user bean cùng type | withBean(MessageSender.class, ...) |
| Muốn chứng minh user @Bean method gây back-off | withUserConfiguration(...) |
| Muốn kiểm tra nhiều @Bean methods tương tác | withUserConfiguration(...) |
| Muốn kiểm tra bean name/qualifier được khai báo thật | withUserConfiguration(...) |
| Muốn dùng một instance giả đơn giản | withBean(...) |
| Muốn mô phỏng app thực tế có nhiều cấu hình | withUserConfiguration(...) kết hợp context runner |

Hai cách đều tạo bean trong test context; điều quan trọng là test phải kiểm tra **default vắng mặt** khi custom bean hiện diện.

## 9. Một bộ kiểm thử tối thiểu nhưng đủ ý nghĩa

Có thể đặt hai test cạnh nhau để người bảo trì thấy ngay hợp đồng:

~~~java
package com.example.messaging.autoconfigure;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.demo.CustomMessageSender;
import com.example.messaging.DefaultMessageSender;
import com.example.messaging.MessageSender;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class MessageSenderBackOffTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            MessageSenderAutoConfiguration.class));

    @Test
    void registersDefaultIfNothingIsProvided() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(MessageSender.class);
            assertThat(context.getBean(MessageSender.class))
                    .isInstanceOf(DefaultMessageSender.class);
        });
    }

    @Test
    void backsOffWhenUserProvidesBean() {
        runner.withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            MessageSender.class);
                    assertThat(context.getBean(
                            MessageSender.class))
                            .isInstanceOf(
                                    CustomMessageSender.class);
                    assertThat(context)
                            .doesNotHaveBean(
                                    "defaultMessageSender");
                });
    }
}
~~~

Nếu phải chọn một cặp test bắt buộc cho mọi auto-configuration có @ConditionalOnMissingBean, đây là cặp có giá trị cao:

**Mặc định tồn tại khi không có user bean; mặc định biến mất khi có user bean.**

Nó xác minh behavior chứ không chỉ kiểm tra annotation đã xuất hiện trong source.

## 10. Điều gì xảy ra nếu có hai user beans cùng kiểu?

Giả sử ứng dụng đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
public class TwoSendersConfiguration {

    @Bean
    MessageSender primaryBusinessSender() {
        return new CustomMessageSender();
    }

    @Bean
    MessageSender secondaryBusinessSender() {
        return new AnotherMessageSender();
    }
}
~~~

AnotherMessageSender là một implementation khác của MessageSender do ứng dụng cung cấp.

Điều kiện:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

vẫn có thể back off, vì **đã có MessageSender bean**. Nhưng khi đó ứng dụng có **hai user beans**; việc inject một MessageSender không có qualifier có thể thất bại vì không thể chọn duy nhất.

Một test tập trung vào condition có thể xác minh:

~~~java
@Test
void backsOffEvenWhenMultipleUserSendersExist() {
    contextRunner
            .withUserConfiguration(
                    TwoSendersConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");
                assertThat(context.getBeansOfType(
                        MessageSender.class)).hasSize(2);
            });
}
~~~

Test trên giả định context không chứa một consumer bắt buộc inject đúng một MessageSender. Nếu có NotificationService như ví dụ ban đầu được component scan/import và nó inject một MessageSender không có qualifier, context có thể fail vì ambiguity.

### 10.1. Back-off không bảo đảm chỉ có một user bean

Những phát biểu sau khác nhau:

- “Thư viện không tạo default khi ứng dụng có MessageSender” — hợp đồng back-off.
- “Ứng dụng luôn có đúng một MessageSender” — một hợp đồng tổng thể khác, có thể cần ràng buộc thêm.

Không nên xem @ConditionalOnMissingBean như cơ chế kiểm tra uniqueness của tất cả beans do người dùng tự đăng ký.

### 10.2. Phân biệt với @ConditionalOnSingleCandidate

Spring Boot còn cung cấp:

~~~java
@ConditionalOnSingleCandidate(MessageSender.class)
~~~

Điều kiện này phục vụ tình huống một configuration muốn đăng ký bean phụ thuộc khi chỉ có một candidate có thể được chọn theo quy tắc của condition, chẳng hạn một bean duy nhất hoặc một primary candidate phù hợp.

Đây là nhu cầu khác với **@ConditionalOnMissingBean**:

- MissingBean: đăng ký default **khi chưa có candidate phù hợp**.
- SingleCandidate: đăng ký phần phụ thuộc **khi có thể chọn được candidate phù hợp**.

Một auto-configuration lớn có thể dùng cả hai loại điều kiện ở những bean methods khác nhau, nhưng chúng không thay thế trực tiếp cho nhau.

## 11. Bean name và bean type dẫn tới những nhánh khác nhau

Giả sử user bean:

~~~java
@Bean("customSender")
MessageSender sender() {
    return new CustomMessageSender();
}
~~~

Điều kiện theo type:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

thường back off vì đã có MessageSender.

Nhưng điều kiện theo name:

~~~java
@ConditionalOnMissingBean(name = "defaultMessageSender")
~~~

không nhất thiết back off, vì context chưa có bean tên **defaultMessageSender**. Auto-configuration có thể tạo một MessageSender khác, và dẫn tới hai beans cùng kiểu.

### 11.1. Test chứng minh contract theo type

User configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class NamedCustomSenderConfiguration {

    @Bean("senderChosenByApplication")
    MessageSender chosenSender() {
        return new CustomMessageSender();
    }
}
~~~

Test:

~~~java
@Test
void doesNotRequireUserBeanToHaveDefaultName() {
    contextRunner
            .withUserConfiguration(
                    NamedCustomSenderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .hasBean("senderChosenByApplication");
                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");
                assertThat(context)
                        .hasSingleBean(MessageSender.class);
            });
}
~~~

Đây là một test hữu ích khi viết starter công khai, vì người dùng không nên phải biết internal default bean name chỉ để tự cung cấp implementation.

### 11.2. Khi nào back-off theo name có ích?

Kiểm tra theo name hợp lý nếu hợp đồng thật sự xoay quanh **một tên bean định danh cụ thể**, ví dụ integration được các phần khác truy cập bởi bean name mà không quan tâm đến một type chung rộng.

Tuy nhiên, với phần lớn SPI theo interface, back-off theo type thường diễn đạt chính xác hơn mục tiêu “người dùng đã cung cấp một implementation”.

### 11.3. Tên method @Bean có thể ảnh hưởng bean name

Khi không chỉ định name:

~~~java
@Bean
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

bean name thường lấy từ tên method **defaultMessageSender**.

Nếu đổi method name, test hard-code bean name cần được cập nhật, dù behavior theo type không đổi. Vì vậy:

- Dùng **hasSingleBean(type)** và **isInstanceOf** cho contract type.
- Dùng **doesNotHaveBean(name)** khi cần chứng minh chính definition mặc định đã được loại bỏ.

Hai dạng assertion bổ sung nhau, không phải luôn thay thế nhau.

## 12. Vì sao return type của user @Bean phải rõ ràng?

Đây là một lỗi dễ gây bất ngờ khi chuyển từ unit test sang auto-configuration.

User có:

~~~java
@Bean
Object customSender() {
    return new CustomMessageSender();
}
~~~

Auto-configuration có:

~~~java
@Bean
@ConditionalOnMissingBean(MessageSender.class)
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

Tại thời điểm điều kiện được đánh giá, Spring có thể chỉ biết bean custom có type **Object** theo signature khai báo. Nếu instance chưa được tạo, metadata có thể không chứng minh nó là MessageSender.

Hệ quả có thể xảy ra:

1. @ConditionalOnMissingBean(MessageSender.class) được đánh giá là phù hợp.
2. defaultMessageSender được đăng ký.
3. Về sau customSender tạo instance CustomMessageSender.
4. ApplicationContext có thể có hai objects cùng khả năng MessageSender, hoặc behavior khác tùy cách tra cứu/candidate detection.

### 12.1. Cách viết tốt hơn

~~~java
@Bean
MessageSender customSender() {
    return new CustomMessageSender();
}
~~~

Hoặc:

~~~java
@Bean
CustomMessageSender customSender() {
    return new CustomMessageSender();
}
~~~

Nếu CustomMessageSender implement MessageSender, type cụ thể cũng giúp container suy luận assignability.

### 12.2. Bài học về kiểm thử

Một test với:

~~~java
.withBean(MessageSender.class, CustomMessageSender::new)
~~~

đăng ký type rất rõ nên có thể pass. Nhưng nếu ứng dụng thật lại dùng một factory method khai báo return type Object, behavior có thể không tương đương.

Vì vậy, nếu starter phải hỗ trợ **cách ứng dụng thực tế khai báo user bean**, nên có ít nhất một test dùng **withUserConfiguration** và signature @Bean đại diện cho cách tích hợp được công bố.

### 12.3. FactoryBean, generic container và type inference phức tạp

Trong Spring, một số beans được tạo qua FactoryBean, proxy hoặc generic wrapper. Thông tin type có thể không hoàn chỉnh ở thời điểm điều kiện được đánh giá.

Spring Boot cung cấp những thuộc tính nâng cao cho @ConditionalOnMissingBean, ví dụ khả năng xem xét **parameterizedContainer** hoặc bỏ qua một số types qua **ignored**.

Đó là các công cụ dành cho contract đặc thù. Nếu không có yêu cầu cụ thể, nên bắt đầu từ điều kiện đơn giản theo interface và viết tests chứng minh hành vi thay thế.

## 13. Bean definition tồn tại khác với instance đã được tạo

@ConditionalOnMissingBean thường dựa trên **bean definitions và thông tin type** đang được Spring biết. Nó không yêu cầu user bean đã thực hiện mọi logic khởi tạo.

Ví dụ:

~~~java
@Bean
@Lazy
MessageSender customMessageSender() {
    return new CustomMessageSender();
}
~~~

Khi @Bean definition đã được đăng ký và type được công bố, auto-configuration có thể back off dù instance được đánh dấu lazy và chưa cần khởi tạo ngay.

### 13.1. Đừng test bằng cách đếm constructor calls rồi kết luận về definition

Giả sử test kiểm tra số lần constructor DefaultMessageSender được gọi. Nếu count là 0, chưa chắc default bean definition không tồn tại: nó có thể là lazy bean chưa được tạo.

Để chứng minh back-off:

~~~java
assertThat(context).doesNotHaveBean("defaultMessageSender");
~~~

hoặc kiểm tra bean definitions/bean names tương ứng. Quan sát số instance tạo ra chỉ là một tín hiệu phụ.

### 13.2. Scope không tự làm một bean bị bỏ qua

Một bean prototype hoặc scoped proxy có thể tham gia condition evaluation theo metadata và các cơ chế matching của Spring. Không nên giả định “chỉ singleton mới khiến auto-configuration back off”.

Khi type/scopes phức tạp, hãy tạo test context cho chính kiểu user bean mà thư viện muốn hỗ trợ.

## 14. Phân biệt back-off với các điều kiện khác

Một auto-configuration thực tế thường không chỉ có @ConditionalOnMissingBean.

Ví dụ:

~~~java
@AutoConfiguration
public class MessageSenderAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.message",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

Nhớ import:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
~~~

Ở đây hai điều kiện cùng tham gia:

- Feature được bật hoặc property vắng mặt và matchIfMissing=true.
- Chưa có MessageSender bean.

### 14.1. Ma trận các trường hợp

| Feature enabled? | User MessageSender? | Default MessageSender? | Lý do |
|---|---|---|---|
| Không khai báo, matchIfMissing=true | Không | Có | Default được phép đăng ký |
| true | Không | Có | Các điều kiện đều phù hợp |
| true | Có | Không | Back-off do user bean |
| false | Không | Không | Feature bị tắt, **không phải** back-off |
| false | Có | Không | Feature tắt; user bean vẫn tồn tại nếu được đăng ký độc lập |

Nếu test chỉ thấy default vắng mặt, nó chưa phân biệt được **vì user bean đã tồn tại** hay **vì feature bị tắt**. Phải dựng scenario và assertion cho từng nhánh.

### 14.2. Test feature disabled

~~~java
@Test
void doesNotCreateDefaultWhenFeatureIsDisabled() {
    contextRunner
            .withPropertyValues(
                    "acme.message.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean(MessageSender.class);
            });
}
~~~

Test này kiểm tra một **điều kiện feature**, không phải test back-off. Nó giúp bảo đảm khi test back-off fail, nhóm không nhầm nguyên nhân với property enable/disable.

### 14.3. Test user bean vẫn tồn tại khi auto-config bị disable

~~~java
@Test
void userBeanIsIndependentOfDefaultFeatureFlag() {
    contextRunner
            .withPropertyValues(
                    "acme.message.enabled=false")
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .hasSingleBean(MessageSender.class);
                assertThat(context.getBean(
                        MessageSender.class))
                        .isInstanceOf(
                                CustomMessageSender.class);
                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");
            });
}
~~~

Nếu yêu cầu nghiệp vụ là tắt feature phải vô hiệu hóa **cả user implementations**, thiết kế điều kiện của toàn hệ thống phải khác. @ConditionalOnProperty trên default bean của thư viện không tự xóa những beans mà ứng dụng đã đăng ký độc lập.

## 15. Back-off và parent ApplicationContext

Một ứng dụng đơn giản thường có một ApplicationContext chính. Nhưng Spring có thể tổ chức **parent/child contexts**, ví dụ trong một số kiến trúc web, tích hợp hoặc test context nâng cao.

Lúc này câu hỏi “đã có bean chưa?” cần thêm phạm vi:

- Chỉ kiểm tra current ApplicationContext?
- Hay còn kiểm tra các ancestor contexts?

**@ConditionalOnMissingBean** hỗ trợ thuộc tính **search** với enum SearchStrategy.

~~~java
import org.springframework.boot.autoconfigure.condition.SearchStrategy;

@ConditionalOnMissingBean(
        value = MessageSender.class,
        search = SearchStrategy.CURRENT)
~~~

Khi search=CURRENT, điều kiện tập trung vào context đang được xử lý, không xem các parent contexts là nơi có candidate phù hợp.

Khi search=ALL theo cơ chế mặc định thông thường, điều kiện có thể xét cả bean từ ancestor contexts.

### 15.1. Tại sao phạm vi tìm kiếm quan trọng?

Giả sử:

~~~text
Parent ApplicationContext
  └── customMessageSender : MessageSender

Child ApplicationContext
  └── MessageSenderAutoConfiguration
~~~

Nếu auto-configuration trong child được phép tìm bean từ parent, nó có thể back off, để child sử dụng bean từ parent khi lookup theo type.

Nếu điều kiện chỉ xét current context, child có thể đăng ký thêm **defaultMessageSender**. Khi đó cấu trúc tổng thể có cả parent custom và child default.

Chọn hành vi nào phụ thuộc API contract của thư viện. Không có câu trả lời chung rằng search=CURRENT luôn tốt hơn hoặc kém hơn.

### 15.2. Kiểm thử back-off khi parent có bean

ApplicationContextRunner hỗ trợ thiết lập parent context.

~~~java
@Test
void backsOffWhenParentContextHasSender() {
    new ApplicationContextRunner()
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(parent -> {

                new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(
                                        MessageSenderAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).hasNotFailed();
                            assertThat(child)
                                    .doesNotHaveBean(
                                            "defaultMessageSender");

                            MessageSender resolved =
                                    child.getBean(MessageSender.class);

                            assertThat(resolved)
                                    .isInstanceOf(
                                            CustomMessageSender.class);
                        });
            });
}
~~~

Đây là test cho auto-configuration với **default search strategy** xét parent theo contract đã chọn.

Lưu ý: child context có thể nhìn thấy parent bean khi tra cứu theo type, nhưng điều đó không đồng nghĩa bean đã được đăng ký **cục bộ** trong child. Khi test boundary của context, hãy phân biệt “bean resolve được qua hierarchy” với “child tự chứa bean definition”.

### 15.3. Kiểm thử search=CURRENT

Một auto-configuration khác có thể viết:

~~~java
@AutoConfiguration
public class ChildOnlyMessageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(
            value = MessageSender.class,
            search = SearchStrategy.CURRENT)
    MessageSender childDefaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

Trong parent/child scenario, child sẽ không coi MessageSender ở parent là candidate khiến condition fail theo search=CURRENT.

Một test có thể kiểm tra:

~~~java
@Test
void currentSearchCreatesChildBeanDespiteParentBean() {
    new ApplicationContextRunner()
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(parent -> {

                new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(
                                        ChildOnlyMessageAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).hasNotFailed();
                            assertThat(child)
                                    .hasBean(
                                            "childDefaultMessageSender");
                        });
            });
}
~~~

Test này tập trung vào **local child bean**. Nếu muốn quan sát đầy đủ beans ở cả hai context, kiểm tra parent và child riêng hoặc lấy bean definitions trực tiếp từ từng bean factory, thay vì nhầm lẫn với lookup có thể đi qua hierarchy.

## 16. Back-off và thứ tự các auto-configurations

Giả sử thư viện có hai auto-configurations:

~~~text
SharedSenderAutoConfiguration
MessageSenderAutoConfiguration
~~~

Cả hai đều có thể liên quan tới MessageSender. Nếu MessageSenderAutoConfiguration đánh giá @ConditionalOnMissingBean trước khi SharedSenderAutoConfiguration đăng ký bean, kết quả có thể khác với ý định thiết kế.

### 16.1. Dùng after để làm rõ dependency về bean definitions

~~~java
@AutoConfiguration(
        after = SharedSenderAutoConfiguration.class)
public class MessageSenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

Điều này yêu cầu auto-configuration này được xem xét sau SharedSenderAutoConfiguration theo cơ chế ordering hỗ trợ của Boot, nếu cả hai cùng tham gia.

### 16.2. Ordering không quyết định tất cả bean creation

Phân biệt:

- **Bean definition registration order**: ảnh hưởng điều kiện như @ConditionalOnMissingBean.
- **Bean instantiation/dependency order**: chịu ảnh hưởng dependency injection, @DependsOn, lazy initialization và lifecycle của container.

Thêm @AutoConfiguration(after=...) chủ yếu nhằm điều khiển **thứ tự auto-configuration processing**, không thay thế việc khai báo các constructor dependencies của một service.

### 16.3. Test nên import đủ những auto-configurations liên quan

Nếu điều kiện của MessageSenderAutoConfiguration phụ thuộc bean được tạo bởi một auto-configuration khác, chỉ chạy:

~~~java
AutoConfigurations.of(MessageSenderAutoConfiguration.class)
~~~

có thể bỏ sót tương tác quan trọng.

Khi đó, dựng runner:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                SharedSenderAutoConfiguration.class,
                MessageSenderAutoConfiguration.class));
~~~

Đây là cách kiểm tra ordering và back-off giữa các auto-configurations trong cùng một test scenario.

Không cần import toàn bộ spring-boot-autoconfigure nếu câu hỏi chỉ liên quan hai classes: context càng nhỏ và có chủ đích, kết quả càng dễ giải thích.

## 17. @ConditionalOnClass và back-off

Trong starter thực tế, auto-configuration còn có thể phụ thuộc vào việc một thư viện nằm trên classpath.

Ví dụ khái niệm:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.messaging.VendorClient")
public class VendorMessagingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender vendorMessageSender() {
        // Tạo adapter từ thư viện vendor khi classpath hợp lệ.
        return new DefaultMessageSender();
    }
}
~~~

Ở đây condition trên class yêu cầu dependency vendor phù hợp. Nếu class không có trên classpath, toàn auto-configuration có thể không được áp dụng.

### 17.1. Đừng kết luận là back-off chỉ vì default bean vắng mặt

Giả sử test:

~~~java
assertThat(context)
        .doesNotHaveBean("vendorMessageSender");
~~~

pass, nhưng trong context không có VendorClient. Điều đó chứng minh vendorMessageSender không tồn tại, **không chứng minh nó nhường chỗ vì user bean**.

Muốn kiểm thử back-off cho vendor integration:

1. Bảo đảm classpath condition thỏa.
2. Không có user bean → vendor default được tạo.
3. Có user bean → vendor default không được tạo.
4. Nếu classpath condition không thỏa → bean không được tạo vì lý do classpath, là test riêng.

### 17.2. FilteredClassLoader cho điều kiện classpath

Spring Boot test hỗ trợ **FilteredClassLoader** để mô phỏng một số class vắng mặt trong test context.

Ví dụ cấu trúc:

~~~java
import org.springframework.boot.test.context.FilteredClassLoader;

contextRunner
        .withClassLoader(new FilteredClassLoader(
                "com.vendor.messaging"))
        .run(context -> {
            // Xác minh auto-configuration đòi vendor
            // không tạo bean khi class không khả dụng.
        });
~~~

Đây là test bổ sung cho @ConditionalOnClass. Không cần làm nó cho một auto-configuration thuần Java không có optional dependencies.

Khi implement classpath-sensitive auto-configuration, hãy cân nhắc việc load class trực tiếp từ method signature. Một số điều kiện classpath cần đặt trên configuration boundary thích hợp để tránh lỗi class loading trước khi condition có cơ hội loại bỏ nhánh.

## 18. @ConditionalOnBean và quan hệ phụ thuộc

Một auto-configuration có thể tạo bean A mặc định, sau đó tạo bean B **chỉ khi có bean A hoặc user replacement**.

Ví dụ:

~~~java
public record MessageGateway(MessageSender sender) {
}
~~~

Auto-configuration:

~~~java
@AutoConfiguration
public class MessagingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }

    @Bean
    @ConditionalOnBean(MessageSender.class)
    @ConditionalOnMissingBean(MessageGateway.class)
    MessageGateway messageGateway(MessageSender sender) {
        return new MessageGateway(sender);
    }
}
~~~

Trong một thiết kế như vậy:

- Nếu chưa có MessageSender, nhánh default có thể tạo MessageSender.
- Nếu user đã cung cấp MessageSender, default back off.
- MessageGateway cần một MessageSender có thể resolve được.
- Nếu user cung cấp MessageGateway, gateway default cũng phải back off.

Nhưng hãy nhớ: điều kiện **@ConditionalOnBean** cũng dựa trên bean definitions được xử lý đến thời điểm đánh giá. Khi đặt nhiều bean methods có điều kiện phụ thuộc nhau trong cùng auto-configuration, cần thiết kế ordering và điều kiện phù hợp; không dựa vào assumptions mơ hồ về thứ tự method.

### 18.1. Test cả replacement chain

Một test tích hợp nhỏ nên xác minh MessageGateway sử dụng **custom** MessageSender:

~~~java
@Test
void gatewayUsesUserProvidedSender() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    MessagingAutoConfiguration.class))
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(
                        "defaultMessageSender");

                MessageGateway gateway =
                        context.getBean(MessageGateway.class);

                assertThat(gateway.sender())
                        .isInstanceOf(
                                CustomMessageSender.class);
            });
}
~~~

Đây là kiểm thử sâu hơn nhánh back-off đơn giản: không những default biến mất, mà bean phụ thuộc vẫn wiring đúng vào user replacement.

### 18.2. Khi có nhiều candidates, dependency có thể fail

Nếu ứng dụng cung cấp hai MessageSender beans, factory method:

~~~java
MessageGateway messageGateway(MessageSender sender)
~~~

có thể không chọn được một candidate. Nếu đây là tình huống starter phải hỗ trợ, cần thiết kế selection contract, dùng qualifier/primary hợp lý hoặc điều kiện như @ConditionalOnSingleCandidate ở vị trí thích hợp.

**Back-off của MessageSender không tự đảm bảo MessageGateway tạo thành công.**

## 19. Condition Evaluation Report: biết vì sao bean không xuất hiện

Khi một bean default vắng mặt, có nhiều giả thuyết:

- @ConditionalOnMissingBean không match do user bean đã tồn tại.
- @ConditionalOnProperty không match vì feature bị tắt.
- @ConditionalOnClass không match vì thiếu dependency.
- Configuration class không được import vào test/application.
- Bean name/type khác với điều kiện cần kiểm tra.

**Condition Evaluation Report** của Spring Boot giúp nhìn thấy những điều kiện đã được đánh giá và outcomes của chúng.

### 19.1. Đọc report trong ApplicationContextRunner

Ví dụ dùng:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;

@Test
void printsConditionReportForDiagnosis() {
    contextRunner
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {

                ConditionEvaluationReport report =
                        ConditionEvaluationReport.get(
                                context.getSourceApplicationContext()
                                        .getBeanFactory());

                report.getConditionAndOutcomesBySource()
                        .forEach((source, outcomes) -> {
                            if (source.contains(
                                    "MessageSenderAutoConfiguration")) {

                                System.out.println(
                                        source + ": "
                                        + outcomes.isFullMatch());

                                outcomes.forEach(
                                        conditionAndOutcome ->
                                                System.out.println(
                                                        conditionAndOutcome
                                                                .getOutcome()
                                                                .getMessage()));
                            }
                        });
            });
}
~~~

Đoạn code minh họa cách quan sát nội dung report khi chẩn đoán, không phải assertion chính của bài. Cấu trúc source names và wording của condition messages có thể thay đổi giữa các phiên bản Spring Boot.

### 19.2. Report mô tả condition, không thay assertion về bean

Một report cho biết điều kiện missing-bean không phù hợp là thông tin rất hữu ích, nhưng kiểm thử behavior vẫn nên dùng:

~~~java
assertThat(context)
        .doesNotHaveBean("defaultMessageSender");
assertThat(context)
        .hasSingleBean(MessageSender.class);
~~~

Nếu test chỉ so sánh chính xác một đoạn text trong condition message, nó có thể bị phá vỡ khi Spring Boot đổi cách diễn đạt log, dù behavior không đổi.

Nên xem condition report là **công cụ hỗ trợ giải thích**, còn bean registry là **bằng chứng cuối** cho contract back-off.

### 19.3. Report không có entry mong đợi

Nếu không tìm được MessageSenderAutoConfiguration trong report, có thể test/app chưa import hoặc activate configuration đó.

Kiểm tra:

1. Context runner có **withConfiguration(AutoConfigurations.of(...))** chưa?
2. Class auto-configuration có bị điều kiện class-level loại bỏ trước khi những method conditions được xét không?
3. Có một configuration khác được import thay thế không?
4. Nếu chạy application thật, file **AutoConfiguration.imports** của thư viện có đúng location/nội dung không?

Không nên thay đổi condition annotation khi nguyên nhân thật là auto-configuration chưa hề được nạp.

## 20. @SpringBootTest có thay thế ApplicationContextRunner không?

**@SpringBootTest** có thể kiểm tra một ứng dụng gần với cấu hình chạy thật. Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class UserOverrideIntegrationTests {

    @Autowired
    MessageSender sender;

    @Test
    void usesCustomSender() {
        assertThat(sender)
                .isInstanceOf(CustomMessageSender.class);
    }
}
~~~

Test này chỉ có giá trị nếu application context thật sự được cấu hình để có CustomMessageSender và starter auto-configuration cần kiểm tra.

### 20.1. Hạn chế của test chỉ inject một bean

Nếu custom có @Primary, @Autowired MessageSender vẫn có thể trả custom **dù default cũng tồn tại**.

Do đó test:

~~~java
assertThat(sender)
        .isInstanceOf(CustomMessageSender.class);
~~~

chưa chứng minh default đã back off.

Trong integration test, có thể inject **ApplicationContext** hoặc **ListableBeanFactory** và kiểm tra số lượng/names:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void defaultBeanWasNotRegistered() {
    assertThat(applicationContext
            .getBeansOfType(MessageSender.class))
            .hasSize(1);

    assertThat(applicationContext
            .containsBean("defaultMessageSender"))
            .isFalse();
}
~~~

Trong những ứng dụng có parent contexts, cần nhớ các API bean lookup và bean factory có thể có phạm vi khác nhau. Chọn cách quan sát phù hợp với contract của ứng dụng.

### 20.2. Vì sao vẫn ưu tiên context runner cho back-off?

| Tiêu chí | ApplicationContextRunner | @SpringBootTest |
|---|---|---|
| Phạm vi | Context nhỏ, chọn auto-configurations rõ ràng | Nhiều cấu hình và dependencies của ứng dụng |
| Tốc độ thông thường | Nhanh, ít side effects | Có thể chậm và mở nhiều resources |
| Dựng case thiếu user bean | Dễ | Có thể cần profile/test config riêng |
| Dựng case có custom user bean | withBean/withUserConfiguration | @TestConfiguration/import/profile |
| Kiểm tra condition và registry | Rất phù hợp | Có thể nhưng nhiều nguồn ảnh hưởng |
| Kiểm tra starter thực sự được import khi đóng gói | Không tự chứng minh | Phù hợp hơn với integration smoke test |
| Kiểm tra web/data integrations | Chỉ khi cấu hình thêm | Thường thích hợp hơn |

**ApplicationContextRunner** là lựa chọn nền tảng để test conditional registration của auto-configuration. **@SpringBootTest** bổ sung độ tin cậy ở integration level khi cần kiểm tra import wiring, profile, dependencies hoặc toàn bộ consumer application.

### 20.3. Context runner không tự quét mọi @Component

Nếu ứng dụng thực tế có:

~~~java
@Component
public class CustomMessageSender
        implements MessageSender {
    // ...
}
~~~

thì một ApplicationContextRunner thuần không tự quét toàn bộ package của ứng dụng chỉ vì class có @Component.

Để kiểm tra back-off, cần:

- Đăng ký component thông qua configuration/component scan phù hợp.
- Hoặc dùng **withBean(MessageSender.class, ...)** để mô phỏng sự hiện diện của bean theo type.

Một test nhầm rằng @Component được phát hiện tự động có thể tạo default và khiến người viết kết luận sai về @ConditionalOnMissingBean.

### 20.4. Integration test kiểm tra imports metadata

Trong một starter thật, auto-configuration có thể hoạt động trong context runner do người viết test đã thêm class thủ công, nhưng **không được ứng dụng consumer tự động phát hiện** nếu file imports của artifact sai.

Do đó, một bộ kiểm thử tốt có thể gồm:

1. **Context runner tests**: chứng minh behavior của từng condition.
2. **Starter smoke/integration test**: kiểm tra artifact thực tế và AutoConfiguration.imports được Boot phát hiện.
3. **Consumer integration test**: xác nhận user-defined bean được ưu tiên trong bối cảnh ứng dụng thực, nếu cần.

Không cần chạy toàn bộ ứng dụng cho mọi biến thể back-off.

## 21. Những kiểu test dễ tạo cảm giác đúng nhưng không đúng

### 21.1. Chỉ kiểm tra custom bean có mặt

~~~java
assertThat(context)
        .hasBean("customMessageSender");
~~~

Test này pass ngay cả khi defaultMessageSender cũng được tạo.

**Sửa:** thêm assertion default vắng mặt và số lượng bean phù hợp.

### 21.2. Chỉ kiểm tra default vắng mặt

~~~java
assertThat(context)
        .doesNotHaveBean("defaultMessageSender");
~~~

Test này có thể pass nếu auto-configuration bị thiếu, bị disabled hoặc condition classpath fail.

**Sửa:** xác nhận user bean tồn tại và default xuất hiện ở nhánh không có user bean trong cùng bộ test.

### 21.3. Không import auto-configuration đang kiểm tra

~~~java
new ApplicationContextRunner()
        .withBean(
                MessageSender.class,
                CustomMessageSender::new)
        .run(context -> {
            assertThat(context)
                    .doesNotHaveBean("defaultMessageSender");
        });
~~~

Trong context không chứa MessageSenderAutoConfiguration, default đương nhiên không được tạo. Test không nói gì về cơ chế back-off.

**Sửa:** phải có:

~~~java
.withConfiguration(
        AutoConfigurations.of(
                MessageSenderAutoConfiguration.class))
~~~

### 21.4. Tự gọi @Bean method bằng tay

~~~java
MessageSenderAutoConfiguration config =
        new MessageSenderAutoConfiguration();
MessageSender sender = config.defaultMessageSender();
~~~

Lệnh này chỉ gọi một Java method. Spring không đánh giá @ConditionalOnMissingBean, không đăng ký bean definition và không chạy auto-configuration lifecycle.

**Sửa:** tạo ApplicationContext và để Spring xử lý configuration class.

### 21.5. Tưởng @Primary đồng nghĩa back-off

Nếu test chỉ inject type:

~~~java
MessageSender sender =
        context.getBean(MessageSender.class);
~~~

và custom có @Primary, kết quả có thể là custom dù default vẫn hiện diện.

**Sửa:** kiểm tra cả registry và absence của bean mặc định.

### 21.6. Dùng mock trực tiếp ngoài context

~~~java
MessageSender fake = Mockito.mock(MessageSender.class);
~~~

Biến fake không tự trở thành Spring bean. Condition không biết nó tồn tại.

**Sửa:** đăng ký mock làm bean trong context thử nghiệm khi mục tiêu là back-off; với context runner, có thể dùng withBean(MessageSender.class, () -> fake).

### 21.7. Không phân biệt test feature disabled

Khi:

~~~java
.withPropertyValues("acme.message.enabled=false")
~~~

default vắng mặt có thể do ConditionalOnProperty, không phải do user bean.

**Sửa:** trong test back-off, giữ những điều kiện khác ở trạng thái cho phép auto-configuration hoạt động, sau đó chỉ thay đổi sự hiện diện của user bean.

### 21.8. Khẳng định mọi bean phải được tạo ngay

Một bean có thể được khai báo lazy hoặc đi qua factory/proxy. Việc constructor chưa chạy không đồng nghĩa bean definition không có.

**Sửa:** assert bean definition/name/type theo contract, không chỉ đếm số lần constructor được gọi.

### 21.9. Test trùng tên thay vì thay thế theo type

Nếu user bean được đặt đúng tên **defaultMessageSender**, có thể bạn đang kiểm tra tình huống bean name collision/overriding thay vì back-off theo type.

**Sửa:** cố ý đặt tên custom khác tên default và xác nhận @ConditionalOnMissingBean(MessageSender.class) vẫn loại default.

## 22. Tại sao không bật bean overriding để “sửa” back-off?

Giả sử sau khi thêm custom bean, Spring báo:

~~~text
The bean 'messageSender' could not be registered.
A bean with that name has already been defined.
~~~

Một cách xử lý hấp tấp là bật:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

Điều này thay đổi chính sách bean definition overriding của Spring Boot. Nhưng nó **không chứng minh** auto-configuration được thiết kế để nhường chỗ.

Rủi ro:

- Thứ tự đăng ký có thể quyết định bean nào thắng.
- Mất tính rõ ràng của cấu hình.
- Có thể che một lỗi đăng ký trùng không liên quan tới user customization.
- Trường hợp trùng theo type nhưng khác tên không được giải quyết chỉ bằng overriding name.

Đối với một starter mở rộng được, giải pháp đúng thường là:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

kèm một bộ test back-off như đã trình bày.

## 23. Back-off và API công khai của starter

Một starter tốt cần trả lời cho người dùng:

- Interface nào họ được phép thay thế?
- Họ cần đăng ký một bean type gì?
- Có bắt buộc tên bean không?
- Default sẽ tự tạo nếu không có custom bean chứ?
- Việc cung cấp custom bean có tắt **toàn bộ integration** hay chỉ thay một component?
- Điều kiện classpath/property/profile nào còn chi phối?

Ví dụ một contract tài liệu rõ ràng:

> Nếu ứng dụng chưa đăng ký MessageSender bean, starter sẽ cung cấp DefaultMessageSender. Để tùy biến, hãy khai báo một bean triển khai MessageSender; auto-configuration sẽ không đăng ký bean mặc định.

Mô tả như vậy cụ thể hơn câu “có thể override cấu hình nếu cần”. Nó chỉ rõ extension point và hành vi back-off mà tests cần bảo vệ.

### 23.1. Test là hợp đồng tương thích

Giả sử nhóm thư viện refactor class:

~~~java
@ConditionalOnMissingBean(DefaultMessageSender.class)
~~~

thay vì:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

Thay đổi này tưởng nhỏ, nhưng có thể phá contract: user cung cấp CustomMessageSender không phải DefaultMessageSender, nên default vẫn được tạo.

Bộ test back-off theo interface sẽ phát hiện sự thay đổi này, dù source code vẫn compile và default-path test vẫn pass.

### 23.2. Dùng abstraction đúng phạm vi

Nếu starter cho phép nhiều loại NotificationSender theo tên/channel, một điều kiện missing-bean theo interface quá rộng có thể không phù hợp: một custom sender cho email có thể vô tình ngăn default sender cho SMS.

Khi đó cần thiết kế lại contract, ví dụ:

- Tách interface cho từng vai trò.
- Dùng bean name/qualifier có chủ đích.
- Tách auto-configuration theo từng module.
- Dùng custom configuration properties để chọn provider.

**@ConditionalOnMissingBean không tự biết “hai beans cùng interface nhưng phục vụ hai chức năng khác nhau”**. Chính API design quyết định type/name nào phải được xem là replacement.

## 24. Ma trận kiểm thử cho một auto-configuration có back-off

Khi một starter dần phát triển, chỉ hai test cơ bản có thể chưa đủ để bảo vệ những điều kiện phối hợp.

Một ma trận kiểm thử có chủ đích:

| Tình huống | Bean mặc định | User bean | Điều cần xác minh |
|---|---|---|---|
| Auto-config bật, không user bean | Có | Không | Fallback hoạt động |
| Auto-config bật, có một user bean đúng type | Không | Có | Back-off chính |
| User bean có tên khác default | Không | Có | Back-off dựa trên type |
| User bean khai báo return type cụ thể | Không | Có | Metadata đủ để match |
| User bean có @Lazy | Không | Có | Dựa trên definition, không chờ instance |
| Có hai user beans cùng type | Không | Có hai | Back-off không đồng nghĩa uniqueness |
| Property disable default | Không | Không | Phân biệt condition khác với back-off |
| Property disable nhưng user tự tạo bean | Không | Có | User bean độc lập với default condition |
| Parent context có user bean, search=ALL | Không ở child | Có ở parent | Scope tìm bean đúng |
| Parent có bean, search=CURRENT | Có thể có ở child | Có ở parent | Scope tìm kiếm hẹp |
| Thiếu optional classpath dependency | Không | Tùy | Classpath condition được kiểm tra riêng |
| User cung cấp component tùy biến cho downstream bean | Không | Có | Wiring sử dụng đúng replacement |

Không phải starter nào cũng cần toàn bộ hàng. Ví dụ không có parent context hoặc optional dependencies thì không cần dựng những bài test phức tạp tương ứng.

**Điểm cốt lõi:** Mỗi test nên thay đổi **một nguyên nhân quan trọng**, để khi thất bại, nhóm phân biệt được type condition, bean registration, profile, classpath hoặc property condition.

## 25. Cách tổ chức test classes để dễ bảo trì

Có thể nhóm các test theo behavior:

~~~text
MessageSenderAutoConfigurationTests
  ├── defaultBeanIsRegistered
  ├── userBeanCausesBackOff
  ├── customBeanNameDoesNotMatter
  ├── disabledFeatureDoesNotRegisterDefault
  └── parentBeanIsConsidered

MessagingIntegrationTests
  ├── downstreamBeanUsesCustomSender
  └── starterIsImportedByConsumerApplication
~~~

Một mẫu tổ chức:

~~~java
class MessageSenderAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    MessageSenderAutoConfiguration.class));

    @Test
    void defaultBeanIsRegistered() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(MessageSender.class);
            assertThat(context.getBean(MessageSender.class))
                    .isInstanceOf(DefaultMessageSender.class);
        });
    }

    @Test
    void userBeanCausesBackOff() {
        runner.withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(MessageSender.class);
                    assertThat(context.getBean(
                            MessageSender.class))
                            .isInstanceOf(CustomMessageSender.class);
                    assertThat(context)
                            .doesNotHaveBean("defaultMessageSender");
                });
    }
}
~~~

Từng phương thức run tạo một context riêng. Không cần viết một test duy nhất khởi động rồi tự gỡ bean và đăng ký bean khác trong cùng context để mô phỏng back-off; conditions đã được đánh giá trong quá trình đăng ký definitions.

### 25.1. Context runner có tính cấu hình tích lũy, không cần shared mutable state

Mẫu:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        MessageSenderAutoConfiguration.class));
~~~

và từng test sử dụng:

~~~java
runner.withBean(MessageSender.class,
        CustomMessageSender::new).run(...);
~~~

là cách cô lập scenario thuận tiện. Tránh giữ một ApplicationContext đã chạy làm shared field rồi thử thay đổi các bean definitions của nó từ nhiều test, vì lúc đó bạn không còn kiểm tra quá trình bootstrapping ban đầu.

### 25.2. Không đặt test fixture có tác dụng ngoài ý muốn

Trong auto-configuration tests, một bean mặc định không nên tự gửi email, truy cập production endpoint, tạo schema hoặc mở socket bên ngoài chỉ để test condition.

Nếu implementation có side effects khi khởi tạo, test có thể:

- Cung cấp mock/stub của external client.
- Dùng configuration properties chỉ tới fake endpoint.
- Tách logic tạo bean khỏi logic thực thi hoạt động bên ngoài.
- Kiểm tra bean definitions mà không gọi business operation nguy hiểm.

Mục tiêu của test back-off là **bean selection contract**, không phải thực hiện side effect thật.

## 26. Khi ứng dụng cho phép người dùng custom nhiều beans

Một starter có thể cung cấp nhiều vai trò:

~~~text
MessageSender
MessageTemplateResolver
MessageAuditSink
~~~

Mỗi vai trò có thể có default riêng:

~~~java
@AutoConfiguration
public class MessagingDefaultsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }

    @Bean
    @ConditionalOnMissingBean(MessageTemplateResolver.class)
    MessageTemplateResolver defaultTemplateResolver() {
        return new DefaultTemplateResolver();
    }

    @Bean
    @ConditionalOnMissingBean(MessageAuditSink.class)
    MessageAuditSink defaultAuditSink() {
        return new DefaultAuditSink();
    }
}
~~~

Đây là các interface/implementation minh họa, không phải classes của Spring Boot.

Nếu user chỉ thay MessageSender, expected behavior có thể là:

~~~text
MessageSender:          custom
MessageTemplateResolver: default
MessageAuditSink:        default
~~~

Một test hữu ích:

~~~java
@Test
void customizingSenderDoesNotDisableOtherDefaults() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    MessagingDefaultsAutoConfiguration.class))
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {
                assertThat(context).hasNotFailed();

                assertThat(context.getBean(
                        MessageSender.class))
                        .isInstanceOf(
                                CustomMessageSender.class);

                assertThat(context)
                        .doesNotHaveBean(
                                "defaultMessageSender");
                assertThat(context)
                        .hasSingleBean(
                                MessageTemplateResolver.class);
                assertThat(context)
                        .hasSingleBean(
                                MessageAuditSink.class);
            });
}
~~~

Test này ngăn lỗi thiết kế: đặt @ConditionalOnMissingBean(MessageSender.class) **ở cấp class auto-configuration** khiến cả nhóm defaults vô tình bị bỏ qua khi user chỉ thay một component.

### 26.1. Điều kiện cấp class và cấp @Bean method khác phạm vi

Ví dụ ở cấp class:

~~~java
@AutoConfiguration
@ConditionalOnMissingBean(MessageSender.class)
public class MessagingDefaultsAutoConfiguration {
    // Nhiều @Bean methods khác nhau.
}
~~~

Nếu user có MessageSender, **toàn class auto-configuration** có thể không được áp dụng, bao gồm các beans khác dù người dùng chưa thay thế chúng.

Ngược lại, đặt condition trên từng @Bean method giúp mỗi default quyết định back-off độc lập.

Đây là một trong những lý do quan trọng để **đặt điều kiện ở cấp phù hợp với hợp đồng thay thế**.

### 26.2. Khi nào đặt condition ở cấp class?

Hợp lý khi cả nhóm bean thật sự phải được bật/tắt như một đơn vị, ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.messaging",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class MessagingAutoConfiguration {
    // ...
}
~~~

Ở đây điều kiện feature enabled có thể áp dụng cho toàn module. Còn @ConditionalOnMissingBean cho từng extension point có thể đặt ở bean methods.

Không có quy tắc rằng mọi condition phải nằm trên @Bean; hãy chọn scope theo hành vi mong muốn và kiểm thử từng nhánh.

## 27. Tích hợp với Spring Boot Actuator khi chẩn đoán

Trong một ứng dụng thật, Spring Boot Actuator có thể cung cấp thông tin hữu ích:

| Endpoint | Tác dụng khi điều tra back-off |
|---|---|
| **/actuator/beans** | Xác minh default và custom beans nào thật sự có trong ApplicationContext. |
| **/actuator/conditions** | Đọc condition outcomes của auto-configurations được ghi nhận. |
| **/actuator/configprops** | Kiểm tra configuration properties beans ảnh hưởng việc tạo default. |
| **/actuator/env** | Kiểm tra giá trị feature flags/property sources liên quan. |

Các endpoint này không nhất thiết được expose qua HTTP mặc định. Chúng có thể tiết lộ metadata nội bộ, nên cần authentication, authorization và các chính sách redaction/exposure phù hợp.

### 27.1. Đừng dùng Actuator thay cho automated tests

Actuator cho biết **trạng thái instance đang chạy**. Test ApplicationContextRunner bảo vệ **contract auto-configuration** qua các thay đổi code.

Nếu một developer vô tình đổi:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

thành:

~~~java
@ConditionalOnMissingBean(DefaultMessageSender.class)
~~~

thì một bộ test back-off theo interface sẽ phát hiện sự cố ngay trong pipeline, thay vì đợi tới lúc quan sát một instance đã deploy.

### 27.2. Conditions report cần được diễn giải đúng

Một điều kiện missing-bean không match có thể là **kết quả mong muốn** khi user cung cấp bean. Đừng nhầm mọi mục negative match trong report là lỗi Spring Boot.

Ngược lại, một mục positive match của điều kiện missing-bean có thể cho thấy default sẽ được đăng ký **nếu các điều kiện khác cùng phù hợp**. Luôn đối chiếu với bean registry.

## 28. Gỡ lỗi khi test back-off thất bại

### 28.1. Custom bean đã đăng ký nhưng default vẫn tồn tại

Kiểm tra:

1. @ConditionalOnMissingBean có dùng đúng interface type không?
2. User @Bean method có return type đủ rõ không?
3. Bean có nằm trong cùng context hoặc parent theo search strategy không?
4. Auto-configuration được xử lý sau user configuration chưa?
5. Có nhiều auto-configurations cùng tạo MessageSender không?
6. Có bean name/type trùng nhưng khác điều kiện matching không?

Nếu condition được viết theo **DefaultMessageSender.class** nhưng user cung cấp **CustomMessageSender**, hãy cân nhắc chuyển sang interface type MessageSender.class theo contract.

### 28.2. Không có default bean ngay cả khi không có custom

Kiểm tra:

1. Auto-configuration đã được import chưa?
2. Có @ConditionalOnProperty bị false không?
3. Có @ConditionalOnClass bị loại vì thiếu dependency không?
4. Có parent context cung cấp MessageSender không?
5. Có test fixture hoặc auto-config khác đăng ký bean cùng type không?
6. Đường đi của @Bean method có bị condition class-level loại bỏ không?

Không vội kết luận @ConditionalOnMissingBean bị hỏng khi một điều kiện khác có thể chặn bean.

### 28.3. Test khởi động context thất bại vì nhiều candidates

Nếu:

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
~~~

thì có thể auto-config không back off đúng, hoặc user tự đăng ký nhiều beans cùng type.

Kiểm tra bằng một test context không có consumer đơn để quan sát toàn bộ MessageSender beans, sau đó xác định:

- Có default ngoài ý định không?
- User có hai candidates không?
- Thiếu @Primary/@Qualifier hay cần @ConditionalOnSingleCandidate?

@Primary có thể giải quyết một injection ambiguity được thiết kế có chủ đích, **không phải cách thay thế kiểm tra back-off**.

### 28.4. Test dùng withBean pass nhưng ứng dụng thật vẫn tạo default

Một số khả năng:

- Application thật không đăng ký user class qua component scan/import.
- Factory @Bean ở ứng dụng khai báo type quá rộng như Object.
- Starter được import khác cách test.
- Profile/property condition của production khác test.
- Auto-configuration ordering hoặc parent context khác.

Hãy thêm một test dùng **withUserConfiguration** đúng signature production hoặc integration test đại diện cho cách user thực sự tích hợp.

### 28.5. Không có condition report mong đợi

Nếu report không xuất hiện tên class/method của auto-configuration:

- Xác minh runner có AutoConfigurations.of đúng class.
- Xác minh class có @AutoConfiguration hoặc được import qua cơ chế tương ứng.
- Xem điều kiện cấp class đã loại phần cần đánh giá chưa.
- Với starter thật, kiểm tra AutoConfiguration.imports.

Một @Bean method không được Spring xử lý thì @ConditionalOnMissingBean của method đó cũng không được đánh giá.

### 28.6. Back-off trong context runner đúng nhưng @SpringBootTest khác

Context runner chỉ chứa các beans/configurations do test đưa vào. @SpringBootTest có thể nạp thêm:

- Component scan.
- Configuration properties.
- Other auto-configurations.
- Test replacements/mocks.
- Profile-specific beans.
- Parent context hoặc framework beans.

Do đó test tích hợp có thể có các candidates khác. Đừng thêm tất cả auto-configurations vào context runner cho “giống SpringBootTest hơn” ngay lập tức; hãy xác định bean bổ sung nào thay đổi kết quả và tạo một integration scenario có kiểm soát.

## 29. Những hiểu nhầm thường gặp

**“Back-off nghĩa Spring tạo default rồi custom bean ghi đè nó.”**  
Không. Với conditional registration đúng, default bean definition không được đăng ký khi condition không đạt.

**“@Primary cũng là một cách để default back off.”**  
Không. @Primary giúp chọn candidate khi dependency injection, không loại bean mặc định khỏi context.

**“Cho phép bean overriding giải quyết mọi vấn đề của starter.”**  
Không. Bean overriding theo name khác với condition back-off theo type. Bật overriding có thể che lỗi thiết kế.

**“Có custom object được tạo bằng new thì @ConditionalOnMissingBean nhìn thấy nó.”**  
Không. Object phải được đăng ký làm Spring bean trong phạm vi phù hợp.

**“@ConditionalOnMissingBean luôn chỉ kiểm tra theo tên của @Bean method.”**  
Không. Có thể kiểm tra theo type, name, annotation và các tiêu chí khác. Với @Bean method không khai báo cụ thể điều kiện, Boot có khả năng suy luận return type theo quy tắc hỗ trợ.

**“Một user bean cùng interface luôn được nhận diện dù @Bean trả về Object.”**  
Không nhất thiết. Condition phụ thuộc bean metadata có sẵn khi đánh giá.

**“Nếu default không tồn tại thì chắc chắn đã back off vì user bean.”**  
Không. Auto-configuration có thể chưa được import hoặc một classpath/property condition khác đã chặn.

**“Chỉ cần test custom bean có trong context.”**  
Không. Default vẫn có thể tồn tại cùng custom bean; cần assert default vắng mặt và số candidate phù hợp.

**“Chỉ cần test default bean vắng mặt.”**  
Không. Nếu không đưa auto-configuration vào context, default vắng mặt là kết quả vô nghĩa đối với back-off.

**“Dùng withBean và withUserConfiguration hoàn toàn tương đương trong mọi tình huống.”**  
Không. withBean rất tiện để tạo type; withUserConfiguration phản ánh thêm bean factory method, tên, scope, điều kiện và metadata của cấu hình người dùng.

**“@ConditionalOnMissingBean đặt ở đâu cũng có kết quả giống nhau.”**  
Không. Điều kiện phụ thuộc những bean definitions đã được xử lý tại thời điểm đánh giá; auto-configuration ordering có ý nghĩa.

**“Khi có hai user beans thì auto-config sẽ tự chọn cái phù hợp.”**  
Không. Missing-bean condition có thể back off nhưng injection vẫn có thể ambiguous.

**“Parent bean lúc nào cũng bị bỏ qua.”**  
Không. SearchStrategy quyết định phạm vi tìm kiếm; mặc định thường có thể xét parent contexts.

**“@ConditionalOnProperty false nghĩa user bean cũng bị xóa.”**  
Không. Một condition gắn trên default factory method không tự loại một user bean được đăng ký riêng.

**“@SpringBootTest chỉ cần inject đúng custom type là chứng minh back-off.”**  
Không. Một default khác vẫn có thể tồn tại và custom được chọn bởi @Primary.

**“Test context runner đã pass thì starter chắc chắn được phát hiện trong consumer.”**  
Không. AutoConfigurations.of import class trực tiếp cho test; packaging/AutoConfiguration.imports cần được kiểm tra riêng nếu đó là mục tiêu.

**“Mọi negative match trong Condition Evaluation Report đều là lỗi.”**  
Không. Negative match của missing-bean condition thường là **hành vi mong đợi** khi user đã tùy chỉnh.

## 30. Quy trình xây dựng bài test back-off cho một auto-configuration mới

Khi viết một starter hoặc một auto-configuration hỗ trợ custom bean, có thể làm theo quy trình sau:

### Bước 1 — Xác định extension point

Chọn public interface hoặc type mà ứng dụng được phép thay thế, ví dụ MessageSender.

Đừng bắt đầu bằng cách đặt một điều kiện thiếu bean lên bất kỳ class concrete nào. Hãy quyết định **user customization contract** trước.

### Bước 2 — Viết default @Bean method

~~~java
@Bean
@ConditionalOnMissingBean(MessageSender.class)
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

Nếu auto-config còn phụ thuộc classpath/property, khai báo conditions tương ứng ở cấp phù hợp.

### Bước 3 — Tạo context runner có auto-configuration

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        MessageSenderAutoConfiguration.class));
~~~

### Bước 4 — Test default path

Không đăng ký MessageSender custom. Assert context thành công, có đúng một MessageSender và implementation là DefaultMessageSender.

### Bước 5 — Test back-off path

Đăng ký MessageSender custom bằng withBean hoặc withUserConfiguration. Assert custom tồn tại, default vắng mặt, candidate count phù hợp và wiring dùng custom.

### Bước 6 — Test những điều kiện khác riêng biệt

Nếu có feature flag, classpath dependency, profile hoặc parent context, dựng test riêng. Không nhầm việc default vắng mặt do feature disabled với việc back-off vì custom.

### Bước 7 — Test mức integration khi cần

Nếu phát hành một starter thật, thêm smoke test để chứng minh auto-configuration được phát hiện từ artifact và một consumer application có thể cung cấp bean tùy biến.

### Bước 8 — Bảo vệ regression

Khi thay đổi interface, bean names, scopes, return types, condition placement hoặc auto-configuration ordering, giữ các test nhánh default/back-off để bảo vệ behavior từ góc nhìn người dùng.

### Sơ đồ quyết định

~~~text
Thiết kế default bean cho starter
                │
                ▼
Xác định type người dùng được thay
                │
                ▼
@ConditionalOnMissingBean(type)
                │
                ▼
ApplicationContextRunner + AutoConfigurations.of
                │
          ┌─────┴─────┐
          │           │
      Không user    Có user
         bean         bean
          │           │
          ▼           ▼
       Có default   Không default
          │           │
          └─────┬─────┘
                ▼
       Bean registry nhất quán?
                │
                ▼
     Test conditions bổ sung nếu có
                │
                ▼
   Integration/packaging test khi cần
~~~

## 31. Bài tập tự luyện

### Bài tập 1 — Phát hiện điều kiện sai type

Auto-configuration:

~~~java
@Bean
@ConditionalOnMissingBean(DefaultMessageSender.class)
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

Ứng dụng:

~~~java
@Bean
MessageSender customMessageSender() {
    return new CustomMessageSender();
}
~~~

**Câu hỏi:** Vì sao có thể có hai MessageSender beans?

**Định hướng:** Điều kiện đang kiểm tra sự vắng mặt của **DefaultMessageSender concrete type**, không kiểm tra public contract MessageSender. CustomMessageSender không phải DefaultMessageSender, nên default có thể vẫn được tạo.

**Cách sửa theo hợp đồng:** dùng @ConditionalOnMissingBean(MessageSender.class), sau đó test nhánh user bean.

### Bài tập 2 — Chọn assertion đủ chứng minh back-off

Test:

~~~java
runner.withBean(MessageSender.class,
                CustomMessageSender::new)
        .run(context -> {
            assertThat(context).hasNotFailed();
        });
~~~

**Câu hỏi:** Test còn thiếu những assertion nào?

**Định hướng:** Kiểm tra có đúng một MessageSender, instance là custom và không có defaultMessageSender. Nếu chỉ kiểm tra startup thành công, test không bảo vệ extension contract.

### Bài tập 3 — Phân biệt feature disabled với user override

Auto-configuration có @ConditionalOnProperty và @ConditionalOnMissingBean. Một test đặt acme.message.enabled=false rồi thấy default vắng mặt.

**Câu hỏi:** Kết luận “back-off hoạt động” có đúng không?

**Đáp án:** Chưa. Default có thể vắng mặt chỉ do feature bị tắt. Hãy bật feature trong case back-off và thêm user bean phù hợp; đồng thời giữ một test disabled độc lập.

### Bài tập 4 — Thử dùng name khác

Ứng dụng tự đăng ký:

~~~java
@Bean("myPreferredSender")
MessageSender sender() {
    return new CustomMessageSender();
}
~~~

**Câu hỏi:** Nếu auto-config có @ConditionalOnMissingBean(MessageSender.class), default có cần được tạo không?

**Đáp án mong đợi:** Không. Tên myPreferredSender khác defaultMessageSender nhưng type đã đáp ứng hợp đồng replacement.

### Bài tập 5 — Đọc hai kết quả test

Kết quả:

~~~text
Test A:
  DefaultMessageSender exists
  CustomMessageSender absent

Test B:
  DefaultMessageSender exists
  CustomMessageSender exists
~~~

**Câu hỏi:** Test nào cho thấy lỗi back-off?

**Định hướng:** Nếu Test B thật sự đăng ký custom bean phù hợp và các điều kiện khác đang cho phép auto-configuration hoạt động, việc default còn tồn tại vi phạm contract back-off. Cần kiểm tra condition type, bean metadata, ordering và tên bean.

### Bài tập 6 — Parent context

Parent có CustomMessageSender. Child import MessageSenderAutoConfiguration. Test thấy child không tạo default.

**Câu hỏi:** Vì sao? Nếu muốn child luôn tạo default riêng bất chấp parent có bean, cần xem gì?

**Đáp án định hướng:** Mặc định condition có thể tìm trong hierarchy và thấy parent bean. Xem thuộc tính search của @ConditionalOnMissingBean, chẳng hạn SearchStrategy.CURRENT, rồi test đúng scope mong muốn.

## Ghi nhớ cốt lõi

**Back-off là hợp đồng nhường quyền tạo bean mặc định cho ứng dụng.** Trong Spring Boot, một auto-configuration có thể khai báo **@ConditionalOnMissingBean(MessageSender.class)** để chỉ cung cấp DefaultMessageSender khi chưa có bean MessageSender phù hợp. Cơ chế này khác hoàn toàn @Primary hoặc bean overriding: default bean definition không nên được đăng ký khi custom bean đã đáp ứng điều kiện.

**Kiểm thử đúng phải có ít nhất hai nhánh.** Với **ApplicationContextRunner** và **AutoConfigurations.of**, test không có user bean phải cho thấy default được tạo. Test có user bean phải xác nhận custom hiện diện, default vắng mặt và candidate count đúng. Dùng **withBean** để tạo nhanh một custom type hoặc **withUserConfiguration** để kiểm tra signature @Bean thực tế. Một test chỉ assert context startup thành công hoặc chỉ assert default vắng mặt là chưa đủ.

**Đừng bỏ qua điều kiện và thứ tự xử lý.** @ConditionalOnMissingBean dựa trên bean metadata đã có ở thời điểm đánh giá; return type, name/type matching, auto-configuration ordering, parent context và các conditions khác đều có thể làm thay đổi kết quả. Dùng Condition Evaluation Report để giải thích nguyên nhân và kiểm tra bean registry để xác nhận behavior. Khi phát hành starter, bổ sung test tích hợp cho cơ chế imports nếu cần.

Mục tiêu cuối cùng không phải chỉ “test có annotation @ConditionalOnMissingBean”, mà là bảo đảm **ứng dụng có thể cung cấp bean tùy chỉnh mà Spring Boot không tạo thêm default gây cạnh tranh**, trong khi vẫn nhận default thuận tiện nếu ứng dụng chưa lựa chọn.
