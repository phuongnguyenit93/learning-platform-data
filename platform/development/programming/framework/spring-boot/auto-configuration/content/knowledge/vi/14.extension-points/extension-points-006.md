# Thiết kế giao diện Strategy và bean thay thế cho người dùng thư viện Spring Boot

## 1. Bài toán mở rộng thư viện

Giả sử một thư viện HTTP client có chính sách retry mặc định: thử lại khi gặp HTTP 429 hoặc lỗi máy chủ 5xx, với số lần thử tối đa đã định. Ứng dụng sử dụng thư viện có thể cần quy tắc khác, chẳng hạn chỉ retry một số mã lỗi nội bộ, giới hạn theo tenant hoặc đọc chính sách từ cấu hình riêng.

Nếu thư viện viết cứng thuật toán vào `AcmeClient`, người dùng phải sửa source, fork thư viện hoặc tạo một client khác hoàn toàn. Một điểm mở rộng tốt cho phép ứng dụng thay đổi **thuật toán** trong khi giữ nguyên cách client sử dụng thuật toán đó.

Mẫu **Strategy** giải quyết phần thiết kế:
- Công bố một interface ổn định mô tả hành vi cần thay thế.
- Cung cấp một implementation mặc định hợp lý.
- Client chỉ phụ thuộc vào interface.
- Cho phép ứng dụng cung cấp một implementation khác qua Spring bean.

Spring Boot bổ sung cơ chế **bean back-off** để auto-configuration tự dùng implementation mặc định khi ứng dụng chưa khai báo chiến lược riêng. Annotation trọng tâm là `@ConditionalOnMissingBean`.

## 2. Thiết kế interface chiến lược như một hợp đồng công khai

Một interface mở rộng là **API của thư viện**. Nó cần mô tả đúng quyết định mà thư viện muốn giao cho ứng dụng, không để lộ toàn bộ chi tiết nội bộ.

Ví dụ `RetryPolicy`:

~~~java
package com.acme.client;

public interface RetryPolicy {

    /**
     * @param failedAttempt số lần request đã thất bại, bắt đầu từ 1
     * @param statusCode HTTP status của lần thất bại
     * @return true nếu client được phép thực hiện lần thử tiếp theo
     */
    boolean shouldRetry(int failedAttempt, int statusCode);
}
~~~

Hợp đồng phải làm rõ các điểm sau:

1. **Ý nghĩa tham số:** `failedAttempt` bắt đầu từ 1 hay 0? Có tính lần gọi đầu tiên không? `statusCode` có thể là mã giả lập khi không nhận được HTTP response không?
2. **Ý nghĩa kết quả:** `true` có nghĩa được thử lại ngay, hay chỉ có nghĩa policy cho phép retry và client vẫn phải kiểm tra deadline/cancellation?
3. **Giới hạn trách nhiệm:** Strategy quyết định có retry hay không; client chịu trách nhiệm thực hiện request, giới hạn tổng thời gian, đóng response và ghi nhận telemetry.
4. **Lỗi và dữ liệu bất thường:** Quy định cách xử lý tham số không hợp lệ và exception do strategy ném ra. Không để hành vi này tùy tiện khác nhau giữa các implementation.
5. **Thread safety:** Một bean Spring thường được dùng chung giữa nhiều request. Hợp đồng nên yêu cầu implementation an toàn khi gọi đồng thời hoặc chỉ chứa state bất biến.
6. **Tính ổn định:** Tránh đưa class nội bộ, bean Spring cụ thể, cấu trúc private hoặc kiểu dữ liệu khó thay đổi vào interface công khai.

Interface nên nằm trong package API mà người dùng thư viện có thể import, ví dụ `com.acme.client`. Implementation mặc định có thể nằm trong package implementation riêng. Người dùng cần biết interface và quy tắc triển khai, không cần phụ thuộc vào class mặc định.

**Không nên tạo một interface quá rộng** như `LibraryStrategy` với hàng chục phương thức không liên quan. Mỗi điểm biến đổi nên có một hợp đồng nhỏ, tên diễn đạt nghiệp vụ và ngữ nghĩa rõ ràng.

## 3. Implementation mặc định của thư viện

Thư viện cung cấp `DefaultRetryPolicy`:

~~~java
package com.acme.client;

