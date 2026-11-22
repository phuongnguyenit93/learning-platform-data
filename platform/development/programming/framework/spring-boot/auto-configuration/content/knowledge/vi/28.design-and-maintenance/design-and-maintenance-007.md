# Tài liệu hóa thuộc tính, điểm mở rộng, bean thay thế và các loại trừ được hỗ trợ

## Mục tiêu học tập

Một starter Spring Boot có thể khởi động được ngay sau khi thêm dependency, nhưng trải nghiệm sử dụng chỉ thực sự tốt khi người dùng biết rõ:

- Những property nào được hỗ trợ, kiểu dữ liệu, giá trị mặc định và cách kiểm tra hợp lệ.
- Họ có thể tùy chỉnh thư viện qua bean, interface, callback hoặc customizer nào.
- Bean mặc định sẽ nhường chỗ cho bean do ứng dụng cung cấp trong trường hợp nào.
- Họ có thể loại trừ toàn bộ auto-configuration hoặc chỉ tắt một tính năng cụ thể bằng cách nào.
- Các contract trên được hỗ trợ từ phiên bản nào và thay đổi ra sao khi nâng cấp.

Tài liệu hóa các phần này là một phần của thiết kế API. Property name, default value, bean type, extension interface và FQCN được dùng trong exclusion đều có thể trở thành hợp đồng mà ứng dụng phụ thuộc vào.

Bài học này dùng Spring Boot 3.3 và Java 17+ để xây dựng một cách tài liệu hóa có thể duy trì: từ `@ConfigurationProperties` và metadata cho IDE đến customizer, `@ConditionalOnMissingBean`, exclusion, kiểm thử và migration note.

Sau bài học, bạn có thể:

- Thiết kế namespace và nhóm configuration properties ổn định.
- Sinh configuration metadata để IDE gợi ý key, kiểu, mô tả, giá trị và deprecation.
- Tài liệu hóa property theo bảng có thể dùng trực tiếp trong README/reference guide.
- Phân biệt bean override, customizer, qualifier và auto-configuration exclusion.
- Công bố rõ các extension point được hỗ trợ và giới hạn của chúng.
- Giải thích các cách loại trừ auto-configuration ở cấp ứng dụng hoặc một tập import.
- Kiểm thử binding, validation, default bean back-off và exclusion.
- Quản lý thay đổi property, bean contract và FQCN qua các phiên bản.

## 1. Bốn nhóm hợp đồng cần công bố

Một thư viện tích hợp Spring Boot thường có bốn nhóm hợp đồng công khai:

| Nhóm | Người dùng cần biết | Ví dụ |
| --- | --- | --- |
| Configuration properties | Cách bật/tắt và cấu hình hành vi | `acme.enabled`, `acme.connect-timeout` |
| Extension points | Cách tùy chỉnh hoặc thay implementation | `AcmeClient`, `AcmeClientCustomizer` |
| Default bean behavior | Khi nào thư viện tạo bean và khi nào nhường cho user bean | `@ConditionalOnMissingBean(AcmeClient.class)` |
| Supported exclusions | Cách loại một hoặc nhiều auto-configuration | `spring.autoconfigure.exclude`, `excludeName` |

Bốn nhóm này liên quan nhưng không thay thế nhau.

Ví dụ, đặt `acme.enabled=false` có thể tắt riêng tính năng Acme theo property condition. Loại `AcmeAutoConfiguration` bằng `spring.autoconfigure.exclude` sẽ ngăn toàn bộ auto-configuration đó tham gia. Cung cấp một `AcmeClient` bean chỉ thay thế implementation mặc định của client; các bean khác trong cùng auto-configuration vẫn có thể được tạo.

Tài liệu tốt cần mô tả chính xác phạm vi ảnh hưởng của từng cách.

## 2. Thiết kế namespace configuration properties

Dùng `@ConfigurationProperties` cho nhóm cấu hình có cấu trúc. Chọn namespace riêng thuộc sở hữu của thư viện, ví dụ `acme`, `acme.client` hoặc `acme.codec`.

Không đặt property của thư viện dưới các namespace Spring Boot đang sở hữu như `spring`, `server`, `management` hoặc namespace của một integration khác. Việc dùng namespace riêng giảm nguy cơ xung đột khi Spring Boot bổ sung property mới.

Ví dụ cấu hình:

~~~yaml
acme:
  enabled: true
  endpoint: https://api.acme.example
  connect-timeout: 3s
  read-timeout: 10s
  max-in-flight: 64
  codec:
    enabled: false
    mode: safe
~~~

Tên property nên theo dạng kebab-case:

- `acme.connect-timeout`
- `acme.max-in-flight`
- `acme.codec.enabled`

Spring Boot hỗ trợ relaxed binding giữa các cách viết phù hợp, nhưng tài liệu nên dùng canonical kebab-case làm dạng chuẩn. Người dùng sẽ dễ tìm kiếm và đối chiếu với metadata hơn.

### 2.1. Chọn kiểu dữ liệu thể hiện đúng ý nghĩa

