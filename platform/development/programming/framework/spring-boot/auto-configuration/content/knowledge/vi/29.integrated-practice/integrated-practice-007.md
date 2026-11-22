# Bổ sung customizer để thay đổi hành vi mà không thay toàn bộ bean trong Spring Boot

## 1. Bài toán: cần thêm một hành vi nhưng muốn giữ cấu hình mặc định

Một thư viện Spring Boot thường tạo sẵn bean để ứng dụng có thể dùng ngay: HTTP client, ObjectMapper, task executor, cache manager hoặc một client chuyên biệt của thư viện. Sau khi tích hợp, mỗi ứng dụng có thể cần điều chỉnh thêm một vài hành vi:

- Thêm header mặc định vào HTTP client.
- Đăng ký serializer hoặc module cho JSON.
- Thêm interceptor, retry policy hoặc timeout riêng.
- Đổi thread name prefix hoặc cấu hình shutdown của executor.
- Bổ sung codec cho một giao thức.

Nếu người dùng phải tự khai báo lại toàn bộ bean chỉ để thay đổi một thuộc tính nhỏ, họ sẽ phải sao chép cấu hình mặc định, tự quản lý các dependency và chịu trách nhiệm cập nhật khi thư viện thay đổi. Cách đó dễ làm mất những tích hợp mà Spring Boot đã cung cấp như message converters, observation, metrics, SSL, resource management hoặc các cấu hình có điều kiện.

**Customizer** là một extension point cho phép ứng dụng đóng góp một callback để điều chỉnh builder hoặc object mà auto-configuration đang tạo. Auto-configuration vẫn sở hữu quy trình tạo bean và giữ các mặc định; customizer chỉ thay đổi phần hành vi mà nó quan tâm.

## 2. Customizer là gì?

Customizer thường là một interface callback có một method, nhận đối tượng mục tiêu rồi thay đổi một số thiết lập trên đối tượng đó.

Ví dụ về contract:

~~~java
@FunctionalInterface
public interface ClientBuilderCustomizer {
    void customize(ClientBuilder builder);
}
~~~

Một bean triển khai interface này có thể thêm header:

~~~java
@Bean
ClientBuilderCustomizer applicationHeader() {
    return builder -> builder.defaultHeader(
            "X-Application", "catalog-service");
}
~~~

Auto-configuration thu thập các customizer, áp dụng chúng lên builder rồi mới gọi build để tạo client.

Một customizer tốt có phạm vi hẹp và dễ dự đoán:
- Chỉ thay đổi những thiết lập thuộc trách nhiệm của nó.
- Không tự tạo một bean thay thế trong Spring container.
- Không thực hiện network call hoặc truy cập database trong callback.
- Không giữ builder để sửa ở một thời điểm không xác định sau khi bean đã được tạo.
- Không giả định chỉ có một customizer trong ứng dụng.

Customizer là một hợp đồng mở rộng; nó không phải một cơ chế tự động của Java. Từng subsystem cần định nghĩa target type, thời điểm gọi và quy tắc thứ tự riêng.

## 3. Phân biệt customizer, configuration properties và thay thế bean

Ba cơ chế này giải quyết các nhu cầu khác nhau:

| Cơ chế | Phù hợp khi | Ví dụ |
| --- | --- | --- |
| `@ConfigurationProperties` | Người dùng cần thay đổi các lựa chọn phổ biến, ổn định và có thể biểu diễn bằng cấu hình | Base URL, timeout, pool size, cache TTL |
| Customizer | Người dùng cần bổ sung hành vi nâng cao mà thư viện chưa đưa thành property | Thêm interceptor, serializer, header, codec |
| Tự khai báo bean cùng loại | Người dùng cần một implementation hoặc lifecycle khác đáng kể | Dùng client khác, factory riêng, thay toàn bộ ObjectMapper |

Một quy tắc thực tế: property dành cho lựa chọn cấu hình mà thư viện muốn hỗ trợ chính thức; customizer dành cho điểm mở rộng có chủ đích; bean override dành cho trường hợp ứng dụng muốn sở hữu implementation.

