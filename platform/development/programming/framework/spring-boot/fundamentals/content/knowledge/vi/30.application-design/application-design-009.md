# Thiết kế thư viện dùng chung có cấu hình rõ và khả năng tùy chỉnh

Một thư viện dùng chung trong hệ sinh thái Spring Boot cần đáp ứng hai yêu cầu: **cung cấp hành vi mặc định đủ hữu ích để ứng dụng sử dụng nhanh**, đồng thời **cho phép từng ứng dụng thay đổi hành vi mà không phải sửa mã nguồn thư viện**.

Nếu thư viện tự đọc environment variables, tự tạo kết nối trong constructor, truy cập ApplicationContext ở khắp nơi hoặc buộc ứng dụng dùng một implementation cố định, nó sẽ khó kiểm thử và khó tích hợp. Nếu thư viện phơi bày quá nhiều chi tiết nội bộ, người dùng lại phải hiểu implementation mới sử dụng được.

Thiết kế tốt đặt ranh giới rõ ràng giữa:

- **API và quy tắc cốt lõi:** thư viện cung cấp chức năng gì và những quy tắc nào phải luôn đúng.
- **Cấu hình:** những lựa chọn có thể thay đổi theo ứng dụng hoặc môi trường.
- **Cơ chế khởi tạo Spring:** đăng ký bean, bind properties và chọn implementation mặc định.
- **Điểm mở rộng:** interface, strategy, callback hoặc bean mà ứng dụng có thể thay thế.
- **Hạ tầng:** HTTP, database, filesystem, scheduler hoặc adapter phụ thuộc framework.

Bài học dùng một thư viện retry policy làm ví dụ. Thư viện cung cấp quy tắc số lần thử và khoảng chờ, có giá trị mặc định, hỗ trợ cấu hình qua application.yml, đồng thời cho phép ứng dụng thay bằng policy riêng. Cùng nguyên tắc có thể áp dụng cho thư viện client, audit, messaging, file processing hoặc các module nội bộ.

## 1. Thư viện dùng chung cần bảo vệ điều gì?

Một thư viện được nhiều ứng dụng sử dụng thường sống lâu hơn một feature đơn lẻ. Nó có thể được nâng version độc lập, được kéo vào nhiều dependency graph và chạy trong những môi trường khác nhau.

Trước khi viết bean configuration, hãy xác định:

1. Chức năng công khai của thư viện là gì?
2. Quy tắc nghiệp vụ hoặc thuật toán nào thuộc thư viện?
3. Những tham số nào người dùng cần cấu hình?
4. Hành vi mặc định nào an toàn và dễ hiểu?
5. Thành phần nào người dùng có thể thay thế?
6. Thư viện phụ thuộc vào Spring Boot hay chỉ cung cấp Java API?
7. Khi cấu hình sai, lỗi được báo ở thời điểm nào và bằng thông điệp nào?
8. Làm sao để kiểm thử thư viện mà không khởi động toàn bộ ứng dụng?

Một thư viện tốt có contract rõ ràng. Người dùng biết method nào ổn định, property nào có ý nghĩa, default nào được áp dụng và cách thay đổi behavior.

### 1.1. Ví dụ: thư viện retry policy

Giả sử nhiều ứng dụng nội bộ gọi dịch vụ ngoài và cần quy tắc retry thống nhất. Các ứng dụng có thể khác nhau về số lần thử tối đa, khoảng chờ ban đầu, hệ số tăng thời gian chờ, khoảng chờ tối đa và chính sách riêng theo loại thao tác.

Thay vì mỗi ứng dụng tự viết vòng lặp retry, thư viện cung cấp API:

~~~java
package com.example.retry;

import java.time.Duration;

public interface RetryPolicy {

    int maxAttempts();

    Duration delayBeforeAttempt(int failedAttempt);
}
~~~

Contract này diễn đạt hai điều: số lần thử tối đa và khoảng chờ trước lần thử tiếp theo sau một lần thất bại.

Thư viện không cần biết ứng dụng đang gọi HTTP, database hay message broker. Nó chỉ cung cấp quy tắc. Thành phần thực thi retry có thể sử dụng policy đó ở tầng phù hợp.

### 1.2. Vì sao không đưa mọi thứ vào một class?

Một class vừa đọc YAML, vừa tạo bean, vừa thực hiện retry, vừa gọi HTTP và vừa quyết định fallback sẽ có quá nhiều trách nhiệm.

Khi người dùng muốn thay policy, họ có thể phải thay cả transport. Khi đổi Spring Boot version, logic nghiệp vụ cũng bị ảnh hưởng. Khi unit test, test phải dựng hàng loạt dependency không liên quan.

Tách trách nhiệm giúp mỗi phần có contract và vòng đời phù hợp.

## 2. Phân biệt library, auto-configuration và starter

Một thư viện Spring Boot có thể được đóng gói thành nhiều module:

| Module | Trách nhiệm | Có cần Spring Boot không? |
| --- | --- | --- |
| retry-api | Interface và kiểu dữ liệu công khai | Không |
| retry-core | Implementation mặc định, thuật toán thuần Java | Không |
| retry-spring-boot-autoconfigure | Bind properties và đăng ký bean mặc định | Có |
| retry-spring-boot-starter | Dependency thuận tiện để ứng dụng thêm một lần | Có |

Không phải dự án nào cũng cần bốn module. Với thư viện nhỏ, API/core có thể nằm chung một module. Khi nhiều ứng dụng dùng Java API mà không dùng Spring Boot, tách core khỏi integration layer giúp họ không phải kéo Spring dependencies.

### 2.1. Library core

Core chứa interface công khai, value objects, thuật toán hoặc quy tắc mặc định, exception thuộc contract nếu cần và dependency thuần Java thiết yếu.

Core không nên cần ApplicationContext, Environment, @Autowired hay @ConfigurationProperties để thực hiện logic chính.

### 2.2. Auto-configuration module

Module này biết Spring Boot và chịu trách nhiệm:

- Đăng ký configuration properties.
- Tạo bean mặc định khi feature được bật.
- Lùi lại khi ứng dụng cung cấp implementation riêng.
- Kiểm tra classpath/property conditions.
- Kết nối các thành phần Spring-specific.

Auto-configuration là composition mechanism. Nó quyết định object nào được tạo và nối với nhau; nó không nên chứa toàn bộ thuật toán nghiệp vụ.

### 2.3. Starter module

Starter chủ yếu gom dependency phù hợp để người dùng thêm một dependency vào ứng dụng. Nó không cần chứa thuật toán retry hoặc API nghiệp vụ.

### 2.4. Khi nào nên tách module?

Tách khi có nhu cầu thực tế: nhiều ứng dụng cần core mà không cần Spring, auto-configuration có dependency khác core, starter cần quản lý dependency graph thuận tiện, hoặc versioning/ownership khác nhau.

Đừng tạo nhiều module chỉ để tăng số thư mục. Ranh giới module cần phản ánh ranh giới phụ thuộc hoặc cách phân phối thật.

## 3. Đặt ranh giới giữa quy tắc cốt lõi và Spring

Một cách tổ chức phổ biến:

~~~text
Application
    |
    v
