# Suy luận constructor liên kết khi lớp có một constructor phù hợp trong Spring Boot

## 1. Mục tiêu: tạo đối tượng cấu hình bất biến mà không cần setter

Spring Boot hỗ trợ cơ chế **Externalized Configuration** để đọc thuộc tính từ `application.yml`, `application.properties`, biến môi trường, Java system properties, đối số dòng lệnh và những nguồn khác. Khi một nhóm thuộc tính cùng chia sẻ tiền tố, ta thường ánh xạ chúng vào một kiểu Java được đánh dấu bằng `@ConfigurationProperties`.

Có hai hướng binding quen thuộc:

- **JavaBean binding**: Spring tạo đối tượng rồi gọi setter để điền thuộc tính.
- **Constructor binding**: Spring đọc và chuyển đổi giá trị cấu hình, sau đó truyền chúng vào constructor để tạo đối tượng hoàn chỉnh.

Ví dụ JavaBean binding:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private String baseUrl;
    private int maxRetries;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Cách này hoạt động với thuộc tính có thể thay đổi, nhưng đối tượng có setter public nên có thể bị sửa sau khi tạo.

Với constructor binding, ta có thể dùng `final` và không cung cấp setter:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final int maxRetries;

    public ClientProperties(String baseUrl, int maxRetries) {
        this.baseUrl = baseUrl;
        this.maxRetries = maxRetries;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

Trong **Spring Boot 3.x**, khi kiểu `@ConfigurationProperties` được đăng ký bằng cơ chế hỗ trợ constructor binding và **có đúng một constructor có tham số phù hợp**, Spring Boot có thể **suy luận constructor đó là constructor dùng để bind cấu hình**, không cần đặt `@ConstructorBinding`.

Đây là trọng tâm của bài: **khi nào constructor được suy luận, khi nào cần chỉ định tường minh, và tại sao việc đăng ký bean ảnh hưởng đến cơ chế binding**.

## 2. “Suy luận constructor liên kết” thực chất có nghĩa gì?

Giả sử file `application.yml` chứa:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    max-retries: 4
~~~

Các thuộc tính phẳng tương ứng:

~~~properties
app.client.base-url=https://api.example.org
app.client.max-retries=4
~~~

Với class `ClientProperties` phía trên, Spring Boot có thể thực hiện theo ý tưởng:

~~~text
app.client.base-url
          │
          └────► tham số constructor baseUrl (String)

app.client.max-retries
          │
          └────► tham số constructor maxRetries (int)

                   ▼
     new ClientProperties(
         "https://api.example.org",
         4
     )
                   ▼
        Bean ClientProperties
~~~

Spring Boot không cần setter để điền dữ liệu sau khi object đã được tạo. Nó lấy tên tham số constructor, tìm các khóa cấu hình tương ứng dưới tiền tố `app.client`, chuyển giá trị sang kiểu đích, rồi gọi constructor.

Cần phân biệt:

1. **Constructor injection** của Spring container: truyền các **bean phụ thuộc** vào constructor, ví dụ `DataSource` hoặc `PaymentService`.
2. **Constructor binding** của `@ConfigurationProperties`: truyền các **giá trị thuộc tính cấu hình** vào constructor, ví dụ `String baseUrl`, `int maxRetries` hoặc `Duration timeout`.

Cả hai đều sử dụng constructor Java, nhưng **nguồn tham số và quy trình khởi tạo khác nhau**. Không nên nhầm việc có một constructor với việc Spring sẽ tự tìm bean `String` hoặc bean `int` để tiêm vào một cấu hình bất biến.

## 3. Điều kiện suy luận khi chỉ có một constructor có tham số

Với cơ chế Spring Boot 3.x, trường hợp phổ biến nhất là:

~~~java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    private final String baseUrl;
    private final int maxRetries;

    public ClientProperties(String baseUrl, int maxRetries) {
        this.baseUrl = baseUrl;
        this.maxRetries = maxRetries;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

Nếu đây là **constructor duy nhất của class**, có tham số và không bị đánh dấu để sử dụng theo cơ chế injection khác, Spring Boot có thể chọn nó cho constructor binding. **Không cần** viết:

~~~java
@ConstructorBinding
public ClientProperties(String baseUrl, int maxRetries) { ... }
~~~

Những điều kiện đi kèm cần nhớ:

- Kiểu phải được khai báo là `@ConfigurationProperties` với tiền tố phù hợp.
- Bean phải được đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, không phải chỉ dựa vào một `@Component` thông thường nếu muốn constructor binding.
- Tên tham số constructor cần được Spring Boot nhận biết để ánh xạ tên thuộc tính.
- Các giá trị phải có thể được chuyển sang kiểu tham số tương ứng.
- Nếu có **nhiều constructor**, quy tắc “chỉ có một nên tự chọn” không còn đủ; có thể cần `@ConstructorBinding` để chỉ rõ constructor được dùng.
- Nếu constructor được đánh dấu `@Autowired`, đó là dấu hiệu dùng constructor theo cơ chế dependency injection thay vì suy luận nó làm constructor binding.

Phát biểu chính xác là: **Spring Boot suy luận một constructor có tham số thích hợp trong ngữ cảnh tạo bean `@ConfigurationProperties` hỗ trợ constructor binding**. Không phải mọi class Java có một constructor đều tự động trở thành đối tượng cấu hình.

## 4. Đăng ký bean đúng cách: `@ConfigurationPropertiesScan`

Chỉ gắn annotation trên một class chưa nhất thiết làm class đó trở thành Spring bean. Với constructor binding, cách đăng ký trực tiếp là quét các kiểu `@ConfigurationProperties`.

Cấu trúc dự án ví dụ:

~~~text
src/main/java/com/example/catalog/
  CatalogApplication.java
  config/
    ClientProperties.java
  service/
    CatalogClient.java

src/main/resources/
  application.yml
~~~

File `ClientProperties.java`:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final Duration timeout;
    private final int maxRetries;

    public ClientProperties(
            String baseUrl,
            Duration timeout,
            int maxRetries) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
        this.maxRetries = maxRetries;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

File `application.yml`:

~~~yaml
app:
  client:
    base-url: "https://catalog.example.org"
    timeout: 5s
    max-retries: 3
~~~

Class ứng dụng:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Spring Boot tìm các class `@ConfigurationProperties` trong phạm vi quét, đăng ký chúng và dùng Binder để tạo giá trị cho constructor.

Một service dùng bean:

~~~java
package com.example.catalog.service;

import com.example.catalog.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogClient {
    private final ClientProperties properties;

    public CatalogClient(ClientProperties properties) {
        this.properties = properties;
    }

    public String endpointDescription() {
        return properties.getBaseUrl()
                + " (timeout=" + properties.getTimeout() + ")";
    }
}
~~~

Ở `CatalogClient`, Spring thực hiện **constructor injection của bean** `ClientProperties` đã được tạo trước đó. Bên trong quá trình tạo `ClientProperties`, Binder thực hiện **constructor binding từ giá trị cấu hình**.

Hai cơ chế nối tiếp nhau nhưng không được đánh đồng.

## 5. Cách đăng ký thay thế: `@EnableConfigurationProperties`

Nếu không muốn quét cả package hoặc muốn chọn tường minh class cần đăng ký, có thể dùng:

~~~java
import com.example.catalog.config.ClientProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {
}
~~~

Hoặc đặt trực tiếp ở class ứng dụng:

~~~java
@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Đối với class `ClientProperties` có một constructor có tham số, cách đăng ký này vẫn phù hợp cho constructor binding.

So sánh:

| Cách đăng ký | Đặc điểm |
| --- | --- |
| `@ConfigurationPropertiesScan` | Tìm và đăng ký các kiểu `@ConfigurationProperties` trong package được quét |
| `@EnableConfigurationProperties(MyProperties.class)` | Đăng ký tường minh kiểu cấu hình được chỉ định |
| `@Component` trên class cấu hình | Đăng ký bean thông thường; **không phù hợp cho constructor binding bất biến** nếu dựa vào constructor nhận giá trị cấu hình |
| `@Bean` trả về đối tượng cấu hình | Một bean do factory method tạo; thường dùng cơ chế JavaBean binding sau khi tạo, không phải constructor binding do Binder trực tiếp lựa chọn |

Nếu class đã có `@Component`, đừng mặc định `@ConfigurationPropertiesScan` sẽ tạo thêm một bean riêng cho class đó. Scanner có quy tắc tránh những kiểu đã được đánh dấu như component thông thường. Với thiết kế constructor binding, nên bỏ `@Component` và đăng ký theo một trong hai cách đầu.

## 6. Vì sao `@Component` và constructor binding dễ bị nhầm?

Giả sử viết:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;

    public ClientProperties(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getBaseUrl() {
        return baseUrl;
    }
}
~~~

Đây là một trường hợp dễ gây hiểu lầm. Vì class được đánh dấu `@Component`, Spring có thể tạo bean bằng **cơ chế container thông thường** và coi `String baseUrl` là dependency phải tiêm theo constructor. Nhưng `String` từ file YAML không tự trở thành một bean `String` để constructor injection tìm thấy.

Kết quả có thể là lỗi khởi tạo bean do không có dependency phù hợp hoặc cách tạo bean không đúng ý định.

Cách phù hợp cho constructor binding:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;

    public ClientProperties(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getBaseUrl() {
        return baseUrl;
    }
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(ClientProperties.class)`.

Ngược lại, `@Component` vẫn có thể kết hợp với `@ConfigurationProperties` theo lối **JavaBean binding**, nếu bean có no-args constructor hoặc cơ chế tạo bean hợp lệ và những thuộc tính có setter phù hợp:

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class MutableClientProperties {
    private String baseUrl;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }
}
~~~

Tóm lại, **không phải `@Component` bị cấm với mọi `@ConfigurationProperties`**; vấn đề là constructor binding không được áp dụng cho bean do những cơ chế tạo bean thông thường như `@Component`, `@Bean` hay `@Import` tạo ra.

## 7. Class có một constructor không tham số thì sao?

Một class chỉ có no-args constructor không phải trường hợp “có một constructor có tham số cần suy luận để binding”.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private String baseUrl;
    private int maxRetries;

    public ClientProperties() {
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Spring Boot có thể tạo đối tượng bằng no-args constructor rồi gọi setter. Đây là **JavaBean binding**.

Bảng phân biệt:

| Thiết kế class | Hướng binding thường gặp |
| --- | --- |
| Một constructor có tham số phù hợp, không setter | Constructor binding ngầm định |
| Một no-args constructor với setter | JavaBean binding |
| Nhiều constructor có tham số | Cần chỉ rõ constructor binding bằng `@ConstructorBinding` khi muốn dùng constructor |
| Constructor có `@Autowired` | Được định hướng cho cơ chế dependency injection |
| Record với canonical constructor phù hợp | Constructor binding thường được suy luận |

Không nên suy ra “cứ có đúng một constructor thì Spring Boot sẽ bind qua constructor” mà bỏ qua việc constructor đó có tham số hay không, bean được đăng ký bằng cách nào, và có annotation nào yêu cầu cơ chế khác.

## 8. Khi class có nhiều constructor: cần chọn tường minh

Xét một class bất biến có hai constructor:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final int maxRetries;

    public ClientProperties(String baseUrl, int maxRetries) {
        this.baseUrl = baseUrl;
        this.maxRetries = maxRetries;
    }

    public ClientProperties(String baseUrl) {
        this(baseUrl, 3);
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

Không còn một constructor duy nhất để suy luận. Nếu muốn Binder dùng constructor nhận cả `baseUrl` và `maxRetries`, trong Spring Boot 3.x có thể đánh dấu **chính constructor đó**:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final int maxRetries;

    @ConstructorBinding
    public ClientProperties(String baseUrl, int maxRetries) {
        this.baseUrl = baseUrl;
        this.maxRetries = maxRetries;
    }

    public ClientProperties(String baseUrl) {
        this(baseUrl, 3);
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

Ở đây `@ConstructorBinding` không dùng để “bật” khả năng binding trên mọi constructor. Nó **chỉ định constructor nào** được Binder sử dụng trong tình huống có nhiều lựa chọn.

**Lưu ý theo phiên bản:** Trong Spring Boot 3.x, annotation `@ConstructorBinding` nằm ở package `org.springframework.boot.context.properties.bind` và được dùng trên **constructor**. Khi đọc ví dụ Spring Boot 2.x, bạn có thể thấy cú pháp hoặc package khác, thậm chí annotation đặt ở **class**. Không copy nguyên import/annotation từ phiên bản cũ vào dự án mới mà không đối chiếu API của phiên bản đang dùng.

Nếu class chỉ có một constructor có tham số phù hợp, việc thêm `@ConstructorBinding` thường không cần thiết trong Spring Boot 3.x.

## 9. Một constructor có `@Autowired`: đó là ý định khác

Annotation `@Autowired` nói với Spring container rằng constructor cần được dùng để **tiêm dependency**.

Ví dụ bean thông thường:

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

Đây là constructor injection của `OrderRepository`, không phải constructor binding các thuộc tính YAML.

Nếu một class có một constructor được đánh dấu `@Autowired`, Spring Boot không nên suy luận constructor đó làm constructor binding cho `@ConfigurationProperties` theo quy tắc một constructor có tham số.

Một trường hợp dễ tạo nhầm lẫn:

~~~java
@ConfigurationProperties(prefix = "app.service")
public class ServiceProperties {
    private final SomeDependency dependency;

    @Autowired
    public ServiceProperties(SomeDependency dependency) {
        this.dependency = dependency;
    }
}
~~~

Ví dụ này không mô tả một đối tượng cấu hình đơn thuần. Nó trộn một dependency là bean vào class giá trị cấu hình.

Thực hành rõ ràng hơn là:

- Để `@ConfigurationProperties` chỉ giữ **dữ liệu cấu hình**.
- Để `@Service`/`@Component` giữ **logic và dependency**.
- Inject bean cấu hình vào service qua constructor thông thường.

Ví dụ:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;
    private final ClientProperties properties;

    public OrderService(
            OrderRepository repository,
            ClientProperties properties) {
        this.repository = repository;
        this.properties = properties;
    }
}
~~~

Việc tách hai trách nhiệm giúp Spring biết tham số nào đến từ Binder và tham số nào đến từ BeanFactory.

## 10. Record Java: trường hợp constructor binding tự nhiên

Từ Java 16, `record` cung cấp cú pháp gọn để mô tả đối tượng dữ liệu bất biến ở mức tham chiếu field.

Cùng cấu hình:

~~~yaml
app:
  client:
    base-url: "https://catalog.example.org"
    timeout: 5s
    max-retries: 3
~~~

Có thể khai báo:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Duration timeout,
        int maxRetries
) {}
~~~

Record có canonical constructor tương ứng với các component. Với record chỉ có constructor cần thiết, Spring Boot có thể dùng **constructor binding ngầm định** mà không cần `@ConstructorBinding`.

Điểm khác so với Java class thông thường:

- Constructor và các accessor được tạo theo cấu trúc record.
- Không cần viết ba field `private final` thủ công.
- Không cần viết getter kiểu JavaBean; accessor của record là `baseUrl()`, `timeout()`, `maxRetries()`.
- Java record cung cấp `equals`, `hashCode` và `toString` dựa trên component.
- Binder ánh xạ theo tên component/constructor parameter thay vì yêu cầu setter.

Bean sử dụng record:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ClientService {
    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public int configuredRetries() {
        return properties.maxRetries();
    }
}
~~~

Dạng record này thích hợp khi mục tiêu là **đọc dữ liệu cấu hình và giữ nó ổn định trong object**.

Cần nhớ rằng bất biến của record là **shallow immutability**. Nếu component là một `List` hoặc `Map` có thể sửa, record không tự biến collection đó thành collection bất biến sâu. Khi cần bảo đảm tuyệt đối không ai thay đổi collection, có thể sao chép phòng vệ trong canonical/compact constructor.

## 11. Record có constructor bổ sung thì sao?

Record Java có thể khai báo thêm constructor bên cạnh canonical constructor. Ví dụ:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {

    public ClientProperties(String baseUrl) {
        this(baseUrl, Duration.ofSeconds(5));
    }
}
~~~

Lúc này có nhiều constructor. Nếu phiên bản Spring Boot cần được hướng dẫn rõ ràng để chọn constructor liên kết, có thể khai báo canonical constructor tường minh và đánh dấu `@ConstructorBinding`:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {

    @ConstructorBinding
    public ClientProperties(String baseUrl, Duration timeout) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    public ClientProperties(String baseUrl) {
        this(baseUrl, Duration.ofSeconds(5));
    }
}
~~~

Việc khai báo canonical constructor tường minh cho phép gắn annotation đúng nơi mà Binder lựa chọn. Trong những trường hợp không cần overload, cách dễ hiểu nhất vẫn là giữ **một canonical constructor** và dùng `@DefaultValue` để mô tả mặc định tại điểm binding.

Đừng thêm một constructor phụ chỉ để cung cấp default nếu mục đích đơn thuần là lấy giá trị mặc định cho một tham số cấu hình.

## 12. Default với constructor binding: `@DefaultValue`

Khi bind qua constructor, các trường trong object bất biến thường không có setter và được gán đúng một lần. Spring Boot có thể sử dụng `@DefaultValue` trên tham số để đưa giá trị dự phòng khi không có thuộc tính tương ứng.

Ví dụ:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("3") int maxRetries,
        @DefaultValue("false") boolean debugEnabled
) {}
~~~

YAML chỉ cần khai báo URL:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
~~~

Khi binding thành công:

~~~text
baseUrl       → https://api.example.org
timeout       → PT5S (Duration = 5 giây)
maxRetries    → 3
debugEnabled  → false
~~~

Cần phân biệt `@DefaultValue` với property placeholder:

~~~yaml
app:
  client:
    timeout: "${CLIENT_TIMEOUT:5s}"
~~~

Cách dùng placeholder mô tả **giá trị fallback khi giải quyết một tham chiếu cấu hình** trong file; `@DefaultValue("5s")` mô tả **giá trị fallback cho constructor parameter khi binding**. Hai cách có thể phục vụ nhu cầu tương tự nhưng nằm ở hai tầng khác nhau.

Khi có giá trị không hợp lệ, chẳng hạn `timeout=bad-duration`, default `5s` không phải cơ chế sửa lỗi dữ liệu. Binder có thể thất bại khi chuyển kiểu.

## 13. Constructor binding với đối tượng lồng nhau

Một class cấu hình có thể chứa nhiều nhóm con. Ví dụ:

~~~yaml
shop:
  name: "Demo Shop"
  checkout:
    timeout: 8s
    retries: 2
  shipping:
    provider: fast
    tracking-enabled: true
~~~

Có thể mô tả bằng record lồng nhau:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop")
public record ShopProperties(
        String name,
        Checkout checkout,
        Shipping shipping
) {
    public record Checkout(Duration timeout, int retries) {}

    public record Shipping(
            String provider,
            boolean trackingEnabled
    ) {}
}
~~~

Spring Boot có thể bind:

~~~text
shop.name                     → ShopProperties.name()
shop.checkout.timeout         → ShopProperties.checkout().timeout()
shop.checkout.retries         → ShopProperties.checkout().retries()
shop.shipping.provider        → ShopProperties.shipping().provider()
shop.shipping.tracking-enabled → ShopProperties.shipping().trackingEnabled()
~~~

Mỗi record lồng nhau có canonical constructor để nhận dữ liệu. Không cần setter để điền các giá trị vào object đã tồn tại.

Nếu nhóm `shipping` hoàn toàn không có thuộc tính nào, tùy khai báo và cách binding, giá trị `shipping` có thể là `null` thay vì một object được tạo với các giá trị rỗng/mặc định. Nếu ứng dụng bắt buộc luôn có object nhóm con, có thể dùng empty `@DefaultValue` trên tham số nhóm con và default phù hợp cho các component bên trong:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "shop")
public record ShopProperties(
        String name,
        @DefaultValue Checkout checkout
) {
    public record Checkout(
            @DefaultValue("8s") Duration timeout,
            @DefaultValue("2") int retries
    ) {}
}
~~~

Empty `@DefaultValue` trên nhóm con giúp Binder tạo nested object ngay cả khi không có thuộc tính nào thuộc nhóm đó, miễn là các tham số bên trong có thể bind hoặc có giá trị thích hợp.

Không nên giả định mọi nested object tự khác `null` chỉ vì kiểu của tham số được khai báo.

## 14. Constructor binding với List và Map

Dữ liệu cấu hình thường chứa danh sách hoặc bảng ánh xạ:

~~~yaml
app:
  clients:
    - name: primary
      url: "https://primary.example.org"
      timeout: 3s
    - name: backup
      url: "https://backup.example.org"
      timeout: 7s
  labels:
    region: asia
    tier: gold
~~~

Kiểu record:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Client> clients,
        Map<String, String> labels
) {
    public record Client(
            String name,
            String url,
            Duration timeout
    ) {}
}
~~~

Tên thuộc tính phẳng điển hình:

~~~properties
app.clients[0].name=primary
app.clients[0].url=https://primary.example.org
app.clients[0].timeout=3s
app.clients[1].name=backup
app.clients[1].url=https://backup.example.org
app.clients[1].timeout=7s
app.labels.region=asia
app.labels.tier=gold
~~~

Ở constructor binding, các tham số `List<Client>` và `Map<String, String>` có thể được xây dựng từ các nhóm thuộc tính phù hợp.

Cần phân biệt:

- **Binding collection**: Binder biết cách dựng `List`/`Map` từ cấu trúc tên khóa.
- **Constructor selection**: quyết định constructor nào được gọi để nhận `List`/`Map`.
- **Property source precedence**: quyết định nguồn nào cung cấp giá trị cuối cùng.

Nếu một danh sách bị khai báo lại ở profile hoặc nguồn ưu tiên cao hơn, binder thường **thay thế danh sách** từ nguồn thấp hơn thay vì ghép từng phần tử theo cách trực giác. Đây là vấn đề cấu hình nhiều nguồn, không phải lỗi suy luận constructor.

Với các collection có thể sửa, nếu cần thiết kế bất biến thực sự, cân nhắc sao chép phòng vệ và áp dụng những quy tắc phù hợp trong record/class.

## 15. Chuyển đổi kiểu: constructor parameter là hợp đồng dữ liệu

Spring Boot có cơ chế chuyển đổi những giá trị cấu hình thành kiểu Java phù hợp. Ví dụ:

~~~yaml
app:
  worker:
    threads: 8
    enabled: true
    timeout: 15s
    buffer-size: 4MB
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int threads,
        boolean enabled,
        Duration timeout,
        DataSize bufferSize
) {}
~~~

Các cặp giá trị:

| Thuộc tính | Kiểu constructor parameter | Giá trị |
| --- | --- | --- |
| `threads=8` | `int` | `8` |
| `enabled=true` | `boolean` | `true` |
| `timeout=15s` | `Duration` | 15 giây |
| `buffer-size=4MB` | `DataSize` | 4 megabyte theo cú pháp đơn vị của Spring |

Việc dùng `Duration` hoặc `DataSize` có ý nghĩa hơn lưu `long timeoutMillis` hoặc `String bufferSize` không rõ đơn vị.

Với kiểu primitive như `int` và `boolean`, khi thuộc tính thiếu và không có default, các quy tắc giá trị mặc định của binding/Java có thể dẫn đến `0` hoặc `false`. **Đừng dùng kiểu primitive như một dấu hiệu chắc chắn rằng cấu hình bắt buộc đã được cung cấp**.

Nếu yêu cầu “threads phải có và lớn hơn 0”, nên dùng validation và/hoặc kiểu đích cho phép phát hiện thiếu giá trị, thay vì chỉ dựa vào constructor binding.

## 16. Constructor parameter name phải được giữ hoặc suy ra được

Binder cần biết tham số `baseUrl` tương ứng với thuộc tính `base-url`, và `maxRetries` tương ứng `max-retries`. Java compiler không phải lúc nào cũng giữ đầy đủ tên tham số của class thông thường trong bytecode nếu không có cấu hình phù hợp.

Đối với constructor binding trên class Java, nên biên dịch với tùy chọn:

~~~text
-parameters
~~~

Ví dụ cấu hình Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Với dự án sử dụng cơ chế build chuẩn của Spring Boot, nhiều cấu hình liên quan có thể đã được thiết lập sẵn; vẫn cần hiểu mục đích của `-parameters` khi gặp lỗi không tìm được tên constructor parameter.

Trong Gradle, một cách cấu hình chung cho Java:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ["-parameters"]
}
~~~

Đối với Java record, tên record component được mô tả trực tiếp trong metadata của record; tuy vậy dự án vẫn nên dùng compiler/build plugin phù hợp với phiên bản Spring Boot.

**Triệu chứng có thể gặp** khi thiếu thông tin tên tham số: Binder không thể xác định đúng tên thuộc tính để ghép với constructor parameter hoặc báo lỗi liên quan đến parameter-name discovery. Đừng cố sửa bằng cách đặt thêm setter nếu ý định ban đầu là giữ object bất biến; hãy xem lại compiler flags và cách đăng ký.

## 17. Relaxed binding: tên YAML và tên constructor parameter có thể khác cách viết

Spring Boot hỗ trợ relaxed binding giữa tên thuộc tính dạng canonical và tên thuộc tính Java.

Ví dụ:

~~~yaml
app:
  http-client:
    base-url: "https://api.example.org"
    max-connections: 20
    read-timeout: 5s
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.http-client")
public record HttpClientProperties(
        String baseUrl,
        int maxConnections,
        Duration readTimeout
) {}
~~~

Bảng đối chiếu:

| Tên thuộc tính YAML | Tên phẳng | Tên tham số Java |
| --- | --- | --- |
| `base-url` | `app.http-client.base-url` | `baseUrl` |
| `max-connections` | `app.http-client.max-connections` | `maxConnections` |
| `read-timeout` | `app.http-client.read-timeout` | `readTimeout` |

Tiền tố `app.http-client` được khai báo bằng dạng canonical kebab-case. Không cần đổi component Java thành tên có dấu gạch ngang; đó không phải cú pháp định danh hợp lệ trong Java.

Nếu cấp cấu hình qua biến môi trường, theo quy tắc chuyển đổi chuẩn có thể dùng:

~~~text
APP_HTTPCLIENT_BASEURL
APP_HTTPCLIENT_MAXCONNECTIONS
APP_HTTPCLIENT_READTIMEOUT
~~~

Đừng nhầm “Spring Boot tự suy luận constructor” với “Spring Boot tự suy luận mọi tên khóa”. Constructor binding vẫn phụ thuộc vào tên thuộc tính phù hợp và giá trị có thể chuyển sang kiểu tham số.

## 18. Khi nào cần validation?

Một constructor có thể nhận giá trị không hợp lệ về nghiệp vụ dù conversion thành công. Ví dụ:

~~~yaml
app:
  worker:
    threads: -3
    timeout: 0s
~~~

Cả hai giá trị có thể chuyển sang `int` và `Duration`, nhưng không phù hợp để tạo worker pool.

Có thể thêm Bean Validation với `@Validated`:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) int threads,
        @NotNull Duration timeout
) {}
~~~

Ứng dụng cần dependency triển khai Bean Validation, chẳng hạn `spring-boot-starter-validation` theo phiên bản Spring Boot phù hợp.

Lưu ý `@NotNull` chỉ kiểm tra không null; nó **không tự đảm bảo timeout lớn hơn 0**. Nếu cần ràng buộc đó, thêm validation phù hợp hoặc kiểm tra trong constructor/một validator.

Với nested object:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull @Valid Client client
) {
    public record Client(
            @NotBlank String baseUrl
    ) {}
}
~~~

`@Valid` cho phép validation đi vào đối tượng lồng nhau, trong khi `@NotNull` yêu cầu đối tượng đó phải tồn tại. Khi kết hợp, chúng mô tả hợp đồng rõ hơn so với chỉ cần constructor có tham số.

**Constructor binding không đồng nghĩa tự động validate mọi thuộc tính.** Nếu muốn fail fast khi thiếu hoặc sai giá trị, hãy thiết kế validation.

## 19. Về null, Optional và tham số thiếu giá trị

Khi một constructor parameter không tìm được nguồn giá trị, hành vi cụ thể phụ thuộc kiểu đích, annotation default và binder. Với tham số tham chiếu không có default, kết quả có thể là `null`.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        String displayName
) {}
~~~

Nếu chỉ cấu hình `base-url`, không nên giả định `displayName` tự nhận chuỗi rỗng. Khi có nhu cầu default, có thể dùng `@DefaultValue("Client")`. Khi bắt buộc, dùng `@NotBlank` hoặc validation tương đương.

Một cạm bẫy khác là dùng `Optional<String>` trực tiếp trong class `@ConfigurationProperties`. Spring Boot không khuyến nghị kiểu `Optional` làm property cấu hình; khi không có giá trị, Binder có thể dùng `null` thay vì `Optional.empty()` như kỳ vọng.

Thực hành dễ dự đoán hơn:

- Dùng `@DefaultValue` cho giá trị có mặc định rõ ràng.
- Dùng validation cho giá trị bắt buộc.
- Dùng kiểu tham chiếu nullable khi sự vắng mặt thật sự có ý nghĩa, rồi xử lý có chủ đích.
- Đừng phụ thuộc vào kiểu primitive để phân biệt thiếu cấu hình và giá trị 0/false.

## 20. Lombok và constructor sinh tự động

Một class có thể dùng Lombok để sinh constructor, ví dụ `@RequiredArgsConstructor` hoặc `@AllArgsConstructor`. Điều này có thể làm thay đổi số lượng constructor thực sự hiện diện trong bytecode.

Ví dụ:

~~~java
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Getter
@RequiredArgsConstructor
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final int maxRetries;
}
~~~

Về ý tưởng, Lombok sinh một constructor có hai tham số, có thể là constructor duy nhất phù hợp để Binder suy luận. Nhưng cần bảo đảm **tên tham số sinh ra được giữ và được Spring Boot nhận diện**, cũng như annotation processors/build configuration hoạt động chính xác.

Một lỗi thường gặp là sau đó thêm constructor khác hoặc dùng annotation Lombok khác sinh no-args constructor, khiến tình huống từ “một constructor” trở thành “nhiều constructor” mà mã nguồn không nhìn thấy đầy đủ nếu không hiểu Lombok.

Với DTO cấu hình đơn giản, record Java thường dễ quan sát hơn vì danh sách tham số và tên component là một phần cú pháp ngôn ngữ. Với class bình thường, constructor viết tường minh cũng là lựa chọn rõ ràng khi cần logic khởi tạo.

Không nên thêm `@ConstructorBinding` chỉ để chữa lỗi do không có parameter-name metadata hoặc do sai cách đăng ký bean.

## 21. Constructor có thể chứa logic kiểm tra bất biến không?

Có. Một lợi ích của constructor binding là object chỉ được tạo khi các tham số đã đi qua constructor, nên ta có thể kiểm tra điều kiện bất biến.

Ví dụ:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private final int threads;
    private final Duration timeout;

    public WorkerProperties(int threads, Duration timeout) {
        if (threads < 1) {
            throw new IllegalArgumentException(
                    "app.worker.threads must be >= 1");
        }
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.worker.timeout must be positive");
        }
        this.threads = threads;
        this.timeout = timeout;
    }

    public int getThreads() {
        return threads;
    }

    public Duration getTimeout() {
        return timeout;
    }
}
~~~

Nếu cấu hình không hợp lệ, constructor có thể ném exception và ứng dụng thất bại khi tạo bean. Cách này phù hợp khi điều kiện đơn giản và là bất biến bắt buộc của object.

Tuy nhiên:

- Không nên để constructor thực hiện network call hoặc truy vấn database chỉ để bind cấu hình.
- Tránh logic có side effect trong constructor.
- Với nhiều ràng buộc dữ liệu, Bean Validation có thể cho thông báo cấu hình rõ ràng hơn.
- Phần chuyển đổi kiểu thường xảy ra **trước khi constructor được gọi**; nếu chuỗi `timeout` không thể chuyển thành `Duration`, constructor không được gọi.

Record cũng có thể dùng compact constructor để kiểm tra:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int threads, Duration timeout) {

    public WorkerProperties {
        if (threads < 1) {
            throw new IllegalArgumentException("threads must be positive");
        }
        if (timeout == null || timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }
}
~~~

Compact constructor không cần viết lệnh gán cho các record component; Java tự thực hiện việc gán sau phần thân kiểm tra.

## 22. Constructor binding và cấu hình theo profile

Cách Spring Boot **chọn constructor** độc lập với việc giá trị đến từ file chung, file theo profile hay biến môi trường.

Giả sử:

~~~yaml
# application.yml
app:
  client:
    base-url: "https://dev.example.org"
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    base-url: "https://api.example.org"
    timeout: 12s
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        java.time.Duration timeout
) {}
~~~

Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Nếu không có nguồn ưu tiên cao hơn, Binder nhận các giá trị cuối là `https://api.example.org` và `12s`. Sau đó constructor của record được gọi với các giá trị tương ứng.

Nếu biến môi trường cung cấp:

~~~bash
APP_CLIENT_TIMEOUT=3s
~~~

trong môi trường chạy, timeout cuối có thể thành `3s`, trong khi base URL vẫn đến từ file profile.

**Constructor không tự biết giá trị đến từ nguồn nào.** Nó nhận những đối tượng Java đã được Binder chuẩn bị sau khi xét các nguồn và chuyển kiểu.

Tương tự, nếu list cấu hình từ profile ưu tiên cao hơn thay thế list mặc định, constructor vẫn nhận list kết quả cuối cùng, chứ không tự quyết định chiến lược merge list.

## 23. Khác biệt phiên bản cần biết

Khi tra cứu tài liệu về constructor binding, hãy phân biệt phiên bản Spring Boot:

### Spring Boot 2.2 đến 2.x

Constructor binding được giới thiệu trong dòng Spring Boot 2.x và nhiều ví dụ cũ dùng `@ConstructorBinding` theo cơ chế và vị trí annotation của thế hệ đó. Các bản 2.x cũ thường có ví dụ khai báo annotation ở cấp class hoặc package import khác với Spring Boot 3.

Không nên copy mã từ một tài liệu Boot 2.3 trực tiếp sang dự án Boot 3 rồi giả định import/annotation tương thích hoàn toàn.

### Spring Boot 3.x

Trong cách sử dụng phổ biến:

- Một constructor có tham số thích hợp của class `@ConfigurationProperties` có thể được **suy luận tự động**.
- Record có canonical constructor phù hợp cũng thường được binding mà không cần annotation tường minh.
- Nếu nhiều constructor cần phân biệt, dùng `org.springframework.boot.context.properties.bind.ConstructorBinding` trên constructor được chọn.
- Kiểu dùng constructor binding được đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
- Với validation, dự án dùng namespace Jakarta, ví dụ `jakarta.validation.constraints.NotBlank` thay vì package `javax.validation` cũ.

Với các phiên bản mới hơn, nên tham chiếu tài liệu khớp **đúng phiên bản dependency của ứng dụng**. Quy tắc học cốt lõi là hiểu việc suy luận **dựa vào số lượng và loại constructor cùng cách đăng ký bean**, không cố học thuộc một annotation độc lập khỏi ngữ cảnh phiên bản.

## 24. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Class bất biến có một constructor nhưng startup thất bại vì thiếu bean `String` | Class được đăng ký bằng `@Component` nên constructor bị dùng cho dependency injection | Bỏ `@Component`; dùng `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` |
| Dùng `@ConstructorBinding` trên class nhưng IDE báo sai target | Đang dùng import hoặc cú pháp của Spring Boot 2.x trong dự án 3.x | Dùng annotation đúng package và đặt trên constructor khi cần |
| Class có hai constructor và Binder không biết chọn cái nào | Không còn một constructor phù hợp duy nhất để suy luận | Chỉ rõ constructor cần dùng bằng `@ConstructorBinding` |
| Đã dùng record nhưng Spring không tạo bean cấu hình | Chưa đăng ký record với `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` | Bổ sung cơ chế đăng ký |
| Thuộc tính `base-url` không bind vào `baseUrl` | Tên tham số/metadata/cấu hình không khớp | Kiểm tra prefix, relaxed binding và `-parameters` |
| Tham số `Duration` không bind được | Giá trị có định dạng không phù hợp | Sửa chuỗi duration/đơn vị và kiểm tra conversion |
| Một trường bắt buộc thành `null` | Không có giá trị và không khai báo validation | Thêm validation hoặc default đúng ý nghĩa |
| Biến môi trường thay đổi nhưng bean giữ giá trị cũ | Object được tạo khi khởi động | Khởi động lại hoặc thiết kế refresh riêng |
| Field cấu hình là `final` nhưng JavaBean binding không sửa được | Đã tạo bean bằng no-args mà không có setter | Chọn constructor binding và đăng ký đúng |
| Dùng `@Autowired` trên constructor cấu hình | Vô tình yêu cầu dependency injection thay vì constructor binding | Tách bean nghiệp vụ với dữ liệu cấu hình; bỏ annotation không cần thiết |
| List cấu hình mất phần tử khi bật profile | List từ nguồn ưu tiên cao có thể thay thế list cũ | Khai báo đầy đủ list ở nguồn override |
| `Optional` nhận null | `Optional` không phải kiểu property được khuyến nghị cho binding | Dùng default/validation hoặc kiểu phù hợp |

Khi gặp lỗi, hãy kiểm tra theo thứ tự: **cách bean được đăng ký → số constructor → annotation chọn constructor → tên tham số → prefix và nguồn thuộc tính → conversion → validation**. Điều này thường giúp phân biệt lỗi cơ chế tạo bean với lỗi dữ liệu cấu hình.

## 25. Bài tập thực hành

### Bài 1 — Constructor duy nhất

Cho:

~~~java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int maxEntries;

    public CacheProperties(int maxEntries) {
        this.maxEntries = maxEntries;
    }

    public int getMaxEntries() {
        return maxEntries;
    }
}
~~~

Cấu hình:

~~~yaml
app:
  cache:
    max-entries: 200
~~~

Ứng dụng có `@ConfigurationPropertiesScan` phù hợp. Có bắt buộc viết `@ConstructorBinding` trên constructor hay không?

**Đáp án:** với Spring Boot 3.x trong ngữ cảnh này, thường **không**. Class có một constructor có tham số phù hợp để Binder tự suy luận. Giá trị `maxEntries` sẽ là `200` nếu binding thành công và không có override khác.

### Bài 2 — Hai constructor

Cho:

~~~java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int maxEntries;

    public CacheProperties() {
        this(100);
    }

    public CacheProperties(int maxEntries) {
        this.maxEntries = maxEntries;
    }
}
~~~

Muốn Binder dùng constructor có tham số, cần làm gì?

**Đáp án:** vì class có nhiều constructor, có thể đánh dấu constructor `CacheProperties(int maxEntries)` bằng `@ConstructorBinding` đúng package của Spring Boot 3.x. Nếu giữ no-args constructor mà muốn JavaBean binding, phải thiết kế trường và setter phù hợp; class trên có field final nên không phù hợp cho setter binding.

### Bài 3 — Component hay configuration properties scan?

Cho:

~~~java
@Component
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int maxEntries;

    public CacheProperties(int maxEntries) {
        this.maxEntries = maxEntries;
    }
}
~~~