| Ý nghĩa | Kiểu nên cân nhắc | Vì sao |
| --- | --- | --- |
| Thời gian chờ | `java.time.Duration` | Có thể ghi `3s`, `500ms`, `2m` thay cho số không rõ đơn vị |
| Dung lượng | `org.springframework.util.unit.DataSize` | Có thể ghi `10MB`, `512KB` |
| Bật/tắt | `boolean` hoặc `Boolean` | Phân biệt default cố định và trạng thái chưa được cấu hình nếu cần |
| URL/endpoint | `URI` | Biểu diễn địa chỉ và scheme có cấu trúc |
| Số lần retry | `int` hoặc `Integer` | Dễ áp dụng giới hạn và validation |
| Tập lựa chọn hữu hạn | `enum` | Giới hạn giá trị hợp lệ và hỗ trợ metadata gợi ý |
| Danh sách | `List<T>` hoặc `Set<T>` | Thể hiện collection thay vì tự parse chuỗi |

Tránh dùng `long timeout` mà không nói rõ đơn vị. Nếu buộc phải dùng số, ghi rõ đơn vị trong tên property hoặc mô tả. Với cấu hình mới, `Duration` thường dễ đọc hơn.

### 2.2. Tách nhóm property theo trách nhiệm

Không nên tạo một class khổng lồ chứa mọi key của starter. Có thể tách:

~~~text
AcmeProperties
  enabled
  endpoint
  connectTimeout
  readTimeout

AcmeRetryProperties
  maxAttempts
  backoff

AcmeCodecProperties
  enabled
  mode
~~~

Nhóm property nên phản ánh các tính năng có thể bật/tắt hoặc thay đổi độc lập. Nếu một nhóm chỉ tồn tại khi dependency tùy chọn có mặt, đặt nó trong integration/autoconfigure module tương ứng.

## 3. Khai báo properties và default values

Ví dụ dùng Java record, phù hợp với Java 17 và Spring Boot 3.3:

