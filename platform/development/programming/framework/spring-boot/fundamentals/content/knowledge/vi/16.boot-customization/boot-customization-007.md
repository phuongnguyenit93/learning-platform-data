# Viết một auto-configuration nhỏ có back-off rõ ràng

Spring Boot auto-configuration giúp một thư viện tự đăng ký những bean hợp lý dựa trên dependency, property và các bean mà ứng dụng đã cung cấp. Một auto-configuration tốt tạo ra trải nghiệm “thêm starter là dùng được”, đồng thời vẫn để ứng dụng kiểm soát và thay thế hành vi mặc định.

Điểm quan trọng khi viết auto-configuration là **back-off**: khi người dùng đã khai báo bean phù hợp, cấu hình tự động nên nhường chỗ thay vì tạo thêm một bean cạnh tranh. Cơ chế phổ biến nhất là **@ConditionalOnMissingBean**.

Bài học này xây dựng một auto-configuration nhỏ cho dịch vụ lời chào. Ta sẽ đăng ký một service mặc định, cho phép ứng dụng thay service đó, bật/tắt tính năng bằng property, và kiểm thử các nhánh bằng ApplicationContextRunner.

## 1. Auto-configuration giải quyết vấn đề gì?

Giả sử nhiều ứng dụng cần gửi thông báo. Thư viện có thể cung cấp một implementation mặc định:

~~~java
public interface GreetingService {
    String greet(String name);
}
~~~

~~~java
public class DefaultGreetingService implements GreetingService {
    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Nếu mỗi ứng dụng phải tự khai báo một @Bean cho DefaultGreetingService, cấu hình sẽ lặp lại. Một auto-configuration có thể tự đăng ký service mặc định khi ứng dụng sử dụng thư viện.

Tuy nhiên, ứng dụng A có thể muốn lời chào tiếng Việt, ứng dụng B muốn lấy lời chào từ một API, còn ứng dụng C muốn không bật tính năng này. Vì vậy auto-configuration cần các quy tắc rõ ràng:

- Tự tạo bean mặc định khi chưa có bean GreetingService do ứng dụng cung cấp.
- Nhường chỗ khi ứng dụng đăng ký GreetingService riêng.
- Chỉ bật tính năng khi property cho phép.
- Chỉ kích hoạt phần tích hợp khi thư viện cần thiết có trên classpath.
- Không tạo nhiều bean cùng vai trò khiến injection trở nên mơ hồ.

Một auto-configuration không nên ép ứng dụng phải chấp nhận mọi lựa chọn mặc định. Nó nên cung cấp **đường đi mặc định có thể thay thế**.

## 2. Phân biệt auto-configuration với component scanning

**Component scanning** tìm các class mang annotation như @Component, @Service hoặc @Repository trong phạm vi package được quét.

**Auto-configuration** là cấu hình được Spring Boot phát hiện và áp dụng theo cơ chế đăng ký riêng, thường nằm trong một thư viện starter hoặc module autoconfigure.

Ví dụ component:

~~~java
@Service
public class GreetingServiceImpl implements GreetingService {
    // ...
}
~~~

Class này chỉ được phát hiện nếu package nằm trong component scan hoặc được đăng ký bằng một cơ chế khác.

Ngược lại, auto-configuration có thể nằm ngoài package của class main và được Boot nạp qua metadata:

~~~text
my-greeting-starter
├── API classes
├── auto-configuration classes
└── META-INF
    └── spring
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Người dùng thêm starter vào dependency graph; Spring Boot đọc file imports để tìm configuration class. Các condition trên class và bean method quyết định phần nào được áp dụng.

## 3. Thiết kế ví dụ trước khi viết code

Ta xây một thư viện tên Greeting:

| Thành phần | Trách nhiệm |
|---|---|
| GreetingService | Interface mà ứng dụng sử dụng. |
| DefaultGreetingService | Implementation mặc định của thư viện. |
| GreetingProperties | Nhận cấu hình từ application.yml. |
| GreetingAutoConfiguration | Đăng ký properties và bean mặc định. |
| Ứng dụng consumer | Có thể dùng bean mặc định hoặc cung cấp bean riêng. |

Các property:

~~~yaml
demo:
  greeting:
    enabled: true
    prefix: "Xin chào"
~~~

Kết quả mong đợi:

| Tình huống | GreetingService trong context |
|---|---|
| Tính năng bật, ứng dụng không khai báo bean riêng | Có DefaultGreetingService. |
| Tính năng bật, ứng dụng khai báo bean riêng | Chỉ dùng bean do ứng dụng cung cấp. |
| Tính năng tắt | Không có bean mặc định từ auto-configuration. |

Đây là hợp đồng back-off cơ bản. Ta sẽ kiểm thử cả ba trường hợp thay vì chỉ kiểm tra ứng dụng khởi động thành công.

## 4. Khai báo API và implementation mặc định

Interface là hợp đồng mà consumer phụ thuộc:

~~~java
package com.example.greeting;

public interface GreetingService {
    String greet(String name);
}
~~~

Implementation mặc định nhận prefix từ constructor:

~~~java
package com.example.greeting;

public class DefaultGreetingService implements GreetingService {
    private final GreetingProperties properties;

