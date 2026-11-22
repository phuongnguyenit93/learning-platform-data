# Chuyển cách hiện thực bằng profile hoặc property

Trong Spring Boot, cùng một chức năng có thể có nhiều cách hiện thực. Ứng dụng có thể dùng email thật ở production, ghi thông báo ra console khi phát triển, hoặc tắt một tích hợp trong môi trường kiểm thử. Một cách tổ chức phổ biến là chọn bean bằng **Spring Profile**; một cách khác là chọn bằng **property**.

Hai cơ chế có liên quan nhưng diễn đạt hai ý định khác nhau:

- **Profile** mô tả một nhóm cấu hình/môi trường đang được kích hoạt, chẳng hạn local, test, staging hoặc prod.
- **Property** mô tả một lựa chọn hay tham số cụ thể, chẳng hạn app.notification.provider=smtp, app.feature.invoice-export.enabled=false hoặc app.payment.timeout=3s.

Chuyển một implementation từ profile sang property không chỉ là đổi @Profile thành @ConditionalOnProperty. Trước hết cần xác định lựa chọn đó thực sự phụ thuộc **môi trường triển khai** hay phụ thuộc **một khả năng/cấu hình độc lập**. Nếu một môi trường có thể bật/tắt tính năng mà không đổi toàn bộ nhóm cấu hình, property thường biểu đạt đúng hơn. Nếu nhiều bean và nhiều file cấu hình phải thay đổi đồng bộ theo một môi trường, profile thường phù hợp hơn.

Bài thực hành dùng một chức năng gửi thông báo để đi qua hai thiết kế, chuyển đổi giữa chúng, kiểm thử các nhánh cấu hình, xử lý trường hợp thiếu/trùng bean và chọn cơ chế phù hợp cho ứng dụng thật.

## 1. Bài toán: cùng một interface, nhiều implementation

Giả sử ứng dụng cần gửi thông báo khi đơn hàng được tạo. Trong local development, ta chỉ muốn ghi nội dung ra console. Ở production, ứng dụng dùng SMTP.

Định nghĩa contract:

~~~java
package com.example.notification;

public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

Implementation cho local:

~~~java
package com.example.notification;

public class ConsoleNotificationSender
        implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.printf(
                "[LOCAL] To=%s, message=%s%n",
                recipient,
                message);
    }
}
~~~

Implementation cho production:

~~~java
package com.example.notification;

public class SmtpNotificationSender
        implements NotificationSender {

    private final SmtpClient client;

    public SmtpNotificationSender(SmtpClient client) {
        this.client = client;
    }

    @Override
    public void send(String recipient, String message) {
        client.send(recipient, message);
    }
}
~~~

SmtpClient ở đây là collaborator do ứng dụng hoặc thư viện mail cung cấp. Ví dụ tập trung vào việc chọn implementation, không triển khai giao thức SMTP.

Service nghiệp vụ chỉ phụ thuộc interface:

~~~java
package com.example.order;

import com.example.notification.NotificationSender;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationService {

    private final NotificationSender sender;

    public OrderNotificationService(NotificationSender sender) {
        this.sender = sender;
    }

    public void orderCreated(String email, String orderNumber) {
        sender.send(
                email,
                "Your order " + orderNumber + " has been created.");
    }
}
~~~

OrderNotificationService không cần biết profile hoặc property nào đã chọn implementation. Đây là điểm quan trọng: **quyết định wiring thuộc cấu hình**, còn business service dùng contract ổn định.

## 2. Cách thứ nhất: chọn implementation bằng @Profile

@Profile giới hạn việc đăng ký bean hoặc configuration class theo profile đang active.

Ví dụ:

~~~java
package com.example.notification;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NotificationProfileConfiguration {

    @Bean
    @Profile("local")
    NotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @Profile("prod")
    NotificationSender smtpNotificationSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }
}
~~~

Khi profile local active, bean console được đăng ký. Khi profile prod active, bean SMTP được đăng ký.

### 2.1. Kích hoạt profile

Có thể kích hoạt profile bằng command-line:

~~~bash
java -jar order-api.jar --spring.profiles.active=local
~~~

Hoặc environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Hoặc trong application.yml:

~~~yaml
spring:
  profiles:
    active: local
~~~

Trong triển khai thực tế, nên để launcher/deployment cung cấp profile theo môi trường. Không hard-code prod trong code Java.

### 2.2. Profile mặc định

Nếu không có profile nào được active rõ ràng, Spring có thể sử dụng profile mặc định default. @Profile("local") không tự match chỉ vì đang chạy trên máy developer.

Nếu muốn bean được chọn khi không có profile active, có thể dùng:

~~~java
@Bean
@Profile("default")
NotificationSender consoleNotificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Tuy nhiên, đừng dùng default profile như một cách ngầm định để production nhận cấu hình local. Môi trường quan trọng nên được khai báo rõ ràng.

### 2.3. Profile expressions

@Profile hỗ trợ biểu thức profile:

~~~java
@Profile("staging | prod")
~~~

Bean match khi staging hoặc prod active.

~~~java
@Profile("!test")
~~~

Bean match khi profile test không active.

~~~java
@Profile("prod & !maintenance")
~~~

Bean match khi prod active và maintenance không active.

Có thể dùng biểu thức này, nhưng tránh tạo điều kiện quá phức tạp. Nếu phải đọc nhiều profile expressions mới hiểu bean nào được tạo, cấu hình đang khó vận hành.

## 3. Dùng profile-specific configuration files

Profile không chỉ chọn bean. Nó còn cho phép nạp cấu hình riêng theo môi trường.

Ví dụ:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-test.yml
├── application-staging.yml
└── application-prod.yml
~~~

application.yml chứa cấu hình chung:

~~~yaml
spring:
  application:
    name: order-api

app:
  notification:
    enabled: true
~~~

application-local.yml:

~~~yaml
app:
  notification:
    provider: console
~~~

application-prod.yml:

~~~yaml
app:
  notification:
    provider: smtp
~~~

Khi prod active, Spring Boot nạp cấu hình base cùng cấu hình profile-specific tương ứng theo quy tắc Config Data và precedence.

### 3.1. Chọn profile và chọn property là hai việc riêng

Giả sử:

~~~bash
java -jar order-api.jar --spring.profiles.active=prod
~~~

Lệnh này chọn profile prod. Giá trị app.notification.provider=smtp có thể đến từ application-prod.yml, nhưng bean nào được tạo còn phụ thuộc code/configuration condition.

Profile không tự biến một class thành SMTP sender nếu class đó không có @Profile, @ConditionalOnProperty hoặc cơ chế đăng ký tương ứng.

### 3.2. Profile groups

Một môi trường có thể cần kích hoạt nhiều profile con. Spring Boot hỗ trợ profile groups:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-notifications
        - observability
~~~

Khi active production, các profile trong group cũng được kích hoạt.

Profile group hữu ích khi một tên môi trường đại diện cho nhiều phần cấu hình cần bật đồng bộ. Không nên tạo một profile group chỉ để chọn một property đơn lẻ.

### 3.3. spring.profiles.include

spring.profiles.include có thể thêm profile vào tập profile active:

~~~yaml
spring:
  profiles:
    include:
      - common-metrics
~~~

Việc include được xử lý theo quy tắc riêng của Spring Boot và có thể kết hợp với profile group. Nếu dùng, cần kiểm tra tập profile thực tế khi startup; đừng giả định chỉ có đúng một profile.

### 3.4. Không khai báo spring.profiles.active trong profile-specific document

Các thuộc tính như spring.profiles.active và spring.profiles.include là cấu hình quyết định profile selection, không được đặt tùy tiện trong document đã được kích hoạt bởi profile-specific condition.

Hãy đặt lựa chọn profile ở nguồn cấu hình bootstrap phù hợp như command-line, environment hoặc document không phụ thuộc profile.

## 4. Khi nào @Profile là lựa chọn tốt?

