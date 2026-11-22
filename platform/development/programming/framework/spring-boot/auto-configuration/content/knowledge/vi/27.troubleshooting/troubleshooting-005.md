# Bean mặc định không xuất hiện vì điều kiện thiếu bean đã không còn thỏa mãn

> **Mục tiêu:** Chẩn đoán vì sao bean mặc định của Spring Boot auto-configuration không được đăng ký khi `@ConditionalOnMissingBean` không còn match. Bài học tập trung vào việc đọc Condition Evaluation Report, tìm bean definition gây back-off, kiểm tra type/name, kiểu trả về của `@Bean` method, thứ tự auto-configuration, context hierarchy và kiểm thử bằng `ApplicationContextRunner`.

Nội dung dùng Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+, JUnit Jupiter và AssertJ. Tình huống cốt lõi là **Spring đã nhìn thấy một bean phù hợp**, nên default bean nhường chỗ. Đây thường là hành vi override đúng thiết kế, nhưng cũng có thể do một definition được đăng ký ngoài dự kiến, type metadata chưa rõ hoặc ordering sai.

## 1. Condition thực sự quyết định điều gì?

`@ConditionalOnMissingBean` là bean condition của Spring Boot. Nó chỉ match khi BeanFactory chưa chứa bean đáp ứng các tiêu chí được khai báo. Nếu tìm thấy bean phù hợp, condition không match và bean mặc định được bảo vệ bởi annotation sẽ không được đăng ký.

~~~java
@AutoConfiguration
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Luồng quyết định:

~~~text
Spring xử lý auto-configuration
              |
              v
Đánh giá @ConditionalOnMissingBean(PaymentGateway.class)
              |
       +------+------+
       |             |
       v             v
Không tìm thấy    Đã tìm thấy bean
bean phù hợp     phù hợp
       |             |
       v             v
MATCH            NO MATCH
       |             |
       v             v
Đăng ký default  Bỏ qua default bean
bean definition  definition
~~~

Điều kiện này cho phép ứng dụng thay thế implementation mặc định bằng bean của mình. Vì thế, default bean biến mất sau khi ứng dụng thêm một bean cùng contract thường là hành vi mong đợi.

Phân biệt ba trạng thái:

- **Không có bean definition:** condition có thể match và default definition được đăng ký.
- **Có definition nhưng instance chưa tạo:** condition vẫn có thể thấy definition; bean lazy vẫn có thể làm default back-off.
- **Instance đã được tạo:** đây là giai đoạn sau. Condition không cần gọi constructor hay lấy instance để quyết định.

`@ConditionalOnMissingBean` không bảo đảm ứng dụng luôn có đúng một bean. Nó chỉ quyết định có đăng ký thêm default hay không. Nếu đã có một hoặc nhiều bean phù hợp, auto-configuration nhường quyền đăng ký default.

## 2. Xác định điều kiện đang kiểm tra type, name hay annotation

Khi đặt trên `@Bean` method, nếu không chỉ định `value`, `type` hoặc `name`, Spring Boot mặc định lấy kiểu trả về khai báo của method làm type cần kiểm tra.

~~~java
@Bean
@ConditionalOnMissingBean
PaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Trong ví dụ này, target type mặc định là `PaymentGateway`. Một bean khác implement interface đó có thể khiến method mặc định back-off.

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `value` | Các bean type được chỉ định bằng Class |
| `type` | Các bean type được chỉ định bằng tên class dạng String |
| `name` | Các bean name cần kiểm tra |
| `annotation` | Các bean được đánh dấu bằng annotation |
| `ignored` | Các type được bỏ qua khi xác định bean phù hợp |
| `ignoredType` | Tên type được bỏ qua |
| `search` | Phạm vi tìm kiếm trong context hierarchy |
| `parameterizedContainer` | Container có generic parameter chứa type cần kiểm tra |

