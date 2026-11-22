# Tham chiếu auto-configuration tùy chọn theo tên để tránh phụ thuộc cứng

## Mục tiêu học tập

Trong Spring Boot, một thư viện có thể cần chạy auto-configuration của mình **sau** hoặc **trước** auto-configuration của một thư viện tích hợp khác. Nhưng thư viện kia có thể là **tùy chọn**: không phải ứng dụng nào cũng cài nó. Nếu dùng `SomePartnerAutoConfiguration.class`, mã nguồn phải nhìn thấy class tương ứng khi biên dịch. Nếu chỉ cần mô tả **thứ tự**, ta có thể tham chiếu class bên kia bằng **tên đầy đủ dạng `String`**.

Bài này giải thích chính xác cách dùng `@AutoConfiguration(afterName = ...)`, `@AutoConfiguration(beforeName = ...)`, `@AutoConfigureAfter(name = ...)` và `@AutoConfigureBefore(name = ...)`; cơ chế khi cấu hình được nhắc tới không có mặt; giới hạn của cách tham chiếu tên; và cách kiểm chứng bằng Java 17+, Spring Boot 3.3 và `ApplicationContextRunner`.

Sau bài học, bạn cần phân biệt được **phụ thuộc vào class tại thời điểm biên dịch**, **sự hiện diện của auto-configuration trong danh sách ứng viên**, **thứ tự đăng ký bean definition**, và **thứ tự tạo đối tượng bean**.

## 1. Bài toán: thư viện tùy chọn nhưng thứ tự vẫn quan trọng

Giả sử thư viện nội bộ cung cấp `MessageService` mặc định, còn thư viện đối tác **có thể** cung cấp một implementation riêng. Mục tiêu:

1. Nếu auto-configuration của đối tác được đưa vào ứng dụng và tạo `MessageService`, hãy xử lý nó trước.
2. Auto-configuration nội bộ chỉ đăng ký fallback khi **chưa có** `MessageService`.
3. Nếu đối tác hoàn toàn không có trên classpath, ứng dụng vẫn khởi động và fallback vẫn hoạt động.

Một cách viết tạo phụ thuộc compile-time:

~~~java
// Mã minh họa; cần dependency để import class bên đối tác.
import com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration;

@AutoConfiguration(after = PartnerMessageAutoConfiguration.class)
class LocalMessageAutoConfiguration {
}
~~~

Mặc dù đây chỉ là chú thích thứ tự, trình biên dịch Java vẫn phải giải quyết `PartnerMessageAutoConfiguration.class`. Nếu library/starter nội bộ không muốn thêm dependency vào module đối tác, ta có thể dùng tên lớp dưới dạng chuỗi:

~~~java
// Không cần import hoặc tham chiếu trực tiếp class của đối tác.
@AutoConfiguration(
    afterName = "com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration"
)
class LocalMessageAutoConfiguration {
}
~~~

Cả hai dạng đều mô tả ý định **LocalMessageAutoConfiguration được áp dụng sau PartnerMessageAutoConfiguration**. Điểm khác là `afterName` dùng tên đầy đủ của class, nên bản thân khai báo thứ tự không đòi class đối tác phải hiện diện khi biên dịch.

**Giới hạn quan trọng:** tên dưới dạng chuỗi chỉ bỏ phụ thuộc trực tiếp ở **khai báo thứ tự**. Nếu bạn vẫn import các API của đối tác ở field, superclass, method parameter, kiểu trả về `@Bean` hoặc nơi khác, thì thư viện vẫn có thể yêu cầu dependency tương ứng. `afterName` không tự biến toàn bộ tích hợp thành tùy chọn.

## 2. API chính trong Spring Boot 3.3