Không nên tạo property cho mọi method của thư viện bên thứ ba. Cũng không nên buộc người dùng thay toàn bộ bean chỉ để thêm một interceptor.

## 4. Spring Boot đã cung cấp nhiều customizer có sẵn

Trước khi tự thiết kế interface mới, hãy kiểm tra subsystem có extension point phù hợp hay chưa.

| Customizer | Đối tượng được điều chỉnh | Mục đích |
| --- | --- | --- |
| `RestClientCustomizer` | `RestClient.Builder` | Thêm cấu hình dùng chung cho RestClient |
| `WebClientCustomizer` | `WebClient.Builder` | Thêm cấu hình dùng chung cho WebClient |
| `Jackson2ObjectMapperBuilderCustomizer` | `Jackson2ObjectMapperBuilder` | Điều chỉnh ObjectMapper mà vẫn giữ auto-configuration |
| `ThreadPoolTaskExecutorCustomizer` | `ThreadPoolTaskExecutor` | Điều chỉnh executor được tạo từ builder |
| `RSocketStrategiesCustomizer` | `RSocketStrategies.Builder` | Bổ sung codec hoặc chiến lược encoding/decoding |

Các interface này là callback beans. Auto-configuration của subsystem nhận chúng và áp dụng vào đối tượng tương ứng.

Điểm cần nhớ: không phải customizer nào cũng nhận builder. Ví dụ `ThreadPoolTaskExecutorCustomizer` nhận instance `ThreadPoolTaskExecutor`, trong khi `RestClientCustomizer` nhận `RestClient.Builder`. Hãy đọc contract của đúng interface trước khi chọn lifecycle và cách test.

## 5. Chọn phạm vi customization

Một thay đổi có thể áp dụng ở nhiều phạm vi:

1. **Một instance:** chỉ cấu hình một client hoặc một bean tại nơi sử dụng.
2. **Mọi builder do Spring Boot cung cấp:** đăng ký customizer bean dùng chung trong ApplicationContext.
3. **Toàn bộ implementation:** thay bean hoặc cấu hình subsystem hoàn toàn.

Ví dụ, nếu chỉ một client cần base URL riêng, inject builder rồi gọi `baseUrl(...)` tại service tạo client. Nếu mọi RestClient cần cùng một header nhận diện ứng dụng, dùng `RestClientCustomizer`.

Với `WebClient.Builder` và `RestClient.Builder`, builder có trạng thái. Thay đổi trên builder ảnh hưởng đến các client được build sau đó từ chính builder đó. Khi cần nhiều client có cấu hình riêng, clone builder trước khi sửa để tránh cấu hình của client này lan sang client khác.

## 6. Thiết kế customizer riêng cho một thư viện

Giả sử thư viện cung cấp `WidgetClient` để gọi dịch vụ bên ngoài. Builder của thư viện hỗ trợ:
- `baseUrl(...)` để đặt địa chỉ dịch vụ.
- `defaultHeader(...)` để thêm header.
- `requestInterceptor(...)` để bổ sung xử lý request.
- `build()` để tạo client cuối cùng.

Thư viện định nghĩa một extension point công khai trong module autoconfigure:

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.client.WidgetClient;

@FunctionalInterface
public interface WidgetClientBuilderCustomizer {

    void customize(WidgetClient.Builder builder);
}
~~~

Contract này có một mục tiêu rõ ràng: cho ứng dụng chỉnh `WidgetClient.Builder` trước khi auto-configuration tạo `WidgetClient`.

Đặt interface trong module autoconfigure hoặc module API mà ứng dụng consumer có thể truy cập. Đừng để interface chỉ nằm trong package nội bộ không được export nếu người dùng cần khai báo bean triển khai nó.

## 7. Auto-configuration áp dụng tất cả customizer trước khi build

