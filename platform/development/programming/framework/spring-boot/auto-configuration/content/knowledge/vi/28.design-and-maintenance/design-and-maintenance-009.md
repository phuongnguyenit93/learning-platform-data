# Dùng kiểm thử hồi quy để bảo vệ giao ước nhường chỗ và tương thích

> **Mục tiêu:** Xây dựng bộ kiểm thử hồi quy chứng minh auto-configuration giữ đúng giao ước công khai: cung cấp bean mặc định khi phù hợp, nhường chỗ cho bean do ứng dụng khai báo, tôn trọng property/classpath/context conditions và tiếp tục hoạt động trên mọi phiên bản Spring Boot mà thư viện cam kết hỗ trợ.

Bài học thuộc nhóm **Thiết kế và bảo trì**, dùng Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+, JUnit Jupiter và AssertJ. Trọng tâm là biến quy tắc back-off thành test có thể chạy lặp lại trong CI. Một lần kiểm thử khởi động thành công chưa đủ để bảo vệ starter; cần kiểm tra trường hợp mặc định, override, điều kiện biên, discovery từ JAR và ma trận phiên bản.

## 1. Giao ước nhường chỗ là một phần của API starter

Auto-configuration cung cấp cấu hình tiện lợi để ứng dụng bắt đầu sử dụng thư viện mà không phải tự khai báo mọi bean. Nhưng người dùng cần quyền thay thế mặc định bằng implementation phù hợp với ứng dụng.

Ví dụ:

~~~java
@AutoConfiguration
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    DefaultPaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Giao ước mà starter cần giữ:

1. Nếu không có bean kiểu PaymentGateway do ứng dụng hoặc cấu hình khác cung cấp, starter đăng ký default.
2. Nếu ứng dụng cung cấp một bean PaymentGateway, default method nhường chỗ.
3. Bean của ứng dụng vẫn được inject và sử dụng qua abstraction PaymentGateway.
4. Property và điều kiện classpath quyết định cấu hình có được bật theo contract đã công bố.
5. Khi nâng Spring Boot, những hành vi công khai này vẫn giữ nguyên trên mọi phiên bản được hỗ trợ.

`@ConditionalOnMissingBean` chỉ match khi BeanFactory chưa chứa bean đáp ứng các tiêu chí đã khai báo. Nếu đặt trên `@Bean` method mà không chỉ định value, type hoặc name, target type mặc định là kiểu trả về của method. Condition chỉ nhìn thấy bean definitions đã được xử lý tại thời điểm đánh giá, vì vậy ordering giữa các auto-configuration cũng thuộc contract cần kiểm thử. [Tài liệu API chính thức](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).

## 2. Chuyển contract thành ma trận kiểm thử

Trước khi viết test, hãy liệt kê các tình huống mà người dùng starter có thể gặp. Mỗi dòng trong ma trận phải tương ứng với một hành vi quan sát được.

| Trường hợp | Setup | Kết quả phải giữ |
| --- | --- | --- |
| Không có custom bean | Chỉ nạp auto-configuration | Default bean tồn tại |
| Có custom bean cùng type | Thêm user bean implement abstraction | Default back-off; custom bean được dùng |
| Có nhiều custom bean cùng type | Đăng ký hai implementation | Default vẫn không xuất hiện; không giả định chỉ có một candidate |
| Property bật | Đặt property thành true | Auto-configuration và default bean được phép hoạt động |
| Property tắt | Đặt property thành false | Bean bị điều kiện property bảo vệ không xuất hiện |
| Property bị thiếu | Không đặt property | Kết quả khớp matchIfMissing đã công bố |
| Optional class có mặt | Class nằm trên classpath | Cấu hình tích hợp tùy chọn được phép áp dụng |
| Optional class vắng mặt | Lọc class khỏi classpath | Cấu hình phụ thuộc class đó không được đăng ký |
| Provider chạy trước fallback | Hai auto-configuration có quan hệ ordering | Provider tồn tại; fallback back-off |
| Discovery từ JAR | Nạp qua EnableAutoConfiguration | Boot tìm thấy class trong imports resource |
| Phiên bản Boot khác nhau | Chạy cùng contract suite trên các baseline | Hành vi công khai không đổi |

