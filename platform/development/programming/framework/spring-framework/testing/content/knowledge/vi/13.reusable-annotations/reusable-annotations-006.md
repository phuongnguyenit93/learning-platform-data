# @EnabledIf, @DisabledIf và điều kiện từ Spring

Trong một test suite, có những bài kiểm thử chỉ phù hợp với một môi trường nhất định. Ví dụ, test tích hợp cần dịch vụ bên ngoài chỉ nên chạy khi CI đã bật nhóm test tương ứng; test cần một bean hoặc cấu hình đặc biệt chỉ có ý nghĩa khi feature flag đang bật; một test có thể tạm thời không chạy trong thời gian hệ thống bảo trì. JUnit Jupiter cung cấp nhiều cơ chế điều kiện để bật hoặc bỏ qua test. Spring TestContext Framework bổ sung @EnabledIf và @DisabledIf, cho phép diễn đạt điều kiện bằng Spring Expression Language (SpEL) hoặc thuộc tính trong Spring Environment.

Hai annotation này là điều kiện thực thi của JUnit Jupiter. Chúng quyết định một test class hoặc test method có được chạy hay không dựa trên biểu thức đã khai báo. Chúng không quyết định bean nào được đăng ký trong ApplicationContext; nhiệm vụ đó thuộc về các cơ chế cấu hình Spring như @Profile, @Conditional và các điều kiện đăng ký bean khác.

## 1. Vai trò của @EnabledIf và @DisabledIf

@EnabledIf cho phép test chạy khi biểu thức trả về giá trị đúng. @DisabledIf bỏ qua test khi biểu thức trả về giá trị đúng.

| Annotation | Biểu thức đúng | Biểu thức không đúng |
|---|---|---|
| @EnabledIf | Test được bật và có thể chạy | Test bị bỏ qua |
| @DisabledIf | Test bị bỏ qua | Test được phép chạy |

Điều kiện được đánh giá bởi JUnit Jupiter trước khi thực thi test container hoặc test method tương ứng. Khi đặt annotation trên class, điều kiện áp dụng cho các test method bên trong class đó. Khi đặt trên method, điều kiện chỉ áp dụng cho method được đánh dấu.

Ví dụ, một nhóm test kiểm tra hệ thống thanh toán thật có thể chỉ chạy khi tiến trình test được bật cờ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@EnabledIf(
        expression = "#{systemProperties['tests.external'] == 'true'}",
        reason = "External integration tests are enabled only on demand"
)
class ExternalPaymentIntegrationTest {
    @Test
    void chargesThroughTheExternalGateway() {
        // Test gọi cổng thanh toán trong môi trường tích hợp đã chuẩn bị.
    }
}
~~~

Khi chạy JVM với system property tests.external=true, biểu thức đúng và các test trong class được bật. Nếu property không được đặt hoặc có giá trị khác true, điều kiện không thỏa mãn và test class bị bỏ qua. Với điều kiện chỉ dựa trên system property, không cần tải Spring ApplicationContext chỉ để đánh giá biểu thức.

Có thể dùng @DisabledIf để bỏ qua một test trong thời gian một chế độ bảo trì được bật:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.DisabledIf;

class InventoryMaintenanceTest {
    @Test
    @DisabledIf(
            expression = "#{systemProperties['inventory.maintenance'] == 'true'}",
            reason = "Inventory writes are unavailable during maintenance"
    )
    void updatesInventory() {
        // Kiểm tra thao tác ghi tồn kho.
    }
}
~~~

Khi inventory.maintenance=true, method bị bỏ qua. Khi điều kiện không đúng, method được phép chạy.

## 2. Đúng package và phạm vi hỗ trợ

Annotation của Spring nằm trong package:

~~~java
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.DisabledIf;
~~~

Spring cung cấp chúng trong Spring TestContext Framework để tích hợp với JUnit Jupiter. Chúng được giới thiệu từ Spring Framework 5.0 và được dùng cùng Spring Extension. Nếu test cần cấu hình Spring, có thể đăng ký extension bằng @SpringJUnitConfig hoặc bằng cặp @ExtendWith(SpringExtension.class) và @ContextConfiguration.

