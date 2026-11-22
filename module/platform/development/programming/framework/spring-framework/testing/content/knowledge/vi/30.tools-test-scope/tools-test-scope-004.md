# Phân biệt @TestConfiguration với cấu hình Spring Framework thông thường

**Ngữ cảnh:** Spring Framework Testing → Công cụ và phạm vi.

Khi viết test cho ứng dụng Spring, đôi khi cần đăng ký thêm bean chỉ phục vụ kịch bản kiểm thử: một Clock cố định, một fake gateway, một bộ chuyển đổi dữ liệu đặc biệt hoặc một bean hỗ trợ quan sát hành vi. Câu hỏi quan trọng là nên khai báo bean đó bằng **@Configuration** thông thường hay **@TestConfiguration**.

Hai annotation có liên quan nhưng phục vụ mục đích khác nhau:

- **@Configuration** là annotation cấu hình chuẩn của Spring Framework. Class được đánh dấu có thể khai báo bean cho ApplicationContext của ứng dụng hoặc test.
- **@TestConfiguration** là annotation của Spring Boot Test, dùng để khai báo cấu hình bổ sung dành cho test. Nó được thiết kế để không bị component scanning thông thường tự động phát hiện.

Khác biệt này ảnh hưởng đến cách Spring tìm cấu hình, cách cấu hình test được kết hợp với cấu hình ứng dụng và nguy cơ một cấu hình dành cho test vô tình đi vào context không mong muốn. Cần chọn annotation theo cách context được khởi tạo và theo phạm vi mà bean cần tồn tại.

## 1. Nguồn gốc và vai trò của hai annotation

### 1.1. @Configuration thuộc Spring Framework

@Configuration nằm trong package org.springframework.context.annotation. Đây là annotation nền tảng để khai báo Java-based configuration.

~~~java
@Configuration
class ApplicationConfig {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderService orderService(OrderRepository repository, Clock clock) {
        return new OrderService(repository, clock);
    }
}
~~~

Spring đọc class cấu hình và đăng ký các bean được khai báo bằng @Bean. Cấu hình này có thể được nạp qua component scanning, @Import hoặc được chỉ định trực tiếp trong @ContextConfiguration.

Một @Configuration thông thường không mặc nhiên có nghĩa là bean chỉ tồn tại trong test. Nếu class đó được nạp vào ApplicationContext của ứng dụng, các bean của nó thuộc context đó.

### 1.2. @TestConfiguration thuộc Spring Boot Test

@TestConfiguration nằm trong package org.springframework.boot.test.context. Đây là chuyên biệt hóa dành cho test của @Configuration.

~~~java
@TestConfiguration
class OrderTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-01-15T10:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Annotation này được Spring Boot cung cấp trong module spring-boot-test. Nó không phải annotation thuộc Spring Framework core. Dự án chỉ dùng Spring Framework và Spring Test thuần sẽ không có @TestConfiguration nếu không thêm Spring Boot Test.

@TestConfiguration cũng cho phép khai báo bean bằng @Bean, import cấu hình khác và kết hợp với các cơ chế cấu hình Spring thông thường. Điểm khác biệt quan trọng là class được đánh dấu như một test component nên bị loại khỏi việc phát hiện bằng component scanning thông thường.

### 1.3. Bảng so sánh

| Tiêu chí | @Configuration | @TestConfiguration |
|---|---|---|
| Nguồn | Spring Framework | Spring Boot Test |
| Mục đích | Khai báo bean cho ApplicationContext | Khai báo cấu hình bổ sung phục vụ test |
| Component scanning thông thường | Có thể được phát hiện như configuration component | Được loại khỏi component scanning thông thường |
| Phạm vi sử dụng | Runtime application và test | Chủ yếu test context |
| Dùng @Bean | Có | Có |
| Có tự động thay thế bean ứng dụng không? | Không | Không |
| Có thể nạp bằng @Import | Có | Có |
| Có thể dùng trong @ContextConfiguration | Có | Có khi dự án có Spring Boot Test |
| Hợp với test slice của Boot | Có thể, nếu import rõ ràng | Thường phù hợp để bổ sung test bean |
| Có tự động tạo context riêng không? | Không | Không |