Không nhất thiết mọi starter đều cần tất cả trường hợp. Chọn các hàng tương ứng với annotation, property, dependency tùy chọn, context type và phiên bản mà starter thực sự công bố. Không thêm test cho một khả năng mà thư viện không hỗ trợ.

## 3. Chọn đúng công cụ kiểm thử

`ApplicationContextRunner` là công cụ phù hợp cho phần lớn auto-configuration tests. Mỗi test dựng một context nhỏ với một tổ hợp xác định của auto-configuration, user configuration, Environment và classpath. Callback nhận context đã được tạo để assertion; runner đóng context sau callback.

Một runner cơ sở thường được khai báo thành field:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                PaymentGatewayAutoConfiguration.class));
~~~

Các biến thể runner cho phép mỗi test thêm điều kiện riêng:

| API | Dùng để kiểm tra |
| --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Nạp một hoặc nhiều auto-configuration |
| `withUserConfiguration(...)` | Mô phỏng cấu hình do ứng dụng khai báo |
| `withBean(...)` | Đăng ký bean test trực tiếp |
| `withPropertyValues(...)` | Thay đổi Environment cho một trường hợp |
| `withClassLoader(...)` | Mô phỏng class hoặc package không có trên classpath |
| `withInitializer(...)` | Thêm initializer, ví dụ condition report listener |
| `run(...)` | Khởi tạo context, assertion trong callback rồi đóng context |

Runner tạo một context mới cho mỗi lần `run`. Có thể dùng chung field runner để tránh lặp cấu hình nền; mỗi test vẫn nên mô tả rõ setup và assertion của riêng nó.

Dùng `WebApplicationContextRunner` nếu cấu hình chỉ áp dụng cho Servlet web context, hoặc `ReactiveWebApplicationContextRunner` nếu cấu hình chỉ áp dụng cho Reactive web context. `ApplicationContextRunner` mặc định là runner non-web. Các runner này là công cụ kiểm thử JVM; chúng không chạy trong native image test. [Hướng dẫn kiểm thử auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

## 4. Viết contract test cho default và custom override

Ví dụ sau là một starter nhỏ. Các test kiểm tra hành vi qua interface công khai, không phụ thuộc vào chi tiết triển khai nội bộ ngoài những gì starter đã cam kết.

### 4.1. Contract và implementation

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

**`src/main/java/com/acme/payment/autoconfigure/PaymentGatewayAutoConfiguration.java`**

~~~java
package com.acme.payment.autoconfigure;

import com.acme.payment.DefaultPaymentGateway;
import com.acme.payment.PaymentGateway;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.payment",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    DefaultPaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Trong ví dụ này, property bị thiếu hoặc có giá trị true cho phép auto-configuration chạy; false tắt nó. Bean method kiểm tra abstraction PaymentGateway, trong khi return type công bố concrete default implementation để cung cấp type metadata rõ ràng.

### 4.2. Test default, override và property

**`src/test/java/com/acme/payment/autoconfigure/PaymentGatewayAutoConfigurationTests.java`**

~~~java
package com.acme.payment.autoconfigure;

import com.acme.payment.PaymentGateway;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentGatewayAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    PaymentGatewayAutoConfiguration.class));

    @Test
    void suppliesDefaultWhenNoUserGatewayExists() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(PaymentGateway.class);
            assertThat(context).hasBean("paymentGateway");

            assertThat(context.getBean(PaymentGateway.class).provider())
                    .isEqualTo("default");
        });
    }

    @Test
    void backsOffAndKeepsUserGateway() {
        contextRunner.withUserConfiguration(UserGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                    assertThat(context).hasBean("customPaymentGateway");
                    assertThat(context).doesNotHaveBean("paymentGateway");

                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("custom");
                });
    }

    @Test
    void disablesGatewayWhenPropertyIsFalse() {
        contextRunner.withPropertyValues("acme.payment.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(PaymentGateway.class);
                });
    }

    @Test
    void explicitlyEnabledPropertyStillSuppliesDefault() {
        contextRunner.withPropertyValues("acme.payment.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("default");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        CustomPaymentGateway customPaymentGateway() {
            return new CustomPaymentGateway();
        }
    }

    static final class CustomPaymentGateway implements PaymentGateway {

        @Override
        public String provider() {
            return "custom";
        }
    }
}
~~~

