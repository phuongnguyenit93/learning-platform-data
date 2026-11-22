# Thiết kế thuộc tính bắt buộc khi tính năng bật và hành vi khi tính năng tắt

## 1. Bài toán: “bắt buộc” phải phụ thuộc trạng thái bật hay tắt

Một thư viện Spring Boot thường cung cấp tính năng tùy chọn: gửi thông báo qua HTTP, xuất báo cáo tới dịch vụ ngoài, tích hợp kho lưu trữ hoặc đồng bộ dữ liệu. Tính năng cần vài thuộc tính để hoạt động, chẳng hạn `endpoint` và `api-key`. Nhưng nếu người dùng **không bật** tích hợp đó, yêu cầu họ vẫn phải khai báo mọi thuộc tính sẽ làm ứng dụng không liên quan tới tích hợp cũng khởi động thất bại.

Hợp đồng cấu hình mong muốn:

- Khi `demo.notify.enabled=true`: phải có endpoint HTTPS hợp lệ và khóa API không rỗng; thiếu/sai thì **fail fast** ngay lúc khởi động, nêu rõ thuộc tính cần sửa. Nếu hợp lệ, thư viện mới đăng ký bean phục vụ tính năng.
- Khi `demo.notify.enabled=false`: thư viện **không tạo** bean tích hợp, không xác thực các thuộc tính chỉ dành cho tích hợp, không khởi tạo client, scheduler, connection pool hoặc mở kết nối vì tích hợp ấy.
- Khi không có khóa `demo.notify.enabled`: ví dụ này chọn **mặc định tắt** (`opt-in`), nên hành vi giống `false`. Đây là quyết định API của thư viện, không phải lựa chọn bắt buộc cho mọi thư viện.
- Khi khóa bật/tắt có giá trị sai như `tru`: cần **báo cấu hình không hợp lệ**, tránh âm thầm tắt tính năng do lỗi gõ.
- Khi người dùng cung cấp bean tự viết: cần nêu rõ thư viện có nhường bean mặc định và các thuộc tính bắt buộc còn phải kiểm tra hay không.

Mục tiêu của bài không chỉ là thêm `@NotBlank`; điều quan trọng là thiết kế đúng **ranh giới giữa điều kiện đăng ký auto-configuration, binding và validation**. Ví dụ dùng Spring Boot 3.3.x, Spring Framework 6.1 và Java 17+.

## 2. Ba câu hỏi khác nhau trong một property library

Hãy tách ba bước về mặt ý nghĩa:

1. **Có nên bật tính năng?** Đọc cờ `enabled` từ `Environment`, quyết định có tham gia cấu hình tích hợp hay không.
2. **Khi bật, dữ liệu có hợp lệ?** Bind các key thuộc tính vào đối tượng `@ConfigurationProperties`, kiểm tra thiếu, rỗng, sai kiểu và các ràng buộc nghiệp vụ.
3. **Khi dữ liệu hợp lệ, tạo thành phần nào?** Đăng ký client, adapter, filter, listener hoặc scheduler dựa trên properties hợp lệ; thường thêm `@ConditionalOnMissingBean` nếu muốn người dùng có thể override.

Đây là ba trách nhiệm khác nhau. Một property có trên classpath hoặc có mặt trong file YAML không chứng minh tính năng đã bật. Tương tự, việc thiếu `endpoint` không phải lỗi nếu tích hợp đã được tắt theo hợp đồng.

Sơ đồ quyết định:

```text
Environment: demo.notify.enabled
                |
                v
      Parse cờ enable hợp lệ?
         | không -> FAIL cấu hình
         v có
  true ----------------------------- false hoặc vắng mặt
   |                                        |
   v                                        v
Kích hoạt cấu hình tích hợp          Bỏ qua phần tích hợp
   |                                 Không bind/validate
   v                                 properties bắt buộc
Bind endpoint/api-key                      |
   |                                        v
   +-- thiếu/sai --> FAIL             Không có client do
   |                                 auto-configuration tạo
   v
Validate endpoint HTTPS,
api-key không trắng
   |
   +-- lỗi --> FAIL
   |
   v
Đăng ký NotificationClient
(nếu không có user override)
```

Cần phân biệt **lỗi cấu hình hợp lệ ở chế độ ON** với **hành vi hợp lệ ở chế độ OFF**. Nếu thư viện vừa báo lỗi thiếu token khi OFF vừa tạo client mặc định, cả điều kiện lẫn vòng đời đều có vấn đề.

## 3. Thiết kế các key và giá trị mặc định

Ví dụ thư viện gửi thông báo `demo.notify`:

| Thuộc tính | Kiểu | Mặc định/hợp đồng | Khi ON | Khi OFF |
| --- | --- | --- | --- | --- |
| `demo.notify.enabled` | boolean | `false` (opt-in) | Phải biểu đạt giá trị bật hợp lệ | `false` hoặc vắng mặt |
| `demo.notify.endpoint` | `URI` | Không có default | **Bắt buộc**, URI tuyệt đối HTTPS có host | Không bắt buộc, không dùng |
| `demo.notify.api-key` | `String` | Không có default | **Bắt buộc**, khác null/rỗng/toàn khoảng trắng | Không bắt buộc, không dùng |

Hai bản cấu hình minh họa:

**Bật, đủ dữ liệu:**

