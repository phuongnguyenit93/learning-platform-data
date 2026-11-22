# Chọn cấp tùy biến: property, customizer, bean hay thay cấu hình

Spring Boot cung cấp nhiều điểm mở rộng để ứng dụng điều chỉnh hành vi mặc định. Khi cần thay đổi một giá trị, bổ sung một bước xử lý hoặc thay hẳn cách tạo thành phần, có thể chọn giữa thuộc tính cấu hình (property), customizer, bean do ứng dụng cung cấp hoặc thay thế toàn bộ cấu hình.

Các cách này có phạm vi tác động khác nhau. Nên bắt đầu từ điểm mở rộng nhỏ nhất đáp ứng yêu cầu. Một thuộc tính thường đủ cho thay đổi về giá trị; customizer phù hợp khi cần bổ sung hành vi vào đối tượng Boot đang xây dựng; bean tùy chỉnh phù hợp khi cần thay implementation; chỉ thay cấu hình khi cần kiểm soát phần lớn quy trình đăng ký và kết nối bean.

## 1. Nhìn vào phạm vi thay đổi trước khi chọn cách tùy biến

Giả sử ứng dụng có một client gọi dịch vụ Catalog. Có thể phát sinh các yêu cầu:

- Đổi endpoint hoặc timeout theo môi trường.
- Thêm header mặc định hoặc interceptor cho các request.
- Dùng một implementation client khác.
- Thay cách tạo client, đăng ký nhiều thành phần phụ thuộc và kiểm soát toàn bộ cấu hình mặc định.

Mỗi yêu cầu nên được giải quyết ở cấp phù hợp:

| Cấp tùy biến | Dùng khi | Ví dụ |
|---|---|---|
| Property | Chỉ thay đổi giá trị đã được hỗ trợ | Endpoint, timeout, bật/tắt tính năng |
| Customizer | Giữ đối tượng và cách tạo mặc định, chỉ bổ sung hoặc điều chỉnh một phần hành vi | Thêm header, converter, interceptor, MVC mapping |
| Bean | Cần thay một thành phần hoặc cung cấp implementation riêng | Thay client mặc định bằng client tùy chỉnh |
| Thay cấu hình | Cần kiểm soát phần lớn hoặc toàn bộ cách đăng ký các bean liên quan | Loại trừ auto-configuration và tự khai báo cấu hình |

Có thể hình dung mức độ tác động tăng dần:

~~~text
Property
   |
   v
Customizer
   |
   v
Custom bean
   |
   v
Replace / exclude configuration
~~~

Đây không phải thứ tự bắt buộc của Spring. Nó là cách suy nghĩ để tránh thay quá nhiều thành phần khi yêu cầu chỉ cần một điều chỉnh nhỏ.

## 2. Cấp 1: dùng property cho thay đổi về giá trị

Thuộc tính cấu hình là lựa chọn đầu tiên khi ứng dụng đã có khả năng điều chỉnh giá trị mà không cần thay đổi cách tạo bean.

Ví dụ, endpoint và timeout của Catalog client thay đổi theo môi trường. Có thể khai báo trong `application.yml`:

~~~yaml
app:
  catalog:
    base-url: https://catalog.example.test
    connect-timeout: 2s
    enabled: true
~~~

