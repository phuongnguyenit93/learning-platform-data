# Quản lý khóa tùy chọn và khóa bắt buộc cho từng môi trường trong Spring Boot

## 1. Bài toán cần giải quyết

Một ứng dụng Spring Boot thường chạy ở nhiều môi trường: local, development, test, staging, production. Mỗi môi trường có thể dùng cùng application artifact nhưng cần cấu hình khác nhau. Ví dụ local có thể dùng dịch vụ giả lập, trong khi production buộc phải có endpoint thật, thông tin xác thực và các giới hạn vận hành rõ ràng.

Giả sử nhóm cấu hình:

~~~yaml
app:
  partner:
    enabled: true
    base-url: https://partner.example.org
    api-token: "DEMO-ONLY"
    connect-timeout: 3s
    max-retries: 2
~~~

Câu hỏi thiết kế không chỉ là giá trị của từng khóa mà là:

- Khóa nào **bắt buộc ở mọi môi trường**?
- Khóa nào chỉ bắt buộc khi một feature được bật?
- Khóa nào có default an toàn và có thể không khai báo?
- Khóa nào bắt buộc ở staging/production nhưng có thể bỏ qua khi chạy local?
- Thiếu khóa và khóa có giá trị rỗng có được xem như nhau không?
- Hệ thống nên fail fast hay dùng fallback?
- Khi đổi tên khóa, làm cách nào nâng cấp mà không làm hỏng deployment cũ?
- Kiểm thử thế nào để phát hiện lỗi trước khi phát hành?

Mục tiêu của bài là thiết kế **hợp đồng cấu hình theo môi trường**, không chỉ viết một file `application-prod.yml`. Hợp đồng đó cần thể hiện bằng schema Java, validation, nguồn cấp secret, tài liệu và test.

## 2. Những khái niệm cần tách biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Required property | Phải được cung cấp và hợp lệ trong phạm vi xác định | `app.partner.base-url` |
| Optional property | Có thể không có mà ứng dụng vẫn hợp lệ | `app.partner.proxy-host` |
| Default value | Giá trị được sử dụng khi không có cấu hình được cung cấp | `connect-timeout=3s` |
| Conditionally required | Chỉ bắt buộc khi một điều kiện đúng | `api-token` khi `partner.enabled=true` |
| Environment-specific required | Bắt buộc ở một số môi trường | Token thật ở production |
| Invalid value | Có khóa nhưng giá trị không đáp ứng kiểu/ràng buộc | `max-retries=-5` |
| Missing value | Không có nguồn có hiệu lực cung cấp khóa | Không có `base-url` |
| Empty/blank value | Khóa có mặt nhưng mang giá trị rỗng hoặc whitespace | `api-token=""` |

Một thuộc tính có thể là optional về mặt sự hiện diện nhưng nếu được cấp thì vẫn phải **hợp lệ về kiểu và phạm vi**. Ví dụ `max-retries` có default 2, nhưng khi người dùng ghi `-20` thì không được âm thầm đổi về 2.

Mặt khác, một khóa required trong production không nhất thiết required trong local. Bài toán cần một quy tắc tường minh để tránh biến những khác biệt môi trường thành hành vi ngẫu nhiên.

## 3. Đừng nhầm "có key" với "có giá trị sử dụng được"

Xét ba trường hợp:

~~~properties
# Không hề có app.partner.api-token
~~~

~~~properties
app.partner.api-token=
~~~

~~~properties
app.partner.api-token=   
~~~

Với target kiểu `String`, các tình huống có thể được bind thành `null`, chuỗi rỗng hoặc chuỗi chỉ gồm whitespace tùy nguồn và pipeline.

Nếu yêu cầu credential có nội dung, annotation:

~~~java
@NotNull String apiToken
~~~

không đủ, vì chuỗi `""` vẫn khác null.

Lựa chọn thường phù hợp:

~~~java
@NotBlank String apiToken
~~~

trong một bean cấu hình được bật validation. `@NotBlank` kiểm tra cả null, chuỗi rỗng và chuỗi chỉ có khoảng trắng. Tuy nhiên, nó không chứng minh token còn hiệu lực, có đúng scope hoặc thuộc đúng environment.

Trong tài liệu schema, nên ghi rõ ý nghĩa của "required": chỉ cần có value, phải không blank, phải đạt format, hay còn phải thỏa quan hệ với field khác.

## 4. Bảng hợp đồng cấu hình theo môi trường

Trước khi viết Java, tạo một bảng dễ review:

| Thuộc tính | Local | Test | Staging | Production | Default / Quy tắc |
| --- | --- | --- | --- | --- | --- |
| `app.partner.enabled` | Optional | Optional | Required | Required | Local/test mặc định false |
| `app.partner.base-url` | Khi enabled | Khi enabled | Khi enabled | Khi enabled | Không default đến production |
| `app.partner.api-token` | Optional khi dùng stub | Fake token nếu cần | Required khi enabled | Required khi enabled | Cấp qua secret source |
| `app.partner.connect-timeout` | Optional | Optional | Optional | Optional | `3s`, phải dương |
| `app.partner.max-retries` | Optional | Optional | Optional | Optional | `2`, trong khoảng 0–5 |
| `app.partner.proxy-host` | Optional | Optional | Optional | Optional | Không có nghĩa không dùng proxy |
| `app.partner.tls-enabled` | Optional | Optional | Required | Required | Production buộc true theo policy |

Bảng này chỉ là một **ví dụ chính sách**. Điều kiện TLS, proxy hoặc feature flags phải dựa trên threat model và yêu cầu thực tế của ứng dụng.

Những cột cần có trong tài liệu schema của một dự án lớn:

- Tên property canonical và kiểu Java.
- Giá trị bắt buộc/tùy chọn theo environment.
- Default và ý nghĩa của default.
- Giá trị hợp lệ hoặc constraint.
- Điều kiện phụ thuộc field khác.
- Nguồn được phép cấp property.
- Có phải secret hay không.
- Ai là owner, khi thay đổi cần review của ai.
- Version app/schema hỗ trợ property.
- Cách migration/deprecation khi nâng cấp.

Bảng hợp đồng nên được version hóa cùng với code hoặc hệ thống tài liệu có audit.

## 5. Một schema Java với các yêu cầu cơ bản

Ví dụ record:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        @NotNull @DefaultValue("false") Boolean enabled,
        String baseUrl,
        String apiToken,
        @NotNull @DefaultValue("3s") Duration connectTimeout,
        @Min(0) @Max(5) @DefaultValue("2") int maxRetries
) {}
~~~