Khi có nhiều tiêu chí, condition chỉ match nếu các yêu cầu được khai báo đều vắng mặt. Các tiêu chí không nhất thiết phải được đáp ứng bởi cùng một bean. Chỉ cần tìm thấy bean cho một yêu cầu cần kiểm tra thì condition có thể không match.

### 2.1. Kiểm tra theo type khác kiểm tra theo name

Theo type:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Một bean tên `customGateway` nhưng implement `PaymentGateway` vẫn khiến condition không match.

Theo name:

~~~java
@Bean
@ConditionalOnMissingBean(name = "customPaymentGateway")
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Ở đây condition kiểm tra tên `customPaymentGateway`. Một bean cùng type nhưng tên khác không tự động thỏa điều kiện kiểm tra name.

Chọn tiêu chí theo contract của starter:

- Muốn ứng dụng thay thế implementation bằng bất kỳ bean cùng abstraction nào: kiểm tra type.
- Muốn tránh đăng ký trùng một bean name cụ thể: kiểm tra name.
- Muốn áp dụng theo marker annotation: dùng `annotation`.

Đừng thêm type và name cùng lúc nếu contract không cần cả hai. Mỗi thuộc tính đều thay đổi tập bean có thể khiến default back-off.

### 2.2. Bean lazy và primary vẫn là bean hiện hữu

~~~java
@Bean
@Lazy
CustomPaymentGateway customPaymentGateway() {
    return new CustomPaymentGateway();
}
~~~

`@Lazy` trì hoãn tạo instance, không xóa bean definition. Nếu definition có type phù hợp đã được xử lý, condition vẫn có thể thấy nó.

Tương tự, `@Primary` ảnh hưởng lựa chọn candidate khi inject nhiều bean; nó không làm bean biến mất khỏi phép kiểm tra tồn tại. Một bean `@Primary` vẫn có thể khiến default back-off.

## 3. Vì sao thứ tự xử lý bean definition quan trọng?

Spring đánh giá bean condition trong quá trình xử lý configuration class và đăng ký bean definition. Condition chỉ có thể dựa vào các definition đã được xử lý tại thời điểm đó.

- Bean definition do người dùng khai báo thường được xử lý trước auto-configuration.
- Bean do auto-configuration khác cung cấp chỉ được nhìn thấy nếu definition của nó đã được xử lý trước.
- Một bean được đăng ký sau đó không thể khiến condition trước đó tự đánh giá lại.

Đây là lý do Spring Boot khuyến nghị dùng `@ConditionalOnBean` và `@ConditionalOnMissingBean` chủ yếu trên auto-configuration. Auto-configuration được áp dụng sau các bean definition do người dùng khai báo, giúp người dùng override default ổn định.

### 3.1. Provider và fallback là hai auto-configuration khác nhau

Giả sử một auto-configuration cung cấp transport chính và cấu hình khác cung cấp transport dự phòng.

~~~java
@AutoConfiguration
public class PrimaryTransportAutoConfiguration {

    @Bean
    PrimaryTransport primaryTransport() {
        return new PrimaryTransport();
    }
}
~~~

Cấu hình fallback:

~~~java
@AutoConfiguration(after = PrimaryTransportAutoConfiguration.class)
public class FallbackTransportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Transport.class)
    FallbackTransport fallbackTransport() {
        return new FallbackTransport();
    }
}
~~~

`after` bảo đảm provider được áp dụng trước fallback. Khi condition của `fallbackTransport` được đánh giá, bean definition `PrimaryTransport` đã có thể được nhìn thấy qua type `Transport`, nên fallback không được đăng ký.

Không dùng `@DependsOn` để sửa thứ tự này. `@DependsOn` điều khiển dependency/lifecycle của bean instance; nó không thay thế thứ tự xử lý auto-configuration và bean definitions. Dùng `@AutoConfiguration(after = ...)` hoặc `@AutoConfigureAfter` cho quan hệ giữa các auto-configuration.