    public DefaultGreetingService(GreetingProperties properties) {
        this.properties = properties;
    }

    @Override
    public String greet(String name) {
        return properties.getPrefix() + ", " + name + "!";
    }
}
~~~

Ta không cần đánh dấu implementation bằng @Component. Auto-configuration sẽ đăng ký nó qua phương thức @Bean. Điều này giúp thư viện kiểm soát rõ bean nào được tạo và điều kiện nào quyết định việc tạo.

Việc không dùng @Component cũng tránh tình huống implementation bị component scan của ứng dụng phát hiện, đồng thời auto-configuration lại khai báo thêm một bean tương tự.

## 5. Tạo class cấu hình bằng @ConfigurationProperties

Property class gom các cấu hình của tính năng vào một nơi:

~~~java
package com.example.greeting;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.greeting")
public class GreetingProperties {
    private boolean enabled = true;
    private String prefix = "Xin chào";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

Với cấu hình:

~~~yaml
demo:
  greeting:
    enabled: true
    prefix: "Chào bạn"
~~~

Spring Boot bind các giá trị vào GreetingProperties.

### 5.1. Vì sao nên có class properties riêng?

Class properties giúp:

- Gom các property theo prefix.
- Có giá trị mặc định dễ hiểu.
- Dễ kiểm tra và validate cấu hình.
- Tái sử dụng property trong nhiều bean.
- Tạo metadata hỗ trợ gợi ý trong IDE nếu module có annotation processor phù hợp.

Không nên rải chuỗi property ở nhiều factory method nếu chúng thuộc cùng một tính năng.

### 5.2. Bật đăng ký properties trong auto-configuration

Auto-configuration có thể dùng:

~~~java
@EnableConfigurationProperties(GreetingProperties.class)
~~~

Annotation này yêu cầu Spring Boot đăng ký và bind GreetingProperties. Không cần bắt consumer thêm @EnableConfigurationProperties vào application class.

## 6. Viết auto-configuration có back-off

Đây là phần cốt lõi:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.DefaultGreetingService;
import com.example.greeting.GreetingProperties;
import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingProperties properties) {
        return new DefaultGreetingService(properties);
    }
}
~~~

Auto-configuration này có ba trách nhiệm:

1. Được đăng ký như một auto-configuration bằng @AutoConfiguration.
2. Bật properties và chỉ áp dụng khi demo.greeting.enabled là true hoặc property bị thiếu.
3. Tạo GreetingService mặc định nếu context chưa có bean GreetingService phù hợp.

