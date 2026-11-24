# Kiểm tra cấu hình runtime không làm thay đổi tập bean ngoài dự kiến

Trong ứng dụng Spring Boot chạy trên JVM thông thường, các điều kiện như `@Profile` và `@ConditionalOnProperty` được đánh giá khi ApplicationContext khởi động. Vì vậy, một biến môi trường hoặc property có thể quyết định bean nào được đăng ký. Khi bật **Spring AOT**, quyết định này chuyển sang **build time**: Spring phân tích Environment, đánh giá conditions và sinh mã khởi tạo cho tập bean đã chọn.

Hệ quả là một ứng dụng được AOT xử lý với `payment.provider=card` vẫn có bean của card provider khi chạy, kể cả khi môi trường triển khai đặt `payment.provider=bank`. Giá trị property runtime có thể được bind vào `@ConfigurationProperties`, nhưng nó không tự tạo lại bean definitions đã được cố định. Nếu service dùng giá trị runtime để tìm bean khác với tập đã sinh, ứng dụng có thể khởi động lỗi hoặc chọn sai đường xử lý.

Bài học thuộc chương **Kiểm thử AOT** của module **`SPRING_BOOT_NATIVE_IMAGE`**: biên dịch Spring Boot bằng Spring AOT thành GraalVM Native Image, kiểm tra tương thích và vận hành executable. Bài này hướng dẫn cách xác định property nào ảnh hưởng bean topology, kiểm thử tập bean mong đợi trên JVM và AOT, phát hiện cấu hình build/runtime lệch nhau, và thiết kế feature toggle an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao Spring AOT đánh giá `@Conditional` ở build time.
- Phân biệt property điều khiển sự hiện diện của bean với property chỉ điều khiển hành vi của bean.
- Kiểm tra tập bean theo từng cấu hình bằng `ApplicationContextRunner`.
- Viết AOT integration test để xác nhận bean definitions được sinh đúng.
- Phát hiện trường hợp runtime property không khớp với bean set đã được AOT cố định.
- Dùng startup validation để fail fast khi cấu hình triển khai không tương thích.
- Cấu hình profile/property cho Maven `process-aot` và Gradle `processAot`.
- Quyết định khi nào cần build native image variant riêng.

## 2. Vì sao tập bean được cố định ở build time?

Spring AOT chuẩn bị ApplicationContext trong quá trình build. BeanFactory được phân tích và hoàn thiện; các điều kiện ảnh hưởng việc đăng ký bean được đánh giá trong Environment của lần AOT đó. Spring sau đó sinh mã đăng ký bean definitions và những tài nguyên AOT liên quan.

Khi chạy ứng dụng AOT trên JVM (bằng system property `spring.aot.enabled=true`) hoặc chạy native executable, Spring sử dụng kết quả đã sinh. Những quyết định về bean topology không được đánh giá lại như một lần khởi động JVM thông thường.

~~~mermaid
flowchart TD
    A["Classpath + Environment lúc build"] --> B["Spring AOT tạo ApplicationContext"]
    B --> C["Đánh giá @Profile / @Conditional"]
    C --> D["Sinh tập bean definitions"]
    D --> E["AOT generated initializer"]
    E --> F["JVM AOT hoặc Native Image runtime"]
    G["Environment lúc triển khai"] --> H["Bind property vào bean đã có"]
    G --> I["Không thêm/bớt bean definition đã cố định"]
    F --> H
    F --> I
~~~

Spring Boot và Spring Framework nêu rõ:

- Classpath được xác định ở build time.
- `@Profile` và các điều kiện `@Conditional` được đánh giá ở build time.
- Profile đã chọn khi AOT được tự động áp dụng khi chạy AOT.
- Bean được tạo trong quá trình AOT sẽ luôn được tạo khi chạy ứng dụng AOT; không thể tắt bean đó bằng cách đổi property runtime.
- Property chỉ thay đổi giá trị cấu hình, không ảnh hưởng condition, vẫn có thể được cung cấp khi chạy.

Vì vậy, bài kiểm thử cần xác minh **tập bean mong đợi** và **các property runtime được phép thay đổi** như hai khía cạnh riêng.

## 3. Phân loại property trước khi viết test