### 3.2. Không đặt bean condition tùy tiện trên user configuration

Một `@Configuration` do ứng dụng khai báo có thể được xử lý trước bean definition mà nó đang chờ từ auto-configuration khác. Nếu đặt `@ConditionalOnMissingBean` trên cấu hình người dùng, kết quả có thể phụ thuộc thứ tự scan/import.

Dùng bean condition chủ yếu trong auto-configuration của thư viện. Nếu cần bật/tắt cấu hình người dùng, cân nhắc `@ConditionalOnProperty` hoặc `@Profile` với ý nghĩa rõ ràng hơn.

## 4. Kiểm tra kiểu trả về của @Bean method

Một lỗi khó thấy là method trả về kiểu quá tổng quát:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
Object paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Method trả về `Object` làm metadata type của bean definition kém cụ thể. Spring Boot cần dựa vào type information có thể suy ra từ method signature; không nên dựa vào việc gọi method để lấy instance rồi mới suy ra implementation.

Khai báo type thể hiện contract thật:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Hoặc để condition mặc định dựa trên interface:

~~~java
@Bean
@ConditionalOnMissingBean
PaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Hai cách thể hiện contract khác nhau:

- `@ConditionalOnMissingBean(PaymentGateway.class)` kiểm tra abstraction được chỉ định rõ.
- `@ConditionalOnMissingBean` không có `value`, `type` hoặc `name` sử dụng kiểu trả về khai báo của method.

Spring Boot khuyến nghị cung cấp càng nhiều type information càng tốt trong return type của `@Bean` method. Khi chẩn đoán, kiểm tra:

1. Method trả về interface hay concrete class?
2. Có dùng `Object`, `FactoryBean` hoặc generic wrapper làm type không rõ không?
3. Condition kiểm tra đúng interface mà user bean implement chưa?
4. Thuộc tính `type` dạng String có sai package hoặc class name không?

Không đổi mọi method sang concrete class một cách máy móc. Chọn return type và condition target theo API mà starter muốn công bố.

## 5. Context hierarchy có thể khiến bean ở parent chặn default

Thuộc tính `search` quyết định condition có tìm bean trong context cha hay không. Mặc định là `SearchStrategy.ALL`, tức tìm trong toàn bộ hierarchy.

| SearchStrategy | Phạm vi |
| --- | --- |
| `ALL` | Context hiện tại và toàn bộ parent hierarchy |
| `CURRENT` | Chỉ context hiện tại |
| `ANCESTORS` | Chỉ các context cha, không gồm context hiện tại |

Ví dụ chỉ xét context hiện tại:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = PaymentGateway.class,
        search = SearchStrategy.CURRENT)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Dùng `CURRENT` khi contract thật sự yêu cầu child context có default riêng dù parent có bean cùng type. Không dùng nó chỉ để ép default xuất hiện trở lại; bean ở parent có thể là override có chủ đích.

Khi điều tra, xác định:

1. Ứng dụng có parent context không?
2. Bean phù hợp nằm trong context hiện tại hay parent?
3. Condition dùng `ALL`, `CURRENT` hay `ANCESTORS`?
4. Bỏ qua parent có phá vỡ kỳ vọng chia sẻ bean giữa root context và child web context không?

## 6. Những nguồn bean definition có thể làm condition không match

| Nguồn | Ví dụ | Điều cần kiểm tra |
| --- | --- | --- |
| User configuration | `@Bean PaymentGateway customGateway()` | Bean type và condition của cấu hình |
| Component scan | `@Component` hoặc `@Service` implement interface | Package scan có phát hiện component không |
| Auto-configuration khác | Provider auto-configuration | Ordering giữa hai cấu hình |
| Import trực tiếp | `@Import(CustomGatewayConfiguration.class)` | Cấu hình import có được xử lý không |
| Parent context | Bean khai báo ở root context | Thuộc tính `search` |
| Lazy bean | `@Lazy @Bean` | Definition vẫn tồn tại dù instance chưa tạo |
| Factory method | `@Bean` trả implementation hoặc interface | Kiểu trả về có đủ thông tin không |
| Test configuration | `@TestConfiguration` hoặc `withBean` | Test có vô tình cung cấp bean thay thế không |