Profile phù hợp khi một môi trường cần một **bộ cấu hình và wiring nhất quán**.

Ví dụ:

| Profile | Database | Notification | External integrations |
|---|---|---|---|
| local | H2 hoặc local database | Console/fake | Stub |
| test | Test database/container | Fake | Mock/stub |
| staging | Staging database | SMTP sandbox | Staging endpoints |
| prod | Production database | SMTP/provider thật | Production endpoints |

Một profile có thể chọn nhiều beans cùng lúc:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("test")
public class TestInfrastructureConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    NotificationSender notificationSender() {
        return new RecordingNotificationSender();
    }
}
~~~

Ở đây profile test mô tả một nhóm hạ tầng test. Điều này hợp lý hơn việc thêm property cho từng fake bean nếu tất cả phải cùng được bật khi chạy test.

### 4.1. Profile không nên đại diện cho mọi feature flag

Giả sử production có thể bật/tắt tính năng export hóa đơn mà không thay database, mail server hoặc các cấu hình khác. Tạo profile prod-with-export và prod-without-export sẽ làm số tổ hợp tăng nhanh.

Với một lựa chọn độc lập như vậy, property thường dễ quản lý hơn:

~~~yaml
app:
  invoice-export:
    enabled: false
~~~

### 4.2. Không dùng profile làm lựa chọn theo từng request

Profile được xác định trong Environment của ApplicationContext, thường tại startup. Nó không phải cơ chế để mỗi request chọn implementation theo user, tenant hoặc loại đơn hàng.

Nếu một ứng dụng phục vụ nhiều tenant với provider khác nhau trong cùng process, hãy dùng factory/strategy registry, routing logic hoặc cấu hình tenant-scoped phù hợp. Không thay active profile giữa các request.

## 5. Chuyển từ @Profile sang @ConditionalOnProperty

Nếu lựa chọn implementation thực chất là một tùy chọn độc lập, có thể chuyển bean registration sang property.

Spring Boot cung cấp:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
~~~

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
public class NotificationPropertyConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "console",
            matchIfMissing = true)
    NotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "smtp")
    NotificationSender smtpNotificationSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }
}
~~~

Cấu hình:

~~~yaml
app:
  notification:
    provider: smtp
~~~

Khi provider là smtp, bean SMTP được đăng ký. Nếu property không tồn tại, nhánh console match vì matchIfMissing=true.

### 5.1. Ý nghĩa của havingValue

havingValue yêu cầu property có giá trị tương ứng để condition match.

~~~java
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "enabled",
        havingValue = "true")
~~~

Chỉ match khi app.notification.enabled=true.

Nếu không đặt havingValue, condition mặc định match khi property tồn tại và giá trị không phải false. Để code dễ đọc, với boolean flag nên ghi havingValue = "true" hoặc "false" tường minh.

### 5.2. Ý nghĩa của matchIfMissing

Mặc định matchIfMissing=false. Nếu property không có, condition không match.

~~~java
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "provider",
        havingValue = "console",
        matchIfMissing = true)
~~~

cho phép chọn console làm fallback khi người vận hành chưa khai báo provider.

Chỉ dùng matchIfMissing=true khi default đó an toàn và có chủ đích. Với một tích hợp có thể gửi email thật, charge tiền hoặc ghi dữ liệu production, default ngầm định có thể không phù hợp.

### 5.3. Property không khớp thì có thể không có bean

Nếu:

~~~yaml
app:
  notification:
    provider: push
~~~

nhưng chỉ có condition cho console và smtp, không bean NotificationSender nào được tạo từ configuration này.

Nếu OrderNotificationService bắt buộc inject NotificationSender, context sẽ thất bại khi khởi tạo. Đây có thể là fail-fast hợp lý, nhưng thông báo lỗi cần giúp người vận hành nhận ra giá trị provider không được hỗ trợ.

Không nên thêm một implementation mặc định bất kỳ chỉ để ứng dụng khởi động với cấu hình sai.

## 6. Tách feature flag và provider selection

Một property có thể trả lời câu hỏi “có bật tính năng không?”, còn property khác trả lời “nếu bật thì dùng provider nào?”.

Ví dụ:

~~~yaml
app:
  notification:
    enabled: true
    provider: smtp
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "smtp")
    NotificationSender smtpNotificationSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "console")
    NotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

Ở đây cả hai điều kiện trên cùng một bean method phải match. Khi enabled=false, không implementation nào được đăng ký từ hai method này.

Nếu business service vẫn yêu cầu NotificationSender bắt buộc, feature disabled sẽ làm context fail. Khi đó cần quyết định rõ thiết kế:

- Không tạo service sử dụng NotificationSender khi feature tắt.
- Cung cấp một No-op implementation nếu “không gửi” là hành vi hợp lệ.
- Hoặc giữ bean nhưng service kiểm tra feature state theo một contract rõ ràng.

Không để feature flag tạo ra một bean graph không thể khởi động.

## 7. Dùng No-op implementation khi tắt tính năng là hợp lệ

Nếu nghiệp vụ cho phép ứng dụng tiếp tục chạy mà không gửi thông báo, có thể cung cấp một implementation không thực hiện side effect:

~~~java
package com.example.notification;

public class NoOpNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        // Chủ động không gửi.
    }
}
~~~

Đăng ký bean khi feature bị tắt:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "enabled",
        havingValue = "false")
NotificationSender noOpNotificationSender() {
    return new NoOpNotificationSender();
}
~~~

Khi đó OrderNotificationService vẫn nhận đúng một NotificationSender. Hành vi “không gửi” được thể hiện bằng implementation cụ thể thay vì để dependency biến mất.

### 7.1. Khi nào No-op không phù hợp?

No-op chỉ hợp lệ nếu bỏ qua hành động là một lựa chọn nghiệp vụ được chấp nhận. Không dùng nó để che lỗi đối với:

- Thanh toán hoặc hoàn tiền.
- Ghi audit bắt buộc.
- Gửi cảnh báo bảo mật bắt buộc.
- Lưu dữ liệu không thể tái tạo.
- Đồng bộ trạng thái cần bảo đảm.

Trong những trường hợp đó, tắt tính năng phải làm rõ hệ thống có được phép chạy hay không. Có thể fail-fast khi startup hoặc ngăn luồng nghiệp vụ tương ứng.

### 7.2. Ma trận lựa chọn khi enabled

| enabled | provider | Bean dự kiến |
|---|---|---|
| true | console | ConsoleNotificationSender |
| true | smtp | SmtpNotificationSender |
| false | bất kỳ/không dùng | NoOpNotificationSender |

Nếu property provider không cần thiết khi enabled=false, đừng để cấu hình gây hiểu nhầm rằng provider vẫn được sử dụng.

## 8. Chuyển đổi từng bước từ profile sang property

Giả sử hiện trạng có:

~~~java
@Bean
@Profile("local")
NotificationSender consoleNotificationSender() {
    return new ConsoleNotificationSender();
}

@Bean
@Profile("prod")
NotificationSender smtpNotificationSender(SmtpClient client) {
    return new SmtpNotificationSender(client);
}
~~~

Mục tiêu mới là để provider có thể được chọn độc lập với môi trường:

~~~yaml
app:
  notification:
    provider: console
~~~

hoặc:

~~~yaml
app:
  notification:
    provider: smtp
~~~

### Bước 1 — Xác định ý nghĩa lựa chọn

Hãy hỏi: local luôn phải console và prod luôn phải SMTP hay production đôi khi cần provider khác, staging có thể chọn provider riêng, và test cần recording fake?

Nếu lựa chọn gắn cứng với bộ môi trường, giữ profile. Nếu nó là một quyết định độc lập, property sẽ linh hoạt hơn.

### Bước 2 — Định nghĩa key và giá trị được phép

Chọn một key ổn định:

~~~text
app.notification.provider
~~~

Và các giá trị:

~~~text
console
smtp
~~~

Đừng để nhiều alias không cần thiết như mail, email, smtp-mail, real-mail cùng chỉ một implementation. Giá trị cấu hình nên có vocabulary nhỏ và được tài liệu hóa.

### Bước 3 — Chuyển bean registration

~~~java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "console")
    NotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "smtp")
    NotificationSender smtpNotificationSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }
}
~~~

Trong ví dụ chuyển đổi nghiêm ngặt, không đặt matchIfMissing=true để property bị thiếu làm context không có sender. Có thể chọn một default rõ ràng nếu yêu cầu sản phẩm cho phép; cần test chính sách đó.

### Bước 4 — Cập nhật cấu hình theo từng môi trường

application-local.yml:

~~~yaml
app:
  notification:
    provider: console
~~~

application-prod.yml:

~~~yaml
app:
  notification:
    provider: smtp
~~~

Profile vẫn có thể dùng để nạp cấu hình môi trường, trong khi property chọn implementation. Đây là mô hình kết hợp thường hữu ích: **profile chọn bộ cấu hình; property trong bộ đó chọn một capability**.

### Bước 5 — Kiểm tra nơi override property

Một command-line argument có thể ghi đè file:

~~~bash
java -jar order-api.jar \
  --spring.profiles.active=prod \
  --app.notification.provider=console
~~~

Theo precedence mặc định, command-line property có thể override giá trị trong application-prod.yml. Điều này hữu ích khi test hoặc vận hành có chủ đích, nhưng cũng có thể làm production dùng nhầm provider nếu launcher truyền sai argument.

### Bước 6 — Gỡ annotation/profile cũ

Khi property-based configuration đã thay thế hoàn toàn profile-based bean registration, xóa hoặc ngừng import configuration cũ.

Nếu giữ cả hai:

- Profile local có thể đăng ký console bean.
- Property provider=smtp có thể đăng ký thêm SMTP bean.
- Một service inject NotificationSender có thể gặp NoUniqueBeanDefinitionException.

Đừng dựa vào @Primary để che hai cấu hình selector đang cùng hoạt động. Mỗi chức năng nên có một nguồn quyết định implementation rõ ràng.

### Bước 7 — Kiểm thử các nhánh trước khi triển khai

Ít nhất cần test:

- provider=console tạo console sender.
- provider=smtp tạo SMTP sender.
- property thiếu có hành vi đúng theo chính sách đã chọn.
- provider không hỗ trợ không âm thầm chọn implementation khác.
- Các profile môi trường vẫn nạp đúng giá trị provider.

## 9. Khi nào nên chuyển từ property sang profile?

Chiều chuyển ngược lại cũng có thể hợp lý. Giả sử một property duy nhất:

~~~yaml
app:
  integration:
    use-stub: true
~~~

đang được dùng để chọn nhiều fake clients cùng lúc trong test:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.integration",
        name = "use-stub",
        havingValue = "true")
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}

@Bean
@ConditionalOnProperty(
        prefix = "app.integration",
        name = "use-stub",
        havingValue = "true")
NotificationSender recordingSender() {
    return new RecordingNotificationSender();
}
~~~

Nếu test profile luôn cần đồng thời fake payment và recording notification, profile có thể diễn đạt nhóm cấu hình rõ hơn:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("test")
public class TestIntegrationConfiguration {

    @Bean
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    NotificationSender recordingSender() {
        return new RecordingNotificationSender();
    }
}
~~~

### 9.1. Dấu hiệu property đang mô phỏng một environment

- Một boolean property được thêm chỉ để bật một nhóm nhiều fake beans.
- Nhiều property phải luôn đổi cùng nhau để một môi trường hoạt động.
- Mỗi deployment đều có một tổ hợp property gần như cố định.
- Các file cấu hình bị trùng lặp vì không có profile grouping.

Khi đó, profile hoặc profile group có thể là mô hình dễ hiểu hơn.

### 9.2. Không chuyển property thành profile nếu lựa chọn vẫn độc lập

Nếu production có thể bật/tắt export, audit hoặc một integration riêng lẻ mà không đổi toàn bộ cấu hình, giữ property. Không tạo một profile cho mỗi tổ hợp feature flags.

Ví dụ nếu có 5 feature độc lập, việc tạo profile cho mọi tổ hợp có thể tạo đến 2^5 tổ hợp. Property giúp mỗi lựa chọn được quản lý riêng.

## 10. Kết hợp profile và property trong cùng ứng dụng

Không cần ép toàn bộ cấu hình dùng một cơ chế. Hai cơ chế có thể bổ sung cho nhau.

Ví dụ:

~~~yaml
# application.yml
spring:
  application:
    name: order-api

app:
  notification:
    enabled: true
~~~

~~~yaml
# application-local.yml
app:
  notification:
    provider: console
~~~

~~~yaml
# application-prod.yml
app:
  notification:
    provider: smtp
    enabled: true
~~~

Profile chọn file cấu hình theo môi trường. Property provider chọn bean. Property enabled bật/tắt capability.

### 10.1. Không tạo hai selector mâu thuẫn

Ví dụ không rõ ràng:

~~~java
@Bean
@Profile("prod")
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "provider",
        havingValue = "console")
NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}
~~~

Bean chỉ được đăng ký khi **cả hai** điều kiện cùng match: prod active và provider=console. Điều này có thể là chủ đích trong một trường hợp đặc biệt, nhưng nếu mục tiêu là chọn provider cho mọi môi trường thì @Profile("prod") đang giới hạn bean không cần thiết.

Khi kết hợp conditions, hãy viết rõ chúng là AND conditions trên cùng bean/configuration. Nếu cần OR logic, biểu đạt bằng profile expression hoặc cấu trúc configuration/condition phù hợp, và test từng nhánh.

### 10.2. Dùng profile-specific property values để tránh điều kiện profile trong code

Một pattern dễ bảo trì:

- Java configuration chỉ hiểu app.notification.provider.
- application-local.yml đặt provider=console.
- application-prod.yml đặt provider=smtp.
- Không cần lặp @Profile trên từng implementation.

Nhờ vậy, nếu staging muốn dùng console hoặc SMTP sandbox, chỉ cần thay property trong file staging mà không sửa code bean selector.

## 11. Gom các property liên quan bằng @ConfigurationProperties

Khi cấu hình có nhiều field, không nên rải nhiều @Value trong các service. Dùng một configuration properties class để thể hiện contract cấu hình.

Ví dụ:

~~~java
package com.example.notification;

import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @NotNull NotificationProvider provider,
        boolean enabled) {
}
~~~

Enum:

~~~java
package com.example.notification;

public enum NotificationProvider {
    CONSOLE,
    SMTP
}
~~~

Đăng ký properties:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationPropertyConfiguration {
    // Các @Bean có điều kiện ở đây.
}
~~~

Trong application.yml:

~~~yaml
app:
  notification:
    enabled: true
    provider: SMTP
~~~

Spring Boot Binder có thể chuyển giá trị property thành enum tương ứng. Nếu giá trị không hợp lệ hoặc provider bị thiếu trong khi field có @NotNull, quá trình bind/validation sẽ báo lỗi thay vì để service nhận một cấu hình không rõ nghĩa.

### 11.1. Dependency validation

Để dùng Jakarta Bean Validation như @NotNull, dự án cần có validation provider phù hợp, thường qua:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Annotation constraint mà không có provider tương ứng sẽ không bảo đảm validation được thực thi.

### 11.2. Properties class không tự chọn bean

NotificationProperties chỉ bind và validate giá trị. Việc đăng ký ConsoleNotificationSender hay SmtpNotificationSender vẫn do configuration conditions quyết định.

Có thể inject properties vào service nếu service cần đọc setting runtime, nhưng đừng tạo một service tự khởi tạo implementation bằng new chỉ vì đã có properties object. Hãy để Spring configuration wiring đảm nhiệm lựa chọn bean.

