# Xác định khả năng của thư viện, điều kiện kích hoạt và giao ước tùy chỉnh

## Mục tiêu học tập

Một thư viện Spring Boot không chỉ cung cấp vài class Java. Khi phát hành một starter, tác giả đang thiết kế **một hợp đồng tích hợp với ứng dụng sử dụng thư viện**: thư viện cung cấp những khả năng nào, khả năng nào được kích hoạt trong hoàn cảnh nào, người dùng cấu hình ra sao và họ có thể thay thế hoặc mở rộng bean mặc định bằng cách nào.

Nếu hợp đồng không rõ, ứng dụng có thể bị kéo thêm dependency không cần thiết, tự bật tính năng ngoài ý muốn, gặp nhiều bean cùng kiểu hoặc không biết cách thay đổi implementation mặc định. Ngược lại, một auto-configuration được thiết kế tốt sẽ có hành vi dễ dự đoán: chỉ hoạt động khi đủ điều kiện, cung cấp default hữu ích và nhường quyền kiểm soát cho ứng dụng khi người dùng đã cấu hình.

Sau bài học, bạn có thể:

- Lập danh mục capability của thư viện và phân biệt core với optional integration.
- Xác định điều kiện classpath, property, bean, resource và web context cho từng capability.
- Thiết kế namespace, kiểu dữ liệu và default thành một configuration API ổn định.
- Quy định cách người dùng thay thế bean, cung cấp callback hoặc tắt auto-configuration.
- Tổ chức module, starter và `AutoConfiguration.imports` để tránh dependency không cần thiết.
- Viết test cho các nhánh kích hoạt, back-off, thiếu dependency và custom implementation.

## 1. Bắt đầu bằng danh mục capability, không bắt đầu bằng annotation

Trước khi viết `@AutoConfiguration`, hãy trả lời câu hỏi: **thư viện thực sự cung cấp điều gì cho ứng dụng?**

Ví dụ giả định thư viện `Acme` cung cấp client gọi một dịch vụ từ xa và một số tích hợp bổ sung:

| Capability | Giá trị mà ứng dụng nhận được | Phụ thuộc cần có | Chính sách kích hoạt |
| --- | --- | --- | --- |
| Core client | `AcmeClient` để gọi API của Acme | Core API và HTTP client implementation | Bật theo cấu hình chung, có default rõ |
| HTTP web integration | Endpoint/controller hoặc adapter dành cho servlet | Spring MVC/Servlet API | Chỉ khi ứng dụng là servlet web app và feature được bật |
| Codec integration | Chuyển đổi payload bằng codec bên thứ ba | SDK/codec của vendor | Chỉ khi SDK hiện diện và feature được opt-in |
| Metrics integration | Ghi nhận số lần gọi, độ trễ | Micrometer API/registry phù hợp | Chỉ khi API metrics có mặt và bean cần thiết tồn tại |
| Custom implementation | Ứng dụng tự thay thế client mặc định | API extension của Acme | Khi người dùng đăng ký bean tương thích |
| Configuration metadata | Gợi ý cấu hình trong IDE | Configuration processor lúc build | Sinh metadata khi đóng gói thư viện |

Danh mục này giúp xác định những gì **bắt buộc**, **tùy chọn**, **có thể thay thế** và **chỉ có ý nghĩa trong một loại ứng dụng**.

Đừng tạo một auto-configuration duy nhất chứa mọi feature nếu chúng có dependency hoặc vòng đời khác nhau. Một thư viện có thể có:
- Core auto-configuration: cung cấp phần cốt lõi.
- Web auto-configuration: chỉ dành cho servlet hoặc reactive web.
- Vendor auto-configuration: chỉ dành cho SDK của nhà cung cấp.
- Metrics auto-configuration: chỉ dành cho observability.

Mỗi lớp nên đại diện cho một nhóm khả năng có chung điều kiện kích hoạt và dependency.

## 2. Viết activation contract cho từng capability

Một capability chỉ nên được bật khi các tiền đề của nó đúng. Có thể dùng ma trận sau để review trước khi triển khai:

| Câu hỏi | Công cụ Spring Boot thường dùng | Ví dụ |
| --- | --- | --- |
| API/class cần thiết có trên runtime classpath không? | `@ConditionalOnClass` / `@ConditionalOnMissingClass` | Có `com.vendor.codec.Codec` |
| Người dùng có bật tính năng không? | `@ConditionalOnProperty` | `acme.codec.enabled=true` |
| Một bean nền tảng đã được đăng ký chưa? | `@ConditionalOnBean` | Có `MeterRegistry` hoặc vendor client |
| Người dùng đã cung cấp bean thay thế chưa? | `@ConditionalOnMissingBean` | Chưa có `AcmeClient` |
| Ứng dụng có đúng loại context không? | `@ConditionalOnWebApplication` | Servlet web application |
| Một resource bắt buộc có tồn tại không? | `@ConditionalOnResource` | File schema hoặc template |
| Có một ứng viên duy nhất để inject không? | `@ConditionalOnSingleCandidate` | Một `DataSource` hoặc một bean primary |
| Điều kiện chuyên biệt có thể biểu diễn bằng SpEL không? | `@ConditionalOnExpression` | Biểu thức đơn giản, không tham chiếu bean |