Application service / use case
    |
    v
Public library API
    |
    v
Core implementation
    |
    v
Ports / interfaces
    |
    +------ Adapter do ứng dụng cung cấp
    |
    +------ Adapter mặc định của thư viện
~~~

Spring Boot ở lớp composition:

~~~text
Spring Boot ApplicationContext
    |
    +--> Bind configuration properties
    |
    +--> Register default beans
    |
    +--> Select user-provided overrides
    |
    +--> Inject dependencies
             |
             v
       Application services
             |
             v
          Core API
~~~

### 3.1. Core không nên tự tìm bean

Không nên để logic retry tự gọi ApplicationContext rồi lấy RetryPolicy bằng getBean. Đây là service locator: class tự đi tìm dependency trong container. Nó làm dependency ẩn khỏi constructor và khiến test phải dựng context hoặc giả lập global state.

Nên truyền dependency tường minh:

~~~java
public final class RetryExecutor {

    private final RetryPolicy policy;

    public RetryExecutor(RetryPolicy policy) {
        this.policy = Objects.requireNonNull(policy);
    }
}
~~~

Người gọi quyết định lấy policy từ Spring hay tạo trực tiếp.

### 3.2. Không để domain phụ thuộc vào Environment

Tránh để core nhận Spring Environment rồi tự đọc company.retry.max-attempts. Class này vừa đọc cấu hình, vừa quyết định thuật toán. Nó phụ thuộc Spring và khó được tái sử dụng ngoài Spring.

Thay vào đó, Spring bind properties rồi truyền các giá trị đã được chuyển đổi vào constructor core.

### 3.3. Spring annotation ở lớp tích hợp là hợp lý

Không phải annotation Spring nào cũng cần bị loại khỏi mọi class. Application service có thể được đăng ký bằng @Service, adapter có thể dùng @Component, và auto-configuration cần @Configuration.

Điều cần tránh là để **quy tắc cốt lõi buộc phải khởi động Spring mới chạy được**. Spring annotations ở lớp tích hợp là cách kết nối, không phải business rule.

## 4. Thiết kế public API trước khi viết auto-configuration

API là contract mà ứng dụng khác sẽ biên dịch dựa vào. Vì vậy, cần giữ nó nhỏ, ổn định và có ý nghĩa.

Interface:

~~~java
package com.example.retry;

import java.time.Duration;

public interface RetryPolicy {

    int maxAttempts();

    Duration delayBeforeAttempt(int failedAttempt);
}
~~~

Một implementation mặc định:

~~~java
package com.example.retry;

import java.time.Duration;
import java.util.Objects;

public final class DefaultRetryPolicy implements RetryPolicy {

    private final int maxAttempts;
    private final Duration initialDelay;
    private final int multiplier;
    private final Duration maxDelay;

    public DefaultRetryPolicy(
            int maxAttempts,
            Duration initialDelay,
            int multiplier,
            Duration maxDelay) {

        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be at least 1"
            );
        }

        this.initialDelay = Objects.requireNonNull(initialDelay);
        this.maxDelay = Objects.requireNonNull(maxDelay);

        if (initialDelay.isNegative() || initialDelay.isZero()) {
            throw new IllegalArgumentException(
                    "initialDelay must be positive"
            );
        }

        if (multiplier < 1) {
            throw new IllegalArgumentException(
                    "multiplier must be at least 1"
            );
        }

        if (maxDelay.compareTo(initialDelay) < 0) {
            throw new IllegalArgumentException(
                    "maxDelay must not be smaller than initialDelay"
            );
        }

        this.maxAttempts = maxAttempts;
        this.multiplier = multiplier;
    }

    @Override
    public int maxAttempts() {
        return maxAttempts;
    }

    @Override
    public Duration delayBeforeAttempt(int failedAttempt) {
        if (failedAttempt < 1) {
            throw new IllegalArgumentException(
                    "failedAttempt must be at least 1"
            );
        }

        Duration delay = initialDelay;

        for (int attempt = 1; attempt < failedAttempt; attempt++) {
            if (delay.compareTo(maxDelay) >= 0) {
                return maxDelay;
            }

            try {
                delay = delay.multipliedBy(multiplier);
            } catch (ArithmeticException overflow) {
                return maxDelay;
            }
        }

        return delay.compareTo(maxDelay) > 0
                ? maxDelay
                : delay;
    }
}
~~~

Implementation này là Java thuần. Nó không đọc property, không biết Spring và không ngủ thread.

### 4.1. Định nghĩa rõ ý nghĩa tham số

Với policy trên:

- maxAttempts = 3 nghĩa là tổng số lần thực thi tối đa là ba, nếu executor định nghĩa attempt theo cách đó.
- failedAttempt = 1 trả về khoảng chờ ban đầu trước lần thử kế tiếp.
- multiplier = 2 tạo dãy 200 ms, 400 ms, 800 ms...
- maxDelay giới hạn khoảng chờ.

Tên và semantics phải được tài liệu hóa. Nếu một implementation coi maxAttempts là số lần retry cộng thêm sau lần đầu, còn implementation khác coi đó là tổng số lần thực hiện, người dùng sẽ gặp lỗi khó phát hiện.

### 4.2. Không đưa Thread.sleep vào policy

Policy nên **trả về quyết định**, không tự thực thi thời gian chờ. Việc chờ có thể dùng blocking sleep, scheduler, reactive delay hoặc cơ chế của message broker.

Tách quyết định khỏi thực thi giúp cùng policy được dùng trong nhiều runtime.

### 4.3. Tránh public API chứa chi tiết nội bộ

Không nên công khai ApplicationContext, BeanFactory, class implementation nội bộ hoặc builder chỉ phục vụ Spring nếu người dùng không cần nó.

API càng nhỏ, việc thay implementation và nâng version càng dễ.

## 5. Cấu hình phải có namespace và semantics rõ ràng

Một thư viện không nên đặt property quá chung:

~~~properties
enabled=true
timeout=5s
max-attempts=3
~~~

Những tên này có thể xung đột với cấu hình của ứng dụng hoặc thư viện khác.

Dùng prefix riêng:

~~~yaml
company:
  retry:
    enabled: true
    max-attempts: 3
    initial-delay: 200ms
    multiplier: 2
    max-delay: 5s
~~~

Prefix company.retry chỉ là ví dụ; thư viện thực tế nên dùng namespace của tổ chức hoặc sản phẩm.

### 5.1. Tên property phản ánh mục đích

| Property | Ý nghĩa |
| --- | --- |
| company.retry.enabled | Bật/tắt auto-configured retry policy |
| company.retry.max-attempts | Tổng số lần thử tối đa theo contract |
| company.retry.initial-delay | Khoảng chờ sau lần thất bại đầu tiên |
| company.retry.multiplier | Hệ số tăng khoảng chờ |
| company.retry.max-delay | Giới hạn khoảng chờ |

Tên property cần ổn định qua các version. Nếu phải đổi tên, cân nhắc alias/deprecation path thay vì âm thầm xóa property cũ.

### 5.2. Phân biệt default, required và optional

Một cấu hình nên xác định default khi không khai báo, property bắt buộc, property chỉ cần khi feature được bật, giá trị hợp lệ và giới hạn, đơn vị thời gian và điều gì xảy ra khi property không hợp lệ.