Điều kiện **@ConditionalOnMissingBean(GreetingService.class)** chính là back-off. Nếu ứng dụng đã đăng ký một bean GreetingService, phương thức greetingService() không được dùng để đăng ký bean mặc định.

### 6.1. Vì sao return type của @Bean là interface?

Phương thức khai báo:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService(GreetingProperties properties) {
    return new DefaultGreetingService(properties);
}
~~~

Return type thể hiện contract mà consumer cần. Với các condition dựa trên bean, Spring Boot dùng metadata kiểu của bean method để đánh giá candidate. Khai báo return type đủ cụ thể và phù hợp với vai trò bean giúp điều kiện được xử lý chính xác.

Nếu condition kiểm tra GreetingService nhưng phương thức chỉ khai báo return type quá chung như Object, một số thông tin kiểu có thể không sẵn có ở thời điểm condition được đánh giá. Hãy khai báo kiểu trả về theo abstraction mà bean thực sự cung cấp.

### 6.2. matchIfMissing có ý nghĩa gì?

Trong ví dụ:

~~~java
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
~~~

- Property true: condition match.
- Property false: condition không match.
- Property không tồn tại: condition match vì matchIfMissing = true.

Điều này cho phép starter hoạt động ngay khi được thêm vào mà không bắt consumer khai báo property bật một cách tường minh.

Nếu muốn tính năng chỉ bật khi người dùng chủ động cấu hình, đặt **matchIfMissing = false** hoặc dùng giá trị mặc định phù hợp với yêu cầu sản phẩm.

## 7. Đăng ký auto-configuration để Spring Boot tìm thấy

Với Spring Boot 3, tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file là tên đầy đủ của auto-configuration class, mỗi class trên một dòng:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Không đặt annotation hoặc cú pháp Java trong file này. Đây là resource metadata để Boot phát hiện auto-configuration.

Nếu file imports thiếu hoặc tên class sai package, auto-configuration có thể không được phát hiện dù class đã biên dịch thành công.

### 7.1. Không dùng cơ chế đăng ký cũ của Spring Boot 2 cho dự án Boot 3

Các dự án Spring Boot cũ có thể dùng file:

~~~text
META-INF/spring.factories
~~~

với key EnableAutoConfiguration. Với Spring Boot 3, cơ chế đăng ký auto-configuration được chuẩn hóa qua **AutoConfiguration.imports**. Khi phát triển thư viện cho Boot 3, hãy dùng đúng resource này.

Nếu thư viện cần hỗ trợ nhiều thế hệ Boot, phải thiết kế artifact/metadata tương thích theo từng phiên bản thay vì giả định một cơ chế đăng ký áp dụng cho mọi phiên bản.

## 8. Back-off diễn ra như thế nào?

Giả sử consumer có:

~~~java
@Configuration(proxyBeanMethods = false)
class ApplicationConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return name -> "Rất vui được gặp " + name;
    }
}
~~~

Context có hai nguồn cấu hình:

~~~text
Application configuration
└── customGreetingService : GreetingService

GreetingAutoConfiguration
└── greetingService()
    @ConditionalOnMissingBean(GreetingService.class)
~~~

Trong quá trình xử lý cấu hình, bean do ứng dụng khai báo được nhận diện. Khi Spring Boot đánh giá điều kiện của bean mặc định, GreetingService đã tồn tại nên condition không match. Bean mặc định không được đăng ký.

Kết quả:

~~~text
GreetingService
└── customGreetingService
~~~

Consumer inject GreetingService sẽ nhận implementation của ứng dụng.

### 8.1. Back-off không xóa bean do ứng dụng khai báo

@ConditionalOnMissingBean không thay thế, sửa hoặc xóa bean hiện có. Nó chỉ quyết định có đăng ký bean mặc định hay không.

Nếu ứng dụng có customGreetingService, bean đó vẫn nằm trong context. Auto-configuration chỉ nhường chỗ.