Tại sao có thể nhận lỗi thiếu dependency `int`?

**Đáp án:** `@Component` khiến bean được tạo theo cơ chế container thông thường; tham số constructor có thể bị coi là dependency phải autowire, không được Binder cấp từ property `app.cache.max-entries`. Để constructor binding, bỏ `@Component` và đăng ký bằng quét/enable `@ConfigurationProperties`.

### Bài 4 — Record và default

Cho:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int threads,
        @DefaultValue("10s") java.time.Duration timeout
) {}
~~~

Không có khóa nào dưới `app.worker`. Hỏi hai giá trị có thể nhận được là gì?

**Đáp án:** `threads=4` và `timeout=10 giây`, khi class được đăng ký và binder có conversion phù hợp.

### Bài 5 — Nested object

Cho YAML:

~~~yaml
app:
  gateway:
    endpoint: "https://gateway.example.org"
    retry:
      max-attempts: 5
~~~

Hãy viết record có thể bind qua constructor với một nested record `Retry`.

**Đáp án gợi ý:**

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        String endpoint,
        Retry retry
) {
    public record Retry(int maxAttempts) {}
}
~~~

### Bài 6 — Phân biệt hai constructor

Một service có constructor `OrderService(OrderRepository repo, ClientProperties config)`, còn `ClientProperties` có constructor `ClientProperties(String baseUrl, int maxRetries)`. Constructor nào do Binder gọi?