`@AutoConfiguration` thuộc package `org.springframework.boot.autoconfigure` và cung cấp bốn thuộc tính thứ tự:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `after` | `Class<?>[]` | Áp dụng auto-configuration hiện tại **sau** các class được tham chiếu trực tiếp |
| `afterName` | `String[]` | Áp dụng **sau** các auto-configuration có tên class tương ứng |
| `before` | `Class<?>[]` | Áp dụng auto-configuration hiện tại **trước** các class được tham chiếu trực tiếp |
| `beforeName` | `String[]` | Áp dụng **trước** các auto-configuration có tên class tương ứng |

Các thuộc tính dạng tên là bí danh của annotation chuyên dụng:

~~~java
// Hai cách thể hiện cùng một yêu cầu thứ tự:
@AutoConfiguration(afterName = "com.vendor.OptionalAutoConfiguration")
class AfterUsingAutoConfiguration {
}

@AutoConfiguration
@AutoConfigureAfter(name = "com.vendor.OptionalAutoConfiguration")
class AfterUsingDedicatedAnnotation {
}
~~~

Dạng tương ứng với `beforeName`:

~~~java
@AutoConfiguration(beforeName = "com.vendor.OptionalAutoConfiguration")
class BeforeUsingAutoConfiguration {
}

@AutoConfiguration
@AutoConfigureBefore(name = "com.vendor.OptionalAutoConfiguration")
class BeforeUsingDedicatedAnnotation {
}
~~~

Các đoạn trên chỉ **minh họa cú pháp annotation** và cần import `AutoConfiguration`, `AutoConfigureAfter`, `AutoConfigureBefore` trong tệp Java thực tế. Tên `com.vendor.OptionalAutoConfiguration` là ví dụ, không ám chỉ một class có thật.

Trong Spring Boot 3.3, có thể ưu tiên `beforeName` và `afterName` trực tiếp trên `@AutoConfiguration` vì dễ đọc cùng các điều kiện khác. Các annotation `@AutoConfigureBefore(name=...)` và `@AutoConfigureAfter(name=...)` vẫn hữu ích khi cần đọc hoặc duy trì code cũ.

### Một chuỗi hay nhiều tên?

Mỗi thuộc tính `*Name` có kiểu `String[]`, vì vậy có thể chứa nhiều tên:

~~~java
@AutoConfiguration(afterName = {
    "com.vendor.alpha.AlphaAutoConfiguration",
    "com.vendor.beta.BetaAutoConfiguration"
})
class MyFallbackAutoConfiguration {
}
~~~

Ý nghĩa là: nếu các auto-configuration được tham chiếu **cũng nằm trong tập được chọn**, cấu hình hiện tại được sắp xếp sau chúng. Đây là các ràng buộc thứ tự; **không phải danh sách dependency cần cài**.

## 3. Nếu cấu hình được nhắc tới không tồn tại thì sao?

Spring Boot xử lý danh sách các **auto-configuration candidate** được tìm thấy và được chọn để đưa vào application context. Tên trong `afterName`/`beforeName` tham gia vào cơ chế sắp xếp danh sách này. Nó **không phải** chỉ thị tải class, không phải `@Import`, cũng không tự làm ứng dụng cài thêm dependency.

| Tình trạng của `PartnerMessageAutoConfiguration` | Kết quả của `afterName` |
| --- | --- |
| Class **không tồn tại trên classpath** | Không thể tạo ràng buộc thứ tự với ứng viên đó; bản thân chuỗi tham chiếu không làm lỗi vì thiếu class |
| Class có trên classpath, nhưng **không được đăng ký làm auto-configuration candidate** | Không có ứng viên tương ứng để áp dụng ràng buộc |
| Auto-configuration của đối tác được chọn và xử lý | Auto-configuration hiện tại được sắp xếp **sau** cấu hình đối tác |
| Auto-configuration của đối tác được chọn, nhưng điều kiện riêng khiến bean của nó không được tạo | Thứ tự vẫn có ý nghĩa; fallback hiện tại vẫn có thể đăng ký nếu `@ConditionalOnMissingBean` khớp |
| Cả hai được chọn, nhưng bên đối tác không tạo bean đúng kiểu | Cấu hình hiện tại chạy sau, nhưng điều kiện thiếu bean có thể vẫn khớp |