Ví dụ cấu hình thông dụng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@SpringJUnitConfig(FeatureTestConfig.class)
@EnabledIf(expression = "#{systemProperties['feature.tests'] == 'true'}")
class FeatureIntegrationTest {
    @Test
    void verifiesFeatureIntegration() {
        // Kiểm tra tích hợp feature.
    }
}
~~~

Từ JUnit Jupiter 5.7, JUnit cũng có annotation điều kiện mang tên @EnabledIf và @DisabledIf. Vì vậy, khi dùng annotation của Spring, hãy import rõ package org.springframework.test.context.junit.jupiter. IDE có thể tự chọn nhầm kiểu cùng tên từ package JUnit nếu không kiểm tra import.

Hai annotation Spring này dành cho mô hình JUnit Jupiter. Không nên giả định chúng hoạt động như annotation điều kiện chung cho JUnit 4 hoặc TestNG. Với test dùng JUnit 4, Spring từng có cơ chế điều kiện theo profile riêng như @IfProfileValue; đó là API khác và không nên trộn với annotation dành cho JUnit Jupiter.

## 3. Biểu thức được hỗ trợ

Thuộc tính expression của hai annotation chấp nhận ba dạng chính:

1. Biểu thức Spring Expression Language (SpEL).
2. Placeholder cho một property có trong Spring Environment.
3. Một text literal.

Kết quả được xem là đúng nếu biểu thức trả về Boolean.TRUE hoặc một String bằng true, không phân biệt chữ hoa và chữ thường. Những kết quả khác không thỏa mãn điều kiện bật của @EnabledIf hoặc điều kiện tắt của @DisabledIf.

### 3.1. Spring Expression Language (SpEL)

SpEL hữu ích khi điều kiện là một biểu thức logic dựa trên system properties, trạng thái bean hoặc giá trị mà Spring có thể truy cập.

Ví dụ kiểm tra hệ điều hành:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@EnabledIf(
        expression = "#{systemProperties['os.name'].toLowerCase().contains('mac')}",
        reason = "This test requires a macOS environment"
)
class MacSpecificIntegrationTest {
    @Test
    void usesMacSpecificIntegration() {
        // Test chỉ chạy trên macOS.
    }
}
~~~

Trong SpEL, systemProperties cho phép đọc các system property của JVM. Biểu thức gọi toLowerCase() trên tên hệ điều hành rồi kiểm tra chuỗi có chứa mac hay không. Đây là ví dụ minh họa khả năng của SpEL; nếu chỉ cần chọn hệ điều hành, các annotation có sẵn của JUnit như @EnabledOnOs thường ngắn gọn và rõ mục đích hơn.

Có thể kiểm tra một cờ được truyền từ command line:

~~~java
@EnabledIf(
        expression = "#{systemProperties['tests.database.integration'] == 'true'}",
        reason = "Database integration tests require an explicit opt-in"
)
class DatabaseIntegrationTest {
    @Test
    void queriesTheConfiguredDatabase() {
        // Test tích hợp với database.
    }
}
~~~

Chạy test với:

~~~text
-Dtests.database.integration=true
~~~

Nếu cần dùng bean trong ApplicationContext, SpEL có thể tham chiếu bean theo tên. Khi đó, context phải được tải để bean tồn tại:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(FeatureTestConfig.class)
@EnabledIf(
        expression = "#{@testCapabilities.externalServiceAvailable}",
        loadContext = true,
        reason = "The external service is available in this test environment"
)
class ExternalServiceTest {
    @Test
    void callsTheExternalService() {
        // Kiểm tra tích hợp dựa trên khả năng do bean cung cấp.
    }
}
~~~

Trong ví dụ, testCapabilities là bean có thuộc tính externalServiceAvailable, chẳng hạn được cung cấp bởi phương thức isExternalServiceAvailable(). SpEL đọc thuộc tính của bean để quyết định có bật test hay không. Thuộc tính loadContext = true yêu cầu Spring tải context trước khi đánh giá biểu thức.

### 3.2. Placeholder từ Spring Environment

Nếu điều kiện chỉ phụ thuộc vào một property, placeholder dạng đô-la và dấu ngoặc nhọn thường dễ đọc hơn SpEL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(FeatureTestConfig.class)
@TestPropertySource(properties = "tests.smoke.enabled=true")
@EnabledIf(
        expression = "${tests.smoke.enabled:false}",
        loadContext = true,
        reason = "Smoke tests are enabled by the test configuration"
)
class SmokeTest {
    @Test
    void verifiesTheSmokeScenario() {
        // Smoke test.
    }
}
~~~