```yaml
demo:
  notify:
    enabled: true
    endpoint: https://notify.example.test/api
    api-key: demo-token
```

`demo-token` chỉ là giá trị giả dành cho bài thử. Khi triển khai thật, đưa bí mật từ secret store/biến môi trường và không commit token vào repository.

**Tắt, không cần key tích hợp:**

```yaml
demo:
  notify:
    enabled: false
```

Có thể không khai báo toàn bộ nhánh `demo.notify` vì thiết kế mặc định tắt. Một file có `enabled: false` và một `endpoint` cũ/malformed vẫn phải khởi động bình thường **nếu các thuộc tính bắt buộc chỉ được bind khi ON**. Nếu còn component khác độc lập đang dùng cùng prefix thì phải xem xét riêng; ví dụ này chỉ xét các bean do thư viện đăng ký.

Không tự cho `endpoint` hoặc token giá trị giả mặc định để “cho app lên được” khi đã bật. Với kết nối tới hệ thống thật, default nguy hiểm khiến lỗi cấu hình bị che đi hoặc client kết nối nhầm đích. Giá trị mặc định phù hợp hơn với các tùy chọn **không bắt buộc** như timeout, retry count hoặc batch size.

### 3.1. Chọn nghĩa của việc không khai báo enabled

`@ConditionalOnProperty` có hai thiết lập quan trọng:

```java
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false)
```

Ở đây:

- `prefix` và `name` ghép thành `demo.notify.enabled`.
- `havingValue="true"` yêu cầu giá trị cấu hình tương ứng với `true`; không chấp nhận các chuỗi bất kỳ như `foo`.
- `matchIfMissing=false` buộc **thiếu cờ** làm condition không khớp.
- Nếu chỉ để `@ConditionalOnProperty(prefix="demo.notify", name="enabled")` mà không có `havingValue`, điều kiện mặc định nhận mọi giá trị ngoài `false`; một giá trị gõ sai có thể vô tình bật tính năng. Vì vậy dùng `havingValue` rõ ràng.
- Nếu chuyển thành `matchIfMissing=true`, tính năng có thể tự bật khi chưa có cờ; đó là hợp đồng **default-on**, kéo theo yêu cầu phải cung cấp dữ liệu bắt buộc ngay cả lúc người dùng không chỉ định `enabled`.

Bảng hành vi của **condition trên** (chưa tính validation của cờ):

| Giá trị `enabled` trong Environment | Condition ON? | Nghĩa |
| --- | :---: | --- |
| Không có | Không | Mặc định OFF |
| `true` | Có | Kích hoạt cấu hình bắt buộc |
| `false` | Không | OFF |
| `foo`, `tru` | Không | Condition từ chối; **chưa phải báo lỗi cấu hình** |
| `"true"` dạng chuỗi trong YAML | Có | Giá trị sau khi đọc có nghĩa true |

Điểm cần nhớ: `@ConditionalOnProperty` là **bộ lọc điều kiện**, không phải một bộ validator boolean mạnh. Chỉ dùng annotation này có thể khiến `tru` bị xem giống OFF. Mục 5 đưa ra cách kiểm tra kiểu của cờ một cách độc lập.

## 4. Vì sao @NotBlank đặt sai chỗ làm ứng dụng OFF thất bại?

Giả sử viết:

```java
@Validated
@ConfigurationProperties(prefix = "demo.notify")
public record NotifyProperties(
        boolean enabled,
        @NotNull URI endpoint,
        @NotBlank String apiKey) {
}
```

rồi đăng ký toàn cục:

```java
@AutoConfiguration
@EnableConfigurationProperties(NotifyProperties.class)
public class NotifyAutoConfiguration {
}
```

**Hai đoạn này minh họa một thiết kế chưa phù hợp** nếu `endpoint`/`apiKey` chỉ bắt buộc khi ON. `@EnableConfigurationProperties` đăng ký bean cấu hình để bind và validate **bất kể ON/OFF**. Trong chế độ `enabled=false` với endpoint và key vắng mặt, `@NotNull` và `@NotBlank` vẫn có thể làm startup fail.

Tương tự, nếu `@ConfigurationPropertiesScan` ở application chủ động quét và đăng ký `NotifyProperties`, việc bạn thêm `@ConditionalOnProperty` vào **mỗi @Bean client** không ngăn props bean đã đăng ký ở nơi khác bị bind/validate.

Một thiết kế chưa đủ:

```java
@AutoConfiguration
@EnableConfigurationProperties(NotifyProperties.class)
class BrokenNotifyAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.notify",
            name = "enabled",
            havingValue = "true")
    NotificationClient notificationClient(NotifyProperties properties) {
        return new NotificationClient(
                properties.endpoint(), properties.apiKey());
    }
}
```

Condition chỉ điều khiển **bean client**. Nó không điều khiển sự tồn tại của `NotifyProperties` đã đăng ký trên class. Kết quả có thể là **OFF nhưng startup fail vì thiếu key**.

Có hai cách thiết kế hợp lý tùy yêu cầu:

1. **Chia cờ bật/tắt và properties bắt buộc thành hai lớp**, chỉ đăng ký lớp bắt buộc trong cấu hình con đã qua điều kiện. Đây là phương án bài này dùng làm ví dụ runnable; dễ đọc và giữ ranh giới OFF sạch.
2. **Bind một object luôn hiện diện nhưng validate có điều kiện** bằng custom Bean Validation như `@AssertTrue` hoặc custom validator: khi OFF cho phép trường tích hợp trống, khi ON yêu cầu đầy đủ. Phương án này hữu ích nếu ứng dụng cần đọc trạng thái cùng các tùy chọn trong một object, nhưng object vẫn được bind cả khi OFF; lỗi chuyển đổi kiểu ở một trường tùy chọn vẫn có thể xảy ra ngay cả khi validator bỏ qua trường đó.

Không có quy tắc bắt buộc “mọi thư viện phải dùng hai lớp”; điều cần đạt là **chính sách rõ ràng và được kiểm chứng**: OFF không yêu cầu key, ON không thể chạy với key thiếu/sai.

## 5. Mẫu bền vững: luôn kiểm tra cờ, chỉ bind required properties khi ON

Mẫu hoàn chỉnh dưới đây tách:

- `NotifySwitchProperties`: chỉ có cờ `enabled`, đăng ký **luôn luôn** để parse thành boolean thật; sai chính tả `tru` gây lỗi chuyển đổi/binding thay vì âm thầm OFF.
- `EnabledNotifyProperties`: chỉ tồn tại khi condition ON, chứa endpoint và token bắt buộc; bind và validate trước lúc client dùng nó.
- `NotifyAutoConfiguration.EnabledConfiguration`: nested configuration được bảo vệ bằng `@ConditionalOnProperty` ngay tại **cấp class**, nên khi OFF nó không đưa required props bean vào context.
- `NotificationClient`: bean mô phỏng adapter nhận thông tin đã validate; constructor trong ví dụ **không** tạo network connection để test độc lập.

### 5.1. Cờ typed, default OFF

```java
@Validated
@ConfigurationProperties(prefix = "demo.notify")
public record NotifySwitchProperties(
        @DefaultValue("false") boolean enabled) {
}
```

`@DefaultValue` là `org.springframework.boot.context.properties.bind.DefaultValue`. Record có một constructor canonical nên Spring Boot 3.3 tự hỗ trợ constructor binding khi bean được đăng ký qua `@EnableConfigurationProperties`; không phải thêm `@ConstructorBinding`.

Một số ý nghĩa:

- `enabled` có giá trị typed `boolean`; binder biết các biểu diễn boolean được hỗ trợ theo conversion service, và sẽ thất bại với giá trị không parse được.
- `@DefaultValue("false")` ghi rõ chính sách của thư viện dù không có key.
- Object switch không khai báo `endpoint`/`apiKey`, nên chúng không bị bind vào switch. Điều này quan trọng trong OFF.
- Dù condition đã có `havingValue="true"`, bean typed switch vẫn hữu ích để phát hiện input enable sai kiểu. Condition và binding là hai cơ chế độc lập.

### 5.2. Required properties chỉ đăng ký trong nhánh ON

```java
@Validated
@ConfigurationProperties(prefix = "demo.notify")
public record EnabledNotifyProperties(
        @NotNull URI endpoint,
        @NotBlank String apiKey) {

    @AssertTrue(message = "endpoint must be an absolute HTTPS URI with a host")
    public boolean isHttpsEndpoint() {
        return endpoint != null
                && "https".equalsIgnoreCase(endpoint.getScheme())
                && endpoint.getHost() != null;
    }
}
```

`@NotNull` kiểm tra endpoint có giá trị; binder chịu trách nhiệm chuyển chuỗi thành `URI`. `@NotBlank` chặn token thiếu, chuỗi rỗng và toàn khoảng trắng. `@AssertTrue` bổ sung ràng buộc **ngữ nghĩa**: `URI.create("relative/path")` vẫn là URI hợp lệ về cú pháp nhưng không thích hợp làm endpoint server; ví dụ yêu cầu scheme HTTPS và host.

Có thể bổ sung quy tắc path, port, allowlist hoặc thời hạn token nếu sản phẩm cần, nhưng đừng dùng một regex quá mức thay cho chuẩn URI. Các ràng buộc chỉ thật sự hoạt động nếu có **Bean Validation provider** trên classpath, ví dụ `spring-boot-starter-validation`, và bean properties được đăng ký để binder gọi validation.

### 5.3. Gắn điều kiện vào đúng ranh giới cấu hình

```java
@AutoConfiguration
@EnableConfigurationProperties(NotifySwitchProperties.class)
public class NotifyAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.notify",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @EnableConfigurationProperties(EnabledNotifyProperties.class)
    static class EnabledConfiguration {

        @Bean
        @ConditionalOnMissingBean(NotificationClient.class)
        NotificationClient notificationClient(
                EnabledNotifyProperties properties) {

            return new NotificationClient(
                    properties.endpoint(),
                    properties.apiKey());
        }
    }
}
```

Đây là **mảnh minh họa cấu trúc**; toàn bộ mã khai báo và import thực tế được cung cấp ở mục 7 dưới dạng một file test chạy được.

Cơ chế theo thứ tự:

1. Spring Boot xử lý `NotifyAutoConfiguration`. `NotifySwitchProperties` được đăng ký để bind cờ đã khai báo, cho phép phát hiện `enabled` sai kiểu.
2. Spring xem điều kiện ở `EnabledConfiguration`. Nếu `enabled` không có hoặc bằng `false`, cấu hình con không được tham gia. Vì `@EnableConfigurationProperties(EnabledNotifyProperties.class)` **nằm bên trong**, bean required properties cũng không được đăng ký từ auto-configuration này.
3. Nếu `enabled=true`, Spring đăng ký `EnabledNotifyProperties`; binder chuyển URI, Bean Validation kiểm tra các ràng buộc.
4. Nếu properties thiếu/sai, quá trình tạo context thất bại trước khi có một `NotificationClient` hoạt động. Không ghi warning rồi âm thầm dùng token null.
5. Nếu dữ liệu hợp lệ, bean client mặc định được tạo nếu chưa có bean `NotificationClient` khác và các điều kiện còn lại đều thỏa.

Lưu ý: `@ConditionalOnMissingBean` **không** thay đổi hợp đồng required props của mẫu này. Ngay cả khi người dùng tự cung cấp `NotificationClient`, nếu `enabled=true` thì `EnabledNotifyProperties` vẫn được đăng ký/validate. Đây là chính sách nhất quán “feature bật thì config hợp lệ”, kể cả khi bean client bị override. Nếu sản phẩm muốn **user override bỏ qua luôn required props**, phải đưa condition về bean missing lên cấp nested configuration (hoặc tách nhánh) và kiểm thử thứ tự phát hiện user bean; không ngầm thay đổi hành vi này.

### 5.4. OFF chính xác đến đâu?

Theo thiết kế trên, OFF có nghĩa:

- Không có `NotificationClient` do **auto-configuration** này tạo.
- Không có `EnabledNotifyProperties` do **auto-configuration** này đăng ký.
- Không cần endpoint/key và không có validation cho hai trường đó.
- Không xây dựng kết nối hoặc scheduler của feature do library cung cấp.
- Có thể vẫn có `NotifySwitchProperties` (bean nhẹ chỉ giữ cờ), vì nó phục vụ validation của chính cờ.
- Nếu ứng dụng người dùng **tự khai báo** bean `NotificationClient` độc lập, auto-configuration không được tự xóa bean ấy: “OFF” là cam kết về những gì **thư viện** quản lý, không phải quyền xóa bean của application.
- Không xóa các property khỏi `Environment`; cấu hình OFF vẫn có thể chứa key cũ. “Không bind/không dùng” không đồng nghĩa “không tồn tại văn bản trong config”.

Với tích hợp có scheduler, listener hoặc filter, điều kiện phải bao trùm **cả nhóm bean** ấy. Tắt riêng client nhưng để scheduler vẫn gửi việc vào client hoặc để health indicator tạo kết nối là chưa đạt hợp đồng OFF.

## 6. Các kiểu lỗi cần xử lý khi ON

| Trường hợp khi `enabled=true` | Tầng phát hiện | Hành vi đúng |
| --- | --- | --- |
| Thiếu `endpoint` | Bean Validation `@NotNull` | Startup fail, chỉ rõ trường cấu hình thiếu |
| `endpoint=relative/path` | Validation `@AssertTrue` | Startup fail vì không phải URL HTTPS tuyệt đối |
| `endpoint=http://...` | Validation `@AssertTrue` | Startup fail vì policy chỉ cho phép HTTPS |
| URI hỏng cú pháp, converter không parse được | Binding/conversion | Startup fail, giữ nguyên nguyên nhân conversion |
| Thiếu `api-key` | Bean Validation `@NotBlank` | Startup fail |
| `api-key="   "` | Bean Validation `@NotBlank` | Startup fail |
| Cờ `enabled=tru` | Typed binding `NotifySwitchProperties` | Startup fail do không parse boolean |
| `enabled=false` nhưng thiếu endpoint/token | Không đăng ký required props | Startup thành công, feature không được tạo |
| Không có `enabled` và không có các key khác | Default OFF | Startup thành công |
| `enabled=true`, endpoint/key đầy đủ | Binding + validation pass | Tạo bean mặc định hoặc nhường bean user theo contract |

**Fail fast** ở đây là thất bại khi xây dựng context, trước khi luồng nghiệp vụ thực sự dùng tích hợp. Một số lỗi chỉ được phát hiện lúc gọi mạng thật — DNS, TLS, HTTP 401, timeout, endpoint tạm ngừng — không thuộc phạm vi validation cấu hình. Không nên cố phát request HTTP trong Bean Validation để “kiểm tra endpoint”: điều đó khiến khởi động phụ thuộc mạng và tạo side effect không cần thiết.

Phân biệt thêm:

- **Conversion failure**: chuỗi không chuyển được sang kiểu Java, ví dụ port nhập chữ vào trường `Integer` hoặc URI sai cú pháp.
- **Constraint violation**: đã bind được kiểu nhưng vi phạm hợp đồng, ví dụ URI `http://` không được phép, apiKey chỉ có dấu cách.
- **Condition no-match**: tính năng tắt nên cấu hình con không được đăng ký. Đây không phải startup failure.

## 7. Thực hành chạy được bằng Java 17 và Spring Boot 3.3

Bài kiểm thử dùng `ApplicationContextRunner` để tạo context riêng biệt cho mỗi trạng thái. Nó không mở HTTP connection; `NotificationClient` chỉ là record mô tả client được cấu hình. Mọi test sử dụng cùng classpath, thay đúng property và user bean để xác minh ON/OFF.

