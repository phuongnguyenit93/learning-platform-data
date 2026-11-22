# `havingValue` trong `@ConditionalOnProperty`: hiểu đúng `true`, `false` và chuỗi tùy chọn

## 1. Vì sao `havingValue` quan trọng?

Trong Spring Boot Auto Configuration, một ứng dụng có thể bật hoặc tắt việc đăng ký bean bằng giá trị cấu hình. Ví dụ cùng một module xuất dữ liệu có thể chọn:

- `demo.export.enabled=true`: kích hoạt tích hợp xuất dữ liệu.
- `demo.export.enabled=false`: không đăng ký tích hợp.
- `demo.export.mode=async`: chọn kiểu xử lý bất đồng bộ.

Annotation `@ConditionalOnProperty` (package `org.springframework.boot.autoconfigure.condition`) kiểm tra giá trị từ Spring `Environment` trước khi Spring quyết định có đăng ký cấu hình hoặc bean tương ứng hay không.

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "true"
)
ExportService exportService() {
    return new ExportService();
}
~~~

Ở đây, khóa đầy đủ là `demo.export.enabled`. Chỉ khi giá trị cấu hình khớp chuỗi `"true"` thì phương thức `@Bean` mới tham gia đăng ký bean. Đoạn mã trên **chỉ là trích đoạn minh họa**: muốn biên dịch độc lập phải định nghĩa `ExportService` và đặt nó trong một class cấu hình; ví dụ kiểm thử chạy được nằm ở mục 6.

Điểm dễ sai nhất: **`havingValue` là `String`**, không phải cờ boolean Java. Bỏ `havingValue` **không tương đương** với đặt `havingValue="true"`.

## 2. Quy tắc khớp chính xác

Spring Boot 3.3 mô tả quy tắc theo giá trị property đã được tìm thấy trong `Environment`:

| Giá trị của property | Mặc định: `havingValue=""` | `havingValue="true"` | `havingValue="false"` | `havingValue="async"` |
| --- | :---: | :---: | :---: | :---: |
| `true` | Khớp | Khớp | Không | Không |
| `false` | Không | Không | Khớp | Không |
| `async` | Khớp | Không | Không | Khớp |
| `sync` | Khớp | Không | Không | Không |
| `0` | Khớp | Không | Không | Không |
| `off` | Khớp | Không | Không | Không |
| Chuỗi rỗng `""` nhưng property **có tồn tại** | Khớp | Không | Không | Không |
| Property **không tồn tại** | Không* | Không* | Không* | Không* |

*Dòng cuối giả sử `matchIfMissing=false` (mặc định). Nếu dùng `matchIfMissing=true`, property bị thiếu có thể làm điều kiện khớp dù `havingValue` được khai báo là gì; xem mục 4.

### 2.1. Không khai báo `havingValue`: “tồn tại và khác `false`”

~~~java
@ConditionalOnProperty(prefix = "demo.export", name = "enabled")
~~~

Quy tắc mặc định là:

> Khóa `demo.export.enabled` phải hiện diện, và giá trị chuỗi không bằng `"false"` (không phân biệt chữ hoa/chữ thường).

Vì vậy `true`, `yes`, `on`, `1`, `async`, `enabled` và chuỗi rỗng (nếu khóa thật sự tồn tại) **đều khớp**. Annotation không chuyển `yes/on/1` thành boolean `true`; chúng đơn giản **không phải chuỗi `false`**.

Điều này có thể trở thành lỗi cấu hình: nếu người dùng gõ `demo.export.enabled=tru`, một điều kiện mặc định vẫn khớp. Đừng dùng điều kiện mặc định khi bài toán thật sự yêu cầu boolean `true`.

### 2.2. `havingValue="true"`: chỉ nhận chuỗi `true`

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "true"
)
~~~

Kết quả:
- `demo.export.enabled=true` hoặc `TRUE` → khớp.
- `demo.export.enabled=false` → không khớp.
- `demo.export.enabled=on`, `1`, `yes`, `tru`, `enabled` → không khớp.
- Khóa bị thiếu → không khớp theo mặc định.

Đây là lựa chọn rõ ràng cho feature flag cần bật **có chủ đích**.