Tạo một lớp nhận các thuộc tính:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public class CatalogProperties {

    private URI baseUrl = URI.create("https://catalog.example.test");
    private Duration connectTimeout = Duration.ofSeconds(2);
    private boolean enabled = true;

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Đăng ký lớp thuộc tính bằng `@EnableConfigurationProperties`:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogConfiguration {
}
~~~

Các bean có thể nhận `CatalogProperties` qua dependency injection:

~~~java
@Bean
CatalogClient catalogClient(CatalogProperties properties) {
    return new CatalogClient(
            properties.getBaseUrl(),
            properties.getConnectTimeout()
    );
}
~~~

Khi triển khai, cùng một artifact có thể dùng các giá trị khác nhau theo môi trường. Giá trị có thể đến từ `application.yml`, file cấu hình riêng, biến môi trường hoặc tham số dòng lệnh. Spring Boot hợp nhất các nguồn cấu hình theo quy tắc ưu tiên của Environment.

Ví dụ, biến môi trường tương ứng với `app.catalog.connect-timeout` là:

~~~bash
APP_CATALOG_CONNECTTIMEOUT=5s
~~~

Quy tắc đặt tên biến môi trường của Spring Boot chuyển tên thuộc tính dạng chấm thành chữ hoa và dấu gạch dưới; dấu gạch nối trong tên thuộc tính được loại bỏ. Cần giữ tên biến phù hợp với quy tắc relaxed binding.

### Khi nào property là đủ?

Dùng property khi:

- Hành vi cần điều chỉnh đã được thành phần hiện tại hỗ trợ.
- Sự khác biệt chỉ nằm ở giá trị, chẳng hạn URL, timeout, số lượng retry hoặc giới hạn.
- Không cần thay đổi loại bean hoặc cấu trúc dependency.
- Người vận hành cần thay giá trị theo môi trường mà không sửa code.

Không nên tạo customizer hoặc bean mới chỉ để đổi một giá trị mà Spring Boot đã cung cấp property tương ứng.

Nếu thư viện tự viết có nhiều thuộc tính liên quan, gom chúng bằng `@ConfigurationProperties` giúp cấu trúc cấu hình rõ ràng, có thể validate và dễ kiểm thử. Tránh rải nhiều chuỗi `@Value` ở các service nếu chúng thuộc cùng một nhóm cấu hình.

## 3. Cấp 2: dùng customizer để điều chỉnh đối tượng Boot tạo

Customizer phù hợp khi muốn giữ cách tạo đối tượng mặc định của Spring Boot nhưng cần bổ sung một vài hành vi. Thay vì tự tạo lại toàn bộ bean, ứng dụng cung cấp một callback để điều chỉnh đối tượng trong quá trình cấu hình.

Một số extension point thường gặp:

- `WebMvcConfigurer`: bổ sung cấu hình cho Spring MVC.
- `Jackson2ObjectMapperBuilderCustomizer`: điều chỉnh Jackson builder mà Boot sử dụng.
- `RestTemplateCustomizer`: tùy chỉnh `RestTemplate` được tạo qua builder của Boot.
- `WebClientCustomizer`: tùy chỉnh `WebClient.Builder` được Boot cấu hình.

Các interface này có hợp đồng riêng. Hãy xem thành phần nào gọi customizer và vào thời điểm nào trước khi giả định mọi instance đều nhận thay đổi.

### Ví dụ: tùy chỉnh Jackson mà vẫn giữ cấu hình mặc định

Nếu muốn Jackson bỏ qua các thuộc tính có giá trị null khi serialize, có thể cung cấp `Jackson2ObjectMapperBuilderCustomizer`:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class JacksonCustomization {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer omitNullProperties() {
        return builder -> builder.serializationInclusion(
                JsonInclude.Include.NON_NULL
        );
    }
}
~~~

Spring Boot áp dụng customizer lên builder được dùng để xây dựng `ObjectMapper` tự động cấu hình. Các thiết lập mặc định khác của Boot vẫn được giữ và kết hợp với thay đổi này.

Đây là cách phù hợp khi chỉ cần điều chỉnh một phần cấu hình Jackson. Nếu tự khai báo một `ObjectMapper` mới, auto-configuration mặc định có thể lùi lại và ứng dụng phải tự chịu trách nhiệm với toàn bộ các thiết lập cần thiết.

### Ví dụ: bổ sung cấu hình MVC bằng WebMvcConfigurer

Nếu cần thêm CORS mapping cho một nhóm API, có thể triển khai `WebMvcConfigurer`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiMvcCustomization implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedMethods("GET", "POST")
                .allowedOrigins("https://portal.example.test");
    }
}
~~~

Spring Boot phát hiện cấu hình MVC bổ sung và kết hợp các callback của `WebMvcConfigurer` với MVC auto-configuration. Cách này giữ cấu hình MVC mặc định của Boot, đồng thời bổ sung mapping cần thiết.

Nếu chỉ muốn mở rộng MVC, không nên thêm `@EnableWebMvc` một cách tùy tiện. Annotation đó chuyển ứng dụng sang chế độ tự kiểm soát cấu hình MVC và làm cho MVC auto-configuration của Boot lùi lại. Chỉ dùng khi thực sự muốn tự chịu trách nhiệm cấu hình MVC ở phạm vi rộng hơn.

### Customizer có thể được áp dụng nhiều lần