### 11.3. Tránh hai nguồn sự thật

Không nên vừa có:

~~~yaml
app:
  notification:
    provider: smtp
~~~

vừa có một profile-based configuration luôn đăng ký ConsoleNotificationSender ở prod. Hai selector sẽ mâu thuẫn.

Một nguồn property có thể được đặt bởi nhiều property sources, nhưng **quy tắc chọn implementation cần có một contract duy nhất**.

## 12. Đưa feature flag vào properties và chọn bean có chủ đích

Có thể tách provider và enabled thành hai phần:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationBeansConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "CONSOLE")
    NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "provider",
            havingValue = "SMTP")
    NotificationSender smtpSender(SmtpClient client) {
        return new SmtpNotificationSender(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notification",
            name = "enabled",
            havingValue = "false")
    NotificationSender noOpSender() {
        return new NoOpNotificationSender();
    }
}
~~~

Ví dụ này dùng enum text in hoa trong property để tương ứng với enum. Nếu muốn cấu hình lowercase như smtp, có thể dùng chuỗi và chuẩn hóa/validate theo quy ước của ứng dụng; không nên giả định mọi conversion/custom condition đều có cùng semantics.

Lưu ý: @ConditionalOnProperty có thể được đặt lặp lại trên cùng một method thông qua repeatable annotation. Các conditions phải cùng match để bean method được đăng ký.

### 12.1. Test giá trị không được hỗ trợ

Nếu provider=push nhưng không có bean condition nào match, properties validation cũng cần bắt giá trị sai. Một enum property giúp Binder báo lỗi chuyển đổi khi giá trị không thuộc enum.

Nếu chỉ dùng String, hãy thêm validation rõ ràng để giá trị lạ không âm thầm làm context thiếu bean.

### 12.2. Không dùng boolean string tùy tiện

Các giá trị như:

~~~text
yes
on
enabled
1
~~~

có thể gây bất ngờ khi dùng với conditional property yêu cầu havingValue cụ thể. Dùng true/false chuẩn và ghi rõ trong cấu hình.

## 13. Property precedence và override khi chọn implementation

Spring Boot có nhiều nguồn property. Một property cùng key có thể được đặt trong:

- application.yml.
- application-local.yml hoặc application-prod.yml.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Các Config Data locations/imports khác.

Nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị thấp hơn theo property source precedence của Spring Boot.

Ví dụ application-prod.yml:

~~~yaml
app:
  notification:
    provider: smtp
~~~

Nhưng process được chạy:

~~~bash
java -jar order-api.jar \
  --spring.profiles.active=prod \
  --app.notification.provider=console
~~~

Command-line property có thể override giá trị trong profile-specific file. Vì vậy, profile prod active không có nghĩa provider chắc chắn là SMTP.

### 13.1. Environment variable mapping

Property app.notification.provider thường có thể được cung cấp qua environment variable:

~~~text
APP_NOTIFICATION_PROVIDER=SMTP
~~~

Điều này hữu ích trong Docker/Kubernetes, nơi deployment inject environment variables hoặc mount config.

### 13.2. Xác minh effective property

Có thể đọc giá trị cuối qua Environment:

~~~java
@Component
public class NotificationConfigurationLogger {

    private final Environment environment;

    public NotificationConfigurationLogger(Environment environment) {
        this.environment = environment;
    }

    public void logProvider() {
        log.info(
                "Notification provider: {}",
                environment.getProperty(
                        "app.notification.provider"));
    }
}
~~~

Ví dụ chỉ log provider vì đây không phải secret. Không log toàn bộ Environment hoặc các credentials.

### 13.3. Đừng suy luận từ tên profile

Khi prod active, property có thể bị override từ command-line hoặc environment. Nếu vận hành yêu cầu bắt buộc SMTP ở production, có thể bổ sung validation/guard theo chính sách deploy, nhưng phải định nghĩa rõ điều gì được phép.

Ví dụ: nếu profile prod và provider=console là cấu hình bị cấm, có thể thêm kiểm tra startup chuyên biệt. Đừng chỉ dựa vào tên file application-prod.yml để khẳng định.

## 14. Multi-document YAML và spring.config.activate.on-profile

Thay vì tạo nhiều file, có thể đặt nhiều document trong một YAML:

~~~yaml
app:
  notification:
    provider: console
---
spring:
  config:
    activate:
      on-profile: prod
app:
  notification:
    provider: smtp
~~~

Document thứ hai chỉ được áp dụng khi profile prod active.

Điều này vẫn là profile-based activation của Config Data document. Bean selector trong Java có thể tiếp tục dùng property app.notification.provider.

### 14.1. Khi nào multi-document YAML hữu ích?

- Cấu hình nhỏ, có vài biến thể rõ ràng.
- Muốn giữ các giá trị gần nhau trong một file.
- Muốn dùng spring.config.activate.on-profile để kích hoạt document.

### 14.2. Khi nào nên tách file?

- Mỗi môi trường có nhiều cấu hình riêng.
- File dài và khó review.
- Quyền quản lý/secret sources khác nhau.
- Deployment mount file theo môi trường.

Chọn cách tổ chức file theo cách đội vận hành quản lý cấu hình, không phải để Java code phải biết đường dẫn file.

## 15. Điều kiện @ConditionalOnProperty có giới hạn gì?

@ConditionalOnProperty phù hợp với scalar properties như string, boolean hoặc enum đã được biểu diễn thành text. Tuy nhiên, annotation không phải bộ truy vấn tổng quát cho mọi cấu trúc property.

### 15.1. Không nên dùng để kiểm tra indexed collection

Ví dụ:

~~~yaml
app:
  notification:
    recipients:
      - ops@example.invalid
      - support@example.invalid
~~~

Kiểm tra sự tồn tại của app.notification.recipients bằng @ConditionalOnProperty có thể không hoạt động như mong đợi với indexed collection.

Nếu cần điều kiện dựa trên collection/map, hãy bind bằng @ConfigurationProperties rồi kiểm tra trong một cơ chế phù hợp, hoặc viết custom Condition khi thật sự cần điều kiện hóa bean registration.

### 15.2. Condition được đánh giá trong startup

@ConditionalOnProperty quyết định bean definition có được đăng ký khi context được xử lý hay không. Thay đổi một environment variable hoặc file bên ngoài sau startup không tự làm Spring tạo/hủy lại bean.

Nếu cần feature flag thay đổi khi ứng dụng đang chạy:

- Dùng một properties/state service có thể cập nhật theo cơ chế được thiết kế.
- Cho business service kiểm tra flag ở thời điểm thực thi.
- Hoặc dùng dynamic configuration/refresh mechanism phù hợp với hệ thống.

Không mong đợi @ConditionalOnProperty tự hot-swap implementation trong một ApplicationContext đang chạy.

### 15.3. Không dùng @ConditionalOnProperty làm validation duy nhất

Condition không match có thể chỉ khiến bean không được đăng ký. Nó không luôn tạo thông báo rõ rằng người dùng nhập sai giá trị.

Kết hợp:

- @ConfigurationProperties để bind.
- Bean Validation để kiểm tra input.
- @ConditionalOnProperty để điều kiện hóa wiring.
- Startup tests để bảo vệ các nhánh.

## 16. Khi property chọn implementation theo từng request

Một lựa chọn cần thay đổi theo user/tenant không nên được biểu diễn bằng active profile hoặc conditional bean.

Ví dụ:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

Hai implementation:

~~~java
public class CardPaymentGateway implements PaymentGateway {
    // ...
}

public class WalletPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Nếu một process phục vụ đồng thời cả card và wallet, đăng ký cả hai beans rồi chọn qua factory:

~~~java
@Component
public class PaymentGatewayRegistry {

    private final Map<PaymentMethod, PaymentGateway> gateways;