Không có nghĩa “cấu hình đối tác được nhắc đến thì bắt buộc phải có mặt”. Cũng không có nghĩa “cấu hình đối tác đã được áp dụng thì chắc chắn tạo ra bean”: nó có thể bị chặn bởi `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` hoặc các điều kiện khác.

**Lưu ý:** nếu **chính mã của bạn** sử dụng API đối tác trong chữ ký phương thức hoặc trực tiếp khởi tạo class của đối tác, thì lỗi classpath vẫn có thể xảy ra. Tên chuỗi chỉ giúp giảm coupling cho *quan hệ thứ tự*, không tự kiểm tra toàn bộ đường phụ thuộc runtime.

## 4. Ví dụ production: fallback phải chạy sau tích hợp tùy chọn

Giả sử có interface `MessageService` do thư viện của bạn sở hữu và hai auto-configuration có khả năng cung cấp bean cùng kiểu. Cấu hình fallback của bạn có thể viết:

**Tệp:** `src/main/java/example/messaging/autoconfigure/MessageFallbackAutoConfiguration.java`

~~~java
package example.messaging.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration"
)
public class MessageFallbackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageService.class)
    MessageService defaultMessageService() {
        return () -> "local-fallback";
    }

    public interface MessageService {
        String source();
    }
}
~~~

Trong mã minh họa này:

- `afterName` mô tả **thứ tự** tương đối, không tạo đối tượng nào.
- `@ConditionalOnMissingBean(MessageService.class)` quyết định **có đăng ký fallback không**, dựa trên định nghĩa bean mà Spring đã thấy tại lúc đánh giá.
- Nếu đối tác được chọn và đã đăng ký `MessageService`, cấu hình fallback xử lý sau sẽ phát hiện bean đó và **không** đăng ký `defaultMessageService`.
- Nếu đối tác không có hoặc không đăng ký bean đúng kiểu, fallback có thể được tạo.
- Mã nguồn của fallback **không import** class tự cấu hình của đối tác.

**Điều kiện tiền đề:** để ví dụ hai bên tương tác thật sự, cấu hình đối tác phải đăng ký bean tương thích với `MessageService` (hoặc một interface chung được cả hai biết). Việc ghi tên đối tác trong `afterName` không khiến hai bean thuộc các kiểu không liên quan trở nên cùng kiểu.

Trong một starter thực tế, nên đặt interface dùng chung vào API package riêng; trong ví dụ này interface được khai báo lồng để trình bày gọn. Kiểu service dùng cho `@ConditionalOnMissingBean` phải là kiểu hợp lý mà downstream consumer dự kiến sử dụng.

### Đăng ký auto-configuration đúng cách

Spring Boot 3.x phát hiện auto-configuration của thư viện từ file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung ví dụ:

~~~text
example.messaging.autoconfigure.MessageFallbackAutoConfiguration
~~~

Chỉ liệt kê **auto-configuration do thư viện của bạn thực sự cung cấp**. Đừng thêm `com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration` vào imports của bạn chỉ vì bạn muốn sắp xếp sau nó. Nếu tích hợp đối tác không hiện diện, việc cố đăng ký class không tồn tại có thể gây lỗi khi Spring Boot xử lý ứng viên.

Nếu bên đối tác có starter của riêng họ, chính starter đó chịu trách nhiệm đăng ký auto-configuration của họ khi được sử dụng.

## 5. Vì sao thứ tự đặc biệt quan trọng với `@ConditionalOnMissingBean`?

Các điều kiện bean được đánh giá trên **những bean definitions đã được xử lý đến thời điểm hiện tại**. Do đó, hai cấu hình cung cấp cùng kiểu bean có thể đưa đến các kết quả khác nhau nếu được đăng ký không đúng thứ tự.