Không phải mọi property đều cần cố định ở build time. Hãy xác định property tác động tới loại quyết định nào:

| Loại property | Ví dụ | Có thể thay đổi lúc runtime AOT? |
|---|---|---|
| Bean topology | `payment.provider` dùng trong `@ConditionalOnProperty` | Không làm condition được đánh giá lại; phải khớp lựa chọn build time |
| Active profile có configuration/condition | `spring.profiles.active` chọn bean theo `@Profile` | Profile ảnh hưởng bean set phải được chọn lúc AOT |
| Giá trị cấu hình của bean đã có | `payment.timeout`, `partner.base-url` | Có, giá trị được bind khi chạy |
| Hành vi của feature đã đăng ký | `reporting.enabled` được service đọc để bật/tắt xử lý | Có, nếu bean vẫn được đăng ký ổn định |
| Classpath/dependency | Thêm implementation provider hoặc starter | Không; dependency phải có trước AOT/native build |

Một property có thể đồng thời được dùng ở hai nơi. Ví dụ `payment.provider` vừa chọn bean qua `@ConditionalOnProperty`, vừa được bind vào `PaymentSettings`. Khi đó property có hai vai trò:

1. Giá trị lúc AOT chọn implementation nào được đưa vào bean set.
2. Giá trị lúc runtime cho biết ứng dụng đang được cấu hình sử dụng provider nào.

Nếu hai giá trị khác nhau, cần phát hiện và dừng ứng dụng sớm.

## 4. Ví dụ: hai payment provider được chọn bằng condition

Giả sử ứng dụng hỗ trợ thanh toán bằng thẻ và chuyển khoản:

~~~java
public interface PaymentGateway {
    String providerId();
    PaymentResult pay(PaymentRequest request);
}
~~~

Hai implementation:

~~~java
public class CardPaymentGateway implements PaymentGateway {
    @Override
    public String providerId() {
        return "card";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        return PaymentResult.approved();
    }
}
~~~

~~~java
public class BankTransferGateway implements PaymentGateway {
    @Override
    public String providerId() {
        return "bank";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        return PaymentResult.pending();
    }
}
~~~

Configuration đăng ký đúng một implementation dựa trên property:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentSettings.class)
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "payment",
            name = "provider",
            havingValue = "card")
    CardPaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "payment",
            name = "provider",
            havingValue = "bank")
    BankTransferGateway bankGateway() {
        return new BankTransferGateway();
    }
}
~~~

Properties được bind:

~~~java
@ConfigurationProperties(prefix = "payment")
public record PaymentSettings(String provider) {
}
~~~

Nếu AOT chạy với `payment.provider=card`, bean set được sinh sẽ chứa `cardGateway`. Khi runtime dùng cùng giá trị, cấu hình nhất quán.

Nếu runtime đổi thành `payment.provider=bank`, Spring AOT không tự thay `cardGateway` thành `bankGateway`. `PaymentSettings` có thể nhận giá trị `bank`, nhưng bean definitions vẫn phản ánh quyết định đã được thực hiện khi build.

## 5. Phát hiện lệch cấu hình ngay khi ứng dụng khởi động

Không nên chờ tới request đầu tiên mới phát hiện property yêu cầu provider không có trong context. Có thể thêm một kiểm tra nhất quán chạy sau khi singleton beans đã được tạo:

~~~java
@Component
public class PaymentProviderConsistencyCheck
        implements SmartInitializingSingleton {

    private final PaymentSettings settings;
    private final List<PaymentGateway> gateways;

    public PaymentProviderConsistencyCheck(
            PaymentSettings settings,
            List<PaymentGateway> gateways) {
        this.settings = settings;
        this.gateways = gateways;
    }

    @Override
    public void afterSingletonsInstantiated() {
        boolean providerAvailable = this.gateways.stream()
                .anyMatch(gateway ->
                        gateway.providerId().equals(settings.provider()));

        if (!providerAvailable) {
            throw new IllegalStateException(
                    "payment.provider='%s' does not match the AOT bean set. "
                            .formatted(settings.provider())
                    + "Rebuild the AOT/native artifact with the intended provider.");
        }
    }
}
~~~

Kiểm tra này xác nhận provider runtime có implementation tương ứng trong ApplicationContext. Nếu artifact được AOT build với card nhưng runtime khai báo bank, ứng dụng dừng khi khởi tạo thay vì âm thầm chạy với một tập bean không phù hợp.