Không nên để một giá trị ngầm định quan trọng mà người dùng không thể khám phá qua tài liệu hoặc IDE metadata.

### 5.3. Default nên phù hợp với mục đích chung

Default của thư viện nên an toàn và dễ dự đoán. Với retry, cần cân nhắc số lần thử và thời gian chờ để không tạo tải lớn lên dịch vụ đang lỗi.

Không phải thao tác nào cũng retry an toàn. Retry một lệnh ghi không idempotent có thể tạo giao dịch trùng. Thư viện cung cấp policy không nên tự tuyên bố mọi exception đều có thể retry.

## 6. Bind properties vào một kiểu cấu hình riêng

Trong module auto-configuration, tạo class properties:

~~~java
package com.example.retry.autoconfigure;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "company.retry")
@Validated
public class RetryProperties {

    private boolean enabled = true;

    @Min(1)
    private int maxAttempts = 3;

    @NotNull
    private Duration initialDelay = Duration.ofMillis(200);

    @Min(1)
    private int multiplier = 2;

    @NotNull
    private Duration maxDelay = Duration.ofSeconds(5);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public Duration getInitialDelay() {
        return initialDelay;
    }

    public void setInitialDelay(Duration initialDelay) {
        this.initialDelay = initialDelay;
    }

    public int getMultiplier() {
        return multiplier;
    }

    public void setMultiplier(int multiplier) {
        this.multiplier = multiplier;
    }

    public Duration getMaxDelay() {
        return maxDelay;
    }

    public void setMaxDelay(Duration maxDelay) {
        this.maxDelay = maxDelay;
    }
}
~~~

Đây là JavaBean properties để Spring Boot Binder điền giá trị. @ConfigurationProperties tách việc đọc cấu hình khỏi core implementation.

### 6.1. Vì sao không inject @Value vào mọi class?

Nếu mỗi class tự khai báo field @Value, cấu hình bị phân tán và khó biết toàn bộ contract của thư viện. Một properties object tập trung giúp nhìn thấy cấu hình trong một nơi, kiểm tra và validate cùng nhau, dễ viết tài liệu và không buộc core phụ thuộc Spring.

### 6.2. Validation phải phản ánh quy tắc thật

@Min(1) kiểm tra số lần thử tối thiểu; @NotNull kiểm tra thời gian không null. Constructor của DefaultRetryPolicy vẫn kiểm tra invariant quan trọng như thời gian dương và maxDelay không nhỏ hơn initialDelay.

Validation ở tầng cấu hình đưa thông báo sớm; constructor core bảo vệ invariant ngay cả khi implementation được tạo ngoài Spring.

### 6.3. Validation dependency

Các constraint Jakarta Validation cần validation provider và integration phù hợp. Trong Spring Boot, thường thêm starter validation nếu ứng dụng muốn bật Bean Validation. Auto-configuration module nên khai báo dependency và optionality phù hợp với packaging strategy.

Nếu thư viện không muốn bắt buộc validation provider, có thể kiểm tra giá trị trong factory method/core constructor và chỉ bật Bean Validation khi dependency có mặt. Hành vi khi thiếu provider phải được xác định rõ.

### 6.4. Không validate property không cần thiết khi feature bị tắt

Nếu một feature có property bắt buộc chỉ khi enabled, thiết kế validation cần phản ánh điều đó. Đừng validate endpoint như bắt buộc cho mọi môi trường nếu feature được phép tắt.

Có thể dùng nested properties, conditional configuration hoặc validator có xét trạng thái enabled. Validation phải xét điều kiện sử dụng thực tế.

## 7. Auto-configuration tạo bean mặc định

Trong Spring Boot 3, auto-configuration có thể dùng @AutoConfiguration:

~~~java
package com.example.retry.autoconfigure;

import com.example.retry.DefaultRetryPolicy;
import com.example.retry.RetryPolicy;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(RetryPolicy.class)
@ConditionalOnProperty(
        prefix = "company.retry",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
@EnableConfigurationProperties(RetryProperties.class)
public class RetryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RetryPolicy.class)
    RetryPolicy retryPolicy(RetryProperties properties) {
        return new DefaultRetryPolicy(
                properties.getMaxAttempts(),
                properties.getInitialDelay(),
                properties.getMultiplier(),
                properties.getMaxDelay()
        );
    }
}
~~~

Auto-configuration thực hiện ba việc:

1. Chỉ được áp dụng khi class API có trên classpath.
2. Bật feature theo property company.retry.enabled, mặc định bật nếu property không được khai báo.
3. Tạo RetryPolicy mặc định khi ứng dụng chưa cung cấp bean cùng contract.

### 7.1. @ConditionalOnClass

Condition này tránh đăng ký cấu hình khi class cần thiết không có trên classpath. Nó hữu ích với thư viện có integration tùy chọn.

### 7.2. @ConditionalOnProperty

Property enabled cho người dùng quyền tắt feature:

~~~yaml
company:
  retry:
    enabled: false
~~~

Khi đó auto-configuration trên không đăng ký default RetryPolicy. Library vẫn có thể nằm trong artifact, nhưng bean tự động không được tạo.

### 7.3. @ConditionalOnMissingBean

Đây là điểm quan trọng cho khả năng tùy chỉnh. Nếu ứng dụng tự cung cấp bean RetryPolicy, auto-configuration lùi lại và không tạo default bean.

Nhờ đó, ứng dụng có thể thay đổi behavior mà không fork thư viện hoặc sửa source của nó.

### 7.4. Auto-configuration cần được phát hiện

Với Spring Boot 3, khai báo file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung một dòng:

~~~text
com.example.retry.autoconfigure.RetryAutoConfiguration
~~~

File này được đóng gói trong auto-configuration JAR để Boot tìm thấy cấu hình.

Các dòng Spring Boot cũ có cơ chế đăng ký auto-configuration khác, ví dụ spring.factories ở những version trước. Hãy chọn cơ chế tương thích với Boot version mà thư viện công bố hỗ trợ.

## 8. Tùy chỉnh qua properties và thay thế bean

Một thư viện nên cung cấp ít nhất hai mức tùy chỉnh:

1. **Cấu hình dữ liệu:** người dùng thay đổi tham số mà vẫn dùng implementation mặc định.
2. **Thay thế strategy:** người dùng cung cấp implementation khác khi behavior mặc định không đủ.

### 8.1. Tùy chỉnh qua YAML

~~~yaml
company:
  retry:
    enabled: true
    max-attempts: 5
    initial-delay: 300ms
    multiplier: 2
    max-delay: 8s
~~~

Ứng dụng không cần tạo bean riêng. Spring Binder điền RetryProperties; auto-configuration truyền giá trị vào DefaultRetryPolicy.

### 8.2. Tắt feature

~~~yaml
company:
  retry:
    enabled: false
~~~

Khi feature bị tắt, default bean không được tạo. Ứng dụng cần hiểu rằng những component bắt buộc RetryPolicy sẽ không thể inject nếu vẫn được đăng ký. Vì vậy consumer cần cấu hình những component đó có điều kiện hoặc chọn contract khác cho tình huống feature optional.