### 8.2. Back-off không phải bean overriding

Phân biệt:

| Cơ chế | Ý nghĩa |
|---|---|
| **@ConditionalOnMissingBean** | Không đăng ký bean mặc định khi đã có bean phù hợp. |
| **Bean definition overriding** | Cho phép một definition khác ghi đè definition trùng tên, tùy cấu hình container. |
| **@Primary** | Ưu tiên một bean khi có nhiều candidate cho dependency đơn. |
| **@Qualifier** | Lọc candidate theo metadata tại injection point. |

Auto-configuration nên ưu tiên back-off tường minh thay vì dựa vào ghi đè bean trùng tên. Cách này dễ hiểu hơn và tránh việc một ứng dụng vô tình thay đổi hành vi chỉ vì thứ tự đăng ký.

## 9. Điều kiện class-level và method-level trong auto-configuration

Ví dụ trên đặt @ConditionalOnProperty ở cấp class và @ConditionalOnMissingBean ở cấp method.

Đây là lựa chọn có chủ ý:

- Nếu tính năng greeting bị tắt, toàn bộ GreetingAutoConfiguration không được áp dụng.
- Nếu tính năng bật nhưng ứng dụng đã có GreetingService, chỉ bean mặc định bị bỏ qua.

Nếu đặt @ConditionalOnMissingBean(GreetingService.class) ở cấp class:

~~~java
@AutoConfiguration
@ConditionalOnMissingBean(GreetingService.class)
public class GreetingAutoConfiguration {
    // Các bean khác...
}
~~~

thì khi ứng dụng cung cấp GreetingService riêng, toàn bộ cấu hình bị loại. Nếu class còn cung cấp GreetingFormatter, GreetingMetrics hoặc bean độc lập khác, chúng cũng biến mất ngoài ý muốn.

Quy tắc thiết kế:

- Đặt condition class-level cho điều kiện nền áp dụng tới tất cả bean trong cấu hình.
- Đặt @ConditionalOnMissingBean ở từng method nếu mỗi bean cần được override độc lập.
- Dùng nested configuration khi một nhóm bean có chung điều kiện riêng.

## 10. Khi nào cần @ConditionalOnClass?

Nếu auto-configuration phụ thuộc một thư viện tùy chọn, cần bảo vệ phần tích hợp bằng classpath condition.

Ví dụ một module chỉ cung cấp adapter khi SDK đối tác có mặt:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.greeting.VendorGreetingClient")
    static class VendorGreetingConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        GreetingService greetingService(VendorGreetingClient client) {
            return new VendorGreetingService(client);
        }
    }
}
~~~

Nested configuration giúp cô lập kiểu tùy chọn. Nếu SDK không có, Spring Boot có thể bỏ qua nhánh này mà không cần nạp các method có chữ ký tham chiếu kiểu VendorGreetingClient trong outer configuration.

Không nên chỉ đặt method-level @ConditionalOnClass nhưng để optional class xuất hiện trong superclass, field hoặc method signature của class ngoài luôn được nạp. Class condition ở cấp nested configuration là mẫu an toàn và dễ đọc cho optional integration.

## 11. Tổ chức module starter và autoconfigure

Với một thư viện nhỏ, có thể đặt API và auto-configuration trong cùng module. Khi thư viện phát triển, nên cân nhắc tách:

~~~text
greeting/
├── greeting-spring-boot-autoconfigure/
│   ├── API
│   ├── GreetingProperties
│   ├── GreetingAutoConfiguration
│   └── AutoConfiguration.imports
│
└── greeting-spring-boot-starter/
    └── dependency vào autoconfigure và các dependency cần thiết
~~~

### 11.1. Module autoconfigure

Module này chứa:

- Auto-configuration class.
- Property class.
- Default implementation.
- Condition metadata.
- Resource AutoConfiguration.imports.