Cách hiểu:

- `enabled` có default `false`, nên **không bắt buộc người triển khai cấp** trong ví dụ này.
- `connectTimeout` có default 3 giây, không cần cấp nếu chấp nhận giá trị này.
- `maxRetries` có default 2, nhưng nếu được cấp `-5` thì vi phạm `@Min(0)`.
- `baseUrl` và `apiToken` hiện vẫn cho phép null; quy tắc bắt buộc có điều kiện sẽ được thiết kế riêng bên dưới.
- `@Validated` yêu cầu kiểm tra các constraint khi bean `@ConfigurationProperties` được tạo bằng cơ chế phù hợp và có Bean Validation provider.

Khi cần bắt buộc `enabled` **phải được khai báo tường minh** ở production, không nên gắn default `false` cho chính field này trong schema production. Default phù hợp cho local có thể không phù hợp cho production.

## 6. Dependency validation

Với Spring Boot 3.x, constraint Jakarta Bean Validation thường cần:

### Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

### Gradle Groovy DSL

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Các annotation phổ biến:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
~~~

Không nên trộn namespace `javax.validation` cũ và `jakarta.validation` mới khi sử dụng Spring Boot 3.x.

Đăng ký properties bean phù hợp:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

Hoặc dùng `@EnableConfigurationProperties(PartnerProperties.class)` tại một configuration class có chủ đích.

**Configuration processor** dành cho metadata IDE khác với **validation starter**; thêm `spring-boot-configuration-processor` không tự thực thi `@NotBlank`.

## 7. Primitive và wrapper khi kiểm tra khóa bắt buộc

Xét:

~~~java
@ConfigurationProperties(prefix = "app.jobs")
public record JobProperties(
        int workers,
        boolean enabled
) {}
~~~

Khi không có property, primitive có thể nhận giá trị mặc định của Java như `0` và `false`. Trong trường hợp đó, code khó phân biệt:

- Người triển khai chủ động đặt `enabled=false`.
- Người triển khai quên khai báo `enabled`.

Nếu cần kiểm tra sự hiện diện, dùng wrapper:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.jobs")
public record JobProperties(
        @NotNull @Min(1) Integer workers,
        @NotNull Boolean enabled
) {}
~~~

Khi không có giá trị và không có default, các trường nullable có thể thành null để validator từ chối.

Lưu ý:

- `@NotNull Boolean enabled` cho phép cả `true` và `false`.
- `@NotNull boolean enabled` không có tác dụng phát hiện thiếu vì primitive không thể null.
- `@Min(1) int workers` có thể từ chối 0 nhưng không nói rõ đó là thiếu hay được cấp 0.
- Một wrapper nullable với `@NotNull` thích hợp khi cần phân biệt rõ hợp đồng required.

## 8. `@NotNull`, `@NotEmpty` và `@NotBlank`

| Constraint | Dùng cho | Vi phạm |
| --- | --- | --- |
| `@NotNull` | Object nullable | Null |
| `@NotEmpty` | String, collection, map, array | Null hoặc rỗng |
| `@NotBlank` | String/CharSequence | Null, rỗng hoặc toàn whitespace |

Ví dụ:

~~~java
public record MailSettings(
        @NotBlank String senderAddress,
        @NotEmpty java.util.List<String> recipients,
        @NotNull Boolean sendEnabled
) {}
~~~

Nếu `senderAddress="  "`, `@NotBlank` phát hiện. Nếu `recipients=[]`, `@NotEmpty` phát hiện. Nếu `sendEnabled=false`, `@NotNull` **không** báo lỗi.

Không dùng `@NotBlank` trên `Duration` hay `Integer`; constraint này không dành cho các kiểu đó.

Nhiều field cũng có quy tắc phạm vi, ví dụ `@Min`/`@Max` hoặc `@Size`. Required không đồng nghĩa hợp lệ: một String có nội dung vẫn có thể là URL hoặc e-mail sai.

## 9. Default qua `@DefaultValue` khác với required

Constructor binding với record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        @DefaultValue("3s") Duration connectTimeout,
        @DefaultValue("2") int maxRetries
) {}
~~~

Khi không có khóa tương ứng, Binder có thể dùng default trong annotation. Nhưng nếu runtime cấp:

~~~properties
app.http.connect-timeout=tomorrow
~~~

thì default `3s` không tự sửa giá trị sai kiểu. Conversion có thể thất bại.

Tương tự:

~~~properties
app.http.max-retries=-1
~~~

vẫn cần constraint hoặc business validation nếu yêu cầu số không âm.

Một nguyên tắc quản lý:

- **Default:** vắng mặt được phép và có giá trị thay thế hợp lý.
- **Required:** vắng mặt là lỗi cần sửa ở nguồn cấu hình.
- **Optional/no default:** vắng mặt có ý nghĩa riêng và code phải xử lý null/absence có chủ đích.

Không thêm default bừa bãi chỉ để tránh startup failure; làm vậy dễ che lỗi deployment.

## 10. Default trong YAML và placeholder

Ví dụ:

~~~yaml
app:
  http:
    connect-timeout: "${HTTP_CONNECT_TIMEOUT:3s}"
~~~

Nếu environment variable `HTTP_CONNECT_TIMEOUT` không có, placeholder có thể dùng `3s`.

Ngược lại:

~~~yaml
app:
  partner:
    api-token: "${PARTNER_API_TOKEN}"
~~~

không có default. Khi property được thực sự resolve và bind, việc thiếu biến cần được xử lý như một lỗi nếu đây là giá trị bắt buộc.

Một ví dụ dễ gây hiểu nhầm:

~~~yaml
app:
  partner:
    api-token: "${PARTNER_API_TOKEN:}"
~~~

Dấu hai chấm cung cấp **fallback rỗng**. Nếu property được bind sang `String`, giá trị rỗng có thể tồn tại dù biến không được cấp. Khi token là required, `@NotBlank` là một lớp bảo vệ quan trọng.

Không nên chỉ dựa vào placeholder không default để kết luận mọi đường code đều fail fast: nếu property không bao giờ được đọc hoặc bean không được tạo, lỗi có thể không xuất hiện trong startup mong đợi.

## 11. `Optional<T>` không phải mặc định nên dùng trong `@ConfigurationProperties`