### 8.3. Cung cấp bean tùy chỉnh

~~~java
@Configuration(proxyBeanMethods = false)
public class ApplicationRetryConfiguration {

    @Bean
    RetryPolicy applicationRetryPolicy() {
        return new RetryPolicy() {

            @Override
            public int maxAttempts() {
                return 2;
            }

            @Override
            public Duration delayBeforeAttempt(int failedAttempt) {
                return Duration.ofMillis(100);
            }
        };
    }
}
~~~

Khi bean này có mặt, @ConditionalOnMissingBean khiến default bean không được đăng ký.

### 8.4. Đừng yêu cầu người dùng exclude toàn bộ auto-configuration để thay một bean

Nếu người dùng chỉ muốn thay policy, họ không nên phải exclude RetryAutoConfiguration, tự bind properties, tạo mọi bean liên quan và lặp lại phần wiring nội bộ.

Một extension point tốt cho phép thay đúng behavior cần thay, còn phần còn lại của thư viện tiếp tục hoạt động.

## 9. Extension point: interface, strategy và callback

Không phải mọi khác biệt đều nên trở thành property. Properties phù hợp với lựa chọn dạng dữ liệu; behavior khác nhau nên có extension point có kiểu rõ ràng.

### 9.1. Strategy interface

RetryPolicy là một strategy. Một ứng dụng có thể cài policy theo tenant hoặc theo loại thao tác:

~~~java
public final class TenantRetryPolicy implements RetryPolicy {

    private final int maxAttempts;

    public TenantRetryPolicy(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    @Override
    public int maxAttempts() {
        return maxAttempts;
    }

    @Override
    public Duration delayBeforeAttempt(int failedAttempt) {
        return Duration.ofMillis(100L * failedAttempt);
    }
}
~~~

Ứng dụng tự quyết định policy nào được đăng ký và cách chọn policy cho từng use case.

### 9.2. Callback/listener

Nếu thư viện cần cho phép ứng dụng quan sát lần retry, có thể cung cấp interface:

~~~java
public interface RetryListener {