Các điều kiện trả lời những câu hỏi khác nhau. Classpath có SDK không đồng nghĩa SDK client đã được tạo; property bật không đồng nghĩa ứng dụng là servlet web app; một bean tồn tại không đồng nghĩa chưa có bean custom thay thế.

### 2.1. Điều kiện classpath

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
class AcmeCodecAutoConfiguration {
    // Các bean chỉ dành cho codec integration.
}
~~~

`@ConditionalOnClass` chỉ cho phép cấu hình được áp dụng khi class được tìm thấy. Dùng `name` khi muốn khai báo tên lớp bằng chuỗi, đặc biệt với optional dependency.

**Đặt condition ở cấp configuration class** nếu chữ ký của bean method có kiểu đến từ thư viện tùy chọn. Nếu condition chỉ đặt trên method, JVM có thể phải resolve kiểu trả về hoặc tham số trước khi condition method được đánh giá. Spring Boot khuyến nghị cô lập phần tích hợp trong một cấu hình riêng có class-level condition.

### 2.2. Điều kiện property

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
class AcmeAutoConfiguration {
}
~~~

Đoạn trên định nghĩa rõ: nếu người dùng không khai báo `acme.enabled`, tính năng vẫn được bật; nếu có khai báo, chỉ giá trị `true` mới khớp. Với một integration tùy chọn, thường nên đặt `matchIfMissing=false` để yêu cầu người dùng chủ động opt-in.

Đừng quên rằng `@ConditionalOnProperty` mặc định khớp khi property **tồn tại và khác chuỗi `false`**. Nếu không khai báo `havingValue="true"`, các giá trị như `off`, `no` hoặc `0` vẫn có thể khớp. Khi property là cờ boolean, hãy viết hợp đồng rõ thay vì dựa vào cách người đọc diễn giải chuỗi.

### 2.3. Điều kiện bean

- `@ConditionalOnBean(MyClient.class)`: chỉ tạo integration khi bean cần thiết đã có.
- `@ConditionalOnMissingBean(MyClient.class)`: chỉ cung cấp default nếu người dùng chưa có bean tương thích.
- `@ConditionalOnSingleCandidate(MyClient.class)`: yêu cầu có một ứng viên duy nhất hoặc một primary candidate có thể chọn.

Bean conditions được đánh giá dựa trên những bean definitions đã được xử lý **tới thời điểm đó**. Vì vậy, chúng phù hợp nhất với auto-configuration được áp dụng sau các cấu hình người dùng. Nếu cần phụ thuộc vào bean do auto-configuration khác cung cấp, hãy khai báo thứ tự bằng `after` hoặc `afterName` và kiểm thử cả hai phía.

### 2.4. Điều kiện web và resource

~~~java
@AutoConfiguration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
class AcmeServletAutoConfiguration {
}
~~~

Condition web giúp tránh tạo bean servlet trong ứng dụng CLI hoặc reactive. Tương tự, `@ConditionalOnResource` có thể dùng khi một feature cần schema/template có mặt. Không dùng điều kiện web thay cho điều kiện classpath: một servlet app vẫn có thể thiếu một SDK tùy chọn.

## 3. Xác định default và chính sách opt-in/opt-out

Mỗi capability cần có chính sách khi người dùng **không khai báo property**:

- **Default-on:** phù hợp với chức năng cốt lõi, an toàn và là điều người dùng mong đợi khi thêm starter.
- **Default-off:** phù hợp với tích hợp tùy chọn, tạo chi phí, kết nối bên ngoài, mở endpoint hoặc có ảnh hưởng vận hành.
- **Required configuration:** không có default nếu thiếu giá trị khiến ứng dụng không thể chạy an toàn; nên fail fast với thông báo rõ.

Ví dụ:

| Property | Default | Hành vi |
| --- | --- | --- |
| `acme.enabled` | `true` | Bật core client khi người dùng thêm starter |
| `acme.timeout` | `3s` | Giới hạn thời gian chờ mặc định |
| `acme.codec.enabled` | `false` (opt-in) | Chỉ tạo codec integration khi người dùng bật |
| `acme.web.enabled` | `true` nhưng cần servlet context | Cho phép web integration trong servlet app |
| `acme.endpoint` | Không dùng endpoint môi trường thật trong production | Người dùng phải cung cấp endpoint phù hợp nếu default không an toàn |