Với ví dụ này, luồng mong muốn là:

~~~text
Có PartnerMessageAutoConfiguration được chọn?
    |
    +-- Không --> Xử lý MessageFallbackAutoConfiguration
    |             -> Chưa có MessageService: đăng ký defaultMessageService
    |
    +-- Có ----> Xử lý PartnerMessageAutoConfiguration trước
                  |
                  +-- Đã đăng ký MessageService
                  |     -> Fallback chạy sau, thấy bean
                  |     -> KHÔNG đăng ký defaultMessageService
                  |
                  +-- Không đăng ký MessageService
                        -> Fallback chạy sau, vẫn thiếu bean
                        -> Đăng ký defaultMessageService
~~~

**Quan trọng:** `afterName` không có tác dụng “chọn bean nào được inject”. Nó tác động lên **thứ tự xử lý auto-configuration**; còn `@ConditionalOnMissingBean` quyết định có bean definition dự phòng hay không. Một khi nhiều bean cùng kiểu đã tồn tại, cơ chế injection như `@Primary` hoặc `@Qualifier` là vấn đề riêng.

### Định nghĩa bean và đối tượng bean là hai mốc khác nhau

Giả sử bean A đăng ký trước bean B; điều đó **không** đảm bảo constructor của A chạy trước constructor của B. Thứ tự tạo bean do dependency graph, `@DependsOn` và cơ chế vòng đời của Spring quyết định.

Vì vậy:

- `afterName`/`beforeName`: dùng để xác định **trình tự áp dụng auto-configuration**.
- `@DependsOn`: dùng khi thực sự cần biểu đạt **quan hệ khởi tạo bean**, không thay cho sắp xếp auto-configuration.
- `@AutoConfigureOrder`: gợi ý thứ tự tổng quát giữa các auto-configuration; không thể hiện trực tiếp “sau class tùy chọn X” rõ bằng `afterName`.
- `@ConditionalOnMissingBean`: kiểm tra hiện diện của bean theo kiểu/tên tại thời điểm đánh giá; không thay thế các ràng buộc thứ tự khi hai auto-configuration cung cấp cùng một kiểu.

## 6. Ví dụ kiểm chứng hoàn chỉnh với JUnit 5 và ApplicationContextRunner

Ví dụ này mô phỏng một auto-configuration đối tác **có thể được đăng ký hoặc không**, đồng thời có thêm một tên cấu hình **không có trên classpath**. Khi cả hai auto-configuration được chọn, Spring Boot phải áp dụng ràng buộc `afterName` và đăng ký bean đối tác trước bean fallback.

**Tệp:** `src/test/java/example/order/NameOnlyOrderingTest.java`

~~~java
package example.order;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class NameOnlyOrderingTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner();

    @Test
    void usesFallbackWhenPartnerAutoConfigurationIsNotSelected() {
        runner.withConfiguration(
                AutoConfigurations.of(FallbackAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasSingleBean(MessageService.class);
                assertThat(context.containsBean("fallbackMessageService")).isTrue();
                assertThat(context.getBean(MessageService.class).source())
                        .isEqualTo("fallback");
            });
    }

    @Test
    void partnerWinsWhenBothAutoConfigurationsAreSelected() {
        // Cố tình đưa Fallback vào danh sách trước Partner.
        // AutoConfigurations.of áp dụng thứ tự auto-configuration của Boot.
        runner.withConfiguration(
                AutoConfigurations.of(
                        FallbackAutoConfiguration.class,
                        PartnerAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasSingleBean(MessageService.class);
                assertThat(context.containsBean("partnerMessageService")).isTrue();
                assertThat(context.containsBean("fallbackMessageService")).isFalse();
                assertThat(context.getBean(MessageService.class).source())
                        .isEqualTo("partner");
            });
    }

    @Test
    void userBeanAlsoPreventsFallback() {
        runner.withUserConfiguration(UserConfiguration.class)
            .withConfiguration(AutoConfigurations.of(FallbackAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasSingleBean(MessageService.class);
                assertThat(context.containsBean("userMessageService")).isTrue();
                assertThat(context.containsBean("fallbackMessageService")).isFalse();
            });
    }

    interface MessageService {
        String source();
    }

    @AutoConfiguration(afterName = {
        "example.order.NameOnlyOrderingTest$PartnerAutoConfiguration",
        "com.vendor.unavailable.NotInstalledAutoConfiguration"
    })
    static class FallbackAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(MessageService.class)
        MessageService fallbackMessageService() {
            return () -> "fallback";
        }
    }

    @AutoConfiguration
    static class PartnerAutoConfiguration {

        @Bean
        MessageService partnerMessageService() {
            return () -> "partner";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        MessageService userMessageService() {
            return () -> "user";
        }
    }
}
~~~