Các test này bảo vệ bốn phần của contract: default có mặt khi không có override, default nhường chỗ cho user bean, property false tắt tính năng và property true bật tính năng.

Nếu bean name paymentGateway không phải API được starter cam kết, có thể bỏ assertion theo tên và chỉ kiểm tra type/behavior. Nếu tài liệu starter công bố bean name để người dùng inject theo qualifier hoặc tên, hãy giữ assertion đó vì đổi tên khi refactor có thể là breaking change.

### 4.3. Kiểm tra nhiều custom bean

`@ConditionalOnMissingBean` không có nghĩa là "chỉ tạo default khi có đúng một implementation". Nó chỉ kiểm tra sự vắng mặt của bean phù hợp. Khi có hai implementation, default vẫn phải back-off.

Có thể bổ sung test:

~~~java
@Test
void doesNotAddDefaultWhenMultipleUserGatewaysExist() {
    contextRunner.withUserConfiguration(MultipleGatewayConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBeansOfType(PaymentGateway.class))
                        .hasSize(2);
                assertThat(context).doesNotHaveBean("paymentGateway");
            });
}
~~~

`MultipleGatewayConfiguration` khai báo hai bean khác nhau cùng implement PaymentGateway. Test này giúp ngăn một thay đổi nhầm từ missing-bean condition sang logic chỉ xét số lượng hoặc Primary.

## 5. Bảo vệ ordering giữa provider và fallback

Nếu một default bean phụ thuộc vào bean được cung cấp bởi auto-configuration khác, test phải bảo vệ thứ tự xử lý bean definitions.

Provider:

~~~java
@AutoConfiguration
public class PrimaryTransportAutoConfiguration {

    @Bean
    PrimaryTransport primaryTransport() {
        return new PrimaryTransport();
    }
}
~~~

Fallback:

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

Test:

~~~java
@Test
void fallbackBacksOffWhenPrimaryProviderIsConfigured() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    FallbackTransportAutoConfiguration.class,
                    PrimaryTransportAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(Transport.class);
                assertThat(context).hasBean("primaryTransport");
                assertThat(context).doesNotHaveBean("fallbackTransport");
            });
}
~~~

Hai lớp PrimaryTransport và FallbackTransport trong ví dụ đều implement Transport. Thứ tự after điều khiển thời điểm đăng ký bean definitions; nó không điều khiển thời điểm khởi tạo instance. Quan hệ phụ thuộc khi tạo bean vẫn do dependency graph và `@DependsOn` quyết định.

`AutoConfigurations.of` áp dụng ordering theo cùng quy tắc như khi ứng dụng chạy. Vì vậy, test nên đưa các auto-configuration cần thiết vào runner và kiểm tra kết quả cuối cùng, thay vì phụ thuộc vào thứ tự liệt kê class trong test. [Tài liệu ordering và bean conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

## 6. Kiểm tra optional dependency và classpath

Starter thường tích hợp với thư viện tùy chọn. Nếu dependency không có, auto-configuration tương ứng phải được bỏ qua mà không làm hỏng quá trình tạo context.

Spring Boot cung cấp `FilteredClassLoader` để mô phỏng class hoặc package không tồn tại:

~~~java
contextRunner
        .withClassLoader(new FilteredClassLoader(OptionalClient.class))
        .withConfiguration(
                AutoConfigurations.of(OptionalClientAutoConfiguration.class))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean("optionalClient");
        });