Các default này chỉ là ví dụ cho một thư viện giả định. Tác giả phải lựa chọn theo nghiệp vụ, chi phí, bảo mật và backward compatibility.

Một cờ feature và một điều kiện classpath thường được kết hợp:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ConditionalOnProperty(
        prefix = "acme.codec",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
class AcmeCodecAutoConfiguration {
}
~~~

Kết quả:
- SDK không có: không áp dụng cấu hình.
- SDK có nhưng property thiếu: không bật integration.
- SDK có và property là `true`: có thể áp dụng; các điều kiện bean bổ sung vẫn phải khớp.
- Property là `false`: không áp dụng.

## 4. Thiết kế configuration API là một phần của giao ước thư viện

Các key công khai nên có namespace riêng do thư viện sở hữu, ví dụ `acme`. Không thêm key của thư viện vào các namespace Spring Boot đang quản lý như `spring`, `server` hoặc `management`.

Ví dụ:

~~~yaml
acme:
  enabled: true
  endpoint: https://api.acme.example
  timeout: 3s
  codec:
    enabled: false
  web:
    enabled: true
~~~

Nên dùng `@ConfigurationProperties` để bind một nhóm key thành đối tượng có kiểu:

~~~java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    /**
     * Endpoint used by the Acme client.
     */
    private URI endpoint = URI.create("https://api.acme.example");

    /**
     * Timeout for an Acme request.
     */
    private Duration timeout = Duration.ofSeconds(3);

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Chọn kiểu phản ánh đúng ý nghĩa:
- `Duration` cho timeout/retry delay.
- `DataSize` cho payload/buffer limit.
- `URI` cho endpoint.
- `enum` cho tập lựa chọn đóng.
- `boolean` cho cờ bật/tắt hai trạng thái.
- `List<T>` hoặc `Map<K,V>` cho tập cấu hình thực sự cần collection.

Mỗi property công khai cần mô tả ý nghĩa, đơn vị, miền hợp lệ và default. Với Java record, dùng Javadoc `@param` ở cấp record để mô tả component. Không nhồi nhiều chức năng độc lập vào một prefix hoặc một properties class khổng lồ.

### 4.1. Metadata và gợi ý trong IDE

Thêm `spring-boot-configuration-processor` vào `annotationProcessor` để tạo `META-INF/spring-configuration-metadata.json`. Metadata này giúp IDE gợi ý key, kiểu và mô tả.

Ví dụ Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Ngoài ra, `spring-boot-autoconfigure-processor` có thể tạo metadata điều kiện auto-configuration (`META-INF/spring-autoconfigure-metadata.properties\)) để Boot lọc sớm những cấu hình không phù hợp. Hai metadata phục vụ hai mục tiêu khác nhau: một cái mô tả configuration properties cho người dùng/IDE, một cái hỗ trợ lọc auto-configuration.

## 5. Định nghĩa giao ước tùy chỉnh: thay thế hay mở rộng?

Một thư viện nên nói rõ người dùng có thể tùy chỉnh ở mức nào. Thường có ba lựa chọn:

1. **Thay thế toàn bộ bean:** ứng dụng đăng ký implementation của interface công khai; auto-configuration dùng `@ConditionalOnMissingBean` để back off.
2. **Điều chỉnh default:** ứng dụng đăng ký một hoặc nhiều callback/customizer mà thư viện áp dụng khi tạo implementation mặc định.
3. **Cấu hình qua properties:** người dùng thay đổi endpoint, timeout, mode hoặc giới hạn mà không cần viết bean mới.

Không nên bắt người dùng thay thế toàn bộ client chỉ để đổi một thuộc tính nhỏ. Ngược lại, đừng phơi quá nhiều chi tiết nội bộ qua hàng chục callback khiến API khó duy trì.

### 5.1. Bean back-off

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
DefaultAcmeClient acmeClient(AcmeProperties properties) {
    return new DefaultAcmeClient(
            properties.getEndpoint(),
            properties.getTimeout());
}
~~~

Khi ứng dụng đã cung cấp bean `AcmeClient`, default không được đăng ký. Dùng interface công khai làm contract để implementation có thể thay đổi. Cung cấp kiểu trả về đủ cụ thể cho Spring suy luận bean type; điều kiện có thể khai báo rõ kiểu interface mà nó kiểm tra.

Tránh dựa vào cơ chế bean-definition overriding để thay thế bean cùng tên. Back-off theo type thể hiện ý định rõ hơn và không buộc người dùng biết tên bean nội bộ.

### 5.2. Callback/customizer

Nếu muốn giữ default implementation nhưng cho phép tinh chỉnh, cung cấp một interface nhỏ:

~~~java
public interface AcmeClientCustomizer {
    void customize(AcmeClientBuilder builder);
}
~~~

Auto-configuration có thể nhận `ObjectProvider<AcmeClientCustomizer>` và gọi theo thứ tự:

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
DefaultAcmeClient acmeClient(
        AcmeProperties properties,
        ObjectProvider<AcmeClientCustomizer> customizers) {

    AcmeClientBuilder builder = new AcmeClientBuilder(
            properties.getEndpoint(),
            properties.getTimeout());

    customizers.orderedStream()
            .forEach(customizer -> customizer.customize(builder));

    return builder.build();
}
~~~

Giao ước phải quy định:
- Customizer được gọi trước hay sau khi áp dụng default.
- Nhiều customizer chạy theo thứ tự nào (`Ordered`/`@Order`).
- Có cho phép ghi đè cùng một thuộc tính nhiều lần không.
- Callback chỉ cấu hình object hay có thể thực hiện I/O.
- Lỗi từ customizer làm startup thất bại hay được xử lý riêng.

Giữ callback ngắn và tránh kết nối mạng trong lúc cấu hình bean. Tài liệu phải nêu rõ customizer không có tác dụng nếu người dùng đã thay thế toàn bộ `AcmeClient`, trừ khi thư viện chủ động thiết kế một hook riêng cho custom implementation.

### 5.3. Tên bean, qualifier và nhiều implementation

Nếu thư viện chỉ cung cấp một default, người dùng thường inject theo interface. Nếu có nhiều implementation, cần công bố qualifier hoặc cách chọn rõ ràng. Không coi tên bean nội bộ như `acmeClient` là API ổn định trừ khi tài liệu cam kết tên đó.

Nếu ứng dụng đăng ký nhiều `AcmeClient`, injection theo kiểu đơn có thể mơ hồ; người dùng phải chọn `@Primary` hoặc `@Qualifier`. Auto-configuration không nên tự tạo thêm bean mặc định khi ứng dụng đã cung cấp implementation phù hợp.

## 6. Ví dụ auto-configuration cốt lõi hoàn chỉnh

Ví dụ sau minh họa một client mặc định, properties có kiểu và customizer. Các class API trong thực tế nên nằm ở file riêng trong package công khai của thư viện.

~~~java
@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    DefaultAcmeClient acmeClient(
            AcmeProperties properties,
            ObjectProvider<AcmeClientCustomizer> customizers) {

        AcmeClientBuilder builder = new AcmeClientBuilder(
                properties.getEndpoint(),
                properties.getTimeout());

        customizers.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder.build();
    }
}
~~~

Đây là **đoạn cấu hình minh họa**; cần import các annotation và kiểu tương ứng. `AcmeClient`, `DefaultAcmeClient`, `AcmeProperties`, `AcmeClientBuilder` và `AcmeClientCustomizer` là API/implementation do thư viện sở hữu.

Cấu hình trên biểu đạt một contract rõ:
- Core API phải có trên classpath.
- Tính năng bật mặc định, nhưng người dùng có thể tắt bằng `acme.enabled=false`.
- Properties được bind khi auto-configuration khớp.
- Client mặc định chỉ được tạo khi chưa có implementation người dùng.
- Customizer được áp dụng theo thứ tự đã định nghĩa.

### 6.1. Optional integration là một auto-configuration riêng

~~~java
@AutoConfiguration(
        afterName = "com.vendor.codec.autoconfigure.CodecAutoConfiguration")
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ConditionalOnProperty(
        prefix = "acme.codec",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public class AcmeCodecAutoConfiguration {

    @Bean
    @ConditionalOnBean(type = "com.vendor.codec.Codec")
    @ConditionalOnMissingBean(AcmeCodec.class)
    DefaultAcmeCodec acmeCodec(com.vendor.codec.Codec codec) {
        return new DefaultAcmeCodec(codec);
    }
}
~~~

Đoạn trên chỉ minh họa cách tổ chức optional integration. Vì chữ ký method có kiểu vendor, class-level `@ConditionalOnClass` bảo vệ toàn bộ cấu hình khi SDK không có. `afterName` chỉ sắp xếp sau auto-configuration của vendor nếu nó là candidate được chọn; nó không tự cài SDK hoặc tạo bean `Codec`. `@ConditionalOnBean` kiểm tra bean client thực sự tồn tại, còn `@ConditionalOnMissingBean` cho phép ứng dụng thay adapter mặc định.

## 7. Đóng gói thành autoconfigure module và starter

Một cách tổ chức phổ biến:

~~~text
acme-spring-boot-autoconfigure/
  AcmeAutoConfiguration.java
  AcmeProperties.java
  AcmeClientCustomizer.java
  META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports

acme-spring-boot-starter/
  build.gradle

acme-spring-boot-codec/
  AcmeCodecAutoConfiguration.java
  META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

- Module `autoconfigure` chứa auto-configuration, configuration properties và extension API.
- Starter cung cấp dependency set hợp lý để ứng dụng bắt đầu sử dụng.
- Optional integration có thể tách thành module/starter riêng khi có dependency, vòng đời hoặc versioning riêng.

Không nhất thiết phải tạo nhiều module nếu thư viện đơn giản. Nếu không có optional feature và dependency graph ổn định, có thể gộp. Khi có nhiều flavor, tách module giúp người dùng chỉ chọn đúng phần cần.

### 7.1. Đăng ký auto-configuration

Trong JAR, file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ nội dung:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Nếu optional integration là một class được công bố bởi artifact khác, file imports của artifact đó liệt kê class tương ứng. Không component-scan package auto-configuration và không import cứng mọi optional configuration từ core class. Dùng `@Import` có chủ đích cho các cấu hình hỗ trợ bên trong một nhánh đã được bảo vệ.

### 7.2. Dependency optional

Core autoconfigure module không nên kéo mọi SDK optional vào mọi ứng dụng. Có thể:
- Tách integration thành artifact riêng để dependency graph chỉ có khi người dùng chọn.
- Đánh dấu dependency là optional trong metadata Maven khi muốn người dùng quyết định có kéo thư viện đó hay không.
- Dùng classpath condition để optional configuration không áp dụng khi SDK không hiện diện.

Một condition không thay thế dependency management. Nếu source code của module trực tiếp tham chiếu SDK, module vẫn cần dependency phù hợp để biên dịch; điều quan trọng là ứng dụng core-only không bị buộc phải nhận SDK runtime không cần thiết.

### 7.3. Tên artifact và starter

Dùng namespace thương hiệu riêng, ví dụ `acme-spring-boot-autoconfigure`, `acme-spring-boot-starter` và `acme-spring-boot-starter-codec`. Tránh đặt module của thư viện bắt đầu bằng `spring-boot`, vì tên đó có thể gây nhầm lẫn với module chính thức của Spring Boot.

## 8. Thứ tự và tương tác với cấu hình người dùng

Auto-configuration thường được áp dụng sau cấu hình người dùng. Đây là nền tảng để `@ConditionalOnMissingBean` nhường chỗ cho custom bean.

Nếu phụ thuộc vào auto-configuration khác:
~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
class AcmeJdbcAutoConfiguration {
}
~~~

Hoặc khi không muốn tham chiếu class trực tiếp:
~~~java
@AutoConfiguration(afterName = "com.vendor.autoconfigure.VendorAutoConfiguration")
class AcmeVendorBridgeAutoConfiguration {
}
~~~

Thứ tự chỉ ảnh hưởng thứ tự **định nghĩa bean**. Nó không đảm bảo thứ tự constructor của các bean. Khi một bean thực sự phụ thuộc bean khác, hãy khai báo dependency bằng constructor/method parameter; dùng `@DependsOn` chỉ khi có quan hệ khởi tạo cụ thể mà dependency graph không thể biểu đạt.

Tránh dùng `@ConditionalOnBean` trên một cấu hình thông thường được parse quá sớm nếu bean cần kiểm tra có thể chưa được xử lý. Bean conditions phù hợp nhất trong auto-configuration và khi có ordering rõ.

## 9. Kiểm thử contract bằng ApplicationContextRunner

Auto-configuration chịu ảnh hưởng của classpath, properties, user-defined beans và context type. Vì vậy, test cần tạo context nhỏ với từng tổ hợp quan trọng. `ApplicationContextRunner` là lựa chọn phù hợp cho các nhánh non-web.

Ví dụ dưới đây là **một tệp test hoàn chỉnh** cho default, property override, disable, custom bean và customizer. Các class lồng trong test chỉ để giữ ví dụ trong một tệp; khi triển khai production hãy tách chúng thành file/package tương ứng.

**Tệp:** `src/test/java/example/acme/AcmeAutoConfigurationContractTest.java`

~~~java
package example.acme;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationContractTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenFeaturePropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);

            AcmeClient client = context.getBean(AcmeClient.class);
            assertThat(client.endpoint())
                    .isEqualTo(URI.create("https://api.acme.example"));
            assertThat(client.timeout()).isEqualTo(Duration.ofSeconds(3));
        });
    }

    @Test
    void bindsUserProvidedProperties() {
        runner.withPropertyValues(
                        "acme.endpoint=https://tenant.example",
                        "acme.timeout=1500ms")
                .run(context -> {
                    AcmeClient client = context.getBean(AcmeClient.class);
                    assertThat(client.endpoint())
                            .isEqualTo(URI.create("https://tenant.example"));
                    assertThat(client.timeout())
                            .isEqualTo(Duration.ofMillis(1500));
                });
    }

    @Test
    void explicitFalseDisablesTheCoreFeature() {
        runner.withPropertyValues("acme.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AcmeClient.class));
    }

    @Test
    void userImplementationReplacesTheDefault() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).endpoint())
                            .isEqualTo(URI.create("https://custom.example"));
                    assertThat(context.containsBean("acmeClient")).isFalse();
                });
    }

    @Test
    void orderedCustomizersChangeTheDefaultClient() {
        runner.withUserConfiguration(UserCustomizerConfiguration.class)
                .run(context -> {
                    AcmeClient client = context.getBean(AcmeClient.class);
                    assertThat(client.endpoint())
                            .isEqualTo(URI.create("https://customized.example"));
                    assertThat(client.timeout())
                            .isEqualTo(Duration.ofSeconds(8));
                });
    }

    interface AcmeClient {
        URI endpoint();
        Duration timeout();
    }

    record DefaultAcmeClient(URI endpoint, Duration timeout)
            implements AcmeClient {
    }

    static class AcmeClientBuilder {

        private URI endpoint;
        private Duration timeout;

        AcmeClientBuilder(URI endpoint, Duration timeout) {
            this.endpoint = endpoint;
            this.timeout = timeout;
        }

        void endpoint(URI endpoint) {
            this.endpoint = endpoint;
        }

        void timeout(Duration timeout) {
            this.timeout = timeout;
        }

        DefaultAcmeClient build() {
            return new DefaultAcmeClient(endpoint, timeout);
        }
    }

    interface AcmeClientCustomizer {
        void customize(AcmeClientBuilder builder);
    }

    @ConfigurationProperties(prefix = "acme")
    public static class AcmeProperties {

        private URI endpoint = URI.create("https://api.acme.example");
        private Duration timeout = Duration.ofSeconds(3);

        public URI getEndpoint() {
            return endpoint;
        }

        public void setEndpoint(URI endpoint) {
            this.endpoint = endpoint;
        }

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }
    }

    @AutoConfiguration
    @ConditionalOnClass(AcmeClient.class)
    @ConditionalOnProperty(
            prefix = "acme",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @EnableConfigurationProperties(AcmeProperties.class)
    static class AcmeAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(AcmeClient.class)
        DefaultAcmeClient acmeClient(
                AcmeProperties properties,
                ObjectProvider<AcmeClientCustomizer> customizers) {

            AcmeClientBuilder builder = new AcmeClientBuilder(
                    properties.getEndpoint(),
                    properties.getTimeout());

            customizers.orderedStream()
                    .forEach(customizer -> customizer.customize(builder));

            return builder.build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new DefaultAcmeClient(
                    URI.create("https://custom.example"),
                    Duration.ofSeconds(9));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCustomizerConfiguration {

        @Bean
        @Order(1)
        AcmeClientCustomizer endpointCustomizer() {
            return builder ->
                    builder.endpoint(URI.create("https://customized.example"));
        }

        @Bean
        @Order(2)
        AcmeClientCustomizer timeoutCustomizer() {
            return builder -> builder.timeout(Duration.ofSeconds(8));
        }
    }
}
~~~

### 9.1. Dependency và lệnh chạy

Yêu cầu Java 17+ và Spring Boot 3.3.x. Trong dự án Gradle đã có Spring Boot plugin hoặc BOM quản lý version:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy trong module chứa test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.acme.AcmeAutoConfigurationContractTest"

# Windows
gradlew.bat test --tests "example.acme.AcmeAutoConfigurationContractTest"
~~~

**Kết quả mong đợi:** năm test PASS:
- Property thiếu: client default được tạo với endpoint và timeout mặc định.
- Property ghi đè: giá trị được bind vào client.
- `acme.enabled=false`: client default không được đăng ký.
- User bean: auto-configuration back off.
- Customizer: default client được điều chỉnh theo thứ tự `@Order`.

Test dùng AssertJ, không có `System.out.println`, nên không có stdout nội dung cố định. Kết quả console phụ thuộc Gradle/JUnit logging. Mã được trình bày để chạy trong dự án tương ứng; cần thực thi lệnh trên dependency graph thật để xác nhận build.

### 9.2. Kiểm thử optional dependency

Với integration phụ thuộc SDK, bổ sung test dùng `FilteredClassLoader`:

~~~java
runner.withClassLoader(new FilteredClassLoader(OptionalVendorClient.class))
        .run(context ->
                assertThat(context).doesNotHaveBean(OptionalVendorAdapter.class));
~~~

Đây là **đoạn minh họa** cho test của optional auto-configuration. Nó mô phỏng runtime classpath không có class SDK và xác nhận adapter không được đăng ký. Nếu feature là servlet/reactive, dùng `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` để tạo đúng loại context.

## 10. Chẩn đoán vì sao capability không được kích hoạt

Bật debug khi chạy ứng dụng:

~~~bash
java -jar app.jar --debug
~~~

Condition Evaluation Report cho biết auto-configuration nào khớp hoặc không khớp. Khi điều tra, kiểm tra theo thứ tự:

1. **Candidate:** class có nằm trong `AutoConfiguration.imports` của JAR được publish không?
2. **Classpath:** `@ConditionalOnClass` có tìm thấy tất cả API cần thiết không?
3. **Exclusion:** ứng dụng có loại cấu hình qua `spring.autoconfigure.exclude` hoặc thuộc tính `exclude` không?
4. **Property:** key có tồn tại và đúng giá trị `havingValue`/ `matchIfMissing` không?
5. **Bean:** `@ConditionalOnBean` có tìm thấy bean nền tảng; `@ConditionalOnMissingBean` có bị chặn bởi bean người dùng không?
6. **Context type:** ứng dụng có đúng servlet/reactive/non-web context không?
7. **Bean creation:** definition có tồn tại nhưng constructor/dependency/initialization bị lỗi không?

Phân biệt cấu hình **không được chọn**, **được chọn nhưng condition không khớp**, **bean definition không được đăng ký**, và **bean đã đăng ký nhưng khởi tạo thất bại**. Đây là các giai đoạn khác nhau.

Không dùng `@ConditionalOnExpression` để tham chiếu bean trong SpEL chỉ nhằm kiểm tra một capability; việc tham chiếu bean có thể làm bean khởi tạo rất sớm, trước các bước post-processing như configuration properties binding. Ưu tiên condition annotation chuyên biệt hoặc viết `Condition` riêng nếu logic thật sự phức tạp.

## 11. Những lỗi thường gặp khi thiết kế giao ước thư viện

1. **Không lập danh mục capability.** Tất cả chức năng bị gom vào một auto-configuration và phụ thuộc không cần thiết.
2. **Dùng chung một cờ cho nhiều integration độc lập.** Một key `acme.enabled` không nên vô tình bật cả web, codec và metrics nếu chúng có chính sách khác nhau.
3. **Mặc định bật một feature có side effect lớn.** Endpoint công khai, gửi telemetry ra ngoài hoặc kết nối dịch vụ cần cân nhắc opt-in rõ ràng.
4. **Không phân biệt classpath và bean presence.** SDK có trên classpath chưa chắc bean client đã tồn tại; dùng `@ConditionalOnBean` khi thực sự cần bean.
5. **Chỉ đặt `@ConditionalOnClass` trên method có kiểu optional.** JVM có thể resolve chữ ký method trước; tách configuration class riêng và bảo vệ ở class-level.
6. **Không dùng `@ConditionalOnMissingBean`.** Người dùng tự tạo implementation nhưng vẫn có default thứ hai, gây mơ hồ khi inject.
7. **Condition bean đặt quá sớm.** Kết quả có thể phụ thuộc bean definitions đã được xử lý; dùng trong auto-configuration và khai báo thứ tự nếu cần.
8. **API cấu hình không có namespace riêng.** Key dễ va chạm và phụ thuộc vào namespace do Spring Boot quản lý.
9. **Default không nhất quán.** Properties, condition và service dùng các default khác nhau; test thiếu key sẽ phát hiện vấn đề.
10. **Không có extension point.** Người dùng buộc thay toàn bộ bean chỉ để thay đổi một thuộc tính nhỏ.
11. **Quá nhiều customizer không có thứ tự.** Kết quả cuối phụ thuộc thứ tự không được công bố; định nghĩa `Ordered` hoặc `@Order` và kiểm thử.
12. **Tên bean nội bộ trở thành hợp đồng ngầm.** Người dùng phụ thuộc tên không được cam kết, khiến refactor gây breaking change.
13. **Starter kéo mọi optional dependency.** Người dùng chỉ cần core nhưng vẫn nhận SDK/web/metrics không cần thiết.
14. **Không đăng ký imports đúng cách.** Class có trong JAR nhưng không được liệt kê trong `AutoConfiguration.imports`, hoặc resource bị ghi đè khi đóng gói.
15. **Component scan package auto-configuration.** Cấu hình có thể được tải ngoài cơ chế ordering/exclusion chuẩn; chỉ công bố qua imports file.
16. **Không test các nhánh âm.** Chỉ test default thành công, bỏ qua property false, class thiếu, bean custom và context không phù hợp.
17. **Không kiểm tra JAR đã phát hành.** Source tree đúng nhưng resource imports/metadata không được đóng gói như mong đợi.
18. **Đổi default hoặc property name mà không có migration.** Đây là thay đổi hành vi/API công khai, có thể phá ứng dụng downstream.

## 12. Checklist trước khi phát hành thư viện hoặc starter

### Capability và điều kiện

- [ ] Có danh sách core và optional capability.
- [ ] Mỗi capability có dependency bắt buộc và điều kiện classpath riêng.
- [ ] Property kích hoạt có default và semantics rõ.
- [ ] Bean conditions và ordering phản ánh đúng thứ tự cung cấp dependency.
- [ ] Servlet/reactive/non-web feature được giới hạn đúng context.

### Configuration API

- [ ] Namespace thuộc sở hữu của thư viện.
- [ ] Kiểu Java phản ánh đúng ý nghĩa property.
- [ ] Mọi default đều có tài liệu và test.
- [ ] Mỗi key có mô tả, đơn vị và miền giá trị.
- [ ] Metadata IDE được sinh và kiểm tra.

### Customization contract

- [ ] Bean default có `@ConditionalOnMissingBean`.
- [ ] Interface công khai ổn định và không phơi chi tiết vendor tùy chọn.
- [ ] Có customizer khi người dùng cần điều chỉnh default.
- [ ] Thứ tự customizer được quy định.
- [ ] Qualifier/primary được mô tả nếu có nhiều implementation.
- [ ] Cách tắt hoặc exclude auto-configuration được tài liệu hóa.

### Build và kiểm thử

- [ ] `AutoConfiguration.imports` chứa đúng class.
- [ ] Optional dependency không bị kéo vào core-only usage.
- [ ] Test default, override, disabled, class missing, bean missing và context type.
- [ ] Test artifact/JAR cuối cùng, không chỉ source.
- [ ] Condition Evaluation Report dễ đọc khi condition không khớp.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** SDK vendor có trên classpath nhưng chưa có bean client. `@ConditionalOnClass` có đủ để đăng ký adapter không?

**Đáp án:** Không. Classpath condition chỉ xác nhận class tồn tại; adapter còn có thể cần `@ConditionalOnBean` để kiểm tra bean client đã được đăng ký.

**Câu 2.** Người dùng khai báo `AcmeClient` riêng. Làm sao tránh tạo thêm default?

**Đáp án:** Dùng `@ConditionalOnMissingBean(AcmeClient.class)` trên bean default trong auto-configuration.

**Câu 3.** Vì sao optional integration nên có auto-configuration riêng?

**Đáp án:** Nó có thể có classpath, property, bean và context conditions khác core; tách class giúp bảo vệ kiểu tùy chọn và giảm coupling.

**Câu 4.** `acme.enabled` thiếu và `matchIfMissing=true`. Điều kiện có khớp không?

**Đáp án:** Có, nếu các điều kiện khác cũng đúng. Nếu muốn opt-in, đặt `matchIfMissing=false`.

**Câu 5.** Ứng dụng muốn thay endpoint mà vẫn dùng default client. Có cần tự khai báo toàn bộ `AcmeClient` không?

**Đáp án:** Không. Dùng `@ConfigurationProperties` để cấu hình endpoint; customizer là lựa chọn nếu cần tùy biến hành vi tạo client ngoài properties.

## 14. Ghi nhớ khi thiết kế

Một giao ước auto-configuration tốt phải nói rõ **thư viện cung cấp gì, điều kiện nào làm từng capability xuất hiện, người dùng có thể điều chỉnh hoặc thay thế nó ra sao**.

Bắt đầu bằng capability matrix, tách core khỏi integration tùy chọn, định nghĩa property namespace có kiểu và default rõ ràng, bảo vệ bean default bằng `@ConditionalOnMissingBean`, và cung cấp customizer có thứ tự khi cần. Đăng ký auto-configuration qua `AutoConfiguration.imports`, giữ optional dependencies ngoài core path khi có thể, rồi kiểm thử từng nhánh bằng `ApplicationContextRunner`.

Khi các quyết định này được ghi thành hợp đồng, ứng dụng dùng starter sẽ biết chính xác điều gì xảy ra khi thêm dependency, khi bật property, khi thiếu SDK hoặc khi tự cung cấp bean. Đó là nền tảng để thư viện có thể phát triển mà vẫn giữ được khả năng tương thích.

### Tài liệu Spring Boot chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — @AutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 — @ConditionalOnClass Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.3 — @ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