### Giải thích đặc biệt về tên class lồng nhau

Trong tệp test, `PartnerAutoConfiguration` là **static nested class** trong `NameOnlyOrderingTest`. Tên nhị phân đúng mà Spring Boot dùng cho tham chiếu thứ tự là:

~~~text
example.order.NameOnlyOrderingTest$PartnerAutoConfiguration
~~~

Dấu **`$`**, không phải dấu chấm, phân tách class chứa bên ngoài và class lồng bên trong. Đây cũng là quy ước được Javadoc chính thức của `afterName`/`beforeName` mô tả. Khi dùng trong code production, nên ưu tiên auto-configuration là **top-level class**; lúc đó tên thường có dạng `com.vendor.package.SomeAutoConfiguration`.

Chuỗi `com.vendor.unavailable.NotInstalledAutoConfiguration` trong test là tên giả định **không có dependency tương ứng**. Nó minh họa việc một ràng buộc thứ tự không có đối tượng khớp vẫn không cản fallback hoạt động. Test thứ nhất chỉ nạp fallback, test thứ hai nạp cả fallback và partner, test thứ ba chứng minh bean người dùng được xử lý trước auto-configuration.

### Dependency và lệnh chạy

Tệp test sử dụng Java 17+ và Spring Boot 3.3.x. Với Gradle Groovy DSL, dự án có Spring Boot plugin hoặc dependency-management/BOM đã quản lý version có thể dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy trong đúng module chứa test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.order.NameOnlyOrderingTest"

# Windows
gradlew.bat test --tests "example.order.NameOnlyOrderingTest"
~~~

**Kết quả mong đợi:** ba test đều PASS. Test 1 thu được `"fallback"`, test 2 thu được `"partner"` và không có bean fallback, test 3 không có bean fallback vì bean người dùng đã hiện diện. Không có `System.out.println`; test kiểm chứng bằng assertion nên **không có stdout nội dung cố định** ngoài thông tin Gradle/test runner.

Ví dụ này kiểm tra **thứ tự auto-configuration và bean definition** trong context nhỏ. Nó không yêu cầu cài thư viện đối tác thật. Khi tích hợp một đối tác thực tế, nên bổ sung test riêng với artifact đối tác để phát hiện thay đổi package/class name hoặc điều kiện đăng ký bean của họ.

## 7. Quan hệ với classpath condition: hai nhiệm vụ khác nhau

Khi lớp đối tác là tùy chọn, đôi khi ngoài thứ tự còn phải kiểm tra một **API/SDK** thực sự tồn tại. Lúc đó sử dụng `@ConditionalOnClass`:

~~~java
@AutoConfiguration(
    afterName = "com.vendor.messaging.autoconfigure.PartnerMessageAutoConfiguration"
)
@ConditionalOnClass(name = "com.vendor.messaging.PartnerClient")
class PartnerBridgeAutoConfiguration {
    // Cấu hình tích hợp được viết an toàn theo classpath thực tế.
}
~~~