### 7.1. Cấu trúc dự án

```text
conditional-required-properties-lab/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/ConditionalRequiredPropertiesTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'conditional-required-properties-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-validation:3.3.13'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

test {
    useJUnitPlatform()
}
```

Chỉ cần JDK 17+ và Gradle tương thích; plugin Java tiêu chuẩn đủ cho test. `-parameters` giữ tên tham số khi framework cần suy luận constructor. Các thành phần ở `spring-boot-starter-validation` cung cấp Jakarta Validation provider để `@NotNull`, `@NotBlank` và `@AssertTrue` có hiệu lực.

### 7.2. File JUnit 5 hoàn chỉnh

`src/test/java/demo/ConditionalRequiredPropertiesTest.java`:

```java
package demo;

import java.net.URI;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalRequiredPropertiesTest {

    @ConfigurationProperties(prefix = "demo.notify")
    public record NotifySwitchProperties(
            @DefaultValue("false") boolean enabled) {
    }

    @Validated
    @ConfigurationProperties(prefix = "demo.notify")
    public record EnabledNotifyProperties(
            @NotNull URI endpoint,
            @NotBlank String apiKey) {

        @AssertTrue(message =
                "endpoint must be an absolute HTTPS URI with a host")
        public boolean isHttpsEndpoint() {
            return endpoint != null
                    && "https".equalsIgnoreCase(endpoint.getScheme())
                    && endpoint.getHost() != null;
        }
    }

    public record NotificationClient(URI endpoint, String apiKey) {
    }

    @AutoConfiguration
    @EnableConfigurationProperties(NotifySwitchProperties.class)
    public static class NotifyAutoConfiguration {

        @Configuration(proxyBeanMethods = false)
        @ConditionalOnProperty(
                prefix = "demo.notify",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false)
        @EnableConfigurationProperties(EnabledNotifyProperties.class)
        static class EnabledConfiguration {

            @Bean
            @ConditionalOnMissingBean(NotificationClient.class)
            NotificationClient notificationClient(
                    EnabledNotifyProperties properties) {
                return new NotificationClient(
                        properties.endpoint(),
                        properties.apiKey());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        NotificationClient customNotificationClient() {
            return new NotificationClient(
                    URI.create("https://custom.example.test/api"),
                    "custom-test-token");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(NotifyAutoConfiguration.class));

    @Test
    void absentFlagMeansDisabledAndRequiresNoIntegrationSettings() {
        runner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context).hasSingleBean(NotifySwitchProperties.class);
            assertThat(context.getBean(NotifySwitchProperties.class).enabled())
                    .isFalse();
            assertThat(context).doesNotHaveBean(EnabledNotifyProperties.class);
            assertThat(context).doesNotHaveBean(NotificationClient.class);
        });
    }

    @Test
    void explicitFalseIgnoresInvalidUnusedEndpointAndMissingKey() {
        runner.withPropertyValues(
                "demo.notify.enabled=false",
                "demo.notify.endpoint=%%%")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).doesNotHaveBean(EnabledNotifyProperties.class);
                    assertThat(context).doesNotHaveBean(NotificationClient.class);
                });
    }

    @Test
    void trueWithValidSettingsCreatesExactlyOneClient() {
        runner.withPropertyValues(
                "demo.notify.enabled=true",
                "demo.notify.endpoint=https://notify.example.test/api",
                "demo.notify.api-key=demo-token")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).hasSingleBean(EnabledNotifyProperties.class);
                    assertThat(context).hasSingleBean(NotificationClient.class);
                    assertThat(context).hasBean("notificationClient");
                    assertThat(context.getBean(NotificationClient.class).endpoint())
                            .isEqualTo(URI.create(
                                    "https://notify.example.test/api"));
                    assertThat(context.getBean(NotificationClient.class).apiKey())
                            .isEqualTo("demo-token");
                });
    }

    @Test
    void trueWithoutEndpointFailsStartup() {
        runner.withPropertyValues(
                "demo.notify.enabled=true",
                "demo.notify.api-key=demo-token")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                });
    }

    @Test
    void trueWithBlankKeyFailsStartup() {
        runner.withPropertyValues(
                "demo.notify.enabled=true",
                "demo.notify.endpoint=https://notify.example.test/api",
                "demo.notify.api-key=   ")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                });
    }

    @Test
    void trueWithNonHttpsEndpointFailsStartup() {
        runner.withPropertyValues(
                "demo.notify.enabled=true",
                "demo.notify.endpoint=http://notify.example.test/api",
                "demo.notify.api-key=demo-token")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                });
    }

    @Test
    void malformedEnableFlagFailsRatherThanSilentlyDisabling() {
        runner.withPropertyValues("demo.notify.enabled=tru")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                });
    }

    @Test
    void userDefinedClientReplacesDefaultWhenEnabledAndConfigured() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .withPropertyValues(
                        "demo.notify.enabled=true",
                        "demo.notify.endpoint=https://notify.example.test/api",
                        "demo.notify.api-key=demo-token")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).hasSingleBean(NotificationClient.class);
                    assertThat(context).hasBean("customNotificationClient");
                    assertThat(context).doesNotHaveBean("notificationClient");
                    assertThat(context.getBean(NotificationClient.class).apiKey())
                            .isEqualTo("custom-test-token");
                });
    }
}
```