Module này nên khai báo dependency cần thiết để compile và chạy cấu hình. SDK optional nên được xử lý riêng, không ép mọi consumer phải dùng nếu không cần.

### 11.2. Module starter

Starter chủ yếu là một artifact tiện dụng để gom các dependency mà consumer thường cần. Nó có thể phụ thuộc vào module autoconfigure và các thư viện runtime phổ biến.

Consumer thêm starter vào build file:

~~~groovy
dependencies {
    implementation 'com.example:greeting-spring-boot-starter:1.0.0'
}
~~~

Sau đó có thể dùng GreetingService mà không cần tự viết cấu hình bean mặc định.

### 11.3. Không nhầm starter với auto-configuration

Starter thường là dependency aggregator. Logic điều kiện và đăng ký bean nằm trong module autoconfigure. Tách hai trách nhiệm giúp consumer có thể chọn artifact phù hợp và giúp thư viện quản lý optional dependency tốt hơn.

## 12. Kiểm thử auto-configuration bằng ApplicationContextRunner

Không nên chỉ kiểm tra ứng dụng lớn có khởi động hay không. Auto-configuration cần được kiểm thử theo từng nhánh điều kiện.

**ApplicationContextRunner** cho phép tạo một context nhỏ, thêm cấu hình, property hoặc bean thử nghiệm rồi kiểm tra kết quả.

Trong module test, cần dependency test phù hợp, ví dụ:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 12.1. Tạo test cho auto-configuration

~~~java
package com.example.greeting.autoconfigure;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class
                            )
                    );
}
~~~

Runner này chỉ nạp auto-configuration được chỉ định. Điều đó giúp test tập trung vào hành vi của thư viện, không cần khởi động toàn bộ web server hay database của một ứng dụng consumer.

### 12.2. Trường hợp không có custom bean

~~~java
@Test
void createsDefaultGreetingServiceWhenUserBeanIsMissing() {
    contextRunner
            .withPropertyValues("demo.greeting.enabled=true")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class))
                        .isInstanceOf(DefaultGreetingService.class);
            });
}
~~~

Test xác nhận khi feature bật và chưa có bean riêng, default implementation được đăng ký.

### 12.3. Trường hợp ứng dụng cung cấp custom bean

Tạo implementation trong test:

~~~java
class CustomGreetingService implements GreetingService {
    @Override
    public String greet(String name) {
        return "Chào mừng, " + name;
    }
}
~~~

Test:

~~~java
@Test
void backsOffWhenUserProvidesGreetingService() {
    contextRunner
            .withPropertyValues("demo.greeting.enabled=true")
            .withBean(
                    GreetingService.class,
                    CustomGreetingService::new
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class))
                        .isInstanceOf(CustomGreetingService.class);
                assertThat(context.getBean(GreetingService.class)
                        .greet("Lan"))
                        .isEqualTo("Chào mừng, Lan");
            });
}
~~~

Đây là test quan trọng nhất cho back-off. Nó xác nhận:

- Context không có hai bean GreetingService cạnh tranh.
- Bean mặc định không được tạo.
- Bean do ứng dụng cung cấp vẫn được sử dụng.

### 12.4. Trường hợp tính năng bị tắt

~~~java
@Test
void doesNotCreateDefaultBeanWhenFeatureIsDisabled() {
    contextRunner
            .withPropertyValues("demo.greeting.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(GreetingService.class);
            });
}
~~~

Test này xác nhận condition class-level hoạt động. Khi property false, cấu hình không đăng ký bean GreetingService mặc định.

### 12.5. Trường hợp property bị thiếu

Vì ví dụ dùng matchIfMissing = true, có thể kiểm tra:

~~~java
@Test
void enablesFeatureWhenPropertyIsMissing() {
    contextRunner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).hasSingleBean(GreetingService.class);
    });
}
~~~