Đoạn trên chỉ minh họa annotation. Trong code production, cần import `ConditionalOnClass` và tổ chức các `@Bean` có kiểu trả về/đối số thuộc SDK tùy chọn trong **cấu hình lồng riêng** được bảo vệ bởi classpath condition, vì JVM có thể phải tải chữ ký method trước khi condition trên method được áp dụng.

Đừng nhầm ba câu hỏi:

| Công cụ | Nó trả lời câu hỏi gì? |
| --- | --- |
| `afterName` / `beforeName` | “Nếu các auto-configuration đó được chọn, ta nên xử lý cái nào trước?” |
| `@ConditionalOnClass(name = "...")` | “Classpath của ứng dụng có kiểu API/SDK này không?” |
| `@ConditionalOnMissingBean(Service.class)` | “Tại thời điểm đánh giá, context đã có bean phù hợp kiểu này chưa?” |

Kết hợp đúng công cụ theo đúng mục đích. **Tên của một auto-configuration trong `afterName` không phải điều kiện hiện diện SDK**.

## 8. Những giới hạn và lỗi phổ biến

1. **Dùng tên đơn giản thay vì fully qualified class name.** Viết `"PartnerAutoConfiguration"` có thể không khớp class thật `"com.vendor.autoconfigure.PartnerAutoConfiguration"`. Hãy lấy tên class đầy đủ từ artifact/tài liệu của đối tác.
2. **Nhầm package của SDK với package của auto-configuration.** `com.vendor.api.Client` và `com.vendor.autoconfigure.ClientAutoConfiguration` là hai class khác nhau. `afterName` cần đúng tên **auto-configuration**, không phải tên client SDK.
3. **Cho rằng `afterName` sẽ bật hoặc import cấu hình đối tác.** Nó chỉ mô tả thứ tự nếu đối tác đã là candidate được chọn. Bên đối tác phải tự được đăng ký qua cơ chế auto-configuration/import phù hợp.
4. **Giả định class đối tác có trên classpath đồng nghĩa bean đối tác đã được tạo.** Auto-configuration có thể không được chọn hoặc điều kiện của nó không khớp. Kiểm tra điều kiện và bean definition thực tế.
5. **Tham chiếu trực tiếp `OptionalAutoConfiguration.class` dù muốn module độc lập khi biên dịch.** Cách đó đòi có class ở compile classpath. Dạng `afterName="fully.qualified.Name"` tránh ràng buộc đó trong khai báo thứ tự.
6. **Trộn dấu chấm và `$` cho nested class.** Với nested configuration, tên nhị phân dùng `$`; sai tên có thể khiến thứ tự mong muốn không được áp dụng.
7. **Cấu hình trước/sau trái ý định fallback.** Nếu `@ConditionalOnMissingBean` cần thấy bean do đối tác đăng ký, cấu hình fallback thông thường nên dùng `afterName`, không phải `beforeName`.
8. **Kỳ vọng annotation thay đổi thứ tự constructor.** Thứ tự áp dụng auto-configuration không đảm bảo thứ tự khởi tạo bean. Khi cần quan hệ khởi tạo thật, hãy mô hình hóa bằng dependency và `@DependsOn` nếu phù hợp.
9. **Hard-code tên class của bên thứ ba nhưng không có test tích hợp.** Đối tác nâng cấp có thể đổi tên hoặc chuyển package; khi chuỗi không còn khớp, ràng buộc thứ tự mất hiệu lực mà không có lỗi biên dịch báo trước.
10. **Viết `@ConditionalOnClass` ở method nhưng chữ ký method trực tiếp tham chiếu class không có trên classpath.** Hãy tách phần tích hợp vào cấu hình có điều kiện ở cấp class theo hướng dẫn Spring Boot.

### Nếu đối tác đổi tên auto-configuration