Java có `Optional<String>`, nhưng không nên mặc định khai báo:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        java.util.Optional<String> proxyHost
) {}
~~~

rồi cho rằng Binder luôn cung cấp `Optional.empty()` khi thiếu property. Tài liệu Spring Boot không khuyến nghị `Optional` làm property trong `@ConfigurationProperties`; khi không có giá trị, kết quả có thể là null thay vì một Optional như kỳ vọng.

Lựa chọn dễ quản lý hơn:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        String proxyHost
) {}
~~~

Sau đó ở lớp sử dụng:

~~~java
if (properties.proxyHost() != null
        && !properties.proxyHost().isBlank()) {
    configureProxy(properties.proxyHost());
}
~~~

Nếu ứng dụng thực sự cần mô hình Optional nội bộ, có thể chuyển đổi sau bước binding, với semantics được test riêng.

## 12. Environment-specific required: hai cách thiết kế

Có hai mẫu phổ biến.

**Cách A — Một schema, yêu cầu có điều kiện theo field.** Ví dụ `apiToken` chỉ bắt buộc khi `enabled=true`. Cách này không phụ thuộc tên profile, phù hợp khi điều kiện chính là feature mode.

**Cách B — Schema/bean registration riêng theo profile.** Ví dụ production có nhóm compliance properties bắt buộc, local không tạo bean đó. Cách này thích hợp khi hợp đồng thật sự khác giữa các môi trường.

Không nên biến tên profile thành một chuỗi được truy cập tự do ở mọi lớp trong ứng dụng để kiểm tra từng field. Hợp đồng càng phân tán, càng khó đảm bảo đồng nhất.

Trong cả hai cách, file YAML riêng theo profile chỉ là **nguồn giá trị**. Quy tắc required nên được thể hiện bằng Java validation và/hoặc chính sách triển khai có thể kiểm thử.

## 13. Required có điều kiện: khi feature được bật

Giả sử token chỉ cần thiết nếu thực sự gọi upstream:

~~~yaml
app:
  partner:
    enabled: false
~~~

Với feature tắt, thiếu token là hợp lệ. Nhưng nếu:

~~~yaml
app:
  partner:
    enabled: true
    base-url: https://partner.example.org
~~~

thì thiếu token phải làm fail fast.

Một cách mô tả bất biến ngay tại constructor:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        @DefaultValue("false") boolean enabled,
        String baseUrl,
        String apiToken,
        @DefaultValue("3s") Duration connectTimeout
) {
    public PartnerProperties {
        if (enabled) {
            if (baseUrl == null || baseUrl.isBlank()) {
                throw new IllegalArgumentException(
                        "app.partner.base-url is required when enabled");
            }
            if (apiToken == null || apiToken.isBlank()) {
                throw new IllegalArgumentException(
                        "app.partner.api-token is required when enabled");
            }
        }
        if (connectTimeout == null
                || connectTimeout.isZero()
                || connectTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.partner.connect-timeout must be positive");
        }
    }
}
~~~

Đây là **constructor invariant**, không phải Jakarta Bean Validation. Nó giúp không tạo được object sai nhưng exception message khác so với các constraint Bean Validation.

Quan trọng: exception chỉ nêu **tên property**, không in giá trị token hoặc toàn bộ config record.

Nếu cần tái sử dụng hoặc muốn constraint errors theo chuẩn Jakarta, có thể viết custom class-level constraint kiểm tra quan hệ `enabled/baseUrl/apiToken` thay vì dùng constructor.

## 14. Không phụ thuộc riêng vào `@ConditionalOnProperty` để kiểm tra required

Một configuration bean có thể phụ thuộc cờ:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PartnerConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.partner",
            name = "enabled",
            havingValue = "true"
    )
    PartnerClient partnerClient(PartnerProperties properties) {
        return new PartnerClient(
                properties.baseUrl(),
                properties.apiToken()
        );
    }
}
~~~

`PartnerClient` là class giả định do ứng dụng định nghĩa.

Condition trên quyết định **có tạo bean hay không**, chứ không tự kiểm tra rằng token có nội dung. Nếu `enabled=true` và token null, bean có thể thất bại muộn hoặc cấu hình sai lọt qua nếu không validation.

Ngược lại, nếu bean không được tạo khi feature tắt, việc token không có có thể là hợp lệ theo hợp đồng.

Cần phân biệt:

- **Conditional bean registration:** tạo bean trong điều kiện nào.
- **Required property validation:** các field cần đạt điều kiện nào.
- **Runtime health:** remote service có hoạt động hay không.

Ba trách nhiệm không thay thế cho nhau.

## 15. `@ConditionalOnProperty` và giá trị thiếu

Ví dụ:

~~~java
@ConditionalOnProperty(
        prefix = "app.partner",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
~~~

Khi property không có, điều kiện thường không match theo chính sách này. Nhưng đó không có nghĩa một môi trường bắt buộc phải khai báo explicit `enabled=false`.

Nếu production yêu cầu **phải có key `enabled`**, cần cơ chế required riêng, ví dụ một wrapper `Boolean` không có default, `@NotNull` trong properties được đăng ký tại production hoặc kiểm tra deploy-time.

`matchIfMissing=true` có thể cho phép bean được tạo khi property thiếu; đây là quyết định về đăng ký bean, không phải lời xác nhận rằng thiếu khóa là hợp lệ theo business contract.

Đặc biệt với collection/indexed properties, tài liệu Spring Boot lưu ý hạn chế khi dùng `@ConditionalOnProperty` trên cấu trúc collection; đừng biến nó thành công cụ kiểm tra tổng quát schema.

## 16. Phân tách bean production và non-production

Khi chính sách required khác nhau rõ rệt, có thể đăng ký bean theo profile.

Ví dụ contract chỉ dành cho production:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partner")
public record ProductionPartnerProperties(
        @NotNull Boolean enabled,
        @NotBlank String baseUrl,
        @NotBlank String apiToken
) {}
~~~

Bean registration:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("prod")
@EnableConfigurationProperties(ProductionPartnerProperties.class)
public class ProductionPartnerConfiguration {}
~~~

Với mẫu này, không đồng thời quét `ProductionPartnerProperties` bằng một `@ConfigurationPropertiesScan` rộng không kiểm soát, vì có thể làm nó được đăng ký cả ngoài `prod`. Hãy chọn **một chiến lược đăng ký bean rõ ràng** và có test xác nhận.

Ở môi trường non-production, có thể dùng một loại properties khác hoặc một mock/stub client được đăng ký theo `@Profile("!prod")`. Khi dùng hai class chung prefix, tránh inject sai type và tránh duplicate bean gây mơ hồ.

Tên profile `prod` chỉ là quy ước dự án, không được Spring Boot tự hiểu là production an toàn. Pipeline triển khai cần đảm bảo profile thực tế được bật đúng.

## 17. Không đặt validation theo environment bằng cách đoán hostname

Một anti-pattern:

~~~java
if (hostname.contains("prod")) {
    requireApiToken();
}
~~~

hoặc:

~~~java
if (System.getenv("ENV_NAME").equals("production")) {
    ...
}
~~~

mà không kiểm soát null và cơ chế cấp biến.

Rủi ro:

- Tên hostname có thể thay đổi khi auto-scaling.
- Staging có thể vô tình có substring `prod`.
- CI không tái hiện điều kiện đúng.
- Logic required phân tán, không có hợp đồng tập trung.
- Một biến env sai có thể làm tắt validation trong môi trường quan trọng.

Nên dùng những tín hiệu được quản lý tường minh: profile, deployment policy, cấu hình mode rõ ràng và test đảm bảo đúng sự kết hợp.

Với ràng buộc bảo mật quan trọng, đặt thêm kiểm tra ở **deployment policy** thay vì chỉ tin một cờ runtime mà người triển khai có thể override.

## 18. Profile chỉ chọn nguồn/configuration, không tự thực thi required schema

Ví dụ production:

~~~yaml
# application-prod.yml
app:
  partner:
    enabled: true
    base-url: https://partner.example.org
    api-token: "${PARTNER_API_TOKEN}"
~~~

File này giúp cung cấp giá trị khi `prod` được kích hoạt. Nhưng required semantics đến từ kiểu properties và validation được đăng ký, không phải chỉ vì tên file có chữ `prod`.

Một vài trường hợp cần test:

1. `prod` bật và biến `PARTNER_API_TOKEN` có giá trị: bean tạo được.
2. `prod` bật và biến không có: quá trình bind/resolve/validation phải thất bại theo thiết kế.
3. `prod` bật nhưng biến là chuỗi rỗng: `@NotBlank` phải từ chối.
4. `prod` không bật: có thể dùng stub, không cố bind bean production vô cớ.
5. Cấu hình từ CLI/env ghi đè `enabled` hoặc token: hệ thống xử lý theo đúng policy.

Nếu environment có nhiều profile cùng hoạt động, xác định rõ thứ tự và ràng buộc kỳ vọng; không suy diễn chỉ từ một tên profile.

## 19. `spring.config.import=optional:` khác với khóa optional

Ví dụ:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Từ khóa `optional:` trên Config Data import có nghĩa **không thất bại chỉ vì vị trí import không tồn tại** trong ngữ cảnh đó. Nó không có nghĩa mọi property bên dưới vị trí này là optional theo business.

Nếu production cần:

~~~properties
app.partner.api-token
~~~

thì bean properties vẫn phải có required/validation riêng. Nếu file mount bị thiếu và import được đánh dấu optional, Spring có thể bỏ qua nguồn, rồi validation của token (nếu đã đăng ký đúng) mới phát hiện không có giá trị.

Ngược lại, nếu vị trí bí mật bắt buộc phải tồn tại, có thể dùng import không có `optional:` hoặc kiểm tra mount/secret reference ở deployment. Nhưng việc thư mục tồn tại cũng **chưa chứng minh đúng file và giá trị secret có mặt**.

Phân biệt:

- Optional **config location**: file/directory có thể không tồn tại.
- Optional **business property**: ứng dụng vẫn hợp lệ khi thiếu một key.
- Optional **feature**: một subsystem có thể không chạy.

## 20. Một schema cho nested object

Giả sử cấu hình:

~~~yaml
app:
  client:
    name: catalog
    connection:
      host: api.example.org
      port: 443
~~~

Java:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotBlank String name,
        @NotNull @Valid Connection connection
) {
    public record Connection(
            @NotBlank String host,
            @Min(1) @Max(65535) int port
    ) {}
}
~~~

Ở đây:

- `@NotNull` yêu cầu toàn bộ nhóm `connection` tồn tại.
- `@Valid` yêu cầu validator đi vào object con.
- `@NotBlank` yêu cầu host có nội dung.
- `@Min` và `@Max` kiểm tra khoảng port.

Một object con null không tự được tạo ra chỉ vì có `@Valid`; khi nhóm bắt buộc, `@NotNull` và cơ chế tạo nested object phải được thiết kế phù hợp.

Nếu connection chỉ cần khi feature enabled, đừng dùng `@NotNull` vô điều kiện ở root khi điều đó làm local stub mode cũng phải khai báo host. Dùng constraint có điều kiện, schema tách mode hoặc registration riêng.

## 21. List và Map: required về container lẫn phần tử

Một danh sách endpoint:

~~~yaml
app:
  gateways:
    - name: primary
      url: https://primary.example.org
    - name: backup
      url: https://backup.example.org
~~~

Java:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record GatewayProperties(
        @NotEmpty List<@Valid Gateway> gateways
) {
    public record Gateway(
            @NotBlank String name,
            @NotBlank String url
    ) {}
}
~~~

`@NotEmpty` yêu cầu danh sách có ít nhất một phần tử. `@Valid` cho phép kiểm tra các phần tử. Nếu list là optional, không dùng `@NotEmpty` trừ khi phạm vi/mode yêu cầu.

Với Map, có thể áp dụng container constraints và cascade:

~~~java
@NotEmpty Map<String, @Valid Tenant> tenants
~~~

Tuy nhiên, danh sách, Map và nested objects có semantics binding riêng. Không giả định list được merge giữa nhiều property sources; một source ưu tiên cao có thể thay thế list.

Khi yêu cầu mỗi môi trường có tối thiểu một endpoint, test trên **effective result** chứ không chỉ từng file.

## 22. Bắt buộc một boolean phải true ở production

Ví dụ policy yêu cầu TLS:

~~~java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

public record ProductionSecurityProperties(
        @NotNull @AssertTrue Boolean tlsEnabled
) {}
~~~

`@NotNull` yêu cầu có giá trị; `@AssertTrue` yêu cầu giá trị true. Lưu ý constraint `@AssertTrue` theo Bean Validation thường coi null là hợp lệ, nên kết hợp `@NotNull` nếu muốn phát hiện thiếu.