Điểm cần nhớ: @TestConfiguration thay đổi cách class cấu hình được nhận diện trong quá trình quét component. Nó không tự tạo một ApplicationContext riêng, không tự động mock bean hiện hữu và không tự động ghi đè cấu hình ứng dụng.

## 2. Vì sao Spring Boot cung cấp @TestConfiguration?

Trong ứng dụng Spring Boot, cấu hình chính thường được tìm từ class có @SpringBootApplication hoặc @SpringBootConfiguration. Test thường muốn giữ cấu hình ứng dụng chính và chỉ bổ sung một số bean cho kịch bản.

Ví dụ một test cần thay Clock hệ thống bằng Clock cố định để kết quả không phụ thuộc thời gian chạy. Nếu khai báo một nested class chỉ dùng @Configuration bên trong test class, Spring Boot có thể xem class đó là cấu hình chính được tìm thấy cho test. Điều này có thể làm test chỉ nạp cấu hình nhỏ đó thay vì cấu hình ứng dụng.

@TestConfiguration được thiết kế để giải quyết tình huống này: một nested test configuration được dùng bổ sung cùng cấu hình chính của ứng dụng.

~~~text
@SpringBootTest
      |
      v
Tìm cấu hình ứng dụng chính
@SpringBootApplication
      |
      +---- Application beans
      |
      +---- Test-only configuration
              @TestConfiguration
              |
              +---- fixed Clock
              +---- fake gateway
              +---- test helper bean
~~~

Với nested @TestConfiguration, Spring Boot có thể dùng cấu hình đó cùng cấu hình chính mà test đang yêu cầu. Với class @TestConfiguration ở top-level, test thường import rõ ràng bằng @Import để đưa cấu hình vào context.

## 3. Component scanning và phạm vi phát hiện

### 3.1. @Configuration có thể được component scan phát hiện

@Configuration là một component candidate. Nếu package của class nằm trong phạm vi component scan, Spring có thể phát hiện class cấu hình và đăng ký bean của nó.

~~~java
@Configuration
class SharedApplicationConfiguration {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }
}
~~~

Nếu class này nằm trong package mà @SpringBootApplication quét, nó có thể được nạp trong ApplicationContext của ứng dụng. Vì thế, đặt một cấu hình chỉ dành cho test vào package production có thể làm cấu hình đó bị phát hiện ngoài ý muốn nếu dùng @Configuration thông thường.

Một test source set riêng thường không được đóng gói vào artifact production, nhưng cấu hình scan và cách tổ chức module vẫn cần rõ ràng. Không nên dựa duy nhất vào việc file nằm trong src/test/java để suy luận component scan sẽ hoặc sẽ không tìm thấy nó trong mọi kiểu test context.

### 3.2. @TestConfiguration bị loại khỏi component scanning thông thường

@TestConfiguration được đánh dấu là test component. Spring Boot dùng đặc tính này để loại cấu hình đó khỏi việc phát hiện bằng component scanning thông thường.

~~~java
@TestConfiguration
class TestClockConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-02-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Class trên sẽ không tự xuất hiện trong application context chỉ vì package scan đi qua vị trí của nó. Test cần nạp nó một cách có chủ đích, chẳng hạn qua @Import hoặc cơ chế nested test configuration.

Điều này giúp tránh việc cấu hình chỉ dành cho test vô tình được đăng ký khi ứng dụng khởi chạy bình thường.

### 3.3. Không nhầm component scan với import tường minh

Việc @TestConfiguration bị loại khỏi component scanning không có nghĩa Spring không thể nạp nó. Khi test chỉ định rõ class bằng @Import hoặc @ContextConfiguration, Spring vẫn xử lý cấu hình đó.

~~~java
@SpringBootTest
@Import(TestClockConfiguration.class)
class OrderServiceTests {
    // Test sử dụng Clock được khai báo trong TestClockConfiguration.
}
~~~

Component scan là cơ chế tự tìm component theo package. @Import là yêu cầu tường minh đưa một class cấu hình hoặc component vào context. Hai cơ chế này khác nhau.