Trong ứng dụng thực tế, thông báo lỗi nên nêu rõ property, giá trị hiện tại và tên artifact/build variant dự kiến. Không đưa secret hoặc credential vào thông báo.

## 6. Test condition matrix trên JVM bằng ApplicationContextRunner

`ApplicationContextRunner` phù hợp để kiểm tra nhanh auto-configuration và condition theo nhiều property set. Nó tạo một ApplicationContext riêng cho từng trường hợp, giúp test rõ bean nào phải có hoặc không được có.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            PaymentConfiguration.class,
                            PaymentProviderConsistencyCheck.class);

    @Test
    void cardProviderRegistersOnlyCardGateway() {
        this.contextRunner
                .withPropertyValues("payment.provider=card")
                .run(context -> {
                    assertThat(context).hasSingleBean(CardPaymentGateway.class);
                    assertThat(context).doesNotHaveBean(BankTransferGateway.class);
                    assertThat(context.getBeansOfType(PaymentGateway.class))
                            .containsOnlyKeys("cardGateway");
                });
    }

    @Test
    void bankProviderRegistersOnlyBankGateway() {
        this.contextRunner
                .withPropertyValues("payment.provider=bank")
                .run(context -> {
                    assertThat(context).hasSingleBean(BankTransferGateway.class);
                    assertThat(context).doesNotHaveBean(CardPaymentGateway.class);
                    assertThat(context.getBeansOfType(PaymentGateway.class))
                            .containsOnlyKeys("bankGateway");
                });
    }
}
~~~

Hai test này xác nhận điều kiện Spring hoạt động đúng trên JVM. Chúng hữu ích để kiểm tra từng cấu hình được hỗ trợ trước khi chạy AOT.

**Giới hạn:** `ApplicationContextRunner` tự tạo context ở runtime trong test. Nó không chứng minh generated AOT initializer đã chứa đúng bean set. Vì vậy, cần thêm AOT integration test ở phần tiếp theo.

## 7. Kiểm tra chính xác bean inventory

Không chỉ kiểm tra rằng bean mong muốn tồn tại. Hãy kiểm tra các bean không mong muốn cũng vắng mặt.

Với một nhóm extension type, có thể lấy inventory bằng:

~~~java
Set<String> gatewayBeanNames =
        Arrays.stream(context.getBeanNamesForType(PaymentGateway.class))
                .collect(Collectors.toUnmodifiableSet());
~~~

Sau đó so sánh với tập mong đợi:

~~~java
assertThat(gatewayBeanNames).containsExactlyInAnyOrder("cardGateway");
~~~

Với context dùng bank provider:

~~~java
assertThat(gatewayBeanNames).containsExactlyInAnyOrder("bankGateway");
~~~

Nên giới hạn inventory vào interface hoặc nhóm bean nghiệp vụ cần kiểm tra. So sánh toàn bộ bean names của ApplicationContext thường dễ bị ảnh hưởng bởi infrastructure beans, auto-configuration và khác biệt phiên bản thư viện.

Nếu ứng dụng có nhiều implementation cùng interface theo thiết kế, hãy biểu diễn tập mong đợi theo provider ID hoặc bean name, và xác định rõ bean nào là fallback/default.

## 8. AOT integration test với Spring TestContext

Spring Framework có AOT support cho integration test dùng TestContext Framework. Trong build, test context được phát hiện và mỗi context duy nhất được refresh để xử lý AOT. Spring sinh `ApplicationContextInitializer` cho test context; khi chạy ở AOT mode, test sử dụng context đã tối ưu.

Một test xác nhận bean inventory:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "payment.provider=card")
class PaymentAotBeanSetTests {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void generatedContextContainsOnlyTheCardGateway() {
        assertThat(applicationContext.getBeansOfType(PaymentGateway.class))
                .containsOnlyKeys("cardGateway");
        assertThat(applicationContext.getBeansOfType(BankTransferGateway.class))
                .isEmpty();
    }
}
~~~

Property trong test phải khớp với Environment dùng để AOT xử lý test context. Nếu test có property source, active profile hoặc context customizer khác nhau, những khác biệt đó có thể tạo context AOT khác hoặc khiến runtime không khớp context đã sinh.