    public PaymentGatewayRegistry(
            CardPaymentGateway card,
            WalletPaymentGateway wallet) {
        this.gateways = Map.of(
                PaymentMethod.CARD, card,
                PaymentMethod.WALLET, wallet);
    }

    public PaymentGateway forMethod(PaymentMethod method) {
        PaymentGateway gateway = gateways.get(method);
        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment method: " + method);
        }
        return gateway;
    }
}
~~~

Ở đây lựa chọn diễn ra theo request data. Profile/property chỉ quyết định provider nào được phép/có sẵn trong ứng dụng, không thay thế routing logic theo từng giao dịch.

Nếu mỗi tenant có endpoint/credential riêng, cần thiết kế registry/tenant configuration và secret handling phù hợp. Không tạo một profile cho từng tenant.

## 17. Kiểm thử lựa chọn bằng profile

Một cách kiểm tra profile-based configuration là tạo context nhỏ và kích hoạt profile tương ứng.

Ví dụ JUnit 5 với ApplicationContextRunner:

~~~java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class NotificationProfileConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            NotificationProfileConfiguration.class);

    @Test
    void localProfileCreatesConsoleSender() {
        runner.withPropertyValues(
                    "spring.profiles.active=local")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                    assertThat(context.getBean(NotificationSender.class))
                            .isInstanceOf(
                                    ConsoleNotificationSender.class);
                });
    }

    @Test
    void prodProfileCreatesSmtpSender() {
        runner.withPropertyValues(
                    "spring.profiles.active=prod")
                .withBean(SmtpClient.class, TestSmtpClient::new)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                    assertThat(context.getBean(NotificationSender.class))
                            .isInstanceOf(
                                    SmtpNotificationSender.class);
                });
    }

    @Test
    void noMatchingProfileRegistersNoSender() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .doesNotHaveBean(NotificationSender.class);
        });
    }
}
~~~

Test fixture TestSmtpClient là implementation giả của collaborator SmtpClient trong ví dụ.

### 17.1. Vì sao không có profile thì test không có sender?

Configuration chỉ đăng ký bean cho local và prod. Nếu không profile nào match, hai @Bean methods đều bị loại.

Nếu context còn một service bắt buộc inject NotificationSender, context sẽ thất bại. Test trên không import service đó vì mục tiêu là quan sát riêng bean selection.

### 17.2. Nhiều profile có thể cùng active

Spring cho phép nhiều profile active cùng lúc. Nếu chạy:

~~~bash
java -jar order-api.jar \
  --spring.profiles.active=local,prod
~~~

cả hai bean methods có thể match và đăng ký hai NotificationSender beans. Một service inject một NotificationSender không có qualifier có thể gặp NoUniqueBeanDefinitionException.

Không giả định local và prod tự loại trừ nhau. Nếu hai profile là lựa chọn loại trừ, deployment phải kích hoạt đúng một trong số đó hoặc configuration cần kiểm soát tổ hợp được phép.

### 17.3. Kiểm tra profile thực tế

Có thể quan sát:

~~~java
environment.getActiveProfiles();
~~~

Nếu dùng profile group/include, danh sách active có thể chứa nhiều profile hơn tên mà launcher truyền vào. Hãy kiểm tra Environment thay vì chỉ nhìn một biến môi trường.

## 18. Kiểm thử lựa chọn bằng property

Với property-based configuration, ApplicationContextRunner giúp kiểm tra mỗi giá trị một cách cô lập.

~~~java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class NotificationPropertyConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            NotificationPropertyConfiguration.class);

    @Test
    void consolePropertyCreatesConsoleSender() {
        runner.withPropertyValues(
                    "app.notification.provider=console")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                    assertThat(context.getBean(NotificationSender.class))
                            .isInstanceOf(
                                    ConsoleNotificationSender.class);
                });
    }

    @Test
    void smtpPropertyCreatesSmtpSender() {
        runner.withPropertyValues(
                    "app.notification.provider=smtp")
                .withBean(SmtpClient.class, TestSmtpClient::new)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                    assertThat(context.getBean(NotificationSender.class))
                            .isInstanceOf(
                                    SmtpNotificationSender.class);
                });
    }

    @Test
    void unsupportedProviderCreatesNoSender() {
        runner.withPropertyValues(
                    "app.notification.provider=push")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(NotificationSender.class);
                });
    }
}
~~~

Test thứ ba không có business service yêu cầu NotificationSender, nên context vẫn khởi động dù không có sender. Trong ứng dụng thật, nếu sender là dependency bắt buộc, startup có thể fail. Đây là một cách test riêng condition outcome.

### 18.1. Kiểm thử matchIfMissing

Nếu selector có:

~~~java
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "provider",
        havingValue = "console",
        matchIfMissing = true)
~~~

có thể kiểm tra:

~~~java
@Test
void missingProviderUsesConsoleFallback() {
    runner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context.getBean(NotificationSender.class))
                .isInstanceOf(ConsoleNotificationSender.class);
    });
}
~~~

Đừng giữ test fallback này nếu contract đã đổi thành bắt buộc khai báo provider. Test phải phản ánh chính sách cấu hình được công bố.

### 18.2. Kiểm thử enabled=false

Nếu NoOpNotificationSender là fallback khi tắt feature:

~~~java
@Test
void disabledFeatureUsesNoOpSender() {
    runner.withPropertyValues(
                "app.notification.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .hasSingleBean(NotificationSender.class);
                assertThat(context.getBean(NotificationSender.class))
                        .isInstanceOf(NoOpNotificationSender.class);
            });
}
~~~

Test này giả định NotificationConfiguration có condition đăng ký no-op bean và provider bean không match khi disabled. Nó không áp dụng nguyên xi cho cấu hình chỉ có hai provider conditions ở phần trước.

## 19. Kiểm thử profile-specific properties cùng bean selector

Context runner có thể test profile active và property selector riêng, nhưng nếu muốn kiểm tra việc Spring Boot thực sự nạp application-prod.yml từ Config Data, cần một test khởi động SpringApplication với Config Data location được kiểm soát.

Phân biệt hai mục tiêu:

| Test | Điều được chứng minh |
|---|---|
| Profile context test | @Profile chọn bean theo active profiles |
| Property context test | @ConditionalOnProperty chọn bean theo Environment property |
| Config Data integration test | application-prod.yml hoặc location được chỉ định thực sự được nạp |
| Deployment smoke test | Environment/profile/config trong runtime thật chọn đúng implementation |

### 19.1. Không dùng test property để giả vờ kiểm tra YAML

Ví dụ:

~~~java
runner.withPropertyValues(
        "spring.profiles.active=prod",
        "app.notification.provider=smtp");
~~~

Test này xác minh profile và property trong Environment của context runner. Nó **không tự chứng minh** application-prod.yml đã được tìm thấy hoặc đọc.

Nếu cần kiểm tra Config Data loading, tạo file cấu hình tạm và khởi chạy SpringApplication với location tương ứng, hoặc dùng một integration test thực sự đọc file.

### 19.2. Kiểm tra active profile và effective provider

Trong ứng dụng có thể ghi log an toàn:

~~~java
log.info(
        "Active profiles: {}",
        Arrays.toString(environment.getActiveProfiles()));
log.info(
        "Notification provider: {}",
        environment.getProperty(
                "app.notification.provider"));
~~~

Chỉ log thông tin không nhạy cảm. Đừng log tất cả property sources nếu chúng chứa credentials.

## 20. So sánh trực tiếp profile và property