Các điểm dễ nhầm:

- `@Primary` không làm bean biến mất khỏi phép kiểm tra tồn tại.
- `@Lazy` trì hoãn instance, không xóa definition.
- Bean được khai báo nhưng condition riêng của nó không match sẽ không tạo definition để chặn default.
- Bean ở parent được tính khi `search = ALL`.
- Bean từ auto-configuration khác có thể đã được đăng ký trước khi fallback condition chạy.

Nếu nhiều bean cùng match type, condition vẫn có thể back-off. `@ConditionalOnMissingBean` không phải công cụ chọn một candidate duy nhất; việc inject một hay nhiều bean là bài toán khác.

## 7. Đọc Condition Evaluation Report để tìm nguyên nhân

Cách nhanh nhất để biết default bean bị bỏ qua vì lý do nào là đọc Condition Evaluation Report.

Chạy ứng dụng với debug:

~~~bash
java -jar target/application.jar --debug
~~~

Tìm tên auto-configuration và method bean đang thiếu. `OnBeanCondition` sẽ ghi lý do match/no-match. Một thông báo minh họa khi tìm thấy bean phù hợp:

~~~text
PaymentGatewayAutoConfiguration#paymentGateway:
@ConditionalOnMissingBean (types: com.acme.payment.PaymentGateway;
SearchStrategy: all) found beans of type 'PaymentGateway'
~~~

Đây là ví dụ diễn giải, không phải chuỗi log cố định cho mọi bản Boot. Hãy đọc type, search strategy và tên bean thực tế mà report trả về.

### 7.1. In report trong ApplicationContextRunner test

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(PaymentGatewayAutoConfiguration.class))
        .run(context -> {
            // Assertions.
        });
~~~

Import:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

Listener giúp xem condition outcome trong test mà không cần khởi động toàn bộ ứng dụng.

### 7.2. Actuator conditions endpoint

Nếu ứng dụng đã dùng Actuator và endpoint được expose/cho phép truy cập, có thể xem:

~~~text
GET /actuator/conditions
~~~

Endpoint `conditions` trả về positive và negative matches theo context. Tìm key dạng `AutoConfigurationClass#beanMethod` để biết condition của bean nào không match.

Không expose endpoint chẩn đoán rộng rãi trong production nếu chưa bảo vệ truy cập. Khi debug cục bộ, `--debug` hoặc test listener thường là đủ.

## 8. Quy trình chẩn đoán

1. **Xác nhận bean mong đợi.** Ghi lại bean name, type/interface và auto-configuration class chứa method.
2. **Xác nhận configuration được nạp.** Kiểm tra imports/discovery, exclusions và condition cấp class.
3. **Đọc condition report.** Tìm `OnBeanCondition` của method và xem type/name/annotation/search strategy.
4. **Tìm bean gây no-match.** Kiểm tra user configuration, component scan, imported config, auto-configuration khác, test configuration và parent context.
5. **Kiểm tra return type.** Xem method mặc định khai báo kiểu gì và target type có đúng không.
6. **Kiểm tra ordering.** Nếu bean gây back-off đến từ auto-configuration khác, đảm bảo fallback chạy sau provider.
7. **Kiểm tra search strategy.** Xác nhận bean ở parent có nên được tính hay không.
8. **Kiểm tra các condition còn lại.** Property, classpath, resource hoặc web condition ở class/method cũng có thể ngăn bean đăng ký.
9. **Viết test tái hiện.** Dùng `ApplicationContextRunner` với từng tổ hợp user bean và auto-configuration.