Đặt constraints này trong bean thực sự được đăng ký cho production, hoặc trong một custom constraint có điều kiện rõ ràng. Không dùng mặc định `true` nếu chính sách yêu cầu người triển khai **phải khai báo tường minh**.

Với security setting, có thể cần chính sách ở hạ tầng thay vì chỉ bean-level validation, ví dụ enforce HTTPS/TLS tại ingress hoặc service mesh.

## 23. Kiểm tra thời lượng dương

~~~java
@NotNull Duration requestTimeout
~~~

chỉ yêu cầu khác null; `0s` có thể được bind thành `Duration.ZERO` và vẫn vượt `@NotNull`.

Một cách kiểm tra trong constructor:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(Duration requestTimeout) {
    public HttpProperties {
        if (requestTimeout == null
                || requestTimeout.isZero()
                || requestTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.http.request-timeout must be positive");
        }
    }
}
~~~

Đây là invariant trong constructor. Nếu cần dùng lặp lại trên nhiều properties class, có thể viết custom Jakarta Bean Validation constraint dành riêng cho `Duration`.

Không dùng `@Positive` trực tiếp trên `Duration` và giả định provider hiểu nó như một số; `@Positive` dành cho những kiểu số tương thích theo Bean Validation.

## 24. Phát hiện khóa thừa hoặc typo

Giả sử:

~~~yaml
app:
  partner:
    connect-timeout: 3s
    max-retrise: 4
~~~

Nếu Java class chỉ có `maxRetries`, property `max-retrise` không có đích tương ứng. Binding thông thường có thể bỏ qua unknown property, để lại default và khiến người vận hành hiểu sai.

Trong namespace do một properties class sở hữu, có thể dùng:

~~~java
@ConfigurationProperties(
        prefix = "app.partner",
        ignoreUnknownFields = false
)
public record PartnerProperties(
        Duration connectTimeout,
        int maxRetries
) {}
~~~

Điều này giúp yêu cầu nghiêm ngặt hơn với các khóa không được bind trong phạm vi phù hợp. Nhưng nếu nhiều subsystem cùng dùng một prefix, bật strict unknown-field checking tại root quá rộng có thể báo những khóa hợp lệ của subsystem khác.

Tách rõ:

- **Missing required key:** một key bắt buộc không có.
- **Unknown/unbound key:** có một key nhưng schema không xử lý.
- **Invalid value:** key có nhưng conversion/validation thất bại.

Ba loại lỗi cần được test độc lập.

## 25. Không dùng `ignoreInvalidFields=true` để che lỗi

Ví dụ:

~~~java
@ConfigurationProperties(
        prefix = "app.http",
        ignoreInvalidFields = true
)
~~~

có thể làm một số lỗi binding bị bỏ qua. Nếu giá trị nhập sai mà field giữ default, ứng dụng có thể chạy với cấu hình khác ý định.

Với cấu hình quan trọng, thường nên giữ behavior chặt:

- Lỗi sai kiểu cần fail thay vì dùng default âm thầm.
- Lỗi constraint cần fail.
- Key không được bind cần được phát hiện nếu namespace yêu cầu strict.
- Có thông báo lỗi đủ rõ tên property nhưng không lộ secret.

Không dùng `ignoreInvalidFields` như một giải pháp thay thế cho required/optional policy.

## 26. Required secret theo môi trường

Ví dụ production bắt buộc token nhưng local dùng stub:

~~~yaml
# application-local.yml
app:
  partner:
    enabled: false
~~~

~~~yaml
# application-prod.yml
app:
  partner:
    enabled: true
    base-url: https://partner.example.org
    api-token: "${PARTNER_API_TOKEN}"
~~~

Trong production, token nên được cấp từ secret manager, mounted file hoặc kênh được tổ chức phê duyệt. Không ghi token thật trong YAML được commit.

Các nguyên tắc:

1. Secret phải có reference, owner, rotation policy.
2. Không log `apiToken` khi báo lỗi missing/invalid.
3. Không dùng secret thật trong unit test.
4. Khi profile không yêu cầu token, không bắt buộc tải secret production vào local.
5. Khi feature enabled, thiếu token phải bị từ chối trước khi phục vụ request.
6. Không nhầm “token có nội dung” với “token hợp lệ tại upstream”.
7. Deployment phải kiểm tra secret reference và workload permission.

Có thể dùng các sentinel giả như `TEST_ONLY_TOKEN` khi kiểm thử binding; không dùng credential có quyền thật.

## 27. Khóa optional không có nghĩa code được phép dereference null

Nếu `proxyHost` là optional:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        String proxyHost
) {}
~~~

Code sai:

~~~java
String normalized = properties.proxyHost().trim();
~~~

Nếu không cấp proxy host, lệnh có thể gây `NullPointerException`.

Code nên biểu đạt semantics rõ ràng:

~~~java
String proxyHost = properties.proxyHost();

if (proxyHost != null && !proxyHost.isBlank()) {
    configureProxy(proxyHost.trim());
} else {
    useDirectConnection();
}
~~~

Nếu null và blank mang ý nghĩa khác nhau, phải định nghĩa rõ trong schema. Ví dụ null = không có proxy; chuỗi trắng = cấu hình sai, không nên ngầm coi cả hai là một.

Một optional field có thể phải chịu constraint nếu được cấp, ví dụ proxy port phải 1–65535 nếu proxy host tồn tại. Đây là cross-field validation.

## 28. Môi trường local, test, staging và production không đồng nhất

Một chính sách mẫu:

### Local

- Cho phép mock HTTP client và database nhúng.
- Có default an toàn cho timeout/retry.
- Không dùng credential production.
- Có sample file ghi rõ giá trị giả.
- Có thể tắt optional integrations.

### Test/CI

- Test phải tái lập với giá trị được kiểm soát.
- Không phụ thuộc environment variables tình cờ có trên máy developer.
- Có test required missing, blank, invalid và config override.
- Credential dùng trong test là sentinel giả.
- Test profile production không yêu cầu kết nối đến hệ thống thật khi chỉ kiểm tra binding.

### Staging

- Tiệm cận policy production đối với required fields.
- Secret và endpoint độc lập với production.
- Validate schema, security và readiness.
- Thử nâng cấp config với app version sắp phát hành.

### Production

- Không cho phép fallback thành môi trường thử nghiệm nếu thiếu endpoint/token.
- Required fields phải fail fast.
- Secret đến từ nguồn quản lý được cấp quyền.
- Có audit của effective configuration phi bí mật.
- Có runbook rollback và tương thích app/config.

