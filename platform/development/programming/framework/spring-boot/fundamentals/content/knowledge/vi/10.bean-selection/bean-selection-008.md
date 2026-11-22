# Chọn cách hiện thực bằng profile hoặc thuộc tính cấu hình

Khi một chức năng có nhiều cách triển khai, ứng dụng cần quyết định bean nào sẽ được tạo trong ApplicationContext. Spring Boot cung cấp hai cách thường dùng: **profile** với `@Profile` và **thuộc tính cấu hình** với `@ConditionalOnProperty`.

Cả hai đều quyết định bean có được đăng ký hay không trong lúc Spring tạo ApplicationContext. Điểm khác nhau nằm ở ý nghĩa của điều kiện: profile mô tả ngữ cảnh chạy của ứng dụng, còn thuộc tính cấu hình mô tả lựa chọn cụ thể mà ứng dụng hoặc người vận hành muốn bật.

## 1. Khi nào nên dùng profile?

Profile phù hợp khi tập bean cần dùng thay đổi theo môi trường hoặc ngữ cảnh chạy, chẳng hạn:

- Môi trường local dùng dịch vụ giả lập để phát triển.
- Môi trường test dùng adapter hoặc dữ liệu dành riêng cho kiểm thử.
- Môi trường production kết nối tới dịch vụ thật.

Hãy xem ví dụ một ứng dụng có hai cách gửi thông báo. Khi chạy local, ứng dụng ghi thông báo ra log; khi chạy production, ứng dụng gửi thông báo qua một nhà cung cấp bên ngoài.

Trước tiên, định nghĩa hợp đồng chung:

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

Tạo các cấu hình cung cấp từng cách triển khai:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class NotificationConfiguration {

    @Bean
    @Profile("local")
    NotificationSender logNotificationSender() {
        return (recipient, message) ->
                System.out.printf("To %s: %s%n", recipient, message);
    }

    @Bean
    @Profile("production")
    NotificationSender productionNotificationSender(
            ExternalNotificationClient client) {
        return (recipient, message) ->
                client.send(recipient, message);
    }
}
~~~

Khi profile local đang hoạt động, Spring đăng ký bean từ phương thức logNotificationSender. Khi profile production đang hoạt động, Spring đăng ký bean từ phương thức productionNotificationSender. Những thành phần khác chỉ cần phụ thuộc vào NotificationSender:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ReminderService {

    private final NotificationSender notificationSender;

    public ReminderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public void remind(String recipient) {
        notificationSender.send(recipient, "Your reminder is ready.");
    }
}
~~~

ReminderService không cần biết ứng dụng đang chạy ở local hay production. Spring chọn bean phù hợp trước khi tạo ReminderService và truyền bean đó vào constructor.

### Kích hoạt profile

Có thể kích hoạt profile bằng thuộc tính spring.profiles.active. Ví dụ, trong application.yml:

~~~yaml
spring:
  profiles:
    active: local
~~~

Khi triển khai, nên để môi trường triển khai quyết định profile thay vì cố định profile production trong cấu hình dùng chung. Có thể truyền profile qua tham số dòng lệnh:

~~~bash
java -jar application.jar --spring.profiles.active=production
~~~

Hoặc đặt biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=production
~~~

Spring Boot cũng hỗ trợ tệp cấu hình riêng theo profile. Ví dụ:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
└── application-production.yml
~~~

Khi profile local hoạt động, các giá trị trong application-local.yml được nạp cùng cấu hình chung. Khi profile production hoạt động, application-production.yml được nạp. Cách này giúp tách endpoint, mức log và các giá trị thay đổi theo môi trường ra khỏi cấu hình chung.

Nếu không khai báo profile đang hoạt động, Spring sử dụng profile mặc định có tên default. Có thể chỉ định profile mặc định bằng spring.profiles.default. Ví dụ:

~~~yaml
spring:
  profiles:
    default: local
~~~

Profile mặc định chỉ được dùng khi không có profile nào được kích hoạt rõ ràng. Khi một profile khác được kích hoạt, profile mặc định không tự động được cộng thêm.

### Điều kiện profile

@Profile nhận tên profile hoặc biểu thức profile. Ví dụ:

~~~java
@Bean
@Profile("local | test")
NotificationSender nonProductionSender() {
    return (recipient, message) -> System.out.println(message);
}
~~~

Biểu thức trên khớp khi local hoặc test đang hoạt động. Có thể kết hợp phép AND và NOT:

~~~java
@Bean
@Profile("production & !maintenance")
NotificationSender productionSender() {
    return createProductionSender();
}
~~~

Trong ví dụ này, bean chỉ được đăng ký khi production đang hoạt động và maintenance không hoạt động. Khi dùng biểu thức phức tạp, hãy giữ điều kiện dễ đọc để người vận hành có thể xác định vì sao một bean được chọn.

## 2. Khi nào nên dùng thuộc tính cấu hình?

Thuộc tính cấu hình phù hợp khi người vận hành cần chọn một cách triển khai hoặc bật một tích hợp cụ thể mà không nhất thiết phải thay đổi profile môi trường.

Ví dụ, ứng dụng luôn chạy trong môi trường production nhưng có thể chọn nhà cung cấp thanh toán bằng thuộc tính app.payment.provider. Môi trường vẫn là production; chỉ lựa chọn nhà cung cấp thay đổi.

Spring Boot cung cấp @ConditionalOnProperty trong package org.springframework.boot.autoconfigure.condition. Điều kiện này kiểm tra một thuộc tính trong Environment trước khi đăng ký cấu hình hoặc bean.

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.payment",
            name = "provider",
            havingValue = "sandbox",
            matchIfMissing = true
    )
    PaymentProcessor sandboxPaymentProcessor() {
        return new SandboxPaymentProcessor();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.payment",
            name = "provider",
            havingValue = "stripe"
    )
    PaymentProcessor stripePaymentProcessor(
            StripeClient stripeClient) {
        return new StripePaymentProcessor(stripeClient);
    }
}
~~~

Cấu hình tương ứng có thể đặt trong application.yml:

~~~yaml
app:
  payment:
    provider: sandbox
~~~

Khi provider có giá trị sandbox, bean SandboxPaymentProcessor được đăng ký. Khi provider có giá trị stripe, Spring đăng ký bean StripePaymentProcessor và cung cấp StripeClient qua dependency injection.

Nếu thuộc tính không tồn tại, matchIfMissing = true cho phép điều kiện sandbox khớp. Nếu thuộc tính có giá trị khác sandbox hoặc stripe, cả hai điều kiện đều không khớp; khi đó ứng dụng có thể lỗi lúc tạo bean cần PaymentProcessor vì không có implementation phù hợp. Vì vậy, cần quy định rõ các giá trị được chấp nhận và cung cấp giá trị mặc định có chủ đích.

### Ý nghĩa các thuộc tính của @ConditionalOnProperty

- prefix: phần tiền tố dùng chung của tên thuộc tính. Trong ví dụ, prefix là app.payment.
- name: tên thuộc tính cần kiểm tra sau prefix. Kết hợp hai phần tạo thành app.payment.provider.
- havingValue: giá trị mà thuộc tính phải có để điều kiện khớp. Nên khai báo rõ khi lựa chọn giữa nhiều implementation.
- matchIfMissing: quyết định điều kiện có khớp khi thuộc tính không tồn tại hay không. Giá trị mặc định là false.

Nếu không chỉ định havingValue, điều kiện khớp khi thuộc tính tồn tại và giá trị không phải false (không phân biệt chữ hoa, chữ thường). Với thuộc tính dùng để chọn một implementation, nên dùng havingValue tường minh để tránh một giá trị ngoài dự kiến cũng làm điều kiện khớp.

Thuộc tính có thể đến từ nhiều nguồn cấu hình mà Spring Boot hỗ trợ, chẳng hạn application.yml, tham số dòng lệnh hoặc biến môi trường. Nhờ đó, cùng một gói ứng dụng có thể được cấu hình để chọn implementation khác nhau khi khởi chạy.

Ví dụ, có thể ghi đè lựa chọn bằng biến môi trường:

~~~bash
APP_PAYMENT_PROVIDER=stripe
~~~

Quy tắc đặt tên biến môi trường của Spring Boot chuyển tên thuộc tính dạng chấm thành chữ hoa và dấu gạch dưới. Giá trị cấu hình thực tế vẫn cần được quản lý phù hợp với môi trường triển khai; không nên đưa khóa bí mật của nhà cung cấp thanh toán vào tệp cấu hình được commit.

## 3. So sánh hai cách lựa chọn