## 4. Dùng nested @TestConfiguration trong Spring Boot test

### 4.1. Nested configuration bổ sung vào cấu hình ứng dụng

Một cách phổ biến là khai báo static nested class ngay trong test:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @TestConfiguration
    static class TestConfig {

        @Bean
        Clock fixedClock() {
            return Clock.fixed(
                    Instant.parse("2025-03-01T09:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Test
    void createsOrderWithDeterministicTimestamp() {
        // Test sử dụng fixedClock đã được nạp cùng application context.
    }
}
~~~

Nested class cần là static để không phụ thuộc vào instance của test class. Cấu hình được dùng thêm cùng cấu hình chính của Spring Boot test, do đó các bean production khác vẫn có thể được nạp theo thiết lập của test.

Cách này phù hợp khi cấu hình chỉ phục vụ một test class và không cần tái sử dụng ở nơi khác.

### 4.2. Nested @Configuration có ý nghĩa khác

Nếu thay @TestConfiguration bằng @Configuration:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Configuration
    static class TestConfig {

        @Bean
        Clock fixedClock() {
            return Clock.systemUTC();
        }
    }
}
~~~

Một nested @Configuration có thể được Spring Boot xem là cấu hình chính được tìm thấy cho test, thay vì chỉ là phần bổ sung cho cấu hình ứng dụng. Kết quả là test có thể không nạp cấu hình chính mà người viết mong muốn.

Đây là lý do Spring Boot phân biệt hai annotation. Khi muốn giữ cấu hình chính của ứng dụng và thêm bean dành riêng cho test, hãy dùng @TestConfiguration cho nested class.

### 4.3. Khi nested config không còn là lựa chọn tốt

Nếu nhiều test class cần cùng một fake, Clock hoặc test helper, có thể tách cấu hình ra top-level class trong test source set:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class SharedOrderTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-03-01T09:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Sau đó import tại test cần dùng:

~~~java
@SpringBootTest
@Import(SharedOrderTestConfiguration.class)
class OrderServiceIntegrationTest {
    // ...
}
~~~

~~~java
@SpringBootTest
@Import(SharedOrderTestConfiguration.class)
class OrderControllerIntegrationTest {
    // ...
}
~~~

Cấu hình top-level có thể tái sử dụng nhưng vẫn chỉ được nạp ở các test import nó. Vì @TestConfiguration không được component scan thông thường tự phát hiện, việc dùng chung vẫn cần import tường minh.

## 5. Dùng @TestConfiguration trong test slice

### 5.1. Test slice chỉ nạp một phần ứng dụng

Spring Boot test slice như @WebMvcTest, @DataJpaTest hoặc @JsonTest chỉ nạp các thành phần liên quan đến một lớp kiểm thử. Chúng không mặc định tạo toàn bộ ApplicationContext như @SpringBootTest.

Ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    // Chỉ nạp phần MVC cần cho controller test.
}
~~~

Nếu controller phụ thuộc một gateway hoặc service mà slice không tự tạo, có thể cung cấp mock bean hoặc import một test configuration.

### 5.2. Bổ sung bean cho @WebMvcTest

~~~java
@WebMvcTest(OrderController.class)
@Import(OrderMvcTestConfiguration.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;
}

@TestConfiguration(proxyBeanMethods = false)
class OrderMvcTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-04-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Cấu hình bổ sung chỉ chứa bean mà MVC test cần. Các dependency nghiệp vụ có thể được mock riêng bằng cơ chế bean override phù hợp với phiên bản Spring Boot/Spring Framework đang dùng.

Không nên import toàn bộ cấu hình production chỉ để lấy một bean nhỏ nếu việc đó kéo thêm datasource, broker hoặc client ngoài phạm vi slice. Giữ test slice tập trung giúp test khởi động nhanh và xác nhận đúng tầng.

### 5.3. Bổ sung cấu hình cho @DataJpaTest

~~~java
@DataJpaTest
@Import(JpaTestClockConfiguration.class)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;
}