Auto-configuration có thể thu thập nhiều bean cùng loại bằng `ObjectProvider`:

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.client.WidgetClient;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(WidgetClient.class)
@EnableConfigurationProperties(WidgetClientProperties.class)
public class WidgetClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(WidgetClient.class)
    WidgetClient widgetClient(
            WidgetClientProperties properties,
            ObjectProvider<WidgetClientBuilderCustomizer> customizers) {

        WidgetClient.Builder builder = WidgetClient.builder()
                .baseUrl(properties.getBaseUrl());

        customizers.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder.build();
    }
}
~~~

Luồng tạo bean:

1. Spring Boot đọc property và tạo cấu hình mặc định cho builder.
2. `ObjectProvider.orderedStream()` lấy các bean `WidgetClientBuilderCustomizer` theo thứ tự Spring.
3. Từng callback điều chỉnh cùng builder của lần tạo client này.
4. Auto-configuration gọi `build()` một lần để tạo `WidgetClient`.
5. `@ConditionalOnMissingBean` bảo đảm client mặc định chỉ được tạo khi ứng dụng chưa cung cấp bean cùng loại.

Nếu không có customizer nào, stream rỗng và client vẫn được tạo từ cấu hình mặc định. Không cần khai báo một no-op customizer chỉ để lấp danh sách.

Đây là ví dụ kiến trúc: `WidgetClient`, `WidgetClientProperties` và các method builder là API giả định của thư viện minh họa. Khi áp dụng vào thư viện thật, thay bằng contract thực tế của client đó.

## 8. Ứng dụng đóng góp nhiều customizer độc lập

Mỗi nhu cầu có thể được đóng gói thành một bean riêng:

~~~java
@Configuration(proxyBeanMethods = false)
class WidgetClientCustomizationConfiguration {

    @Bean
    @Order(10)
    WidgetClientBuilderCustomizer applicationHeader() {
        return builder -> builder.defaultHeader(
                "X-Application", "catalog-service");
    }

    @Bean
    @Order(20)
    WidgetClientBuilderCustomizer tenantHeader() {
        return builder -> builder.defaultHeader(
                "X-Tenant", "north");
    }
}
~~~

Hai customizer không cần biết về nhau. Một bean thêm thông tin ứng dụng, bean còn lại thêm thông tin tenant. Auto-configuration thu thập cả hai rồi áp dụng theo thứ tự.

Spring sắp xếp các bean có `Ordered` hoặc `@Order`; giá trị order nhỏ hơn được áp dụng trước. Nếu hai customizer cùng sửa một thiết lập, kết quả phụ thuộc vào cách builder xử lý lời gọi và thứ tự callback. Ví dụ, nếu `defaultHeader` thay giá trị cũ của cùng header, callback chạy sau có thể ghi đè giá trị trước.

Chỉ đặt order khi có quan hệ thực sự giữa các bước. Tránh dùng thứ tự như một cơ chế ngầm để giải quyết xung đột cấu hình mà không giải thích rõ.

## 9. Properties nên được áp dụng trước customizer

Auto-configuration nên áp dụng các property ổn định trước, sau đó mới gọi customizer để ứng dụng có cơ hội điều chỉnh chi tiết hơn.

Ví dụ:

~~~java
WidgetClient.Builder builder = WidgetClient.builder()
        .baseUrl(properties.getBaseUrl())
        .connectTimeout(properties.getConnectTimeout())
        .readTimeout(properties.getReadTimeout());

customizers.orderedStream()
        .forEach(customizer -> customizer.customize(builder));

return builder.build();
~~~

Trình tự này tạo một baseline nhất quán:
- Property thể hiện cấu hình mặc định mà thư viện hỗ trợ.
- Customizer có thể bổ sung interceptor hoặc điều chỉnh một tùy chọn nâng cao.
- `build()` tạo instance cuối cùng sau khi toàn bộ callback hoàn tất.

Nếu customizer ghi đè một giá trị đã được property đặt, hãy coi đó là hành vi override có chủ đích. Ghi tài liệu rõ để người dùng hiểu nguồn cấu hình nào có độ ưu tiên cao hơn.