| Tiêu chí | @Profile | @ConditionalOnProperty |
|---|---|---|
| Điều kiện | Profile đang hoạt động | Giá trị của thuộc tính cấu hình |
| Ý nghĩa thường gặp | Ngữ cảnh hoặc môi trường chạy | Tùy chọn hoặc tích hợp được chọn |
| Cách kích hoạt | spring.profiles.active | Thuộc tính do ứng dụng định nghĩa |
| Ví dụ | local, test, production | app.payment.provider=stripe |
| Phạm vi | Một nhóm cấu hình theo ngữ cảnh | Một bean hoặc nhóm cấu hình theo giá trị thuộc tính |
| Khi phù hợp | Cấu hình thay đổi theo môi trường | Lựa chọn thay đổi độc lập với môi trường |

Không có quy tắc bắt buộc rằng mọi lựa chọn phải dùng một trong hai cách. Hãy đặt câu hỏi về ý nghĩa của điều kiện:

- Nếu câu hỏi là “Ứng dụng đang chạy trong ngữ cảnh nào?”, profile thường là lựa chọn rõ ràng.
- Nếu câu hỏi là “Ứng dụng cần dùng nhà cung cấp hoặc implementation nào?”, thuộc tính cấu hình thường phù hợp hơn.

Ví dụ, production có thể luôn là profile đang hoạt động, trong khi app.payment.provider cho phép chọn stripe hoặc một nhà cung cấp khác. Như vậy, lựa chọn nhà cung cấp không cần tạo thêm profile production-stripe, production-provider-b, test-stripe và nhiều profile kết hợp tương tự.

## 4. Có thể kết hợp profile và thuộc tính cấu hình không?

Có thể đặt nhiều điều kiện trên cùng một phương thức @Bean hoặc lớp cấu hình. Khi kết hợp, tất cả điều kiện phải thỏa mãn thì bean mới được đăng ký.

~~~java
@Bean
@Profile("production")
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
PaymentProcessor productionPaymentProcessor(
        StripeClient stripeClient) {
    return new StripePaymentProcessor(stripeClient);
}
~~~

Bean trên chỉ được tạo khi profile production hoạt động và app.payment.enabled có giá trị true. Cách kết hợp này hữu ích khi một tích hợp chỉ được phép xuất hiện trong một số môi trường và còn cần được bật bằng một thuộc tính riêng.

Tuy nhiên, mỗi điều kiện bổ sung làm tăng số trường hợp cấu hình cần quản lý. Chỉ kết hợp khi hai điều kiện thể hiện hai yêu cầu độc lập và có ý nghĩa rõ ràng.

## 5. Những lỗi thường gặp khi chọn bean

### Hai implementation cùng được đăng ký

Giả sử hai bean cùng triển khai PaymentProcessor và cả hai điều kiện đều khớp. Khi một service yêu cầu PaymentProcessor, Spring không thể tự đoán bean nào cần tiêm và có thể báo NoUniqueBeanDefinitionException.

Để tránh lỗi này:

- Thiết kế điều kiện loại trừ lẫn nhau nếu chỉ được phép có một implementation.
- Kiểm tra các profile được kích hoạt đồng thời.
- Kiểm tra giá trị thuộc tính và điều kiện mặc định.
- Chỉ dùng @Primary hoặc @Qualifier khi ứng dụng thực sự cần nhiều bean cùng tồn tại và có quy tắc chọn bean rõ ràng.

@Primary và @Qualifier giải quyết việc chọn giữa nhiều bean đã được đăng ký. Chúng không thay thế điều kiện đăng ký bean khi mục tiêu là chỉ tạo một implementation theo cấu hình.

### Không có implementation nào được đăng ký

Nếu thuộc tính không khớp bất kỳ havingValue nào, hoặc profile cần thiết không hoạt động, Spring có thể không đăng ký bean. Một service yêu cầu kiểu đó qua constructor sẽ không được tạo và quá trình khởi động thất bại.

Khi gặp lỗi này, hãy kiểm tra:

1. Profile nào đang hoạt động tại thời điểm khởi động.
2. Thuộc tính có tồn tại trong Environment hay không.
3. Giá trị thực tế có khớp havingValue hay không.
4. matchIfMissing có đúng với chính sách mặc định hay không.
5. Có cấu hình nào ở nguồn ưu tiên cao hơn ghi đè giá trị dự kiến hay không.

Không nên bật matchIfMissing một cách tùy tiện để che lỗi cấu hình. Chỉ bật khi implementation đó thực sự là lựa chọn mặc định an toàn và được dự định.