@TestConfiguration(proxyBeanMethods = false)
class JpaTestClockConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2025-05-01T12:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Nếu test cần một bean hỗ trợ entity listener hoặc auditing, có thể import cấu hình nhỏ. Cần xem slice hiện tại đã cung cấp bean đó chưa để tránh khai báo trùng hoặc thay đổi ngoài ý muốn.

### 5.4. Test slice không đồng nghĩa với test config tự động được nạp

Một class top-level có @TestConfiguration không được đưa vào slice chỉ vì nằm trong cùng package. Hãy import nó rõ ràng hoặc khai báo nested class theo quy tắc test của Spring Boot.

Nếu quên import, test có thể báo thiếu bean khi context khởi tạo. Không nên khắc phục bằng cách thêm @ComponentScan rộng cho toàn ứng dụng, vì điều đó có thể phá vỡ phạm vi slice và làm test nạp quá nhiều bean.

## 6. Dùng cấu hình trong Spring Framework thuần

### 6.1. @TestConfiguration không thuộc Spring Framework core

Nếu project chỉ dùng Spring Framework và Spring Test, không có Spring Boot Test, annotation @TestConfiguration không có sẵn.

Trong trường hợp đó, dùng @Configuration thông thường nhưng nạp nó tường minh trong test context:

~~~java
@Configuration
class OrderTestBeans {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-06-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Test:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
        OrderService.class,
        OrderTestBeans.class
})
class OrderServiceTest {

    @Autowired
    OrderService orderService;
}
~~~

Ở đây, @ContextConfiguration chỉ định chính xác cấu hình và component cần đưa vào context. Cấu hình test không được nạp bởi component scan của ứng dụng nếu test không yêu cầu scan package đó.

### 6.2. Dùng @Import để tách cấu hình

Có thể khai báo cấu hình gốc và import test config:

~~~java
@Configuration
@Import(OrderTestBeans.class)
class OrderTestContextConfiguration {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            Clock fixedClock) {
        return new OrderService(repository, fixedClock);
    }
}
~~~

Test:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestContextConfiguration.class)
class OrderServiceTest {
    // ...
}
~~~

Cách này có thể dùng với Spring Framework thuần. Ý tưởng vẫn giống Spring Boot: tách cấu hình test và chỉ nạp nó vào context được chỉ định.

### 6.3. Khi nào vẫn dùng @Configuration trong test source?

Trong project không dùng Spring Boot, @Configuration là cách chuẩn để khai báo bean trong test. Trong project có Boot, vẫn có thể dùng @Configuration cho cấu hình test nếu test chủ động chỉ định class đó bằng @ContextConfiguration hoặc @Import và không gây nhầm lẫn với primary configuration discovery.

Không cần thêm Spring Boot Test chỉ để có annotation @TestConfiguration nếu project không sử dụng Boot. Chọn dependency theo nền tảng thực tế của project.

## 7. @TestConfiguration không tự động thay thế bean production

Đây là nhầm lẫn thường gặp. Tên annotation không có nghĩa mọi bean được khai báo bên trong sẽ thay thế bean cùng loại trong application context.

Giả sử ứng dụng có:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

Test thêm:

~~~java
@TestConfiguration
class PaymentTestConfiguration {