Đừng xóa bean đang làm condition fail chỉ để ép default xuất hiện. Trước tiên xác định bean đó là override có chủ đích, dependency từ module khác hay definition bị đăng ký nhầm.

## 9. Ví dụ hoàn chỉnh: default PaymentGateway tự back-off

### 9.1. Contract và implementation

**`src/main/java/com/acme/payment/PaymentGateway.java`**

~~~java
package com.acme.payment;

public interface PaymentGateway {
    String provider();
}
~~~

**`src/main/java/com/acme/payment/DefaultPaymentGateway.java`**

~~~java
package com.acme.payment;

public final class DefaultPaymentGateway implements PaymentGateway {

    @Override
    public String provider() {
        return "default";
    }
}
~~~

**`src/main/java/com/acme/payment/CustomPaymentGateway.java`**

~~~java
package com.acme.payment;

public final class CustomPaymentGateway implements PaymentGateway {

    @Override
    public String provider() {
        return "custom";
    }
}
~~~

### 9.2. Auto-configuration

**`src/main/java/com/acme/payment/autoconfigure/PaymentGatewayAutoConfiguration.java`**

~~~java
package com.acme.payment.autoconfigure;

import com.acme.payment.DefaultPaymentGateway;
import com.acme.payment.PaymentGateway;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    DefaultPaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Return type là concrete class, trong khi condition kiểm tra interface `PaymentGateway`. Bean definition của bất kỳ implementation phù hợp nào đã được xử lý trước đều có thể khiến default method back-off.

### 9.3. Đăng ký auto-configuration

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.acme.payment.autoconfigure.PaymentGatewayAutoConfiguration
~~~

### 9.4. Kiểm thử default và user override

**`src/test/java/com/acme/payment/autoconfigure/PaymentGatewayAutoConfigurationTests.java`**

~~~java
package com.acme.payment.autoconfigure;

import com.acme.payment.CustomPaymentGateway;
import com.acme.payment.PaymentGateway;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentGatewayAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    PaymentGatewayAutoConfiguration.class));

    @Test
    void createsDefaultGatewayWhenNoUserGatewayExists() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(PaymentGateway.class);
            assertThat(context).hasBean("paymentGateway");
            assertThat(context.getBean(PaymentGateway.class).provider())
                    .isEqualTo("default");
        });
    }

    @Test
    void backsOffWhenUserProvidesGateway() {
        runner.withUserConfiguration(UserGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                    assertThat(context).hasBean("customPaymentGateway");
                    assertThat(context).doesNotHaveBean("paymentGateway");
                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("custom");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        CustomPaymentGateway customPaymentGateway() {
            return new CustomPaymentGateway();
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Hai test chứng minh hai trạng thái: không có user bean thì default được đăng ký; có user bean cùng contract thì default back-off và user bean được dùng.

### 9.5. Kiểm thử ordering giữa hai auto-configuration

~~~java
interface Transport {
}

final class PrimaryTransport implements Transport {
}

final class FallbackTransport implements Transport {
}

@AutoConfiguration
class PrimaryTransportAutoConfiguration {

    @Bean
    PrimaryTransport primaryTransport() {
        return new PrimaryTransport();
    }
}

@AutoConfiguration(after = PrimaryTransportAutoConfiguration.class)
class FallbackTransportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Transport.class)
    FallbackTransport fallbackTransport() {
        return new FallbackTransport();
    }
}
~~~

Test:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                PrimaryTransportAutoConfiguration.class,
                FallbackTransportAutoConfiguration.class))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(Transport.class);
            assertThat(context).hasBean("primaryTransport");
            assertThat(context).doesNotHaveBean("fallbackTransport");
        });
~~~

`after` bảo đảm provider được áp dụng trước fallback. Condition nhìn thấy provider definition nên không đăng ký fallback.

### 9.6. Dependency và lệnh chạy

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
~~~