**Tệp:** `src/main/java/com/acme/autoconfigure/AcmeProperties.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@ConfigurationProperties(prefix = "acme")
@Validated
public record AcmeProperties(
        @DefaultValue("true")
        boolean enabled,

        @NotNull
        URI endpoint,

        @DefaultValue("3s")
        Duration connectTimeout,

        @DefaultValue("10s")
        Duration readTimeout,

        @DefaultValue("64")
        @Min(1)
        @Max(4096)
        int maxInFlight
) {
}
~~~

Record có một constructor duy nhất nên Spring Boot có thể dùng constructor binding. `@DefaultValue` cung cấp giá trị khi property không được khai báo. `@Validated` kích hoạt validation cho configuration properties; các constraint như `@NotNull`, `@Min` và `@Max` giúp phát hiện cấu hình sai lúc khởi động.

Nếu dùng validation annotations, module cần dependency validation phù hợp, thường là `spring-boot-starter-validation` hoặc provider Jakarta Validation tương ứng. Không nên khai báo constraint rồi quên runtime validator, vì khi đó validation có thể không được thực hiện như mong muốn.

### 3.1. Đăng ký properties trong auto-configuration

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@AutoConfiguration
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {
}
~~~

Có thể dùng `@ConfigurationPropertiesScan` trong ứng dụng để tìm các lớp properties của ứng dụng. Với thư viện auto-configuration, `@EnableConfigurationProperties` thường làm rõ chính xác lớp properties mà thư viện đăng ký.

### 3.2. Default trong code và default trong tài liệu phải giống nhau

Nếu record dùng `@DefaultValue("3s")`, tài liệu không được ghi `5s`. Nếu property có default phụ thuộc môi trường hoặc được tính ở runtime, hãy ghi “được xác định theo...” và giải thích quy tắc.

Đừng đặt default trong README nhưng không có trong binding code. Metadata, runtime behavior và tài liệu cần cùng một nguồn sự thật.

## 4. Tài liệu hóa từng property

Mỗi property công khai nên có tối thiểu:

- Tên canonical.
- Kiểu dữ liệu.
- Giá trị mặc định.
- Ý nghĩa và ảnh hưởng đến runtime.
- Giới hạn/validation.
- Ví dụ hợp lệ.
- Phiên bản được giới thiệu.
- Trạng thái deprecated và property thay thế nếu có.

Ví dụ bảng reference:

| Property | Kiểu | Default | Mô tả |
| --- | --- | --- | --- |
| `acme.enabled` | boolean | `true` | Bật hoặc tắt nhóm bean Acme core |
| `acme.endpoint` | URI | Không có; bắt buộc | Endpoint dịch vụ Acme |
| `acme.connect-timeout` | Duration | `3s` | Thời gian tối đa thiết lập kết nối |
| `acme.read-timeout` | Duration | `10s` | Thời gian chờ dữ liệu phản hồi |
| `acme.max-in-flight` | int | `64` | Số request đồng thời tối đa; từ 1 đến 4096 |
| `acme.codec.enabled` | boolean | `false` | Bật optional codec integration khi dependency tương ứng có mặt |
| `acme.codec.mode` | enum | `safe` | Chế độ codec được hỗ trợ |

Đây là bảng minh họa cho contract Acme ở bài học; giá trị default phải được đồng bộ với class properties thực tế của thư viện.

### 4.1. Viết mô tả có ích

Mô tả tốt trả lời “property thay đổi điều gì?” thay vì lặp lại tên key.

Chưa tốt:

~~~text
acme.read-timeout: Read timeout.
~~~

Tốt hơn:

~~~text
acme.read-timeout: Thời gian tối đa chờ dữ liệu phản hồi sau khi kết nối đã được thiết lập. Giá trị hỗ trợ các hậu tố ms, s, m và h.
~~~

Với boolean, mô tả nên bắt đầu bằng “Bật...” hoặc “Cho phép...”. Với collection, nói rõ đây là danh sách, thứ tự có ý nghĩa hay không, có hỗ trợ giá trị trùng không. Với Duration/DataSize, nêu đơn vị mặc định nếu định dạng cho phép bỏ hậu tố.

### 4.2. Javadoc cho properties metadata

Spring Boot khuyến nghị dùng Javadoc cho field của JavaBean properties. Với record, dùng class-level Javadoc có thẻ `@param` cho từng record component:

~~~java
/**
 * Configuration for the Acme client.
 *
 * @param enabled whether the Acme integration is enabled
 * @param endpoint service endpoint used by the client
 * @param connectTimeout maximum time allowed to establish a connection
 * @param readTimeout maximum time allowed to wait for a response
 * @param maxInFlight maximum number of concurrent requests
 */
@ConfigurationProperties(prefix = "acme")
public record AcmeProperties(
        boolean enabled,
        URI endpoint,
        Duration connectTimeout,
        Duration readTimeout,
        int maxInFlight
) {
}
~~~

Configuration metadata processor có thể thu thập mô tả này và cung cấp cho IDE. Giữ mô tả là plain text, ngắn, kết thúc bằng dấu chấm và không lặp lại default value nếu default đã được metadata biểu diễn riêng.

## 5. Sinh configuration metadata cho IDE

Spring Boot cung cấp annotation processor `spring-boot-configuration-processor`. Processor đọc các lớp `@ConfigurationProperties` khi compile và sinh file:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Metadata hỗ trợ IDE:
- Gợi ý tên property.
- Hiển thị kiểu dữ liệu.
- Hiển thị mô tả.
- Hiển thị default value.
- Gợi ý giá trị enum hoặc các giá trị được khai báo.
- Hiển thị deprecation và replacement.

### 5.1. Gradle

Trong module chứa `@ConfigurationProperties`:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Nếu dùng Kotlin, cấu hình annotation processing phù hợp với Kotlin build (ví dụ KAPT/KSP theo toolchain và plugin đang dùng). Không giả định Java `annotationProcessor` tự xử lý source Kotlin.

### 5.2. Maven

Khai báo processor trong compiler annotation processor path theo cấu hình Maven Compiler Plugin của dự án. Với dependency thông thường, Spring Boot documentation khuyến nghị đánh dấu configuration processor là optional trong POM để nó không trở thành runtime dependency bắt buộc của consumer.

Ví dụ phần dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Với Maven Compiler Plugin, cần đưa processor vào `annotationProcessorPaths` nếu dự án cấu hình xử lý annotation tường minh. Dùng version phù hợp với Spring Boot BOM của dự án.

### 5.3. Kiểm tra metadata được sinh

Sau build, kiểm tra file trong output classes hoặc JAR:

~~~bash
jar tf build/libs/acme-spring-boot-autoconfigure-1.2.0.jar
~~~

Tìm:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Đọc file JSON và xác nhận:
- Namespace đúng.
- Property name đúng canonical form.
- Type đúng.
- Description không rỗng.
- Default value khớp với code.
- Deprecated property có replacement đúng.

Không chỉnh tay file metadata được sinh. Sửa source/Javadoc/annotation rồi build lại.

## 6. Additional metadata cho trường hợp đặc biệt

Một số property không thể được suy ra tự động, chẳng hạn key được đọc trực tiếp từ Environment mà không bind vào `@ConfigurationProperties`, hoặc property cần gợi ý đặc biệt cho IDE.

Có thể thêm:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "acme.codec.mode",
      "type": "java.lang.String",
      "description": "Codec mode used by the optional integration.",
      "defaultValue": "safe"
    }
  ],
  "hints": [
    {
      "name": "acme.codec.mode",
      "values": [
        {
          "value": "safe",
          "description": "Use the conservative codec behavior."
        },
        {
          "value": "fast",
          "description": "Prefer throughput when the payload is trusted."
        }
      ]
    }
  ]
}
~~~

Additional metadata được annotation processor merge vào metadata chính. Nếu property đã được phát hiện tự động, một số thông tin như description, default và deprecation có thể được bổ sung/ghi đè theo metadata thủ công.

Chỉ thêm file này khi có giá trị. Nếu mọi property đã được biểu diễn đầy đủ bằng `@ConfigurationProperties`, không cần tạo file rỗng.

## 7. Deprecate property mà không làm người dùng bất ngờ

Property name có thể được lưu trong application.yml, Helm chart, environment variable và deployment automation. Đổi tên property là thay đổi contract.

Một lộ trình thường dùng:

1. Giới thiệu property mới.
2. Giữ property cũ trong một giai đoạn tương thích.
3. Đánh dấu property cũ deprecated và chỉ rõ property thay thế.
4. Nếu cần, xử lý property cũ bằng cách chuyển tiếp sang giá trị mới.
5. Công bố phiên bản dự kiến xóa.
6. Chỉ xóa sau giai đoạn migration đã công bố.

Với JavaBean properties, có thể dùng `@DeprecatedConfigurationProperty` trên getter của property cũ để sinh metadata deprecation:

~~~java
@ConfigurationProperties("acme")
public class AcmeProperties {

    private String endpointName;

    public String getEndpointName() {
        return this.endpointName;
    }

    public void setEndpointName(String endpointName) {
        this.endpointName = endpointName;
    }

    /**
     * @deprecated use {@code endpoint-name} instead.
     */
    @Deprecated
    @DeprecatedConfigurationProperty(
            replacement = "acme.endpoint-name",
            since = "2.1.0")
    public String getLegacyEndpoint() {
        return this.endpointName;
    }

    @Deprecated
    public void setLegacyEndpoint(String legacyEndpoint) {
        this.endpointName = legacyEndpoint;
    }
}
~~~

Đây là ví dụ JavaBean minh họa cho deprecation metadata. Getter cũ vẫn trả về giá trị đã được chuyển tiếp, do đó property cũ tiếp tục được bind trong giai đoạn warning.

Trong metadata JSON thủ công, có thể mô tả deprecation với:
- `level`: `warning` hoặc `error`.
- `reason`: lý do deprecated.
- `replacement`: tên property mới.
- `since`: phiên bản bắt đầu deprecated.

Mức warning có nghĩa property vẫn được quản lý/bind. Mức error có nghĩa property không còn được quản lý và không được bind. Hãy chọn hành vi phù hợp với chính sách tương thích của thư viện.

## 8. Công bố extension points được hỗ trợ

Tài liệu cần phân biệt rõ ba cách tùy chỉnh:

1. **Thay toàn bộ bean:** người dùng cung cấp implementation riêng của interface công khai.
2. **Tùy chỉnh default implementation:** người dùng cung cấp một hoặc nhiều customizer được thư viện gọi.
3. **Chọn giữa nhiều bean:** người dùng dùng `@Primary`, `@Qualifier` hoặc injection theo collection khi thư viện cho phép nhiều implementation.

Không phải mọi bean nội bộ đều là extension point. Chỉ công bố các kiểu, callback và điểm thay thế mà thư viện cam kết hỗ trợ. Nếu người dùng override một bean nội bộ không được tài liệu hóa, thay đổi implementation ở phiên bản sau có thể phá vỡ ứng dụng của họ.

### 8.1. Extension point qua interface công khai

Ví dụ API:

~~~java
package com.acme.api;

public interface AcmeClient {
    AcmeResponse send(AcmeRequest request);
}
~~~

Ứng dụng có thể cung cấp implementation riêng:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomAcmeConfiguration {

    @Bean
    AcmeClient customAcmeClient() {
        return new MyAcmeClient();
    }
}
~~~

Auto-configuration cung cấp default bean:

~~~java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient(AcmeProperties properties) {
        return new DefaultAcmeClient(properties.endpoint());
    }
}
~~~

Khi user bean `AcmeClient` được đăng ký trước auto-configuration, `@ConditionalOnMissingBean` không khớp và default client không được tạo.

Trong thư viện thật, hãy cung cấp đủ type information trong return type của bean method để bean conditions có thể đánh giá dựa trên kiểu được khai báo. Nếu có thể, dùng concrete return type khi phù hợp với public contract và không làm lộ implementation ngoài ý muốn.

### 8.2. Extension point qua customizer

Nếu người dùng chỉ muốn thay đổi một vài tùy chọn mà không cần viết lại toàn bộ client, một customizer contract có thể phù hợp hơn.

API minh họa:

~~~java
package com.acme.api;

public interface AcmeClientCustomizer {
    void customize(AcmeClient.Builder builder);
}
~~~

Auto-configuration áp dụng các customizer theo thứ tự:

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
AcmeClient acmeClient(
        AcmeProperties properties,
        ObjectProvider<AcmeClientCustomizer> customizers) {

    AcmeClient.Builder builder = AcmeClient.builder()
            .endpoint(properties.endpoint());

    customizers.orderedStream()
            .forEach(customizer -> customizer.customize(builder));

    return builder.build();
}
~~~

Người dùng có thể đăng ký:

~~~java
@Bean
AcmeClientCustomizer addTenantHeader() {
    return builder -> builder.defaultHeader("X-Tenant", "billing");
}
~~~

Tài liệu phải nói rõ:
- Customizer được gọi theo thứ tự nào.
- Có được khai báo nhiều customizer không.
- Customizer được áp dụng chỉ cho default client hay cả custom bean.
- Có được phép thay endpoint/timeout do properties cung cấp không.
- Nếu hai customizer thay cùng một giá trị, customizer nào thắng.

Trong ví dụ trên, customizer chỉ được gọi khi default bean được tạo. Nếu người dùng tự cung cấp toàn bộ `AcmeClient`, default factory không chạy và customizer không tự động sửa custom bean.

### 8.3. @Primary và @Qualifier không thay thế back-off

Nếu ứng dụng có hai bean cùng implement `AcmeClient`, `@Primary` có thể giúp Spring chọn một ứng viên khi injection theo type. `@Qualifier` giúp chọn bean cụ thể.

Nhưng:
- `@Primary` không ngăn auto-configuration tạo default bean.
- `@Qualifier` không làm `@ConditionalOnMissingBean` tự back off.
- Nếu mục tiêu là thay default, cung cấp bean phù hợp để missing-bean condition không khớp.
- Nếu mục tiêu là giữ nhiều implementation và chọn một, tài liệu hóa rõ qualifier hoặc collection injection.

## 9. Bean thay thế và thứ tự điều kiện

### 9.1. Dùng @ConditionalOnMissingBean cho default bean

Đây là pattern chuẩn để auto-configuration nhường quyền kiểm soát cho ứng dụng:

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
AcmeClient acmeClient(AcmeProperties properties) {
    return new DefaultAcmeClient(properties.endpoint());
}
~~~

Điều kiện được đánh giá dựa trên bean definitions đã được xử lý tới thời điểm đó. Vì vậy, Spring Boot khuyến nghị đặt `@ConditionalOnBean` và `@ConditionalOnMissingBean` trong auto-configuration, vốn được xử lý sau user-defined bean definitions.

Không nên dùng annotation này trên cấu hình người dùng thông thường để đoán các bean sẽ xuất hiện sau đó.

### 9.2. Phân biệt thay thế bean với tắt toàn bộ auto-configuration

| Hành động | Kết quả |
| --- | --- |
| User cung cấp `AcmeClient` | Default AcmeClient back off; các bean khác có thể vẫn được tạo |
| User cung cấp `AcmeClientCustomizer` | Customizer được áp dụng nếu default factory sử dụng customizer |
| User dùng `@Primary` | Chọn ứng viên ưu tiên khi autowire; default bean vẫn có thể tồn tại |
| User đặt `acme.enabled=false` | Các bean nằm trong nhánh property condition có thể không được tạo |
| User exclude `AcmeAutoConfiguration` | Toàn bộ configuration class đó không được áp dụng |

Tài liệu phải chỉ rõ property nào chỉ tắt một feature và exclusion nào loại toàn bộ cấu hình.

### 9.3. Đặt condition ở đúng phạm vi

Nếu một auto-configuration cung cấp nhiều bean độc lập, thường nên đặt `@ConditionalOnMissingBean` trên từng bean method cần override. Nếu đặt ở class-level, cả configuration class có thể không được đăng ký khi một điều kiện không khớp.

Ví dụ:
- Người dùng thay `AcmeClient`, nhưng vẫn muốn `AcmeHealthIndicator`.
- Người dùng thay `AcmeConnectionPool`, nhưng vẫn muốn `AcmeMetricsBinder`.

Tách điều kiện theo bean giúp customization có phạm vi nhỏ và dễ dự đoán.

## 10. Các cách loại trừ auto-configuration được hỗ trợ

Spring Boot cung cấp các cách khác nhau tùy phạm vi:

| Cách | Phạm vi | Dùng khi |
| --- | --- | --- |
| `@SpringBootApplication(exclude = ...)` | Một ứng dụng, tham chiếu class | Ứng dụng compile được với class cần loại |
| `@EnableAutoConfiguration(exclude = ...)` | Một ứng dụng, tham chiếu class | Cấu hình auto-configuration tường minh |
| `excludeName = "..."` | Một ứng dụng, dùng FQCN dạng chuỗi | Không muốn tham chiếu class trực tiếp |
| `spring.autoconfigure.exclude` | Một ứng dụng/environment | Cấu hình qua YAML, properties, environment hoặc command line |
| `@ImportAutoConfiguration(exclude = ...)` | Tập auto-configuration được import tường minh | Test hoặc cấu hình chỉ chọn một tập candidate |

### 10.1. Exclude bằng class

~~~java
@SpringBootApplication(
        exclude = {
                AcmeAutoConfiguration.class,
                AcmeMetricsAutoConfiguration.class
        })
public class BillingApplication {
}
~~~

Có thể dùng thuộc tính `exclude` trên `@EnableAutoConfiguration` tương tự. Đây là class literal nên ứng dụng cần có class trong compile classpath.

### 10.2. Exclude bằng tên class

~~~java
@SpringBootApplication(
        excludeName = {
                "com.acme.autoconfigure.AcmeAutoConfiguration",
                "com.acme.autoconfigure.AcmeMetricsAutoConfiguration"
        })
public class BillingApplication {
}
~~~

Dùng `excludeName` khi muốn lưu FQCN dưới dạng chuỗi, ví dụ trong một module không muốn phụ thuộc trực tiếp vào artifact chứa auto-configuration.

### 10.3. Exclude qua spring.autoconfigure.exclude

Trong `application.yml`:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
      - com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

Trong `application.properties`:

~~~properties
spring.autoconfigure.exclude=com.acme.autoconfigure.AcmeAutoConfiguration,com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

Property này phù hợp khi exclusion thay đổi theo môi trường triển khai. Hãy ghi rõ FQCN trong tài liệu và nhắc người dùng kiểm tra profile/property source hiệu lực nếu exclusion không hoạt động như mong đợi.

### 10.4. Exclude trong @ImportAutoConfiguration

`@ImportAutoConfiguration` cho phép import một tập auto-configuration cụ thể và loại một số class khỏi tập đó:

~~~java
@ImportAutoConfiguration(
        classes = {
                AcmeAutoConfiguration.class,
                AcmeMetricsAutoConfiguration.class
        },
        exclude = AcmeMetricsAutoConfiguration.class)
class AcmeTestConfiguration {
}
~~~

Annotation này thường hữu ích trong test hoặc khi cần một tập import tường minh. Nó áp dụng ordering rules như `@EnableAutoConfiguration`, nhưng giới hạn vào các class được chỉ định thay vì đọc toàn bộ ImportCandidates.

Trong Spring Boot 3.3, thuộc tính `exclude` của `@ImportAutoConfiguration` nhận class literals. Không giả định annotation này có thuộc tính `excludeName` như `@SpringBootApplication` hoặc `@EnableAutoConfiguration`.

### 10.5. Exclusion không giống feature toggle

Ví dụ:

~~~yaml
acme:
  codec:
    enabled: false
~~~

Đây là property điều khiển feature codec. Nó không nhất thiết loại toàn bộ `AcmeAutoConfiguration`.

Ngược lại:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
~~~

loại auto-configuration class khỏi quá trình áp dụng. Các bean do class đó cung cấp đều không được đăng ký qua nhánh này.

Nếu thư viện có nhiều feature độc lập, nên công bố property toggle cho từng feature thay vì yêu cầu người dùng loại toàn bộ auto-configuration để tắt một bean.

## 11. FQCN và exclusion là hợp đồng cần quản lý

Tên auto-configuration có thể xuất hiện trong:
- `excludeName`.
- `spring.autoconfigure.exclude`.
- `beforeName` và `afterName` của auto-configuration khác.
- Test, sample app, deployment config và tài liệu.

Vì vậy, đổi package hoặc tên lớp có thể ảnh hưởng consumer. Hãy rà soát mọi tham chiếu trước khi rename.

Spring Boot 3.4+ hỗ trợ replacement metadata tại:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Ví dụ:

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

Imports file chỉ liệt kê class mới. Replacement metadata giúp xử lý các tham chiếu cũ trong exclusions và before/after ordering được hỗ trợ. Spring Boot 3.3 không đọc replacement file này, vì vậy consumer 3.3 cần cập nhật FQCN hoặc thư viện phải giữ tên cũ trong dòng phát hành tương thích.

Đừng mô tả replacement metadata như cơ chế đổi tên tổng quát cho mọi chuỗi Java. Nó không sửa reflection string, direct class import, bean name hoặc property name tùy ý.

## 12. Viết reference guide cho người dùng starter

Một reference guide nên có các phần dễ tra cứu:

### 12.1. Quick start

Cho một dependency declaration, YAML tối thiểu và ví dụ inject API. Người dùng phải biết feature được bật mặc định hay cần opt-in.

### 12.2. Configuration properties

Một bảng cho mỗi namespace, gồm key, type, default, description, constraints và deprecation. Thêm ví dụ YAML có giá trị thực tế.

### 12.3. Customization

Liệt kê:
- Interface bean có thể thay.
- Bean customizer/callback được hỗ trợ.
- Thứ tự áp dụng customizer.
- Cách xử lý nhiều bean.
- Hành vi back-off của default bean.
- Những bean nội bộ không phải extension point công khai.

### 12.4. Exclusions

Ghi đầy đủ FQCN của auto-configuration và các cách exclude được hỗ trợ. Nói rõ phạm vi: loại toàn bộ class hay chỉ tắt một feature.

### 12.5. Compatibility and migration

Với mỗi thay đổi public contract, ghi:
- Phiên bản giới thiệu.
- Phiên bản deprecated.
- Property hoặc class thay thế.
- Phiên bản cuối cùng còn hỗ trợ đường cũ.
- Cách cập nhật ứng dụng.
- Khác biệt giữa Spring Boot versions nếu API metadata thay đổi.

Không chỉ ghi “đã cải thiện cấu hình”. Hãy cung cấp key cũ, key mới và YAML trước/sau.

## 13. Kiểm thử tài liệu và hành vi auto-configuration

Tài liệu là một phần của contract, vì vậy cần kiểm tra ví dụ và bảng property cùng với code.

### 13.1. Test default properties và custom bean back-off

**Tệp:** `src/test/java/com/acme/autoconfigure/AcmeAutoConfigurationTests.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;
import java.time.Duration;

