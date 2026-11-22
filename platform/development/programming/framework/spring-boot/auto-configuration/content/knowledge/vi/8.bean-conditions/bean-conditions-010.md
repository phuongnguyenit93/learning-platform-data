# @ConditionalOnSingleCandidate: khi có một bean ứng viên hoặc một bean @Primary

## 1. Mục tiêu và ý nghĩa

Trong Spring Boot Auto-configuration, có những bean phụ trợ chỉ nên được tạo khi Spring có thể chọn **một bean duy nhất theo kiểu dữ liệu** để tiêm vào chúng. Annotation **@ConditionalOnSingleCandidate** trong gói **org.springframework.boot.autoconfigure.condition** giải quyết tình huống này.

Điều kiện khớp (match) khi **BeanFactory đã biết ít nhất một bean ứng viên phù hợp với kiểu được chỉ định** và có thể xác định một ứng viên duy nhất:

- Chỉ có **một** bean ứng viên hợp lệ của kiểu đó: **match**.
- Có **nhiều** bean ứng viên hợp lệ, nhưng **đúng một bean được đánh dấu @Primary**: **match**.
- Không có ứng viên, hoặc có nhiều ứng viên mà không thể xác định duy nhất: **không match**.

Điểm then chốt: "single candidate" nói về **khả năng chọn một bean để autowire**, không nhất thiết là trong ApplicationContext chỉ tồn tại đúng một instance thuộc kiểu đó. Vì vậy, hai implementation có thể cùng tồn tại mà điều kiện vẫn khớp nếu chỉ một implementation là @Primary.

Annotation này bản chất là một điều kiện **@Conditional** được đánh giá bởi **OnBeanCondition**. Nó thường được đặt trên phương thức **@Bean** hoặc lớp cấu hình tự động (**@AutoConfiguration**), không phải công tắc bật/tắt tùy thời điểm sau khi ứng dụng đã khởi động.

## 2. Bảng quyết định: số ứng viên và @Primary

Giả sử điều kiện đang kiểm tra kiểu **PaymentGateway** và các bean được liệt kê đều là ứng viên hợp lệ.

| Bean PaymentGateway hiện diện khi điều kiện được đánh giá | Kết quả | Lý do |
| --- | --- | --- |
| Không có bean nào | Không match | Không tồn tại ứng viên để tiêm |
| Chỉ có gatewayA | Match | gatewayA là ứng viên duy nhất |
| gatewayA và gatewayB, không bean nào @Primary | Không match | Không chọn được một bean chỉ bằng kiểu |
| gatewayA (@Primary) và gatewayB | Match | gatewayA là ứng viên ưu tiên duy nhất |
| gatewayA (@Primary) và gatewayB (@Primary) | Không match | Hai bean cùng ưu tiên, vẫn mơ hồ |
| Chỉ có gatewayA (@Primary) | Match | Vẫn chỉ có một ứng viên; @Primary không cần thiết |

**@Primary** không làm các bean còn lại biến mất: chúng vẫn có thể được lấy theo tên, dùng với @Qualifier hoặc đưa vào collection. @Primary chỉ cung cấp ưu tiên trong việc chọn một bean cho điểm tiêm phù hợp.

Một điểm tinh tế: điều kiện tính trên **các ứng viên đủ điều kiện**, không nhất thiết đếm mọi bean về mặt vật lý. Theo Javadoc Spring Boot hiện hành, bean không phải autowire candidate, không phải default candidate, hoặc là fallback candidate sẽ bị bỏ qua khi xác định ứng viên. Trên một phiên bản Spring Boot khác, hãy kiểm tra Javadoc tương ứng trước khi dựa vào các quy tắc lọc ứng viên mới.

## 3. Cú pháp và các thuộc tính

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.autoconfigure.condition.SearchStrategy;

// Các đoạn sau minh họa cách viết annotation; không phải chương trình độc lập.
@ConditionalOnSingleCandidate(PaymentGateway.class)
@ConditionalOnSingleCandidate(value = PaymentGateway.class)
@ConditionalOnSingleCandidate(type = "example.PaymentGateway")
@ConditionalOnSingleCandidate(
    value = PaymentGateway.class,
    search = SearchStrategy.CURRENT
)
~~~

Trong ví dụ cú pháp ở trên, mỗi annotation là **một lựa chọn thay thế**, không đặt đồng thời cả bốn trên cùng một phần tử Java.