    default void onRetry(
            String operation,
            int failedAttempt,
            Throwable failure,
            Duration nextDelay) {
    }
}
~~~

Executor có thể nhận một tập listener hoặc một callback. Người dùng đăng ký listener để ghi metric, audit hoặc tracing.

Không nên bắt người dùng subclass implementation nội bộ chỉ để nhận callback. Interface nhỏ và ổn định thường là extension point tốt hơn.

### 9.3. ObjectProvider khi cần nhiều bean tùy chọn

Trong auto-configuration, Spring ObjectProvider có thể giúp lấy một bean optional hoặc danh sách extension:

~~~java
@Bean
RetryObserver retryObserver(
        ObjectProvider<RetryListener> listeners) {

    return new CompositeRetryObserver(
            listeners.orderedStream().toList()
    );
}
~~~

ObjectProvider hữu ích khi dependency không bắt buộc hoặc có nhiều candidate. Không nên dùng nó như cách che giấu dependency bắt buộc; constructor injection trực tiếp dễ hiểu hơn.

### 9.4. Quy định thứ tự extension

Nếu nhiều listener/customizer được gọi, hãy xác định:

- Có hỗ trợ Ordered/@Order không?
- Thứ tự có ảnh hưởng kết quả không?
- Nếu hai customizer thay đổi cùng một thuộc tính, ai thắng?
- Có nên fail khi cấu hình xung đột không?

Không để behavior phụ thuộc vào thứ tự scan tình cờ nếu thứ tự đó có ý nghĩa.

## 10. Properties hay custom bean: chọn đúng công cụ

| Nhu cầu | Cơ chế phù hợp |
| --- | --- |
| Thay số lần retry | Configuration property |
| Thay khoảng chờ | Configuration property |
| Bật/tắt feature | Conditional property |
| Thay thuật toán hoàn toàn | Strategy bean |
| Thêm metric/audit callback | Listener bean |
| Cung cấp transport riêng | Adapter interface/bean |
| Thay toàn bộ composition | User configuration/auto-configuration exclusion |
| Thay giá trị theo request/tenant | Context hoặc argument rõ ràng trong API |

Một property không nên chứa tên class tùy ý để thư viện reflection rồi instantiate nếu một interface bean có thể diễn đạt điểm mở rộng tốt hơn.

### 10.1. Tránh cấu hình quá nhiều

Nếu thư viện có hàng trăm property, người dùng khó biết những lựa chọn nào quan trọng. Hãy giữ cấu hình tập trung vào các quyết định có giá trị và có default tốt.

### 10.2. Không dùng property để thay business decision của từng request

Property là cấu hình cấp ứng dụng/môi trường. Nếu retry policy phụ thuộc mức độ quan trọng của từng giao dịch hoặc tenant, hãy đưa thông tin đó vào API/strategy có kiểu thay vì đọc global property trong mỗi method.

## 11. Để ứng dụng kiểm soát profile và môi trường

Thư viện không nên tự kích hoạt profile dev, test hoặc prod. Profile là quyết định của ứng dụng triển khai.

Ứng dụng có thể đặt:

~~~yaml
# application-dev.yml
company:
  retry:
    max-attempts: 2
    initial-delay: 100ms
~~~

~~~yaml
# application-prod.yml
company:
  retry:
    max-attempts: 4
    initial-delay: 300ms
    max-delay: 5s
~~~

Thư viện chỉ cần bind property có hiệu lực. Nó không cần biết profile nào đang active nếu logic không phụ thuộc tên profile.

### 11.1. Không kiểm tra profile trong core

Tránh để thuật toán gọi Environment.acceptsProfiles hoặc tự chọn behavior theo tên profile.

Nếu behavior khác nhau theo môi trường, hãy để cấu hình chọn giá trị hoặc implementation phù hợp ở composition layer.

### 11.2. Profile không thay thế validation

Một file profile có thể bị thiếu hoặc override bởi environment variable. Dù giá trị đến từ nguồn nào, properties vẫn phải đáp ứng contract. Validate dữ liệu cuối cùng được bind, không chỉ validate một file YAML cụ thể.

### 11.3. Tránh hard-code môi trường triển khai

Thư viện không nên giả định ứng dụng luôn chạy trong Docker, Kubernetes, local IDE hoặc một cloud provider. Hãy cung cấp API/configuration trung lập và để ứng dụng cung cấp adapter cho hạ tầng riêng.

## 12. Tránh khởi tạo side effect trong constructor hoặc auto-configuration

Một lỗi thiết kế phổ biến là kết nối tới external service ngay khi Spring tạo bean:

~~~java
public RemoteCatalogClient(CatalogProperties properties) {
    this.connection = connect(properties.getEndpoint());
}
~~~

Nếu network chưa sẵn sàng, startup có thể thất bại dù ứng dụng chưa cần gọi chức năng catalog. Điều này cũng khiến context test phải dựng external service.

### 12.1. Constructor nên thiết lập object

Constructor phù hợp để kiểm tra argument, gán field, tạo object nội bộ nhẹ và thiết lập invariant không cần I/O.

Không nên dùng constructor để thực hiện request HTTP, chạy migration lớn, tải toàn bộ dataset hoặc chờ service ngoài nếu đó không phải yêu cầu rõ của startup.

### 12.2. Kết nối khi cần hoặc qua lifecycle có chủ đích

Tùy use case, có thể tạo HTTP client nhẹ nhưng mở connection khi request, lazy initialize tài nguyên, dùng lifecycle callback nếu tài nguyên bắt buộc phải sẵn sàng trước khi nhận traffic, hoặc dùng readiness/health check để biểu diễn dependency availability.

Không có một chiến lược duy nhất đúng cho mọi thư viện. Điều quan trọng là tài liệu phải nói rõ startup có phụ thuộc dịch vụ ngoài hay không.

### 12.3. Đừng retry vô hạn trong startup

Một bean factory method chờ network mãi có thể làm ứng dụng không bao giờ sẵn sàng. Nếu startup thật sự phải xác minh dependency, hãy có timeout, retry budget và thông báo lỗi cụ thể.

## 13. Giữ dependency direction ổn định

Một module có thể có dependency graph:

~~~text
retry-spring-boot-starter
          |
          v
retry-spring-boot-autoconfigure
          |
          v
retry-core
          |
          v
retry-api
~~~

Core không phụ thuộc ngược vào auto-configuration.

### 13.1. Vì sao dependency direction quan trọng?

Nếu retry-core import org.springframework.context.ApplicationContext, mọi ứng dụng dùng core đều phải kéo Spring context. Core cũng khó chạy trong command-line tool, batch job thuần Java hoặc một framework khác.

Nếu auto-configuration phụ thuộc core, ứng dụng dùng Spring Boot có đầy đủ chức năng, còn ứng dụng thuần Java vẫn dùng được API/core.

### 13.2. Tránh circular module dependencies

Không nên có retry-core phụ thuộc retry-spring trong khi retry-spring lại phụ thuộc retry-core. Nếu hai module cần chung contract, đưa contract về module thấp hơn.

### 13.3. API module không nhất thiết phải tách riêng

Nếu thư viện nhỏ, retry-core có thể chứa cả interface và default implementation. Chỉ tách retry-api khi có consumer cần contract mà không muốn kéo implementation hoặc khi nhiều implementation độc lập cần chia sẻ API.

## 14. Cấu hình auto-configuration để người dùng dễ override

Một auto-configuration nên có điều kiện classpath/property rõ ràng, tạo bean mặc định bằng @ConditionalOnMissingBean, không quét component package quá rộng, không tự đăng ký implementation trùng với bean người dùng, tách feature nếu chúng có điều kiện độc lập và dùng constructor injection cho bean factory dependencies.

### 14.1. Không component scan toàn bộ package thư viện

Một thư viện có thể khai báo @ComponentScan cho toàn bộ package của mình, nhưng cách này có thể vô tình đăng ký implementation, internal component hoặc bean không thuộc feature đang bật. Nó cũng làm người dùng khó kiểm soát những thành phần được tạo.

Với auto-configuration, thường nên khai báo bean tường minh qua @Bean methods và import configuration cần thiết. Điều đó giúp contract đăng ký bean rõ ràng.

### 14.2. @ConditionalOnMissingBean nên đặt đúng chỗ

~~~java
@Bean
@ConditionalOnMissingBean(RetryPolicy.class)
RetryPolicy retryPolicy(RetryProperties properties) {
    return new DefaultRetryPolicy(...);
}
~~~

Condition này giúp ứng dụng thay policy. Trong auto-configuration, thứ tự xử lý cấu hình và điều kiện cũng quan trọng; nếu có nhiều auto-configuration tương tác, dùng ordering/import rules phù hợp và test bằng context runner.

### 14.3. Không dựa vào bean definition order tình cờ

Nếu một bean mặc định cần back off khi bean người dùng tồn tại, dùng condition chính thức thay vì giả định component scan sẽ luôn chạy trước hay sau theo một thứ tự không được contract bảo đảm.

### 14.4. Tách feature độc lập

Nếu thư viện có retry policy và metrics integration, có thể tách cấu hình metrics theo điều kiện classpath/property. Ứng dụng không dùng metrics dependency vẫn có thể sử dụng core retry.

## 15. Configuration metadata giúp người dùng khám phá properties

Spring Boot có thể tạo metadata để IDE gợi ý property, mô tả và default values.

Với Maven, thêm configuration processor phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Khi build, processor có thể tạo metadata dưới META-INF/spring-configuration-metadata.json.

### 15.1. Mô tả property có giá trị thực tế

Ví dụ:

- max-attempts: tổng số lần gọi tối đa, bao gồm lần đầu.
- initial-delay: thời gian chờ sau lần thất bại đầu tiên.
- multiplier: hệ số nhân cho lần chờ tiếp theo.
- max-delay: giới hạn trên của thời gian chờ.

Mô tả này ngăn hiểu nhầm giữa “số lần retry” và “tổng số lần thử”.

### 15.2. Metadata không thay thế tài liệu

IDE metadata giúp autocomplete và quick documentation. Người dùng vẫn cần hướng dẫn về semantics, ví dụ, default, interaction giữa properties và cách override bean.

### 15.3. Không ghi secret vào metadata/default

Không cung cấp API key, password hoặc token làm default. Nếu thư viện cần secret, ứng dụng nên truyền từ secret manager/environment theo quy trình bảo mật của nó.

## 16. Kiểm thử core mà không cần Spring

Vì DefaultRetryPolicy là Java thuần, unit test không cần Spring Boot.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;

import org.junit.jupiter.api.Test;

class DefaultRetryPolicyTest {

    @Test
    void calculatesExponentialDelayWithMaximum() {
        RetryPolicy policy = new DefaultRetryPolicy(
                5,
                Duration.ofMillis(200),
                2,
                Duration.ofMillis(700)
        );

        assertEquals(
                Duration.ofMillis(200),
                policy.delayBeforeAttempt(1)
        );

        assertEquals(
                Duration.ofMillis(400),
                policy.delayBeforeAttempt(2)
        );

        assertEquals(
                Duration.ofMillis(700),
                policy.delayBeforeAttempt(3)
        );
    }

    @Test
    void rejectsInvalidAttemptNumber() {
        RetryPolicy policy = new DefaultRetryPolicy(
                3,
                Duration.ofMillis(100),
                2,
                Duration.ofSeconds(1)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> policy.delayBeforeAttempt(0)
        );
    }
}
~~~

Test này xác minh thuật toán và constructor invariants. Không cần @SpringBootTest, không cần bind YAML.

### 16.1. Test các giới hạn

Nên kiểm tra maxAttempts nhỏ nhất, initialDelay bằng zero hoặc âm, maxDelay nhỏ hơn initialDelay, multiplier bằng 1, delay chạm giới hạn tối đa, attempt number không hợp lệ và giá trị lớn có thể gây overflow.

Core unit tests nhanh giúp bắt lỗi thuật toán mà không bị ảnh hưởng bởi Spring configuration.

## 17. Kiểm thử properties và auto-configuration bằng ApplicationContextRunner

Auto-configuration là phần Spring-specific, nên cần test context. ApplicationContextRunner giúp tạo context nhỏ, cung cấp properties và quan sát bean.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class RetryAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    RetryAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultPolicy() {
        runner.run(context -> {
            assertThat(context)
                    .hasSingleBean(RetryPolicy.class);

            RetryPolicy policy =
                    context.getBean(RetryPolicy.class);

            assertThat(policy.maxAttempts()).isEqualTo(3);
        });
    }