Test xác nhận hành vi mặc định được thiết kế. Nếu thay đổi matchIfMissing thành false, hãy đổi assertion tương ứng.

## 13. Kiểm thử property binding

Ngoài việc kiểm tra bean có xuất hiện, nên xác nhận property được bind đúng:

~~~java
@Test
void bindsGreetingPrefix() {
    contextRunner
            .withPropertyValues(
                    "demo.greeting.enabled=true",
                    "demo.greeting.prefix=Chào buổi sáng"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                GreetingService service =
                        context.getBean(GreetingService.class);
                assertThat(service.greet("Minh"))
                        .isEqualTo("Chào buổi sáng, Minh!");
            });
}
~~~

Test này kiểm tra luồng đầy đủ: property được bind, auto-configuration tạo default service, và service sử dụng giá trị cấu hình.

Nếu có validation như @Validated hoặc các constraint trên properties, nên thêm test cho property hợp lệ và không hợp lệ.

## 14. Kiểm thử khi bean mặc định có dependency

Một auto-configuration có thể đăng ký nhiều bean, trong đó bean mặc định phụ thuộc bean khác.

Ví dụ:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    GreetingFormatter greetingFormatter() {
        return new DefaultGreetingFormatter();
    }

    @Bean
    @ConditionalOnMissingBean
    GreetingService greetingService(
            GreetingProperties properties,
            GreetingFormatter formatter) {
        return new DefaultGreetingService(properties, formatter);
    }
}
~~~

Trong trường hợp này, nếu ứng dụng tự cung cấp GreetingFormatter, GreetingService mặc định vẫn có thể được tạo và sử dụng formatter tùy chỉnh.

Nếu ứng dụng tự cung cấp GreetingService nhưng không cung cấp GreetingFormatter, chỉ service mặc định nhường chỗ; formatter mặc định vẫn có thể được đăng ký. Đây là lý do nên đặt @ConditionalOnMissingBean trên từng bean cần override độc lập.

Test nên kiểm tra các tổ hợp:

- Không có bean nào: cả formatter và service mặc định được tạo.
- Có formatter riêng: service mặc định dùng formatter riêng.
- Có service riêng: service mặc định không được tạo, formatter mặc định vẫn có thể tồn tại.

## 15. Thứ tự auto-configuration và bean do ứng dụng cung cấp

Auto-configuration của Spring Boot được xử lý theo cơ chế được thiết kế để cấu hình ứng dụng có thể cung cấp bean tùy chỉnh trước khi cấu hình mặc định quyết định có back-off hay không.

Đó là lý do @ConditionalOnMissingBean thường hoạt động tốt trong auto-configuration: condition có thể nhận diện bean do ứng dụng khai báo và không đăng ký default bean.

### 15.1. Không cần tự bật bean overriding

Với thiết kế back-off đúng:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new DefaultGreetingService(...);
}
~~~

consumer có thể đăng ký GreetingService riêng mà không cần hai definition trùng tên và không cần bật cơ chế overriding.

### 15.2. Khi có nhiều auto-configuration phụ thuộc nhau

Nếu một auto-configuration cần bean do auto-configuration khác cung cấp, có thể khai báo thứ tự tương đối:

~~~java
@AutoConfiguration(after = GreetingCoreAutoConfiguration.class)
public class GreetingMetricsAutoConfiguration {
    // ...
}
~~~

Các thuộc tính before/after điều khiển thứ tự giữa các auto-configuration. Chúng không phải công cụ sắp xếp mọi bean trong ứng dụng.

Không nên dựa vào thứ tự ngẫu nhiên của classpath hoặc component scan để quyết định @ConditionalOnMissingBean có nhìn thấy một bean khác hay không.

### 15.3. Giữ điều kiện về bean ở method khi có thể

Với auto-configuration, method-level @ConditionalOnMissingBean thường là lựa chọn rõ ràng vì mỗi bean mặc định có thể back-off độc lập. Class-level @ConditionalOnMissingBean chỉ nên dùng khi toàn bộ nhóm cấu hình thực sự cần nhường chỗ cùng nhau.