**Đáp án:** Binder dùng constructor của `ClientProperties` để tạo bean cấu hình nếu kiểu được đăng ký phù hợp. Sau đó Spring container dùng constructor của `OrderService` để tiêm `OrderRepository` và bean `ClientProperties`. Không phải cùng một cơ chế.

### Bài 7 — Validation

Cho `@ConfigurationProperties` với constructor nhận `int threads`. Tệp YAML có `threads=-2`. Constructor binding có tự từ chối cấu hình không?

**Đáp án:** không phải mặc định chỉ vì sử dụng constructor binding. `-2` vẫn là số nguyên hợp lệ về kiểu. Cần `@Min(1)` cùng validation, hoặc logic kiểm tra bất biến trong constructor, để từ chối giá trị trái quy tắc nghiệp vụ.

## 26. Ghi nhớ

- Trong Spring Boot 3.x, một class `@ConfigurationProperties` có **một constructor có tham số phù hợp** thường được **constructor-bound ngầm định**, không cần `@ConstructorBinding`.
- **Số constructor chỉ là một phần điều kiện.** Cần xét cách bean đăng ký, annotation trên constructor, tên tham số và khả năng conversion.
- `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` là hai cách đăng ký phù hợp cho constructor binding.
- `@Component`/`@Bean` tạo bean theo cơ chế Spring thông thường; không nên trộn constructor binding bất biến với constructor injection dependency.
- Nếu có **nhiều constructor**, chỉ rõ constructor binding bằng `@ConstructorBinding` (Spring Boot 3.x: package `org.springframework.boot.context.properties.bind`).
- **Record** có canonical constructor phù hợp là lựa chọn gọn cho cấu hình bất biến; không cần setter.
- Dùng **`@DefaultValue`** để khai báo giá trị mặc định ở tham số constructor, và **Bean Validation** để kiểm tra giá trị bắt buộc hoặc giới hạn nghiệp vụ.
- Các nhóm lồng nhau, list, map và kiểu `Duration`/`DataSize` có thể được Binder tạo/chuyển đổi trước khi constructor được gọi.
- Compiler metadata như **`-parameters`** cần được lưu ý với constructor binding của class Java thông thường.
- Luôn dùng tài liệu tương ứng với **phiên bản Spring Boot của dự án**, vì vị trí và cách dùng `@ConstructorBinding` khác giữa các dòng phiên bản.

## Tài liệu tham khảo

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Constructor Binding](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot API — ConstructorBinding](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/ConstructorBinding.html)