    @Bean
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

Nếu cả hai bean cùng được nạp, context có thể có hai bean kiểu PaymentGateway. Khi một constructor yêu cầu PaymentGateway, Spring có thể báo không xác định được bean phù hợp nếu không có quy tắc chọn rõ ràng.

### 7.1. Dùng @Primary khi muốn ưu tiên bean test cho injection

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PaymentTestConfiguration {

    @Bean
    @Primary
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

@Primary đánh dấu bean ưu tiên khi Spring cần chọn một candidate trong nhiều bean cùng phù hợp với một dependency injection point.

Nó không xóa bean production khỏi context. Nếu code inject bằng qualifier, yêu cầu bean theo tên hoặc truy cập tất cả bean theo collection/map, bean production vẫn có thể xuất hiện.

### 7.2. Dùng @Qualifier khi cần lựa chọn rõ ràng

~~~java
@Bean
@Qualifier("testPaymentGateway")
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}
~~~

Tại injection point:

~~~java
OrderService(
        @Qualifier("testPaymentGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Qualifier giúp chọn đúng bean theo mục đích. Tuy nhiên, nếu production code được thiết kế để luôn inject bean theo tên cụ thể, thêm một bean test khác không thay thế được bean đó.

### 7.3. Dùng bean override khi mục tiêu là thay thế dependency

Nếu cần thay bean thật bằng mock trong test, dùng cơ chế bean override được hỗ trợ bởi phiên bản Spring đang dùng, chẳng hạn @MockitoBean trong Spring Framework 6.2+ hoặc annotation tương ứng của Spring Boot Test ở phiên bản cũ hơn.

~~~java
@SpringBootTest
class PaymentServiceTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    PaymentService paymentService;

    @Test
    void handlesApprovedPayment() {
        given(paymentGateway.charge(any()))
                .willReturn(PaymentResult.approved());

        // Xác nhận nghiệp vụ.
    }
}
~~~

Bean override có mục tiêu khác với việc thêm một bean qua @TestConfiguration. Khi muốn thêm collaborator hoặc test utility, cấu hình test phù hợp. Khi muốn thay một dependency cụ thể, bean override thường diễn đạt ý định chính xác hơn.

### 7.4. Không dựa vào bean definition overriding ngầm

Việc khai báo hai bean cùng tên hoặc trông chờ một bean đăng ký sau ghi đè bean trước phụ thuộc vào quy tắc bean definition overriding và cấu hình của context. Trong nhiều cấu hình Spring Boot hiện đại, bean definition overriding bị tắt mặc định.

Không nên thiết kế test dựa trên thứ tự component scan hoặc thứ tự import để bean test tình cờ thắng. Dùng @Primary, @Qualifier hoặc bean override API một cách tường minh.

## 8. proxyBeanMethods và cách khai báo @Bean

Cả @Configuration và @TestConfiguration đều hỗ trợ cấu hình proxyBeanMethods.

### 8.1. Mặc định full configuration

Với cấu hình proxyBeanMethods mặc định, Spring có thể tạo subclass proxy cho configuration class để lời gọi giữa các phương thức @Bean được điều phối qua container.

~~~java
@TestConfiguration
class OrderTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-07-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy(fixedClock());
    }
}
~~~

Trong full configuration, lời gọi fixedClock() từ phương thức @Bean khác được xử lý để trả về bean do container quản lý, thay vì tạo instance mới ngoài container.

### 8.2. proxyBeanMethods = false

Nếu các bean được nối bằng method parameter injection, có thể tắt proxy:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class OrderTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-07-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderPolicy orderPolicy(Clock fixedClock) {
        return new OrderPolicy(fixedClock);
    }
}
~~~

Cách này thường gọn và hiệu quả hơn cho cấu hình test nhỏ. Spring vẫn quản lý các bean, nhưng lời gọi trực tiếp giữa các phương thức @Bean không được intercept để lấy instance từ container.

Nếu viết orderPolicy() gọi fixedClock() trực tiếp trong cấu hình lite mode, lời gọi đó có thể tạo một Clock instance mới thay vì lấy bean được quản lý. Dùng method parameter injection để thể hiện dependency rõ ràng.

### 8.3. Chọn khi nào tắt proxy

Dùng proxyBeanMethods = false khi:

- Các bean độc lập hoặc kết nối với nhau qua method parameters.
- Không cần gọi một @Bean method từ một @Bean method khác.
- Muốn cấu hình test nhẹ và dễ đọc.

Giữ chế độ mặc định khi cần semantics full configuration và có lý do rõ ràng. Không nên tắt proxy rồi tiếp tục gọi trực tiếp các phương thức @Bean như thể chúng luôn trả cùng singleton.

## 9. Tổ chức cấu hình test theo phạm vi

Một dự án có thể chia cấu hình test thành nhiều nhóm:

| Phạm vi | Vị trí phù hợp | Cách nạp |
|---|---|---|
| Chỉ một test method/class | Nested @TestConfiguration | Được Boot test dùng cùng cấu hình chính |
| Nhiều test trong một package | Top-level @TestConfiguration trong test source | @Import tại các test cần dùng |
| Test slice MVC | Test configuration nhỏ | @Import cùng @WebMvcTest |
| Test slice JPA | Test configuration liên quan persistence | @Import cùng @DataJpaTest |
| Spring Framework thuần | Top-level @Configuration trong test source | @ContextConfiguration hoặc @Import |
| Cấu hình production dùng chung | @Configuration trong main source | Component scan hoặc import của ứng dụng |

Không nên tạo một test configuration khổng lồ chứa mọi fake, mock, Clock, converter và datasource cho toàn bộ repository. Khi mọi test import cùng cấu hình lớn, context có thể kéo theo bean không liên quan và cache key khó tái sử dụng.

Tách cấu hình theo mục đích giúp người đọc thấy rõ test cần những bean nào và tránh vô tình đưa infrastructure không cần thiết vào context.

## 10. Kết hợp với @Import và cấu hình hiện hữu

### 10.1. Import test configuration vào test class

~~~java
@SpringBootTest
@Import(OrderTestConfiguration.class)
class OrderIntegrationTest {
    // ...
}
~~~

Cách này thích hợp khi test dùng cấu hình chính của ứng dụng và chỉ thêm một số bean test.

### 10.2. Import nhiều cấu hình nhỏ

~~~java
@SpringBootTest
@Import({
        FixedClockConfiguration.class,
        FakeCatalogConfiguration.class,
        TestEventPublisherConfiguration.class
})
class OrderIntegrationTest {
    // ...
}
~~~

Mỗi cấu hình có trách nhiệm hẹp. Test chỉ import những phần nó cần.

### 10.3. Dùng profile cho cấu hình theo môi trường test

@Profile có thể giới hạn cấu hình theo active profile:

~~~java
@Configuration
@Profile("test")
class TestProfileConfiguration {

    @Bean
    Clock testClock() {
        return Clock.systemUTC();
    }
}
~~~

Profile và @TestConfiguration giải quyết hai vấn đề khác nhau. @Profile điều khiển cấu hình được kích hoạt theo environment profile. @TestConfiguration thể hiện cấu hình bổ sung dành cho test và loại nó khỏi component scan thông thường.

Không nên thay @TestConfiguration bằng @Profile("test") nếu mục tiêu chính là tránh test configuration bị component scanning tự phát hiện trong các context không mong muốn. Profile vẫn có thể bị kích hoạt ở một application context chạy ngoài test nếu cấu hình được scan và profile được bật.

## 11. Các lỗi thường gặp và cách xử lý

### Nested @Configuration làm mất cấu hình ứng dụng chính

**Dấu hiệu:** Test chỉ thấy một nhóm bean nhỏ hoặc báo thiếu bean production sau khi thêm nested @Configuration.

**Nguyên nhân:** Spring Boot có thể chọn nested @Configuration làm primary configuration cho test.

**Cách xử lý:** Nếu muốn bổ sung bean vào cấu hình ứng dụng, đổi nested class sang @TestConfiguration. Nếu cần một context hoàn toàn riêng, khai báo chủ đích cấu hình chính qua @ContextConfiguration hoặc cơ chế phù hợp.

### Top-level @TestConfiguration không được nạp

**Dấu hiệu:** Bean được khai báo trong class nhưng Spring báo NoSuchBeanDefinitionException.

**Nguyên nhân:** @TestConfiguration bị loại khỏi component scanning thông thường.

**Cách xử lý:** Import class bằng @Import hoặc chỉ định rõ trong cấu hình test. Với test slice, import vào test class đang dùng slice đó.

### Hai bean cùng kiểu gây NoUniqueBeanDefinitionException

**Dấu hiệu:** Spring tìm thấy nhiều bean cùng type khi inject một dependency.

**Nguyên nhân:** Test configuration thêm bean mới nhưng bean production vẫn tồn tại.

**Cách xử lý:** Dùng @Primary hoặc @Qualifier nếu cần chọn một candidate; dùng @MockitoBean hoặc cơ chế bean override nếu mục tiêu là thay thế dependency hiện hữu.

### Trông chờ bean test tự động ghi đè bean production

**Dấu hiệu:** Context khởi tạo lỗi bean definition conflict hoặc test vẫn dùng bean production.