## 16. Tùy biến auto-configuration bằng property

Một auto-configuration hữu ích thường cho phép người dùng điều chỉnh hành vi mà không cần thay bean.

Ví dụ:

~~~yaml
demo:
  greeting:
    enabled: true
    prefix: "Chào"
~~~

Property nên có:

- Prefix ổn định, có namespace riêng của thư viện.
- Tên phản ánh ý nghĩa nghiệp vụ.
- Giá trị mặc định hợp lý.
- Tài liệu rõ về tác động khi thiếu hoặc sai giá trị.

Không nên dùng một property chung chung như **enabled** ở root của toàn ứng dụng. Dùng prefix như demo.greeting giúp tránh xung đột với property của thư viện khác.

### 16.1. Property bật/tắt và bean override là hai quyết định khác nhau

Giả sử demo.greeting.enabled=false nhưng consumer vẫn khai báo custom GreetingService. Nếu @ConditionalOnProperty được đặt ở cấp class như ví dụ, toàn bộ auto-configuration bị bỏ qua; bean custom do ứng dụng khai báo vẫn tồn tại.

Property này điều khiển **cấu hình tự động của thư viện**, không có quyền xóa bean mà consumer tự đăng ký.

Nếu yêu cầu nghiệp vụ là tắt toàn bộ tính năng kể cả custom implementation, consumer cần tự điều khiển việc đăng ký bean hoặc service ở cấp ứng dụng; auto-configuration không nên tự ý loại bỏ bean do người dùng quản lý.

## 17. Chẩn đoán khi auto-configuration không hoạt động

Nếu bean mặc định không xuất hiện, hãy kiểm tra theo trình tự:

### Bước 1: Xác nhận auto-configuration đã được đăng ký

Kiểm tra resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đảm bảo tên class đầy đủ và file được đóng gói vào artifact.

### Bước 2: Kiểm tra classpath

Nếu class configuration hoặc nested configuration có @ConditionalOnClass, xác nhận dependency có trên runtime classpath. Test classpath có thể khác runtime production.

### Bước 3: Kiểm tra property

Xác nhận property có đúng prefix, tên và giá trị. Với @ConditionalOnProperty, chú ý havingValue và matchIfMissing.

### Bước 4: Kiểm tra back-off

Nếu @ConditionalOnMissingBean không match, có thể ứng dụng đã cung cấp bean phù hợp. Truy vấn ApplicationContext hoặc Actuator để xác định bean name và type.

### Bước 5: Đọc Condition Evaluation Report

Chạy ứng dụng với:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot có thể in Condition Evaluation Report, trong đó cho biết auto-configuration nào match hoặc không match và lý do.

### Bước 6: Phân biệt không đăng ký với tạo bean thất bại

Nếu condition match nhưng constructor hoặc factory method lỗi, đọc BeanCreationException và cause chain. Condition match không bảo đảm bean khởi tạo thành công.

## 18. Những nguyên tắc khi thiết kế auto-configuration

1. **Cung cấp mặc định có thể thay thế.** Consumer nên dùng được ngay nhưng vẫn có thể đăng ký bean riêng.
2. **Dùng @ConditionalOnMissingBean trên từng bean mặc định.** Điều này giữ các bean độc lập khi một bean khác được tùy biến.
3. **Đặt điều kiện ở đúng phạm vi.** Điều kiện nền chung đặt ở class hoặc nested configuration; điều kiện riêng đặt ở method.
4. **Khai báo property rõ ràng.** Dùng prefix riêng, giá trị mặc định có chủ ý và semantics dễ hiểu.
5. **Bảo vệ optional dependency.** Dùng @ConditionalOnClass và nested configuration cho phần code tham chiếu thư viện tùy chọn.
6. **Giữ API ổn định.** Consumer phụ thuộc interface; implementation mặc định có thể thay đổi bên trong thư viện.
7. **Tránh bean name trùng lặp.** Back-off theo type hoặc name thay vì dựa vào overriding.
8. **Chú ý thứ tự auto-configuration.** Dùng before/after khi một cấu hình thực sự phụ thuộc cấu hình khác.
9. **Kiểm thử các nhánh condition.** Test default, user override, property disabled và optional class.
10. **Giữ auto-configuration tập trung.** Tách các nhóm tính năng độc lập thành nested configuration hoặc auto-configuration riêng.