Chạy từ thư mục dự án (có Gradle đã cài):

```bash
gradle test --tests demo.ConditionalRequiredPropertiesTest
```

Nếu có wrapper trên Linux/macOS:

```bash
./gradlew test --tests demo.ConditionalRequiredPropertiesTest
```

Trên Windows:

```powershell
.\gradlew.bat test --tests demo.ConditionalRequiredPropertiesTest
```

**Kết quả kỳ vọng:** `test` hoàn tất với **8 test passed** khi JDK và dependencies tương thích. Đây là kết quả dự kiến từ thiết kế ví dụ; không coi log build hay stdout của Gradle là cố định và không tuyên bố bộ test đã được chạy thực tế trên máy người học.

### 7.3. Bảng giải thích tám test

| Test | Cờ | Dữ liệu | Kỳ vọng |
| --- | --- | --- | --- |
| `absentFlag...` | Thiếu | Không có endpoint/key | Startup OK, không có client |
| `explicitFalse...` | false | Endpoint hỏng, thiếu key | Startup OK, required props không bị bind |
| `trueWithValid...` | true | HTTPS + token | Startup OK, có đúng một client |
| `trueWithoutEndpoint...` | true | Thiếu endpoint | Startup FAIL (validation) |
| `trueWithBlankKey...` | true | Token chỉ khoảng trắng | Startup FAIL (validation) |
| `trueWithNonHttps...` | true | HTTP hợp cú pháp nhưng sai policy | Startup FAIL (validation) |
| `malformedEnableFlag...` | `tru` | Không cần key | Startup FAIL (typed binding cờ) |
| `userDefinedClient...` | true | HTTPS + token và user bean | Startup OK, chỉ có user client |

Test đầu tiên là quan trọng: nó chứng minh mặc định OFF **không bị ràng buộc** bởi cấu hình bắt buộc. Test thứ hai còn đi xa hơn: khi endpoint có chuỗi mà `URI` không parse được, không có bean `EnabledNotifyProperties` nên không phát sinh conversion error từ những setting không dùng. Test thứ bảy phát hiện lỗi chính tả ở cờ, một nguy cơ thường bị bỏ qua khi chỉ dùng `@ConditionalOnProperty`.

Test cuối minh họa giới hạn của `@ConditionalOnMissingBean`: nó làm client mặc định nhường user bean. **Mẫu này vẫn kiểm tra required props khi bật**, đúng chính sách đã nêu. Đừng giả định tự override client sẽ tự miễn điều kiện validation.

## 8. So sánh ba phương án thiết kế validation có điều kiện

| Thiết kế | OFF thiếu endpoint/key | ON thiếu endpoint/key | Ưu điểm | Giới hạn |
| --- | --- | --- | --- | --- |
| `@Validated @ConfigurationProperties` đăng ký toàn cục với `@NotBlank` | Có nguy cơ FAIL | FAIL | Code đơn giản | Không diễn đạt đúng “chỉ bắt buộc khi ON” |
| **Tách switch + required properties trong nested conditional config** | PASS | FAIL | Không bind/validate required fields khi OFF; rõ ownership | Cần thêm một lớp và chú ý tránh đăng ký props ở nơi khác |
| Một properties bean luôn được bind, custom `@AssertTrue` kiểm tra `!enabled || fieldsValid` | PASS nếu các giá trị bind được | FAIL | Đọc toàn bộ cấu hình từ một object | Invalid conversion có thể FAIL khi OFF; phải kiểm tra mọi nhánh logic |
| Bắt exception lúc tạo client rồi log và bỏ qua | Có thể PASS | Sai yêu cầu fail fast | Triển khai tưởng nhanh | Che lỗi vận hành, có thể để bean/feature ở trạng thái dở dang |

Với thư viện mà OFF nghĩa là **không sử dụng** bất kỳ cấu hình tích hợp nào, phương án tách lớp là lựa chọn mạnh. Với sản phẩm cần hiển thị đầy đủ cấu hình dù OFF, có thể chọn một properties bean và custom validator, nhưng phải quyết định xử lý dữ liệu không thể convert khi OFF.

### 8.1. Khi bắt buộc có điều kiện trong một object

Một thiết kế đơn giản khác (mã **minh họa**, không thay cho bộ test ở mục 7):

```java
@Validated
@ConfigurationProperties(prefix = "demo.notify")
public record CombinedNotifyProperties(
        boolean enabled,
        String endpoint,
        String apiKey) {

    @AssertTrue(message =
            "endpoint and apiKey are required when notify is enabled")
    public boolean isValidWhenEnabled() {
        if (!enabled) {
            return true;
        }
        return endpoint != null && !endpoint.isBlank()
                && apiKey != null && !apiKey.isBlank();
    }
}
```

Lớp này có thể cho phép OFF với endpoint/key trống. Tuy nhiên: endpoint dạng `String` vẫn cần parse/kiểm tra scheme riêng khi ON; nếu chuyển trường sang `URI` thì một giá trị không parse được có thể làm **binding fail kể cả OFF**. Đây là trade-off của việc luôn bind cùng một object. Nếu muốn kiểm tra điều kiện phức tạp nhiều trường, một class-level constraint riêng có thể trình bày lỗi rõ hơn `@AssertTrue`.

## 9. Ghi chú khi dùng bean override và nhiều auto-configuration