public final class DefaultRetryPolicy implements RetryPolicy {

    private final int maxAttempts;

    public DefaultRetryPolicy() {
        this(3);
    }

    public DefaultRetryPolicy(int maxAttempts) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be at least 1");
        }
        this.maxAttempts = maxAttempts;
    }

    @Override
    public boolean shouldRetry(int failedAttempt, int statusCode) {
        if (failedAttempt < 1) {
            throw new IllegalArgumentException(
                    "failedAttempt must start at 1");
        }

        boolean transientFailure =
                statusCode == 429 || (statusCode >= 500 && statusCode <= 599);

        return failedAttempt < maxAttempts && transientFailure;
    }
}
~~~

Với `maxAttempts=3`:
- Lần thất bại thứ 1: có thể retry nếu status là 429 hoặc 5xx.
- Lần thất bại thứ 2: có thể retry nếu status vẫn thuộc nhóm trên.
- Lần thất bại thứ 3: không retry nữa vì đã đạt giới hạn tổng số lần thử.
- Status 400, 401, 404 hoặc 503? 503 thuộc 5xx nên có thể retry; các mã 4xx còn lại trong ví dụ không retry.

Đây là policy minh họa, không phải khuyến nghị rằng mọi HTTP client đều nên retry mọi 5xx. Thư viện thực tế phải xem xét tính idempotent của request, retry-after, exponential backoff, jitter, deadline, giới hạn tải và khả năng gây gửi lặp thao tác ghi.

**Implementation mặc định nên độc lập với Spring** khi không cần Spring API. Như vậy người dùng có thể unit test hoặc dùng trực tiếp trong thành phần không quản lý bởi container; Spring chỉ đảm nhiệm việc đăng ký bean và tiêm dependency.

## 4. Client phụ thuộc vào interface

Client nhận `RetryPolicy` qua constructor:

~~~java
package com.acme.client;

import java.util.Objects;

public final class AcmeClient {

    private final RetryPolicy retryPolicy;

    public AcmeClient(RetryPolicy retryPolicy) {
        this.retryPolicy = Objects.requireNonNull(retryPolicy);
    }

    public boolean shouldRetry(int failedAttempt, int statusCode) {
        return retryPolicy.shouldRetry(failedAttempt, statusCode);
    }
}
~~~

`AcmeClient` không cần biết implementation đang dùng là `DefaultRetryPolicy`, `TenantRetryPolicy` hay một class do ứng dụng viết. Đây là **Dependency Inversion**: client phụ thuộc vào abstraction; các implementation cùng tuân theo hợp đồng.

Có thể hình dung luồng:

~~~mermaid
flowchart TD
    A["Ứng dụng khởi động"] --> B{"Đã có bean RetryPolicy?"}
    B -->|"Chưa"| C["Đăng ký DefaultRetryPolicy"]
    B -->|"Đã có"| D["Dùng implementation của ứng dụng"]
    C --> E["Tiêm RetryPolicy vào AcmeClient"]
    D --> E
    E --> F["AcmeClient gọi shouldRetry()"]
~~~

Mỗi context chọn một implementation cho điểm mở rộng dạng single-strategy. Việc ứng dụng tự tạo bean chỉ thay đổi hành vi policy; nó không yêu cầu sửa client hoặc thay thế toàn bộ thư viện.

## 5. Đăng ký bean mặc định bằng @ConditionalOnMissingBean

Auto-configuration của thư viện:

~~~java
package com.acme.client.autoconfigure;

import com.acme.client.AcmeClient;
import com.acme.client.DefaultRetryPolicy;
import com.acme.client.RetryPolicy;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RetryPolicy.class)
    DefaultRetryPolicy retryPolicy() {
        return new DefaultRetryPolicy();
    }

    @Bean
    AcmeClient acmeClient(RetryPolicy retryPolicy) {
        return new AcmeClient(retryPolicy);
    }
}
~~~

Đọc điều kiện:

~~~java
@ConditionalOnMissingBean(RetryPolicy.class)
~~~

Nghĩa là: chỉ đăng ký bean mặc định từ method `retryPolicy()` nếu trong `BeanFactory` chưa có bean phù hợp với kiểu `RetryPolicy` theo phạm vi tìm kiếm của condition.

Có hai nhánh:

| Bean do ứng dụng cung cấp | Condition | Kết quả |
| --- | --- | --- |
| Không có implementation `RetryPolicy` | Khớp | Spring đăng ký `DefaultRetryPolicy` |
| Có một implementation `RetryPolicy` | Không khớp | Bean mặc định được bỏ qua; bean ứng dụng được dùng |
| Có nhiều implementation `RetryPolicy` | Không khớp | Không tạo thêm mặc định; client đơn trị có thể bị ambiguous nếu không chọn candidate |

**Vì sao kiểm tra interface?** Đây là hợp đồng thay thế. Nếu condition chỉ kiểm tra `DefaultRetryPolicy.class`, bean tùy chỉnh triển khai `RetryPolicy` sẽ không làm condition back off; Spring có thể đăng ký cả hai và client tiêm theo interface sẽ gặp nhiều candidate.

**Vì sao method trả về kiểu cụ thể?** `DefaultRetryPolicy` là return type giàu thông tin cho Spring. Điều kiện đã chỉ rõ `RetryPolicy.class`, còn return type cụ thể giúp container biết thêm type metadata trước khi instance được tạo. Spring Boot khuyến nghị khai báo kiểu trả về cụ thể nhất có thể cho method `@Bean`, đặc biệt khi dùng bean conditions.

`@ConditionalOnMissingBean` nên được đặt trong **auto-configuration** của thư viện. Condition chỉ xét bean definitions đã được xử lý đến thời điểm đánh giá; Spring Boot bảo đảm auto-configuration được áp dụng sau các bean definitions do người dùng khai báo. Đặt cùng điều kiện trên cấu hình thông thường được scan sớm có thể làm kết quả phụ thuộc thứ tự xử lý.

## 6. Người dùng thay thế strategy bằng bean của riêng họ

Ứng dụng không cần sửa class của thư viện. Nó triển khai interface và khai báo bean trong cấu hình ứng dụng:

~~~java
package com.example.app;

import com.acme.client.RetryPolicy;

public final class BusinessRetryPolicy implements RetryPolicy {

    @Override
    public boolean shouldRetry(int failedAttempt, int statusCode) {
        return failedAttempt <= 5 && statusCode == 503;
    }
}
~~~

Đăng ký implementation:

~~~java
package com.example.app;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RetryConfiguration {

    @Bean
    BusinessRetryPolicy businessRetryPolicy() {
        return new BusinessRetryPolicy();
    }
}
~~~

Khi ứng dụng khởi động:
1. Spring xử lý cấu hình ứng dụng và đăng ký bean `BusinessRetryPolicy`.
2. Spring Boot xử lý `AcmeClientAutoConfiguration`.
3. `@ConditionalOnMissingBean(RetryPolicy.class)` phát hiện bean người dùng đã triển khai interface, nên method mặc định không được áp dụng.
4. Bean `AcmeClient` nhận `BusinessRetryPolicy` thông qua tham số `RetryPolicy`.

Tên bean có thể là `businessRetryPolicy`; không cần trùng tên `retryPolicy` của method mặc định. Cơ chế thay thế dựa trên **kiểu bean**, không dựa vào ghi đè bean definition cùng tên.

Nếu người dùng muốn cấu hình bằng component scan, class implementation có thể được đánh dấu `@Component` miễn là nó thực sự nằm trong scan scope của ứng dụng. Với thư viện và ứng dụng lớn, cấu hình `@Bean` tường minh thường dễ đọc và kiểm soát hơn.

## 7. Vì sao bean người dùng được ưu tiên?

Auto-configuration là cơ chế cung cấp mặc định có điều kiện. Spring Boot khuyến nghị sử dụng `@ConditionalOnMissingBean` để người dùng có thể thay thế các bean tự động cấu hình khi muốn hành vi khác.

Thứ tự xử lý là yếu tố quan trọng:

- Bean definitions của cấu hình ứng dụng được đăng ký trước.
- Auto-configuration của thư viện được áp dụng sau.
- Condition quan sát những bean definitions đã được xử lý đến lúc đó.
- Nếu đã có bean phù hợp, bean mặc định của thư viện back off.

Vì vậy hãy công bố auto-configuration theo cơ chế chính thức và đặt condition ở đó. Đừng dựa vào thứ tự scan tình cờ hoặc giả định rằng một class trên classpath tự động trở thành bean.