    @Test
    void bindsCustomProperties() {
        runner.withPropertyValues(
                "company.retry.max-attempts=5",
                "company.retry.initial-delay=300ms",
                "company.retry.multiplier=3",
                "company.retry.max-delay=4s"
        ).run(context -> {
            assertThat(context).hasSingleBean(RetryPolicy.class);

            RetryPolicy policy =
                    context.getBean(RetryPolicy.class);

            assertThat(policy.maxAttempts()).isEqualTo(5);
            assertThat(policy.delayBeforeAttempt(1))
                    .isEqualTo(Duration.ofMillis(300));
        });
    }

    @Test
    void backsOffWhenUserProvidesPolicy() {
        RetryPolicy custom = new RetryPolicy() {

            @Override
            public int maxAttempts() {
                return 1;
            }

            @Override
            public Duration delayBeforeAttempt(int failedAttempt) {
                return Duration.ZERO;
            }
        };

        runner.withBean("customRetryPolicy", RetryPolicy.class, () -> custom)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(RetryPolicy.class);

                    assertThat(context.getBean(RetryPolicy.class))
                            .isSameAs(custom);
                });
    }

    @Test
    void doesNotCreatePolicyWhenDisabled() {
        runner.withPropertyValues(
                "company.retry.enabled=false"
        ).run(context -> {
            assertThat(context)
                    .doesNotHaveBean(RetryPolicy.class);
        });
    }
}
~~~

Ví dụ giả định Spring Boot Test và Spring Framework version hỗ trợ những API được dùng. Khi triển khai, import và API của runner phải khớp version được project quản lý.

### 17.1. Test default values

Không chỉ kiểm tra bean tồn tại. Xác nhận default có đúng contract đã tài liệu hóa.

### 17.2. Test custom properties

Cung cấp property values và kiểm tra policy nhận đúng giá trị. Điều này xác minh đường đi từ Binder đến factory method.

### 17.3. Test back-off

Đăng ký bean người dùng và xác nhận auto-configuration không tạo thêm default bean.

### 17.4. Test disabled condition

Xác nhận enabled=false làm bean mặc định không xuất hiện. Nếu consumer bean vẫn phụ thuộc policy, đó là vấn đề composition của ứng dụng cần được thiết kế và test riêng.

## 18. Kiểm thử configuration validation và lỗi startup

Một thư viện có cấu hình sai nên fail với thông điệp đủ rõ.

Ví dụ:

~~~yaml
company:
  retry:
    max-attempts: 0
    initial-delay: -5ms
~~~

Có thể kiểm thử qua context runner hoặc Boot context có validation infrastructure.

Điều cần xác minh:

- Bean properties được đăng ký.
- Binder đọc property.
- Constraint validation được kích hoạt.
- Context báo property/field không hợp lệ.
- Không có default bean được tạo với giá trị sai.

### 18.1. Fail fast khi lỗi thực sự bắt buộc

Nếu property là bắt buộc để thư viện hoạt động, fail startup với message rõ thường tốt hơn để ứng dụng chạy rồi thất bại ở request đầu tiên.

### 18.2. Không validate mọi thứ theo cách cứng nhắc

Một property optional không nên làm startup fail khi feature đã tắt. Validation cần xét điều kiện sử dụng thực tế.

### 18.3. Không che lỗi bằng fallback bất ngờ

Nếu người dùng nhập max-attempts=0, đừng tự âm thầm chuyển về 3 trừ khi đó là contract được công bố. Silent fallback khiến cấu hình sai khó phát hiện.

## 19. Thread safety và lifecycle của shared beans

Spring singleton bean thường được chia sẻ giữa nhiều request/thread. Nếu auto-configuration đăng ký một policy singleton, implementation nên bất biến hoặc thread-safe.

DefaultRetryPolicy trong ví dụ chỉ giữ các field final và không có mutable per-call state, nên có thể được chia sẻ an toàn theo thiết kế đó.

### 19.1. Không giữ state của từng lần gọi trong singleton field

Tránh:

~~~java
@Component
public class RetryExecutor {

    private int currentAttempt;

    public void execute() {
        currentAttempt = 0;
        // ...
    }
}
~~~

Nhiều request đồng thời có thể ghi đè currentAttempt của nhau. State của từng lần thực thi nên nằm trong local variables hoặc execution context riêng.

### 19.2. Bean có tài nguyên phải quản lý lifecycle

Nếu thư viện tạo executor, scheduler, connection pool hoặc thread, cần quy định ai sở hữu và ai đóng tài nguyên.

- Bean singleton do Spring quản lý có thể dùng destroy callback.
- Object được tạo thủ công phải có API close/lifecycle rõ.
- Không tạo thread nền không có cách shutdown.
- Không để bean giữ reference tới request-scoped object lâu hơn scope.

### 19.3. Không mở tài nguyên trong static initializer

Static initializer chạy khi JVM khởi tạo class, khó gắn với Spring lifecycle và có thể làm lỗi xuất hiện trước khi context có đủ cấu hình. Hãy tạo tài nguyên trong bean lifecycle có chủ đích hoặc qua factory.

## 20. Quản lý transaction và lỗi trong thư viện

Một thư viện dùng chung cần thận trọng khi quyết định ranh giới transaction.

Core retry policy không nên tự mở transaction. Nó chỉ trả về số lần thử và khoảng chờ.

Nếu thư viện cung cấp service thao tác database, transaction boundary có thể thuộc application service hoặc adapter tùy semantics.

### 20.1. Retry transaction không đơn giản là gọi lại method

Nếu một thao tác thất bại giữa transaction, retry cần xác định transaction trước đã rollback chưa và lần thử mới có transaction sạch không. Việc đặt @Transactional và retry advice theo thứ tự không phù hợp có thể khiến retry chạy bên trong một transaction đã đánh dấu rollback-only.

Thư viện không nên hứa “retry mọi exception” mà không định nghĩa exception nào retry được, có retry business error không, mỗi lần thử có transaction mới không, operation có idempotent không và side effect đã phát sinh có thể lặp không.

### 20.2. Để ứng dụng chọn policy theo use case

Một thao tác đọc có thể retry khác thao tác ghi. Thay vì ép một global policy áp dụng cho mọi request, hãy để application layer truyền policy hoặc chọn strategy theo operation khi cần.

### 20.3. Không bắt exception quá rộng

Tránh catch mọi Throwable rồi retry. Những lỗi như OutOfMemoryError, linkage errors hoặc validation failures thường không thể giải quyết bằng cách gọi lại operation.

## 21. Versioning và compatibility của thư viện

Thư viện dùng chung cần có chính sách versioning rõ, đặc biệt nếu nhiều ứng dụng nâng cấp độc lập.

### 21.1. Public API là contract dài hạn

Thay đổi có thể gây breaking change:

- Xóa method/interface.
- Đổi kiểu tham số hoặc return type.
- Đổi semantics của maxAttempts.
- Đổi default làm behavior ứng dụng khác đi.
- Đổi tên property mà không hỗ trợ migration.
- Thay bean type hoặc bean name mà consumer đang inject theo qualifier.

Không phải thay đổi nào cũng là breaking theo ngôn ngữ Java, nhưng có thể phá behavior.

### 21.2. Properties cần migration path

Nếu đổi tên company.retry.max-attempts, hãy cân nhắc deprecate property cũ trong metadata, hỗ trợ alias trong một khoảng thời gian, log warning có hướng dẫn khi property cũ được dùng, cập nhật tài liệu migration và chỉ xóa ở major version phù hợp.

### 21.3. Spring Boot compatibility

Auto-configuration API thay đổi theo Spring Boot/Spring Framework version. Công bố rõ version matrix: Boot versions, Java baseline, Spring Framework baseline, validation dependency có bắt buộc không và module nào cần runtime dependency nào.

Không trộn version Spring Framework hoặc Boot tùy ý trong cùng dependency graph. Với ứng dụng Boot, nên tận dụng dependency management/BOM tương thích.

### 21.4. Starter không nên ép version xung đột

Starter thường nên để dependency management của ứng dụng quyết định version Spring Boot. Nếu starter tự ghim nhiều version nền tảng khác nhau, người dùng có thể gặp NoSuchMethodError, ClassNotFoundException hoặc binary incompatibility.

## 22. Đóng gói và publish thư viện

Một thư viện Spring Boot auto-configuration cần đảm bảo artifact chứa đúng API/core classes, auto-configuration class, configuration properties class, AutoConfiguration.imports, metadata nếu có và dependency graph phù hợp.

### 22.1. Dependency direction

~~~text
retry-spring-boot-starter
    |
    +--> retry-spring-boot-autoconfigure
    |
    +--> retry-core
             |
             +--> retry-api (nếu tách riêng)
~~~

Module auto-configuration phụ thuộc core và Spring Boot auto-configure. Starter gom những module cần thiết cho người dùng.

### 22.2. Optional dependency và runtime scope

Không phải mọi dependency compile của auto-configuration đều phải trở thành dependency bắt buộc của mọi ứng dụng. Cần xem class nào được load khi condition nào thỏa mãn, dependency nào cần có trên runtime classpath và cách Spring Boot version xử lý optional integration.

Đừng đánh dấu dependency optional chỉ để làm artifact nhỏ nếu auto-configuration thực tế cần class đó mà không có guard condition phù hợp.

### 22.3. Kiểm tra artifact đã publish

Sau khi build, có thể kiểm tra nội dung JAR:

~~~bash
jar tf retry-spring-boot-autoconfigure.jar
~~~

Xác nhận file AutoConfiguration.imports và class auto-configuration có trong artifact. Một context test chạy từ IDE có thể pass dù file metadata bị thiếu trong artifact publish nếu build resource configuration sai.

### 22.4. Không yêu cầu người dùng component scan package thư viện

Một auto-configuration đúng chuẩn được Boot phát hiện qua metadata. Người dùng không nên phải thêm package thư viện vào @ComponentScan thủ công nếu tài liệu nói rằng chỉ cần starter.

## 23. Ví dụ sử dụng từ ứng dụng consumer

Ứng dụng Maven thêm starter theo version do dependency management của tổ chức quản lý:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>company-retry-spring-boot-starter</artifactId>
</dependency>
~~~

Cấu hình:

~~~yaml
company:
  retry:
    enabled: true
    max-attempts: 4
    initial-delay: 250ms
    multiplier: 2
    max-delay: 3s
~~~

Service inject contract:

~~~java
@Service
public class InventoryGateway {

    private final RetryPolicy retryPolicy;

    public InventoryGateway(RetryPolicy retryPolicy) {
        this.retryPolicy = retryPolicy;
    }

    public int maxAttempts() {
        return retryPolicy.maxAttempts();
    }
}
~~~

Nếu ứng dụng muốn policy riêng, đăng ký bean RetryPolicy của mình. Không cần thay source thư viện.

### 23.1. Ứng dụng không dùng Spring Boot

Nếu core được tách độc lập, một Java application có thể tạo implementation:

~~~java
RetryPolicy policy = new DefaultRetryPolicy(
        3,
        Duration.ofMillis(200),
        2,
        Duration.ofSeconds(5)
);
~~~

Điều này chứng minh API/core không cần Spring container để hoạt động.

### 23.2. Ứng dụng có nhiều policy

Nếu một ứng dụng cần policy cho nhiều nhóm operation, một bean đơn lẻ có thể không đủ. Khi đó thiết kế registry/factory có key hoặc truyền strategy vào use case. Đừng dựa vào việc Spring inject một bean type duy nhất rồi cố ép nó phục vụ mọi semantics.

## 24. Những anti-pattern thường gặp

### 24.1. Core gọi ApplicationContext

Logic tự tìm dependency, test và reuse khó. Thay bằng constructor injection hoặc truyền dependency qua method.

### 24.2. Mỗi class tự đọc Environment

Cấu hình phân tán, khó validate và khó biết property contract. Thay bằng một @ConfigurationProperties object ở integration layer rồi chuyển giá trị vào core.

### 24.3. Bắt người dùng exclude auto-configuration để thay một bean

Người dùng phải tự lặp lại toàn bộ wiring. Thay bằng @ConditionalOnMissingBean trên default bean phù hợp.

### 24.4. Component scan package thư viện quá rộng

Bean nội bộ bị đăng ký ngoài ý muốn và feature condition khó kiểm soát. Thay bằng auto-configuration và @Bean methods tường minh.

### 24.5. Constructor thực hiện network/database I/O

Startup phụ thuộc external availability và test khó cô lập. Thay bằng client nhẹ, kết nối theo nhu cầu hoặc lifecycle/readiness policy có chủ đích.

### 24.6. Default âm thầm thay cấu hình sai

Ứng dụng chạy với behavior khác điều người vận hành mong muốn. Thay bằng validation và lỗi rõ ràng khi giá trị không hợp lệ.

### 24.7. Dùng property để chọn tên class tùy ý

Reflection, classloading và lỗi runtime khó chẩn đoán; API không type-safe. Thay bằng strategy interface và bean customization.

### 24.8. Một singleton giữ state của từng request

Race condition có thể xuất hiện giữa các thread. Thay bằng state local theo execution hoặc object scope phù hợp.

### 24.9. Retry mọi exception

Có thể lặp side effect và làm tăng tải khi lỗi không thể phục hồi. Thay bằng retry policy có loại lỗi được phép, budget và semantics idempotency rõ.

### 24.10. Chỉ test bằng @SpringBootTest

Core test chậm và bị gắn với framework. Thay bằng unit test core thuần Java, context runner cho auto-configuration và integration tests cần thiết.

## 25. Quy trình thiết kế một thư viện dùng chung