## 19. Những hiểu nhầm thường gặp

**“Thêm @AutoConfiguration là Boot tự tìm thấy class ở mọi package.”**  
Không. Auto-configuration cần được đăng ký qua metadata, với Spring Boot 3 là file AutoConfiguration.imports.

**“@ConditionalOnMissingBean tạo bean nếu không có bean cùng tên.”**  
Thông thường condition được dùng để kiểm tra bean phù hợp theo kiểu hoặc điều kiện đã chỉ định; nó không đơn giản chỉ so sánh tên. Dùng thuộc tính name nếu chủ đích là kiểm tra một bean name cụ thể.

**“Back-off xóa bean mặc định hoặc thay bean custom.”**  
Không. Back-off chỉ khiến factory method mặc định không đăng ký bean khi đã có bean phù hợp.

**“@Primary thay thế @ConditionalOnMissingBean.”**  
Không. @Primary chọn một candidate khi inject dependency đơn; @ConditionalOnMissingBean quyết định có tạo bean mặc định hay không.

**“Đặt @ConditionalOnMissingBean ở cấp class luôn gọn hơn.”**  
Không. Nó có thể làm biến mất cả những bean khác mà ứng dụng vẫn cần. Dùng method-level condition khi các bean có thể override độc lập.

**“Bean custom phải dùng cùng tên với bean mặc định.”**  
Không. Back-off theo kiểu có thể nhận diện bean phù hợp dù tên khác.

**“Property enabled=false sẽ xóa mọi bean của tính năng.”**  
Không. Nó chỉ điều khiển cấu hình được gắn condition; bean do ứng dụng khai báo không tự bị xóa.

**“Condition match nghĩa bean chắc chắn khởi tạo thành công.”**  
Không. Constructor, factory method, dependency hoặc cấu hình bên ngoài vẫn có thể gây lỗi.

**“Auto-configuration cần được thêm vào component scan.”**  
Không. Cơ chế đăng ký auto-configuration riêng giúp Boot phát hiện cấu hình từ metadata.

**“Chỉ test trường hợp mặc định là đủ.”**  
Không. Back-off chỉ được chứng minh khi test có bean tùy chỉnh và xác nhận default bean nhường chỗ.

## Ghi nhớ cốt lõi

Một auto-configuration nhỏ nên cung cấp bean mặc định khi điều kiện phù hợp và **back-off** khi ứng dụng đã cung cấp bean riêng. Với Spring Boot 3, đăng ký class qua **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**, dùng **@AutoConfiguration** để khai báo cấu hình, **@EnableConfigurationProperties** để bind property, và **@ConditionalOnMissingBean** trên từng factory method mặc định để cho phép override rõ ràng.

Hãy đặt condition class-level cho điều kiện nền chung của toàn bộ cấu hình, method-level cho từng bean tùy chọn, và nested configuration cho nhóm phụ thuộc thư viện optional. Kiểm thử ít nhất trường hợp dùng default bean, trường hợp custom bean khiến auto-configuration nhường chỗ, và trường hợp property tắt. Khi back-off được thiết kế và kiểm chứng rõ ràng, starter có thể cung cấp trải nghiệm mặc định tiện lợi mà vẫn giữ quyền tùy biến ở phía ứng dụng.