### 2.3. `havingValue="false"`: kích hoạt nhánh khi tắt

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "false"
)
~~~

Lúc này giá trị `false` làm **điều kiện khớp**, vì đó chính là giá trị mong đợi. Không có mâu thuẫn: điều kiện kiểm tra một chuỗi, chứ không hỏi “feature có bật không?”.

Một cách dùng hợp lý là đăng ký bean hỗ trợ hoặc triển khai fallback *khi cấu hình đã khai báo rõ* `enabled=false`. Cần nhớ: **thiếu khóa** không giống `false`. Muốn xử lý trường hợp thiếu khóa, đánh giá `matchIfMissing` và thiết kế nhánh mặc định riêng.

### 2.4. `havingValue="async"`: chuỗi do ứng dụng quy định

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "mode",
    havingValue = "async"
)
~~~

- `mode=async` hoặc `mode=ASYNC` → khớp.
- `mode=sync`, `mode=true`, `mode=false` hoặc property thiếu → không khớp.
- `havingValue="async,scheduled"` **không** có nghĩa là “async **hoặc** scheduled”: nó so sánh với một chuỗi nguyên vẹn `async,scheduled`.

Trong Spring Boot 3.3, phần so sánh giá trị của condition không phân biệt chữ hoa/chữ thường (case-insensitive). Không nên dựa vào việc tự cắt khoảng trắng hoặc tự sửa lỗi chính tả: `mode=async ` có thể không được xem là cùng giá trị `async`, tùy cách nguồn cấu hình cung cấp chuỗi. Hãy sử dụng các giá trị đã chuẩn hóa và kiểm thử nguồn cấu hình thực tế.

## 3. Cách Spring Boot đánh giá điều kiện

Cách hiểu tương đương ở mức ý tưởng:

~~~text
key = prefix + "." + name
nếu key không có trong Environment:
    trả về matchIfMissing
nếu havingValue khác chuỗi rỗng:
    trả về so sánh giá trị với havingValue, không phân biệt hoa/thường
ngược lại:
    trả về giá trị khác "false", không phân biệt hoa/thường
~~~

Đây là **mô tả thuật toán**, không phải mã Java cần sao chép vào project.

Hệ quả quan trọng:

1. Spring Boot lấy property từ `Environment` và nguồn có độ ưu tiên áp dụng, như `application.properties`/`application.yml`, biến môi trường hoặc tham số dòng lệnh. Nếu cùng một key xuất hiện nhiều nơi, condition nhận **giá trị có hiệu lực theo precedence** của `Environment`, không đọc riêng từng file để lấy mọi giá trị.
2. So sánh dựa trên **giá trị biểu diễn dạng chuỗi**. Đây không phải phép kiểm tra boolean theo những quy ước như “`0` = false”, “`on` = true”.
3. Điều kiện được xét khi Spring chuẩn bị context và đăng ký bean. Sau khi bean đã được tạo, đổi giá trị trong một file cấu hình không khiến condition tự chạy lại để thêm/xóa bean trong context hiện tại.
4. Nếu một property tồn tại nhưng có giá trị rỗng, nó khác với property không tồn tại. Với `havingValue=""`, chuỗi rỗng vẫn khớp vì nó khác `false`.
5. Với `havingValue="false"`, property `FALSE` cũng khớp. Với `havingValue="async"`, `ASYNC` khớp. Sự không phân biệt chữ hoa/chữ thường ở đây thuộc phép so sánh **value**; cách đặt tên key vẫn nên tuân thủ quy ước.

## 4. Kết hợp `matchIfMissing`, `prefix`, `name`

### 4.1. Thiếu property: `matchIfMissing` quyết định

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

Cấu hình này khớp nếu:
- `demo.export.enabled=true`; **hoặc**
- `demo.export.enabled` hoàn toàn không tồn tại trong `Environment`.

Nhưng `demo.export.enabled=false` vẫn **không khớp**, vì khóa đã tồn tại và giá trị không phải `true`.

Đây là chiến lược **default-on**. Nó có thể phù hợp cho tính năng vốn bật theo mặc định, nhưng có rủi ro khi người triển khai đánh sai tên key: thiếu property vô tình vẫn bật tính năng. Đối với chức năng tốn tài nguyên, có tác dụng bên ngoài hoặc cần được bật rõ ràng, thường chọn `havingValue="true", matchIfMissing=false`.