import com.acme.api.AcmeClient;
import com.acme.api.AcmeRequest;
import com.acme.api.AcmeResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class));

    @Test
    void bindsDocumentedDefaultsAndProperties() {
        this.runner
                .withPropertyValues(
                        "acme.endpoint=https://tenant.example",
                        "acme.connect-timeout=5s",
                        "acme.max-in-flight=128")
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);

                    AcmeProperties properties =
                            context.getBean(AcmeProperties.class);

                    assertThat(properties.enabled()).isTrue();
                    assertThat(properties.endpoint())
                            .isEqualTo(URI.create("https://tenant.example"));
                    assertThat(properties.connectTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                    assertThat(properties.readTimeout())
                            .isEqualTo(Duration.ofSeconds(10));
                    assertThat(properties.maxInFlight()).isEqualTo(128);
                });
    }

    @Test
    void userClientReplacesDefaultClient() {
        this.runner
                .withPropertyValues("acme.endpoint=https://tenant.example")
                .withUserConfiguration(UserClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class))
                            .isInstanceOf(CustomAcmeClient.class);
                });
    }

    @Test
    void invalidConcurrencyValueFailsValidation() {
        this.runner
                .withPropertyValues(
                        "acme.endpoint=https://tenant.example",
                        "acme.max-in-flight=0")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    jakarta.validation.ConstraintViolationException.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new CustomAcmeClient();
        }
    }

    static class CustomAcmeClient implements AcmeClient {
        @Override
        public AcmeResponse send(AcmeRequest request) {
            throw new UnsupportedOperationException(
                    "Not exercised by this bean back-off test");
        }
    }
}
~~~