| Tiêu chí | Profile | Property |
|---|---|---|
| Ý nghĩa chính | Nhóm môi trường/cấu hình active | Một lựa chọn hoặc giá trị cụ thể |
| Chọn nhiều bean đồng bộ | Rất phù hợp | Có thể nhưng cần lặp conditions |
| Chọn implementation đơn lẻ | Có thể | Thường rõ ràng |
| Feature flag độc lập | Dễ tạo nhiều profile tổ hợp | Phù hợp |
| Cấu hình file theo môi trường | application-{profile}.yml | Có thể đặt trong bất kỳ property source nào |
| Nhiều lựa chọn đồng thời | Nhiều profiles có thể active cùng lúc | Mỗi property có một effective value |
| Thay đổi khi runtime | Không tự đổi wiring của context | Condition cũng không tự đổi wiring sau startup |
| Chọn theo request/tenant | Không phù hợp | Condition cũng không phù hợp; cần routing/service logic |
| Kiểm thử | Kích hoạt profile rồi kiểm tra beans | Đặt property rồi kiểm tra beans |

### 20.1. Một quy tắc chọn nhanh

- Nếu một tên đại diện cho **cả bộ cấu hình môi trường**, dùng profile.
- Nếu một key chọn **một provider/feature cụ thể**, dùng property.
- Nếu lựa chọn thay đổi theo **request, user hoặc tenant**, dùng strategy/factory/runtime routing.
- Nếu lựa chọn cần đổi **ngay khi ứng dụng đang chạy**, thiết kế dynamic state/configuration riêng; không trông đợi @Profile hoặc @ConditionalOnProperty tự thay bean.

## 21. Cấu hình profile/property trong Docker và Kubernetes

Một image có thể được dùng ở nhiều môi trường. Không nên build một JAR khác chỉ để đổi implementation nếu code và dependency giống nhau.

### 21.1. Docker environment variables

Ví dụ:

~~~bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e APP_NOTIFICATION_PROVIDER=SMTP \
  -e APP_NOTIFICATION_ENABLED=true \
  order-api:latest
~~~

Trong ví dụ:

- SPRING_PROFILES_ACTIVE chọn bộ cấu hình production.
- APP_NOTIFICATION_PROVIDER chọn provider.
- APP_NOTIFICATION_ENABLED bật capability.

Nếu application-prod.yml cũng khai báo provider=smtp, environment variable có thể cung cấp/ghi đè giá trị theo property source precedence.

### 21.2. Kubernetes Deployment

Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: order-api
          image: registry.example.invalid/order-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: APP_NOTIFICATION_PROVIDER
              value: SMTP
            - name: APP_NOTIFICATION_ENABLED
              value: "true"
~~~

Đây là manifest minh họa. Trong hệ thống thật, các giá trị và image reference cần được quản lý bởi deployment pipeline/manifest phù hợp.

### 21.3. Secret không phải provider selector

Provider có thể là một giá trị không nhạy cảm như SMTP, nhưng password/token dùng để kết nối mail server phải được quản lý qua Secret hoặc secret manager.

Ví dụ:

~~~yaml
app:
  notification:
    provider: smtp
    smtp:
      host: mail.example.invalid
      username: order-api
      # Cấp app.notification.smtp.password từ secret source của deployment.
~~~

Không commit password thật vào application-prod.yml. Deployment phải cung cấp property tương ứng và giới hạn quyền truy cập.

### 21.4. Profile không phải ranh giới bảo mật

Kích hoạt profile prod không tự bảo vệ credential, endpoint hoặc quyền truy cập. Bảo mật phải dựa trên secret management, network policy, identity và authorization.

Không coi @Profile("prod") là cơ chế access control cho một API hoặc dữ liệu nhạy cảm.

## 22. Default implementation và @ConditionalOnMissingBean

Một starter có thể muốn cung cấp default NotificationSender nếu ứng dụng chưa đăng ký bean nào. Đây là trường hợp khác với chọn provider bằng property.

Ví dụ trong auto-configuration:

~~~java
@AutoConfiguration
public class NotificationDefaultAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    NotificationSender defaultNotificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

Khi ứng dụng có bean NotificationSender riêng, auto-configuration nên back off theo type.

### 22.1. Phân biệt ba cách chọn

- @Profile: bean được đăng ký khi một profile match.
- @ConditionalOnProperty: bean được đăng ký khi property match.
- @ConditionalOnMissingBean: bean được đăng ký khi chưa có bean phù hợp.

Có thể kết hợp chúng, nhưng mỗi condition phải phản ánh một lý do riêng.

### 22.2. Đừng dùng default bean để che provider value sai

Nếu provider=push nhưng chỉ hỗ trợ console/smtp, việc tạo default console bằng @ConditionalOnMissingBean có thể làm cấu hình sai chạy âm thầm.

Default bean phù hợp khi mục tiêu là cung cấp fallback nếu user chưa custom, không phải để chấp nhận mọi giá trị property không hợp lệ.

### 22.3. Thứ tự auto-configuration

@ConditionalOnMissingBean được dùng phổ biến trong auto-configuration vì Boot xử lý auto-configurations theo cơ chế ordering để user configuration có thể được ưu tiên.

Nếu đặt condition này trong một configuration class thông thường được xử lý trước user bean, kết quả có thể không như mong đợi. Hãy test với ApplicationContextRunner và AutoConfigurations.of khi phát triển starter.

## 23. Cách chọn default khi property bị thiếu

Có ba chính sách thường gặp:

### 23.1. Bắt buộc khai báo

Không đặt matchIfMissing=true. Nếu provider thiếu, không có bean phù hợp hoặc properties validation fail.

Phù hợp khi chọn nhầm provider có hậu quả đáng kể.

### 23.2. Default an toàn

Đặt matchIfMissing=true cho một implementation an toàn như console/no-op, nếu đó là contract được công bố.

Phù hợp với local tools hoặc thư viện muốn chạy được với cấu hình tối thiểu.

### 23.3. Default theo profile-specific file

application-local.yml có thể đặt provider=console, application-prod.yml đặt provider=smtp. Java selector yêu cầu property có mặt.

Phù hợp khi deployment đã có profile rõ ràng và mỗi môi trường phải chọn provider cụ thể.

### 23.4. Không để default thay đổi âm thầm giữa môi trường

Ví dụ nguy hiểm:

- Local thiếu provider → console.
- Production thiếu provider → cũng console vì matchIfMissing=true.

Nếu production yêu cầu SMTP, default console có thể che lỗi thiếu cấu hình và khiến thông báo không được gửi.

Hãy chọn một trong các chính sách trên và ghi rõ trong tài liệu vận hành.

## 24. Những lỗi thường gặp khi chuyển profile/property

### 24.1. Cả profile cũ và property selector cùng đăng ký bean

**Dấu hiệu:** NoUniqueBeanDefinitionException vì có console và SMTP cùng tồn tại.

**Nguyên nhân:** configuration cũ vẫn được import hoặc profile active cùng lúc với property selector mới.

**Cách xử lý:** chọn một nơi chịu trách nhiệm đăng ký implementation; xóa/disable selector cũ sau khi migration hoàn tất.

### 24.2. Kích hoạt đồng thời hai profile loại trừ nhau

**Dấu hiệu:** nhiều bean cùng interface dù mỗi profile riêng lẻ chạy đúng.

**Nguyên nhân:** Spring cho phép nhiều active profiles. local,prod có thể cùng match hai @Profile methods.

**Cách xử lý:** kiểm soát danh sách active profiles ở launcher/deployment; thêm startup guard nếu các tổ hợp đó bị cấm.

### 24.3. Nghĩ rằng profile prod luôn quyết định provider

**Dấu hiệu:** prod active nhưng ứng dụng dùng console.

**Nguyên nhân:** provider bị override từ command-line, environment variable hoặc property source ưu tiên cao hơn.

**Cách xử lý:** kiểm tra effective property và nguồn cung cấp; kiểm tra arguments/env của process.

### 24.4. Gõ sai property key

**Dấu hiệu:** không bean nào match dù YAML nhìn có vẻ đúng.

**Nguyên nhân:** prefix/name không khớp, ví dụ app.notification.provider khác app.notifications.provider.

**Cách xử lý:** đối chiếu key trong annotation, YAML và environment variable mapping. Dùng @ConfigurationProperties để tập trung contract.

### 24.5. Quên havingValue