~~~

Với cấu hình có method signature tham chiếu class tùy chọn, hãy cô lập các bean đó trong nested configuration được bảo vệ bằng `@ConditionalOnClass`. Nếu class tùy chọn bị thiếu, Spring có thể loại nested configuration trước khi xử lý method cần class đó. Không đặt return type của dependency tùy chọn trực tiếp vào một method mà JVM phải nạp trước khi condition class được đánh giá.

Bộ test hồi quy cho optional integration nên có hai nhánh:

- Class có mặt: bean tích hợp được đăng ký nếu các điều kiện khác thỏa mãn.
- Class vắng mặt: context vẫn khởi động và bean tích hợp không xuất hiện.

Không chỉ kiểm tra `doesNotHaveBean`; hãy xác nhận context không bị lỗi do `NoClassDefFoundError` hoặc `ClassNotFoundException`.

## 7. Kiểm tra discovery từ artifact đã đóng gói

Một test nạp trực tiếp class bằng `AutoConfigurations.of(...)` xác nhận behavior của class, nhưng không xác nhận Boot có tìm thấy class từ file registration trong JAR hay không.

Với Boot 2.7+/3.x, auto-configuration phải được liệt kê trong:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ:

~~~text
com.acme.payment.autoconfigure.PaymentGatewayAutoConfiguration
~~~

Để kiểm tra discovery, tạo một test fixture dùng `@EnableAutoConfiguration`:

~~~java
@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
static class DiscoveryApplication {
}
~~~

Test chạy với classpath thật của module:

~~~java
@Test
void discoversAutoConfigurationFromImportsResource() {
    new ApplicationContextRunner()
            .withUserConfiguration(DiscoveryApplication.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(PaymentGateway.class);
            });
~~~

Test này phải chạy trong module có resource registration thật trên classpath. Không thêm `AutoConfigurations.of(PaymentGatewayAutoConfiguration.class)` vào discovery test, vì như vậy test đã nạp class trực tiếp và không còn kiểm tra file imports.

Sau khi build artifact, kiểm tra resource thực tế trong JAR:

~~~bash
mvn -B -DskipTests package
jar tf target/acme-payment-autoconfigure-1.0.0.jar
~~~

Xác nhận file imports có trong artifact và chứa đủ FQCN. Nếu dùng Maven Shade hoặc Gradle Shadow để tạo uber-JAR, kiểm tra các resource cùng tên được nối đúng cách thay vì một dependency ghi đè nội dung của dependency khác.

## 8. Kiểm tra Condition Evaluation Report khi test hồi quy thất bại

Khi một test báo default bean biến mất, Condition Evaluation Report giúp xác định condition nào không match và lý do.

Có thể bật listener trong test:

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

Các thông tin cần đọc:

- Auto-configuration class và bean method đang được đánh giá.
- Type, name hoặc annotation mà condition đang tìm.
- Bean hiện hữu làm `@ConditionalOnMissingBean` không match.
- Property hoặc classpath condition nào đang loại cấu hình.
- Ordering có khiến provider definition chưa được xử lý hay không.

Có thể dùng `--debug` khi chạy ứng dụng để in condition report. Nếu Actuator được dùng và endpoint được expose/cho phép truy cập, `/actuator/conditions` cung cấp các positive và negative matches. Chỉ expose endpoint theo chính sách bảo vệ của ứng dụng; không mở endpoint chẩn đoán rộng rãi chỉ để tiện test.

## 9. Phân biệt các lớp kiểm thử hồi quy

Không phải mọi lỗi auto-configuration đều nên được kiểm tra bằng cùng một loại test.