Đây là mẫu test cho contract properties và bean back-off. Các kiểu `AcmeClient`, `AcmeProperties`, `AcmeAutoConfiguration` và `DefaultAcmeClient` phải được định nghĩa trong source module tương ứng; test không tự tạo implementation mặc định. Test validation yêu cầu Jakarta Validation provider có mặt trong test runtime.

### 13.2. Test property condition và feature toggle

Nếu codec là optional feature, kiểm thử property condition riêng:

~~~java
@Test
void codecFeatureCanBeDisabledWithoutExcludingCore() {
    runner.withPropertyValues(
            "acme.endpoint=https://tenant.example",
            "acme.codec.enabled=false")
            .run(context -> {
                assertThat(context).hasSingleBean(AcmeClient.class);
                assertThat(context).doesNotHaveBean(AcmeCodec.class);
            });
}
~~~

Test này chứng minh feature toggle chỉ ảnh hưởng codec; core client vẫn được đăng ký.

### 13.3. Test global exclusion đúng qua auto-configuration selector

Nếu cần kiểm tra `spring.autoconfigure.exclude`, hãy tạo test integration đi qua `@EnableAutoConfiguration` hoặc `@SpringBootApplication`, để Boot thực sự đọc danh sách candidate và exclusions. Không chỉ dùng `AutoConfigurations.of(AcmeAutoConfiguration.class)`, vì cách import trực tiếp này không kiểm tra toàn bộ selector/import metadata như một ứng dụng Boot thật.