Spring thay placeholder bằng giá trị của property trong Environment. Trong ví dụ, @TestPropertySource cung cấp giá trị true. Phần :false là giá trị mặc định nếu property không được khai báo, giúp điều kiện không phụ thuộc vào việc mọi môi trường đều phải có property đó.

Khi property được cung cấp bởi cấu hình của test context, chẳng hạn @TestPropertySource hoặc một context initializer, dùng loadContext = true để bảo đảm context và Environment tương ứng sẵn sàng trước khi biểu thức cần đến chúng. Với điều kiện chỉ đọc system properties hoặc environment variables của tiến trình và không truy cập bean/context, có thể giữ mặc định loadContext = false.

Có thể dùng placeholder cho một property môi trường để bỏ qua nhóm test không phù hợp:

~~~java
@DisabledIf(
        expression = "${tests.external-service.disabled:false}",
        loadContext = true,
        reason = "The external service is disabled in this environment"
)
class ExternalServiceContractTest {
    @Test
    void verifiesTheExternalServiceContract() {
        // Contract test.
    }
}
~~~

Nếu tests.external-service.disabled là true, test bị bỏ qua. Nếu property không tồn tại, giá trị mặc định false khiến điều kiện không vô hiệu hóa test.

### 3.3. Text literal

Một biểu thức cũng có thể là text literal:

~~~java
@EnabledIf("true")
class AlwaysEnabledTest {
}

@DisabledIf("true")
class AlwaysDisabledTest {
}
~~~

Các literal này thường không đem lại giá trị vì @EnabledIf("true") tương đương một test luôn được bật, còn @DisabledIf("true") tương đương một test luôn bị bỏ qua. Spring khuyến nghị dùng biểu thức động hoặc property placeholder để điều kiện phản ánh môi trường thực tế.

## 4. Các thuộc tính của annotation

Hai annotation Spring có các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| expression | Biểu thức được đánh giá để quyết định điều kiện bật hoặc tắt |
| value | Alias của expression, thường dùng cho cách khai báo ngắn |
| reason | Lý do gắn với kết quả điều kiện |
| loadContext | Có yêu cầu tải ApplicationContext trước khi đánh giá biểu thức hay không |

### expression và value

value là alias của expression. Hai cách khai báo sau tương đương khi không cần cấu hình thêm thuộc tính:

~~~java
@EnabledIf("#{systemProperties['ci'] == 'true'}")
class CiOnlyTest {
}

@EnabledIf(expression = "#{systemProperties['ci'] == 'true'}")
class CiOnlyTestWithExpression {
}
~~~

Khi cần khai báo reason hoặc loadContext, nên dùng tên expression để thể hiện rõ ý định:

~~~java
@EnabledIf(
        expression = "${tests.integration.enabled:false}",
        loadContext = true,
        reason = "Integration environment is configured"
)
class ConfiguredIntegrationTest {
}
~~~

Trong API của Spring, value và expression là hai tên thay thế cho cùng một giá trị. Không truyền hai giá trị khác nhau cho cả hai thuộc tính.

### reason

reason giúp JUnit báo cáo lý do gắn với điều kiện. Với @DisabledIf, đây là thông tin hữu ích để người đọc báo cáo biết tại sao test bị bỏ qua. Với @EnabledIf, reason mô tả lý do test được bật khi điều kiện đúng.

~~~java
@DisabledIf(
        expression = "#{systemProperties['external.api.offline'] == 'true'}",
        reason = "External API is unavailable in this test run"
)
class ExternalApiTest {
}
~~~

Nên viết reason ngắn, nêu điều kiện môi trường hoặc phụ thuộc cần thiết. Điều này giúp phân biệt một test bị bỏ qua có chủ đích với một test chưa được cấu hình đúng.

### loadContext

loadContext quyết định Spring có chủ động tải ApplicationContext gắn với test để đánh giá biểu thức hay không. Giá trị mặc định là false.