~~~bash
./gradlew test --tests com.acme.payment.autoconfigure.PaymentGatewayAutoConfigurationTests
~~~

Với Maven:

~~~bash
mvn -Dtest=PaymentGatewayAutoConfigurationTests test
~~~

Kết quả trên là output mong đợi khi test chạy thành công; dùng build thực tế của module để xác nhận.

## 10. Các thuộc tính nâng cao

### 10.1. Search strategy

Ví dụ chỉ xét context hiện tại:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = PaymentGateway.class,
        search = SearchStrategy.CURRENT)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Dùng khi child context cần có default riêng dù parent có bean cùng type. Nếu ứng dụng mong muốn child kế thừa gateway từ parent, giữ mặc định `ALL`.

### 10.2. Ignored types

`ignored` và `ignoredType` cho phép bỏ qua một số type khi xác định bean phù hợp:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = PaymentGateway.class,
        ignored = LegacyPaymentGatewayAdapter.class)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Chỉ dùng khi contract thật sự yêu cầu một adapter/compatibility bean không được xem như implementation thay thế. Nếu dùng `ignored` chỉ để làm condition match, có thể che giấu một bean đang tồn tại và tạo hai implementation cùng lúc.

`ignoredType` nhận tên class dạng String; nó hữu ích khi không muốn tạo tham chiếu class trực tiếp trong annotation.

### 10.3. Parameterized container

Khi cần kiểm tra một type nằm bên trong generic container, `parameterizedContainer` cho phép khai báo container type:

~~~java
@ConditionalOnMissingBean(
        value = PaymentGateway.class,
        parameterizedContainer = GatewayRegistration.class)
~~~

Chỉ dùng khi thư viện thực sự dùng `GatewayRegistration<PaymentGateway>` như một cách đăng ký provider. Hãy xác định rõ cấu trúc generic cần nhận diện.

## 11. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Default biến mất sau khi thêm custom `@Bean` | User bean cùng type làm condition no-match | Xác nhận override có chủ đích; kiểm tra report |
| Default biến mất dù custom bean đang `@Lazy` | Definition đã tồn tại dù instance chưa tạo | Kiểm tra definition, không chỉ singleton instances |
| Default biến mất do bean ở parent | `search` mặc định là `ALL` | Xác minh hierarchy; cân nhắc `CURRENT` nếu đúng contract |
| Default vẫn xuất hiện dù provider auto-config có bean | Fallback được xử lý trước provider | Thêm `after` hoặc `@AutoConfigureAfter` |
| Condition kiểm tra sai type | Return type quá tổng quát hoặc target sai | Khai báo type rõ ràng và kiểm tra signature |
| Bean bị back-off dù có nhiều implementation | Condition chỉ cần tìm thấy bean phù hợp | Kiểm tra type/name/annotation criteria |
| Report không có `OnBeanCondition` mong đợi | Configuration chưa discover hoặc condition khác/exclusion chặn | Kiểm tra imports, exclusions và class-level conditions |
| Test pass nhưng ứng dụng thực tế khác | Test thiếu user config hoặc parent context tương đương | Dựng context phản ánh đúng discovery và hierarchy |
| Dùng `@Primary` nhưng default vẫn back-off | `@Primary` không loại bean khỏi phép kiểm tra | Phân biệt bean existence với injection selection |
| Dùng `ignored` để ép default xuất hiện | Condition bỏ qua bean vốn là override hợp lệ | Sửa contract hoặc loại bean đăng ký nhầm |

## 12. Checklist review