Test này kiểm tra bean set trong context AOT đã tạo cho trường hợp card. Để kiểm tra runtime deployment override, cần thêm smoke test chạy ứng dụng AOT với property khác và xác nhận consistency check phát hiện mismatch.

## 9. Chạy test trong AOT mode và native image

Có hai mức xác minh:

1. **AOT runtime trên JVM:** kiểm tra ứng dụng sử dụng generated initialization code.
2. **Native integration test:** kiểm tra test context và code đã biên dịch thành native executable.

### Chạy AOT test trên JVM

Sau khi xử lý test context bằng AOT, chạy test JVM với system property `spring.aot.enabled=true`. Cách cấu hình task hoặc Surefire phụ thuộc build plugin/version của dự án.

Ví dụ Gradle:

~~~bash
./gradlew processTestAot
./gradlew test -Dspring.aot.enabled=true
~~~

Nếu test task fork JVM và không truyền system property từ command line, cấu hình rõ trong build script:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty "spring.aot.enabled", "true"
}
~~~

### Native tests với Gradle

Khi plugin GraalVM Native Image và Spring Boot AOT được cấu hình, task `nativeTest` sử dụng output từ `processAot` và `processTestAot`:

~~~bash
./gradlew nativeTest
~~~

### Native tests với Maven

Với Spring Boot parent/profile đã cấu hình `nativeTest`:

~~~bash
./mvnw test -PnativeTest
~~~

Profile này kích hoạt `process-test-aot` và native test execution theo cấu hình Native Build Tools. Kiểm tra plugin và profile trong project trước khi dùng lệnh; không phải mọi Maven project đều có sẵn cấu hình này.

Native test giúp xác nhận generated test context và runtime native. Tuy nhiên, vẫn cần kiểm tra application artifact cuối cùng với Environment triển khai thật, vì test context có thể dùng property source riêng.

## 10. Kiểm tra runtime property khác với build-time property

Một cách kiểm tra trực tiếp là build artifact với provider card rồi chạy AOT application với provider bank.

### Bước 1: AOT build với provider card

Maven plugin cho phép cấu hình property/profile cho goal `process-aot`. Ví dụ cấu hình plugin:

~~~xml
<execution>
    <id>process-aot</id>
    <goals>
        <goal>process-aot</goal>
    </goals>
    <configuration>
        <systemPropertyVariables>
            <payment.provider>card</payment.provider>
        </systemPropertyVariables>
    </configuration>
</execution>
~~~

Sau đó build theo native profile đã cấu hình:

~~~bash
./mvnw -Pnative package
~~~

Với Gradle, `ProcessAot` là JavaExec task nên có thể cấu hình system property:

~~~groovy
import org.springframework.boot.gradle.tasks.aot.ProcessAot

tasks.withType(ProcessAot).configureEach {
    systemProperty "payment.provider", "card"
}
~~~

Build:

~~~bash
./gradlew nativeCompile
~~~

### Bước 2: chạy với property bank

Trên Linux/macOS, với JVM AOT:

~~~bash
PAYMENT_PROVIDER=bank java -Dspring.aot.enabled=true -jar target/orders-service.jar
~~~

Với native executable:

~~~bash
PAYMENT_PROVIDER=bank ./target/orders-service
~~~

Vì bean set được tạo lúc build chỉ có card provider, consistency check phải báo lỗi rằng `payment.provider=bank` không khớp AOT bean set.

### Bước 3: chạy với cấu hình khớp

~~~bash
PAYMENT_PROVIDER=card ./target/orders-service
~~~

Ứng dụng phải khởi động thành công và inventory chỉ có `cardGateway`.

Ví dụ này là một **negative test có chủ đích**: nó chứng minh property runtime không âm thầm thay đổi tập bean. Trong production, cấu hình build/runtime phải được quản lý đồng bộ; không triển khai artifact card với property bank.

## 11. Kiểm tra profile và profile-specific configuration

`@Profile` được triển khai thông qua condition. Vì vậy, profile ảnh hưởng bean topology phải được chọn khi AOT processing chạy.

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("payment-card")
class CardPaymentConfiguration {
    @Bean
    CardPaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }
}
~~~