| Trường hợp | Giá trị nên cân nhắc |
|---|---|
| Chỉ đọc systemProperties | false |
| Chỉ đọc environment variables của tiến trình | false |
| Biểu thức không truy cập bean trong context | Thường là false |
| SpEL tham chiếu bean trong ApplicationContext | true |
| Property chỉ có trong cấu hình riêng của test context | true |

Giữ loadContext = false khi không cần context giúp tránh khởi tạo toàn bộ ứng dụng chỉ để quyết định bỏ qua test. Nếu điều kiện cần bean hoặc cấu hình chỉ xuất hiện khi context được tạo, đặt true để Spring có thể cung cấp các thành phần đó.

Không nên đặt loadContext = true theo thói quen cho mọi test. Nếu điều kiện cuối cùng là false, việc tải context trước khi bỏ qua test vẫn tiêu tốn thời gian và có thể khởi tạo database, connection pool hoặc các thành phần tích hợp khác.

## 5. Áp dụng ở cấp class và cấp method

Có thể đặt @EnabledIf hoặc @DisabledIf trên test class hoặc test method.

### Điều kiện ở cấp class

Khi annotation được đặt trên class, điều kiện áp dụng cho các test method bên trong class. Cách này phù hợp khi toàn bộ nhóm test có cùng yêu cầu môi trường.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@EnabledIf(
        expression = "#{systemProperties['tests.payment.integration'] == 'true'}",
        reason = "Payment integration suite requires an explicit opt-in"
)
class PaymentIntegrationTests {
    @Test
    void authorizesPayment() {
        // ...
    }

    @Test
    void refundsPayment() {
        // ...
    }
}
~~~

Khi điều kiện ở cấp class không thỏa mãn, JUnit bỏ qua class container và các method bên trong không được thực thi. Khi điều kiện thỏa mãn, các method được phép chạy và vẫn chịu ảnh hưởng của những điều kiện khác nếu có.

### Điều kiện ở cấp method

Khi chỉ một tình huống cần điều kiện riêng, đặt annotation trên method:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.DisabledIf;

class PaymentServiceTests {
    @Test
    void calculatesTheFee() {
        // Test logic không phụ thuộc hệ thống bên ngoài.
    }

    @Test
    @EnabledIf(
            expression = "#{systemProperties['tests.payment.gateway'] == 'true'}",
            reason = "A payment gateway is available for this run"
    )
    void sendsPaymentToGateway() {
        // Test tích hợp với gateway.
    }

    @Test
    @DisabledIf(
            expression = "#{systemProperties['tests.payment.readOnly'] == 'true'}",
            reason = "The configured payment environment is read-only"
    )
    void changesPaymentState() {
        // Test cần thay đổi trạng thái payment.
    }
}
~~~

Trong cùng một class, test logic thuần túy vẫn chạy bình thường; chỉ những method có điều kiện riêng mới bị giới hạn. Cách tổ chức này giữ các yêu cầu hạ tầng gần với test thực sự cần chúng.

### Kết hợp điều kiện class và method

JUnit đánh giá các điều kiện áp dụng cho container và method. Nếu điều kiện ở cấp class không cho phép chạy, method bên trong không thể chạy chỉ nhờ điều kiện riêng ở cấp method. Nếu class được bật, điều kiện method tiếp tục quyết định method cụ thể có được thực thi hay không.

Hãy giữ điều kiện dễ hiểu và tránh đặt các biểu thức mâu thuẫn trên cùng một phạm vi. Nếu một nhóm test luôn cần cùng profile hoặc cấu hình bean, có thể dùng cấu hình test riêng; nếu chỉ một method cần phụ thuộc tùy chọn, đặt điều kiện ở method để phạm vi bị giới hạn rõ ràng.

## 6. Dùng điều kiện dựa trên Spring bean

Một ưu điểm của Spring @EnabledIf và @DisabledIf là biểu thức SpEL có thể tham chiếu bean khi context được tải. Điều này hữu ích khi khả năng chạy test phụ thuộc vào một thành phần đã được cấu hình trong ứng dụng, ví dụ adapter tích hợp, feature capability hoặc thông tin về môi trường.

Ví dụ cấu hình bean cung cấp trạng thái khả dụng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class FeatureTestConfig {
    @Bean
    TestCapabilities testCapabilities(Environment environment) {
        boolean available = environment.getProperty(
                "external.service.available",
                Boolean.class,
                false);
        return new TestCapabilities(available);
    }
}