### Đăng ký auto-configuration trong JAR

Tạo file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

~~~text
com.acme.client.autoconfigure.AcmeClientAutoConfiguration
~~~

Đây là bước để Spring Boot phát hiện auto-configuration khi starter/thư viện được đưa vào classpath. Chỉ viết class có `@AutoConfiguration` mà thiếu đăng ký imports phù hợp thì ứng dụng chưa chắc tự áp dụng cấu hình.

### Bean mặc định không nên là component được scan vô điều kiện

Không nên vừa đánh dấu `DefaultRetryPolicy` bằng `@Component` để component scan tạo bean, vừa đăng ký nó qua method `@Bean` có `@ConditionalOnMissingBean`. Nếu component scan đã tạo bean mặc định, condition sẽ thấy interface tồn tại và back off; nhưng ứng dụng tùy chỉnh không còn thay thế được default theo ý đồ thiết kế vì bean component đã luôn được đăng ký. Hãy để auto-configuration sở hữu việc tạo bean mặc định.

## 8. Một hay nhiều strategy? Xử lý candidate rõ ràng

Ví dụ trên thiết kế một **strategy duy nhất** cho mỗi `AcmeClient`. Nếu ứng dụng đăng ký hai bean cùng triển khai `RetryPolicy`:
- `@ConditionalOnMissingBean(RetryPolicy.class)` thấy đã có bean nên bỏ qua default.
- Constructor `AcmeClient(RetryPolicy retryPolicy)` yêu cầu một candidate.
- Nếu Spring không xác định được candidate duy nhất, context có thể thất bại với lỗi nhiều bean phù hợp, thường là `NoUniqueBeanDefinitionException`.

Có ba hướng thiết kế tùy hợp đồng.

### 8.1. Single strategy: yêu cầu đúng một implementation

Đây là lựa chọn đơn giản nhất. Ứng dụng chỉ đăng ký một bean `RetryPolicy`. Nếu không khai báo, thư viện dùng default. Nếu khai báo một custom bean, default back off.

### 8.2. Nhiều implementation nhưng chọn một bean chính

Ứng dụng có thể đánh dấu custom bean bằng `@Primary` khi có nhiều candidate:

~~~java
@Bean
@Primary
BusinessRetryPolicy businessRetryPolicy() {
    return new BusinessRetryPolicy();
}
~~~

`@Primary` giúp Spring ưu tiên bean đó cho dependency đơn trị khi có nhiều candidate và có đúng một bean primary. Nó **không** làm các bean khác biến mất, cũng không thay thế `@ConditionalOnMissingBean`; condition quyết định có tạo default hay không, còn `@Primary` quyết định candidate được tiêm khi nhiều bean cùng tồn tại.

Hoặc dùng `@Qualifier` khi consumer có chủ đích yêu cầu một biến thể được đặt tên/đánh dấu cụ thể. Với API thư viện, qualifier cần được tài liệu hóa để người dùng có thể cung cấp đúng metadata; tránh hardcode một qualifier nội bộ khó thay thế.

### 8.3. Nhiều strategy cùng tham gia

Nếu nghiệp vụ thật sự muốn chạy nhiều policy, hãy thiết kế consumer nhận collection:

~~~java
public AcmeClient(List<RetryPolicy> retryPolicies) {
    this.retryPolicies = List.copyOf(retryPolicies);
}
~~~

Có thể dùng `@Order`/`Ordered` để sắp thứ tự các phần tử trong collection. Đây là mô hình **pipeline/chain** khác với một strategy thay thế duy nhất. Phải quy định cách kết hợp kết quả (AND, OR, first-match, short-circuit), thứ tự, xử lý exception và cách xử lý collection rỗng.

**Không dùng `@Order` để giải quyết injection một bean đơn trị**; `@Order` không phải cơ chế chọn duy nhất một candidate như `@Primary`.

## 9. Phân biệt các cơ chế thường bị nhầm