Đặc biệt, `matchIfMissing` **chỉ** áp dụng khi property vắng mặt. Nó không biến giá trị sai như `enabled=maybe` thành một kết quả mặc định.

### 4.2. Ghép tên property

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "true"
)
~~~

Tương ứng property:

~~~properties
demo.export.enabled=true
~~~

`prefix="demo.export"` có thể viết kèm dấu chấm cuối; Spring Boot sẽ ghép dấu phân tách khi cần. `name` và `value` là hai thuộc tính alias trong `@ConditionalOnProperty`: có thể dùng một trong hai để chỉ tên property. Nên viết key theo quy tắc **lowercase-kebab-case**, ví dụ `demo.export.fast-mode` (thay vì camelCase khi khai báo trong annotation).

### 4.3. Nhiều tên property nghĩa là AND

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

Điều kiện chỉ khớp khi **cả hai** key `demo.export.enabled` và `demo.export.audit-enabled` đều có giá trị `true`. Nếu một key là `false` hoặc thiếu (và `matchIfMissing=false`), condition không khớp.

`havingValue` được áp dụng cho **tất cả** các tên đã liệt kê. Muốn các key yêu cầu **những giá trị khác nhau**, chẳng hạn `enabled=true` và `mode=async`, cần cấu trúc điều kiện riêng phù hợp (ví dụ một class cấu hình được điều kiện hóa theo một key và phương thức bean được điều kiện hóa theo key khác, hoặc custom `Condition`), không gộp hai tên vào cùng một annotation với một `havingValue` rồi mong mỗi tên có giá trị riêng.

## 5. Cấu hình thực tế với `application.yml` và `application.properties`

Cấu hình YAML:

~~~yaml
demo:
  export:
    enabled: true
    mode: async
~~~

Tương đương theo các key cần xét:

~~~properties
demo.export.enabled=true
demo.export.mode=async
~~~

Một auto-configuration có thể định nghĩa nhánh cho từng mode:

~~~java
@AutoConfiguration
class ExportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo.export", name = "mode", havingValue = "async"
    )
    ExportEngine asyncExportEngine() {
        return new AsyncExportEngine();
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "demo.export", name = "mode", havingValue = "sync"
    )
    ExportEngine syncExportEngine() {
        return new SyncExportEngine();
    }
}
~~~

Đây là **mã kiến trúc minh họa**: `ExportEngine`, `AsyncExportEngine` và `SyncExportEngine` cần được triển khai trong ứng dụng hoặc thư viện. Với `mode=async` chỉ nhánh async khớp; với `mode=sync` chỉ nhánh sync khớp; với `mode=unknown` hoặc thiếu mode, không nhánh nào khớp nếu không thiết kế mặc định. Nếu một bean khác luôn yêu cầu `ExportEngine`, nên thêm kiểm soát giá trị cấu hình hoặc cung cấp nhánh mặc định một cách rõ ràng.

Trong ứng dụng thật, cần quyết định `enabled` có chi phối cả hai mode hay không. **Chỉ kiểm tra `mode` chưa đủ để thể hiện yêu cầu `enabled=true`.** Có thể áp dụng `@ConditionalOnProperty(prefix="demo.export", name="enabled", havingValue="true")` ở class cấu hình bao ngoài, rồi áp dụng điều kiện `mode` trên từng `@Bean`.

## 6. Test chạy được: chứng minh từng trường hợp

Ví dụ này chạy với **Java 17+ và Spring Boot 3.3**, trong một project Gradle/Maven đã có `spring-boot-starter-test` (JUnit 5, AssertJ, `ApplicationContextRunner`). Tạo file:

`src/test/java/com/example/demo/HavingValueConditionTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class HavingValueConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(FeatureAutoConfiguration.class));

    @AutoConfiguration
    static class FeatureAutoConfiguration {

        @Bean("defaultEnabled")
        @ConditionalOnProperty(prefix = "demo.feature", name = "enabled")
        String defaultEnabled() {
            return "default";
        }

        @Bean("strictEnabled")
        @ConditionalOnProperty(
                prefix = "demo.feature", name = "enabled", havingValue = "true"
        )
        String strictEnabled() {
            return "strict";
        }

        @Bean("whenDisabled")
        @ConditionalOnProperty(
                prefix = "demo.feature", name = "enabled", havingValue = "false"
        )
        String whenDisabled() {
            return "disabled";
        }

        @Bean("asyncMode")
        @ConditionalOnProperty(
                prefix = "demo.feature", name = "mode", havingValue = "async"
        )
        String asyncMode() {
            return "async";
        }

        @Bean("defaultOn")
        @ConditionalOnProperty(
                prefix = "demo.feature", name = "enabled",
                havingValue = "true", matchIfMissing = true
        )
        String defaultOn() {
            return "default-on";
        }
    }

    @Test
    void missingProperty_usesMatchIfMissingOnly() {
        runner.run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isFalse();
            assertThat(context.containsBean("strictEnabled")).isFalse();
            assertThat(context.containsBean("whenDisabled")).isFalse();
            assertThat(context.containsBean("asyncMode")).isFalse();
            assertThat(context.containsBean("defaultOn")).isTrue();
        });
    }

    @Test
    void trueProperty_matchesDefaultAndStrictTrue() {
        runner.withPropertyValues(
                "demo.feature.enabled=true",
                "demo.feature.mode=async"
        ).run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isTrue();
            assertThat(context.containsBean("strictEnabled")).isTrue();
            assertThat(context.containsBean("whenDisabled")).isFalse();
            assertThat(context.containsBean("asyncMode")).isTrue();
            assertThat(context.containsBean("defaultOn")).isTrue();
        });
    }

    @Test
    void falseProperty_matchesOnlyExplicitFalse() {
        runner.withPropertyValues(
                "demo.feature.enabled=FALSE",
                "demo.feature.mode=sync"
        ).run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isFalse();
            assertThat(context.containsBean("strictEnabled")).isFalse();
            assertThat(context.containsBean("whenDisabled")).isTrue();
            assertThat(context.containsBean("asyncMode")).isFalse();
            assertThat(context.containsBean("defaultOn")).isFalse();
        });
    }

    @Test
    void arbitraryText_matchesDefaultButNotStrictTrue() {
        runner.withPropertyValues(
                "demo.feature.enabled=on",
                "demo.feature.mode=ASYNC"
        ).run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isTrue();
            assertThat(context.containsBean("strictEnabled")).isFalse();
            assertThat(context.containsBean("whenDisabled")).isFalse();
            assertThat(context.containsBean("asyncMode")).isTrue();
            assertThat(context.containsBean("defaultOn")).isFalse();
        });
    }

    @Test
    void emptyExistingValue_isNotMissing() {
        runner.withPropertyValues("demo.feature.enabled=").run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isTrue();
            assertThat(context.containsBean("strictEnabled")).isFalse();
            assertThat(context.containsBean("whenDisabled")).isFalse();
            assertThat(context.containsBean("defaultOn")).isFalse();
        });
    }
}
~~~

Chạy trong project có Gradle wrapper và dependency test như đã nêu:

~~~bash
./gradlew test --tests "com.example.demo.HavingValueConditionTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.HavingValueConditionTest"
~~~

**Kết quả mong đợi:** 5 test PASS. Assertions kiểm tra trực tiếp bean có được đăng ký theo tên hay không; chúng không yêu cầu stdout cụ thể. Với trường hợp `enabled=on`, bean mặc định có mặt nhưng `strictEnabled` vắng mặt: đó là khác biệt cốt lõi của bài. Với `enabled=FALSE`, `whenDisabled` có mặt; với mode `ASYNC`, `asyncMode` có mặt do so sánh case-insensitive. Các bean trả về `String` chỉ là đối tượng test đơn giản để tách biệt hành vi condition khỏi nghiệp vụ.

`@AutoConfiguration` trong test được cung cấp trực tiếp cho `ApplicationContextRunner` bằng `AutoConfigurations.of(...)` nên không cần file đăng ký imports cho fixture test này. Nếu đóng gói thành auto-configuration thực sự để Spring Boot tự phát hiện, đăng ký class tương ứng trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

## 7. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách giải quyết |
| --- | --- | --- |
| `enabled=on` vẫn tạo bean dù tưởng chỉ có `true` mới bật | Bỏ trống `havingValue`, mặc định chỉ loại chuỗi `false` | Dùng `havingValue="true"` cho boolean flag nghiêm ngặt |
| `enabled=false` nhưng bean dùng `havingValue="false"` lại xuất hiện | Đã yêu cầu **khớp chính giá trị false** | Chỉ dùng cấu hình đó cho nhánh “đang tắt”; dùng `havingValue="true"` cho nhánh “đang bật” |
| Không cấu hình property mà bean không xuất hiện | `matchIfMissing=false` mặc định | Thêm property đúng key; chỉ đặt `matchIfMissing=true` khi cần default-on thực sự |
| Muốn `mode=async` hoặc `mode=queue` nhưng viết `havingValue="async,queue"` | `havingValue` không parse danh sách giá trị | Dùng điều kiện tùy chỉnh hoặc chia nhánh theo thiết kế |
| Có nhiều key trong `name` mà chỉ một key đạt | Điều kiện yêu cầu tất cả tên đều khớp | Xem từng key và giá trị, kiểm tra `matchIfMissing` |
| Ghi cấu hình một kiểu nhưng condition nhận giá trị khác | Nguồn property ưu tiên cao hơn đã ghi đè | Xem giá trị hiệu lực trong `Environment`/config data và thứ tự precedence |
| Dùng `@ConditionalOnProperty` cho một list/indexed property | Property cha và indexed key có thể không được nhìn nhận đồng nhất | Dùng `@ConfigurationProperties`/custom `Condition` cho dữ liệu phức tạp |
| Đổi file cấu hình khi app đang chạy nhưng bean không đổi | Condition chỉ đánh giá trong quá trình tạo context | Khởi động lại context hoặc thiết kế riêng cơ chế thay đổi trạng thái runtime |

Khi debug auto-configuration, có thể bật `debug=true` hoặc truyền `--debug` để xem **Condition Evaluation Report**. Với Spring Boot Actuator được cấu hình phù hợp, endpoint `/actuator/conditions` cũng có thể cho biết điều kiện match/unmatch. Khi kiểm thử, dùng `ApplicationContextRunner.withPropertyValues(...)` để tạo ma trận các giá trị, thay vì chỉ chạy một cấu hình thành công.

## 8. Nguyên tắc thiết kế thực tế

- **Feature flag boolean:** ưu tiên `@ConditionalOnProperty(name = "...", havingValue = "true")` khi cần đúng giá trị `true`. Có thể dùng `matchIfMissing=true` chỉ khi nghiệp vụ thực sự muốn mặc định bật.
- **Nhánh tắt rõ ràng:** `havingValue="false"` có ý nghĩa “khóa tồn tại và giá trị là false”, **không** đại diện mặc định cho cả trường hợp thiếu khóa.
- **Mode dạng chuỗi:** dùng `havingValue="async"` hoặc `"sync"` cho một giá trị cố định; nếu mode có nhiều nhánh, cần xác định trường hợp không hợp lệ hoặc bị thiếu. Với cấu hình phức tạp, cân nhắc `@ConfigurationProperties`, enum và validation để phát hiện lỗi sớm.
- **Tách tồn tại và giá trị:** kiểm tra property có tồn tại khác với kiểm tra boolean hay so khớp mode; việc viết rõ `havingValue` giúp người đọc hiểu ý đồ.
- **Không giả định định dạng đầu vào:** `yes`, `1`, `on` và chuỗi rỗng không có nghĩa boolean `true` trong phép so sánh `havingValue="true"`. Có thể chúng lại khiến điều kiện mặc định khớp.
- **Test cả trường hợp âm:** với mỗi condition quan trọng, kiểm chứng đủ `true`, `false`, chuỗi tùy chọn, thiếu key và giá trị bất ngờ.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — JavaDoc `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): bảng `havingValue`, thuộc tính `matchIfMissing`, `prefix`, `name`, cảnh báo collection.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): mục Property Conditions và cách kiểm thử bằng `ApplicationContextRunner`.