Nếu profile `payment-card` được bật trong quá trình AOT, nó sẽ được áp dụng khi chạy AOT. Thay `spring.profiles.active` ở runtime không thể loại bỏ các bean đã được sinh từ profile đó hoặc thêm bean của profile khác.

### Chọn profile lúc AOT với Maven

Goal `process-aot` có cấu hình `profiles`:

~~~xml
<execution>
    <id>process-aot</id>
    <goals>
        <goal>process-aot</goal>
    </goals>
    <configuration>
        <profiles>
            <profile>payment-card</profile>
        </profiles>
    </configuration>
</execution>
~~~

### Chọn profile lúc AOT với Gradle

~~~groovy
import org.springframework.boot.gradle.tasks.aot.ProcessAot

tasks.withType(ProcessAot).configureEach {
    args("--spring.profiles.active=payment-card")
}
~~~

Profile-specific file chỉ thay đổi các property thông thường, không làm thay đổi condition/bean set, có thể tiếp tục được dùng như nguồn cấu hình runtime theo quy tắc property source của Spring. Hãy phân biệt nội dung cấu hình với profile/condition chọn bean.

## 12. Feature toggle runtime không nên điều khiển bean topology

Nếu operator cần bật/tắt một tính năng khi chạy mà không build lại native image, hãy đăng ký service/bean ổn định rồi để property quyết định hành vi.

Không nên:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "reporting",
        name = "enabled",
        havingValue = "true")
ReportExporter reportExporter() {
    return new ReportExporter();
}
~~~

Nếu `reporting.enabled` thay đổi sau AOT build, bean exporter vẫn phản ánh condition lúc build.

Thay vào đó, đăng ký bean không điều kiện:

~~~java
@ConfigurationProperties(prefix = "reporting")
public record ReportingSettings(boolean enabled) {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportingSettings.class)
class ReportingConfiguration {

    @Bean
    ReportExporter reportExporter() {
        return new ReportExporter();
    }
}
~~~

Service đọc setting để quyết định có thực hiện công việc hay không:

~~~java
@Service
public class ReportService {

    private final ReportingSettings settings;
    private final ReportExporter exporter;

    public ReportService(
            ReportingSettings settings,
            ReportExporter exporter) {
        this.settings = settings;
        this.exporter = exporter;
    }

    public ReportResult export(ReportRequest request) {
        if (!settings.enabled()) {
            throw new IllegalStateException("Reporting is disabled");
        }
        return exporter.export(request);
    }
}
~~~

Bean set luôn có `ReportExporter`; property runtime chỉ thay đổi hành vi. Nếu cần cập nhật property ngay khi ứng dụng đang chạy, phải dùng cơ chế refresh/configuration reload phù hợp. `@ConfigurationProperties` thông thường không tự reload mọi thay đổi bên ngoài sau khi bind.

## 13. Các condition khác cũng cần kiểm thử

Đừng chỉ tìm `@ConditionalOnProperty`. Những cơ chế sau cũng có thể làm bean set thay đổi:

- `@Profile`.
- `@ConditionalOnClass` và `@ConditionalOnMissingClass`.
- `@ConditionalOnBean` và `@ConditionalOnMissingBean`.
- `@ConditionalOnResource`.
- `@ConditionalOnExpression`.
- `@Conditional` tùy biến.
- Component scan/import/registrar phụ thuộc Environment hoặc classpath.

Ví dụ `@ConditionalOnClass` phụ thuộc classpath lúc build. Thêm dependency vào runtime container không làm native executable có class đó. Tương tự, `@ConditionalOnResource` được đánh giá khi AOT; một file mới được mount lúc runtime không làm Spring sinh lại bean definition.

Các bean definitions đăng ký bằng callback programmatic cũng cần được xem xét. Spring AOT có hỗ trợ nhiều extension point, nhưng không thể chuyển đổi mọi thao tác thêm singleton hoặc instance supplier tùy ý thành mã generated. Kiểm tra tài liệu AOT cho loại registry callback đang dùng.

## 14. Chẩn đoán condition khi test JVM

Khi condition không cho kết quả mong đợi, hãy xem Condition Evaluation Report. Trong Spring Boot, báo cáo này giải thích auto-configuration/condition nào match hoặc không match và lý do.