**Nguyên nhân:** @TestConfiguration không phải lệnh override bean.

**Cách xử lý:** Xác định mục tiêu là bổ sung hay thay thế. Chọn cấu hình bổ sung, qualifier, primary hoặc bean override API tương ứng.

### Test slice không tìm thấy test bean

**Dấu hiệu:** @WebMvcTest hoặc @DataJpaTest báo thiếu dependency dù test configuration nằm trong source set test.

**Nguyên nhân:** Test slice có phạm vi component scan giới hạn và top-level test configuration không tự được import.

**Cách xử lý:** Dùng @Import hoặc nested @TestConfiguration phù hợp. Tránh mở rộng component scan toàn ứng dụng chỉ để tìm một bean test.

### Cấu hình test vô tình được nạp trong application context khác

**Dấu hiệu:** Một bean chỉ dành cho test xuất hiện trong context không mong muốn.

**Nguyên nhân:** Cấu hình được đánh dấu @Configuration và package scan đi qua class đó.

**Cách xử lý:** Dùng @TestConfiguration cho cấu hình test khi có Spring Boot Test, đặt trong test source set và import tường minh. Với Spring Framework thuần, kiểm soát danh sách class trong @ContextConfiguration và không scan package chứa cấu hình test ngoài ý muốn.

### proxyBeanMethods bị tắt nhưng method @Bean gọi lẫn nhau

**Dấu hiệu:** Có nhiều instance của một dependency thay vì singleton bean đã được đăng ký.

**Nguyên nhân:** Lời gọi Java trực tiếp giữa các phương thức @Bean không được proxy intercept khi proxyBeanMethods = false.

**Cách xử lý:** Inject bean qua parameter của phương thức @Bean hoặc bật full configuration nếu cần gọi qua method.

### Thêm @TestConfiguration làm context cache thay đổi

**Dấu hiệu:** Nhiều context được tạo hơn và test suite chạy chậm hơn.

**Nguyên nhân:** Cấu hình import, bean override hoặc context customizer có thể làm cache key khác nhau giữa các test class.

**Cách xử lý:** Tái sử dụng các test configuration nhỏ và ổn định cho nhóm test có cùng nhu cầu. Tránh tạo cấu hình khác nhau không cần thiết ở mỗi test class nếu chúng không cần bean khác nhau.

## 12. Ví dụ hoàn chỉnh: thay Clock bằng cấu hình test

Giả sử service dùng Clock để tạo timestamp cho đơn hàng:

~~~java
record Order(String id, Instant createdAt) {}

class OrderService {

    private final Clock clock;

    OrderService(Clock clock) {
        this.clock = clock;
    }

    Order create(String id) {
        return new Order(id, Instant.now(clock));
    }
}
~~~

Cấu hình production:

~~~java
@Configuration
class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Test configuration:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class FixedTimeTestConfiguration {

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-08-10T12:30:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Test:

~~~java
@SpringBootTest
@Import(FixedTimeTestConfiguration.class)
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrderAtFixedInstant() {
        Order order = orderService.create("ORD-100");

        assertThat(order.createdAt())
                .isEqualTo(Instant.parse("2025-08-10T12:30:00Z"));
    }
}
~~~

Trong ví dụ này, cấu hình production vẫn tạo Clock hệ thống. Test configuration thêm Clock cố định và đánh dấu @Primary để dependency injection chọn nó khi OrderService yêu cầu Clock. Bean production vẫn có mặt trong context; test chỉ ưu tiên bean test cho injection theo type.

Nếu muốn test thay thế hoàn toàn bean Clock production, có thể dùng cơ chế bean override phù hợp thay vì thêm bean thứ hai. Lựa chọn phụ thuộc vào cách cấu hình ứng dụng và contract mà test muốn xác nhận.

## 13. Ví dụ hoàn chỉnh: test slice MVC với fake service

Giả sử controller phụ thuộc OrderQueryService:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderQueryService queryService;

    OrderController(OrderQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping("/{id}")
    OrderResponse find(@PathVariable String id) {
        return queryService.find(id);
    }
}