Một số extension point có thể được nhiều bean customizer cùng triển khai. Khi đó, thứ tự và cách kết hợp tùy thuộc vào API cụ thể. Một số customizer hỗ trợ `Ordered` hoặc `@Order`; không nên giả định mọi interface đều có cùng quy tắc.

Nếu customizer được áp dụng cho builder dùng chung hoặc nhiều instance được tạo từ builder đó, thay đổi có thể ảnh hưởng đến nhiều đối tượng. Hãy xác định rõ phạm vi đối tượng nhận callback trước khi thêm hành vi có trạng thái.

## 4. Cấp 3: cung cấp bean tùy chỉnh để thay implementation

Nếu property và customizer không đủ vì cần thay chính implementation, ứng dụng có thể cung cấp bean của mình.

Spring Boot auto-configuration thường dùng `@ConditionalOnMissingBean` để chỉ đăng ký bean mặc định khi chưa có bean phù hợp. Ví dụ:

~~~java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogProperties properties) {
        return new DefaultCatalogClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout()
        );
    }
}
~~~

Ứng dụng có thể cung cấp implementation riêng:

~~~java
@Configuration(proxyBeanMethods = false)
public class CustomCatalogConfiguration {

    @Bean
    CatalogClient catalogClient(CatalogProperties properties) {
        return new ResilientCatalogClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout()
        );
    }
}
~~~

Khi bean tùy chỉnh được đăng ký, điều kiện `@ConditionalOnMissingBean(CatalogClient.class)` của auto-configuration không còn khớp. Bean mặc định được bỏ qua và các thành phần phụ thuộc vào `CatalogClient` nhận implementation do ứng dụng cung cấp.

Cách này phù hợp khi ứng dụng cần thay một thành phần, còn những phần khác của auto-configuration vẫn hữu ích.

### Phân biệt thay bean với @Primary và @Qualifier

Không phải mọi cấu hình đều dùng `@ConditionalOnMissingBean`. Nếu hai bean cùng tồn tại, Spring có thể cần quy tắc chọn candidate khi inject:

- `@Primary` đánh dấu bean ưu tiên khi inject theo kiểu và có nhiều candidate phù hợp.
- `@Qualifier` chỉ định rõ candidate theo qualifier.
- `@ConditionalOnMissingBean` quyết định bean mặc định có được đăng ký hay không.

Ví dụ, `@Primary` không làm bean còn lại biến mất:

~~~java
@Bean
@Primary
CatalogClient primaryCatalogClient() {
    return new ResilientCatalogClient();
}

@Bean
CatalogClient fallbackCatalogClient() {
    return new DefaultCatalogClient();
}
~~~

Cả hai bean vẫn tồn tại trong context. Khi một service inject `CatalogClient` mà không có qualifier, bean primary được ưu tiên. Nếu mục tiêu là chỉ có một implementation được đăng ký theo cấu hình, hãy dùng điều kiện hoặc quy tắc cấu hình phù hợp thay vì coi `@Primary` là cơ chế thay thế bean.

### Khi nào nên thay một bean?

Cung cấp bean tùy chỉnh khi:

- Cần thay implementation mặc định.
- Cần kiểm soát cách tạo một thành phần cụ thể.
- Các bean và cấu hình còn lại của auto-configuration vẫn phù hợp.
- Auto-configuration có hỗ trợ back-off bằng `@ConditionalOnMissingBean`, hoặc có một điểm mở rộng bean rõ ràng.

Trước khi thêm bean, cần xem điều kiện của auto-configuration. Nếu bean mặc định không có điều kiện back-off và vẫn được đăng ký, ứng dụng có thể gặp xung đột tên bean hoặc nhiều candidate cùng kiểu.

## 5. Cấp 4: thay hoặc loại trừ cấu hình

Đôi khi yêu cầu thay đổi rộng hơn một bean. Ví dụ, ứng dụng cần tự tổ chức nhiều bean liên quan, dùng một thư viện khác hoặc thay cách tích hợp mà auto-configuration mặc định không hỗ trợ.

Khi đó, có thể loại trừ auto-configuration và khai báo cấu hình thay thế.

~~~java
@SpringBootApplication(
        exclude = CatalogAutoConfiguration.class
)
public class Application {
}
~~~

Hoặc loại trừ bằng tên lớp:

~~~java
@SpringBootApplication(
        excludeName = "com.example.catalog.autoconfigure.CatalogAutoConfiguration"
)
public class Application {
}
~~~

Cũng có thể dùng thuộc tính cấu hình:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.example.catalog.autoconfigure.CatalogAutoConfiguration
~~~

Sau khi loại trừ, ứng dụng phải tự khai báo các bean cần thiết:

~~~java
@Configuration(proxyBeanMethods = false)
public class ApplicationCatalogConfiguration {

    @Bean
    CatalogClient catalogClient(CatalogProperties properties) {
        return new ResilientCatalogClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout()
        );
    }

    @Bean
    CatalogService catalogService(CatalogClient client) {
        return new CatalogService(client);
    }
}
~~~

Loại trừ một auto-configuration sẽ ngăn lớp đó tham gia cơ chế auto-configuration. Nếu lớp đó cung cấp nhiều bean, ứng dụng cần xác định bean nào vẫn cần và khai báo lại những phần cần thiết. Không nên loại trừ toàn bộ cấu hình chỉ để thay một bean nếu điều kiện back-off đã giải quyết được yêu cầu.

### Trường hợp muốn kiểm soát toàn bộ một framework

Một số framework cung cấp annotation bật cấu hình thủ công. Ví dụ, `@EnableWebMvc` cho phép ứng dụng tự kiểm soát MVC và khiến MVC auto-configuration của Spring Boot lùi lại. Đây là thay đổi phạm vi lớn: ứng dụng có thể phải tự khai báo các thành phần mà Boot vốn cung cấp như resource handling, message converters và các thiết lập MVC khác.

Vì vậy, nếu chỉ cần thêm interceptor, formatter hoặc CORS mapping, hãy ưu tiên các extension point như `WebMvcConfigurer`. Chỉ bật cấu hình thủ công khi thật sự cần kiểm soát toàn bộ cách tích hợp.

## 6. Chọn cấp nào trong các tình huống thường gặp?

| Yêu cầu | Cấp nên chọn | Lý do |
|---|---|---|
| Đổi URL API giữa local và production | Property | Chỉ thay giá trị |
| Thay timeout đã được thư viện hỗ trợ | Property | Không cần tạo bean mới |
| Thêm header mặc định cho HTTP client builder | Customizer | Giữ builder và cấu hình Boot |
| Thêm CORS mapping trong Spring MVC | Customizer / WebMvcConfigurer | Bổ sung một phần MVC |
| Điều chỉnh quy tắc serialize Jackson | Jackson customizer | Giữ ObjectMapper auto-configured |
| Dùng client implementation riêng | Custom bean | Thay đúng thành phần cần thay |
| Cần nhiều bean liên quan được tạo theo quy tắc riêng | Thay cấu hình | Cần kiểm soát cấu trúc đăng ký |
| Muốn bỏ toàn bộ tích hợp mặc định của một thư viện | Exclude auto-configuration | Tự chịu trách nhiệm cấu hình thay thế |
| Muốn tự kiểm soát toàn bộ MVC | Cấu hình MVC thủ công | Thay phạm vi auto-configuration |

Hãy xét một ví dụ xuyên suốt: ứng dụng cần gọi Catalog API.

- Nếu chỉ đổi endpoint và timeout, cấu hình `app.catalog.*`.
- Nếu cần thêm header trace cho các request, dùng customizer phù hợp với HTTP client đang sử dụng.
- Nếu cần dùng client có cơ chế retry riêng, cung cấp bean `CatalogClient` để auto-configuration mặc định back off.
- Nếu cần thay cả cách tổ chức client, cache, health indicator và các bean liên quan, cân nhắc loại trừ auto-configuration rồi khai báo cấu hình riêng.

## 7. Những lỗi thường gặp khi tùy biến

### Tạo bean mới chỉ để đổi một property

Việc tự tạo bean có thể khiến auto-configuration lùi lại hoặc làm mất các thiết lập mặc định khác. Nếu thư viện đã hỗ trợ property, hãy dùng property trước.

### Tự tạo lại đối tượng trong khi chỉ cần customizer

Một customizer thường cho phép điều chỉnh builder hoặc đối tượng được Boot chuẩn bị sẵn. Tự tạo đối tượng mới có thể bỏ qua converter, codec, message source, metrics hoặc các thiết lập mặc định khác.