Có thể bật debug log khi chạy test hoặc ứng dụng JVM:

~~~properties
debug=true
~~~

Hoặc truyền property khi chạy:

~~~bash
java -Ddebug=true -jar target/orders-service.jar
~~~

Đối với test dùng `ApplicationContextRunner`, có thể kiểm tra context có đúng bean và condition hay không; khi cần, xem `ConditionEvaluationReport` từ bean factory của context.

Lưu ý: Condition Evaluation Report trong một lần chạy JVM thông thường giúp giải thích condition được đánh giá trong lần chạy đó. Khi context dùng generated AOT initializer, không nên kỳ vọng nó đánh giá lại toàn bộ condition như một context JVM mới. Hãy đối chiếu Environment ở build time và generated bean inventory.

## 15. Tổ chức build variant khi bean topology phải khác nhau

Nếu card và bank cần bean definitions, dependencies hoặc proxy hoàn toàn khác nhau, hãy tạo hai AOT/native variants:

~~~text
payment-card:
  AOT profile = payment-card
  bean set = CardPaymentGateway
  artifact = orders-card-native

payment-bank:
  AOT profile = payment-bank
  bean set = BankTransferGateway
  artifact = orders-bank-native
~~~

Mỗi variant phải có:

- Environment/profile được cấu hình rõ trong AOT process.
- Generated AOT sources/resources riêng.
- Native image build riêng.
- Bean inventory tests tương ứng.
- Runtime configuration validation.

Không tái sử dụng output AOT giữa các variant có bean topology khác nhau. Với Maven/Gradle, cần tách output directory hoặc build workspace theo variant để tránh dùng nhầm generated sources của lần build trước.

Nếu chỉ khác endpoint, timeout, API key reference hoặc feature value mà không khác bean set, không cần tạo nhiều native variants; giữ một bean topology ổn định và cấp giá trị cấu hình khi chạy.

## 16. Ma trận kiểm thử đề xuất

| AOT build property | Runtime property | Kết quả mong đợi |
|---|---|---|
| `payment.provider=card` | `payment.provider=card` | Có card bean; startup thành công |
| `payment.provider=card` | `payment.provider=bank` | Bean set vẫn là card; consistency check fail fast |
| `payment.provider=bank` | `payment.provider=bank` | Có bank bean; startup thành công |
| `payment.provider=bank` | `payment.provider=card` | Bean set vẫn là bank; consistency check fail fast |
| `payment.provider=card` | `payment.timeout=5s` thay đổi | Card bean vẫn có; timeout được bind theo giá trị runtime |

Ngoài property chính, nên kiểm tra:

- Active profiles.
- Property source precedence (environment, command line, config file, system property).
- Optional dependencies có ảnh hưởng `@ConditionalOnClass`.
- Các condition tùy biến.
- Configuration properties lồng nhau.
- Runtime flags không được dùng trong điều kiện tạo bean.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JVM test pass nhưng AOT context thiếu bean | Property/profile lúc AOT khác test JVM | Cấu hình Environment cho process AOT và test context |
| Runtime đổi property nhưng bean không đổi | Condition đã được đánh giá ở build time | Rebuild AOT variant hoặc chuyển toggle sang logic runtime |
| Runtime settings nói provider B nhưng context chỉ có provider A | Build/runtime configuration drift | Thêm startup consistency check và đồng bộ cấu hình |
| `@Profile` không hoạt động như mong đợi | Profile ảnh hưởng bean set chưa được bật khi AOT | Chọn profile trong process AOT |
| Một dependency có mặt trong container nhưng condition vẫn không match | Classpath đã cố định khi build | Thêm dependency trước AOT/native build |
| Native test khác JVM test | Test context được xử lý AOT hoặc native runtime khác | Chạy `processTestAot`/`nativeTest` và kiểm tra context configuration |
| Bean xuất hiện hai lần | Nhiều configuration/auto-configuration cùng đăng ký | Kiểm tra condition, bean names và `@ConditionalOnMissingBean` |

## 18. Quy trình kiểm tra trước khi phát hành