- **value**: kiểu cần kiểm tra, ví dụ PaymentGateway.class. Đây là lựa chọn phổ biến khi ứng dụng có kiểu đó trên classpath.
- **type**: tên lớp đầy đủ dạng chuỗi. Hữu ích với class tùy chọn; không sử dụng **value** và **type** cùng lúc.
- **search**: phạm vi tìm bean trong cấu trúc context cha–con. Mặc định là **SearchStrategy.ALL**; **CURRENT** chỉ xét context hiện tại; **ANCESTORS** chỉ xét các context cha.

Nếu tạo annotation tổng hợp (meta-annotation) cho điều kiện phụ thuộc vào một lớp có thể vắng mặt trên classpath, hãy cân nhắc **type** dạng tên chuỗi theo hướng dẫn Javadoc. Để bài học dễ đọc và dễ kiểm thử, các ví dụ tiếp theo chỉ rõ kiểu trong **value**.

### Đặt trên phương thức hay lớp cấu hình?

~~~java
// Giả định PaymentGateway, GatewayClient và constructor của chúng đã được định nghĩa.
@AutoConfiguration
class GatewayClientAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(PaymentGateway.class)
    GatewayClient gatewayClient(PaymentGateway gateway) {
        return new GatewayClient(gateway);
    }
}
~~~

Ở cấp **@Bean**, chỉ bean gatewayClient bị điều kiện chi phối; các bean khác trong cùng cấu hình vẫn có thể được đăng ký. Khi gắn điều kiện lên **lớp @AutoConfiguration**, điều kiện quyết định cấu hình đó có được áp dụng hay không. Hãy chọn phạm vi đặt annotation theo đối tượng thực sự cần phụ thuộc vào một ứng viên duy nhất.

## 4. Ví dụ kiểm thử chạy được với Java 17+ và Spring Boot

Ví dụ sau dùng JUnit 5, AssertJ và **ApplicationContextRunner** (từ spring-boot-test) để quan sát cả bốn trường hợp cơ bản, không cần khởi động web server. Nó có thể đặt trong một dự án Maven Spring Boot đã có dependency **spring-boot-starter** và **spring-boot-starter-test**. Tạo tệp **src/test/java/example/SingleCandidateConditionTests.java**:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class SingleCandidateConditionTests {

    interface Gateway {
        String name();
    }

    record Client(Gateway gateway) {
    }

    @AutoConfiguration
    static class ClientAutoConfiguration {

        @Bean
        @ConditionalOnSingleCandidate(Gateway.class)
        Client client(Gateway gateway) {
            return new Client(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OneGateway {

        @Bean
        Gateway alphaGateway() {
            return () -> "alpha";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoGateways {

        @Bean
        Gateway alphaGateway() {
            return () -> "alpha";
        }

        @Bean
        Gateway betaGateway() {
            return () -> "beta";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OnePrimaryGateway {

        @Bean
        @Primary
        Gateway alphaGateway() {
            return () -> "alpha";
        }

        @Bean
        Gateway betaGateway() {
            return () -> "beta";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ClientAutoConfiguration.class)
                    );

    @Test
    void noGatewayDoesNotCreateClient() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean(Client.class));
    }

    @Test
    void oneGatewayCreatesClient() {
        runner.withUserConfiguration(OneGateway.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Client.class);
                    assertThat(context.getBean(Client.class)
                            .gateway().name()).isEqualTo("alpha");
                });
    }

    @Test
    void twoGatewaysWithoutPrimaryDoNotCreateClient() {
        runner.withUserConfiguration(TwoGateways.class)
                .run(context ->
                        assertThat(context).doesNotHaveBean(Client.class));
    }

    @Test
    void twoGatewaysWithOnePrimaryCreateClient() {
        runner.withUserConfiguration(OnePrimaryGateway.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Client.class);
                    assertThat(context.getBean(Client.class)
                            .gateway().name()).isEqualTo("alpha");
                });
    }
}
~~~

Chạy với Maven Wrapper của dự án:

~~~bash
./mvnw test -Dtest=SingleCandidateConditionTests
~~~

Trên Windows PowerShell, dùng **.\mvnw.cmd test -Dtest=SingleCandidateConditionTests**. Nếu dự án cài Maven toàn cục, dùng **mvn test -Dtest=SingleCandidateConditionTests**.

**Kết quả kỳ vọng:** cả bốn test thành công; không có bean Client ở hai ca thiếu ứng viên hoặc mơ hồ, và có một bean Client ở hai ca chọn được Gateway. Test cuối còn xác nhận Gateway được tiêm là **alpha**, tức bean có **@Primary**. Output console chi tiết do phiên bản Maven, plugin và cấu hình log quyết định; không nên coi một đoạn log cố định là phần định nghĩa của annotation.

**Giải thích cơ chế của test:**

1. ApplicationContextRunner đăng ký cấu hình người dùng trước khi xử lý auto-configuration trong trường hợp kiểm thử này.
2. Spring Boot đánh giá điều kiện trên phương thức client(...) dựa trên các bean **Gateway** đã được đăng ký ở thời điểm đó.
3. Nếu điều kiện không khớp, bean definition của Client không được thêm vào context.
4. Nếu khớp, Spring tạo Client và resolve tham số Gateway. Với hai Gateway và một @Primary, bean ưu tiên được chọn.

**Vì sao dùng @Primary trên phương thức @Bean?** Trong ví dụ, các Gateway được tạo bởi phương thức @Bean. Gắn @Primary trực tiếp lên phương thức tạo bean biểu đạt rõ ưu tiên của chính bean definition đó.

## 5. Tình huống ứng dụng trong auto-configuration thật

Giả sử thư viện tích hợp muốn tạo một **PaymentAuditService** để ghi audit khi ứng dụng có thể cung cấp đúng một **PaymentGateway** cần dùng. Lõi ý tưởng là:

~~~java
// Đoạn minh họa, giả định các kiểu PaymentGateway và PaymentAuditService đã tồn tại.
@AutoConfiguration
class PaymentAuditAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(PaymentGateway.class)
    PaymentAuditService paymentAuditService(PaymentGateway gateway) {
        return new PaymentAuditService(gateway);
    }
}
~~~