class TestCapabilities {
    private final boolean externalServiceAvailable;

    TestCapabilities(boolean externalServiceAvailable) {
        this.externalServiceAvailable = externalServiceAvailable;
    }

    public boolean isExternalServiceAvailable() {
        return externalServiceAvailable;
    }
}
~~~

Test tham chiếu bean testCapabilities trong SpEL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(FeatureTestConfig.class)
@TestPropertySource(properties = "external.service.available=true")
@EnabledIf(
        expression = "#{@testCapabilities.externalServiceAvailable}",
        loadContext = true,
        reason = "The external service capability is available"
)
class ExternalCapabilityTest {
    @Test
    void runsTheCapabilityDependentScenario() {
        // Kiểm tra hành vi cần dịch vụ bên ngoài.
    }
}
~~~

Spring tạo context, đăng ký bean testCapabilities, sau đó SpEL đọc thuộc tính externalServiceAvailable. Vì biểu thức cần bean trong context, loadContext = true là cần thiết.

Điều kiện dựa trên bean nên chỉ dùng khi trạng thái đó thật sự là một phần của cấu hình test. Không nên dùng bean điều kiện để thực hiện một kết nối mạng tốn kém hoặc một thao tác có side effect chỉ nhằm quyết định có chạy test hay không. Nếu cần xác nhận dịch vụ thật có hoạt động, cân nhắc một health check nhẹ, một bước setup riêng hoặc để integration test thực hiện kiểm tra kết nối và báo lỗi rõ ràng.

## 7. Dùng property và profile để chọn nhóm test

Điều kiện từ Spring thường phối hợp với @ActiveProfiles, @TestPropertySource và @DynamicPropertySource.

### Profile chọn cấu hình bean

@ActiveProfiles xác định profile cho test context. @Profile trên cấu hình bean quyết định bean nào được đăng ký. @EnabledIf có thể đọc property hoặc trạng thái liên quan để quyết định một nhóm test có được chạy không.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
class ExternalClientTestConfig {
    @Bean
    @Profile("integration")
    ExternalClient externalClient() {
        return new RealExternalClient();
    }
}
~~~

Test dùng profile integration:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@SpringJUnitConfig(ExternalClientTestConfig.class)
@ActiveProfiles("integration")
@EnabledIf(
        expression = "${tests.external.enabled:false}",
        loadContext = true,
        reason = "External integration tests are enabled by configuration"
)
class ExternalClientIntegrationTest {
    @Test
    void callsTheConfiguredClient() {
        // Kiểm tra client được cấu hình cho profile integration.
    }
}
~~~

Profile và điều kiện test có hai vai trò:

- @ActiveProfiles("integration") chọn profile dùng khi tạo context.
- @Profile("integration") chọn bean được đăng ký trong context.
- @EnabledIf quyết định test có chạy trong lần test hiện tại hay không.

Nếu profile integration đã đủ để xác định môi trường chạy test, có thể dùng một property rõ nghĩa để bật/tắt test. Không nên dùng điều kiện test thay thế profile hoặc dùng profile chỉ để biểu diễn một cờ bật/tắt method.

### Property đến từ TestPropertySource

@TestPropertySource phù hợp với property cố định của một nhóm test:

~~~java
@SpringJUnitConfig(ExternalClientTestConfig.class)
@TestPropertySource(properties = {
        "tests.external.enabled=true",
        "external.client.mode=stub"
})
@EnabledIf(
        expression = "${tests.external.enabled:false}",
        loadContext = true
)
class ConfiguredExternalClientTest {
}
~~~

Khi property được thay đổi theo môi trường CI, có thể truyền property vào JVM hoặc cấu hình test task. Điều kiện sẽ phản ánh giá trị được Spring Environment phân giải theo thứ tự ưu tiên của các property source.

### Property động từ DynamicPropertySource

Nếu test dùng Testcontainers hoặc một dịch vụ có cổng runtime, @DynamicPropertySource có thể đăng ký giá trị động vào Environment. Điều kiện có thể đọc property đó nếu việc bật test thực sự phụ thuộc vào giá trị đã được đăng ký.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ExternalClientTestConfig.class)
class ContainerBackedIntegrationTest {
    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("external.service.enabled", () -> true);
    }

    @Test
    @EnabledIf(
            expression = "${external.service.enabled:false}",
            loadContext = true
    )
    void callsTheContainerBackedService() {
        // Kiểm tra tích hợp khi property động đã được đăng ký.
    }
}
~~~