~~~mermaid
flowchart TD
    A["Phân loại properties"] --> B["Chọn build-time profiles/conditions"]
    B --> C["Chạy JVM ApplicationContextRunner matrix"]
    C --> D["Chạy processAot / processTestAot"]
    D --> E["Kiểm tra AOT bean inventory"]
    E --> F["Build native executable"]
    F --> G["Chạy runtime config match"]
    G --> H["Chạy runtime config mismatch"]
    H --> I{"Mismatch bị phát hiện sớm?"}
    I -->|Không| J["Sửa validation/test"]
    J --> D
    I -->|Có| K["Kiểm thử container và phát hành"]
~~~

Checklist:

- [ ] Liệt kê mọi property được dùng trong `@Conditional` hoặc `@Profile`.
- [ ] Ghi rõ giá trị/profile dùng cho AOT build.
- [ ] Tách property chọn bean khỏi property chỉ điều khiển hành vi.
- [ ] Kiểm thử condition matrix bằng `ApplicationContextRunner`.
- [ ] Assert cả bean cần có và bean phải vắng mặt.
- [ ] Chạy AOT integration tests với generated TestContext initializer.
- [ ] Kiểm tra bean inventory của context AOT.
- [ ] Thêm startup validation cho property runtime có thể lệch bean topology.
- [ ] Chạy negative test với property runtime cố tình không khớp.
- [ ] Build native image và chạy native tests.
- [ ] Kiểm tra config/environment của container triển khai.
- [ ] Tạo build variant riêng nếu bean topology phải khác nhau.

## 19. Bài tập tự kiểm tra

**Câu 1.** Vì sao `@ConditionalOnProperty` được đánh giá khác nhau giữa JVM thường và AOT?

**Gợi ý:** JVM thường đánh giá khi context khởi động; AOT đánh giá trong build process và sinh bean definitions tương ứng.

**Câu 2.** AOT build với `feature.enabled=true`, runtime đổi thành `false` thì bean có bị xóa không?

**Gợi ý:** không. Bean đã được tạo trong AOT output vẫn được đăng ký; nếu cần toggle runtime, hãy giữ bean và điều khiển hành vi bằng property.

**Câu 3.** Vì sao cần kiểm tra cả bean tồn tại và bean vắng mặt?

**Gợi ý:** chỉ assert bean mong muốn có thể bỏ sót implementation khác cũng được đăng ký, gây ambiguous injection hoặc chọn nhầm provider.

**Câu 4.** `ApplicationContextRunner` có đủ để chứng minh generated AOT context đúng không?

**Gợi ý:** không. Nó kiểm tra condition trong context JVM được tạo trực tiếp; cần thêm AOT integration test dùng generated initializer.

**Câu 5.** Nếu build-time provider là card nhưng runtime provider là bank, nên xử lý thế nào?

**Gợi ý:** bean set vẫn là card. Startup validator nên phát hiện mismatch và dừng ứng dụng; nếu cần bank, build AOT/native variant cho bank.

**Câu 6.** Property nào có thể thay đổi runtime mà không làm thay bean set?

**Gợi ý:** các giá trị như endpoint, timeout, giới hạn request hoặc feature setting được bean đã đăng ký đọc, miễn là chúng không tham gia condition tạo bean.

## 20. Tài liệu tham khảo

- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/how-to/aot.html): condition được đánh giá ở build time, profiles và property không ảnh hưởng condition.
- [Spring Boot — Ahead-of-Time Processing with Maven](https://docs.spring.io/spring-boot/maven-plugin/aot.html): goal `process-aot`, `profiles`, `systemPropertyVariables` và `process-test-aot`.
- [Spring Boot — Ahead-of-Time Processing with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/aot.html): task `processAot`, `ProcessAot`, `processTestAot` và `nativeTest`.
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): giới hạn bean definitions, classpath và Environment trong AOT.
- [Spring Framework — Ahead-of-Time Support for Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/aot.html): xử lý TestContext ở build time và chạy AOT-optimized context khi test.

**Ghi nhớ:** Spring AOT cố định bean topology theo classpath và Environment lúc build. Property runtime vẫn có thể điều khiển giá trị/hành vi của bean đã có, nhưng không làm `@Conditional` được đánh giá lại. Hãy kiểm thử condition matrix trên JVM, xác minh bean inventory trong AOT context, thêm startup validation cho cấu hình có thể lệch và build native variants riêng khi tập bean thực sự cần khác nhau.