| Cơ chế | Vai trò | Ảnh hưởng đến điểm mở rộng |
| --- | --- | --- |
| `Strategy interface` | Định nghĩa hợp đồng thuật toán có thể thay thế | Tách client khỏi implementation |
| `@ConditionalOnMissingBean(Strategy.class)` | Đăng ký default khi chưa có bean phù hợp | Cho phép bean người dùng thay thế default |
| `@Primary` | Chọn candidate ưu tiên cho dependency đơn trị khi có nhiều bean | Chọn một bean trong nhiều bean đã tồn tại |
| `@Qualifier` | Thu hẹp candidate theo qualifier được khai báo | Chọn biến thể có metadata phù hợp |
| `@Order`/`Ordered` | Sắp thứ tự các bean trong ngữ cảnh collection/order-aware | Phù hợp khi nhiều strategy cùng tham gia |
| `@ConditionalOnProperty` | Bật cấu hình dựa vào property | Chọn nhánh cấu hình theo giá trị property, không tự thay bean theo interface |
| Bean name | Định danh bean trong context | Không phải hợp đồng thay thế theo type |

### Không dựa vào bean definition overriding

Đừng hướng dẫn người dùng tạo một bean trùng tên với bean mặc định rồi mong Spring ghi đè. Cách đó phụ thuộc cấu hình cho phép overriding và dễ gây xung đột. Thiết kế auto-configuration nên dùng điều kiện theo type rõ ràng để back off trước khi đăng ký default.

## 10. Ví dụ kiểm thử hoàn chỉnh với ApplicationContextRunner

Kiểm thử auto-configuration nên tạo các context độc lập cho từng trường hợp: không có custom bean và có custom bean. `ApplicationContextRunner` của Spring Boot phù hợp vì có thể cung cấp auto-configuration và user configuration riêng cho mỗi test.

Tạo file `src/test/java/com/example/app/RetryPolicyAutoConfigurationTest.java` trong project Java 17+ có dependency `spring-boot-starter-test` (Spring Boot 3.3, JUnit 5 và AssertJ):

~~~java
package com.example.app;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class RetryPolicyAutoConfigurationTest {

    interface RetryPolicy {
        boolean shouldRetry(int failedAttempt, int statusCode);
    }

    static final class DefaultRetryPolicy implements RetryPolicy {
        @Override
        public boolean shouldRetry(int failedAttempt, int statusCode) {
            return failedAttempt < 3
                    && (statusCode == 429
                    || (statusCode >= 500 && statusCode <= 599));
        }
    }

    static final class BusinessRetryPolicy implements RetryPolicy {
        @Override
        public boolean shouldRetry(int failedAttempt, int statusCode) {
            return failedAttempt <= 5 && statusCode == 503;
        }
    }

    static final class AcmeClient {
        private final RetryPolicy retryPolicy;

        AcmeClient(RetryPolicy retryPolicy) {
            this.retryPolicy = retryPolicy;
        }

        boolean shouldRetry(int failedAttempt, int statusCode) {
            return retryPolicy.shouldRetry(failedAttempt, statusCode);
        }
    }

    @AutoConfiguration
    static class LibraryAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(RetryPolicy.class)
        DefaultRetryPolicy retryPolicy() {
            return new DefaultRetryPolicy();
        }

        @Bean
        AcmeClient acmeClient(RetryPolicy retryPolicy) {
            return new AcmeClient(retryPolicy);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserRetryConfiguration {

        @Bean
        BusinessRetryPolicy businessRetryPolicy() {
            return new BusinessRetryPolicy();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(LibraryAutoConfiguration.class));

    @Test
    void registersDefaultWhenUserHasNoStrategy() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(RetryPolicy.class);
            assertThat(context).hasSingleBean(DefaultRetryPolicy.class);
            assertThat(context).doesNotHaveBean(BusinessRetryPolicy.class);
            assertThat(context).hasSingleBean(AcmeClient.class);

            AcmeClient client = context.getBean(AcmeClient.class);
            assertThat(client.shouldRetry(1, 503)).isTrue();
            assertThat(client.shouldRetry(1, 404)).isFalse();
            assertThat(client.shouldRetry(3, 503)).isFalse();
        });
    }

    @Test
    void userStrategyReplacesDefaultAndIsInjected() {
        runner.withUserConfiguration(UserRetryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(RetryPolicy.class);
                    assertThat(context).hasSingleBean(BusinessRetryPolicy.class);
                    assertThat(context).doesNotHaveBean(DefaultRetryPolicy.class);
                    assertThat(context).hasSingleBean(AcmeClient.class);

                    AcmeClient client = context.getBean(AcmeClient.class);
                    assertThat(client.shouldRetry(1, 503)).isTrue();
                    assertThat(client.shouldRetry(5, 503)).isTrue();
                    assertThat(client.shouldRetry(1, 500)).isFalse();
                    assertThat(client.shouldRetry(6, 503)).isFalse();
                });
    }
}
~~~