Không áp dụng customizer sau khi đã build nếu contract của customizer yêu cầu builder. Khi object đã được tạo, thay đổi có thể không còn tác dụng hoặc phải dựa vào API mutation riêng của implementation.

## 10. Ví dụ thực tế: RestClientCustomizer

Spring Boot 3.3 cung cấp `RestClientCustomizer` trong package `org.springframework.boot.web.client`. Interface này nhận `RestClient.Builder`.

~~~java
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class RestClientConfiguration {

    @Bean
    RestClientCustomizer applicationIdentityHeader() {
        return builder -> builder.defaultHeader(
                "X-Application", "orders-service");
    }
}
~~~

Service sử dụng builder do Boot cung cấp:

~~~java
@Service
class CatalogGateway {

    private final RestClient client;

    CatalogGateway(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://catalog.example.test")
                .build();
    }
}
~~~

Boot tạo và cấu hình `RestClient.Builder` với message converters và request factory phù hợp. Customizer bean bổ sung header cho các builder được auto-configure. Service chỉ cần chọn base URL và build client.

Nếu gọi trực tiếp `RestClient.create()`, đường auto-configuration và `RestClientCustomizer` không được áp dụng. Vì vậy, khi muốn hưởng cấu hình chung của Boot, hãy inject builder đã được auto-configure.

## 11. Ví dụ WebClientCustomizer và builder có trạng thái

`WebClientCustomizer` trong package `org.springframework.boot.web.reactive.function.client` nhận `WebClient.Builder`.

~~~java
@Bean
WebClientCustomizer correlationHeader() {
    return builder -> builder.defaultHeader(
            "X-Correlation-Source", "billing");
}
~~~

Có thể inject builder tại nơi tạo client:

~~~java
@Service
class BillingGateway {

    private final WebClient client;

    BillingGateway(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://billing.example.test")
                .build();
    }
}
~~~

Tài liệu Spring Boot lưu ý `WebClient.Builder` là stateful: mọi thay đổi trên builder ảnh hưởng đến client được tạo sau đó từ builder đó. Nếu cùng một nơi cần nhiều client có thiết lập riêng, clone trước khi tùy chỉnh:

~~~java
WebClient.Builder billingBuilder = builder.clone();
WebClient.Builder identityBuilder = builder.clone();

WebClient billingClient = billingBuilder
        .baseUrl("https://billing.example.test")
        .build();

WebClient identityClient = identityBuilder
        .baseUrl("https://identity.example.test")
        .build();
~~~

Nếu gọi `WebClient.create()` trực tiếp, auto-configuration và customizer của Boot không được áp dụng.

## 12. Ví dụ Jackson: bổ sung cấu hình mà vẫn giữ ObjectMapper mặc định

Spring Boot cung cấp `Jackson2ObjectMapperBuilderCustomizer`. Interface này cho phép chỉnh `Jackson2ObjectMapperBuilder` và giữ lại quy trình auto-configuration mặc định.

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
class JacksonCustomizationConfiguration {

    @Bean
    @Order(10)
    Jackson2ObjectMapperBuilderCustomizer omitNullProperties() {
        return builder -> builder.serializationInclusion(
                JsonInclude.Include.NON_NULL);
    }
}
~~~

Spring Boot có customizer nội bộ với order `0`. Customizer ở order `10` được áp dụng sau customizer đó. Nhờ vậy, ứng dụng có thể bổ sung quy tắc riêng mà vẫn dùng builder và các tích hợp JSON do Boot quản lý.

Nếu khai báo một bean `ObjectMapper` riêng hoặc một bean `Jackson2ObjectMapperBuilder` riêng để thay thế cấu hình mặc định, Spring Boot sẽ ngừng auto-configure ObjectMapper theo cơ chế thông thường. Hãy chọn customizer nếu chỉ cần thay một vài quy tắc serialization.

## 13. Ví dụ ThreadPoolTaskExecutorCustomizer

Spring Boot 3.3 có `ThreadPoolTaskExecutorCustomizer` trong package `org.springframework.boot.task`. Callback nhận instance `ThreadPoolTaskExecutor`.