record OrderResponse(String id, String status) {}
~~~

Test configuration cung cấp fake service:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class OrderMvcTestConfiguration {

    @Bean
    @Primary
    OrderQueryService fakeOrderQueryService() {
        return id -> new OrderResponse(id, "PAID");
    }
}
~~~

Test slice:

~~~java
@WebMvcTest(OrderController.class)
@Import(OrderMvcTestConfiguration.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsOrderFromTestService() throws Exception {
        mockMvc.perform(get("/orders/ORD-100"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ORD-100"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

Ví dụ giả định OrderQueryService là interface hoặc type có thể được triển khai bằng lambda như trên. Cấu hình chỉ thêm dependency phục vụ controller test. @WebMvcTest vẫn giữ phạm vi MVC slice và @Import đưa fake vào context.

Trong một test khác, nếu cần xác nhận cách controller xử lý nhiều kết quả hoặc exception, có thể dùng fake có trạng thái được tạo riêng cho test hoặc bean mock override. Không nên dùng một fake singleton mutable cho nhiều test concurrent mà không có cơ chế cô lập.

## 14. Checklist lựa chọn annotation

| Câu hỏi | Lựa chọn phù hợp |
|---|---|
| Đây là cấu hình production được ứng dụng sử dụng? | @Configuration |
| Đây là cấu hình bổ sung chỉ dành cho Spring Boot test? | @TestConfiguration |
| Cần thêm bean vào @SpringBootTest mà vẫn giữ cấu hình chính? | @TestConfiguration + @Import hoặc nested @TestConfiguration |
| Cần thêm bean vào @WebMvcTest/@DataJpaTest? | @TestConfiguration + @Import |
| Project chỉ dùng Spring Framework, không dùng Boot Test? | @Configuration + @ContextConfiguration/@Import |
| Cần thay dependency bằng Mockito mock? | @MockitoBean hoặc cơ chế bean override tương ứng |
| Cần thêm bean cùng type nhưng ưu tiên cho injection? | @Primary hoặc @Qualifier |
| Cấu hình test top-level không tự được tìm thấy? | Import tường minh |
| Muốn cấu hình test không bị component scan thông thường phát hiện? | @TestConfiguration trong Spring Boot Test |

## 15. Nguyên tắc thực hành

1. Nhớ rằng @Configuration thuộc Spring Framework, còn @TestConfiguration thuộc Spring Boot Test.
2. Dùng @Configuration cho cấu hình bean của ứng dụng hoặc cấu hình test được nạp tường minh trong Spring Framework thuần.
3. Dùng @TestConfiguration để khai báo bean bổ sung chỉ phục vụ Spring Boot test.
4. Dùng nested static @TestConfiguration khi cấu hình chỉ cần trong một test class.
5. Dùng top-level @TestConfiguration và @Import khi nhiều test cần tái sử dụng cùng cấu hình.
6. Không giả định top-level @TestConfiguration tự được component scan phát hiện.
7. Với @WebMvcTest, @DataJpaTest và các slice khác, import rõ ràng test configuration cần thiết.
8. Không xem @TestConfiguration là cơ chế tự động ghi đè bean production.
9. Dùng @Primary hoặc @Qualifier để chọn bean; dùng bean override API khi cần thay thế dependency.
10. Dùng proxyBeanMethods = false khi bean được kết nối bằng method parameter injection và không cần full configuration proxy.
11. Không để cấu hình chỉ dành cho test nằm trong package production theo cách có thể bị scan ngoài ý muốn.
12. Giữ test configuration nhỏ, có tên thể hiện mục đích và chỉ chứa bean mà test thực sự cần.

@Configuration là cơ chế khai báo bean chung của Spring Framework. @TestConfiguration bổ sung một cách diễn đạt rõ ràng cho cấu hình chỉ dành cho test trong hệ sinh thái Spring Boot và tránh việc class đó bị component scanning thông thường phát hiện. Chọn đúng annotation, import cấu hình có chủ đích và phân biệt rõ việc thêm bean với việc thay thế bean sẽ giúp test context giữ đúng phạm vi, dễ hiểu và ít gây tác động ngoài ý muốn.