| Lớp kiểm thử | Phạm vi | Công cụ phù hợp |
| --- | --- | --- |
| Contract test | Default, override, property, type/name, bean count | `ApplicationContextRunner` |
| Condition test | Classpath, resource, profile, web condition | Runner + `FilteredClassLoader` |
| Ordering test | Provider và fallback auto-configuration | `AutoConfigurations.of(...)` |
| Discovery test | File imports, classpath và auto-configuration registration | `@EnableAutoConfiguration` trên artifact |
| Web context test | Servlet hoặc Reactive conditions | `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` |
| Compatibility test | Các phiên bản Boot/JDK được hỗ trợ | CI version matrix |
| Integration test | Kết nối thực tế với hệ thống bên ngoài | Testcontainers hoặc môi trường tích hợp riêng |

Giữ contract tests nhanh và độc lập. Chỉ dùng database, broker hoặc HTTP server thật trong integration test khi behavior đó thực sự thuộc contract cần bảo vệ. Một test kiểm tra bean back-off không nên phụ thuộc vào một dịch vụ mạng bên ngoài.

## 10. Bảo vệ tương thích qua các phiên bản Spring Boot

Thư viện cần công bố rõ các phiên bản Boot mà nó hỗ trợ. CI chỉ có thể bảo vệ contract nếu chạy trên những baseline thực sự được cam kết.

Ví dụ một thư viện hỗ trợ Boot 2.7 và Boot 3.3 có thể chạy cùng bộ contract tests trên hai dòng sau:

| Runtime | JDK kiểm thử | Mục tiêu |
| --- | --- | --- |
| Spring Boot 2.7.18 | 17 | Giữ tương thích với baseline 2.7 |
| Spring Boot 3.3.13 | 17 | Bảo vệ behavior trên dòng Boot 3 |

Boot 2.7 đã có `@AutoConfiguration` và `AutoConfiguration.imports`, vì vậy một source set dùng các API đó có thể được kiểm thử trên cả hai dòng này. Nếu thư viện còn hỗ trợ Boot 2.6 trở xuống, API `@AutoConfiguration` chưa có ở baseline đó; cần duy trì source/artifact tương thích riêng, chẳng hạn dùng `@Configuration` và registration `spring.factories`, rồi chạy contract suite tương ứng. Không đưa một baseline không thể compile vào cùng ma trận chỉ bằng cách đổi dependency version.

### 10.1. Dùng Maven property để chọn Boot BOM

Một POM có thể khai báo version Boot qua property:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và các thành phần test cần thiết. Trong dự án thực tế, plugin compiler và Surefire cần được quản lý bằng parent hoặc plugin management phù hợp.

Có thể chạy thủ công cùng một suite trên từng baseline:

~~~bash
mvn -B -Dspring-boot.version=2.7.18 verify
mvn -B -Dspring-boot.version=3.3.13 verify
~~~

### 10.2. Ví dụ CI matrix

Một GitHub Actions workflow tối giản:

~~~yaml
name: Auto-configuration compatibility

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        boot-version: ['2.7.18', '3.3.13']
        java-version: ['17']

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java-version }}
          cache: maven

      - name: Run regression suite
        run: mvn -B -Dspring-boot.version=${{ matrix.boot-version }} verify
~~~

Trong workflow thực tế, hai marker trên được thay bằng biểu thức GitHub Actions cho matrix.java-version và matrix.boot-version tương ứng. Khi thêm một Boot baseline được hỗ trợ, thêm nó vào matrix và bảo đảm dependency/plugin tương ứng thực sự tương thích.

Không chỉ chạy test ở phiên bản mới nhất. Một thay đổi dependency có thể vô tình bỏ hỗ trợ cho baseline cũ dù code vẫn compile và pass ở phiên bản mới.

## 11. Kiểm tra những gì thuộc contract công khai

Một regression test hữu ích bảo vệ hành vi mà người dùng starter có thể quan sát. Các contract thường gặp:

- **Bean type:** ứng dụng có thể inject abstraction đã công bố.
- **Back-off:** user bean cùng type khiến default không được đăng ký.
- **Bean name:** chỉ kiểm tra nếu starter tài liệu hóa name hoặc qualifier.
- **Property key:** prefix, tên property, default value, havingValue và matchIfMissing.
- **Optional dependency:** thiếu thư viện không làm hỏng context.
- **Ordering:** provider/fallback được xử lý đúng thứ tự.
- **Registration:** imports resource tồn tại trong artifact và discovery hoạt động.
- **Supported versions:** các baseline được cam kết đều chạy cùng contract suite.

Tránh khóa test vào chi tiết nội bộ không phải API. Ví dụ, nếu contract chỉ hứa có một PaymentGateway, không cần mọi test đều yêu cầu class chính xác phải là DefaultPaymentGateway. Khi implementation thay đổi nhưng contract không đổi, test không nên thất bại chỉ vì một refactor hợp lệ.

Ngược lại, nếu bean name hoặc qualifier được công bố trong tài liệu và người dùng dựa vào nó, hãy kiểm thử như một phần của API.

## 12. Các lỗi khiến regression suite không bảo vệ được starter

| Cách kiểm thử yếu | Vì sao dễ lọt lỗi | Cách cải thiện |
| --- | --- | --- |
| Chỉ kiểm tra context khởi động thành công | Không biết default có tồn tại hoặc back-off đúng không | Assert bean type, count và custom implementation |
| Chỉ test trường hợp không có custom bean | Không bảo vệ giao ước nhường chỗ | Thêm user configuration có bean cùng abstraction |
| Chỉ assert bean name | Bean có thể tồn tại nhưng sai type hoặc behavior | Assert type và hành vi công khai |
| Chỉ nạp class bằng `AutoConfigurations.of` | Không phát hiện imports resource bị thiếu | Thêm discovery test qua `@EnableAutoConfiguration` |
| Chỉ test phiên bản Boot mới nhất | Baseline cũ có thể bị breaking change | Chạy version matrix theo support policy |
| Dùng một `@SpringBootTest` lớn cho mọi trường hợp | Test chậm và khó xác định condition gây lỗi | Dùng `ApplicationContextRunner` cho từng tổ hợp nhỏ |
| Không test property bị thiếu | Có thể đổi nhầm matchIfMissing | Test missing, true và false |
| Không mô phỏng classpath thiếu | Optional integration có thể làm context fail | Dùng `FilteredClassLoader` |
| Không kiểm tra ordering | Fallback có thể đăng ký trước provider | Thêm hai auto-configuration vào runner và assert kết quả |
| Test phụ thuộc database/broker thật | Lỗi môi trường che lỗi condition | Giữ contract test local; integration test tách riêng |

## 13. Quy trình cập nhật regression suite khi thay đổi starter

Khi sửa auto-configuration, thực hiện quy trình:

1. Xác định contract bị tác động: bean type/name, property, classpath, ordering hay registration.
2. Tìm test hiện tại bảo vệ contract đó.
3. Nếu thay đổi hành vi có chủ đích, cập nhật tài liệu contract trước khi cập nhật assertion.
4. Thêm test tái hiện trước hoặc cùng thay đổi implementation.
5. Chạy test class liên quan để có phản hồi nhanh.
6. Chạy toàn bộ contract suite và discovery test.
7. Chạy CI matrix trên tất cả baseline được hỗ trợ.
8. Kiểm tra JAR phát hành và imports resource nếu có thay đổi packaging.
9. Review diff để bảo đảm không vô tình bỏ test của baseline cũ.

Một thay đổi được xem là tương thích khi mọi contract được công bố vẫn đúng. Nếu thay đổi làm user override không còn hoạt động, đổi property mặc định hoặc bỏ một baseline đã cam kết, cần xử lý như breaking change và công bố rõ trong release notes.

## 14. Checklist trước khi phát hành