Nếu ứng dụng chỉ có StripeGateway, bean audit được tạo. Nếu ứng dụng có StripeGateway và OfflineGateway mà không có @Primary, cấu hình audit sẽ bỏ qua phương thức này để tránh chọn bừa một cổng thanh toán. Nếu StripeGateway được đánh dấu @Primary và OfflineGateway không được đánh dấu, cấu hình audit có thể tạo bean và nhận StripeGateway.

Trong một starter/library thực tế, lớp auto-configuration thường được khai báo trong tệp **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**. Nếu bean PaymentGateway đến từ một auto-configuration khác, hãy sắp thứ tự chúng để cấu hình cung cấp Gateway được xử lý trước, ví dụ dùng thuộc tính **after** của @AutoConfiguration hoặc **@AutoConfigureAfter** phù hợp với phiên bản Spring Boot.

**Phân biệt thứ tự định nghĩa bean và thời điểm tạo instance:** điều kiện được quyết định trong quá trình xử lý các **bean definition**; nó không chờ toàn bộ bean trong ứng dụng được khởi tạo xong rồi mới đếm. Vì vậy thứ tự auto-configuration có thể làm thay đổi kết quả ngay cả khi nhìn vào ứng dụng sau khởi động ta tưởng đã có đủ bean.

## 6. So sánh với các điều kiện gần giống

| Annotation | Câu hỏi mà điều kiện trả lời | Tình huống hai bean cùng kiểu, không có @Primary |
| --- | --- | --- |
| **@ConditionalOnBean(PaymentGateway.class)** | Có bean PaymentGateway phù hợp đã được đăng ký chưa? | Thường match vì có ít nhất một bean |
| **@ConditionalOnMissingBean(PaymentGateway.class)** | Chưa có bean PaymentGateway phù hợp nào? | Không match |
| **@ConditionalOnSingleCandidate(PaymentGateway.class)** | Có thể chọn duy nhất một ứng viên PaymentGateway không? | Không match |

Không nên thay **@ConditionalOnSingleCandidate** bằng **@ConditionalOnBean** trong một phương thức @Bean bắt buộc tiêm một tham số theo kiểu nếu có khả năng xuất hiện nhiều ứng viên: điều kiện "có tồn tại" có thể khớp trong khi điểm tiêm vẫn mơ hồ. Ngược lại, **@ConditionalOnMissingBean** thường dùng cho bài toán cung cấp bean mặc định và cho phép người dùng tự thay thế; mục đích khác với điều kiện chọn một dependency duy nhất.

**@Qualifier** cũng khác **@Primary**: một điểm tiêm có thể dùng @Qualifier("alphaGateway") để chọn giữa nhiều bean, nhưng **@ConditionalOnSingleCandidate(Gateway.class)** đang kiểm tra tính duy nhất của các ứng viên theo kiểu Gateway. Nó không tự suy luận giá trị @Qualifier từ tham số của phương thức @Bean để biến hai ứng viên không có @Primary thành một ứng viên duy nhất. Nếu cần ghim một bean theo tên, hãy thiết kế điều kiện và tham số tiêm rõ ràng theo hợp đồng của thư viện.

## 7. Lưu ý quan trọng, lỗi thường gặp và cách chẩn đoán