~~~java
import org.springframework.boot.task.ThreadPoolTaskExecutorCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ExecutorCustomizationConfiguration {

    @Bean
    ThreadPoolTaskExecutorCustomizer executorShutdownPolicy() {
        return executor -> {
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(20);
        };
    }
}
~~~

`ThreadPoolTaskExecutorBuilder` của Boot hỗ trợ thêm các customizer để cấu hình executor được tạo ra. Customizer này điều chỉnh instance executor trong quá trình builder cấu hình nó.

Không nhầm interface này với một callback nhận builder. Contract của nó là `customize(ThreadPoolTaskExecutor taskExecutor)`, vì vậy code cần thao tác trên executor instance.

## 14. Khi nào customizer được áp dụng và khi nào bị bỏ qua?

Phạm vi áp dụng phụ thuộc vào đường tạo object:

| Cách tạo object | Customizer của auto-configuration có được áp dụng? |
| --- | --- |
| Inject builder do Boot auto-configure rồi gọi `build()` | Có, nếu subsystem tích hợp customizer |
| Auto-configuration của thư viện nhận customizer beans và gọi callback | Có |
| Gọi trực tiếp `RestClient.create()` hoặc `WebClient.create()` | Không áp dụng customizer của builder auto-configure |
| Ứng dụng tự khai báo bean client hoàn chỉnh | Bean mặc định back off; customizer của factory mặc định không tự chạy trên bean ứng dụng |
| Tự tạo builder bằng constructor/API độc lập | Không tự động; phải gọi customizer nếu muốn tái sử dụng contract |

Điểm cuối rất quan trọng khi viết thư viện. Việc một customizer bean tồn tại trong context không có nghĩa Spring sẽ tự tìm mọi object cùng loại và sửa chúng. Phải có một auto-configuration hoặc factory chủ động thu thập và gọi callback.

## 15. Customizer tương tác với @ConditionalOnMissingBean

Một auto-configuration thường tạo bean mặc định bằng:

~~~java
@Bean
@ConditionalOnMissingBean(WidgetClient.class)
WidgetClient widgetClient(...) {
    // Tạo client mặc định và áp dụng customizers
}
~~~

Khi ứng dụng đăng ký `WidgetClientBuilderCustomizer`, bean mặc định vẫn được tạo và callback được áp dụng.

Khi ứng dụng tự đăng ký một bean `WidgetClient`, điều kiện `@ConditionalOnMissingBean` không còn khớp. Factory mặc định không chạy, do đó các customizer dành cho builder của factory đó cũng không tự động tác động lên bean do ứng dụng tạo.

Đây là hành vi có chủ đích:
- Customizer: ứng dụng muốn giữ factory và defaults của thư viện, chỉ bổ sung hành vi.
- Bean override: ứng dụng muốn sở hữu hoàn toàn object và cách tạo object.

Nếu ứng dụng tự tạo bean nhưng vẫn muốn tái sử dụng customizer, nó có thể tạo builder và gọi các callback theo contract phù hợp. Tuy nhiên, nên cân nhắc dùng builder bean hoặc factory công khai để tránh lặp lại logic tạo mặc định.

## 16. Không dùng BeanPostProcessor thay cho customizer có chủ đích

`BeanPostProcessor` có thể can thiệp vào bean sau khi container khởi tạo hoặc trước khi bean được đưa ra sử dụng. Đây là extension point ở phạm vi rộng và có ảnh hưởng đến lifecycle.

Dùng một `BeanPostProcessor` tổng quát chỉ để thêm header vào một loại client thường gây khó hiểu:
- Tác động có thể rộng hơn bean mà thư viện muốn hỗ trợ.
- Thời điểm can thiệp khó nhìn thấy ở nơi khai báo bean.
- Proxy hoặc thứ tự post-processor có thể làm thay đổi hành vi.
- Test phải kiểm tra cả lifecycle và việc thay thế object.

Customizer chuyên biệt cho biết rõ target type và thời điểm điều chỉnh. Dùng `BeanPostProcessor` khi thật sự cần can thiệp vào lifecycle của nhiều bean theo một quy tắc chung, không phải để thay một callback builder đơn giản.