Chuỗi FQCN không được trình biên dịch kiểm tra, nên khi đối tác đổi package/tên class, một ràng buộc thứ tự có thể trở nên không còn hiệu lực. Với thư viện bạn kiểm soát, Spring Boot cung cấp cơ chế `AutoConfiguration.replacements` khi di chuyển/đổi tên auto-configuration để giữ tương thích với tham chiếu và exclusions cũ. Với thư viện bên ngoài, hãy xác minh release notes và bổ sung test tích hợp theo version mà ứng dụng hỗ trợ.

### Chẩn đoán trong thực tế

- Kiểm tra class mong đợi có thực sự nằm trong file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` của artifact liên quan hay không.
- Xem auto-configuration có được chọn, có bị loại bởi điều kiện classpath/property/bean hoặc exclude hay không.
- Bật `--debug` và đọc **Condition Evaluation Report** để biết những điều kiện bean/class đã khớp hay không khớp.
- Khi vấn đề là **thứ tự**, viết `ApplicationContextRunner` test có cả hai auto-configuration và xác minh bean definitions/fallback như ví dụ trên. Báo cáo điều kiện không phải lúc nào cũng cho bạn biết nguyên nhân sắp xếp; test cả hai ứng viên cung cấp chứng cứ trực tiếp hơn.

## 9. Tự kiểm tra

**Câu 1.** Một starter A khai báo `@AutoConfiguration(afterName="com.vendor.BAutoConfiguration")`, nhưng B hoàn toàn không được cài. A có bắt buộc thất bại vì không tìm thấy class B không?

**Đáp án:** Không, chỉ tham chiếu B bằng chuỗi tên trong ràng buộc thứ tự không ép phải tải class đó. A vẫn phải có class/dependency cho chính các API A sử dụng.

**Câu 2.** Cài artifact của B nhưng auto-configuration B không được chọn. `afterName` có tự đăng ký B không?

**Đáp án:** Không. Thuộc tính chỉ sắp xếp những auto-configuration đã được chọn làm ứng viên.

**Câu 3.** B được xử lý trước A nhưng B không tạo bean `MessageService`. A có thể đăng ký fallback không?

**Đáp án:** Có. `@ConditionalOnMissingBean(MessageService.class)` dựa vào bean definition thực sự có tại thời điểm đánh giá, không dựa vào tên B có xuất hiện trong `afterName`.

**Câu 4.** Vì sao test cần dùng đúng `NameOnlyOrderingTest$PartnerAutoConfiguration` thay vì `NameOnlyOrderingTest.PartnerAutoConfiguration`?

**Đáp án:** Vì đây là **nested Java class**. Tên class ở dạng nhị phân được dùng trong metadata annotation có `$` giữa class chứa bên ngoài và class lồng.

**Câu 5.** `afterName` có đảm bảo constructor bean B chạy trước constructor bean A không?

**Đáp án:** Không. Nó ảnh hưởng thứ tự xử lý auto-configuration/định nghĩa bean, còn khởi tạo đối tượng phụ thuộc vòng đời và dependency graph của Spring.

## 10. Ghi nhớ khi áp dụng

Khi một auto-configuration có nhu cầu thứ tự tương đối với **thư viện tùy chọn**, ưu tiên khai báo bằng **tên đầy đủ của auto-configuration**:

~~~java
@AutoConfiguration(afterName = "com.vendor.OptionalAutoConfiguration")
~~~

Dùng `beforeName` cho chiều ngược lại. Không thêm dependency chỉ để tham chiếu `SomeAutoConfiguration.class` khi thông tin duy nhất cần dùng là tên cho việc sắp xếp. Đồng thời, nếu bean chỉ cần tồn tại khi class SDK hiện diện, hãy kiểm tra classpath riêng; nếu muốn fallback nhường chỗ cho bean đã được đăng ký, hãy dùng `@ConditionalOnMissingBean` và kiểm chứng **khi cấu hình đối tác vắng mặt, khi có mặt và khi bean người dùng đã tồn tại**.

### Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — `@AutoConfiguration` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 — `@AutoConfigureAfter` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html)
- [Spring Boot 3.3 — `@AutoConfigureBefore` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html)