### Nhầm lẫn giữa profile và thuộc tính bật/tắt

Một profile như production mô tả ngữ cảnh chạy. Một thuộc tính như app.payment.enabled mô tả lựa chọn của ứng dụng trong ngữ cảnh đó. Nếu dùng profile cho mọi công tắc nhỏ, số profile có thể tăng nhanh và khó quản lý.

Ngược lại, nếu dùng hàng loạt thuộc tính để mô phỏng toàn bộ môi trường, cấu hình sẽ khó hiểu vì không còn một tên profile thể hiện rõ ngữ cảnh đang chạy.

Hãy giữ profile cho các nhóm cấu hình gắn với môi trường; dùng thuộc tính cho những lựa chọn độc lập như nhà cung cấp, chế độ tích hợp hoặc khả năng bật/tắt một chức năng.

### Mong đợi bean tự đổi khi thuộc tính thay đổi

Các điều kiện này được đánh giá trong quá trình Spring xây dựng ApplicationContext. Thay đổi một giá trị trong tệp cấu hình sau khi ứng dụng đã khởi động không tự động thay thế bean đang được sử dụng. Muốn lựa chọn khác có hiệu lực, cần khởi động lại ApplicationContext hoặc ứng dụng theo cơ chế triển khai phù hợp.

## 6. Cách kiểm tra lựa chọn trước khi triển khai

Khi thêm một implementation mới, hãy kiểm tra các tình huống cấu hình dự kiến bằng cách khởi động ứng dụng với từng profile hoặc giá trị thuộc tính tương ứng. Có thể ghi log tên implementation được chọn ở giai đoạn khởi động hoặc kiểm tra bean trong test ApplicationContext.

Ví dụ, chạy ứng dụng với profile local:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

Chạy với profile production và chọn Stripe:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=production --app.payment.provider=stripe'
~~~

Trong môi trường production thật, các thông tin kết nối và bí mật phải được cấp từ cơ chế cấu hình bảo mật của môi trường. Ví dụ dòng lệnh trên minh họa cách truyền lựa chọn bean, không phải hướng dẫn lưu hoặc công khai thông tin xác thực.

Một bộ trường hợp tối thiểu nên bao gồm:

| Trường hợp | Cấu hình | Kết quả mong đợi |
|---|---|---|
| Profile local | spring.profiles.active=local | Bean dành cho local được đăng ký |
| Profile production | spring.profiles.active=production | Bean dành cho production được đăng ký |
| Thuộc tính sandbox | app.payment.provider=sandbox | SandboxPaymentProcessor được đăng ký |
| Thuộc tính stripe | app.payment.provider=stripe | StripePaymentProcessor được đăng ký |
| Thuộc tính thiếu | Không khai báo app.payment.provider | Áp dụng đúng chính sách matchIfMissing |
| Giá trị không hợp lệ | app.payment.provider=unknown | Không âm thầm chọn nhầm implementation |

Khi có nhiều điều kiện kết hợp, cần kiểm tra cả trường hợp tất cả điều kiện cùng khớp và trường hợp chỉ một điều kiện không khớp. Điều này giúp phát hiện sớm tình huống không có bean hoặc có nhiều bean cùng được đăng ký.

## 7. Quy trình chọn cách hiện thực

Khi một interface có nhiều implementation, có thể thực hiện lần lượt:

1. Xác định các implementation và hợp đồng chung mà service sẽ phụ thuộc vào.
2. Xác định điều kiện lựa chọn có đại diện cho môi trường chạy hay một tùy chọn cấu hình.
3. Dùng @Profile nếu implementation phụ thuộc vào profile; dùng @ConditionalOnProperty nếu implementation phụ thuộc vào giá trị thuộc tính.
4. Đảm bảo mỗi cấu hình hợp lệ đăng ký đúng số bean mà các thành phần phụ thuộc cần.
5. Xác định hành vi khi thiếu thuộc tính hoặc khi nhận giá trị không hợp lệ.
6. Khởi động ứng dụng với các cấu hình đại diện và kiểm tra implementation được đăng ký.

Khi service chỉ phụ thuộc vào interface, việc chọn bean được tập trung ở cấu hình Spring. Nhờ đó, service không phải tự đọc profile, kiểm tra thuộc tính hoặc chứa nhiều nhánh điều kiện để quyết định cách gọi implementation. Cấu hình chịu trách nhiệm chọn thành phần phù hợp; service tập trung vào nghiệp vụ của nó.