Chạy từ project Gradle đã cấu hình Spring Boot và `spring-boot-starter-test`:

~~~bash
./gradlew test --tests "com.example.app.RetryPolicyAutoConfigurationTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.app.RetryPolicyAutoConfigurationTest"
~~~

**Kết quả mong đợi:** cả hai test PASS.

- Test đầu chứng minh default bean được tạo và client dùng chính sách mặc định.
- Test thứ hai đăng ký cấu hình người dùng cùng lúc với auto-configuration; default bean back off, bean `BusinessRetryPolicy` được tiêm vào client và thay đổi kết quả theo đúng thuật toán custom.
- Assertions kiểm tra bean type và hành vi; không phụ thuộc stdout của Gradle.
- Fixture đưa auto-configuration trực tiếp vào `ApplicationContextRunner` nên không cần file imports trong test. Starter thực tế vẫn cần `AutoConfiguration.imports` như mục 7.

Các test này là ví dụ có thể chạy khi dependency và package được thiết lập đúng; cần thực thi trên project để xác nhận môi trường build cụ thể.

## 11. Các lỗi thiết kế và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Default và custom cùng tồn tại | Condition kiểm tra class mặc định thay vì interface strategy | Dùng `@ConditionalOnMissingBean(RetryPolicy.class)` |
| Custom bean không thay thế default | Custom class chưa được đăng ký hoặc không implement đúng interface | Kiểm tra `@Bean`/component scan và type thực tế |
| `NoUniqueBeanDefinitionException` | Có nhiều bean strategy nhưng consumer tiêm một candidate | Chỉ đăng ký một bean, hoặc dùng `@Primary`/`@Qualifier` phù hợp |
| Client không tìm thấy strategy | Auto-configuration client được áp dụng nhưng default bị back off trong khi custom bean chưa được xử lý | Đảm bảo custom bean là user configuration hoặc sắp thứ tự auto-configuration đúng |
| Người dùng phải scan package thư viện | Thư viện dựa vào component scan của ứng dụng để đăng ký default | Đăng ký default bằng `@Bean` trong auto-configuration |
| Thay tên bean vẫn không thay được implementation | Condition kiểm tra theo type, không theo tên bean | Implement đúng interface; không dựa vào trùng tên |
| Condition không back off dù custom bean có trong code | Bean chưa được đăng ký khi condition được đánh giá, hoặc return type không bộc lộ type đủ cụ thể | Kiểm tra thứ tự và return type của method `@Bean` |
| Custom policy gây lỗi khi nhiều request đồng thời | Implementation giữ mutable state không an toàn | Dùng state bất biến hoặc đồng bộ đúng cách |
| Retry quá nhiều hoặc tạo request lặp | Strategy không xét idempotency, deadline, retry-after hoặc backoff | Xác định rõ trách nhiệm policy và client, giới hạn tổng thời gian/số lần |
| Không biết bean nào đang được chọn | Chưa kiểm tra context thực tế | Dùng `ApplicationContextRunner`, kiểm tra bean type và condition report |

### Quy trình điều tra