Bảng policy giúp tránh anti-pattern: “nếu không có token thì tự đổi sang anonymous mode” trong production mà không hề có quyết định thiết kế.

## 29. Một profile không phải hàng rào bảo mật

Một deployment có thể vô tình bật:

~~~properties
spring.profiles.active=local
~~~

trong production. Nếu logic required phụ thuộc hoàn toàn vào profile và local cho phép bỏ token, ứng dụng có thể khởi động ở mode không mong muốn.

Cần thiết kế các guardrails:

- Pipeline quy định profile được phép ở từng environment.
- Manifest và release record ghi profile.
- Có kiểm tra deploy-time với expected environment.
- Các secret/security invariants quan trọng không chỉ dựa vào một cờ tùy ý.
- Health/readiness phải kiểm tra những điều kiện quan trọng phù hợp.
- Không bật local stub client trong production theo đường fallback âm thầm.

Không dựa vào hostname substring để phân biệt môi trường. Sử dụng policy do nền tảng triển khai quản lý và test nó.

## 30. Kiểm thử required fields bằng `ApplicationContextRunner`

Với class:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotBlank String endpoint,
        @NotBlank String apiToken
) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class IntegrationPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(IntegrationProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void validPropertiesCreateBean() {
        runner.withPropertyValues(
                "app.integration.endpoint=https://test.example.org",
                "app.integration.api-token=TEST_ONLY_TOKEN"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            IntegrationProperties p =
                    context.getBean(IntegrationProperties.class);
            assertThat(p.endpoint())
                    .isEqualTo("https://test.example.org");
        });
    }

    @Test
    void missingTokenFails() {
        runner.withPropertyValues(
                "app.integration.endpoint=https://test.example.org"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void blankTokenFails() {
        runner.withPropertyValues(
                "app.integration.endpoint=https://test.example.org",
                "app.integration.api-token="
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

Ví dụ giả định có Spring Boot Test, AssertJ, JUnit 5 và Bean Validation provider. Trong dự án thực tế, nên assert nguyên nhân/cause chain để bảo đảm context fail vì **validation** chứ không phải lỗi thiếu dependency khác.

`ApplicationContextRunner` kiểm tra một application context nhỏ. Nó không tự chứng minh các profile-specific file được Spring Boot Config Data loader xử lý đúng trong full application; cần thêm integration test cho đường nạp cấu hình thực tế.

## 31. Test profile bằng hai registration khác nhau

Một pattern là có cấu hình production:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
@EnableConfigurationProperties(ProductionPartnerProperties.class)
class ProdRegistration {}
~~~

Và non-production:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("!prod")
@EnableConfigurationProperties(LocalPartnerProperties.class)
class NonProdRegistration {}
~~~

Để test, sử dụng `ApplicationContextRunner` với hai class registration và `withPropertyValues("spring.profiles.active=prod")` hoặc active profiles được cấu hình theo test framework. Sau đó assert:

- Production properties bean tồn tại khi profile `prod` được kích hoạt.
- Production properties bean không bị đăng ký ở non-prod.
- Missing/blank token trong prod gây startup failure.
- Local config không bắt buộc production token.
- Không có bean trùng với cùng responsibility gây ambiguity.

Nếu dùng `@ConfigurationPropertiesScan` trên các class theo môi trường, phải xác nhận scan không đăng ký cả hai ngoài ý định.

Lưu ý property `spring.profiles.active` có quy tắc về nơi được phép khai báo trong Config Data; test profile nên gần thực tế và tránh đặt nó vào tài liệu được Spring Boot giới hạn.

## 32. Test khi có nhiều nguồn override

Đôi khi file có giá trị đúng nhưng env hoặc CLI override sai.

Giả sử:

~~~yaml
app:
  partner:
    connect-timeout: 3s
~~~

Environment:

~~~text
APP_PARTNER_CONNECTTIMEOUT=0s
~~~

Theo precedence thông thường, environment có thể thắng Config Data. Nếu timeout phải dương, ứng dụng cần từ chối `0s` bằng validation/invariant.

Bộ test nên có:

1. Giá trị mặc định hợp lệ khi không cấp.
2. File profile cung cấp giá trị hợp lệ.
3. Environment override một giá trị hợp lệ.
4. Environment override giá trị invalid.
5. CLI override nếu policy cho phép.
6. Kết hợp nhiều profile.
7. Nguồn config import không tồn tại.
8. Secret reference trống hoặc không có.

Phải kiểm tra **effective value** sau binding, không chỉ sự hiện diện của key trong một nguồn riêng.

## 33. Môi trường deployment và tên biến môi trường chuẩn

Với Spring Boot, tên property canonical:

~~~text
app.partner.connect-timeout
app.partner.max-retries
app.partner.api-token
~~~

thường chuyển thành environment variable:

~~~text
APP_PARTNER_CONNECTTIMEOUT
APP_PARTNER_MAXRETRIES
APP_PARTNER_APITOKEN
~~~

Quy tắc thông dụng: thay dấu chấm bằng dấu gạch dưới, **bỏ dấu gạch ngang**, rồi viết hoa.

Sai lầm hay gặp là tự thêm underscore giữa hai phần của kebab-case:

~~~text
APP_PARTNER_CONNECT_TIMEOUT
~~~

rồi giả định nó chắc chắn tương ứng với `connect-timeout` trong mọi trường hợp. Hãy dùng quy tắc tên chuẩn của Spring Boot và kiểm thử binding của runtime đang dùng.

Những tên biến môi trường chỉ là một cơ chế cấp giá trị, **không đồng nghĩa bảo mật**. Nếu token được cấp qua environment, vẫn cần kiểm soát quyền process, debug logs và container inspection.

## 34. Tách secret-required khỏi non-secret-required

Một số field cần được log an toàn để hỗ trợ chẩn đoán:

~~~java
log.info(
        "Partner enabled={} timeoutSeconds={}",
        properties.enabled(),
        properties.connectTimeout().toSeconds()
);
~~~

Chỉ log nếu các field được phân loại không nhạy cảm.

Không làm:

~~~java
log.info("Partner configuration: {}", properties);
~~~

Java record mặc định có `toString()` có thể in cả `apiToken`. Với Lombok `@Data` và một DTO chứa secret, lỗi tương tự có thể xảy ra.

Nếu validation thiếu token, exception nên báo **tên property** và lý do, không echo token. Không dùng raw secret để tính và log hash làm “chứng minh cấu hình”, đặc biệt với credential entropy thấp.

Sự bắt buộc của một field và tính bí mật của nó là hai chiều độc lập. Một field optional vẫn có thể rất nhạy cảm nếu được cấp.

## 35. Khi thay đổi schema giữa các phiên bản ứng dụng

Giả sử phiên bản cũ dùng:

~~~properties
app.partner.retry-count=3
~~~

Phiên bản mới chuyển sang:

~~~properties
app.partner.max-retries=3
~~~

Nếu trong production còn file cũ, ứng dụng mới có thể bỏ qua `retry-count` và dùng default cho `max-retries`. Đây là rủi ro của việc nâng cấp.

Một migration plan:

1. Ghi thay đổi trong release notes và configuration contract.
2. Đánh dấu tên cũ deprecated trong metadata/tài liệu nếu phù hợp.
3. Cho phép alias/migration trong một cửa sổ tương thích nếu cần rolling deployment.
4. CI kiểm tra các file cấu hình còn dùng tên cũ.
5. Cập nhật config artifact trước hoặc cùng lúc với app version tương thích.
6. Bật strict unknown-field detection khi schema ownership cho phép.
7. Xóa hỗ trợ tên cũ sau khi mọi môi trường đã chuyển.
8. Giữ compatibility matrix và rollback plan.

`spring-boot-configuration-processor` hỗ trợ metadata cho tooling, nhưng metadata deprecation **không tự đảm bảo binder đổi mọi key cũ sang key mới**. Migration phải được thiết kế riêng.

## 36. Đừng biến default thành lớp che schema drift

Giả sử:

~~~java
@DefaultValue("2") int maxRetries
~~~

và config cũ còn:

~~~properties
app.partner.retry-count=9
~~~

Nếu app mới không biết `retry-count`, nó có thể dùng default `2` mà không báo rõ người vận hành rằng setting 9 đã bị bỏ qua.

Để tránh:

- Review schema diff trong PR.
- Dùng strict unknown fields khi phù hợp.
- Có test chạy cấu hình đã render qua app version đích.
- Không thêm default chỉ để bypass required violations.
- Giữ migration window khi thay key có ảnh hưởng lớn.
- Quan sát một số effective values phi bí mật sau rollout.

Khi lỗi xuất hiện, cần phân biệt **runtime default đã được dùng đúng thiết kế** với **default đã che một cấu hình cũ bị bỏ qua**.

## 37. Không nhầm optional import với fail-fast secret

Ví dụ một local setup:

~~~yaml
spring:
  config:
    import: "optional:file:./local-overrides.properties"
~~~

File local không có vẫn có thể hợp lệ.

Nhưng production cần một config tree bắt buộc:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Nếu vị trí không tồn tại, Spring Boot có thể báo lỗi load Config Data. Tuy nhiên, nếu thư mục tồn tại nhưng file `app.partner.api-token` thiếu, import location vẫn có thể hợp lệ. Required token cần validation.

Nếu chủ động dùng `optional:configtree:` để hỗ trợ local, không coi đó là cách bỏ mọi required property ở production. Cần chọn import policy theo environment và có test.

## 38. Đăng ký bean chỉ khi một feature thực sự hoạt động

Một thiết kế rõ ràng có thể tách:

~~~text
PartnerProperties (state và options)
          |
      enabled?
       /    \
     no      yes
     |        |
  NoOp       Validated real client
  Client     requiring endpoint + token
~~~

Trong mode disabled, thiếu endpoint và token là hợp lệ. Trong mode enabled, chúng bắt buộc.

Không nên tạo client thật rồi dùng một token rỗng khi mode disabled, vì một đường code vô tình có thể vẫn gọi upstream.

Ngược lại, nếu production policy **bắt buộc feature enabled**, kiểm tra riêng rằng production không tự dùng NoOp mode chỉ vì property `enabled` thiếu hoặc false. Một boolean default false là tiện cho local nhưng có thể không đáp ứng chính sách production.

## 39. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Prod chạy dù thiếu token | Không có validation đúng hoặc bean không được tạo | Thêm required constraint/invariant và test startup |
| `@NotNull` không bắt chuỗi whitespace | Khác null chưa đủ | Dùng `@NotBlank` |
| Thiếu `boolean enabled` nhưng không lỗi | Primitive mặc định false | Dùng `Boolean` + `@NotNull` nếu cần explicit |
| Có `@DefaultValue` nhưng giá trị nhập sai vẫn fail | Default chỉ áp dụng khi thiếu | Sửa nguồn sai, giữ validation |
| Local fail vì thiếu prod token | Dùng required constraint vô điều kiện | Tách profile/mode contract |
| Prod vào stub mode | Profile/feature flag sai hoặc default nguy hiểm | Guardrail deployment và prod-specific check |
| Missing config import nhưng app vẫn chạy | `optional:` bỏ qua location | Kiểm tra requirement của location và property riêng |
| Key sai tên, app dùng default | Unknown field bị bỏ qua | Schema validation và strict unknown checking |
| `@Valid` không bắt nested object thiếu | Cascade không yêu cầu object có mặt | Kết hợp `@NotNull` |
| `@NotNull Duration` cho phép 0s | Không kiểm tra positive | Custom validator/constructor invariant |
| Property từ YAML đúng nhưng runtime sai | Environment/CLI override | Kiểm tra effective source |
| `Optional<String>` bất ngờ null | Optional không được khuyến nghị cho properties field | Dùng nullable field rõ nghĩa |
| Test fail vì lý do khác | Chỉ assert context failed | Kiểm tra cause chain và bean |
| Đổi key khi nâng cấp làm mất giá trị | Schema migration chưa triển khai | Compatibility window, deprecation, lint |
| Log để debug lộ API token | In configuration record | Diagnostic allowlist và redaction |
| Staging pass nhưng prod fail | Overlay/secret/profile khác | Test profile matrix và production preflight |

## 40. Bài tập thực hành

### Bài 1 — Nhận biết required

Một property `app.mail.sender-name` có `String` và phải chứa ít nhất một ký tự không trắng. Annotation nào?

**Đáp án:** `@NotBlank` trong properties bean được validation phù hợp.

### Bài 2 — Boolean explicit

Prod phải khai báo `app.feature.enabled`, cho phép true hoặc false. Dùng `boolean` hay `Boolean`?

**Đáp án:** `Boolean` cùng `@NotNull`, không cấp default nếu muốn nhận biết thiếu.

### Bài 3 — Optional timeout có default

Nếu timeout không được cấp, dùng 3 giây, nhưng timeout bằng 0 phải bị từ chối. Thiết kế ra sao?

**Đáp án:** `@DefaultValue("3s")` trên `Duration` và custom positive-duration validation/constructor invariant. `@NotNull` đơn thuần không từ chối zero.

### Bài 4 — Token chỉ cần khi feature enabled

`enabled=false` và token không có; `enabled=true` và token rỗng. Trường hợp nào phải fail?

**Đáp án:** với hợp đồng điều kiện, trường hợp thứ hai phải fail; trường hợp đầu được phép nếu integration thật sự tắt.

### Bài 5 — Optional Config Data

`spring.config.import=optional:configtree:/run/secrets/` có biến `api-token` thành business-optional không?

**Đáp án:** không. `optional:` chỉ liên quan việc thiếu vị trí import. Required property phải được kiểm tra riêng.

### Bài 6 — Primitive trap

`@NotNull boolean tlsEnabled` có phát hiện key thiếu không?

**Đáp án:** không. Primitive không null; nên dùng `Boolean` và ràng buộc thích hợp khi muốn explicit declaration.

### Bài 7 — Profile production

Ứng dụng có `@Profile("prod")` trên configuration nhưng một scan khác vẫn đăng ký production properties class ở local. Vấn đề là gì?

**Đáp án:** chiến lược đăng ký bean không nhất quán. Cần kiểm soát registration và test active profiles để tránh production bean chạy ngoài profile.

### Bài 8 — Giá trị theo precedence

`application-prod.yml` có `max-retries=2`, env đặt `APP_PARTNER_MAXRETRIES=9`. Nếu constraint `@Max(5)` bật, điều gì xảy ra?

**Đáp án:** nguồn env thường ưu tiên hơn Config Data; giá trị 9 có thể được bind rồi bị validation từ chối.

### Bài 9 — List bắt buộc

Một cấu hình production phải có ít nhất một endpoint và mỗi endpoint cần name không trắng. Cần gì?

**Đáp án:** `@NotEmpty List<@Valid Endpoint>` và `@NotBlank` trên `Endpoint.name` trong properties bean được validation.

### Bài 10 — Đổi tên key

`retry-count` đổi thành `max-retries`. Có đủ nếu chỉ ghi deprecation trong metadata?

**Đáp án:** không. Cần migration code/compatibility nếu cần và cập nhật artifact cấu hình, test app/config.

### Bài 11 — Bí mật trong log

Một record có field `apiToken` được log bằng `log.info("{}", properties)`. Nguy cơ gì?

**Đáp án:** record `toString()` có thể in token thật. Tránh log object; dùng allowlist diagnostic.

### Bài 12 — Kiểm thử fail-fast

Trong `ApplicationContextRunner`, test chỉ assert `hasFailed()` khi thiếu token. Có nên bổ sung gì?

**Đáp án:** nên kiểm tra nguyên nhân trong cause chain để bảo đảm fail vì required violation, không phải một lỗi unrelated.

## 41. Checklist áp dụng cho dự án

### Thiết kế

- [ ] Có catalog property theo tên canonical và kiểu.
- [ ] Mỗi property có owner, environment requirement và default rõ ràng.
- [ ] Phân biệt missing/blank/invalid/unbound.
- [ ] Không dùng primitive khi cần phát hiện thiếu explicit.
- [ ] Không dùng default chỉ để che lỗi cấu hình.
- [ ] Điều kiện required phụ thuộc mode/feature được tài liệu hóa.
- [ ] Nested object/list/map có constraints và cascade phù hợp.
- [ ] Secret được đánh dấu nhạy cảm, không nằm trong source.

### Spring Boot implementation

- [ ] Bean được đăng ký đúng bằng scan/enable.
- [ ] Có provider Bean Validation nếu dùng Jakarta constraints.
- [ ] `@Validated` và constraints ở đúng root/field.
- [ ] Cross-field invariants được kiểm tra.
- [ ] Profile-specific registration không tạo bean ngoài dự kiến.
- [ ] Strict unknown field policy được bật trong namespace phù hợp.
- [ ] Không nuốt conversion errors bằng `ignoreInvalidFields=true` tùy tiện.
- [ ] Không dựa vào `Optional` field với giả định không được bảo đảm.

### Kiểm thử và triển khai

- [ ] Test valid, missing, blank, invalid, optional và default cases.
- [ ] Test local, test, staging và prod profiles.
- [ ] Test feature on/off.
- [ ] Test env/CLI precedence và config import.
- [ ] Test app/config schema compatibility khi đổi key.
- [ ] Có test fail-fast production token mà không dùng secret thật.
- [ ] Pipeline kiểm tra expected profile, required secret references.
- [ ] Không log cấu hình thô, token hoặc exception chứa credential.
- [ ] Rollback plan ghi app/config/secret reference tương thích.

## 42. Tóm tắt

- **Required** là một hợp đồng cụ thể về sự hiện diện và tính hợp lệ; **optional** phải có semantics khi thiếu.
- **Default** nên chỉ áp dụng khi việc thiếu được phép, không phải phương án sửa dữ liệu sai.
- `@NotNull`, `@NotBlank` và `@NotEmpty` có vai trò khác nhau.
- Khi cần nhận biết field thiếu, thường nên dùng wrapper `Boolean`/`Integer` thay vì primitive.
- Với `@ConfigurationProperties`, kết hợp `@Validated` và Bean Validation provider thích hợp.
- **Conditional required** nên dựa vào mode/feature hoặc schema riêng, không rải các `if (prod)` không kiểm soát.
- `@Profile` quyết định registration/config activation; không tự làm mọi field bắt buộc.
- **`optional:` của Config Data** chỉ nói về location, không quyết định business requirement của một key.
- **Effective configuration** có thể bị env/CLI override; kiểm tra kết quả binding thực tế.
- Optional secret vẫn là secret nếu được cấp; không log credential hoặc object cấu hình chứa nó.
- Khi nâng cấp, đổi tên key cần migration/compatibility và test theo app/config pair.
- Với production, ưu tiên fail fast cho cấu hình quan trọng, kiểm thử profile matrix và có preflight triển khai.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot — Config Data and Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing)
- [Spring Boot — Profile-specific Files](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot — `@ConditionalOnProperty` API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