1. **Hiểu nhầm "single" là đếm toàn bộ instance.** Có hai bean nhưng đúng một @Primary vẫn match; xem bảng ở mục 2.
2. **Quên @Primary khi có nhiều implementation.** Spring Boot có thể bỏ qua bean phụ trợ của auto-configuration vì không chọn được ứng viên; cân nhắc đặt @Primary trên bean chủ đạo hoặc tách cấu hình theo nhu cầu thực tế.
3. **Đặt hai @Primary.** Hai ưu tiên đồng hạng không giải quyết được tính mơ hồ. Chọn một primary rõ ràng.
4. **Nhầm @Qualifier với @Primary.** Qualifier của một injection point không làm thay đổi phép kiểm tra type-only của annotation.
5. **Đặt annotation ở vị trí quá rộng.** Đặt trên lớp auto-configuration có thể khiến mọi @Bean trong lớp bị loại; đặt trên phương thức cụ thể nếu chỉ một bean cần điều kiện này.
6. **Thiếu kiểu khai báo đủ rõ.** Ví dụ phương thức @Bean khai báo trả về Object dù thực tế trả về Gateway có thể khiến việc suy luận kiểu khi xét bean definition không như mong muốn. Khai báo kiểu trả về thể hiện đúng contract, ví dụ Gateway.
7. **Sai thứ tự auto-configuration.** Điều kiện chỉ nhận biết các bean definition đã được xử lý. Khi phụ thuộc bean do auto-configuration khác đăng ký, xác định thứ tự rõ ràng.
8. **Không chú ý context cha–con.** Mặc định search=ALL xem toàn bộ hierarchy. Nếu chỉ muốn bean trong context hiện tại thì dùng search=SearchStrategy.CURRENT; khi cần xét riêng các context cha thì dùng ANCESTORS.
9. **Cho rằng match bảo đảm toàn bộ ứng dụng khởi động thành công.** Điều kiện chỉ xét khả năng chọn ứng viên của kiểu chỉ định; constructor, dependencies khác hoặc logic khởi tạo vẫn có thể lỗi.
10. **Dựa vào hành vi đặc thù phiên bản mà không kiểm tra.** Các khái niệm default candidate/fallback candidate đã có quy tắc lọc rõ trong Javadoc Spring Boot hiện hành; cần đối chiếu với phiên bản thực tế của dự án.

Khi bất ngờ không có bean, bật báo cáo điều kiện bằng tùy chọn **--debug** lúc chạy Spring Boot; trong ứng dụng có Actuator và cho phép truy cập endpoint tương ứng, **/actuator/conditions** cũng cho biết các điều kiện match hoặc không match. Với unit test, dùng **ApplicationContextRunner** để tạo các tổ hợp bean có kiểm soát và xem **ConditionEvaluationReport**.

## 8. Tự kiểm tra hiểu bài

**Câu 1.** Có hai bean PaymentGateway, một bean là @Primary. @ConditionalOnSingleCandidate(PaymentGateway.class) có match không?

**Đáp án:** Có, nếu các bean là ứng viên hợp lệ và chỉ một bean được đánh dấu @Primary; điều kiện chọn được một ứng viên ưu tiên.

**Câu 2.** Có ba bean cùng kiểu, không có @Primary; phương thức @Bean được đánh dấu điều kiện này và nhận một tham số cùng kiểu. Điều gì xảy ra?

**Đáp án:** Điều kiện không match, nên bean do phương thức đó tạo không được đăng ký. Không nên nói mặc định cả ứng dụng chắc chắn lỗi: các bean khác có thể hoạt động bình thường.

**Câu 3.** Hai bean cùng kiểu không có @Primary, nhưng tham số của phương thức @Bean có @Qualifier. Chỉ riêng qualifier đó có khiến @ConditionalOnSingleCandidate match không?

**Đáp án:** Không. Điều kiện kiểm tra khả năng chọn ứng viên của kiểu được chỉ định, không tự lấy qualifier từ tham số làm điều kiện chọn.

**Câu 4.** Vì sao cần cân nhắc thứ tự các lớp auto-configuration?

**Đáp án:** Vì điều kiện được đánh giá theo những bean definition đã được xử lý tại thời điểm đó. Nếu cấu hình tạo dependency chạy sau, điều kiện có thể không nhìn thấy dependency mà ta mong đợi.

## 9. Tài liệu tham khảo chính thức

- Spring Boot Javadoc — ConditionalOnSingleCandidate: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html
- Spring Boot Javadoc — SearchStrategy: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html
- Spring Boot Reference — Creating Your Own Auto-configuration (bean conditions và ApplicationContextRunner): https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