1. Xác nhận interface là đúng type mà client constructor yêu cầu.
2. Kiểm tra custom bean có thực sự được đăng ký trong đúng `ApplicationContext` không.
3. Kiểm tra auto-configuration có nằm trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` và không bị exclude/condition khác loại.
4. Kiểm tra `@ConditionalOnMissingBean` có chỉ rõ interface strategy.
5. Kiểm tra return type của các method `@Bean` cung cấp implementation là kiểu cụ thể.
6. Nếu có nhiều candidate, kiểm tra `@Primary`/`@Qualifier` hoặc chuyển sang mô hình collection.
7. Bật `--debug` hoặc `debug=true` để xem Condition Evaluation Report của Spring Boot. Có thể dùng `ApplicationContextRunner` để tái hiện chính xác nhánh default/custom.

## 12. Nguyên tắc thiết kế điểm mở rộng bền vững

- **Công bố API nhỏ:** interface chỉ chứa hành vi cần tùy chỉnh, có JavaDoc về tham số, kết quả, lỗi và concurrency.
- **Có default hữu ích:** người dùng cài starter mà không cấu hình thêm vẫn nhận hành vi hợp lý.
- **Dùng type làm hợp đồng:** `@ConditionalOnMissingBean(Strategy.class)` diễn tả đúng điểm mở rộng; tránh kiểm tra tên bean hoặc implementation mặc định.
- **Đặt điều kiện trong auto-configuration:** user-defined bean definitions được xử lý trước khi điều kiện default được đánh giá.
- **Client phụ thuộc abstraction:** constructor nhận interface, không tự khởi tạo class mặc định bằng `new DefaultStrategy()`.
- **Giữ implementation mặc định tách biệt:** không để component scan tạo default vô điều kiện nếu mục tiêu là cho custom bean thay thế.
- **Chọn mô hình một hay nhiều strategy ngay từ đầu:** single strategy dùng injection đơn trị; pipeline dùng collection và quy tắc thứ tự/kết hợp.
- **Không biến @Primary thành cơ chế back-off:** `@Primary` chỉ chọn candidate khi có nhiều bean; `@ConditionalOnMissingBean` mới quyết định có đăng ký bean mặc định hay không.
- **Kiểm thử cả hai nhánh:** không có custom bean và có custom bean; nếu hỗ trợ nhiều strategy thì test thêm ambiguity, qualifier/primary hoặc collection order.
- **Bảo vệ tương thích API:** thay đổi chữ ký interface là thay đổi hợp đồng của thư viện. Nếu cần thêm hành vi, cân nhắc default method, interface mới hoặc adapter để giảm tác động tới implementation hiện có.

## 13. Tự kiểm tra kiến thức

1. Vì sao client nhận `RetryPolicy` thay vì `DefaultRetryPolicy`? **Để phụ thuộc vào hợp đồng và cho phép nhiều implementation thay thế.**
2. `@ConditionalOnMissingBean(DefaultRetryPolicy.class)` có đủ để custom strategy thay thế default không? **Không**; custom class khác type default nên condition vẫn có thể tạo default. Kiểm tra interface `RetryPolicy.class`.
3. Khi ứng dụng cung cấp một bean `BusinessRetryPolicy implements RetryPolicy`, điều gì xảy ra? **Condition không khớp và bean mặc định được bỏ qua.**
4. Bean custom cần cùng tên với method `retryPolicy()` không? **Không**; condition được khai báo theo type.
5. Vì sao condition nên ở auto-configuration? **Vì nó chỉ xét bean definitions đã được xử lý, và auto-configuration được áp dụng sau user-defined bean definitions.**
6. Nếu có hai bean `RetryPolicy`, default có được tạo không? **Không**, vì condition đã thấy bean phù hợp; nhưng client đơn trị có thể bị ambiguous.
7. `@Primary` có làm default bean không được đăng ký không? **Không**; nó chỉ ưu tiên một candidate khi nhiều bean cùng tồn tại.
8. `@Order` có thay thế `@Primary` cho constructor tiêm một strategy không? **Không**; `@Order` phù hợp để sắp collection/order-aware components.
9. Vì sao không nên đặt `@Component` trên default implementation trong thiết kế này? **Vì component scan có thể đăng ký default vô điều kiện, làm mất ý nghĩa back-off của auto-configuration.**
10. Điều gì chứng minh ứng dụng thực sự thay thế strategy? **Context chỉ có custom strategy, không có default, và hành vi client phản ánh implementation custom.**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition annotations, `@ConditionalOnMissingBean`, bean method return type, user-defined bean definitions và `ApplicationContextRunner`.
- [Spring Boot 3.3.13 — `@ConditionalOnMissingBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): điều kiện khớp khi không có bean phù hợp và giới hạn theo bean definitions đã xử lý.
- [Spring Boot 3.3 — `@AutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): vai trò của auto-configuration và cơ chế before/after.
- [Spring Framework — `@Primary` và `@Fallback`/candidate selection](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html): chọn candidate cho dependency đơn trị khi có nhiều bean.
- [Spring Framework — `@Bean` JavaDoc and reference](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): đăng ký bean definition từ method `@Bean` và kiểu bean theo return type.