Ví dụ cấu hình test:

~~~java
@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
class ExclusionTestApplication {
}
~~~

Test có thể khởi chạy context với property:

~~~properties
spring.autoconfigure.exclude=com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Sau đó xác nhận các bean do auto-configuration đó cung cấp không xuất hiện. Với `@ImportAutoConfiguration(exclude=...)`, tạo một test configuration riêng dùng chính annotation này.

### 13.4. Kiểm tra metadata và ví dụ trong JAR

Sau build:
- Xác nhận `META-INF/spring-configuration-metadata.json` có trong JAR.
- Kiểm tra property names, defaults, descriptions và deprecation.
- Xác nhận `AutoConfiguration.imports` liệt kê đúng candidate.
- Chạy sample consumer chỉ thêm starter.
- Nếu có deprecation, compile/run test với cả property cũ và mới trong giai đoạn tương thích.

## 14. Những lỗi thường gặp khi tài liệu hóa

1. **Không ghi namespace riêng.** Property có thể xung đột với Spring Boot hoặc thư viện khác; dùng namespace thuộc sở hữu của starter.
2. **Dùng long cho timeout nhưng không nói đơn vị.** Chọn Duration hoặc mô tả rõ đơn vị.
3. **Default trong tài liệu khác default trong code.** Đồng bộ @DefaultValue, field initializer và metadata.
4. **Chỉ ghi tên property.** Người dùng cần kiểu, default, mô tả, constraint và ví dụ.
5. **Không sinh configuration metadata.** IDE không có completion/description; thêm configuration processor.
6. **Sửa trực tiếp file metadata generated.** Build sau sẽ ghi đè; dùng Javadoc hoặc additional metadata.
7. **Không đánh dấu property cũ deprecated.** Người dùng không có hướng migration; cung cấp replacement và since version.
8. **Coi mọi bean là extension point.** Implementation nội bộ không phải public contract; chỉ công bố interface/callback được hỗ trợ.
9. **Dùng @Primary để thay default.** Default bean vẫn có thể tồn tại; dùng @ConditionalOnMissingBean cho back-off.
10. **Dùng @Qualifier để tắt auto-configuration.** Qualifier chỉ chọn ứng viên khi inject; không loại configuration.
11. **Đặt ConditionalOnMissingBean trên user configuration.** Điều kiện có thể chạy trước các bean definitions mong đợi; ưu tiên đặt trong auto-configuration.
12. **Không công bố thứ tự customizer.** Nhiều customizer có thể ghi đè nhau; định nghĩa quy tắc ordering và test.
13. **Nhầm feature toggle với exclusion.** Property tắt một feature; exclusion loại cả auto-configuration class.
14. **Không ghi FQCN của auto-configuration.** Consumer không biết chuỗi cần dùng cho excludeName/property.
15. **Dùng nhầm excludeName cho @ImportAutoConfiguration.** Spring Boot 3.3 @ImportAutoConfiguration có thuộc tính exclude kiểu Class; không có excludeName.
16. **Không test selector khi kiểm tra spring.autoconfigure.exclude.** Import trực tiếp auto-configuration không xác minh global exclusion pipeline.
17. **Đổi package auto-configuration nhưng quên exclusion references.** Rà soát YAML, source, ordering và test; dùng replacement metadata trên Boot 3.4+ khi phù hợp.
18. **Không công bố khác biệt Spring Boot version.** Một metadata feature mới có thể không được phiên bản cũ đọc; nêu rõ dải tương thích.
19. **Tài liệu chỉ có YAML mà không có hành vi.** Nói rõ bean nào xuất hiện, bean nào back off và phạm vi property condition.
20. **Ví dụ không được kiểm tra.** Dùng sample consumer và test context để bảo đảm tài liệu không mô tả hành vi tưởng tượng.