### Nghĩ rằng @Primary thay thế bean mặc định

`@Primary` chỉ ảnh hưởng đến lựa chọn candidate khi inject. Nó không ngăn bean mặc định được đăng ký. Muốn auto-configuration lùi lại, cần điểm mở rộng hoặc điều kiện back-off phù hợp.

### Thêm @EnableWebMvc khi chỉ muốn bổ sung MVC

Annotation này chuyển sang cấu hình MVC thủ công và có thể làm mất các thiết lập tự động của Boot. Dùng `WebMvcConfigurer` cho những thay đổi mang tính bổ sung.

### Loại trừ quá nhiều auto-configuration

Một auto-configuration có thể cung cấp nhiều bean. Loại trừ toàn bộ lớp để thay một bean nhỏ sẽ khiến ứng dụng phải tự khai báo lại nhiều thành phần. Trước tiên hãy xem xét bean nào có thể thay riêng lẻ.

### Không kiểm tra thứ tự cấu hình và điều kiện back-off

Điều kiện `@ConditionalOnMissingBean` được đánh giá dựa trên những bean definition đã được xử lý tại thời điểm đó. Auto-configuration của Boot được tổ chức để cho phép cấu hình ứng dụng và các cấu hình ưu tiên phù hợp được xét trước. Với auto-configuration tự viết, cần khai báo thứ tự và điều kiện đúng, đồng thời kiểm thử khi ứng dụng có bean tùy chỉnh.

## 8. Kiểm tra kết quả sau khi tùy biến

Sau khi thay đổi cấp tùy biến, cần xác nhận cả bean được tạo và hành vi cuối cùng.

Có thể kiểm tra theo các trường hợp:

1. Không khai báo property: giá trị mặc định có được dùng đúng không?
2. Ghi đè property: bean có nhận giá trị mới không?
3. Có customizer: đối tượng được Boot tạo có nhận điều chỉnh không?
4. Ứng dụng cung cấp bean riêng: bean mặc định có back off không?
5. Loại trừ auto-configuration: các bean thay thế đã được khai báo đầy đủ chưa?
6. Chạy trong profile hoặc loại ứng dụng khác: điều kiện có tạo đúng tập bean không?

Với auto-configuration, có thể dùng `ApplicationContextRunner` để kiểm tra cấu hình trong một context nhỏ. Kiểm tra bean theo kiểu, tên và thuộc tính; sau đó kiểm tra hành vi của bean nếu thay đổi ảnh hưởng tới runtime.

Nếu dùng Actuator, endpoint `conditions` có thể giúp giải thích vì sao một auto-configuration được áp dụng hoặc bị bỏ qua. Endpoint này cần được cấu hình và bảo vệ phù hợp với môi trường vận hành.

## 9. Quy trình quyết định cấp tùy biến

Khi nhận một yêu cầu thay đổi hành vi Spring Boot, có thể đi theo các bước:

1. Xác định chính xác hành vi hoặc giá trị cần thay đổi.
2. Kiểm tra property hiện có của Spring Boot hoặc thư viện đã đáp ứng yêu cầu chưa.
3. Nếu cần bổ sung hành vi lên builder hoặc đối tượng Boot tạo, tìm customizer extension point tương ứng.
4. Nếu cần thay implementation, kiểm tra auto-configuration có hỗ trợ `@ConditionalOnMissingBean` hoặc điểm mở rộng bean không.
5. Chỉ loại trừ hoặc thay toàn bộ cấu hình khi các cấp nhỏ hơn không đáp ứng yêu cầu.
6. Kiểm tra tác động tới những bean khác do auto-configuration cung cấp.
7. Kiểm thử trường hợp mặc định, trường hợp tùy biến và trường hợp tắt hoặc thay thế cấu hình.

Mỗi cấp tùy biến giải quyết một phạm vi khác nhau. Property điều chỉnh dữ liệu cấu hình; customizer bổ sung hành vi cho đối tượng được tạo; bean cho phép thay một thành phần; thay cấu hình trao quyền kiểm soát rộng hơn cho ứng dụng. Chọn đúng cấp giúp giữ lại các thiết lập mặc định hữu ích của Spring Boot, giảm số thành phần phải tự quản lý và làm rõ trách nhiệm của cấu hình ứng dụng.