- [ ] Test default bean khi không có custom bean.
- [ ] Test user bean cùng type khiến default back-off.
- [ ] Test nhiều user bean nếu starter cho phép nhiều implementation.
- [ ] Test property thiếu, bật và tắt.
- [ ] Test optional dependency có mặt và vắng mặt.
- [ ] Test provider/fallback ordering.
- [ ] Test bean type và bean name nếu chúng là contract công khai.
- [ ] Test discovery qua EnableAutoConfiguration trên artifact.
- [ ] Kiểm tra imports resource trong JAR sau package/shade/shadow.
- [ ] Chạy contract suite trên mọi phiên bản Boot được hỗ trợ.
- [ ] Kiểm tra JDK baseline tương ứng.
- [ ] Giữ contract tests độc lập với hệ thống bên ngoài.
- [ ] Đọc Condition Evaluation Report khi có test no-match ngoài dự kiến.
- [ ] Cập nhật tài liệu và release notes khi contract thay đổi.

## 15. Câu hỏi tự kiểm tra

1. Vì sao chỉ test default bean xuất hiện là chưa đủ?  
   **Đáp án:** Vì test đó không chứng minh starter nhường chỗ khi ứng dụng cung cấp implementation riêng.

2. Test nào chứng minh giao ước back-off?  
   **Đáp án:** Dựng context có user bean cùng type, xác nhận user bean được dùng và bean mặc định không được đăng ký.

3. Vì sao nên dùng ApplicationContextRunner?  
   **Đáp án:** Nó tạo context nhỏ, có thể kiểm soát user configuration, property và classpath cho từng trường hợp, giúp test condition nhanh và độc lập.

4. AutoConfigurations.of có kiểm tra file imports không?  
   **Đáp án:** Không. Nó nạp class trực tiếp; cần discovery test qua EnableAutoConfiguration để kiểm tra registration resource.

5. Khi nào dùng FilteredClassLoader?  
   **Đáp án:** Khi cần mô phỏng optional class hoặc package không có trên classpath.

6. Vì sao phải test property bị thiếu?  
   **Đáp án:** Vì matchIfMissing và default property value là một phần của contract; thay đổi chúng có thể làm tính năng bật/tắt khác đi.

7. Vì sao phải test trên baseline Boot cũ nhất được hỗ trợ?  
   **Đáp án:** Vì API, registration và behavior có thể thay đổi giữa các dòng; test chỉ trên phiên bản mới không bảo vệ khả năng tương thích đã cam kết.

8. Có nên assert class implementation nội bộ trong mọi test không?  
   **Đáp án:** Không. Ưu tiên type và behavior công khai; chỉ assert implementation cụ thể khi đó là contract được tài liệu hóa.

9. Nếu provider được tạo bởi auto-configuration khác, điều gì cần được kiểm thử?  
   **Đáp án:** Ordering của hai auto-configuration và việc fallback back-off sau khi provider definition được xử lý.

10. Regression suite có thay thế integration test với hệ thống bên ngoài không?  
    **Đáp án:** Không. Contract test xác minh condition và bean registration; integration test vẫn cần cho giao tiếp thật với database, broker hoặc dịch vụ ngoài.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): ordering, bean conditions, ApplicationContextRunner, condition report, web runners và FilteredClassLoader.
- [Spring Boot 3.3.13 — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): tiêu chí type/name/annotation, return type mặc định, search strategy và ignored types.
- [Spring Boot 3.3.13 — AutoConfigurations API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html): tiện ích nạp và sắp thứ tự auto-configuration trong test.
- [Spring Boot 3.3.13 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): runner cho context test non-web.
- [Spring Boot 3.3.13 — Conditions Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): kết quả positive/negative condition matches.
- [Spring Boot 2.7 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes): mốc AutoConfiguration và resource registration mới trong dòng 2.7.

**Ghi nhớ:** Regression suite phải chứng minh cả hai phía của giao ước: default xuất hiện khi chưa có override và nhường chỗ khi user bean đã tồn tại. Sau đó mở rộng test cho property, classpath, ordering, discovery và mọi phiên bản Boot được hỗ trợ. Khi các contract này chạy tự động trong CI, refactor nội bộ có thể diễn ra mà người dùng starter vẫn nhận được hành vi đã công bố.