**Dấu hiệu:** một property có giá trị ngoài dự kiến vẫn làm condition match.

**Nguyên nhân:** không đặt havingValue; default semantics là property tồn tại và không bằng false.

**Cách xử lý:** với provider selector, ghi havingValue cho từng giá trị rõ ràng.

### 24.6. Dùng matchIfMissing sai

**Dấu hiệu:** production chạy default dù deployment quên khai báo provider.

**Nguyên nhân:** matchIfMissing=true cho một fallback không an toàn trong môi trường đó.

**Cách xử lý:** yêu cầu property bắt buộc hoặc đặt giá trị profile-specific rõ ràng; test trường hợp property vắng mặt.

### 24.7. Giá trị property không được hỗ trợ

**Dấu hiệu:** không có NotificationSender hoặc startup fail ở một bean downstream.

**Nguyên nhân:** property có giá trị push nhưng chỉ có condition console/smtp.

**Cách xử lý:** dùng enum/validation hoặc startup guard để báo rõ tập giá trị hợp lệ.

### 24.8. Tắt feature nhưng service vẫn cần bean

**Dấu hiệu:** context fail vì thiếu NotificationSender khi enabled=false.

**Nguyên nhân:** condition loại bỏ provider bean trong khi consumer vẫn có constructor dependency bắt buộc.

**Cách xử lý:** chọn No-op implementation nếu hợp lệ, điều kiện hóa cả consumer hoặc thiết kế feature state rõ ràng.

### 24.9. No-op che mất lỗi nghiệp vụ

**Dấu hiệu:** thanh toán/audit/cảnh báo không được thực hiện nhưng ứng dụng vẫn báo thành công.

**Nguyên nhân:** dùng implementation rỗng cho một capability bắt buộc.

**Cách xử lý:** chỉ dùng no-op khi không thực hiện hành động là behavior được chấp nhận. Với capability bắt buộc, fail-fast hoặc chặn use case.

### 24.10. Đổi property sau startup nhưng bean không đổi

**Dấu hiệu:** sửa environment/config file nhưng process đang chạy vẫn dùng implementation cũ.

**Nguyên nhân:** condition đã được đánh giá khi context bootstrap.

**Cách xử lý:** restart/rollout hoặc dùng dynamic configuration mechanism có thiết kế riêng. Không kỳ vọng @ConditionalOnProperty tự thay bean.

### 24.11. Dùng @ConditionalOnProperty cho collection

**Dấu hiệu:** condition không match dù YAML có list recipients.

**Nguyên nhân:** annotation không phù hợp để kiểm tra indexed collection properties.

**Cách xử lý:** bind collection qua @ConfigurationProperties và kiểm tra bằng logic phù hợp.

### 24.12. Dùng profile để chọn theo từng request

**Dấu hiệu:** cố thay active profile theo tenant hoặc user.

**Nguyên nhân:** profile thuộc Environment của ApplicationContext, không phải request context.

**Cách xử lý:** dùng factory/strategy registry hoặc tenant-aware routing.

### 24.13. Test bằng withPropertyValues nhưng tưởng đã test file YAML

**Dấu hiệu:** test pass nhưng deployment không nạp application-prod.yml.

**Nguyên nhân:** test trực tiếp đưa property vào context, bỏ qua Config Data file loading.

**Cách xử lý:** viết Config Data integration test hoặc startup smoke test với file/location thực.

### 24.14. Test profile không tạo profile thật

**Dấu hiệu:** @Profile bean không xuất hiện trong test.

**Nguyên nhân:** chỉ đặt property tùy ý thay vì active profile, hoặc context test không nhận property spring.profiles.active như mong muốn.

**Cách xử lý:** dùng context initializer để gọi Environment.setActiveProfiles(...) hoặc kiểm tra active profiles của context trước khi assert bean.

### 24.15. Chỉ kiểm tra bean được inject mà không đếm candidates

**Dấu hiệu:** test inject được custom sender nhưng default cũng tồn tại.

**Nguyên nhân:** @Primary hoặc qualifier khiến injection chọn một bean trong khi context có nhiều candidates.

**Cách xử lý:** assert hasSingleBean và kiểm tra bean names khi contract yêu cầu chỉ có một implementation.

### 24.16. Đưa secret vào profile-specific YAML trong repository

**Dấu hiệu:** application-prod.yml chứa SMTP password hoặc API token.

**Nguyên nhân:** nhầm profile file là secret store.

**Cách xử lý:** giữ non-secret settings trong file cấu hình; cấp credentials qua secret manager, Kubernetes Secret hoặc nguồn bảo mật được tổ chức phê duyệt.

### 24.17. Tạo profile cho mọi tổ hợp feature

**Dấu hiệu:** có các profile như prod-mail-on-export-off, prod-mail-off-export-on.

**Nguyên nhân:** dùng profile để điều khiển các lựa chọn độc lập.

**Cách xử lý:** profile cho nhóm môi trường; property cho feature flags và provider options.

### 24.18. Đặt @Profile ở cấp class ngoài ý muốn

**Dấu hiệu:** nhiều bean trong configuration cùng biến mất dù chỉ muốn điều kiện hóa một bean.

**Nguyên nhân:** @Profile đặt trên @Configuration class áp dụng cho toàn configuration.

**Cách xử lý:** đặt @Profile trên từng @Bean method nếu chỉ một bean cần điều kiện, hoặc tách configuration class theo nhóm.

## 25. Kế hoạch migration an toàn

Chuyển selector từ profile sang property có thể làm thay đổi bean graph của ứng dụng. Nên thực hiện theo từng bước có thể quan sát và rollback.

### Bước 1 — Ghi lại behavior hiện tại

Với từng profile được hỗ trợ, xác định:

- Bean implementation nào được đăng ký?
- Các dependency nào bắt buộc?
- Property nào được nạp từ file profile-specific?
- Có nhiều profile được phép active cùng lúc không?
- Những test/integration nào đang dựa vào bean hiện tại?

Đây là baseline để so sánh sau chuyển đổi.

### Bước 2 — Chốt vocabulary property

Ví dụ:

~~~text
app.notification.provider = console | smtp
app.notification.enabled = true | false
~~~

Ghi rõ giá trị mặc định, giá trị bắt buộc, trường hợp không hỗ trợ và cách cấp property trong từng môi trường.

### Bước 3 — Viết selector mới và tests

Tạo configuration dùng @ConditionalOnProperty. Kiểm tra từng provider, property thiếu, property sai và feature disabled. Nếu có No-op implementation, test riêng semantics của nó.

### Bước 4 — Đặt property vào profile-specific files

Giữ profile để chọn bộ cấu hình:

- application-local.yml: provider=console.
- application-test.yml: provider=console hoặc fake/recording.
- application-staging.yml: provider=smtp hoặc sandbox.
- application-prod.yml: provider=smtp.

Giá trị thật phụ thuộc deployment contract; ví dụ chỉ minh họa.

### Bước 5 — Chạy integration test cho từng profile

Khởi động context với profile tương ứng và kiểm tra:

- Active profiles.
- Effective provider property.
- Bean type được đăng ký.
- Không có implementation cạnh tranh.
- Các dependencies cần thiết được cung cấp.

### Bước 6 — Gỡ selector cũ

Sau khi property selector thay thế thành công, xóa hoặc ngừng import @Profile bean methods cũ. Không giữ hai cấu hình cùng đăng ký một interface.

### Bước 7 — Triển khai theo môi trường

Rollout local/test trước, sau đó staging. Xác minh provider thật và các external dependencies trước khi rollout production.

### Bước 8 — Theo dõi và rollback

Nếu startup fail hoặc provider không đúng, kiểm tra effective property, source precedence và bean registry. Rollback cần khôi phục cả code selector lẫn cấu hình property tương ứng.

## 26. Checklist cấu hình trước khi chạy ứng dụng

Với mỗi môi trường, có thể trả lời các câu hỏi sau:

| Câu hỏi | Ví dụ kiểm tra |
|---|---|
| Profile nào đang active? | Environment.getActiveProfiles() |
| Provider property có giá trị gì? | app.notification.provider |
| Giá trị đến từ đâu? | application-prod.yml, environment hoặc command-line |
| Có đúng một NotificationSender không? | getBeansOfType(NotificationSender.class) |
| Implementation thực tế là gì? | Bean class/type |
| External client có dependency cần thiết không? | SMTP client/credentials/endpoint |
| Secret được cấp từ đâu? | Secret manager hoặc deployment secret |
| Feature disabled có behavior hợp lệ không? | No-op hoặc consumer không được đăng ký |
| Thay property có cần restart không? | Conditional bean thường cần context startup mới |
| Có test cho nhánh cấu hình này không? | Profile/property context tests |

Trong production, không log credentials để trả lời các câu hỏi này. Có thể log provider, active profiles và trạng thái cấu hình đã được kiểm tra mà không in giá trị bí mật.

## 27. Bài tập thực hành

### Bài tập 1 — Chọn cơ chế

Ứng dụng có ba môi trường local, staging và production. Mỗi môi trường có database URL, log level và endpoint riêng.

**Câu hỏi:** Nên dùng profile hay tạo ba property riêng cho từng thành phần?

**Đáp án định hướng:** Profile phù hợp để chọn một bộ cấu hình theo môi trường. Các giá trị cụ thể vẫn là properties trong file tương ứng.

### Bài tập 2 — Chọn provider độc lập

Production mặc định dùng SMTP nhưng một số deployment cần dùng provider push. Database và các cấu hình khác không đổi.

**Câu hỏi:** Có nên tạo profile prod-smtp và prod-push?

**Đáp án định hướng:** Nếu chỉ provider thay đổi độc lập, property app.notification.provider diễn đạt rõ hơn. Chỉ dùng profile riêng nếu hai lựa chọn đại diện cho những bộ cấu hình môi trường khác nhau.

### Bài tập 3 — Dự đoán bean

Cấu hình:

~~~java
@Bean
@Profile("local")
NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
@Profile("prod")
NotificationSender smtpSender(SmtpClient client) {
    return new SmtpNotificationSender(client);
}
~~~

Process chạy với:

~~~text
SPRING_PROFILES_ACTIVE=local,prod
~~~

**Câu hỏi:** Có bao nhiêu NotificationSender beans có thể được đăng ký?

**Đáp án:** Hai bean methods đều match. Nếu một service inject một NotificationSender không có qualifier/primary, context có thể thất bại do nhiều candidates.

### Bài tập 4 — Dự đoán property condition

Condition:

~~~java
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "provider",
        havingValue = "smtp",
        matchIfMissing = false)
~~~

**Câu hỏi:** Điều gì xảy ra với các giá trị smtp, console, push và property bị thiếu?

**Đáp án định hướng:** Chỉ smtp match. Console, push và missing không match condition này.

### Bài tập 5 — Property bị override

application-prod.yml:

~~~yaml
app:
  notification:
    provider: smtp
~~~

Command line:

~~~bash
java -jar order-api.jar \
  --spring.profiles.active=prod \
  --app.notification.provider=console
~~~

**Câu hỏi:** Provider nào được chọn nếu command-line property có precedence cao hơn?

**Đáp án:** console. Profile prod vẫn active nhưng không bảo đảm provider=smtp.

### Bài tập 6 — Feature disabled

OrderNotificationService có constructor dependency bắt buộc NotificationSender. Khi enabled=false, hai provider beans đều không được đăng ký.

**Câu hỏi:** Vì sao context có thể fail? Có những lựa chọn thiết kế nào?

**Đáp án định hướng:** Service thiếu dependency bắt buộc. Có thể cung cấp No-op nếu “không gửi” hợp lệ, condition hóa cả consumer/service, hoặc giữ service nhưng thiết kế feature state rõ ràng.

### Bài tập 7 — Chọn theo tenant

Một process phục vụ hai tenant, tenant A dùng SMTP server A, tenant B dùng SMTP server B.

**Câu hỏi:** Có nên active profile tenant-a/tenant-b theo từng request?

**Đáp án:** Không. Profile thuộc ApplicationContext. Dùng tenant-aware routing, registry hoặc client factory với cấu hình tenant được quản lý an toàn.

### Bài tập 8 — Viết test

Hãy viết hai ApplicationContextRunner tests:

1. app.notification.provider=console tạo ConsoleNotificationSender.
2. app.notification.provider=smtp tạo SmtpNotificationSender.

**Yêu cầu:** assert context không lỗi, có đúng một NotificationSender và implementation đúng type. Cung cấp SmtpClient fake trong nhánh SMTP.

### Bài tập 9 — Tìm lỗi migration

Sau migration, configuration vẫn có @Profile("local") console bean và @ConditionalOnProperty provider=smtp SMTP bean. Khi local active và provider=smtp, context có hai NotificationSender.

**Câu hỏi:** Nên sửa bằng @Primary hay bỏ một selector?

**Đáp án:** Xác định selector nào là nguồn quyết định chính rồi bỏ/disable selector cũ. @Primary chỉ chọn candidate khi inject, không loại bean thừa.

### Bài tập 10 — Dynamic feature flag

Operations muốn đổi provider mà không restart process.

**Câu hỏi:** Chỉ sửa property app.notification.provider có làm Spring tự thay bean không?

**Đáp án:** Không. @ConditionalOnProperty được đánh giá khi context xử lý bean definitions. Cần dynamic configuration/strategy routing có lifecycle và concurrency contract riêng.

## 28. Nguyên tắc cần ghi nhớ

1. **Profile mô tả nhóm cấu hình/môi trường active.** Dùng để chọn database, endpoint, infrastructure hoặc nhiều beans cần thay đổi đồng bộ.
2. **Property mô tả lựa chọn/giá trị cụ thể.** Dùng cho provider selector, feature flag, timeout, limit và các tham số độc lập.
3. @Profile có thể đặt trên configuration class hoặc từng bean method. Nếu nhiều profile cùng active, nhiều bean methods có thể cùng match.
4. @ConditionalOnProperty nên ghi rõ prefix, name, havingValue và matchIfMissing theo contract.
5. Property không match có thể khiến bean không được đăng ký. Hãy kiểm tra bean graph và fail-fast khi cấu hình sai.
6. No-op implementation chỉ phù hợp khi không thực hiện hành động là behavior nghiệp vụ hợp lệ.
7. Profile-specific YAML có thể cung cấp property cho bean selector. Profile chọn file; property chọn implementation.
8. Command-line/environment variables có thể override file configuration. Luôn kiểm tra effective property thay vì suy luận từ profile.
9. @ConditionalOnProperty không tự hot-swap bean sau startup và không phù hợp để kiểm tra indexed collections.
10. Nếu lựa chọn thay đổi theo request/tenant, dùng strategy/factory/routing; không thay active profile.
11. Khi chuyển selector, gỡ configuration cũ để tránh hai implementation cùng được đăng ký.
12. Kiểm thử từng profile/property branch và kiểm tra đúng một candidate khi service cần một implementation duy nhất.

**Kết luận:** Chọn profile khi cần kích hoạt một bộ cấu hình môi trường, chọn property khi cần điều khiển một capability hoặc implementation độc lập. Trong nhiều ứng dụng, cách rõ ràng nhất là kết hợp cả hai: profile chọn application-local.yml hoặc application-prod.yml, property trong file đó chọn provider qua @ConditionalOnProperty. Business service tiếp tục phụ thuộc interface, còn configuration chịu trách nhiệm đăng ký đúng implementation. Khi migration, cần kiểm soát property precedence, default behavior, các profile cùng active và bean graph; kiểm thử từng nhánh trước khi rollout để tránh thiếu bean hoặc đăng ký trùng implementation.