## 15. Checklist trước khi phát hành starter

### Configuration properties

- [ ] Namespace thuộc sở hữu của thư viện.
- [ ] Tên canonical dùng kebab-case.
- [ ] Mỗi key có type, default, description và constraint.
- [ ] Duration/DataSize được dùng khi phù hợp.
- [ ] Default trong code khớp tài liệu.
- [ ] Configuration processor được cấu hình.
- [ ] Generated metadata được kiểm tra trong JAR.
- [ ] Additional metadata chỉ dùng cho trường hợp đặc biệt.
- [ ] Deprecated property có replacement và mốc phiên bản.

### Extension points và bean behavior

- [ ] Public API/interface thay thế được công bố.
- [ ] Customizer/callback được hỗ trợ được mô tả.
- [ ] Thứ tự customizer và phạm vi áp dụng rõ ràng.
- [ ] Default bean dùng @ConditionalOnMissingBean khi cho phép override.
- [ ] Phân biệt @Primary, @Qualifier và bean back-off.
- [ ] Bean nội bộ không bị mô tả nhầm thành extension point.

### Exclusions

- [ ] Có danh sách FQCN auto-configuration công khai.
- [ ] Có ví dụ exclude class và excludeName.
- [ ] Có ví dụ spring.autoconfigure.exclude.
- [ ] Có ví dụ @ImportAutoConfiguration(exclude=...) khi cần.
- [ ] Phân biệt feature property với loại trừ toàn configuration.
- [ ] Đã rà soát FQCN khi rename class.
- [ ] Có hướng dẫn khác biệt theo Spring Boot version.