## 17. Thiết kế customizer để dễ bảo trì

Một extension point công khai cần có hợp đồng ổn định:

- **Đặt tên rõ target:** ví dụ `WidgetClientBuilderCustomizer`, không dùng một interface chung chung tên `Customizer`.
- **Giữ method đơn giản:** một callback `customize(...)` là đủ cho đa số trường hợp.
- **Không làm rò rỉ implementation nội bộ:** chỉ expose những API mà người dùng cần để cấu hình.
- **Tách theo subsystem:** HTTP client, cache và executor nên có customizer riêng nếu chúng có lifecycle khác nhau.
- **Hỗ trợ nhiều bean:** thiết kế theo danh sách callback thay vì chỉ inject một instance.
- **Quy định thứ tự:** dùng `Ordered` hoặc `@Order` khi thứ tự có ảnh hưởng và giải thích điều gì xảy ra khi hai customizer sửa cùng thuộc tính.
- **Giữ defaults:** áp dụng property và cấu hình nội bộ trước callback, rồi build object sau cùng.
- **Tài liệu hóa phạm vi:** nói rõ customizer tác động một instance, mọi builder do Boot tạo hay một bean factory cụ thể.

Không nên cho customizer quyền thay đổi mọi thứ trong container. Nó chỉ nên mở đúng điểm mà thư viện muốn hỗ trợ.

## 18. Kiểm thử customizer bằng ApplicationContextRunner

Với thư viện auto-configuration, `ApplicationContextRunner` giúp kiểm tra bean mặc định và callback mà không cần khởi động cả ứng dụng.

Ví dụ kiểm thử customizer được áp dụng:

~~~java
class WidgetClientAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    WidgetClientAutoConfiguration.class))
                    .withPropertyValues(
                            "acme.widget.base-url=https://widget.example.test");

    @Test
    void appliesCustomizerAndKeepsDefaultClient() {
        runner.withBean(
                WidgetClientBuilderCustomizer.class,
                () -> builder -> builder.defaultHeader(
                        "X-Test-Mode", "enabled"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WidgetClient.class);

                    WidgetClient client =
                            context.getBean(WidgetClient.class);

                    assertThat(client.defaultHeaders())
                            .containsEntry("X-Test-Mode", "enabled");
                    assertThat(client.baseUrl())
                            .isEqualTo("https://widget.example.test");
                });
    }
}
~~~

Test này xác nhận:
- Auto-configuration vẫn tạo đúng một bean client mặc định.
- Customizer được tìm thấy và gọi trước `build()`.
- Header được bổ sung.
- Base URL lấy từ property vẫn được giữ.

Có thể bổ sung các test khác:
- Không có customizer: client vẫn được tạo với defaults.
- Có hai customizer: cả hai thay đổi đều xuất hiện.
- Hai customizer cùng sửa một thuộc tính: xác nhận thứ tự và kết quả cuối.
- Người dùng cung cấp bean client riêng: bean mặc định back off.
- Dependency tùy chọn vắng mặt: auto-configuration không tạo client phụ thuộc class đó.

Lưu ý: ví dụ `WidgetClient` và các accessor `defaultHeaders()`/`baseUrl()` là API minh họa. Điều chỉnh assertion theo API thực tế của thư viện.

## 19. Ví dụ Java 17 chạy độc lập để hiểu callback

Chương trình sau mô phỏng ý tưởng customizer bằng Java thuần. Nó có một builder, hai callback độc lập và một bước build cuối cùng. Chương trình không dùng Spring; phần Spring-specific là việc container tự tìm và sắp xếp customizer beans.