Trong thư viện thật, `@ConditionalOnMissingBean` và thứ tự auto-config có ý nghĩa:

- Spring Boot xử lý bean do ứng dụng người dùng định nghĩa trước auto-configuration trong cấu hình điển hình, nên user override thường được nhận diện.
- Nếu nhiều auto-config cung cấp cùng một type, cần khai báo `@AutoConfiguration(after=...)` hoặc `before` khi chúng phụ thuộc vào kết quả presence/missing bean.
- Điều kiện ở nested configuration nên dùng type thực sự là hợp đồng của feature. Nếu client khai báo kiểu trả về quá rộng như `Object`, `@ConditionalOnMissingBean(NotificationClient.class)` có thể không nhìn thấy ứng viên như dự kiến.
- Khi feature OFF, một custom client bean từ ứng dụng vẫn có thể tồn tại. Không nên giả mạo “OFF xóa mọi bean trong JVM”; chỉ kiểm soát bean do auto-configuration sở hữu.
- Nếu chính sách là “user bean thay thế hoàn toàn feature, nên không yêu cầu endpoint/key”, hãy đặt điều kiện missing bean bao quanh **cả phần required properties**. Điều đó làm thay đổi startup contract, nên phải có các test: ON + user client + thiếu settings, ON + không user client + thiếu settings, ON + user client + settings hợp lệ.
- Đừng để hai nhánh riêng vô tình tạo hai `NotificationClient`; assert `hasSingleBean` cùng tên bean sẽ bắt được lỗi này.

Ví dụ ý tưởng đặt điều kiện lên nested class (đây là **mảnh annotation**, không phải code file đầy đủ):

```java
@ConditionalOnProperty(
        prefix = "demo.notify", name = "enabled", havingValue = "true")
@ConditionalOnMissingBean(NotificationClient.class)
@EnableConfigurationProperties(EnabledNotifyProperties.class)
```

Nếu áp dụng variant này, `@ConditionalOnMissingBean` tại cấp class phải được kiểm chứng trong auto-configuration và thứ tự đăng ký bean của consumer. Không thêm condition ở mọi chỗ một cách tùy tiện rồi coi hai hợp đồng như nhau.

## 10. Quan sát condition và lỗi binding trong Spring Boot

Hai nguồn thông tin bổ sung cho nhau:

1. **Condition evaluation:** Vì sao nested configuration `EnabledConfiguration` được bật/bỏ qua? Dùng `ConditionEvaluationReport`, log `--debug` hoặc Actuator `/actuator/conditions` (khi đã bật/expose). Tìm điều kiện `OnPropertyCondition` liên quan `demo.notify.enabled`.
2. **Binding/validation failure:** Khi ON nhưng dữ liệu thiếu/sai, xem phần `Failed to bind properties under 'demo.notify'`, `BindException` hoặc chi tiết Bean Validation với property/reason. Condition có thể đã khớp, nhưng context vẫn fail khi tạo properties bean.

Trong một test context đã khởi động thành công, có thể lấy report:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource()
        .forEach((source, outcomes) -> {
            if (source.contains("EnabledConfiguration")) {
                System.out.println(source);
                outcomes.forEach(item -> System.out.println(
                        item.getCondition().getClass().getSimpleName()
                        + ": matched=" + item.getOutcome().isMatch()
                        + ", reason=" + item.getOutcome().getMessage()));
            }
        });