### Verification

- [ ] Test default property binding.
- [ ] Test validation fail.
- [ ] Test custom bean back-off.
- [ ] Test customizer ordering nếu có.
- [ ] Test feature toggle.
- [ ] Test global exclusion qua @EnableAutoConfiguration.
- [ ] Test targeted @ImportAutoConfiguration exclusion.
- [ ] Kiểm tra configuration metadata trong artifact.
- [ ] Sample consumer chạy với starter được publish.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao starter nên dùng namespace riêng như `acme`?

**Đáp án:** Để tránh xung đột với namespace do Spring Boot hoặc thư viện khác sở hữu, đồng thời giúp người dùng nhận diện rõ property thuộc thư viện nào.

**Câu 2.** File metadata nào hỗ trợ IDE gợi ý configuration properties?

**Đáp án:** `META-INF/spring-configuration-metadata.json`, thường được sinh bởi `spring-boot-configuration-processor`.

**Câu 3.** Muốn người dùng thay default AcmeClient, nên dùng cơ chế nào?

**Đáp án:** Công bố interface AcmeClient và đặt default bean dưới `@ConditionalOnMissingBean(AcmeClient.class)`. Khi user cung cấp bean phù hợp, default sẽ back off.

**Câu 4.** @Primary có ngăn auto-configuration tạo default bean không?

**Đáp án:** Không. @Primary chỉ ảnh hưởng lựa chọn candidate khi autowiring; muốn default bean back off, dùng missing-bean condition.

**Câu 5.** Khác biệt giữa `acme.codec.enabled=false` và `spring.autoconfigure.exclude=...` là gì?

**Đáp án:** Property feature toggle có thể chỉ tắt codec; global exclusion loại toàn bộ auto-configuration được chỉ định.

**Câu 6.** Trong Spring Boot 3.3, @ImportAutoConfiguration loại class bằng thuộc tính nào?

**Đáp án:** Thuộc tính `exclude` nhận các class literals. Không giả định có `excludeName` trong annotation này.

**Câu 7.** Vì sao test spring.autoconfigure.exclude cần đi qua @EnableAutoConfiguration?

**Đáp án:** Vì cần xác minh selector đọc candidate list và global exclusion. Nạp trực tiếp bằng AutoConfigurations.of không kiểm tra đầy đủ pipeline đó.

**Câu 8.** Khi đổi tên property, tài liệu migration cần nêu gì?

**Đáp án:** Key cũ, key mới, phiên bản deprecated, thời gian còn hỗ trợ, hành vi chuyển tiếp và ví dụ YAML trước/sau.

## 17. Ghi nhớ

Tài liệu của một starter cần làm rõ bốn hợp đồng: property được hỗ trợ, extension point được cam kết, cách default bean nhường cho user bean và cách loại trừ auto-configuration. Các hợp đồng này ảnh hưởng trực tiếp đến cấu hình, source code, deployment và khả năng nâng cấp của ứng dụng.

Dùng `@ConfigurationProperties` với namespace riêng, kiểu dữ liệu có ý nghĩa, default và validation rõ ràng. Sinh configuration metadata để IDE cung cấp completion và mô tả. Công bố interface/customizer được hỗ trợ; dùng `@ConditionalOnMissingBean` để default bean back off; giải thích rõ `@Primary` và `@Qualifier` chỉ điều khiển autowiring.

Cuối cùng, liệt kê FQCN và các exclusion mechanisms: class literal, excludeName, `spring.autoconfigure.exclude` và `@ImportAutoConfiguration(exclude=...)`. Kiểm thử binding, override, feature toggle và global exclusion qua đúng selector. Khi public contract thay đổi, công bố migration path cùng phiên bản hỗ trợ.

### Tài liệu Spring Boot 3.3 chính thức

- [Creating Your Own Auto-configuration — configuration keys, customization and testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Configuration Metadata — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Configuration Metadata Format — Spring Boot](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html)
- [@ConfigurationProperties Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [@DeprecatedConfigurationProperty Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/DeprecatedConfigurationProperty.html)
- [@ConditionalOnMissingBean Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [@EnableAutoConfiguration Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html)
- [@ImportAutoConfiguration Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html)