- [ ] Đã xác định đúng auto-configuration class và `@Bean` method.
- [ ] Đã đọc Condition Evaluation Report cho `OnBeanCondition`.
- [ ] Đã xác định type, name hoặc annotation mà `@ConditionalOnMissingBean` kiểm tra.
- [ ] Đã tìm bean definition gây back-off và nguồn đăng ký.
- [ ] Đã kiểm tra bean `@Lazy`, test configuration và component scan.
- [ ] Đã kiểm tra return type và type metadata.
- [ ] Đã xác nhận ordering nếu provider đến từ auto-configuration khác.
- [ ] Đã kiểm tra `search` và parent context.
- [ ] Đã kiểm tra các condition khác ở class và method.
- [ ] Đã viết test cho cả default và override.
- [ ] Không xóa provider hợp lệ hoặc bỏ qua bean type ngoài ý muốn.

## 13. Câu hỏi tự kiểm tra

1. `@ConditionalOnMissingBean` match khi nào?  
   **Đáp án:** Khi BeanFactory không chứa bean đáp ứng các tiêu chí type, name hoặc annotation được chỉ định.

2. Vì sao thêm user bean cùng interface khiến default biến mất?  
   **Đáp án:** User bean đã tồn tại trong BeanFactory, nên condition không match và default method không đăng ký bean definition.

3. Bean `@Lazy` có làm default back-off không?  
   **Đáp án:** Có thể. Lazy trì hoãn instance, nhưng definition vẫn tồn tại và có thể được condition nhìn thấy.

4. Nếu không khai báo type, condition trên `@Bean` method kiểm tra type nào?  
   **Đáp án:** Kiểu trả về khai báo của method khi `value`, `type` và `name` không được chỉ định.

5. Vì sao cần `@AutoConfiguration(after = ...)`?  
   **Đáp án:** Để provider được xử lý trước fallback, giúp condition nhìn thấy bean definition của provider.

6. `SearchStrategy.ALL` có nghĩa gì?  
   **Đáp án:** Tìm trong context hiện tại và toàn bộ parent hierarchy.

7. `@Primary` có làm bean không còn được tính là existing bean không?  
   **Đáp án:** Không. Nó ảnh hưởng chọn candidate khi inject, không loại bean khỏi phép kiểm tra tồn tại.

8. Vì sao condition report hữu ích?  
   **Đáp án:** Nó cho biết condition nào match/no-match và lý do, giúp xác định bean hoặc tiêu chí làm default back-off.

9. Có nên đặt `@ConditionalOnMissingBean` trên mọi user `@Configuration` không?  
   **Đáp án:** Không nên. Spring Boot khuyến nghị dùng bean conditions chủ yếu trong auto-configuration vì thứ tự user definitions phù hợp hơn.

10. Nếu auto-configuration khác cung cấp bean sau fallback, condition fallback có tự đánh giá lại không?  
    **Đáp án:** Không. Condition dựa trên các definition đã xử lý tại thời điểm đánh giá; cần ordering đúng.

## Tài liệu chính thức

- [Spring Boot 3.3.13 — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): tiêu chí type/name/annotation, return type mặc định, ignored types và search strategy.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, thứ tự xử lý definition, kiểu trả về `@Bean` và kiểm thử back-off.
- [Spring Boot 3.3.13 — ConditionEvaluationReport API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): API lưu condition outcomes để reporting.
- [Spring Boot 3.3.13 — ConditionEvaluationReportLoggingListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): initializer ghi condition report vào log.
- [Spring Boot 3.3.13 — Conditions Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): report positive/negative matches qua `/actuator/conditions`.
- [Spring Boot 3.3.13 — SearchStrategy API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html): ý nghĩa `ALL`, `CURRENT` và `ANCESTORS`.

**Ghi nhớ:** Default bean biến mất khi `@ConditionalOnMissingBean` nhìn thấy một bean definition phù hợp tại thời điểm condition được đánh giá. Hãy đọc condition report, xác định type/name/search scope, kiểm tra return type và ordering, sau đó viết test cho cả default lẫn override. Đây là cơ chế back-off giúp auto-configuration có thể tùy biến; chẩn đoán đúng sẽ cho biết bean hiện hữu là override có chủ đích hay definition được đăng ký ngoài dự kiến.