1. **Viết contract trước.** Xác định interface, input/output, exception và semantics.
2. **Tách core khỏi framework.** Giữ thuật toán và invariant trong Java thuần khi có thể.
3. **Xác định cấu hình thực sự cần thiết.** Đặt namespace riêng và mô tả default.
4. **Tạo typed properties.** Bind một lần, validate rõ ràng.
5. **Tạo default implementation.** Giữ state bất biến hoặc thread-safe.
6. **Viết auto-configuration.** Dùng conditions và bean factory methods có chủ đích.
7. **Cho phép override.** Dùng interface/strategy và @ConditionalOnMissingBean.
8. **Định nghĩa extension points.** Listener/customizer chỉ khi có nhu cầu thật.
9. **Quản lý lifecycle.** Không tạo external side effect vô thức trong startup.
10. **Viết unit tests cho core.** Không cần Spring.
11. **Viết context tests cho auto-configuration.** Kiểm tra defaults, properties, conditions và back-off.
12. **Kiểm tra artifact.** Xác nhận metadata và dependencies được đóng gói.
13. **Viết tài liệu consumer.** Có ví dụ cấu hình, override, disable và migration.
14. **Công bố compatibility.** Nêu Java/Spring Boot versions và chính sách versioning.

## 26. Bài thực hành

### Bài A: Tách core khỏi Spring

Tạo RetryPolicy và DefaultRetryPolicy trong module Java thuần. Không import org.springframework.* vào core.

Viết unit tests cho max attempts, delay sequence, max delay và invalid arguments.

### Bài B: Tạo properties

Tạo RetryProperties với prefix riêng, default values và validation. Viết cấu hình YAML thay đổi từng tham số.

Giải thích property nào optional, property nào bắt buộc và semantics của từng đơn vị.

### Bài C: Auto-configuration

Tạo RetryAutoConfiguration với @AutoConfiguration, @EnableConfigurationProperties, @ConditionalOnProperty và @ConditionalOnMissingBean. Đăng ký trong AutoConfiguration.imports.

### Bài D: Custom bean

Trong ứng dụng demo, cung cấp một bean RetryPolicy riêng. Xác nhận auto-configuration không tạo thêm default bean.

### Bài E: Tắt feature

Đặt company.retry.enabled=false. Xác nhận default bean không tồn tại. Nếu một service vẫn yêu cầu bean, thiết kế lại conditional composition để startup behavior nhất quán.

### Bài F: Context runner

Viết tests cho default values, custom property values, user bean override và disabled condition bằng ApplicationContextRunner.

### Bài G: Không có Spring

Dùng core library trong một Java main method không khởi động Spring. Tạo policy trực tiếp và sử dụng API.

### Bài H: Extension listener

Thêm RetryListener để consumer ghi metric. Xác định thứ tự listener, cách xử lý exception từ callback và liệu callback có được gọi trong mọi retry hay không.

### Bài I: Profile configuration

Cung cấp hai profile configuration khác nhau. Chạy context với từng profile và xác nhận properties được bind. Thư viện không tự chọn profile.

### Bài J: Thread safety

Tạo nhiều thread cùng sử dụng một DefaultRetryPolicy. Xác nhận implementation không giữ state của từng operation trong field mutable.

### Bài K: Startup side effect

Tạo một adapter mô phỏng external client. So sánh kết nối ngay trong constructor với kết nối theo nhu cầu. Quan sát ảnh hưởng đến context startup và test.

### Bài L: Kiểm tra artifact

Build auto-configuration JAR và kiểm tra AutoConfiguration.imports cùng configuration metadata có mặt trong archive.

## 27. Câu hỏi tự kiểm tra

**1. Vì sao nên tách core khỏi Spring auto-configuration?**

Để quy tắc và API có thể dùng độc lập, kiểm thử thuần Java và không buộc consumer phải kéo Spring nếu không cần.

**2. Auto-configuration có nhiệm vụ gì?**

Đăng ký bean mặc định theo classpath, properties và những bean đã tồn tại.

**3. Starter có nhất thiết chứa logic nghiệp vụ không?**

Không. Starter chủ yếu gom dependency để consumer tích hợp thuận tiện.

**4. Vì sao property cần namespace riêng?**

Để tránh xung đột, thể hiện ownership và giúp người dùng khám phá cấu hình.

**5. @ConfigurationProperties nên nằm ở đâu?**

Trong lớp tích hợp Spring Boot, sau đó giá trị được chuyển thành argument/configuration thuần cho core.

**6. @ConditionalOnMissingBean hỗ trợ điều gì?**

Cho phép ứng dụng cung cấp implementation riêng và khiến default bean lùi lại.

**7. Khi nào dùng property, khi nào dùng strategy bean?**

Property cho lựa chọn dữ liệu; strategy bean cho hành vi thay thế.

**8. Vì sao core không nên tự gọi ApplicationContext?**

Nó tạo service locator, dependency ẩn và phụ thuộc container.

**9. Vì sao constructor không nên thực hiện network I/O?**

Nó làm startup phụ thuộc dịch vụ ngoài, khó kiểm soát timeout và khó test.

**10. Vì sao cần ApplicationContextRunner?**

Để kiểm thử auto-configuration, property binding, conditions và bean override trong context nhỏ.

**11. Một singleton bean có thể giữ state của từng request không?**

Không nên nếu state có thể bị chia sẻ giữa các thread; dùng local/execution state hoặc scope phù hợp.

**12. Vì sao retry mọi exception là nguy hiểm?**

Một số lỗi không thể phục hồi và retry có thể lặp side effect, tạo dữ liệu trùng hoặc tăng tải.

**13. Auto-configuration có nên component scan toàn package library không?**

Thường không; đăng ký bean tường minh giúp điều kiện và composition dễ kiểm soát.

**14. Vì sao cần kiểm tra JAR đã publish?**

Để xác nhận auto-configuration metadata, resource và dependency thực sự có trong artifact consumer nhận được.

**15. Vì sao default behavior cần được tài liệu hóa?**

Người dùng phải biết điều gì xảy ra khi không khai báo property và hiểu semantics trước khi triển khai.

## 28. Kết luận

Một thư viện dùng chung tốt có **API nhỏ, quy tắc cốt lõi độc lập và cơ chế tích hợp Spring rõ ràng**. Core xử lý hành vi và invariant; typed configuration properties biểu diễn lựa chọn của ứng dụng; auto-configuration đăng ký implementation mặc định; @ConditionalOnMissingBean và strategy interfaces tạo điểm mở rộng để consumer thay đổi behavior.

Hãy để ứng dụng kiểm soát profile và môi trường, tránh để core tự đọc Environment hoặc tự tìm bean qua ApplicationContext. Giữ constructor nhẹ, quản lý lifecycle có chủ đích và không để singleton giữ state riêng của từng request. Kiểm thử core bằng JUnit thuần Java, kiểm thử binding/conditions/back-off bằng context runner, rồi kiểm tra artifact thực tế trước khi publish.

Khi contract, defaults, properties và extension points đều rõ, ứng dụng có thể dùng thư viện nhanh với cấu hình mặc định hoặc tùy chỉnh theo nhu cầu riêng mà không phải fork implementation. Đó là nền tảng để nhiều ứng dụng chia sẻ cùng một capability mà vẫn giữ quyền kiểm soát composition và business behavior của mình.