Ví dụ trên minh họa cách property động tham gia Spring Environment. Trong dự án thực tế, lifecycle của container và việc đăng ký property cần được tổ chức sao cho tài nguyên đã sẵn sàng khi context được tạo. Nếu điều kiện chỉ nhằm xác định container có thể khởi động hay không, nên cân nhắc để test setup hoặc Testcontainers quản lý việc đó thay vì tạo thêm một điều kiện phụ thuộc vòng đời phức tạp.

## 8. Tạo annotation điều kiện dùng lại

Spring cho phép dùng @EnabledIf và @DisabledIf như meta-annotation để tạo annotation tổng hợp. Cách này hữu ích khi nhiều test class cùng tuân theo một điều kiện.

Ví dụ tạo annotation cho nhóm test phụ thuộc dịch vụ ngoài:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@Target({ElementType.TYPE, ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@EnabledIf(
        expression = "${tests.external.enabled:false}",
        loadContext = true,
        reason = "External integration tests are enabled by configuration"
)
public @interface EnabledForExternalIntegration {
}
~~~

Dùng annotation tổng hợp:

~~~java
@SpringJUnitConfig(ExternalClientTestConfig.class)
@EnabledForExternalIntegration
class ExternalClientContractTest {
    @Test
    void verifiesTheClientContract() {
        // ...
    }
}
~~~

Có thể tạo annotation để bỏ qua test trong một chế độ cụ thể:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.junit.jupiter.DisabledIf;

@Target({ElementType.TYPE, ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@DisabledIf(
        expression = "${tests.database.readOnly:false}",
        loadContext = true,
        reason = "Database write tests are disabled in read-only mode"
)
public @interface DisabledInReadOnlyDatabaseMode {
}
~~~

Các annotation tổng hợp giúp chuẩn hóa điều kiện và reason trong một test suite. Hãy đặt tên theo ý nghĩa nghiệp vụ hoặc môi trường, chẳng hạn @EnabledForExternalIntegration, thay vì để mọi test lặp lại cùng một biểu thức SpEL dài.

## 9. Phân biệt điều kiện Spring với annotation điều kiện của JUnit

JUnit Jupiter có sẵn nhiều annotation điều kiện cho những trường hợp phổ biến. Nếu điều kiện chỉ dựa trên hệ điều hành, system property hoặc environment variable, annotation của JUnit thường là lựa chọn trực tiếp hơn.

| Nhu cầu | Annotation có thể dùng |
|---|---|
| Chỉ chạy trên một hệ điều hành | @EnabledOnOs, @DisabledOnOs |
| Chỉ chạy khi system property có giá trị nhất định | @EnabledIfSystemProperty, @DisabledIfSystemProperty |
| Chỉ chạy khi environment variable có giá trị nhất định | @EnabledIfEnvironmentVariable, @DisabledIfEnvironmentVariable |
| Điều kiện cần SpEL hoặc property từ Spring Environment | Spring @EnabledIf, @DisabledIf |
| Điều kiện cần đọc bean trong ApplicationContext | Spring @EnabledIf hoặc @DisabledIf với loadContext = true |

Ví dụ, nếu chỉ cần test chạy trên Linux, JUnit cung cấp annotation chuyên dụng:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;

class LinuxSpecificTest {
    @Test
    @EnabledOnOs(OS.LINUX)
    void usesLinuxSpecificFeature() {
        // ...
    }
}
~~~

Nếu chỉ cần kiểm tra biến môi trường CI, có thể dùng:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

class CiOnlyTest {
    @Test
    @EnabledIfEnvironmentVariable(
            named = "CI",
            matches = "true"
    )
    void runsInCi() {
        // ...
    }
}
~~~

Spring @EnabledIf hữu ích khi điều kiện cần kết hợp nhiều giá trị, cần cú pháp SpEL, hoặc phải đọc property/bean từ Spring context. Với điều kiện đơn giản mà JUnit đã hỗ trợ trực tiếp, annotation của JUnit thường làm ý định rõ hơn và không yêu cầu đánh giá biểu thức Spring.

## 10. Phân biệt điều kiện chạy test với điều kiện đăng ký bean

Các annotation có chữ If có thể xuất hiện ở nhiều tầng, nhưng chúng không thay thế nhau.

| Cơ chế | Tác động | Ví dụ |
|---|---|---|
| @EnabledIf / @DisabledIf | Quyết định test class hoặc method có được chạy | Bỏ qua test tích hợp khi feature chưa sẵn sàng |
| @Profile | Chọn bean theo profile active | Chọn fake gateway trong profile test |
| @Conditional | Quyết định bean definition có được đăng ký hay không | Chỉ đăng ký adapter khi classpath hoặc property phù hợp |
| JUnit assumption | Dừng một test đang chạy khi giả định runtime không thỏa mãn | Bỏ qua một nhánh sau khi test đã kiểm tra trạng thái thực tế |

Ví dụ @Profile:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
class GatewayConfiguration {
    @Bean
    @Profile("test")
    PaymentGateway fakeGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("production")
    PaymentGateway realGateway() {
        return new RealPaymentGateway();
    }
}
~~~

Profile quyết định bean nào được tạo khi context khởi động. @EnabledIf quyết định test nào được chạy. Có thể dùng cả hai trong một test suite, nhưng mỗi annotation phải làm đúng nhiệm vụ của nó.

JUnit assumptions như Assumptions.assumeTrue() phù hợp khi điều kiện chỉ biết được trong lúc test method đang thực thi, chẳng hạn một phép kiểm tra nhanh trên tài nguyên đã kết nối. Ngược lại, @EnabledIf phù hợp với điều kiện có thể đánh giá trước khi chạy test method và có thể áp dụng cho cả class.

## 11. Xử lý lỗi khi đánh giá điều kiện

Điều kiện không nên là nơi che giấu lỗi cấu hình. Nếu biểu thức không thể phân giải, placeholder bị thiếu hoặc SpEL sai cú pháp, quá trình đánh giá điều kiện có thể thất bại và JUnit báo lỗi thay vì đơn giản bỏ qua test.

Một số vấn đề thường gặp:

### Import nhầm annotation

JUnit Jupiter và Spring có annotation cùng tên. Kiểm tra import phải là org.springframework.test.context.junit.jupiter.EnabledIf hoặc DisabledIf nếu muốn dùng biểu thức Spring.

### Property placeholder không tồn tại

Nếu khai báo property tests.integration.enabled nhưng môi trường không cung cấp property, Spring có thể không phân giải được placeholder. Có thể khai báo property ở @TestPropertySource, file cấu hình hoặc command line; nếu property tùy chọn, dùng giá trị mặc định false trong placeholder.

### SpEL trả về kiểu không đúng

Điều kiện cần trả về Boolean.TRUE hoặc chuỗi true không phân biệt hoa thường. Một biểu thức trả về đối tượng tùy ý hoặc chuỗi khác không làm điều kiện trở thành đúng. Hãy viết phép so sánh boolean rõ ràng:

~~~java
@EnabledIf(
        expression = "#{systemProperties['tests.external'] == 'true'}"
)
class ExternalTest {
}
~~~

### Bean tham chiếu chưa tồn tại

Nếu SpEL tham chiếu testCapabilities nhưng cấu hình không đăng ký bean đó, điều kiện không thể đánh giá thành công. Kiểm tra lớp cấu hình, component scan, profile và loadContext = true.

### Tải context không cần thiết

Nếu điều kiện chỉ đọc system property mà đặt loadContext = true, Spring có thể khởi tạo toàn bộ context trước khi bỏ qua test. Bỏ cờ này nếu không cần bean hoặc cấu hình trong context.

### Điều kiện quá phức tạp

Một biểu thức dài có nhiều phép gọi bean, truy cập hệ thống và nhánh logic sẽ khó chẩn đoán. Chuyển logic phức tạp thành một bean hoặc property có tên rõ ràng, sau đó để biểu thức chỉ đọc một giá trị boolean.

### Bỏ qua test thay vì báo lỗi môi trường

Nếu một integration test bắt buộc phải có database hoặc dịch vụ ngoài trong pipeline, điều kiện tắt test khi dependency không có có thể che giấu lỗi cấu hình CI. Chỉ dùng điều kiện bỏ qua khi việc không chạy là một trạng thái hợp lệ và có chủ đích. Nếu dependency bắt buộc, để test khởi chạy và báo lỗi rõ ràng khi môi trường thiếu.

## 12. Quy trình chọn điều kiện phù hợp

Khi quyết định có dùng @EnabledIf hoặc @DisabledIf, hãy xác định nguồn dữ liệu và phạm vi điều kiện:

1. Nếu điều kiện là hệ điều hành, system property hoặc environment variable đơn giản, xem xét annotation điều kiện có sẵn của JUnit.
2. Nếu điều kiện cần SpEL, property trong Spring Environment hoặc bean trong context, dùng annotation của Spring.
3. Nếu toàn bộ class có cùng yêu cầu môi trường, đặt điều kiện ở class; nếu chỉ một method phụ thuộc, đặt ở method.
4. Nếu biểu thức cần bean hoặc context-specific property, đặt loadContext = true; nếu chỉ đọc system properties hoặc environment variables, giữ mặc định false.
5. Dùng reason để giải thích điều kiện cho người đọc báo cáo test.
6. Với property tùy chọn, cung cấp giá trị mặc định hoặc khai báo rõ property trong cấu hình test.
7. Nếu cùng điều kiện xuất hiện nhiều nơi, tạo composed annotation có tên thể hiện mục đích.
8. Không dùng điều kiện để che giấu dependency bắt buộc bị thiếu trong CI hoặc môi trường tích hợp.
9. Dùng @Profile hoặc @Conditional cho lựa chọn bean; dùng @EnabledIf hoặc @DisabledIf cho việc chạy test.
10. Khi điều kiện bị đánh giá lỗi, kiểm tra import, placeholder, SpEL, bean và loadContext trước khi thay đổi logic nghiệp vụ.

## 13. Nguyên tắc cần ghi nhớ

- Spring @EnabledIf bật test khi biểu thức trả về Boolean.TRUE hoặc chuỗi true; @DisabledIf bỏ qua test khi biểu thức trả về giá trị đó.
- Hai annotation hỗ trợ SpEL, placeholder trong Spring Environment và text literal.
- Annotation có thể đặt ở cấp class hoặc method; class-level condition áp dụng cho các test method bên trong class.
- Dùng import từ org.springframework.test.context.junit.jupiter để tránh nhầm annotation cùng tên của JUnit.
- expression và value là alias; dùng expression khi cần khai báo reason hoặc loadContext.
- reason giúp giải thích trạng thái điều kiện trong báo cáo test.
- loadContext mặc định là false; chỉ bật khi biểu thức cần bean hoặc cấu hình gắn với ApplicationContext.
- Ưu tiên annotation JUnit chuyên dụng cho điều kiện đơn giản như hệ điều hành, system property và environment variable.
- Phân biệt điều kiện chạy test với @Profile và @Conditional, vốn quyết định bean được đăng ký.
- Không dùng điều kiện để biến một dependency bắt buộc thành dependency tùy chọn một cách âm thầm.
- Giữ biểu thức ngắn, có giá trị mặc định phù hợp và có reason rõ ràng để test suite dễ vận hành.

@EnabledIf và @DisabledIf bổ sung khả năng điều khiển test dựa trên biểu thức và cấu hình Spring. Khi chọn đúng nguồn dữ liệu, đặt điều kiện ở đúng phạm vi và chỉ tải context khi cần, chúng giúp một test suite hỗ trợ nhiều môi trường mà vẫn thể hiện rõ vì sao một test được chạy hoặc bị bỏ qua.

## Tài liệu tham khảo

- [Spring Framework Reference — Spring JUnit Jupiter Testing Annotations](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-junit-jupiter.html)
- [Spring Framework Javadoc 6.2 — EnabledIf](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/test/context/junit/jupiter/EnabledIf.html)
- [Spring Framework Javadoc 6.0 — DisabledIf](https://docs.spring.io/spring-framework/docs/6.0.19/javadoc-api/org/springframework/test/context/junit/jupiter/DisabledIf.html)
- [Spring Framework Reference — Meta-Annotation Support for Testing](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-meta.html)