```

Đây là **đoạn minh họa nằm bên trong callback `ApplicationContextRunner`**, cần import `org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport` và biến `context` của runner. Nó không có stdout cố định; lý do condition thay đổi theo môi trường. Khi startup FAIL, ưu tiên thông điệp lỗi binding/validation và startup failure thay vì chỉ tìm report của context không khởi tạo thành công.

Bảng chẩn đoán:

| Triệu chứng | Kiểm tra đầu tiên | Kết luận nếu đã xác nhận |
| --- | --- | --- |
| OFF mà lỗi thiếu token | `EnabledNotifyProperties` có đang đăng ký toàn cục hoặc được scan không? | Required properties không được gated đúng |
| ON mà không có client, startup vẫn OK | `OnPropertyCondition`, `havingValue`, tên property và user override | Condition không khớp hoặc bean mặc định nhường user bean |
| ON sai key nhưng startup vẫn OK | Có `@Validated` và provider validation không? Props bean có thực sự tạo không? | Validation không được kích hoạt đúng |
| `enabled=tru` nhưng startup OK, feature OFF | Có typed switch bean được bind luôn không? | Cờ chỉ bị condition bỏ qua, chưa validate type |
| OFF mà vẫn kết nối mạng | Có scheduler/health check/bean khác tạo side effect không? | Chưa gated đủ phạm vi feature |
| ON fail với URI không hợp lệ | Binder conversion hoặc custom URI constraint | Fail fast đang hoạt động |
| Startup FAIL dù user client đã override | Chính sách yêu cầu props khi ON hay chỉ khi tạo default client? | Cần quyết định contract và dịch chuyển ranh giới condition nếu muốn đổi |

Không ghi giá trị bí mật ra console trong debug. Spring Boot Actuator `/actuator/configprops` có cơ chế sanitization nhưng vẫn cần cấu hình access và xử lý secret cẩn trọng; test/log nên dùng key giả và tránh `toString()` của record chứa token thật.

## 11. Lưu ý triển khai trong thư viện phát hành

1. **Đăng ký auto-configuration đúng chuẩn Boot 3.x.** Trong module phát hành, liệt kê fully qualified class name của `NotifyAutoConfiguration` tại `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Bài test dùng `AutoConfigurations.of(...)` để import trực tiếp, không cần file imports; ứng dụng thực có yêu cầu khác.
2. **Tách package/kiểm soát scan.** Đừng để ứng dụng vô tình quét và đăng ký `EnabledNotifyProperties` toàn cục khi ý định là gated. Dùng `@EnableConfigurationProperties` trong nested class có condition; nếu framework/application có `@ConfigurationPropertiesScan` rộng, cần xác minh class này có bị scan thêm hay không.
3. **Không dùng `@Component` cho record constructor-bound properties.** Spring Boot khuyến nghị đăng ký qua `@EnableConfigurationProperties` hoặc configuration-properties scanning; constructor binding record không đồng nghĩa constructor injection thông thường của Spring.
4. **Chọn prefix ổn định.** Dùng tên lowercase/kebab-case có namespace thư viện; property name trong `@ConditionalOnProperty` nên dùng dạng chuẩn, tránh hai cờ đồng nghĩa khó bảo trì.
5. **Bảo mật token.** Ưu tiên biến môi trường, secret manager, cấu hình được bảo vệ; không lưu token thật trong README, test snapshot hoặc condition log.
6. **Không chạy side effect trong validation.** Validator nên kiểm tra ràng buộc cấu hình thuần túy. Mạng và authentication là runtime concerns; nếu cần startup probe riêng, phải có chính sách retry/timeout/failure rõ ràng.
7. **Chính sách reload phải tách biệt.** `@ConditionalOnProperty` tại bootstrap không tạo cơ chế bật/tắt động. Đổi property ở runtime không tự tái áp dụng auto-configuration, không tự tạo/hủy bean. Nếu thư viện cần hot toggle, thiết kế quản lý lifecycle riêng và kiểm thử chuyển trạng thái.
8. **Dependency của provider validation.** Thư viện cần cơ chế tài liệu hóa dependency `spring-boot-starter-validation` hoặc provider Jakarta Validation tương đương. Không giả định chỉ có các annotation `jakarta.validation` là đủ để mọi constraint được áp dụng.
9. **Document cả hai phía.** Hướng dẫn vận hành phải ghi rõ default của enabled, danh sách required fields chỉ khi ON, kiểu lỗi khi thiếu, cách OFF để triển khai không phụ thuộc tích hợp và chính sách user override.
10. **Thêm metadata cho IDE nếu đóng gói library.** Spring Boot configuration processor có thể sinh metadata cho `@ConfigurationProperties`, giúp IDE gợi ý property name/type; metadata không tự thay thế validation hoặc condition.

## 12. Checklist QA cho hợp đồng ON/OFF

- [ ] Khi thiếu cờ và không có endpoint/key: ứng dụng khởi động, không có bean tính năng.
- [ ] Khi cờ là `false`, endpoint lỗi cú pháp và key thiếu: ứng dụng vẫn khởi động, vì required props không bị bind.
- [ ] Khi cờ là `true`, thiếu endpoint: startup fail với lỗi cấu hình, không có client hoạt động.
- [ ] Khi cờ là `true`, token trống/toàn khoảng trắng: startup fail.
- [ ] Khi endpoint sai scheme/host: startup fail với ràng buộc có ý nghĩa.
- [ ] Khi cờ sai chính tả: startup fail (nếu thiết kế hứa strict boolean parsing).
- [ ] Khi ON và hợp lệ: đúng một client/adapter được đăng ký.
- [ ] Khi có user bean: hành vi nhường bean và validation của properties đúng theo contract đã tài liệu hóa.
- [ ] Khi OFF: không còn scheduler, listener, bean kết nối hoặc background task do feature tự đăng ký.
- [ ] Đã kiểm tra điều kiện cấp class với `@ConditionalOnProperty`, không chỉ ở method tạo client.
- [ ] Đã chắc chắn `EnabledNotifyProperties` không được scan/đăng ký qua đường khác.
- [ ] Không có giá trị “mặc định giả” cho endpoint hoặc token để lách lỗi khi ON.

**Điểm cần nắm:** một thuộc tính chỉ thật sự **bắt buộc khi tính năng được bật** nếu quá trình đăng ký, binding và validation phản ánh được điều kiện đó. Với feature opt-in, giải pháp rõ ràng là kiểm tra cờ bật/tắt độc lập, đặt required properties trong cấu hình con có `@ConditionalOnProperty`, fail fast khi ON cấu hình sai và đảm bảo OFF không dựng các thành phần tích hợp. Test phải chứng minh cả **trường hợp được tạo** và **trường hợp có chủ đích không được tạo**, kèm chính sách khi cờ hoặc dữ liệu không hợp lệ.

## Tài liệu chính thức

- Spring Boot 3.3 — Externalized Configuration: constructor binding, `@EnableConfigurationProperties` và validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration, Property Conditions và testing: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 API — `@ConditionalOnProperty` và bảng `havingValue` / `matchIfMissing`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 API — `@ConfigurationProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Boot 3.3 API — `@EnableConfigurationProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/EnableConfigurationProperties.html
- Spring Boot 3.3 API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