Tệp `CustomizerDemo.java`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class CustomizerDemo {

    record BuiltClient(String baseUrl, Map<String, String> headers) {
    }

    static final class ClientBuilder {

        private String baseUrl;
        private final Map<String, String> headers = new LinkedHashMap<>();

        ClientBuilder baseUrl(String baseUrl) {
            this.baseUrl = Objects.requireNonNull(baseUrl);
            return this;
        }

        ClientBuilder defaultHeader(String name, String value) {
            headers.put(name, value);
            return this;
        }

        BuiltClient build() {
            if (baseUrl == null) {
                throw new IllegalStateException("baseUrl is required");
            }
            return new BuiltClient(baseUrl, Map.copyOf(headers));
        }
    }

    @FunctionalInterface
    interface ClientCustomizer {
        void customize(ClientBuilder builder);
    }

    public static void main(String[] args) {
        List<ClientCustomizer> customizers = List.of(
                builder -> builder.defaultHeader(
                        "X-Application", "catalog-service"),
                builder -> builder.defaultHeader(
                        "X-Request-Mode", "safe")
        );

        ClientBuilder builder = new ClientBuilder()
                .baseUrl("https://api.example.test");

        customizers.forEach(customizer -> customizer.customize(builder));

        BuiltClient client = builder.build();

        System.out.println(client.baseUrl());
        System.out.println(client.headers().get("X-Application"));
        System.out.println(client.headers().get("X-Request-Mode"));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac CustomizerDemo.java
java CustomizerDemo
~~~

Stdout chính xác:

~~~text
https://api.example.test
catalog-service
safe
~~~

Hai customizer bổ sung hai header trên cùng builder. Không cần tạo một client mới cho mỗi thay đổi và không cần viết lại cấu hình base URL.

Trong Spring Boot, `ObjectProvider.orderedStream()` thực hiện bước thu thập/sắp xếp các callback từ ApplicationContext. Ý tưởng callback và builder trong chương trình Java thuần vẫn giữ nguyên.

## 20. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Customizer bean có trong context nhưng không có tác dụng | Factory không thu thập hoặc không gọi customizer | Kiểm tra auto-configuration và method tạo bean |
| Default bean biến mất sau khi thêm customizer | Customizer bị khai báo nhầm cùng type với bean đích hoặc condition sai | Dùng interface customizer riêng, giữ `@ConditionalOnMissingBean` trên bean đích |
| Customizer không chạy với bean do ứng dụng tự tạo | Factory mặc định đã back off | Tự áp dụng customizer trong factory của ứng dụng hoặc dùng builder/factory được chia sẻ |
| Chỉ một trong nhiều customizer được áp dụng | Code chỉ inject một callback thay vì collection/provider | Dùng `ObjectProvider.orderedStream()` hoặc collection injection |
| Kết quả thay đổi khi thêm customizer khác | Nhiều callback sửa cùng một thuộc tính | Quy định `@Order`, tách trách nhiệm hoặc bỏ xung đột |
| Header/interceptor xuất hiện nhiều lần | Callback được áp dụng lặp hoặc builder được tái sử dụng | Tạo builder riêng cho mỗi instance và kiểm tra nơi gọi callback |
| Client này nhận base URL của client khác | Dùng chung builder stateful | Clone builder trước khi tùy chỉnh riêng |
| Customizer chạy nhưng bean cuối không đổi | Callback được gọi sau khi đã build hoặc sửa nhầm builder | Áp dụng callback trước `build()` |
| Dùng `RestClient.create()` nhưng thiếu header chung | Bỏ qua builder auto-configure của Boot | Inject `RestClient.Builder` và build client từ builder |
| ObjectMapper mất cấu hình Boot | Đã khai báo ObjectMapper/builder thay thế toàn bộ | Dùng `Jackson2ObjectMapperBuilderCustomizer` nếu chỉ cần điều chỉnh |
| Order không như mong muốn | Chưa khai báo `Ordered`/`@Order` hoặc hai callback xung đột | Gán order rõ và kiểm thử thứ tự |
| Context không khởi động khi customizer cần bean đích | Customizer inject client cuối cùng trong lúc factory đang tạo client | Customizer chỉ nên nhận builder hoặc target chưa hoàn tất, tránh phụ thuộc ngược |

## 21. Checklist trước khi phát hành customizer API

1. Xác định chính xác bean hoặc builder nào được phép tùy chỉnh.
2. Kiểm tra subsystem đã có customizer interface do Spring Boot cung cấp chưa.
3. Định nghĩa interface riêng có tên phản ánh đúng target.
4. Công khai interface trong module mà consumer có thể dependency.
5. Áp dụng property và defaults trước khi gọi customizer.
6. Thu thập tất cả callback, không chỉ một bean.
7. Hỗ trợ thứ tự bằng `Ordered`/`@Order` nếu thứ tự có ý nghĩa.
8. Gọi callback trước khi tạo instance cuối cùng.
9. Giữ `@ConditionalOnMissingBean` trên bean mặc định để user có thể override khi thực sự cần.
10. Kiểm tra customizer có làm mất defaults, observation, metrics hoặc message converters không.
11. Test không có customizer, một customizer, nhiều customizer và user bean override.
12. Ghi rõ customizer áp dụng cho builder/instance nào và các đường tạo object nào bỏ qua nó.

## 22. Tự kiểm tra kiến thức

1. Customizer dùng để làm gì? **Cho phép bổ sung hành vi lên builder hoặc object trong quá trình tạo mà vẫn giữ factory/defaults hiện có.**
2. Khi nào nên dùng property? **Khi đó là lựa chọn cấu hình phổ biến, ổn định và cần hỗ trợ chính thức.**
3. Khi nào nên dùng customizer? **Khi cần một extension point nâng cao hoặc callback bổ sung mà không thay toàn bộ bean.**
4. `RestClientCustomizer` nhận đối tượng nào? **`RestClient.Builder`.**
5. `Jackson2ObjectMapperBuilderCustomizer` giữ lợi ích gì? **Có thể điều chỉnh Jackson builder trong khi giữ auto-configuration mặc định của Boot.**
6. `ThreadPoolTaskExecutorCustomizer` nhận builder hay instance? **Nhận `ThreadPoolTaskExecutor` instance.**
7. `ObjectProvider.orderedStream()` giải quyết điều gì? **Thu thập các customizer beans và duyệt theo thứ tự Spring.**
8. `@Order(10)` chạy trước hay sau `@Order(0)`? **Sau; order nhỏ hơn được áp dụng trước.**
9. Customizer có tự động chạy trên bean do ứng dụng tự khai báo không? **Không; factory phải gọi callback.**
10. Vì sao builder stateful cần được clone khi tạo nhiều client? **Để thiết lập riêng của client này không ảnh hưởng client khác.**
11. Vì sao không nên dùng BeanPostProcessor cho mọi customization nhỏ? **Nó can thiệp rộng vào lifecycle và khó nhìn thấy phạm vi tác động hơn callback chuyên biệt.**
12. Khi nào nên thay bean hoàn toàn? **Khi ứng dụng cần implementation hoặc lifecycle khác đáng kể và chấp nhận tự sở hữu cấu hình.**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): module autoconfigure có thể công bố callback interface để ứng dụng tùy chỉnh component được khởi tạo.
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): cách dùng WebClient/RestClient builder, customizer beans, phạm vi áp dụng và builder stateful.
- [Spring Boot 3.3.13 — RestClientCustomizer JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/client/RestClientCustomizer.html): callback dành cho `RestClient.Builder`.
- [Spring Boot 3.3.13 — WebClientCustomizer JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/function/client/WebClientCustomizer.html): callback dành cho `WebClient.Builder`.
- [Spring Boot 3.3.13 — Jackson2ObjectMapperBuilderCustomizer JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jackson/Jackson2ObjectMapperBuilderCustomizer.html): tùy chỉnh Jackson builder và giữ default auto-configuration.
- [Spring Boot 3.3.13 — ThreadPoolTaskExecutorCustomizer JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/task/ThreadPoolTaskExecutorCustomizer.html): callback dành cho `ThreadPoolTaskExecutor`.
- [Spring Boot 3.3.13 — ThreadPoolTaskExecutorBuilder JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/task/ThreadPoolTaskExecutorBuilder.html): builder và các customizer được áp dụng cho executor.
